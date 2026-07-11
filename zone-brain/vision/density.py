"""zone-brain/vision/density.py — head points -> per-zone density/m2 -> publish.

OWNER: Alpha. Counts head points inside each zone polygon (config/zones.yaml),
divides by zone area_m2, runs the analytic engine (risk.py) to stamp risk/TTT,
attaches the flow_check block (flow.py), and publishes zone.density.update.

PUBLISHES (docs/MESSAGES.md #1) topic cv/zone/{zone_id}/density (1 Hz/zone):
  payload {zone_id, camera_id, transport, fps_effective, people_count, area_m2,
           density_per_m2, trend_per_min, ttt_red_s, risk, flow_check{...},
           temp_c, temp_source, model_id, inference_backend, latency_ms}

STALE-FEED (Hard Rule 7): if the feed health is LOST, publish risk="UNKNOWN" with
people_count/density = null — never a guessed number.

CONTRACT:
  publish_zone(node, zone_id, head_points_m, feed_health, badges, *,
               risk_state=None, gate_flow=None, fps_effective=None,
               ts_ms=None, temp_c=None, temp_source="config-default") -> envelope
  gate_flow = (in_per_min, out_per_min, method) from gatelines.py, or None for a
  virtual line derived from the density trend.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from crowdvision._lib import messages as M, config as C

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import risk as _risk  # noqa: E402  (sibling engine module)
import flow as _flow  # noqa: E402

_DEFAULT_STATE = _risk.new_state()


def _in_poly(pt, poly) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def count_in_polygon(points_m, polygon) -> int:
    return sum(1 for p in points_m if _in_poly(p, polygon))


def _feed_state(feed_health) -> str:
    if feed_health is None:
        return M.FEED_OK
    return getattr(feed_health, "state", None) or feed_health.get("state", M.FEED_OK)


def publish_zone(node, zone_id, head_points_m, feed_health, badges, *,
                 risk_state=None, gate_flow=None, fps_effective=None,
                 ts_ms=None, temp_c=None, temp_source="config-default") -> dict:
    """Compute density for a zone and publish zone.density.update."""
    z = C.zones().get("zones", {}).get(zone_id, {})
    area = float(z.get("area_m2", 20.0))
    polygon = z.get("polygon", [])
    cam = z.get("camera_id", "")
    transport = C.cameras().get("cameras", {}).get(cam, {}).get("transport", "sim")
    if ts_ms is None:
        ts_ms = time.monotonic() * 1000.0
    state = _feed_state(feed_health)
    rstate = risk_state if risk_state is not None else _DEFAULT_STATE
    fps = float(fps_effective) if fps_effective is not None else 12.0

    common = {
        "zone_id": zone_id, "camera_id": cam, "transport": transport,
        "fps_effective": round(fps, 2), "area_m2": area,
        "temp_c": temp_c, "temp_source": temp_source,
        **badges,  # model_id / inference_backend / latency_ms (AI-message contract)
    }

    if state == M.FEED_LOST:
        # Hard Rule 7 — no guessed density; gates hold on UNKNOWN.
        _risk.update(rstate, zone_id, 0.0, ts_ms, M.FEED_LOST, temp_c)
        payload = {**common, "people_count": None, "density_per_m2": None,
                   "trend_per_min": 0.0, "ttt_red_s": None, "risk": M.RISK_UNKNOWN,
                   "flow_check": {"gateline_in_per_min": 0.0, "gateline_out_per_min": 0.0,
                                  "method": "virtual-gate-line/zone-view", "residual": None}}
        return node.publish(M.topic_zone_density(zone_id), M.T_ZONE_DENSITY,
                            payload, qos=0)

    count = count_in_polygon(head_points_m, polygon)
    density = count / area if area > 0 else 0.0
    rr = _risk.update(rstate, zone_id, density, ts_ms, state, temp_c)
    if gate_flow is not None:
        gin, gout, gmethod = gate_flow
    else:  # virtual gate line derived from the density trend
        gin, gout, gmethod = 0.0, 0.0, "virtual-gate-line/zone-view"
    flow_block = _flow.check(zone_id, in_per_min=gin, out_per_min=gout,
                             density_trend=rr.trend_per_min * area, method=gmethod)
    payload = {**common, "people_count": count,
               "density_per_m2": round(density, 3),
               "trend_per_min": rr.trend_per_min, "ttt_red_s": rr.ttt_red_s,
               "risk": rr.risk, "flow_check": flow_block}
    return node.publish(M.topic_zone_density(zone_id), M.T_ZONE_DENSITY,
                        payload, qos=0)


def _selftest() -> int:
    class FakeNode:
        def __init__(self):
            self.sent = []
            self._seq = 0

        def publish(self, topic, mtype, payload, **kw):
            self._seq += 1
            env = M.envelope(mtype, "zonebrain-A", self._seq, payload)
            self.sent.append((topic, env))
            return env

    node = FakeNode()
    badges = {"model_id": _model_badge(), "inference_backend": M.BACKEND_CPU,
              "latency_ms": 14.2}
    # 80 head points inside zone A (0..8 x, 0..5 y) -> 80/20 = 4.0 /m^2.
    pts = [(0.1 + (i % 8), 0.1 + (i // 8) % 5) for i in range(80)]
    st = _risk.new_state()
    env = publish_zone(node, "A", pts, {"state": M.FEED_OK}, badges,
                       risk_state=st, ts_ms=1000.0)
    p = env["payload"]
    assert M.validate_envelope(env) == [], M.validate_envelope(env)
    assert p["people_count"] == 80 and abs(p["density_per_m2"] - 4.0) < 1e-6, p
    assert node.sent[0][0] == "cv/zone/A/density"
    # LOST feed -> UNKNOWN, null density, still contract-valid (badges present).
    env2 = publish_zone(node, "A", pts, {"state": M.FEED_LOST}, badges,
                        risk_state=st, ts_ms=2000.0)
    p2 = env2["payload"]
    assert M.validate_envelope(env2) == [], M.validate_envelope(env2)
    assert p2["risk"] == M.RISK_UNKNOWN and p2["people_count"] is None \
        and p2["density_per_m2"] is None, p2
    print("density.py selftest OK: 80 pts / 20 m^2 = 4.0/m^2; LOST -> UNKNOWN null count")
    return 0


def _model_badge() -> str:
    from importlib import import_module
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        return import_module("detect_qnn").MODEL_ID
    except Exception:  # noqa: BLE001
        return "yolov8n-det-int8-qnn"


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
