"""zone-brain/vision/gatelines.py — real + virtual gate-line flow counting.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Hybrid gate-flow counting:
  * REAL gate lines on Feed G (C4's dedicated Gate-3 lane view) — directed
    in/out counters from tracker.py tracks (higher accuracy).
  * VIRTUAL gate lines derived from zone views for un-camera'd gates.
The method is badged per gate in the flow_check block of zone.density.update
(docs/MESSAGES.md #1): method ∈ "real-gate-line/c4" | "virtual-gate-line/zone-view".

CONTRACT:
  count(tracks, line, direction) -> {in_per_min, out_per_min, method}
"""
from __future__ import annotations


def count(tracks, line, direction) -> dict:
    """Directed line-crossing counts for a gate line. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): signed crossings over the line segment")
