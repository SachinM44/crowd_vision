"""mesh_bench.py — 5-feed sustained mesh soak (BENCHMARKS.md #2). THE headline.

OWNER: Alpha. 10-min soak: 5 synthetic feeds through ONE shared QNN (or CPU)
session using the real scheduler.py round-robin freshest-frame loop. Emits
JSON → bench/out/mesh.json with:
  - aggregate inferences/s
  - effective fps per feed (5-s rolling window at end of soak)
  - per-stage breakdown (capture/schedule/infer/decide) ms averages
  - thermal decay check: first-min vs last-min inferences/s delta (≤10% target)
  - backend badge (honest: qnn-npu-hexagon-v73 or cpu)

On the X Elite: run with --model weights/vision/yolov8n_det_int8.onnx
On dev machine (no model): run with --dry-run (synthetic detection — wiring proof)

USAGE:
    python zone-brain/bench/mesh_bench.py --dry-run          # dev / CI
    python zone-brain/bench/mesh_bench.py --duration 600     # 10-min real soak (X Elite)
    python zone-brain/bench/mesh_bench.py --duration 60      # quick 1-min smoke test
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "vision"), str(_ROOT / "engine")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detect_qnn as _det
import scheduler as _sch
import capture as _cap
from crowdvision._lib import messages as M

_OUT_DIR = Path(__file__).resolve().parent / "out"
_N_FEEDS = 5
_DEFAULT_DURATION_S = 600   # 10 minutes
_IMGSZ = 640


# ---------------------------------------------------------------------------
# Synthetic feed (no real cameras or MQTT needed for the bench)
# ---------------------------------------------------------------------------

class _SyntheticFeed:
    """Mimics capture.CaptureFeed with advancing timestamps."""

    def __init__(self, camera_id: str, fps: float = 12.0):
        self.camera_id = camera_id
        self._fps = fps
        self._frame_ms = 1000.0 / fps
        self._ts = 0.0
        self._last_served = -1.0
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._image = np.zeros((_IMGSZ, _IMGSZ, 3), dtype=np.uint8)

    def start(self) -> "_SyntheticFeed":
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name=f"synth-{self.camera_id}")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            with self._lock:
                self._ts += self._frame_ms
            time.sleep(self._frame_ms / 1000.0)

    def latest(self):
        with self._lock:
            ts = self._ts
        if ts == self._last_served:
            return None   # stale: freshest-frame scheduler drops it
        self._last_served = ts
        return _cap.Frame(self.camera_id, ts, self._image, "sim")

    def health(self):
        return _cap.FeedHealth(self.camera_id, "sim", f"{_IMGSZ}x{_IMGSZ}",
                               self._fps, 0.0, 0.0, M.FEED_OK, 0)


# ---------------------------------------------------------------------------
# Thermal / throughput tracker
# ---------------------------------------------------------------------------

class _ThroughputTracker:
    """Records per-minute inference counts for the thermal-decay check."""

    def __init__(self):
        self._buckets: deque = deque()   # (minute_index, count)
        self._lock = threading.Lock()
        self._t0 = time.monotonic()
        self._count = 0

    def record(self) -> None:
        with self._lock:
            self._count += 1
            minute = int((time.monotonic() - self._t0) / 60.0)
            if self._buckets and self._buckets[-1][0] == minute:
                lst = list(self._buckets)
                lst[-1] = (minute, lst[-1][1] + 1)
                self._buckets = deque(lst)
            else:
                self._buckets.append((minute, 1))

    def total(self) -> int:
        with self._lock:
            return self._count

    def decay_pct(self) -> float | None:
        """Thermal decay: (first_min_rate - last_min_rate) / first_min_rate * 100."""
        with self._lock:
            bkts = list(self._buckets)
        if len(bkts) < 2:
            return None
        first = bkts[0][1]
        last = bkts[-1][1]
        if first == 0:
            return None
        return round((first - last) / first * 100.0, 1)


def main(model_path: str | None = None, duration_s: float = _DEFAULT_DURATION_S,
         dry_run: bool = False) -> int:
    if not dry_run:
        if model_path is None:
            model_path = str(_ROOT.parent / "weights" / "vision" / "yolov8n_det_int8.onnx")
        if not Path(model_path).exists():
            print(f"[mesh_bench] model not found: {model_path}")
            print("  Use --dry-run for a wiring-only bench, or stage the model first.")
            return 1

    print(f"[mesh_bench] {_N_FEEDS}-feed soak  duration={duration_s:.0f}s  "
          f"dry_run={dry_run}")

    # Build session.
    if dry_run:
        backend = M.BACKEND_SIM   # honest: no real NPU/CPU inference runs in --dry-run
        session = None

        def _fake_detect(sess, image):
            return [], [(1.0, 1.0)], 5.0   # 5 ms synthetic latency
        detect_fn = _fake_detect
    else:
        session = _det.build_session(model_path, require_npu=False)
        backend = _det.active_backend(session)
        detect_fn = None   # scheduler uses detect_qnn.detect by default

    # 5 synthetic feeds.
    feeds = [_SyntheticFeed(f"c{i+1}", fps=12.0).start() for i in range(_N_FEEDS)]

    # Throughput tracker.
    tt = _ThroughputTracker()

    # Scheduler callback: just count frames (no MQTT needed for the bench).
    def on_result(camera_id, frame, detections, latency_ms):
        tt.record()

    # Capture first-minute inferences/s separately.
    first_min_end_s = 60.0
    first_min_count = 0
    first_min_done = False

    t_start = time.monotonic()
    stop = threading.Event()

    sch = _sch.Scheduler(feeds, session, on_result,
                         detect_fn=detect_fn if dry_run else None)

    def _run_loop():
        sch.run(stop_event=stop)

    t = threading.Thread(target=_run_loop, daemon=True, name="sched")
    t.start()

    try:
        while True:
            elapsed = time.monotonic() - t_start
            if elapsed >= duration_s:
                break
            if not first_min_done and elapsed >= first_min_end_s:
                first_min_count = sch.frames
                first_min_done = True
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[mesh_bench] interrupted")
    finally:
        stop.set()
        for f in feeds:
            f.stop()

    elapsed_s = time.monotonic() - t_start
    counters = sch.counters()
    total_frames = counters["frames"]
    agg_inf_per_s = counters["aggregate_inferences_per_s"]

    fps_per_feed = {}
    for feed in feeds:
        fps_per_feed[feed.camera_id] = sch.fps_effective(feed.camera_id,
                                                          window_ms=5000.0)

    # First-min vs last-min comparison.
    last_min_count = total_frames - (first_min_count if first_min_done else 0)
    first_rate = first_min_count / min(first_min_end_s, elapsed_s)
    last_rate = last_min_count / max(elapsed_s - first_min_end_s, 1.0)
    thermal_decay_pct = tt.decay_pct()

    result = {
        "bench": "mesh",
        "backend": backend,
        "duration_s": round(elapsed_s, 1),
        "n_feeds": _N_FEEDS,
        "total_frames": total_frames,
        "aggregate_inferences_per_s": agg_inf_per_s,
        "effective_fps_per_feed": fps_per_feed,
        "stage_ms_avg": counters["stage_ms_avg"],
        "thermal": {
            "first_min_rate": round(first_rate, 2),
            "last_min_rate": round(last_rate, 2),
            "decay_pct": thermal_decay_pct,
            "pass": thermal_decay_pct is None or thermal_decay_pct <= 10.0,
        },
        "dry_run": dry_run,
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = _OUT_DIR / "mesh.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\n[mesh_bench] {total_frames} frames / {elapsed_s:.0f}s "
          f"= {agg_inf_per_s} inf/s  backend={backend}")
    print(f"  fps/feed: { {k: v for k, v in fps_per_feed.items()} }")
    print(f"  stage_ms_avg: {counters['stage_ms_avg']}")
    if thermal_decay_pct is not None:
        flag = "PASS" if thermal_decay_pct <= 10.0 else "WARN: THERMAL DECAY"
        print(f"  thermal decay: {thermal_decay_pct:.1f}%  {flag}")
    else:
        print("  thermal decay: insufficient data (run >=2 min)")
    print(f"[mesh_bench] -> {out}")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Alpha 5-feed mesh soak bench")
    ap.add_argument("--model", default=None, help="Path to ONNX model")
    ap.add_argument("--duration", type=float, default=_DEFAULT_DURATION_S,
                    help="Soak duration in seconds (default: 600)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Synthetic detection — no model needed (wiring proof)")
    args = ap.parse_args()
    raise SystemExit(main(args.model, args.duration, args.dry_run))
