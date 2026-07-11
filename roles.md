# CrowdVision — Role Assignment (3 Technical + 1 Ops)

Companion to Build Plan v9. Print this page or keep it open on a phone. Every hour, every person knows exactly what they're doing without consulting the 600-line plan.

---

## The Four Roles

### ALPHA — The Brain (strongest developer)
**Owns:** the entire zone-brain on the Surface Laptop — everything the NPU touches and everything that makes safety decisions.

| Permanent ownership | What this means concretely |
|---|---|
| Vision pipeline | `capture.py` (5-feed RTSP + file ingest, watchdog), `scheduler.py` (round-robin freshest-frame), `detect_qnn.py` (shared QNN session), `homography.py`, `density.py` |
| Tracker + gate lines | `tracker.py` (centroid tracker), `gatelines.py` (real lines on C4 feed, virtual lines on zone views) |
| Risk engine | `risk.py` (EWMA, TTT, flow conservation, hysteresis, stale-feed policy), `playbooks.py` |
| NPU verification | `verify_npu.py` — runs it first thing Saturday, owns the proof artifact |
| Benchmarks (vision) | `detect_bench.py`, `mesh_bench.py` (5-feed sustained soak), `power_delta.ps1` |

**Alpha does NOT touch:** the gate node, the phone app, the dashboard frontend, or any documentation file. If Alpha is debugging the QNN session at 2 a.m., nothing else should interrupt that.

**Pre-event (July 8–10):** kicks off AI Hub exports (YOLO ×2, Genie bundle in WSL2), assembles the 60-image calibration set, writes the full vision pipeline and scheduler against file feeds on the personal laptop, runs the mesh dress rehearsal (July 10, 60 min, 4 RTSP + 1 file through the pipeline).

---

### BETA — The Hands (comfortable with both Android/Kotlin and Arduino/C++)
**Owns:** every physical device that isn't the Surface — the UNO Q gate node and the OnePlus officer app. Beta is the person whose work judges can *touch and watch*.

| Permanent ownership | What this means concretely |
|---|---|
| Gate node (UNO Q) | `gate-node/` — the full App Lab app: `sketch.ino` (Bridge RPC: matrix patterns, RGB, Knob/Buzzer/Thermo behind feature flags), `main.py` (MQTT client, fail-safe state machine, LWT logic) |
| Officer app (OnePlus) | `field-app/` — Kotlin + Compose: MQTT dispatch receive/ack, GPS beacon (AOSP LocationManager), incident reporting (FunctionGemma 270M integration + dropdown form fallback), Officer-2 instance on Phone-H |
| Bridge RPC | The single highest-risk integration — Beta owns de-risking it pre-event and being the first to test it on real hardware Saturday 13:00 |
| E2B NPU probe | Saturday 13:30 timeboxed 30-min probe on the OnePlus: load the model, capture result, done — Beta then returns to the officer app |
| Benchmarks (devices) | FunctionGemma TTFT/tok-s, Bridge RPC round-trip, gate actuation timing |

**Beta does NOT touch:** the vision pipeline, the risk engine, the dashboard, or docs. Beta's hands are literally on the UNO Q and the phone during the demo.

**Pre-event (July 8–10):** downloads FunctionGemma + E2B model + NPU `.so` set; builds the Kotlin officer app skeleton (MQTT, dispatch, beacon, report, form, E2B probe flag behind a toggle), `assembleRelease` → APK; writes the full gate-node App Lab app; pins Bridge API names from the User Manual + built-in examples (guide warns they vary by version); runs the mocked-Bridge test; installs IP Webcam on all camera phones (C1–C4), presets 640×480 @ 12 fps.

---

### GAMMA — The Glue (full-stack: Python backend + JS frontend + cloud integration)
**Owns:** everything that makes the system *visible and connected* — the MQTT broker, the dashboard, the cloud venue tier, the camera mesh config, and the sim harness.

