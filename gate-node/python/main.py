"""gate-node/python/main.py — UNO Q MPU: MQTT + fail-safe state machine + LWT.

OWNER: Beta (TODO(beta)). STUB — contract only.

SUBSCRIBES (docs/MESSAGES.md #3) cv/gate/{gate_id}/cmd  (QoS 1, retained, TTL):
  {gate_id, action, allowed, reason, playbook_id, triggered_by, ttl_s}
  On receipt: honor ttl_s, call the MCU over the Bridge to actuate, then ACK.

PUBLISHES (docs/MESSAGES.md #4) cv/gate/{gate_id}/telemetry (1 Hz, the ACK):
  {gate_id, state, actuated_ms, bridge_rpc_ms, override, failsafe_active,
   temp_c, modulinos{knob,buzzer,thermo}, link_ok, provenance:"deterministic-mcu"}

LWT + heartbeat: cv/sys/heartbeat/uno-q-{gate_id} (retained). On broker/link loss
the MCU holds LAST_SAFE independently of Linux — fail-safe (Q&A-demoable by
dropping the UNO Q from the hotspot).

BRIDGE RPC (pinned from App Lab built-in examples — NEVER invent names):
    from arduino.app_bridge import Bridge
    bridge = Bridge()
    bridge.call("gate_set_state", state)      # RGB + matrix, provided by sketch.ino
    bridge.call("gate_chirp")                 # buzzer steward chirp (if secured)
    knob = bridge.call("gate_read_knob")      # override input (if secured)
TODO(beta): confirm the exact provided/called method names on real hardware at
13:00 Saturday (Blink + RPC echo first). Until then this is a mocked-Bridge test.
"""
from __future__ import annotations


def on_command(bridge, node, topic: str, msg: dict) -> None:
    """Actuate the MCU for a gate.command and publish telemetry. TODO(beta)."""
    raise NotImplementedError("TODO(beta): ttl check -> bridge.call(...) -> telemetry ACK")


def failsafe_loop(bridge, node) -> None:
    """Hold LAST_SAFE on link loss; auto-rejoin; chirp-once. TODO(beta)."""
    raise NotImplementedError("TODO(beta): LWT-driven LAST_SAFE state machine")


if __name__ == "__main__":
    raise SystemExit("TODO(beta): wire MQTT (paho) + Bridge + failsafe loop")
