# field-app — OnePlus 15 Officer App (Kotlin + Compose)

OWNER: **Beta** (TODO(beta)). This directory holds the Android Studio project.
Contract only for now — code to `docs/MESSAGES.md`, never to another lane's
internals.

## Role
Officer-1 endpoint on the OnePlus 15 (Officer-2 = a second instance on Phone-H).
No VLM anywhere — officer eyes win; the phone structures text, it doesn't see.

## MQTT (Paho/HiveMQ Kotlin) — code to docs/MESSAGES.md
- **SUBSCRIBE** `cv/dispatch/{officer_id}` (#6 dispatch.order) → show dispatch +
  route hint → **ACK** back.
- **PUBLISH** `cv/officer/{officer_id}/beacon` (#7) — GPS via AOSP
  `LocationManager` (no Google Play Services dependency).
- **PUBLISH** `cv/incident/new` (#5 incident.report) — see below.
- **LWT + heartbeat** `cv/sys/heartbeat/officer-{id}` (retained).

## Incident reporting (the AI beat)
Free text (+ optional photo) → **FunctionGemma 270M** (LiteRT-LM, GPU backend) →
`report_incident(...)` → **schema validation**. Emit `incident.report` with
`structured{...}`, `schema_valid`, badges `model_id:"functiongemma-270m"`,
`inference_backend:"litert-gpu"`, `ttft_ms`, `latency_ms`.
**Schema-invalid ⇒ no-op** (never a wrong action). Dropdown **form fallback** on
the same screen = zero-AI path.

## E2B NPU probe (Saturday 13:30, timeboxed 30 min — behind a flag)
Load `gemma-4-E2B-it_qualcomm_sm8750.litertlm` on the Hexagon v81 NPU with the
NPU `.so` set (from the official LiteRT-LM sample — never redistributed, see
`.gitignore` + `THIRD_PARTY_LICENSES.md`). Success → capture TTFT/tok-s, badge
`litert-npu`. Failure → screenshot the exact error. **Either outcome is a
benchmark row** (BENCHMARKS.md #7). It does NOT replace FunctionGemma as the
shipped structurer (Constraint 4).

## Build
`assembleRelease` → `field-app.apk` → attach to GitHub Releases (never commit the
APK — `.gitignore`). `adb install Releases/field-app.apk`.

## TODO(beta)
- Kotlin skeleton (MQTT, dispatch/ack, beacon, report, form) · LiteRT-LM wiring ·
  E2B probe flag · APK in Releases.
