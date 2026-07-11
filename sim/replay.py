"""sim/replay.py — scripted decider (stand-in for Alpha's risk engine).

Subscribes cv/zone/+/density and, on risk TRANSITIONS, publishes the downstream
loop so gates flip + officers get dispatched with zero hardware and zero engine:
  AMBER  -> gate.command P1 (DIVERT_LEFT)
  RED    -> gate.command P2 (CLOSE_DIVERT_LEFT) + incident.report + dispatch.order
            (nearest officer by haversine over beacons) + venue.advisory
  GREEN  -> gate.command P3 (SAFE_FLASH)   [recovery]

Everything is badged honestly (triggered_by:"sim-scripted:...",
inference_backend:"sim-replay"/"template-local"). When Alpha's REAL engine runs,
don't start this — run `--feeds` instead and let the engine decide.

Run standalone:  python -m crowdvision.sim --all   (decider is part of --all)
"""
from __future__ import annotations

import math
import time

from .._lib import mqttc, messages as M, config

# Demo incident location (near officer-2 => nearest-dispatch picks the closer one).
INCIDENT_LOC = {"lat": 12.9699, "lon": 77.7501}

_PLAYBOOK_BY_RISK = {  # fallback if playbooks.yaml is absent
    M.RISK_AMBER: ("P1", "DIVERT_LEFT", 120),
    M.RISK_RED: ("P2", "CLOSE_DIVERT_LEFT", 120),
    M.RISK_GREEN: ("P3", "SAFE_FLASH", 60),
}


def _haversine(a: dict, b: dict) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dphi = math.radians(b["lat"] - a["lat"])
    dlam = math.radians(b["lon"] - a["lon"])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class Decider:
    def __init__(self, node: mqttc.MqttNode):
        self.node = node
        self.zones = config.zones().get("zones", {})
        try:
            self.playbooks = config.playbooks().get("playbooks", {})
        except Exception:  # noqa: BLE001
            self.playbooks = {}
        self.last_risk: dict[str, str] = {}
        self.officers: dict[str, dict] = {}
        self._inc_seq = 0
        node.on("cv/zone/+/density", self._on_density)
        node.on("cv/officer/+/beacon", self._on_beacon)

    def _on_beacon(self, topic: str, msg: dict) -> None:
        p = msg.get("payload", {})
        oid = p.get("officer_id")
        if oid and "lat" in p:
            self.officers[oid] = {"lat": p["lat"], "lon": p["lon"]}

    def _playbook(self, risk: str):
        for pid, spec in self.playbooks.items():
            when = spec.get("when", {})
            if when.get("risk") == risk:
                return pid, spec.get("gate_action"), int(spec.get("ttl_s", 120))
        return _PLAYBOOK_BY_RISK.get(risk, (None, None, 120))

    def _nearest_officer(self) -> str:
        if not self.officers:
            return "officer-2"
        return min(self.officers,
                   key=lambda oid: _haversine(INCIDENT_LOC, self.officers[oid]))

    def _on_density(self, topic: str, msg: dict) -> None:
        p = msg.get("payload", {})
        zid = p.get("zone_id")
        risk = p.get("risk")
        seq = msg.get("seq")
        if zid is None or risk in (None, M.RISK_UNKNOWN):
            return
        prev = self.last_risk.get(zid)
        if risk == prev:
            return                       # only act on transitions
        self.last_risk[zid] = risk
        # Recovery (P3/SAFE_FLASH) only fires coming DOWN from AMBER/RED, never on
        # first sight of GREEN at startup (matches playbooks.yaml P3 `from`).
        if risk == M.RISK_GREEN and prev not in (M.RISK_AMBER, M.RISK_RED):
            return
        z = self.zones.get(zid, {})
        gate_id = z.get("gate_id")
        if not gate_id:
            return
        pid, action, ttl = self._playbook(risk)
        if action:
            self.node.publish(
                M.topic_gate_cmd(gate_id), M.T_GATE_COMMAND,
                {"gate_id": gate_id, "action": action, "allowed": M.GATE_ACTIONS,
                 "reason": f"zone {zid} density {p.get('density_per_m2')} "
                           f"trend {p.get('trend_per_min')}/min TTT {p.get('ttt_red_s')}",
                 "playbook_id": pid, "triggered_by": f"sim-scripted:seq:{seq}",
                 "ttl_s": ttl},
                qos=1, retain=True, properties=mqttc.ttl_properties(ttl))
        if risk == M.RISK_RED:
            self._escalate(zid, gate_id, pid, seq, p)

    def _escalate(self, zid, gate_id, pid, seq, dens) -> None:
        self._inc_seq += 1
        inc_id = f"inc-sim-{self._inc_seq:03d}"
        # incident.report (sim-badged)
        self.node.publish(
            M.TOPIC_INCIDENT_NEW, M.T_INCIDENT_REPORT,
            {"incident_id": inc_id, "officer_id": "sim", **INCIDENT_LOC,
             "text": f"crush risk building at {zid}/gate {gate_id}",
             "structured": {"type": "crowd-crush", "location_hint": f"{zid}-gate-{gate_id}",
                            "severity": "high", "needs": ["crowd-control", "medic"]},
             "schema_valid": True, "photo_ref": None,
             "model_id": "sim", "inference_backend": M.BACKEND_SIM,
             "latency_ms": 0.0, "ttft_ms": 0.0},
            qos=1)
        # dispatch.order to the nearest officer
        oid = self._nearest_officer()
        self.node.publish(
            M.topic_dispatch(oid), M.T_DISPATCH_ORDER,
            {"dispatch_id": f"dsp-sim-{self._inc_seq:03d}", "officer_id": oid,
             "incident_id": inc_id, **INCIDENT_LOC,
             "reason": "nearest officer to crush-risk incident", "eta_s": 45,
             "playbook_id": pid, "triggered_by": f"sim-scripted:seq:{seq}"},
            qos=1)
        # venue.advisory (template-local — honest badge; no cloud in sim)
        self.node.publish(
            M.TOPIC_VENUE_ADVISORY, M.T_VENUE_ADVISORY,
            {"advisory_id": f"adv-sim-{self._inc_seq:03d}", "scope": f"zone:{zid}",
             "en": f"Zone {zid} is crowded. Please use alternate exits.",
             "hi": f"ज़ोन {zid} में भीड़ है। कृपया वैकल्पिक निकास का उपयोग करें।",
             "kn": f"ವಲಯ {zid} ರಲ್ಲಿ ಜನದಟ್ಟಣೆ ಇದೆ. ಪರ್ಯಾಯ ನಿರ್ಗಮನ ಬಳಸಿ.",
             "model_id": "sim-template", "inference_backend": M.BACKEND_TEMPLATE,
             "latency_ms": 0.0},
            qos=1)


def run(host="127.0.0.1", port=1883) -> Decider:
    node = mqttc.MqttNode("sim-decider", host=host, port=port).connect()
    time.sleep(0.2)
    return Decider(node)
