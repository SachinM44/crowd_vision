"""zone-brain/engine/risk.py — analytic risk engine (deliberately NOT ML).

OWNER: Alpha. Auditable safety logic (Constraint 4: predictor stays analytic by
choice):
  * EWMA(alpha) @1 Hz on density -> slope over slope_window_s -> time-to-threshold
  * hysteresis: hysteresis_pct band + dwell_s before a state change
  * temp modifier (modulino-thermo or config default) nudges the bands
  * STALE-FEED POLICY (Hard Rule 7): feed LOST => zone UNKNOWN, gates hold state,
    operator alerted — never silently guess.

All tunables come from config/zones.yaml (Hard Rule 5): risk_bands_default
{amber_at, red_at, hysteresis_pct, dwell_s} and predictor {ewma_alpha,
slope_window_s, stale_lost_s}. A zone may override via a `risk_bands` block.

CONTRACT:
  new_state() -> dict            # caller owns the per-zone state
  update(state, zone_id, density, ts_ms, feed_state, temp_c) -> RiskResult
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from crowdvision._lib import messages as M, config as C


@dataclass
class RiskResult:
    zone_id: str
    risk: str          # GREEN | AMBER | RED | UNKNOWN
    density_per_m2: float
    trend_per_min: float
    ttt_red_s: int | None


@dataclass
class _ZoneState:
    ewma: float | None = None
    history: deque = field(default_factory=lambda: deque())  # (ts_ms, ewma)
    committed: str = M.RISK_GREEN
    cand_band: str | None = None
    cand_since_ms: float = 0.0


def new_state() -> dict:
    """Fresh engine state; the pipeline holds one and passes it to update()."""
    return {}


def _bands(zone_id: str):
    """(amber_at, red_at, hyst, dwell_s, alpha, slope_window_s) for a zone."""
    z = C.zones()
    base = dict(z.get("risk_bands_default", {}))
    pred = z.get("predictor", {})
    override = z.get("zones", {}).get(zone_id, {}).get("risk_bands", {})
    base.update(override)
    return (
        float(base.get("amber_at", 3.0)),
        float(base.get("red_at", 5.0)),
        float(base.get("hysteresis_pct", 10)) / 100.0,
        float(base.get("dwell_s", 5)),
        float(pred.get("ewma_alpha", 0.3)),
        float(pred.get("slope_window_s", 60)),
    )


def _temp_scale(temp_c: float | None) -> float:
    """Hot venues crush sooner: shave up to 10% off the bands above 30 C."""
    if temp_c is None:
        return 1.0
    over = max(0.0, float(temp_c) - 30.0)
    return max(0.90, 1.0 - 0.01 * over)  # -1%/degC, floored at -10%


def _target_band(ewma: float, amber: float, red: float, committed: str,
                 hyst: float) -> str:
    """Fruin band with hysteresis relative to the committed state."""
    dn_amber, dn_red = amber * (1 - hyst), red * (1 - hyst)
    if committed == M.RISK_RED:
        if ewma < dn_red:
            return M.RISK_AMBER if ewma >= dn_amber else M.RISK_GREEN
        return M.RISK_RED
    if committed == M.RISK_AMBER:
        if ewma >= red:
            return M.RISK_RED
        if ewma < dn_amber:
            return M.RISK_GREEN
        return M.RISK_AMBER
    # committed GREEN (or UNKNOWN recovering)
    if ewma >= red:
        return M.RISK_RED
    if ewma >= amber:
        return M.RISK_AMBER
    return M.RISK_GREEN


def update(state: dict, zone_id: str, density, ts_ms: float,
           feed_state: str, temp_c=None) -> RiskResult:
    """Advance the analytic model for one zone tick."""
    st = state.get(zone_id)
    if st is None:
        st = state[zone_id] = _ZoneState()

    # Hard Rule 7: a lost feed never produces a guessed density. Hold committed
    # band internally but report UNKNOWN so gates hold and the operator is alerted.
    if feed_state == M.FEED_LOST:
        return RiskResult(zone_id, M.RISK_UNKNOWN, 0.0, 0.0, None)

    d = float(density)
    amber, red, hyst, dwell_s, alpha, slope_window_s = _bands(zone_id)
    scale = _temp_scale(temp_c)
    amber_e, red_e = amber * scale, red * scale

    # EWMA update.
    st.ewma = d if st.ewma is None else alpha * d + (1 - alpha) * st.ewma
    st.history.append((ts_ms, st.ewma))
    while st.history and ts_ms - st.history[0][0] > slope_window_s * 1000.0:
        st.history.popleft()

    # Slope over the window (per minute).
    trend_per_min = 0.0
    if len(st.history) >= 2:
        t0, e0 = st.history[0]
        dt_min = (ts_ms - t0) / 60000.0
        if dt_min > 0:
            trend_per_min = (st.ewma - e0) / dt_min

    # Hysteresis target + dwell before committing.
    target = _target_band(st.ewma, amber_e, red_e, st.committed, hyst)
    if target == st.committed:
        st.cand_band = None
    elif st.cand_band != target:
        st.cand_band, st.cand_since_ms = target, ts_ms
    elif ts_ms - st.cand_since_ms >= dwell_s * 1000.0:
        st.committed, st.cand_band = target, None

    # Time-to-threshold (RED), from the smoothed value and its slope.
    ttt = None
    if trend_per_min > 1e-6 and st.ewma < red_e:
        ttt = int((red_e - st.ewma) / (trend_per_min / 60.0))

    return RiskResult(zone_id, st.committed, round(d, 2),
                      round(trend_per_min, 3), ttt)


def _selftest() -> int:
    """Drive a synthetic surge; assert GREEN->AMBER->RED->recover + UNKNOWN."""
    state = new_state()
    seen = []
    ts = 0.0
    ttt_during_climb = []

    def step(d, feed=M.FEED_OK, temp=None):
        nonlocal ts
        ts += 1000.0
        r = update(state, "A", d, ts, feed, temp)
        seen.append(r.risk)
        return r

    for _ in range(6):      # settle GREEN
        step(0.4)
    # Gradual ramp 0.4 -> 6.0 so AMBER is genuinely traversed before RED.
    for i in range(20):
        r = step(0.4 + i * 0.3)
        if r.risk == M.RISK_AMBER and r.ttt_red_s is not None:
            ttt_during_climb.append(r.ttt_red_s)
    for _ in range(6):      # hold RED
        red = step(6.0)
    assert M.RISK_AMBER in seen, f"AMBER never committed: {seen}"
    assert red.risk == M.RISK_RED, f"expected RED, got {red.risk}"
    assert ttt_during_climb, "expected a finite time-to-RED while climbing in AMBER"
    assert all(t >= 0 for t in ttt_during_climb)
    for _ in range(14):     # recover
        step(0.4)
    rec = step(0.4)
    assert rec.risk == M.RISK_GREEN, f"expected GREEN recovery, got {rec.risk}"
    lost = step(0.4, feed=M.FEED_LOST)
    assert lost.risk == M.RISK_UNKNOWN, f"LOST must be UNKNOWN, got {lost.risk}"
    # a hot venue must reach RED no later than a cool one
    hot = new_state()
    hot_ts = 0.0
    hot_red_at = None
    for i in range(20):
        hot_ts += 1000.0
        if update(hot, "A", 4.7, hot_ts, M.FEED_OK, 40.0).risk == M.RISK_RED:
            hot_red_at = i
            break
    assert hot_red_at is not None, "temp modifier should push 4.7 to RED when hot"
    print("risk.py selftest OK:", "->".join(dict.fromkeys(seen)))
    print(f"  time-to-RED while climbing: {ttt_during_climb[0]}s -> {ttt_during_climb[-1]}s;"
          f" hot-venue RED at tick {hot_red_at}")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
