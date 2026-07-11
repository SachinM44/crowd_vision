"""tools/live_capture.py — REAL camera bridge (RTSP / webcam / file -> density).

OWNER: Gamma. A CPU/dev stand-in for Alpha's NPU vision pipeline: it opens real
camera sources from config/cameras.yaml, estimates per-zone crowd level from the
live video (MOG2 motion-occupancy), and publishes the SAME messages the sim does
(zone.density.update + camera.health) on the MESSAGES.md contract. So the whole
dashboard + react/inform loop runs on REAL video, with zero extra downloads.

HONEST BADGES (Hard Rule 2): inference_backend="cpu", model_id="motion-occupancy".
This is an occupancy PROXY, not a true per-person count — Alpha's YOLOv8-on-NPU
(zone-brain/vision/*) is the production counter; it publishes the identical
messages, so swapping it in changes nothing downstream.

Per-feed watchdog: reconnect with backoff; stale > 10 s => zone UNKNOWN, honest
OK/DEGRADED/LOST (Hard Rule 7).

Standalone:  python tools/live_capture.py            # all cameras in cameras.yaml
             python -m crowdvision.sim --live        # + broker + dashboard + loop
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crowdvision._lib import mqttc, messages as M, config      # noqa: E402
from crowdvision.sim.sim_feeds import risk_for                 # noqa: E402

STALE_LOST_S = 10.0            # Hard Rule 7
DENSITY_AT_FULL = 8.0         # occupancy ratio 1.0 -> 8 /m^2 (so a busy frame => RED)
PLACEHOLDER_TOKENS = ("PHONE_", "_IP")   # un-configured URLs in the template


def _source(profile: dict):
    """Resolve a cameras.yaml profile to a cv2.VideoCapture argument."""
    transport = (profile.get("transport") or "").lower()
    url = profile.get("url")
    if transport == "webcam":
        idx = int(url) if str(url).isdigit() else 0
        return idx, transport
    return url, transport


class MotionDetector:
    """Occupancy from reference-frame differencing. CPU, zero downloads.

    Warms up on the (empty) scene to learn a background reference, then reports
    the fraction of the frame that differs from it — people who hold still keep
    registering (unlike MOG2, which fades them). Auto-recalibrates the baseline
    when the scene stays empty, so lighting drift doesn't accumulate. Start with
    the scene EMPTY for ~2 s, then people walk in.
    """
    model_id = "motion-occupancy"

    def __init__(self, warmup: int = 20, diff_thresh: int = 25,
                 empty_ratio: float = 0.02, recal_after: int = 40):
        self.ref = None          # float32 background reference (grayscale)
        self.seen = 0
        self.warmup = warmup
        self.thr = diff_thresh
        self.empty_ratio = empty_ratio
        self.recal_after = recal_after
        self._low_streak = 0

    def _prep(self, frame):
        g = cv2.cvtColor(cv2.resize(frame, (320, 240)), cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(g, (21, 21), 0)

    def occupancy(self, frame) -> tuple[float, float]:
        t0 = time.perf_counter()
        g = self._prep(frame)
        ms = lambda: round((time.perf_counter() - t0) * 1000, 1)  # noqa: E731
        if self.ref is None:
            self.ref = g.astype("float32")
            self.seen = 1
            return 0.0, ms()                       # no spurious RED on frame 1
        if self.seen < self.warmup:                # build the empty-scene baseline
            cv2.accumulateWeighted(g, self.ref, 0.25)
            self.seen += 1
            return 0.0, ms()
        ref8 = cv2.convertScaleAbs(self.ref)
        diff = cv2.absdiff(g, ref8)
        _, th = cv2.threshold(diff, self.thr, 255, cv2.THRESH_BINARY)
        ratio = float(np.count_nonzero(th)) / th.size
        if ratio < self.empty_ratio:               # scene empty -> refresh baseline
            self._low_streak += 1
            if self._low_streak >= self.recal_after:
                cv2.accumulateWeighted(g, self.ref, 0.05)
        else:
            self._low_streak = 0
        return min(ratio, 1.0), ms()


class LiveFeed:
    def __init__(self, node, camera_id, profile, zone_id, area_m2, bands):
        self.node = node
        self.camera_id = camera_id
        self.profile = profile
        self.zone_id = zone_id
        self.area_m2 = area_m2
        self.amber = float(bands.get("amber_at", 3.0))
        self.red = float(bands.get("red_at", 5.0))
        self.det = MotionDetector()
        self._stop = threading.Event()
        self.reconnects = 0
        # Pace file sources to ~real speed; stream sources are paced by the camera.
        transport = (profile.get("transport") or "").lower()
        self._min_dt = 1 / 12.0 if transport in ("file",) else 0.01

    def _open(self):
        arg, transport = _source(self.profile)
        if transport == "webcam" and sys.platform == "win32":
            cap = cv2.VideoCapture(arg, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(arg)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # noqa: BLE001
            pass
        return cap

    def _publish_lost(self):
        self.node.publish(M.topic_camera_health(self.camera_id), M.T_CAMERA_HEALTH,
                          {"camera_id": self.camera_id,
                           "transport": self.profile.get("transport", "?"),
                           "resolution": "?", "fps_effective": 0.0,
                           "drop_rate_pct": 100.0, "last_frame_age_ms": 99999,
                           "state": M.FEED_LOST, "reconnects": self.reconnects,
                           "note": M.FEED_LOST}, qos=0)
        # Stale-feed policy: zone UNKNOWN, no guessed number.
        self.node.publish(M.topic_zone_density(self.zone_id), M.T_ZONE_DENSITY,
                          {"zone_id": self.zone_id, "camera_id": self.camera_id,
                           "transport": self.profile.get("transport", "?"),
                           "fps_effective": 0.0, "people_count": None,
                           "area_m2": self.area_m2, "density_per_m2": None,
                           "trend_per_min": 0.0, "ttt_red_s": None,
                           "risk": M.RISK_UNKNOWN,
                           "model_id": "motion-occupancy",
                           "inference_backend": M.BACKEND_CPU, "latency_ms": 0.0}, qos=0)

    def _loop(self):
        cap = self._open()
        last_frame = time.monotonic()
        last_pub = 0.0
        frames = 0
        occ = 0.0
        prev_density = 0.0
        backoff = 0.5
        while not self._stop.is_set():
            ok, frame = cap.read() if cap is not None else (False, None)
            now = time.monotonic()
            if not ok or frame is None:
                if now - last_frame > STALE_LOST_S:
                    self._publish_lost()
                try:
                    cap.release()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
                self.reconnects += 1
                cap = self._open()
                continue
            backoff = 0.5
            last_frame = now
            frames += 1
            time.sleep(self._min_dt)       # pace files; negligible for live streams
            occ, det_ms = self.det.occupancy(frame)
            if now - last_pub >= 1.0:
                fps = frames / max(now - last_pub, 1e-6)
                frames = 0
                density = round(occ * DENSITY_AT_FULL, 2)
                trend = round((density - prev_density) * 60.0, 2)
                prev_density = density
                risk = risk_for(density, self.amber, self.red)
                ttt = int((self.red - density) / max(trend / 60.0, 1e-6)) \
                    if trend > 0 and density < self.red else None
                self.node.publish(
                    M.topic_zone_density(self.zone_id), M.T_ZONE_DENSITY,
                    {"zone_id": self.zone_id, "camera_id": self.camera_id,
                     "transport": self.profile.get("transport", "?"),
                     "fps_effective": round(fps, 1),
                     "people_count": int(round(density * self.area_m2)),
                     "area_m2": self.area_m2, "density_per_m2": density,
                     "trend_per_min": trend, "ttt_red_s": ttt, "risk": risk,
                     "temp_c": 0.0, "temp_source": "n/a",
                     "model_id": "motion-occupancy",
                     "inference_backend": M.BACKEND_CPU, "latency_ms": det_ms}, qos=0)
                self.node.publish(
                    M.topic_camera_health(self.camera_id), M.T_CAMERA_HEALTH,
                    {"camera_id": self.camera_id,
                     "transport": self.profile.get("transport", "?"),
                     "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
                     "fps_effective": round(fps, 1), "drop_rate_pct": 0.0,
                     "last_frame_age_ms": int((now - last_frame) * 1000),
                     "state": M.FEED_OK, "reconnects": self.reconnects,
                     "note": M.FEED_OK}, qos=0)
                last_pub = now
        try:
            cap.release()
        except Exception:  # noqa: BLE001
            pass

    def start(self):
        threading.Thread(target=self._loop, name=f"live-{self.camera_id}",
                         daemon=True).start()
        return self

    def stop(self):
        self._stop.set()


class LiveCapture:
    def __init__(self, feeds):
        self.feeds = feeds

    def stop(self):
        for f in self.feeds:
            f.stop()


def run(host="127.0.0.1", port=1883) -> LiveCapture:
    zcfg = config.zones()
    zones = zcfg.get("zones", {})
    bands = zcfg.get("risk_bands_default", {})
    cams = config.cameras().get("cameras", {})
    node = mqttc.MqttNode("live-capture", host=host, port=port).connect()
    time.sleep(0.2)
    feeds = []
    for cid, prof in cams.items():
        zid = prof.get("zone_id")
        if zid not in zones:
            continue                              # e.g. c4 gate-lane: not a density zone
        url = str(prof.get("url", ""))
        if any(tok in url for tok in PLACEHOLDER_TOKENS):
            print(f"[live] skipping {cid}: url still a placeholder ({url}) "
                  f"-- set a real RTSP/MJPEG URL in config/cameras.yaml")
            continue
        if (prof.get("transport") or "").lower() == "file":
            fpath = url if Path(url).is_absolute() else config.repo_root() / url
            if not Path(fpath).exists():
                print(f"[live] skipping {cid}: file not found ({url}) "
                      f"-- use --surge for a scripted zone, or map a real camera")
                continue
        area = float(zones[zid].get("area_m2", 20.0))
        feeds.append(LiveFeed(node, cid, prof, zid, area, bands).start())
        print(f"[live] {cid} -> zone {zid}  source={prof.get('transport')}:{prof.get('url')}")
    if not feeds:
        print("[live] no real cameras configured -- edit config/cameras.yaml "
              "(set transport+url for c1..c4 or a webcam).")
    return LiveCapture(feeds)


if __name__ == "__main__":
    cap = run()
    print("[live] capturing real video -> MQTT. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cap.stop()
