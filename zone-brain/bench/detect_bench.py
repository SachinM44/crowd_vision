"""detect_bench.py — detection latency, NPU vs CPU (BENCHMARKS.md #1).

OWNER: Alpha (TODO(alpha)). STUB.

3 warmup + 300 timed frames @640^2 INT8; once QNN EP (burst), once CPU EP.
Emit JSON -> bench/out/detect.json with {mean,p50,p95,p99} per backend for the
BENCH:detect marker in docs/BENCHMARKS.md.
"""
from __future__ import annotations


def main() -> int:
    raise NotImplementedError("TODO(alpha): 300 frames NPU vs CPU -> bench/out/detect.json")


if __name__ == "__main__":
    raise SystemExit(main())
