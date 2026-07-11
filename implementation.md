# CrowdVision — AI-Assistant Prompt Pack v2 (Repo-Aligned)

Rebuilt against the actual boilerplate at `SachinM44/crowd_vision`. This supersedes v1: it references the real package (`crowdvision._lib`), real file paths, real config field names, the Hard Rules from `CLAUDE.md`, and your team's actual **M0–M5** milestones.

**Why the jigsaw already fits:** the contract isn't a document anyone has to remember — it's importable code. `crowdvision._lib.messages` holds the envelope, topics, and honest badge constants; `_lib.mqttc.MqttNode` is the MQTT client with LWT baked in; `_lib.config` loads the YAML. Everyone codes to `docs/MESSAGES.md` / `_lib`, tests against the running sim, and the lanes were never really separate. Gamma has already stood up the integration surface (`python -m crowdvision.sim --all` fires the full kill-shot chain, `pytest sim/tests` = 5 green). So the job now is: **Alpha and Beta fill their stubs against that live sim; Gamma finishes calibrate + benches and supports; Delta writes and runs the clock.**

---

## Part 0 — How to use this pack (with Claude Code)

Your team runs Claude Code with a per-lane session, and `CLAUDE.md` is auto-loaded as context — so these prompts are shorter than v1 and lean on that. Workflow per person:

