"""zone-brain/vision/scheduler.py — shared-session round-robin, freshest-frame.

OWNER: Alpha. THE headline Technical-40 mechanism. One shared QNN session (see
detect_qnn.py) services all feeds via a round-robin, freshest-frame scheduler:
each feed contributes its NEWEST frame; stale frames are dropped, never queued.
NOT 5 parallel sessions (NPU contention), NOT batch>1 (kills per-frame determinism).

Target: ~10–25 ms/frame ⇒ ~50–75 inferences/s aggregate ⇒ 10–15 effective fps/feed
across 5 feeds. Per-stage counters (capture/schedule/infer/decide) + effective fps
per feed are exposed for zone-brain/bench/mesh_bench.py.

INPUT: capture.CaptureFeed[] (each .latest()), one detect session, and an
on_result(camera_id, frame, detections, latency_ms) callback (density/tracker/
gatelines/playbooks run inside it).
"""
from __future__ import annotations

import time
from collections import deque


class Scheduler:
    def __init__(self, feeds, session, on_result, *, detect_fn=None,
                 clock=None):
        self.feeds = feeds
        self.session = session
        self.on_result = on_result
        self._detect = detect_fn
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self._last_ts: dict[str, float] = {}          # freshest-frame guard
        self._result_ts: dict[str, deque] = {}        # per-cam result times (fps)
        self.frames = 0
        self.stage_ms = {"capture": 0.0, "schedule": 0.0, "infer": 0.0, "decide": 0.0}
        self.t_start = self._clock()

    def _detect_fn(self):
        if self._detect is not None:
            return self._detect
        import detect_qnn  # sibling (script dir on sys.path)
        return detect_qnn.detect

    def _one_feed(self, feed) -> bool:
        cid = feed.camera_id
        t0 = self._clock()
        frame = feed.latest()                          # capture stage
        t1 = self._clock()
        self.stage_ms["capture"] += t1 - t0
        if frame is None or self._last_ts.get(cid) == frame.ts_ms:
            return False                               # stale/no new frame -> drop
        self._last_ts[cid] = frame.ts_ms

        det = self._detect_fn()
        t_i0 = self._clock()
        boxes, heads, infer_ms = det(self.session, frame.image)
        t_i1 = self._clock()
        self.stage_ms["schedule"] += t_i0 - t1         # bookkeeping between stages
        self.stage_ms["infer"] += t_i1 - t_i0          # wall-clock inference time

        self.on_result(cid, frame, (boxes, heads), infer_ms)
        t3 = self._clock()
        self.stage_ms["decide"] += t3 - t_i1

        self.frames += 1
        self._result_ts.setdefault(cid, deque()).append(t3)
        return True

    def tick(self) -> int:
        """One round-robin pass over all feeds; returns #frames processed."""
        n = 0
        for feed in self.feeds:
            if self._one_feed(feed):
                n += 1
        return n

    def run(self, *, stop_event=None, max_iters=None, idle_sleep=0.02) -> None:
        i = 0
        while stop_event is None or not stop_event.is_set():
            processed = self.tick()
            i += 1
            if max_iters is not None and i >= max_iters:
                break
            if processed == 0:
                time.sleep(idle_sleep)

    def fps_effective(self, camera_id: str, window_ms: float = 5000.0) -> float:
        dq = self._result_ts.get(camera_id)
        if not dq:
            return 0.0
        now = self._clock()
        while dq and now - dq[0] > window_ms:
            dq.popleft()
        return round(len(dq) / (window_ms / 1000.0), 2)

    def counters(self) -> dict:
        elapsed_s = max((self._clock() - self.t_start) / 1000.0, 1e-6)
        per = {k: (v / self.frames if self.frames else 0.0)
               for k, v in self.stage_ms.items()}
        return {"frames": self.frames,
                "aggregate_inferences_per_s": round(self.frames / elapsed_s, 2),
                "stage_ms_avg": {k: round(v, 3) for k, v in per.items()}}


_CURRENT: Scheduler | None = None


def run(feeds, session, on_result, *, detect_fn=None, stop_event=None,
        max_iters=None) -> Scheduler:
    """Round-robin freshest-frame loop (module entry; keeps the last Scheduler)."""
    global _CURRENT
    _CURRENT = Scheduler(feeds, session, on_result, detect_fn=detect_fn)
    _CURRENT.run(stop_event=stop_event, max_iters=max_iters)
    return _CURRENT


def fps_effective(camera_id: str) -> float:
    """Rolling effective fps for a feed (goes into zone.density.update)."""
    return _CURRENT.fps_effective(camera_id) if _CURRENT else 0.0


def _selftest() -> int:
    from dataclasses import dataclass

    @dataclass
    class FakeFrame:
        camera_id: str
        ts_ms: float
        image: object
        transport: str = "sim"

    class FakeFeed:
        def __init__(self, cid):
            self.camera_id = cid
            self._ts = 0.0
            self._advance = True

        def latest(self):
            if self._advance:
                self._ts += 100.0
            return FakeFrame(self.camera_id, self._ts, None)

    def fake_detect(session, image):
        return [], [(1.0, 1.0), (2.0, 2.0)], 12.0     # 2 heads, 12 ms

    got = []
    feeds = [FakeFeed("c1"), FakeFeed("c2")]
    sch = Scheduler(feeds, session=None, on_result=lambda c, f, d, ms: got.append((c, len(d[1]), ms)),
                    detect_fn=fake_detect)
    sch.run(max_iters=5)
    assert sch.frames == 10, sch.frames                 # 2 feeds x 5 rounds
    assert got.count(("c1", 2, 12.0)) == 5, got         # heads + reported infer_ms threaded through
    # freshest-frame: if a feed stops advancing, its unchanged frame is dropped.
    feeds[0]._advance = False
    before = sch.frames
    sch.tick()
    assert sch.frames == before + 1, "stale (unchanged-ts) frame must be dropped"
    stages = sch.counters()["stage_ms_avg"]
    assert sch.fps_effective("c1") > 0 and all(v >= 0 for v in stages.values()), stages
    print(f"scheduler.py selftest OK: {sch.frames} frames, stale-drop works, "
          f"reported infer_ms threaded to density, stage_ms_avg={stages}")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
