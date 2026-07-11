# CrowdVision Message Schema (v9 §e)

**This is the contract.** Every lane codes to this document, never to another
lane's internals (Hard Rule 1). If the right JSON arrives on the right topic,
your side works. The reference implementation is `crowdvision._lib.messages`.

## Envelope
Every message is wrapped in a common envelope:

```json
{ "type": "...", "v": 1, "ts": "2026-07-12T07:41:03.214+05:30",
  "src": "zonebrain-A", "seq": 4812, "payload": { } }
```

| Field | Meaning |
|---|---|
| `type` | message type id (e.g. `zone.density.update`) |
| `v` | schema version (currently `1`) |
| `ts` | ISO-8601 timestamp, **IST (+05:30)** |
| `src` | publisher id (`zonebrain-A`, `uno-q-G3`, `officer-1`, `cloud`, `sim`, …) |
| `seq` | monotonically increasing per source |
| `payload` | type-specific body (below) |

**Provenance rules:**
- Every **AI-produced** message carries `inference_backend`, `latency_ms`,
  `model_id` in its payload.
- **Commands** carry `playbook_id`, `triggered_by`, and (for gate.command) `ttl_s`.
- **Badges never lie** (Hard Rule 2). `inference_backend` ∈
  `qnn-npu-hexagon-v73` · `cpu` · `cloud-ai100` · `template-local` ·
  `litert-gpu` · `litert-npu` · `sarvam-edge` · `sim-replay`.

## Topic tree
| Topic | Direction | QoS / flags |
|---|---|---|
| `cv/zone/{id}/density` | PC → dashboard/cloud (1 Hz/zone) | 0 |
| `cv/camera/{id}/health` | PC watchdog → dashboard (0.2 Hz/feed) | 0 |
| `cv/gate/{id}/cmd` | PC → UNO Q | **QoS 1, retained, TTL** |
| `cv/gate/{id}/telemetry` | UNO Q → PC (1 Hz, the ACK) | 1 |
| `cv/officer/{id}/beacon` | phone → PC | 0 |
| `cv/incident/new` | phone → PC | 1 |
| `cv/dispatch/{officer_id}` | PC → phone | 1 |
| `cv/venue/advisory` | Cloud → PC/dashboard | 1 |
| `cv/venue/state` | Cloud/PC → dashboard | 1 |
| `cv/attendee/report` | attendee web → PC (stretch) | 1 |
| `cv/sys/heartbeat/{device}` | every device | **retained + LWT** |

---

## 1. `zone.density.update` — PC → dashboard/cloud, 1 Hz/zone
[v9] gains `camera_id`, `transport`, `fps_effective`. **AI message** (carries badges).

