"""zone-brain/server/mqtt_bridge.py — MQTT (paho) -> WebSocket fan-out + state.

OWNER: Gamma. Subscribes cv/# on the broker, keeps the latest state per entity
(for snapshotting new dashboard clients), maintains a provenance event log, and
broadcasts every live message to connected WebSockets. Also publishes operator
overrides as gate.command with triggered_by:"operator-override".

Runs paho in its own thread; hands messages to the FastAPI asyncio loop via
run_coroutine_threadsafe. Code to docs/MESSAGES.md only.
"""
from __future__ import annotations

import asyncio
import collections
import sys
from pathlib import Path

# Make crowdvision._lib importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from crowdvision._lib import mqttc, messages as M  # noqa: E402

# Message types that become scrolling event-log entries (provenance as theatre).
_LOG_TYPES = {M.T_GATE_COMMAND, M.T_INCIDENT_REPORT, M.T_DISPATCH_ORDER,
              M.T_VENUE_ADVISORY}


class DashboardBridge:
    def __init__(self, broker_host: str = "127.0.0.1", broker_port: int = 1883):
        self.node = mqttc.MqttNode("dashboard", host=broker_host, port=broker_port)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: set = set()
        self.state = {"zones": {}, "cameras": {}, "gates": {}, "officers": {},
                      "venue": {}, "advisory": {}}
        self.log = collections.deque(maxlen=200)
        self.node.on("cv/#", self._on_mqtt)

    # -- lifecycle (called from the asyncio side) -------------------------
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.node.connect()

    def stop(self) -> None:
        self.node.disconnect()

    # -- paho thread ------------------------------------------------------
    def _on_mqtt(self, topic: str, msg: dict) -> None:
        self._update_state(topic, msg)
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"kind": "msg", "topic": topic, "message": msg}),
                self.loop)

    def _update_state(self, topic: str, msg: dict) -> None:
        t = msg.get("type")
        p = msg.get("payload", {})
        if t == M.T_ZONE_DENSITY and "zone_id" in p:
            self.state["zones"][p["zone_id"]] = p
        elif t == M.T_CAMERA_HEALTH and "camera_id" in p:
            self.state["cameras"][p["camera_id"]] = p
        elif t == M.T_GATE_TELEMETRY and "gate_id" in p:
            self.state["gates"][p["gate_id"]] = p
        elif t == M.T_OFFICER_BEACON and "officer_id" in p:
            self.state["officers"][p["officer_id"]] = p
        elif t == M.T_VENUE_STATE:
            self.state["venue"] = p
        elif t == M.T_VENUE_ADVISORY:
            self.state["advisory"] = p
        if t in _LOG_TYPES:
            self.log.append({"ts": msg.get("ts"), "type": t, "payload": p})

    # -- asyncio side -----------------------------------------------------
    async def _broadcast(self, data: dict) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def snapshot(self) -> dict:
        return {"kind": "snapshot", "state": self.state, "log": list(self.log)}

    # -- operator override (dashboard -> gate.command) --------------------
    def publish_override(self, gate_id: str, action: str) -> dict:
        if action not in M.GATE_ACTIONS:
            raise ValueError(f"action must be one of {M.GATE_ACTIONS}")
        return self.node.publish(
            M.topic_gate_cmd(gate_id), M.T_GATE_COMMAND,
            {"gate_id": gate_id, "action": action, "allowed": M.GATE_ACTIONS,
             "reason": "manual operator override from dashboard",
             "playbook_id": None, "triggered_by": "operator-override", "ttl_s": 120},
            qos=1, retain=True, properties=mqttc.ttl_properties(120))
