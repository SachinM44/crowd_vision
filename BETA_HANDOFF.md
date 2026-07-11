# BETA_HANDOFF — everything built so far + exactly what Beta must build

**Audience:** Beta (the Hands) and Beta's Claude Code session. Read this top to
bottom before writing a line. It is the single source of truth for: what exists
(Alpha + Gamma, 100% built and verified), how it all connects, the exact MQTT
contract your two devices must speak, how to test against the running system on
this laptop, and every gotcha that will otherwise burn your time.

**It is SUNDAY. Submission (Microsoft Form) is 12:15 IST today. Demos 13:00–16:00.
Feature freeze rules apply — build the MVP contract below, nothing else.**

---

## 0. TL;DR for Beta's Claude session

```
You are Beta on CrowdVision. You own ONLY gate-node/ (Arduino UNO Q) and
field-app/ (OnePlus Kotlin app). Everything else is DONE and working — do not
touch sim/, zone-brain/, venue-tier/, _lib/, config/, docs/MESSAGES.md, or
pyproject.toml. You talk to the system ONLY via MQTT messages (section 4).
Your stand-ins already exist and work: sim/sim_gate.py and sim/sim_officer.py
mirror your exact topics — replicate their observable behavior on real hardware
and everything integrates with zero changes elsewhere. Test against
`python -m crowdvision.sim --all --real-gates G3` (section 6). If your JSON
shows on the dashboard at http://<laptop-ip>:8000, your side works.
```

---

## 1. What CrowdVision is (30 seconds)

Edge crowd-crush prevention: **SENSE → PREDICT → ACT → INFORM**, frame → red
gate in **< 2 s**, no human in the loop, no video leaves the venue.

- **Zone-brain (Surface X Elite)** — Alpha: 5-camera mesh → one shared YOLOv8
  NPU session → density/m² per zone → analytic risk (EWMA→TTT) → playbooks fire
  `gate.command`. DONE (hardware-free verified; NPU steps happen on the Surface).
- **Glue (broker/dashboard/sim/venue tier/configs)** — Gamma. DONE.
- **Gate node (UNO Q) + Officer app (OnePlus)** — **Beta. THE ONLY UNBUILT LANE.**
- **Venue tier (Cloud AI 100)** — Gamma: trilingual advisories, off the safety
  path, auto-falls-back to local templates. DONE.

Prize criteria: Technical 40 · Use-case 25 · Deployment 20 · Presentation 15.
Multi-device prize = second target. Honesty is doctrine: **badges never lie**.

---

## 2. What is ALREADY BUILT and VERIFIED (do not rebuild, do not modify)

