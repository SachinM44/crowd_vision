"""zone-brain/engine/flow.py — gate-flow conservation.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Checks mass conservation against gate-line in/out counts (gatelines.py): a zone's
density trend should be consistent with net inflow. Produces the flow_check block
carried in zone.density.update (docs/MESSAGES.md #1):
  {gateline_in_per_min, gateline_out_per_min, method, residual}

CONTRACT:
  check(zone_id, in_per_min, out_per_min, density_trend, method) -> flow_check dict
"""
from __future__ import annotations


def check(zone_id, in_per_min, out_per_min, density_trend, method) -> dict:
    """Return the flow_check block (residual = model vs observed). TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): conservation residual")
