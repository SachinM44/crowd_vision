"""crowdvision._lib.messages — the MESSAGES.md (v9 §e) contract, in code.

Single source of truth for:
  * the message envelope  {type, v, ts, src, seq, payload}
  * MQTT topic names + builders
  * honest backend badge values (Hard Rule 2 — badges never lie)
  * a light validator used by sim/tests

Every AI-produced message MUST carry inference_backend / latency_ms / model_id.
Non-AI messages carry provenance (playbook_id / triggered_by / provenance).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA_VERSION = 1
IST = timezone(timedelta(hours=5, minutes=30))

# --- Honest backend badges (Hard Rule 2). ----------------------------------
# The value MUST reflect what ACTUALLY produced the message.
BACKEND_QNN_NPU = "qnn-npu-hexagon-v73"   # X Elite vision (Alpha, real NPU)
BACKEND_CPU = "cpu"                       # honest CPU fallback
BACKEND_CLOUD = "cloud-ai100"             # Cloud AI 100 venue tier (real)
BACKEND_TEMPLATE = "template-local"       # venue-tier template fallback
BACKEND_LITERT_GPU = "litert-gpu"         # FunctionGemma on OnePlus (shipped)
BACKEND_LITERT_NPU = "litert-npu"         # E2B probe success (Hexagon v81)
BACKEND_SARVAM = "sarvam-edge"            # if the Sarvam upgrade lands
BACKEND_SIM = "sim-replay"                # sim harness — NOT the NPU. Honest.

# --- Message type identifiers. ---------------------------------------------
T_ZONE_DENSITY = "zone.density.update"
T_CAMERA_HEALTH = "camera.health"
T_GATE_COMMAND = "gate.command"
T_GATE_TELEMETRY = "gate.telemetry"
T_OFFICER_BEACON = "officer.beacon"
T_INCIDENT_REPORT = "incident.report"
T_DISPATCH_ORDER = "dispatch.order"
T_VENUE_ADVISORY = "venue.advisory"
T_VENUE_STATE = "venue.state"
T_ATTENDEE_REPORT = "attendee.report"
T_HEARTBEAT = "sys.heartbeat"

# --- Topic tree (v9 §e). ---------------------------------------------------
TOPIC_ZONE_DENSITY = "cv/zone/{id}/density"
TOPIC_CAMERA_HEALTH = "cv/camera/{id}/health"
TOPIC_GATE_CMD = "cv/gate/{id}/cmd"
TOPIC_GATE_TELEMETRY = "cv/gate/{id}/telemetry"
TOPIC_OFFICER_BEACON = "cv/officer/{id}/beacon"
TOPIC_INCIDENT_NEW = "cv/incident/new"
TOPIC_DISPATCH = "cv/dispatch/{officer_id}"
TOPIC_VENUE_ADVISORY = "cv/venue/advisory"
TOPIC_VENUE_STATE = "cv/venue/state"
TOPIC_ATTENDEE_REPORT = "cv/attendee/report"
TOPIC_HEARTBEAT = "cv/sys/heartbeat/{device}"  # retained + LWT

# Gate actions allowed on gate.command (v9 §e #3).
GATE_ACTIONS = [
    "OPEN", "CLOSE", "DIVERT_LEFT", "DIVERT_RIGHT",
    "CLOSE_DIVERT_LEFT", "CLOSE_DIVERT_RIGHT", "SAFE_FLASH",
]

# Risk bands (Fruin LOS). UNKNOWN = stale-feed policy (Hard Rule 7).
RISK_GREEN, RISK_AMBER, RISK_RED, RISK_UNKNOWN = "GREEN", "AMBER", "RED", "UNKNOWN"

# Feed health states.
FEED_OK, FEED_DEGRADED, FEED_LOST = "OK", "DEGRADED", "LOST"


def now_ts() -> str:
    """ISO-8601 timestamp in IST (matches the v9 §e example format)."""
    return datetime.now(IST).isoformat(timespec="milliseconds")


def envelope(msg_type: str, src: str, seq: int, payload: dict[str, Any],
             *, ts: str | None = None, v: int = SCHEMA_VERSION) -> dict[str, Any]:
    """Wrap a payload in the v9 §e envelope: {type, v, ts, src, seq, payload}."""
    return {
        "type": msg_type,
        "v": v,
        "ts": ts or now_ts(),
        "src": src,
        "seq": int(seq),
        "payload": payload,
    }


def dumps(msg: dict[str, Any]) -> bytes:
    """Serialize a message for MQTT publish."""
    return json.dumps(msg, separators=(",", ":")).encode("utf-8")


def loads(raw: bytes | str) -> dict[str, Any]:
    """Parse an MQTT payload back into a message dict."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


# --- Topic builders. -------------------------------------------------------
def topic_zone_density(zone_id: str) -> str:
    return TOPIC_ZONE_DENSITY.format(id=zone_id)


def topic_camera_health(camera_id: str) -> str:
    return TOPIC_CAMERA_HEALTH.format(id=camera_id)


def topic_gate_cmd(gate_id: str) -> str:
    return TOPIC_GATE_CMD.format(id=gate_id)


def topic_gate_telemetry(gate_id: str) -> str:
    return TOPIC_GATE_TELEMETRY.format(id=gate_id)


def topic_officer_beacon(officer_id: str) -> str:
    return TOPIC_OFFICER_BEACON.format(id=officer_id)


def topic_dispatch(officer_id: str) -> str:
    return TOPIC_DISPATCH.format(officer_id=officer_id)


def topic_heartbeat(device: str) -> str:
    return TOPIC_HEARTBEAT.format(device=device)


# --- Validation (used by sim/tests). ---------------------------------------
_ENVELOPE_KEYS = {"type", "v", "ts", "src", "seq", "payload"}
_AI_TYPES = {T_ZONE_DENSITY, T_INCIDENT_REPORT, T_VENUE_ADVISORY}
_AI_BADGE_KEYS = ("inference_backend", "latency_ms", "model_id")


def validate_envelope(msg: dict[str, Any]) -> list[str]:
    """Return a list of contract violations ([] == valid)."""
    errors: list[str] = []
    missing = _ENVELOPE_KEYS - set(msg)
    if missing:
        errors.append(f"envelope missing keys: {sorted(missing)}")
        return errors
    if not isinstance(msg["payload"], dict):
        errors.append("payload must be an object")
    if not isinstance(msg["seq"], int):
        errors.append("seq must be an int")
    if msg["type"] in _AI_TYPES:
        for k in _AI_BADGE_KEYS:
            if k not in msg["payload"]:
                errors.append(f"AI message '{msg['type']}' missing badge '{k}'")
    if msg["type"] == T_GATE_COMMAND:
        for k in ("playbook_id", "triggered_by", "ttl_s"):
            if k not in msg["payload"]:
                errors.append(f"gate.command missing provenance '{k}'")
        if msg["payload"].get("action") not in GATE_ACTIONS:
            errors.append(f"gate.command action not in {GATE_ACTIONS}")
    return errors
