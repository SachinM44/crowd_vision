# CLAUDE.md — CrowdVision build context (read me first)

CrowdVision is our Snapdragon Multiverse Hackathon 2026 (Bengaluru) entry.
This file is the shared brain for every teammate's Claude Code session. Keep the
**Current Status** section at the bottom updated as things land.

## What it is (the spine)
An edge-first crowd-safety nervous system: **SENSE → PREDICT → ACT → INFORM**,
frame → red-gate in **< 2 s**, no human in the loop, no frame leaves the venue.

```
VENUE TIER — Cloud AI 100 (REST)     N-zone fusion · EN/HI/KN advisories · report
        ▲  tiny JSON state (~1 KB/s, never video) · off the safety path
        │  DEMO BEAT: toggle Phone-H mobile data OFF → LAN survives, zones don't care
════════ EDGE — LAN = Phone-H hotspot (5 GHz) ════════════════════════════════
ZONE-BRAIN — Surface X Elite (Hexagon NPU v73)
  5-feed mesh (Feed A surge clip + C1–C4 RTSP 480p@12) → ONE shared YOLOv8-INT8
  QNN session + round-robin freshest-frame scheduler → density/m² per zone
  → centroid tracker + gate lines (real on C4/Gate-3, virtual elsewhere)
  → analytic risk engine (EWMA slope→TTT, flow conservation, hysteresis,
     stale-feed policy) → playbooks
        │ gate.command        │ dispatch.order         │ zone/venue telemetry
        ▼                     ▼                         ▼
  GATE NODE (UNO Q)     FIELD OFFICERS (OnePlus 15 + Phone-H)   dashboard + cloud
  Bridge RPC → MCU:     dispatch recv/ack · GPS beacon ·
  matrix arrows/RGB/    incident: text/photo → FunctionGemma 270M
  chirp · LWG fail-safe   → validated report_incident() · form fallback
  (runs NO model)
```

## The contract: `docs/MESSAGES.md` (v9 §e)
**Code to the schema, never to another lane's internals** (Hard Rule 1). If the
right JSON arrives on the right topic, your side works.

Envelope: `{ "type", "v":1, "ts", "src", "seq", "payload" }`.
Every **AI** message carries `inference_backend` / `latency_ms` / `model_id`.
**Commands** carry `playbook_id` / `triggered_by` / `ttl_s`.

Topics: `cv/zone/{id}/density` · `cv/camera/{id}/health` · `cv/gate/{id}/cmd` ·
`cv/gate/{id}/telemetry` · `cv/officer/{id}/beacon` · `cv/incident/new` ·
`cv/dispatch/{officer_id}` · `cv/venue/advisory` · `cv/venue/state` ·
`cv/sys/heartbeat/{device}` (retained + LWT).

Shared implementation of this contract lives in **`crowdvision._lib`**
(`messages.py` envelope/topics/badges, `mqttc.py` paho+LWT, `config.py` YAML
loader). Use it or emit raw JSON — both conform.

## HARD RULES (never violate)
1. **Code to `docs/MESSAGES.md`, never another lane's internals.**
2. **Badges never lie.** `inference_backend`/`latency_ms`/`model_id` reflect what
   ACTUALLY ran: `qnn-npu-hexagon-v73` / `cpu` / `cloud-ai100` / `template-local`
   / `litert-gpu` / `litert-npu` / `sarvam-edge` / `sim-replay`.
3. **NPU verification uses `onnxruntime.get_ep_devices()`, NEVER
   `get_available_providers()`** (ORT 2.x QNN EP is a plugin EP; it won't appear
   in `get_available_providers()`).
4. **Never commit** model weights, `.litertlm/.onnx/.dlc/.pte`, or Qualcomm
   runtime binaries. `download_models.py` fetches at setup with license notices.
5. **All tunables in `config/*.yaml`** — nothing hardcoded.
6. **Every module runnable standalone AND against `sim/`.** `pytest sim/tests`
   passes headless.
7. **Stale-feed policy:** camera LOST > 10 s ⇒ zone `UNKNOWN`, gates **hold**
   state, operator alerted. Fail safe, never guess.
8. **Windows ARM64 host** (Surface X Elite): pure-Python deps only in the Gamma
   lane (paho-mqtt, fastapi, uvicorn, websockets, pyyaml, numpy, opencv-python).
   Broker = mosquitto at the venue, **amqtt** in sim/dev. **`resource/` PDFs are
   confidential — never push them.**