1. Open Claude Code in the repo root. It reads `CLAUDE.md` automatically.
2. Paste your lane's **Session Primer** (Part 2) as the first message. It stays open all sprint.
3. Fire the **milestone prompts** in order (M1 → M5, then the Saturday hardware G-prompts).
4. Before every push: `git pull --rebase`, commit **only your lane's directory**, push to `main`.
5. Definition of done for every task: **it shows up in the sim** (`python -m crowdvision.sim --all` → http://localhost:8000) or `pytest sim/tests` stays green. Hardware-independent.

**The eight Hard Rules (from `CLAUDE.md`, quoted so your assistant honors them):** (1) code to `docs/MESSAGES.md`, never another lane's internals; (2) badges never lie; (3) NPU check uses `get_ep_devices()`, never `get_available_providers()`; (4) never commit weights/`.litertlm`/`.onnx`/`.dlc`/`.pte`/runtime binaries/`.env`/`resource/`; (5) all tunables in `config/*.yaml`; (6) every module runnable standalone AND against `sim/`, `pytest sim/tests` green; (7) stale-feed policy — LOST >10 s ⇒ zone UNKNOWN, gates hold, alert; (8) Windows ARM64 host, pure-Python approved deps only, no new deps without Gamma. **Ask the human before** changing `docs/MESSAGES.md`, `_lib/*`, `pyproject.toml`, or touching another lane's files.

---

## Part 1 — The Contract, as code (the shared cheat-sheet)

Every technical lane imports these. Paste this cheat-sheet into any session that's fuzzy on the API.

```python
from crowdvision._lib import messages as M, config as C
from crowdvision._lib.mqttc import MqttNode, ttl_properties

# --- Envelope & serialization ---
msg = M.envelope(M.T_ZONE_DENSITY, src="zonebrain-A", seq=n, payload={...})  # {type,v,ts,src,seq,payload}
raw = M.dumps(msg);  back = M.loads(raw);  M.now_ts()  # ISO-8601 IST
errs = M.validate_envelope(msg)  # [] == valid; used by sim/tests

# --- Topics (builders, never hand-format) ---
M.topic_zone_density("B") -> "cv/zone/B/density"    ;  M.topic_camera_health("c3")
M.topic_gate_cmd("G3")    ;  M.topic_gate_telemetry("G3")
M.topic_officer_beacon("2");  M.topic_dispatch("2") ;  M.topic_heartbeat("unoq")

# --- Message-type ids ---
M.T_ZONE_DENSITY  M.T_CAMERA_HEALTH  M.T_GATE_COMMAND  M.T_GATE_TELEMETRY
M.T_OFFICER_BEACON  M.T_INCIDENT_REPORT  M.T_DISPATCH_ORDER
M.T_VENUE_ADVISORY  M.T_VENUE_STATE  M.T_ATTENDEE_REPORT  M.T_HEARTBEAT

# --- Honest backend badges (Hard Rule 2) — pick the one that ACTUALLY ran ---
M.BACKEND_QNN_NPU  "qnn-npu-hexagon-v73"   M.BACKEND_CPU        "cpu"
M.BACKEND_CLOUD    "cloud-ai100"           M.BACKEND_TEMPLATE   "template-local"
M.BACKEND_LITERT_GPU "litert-gpu"          M.BACKEND_LITERT_NPU "litert-npu"
M.BACKEND_SARVAM   "sarvam-edge"           M.BACKEND_SIM        "sim-replay"

# --- Enums ---
M.GATE_ACTIONS  # OPEN CLOSE DIVERT_LEFT DIVERT_RIGHT CLOSE_DIVERT_LEFT CLOSE_DIVERT_RIGHT SAFE_FLASH
M.RISK_GREEN M.RISK_AMBER M.RISK_RED M.RISK_UNKNOWN
M.FEED_OK M.FEED_DEGRADED M.FEED_LOST

# --- MQTT node (LWT + retained heartbeat already wired) ---
node = MqttNode("zonebrain-A", host="127.0.0.1").connect()
node.on(M.topic_gate_telemetry("G3"), handler)         # subscribe
node.publish(M.topic_zone_density("B"), M.T_ZONE_DENSITY, payload, qos=0)
node.next_seq()  ;  node.publish_heartbeat(state)  ;  ttl_properties(120)  # for gate.command

# --- Config (single source of truth; Gamma writes, everyone reads) ---
C.zones() C.cameras() C.playbooks() C.devices()  ;  C.env("AISUITE_KEY")
```

**Config field names you must match (from `config/*.yaml`):**
- `cameras.yaml`: each camera has `transport` (file|webcam|rtsp), `url`, `zone_id`, `homography` (3×3); `c4` additionally has `gate_id: G3` and `gate_line: [[x,y],[x,y]]`; `defaults: {resolution, fps_cap}`.
- `zones.yaml`: `risk_bands_default {amber_at:3.0, red_at:5.0, hysteresis_pct:10, dwell_s:5}`; `predictor {ewma_alpha:0.3, slope_window_s:60, stale_lost_s:10}`; each zone `{name, camera_id, area_m2, polygon, gate_id}`.
- `playbooks.yaml`: `P1/P2/P3` each `{name, when, gate_action, ttl_s, reason_template}`; `gate_action` must be in `M.GATE_ACTIONS`.

**AI-message payloads** carry `inference_backend` / `latency_ms` / `model_id`; **commands** carry `playbook_id` / `triggered_by` / `ttl_s`. `validate_envelope()` enforces both — run it. Full payload examples live in `docs/MESSAGES.md`; your stub files already contain the exact publish/consume payloads with `TODO(<lane>)` markers.

---

## Part 2 — Lane Prompt Packs

### ALPHA — The Brain (vision + engine) · CRITICAL PATH

Alpha's lane is greenfield against a working sim. Everything Alpha builds is validated the moment its JSON appears on Gamma's dashboard.

**A0 · Session Primer** (paste once)

> You are Alpha on CrowdVision (Claude Code, repo root — you've read `CLAUDE.md`). You own ONLY `zone-brain/vision/*`, `zone-brain/engine/*`, `zone-brain/scripts/verify_npu.py`, and `zone-brain/bench/{detect_bench,mesh_bench}.py` + `power_delta.ps1`. You never edit `docs/MESSAGES.md`, `_lib/*`, `pyproject.toml`, `config/*`, or another lane's files — if you need a contract or config change, stop and tell Gamma.
>
> Import the contract, don't reinvent it: `from crowdvision._lib import messages as M, config as C` and `from crowdvision._lib.mqttc import MqttNode`. Publish `M.T_ZONE_DENSITY` on `M.topic_zone_density(zone)` and `M.T_CAMERA_HEALTH` on `M.topic_camera_health(cam)`. Consume nothing outside the contract. Read all tunables from `C.zones()` / `C.cameras()` — nothing hardcoded (Hard Rule 5).
>
> The architecture is fixed and you must respect it: **ONE shared QNN session (burst) + a round-robin freshest-frame scheduler** across the 5 feeds — never 5 parallel sessions, never batching. Stale frames dropped, never queued. Pipeline: `capture.py` (RTSP/file/webcam + per-feed watchdog, OK/DEGRADED/LOST) → `scheduler.py` → `detect_qnn.py` (shared ORT session) → `homography.py` → `density.py` → `tracker.py` → `gatelines.py` (real lines on the C4/Gate-3 feed via `cameras.yaml` `gate_line`, virtual lines on zone views) → `engine/risk.py` + `flow.py` + `playbooks.py`.
>
> The risk engine is deliberately analytic, not ML — this is a rehearsed strength, not a gap: EWMA(`ewma_alpha`) → `slope_window_s` slope → TTT; flow conservation; `hysteresis_pct` + `dwell_s`; stale-feed policy (`stale_lost_s`: LOST ⇒ zone `M.RISK_UNKNOWN`, gates hold, operator alerted — Hard Rule 7). `playbooks.py` reads `C.playbooks()` and emits `gate.command` with `playbook_id` / `triggered_by` / `ttl_s`.
>
> Badges are honest (Hard Rule 2): use `M.BACKEND_QNN_NPU` ONLY when the QNN EP is truly attached — verify via `onnxruntime.get_ep_devices()`, NEVER `get_available_providers()` (Hard Rule 3) — else `M.BACKEND_CPU`. Anti-patterns that lose Technical-40 points and that you must refuse to ship: silent CPU fallback (assert the EP or fail loud), one blob latency number, queuing stale frames, guessing on a lost feed. No new deps (Hard Rule 8).
>
> For each deliverable: fill the stub's `TODO(alpha)`, keep the standalone `__main__` runnable, and give me the one-command proof — `python -m crowdvision.sim --all` shows my density on the dashboard, or `pytest sim/tests` stays green. `git pull --rebase`, commit only `zone-brain/`.

**A1 · Pre-hardware build (against the live sim — do M1→M3 in this order)**

> Build my whole pipeline against the sim now (no NPU on this laptop — abstract the detector so the SAME code selects QNN-EP on the X Elite and CPU-EP here, and refuses silent fallback). In order, each as its stub with a self-test:
> 1. `verify_npu.py` — prints `onnxruntime.get_ep_devices()`, writes timestamped raw output to `docs/verify_npu.out`; here it honestly reports the QNN EP absent. This is the Saturday proof artifact.
> 2. `vision/capture.py` — 5-feed ingest from `C.cameras()` (rtsp/file/webcam), per-feed watchdog with reconnect-backoff + stale detector, publishes `camera.health` with `M.FEED_OK/DEGRADED/LOST`.
> 3. `vision/scheduler.py` — one shared session, round-robin freshest-frame, drops stale frames, exposes per-stage counters (capture/schedule/infer/track+lines/decide) for `mesh_bench`.
> 4. `vision/detect_qnn.py` — detector wrapping one ORT session; selects QNN-EP if `get_ep_devices()` shows it, else CPU-EP, logging the backend loudly and never silently downgrading. Emits head points.
> 5. `vision/homography.py` + `vision/density.py` — per-camera homography from `cameras.yaml`, head points → density/m² per zone using `zones.yaml` polygons + `area_m2`.
> 6. `vision/tracker.py` + `vision/gatelines.py` — centroid tracker; real line-crossing on the `c4` `gate_line`, virtual lines on zone views; fill the `flow_check` block with `method: "real-gate-line/c4"` vs `"virtual-gate-line/zone-view"`.
> 7. `engine/risk.py` + `engine/flow.py` + `engine/playbooks.py` — full analytic engine + P1/P2/P3 → `gate.command`. Publish `zone.density.update` at 1 Hz.
> After each, show me it on the dashboard from `sim --all`. Then prove the stale-feed policy: kill a feed and show the zone flip to UNKNOWN with gates holding — not a guessed density.

**A2 · Saturday hardware prompts (X Elite present)**

- **G0 (first boot):** `Run verify_npu.py on the X Elite. Confirm get_ep_devices() reports the QNN EP present, commit docs/verify_npu.out, and give me a startup assertion that hard-fails if the EP is ever CPU in the demo path. Point capture.py at Feed A + C1 from cameras.yaml; confirm both in camera.health.`
- **G1 (detect <40 ms + ≥3 feeds):** `Bring Feed A + C1 through the shared QNN session; print measured per-frame ms (mean/p50/p95). Add C2–C4 to the scheduler. If a feed is unstable, confirm capture.py marks it DEGRADED/LOST without stalling the round-robin.`
- **G2→G3 (density → real gate):** `Turn on homography → density → tracker → real gate lines on c4 + virtual elsewhere; emit full zone.density.update with populated flow_check. Then fire P1/P2/P3 on the surge clip and confirm Beta's UNO Q ACKs within TTL.`
- **Benchmarks (post-G3):** `Run mesh_bench.py (10-min 5-feed soak → aggregate inf/s, effective fps/feed, per-stage, thermal check) and detect_bench.py (300 frames NPU vs CPU) and power_delta.ps1 (burst vs balanced batteryreport). Emit JSON for Delta to embed. Flag any thermal decay.`

---

### BETA — The Hands (UNO Q gate node + OnePlus officer app) · CRITICAL PATH

**B0 · Session Primer** (paste once)

> You are Beta on CrowdVision (Claude Code — you've read `CLAUDE.md`). You own ONLY `gate-node/*` (UNO Q App Lab: `sketch/sketch.ino`, `python/main.py`) and `field-app/*` (OnePlus Kotlin). You never edit `docs/MESSAGES.md`, `_lib/*`, `pyproject.toml`, or other lanes' files — ping Gamma for contract changes.
>
> Code to the contract: subscribe `M.topic_gate_cmd(id)`, actuate over the Bridge, publish `M.T_GATE_TELEMETRY` on `M.topic_gate_telemetry(id)`; on the phone subscribe `M.topic_dispatch(officer)`, publish `M.T_OFFICER_BEACON` and `M.T_INCIDENT_REPORT` on `cv/incident/new`. The gate.command you consume carries `action` (∈ `M.GATE_ACTIONS`), `playbook_id`, `triggered_by`, `ttl_s` — honor the TTL and the allowed list.
>
> **Highest-risk thing you own: the Bridge RPC** between the UNO Q's Python MPU and the MCU sketch. The App Lab helper API names vary by version and no UNO Q exists until Saturday 12:00, so you pin the exact class/method names from the built-in examples + UNO Q User Manual — never invent them — and test against a mocked Bridge pre-event. The first real-hardware action Saturday is Blink + a Bridge RPC echo, before anything else. The UNO Q runs NO model and has no camera — never claim otherwise; Gate 3's eye is a camera feed on the PC.
>
> Fail-safe is a headline demo beat: on MQTT link loss the LWT triggers and the gate holds LAST_SAFE, auto-rejoining on reconnect. The Knob is a physical human override, always logged in telemetry (`override` field).
>
> Officer app = Kotlin + Compose: MQTT dispatch recv/ack, GPS beacon via AOSP LocationManager, incident reporting via FunctionGemma 270M (LiteRT-LM, GPU, badge `M.BACKEND_LITERT_GPU`) with a dropdown form fallback; a misparse ⇒ `schema_valid:false` no-op, never a wrong dispatch. Second instance = Officer-2 on Phone-H. You also own the Saturday 13:30 timeboxed 30-min E2B NPU probe (load `gemma-4-E2B` with the NPU `.so` set behind a build flag; success → badge `M.BACKEND_LITERT_NPU` + TTFT/tok-s; failure → screenshot the exact error; either way FunctionGemma stays the shipped structurer). Hard stop 14:00.
>
> Never commit the `.so` set, `.litertlm`, or weights (Hard Rule 4) — the README documents copying them from the LiteRT-LM sample app; `download_models.py` fetches weights. Test your MQTT against `python -m crowdvision.sim --all` — the sim gate/officer mirror your topics. `git pull --rebase`, commit only `gate-node/` / `field-app/`.

**B1 · Pre-hardware build (two devices, against sim + mocked Bridge)**

> **[Gate node]** Fill `gate-node/`, testable with no hardware:
> 1. `sketch/sketch.ino` — Bridge RPC handlers for all 7 `M.GATE_ACTIONS`, driving matrix arrows + RGB (green/amber/red) + Modulino Knob/Buzzer/Thermo behind `#define` flags so it compiles and runs with none attached. Put the pinned Bridge class/method names in a clearly-marked block up top so I can correct them against the real User Manual Saturday.
> 2. `python/main.py` — `MqttNode` subscribing `M.topic_gate_cmd("G3")`, validating `action` against `M.GATE_ACTIONS` + TTL, calling the Bridge, publishing `gate.telemetry` at 1 Hz with real `actuated_ms`/`bridge_rpc_ms`. Fail-safe state machine: LWT on `M.topic_heartbeat("unoq")`, hold LAST_SAFE on link loss, auto-rejoin.
> 3. A mocked-Bridge test: swap the real Bridge for a stub, feed `main.py` a hand-crafted `gate.command` from the sim, watch the correct `gate.telemetry` return.
>
> **[Officer app]** Build the `field-app/` Kotlin/Compose skeleton → `assembleRelease` APK:
> 1. Paho/HiveMQ MQTT with LWT: subscribe `cv/dispatch/{officer_id}`, publish beacon (GPS) + `incident.report`.
> 2. Incident screen: free text → FunctionGemma 270M (LiteRT-LM GPU) → validated JSON, badge `litert-gpu`; on invalid, dropdown form + `schema_valid:false` no-op.
> 3. Dispatch recv + ack UI; nearest-officer is decided PC-side, the app just acks.
> 4. E2B probe path behind a build flag (model path + NPU backend config + TTFT/tok-s logging) so Saturday is a toggle, not an integration. Don't bundle the `.so` set/weights — document the copy step in `field-app/README_FIELD_APP.md`. Give me the gradle command + the sideload-vs-fetch checklist.

**B2 · Saturday hardware prompts**

- **G0 (THE moment):** `Walk me through UNO Q first boot: Blink, then a Bridge RPC echo with my pinned method names. If a name is wrong, help me find the right one in the App Lab examples fast. The instant the echo returns I start the state machine — nothing else in my lane matters until the gate flips. Then adb install the officer APK on the OnePlus; confirm it joins the hotspot and publishes a beacon.`
- **Probe (13:30, 30-min hard stop):** `Flip the E2B build flag, try to load gemma-4-E2B on the v81 NPU with the .so set. Success: capture TTFT/tok-s, badge litert-npu. Failure: screenshot the exact error. Either way one BENCHMARKS row, then back to the officer app at 14:00 — do not let me rabbit-hole.`
- **G1→G2:** `Wire the gate end-to-end: subscribe cv/gate/G3/cmd, drive matrix + RGB, publish telemetry. Feed a hand-crafted CLOSE_DIVERT_LEFT and confirm LEDs + ACK. Add fail-safe timer + Knob override + buzzer chirp (if secured); prove fail-safe by dropping the UNO Q off the hotspot (LWT → LAST_SAFE → auto-rejoin). Finish FunctionGemma structuring + form fallback; show a schema_valid:true and a schema_valid:false no-op.`
- **G2→G3:** `Close the physical loop: Alpha's real gate.command flips the LEDs. Then nearest-dispatch + ack chain with Officer-2 on Phone-H — two officers on the map, the closer one dispatched.`
- **Benchmarks:** `FunctionGemma TTFT/tok-s ×20, Bridge RPC round-trip ×100, gate actuation timing → JSON for Delta.`

---

### GAMMA — The Glue · MOSTLY DONE → finish + support

Gamma already shipped B1 sim, B2 broker+LWT, B3 dashboard, B4 venue-tier. Remaining: B5 `tools/calibrate.py`, B6 benches (`bench/net_bench.py`, `bench/cloud_rtt_bench.py`, `bench/embed.py`, and aligning `zone-brain/bench/e2e_bench.py`). Plus: keep the sim honest and be the contract referee.

**Γ0 · Session Primer** (paste once)

> You are Gamma on CrowdVision (Claude Code — you've read `CLAUDE.md`) and you own the contract's implementation. You own `sim/*`, `zone-brain/server/*`, `venue-tier/*`, `config/*`, `tools/*`, `bench/*`, and `_lib/*`. You are the ONLY lane allowed to change `docs/MESSAGES.md`, `_lib/*`, or `pyproject.toml` — and only after pinging Sachin, because it's a cross-lane event. The sim is the integration surface everyone builds against, so its honesty (badges = `sim-replay`) and stability are sacred. No new deps outside the approved pure-Python set (Hard Rule 8). `git pull --rebase`, commit only your dirs.

**Γ1 · Finish the lane**

> 1. `tools/calibrate.py --camera cN --verify` — click 4+ floor points per camera to solve the homography, write it back into `config/cameras.yaml` under that camera's `homography`, and `--verify` overlays the reprojected grid. Runs at the venue with Delta positioning phones. Keep it standalone.
> 2. `bench/net_bench.py` — hotspot throughput + per-stream RTSP drop rate + reconnect counts over a 10-min window (reads Alpha's `camera.health`). `bench/cloud_rtt_bench.py` — 30 advisory calls to Cloud AI 100, wall-clock RTT distribution (proves why the safety loop is edge-side).
> 3. `bench/embed.py` — collects the JSON emitted by every lane's bench script and embeds the tables into `docs/BENCHMARKS.md` (no hand-typed numbers). Delta runs this.
> 4. Align `zone-brain/bench/e2e_bench.py` with me: frame-ts → gate ACK, single-clock RTT/2 method, drivable from `sim/` and my `bench/`. Settle the Alpha/Gamma ownership seam before G4.
> Each with a `sim --all` or `pytest sim/tests` proof.

**Γ2 · Support prompts (during the sprint)**

- Camera mesh at the venue: `Help me configure the phones as RTSP sources, write the four URLs into cameras.yaml under c1–c4, and confirm all feeds show as health chips on the dashboard.`
- Resilience beat: `Verify the uplink-cut: CV_UPLINK_DOWN=1 (and physically toggling Phone-H data) stops venue.advisory while every zone keeps producing density and the gate still flips.`
- Sarvam decision at G2: `If the 11:30 session offered an API/model, estimate integration time; adopt into sarvam_adapter.py + template_fallback only if ≤90 min and the core is green — else log it as upside and skip.`
- Contract referee (any lane): `Lane X says their message isn't rendering. Do NOT edit their code. Diff their actual JSON against docs/MESSAGES.md / validate_envelope() and tell them which field is wrong.`

---

### DELTA — Story & Ops (no code) · owns docs, benchmarks-running, compliance, the clock

**Δ0 · Session Primer** (paste once)

> You are Delta on CrowdVision (Claude Code — you've read `CLAUDE.md`). You own `README.md`, the prose in `docs/*` (ARCHITECTURE / DEMO / DEVICES — seeded, expand them), `THIRD_PARTY_LICENSES.md`, running the bench scripts + embedding results via `bench/embed.py`, the §n/§o compliance checklists, and the clock (gates G0–G6, two-strike rule, G4 freeze). You never write or edit code, `_lib/*`, or `docs/MESSAGES.md` (Gamma owns the contract). Every claim in every doc must describe what ACTUALLY runs at submission — over-claiming is disqualification-grade, not style. Keep me honest; if I ask for a phrasing that over-claims, give me the accurate version instead.

**Δ1 · Docs (write as features land)**

> - `README.md`: fill the 5 team names+emails (verify the 5th is present), keep every claim to what runs; flag anything depending on a Saturday outcome (the E2B probe, the live-feed mix) so I confirm it before submit.
> - Expand `docs/ARCHITECTURE.md` from the v9 architecture (tiers, 5-feed mesh, one shared QNN session + scheduler, analytic engine, deliberate cuts). Plain-text platform names only — no Qualcomm/Snapdragon/Hexagon logos anywhere (Rules §8.f).
> - Expand `docs/DEVICES.md`: labels + IPs from `config/devices.yaml` + the per-workload power-profile rationale (burst for sustained multi-stream, balanced for interactive, efficiency for background).
> - `THIRD_PARTY_LICENSES.md`: Ultralytics AGPL-3.0, Gemma Terms, Qualcomm SDK/QNN (via pip), Leaflet BSD, Paho EPL; our code MIT. This one file turns a judge objection into a doc point.

**Δ2 · Demo, benchmarks, Q&A**

> - Turn `docs/DEMO.md` into the clean 5-minute beat sheet (hook · live mesh · kill-shot at 1:15 · officer loop · venue tier + uplink-cut · numbers · close), with roles (Narrator me, Driver Alpha, Beta at the gate, Gamma on the dashboard), the 3:30 drop-dead cue, and the pre-scripted recoveries (dead beat → play its video; feed goes amber on stage → "that's the watchdog being honest").
> - Rehearse me as narrator against the clock — flag where I'm over, where I'm dramatizing (state facts, move on), where a judge is likely to interrupt.
> - Drill the Q&A: cloud-only? · occlusion at crush density? (add: Gate 3 has a dedicated lane camera because gate throughput is where counting accuracy matters most) · operator acceptance? · the energy/power-profile question · "are those phone cameras realistic?" (stand-ins for venue CCTV over the identical RTSP contract). Two honest sentences each, quiz me until reflexive.
> - `Here's the JSON from the bench scripts — run bench/embed.py and confirm docs/BENCHMARKS.md shows clean tables with method + target columns, no hand-typed numbers.`

**Δ3 · Compliance + fresh-clone**

> - Build a printable §n + §o checklist as tick-boxes with the rule cite next to each, ordered by when I hit them: **repo/resource privacy purge (the resource/ PDFs are confidential and were pushed — confirm they're off the public repo and out of history)** → scope-confirmation email naming BOTH deltas (gate-line counting AND the phone camera mesh) for Alpha to review → Modulino sprint → charging audits (17:00/23:00/02:30/08:30) → G5 audit → Form submit by 12:15. Include the exact scope-confirmation email text.
> - Fresh-clone script (Sun 06:00): I follow the README cold on a non-author laptop — step-by-step verification list, what I should see at each step, and a gap-report template. Fixes go to docs, not code.

**Δ4 · Gate calls (Delta's authority is absolute — no "five more minutes")**

> Give me a one-line pass/fail + the pre-agreed fail branch for each gate so I can call it in 10 seconds: G0 14:00 (devices/NPU/cloud/≥3 feeds/Bridge echo) · G1 17:00 (NPU <40 ms + ≥3 feeds → else backup export / demo-min Feed A+C1+C4) · G2 21:00 (e2e in sim + Sarvam decision → else 3 feeds/1 zone/1 gate) · G3 00:30 (p95 <2 s, ≥4 feeds → open should-haves else converge) · **G4 03:00 FREEZE** (bugs+docs only) · G5 09:00 (README/benches/Releases/compliance → triage README > run scripts > benchmarks > polish) · G6 SUBMIT by 12:15, screenshot.

---

## Part 3 — Integration & Jigsaw-Fit Prompts (run against the live sim)

Because everyone codes to `_lib` / `docs/MESSAGES.md`, integration is verification, not surgery.

- **Master fit (any lane, anytime):** `Run python -m crowdvision.sim --all, open http://localhost:8000, point my MQTT at 127.0.0.1:1883, and confirm MY message type appears correctly on the dashboard / passes pytest sim/tests. If it doesn't, the fault is mine, not the sim.`
- **Alpha→Beta (density drives the real gate):** `Confirm Alpha's playbook fires a gate.command whose action is in M.GATE_ACTIONS with playbook_id/triggered_by/ttl_s, and Beta's UNO Q ACKs with gate.telemetry inside the TTL. Mismatch = one side drifted from the contract; diff against docs/MESSAGES.md, don't rewrite either component.`
- **Alpha→Gamma (kill-shot log):** `Confirm a real zone.density.update renders in the dashboard event log with playbook_id, density, TTT, triggered_by and a backend/latency badge — the exact log Alpha scrolls live during the kill-shot.`
- **Beta→Gamma (officer loop visible):** `Confirm an incident.report from the OnePlus lands as a map pin with its schema_valid state, and a dashboard dispatch reaches Officer-2 on Phone-H and gets acked.`
- **Contract-drift guard (universal):** `A message isn't being honored. Do NOT edit the other lane. Print the JSON we emit, run M.validate_envelope() on it, diff field-by-field against docs/MESSAGES.md, and tell me which of MY fields is wrong. The contract is the referee.`

---

## Part 4 — Timeline (your real M0–M5, then the Saturday hardware gates)

**Sprint to "full loop green in sim" (Delta owns the clock; ~15:00 start, finish 22:00):**

| Milestone | Target | Alpha | Beta | Gamma | Delta |
|---|---|---|---|---|---|
| **M0 Onboard** | +30 m | pull · `pip install -e .` · read CLAUDE+MESSAGES · claim lane | same | sim harness up by M0+45 | claim clock; **resource/ privacy purge** |
| **M1 First JSON** | +2 h | A1 #1–4 (verify_npu, capture, scheduler, detect vs CPU) | B1 gate `main.py` + mocked Bridge emits telemetry | Γ1 calibrate + net_bench | Δ1 README + ARCHITECTURE |
| **M2 Wired** | +4 h | A1 #5–6 (homography, density, tracker, gate lines) | B1 officer app MQTT + dispatch ack | dashboard renders new fields; referee | Δ2 DEMO.md |
| **M3 Full loop in sim** | 20:00 | A1 #7 (risk + playbooks → gate.command) | real gate reacts in sim; officer loop | venue tier + override confirmed | run stopwatch on the sim loop |
| **M4 Freeze core** | 21:00 | stale-feed policy proven; `pytest` green | fail-safe + form fallback green | `pytest sim/tests` green | **call freeze**; compliance pass |
| **M5 Polish + dry-run** | 22:00 | benches (stub→real) | benches | embed.py wiring | README pass; one timed dry-run; push |

**Saturday-into-Sunday hardware gates (when the provided devices arrive):**

| Gate | Time | Alpha | Beta | Gamma | Delta |
|---|---|---|---|---|---|
| G0 | 14:00 | verify_npu on X Elite | **Blink + Bridge echo** + APK | broker + camera mesh | announce G0; scope email sent |
| probe | 13:30 | — | E2B probe (hard stop 14:00) | — | time-keep |
| G1 | 17:00 | NPU detect + feeds | gate state machine | dashboard + calibrate live | announce G1 |
| G2 | 21:00 | density + gate lines | fail-safe + officer | cloud + resilience + Sarvam call | announce G2 |
| G3 | 00:30 | risk + playbooks (real gate) | real gate + dispatch | (+Sarvam if adopted) | announce G3; stopwatch |
| G4 | 03:00 | harden / should-have | harden / should-have | harden / should-have | **run benchmarks; FREEZE** |
| G5 | 09:00 | demo-crit fixes only | demo-crit fixes only | demo-crit fixes only | **fresh-clone test; backup video** |
| G6 | 12:15 | tag v1.0 | verify APK in Releases | verify `--sim-all` public | **SUBMIT; screenshot** |
| Demo | 13:00 | Driver | gate + OnePlus | dashboard monitor | Narrator |

---

## The one thing that makes it fit

Every technical prompt forces the same three habits: **(1) stay in your lane's directory, (2) import and emit `crowdvision._lib` / `docs/MESSAGES.md` exactly, (3) prove it in the sim before integrating.** Do those and the four lanes were never separate — they're four views of one contract that already runs.

*Protect the core: SENSE → PREDICT → ACT → INFORM, frame → red-gate under two seconds, on the edge.*