"""sim/sim_gate.py — virtual UNO Q gate node.

Subscribes cv/gate/{id}/cmd (docs/MESSAGES.md #3), actuates instantly, and echoes
cv/gate/{id}/telemetry (#4). Also republishes the held state ~1 Hz so the
dashboard shows steady gate state. Stand-in for Beta's real gate node on the same
topics — replace with zero code changes.

Run standalone:  python -m crowdvision.sim --gate
"""
from __future__ import annotations

import threading
import time

from .._lib import mqttc, messages as M


class SimGate:
    def __init__(self, node: mqttc.MqttNode, gate_ids=("G1", "G2", "G3")):
        self.node = node
        self.state = {g: "OPEN" for g in gate_ids}
        self._override = {g: "NONE" for g in gate_ids}
        self._stop = threading.Event()
        for g in gate_ids:
            node.on(M.topic_gate_cmd(g), self._on_cmd)

    def _on_cmd(self, topic: str, msg: dict) -> None:
        p = msg.get("payload", {})
        gid = p.get("gate_id")
        action = p.get("action")
        if gid not in self.state or action not in M.GATE_ACTIONS:
            return
        self.state[gid] = action
        # Deterministic MCU actuation (sim): a few ms.
        self.node.publish(
            M.topic_gate_telemetry(gid), M.T_GATE_TELEMETRY,
            {"gate_id": gid, "state": action, "actuated_ms": 6, "bridge_rpc_ms": 4,
             "override": self._override[gid], "failsafe_active": False,
             "temp_c": 33.5, "modulinos": {"knob": False, "buzzer": False, "thermo": False},
             "link_ok": True, "provenance": "deterministic-mcu (sim)",
             "triggered_by": p.get("triggered_by"), "playbook_id": p.get("playbook_id")},
            qos=1)

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(1.0):
            for gid, st in self.state.items():
                self.node.publish(
                    M.topic_gate_telemetry(gid), M.T_GATE_TELEMETRY,
                    {"gate_id": gid, "state": st, "actuated_ms": 0, "bridge_rpc_ms": 0,
                     "override": self._override[gid], "failsafe_active": False,
                     "temp_c": 33.5,
                     "modulinos": {"knob": False, "buzzer": False, "thermo": False},
                     "link_ok": True, "provenance": "deterministic-mcu (sim)"},
                    qos=0)

    def start(self) -> "SimGate":
        threading.Thread(target=self._heartbeat_loop, name="sim-gate", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()


def run(host="127.0.0.1", port=1883, gate_ids=None) -> SimGate:
    """gate_ids: which gates to emulate (default G1,G2,G3). Pass a subset when a
    REAL UNO Q owns some gate (e.g. real G3 -> sim only G1,G2) so the sim never
    fights the hardware's telemetry on the same topic."""
    node = mqttc.MqttNode("uno-q-sim", host=host, port=port).connect()
    time.sleep(0.2)
    return SimGate(node, gate_ids or ("G1", "G2", "G3")).start()
