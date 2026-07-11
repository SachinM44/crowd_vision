"""bench/cloud_rtt_bench.py — venue-tier advisory RTT (BENCHMARKS #10).

OWNER: Gamma. Times N advisory calls through the venue tier. With Cloud AI 100
creds in .env it measures real cloud RTT (badged cloud-ai100); without them it
measures the offline template fallback (badged template-local). Either way the
badge is honest.

Standalone:  python bench/cloud_rtt_bench.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crowdvision._lib import config              # noqa: E402
from bench import _util                          # noqa: E402


def _load_client():
    path = config.repo_root() / "venue-tier" / "aisuite_client.py"
    spec = importlib.util.spec_from_file_location("cv_aisuite", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(n: int = 30) -> dict:
    client = _load_client()
    rtt_ms, backend = [], "template-local"
    for i in range(n):
        ctx = {"zone_id": "A", "risk": "RED", "density_per_m2": 5.6, "seq": i}
        t0 = time.perf_counter()
        adv = client.advisory(ctx)
        rtt_ms.append((time.perf_counter() - t0) * 1000.0)
        backend = adv.get("inference_backend", backend)
    s = _util.stats(rtt_ms)
    md = (f"| metric | value |\n|---|---|\n"
          f"| backend | `{backend}` |\n"
          f"| calls | {s['n']} |\n"
          f"| RTT mean | {s['mean']} ms |\n"
          f"| RTT p50 / p95 | {s['p50']} / {s['p95']} ms |\n"
          f"\n_With AISUITE_* creds this measures real Cloud AI 100 RTT "
          f"(badged `cloud-ai100`); here it measured the offline fallback._")
    return {"title": "Venue-tier advisory RTT", "backend": backend,
            "rtt_ms": s, "markdown": md}


if __name__ == "__main__":
    _util.write("cloud_rtt", run())
