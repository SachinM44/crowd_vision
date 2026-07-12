# field-app — OnePlus 15 Officer App (Kotlin)

OWNER: **Beta**. **BUILT.** Single-module Gradle project; code to
`docs/MESSAGES.md`, never to another lane's internals.

## Role
Officer-1 endpoint on the OnePlus 15 (Officer-2 = a second install on Phone-H —
set the officer id on the first screen). No VLM anywhere: officer eyes win; the
phone structures text, it doesn't see.

## What it does
- **PUBLISH** `cv/officer/{id}/beacon` (#7) every 3 s — GPS via AOSP
  `LocationManager` (no Play Services). **Never fabricates a position**: with no
  fix yet, it simply does not beacon.
- **SUBSCRIBE** `cv/dispatch/{id}` (#6) → status flips to `enroute` and it
  immediately publishes a beacon carrying `ack_dispatch_id` — **that beacon IS
  the ack** (§4G).
- **PUBLISH** `cv/incident/new` (#5) — the AI beat, below.
- **LWT + retained heartbeat** on `cv/sys/heartbeat/{id}` (set before connect).
- Runs in a **foreground service**, so beacons and dispatches survive screen-off.

MQTT is the Eclipse Paho **Java** client (`org.eclipse.paho.client.mqttv3`),
not the `paho.android.service` artifact — that one is unmaintained and breaks on
API 31+. We own the lifecycle in `FieldService`.

## Incident reporting (the AI beat)
Free text → **FunctionGemma 270M** (LiteRT-LM, **GPU**) → `report_incident(...)`
→ **schema validation** → `incident.report` with `structured{}`, `schema_valid`,
and honest badges `model_id:"functiongemma-270m"`, `inference_backend:"litert-gpu"`,
`ttft_ms`, `latency_ms`.

**Schema-invalid ⇒ no-op.** A hallucinated field never dispatches an officer;
the UI pushes you to the dropdown **form fallback** on the same screen
(`model_id:"dropdown-form"`, `inference_backend:"cpu"`, `latency_ms:0`).

**Badges never lie (Hard Rule 2).** The shipped FunctionGemma artifact
(`Mobile_actions_q8_ekv1024.litertlm`) is a CPU/GPU build — there is no sm8750
NPU build of it — so this path is `litert-gpu` and never `litert-npu`. If the
LiteRT-LM engine is unavailable at runtime, `StructurerFactory` falls back to a
deterministic keyword structurer badged `keyword-rules` / `cpu`. It never
borrows FunctionGemma's badge.

## Build
```bash
# JDK 17 + Android SDK (platform 35, build-tools 35). No Android Studio needed.
cd field-app

gradle assembleDebug                    # ships WITHOUT LiteRT-LM (keyword structurer)
gradle assembleDebug -PwithLlm=true     # + FunctionGemma 270M (litert-gpu)

adb install -r app/build/outputs/apk/debug/app-debug.apk
```
`-PwithLlm` is a build flag on purpose: the LiteRT-LM artifact moves between
releases, and a dependency-resolution failure must never block the demo build.
If the Maven coordinate does not resolve, drop the LiteRT-LM AAR into
`app/libs/` — `LlmEngine` binds it by reflection and nothing else changes.

Release APK → GitHub Releases (never commit it — `.gitignore`):
```bash
gradle assembleRelease      # debug-signed so it is installable from Releases
```

## Getting the model onto the phone
```bash
adb push Mobile_actions_q8_ekv1024.litertlm \
  /sdcard/Android/data/com.crowdvision.field/files/models/
```
If the OEM build blocks shell writes into `Android/data`, push it to
`/sdcard/Download/` and use the app's **Import model** button (SAF) instead.

## Tests — no phone required
```bash
cd field-app && gradle :app:test        # envelope shape, schema gate, parser, structurer
python tools/check_field_contract.py    # the SAME messages, checked by the REAL
                                        # crowdvision._lib validate_envelope()
```
`MqttLiveTest` additionally drives the shipped Paho client against a live broker
and asserts the dispatch → ack loop. It skips itself when no broker is up:
```bash
python -m crowdvision.sim --all --real-officers officer-1,officer-2
cd field-app && gradle :app:testDebugUnitTest --tests '*MqttLiveTest'
```
Both officer slots are reserved on purpose: the sim's officer-2 sits *on* the
demo incident, so nearest-officer selection would always pick it over a real
phone (that is correct — it is what the two-dot demo shows).

## On the phone, against the mesh
```bash
python -m crowdvision.sim --all --real-officers officer-1
```
Enter the laptop's LAN IP (`ipconfig`) — **not** 127.0.0.1 — and officer id
`officer-1`, then **Go on duty**. The officer dot moves on the dashboard; a RED
surge dispatches; the ack flips it. Airplane mode → LWT flips the heartbeat.

## Benches
"Run bench" writes `BENCH:functiongemma` JSON (TTFT/latency percentiles, tok/s,
schema-valid rate over 20 scripted prompts) to the app's external files dir; the
"E2B NPU probe" button writes `BENCH:e2b_probe` (§4J — benchmark only, badge
`litert-npu` **only** if it truly ran on the v81 NPU; a failure is recorded as a
failure). Pull and embed:
```bash
adb pull /sdcard/Android/data/com.crowdvision.field/files/bench/functiongemma.json \
         bench/out/functiongemma.json
python bench/embed.py
```
A bench produced by the keyword fallback labels itself as such in the markdown —
it is never presented as a model number.