| Permanent ownership | What this means concretely |
|---|---|
| MQTT broker | `mosquitto` setup on the Surface (or `amqtt` fallback); topic structure; LWT configuration for every device |
| Dashboard | `zone-brain/server/` — FastAPI + WebSocket fan-out, Leaflet local-CRS floorplan, feed-health chips, zone/gate/officer/incident rendering, **event log with decision provenance**, per-gate operator override buttons, backend+latency badges on every message |
| Cloud venue tier | `venue-tier/` — AI Inference Suite REST client, trilingual advisory prompts, sim-zone publisher (2 SIM zones), `template_fallback.py`, Sarvam adapter slot |
| Camera mesh config | `config/cameras.yaml` (RTSP URLs, resolution, fps), `config/devices.yaml` (IPs), `config/zones.yaml` (polygons, thresholds) — Gamma writes the configs, Alpha's pipeline reads them |
| Calibration tool | `tools/calibrate.py --camera c1..c4 --verify` — Gamma runs it Saturday with Delta positioning phones |
| Sim harness | `sim/` — `sim_feeds.py` (5 looping file feeds), `sim_gate.py`, `sim_officer.py`, `sim/tests/` |
| Benchmarks (network) | `net_bench.py` (hotspot throughput, RTSP drop rate), `e2e_bench.py` (frame→gate round-trip), Cloud AI 100 RTT |
| Attendee QR view (stretch) | `server/attendee.py` — if time exists post-G4, Gamma builds it |

**Gamma does NOT touch:** the vision pipeline internals, the QNN session, the phone app, or the gate node sketch. Gamma's integration testing is done via MQTT messages — if the right JSON arrives on the right topic, Gamma's side works regardless of what produced it.

