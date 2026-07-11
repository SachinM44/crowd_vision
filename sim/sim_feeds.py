"""sim/sim_feeds.py — 5 looping simulated camera feeds.

Publishes zone.density.update (docs/MESSAGES.md #1, 1 Hz/zone) + camera.health
(#2, ~0.2 Hz/feed) from a deterministic scenario. Zone A runs a repeating surge
(GREEN -> AMBER -> RED -> recover) so the kill-shot fires without hardware. Other
zones idle GREEN-ish. This stands in for Alpha's vision pipeline on the SAME
topics — swap in the real pipeline with zero code changes.

BADGES ARE HONEST (Hard Rule 2): inference_backend="sim-replay", model_id="sim"
— never claims the NPU.

Run standalone:  python -m crowdvision.sim --feeds
"""
from __future__ import annotations

import math
import threading
import time

from .._lib import mqttc, messages as M, config


def risk_for(density: float, amber_at: float, red_at: float) -> str:
    if density >= red_at:
        return M.RISK_RED
    if density >= amber_at:
        return M.RISK_AMBER
    return M.RISK_GREEN


def _surge(t: float, period: float = 45.0) -> float:
    """Zone A density over a repeating 45 s surge cycle."""
    x = t % period
    if x < 8:
        return 0.4
    if x < 20:                       # ramp 0.4 -> 6.0 (amber ~13s, red ~18s)
        return 0.4 + (x - 8) / 12.0 * 5.6
    if x < 26:
        return 5.6                   # hold RED
    if x < 34:                       # recover 5.6 -> 0.6
        return 5.6 - (x - 26) / 8.0 * 5.0
    return 0.5


def _idle(base: float, t: float, wobble: float = 0.25) -> float:
    return max(0.0, base + wobble * math.sin(t / 5.0))


class SimFeeds:
    def __init__(self, node: mqttc.MqttNode):
        self.node = node
        self.zones = config.zones()
        self.cams = config.cameras()
        bands = self.zones.get("risk_bands_default", {})
        self.amber = float(bands.get("amber_at", 3.0))
        self.red = float(bands.get("red_at", 5.0))
        self._prev: dict[str, float] = {}
        self._stop = threading.Event()
        self.t0 = time.monotonic()

    # -- density model per zone -------------------------------------------
    def _density(self, zone_id: str, t: float) -> float:
        if zone_id == "A":
            return _surge(t)
        base = {"B": 0.4, "C": 1.5, "D": 2.2}.get(zone_id, 1.0)
        return _idle(base, t)

    def _publish_density(self, t: float) -> None:
        for zid, z in self.zones.get("zones", {}).items():
            d = round(self._density(zid, t), 2)
            prev = self._prev.get(zid, d)
            trend = round((d - prev) * 60.0, 2)   # per-minute (dt = 1 s)
            self._prev[zid] = d
            risk = risk_for(d, self.amber, self.red)
            ttt = None
            if trend > 0 and d < self.red:
                ttt = int((self.red - d) / max(trend / 60.0, 1e-6))
            area = float(z.get("area_m2", 20.0))
            cam = z.get("camera_id", "")
            transport = self.cams.get("cameras", {}).get(cam, {}).get("transport", "sim")
            payload = {
                "zone_id": zid, "camera_id": cam, "transport": transport,
                "fps_effective": 11.8, "people_count": int(round(d * area)),
                "area_m2": area, "density_per_m2": d, "trend_per_min": trend,
                "ttt_red_s": ttt, "risk": risk,
                "flow_check": {"gateline_in_per_min": 42 if zid == "A" else 12,
                               "gateline_out_per_min": 18,
                               "method": "virtual-gate-line/zone-view", "residual": 0.06},
                "temp_c": 33.5, "temp_source": "config-default",
                "model_id": "sim-yolov8n", "inference_backend": M.BACKEND_SIM,
                "latency_ms": 13.5,
            }
            self.node.publish(M.topic_zone_density(zid), M.T_ZONE_DENSITY, payload, qos=0)

    def _publish_health(self) -> None:
        for cid, c in self.cams.get("cameras", {}).items():
            self.node.publish(
                M.topic_camera_health(cid), M.T_CAMERA_HEALTH,
                {"camera_id": cid, "transport": c.get("transport", "sim"),
                 "resolution": "640x480", "fps_effective": 11.6, "drop_rate_pct": 1.2,
                 "last_frame_age_ms": 85, "state": M.FEED_OK, "reconnects": 0,
                 "note": M.FEED_OK}, qos=0)

    def _loop(self) -> None:
        tick = 0
        self._publish_health()
        while not self._stop.wait(1.0):
            t = time.monotonic() - self.t0
            self._publish_density(t)
            tick += 1
            if tick % 5 == 0:            # ~0.2 Hz health
                self._publish_health()

    def start(self) -> "SimFeeds":
        threading.Thread(target=self._loop, name="sim-feeds", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()


def run(host="127.0.0.1", port=1883) -> SimFeeds:
    node = mqttc.MqttNode("sim-feeds", host=host, port=port).connect()
    time.sleep(0.2)
    return SimFeeds(node).start()


class SurgeZone:
    """Publishes ONLY one zone's scripted surge — the deterministic kill-shot.

    Used in --live mode so the gate demo still fires even when the real cameras
    are (correctly) calm/GREEN. This is the plan's hybrid: real live zones + one
    scripted surge clip zone. Badged sim-replay (honest — it's the surge clip)."""

    def __init__(self, node: mqttc.MqttNode, zone_id: str = "A"):
        self.node = node
        self.zone_id = zone_id
        z = config.zones()
        bands = z.get("risk_bands_default", {})
        self.amber = float(bands.get("amber_at", 3.0))
        self.red = float(bands.get("red_at", 5.0))
        self.zprof = z.get("zones", {}).get(zone_id, {})
        self._stop = threading.Event()
        self.t0 = time.monotonic()
        self._prev = 0.0

    def _loop(self) -> None:
        area = float(self.zprof.get("area_m2", 20.0))
        cam = self.zprof.get("camera_id", "")
        while not self._stop.wait(1.0):
            t = time.monotonic() - self.t0
            d = round(_surge(t), 2)
            trend = round((d - self._prev) * 60.0, 2)
            self._prev = d
            risk = risk_for(d, self.amber, self.red)
            ttt = int((self.red - d) / max(trend / 60.0, 1e-6)) \
                if trend > 0 and d < self.red else None
            self.node.publish(M.topic_zone_density(self.zone_id), M.T_ZONE_DENSITY,
                              {"zone_id": self.zone_id, "camera_id": cam,
                               "transport": "file", "fps_effective": 12.0,
                               "people_count": int(d * area), "area_m2": area,
                               "density_per_m2": d, "trend_per_min": trend,
                               "ttt_red_s": ttt, "risk": risk,
                               "model_id": "surge-clip",
                               "inference_backend": M.BACKEND_SIM,
                               "latency_ms": 0.0}, qos=0)

    def start(self) -> "SurgeZone":
        threading.Thread(target=self._loop, name="surge", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()


def run_surge(host="127.0.0.1", port=1883, zone_id="A") -> SurgeZone:
    node = mqttc.MqttNode("surge-clip", host=host, port=port).connect()
    time.sleep(0.2)
    return SurgeZone(node, zone_id).start()
