"""Headless tests for the sim message loop (Hard Rule 6).

Verifies: broker boots, every message type validates against docs/MESSAGES.md,
gate.command -> telemetry round-trip, dispatch -> officer ack, and the decider's
RED -> gate.command + incident + dispatch + advisory chain (with nearest-officer
selection). No hardware, no display.
"""
from __future__ import annotations

import time

from crowdvision._lib import mqttc, messages as M
from .conftest import wait_for


def _types(monitor):
    return [m["type"] for _t, m in monitor.messages]


def test_broker_roundtrip_and_schema(broker, monitor):
    host, port = broker
    pub = mqttc.MqttNode("t-pub", host=host, port=port).connect()
    time.sleep(0.3)
    pub.publish(M.topic_zone_density("B"), M.T_ZONE_DENSITY,
                {"zone_id": "B", "density_per_m2": 4.1, "risk": "AMBER",
                 "model_id": "sim", "inference_backend": M.BACKEND_SIM,
                 "latency_ms": 1.0})
    assert wait_for(lambda: M.T_ZONE_DENSITY in _types(monitor))
    msg = next(m for _t, m in monitor.messages if m["type"] == M.T_ZONE_DENSITY)
    assert M.validate_envelope(msg) == []
    pub.disconnect()


def test_gate_command_to_telemetry(broker, monitor):
    from crowdvision.sim import sim_gate
    host, port = broker
    gate = sim_gate.run(host, port)
    time.sleep(0.4)
    pub = mqttc.MqttNode("t-cmd", host=host, port=port).connect()
    time.sleep(0.3)
    pub.publish(M.topic_gate_cmd("G3"), M.T_GATE_COMMAND,
                {"gate_id": "G3", "action": "CLOSE_DIVERT_LEFT",
                 "allowed": M.GATE_ACTIONS, "reason": "test",
                 "playbook_id": "P2", "triggered_by": "test", "ttl_s": 120})

    def acked():
        return any(m["type"] == M.T_GATE_TELEMETRY
                   and m["payload"].get("state") == "CLOSE_DIVERT_LEFT"
                   and m["payload"].get("actuated_ms", 0) > 0
                   for _t, m in monitor.messages)

    assert wait_for(acked), "gate did not ACK the command"
    gate.stop()
    pub.disconnect()


def test_officer_dispatch_ack_nearest(broker, monitor):
    from crowdvision.sim import sim_officer
    host, port = broker
    off = sim_officer.run(host, port)
    time.sleep(0.4)
    pub = mqttc.MqttNode("t-dsp", host=host, port=port).connect()
    time.sleep(0.3)
    pub.publish(M.topic_dispatch("officer-2"), M.T_DISPATCH_ORDER,
                {"dispatch_id": "dsp-1", "officer_id": "officer-2",
                 "incident_id": "inc-1", "lat": 12.9699, "lon": 77.7501,
                 "reason": "test", "eta_s": 30, "playbook_id": "P2",
                 "triggered_by": "test"})

    def enroute():
        return any(m["type"] == M.T_OFFICER_BEACON
                   and m["payload"].get("officer_id") == "officer-2"
                   and m["payload"].get("status") == "enroute"
                   and m["payload"].get("ack_dispatch_id") == "dsp-1"
                   for _t, m in monitor.messages)

    assert wait_for(enroute), "officer did not ack the dispatch"
    off.stop()
    pub.disconnect()


def test_decider_red_escalates(broker, monitor):
    from crowdvision.sim import replay
    host, port = broker
    dec = replay.run(host, port)
    time.sleep(0.4)
    pub = mqttc.MqttNode("t-den", host=host, port=port).connect()
    time.sleep(0.3)
    # Seed two officer positions so nearest-selection is exercised.
    pub.publish(M.topic_officer_beacon("officer-1"), M.T_OFFICER_BEACON,
                {"officer_id": "officer-1", "lat": 12.9690, "lon": 77.7490,
                 "status": "available"})
    pub.publish(M.topic_officer_beacon("officer-2"), M.T_OFFICER_BEACON,
                {"officer_id": "officer-2", "lat": 12.9699, "lon": 77.7501,
                 "status": "available"})
    time.sleep(0.3)
    # A RED density for zone A must trigger the whole downstream chain.
    pub.publish(M.topic_zone_density("A"), M.T_ZONE_DENSITY,
                {"zone_id": "A", "density_per_m2": 5.6, "risk": "RED",
                 "trend_per_min": 0.5, "ttt_red_s": 0,
                 "model_id": "sim", "inference_backend": M.BACKEND_SIM,
                 "latency_ms": 1.0})

    def chain_ok():
        types = _types(monitor)
        return (M.T_GATE_COMMAND in types and M.T_INCIDENT_REPORT in types
                and M.T_DISPATCH_ORDER in types and M.T_VENUE_ADVISORY in types)

    assert wait_for(chain_ok), "decider did not fire the full RED chain"

    cmd = next(m for _t, m in monitor.messages if m["type"] == M.T_GATE_COMMAND)
    assert cmd["payload"]["action"] == "CLOSE_DIVERT_LEFT"
    assert cmd["payload"]["gate_id"] == "G3"
    # nearest-officer selection picked the closer one
    dsp = next(m for _t, m in monitor.messages if m["type"] == M.T_DISPATCH_ORDER)
    assert dsp["payload"]["officer_id"] == "officer-2"
    # honest badges
    adv = next(m for _t, m in monitor.messages if m["type"] == M.T_VENUE_ADVISORY)
    assert adv["payload"]["inference_backend"] == M.BACKEND_TEMPLATE
    assert {"en", "hi", "kn"} <= set(adv["payload"])
    pub.disconnect()


def test_all_captured_messages_valid(broker, monitor):
    """Run the full mesh briefly; every message must satisfy the envelope contract."""
    from crowdvision.sim import sim_gate, sim_officer, sim_feeds, replay
    host, port = broker
    comps = [sim_gate.run(host, port), sim_officer.run(host, port),
             sim_feeds.run(host, port), replay.run(host, port)]
    time.sleep(3.0)
    for c in comps:
        if hasattr(c, "stop"):
            c.stop()
    time.sleep(0.3)
    assert monitor.messages, "no messages captured"
    invalid = [(m["type"], M.validate_envelope(m))
               for _t, m in monitor.messages if M.validate_envelope(m)]
    assert not invalid, f"invalid messages: {invalid[:5]}"
    # honest badge on sim density — never claims the NPU
    dens = [m for _t, m in monitor.messages if m["type"] == M.T_ZONE_DENSITY]
    assert dens and all(m["payload"]["inference_backend"] == M.BACKEND_SIM for m in dens)
