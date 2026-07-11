# CrowdVision Architecture

> Seeded by Gamma; **Delta owns the prose.** Diagram + contract links are here to
> build on. Keep in sync with `CLAUDE.md` and `docs/MESSAGES.md`.

## One line
An edge-first crowd-safety nervous system: **SENSE → PREDICT → ACT → INFORM**,
frame → red-gate in **< 2 s**, no human in the loop, no frame leaves the venue.

## Tiers
```
VENUE TIER — Qualcomm Cloud AI 100 (REST)
  N-zone fusion · EN/HI/KN PA advisories · cross-zone reasoning · post-event report
  ▲ tiny JSON state (~1 KB/s, never video). internet = Phone-H cellular.
  │ DEMO BEAT: mobile data OFF → LAN survives, cloud dies, zones don't care.
══ EDGE — LAN = Phone-H hotspot (5 GHz), zero venue Wi-Fi ═════════════════════
ZONE-BRAIN — Surface Laptop 7, X Elite (Hexagon NPU v73, 45 TOPS)
  MQTT broker · FastAPI dashboard (Leaflet, local floorplan CRS)
  FIVE-FEED MESH (~4–5 Mbps): Feed A surge clip + C1–C4 RTSP 480p@12
   → per-feed watchdog (reconnect/backoff, stale detector, OK/DEGRADED/LOST)
   → ONE shared YOLOv8-INT8 QNN session (burst) + round-robin freshest-frame
   → head points → per-camera homography → density/m² per zone
   → centroid tracker → real gate lines (C4/Gate-3) + virtual gate lines
   → analytic risk engine (EWMA slope→TTT · flow conservation · hysteresis ·
      temp bands · stale-feed policy) → playbooks
        │ gate.command         │ dispatch.order          │ telemetry
        ▼                      ▼                          ▼
  GATE NODE (UNO Q 4GB)   FIELD OFFICERS (OnePlus 15 + Phone-H)   dashboard + cloud
```

## Data flow (the kill-shot loop, stopwatch-measured)
`Feed A frame → YOLO INT8 @ shared QNN (~10–25 ms) → density/slope/TTT →
AMBER→RED playbook P2 (<1 ms) → gate.command (MQTT ~5–20 ms) → UNO Q Bridge RPC
→ RGB red + matrix arrow + chirp → telemetry ACK → nearest-officer dispatch →
ack`. Target < 2 s (~1.4 s expected) while four live phone streams keep flowing
through the same NPU session.

## Message contract
See **`docs/MESSAGES.md`** — the single source of truth. Shared code:
`crowdvision._lib`.

## Deliberate non-goals
No face recognition / identity / re-ID · no VLM · no audio sensing · no attendee
GPS tracking · no black-box prediction · no cloud/mains dependence in the safety
loop.

## TODO(delta)
- Expand prose per demo narrative; add the sequence diagram; cite Fruin/Helbing.
