"""tools/live_capture.py — REAL camera bridge with person detection + boxes.

OWNER: Gamma. A CPU/dev stand-in for Alpha's NPU vision pipeline. Opens real
cameras from config/cameras.yaml, runs YOLOv8n person detection on the laptop
CPU (boxes around people -> count -> density), draws the boxes onto the frame for
the dashboard preview, and publishes the SAME messages the sim does
(zone.density.update + camera.health) on the MESSAGES.md contract.

HONEST BADGES (Hard Rule 2): inference_backend="cpu", model_id="yolov8n-cpu".
Same idea as the shipped pipeline (YOLOv8 person detection -> count -> density);
the only difference is CPU here vs the Snapdragon NPU there. If YOLO isn't
installed it falls back to a motion-occupancy proxy (model_id="motion-cpu").

Per-feed watchdog: reconnect w/ backoff; stale > 10 s => zone UNKNOWN; a covered/
dark lens => UNKNOWN (we can't see -> we don't guess).

Standalone:  python tools/live_capture.py
             python -m crowdvision.sim --live       # + broker + dashboard + loop
"""
from __future__ import annotations

import sys
import threading
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crowdvision._lib import mqttc, messages as M, config, framebus  # noqa: E402
from crowdvision.sim.sim_feeds import risk_for                        # noqa: E402

STALE_LOST_S = 10.0
DENSITY_AT_FULL = 8.0                 # motion fallback: occupancy 1.0 -> 8 /m^2
PLACEHOLDER_TOKENS = ("PHONE_", "_IP")
YOLO_WEIGHTS = Path(__file__).resolve().parents[1] / "weights" / "vision" / "yolov8n.pt"
YOLO_URLS = [
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
    "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt",
]


def _is_blocked(frame) -> bool:
    """Covered lens / blank view -> we can't see the zone."""
    g = cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY)
    return bool(g.mean() < 15 or g.std() < 8)


class YoloDetector:
    """YOLOv8n person detection (CPU). Returns boxes + count."""
    model_id = "yolov8n-cpu"

    def __init__(self, conf: float = 0.35, imgsz: int = 480):
        from ultralytics import YOLO
        import logging
        logging.getLogger("ultralytics").setLevel(logging.ERROR)
        self.model = YOLO(str(YOLO_WEIGHTS))
        self.conf = conf
        self.imgsz = imgsz
        self._lock = threading.Lock()   # torch model shared across feed threads

    def detect(self, frame) -> dict:
        t0 = time.perf_counter()
        if _is_blocked(frame):
            return {"count": None, "boxes": [], "blocked": True,
                    "ms": round((time.perf_counter() - t0) * 1000, 1)}
        with self._lock:
            r = self.model(frame, classes=[0], conf=self.conf, imgsz=self.imgsz,
                           verbose=False)[0]
        boxes = (r.boxes.xyxy.cpu().numpy().astype(int).tolist()
                 if r.boxes is not None else [])
        return {"count": len(boxes), "boxes": boxes, "blocked": False,
                "ms": round((time.perf_counter() - t0) * 1000, 1)}


