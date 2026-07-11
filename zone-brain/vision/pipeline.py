"""zone-brain/vision/pipeline.py — thin orchestrator: the Alpha kill-shot loop.

OWNER: Alpha. Wires every Alpha module into one running process:

  capture.py  →  scheduler.py  →  detect_qnn.py  →  homography.py
  →  tracker.py  →  gatelines.py  →  density.py (stamps risk via engine/)
  →  playbooks.py (emits gate.command on transitions)

plus camera.health at ~0.2 Hz and — critically — a status loop that publishes
risk=UNKNOWN for any LOST feed (Hard Rule 7), since on_result only runs on fresh
frames and a dead feed would otherwise fall silent.

This file is intentionally thin — every piece of logic lives in the module it
belongs to. Badges are honest (Hard Rule 2): the inference_backend comes from
detect_qnn.active_backend(session) on hardware, and "sim-replay" for the scripted
--dry-run (which runs no model at all).

USAGE:
    # dev wiring + kill-shot proof (no cameras, no model, needs a broker):
    python zone-brain/vision/pipeline.py --dry-run --max-iters 40
    # production (X Elite, QNN EP present, model staged):
    python zone-brain/vision/pipeline.py --require-npu
"""
from __future__ import annotations

import argparse
import math
import sys
import threading
import time
from pathlib import Path

import numpy as np

