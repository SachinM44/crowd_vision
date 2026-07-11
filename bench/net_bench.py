"""bench/net_bench.py — hotspot throughput + RTSP drop rate (BENCHMARKS.md #3).

OWNER: Gamma (Phase B6). Building now — don't touch.

10-min window during the mesh soak: hotspot throughput, per-stream RTSP drop
rate, reconnect count (watchdog counters). Emit JSON -> bench/out/net.json.
"""
from __future__ import annotations


def main() -> int:
    raise NotImplementedError("TODO(gamma B6): throughput + drop rate -> bench/out/net.json")


if __name__ == "__main__":
    raise SystemExit(main())
