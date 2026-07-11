"""zone-brain/engine/flow.py — gate-flow conservation.

OWNER: Alpha. Checks mass conservation against gate-line in/out counts
(gatelines.py): a zone's density trend should be consistent with net inflow.
Produces the flow_check block carried in zone.density.update
(docs/MESSAGES.md #1): {gateline_in_per_min, gateline_out_per_min, method, residual}.

`density_trend` MUST be supplied in people/min (density.py converts
trend_per_min[/m^2] * area_m2) so it is unit-comparable with the gate-line
counts. `residual` in [0,1] is the normalized disagreement between observed net
inflow and the density trend — small means the counts and the density agree.

CONTRACT:
  check(zone_id, in_per_min, out_per_min, density_trend, method) -> flow_check dict
"""
from __future__ import annotations


def check(zone_id: str, in_per_min: float, out_per_min: float,
          density_trend: float, method: str) -> dict:
    """Return the flow_check block (residual = model vs observed)."""
    net = float(in_per_min) - float(out_per_min)          # people/min entering
    denom = abs(net) + abs(float(density_trend)) + 1e-6
    residual = round(abs(net - float(density_trend)) / denom, 3)
    return {
        "gateline_in_per_min": round(float(in_per_min), 2),
        "gateline_out_per_min": round(float(out_per_min), 2),
        "method": method,
        "residual": residual,
    }


def _selftest() -> int:
    # Perfect agreement -> ~0 residual.
    a = check("A", 42, 18, 24, "real-gate-line/c4")
    assert a["residual"] < 0.01, a
    # Net inflow but flat density -> large residual (something is off/occluded).
    b = check("A", 42, 18, 0, "virtual-gate-line/zone-view")
    assert b["residual"] > 0.5, b
    assert b["method"] == "virtual-gate-line/zone-view"
    print("flow.py selftest OK:", a, b)
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