class MotionDetector:
    """Fallback occupancy proxy (no YOLO). No boxes."""
    model_id = "motion-cpu"

    def __init__(self):
        self.ref = None
        self.seen = 0

    def detect(self, frame) -> dict:
        t0 = time.perf_counter()
        blocked = _is_blocked(frame)
        g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (320, 240)),
                                          cv2.COLOR_BGR2GRAY), (21, 21), 0)
        if self.ref is None or self.seen < 15:
            if self.ref is None:
                self.ref = g.astype("float32")
            else:
                cv2.accumulateWeighted(g, self.ref, 0.25)
            self.seen += 1
            return {"count": None, "occupancy": 0.0, "boxes": [],
                    "blocked": blocked, "ms": round((time.perf_counter() - t0) * 1000, 1)}
        diff = cv2.absdiff(g, cv2.convertScaleAbs(self.ref))
        _, th = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        occ = float(np.count_nonzero(th)) / th.size
        return {"count": None, "occupancy": min(occ, 1.0), "boxes": [],
                "blocked": blocked, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def ensure_yolo_weights() -> bool:
    if YOLO_WEIGHTS.exists() and YOLO_WEIGHTS.stat().st_size > 100000:
        return True
    YOLO_WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    for u in YOLO_URLS:
        try:
            urllib.request.urlretrieve(u, YOLO_WEIGHTS)
            if YOLO_WEIGHTS.stat().st_size > 100000:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def make_detector():
    """YOLO if available, else the motion fallback."""
    try:
        import ultralytics  # noqa: F401
        if ensure_yolo_weights():
            det = YoloDetector()
            print("[live] detector: YOLOv8n person detection (CPU) — boxes on")
            return det
    except Exception as exc:  # noqa: BLE001
        print(f"[live] YOLO unavailable ({exc}); using motion fallback")
    print("[live] detector: motion-occupancy fallback (no boxes) — "
          "pip install ultralytics for person boxes")
    return MotionDetector()


# --- frame sources ---------------------------------------------------------
class _CapSource:
    def __init__(self, cap):
        self.cap = cap

    def read(self):
        return self.cap.read() if self.cap is not None else (False, None)

    def release(self):
        try:
            self.cap.release()
        except Exception:  # noqa: BLE001
            pass


class _SnapshotSource:
    """Poll a still-JPEG URL (IP Webcam /shot.jpg) — robust over slow links."""
    def __init__(self, shot_url, timeout=4.0):
        self.url = shot_url
        self.timeout = timeout

    def read(self):
        try:
            data = urllib.request.urlopen(self.url, timeout=self.timeout).read()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            return (img is not None), img
        except Exception:  # noqa: BLE001
            return False, None

    def release(self):
        pass


class LiveFeed:
    def __init__(self, node, camera_id, profile, zone_id, area_m2, bands, detector):
        self.node = node
        self.camera_id = camera_id
        self.profile = profile
        self.zone_id = zone_id
        self.area_m2 = area_m2
        self.amber = float(bands.get("amber_at", 3.0))
        self.red = float(bands.get("red_at", 5.0))
        self.det = detector
        self._stop = threading.Event()
        self.reconnects = 0

    def _open(self):
        transport = (self.profile.get("transport") or "").lower()
        url = self.profile.get("url")
        if transport in ("snapshot", "ipwebcam") or \
                (isinstance(url, str) and url.endswith(".jpg")):
            shot = url if (isinstance(url, str) and url.endswith(".jpg")) \
                else f"{str(url).rstrip('/')}/shot.jpg"
            return _SnapshotSource(shot)
        if transport == "webcam":
            idx = int(url) if str(url).isdigit() else 0
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if sys.platform == "win32" \
                else cv2.VideoCapture(idx)
        else:
            cap = cv2.VideoCapture(url)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # noqa: BLE001
            pass
        return _CapSource(cap)

    def _annotate(self, frame, res, density, risk):
        img = frame.copy()
        for (x1, y1, x2, y2) in res.get("boxes", []):
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cnt = res.get("count")
        who = f"people:{cnt}" if cnt is not None else f"occ:{int((res.get('occupancy') or 0)*100)}%"
        if res.get("blocked"):
            who = "VIEW BLOCKED"
        label = f"{self.camera_id} -> Zone {self.zone_id}  {who}  [{risk}]"
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, 0), (w, 26), (0, 0, 0), -1)
        cv2.putText(img, label, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (0, 255, 0), 2)
        nw = 480
        small = cv2.resize(img, (nw, int(h * nw / w)))
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            framebus.put(self.camera_id, buf.tobytes())

    def _publish_unknown(self, fps, transport, note):
        self.node.publish(M.topic_zone_density(self.zone_id), M.T_ZONE_DENSITY,
                          {"zone_id": self.zone_id, "camera_id": self.camera_id,
                           "transport": transport, "fps_effective": round(fps, 1),
                           "people_count": None, "area_m2": self.area_m2,
                           "density_per_m2": None, "trend_per_min": 0.0,
                           "ttt_red_s": None, "risk": M.RISK_UNKNOWN,
                           "model_id": self.det.model_id,
                           "inference_backend": M.BACKEND_CPU, "latency_ms": 0.0}, qos=0)
        self.node.publish(M.topic_camera_health(self.camera_id), M.T_CAMERA_HEALTH,
                          {"camera_id": self.camera_id, "transport": transport,
                           "resolution": "?", "fps_effective": round(fps, 1),
                           "drop_rate_pct": 0.0, "last_frame_age_ms": 0,
                           "state": M.FEED_DEGRADED, "reconnects": self.reconnects,
                           "note": note}, qos=0)

    def _loop(self):
        src = self._open()
        last_frame = time.monotonic()
        last_pub = 0.0
        frames = 0
        prev_density = 0.0
        backoff = 0.5
        latest = None
        transport = self.profile.get("transport", "?")
        while not self._stop.is_set():
            ok, frame = src.read()
            now = time.monotonic()
            if not ok or frame is None:
                if now - last_frame > STALE_LOST_S:
                    self._publish_unknown(0.0, transport, M.FEED_LOST)
                src.release()
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
                self.reconnects += 1
                src = self._open()
                continue
            backoff = 0.5
            last_frame = now
            frames += 1
            latest = frame
            if now - last_pub >= 1.0 and latest is not None:
                fps = frames / max(now - last_pub, 1e-6)
                frames = 0
                try:
                    res = self.det.detect(latest)
                except Exception as exc:  # noqa: BLE001
                    # A detector crash must NEVER silently kill this feed's
                    # thread (that leaves the zone with no messages at all —
                    # worse than an honest UNKNOWN). Log, degrade to the
                    # motion fallback, keep the loop alive (Hard Rule 7).
                    print(f"[live] {self.camera_id}: detector crashed "
                          f"({type(exc).__name__}: {exc}) -> motion fallback")
                    self.det = MotionDetector()
                    self._publish_unknown(fps, transport, "detector crashed")
                    last_pub = now
                    continue
                if res.get("blocked"):
                    self._annotate(latest, res, 0, M.RISK_UNKNOWN)
                    self._publish_unknown(fps, transport, "view blocked/dark")
                    last_pub = now
                    continue
                if res.get("count") is not None:            # YOLO: count -> density
                    count = res["count"]
                    # demo-scaled: ~3 detected people => RED so a small test reacts.
                    # (Alpha's real pipeline uses homography for true people/m^2.)
                    density = round(count * (self.red / 3.0), 2)
                    people = count
                else:                                       # motion fallback
                    density = round((res.get("occupancy") or 0.0) * DENSITY_AT_FULL, 2)
                    people = int(round(density * self.area_m2))
                trend = round((density - prev_density) * 60.0, 2)
                prev_density = density
                risk = risk_for(density, self.amber, self.red)
                ttt = int((self.red - density) / max(trend / 60.0, 1e-6)) \
                    if trend > 0 and density < self.red else None
                self._annotate(latest, res, density, risk)
                self.node.publish(
                    M.topic_zone_density(self.zone_id), M.T_ZONE_DENSITY,
                    {"zone_id": self.zone_id, "camera_id": self.camera_id,
                     "transport": transport, "fps_effective": round(fps, 1),
                     "people_count": people, "area_m2": self.area_m2,
                     "density_per_m2": density, "trend_per_min": trend,
                     "ttt_red_s": ttt, "risk": risk, "temp_c": 0.0,
                     "temp_source": "n/a", "model_id": self.det.model_id,
                     "inference_backend": M.BACKEND_CPU, "latency_ms": res.get("ms", 0.0)},
                    qos=0)
                self.node.publish(
                    M.topic_camera_health(self.camera_id), M.T_CAMERA_HEALTH,
                    {"camera_id": self.camera_id, "transport": transport,
                     "resolution": f"{latest.shape[1]}x{latest.shape[0]}",
                     "fps_effective": round(fps, 1), "drop_rate_pct": 0.0,
                     "last_frame_age_ms": int((now - last_frame) * 1000),
                     "state": M.FEED_OK, "reconnects": self.reconnects,
                     "note": M.FEED_OK}, qos=0)
                last_pub = now
        src.release()

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
    detector = make_detector()          # shared across feeds
    feeds = []
    for cid, prof in cams.items():
        zid = prof.get("zone_id")
        if zid not in zones:
            continue
        url = str(prof.get("url", ""))
        if any(tok in url for tok in PLACEHOLDER_TOKENS):
            print(f"[live] skipping {cid}: placeholder url ({url})")
            continue
        if (prof.get("transport") or "").lower() == "file":
            fpath = url if Path(url).is_absolute() else config.repo_root() / url
            if not Path(fpath).exists():
                print(f"[live] skipping {cid}: file not found ({url})")
                continue
        area = float(zones[zid].get("area_m2", 20.0))
        feeds.append(LiveFeed(node, cid, prof, zid, area, bands, detector).start())
        print(f"[live] {cid} -> zone {zid}  source={prof.get('transport')}:{prof.get('url')}")
    if not feeds:
        print("[live] no real cameras configured -- edit config/cameras.yaml")
    return LiveCapture(feeds)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="live camera bridge (standalone)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="broker host — from WSL use the Windows host IP "
                         "(ip route show default), never 127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    args = ap.parse_args()
    cap = run(host=args.host, port=args.port)
    print("[live] capturing real video -> detection -> MQTT. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cap.stop()
