"""zone-brain/engine/playbooks.py — risk state -> autonomous gate.command.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Maps risk transitions to pre-approved playbooks (config/playbooks.yaml: P1/P2/P3)
and publishes gate.command. Human override at every level (dashboard buttons +
UNO Q knob) — this is autonomy for PRE-APPROVED actions only.

PUBLISHES (docs/MESSAGES.md #3) topic cv/gate/{gate_id}/cmd (QoS 1, retained, TTL):
  payload {gate_id, action, allowed, reason, playbook_id, triggered_by, ttl_s}
  action in messages.GATE_ACTIONS. triggered_by = "seq:<density seq>".

CONTRACT:
  fire(node, playbook_id, gate_id, reason, triggered_by) -> envelope
"""
from __future__ import annotations


def fire(node, playbook_id: str, gate_id: str, reason: str, triggered_by: str) -> dict:
    """Publish the gate.command for a playbook. TODO(alpha).

    Use crowdvision._lib.messages.topic_gate_cmd + GATE_ACTIONS + ttl_properties.
    """
    raise NotImplementedError("TODO(alpha): map playbook -> action, publish w/ TTL")
