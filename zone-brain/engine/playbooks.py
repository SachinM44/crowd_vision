"""zone-brain/engine/playbooks.py — risk state -> autonomous gate.command.

OWNER: Alpha. Maps risk transitions to pre-approved playbooks
(config/playbooks.yaml: P1/P2/P3) and publishes gate.command. Human override at
every level (dashboard buttons + UNO Q knob) — this is autonomy for PRE-APPROVED
actions only.

PUBLISHES (docs/MESSAGES.md #3) topic cv/gate/{gate_id}/cmd (QoS 1, retained, TTL):
  payload {gate_id, action, allowed, reason, playbook_id, triggered_by, ttl_s}
  action in messages.GATE_ACTIONS. triggered_by = "seq:<density seq>".

CONTRACT:
  select_playbook(risk, trend_per_min, prev_risk=None) -> (playbook_id, action, ttl_s) | (None,None,ttl)
  reason_for(playbook_id, zone, density, trend, ttt) -> str
  fire(node, playbook_id, gate_id, reason, triggered_by) -> envelope
"""
from __future__ import annotations

from crowdvision._lib import messages as M, config as C

_DEFAULTS = {  # used only if playbooks.yaml is missing a field
    M.RISK_AMBER: ("P1", "DIVERT_LEFT", 120),
    M.RISK_RED: ("P2", "CLOSE_DIVERT_LEFT", 120),
    M.RISK_GREEN: ("P3", "SAFE_FLASH", 60),
}


def _playbooks() -> dict:
    try:
        return C.playbooks().get("playbooks", {}) or {}
    except Exception:  # noqa: BLE001 — config optional in some dev contexts
        return {}


def select_playbook(risk: str, trend_per_min: float = 0.0, prev_risk=None):
    """Pick the playbook whose `when` matches this risk (+ trend / `from` guards)."""
    pbs = _playbooks()
    risk_defined = False
    for pid, spec in pbs.items():
        when = spec.get("when", {})
        if when.get("risk") != risk:
            continue
        risk_defined = True  # config governs this risk; guards decide fire/no-fire
        gt = when.get("trend_per_min_gt")
        if gt is not None and not (float(trend_per_min) > float(gt)):
            continue
        frm = when.get("from")
        if frm is not None and prev_risk not in frm:
            continue
        action = spec.get("gate_action")
        if action not in M.GATE_ACTIONS:
            continue
        return pid, action, int(spec.get("ttl_s", 120))
    if risk_defined:
        return None, None, 120  # config matched the risk but a guard blocked it
    # No config for this risk -> built-in defaults (P3 still needs to come DOWN).
    pid, action, ttl = _DEFAULTS.get(risk, (None, None, 120))
    if risk == M.RISK_GREEN and prev_risk not in (M.RISK_AMBER, M.RISK_RED):
        return None, None, ttl
    return pid, action, ttl


def reason_for(playbook_id, zone, density, trend, ttt) -> str:
    """Fill the playbook's reason_template (falls back to a plain sentence)."""
    spec = _playbooks().get(playbook_id, {})
    tmpl = spec.get("reason_template")
    if tmpl:
        try:
            return tmpl.format(zone=zone, density=density, trend=trend, ttt=ttt)
        except Exception:  # noqa: BLE001
            pass
    return f"zone {zone} density {density} trend {trend}/min TTT {ttt}"


def fire(node, playbook_id: str, gate_id: str, reason: str, triggered_by: str) -> dict:
    """Publish the gate.command for a playbook. Returns the sent envelope."""
    from crowdvision._lib.mqttc import ttl_properties
    spec = _playbooks().get(playbook_id, {})
    action = spec.get("gate_action")
    ttl = int(spec.get("ttl_s", 120))
    if action not in M.GATE_ACTIONS:  # fallback lookup by id
        for risk, (pid, act, t) in _DEFAULTS.items():
            if pid == playbook_id:
                action, ttl = act, t
                break
    if action not in M.GATE_ACTIONS:
        raise ValueError(f"playbook '{playbook_id}' has no valid gate_action")
    payload = {
        "gate_id": gate_id, "action": action, "allowed": M.GATE_ACTIONS,
        "reason": reason, "playbook_id": playbook_id,
        "triggered_by": triggered_by, "ttl_s": ttl,
    }
    return node.publish(M.topic_gate_cmd(gate_id), M.T_GATE_COMMAND, payload,
                        qos=1, retain=True, properties=ttl_properties(ttl))


def _selftest() -> int:
    # Mapping: AMBER(trend>0.15)->P1, RED->P2, GREEN from RED->P3, GREEN cold->none.
    assert select_playbook(M.RISK_AMBER, 0.31)[:2] == ("P1", "DIVERT_LEFT")
    assert select_playbook(M.RISK_AMBER, 0.0)[0] is None, "AMBER needs trend>0.15"
    assert select_playbook(M.RISK_RED, 0.0)[:2] == ("P2", "CLOSE_DIVERT_LEFT")
    assert select_playbook(M.RISK_GREEN, 0.0, prev_risk=M.RISK_RED)[:2] == ("P3", "SAFE_FLASH")
    assert select_playbook(M.RISK_GREEN, 0.0, prev_risk=M.RISK_GREEN)[0] is None

    # fire() builds a contract-valid gate.command (no broker needed — fake node).
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
    env = fire(node, "P2", "G3", reason_for("P2", "A", 5.6, 0.5, 0), "seq:4812")
    assert M.validate_envelope(env) == [], M.validate_envelope(env)
    assert env["payload"]["action"] == "CLOSE_DIVERT_LEFT"
    assert node.sent[0][0] == "cv/gate/G3/cmd"
    print("playbooks.py selftest OK: P1/P2/P3 mapping + contract-valid gate.command")
    print("  reason:", env["payload"]["reason"])
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