# Resolve sibling vision + engine dirs so imports work when run as a script.
_HERE = Path(__file__).resolve().parent
_ENGINE = _HERE.parent / "engine"
for _p in [str(_HERE), str(_ENGINE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crowdvision._lib import messages as M, config as C
from crowdvision._lib.mqttc import MqttNode

import capture as _cap
import detect_qnn as _det
import homography as _hom
import tracker as _trk
import gatelines as _gat
import density as _den
import scheduler as _sch
import playbooks as _pb
import risk as _risk

_DEFAULT_MODEL = "weights/vision/yolov8n_det_int8.onnx"
_HEALTH_INTERVAL_S = 5.0   # camera.health + LOST-zone status ~0.2 Hz


def _zones_for_camera(zone_cfg: dict, camera_id: str) -> list[str]:
    return [zid for zid, z in zone_cfg.get("zones", {}).items()
            if z.get("camera_id") == camera_id]


def _make_on_result(node, feeds, zone_states, hom_map, zone_cfg, cam_cfg,
                    *, backend: str, model_id: str, fps_fn) -> callable:
    """The per-frame callback that runs the post-detect chain. One closure keeps
    all shared state (per-camera trackers + gate lines)."""
    tracker_states: dict = {}                 # camera_id -> TrackSet (one PER camera)
    gate_lines: dict = {}                     # camera_id -> GateLine (real gate cams)
    cam_gate: dict = {}                       # gate-camera -> the gate_id it watches
    gate_counts: dict = {}                    # gate_id -> (in,out,method) — shared across cams
    for cid, profile in cam_cfg.get("cameras", {}).items():
        if profile.get("gate_line"):
            gate_lines[cid] = _gat.GateLine(profile["gate_line"],
                                            method="real-gate-line/c4",
                                            direction=1, window_s=60.0)
            cam_gate[cid] = profile.get("gate_id")

    def on_result(camera_id, frame, detections, latency_ms):
        _boxes, heads_px = detections
        H = hom_map.get(camera_id)
        heads_m = _hom.to_floor(H, heads_px) if (H is not None and len(heads_px)) else []

        tracks = _trk.update(tracker_states.setdefault(camera_id, _trk.new_tracks()),
                             heads_m, ts_ms=frame.ts_ms)

        # A dedicated gate-lane camera (e.g. c4 for Gate 3) feeds REAL line-crossing
        # counts into the shared store, keyed by the gate_id it watches — so the
        # zone whose gate that is (zone A / G3) reports real-gate-line, not virtual.
        gl = gate_lines.get(camera_id)
        if gl is not None:
            c = gl.block(tracks, frame.ts_ms)         # step every frame (window stays fresh)
            if getattr(tracks, "tracks", None):        # only publish counts we actually saw
                gate_counts[cam_gate.get(camera_id)] = (
                    c["gateline_in_per_min"], c["gateline_out_per_min"], c["method"])

        badges = {"model_id": model_id, "inference_backend": backend,
                  "latency_ms": round(latency_ms, 2)}
        feed = next((f for f in feeds if f.camera_id == camera_id), None)
        feed_health = feed.health() if feed else None

        for zid in _zones_for_camera(zone_cfg, camera_id):
            zgate = zone_cfg["zones"][zid].get("gate_id")
            gate_flow = gate_counts.get(zgate)        # real gate line if a cam supplied it, else None -> virtual
            env = _den.publish_zone(node, zid, heads_m, feed_health, badges,
                                    risk_state=zone_states[zid], gate_flow=gate_flow,
                                    fps_effective=fps_fn(camera_id), ts_ms=frame.ts_ms)
            p = env["payload"]
            _pb.fire_if_needed(node, zid, p.get("risk"),
                               p.get("density_per_m2") or 0.0,
                               float(p.get("trend_per_min", 0.0)), p.get("ttt_red_s"))

    return on_result


def _status_loop(node, feeds, zone_cfg, zone_states, model_id, backend,
                 stop: threading.Event) -> None:
    """camera.health for every feed + risk=UNKNOWN for LOST feeds (Hard Rule 7).

    on_result cannot publish a lost zone (no fresh frame arrives), so the stale
    zone would go silent without this — the operator must still see UNKNOWN and
    gates must hold, never a guessed density."""
    badges = {"model_id": model_id, "inference_backend": backend, "latency_ms": 0.0}
    while not stop.is_set():
        _cap.publish_health(node, feeds)
        for f in feeds:
            h = f.health()
            if h.state == M.FEED_LOST:
                for zid in _zones_for_camera(zone_cfg, f.camera_id):
                    _den.publish_zone(node, zid, [], h, badges,
                                      risk_state=zone_states[zid],
                                      ts_ms=time.monotonic() * 1000.0)
        stop.wait(_HEALTH_INTERVAL_S)


# --------------------------------------------------------------------------
# --dry-run: scripted feeds that actually drive the kill-shot (zone A surge),
# so the full chain (density -> risk -> playbook -> gate.command) is provable
# with no cameras and no model. Detection is scripted, so the badge is honestly
# "sim-replay" — never a claimed NPU/CPU inference.
# --------------------------------------------------------------------------

def _scatter(rect, n: int) -> list:
    """n head points on a grid inside rect=(x0,y0,x1,y1) (floor metres)."""
    if n <= 0:
        return []
    x0, y0, x1, y1 = rect
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    pts = []
    for k in range(n):
        c, r = k % cols, k // cols
        pts.append((x0 + (c + 0.5) / cols * (x1 - x0),
                    y0 + (r + 0.5) / rows * (y1 - y0)))
    return pts


def _surge(i: int) -> float:
    """Zone-A density over a repeating cycle (1 frame = 1 s): GREEN→AMBER→RED→recover.

    The ramp is deliberately gradual (20 frames) so the real engine's EWMA + 5 s
    dwell commits AMBER (→ P1 early divert) before RED (→ P2), instead of jumping
    straight through — the escalation is the demo's whole point.
    """
    x = i % 50
    if x < 5:
        return 0.4
    if x < 25:
        return 0.4 + (x - 5) / 20.0 * 5.2      # ramp 0.4 -> 5.6 over 20 frames
    if x < 33:
        return 5.6                             # hold RED
    if x < 45:
        return 5.6 - (x - 33) / 12.0 * 5.1     # recover -> 0.5
    return 0.5


def _dry_scenario_factory(zone_cfg, cam_cfg):
    """camera_id -> rect/area, so scripted head counts land inside zone polygons."""
    rects, areas, surge_cam = {}, {}, {}
    for zid, z in zone_cfg.get("zones", {}).items():
        cid = z.get("camera_id")
        poly = z.get("polygon", [])
        if not cid or not poly:
            continue
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        # inset a little so points sit strictly inside the polygon
        rects[cid] = (min(xs) + 0.3, min(ys) + 0.3, max(xs) - 0.3, max(ys) - 0.3)
        areas[cid] = float(z.get("area_m2", 20.0))
        surge_cam[cid] = (zid == "A")
    idle = {"c1": 0.4, "c2": 1.5, "c3": 2.2}

    def scenario(camera_id, i):
        if camera_id not in rects:
            return []                          # e.g. c4 (gate lane, no zone) -> no heads
        z = cam_cfg  # unused; kept for clarity
        d = _surge(i) if surge_cam.get(camera_id) else idle.get(camera_id, 0.6)
        return _scatter(rects[camera_id], int(round(d * areas[camera_id])))

    return scenario


class _DryFrame:
    def __init__(self, camera_id, ts_ms, heads):
        self.camera_id = camera_id
        self.ts_ms = ts_ms
        self.image = heads          # in dry-run the "image" carries the scripted heads
        self.transport = "sim"


class _DryFeed:
    def __init__(self, camera_id, scenario, step_ms=1000.0):
        self.camera_id = camera_id
        self._scenario = scenario
        self._step = step_ms
        self._i = 0
        self._ts = 0.0

    def latest(self):
        self._i += 1
        self._ts += self._step
        return _DryFrame(self.camera_id, self._ts, self._scenario(self.camera_id, self._i))

    def health(self):
        return _cap.FeedHealth(self.camera_id, "sim", "640x480", 1.0, 0.0, 0.0,
                               M.FEED_OK, 0)


def _dry_detect(_session, image):
    """Scripted 'detection': the frame already carries head points (floor metres)."""
    return [], list(image), 5.0


def run(*, model_path: str = _DEFAULT_MODEL, require_npu: bool = False,
        dry_run: bool = False, max_iters: int | None = None,
        host: str = "127.0.0.1") -> None:
    """Start the full Alpha pipeline; blocks until Ctrl+C or max_iters."""
    zone_cfg, cam_cfg = C.zones(), C.cameras()
    node = MqttNode("zonebrain-A", host=host).connect()

    hom_map = {cid: _hom.load(cid) for cid in cam_cfg.get("cameras", {})}
    zone_states = {zid: _risk.new_state() for zid in zone_cfg.get("zones", {})}

    if dry_run:
        scenario = _dry_scenario_factory(zone_cfg, cam_cfg)
        feeds = [_DryFeed(cid, scenario) for cid in cam_cfg.get("cameras", {})]
        session, detect_fn = None, _dry_detect
        backend, model_id = M.BACKEND_SIM, "scripted-pipeline"
        print("[pipeline] dry-run: scripted surge feeds, no model — backend "
              f"'{backend}' (honest: no NPU/CPU inference ran)")
    else:
        print(f"[pipeline] building shared session: {model_path} require_npu={require_npu}")
        session = _det.build_session(model_path, require_npu=require_npu)
        detect_fn = None                       # scheduler uses detect_qnn.detect
        backend, model_id = _det.active_backend(session), _det.MODEL_ID
        feeds = _cap.open_all()
        print(f"[pipeline] backend: {backend}; {len(feeds)} feeds open")

    on_result = _make_on_result(node, feeds, zone_states, hom_map, zone_cfg, cam_cfg,
                                backend=backend, model_id=model_id,
                                fps_fn=_sch.fps_effective)

    stop = threading.Event()
    threading.Thread(target=_status_loop,
                     args=(node, feeds, zone_cfg, zone_states, model_id, backend, stop),
                     daemon=True, name="status-pub").start()

    print(f"[pipeline] running ({'dry-run' if dry_run else 'live'}); Ctrl+C to stop")
    try:
        _sch.run(feeds, session, on_result, detect_fn=detect_fn,
                 stop_event=stop, max_iters=max_iters)
    except KeyboardInterrupt:
        print("\n[pipeline] KeyboardInterrupt — shutting down")
    finally:
        stop.set()
        for f in feeds:
            if hasattr(f, "stop"):
                f.stop()
        if _sch._CURRENT is not None:
            print(f"[pipeline] counters: {_sch._CURRENT.counters()}")
        node.disconnect()
        print("[pipeline] clean shutdown")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Alpha vision pipeline")
    ap.add_argument("--require-npu", action="store_true",
                    help="Hard-fail if the QNN NPU EP is absent (demo path)")
    ap.add_argument("--model", default=_DEFAULT_MODEL, help="Path to YOLOv8 INT8 ONNX")
    ap.add_argument("--dry-run", action="store_true",
                    help="Scripted surge feeds + scripted detector (no model, no cameras)")
    ap.add_argument("--host", default="127.0.0.1", help="MQTT broker host")
    ap.add_argument("--max-iters", type=int, default=None,
                    help="Stop after N scheduler rounds (automated tests)")
    args = ap.parse_args()
    run(model_path=args.model, require_npu=args.require_npu, dry_run=args.dry_run,
        max_iters=args.max_iters, host=args.host)
