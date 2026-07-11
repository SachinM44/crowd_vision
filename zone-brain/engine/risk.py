"""zone-brain/engine/risk.py — analytic risk engine (deliberately NOT ML).

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Auditable safety logic (Constraint 4: predictor stays analytic by choice):
  * EWMA(alpha=0.3) @1 Hz on density -> 60 s slope -> time-to-threshold (TTT)
  * flow conservation (see flow.py)
  * hysteresis: 10% band + 5 s dwell before a state change
  * temp modifier (modulino-thermo or config default)
  * STALE-FEED POLICY (Hard Rule 7): feed LOST > 10 s => zone UNKNOWN, gates
    hold state, operator alerted — never silently guess.

INPUT: a stream of zone.density.update payloads (per docs/MESSAGES.md #1).
OUTPUT: risk state per zone {GREEN|AMBER|RED|UNKNOWN} + ttt_red_s + trend, which
        density.py stamps onto the published payload and playbooks.py consumes.

CONTRACT:
  update(state, zone_id, density, ts_ms, feed_state, temp_c) -> RiskResult
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskResult:
    zone_id: str
    risk: str          # GREEN | AMBER | RED | UNKNOWN
    density_per_m2: float
    trend_per_min: float
    ttt_red_s: int | None


def update(state, zone_id, density, ts_ms, feed_state, temp_c) -> RiskResult:
    """Advance the analytic model for one zone tick. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): EWMA slope->TTT, hysteresis, stale->UNKNOWN")