**Pre-event (July 8–10):** builds the full dashboard + broker + sim harness; gets `--sim-all` working end-to-end (the judges' install path — this must be done by July 10); writes all config files; builds the venue-tier client; tests hotspot throughput with the real phone mesh (July 10 dress rehearsal with Alpha).

---

### DELTA — Story & Ops (non-technical; the conscience)
**Owns:** everything that isn't code — which is worth **35 points** (Innovation framing 25 + Presentation 15, minus the parts that are inherent in the code). Delta is the reason the team doesn't lose points to exhaustion, missed deadlines, or a fumbled demo.

| Permanent ownership | What this means concretely |
|---|---|
| The clock | Announces every gate (G0–G6) on time, calls the pre-agreed fail branch if the gate is red, enforces the two-strike bug rule, calls feature freeze at G4 03:00. **Delta's authority on gates is absolute** — no "five more minutes." |
| Demo narration | Primary Narrator during the 5-minute demo. Knows the script cold. Rehearses ×2 Sunday morning. Owns the 3:30 cue card (drop-dead jump to Numbers). Delivers the hook, the kill-shot punchline, and the close. |
| Documentation | README (from the template, filled), ARCHITECTURE.md, MESSAGES.md, DEMO.md, DEVICES.md, THIRD_PARTY_LICENSES.md. Writes them in real-time as features land — never as a 6 a.m. panic. |
| BENCHMARKS.md | Runs the bench scripts (they're one-command), collects the JSON output, embeds the tables. Delta doesn't write the scripts — Alpha/Beta/Gamma do — but Delta runs them and owns the doc. |
| Compliance | §n + §o checklists: all five names+emails (including the 4th member), MIT license, no sponsor marks, no social media posts (§17.c), scope-confirmation email, loaner agreement, Form submission by 12:15. **Delta screenshots every compliance action.** |
| Physical ops | Modulino sprint at 12:00 distribution (be first in line); camera phone positioning + charging audits (17:00, 23:00, 02:30, 08:30); "GATE 3" card folded from venue paper; demo station reset Sunday 12:15. |
| Fresh-clone test | Sunday 06:00: follows the README cold on a personal laptop — the test is whether a *non-author* can reproduce the setup. Fixes go to docs, not code. This is Delta's most important morning action. |
| Backup video | Sunday 07:00: records the 2-minute screen capture of the full live loop; stores on the Surface desktop + a personal phone. |
| Sarvam listener | Attends the 11:30–12:00 Sarvam session; captures any API/key/model offer; reports to Gamma at lunch for the G2 adopt/skip decision. |
| Q&A prep | Holds the three pre-rehearsed answers (cloud-only? occlusion? operator acceptance?) + the energy answer + the camera-realism answer. If a judge asks during the demo and the Narrator stumbles, Delta can interject. |

**Delta does NOT:** write code, debug code, touch the terminal, or make technical decisions. If Delta is coding at any point, the plan has failed. Delta's value is being the fresh eyes, the clock, and the voice.

---

## Schedule Remapped to 3+1

| Time | ALPHA (Brain) | BETA (Hands) | GAMMA (Glue) | DELTA (Story) |
|---|---|---|---|---|
| **Sat 10:00** | Check-in | Check-in | Check-in | Check-in; **written scope confirmation** with organizers (gate lines + camera mesh); request outlet-adjacent table; ask demo A/V + Cloud creds |
| **11:00–12:00** | Kickoff + DevRel masterclass (all attend) | Kickoff | Kickoff | **Sarvam session 11:30 — dedicated listener** |
| **12:00–13:00** | Lunch | Lunch | Lunch | **Sprint Modulino distribution table** (sign out 1× Knob/Buzzer/Thermo); Team Lead signs loaner; lunch |
| **13:00–14:00** | Surface: wheelhouse install → `verify_npu.py` (NPU proof) | **UNO Q first boot: Blink + Bridge RPC echo** (the highest-risk moment) → OnePlus APK install | Phone-H hotspot up; broker started; camera phones configured (with Delta positioning); RTSP URLs into `cameras.yaml`; all feeds visible in `capture.py` | Camera phone positioning (lean C1–C4 against objects, plug into charge); Cloud AI 100: one REST round-trip test |
| **13:30–14:00** | (continues NPU verification) | **E2B NPU probe** (30-min timebox, hard stop 14:00; result recorded either way) | (continues mesh config) | Announce **G0 at 14:00** |
| **14:00–17:00** | Feed A + C1 through shared QNN session; per-frame ms measured; add remaining feeds to scheduler | Gate state machine: MQTT subscription → Bridge RPC → matrix/RGB patterns; Modulino feature flags | Dashboard rendering: floorplan + fake zones + feed-health chips; broker topic structure | **Per-camera calibration with Gamma** (`calibrate.py --camera c1..c4 --verify` — Delta positions, Gamma clicks); README skeleton draft |
| **17:00** | — | — | — | Announce **G1**: detection on NPU <40 ms AND ≥3 feeds flowing? Call the branch. |
| **17:00–20:00** | Homography per camera → density → tracker → real gate lines (C4) + virtual lines → risk states | Fail-safe timer + knob override + buzzer chirp (if secured) | Zones/gates/officers/incidents live on dashboard + event log with provenance fields | Bench harness dry run (run the scripts Alpha/Beta wrote, check output format); **charging audit #1 (17:00)**; start ARCHITECTURE.md |
| **19:30–20:15** | Dinner (shift 1 with Beta) | Dinner (shift 1 with Alpha) | Dinner (shift 2 with Delta) | Dinner (shift 2 with Gamma) |
| **20:00–21:00** | Integration: send density → sim gate → dashboard, full loop in sim | Integration: officer app MQTT wiring; Officer-2 on Phone-H | Integration: cloud advisory call + venue view (2 SIM zones) + uplink-cut handling | — |
| **21:00** | — | — | — | Announce **G2**: end-to-end in sim? Sarvam adopt/skip? Call the branches. |
| **21:00–24:00** | TTT predictor + flow conservation + hysteresis + stale-feed policy + playbooks P1/P2/P3 | **Real gate end-to-end** — physical LEDs flip from live density; nearest-dispatch + ack chain | Cloud advisory wiring; template fallback; (Sarvam if adopted — 90 min timebox ends ~22:30) | MESSAGES.md; DEMO.md (demo script from §l); surge clips trimmed; stopwatch overlay verified |
| **24:00** | Midnight rehearsal (all): one full live run, rough stopwatch | Midnight rehearsal | Midnight rehearsal | Midnight rehearsal — operate the stopwatch; record the number |
| **00:30** | — | — | — | Announce **G3**: loop stable, p95 < 2 s with ≥4 feeds? Open should-haves or converge on core. |
| **00:30–03:00** | Should-have (fall-confirm) OR hardening (reconnects, watchdog tuning) | Should-have (Thermo/Buzzer wiring) OR hardening (Bridge robustness) | Should-have (replay heatmap) OR hardening (QoS audit, badge polish) | **Run BENCHMARKS** (quiet venue = clean numbers): mesh_bench, detect_bench, e2e_bench, net_bench; embed JSON into BENCHMARKS.md; **charging audit #2 (02:30)** |
| **03:00** | — | — | — | Announce **G4: FEATURE FREEZE.** After this: bugs, docs, demo only. |
| **03:00–06:00** | Sleep pod 1 (03:00–04:30) → watch + soak test monitoring (04:30–06:00) | Sleep pod 1 (03:00–04:30) → sleep pod 2 (04:30–06:00) | Watch + soak test (03:00–04:30) → sleep pod 2 (04:30–06:00) | Sleep (03:00–06:00) — Delta needs to be sharp for narration. Camera phones stay on charge, screens off. |
| **06:00–07:00** | Final vision-side bug fixes (demo-critical only, two-strike rule) | Final device-side bug fixes | Final dashboard/cloud fixes | **Fresh-clone test**: follow README cold on personal laptop. Fix **docs**, not code. Report gaps to whoever owns the section. |
| **07:00–08:00** | Final benchmarks: 300-frame NPU vs CPU, 5-feed aggregate, battery deltas | FunctionGemma TTFT/tok-s ×20, Bridge RPC ×100 | e2e ×50, hotspot throughput, Cloud RTT ×30 | **Record 2-min backup video** (screen capture of full live loop); store on Surface + personal phone; **charging audit #3 (08:30)** — every phone >80% |
| **08:00–09:00** | Benchmark results → JSON committed | Benchmark results → JSON committed | Benchmark results → JSON committed; BENCHMARKS.md auto-embedded | README final pass: does every claim match reality? All 4 names+emails present? THIRD_PARTY_LICENSES.md done? |
| **09:00** | — | — | — | Announce **G5**: submission-ready? Triage: README > run scripts > benchmarks > polish. **Full §n + §o compliance audit.** |
| **09:00–10:00** | Demo rehearsal #1 (timed — Alpha drives) | Demo rehearsal #1 (Beta at the gate, holds OnePlus) | Demo rehearsal #1 (Gamma ensures dashboard is on-screen) | Demo rehearsal #1: **Delta narrates, times it, calls the 3:30 cue if overrun** |
| **10:00–11:00** | Demo rehearsal #2 + **feed-mix lock**: C2/C3 live only if zero dropouts across both rehearsals | Demo rehearsal #2 | Demo rehearsal #2 | Demo rehearsal #2; make "GATE 3" card from venue paper |
| **11:00–11:45** | Repo freeze: `git tag v1.0`, push | Verify APK in Releases downloads | Verify `--sim-all` from the public repo on a phone in incognito | Verify all 4 names+emails, MIT LICENSE, no sponsor logos, no demeaning labels |
| **11:45–12:15** | — | — | — | **SUBMIT Microsoft Form. Screenshot confirmation.** Never later than 12:15. Announce **G6.** |
| **12:15–13:00** | Reset demo station; cache one cloud advisory response as slide backup | Reposition UNO Q + phone; top up charges | One silent end-to-end dry run | Place "GATE 3" card; final cue-card review; lunch |
| **13:00–16:00** | **DEMO: Driver** — operates the Surface, starts the surge clip, scrolls the log, clicks overrides, shows the numbers slide | **DEMO: Device hands** — stands at Gate 3, turns the Knob (or points at the override), holds the OnePlus for the officer beat | **DEMO: Dashboard monitor** — ensures the screen shows the right view at the right beat; switches to venue view for beat 4; toggles Phone-H data for the uplink-cut | **DEMO: Narrator** — delivers the script, times the beats, calls the backup video if anything dies, handles Q&A |
| **16:00** | Device return (Surface) | Device return (UNO Q, OnePlus, Modulinos) | — | Loaner checklist verified; all devices returned |

---

## Decision Authority

| Decision | Who decides | Rule |
|---|---|---|
| Gate pass/fail (G0–G6) | **Delta** | Delta's call is final. No "five more minutes." |
| Technical triage (which bug to fix, which workaround to take) | **Alpha** (vision/engine) · **Beta** (devices) · **Gamma** (dashboard/cloud) — each in their domain | Two 20-min attempts, then the pre-planned workaround. If they disagree across domains, Alpha breaks the tie (the core is on the PC). |
| Feature freeze exception after G4 | **Nobody.** G4 is a lock, not a suggestion. | Bugs and docs only. |
| Feed-mix lock (which cameras stay live) | **Alpha + Delta jointly** after rehearsal #2 | Minimum live = Feed A + C1 + C4. C2/C3 live only if zero dropouts in both rehearsals. |
| Demo script changes | **Delta** | The script is rehearsed; ad-libs at 4 a.m. don't make it in. |
| Scope-confirmation wording to organizers | **Delta** (non-technical framing is Delta's job) | Alpha reviews for technical accuracy before sending. |
| Sarvam adopt/skip at G2 | **Gamma** (owns the integration) with Delta's clock authority on the timebox | Adopt only if Gamma estimates ≤90 min AND the core (G2) is green. |

---

## One-Line Mantras (tape to the table)

- **Alpha:** "The NPU session is sacred. Nothing interrupts the vision pipeline."
- **Beta:** "Bridge echo first. If the gate doesn't flip, nothing else matters."
- **Gamma:** "If the dashboard doesn't show it, it didn't happen."
- **Delta:** "I own the clock, the voice, and the checklist. I never touch the terminal."