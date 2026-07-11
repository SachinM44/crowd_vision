"""zone-brain/bench/e2e_bench.py — end-to-end frame -> gate-actuated (BENCHMARKS #4).

RESOLVED SEAM (was a stub): per the Role Assignment the frame->gate e2e semantics
are Gamma's, and the real implementation lives in bench/e2e_bench.py (density ->
decider -> gate.command -> telemetry ACK, 50 fires, p50/p95 -> bench/out/e2e.json).
This wrapper simply delegates so Alpha's bench dir has no dead stub and both
entry points produce the same artifact.

    python zone-brain/bench/e2e_bench.py     # == python bench/e2e_bench.py

On hardware, the same clock method measures NPU frame -> UNO Q actuation.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from bench import e2e_bench as _impl  # noqa: E402
from bench import _util  # noqa: E402


def main() -> int:
    _util.write("e2e", _impl.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
