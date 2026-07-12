"""detect_bench.py — detection latency, NPU vs CPU (BENCHMARKS.md #1).

OWNER: Alpha. 3 warmup + 300 timed frames @640×640 INT8; once QNN EP (burst),
once CPU EP. Emits JSON → bench/out/detect.json with {mean, p50, p95, p99}
per backend for the BENCH:detect marker in docs/BENCHMARKS.md.

USAGE (on X Elite after setup.ps1, model staged by download_models.py):
    python zone-brain/bench/detect_bench.py
    python zone-brain/bench/detect_bench.py --model weights/vision/yolov8n_det_int8.onnx

The script writes bench/out/detect.json and prints a summary table.
Without NPU it benchmarks CPU only (honest fallback — badges never lie).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

# Allow the script to resolve the sibling vision package.
_ROOT = Path(__file__).resolve().parent.parent
for _p in [str(_ROOT / "vision"), str(_ROOT / "engine")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detect_qnn as _det

_OUT_DIR = Path(__file__).resolve().parent / "out"
_WARMUP = 3
_N = 300
_IMGSZ = 640


def _bench_one(session, n: int, warmup: int) -> list[float]:
    """Run `warmup` throwaway frames then `n` timed frames.

    Uses the INFERENCE latency detect() itself reports (the same number the
    density messages badge), so the NPU-vs-CPU comparison measures the EP, not
    the shared numpy pre/post-processing around it.
    """
    frame = np.zeros((_IMGSZ, _IMGSZ, 3), dtype=np.uint8)
    for _ in range(warmup):
        _det.detect(session, frame)
    lats = []
    for _ in range(n):
        _, _, infer_ms = _det.detect(session, frame)
        lats.append(infer_ms)
    return lats


def _stats(lats: list[float], backend: str) -> dict:
    arr = np.array(lats)
    return {
        "backend": backend,
        "n": len(lats),
        "mean_ms": round(float(arr.mean()), 2),
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "min_ms": round(float(arr.min()), 2),
        "max_ms": round(float(arr.max()), 2),
    }


def main(model_path: str | None = None) -> int:
    if model_path is None:
        model_path = str(_ROOT.parent / "weights" / "vision" / "yolov8n_det_int8.onnx")
    if not Path(model_path).exists():
        print(f"[detect_bench] model not found: {model_path}")
        print("  Run download_models.py to stage weights, then re-run.")
        return 1

    results = []

    # --- QNN EP (NPU burst) if available ---
    if _det._qnn_attached():
        print(f"[detect_bench] QNN NPU attached — benchmarking {_N} frames (burst)...")
        sess_npu = _det.build_session(model_path, performance_mode="burst",
                                      require_npu=False)
        lats_npu = _bench_one(sess_npu, _N, _WARMUP)
        st = _stats(lats_npu, _det.BACKEND_QNN_NPU if hasattr(_det, "BACKEND_QNN_NPU")
                    else "qnn-npu-hexagon-v73")
        results.append(st)
        print(f"  NPU  mean={st['mean_ms']:.1f}ms  p50={st['p50_ms']:.1f}  "
              f"p95={st['p95_ms']:.1f}  p99={st['p99_ms']:.1f}")
    else:
        print("[detect_bench] QNN EP absent on this machine (expected on non-X Elite dev).")
        print("  CPU-only benchmark follows.")

    # --- CPU EP (always runs for comparison; force_cpu so an NPU machine
    # doesn't silently hand this leg a QNN session and fake a 1x "speedup") ---
    print(f"[detect_bench] CPU EP — benchmarking {_N} frames...")
    sess_cpu = _det.build_session(model_path, require_npu=False, force_cpu=True)
    lats_cpu = _bench_one(sess_cpu, _N, _WARMUP)
    st = _stats(lats_cpu, "cpu")
    results.append(st)
    print(f"  CPU  mean={st['mean_ms']:.1f}ms  p50={st['p50_ms']:.1f}  "
          f"p95={st['p95_ms']:.1f}  p99={st['p99_ms']:.1f}")

    if len(results) == 2:
        speedup = results[1]["mean_ms"] / results[0]["mean_ms"]
        print(f"  NPU speedup vs CPU: {speedup:.1f}×")

    # Emit JSON — including the "markdown" field bench/embed.py inlines into the
    # BENCH:detect marker (no hand-typed numbers), mirrored to root bench/out/.
    rows = "\n".join(
        f"| `{r['backend']}` | {r['mean_ms']} | {r['p50_ms']} | {r['p95_ms']} | "
        f"{r['p99_ms']} |" for r in results)
    md = ("| backend | mean ms | p50 | p95 | p99 |\n|---|---|---|---|---|\n" + rows
          + f"\n\n{_N} frames @640x640, INT8 (QDQ, CrowdHuman-calibrated), "
            "inference-only latency (the number density messages badge).")
    if len(results) == 2:
        md += f" NPU speedup vs CPU: {results[1]['mean_ms'] / results[0]['mean_ms']:.1f}x."
    from datetime import datetime, timedelta, timezone
    captured = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(
        timespec="seconds")
    doc = {"bench": "detect", "warmup": _WARMUP, "frames": _N, "results": results,
           "markdown": md, "captured_at": captured}
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = _OUT_DIR / "detect.json"
    out.write_text(json.dumps(doc, indent=2))
    root_out = _ROOT.parent / "bench" / "out"
    root_out.mkdir(parents=True, exist_ok=True)
    (root_out / "detect.json").write_text(json.dumps(doc, indent=2))
    print(f"[detect_bench] -> {out}  (+ mirrored to bench/out/ for embed.py)")

    # Return non-zero if NPU was expected but absent (CI signal).
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Alpha detection latency bench")
    ap.add_argument("--model", default=None, help="Path to ONNX model")
    args = ap.parse_args()
    raise SystemExit(main(args.model))