_Ask the human before: adding deps beyond the approved set, changing
`docs/MESSAGES.md`, or touching another lane's stubs beyond their contract._

## Lane ownership (directories are owned; conflicts stay rare)
| Lane | Owner | Owns |
|---|---|---|
| **Alpha** — Brain | vision + engine | `zone-brain/vision/*`, `zone-brain/engine/*`, `verify_npu.py`, `zone-brain/bench/{detect,mesh}` , `power_delta.ps1` |
| **Beta** — Hands | devices | `gate-node/*` (UNO Q App Lab + Bridge RPC), `field-app/*` (OnePlus Kotlin) |
| **Gamma** — Glue | connect + visible | broker/LWT, `sim/*`, `zone-brain/server/*` (dashboard), `venue-tier/*`, `config/*`, `tools/*`, `bench/` (network + cloud RTT), `_lib/*` |
| **Delta** — Story/Ops | non-code | `README.md`, `docs/*` prose, `THIRD_PARTY_LICENSES.md`, benchmarks running, compliance, the clock, narration |

**Coordination notes:**
- `zone-brain/bench/e2e_bench.py` is stubbed for Alpha, but the frame→gate e2e
  semantics are Gamma's per the Role Assignment — it is drivable by `sim/` and
  Gamma's `bench/`. Align before G4.
- `download_models.py`, `setup.ps1`, `run_demo.ps1` live in Alpha's
  `zone-brain/scripts/` but are cross-lane setup — edit by agreement.

## Git / workflow
Trunk-based: small commits straight to `main`, `git pull --rebase` before push,
lanes own their dirs. Repo private until Sun ~11:00, then public before submit.
**Two-strike bug rule** (two 20-min attempts, then the pre-agreed workaround).
**G4 03:00 = FEATURE FREEZE** (bugs + docs only after).

## Gates (Delta's call is final)
G0 14:00 devices/NPU/cloud/≥3 feeds/Bridge echo · G1 17:00 NPU detect <40 ms +
≥3 feeds · G2 21:00 e2e in sim + Sarvam decision · G3 00:30 p95 <2 s, ≥4 feeds ·
**G4 03:00 FREEZE** · G5 09:00 README/benches/Releases/compliance · **G6 SUBMIT
by Sun 12:15**.

## Run it
```bash
pip install -e .                 # editable; pulls the approved deps
python -m crowdvision.sim --all  # embedded amqtt broker + full sim mesh
# dashboard: http://localhost:8000   (also on the LAN IP)
pytest sim/tests                 # headless message-loop tests
```

---
## Current Status (keep updated — teammates inherit this)
_Last updated: 2026-07-11 (Sat, build day) by Gamma._

**Scaffold (Phase A):** ✅ DONE, pushed to `origin/main`.
- Packaging (`pip install -e .` verified), `crowdvision._lib`, full `docs/MESSAGES.md`, all lane stubs, config templates, `TEAM_START.md`, README/LICENSE/THIRD_PARTY/.gitignore.

**Gamma lane (Phase B):**
- ✅ **B1 sim harness** — `python -m crowdvision.sim --all` works: embedded amqtt broker + 5 feeds (scripted surge) + decider + virtual gate + virtual officer. Full kill-shot chain fires (density → gate.command → telemetry → incident → nearest-officer dispatch → template-local advisory). `pytest sim/tests` = **5 passed, headless**. Honest badges (`sim-replay`). **This is the integration surface — build your lane against it.**
- ✅ **B2 broker + LWT** — `mosquitto.conf` (venue) + embedded amqtt (sim); `_lib/mqttc` sets LWT + retained heartbeat on `cv/sys/heartbeat/{device}`; gate.command QoS1+retained+TTL.
- ⬜ B3 dashboard · ⬜ B4 venue-tier · ⬜ B5 calibrate/config polish · ⬜ B6 benches.

**Integrate now:** run `python -m crowdvision.sim --all`, then point your lane's MQTT at `127.0.0.1:1883` and code to `docs/MESSAGES.md`.

**⚠️ Compliance:** the `resource/` PDFs were pushed earlier (commit 8e666da) and are on GitHub. `.gitignore` blocks them going forward; purge/private decision pending with Sachin.

**Blockers:** none.
