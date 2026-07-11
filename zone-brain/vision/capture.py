"""zone-brain/vision/capture.py — multi-source capture + per-feed watchdog.

OWNER: Alpha. Reads N sources (file / webcam / RTSP) from config/cameras.yaml and
provides the freshest frame per feed to scheduler.py. Owns the per-feed watchdog:
reconnect with exponential backoff, stale-frame detector, and honest health states.

PUBLISHES (per docs/MESSAGES.md #2):
  topic  cv/camera/{camera_id}/health   (~0.2 Hz/feed)
  payload {camera_id, transport, resolution, fps_effective, drop_rate_pct,
           last_frame_age_ms, state:"OK"|"DEGRADED"|"LOST", reconnects, note}

STALE-FEED POLICY (Hard Rule 7): frame age > stale_lost_s ⇒ state LOST ⇒ density.py
emits that zone as UNKNOWN, gates hold, operator alerted. Never silently guess.

cv2 is lazily imported (Hard Rule 8). The frame `reader` is injectable so the
watchdog/health logic is testable headless (and swaps to cv2.VideoCapture live).

CONTRACT:
  open_all() -> list[CaptureFeed]
  CaptureFeed.latest() -> Frame | None   (freshest, never a queued stale frame)
  CaptureFeed.health() -> FeedHealth
  publish_health(node, feeds) -> None
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np  # noqa: F401  (contract type)

from crowdvision._lib import messages as M, config as C

DEGRADED_AGE_MS = 2000.0
BACKOFF_MAX_S = 5.0


@dataclass
class Frame:
    camera_id: str
    ts_ms: float
    image: "np.ndarray"
    transport: str


@dataclass
class FeedHealth:
    camera_id: str
    transport: str
    resolution: str
    fps_effective: float
    drop_rate_pct: float
    last_frame_age_ms: float
    state: str  # OK | DEGRADED | LOST
    reconnects: int


def _stale_lost_ms() -> float:
    pred = C.zones().get("predictor", {})
    return float(pred.get("stale_lost_s", 10)) * 1000.0


def _cv2_reader(url, transport):
    """Default reader factory backed by cv2.VideoCapture (lazy import)."""
    import cv2
    src = int(url) if transport == "webcam" and str(url).isdigit() else url
    cap = cv2.VideoCapture(src)

    def read():
        if not cap.isOpened():
            return False, None
        ok, frame = cap.read()
        if ok and transport == "file" and frame is None:  # loop files
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        return ok, frame

    def reopen():
        cap.release()
        return _cv2_reader(url, transport)

    read.reopen = reopen  # type: ignore[attr-defined]
    return read


class CaptureFeed:
    """One camera source with a watchdog."""

    def __init__(self, camera_id: str, profile: dict, *, reader=None, clock=None):
        self.camera_id = camera_id
        self.transport = profile.get("transport", "file")
        self.url = profile.get("url", "")
        self.resolution = profile.get("resolution",
                                      C.cameras().get("defaults", {}).get("resolution", "640x480"))
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self._reader = reader if reader is not None else _cv2_reader(self.url, self.transport)
        self._latest: Optional[Frame] = None
        self._last_ts = self._clock()
        self._frames = deque()      # ts of recent successful reads (fps window)
        self._reads = 0
        self._drops = 0
        self.reconnects = 0
        self._backoff = 0.5
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- one watchdog iteration (factored out so tests drive it deterministically)
    def _tick(self) -> None:
        now = self._clock()
        try:
            ok, frame = self._reader()
        except Exception:  # noqa: BLE001
            ok, frame = False, None
        self._reads += 1
        if ok and frame is not None:
            self._latest = Frame(self.camera_id, now, frame, self.transport)
            self._last_ts = now
            self._frames.append(now)
            while self._frames and now - self._frames[0] > 5000.0:
                self._frames.popleft()
            self._backoff = 0.5
        else:
            self._drops += 1
            self._reconnect()

    def _reconnect(self) -> None:
        self.reconnects += 1
        reopen = getattr(self._reader, "reopen", None)
        if reopen:
            try:
                self._reader = reopen()
            except Exception:  # noqa: BLE001
                pass
        self._backoff = min(self._backoff * 2, BACKOFF_MAX_S)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._tick()
            # sleep a frame period, or the backoff after a failure
            self._stop.wait(self._backoff if self._drops and not self._latest else 0.08)

    def start(self) -> "CaptureFeed":
        self._thread = threading.Thread(target=self._loop, name=f"cap-{self.camera_id}",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def latest(self) -> Optional[Frame]:
        """Freshest frame, or None if stale/LOST (never a queued stale frame)."""
        if self._latest is None:
            return None
        if self._clock() - self._latest.ts_ms > _stale_lost_ms():
            return None
        return self._latest

    def health(self) -> FeedHealth:
        now = self._clock()
        age = now - self._last_ts
        fps = len(self._frames) / 5.0
        drop_pct = (100.0 * self._drops / self._reads) if self._reads else 0.0
        if age > _stale_lost_ms():
            state = M.FEED_LOST
        elif age > DEGRADED_AGE_MS or drop_pct > 5.0:
            state = M.FEED_DEGRADED
        else:
            state = M.FEED_OK
        return FeedHealth(self.camera_id, self.transport, self.resolution,
                          round(fps, 2), round(drop_pct, 2), round(age, 1),
                          state, self.reconnects)


def open_all(*, reader_factory=None) -> list[CaptureFeed]:
    """Open every camera in config/cameras.yaml and start its watchdog."""
    feeds = []
    for cid, profile in C.cameras().get("cameras", {}).items():
        reader = reader_factory(cid, profile) if reader_factory else None
        feeds.append(CaptureFeed(cid, profile, reader=reader).start())
    return feeds


def publish_health(node, feeds) -> None:
    """Publish camera.health for every feed (docs/MESSAGES.md #2)."""
    for f in feeds:
        h = f.health()
        node.publish(M.topic_camera_health(h.camera_id), M.T_CAMERA_HEALTH, {
            "camera_id": h.camera_id, "transport": h.transport,
            "resolution": h.resolution, "fps_effective": h.fps_effective,
            "drop_rate_pct": h.drop_rate_pct, "last_frame_age_ms": h.last_frame_age_ms,
            "state": h.state, "reconnects": h.reconnects, "note": h.state}, qos=0)


def _selftest() -> int:
    clock = {"t": 0.0}
    frames = {"remaining": 3}

    def reader():
        if frames["remaining"] > 0:
            frames["remaining"] -= 1
            return True, np.zeros((480, 640, 3), np.uint8)
        return False, None

    feed = CaptureFeed("c1", {"transport": "rtsp", "url": "rtsp://x"},
                       reader=reader, clock=lambda: clock["t"])
    for _ in range(3):                     # three good frames
        feed._tick()
        clock["t"] += 100.0
    assert feed.latest() is not None and feed.health().state == M.FEED_OK
    # source dies: reconnect attempts increment, then age crosses stale_lost -> LOST.
    for _ in range(3):
        feed._tick()
    assert feed.reconnects >= 3, feed.reconnects
    clock["t"] += _stale_lost_ms() + 1000.0
    assert feed.latest() is None, "stale frame must not be served"
    assert feed.health().state == M.FEED_LOST, feed.health().state
    print(f"capture.py selftest OK: OK -> LOST after stale, reconnects={feed.reconnects}, "
          "stale frame withheld")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