```json
{ "zone_id": "B", "camera_id": "c1", "transport": "rtsp", "fps_effective": 11.8,
  "people_count": 87, "area_m2": 21.0, "density_per_m2": 4.14,
  "trend_per_min": 0.31, "ttt_red_s": 160, "risk": "AMBER",
  "flow_check": { "gateline_in_per_min": 42, "gateline_out_per_min": 18,
                  "method": "real-gate-line/c4|virtual-gate-line/zone-view",
                  "residual": 0.06 },
  "temp_c": 33.5, "temp_source": "modulino-thermo|config-default",
  "model_id": "yolov8n-det-int8-qnn",
  "inference_backend": "qnn-npu-hexagon-v73", "latency_ms": 14.2 }
```
`risk` ∈ `GREEN` `AMBER` `RED` `UNKNOWN`. `UNKNOWN` is emitted under the
stale-feed policy (see #2).

## 2. `camera.health` — PC watchdog → dashboard, 0.2 Hz/feed  [v9 new]
```json
{ "camera_id": "c3", "transport": "rtsp", "resolution": "640x480",
  "fps_effective": 11.6, "drop_rate_pct": 1.8, "last_frame_age_ms": 85,
  "state": "OK", "reconnects": 0, "note": "OK|DEGRADED|LOST" }
```
**Policy (Hard Rule 7):** `LOST` (> 10 s stale) ⇒ that zone flips `UNKNOWN`,
gates **hold** state, operator alerted — honesty over silent guessing.

## 3. `gate.command` — PC → UNO Q  (QoS 1, retained, TTL). **Command.**
```json
{ "gate_id": "G3", "action": "CLOSE_DIVERT_LEFT",
  "allowed": ["OPEN","CLOSE","DIVERT_LEFT","DIVERT_RIGHT",
              "CLOSE_DIVERT_LEFT","CLOSE_DIVERT_RIGHT","SAFE_FLASH"],
  "reason": "zone B density 4.1 rising 0.31/min, TTT 2:40",
  "playbook_id": "P2", "triggered_by": "seq:4812", "ttl_s": 120 }
```
`triggered_by` may also be `"operator-override"` (manual dashboard/knob action).

## 4. `gate.telemetry` — UNO Q → PC, 1 Hz (the ACK).
```json
{ "gate_id": "G3", "state": "CLOSE_DIVERT_LEFT", "actuated_ms": 6,
  "bridge_rpc_ms": 4, "override": "NONE",
  "failsafe_active": false, "temp_c": 33.5,
  "modulinos": { "knob": true, "buzzer": true, "thermo": true },
  "link_ok": true, "provenance": "deterministic-mcu" }
```

## 5. `incident.report` — phone → PC (`cv/incident/new`). **AI message.**
FunctionGemma structures free text/photo into a validated call; badged
`litert-gpu`; TTFT reported. Schema-invalid ⇒ no-op (never a wrong action).
```json
{ "incident_id": "inc-1207-014", "officer_id": "officer-1",
  "lat": 12.9698, "lon": 77.7500,
  "text": "man collapsed near gate 2 barrier, crowd gathering",
  "structured": { "type": "medical", "location_hint": "gate-2-barrier",
                  "severity": "high", "needs": ["medic","crowd-control"] },
  "schema_valid": true, "photo_ref": null,
  "model_id": "functiongemma-270m", "inference_backend": "litert-gpu",
  "latency_ms": 380, "ttft_ms": 210 }
```

## 6. `dispatch.order` — PC → phone (`cv/dispatch/{officer_id}`). **Command.**
Nearest officer chosen by haversine over beacons.
```json
{ "dispatch_id": "dsp-1207-009", "officer_id": "officer-2",
  "incident_id": "inc-1207-014", "lat": 12.9699, "lon": 77.7501,
  "reason": "nearest officer to medical incident",
  "route_hint": "via central aisle", "eta_s": 45,
  "playbook_id": "P2", "triggered_by": "seq:4820" }
```

## 7. `officer.beacon` — phone → PC (`cv/officer/{id}/beacon`).
```json
{ "officer_id": "officer-1", "lat": 12.9698, "lon": 77.7500,
  "accuracy_m": 5.0, "status": "available", "battery_pct": 82 }
```

## 8. `venue.advisory` — Cloud → PC/dashboard. **AI message.**
[v9] `inference_backend` may read `cloud-ai100` | `template-local` |
`sarvam-edge` — badged truthfully either way. Falls back to `template-local`
automatically on timeout/failure.
```json
{ "advisory_id": "adv-1207-003", "scope": "venue|zone:B",
  "en": "Zone B is filling. Please use the north exits.",
  "hi": "ज़ोन B भर रहा है। कृपया उत्तर के द्वार का उपयोग करें।",
  "kn": "ವಲಯ B ತುಂಬುತ್ತಿದೆ. ದಯವಿಟ್ಟು ಉತ್ತರ ದ್ವಾರಗಳನ್ನು ಬಳಸಿ.",
  "model_id": "cloud-ai100-advisor", "inference_backend": "cloud-ai100",
  "latency_ms": 512 }
```

## 9. `venue.state` — Cloud/PC → dashboard.
Fused N-zone picture (1 real cluster + 2 SIM-labeled zones in the demo).
```json
{ "zones": [
    { "zone_id": "B", "risk": "AMBER", "density_per_m2": 4.14, "simulated": false },
    { "zone_id": "SIM-1", "risk": "GREEN", "density_per_m2": 1.2, "simulated": true },
    { "zone_id": "SIM-2", "risk": "RED",  "density_per_m2": 5.6, "simulated": true } ],
  "uplink": "online|offline", "advisory_id": "adv-1207-003" }
```

## 10. `attendee.report` — attendee web → PC (stretch).
```json
{ "report_id": "att-1207-001", "zone_hint": "near food court",
  "text": "very crowded here", "trust": "low" }
```

## 11. `sys.heartbeat` — every device (`cv/sys/heartbeat/{device}`, retained + LWT).
```json
{ "device": "uno-q-G3", "state": "online|offline",
  "reason": "lwt", "note": "optional" }
```
On clean disconnect a device publishes `offline`; on an unclean drop the broker
publishes the retained LWT (`state:"offline","reason":"lwt"`) — every leg has
LWT-driven failure behavior.

---
### Changing this document
Changing MESSAGES.md is a cross-lane event. Propose in the team channel, update
`crowdvision._lib.messages` + `sim/tests` in the same change, and bump examples.