### Gamma (the glue) — all on `main`, all tested
| Piece | Where | State |
|---|---|---|
| MQTT broker | embedded amqtt (auto-starts with sim, **binds 0.0.0.0:1883** — your devices connect to the laptop's LAN IP) + `mosquitto.conf` for the venue | ✅ |
| Message contract + helpers | `docs/MESSAGES.md` (the law) + `crowdvision._lib` (`messages.py`, `mqttc.py`, `config.py`) | ✅ |
| Sim harness | `sim/` — feeds, scripted decider, **sim_gate (your gate stand-in)**, **sim_officer (your app stand-in)**, dispatcher, 6 headless pytest | ✅ |
| Dashboard | `zone-brain/server/` — FastAPI+WS on **0.0.0.0:8000**; floorplan, zones by risk, **gate icons + per-gate cards fed by YOUR telemetry**, **officer dots fed by YOUR beacons**, provenance decision log, per-gate override buttons (publish `gate.command` w/ `triggered_by:"operator-override"`), venue panel (real + 2 SIM zones + uplink), sparklines, live camera previews | ✅ |
| Venue tier | `venue-tier/` — Cloud AI 100 REST client → `template-local` fallback (EN/HI/KN), venue.state, uplink-cut | ✅ |
| Configs | `config/zones.yaml`, `cameras.yaml`, `playbooks.yaml` (P1/P2/P3), `devices.yaml`, `.env.example` | ✅ |
| Tools | `tools/calibrate.py` (homography), `tools/find_cameras.py` (scan phone IPs), `tools/live_capture.py` (real-camera CPU bridge w/ YOLO boxes) | ✅ |
| Benches | `bench/{net,e2e,cloud_rtt}_bench.py` + `bench/embed.py` → auto-fill `docs/BENCHMARKS.md` markers | ✅ |
| Dispatcher | `sim/replay.py --dispatch_only` — nearest-officer dispatch on RED when the REAL engine owns gates (runs automatically under `--no-feeds`) | ✅ |

### Alpha (the brain) — merged (PR #1), deep-reviewed by Gamma, all claims verified
| Piece | Where | State |
|---|---|---|
| Vision | `zone-brain/vision/{capture,scheduler,detect_qnn,homography,tracker,gatelines,density,pipeline}.py` | ✅ 10/10 self-tests |
| Engine | `zone-brain/engine/{risk,flow,playbooks}.py` — analytic, config-driven (EWMA α=.3, 60 s slope, 10% hysteresis, 5 s dwell, LOST>10 s ⇒ UNKNOWN) | ✅ |
| NPU proof | `zone-brain/scripts/verify_npu.py` (`get_ep_devices()`, never `get_available_providers()`) | ✅ (real NPU run happens on the Surface) |
| Benches | `detect_bench.py`, `mesh_bench.py` (wiring verified; real numbers need the X Elite) | ✅ |
| Alpha handoff | `alpha.md` / `zone-brain/README_ALPHA.md` — read it if you touch anything near his lane | ✅ |

### Proven end-to-end THIS session (evidence, not claims)
1. **Judges' path** (`python -m crowdvision.sim --all`): HTTP+WS+override live;
   kill-shot fires (RED → `CLOSE_DIVERT_LEFT`), officer goes enroute, EN/HI/KN
   advisory, SIM zones in the venue panel. PASS.
2. **Hardware path** (`--all --no-feeds` + Alpha's real `pipeline.py`): his
   engine fires P1→P2→P3 with real provenance; dispatcher escalates; officer-2
   acks; **220 density msgs, 0 invalid envelopes**. PASS.
3. `pytest sim/tests` = **6 passed** (rerun after every change).
4. Real cameras (2 phones + laptop webcam) drove the dashboard with YOLO-CPU
   person boxes (`tools/live_capture.py`). PASS.

---

## 3. How your devices join the network

- Everything meets on one LAN (venue: Phone-H hotspot; dev: this laptop's network).
- **Broker = this laptop**, port **1883**, anonymous, keepalive ~15 s. It starts
  automatically with any `python -m crowdvision.sim ...` command (or use
  `mosquitto -c mosquitto.conf`). It binds **0.0.0.0** — reachable from your
  devices at the laptop's LAN IP.
- Find the laptop IP: `ipconfig` → IPv4 (e.g. `10.149.252.6`). If a device can't
  connect, it's almost always (a) different Wi-Fi network, or (b) Windows
  firewall — allow Python on private networks when prompted.
- Dashboard: `http://<laptop-ip>:8000` from ANY device on the LAN.
- Venue IPs get recorded in `config/devices.yaml` (Gamma's file — tell Gamma).

---

## 4. THE CONTRACT — exactly what your devices say and hear

Everything is MQTT + JSON with this envelope (see `docs/MESSAGES.md`, the law):

```json
{ "type": "<message type>", "v": 1, "ts": "2026-07-12T07:41:03.214+05:30",
  "src": "<your device id>", "seq": 4812, "payload": { } }
```
- `ts`: ISO-8601 **IST (+05:30)**, milliseconds.
- `src`: `"uno-q-G3"` for the gate node, `"officer-1"` / `"officer-2"` for phones.
- `seq`: int, monotonically increasing per device.
- Neither device can `import crowdvision` (UNO Q Linux + Android) — **build the
  JSON by hand** exactly as below. `gate-node/python/requirements.txt` already
  pins `paho-mqtt`; Android uses Paho/HiveMQ Kotlin.

### 4A. GATE NODE (UNO Q) — subscribe `cv/gate/G3/cmd`  *(QoS 1, RETAINED, TTL)*
You receive (from Alpha's engine, the sim decider, or a dashboard override):
```json
{ "type": "gate.command", "v": 1, "ts": "...", "src": "zonebrain-A", "seq": 4812,
  "payload": {
    "gate_id": "G3",
    "action": "CLOSE_DIVERT_LEFT",
    "allowed": ["OPEN","CLOSE","DIVERT_LEFT","DIVERT_RIGHT",
                "CLOSE_DIVERT_LEFT","CLOSE_DIVERT_RIGHT","SAFE_FLASH"],
    "reason": "zone A density 4.1 rising 0.31/min, TTT 2:40",
    "playbook_id": "P2",
    "triggered_by": "zone:A/risk:RED",      // or "operator-override" or "sim-scripted:seq:N"
    "ttl_s": 120 } }
```
**⚠ CRITICAL — retained-message TTL check:** commands are published **retained**,
so the instant you (re)connect+subscribe, the broker hands you the LAST command.
You MUST parse `ts`, and if `now - ts > ttl_s`, **discard it** (do not actuate a
stale command at boot). This is exactly what `ttl_s` is for. Fresh commands:
actuate immediately via Bridge RPC.

### 4B. GATE NODE — publish `cv/gate/G3/telemetry` *(the ACK — QoS 1)*
Two modes (mirror `sim/sim_gate.py`, your stand-in):
1. **Immediately after actuating a command** (this is what the dashboard, the e2e
   bench, and the stopwatch measure):
```json
{ "type": "gate.telemetry", "v": 1, "ts": "...", "src": "uno-q-G3", "seq": 88,
  "payload": {
    "gate_id": "G3", "state": "CLOSE_DIVERT_LEFT",
    "actuated_ms": 6,            // >0 = real actuation ACK (measure it!)
    "bridge_rpc_ms": 4,          // Bridge round-trip you measured
    "override": "NONE",          // or "KNOB" / "DASHBOARD" when a human overrode
    "failsafe_active": false,
    "temp_c": 33.5,              // Modulino Thermo if secured, else config default
    "modulinos": {"knob": false, "buzzer": false, "thermo": false},  // honest auto-detect
    "link_ok": true,
    "provenance": "deterministic-mcu",
    "triggered_by": "zone:A/risk:RED", "playbook_id": "P2" } }   // echo from the command
```
2. **Steady-state 1 Hz** — same shape, current held `state`, `actuated_ms: 0`.

### 4C. GATE NODE — heartbeat + LWT `cv/sys/heartbeat/uno-q-G3` *(retained)*
- On CONNECT, register a **Last Will**: topic `cv/sys/heartbeat/uno-q-G3`,
  retained, QoS 1, payload = envelope with
  `{"type":"sys.heartbeat", ..., "payload":{"device":"uno-q-G3","state":"offline","reason":"lwt"}}`.
- After connecting, publish the same retained topic with `"state":"online"`.
- On clean shutdown publish `"offline"` then disconnect.
(This is how "drop the UNO Q from the hotspot" becomes a demoable fail-safe beat.)

### 4D. GATE NODE — fail-safe state machine (MCU side)
- Broker link lost ⇒ MCU **holds LAST_SAFE state** (deterministic even if Linux
  hiccups), Python side auto-reconnects with backoff, chirp-once on rejoin.
- Physical override (Modulino Knob, if secured) ⇒ actuate + publish telemetry
  with `"override":"KNOB"`. All Modulinos are OPTIONAL — feature-flag/auto-detect,
  never a hard dependency.
- Gate actions → physical outputs: 8×13 matrix (← → arrows, stop ✕), 4 RGB gate
  state (green/red), buzzer = "steward chirp" (named as such — never crowd-facing
  audio).

### 4E. GATE NODE — Bridge RPC (PINNED names — never invent)
From the App Lab built-in examples / UNO Q User Manual (the guide warns names
vary by App Lab version — verify on the real board FIRST):
```python
# python/main.py  (MPU, Linux)
from arduino.app_bridge import Bridge     # App Lab helper — ships on the board
bridge = Bridge()
bridge.call("gate_set_state", state)      # -> sketch actuates matrix + RGB
```
```cpp
// sketch/sketch.ino  (MCU)
#include <Arduino.h>
#include "Bridge.h"
void gate_set_state(const char* state) { /* matrix + RGB pattern */ }
void setup() { Bridge.begin(); Bridge.provide("gate_set_state", gate_set_state); }
void loop()  { Bridge.update(); }
```
Run on the board: `arduino-app-cli app start ./gate-node` (logs: `... app logs`).
**First action on real hardware: Blink + RPC echo.** Contract stubs with fuller
notes already exist: `gate-node/python/main.py`, `gate-node/sketch/sketch.ino`.

### 4F. OFFICER APP (OnePlus) — publish `cv/officer/officer-1/beacon` *(~every 3 s, QoS 0)*
```json
{ "type": "officer.beacon", "v": 1, "ts": "...", "src": "officer-1", "seq": 12,
  "payload": {
    "officer_id": "officer-1",
    "lat": 12.9698, "lon": 77.7500, "accuracy_m": 5.0,   // AOSP LocationManager (NOT Play Services)
    "status": "available",                                // -> "enroute" after a dispatch
    "battery_pct": 82,
    "ack_dispatch_id": null } }
```
The dashboard draws you as a dot (green=available, blue=enroute). The dispatcher
uses beacons for **nearest-officer selection (haversine)** — two officers make
that visibly real (officer-2 can stay simulated: see §6).

### 4G. OFFICER APP — subscribe `cv/dispatch/officer-1` *(QoS 1)*
```json
{ "type": "dispatch.order", "v": 1, "ts": "...", "src": "dispatcher", "seq": 31,
  "payload": {
    "dispatch_id": "dsp-dispatcher-001", "officer_id": "officer-1",
    "incident_id": "inc-dispatcher-001",
    "lat": 12.9699, "lon": 77.7501,
    "reason": "nearest officer to crush-risk incident",
    "route_hint": "via central aisle", "eta_s": 45,
    "playbook_id": "P2", "triggered_by": "dispatcher:seq:128" } }
```
**ACK semantics (must match sim_officer):** on receipt, show the dispatch in the
UI, set `status:"enroute"`, and immediately publish a beacon carrying
`"ack_dispatch_id": "<dispatch_id>"`. That beacon IS the ack.

### 4H. OFFICER APP — publish `cv/incident/new` *(QoS 1)* — the AI beat
Free text (+ optional photo) → **FunctionGemma 270M** (LiteRT-LM, **GPU** backend,
artifact `Mobile_actions_q8_ekv1024.litertlm`) → structured call → **validate
against this schema**; invalid ⇒ **no-op** (never a wrong action); dropdown form
on the same screen = zero-AI fallback:
```json
{ "type": "incident.report", "v": 1, "ts": "...", "src": "officer-1", "seq": 44,
  "payload": {
    "incident_id": "inc-1207-014", "officer_id": "officer-1",
    "lat": 12.9698, "lon": 77.7500,
    "text": "man collapsed near gate 2 barrier, crowd gathering",
    "structured": { "type": "medical", "location_hint": "gate-2-barrier",
                    "severity": "high", "needs": ["medic","crowd-control"] },
    "schema_valid": true, "photo_ref": null,
    "model_id": "functiongemma-270m",
    "inference_backend": "litert-gpu",      // HONEST — provided artifact is CPU/GPU
    "latency_ms": 380, "ttft_ms": 210 } }
```
Form-fallback reports: same shape, `"model_id":"form"`, `"inference_backend":"none"`? —
NO: keep the AI badge rule honest — for the form path use
`"model_id":"dropdown-form"`, `"inference_backend":"cpu"`, `"latency_ms":0`,
`"ttft_ms":0`, `"schema_valid":true`.

### 4I. OFFICER APP — heartbeat + LWT `cv/sys/heartbeat/officer-1` *(retained)* — same pattern as 4C.

### 4J. E2B NPU probe (timeboxed 30 min, benchmark-only — NOT a feature)
Behind an app flag: load `gemma-4-E2B-it_qualcomm_sm8750.litertlm` with the NPU
`.so` set copied from the official LiteRT-LM sample app
(`libLiteRtDispatch_Qualcomm.so`, `libQnnHtp.so`, `libQnnHtpV81Skel.so`,
`libQnnHtpV81Stub.so`, `libQnnSystem.so`, `libGemmaModelConstraintProvider.so`).
Kotlin config per the Dev Guide: `EngineConfig(modelPath=..., backend=Backend.NPU(nativeLibDir))`.
Success → record TTFT + tok/s, badge `litert-npu`, put numbers in
`docs/BENCHMARKS.md` (BENCH:e2b_probe marker). Failure → screenshot the exact
error, record that. **Either way it ends on time and FunctionGemma stays the
shipped structurer.** Never commit the `.litertlm` or `.so` files (gitignored;
license-restricted).

---

## 5. What Beta builds (definition of done per piece)

### gate-node/ (UNO Q App Lab app)
- [ ] `python/main.py`: paho client → laptop broker; LWT (4C); subscribe
      `cv/gate/G3/cmd`; **TTL check on retained commands (4A)**; `bridge.call`
      to actuate; publish telemetry ACK + 1 Hz steady state (4B); reconnect w/
      backoff; fail-safe trigger to MCU on link loss.
- [ ] `sketch/sketch.ino`: `Bridge.provide` the actuation fn(s); matrix arrow /
      stop patterns; RGB states; LAST_SAFE hold; optional Knob/Buzzer/Thermo
      behind auto-detect flags.
- [ ] `app.yaml` / `sketch.yaml`: pin real manifest keys + FQBN from the User
      Manual on the actual board (stubs mark every TODO).
- [ ] Bench numbers for Delta: `bridge_rpc_ms` ×100, `actuated_ms` per command
      (BENCH:gate marker).
- **DONE =** with `python -m crowdvision.sim --all --real-gates G3` running on
  this laptop, the physical gate flips on the surge, its card on the dashboard
  updates from YOUR telemetry, the override button moves the real LEDs, and
  pulling the UNO Q off Wi-Fi flips its heartbeat to offline (LWT) while the
  MCU holds state.

### field-app/ (OnePlus Kotlin app)
- [ ] MQTT (Paho/HiveMQ Kotlin) → laptop broker; LWT (4I).
- [ ] GPS beacon every ~3 s via **AOSP LocationManager** (no closed deps) (4F).
- [ ] Dispatch receive → UI + enroute + ack-beacon (4G).
- [ ] Incident: text/photo → FunctionGemma (LiteRT-LM, GPU) → schema-validate →
      publish (4H); dropdown form fallback on the same screen.
- [ ] E2B probe behind a flag (4J) — benchmark only.
- [ ] FunctionGemma bench: TTFT + tok/s ×20 scripted + 5 free-form, schema-valid
      rate (BENCH:functiongemma marker).
- [ ] `assembleRelease` → `field-app.apk` → **GitHub Releases** (never commit the
      APK; `.gitignore` blocks it). Officer-2 = second install (Phone-H).
- **DONE =** with `--real-officers officer-1` running, your dot moves on the
  dashboard, a RED surge dispatches you (or sim officer-2 if closer — two dots
  prove nearest-selection), your ack flips you blue, and your typed incident
  appears in the decision log with honest badges.

---

## 6. How to test on THIS laptop (recipes — the sim yields to your hardware)

The sim components are **subtractive**: flags tell them which devices are real
so they never fight your topics.

```bash
# 0) once: pip install -e ".[dev]"     (already installed on this laptop)

# 1) Full sim baseline (nothing real yet) — see what "working" looks like:
python -m crowdvision.sim --all
#    -> http://<laptop-ip>:8000 ; watch G3 flip on the surge every ~45 s.

# 2) REAL UNO Q owns G3 (sim keeps G1,G2; sim officers stay):
python -m crowdvision.sim --all --real-gates G3

# 3) REAL OnePlus owns officer-1 (sim keeps officer-2 -> nearest-dispatch demo):
python -m crowdvision.sim --all --real-officers officer-1

# 4) Both real:
python -m crowdvision.sim --all --real-gates G3 --real-officers officer-1

# 5) Full hardware path (Alpha's real engine too — 2 terminals):
python -m crowdvision.sim --all --no-feeds --real-gates G3 --real-officers officer-1
python zone-brain/vision/pipeline.py --dry-run        # (or --require-npu on the Surface)

# 6) All-real everything (venue): broker+dashboard+venue+dispatcher only:
python -m crowdvision.sim --all --no-feeds --no-gate --no-officer
```

**Debug like Gamma does** — watch the raw bus while you develop:
```python
# quick monitor (run on the laptop):
python - <<'PY'
import time
from crowdvision._lib import mqttc
n = mqttc.MqttNode("beta-monitor").connect()
n.on("cv/#", lambda t, m: print(t, "|", m["type"], "|", m["payload"]))
time.sleep(120)
PY
```
And validate any payload you build: `crowdvision._lib.messages.validate_envelope(msg)`
returns `[]` when it conforms.

**Regression rule:** after ANY change, `pytest sim/tests` must stay **6 passed**.

---

## 7. Gotchas that WILL bite you (learned this session)

1. **Retained gate.command replays at (re)connect** — TTL-check or you actuate
   history (4A). The sim gate doesn't bother (it's disposable); the REAL gate must.
2. **Bind vs connect**: broker + dashboard bind 0.0.0.0; your devices connect to
   the laptop's **LAN IP**, never 127.0.0.1. Phone IPs change per hotspot —
   the laptop's does too; re-check `ipconfig` at the venue.
3. **Windows firewall** silently blocks 1883/8000 the first time — allow Python
   (private networks). Test with `Test-NetConnection <ip> -Port 1883` from
   PowerShell or a phone MQTT app before blaming your code.
4. **paho-mqtt 2.x API** (on the UNO Q): `mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, ...)`
   — see `_lib/mqttc.py` for the tolerant pattern; `will_set` BEFORE `connect`.
5. **Badges never lie** (Hard Rule 2): `litert-gpu` for FunctionGemma (the
   provided artifact is CPU/GPU — saying NPU is a disqualifying-grade lie),
   `litert-npu` ONLY if the E2B probe truly ran on the v81 NPU.
6. **Commands carry provenance** — echo `triggered_by`/`playbook_id` back in the
   actuation telemetry so the log tells one story.
7. **UNKNOWN ≠ crowded**: if you see grey zones, a camera is covered/LOST — the
   system holds gates rather than guessing. Expected behavior, not a bug.
8. **Never commit**: weights, `.litertlm`, `.apk`, Qualcomm `.so`/dll, `.env`,
   `resource/` (confidential PDFs — already in history, do not add more).
9. **Git**: trunk-based; `git pull --rebase origin main` before push; commit only
   `gate-node/` + `field-app/` (+ BENCH json via Delta). Repo goes public ~11:00
   today — nothing embarrassing in commit messages.
10. **`sim_gate`/`sim_officer` are executable specs** — when in doubt about a
    field or timing, open them and copy the behavior exactly.

---

## 8. Remaining project checklist (beyond Beta's code)

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | UNO Q gate node end-to-end (this doc §5) | **Beta** | ⬜ THE critical path |
| 2 | OnePlus officer app end-to-end (§5) | **Beta** | ⬜ THE critical path |
| 3 | E2B NPU probe (30-min timebox, benchmark row) | Beta | ⬜ |
| 4 | X Elite: `setup.ps1` → stage YOLO → `verify_npu.py` → `pipeline.py --require-npu` | Alpha | ⬜ venue |
| 5 | Real RTSP ×4 + `tools/calibrate.py` per camera | Gamma+Alpha | ⬜ venue |
| 6 | Real benches: detect / mesh soak / power / e2e / net / FunctionGemma / gate | Alpha+Beta+Delta | ⬜ venue |
| 7 | Cloud AI 100 creds in `.env` → real `cloud-ai100` advisory + RTT bench | Gamma | ⬜ check-in |
| 8 | README: 5 names+emails, claims match reality (Rules §7.c) | Delta | ⬜ |
| 9 | `docs/` prose final + BENCHMARKS embedded + APK/models in Releases | Delta | ⬜ |
| 10 | Fresh-clone test on a non-author laptop | Delta | ⬜ 06:00 |
| 11 | Backup demo video ×2 locations | Delta | ⬜ 07:00 |
| 12 | Repo public ~11:00 → tag v1.0 → **SUBMIT Form by 12:15** → screenshot | Delta | ⬜ HARD DEADLINE |

Everything NOT in this table is **done and verified** (sections 2, and the test
evidence there). The judges' zero-hardware path (`download_models.py` →
`sim --all` → localhost:8000) works today, end to end.

---

## 9. File map (where everything lives)

```
crowdvision/
├── BETA_HANDOFF.md        ← you are here
├── CLAUDE.md              ← hard rules, lane map, live status (keep updated)
├── TEAM_START.md          ← per-lane kickoff prompts + timeline
├── alpha.md               ← Alpha's deep handoff (zone-brain internals)
├── docs/MESSAGES.md       ← THE contract (never edit without Gamma)
├── docs/{ARCHITECTURE,BENCHMARKS,DEMO,DEVICES,LIVE_CAMERAS}.md
├── _lib/                  ← envelope/topics/badges + paho wrapper (installed as crowdvision._lib)
├── sim/                   ← broker, feeds, decider+dispatcher, sim_gate, sim_officer, tests
├── zone-brain/vision|engine|scripts|bench   ← Alpha (DONE)
├── zone-brain/server/     ← dashboard (DONE)
├── venue-tier/            ← cloud tier + fallback (DONE)
├── gate-node/             ← ★ BETA: app.yaml, python/main.py, sketch/sketch.ino (stubs w/ contracts)
├── field-app/             ← ★ BETA: README_FIELD_APP.md spec; Kotlin project goes here
├── config/                ← zones/cameras/playbooks/devices (+ .env.example)
├── tools/                 ← calibrate, find_cameras, live_capture
└── bench/                 ← net/e2e/cloud benches + embed.py
```

*Mantras: Alpha — "the NPU session is sacred." Beta — "Bridge echo first; if the
gate doesn't flip, nothing else matters." Gamma — "if the dashboard doesn't show
it, it didn't happen." Protect the core: sense → predict → act → inform, under
two seconds, on the edge.*
