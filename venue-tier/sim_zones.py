"""venue-tier/sim_zones.py — the venue tier: N-zone fusion + trilingual advisories.

OWNER: Gamma. Subscribes cv/zone/+/density, then publishes:
  * cv/venue/state  (~every 3 s): 1 real cluster + 2 SIM-labeled zones (the honest
    "N-zone fusion" view), with an uplink status.
  * cv/venue/advisory: on a real zone escalating to AMBER/RED, via aisuite_client
    (Cloud AI 100 -> falls back to template-local, badged honestly).

Off the safety path entirely: cloud dead => zones don't care (uplink-cut beat).

Run standalone:  python -m crowdvision.sim --zones   (or as part of --all)
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # crowdvision._lib

from crowdvision._lib import mqttc, messages as M  # noqa: E402
import aisuite_client  # noqa: E402

# Two simulated peer zones (cross-venue picture the single zone-brain can't see).
SIM_ZONES = [
    {"zone_id": "SIM-1", "risk": M.RISK_GREEN, "density_per_m2": 1.2, "simulated": True},
    {"zone_id": "SIM-2", "risk": M.RISK_RED, "density_per_m2": 5.6, "simulated": True},
]


class VenueTier:
    def __init__(self, node: mqttc.MqttNode):
        self.node = node
        self.real: dict[str, dict] = {}
        self.last_adv_risk: dict[str, str] = {}
        self._seq = 0
        self._stop = threading.Event()
        node.on("cv/zone/+/density", self._on_density)

    def _uplink(self) -> str:
        # Demo hook: set CV_UPLINK_DOWN=1 to simulate the cellular cut.
        return "offline" if os.environ.get("CV_UPLINK_DOWN") == "1" else "online"

    def _on_density(self, topic: str, msg: dict) -> None:
        p = msg.get("payload", {})
        zid, risk = p.get("zone_id"), p.get("risk")
        if not zid or risk == M.RISK_UNKNOWN:
            return
        self.real[zid] = {"zone_id": zid, "risk": risk,
                          "density_per_m2": p.get("density_per_m2"), "simulated": False}
        prev = self.last_adv_risk.get(zid)
        if risk != prev and risk in (M.RISK_AMBER, M.RISK_RED):
            self.last_adv_risk[zid] = risk
            self._publish_advisory(zid, risk, p)
        elif risk == M.RISK_GREEN:
            self.last_adv_risk[zid] = risk

    def _publish_advisory(self, zid, risk, p) -> None:
        self._seq += 1
        adv = aisuite_client.advisory(
            {"zone_id": zid, "risk": risk, "density_per_m2": p.get("density_per_m2"),
             "scope": f"zone:{zid}", "seq": self._seq})
        self.node.publish(M.TOPIC_VENUE_ADVISORY, M.T_VENUE_ADVISORY, adv, qos=1)

    def _state_loop(self) -> None:
        while not self._stop.wait(3.0):
            worst = None
            for z in self.real.values():
                order = {M.RISK_GREEN: 0, M.RISK_AMBER: 1, M.RISK_RED: 2}
                if worst is None or order.get(z["risk"], 0) > order.get(worst["risk"], 0):
                    worst = z
            zones = ([worst] if worst else []) + SIM_ZONES
            self.node.publish(M.TOPIC_VENUE_STATE, M.T_VENUE_STATE,
                              {"zones": zones, "uplink": self._uplink(),
                               "advisory_id": f"adv-tmpl-{self._seq}"}, qos=0)

    def start(self) -> "VenueTier":
        threading.Thread(target=self._state_loop, name="venue-tier", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()


def run(host="127.0.0.1", port=1883) -> VenueTier:
    node = mqttc.MqttNode("venue-tier", host=host, port=port).connect()
    time.sleep(0.2)
    return VenueTier(node).start()
