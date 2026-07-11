"""bench/_util.py — shared helpers for the bench scripts (Gamma lane)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
OUT = Path(__file__).resolve().parent / "out"


def pctl(values, p: float) -> float:
    """Percentile (nearest-rank) of a list of numbers."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def stats(values) -> dict:
    vals = list(values)
    n = len(vals)
    return {
        "n": n,
        "mean": round(sum(vals) / n, 3) if n else 0.0,
        "p50": round(pctl(vals, 50), 3),
        "p95": round(pctl(vals, 95), 3),
        "p99": round(pctl(vals, 99), 3),
        "min": round(min(vals), 3) if n else 0.0,
        "max": round(max(vals), 3) if n else 0.0,
    }


def write(stem: str, payload: dict) -> Path:
    """Write bench/out/<stem>.json (adds a timestamp). Returns the path."""
    OUT.mkdir(exist_ok=True)
    payload = dict(payload)
    payload["captured_at"] = datetime.now(IST).isoformat(timespec="seconds")
    path = OUT / f"{stem}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[bench] wrote {path}")
    return path
