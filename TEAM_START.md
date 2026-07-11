# TEAM_START — read this, then start (5 min)

CrowdVision scaffold is live. Every lane can build in parallel **right now**
without stepping on each other. Target: **full loop green in sim by 22:00 IST
tonight.** This file is your on-ramp; `CLAUDE.md` is the deeper reference.

## 60-second orientation
Edge-first crowd safety: **SENSE → PREDICT → ACT → INFORM**, frame → red-gate in
< 2 s, on the edge. You own one lane; you talk to the others **only through MQTT
messages** defined in `docs/MESSAGES.md`. If the right JSON lands on the right
topic, your side works — you never read another lane's code.

## First 5 minutes
```bash
git clone <repo-url> crowdvision && cd crowdvision   # or: git pull --rebase
pip install -e .            # editable install; pulls the approved deps
python -m crowdvision.sim --all     # sim harness (Gamma commit #2 — landing shortly)
pytest sim/tests            # headless message-loop tests
```
Then open **`CLAUDE.md`** (hard rules + lane map) and **`docs/MESSAGES.md`** (the
contract). Your lane's stub files already contain the exact topics + payloads you
publish/consume, with `TODO(<you>)`.

## Rules of engagement — so nobody's Claude breaks shared things
1. **Stay in your lane's directory.** Owners:
   - **Alpha** → `zone-brain/vision/*`, `zone-brain/engine/*`, `verify_npu.py`, `zone-brain/bench/{detect,mesh}`, `power_delta.ps1`
   - **Beta** → `gate-node/*`, `field-app/*`
   - **Gamma** → `sim/*`, `zone-brain/server/*`, `venue-tier/*`, `config/*`, `tools/*`, `bench/*`, `_lib/*`
   - **Delta** → `README.md`, `docs/*` prose, `THIRD_PARTY_LICENSES.md`, benchmarks, compliance
2. **Never edit these without pinging Gamma first:** `docs/MESSAGES.md`,
   `_lib/*`, `pyproject.toml`, or another lane's files. Changing the contract is a
   cross-lane event.
3. **Code to `docs/MESSAGES.md`, not to another lane's internals.** Use the
   helpers in `crowdvision._lib` (envelope/topics/badges/MQTT+LWT) or emit raw
   JSON — both are fine as long as the envelope matches.
4. **Badges never lie** (Hard Rule 2): `inference_backend`/`latency_ms`/`model_id`
   must reflect what ACTUALLY ran. No claiming the NPU when it's CPU/sim.
5. **No new dependencies** beyond the approved set (paho-mqtt, amqtt, fastapi,
   uvicorn, websockets, pyyaml, numpy, opencv-python). Ask Gamma if you think you
   need one.
6. **Git:** `git pull --rebase` before push · small commits straight to `main` ·
   commit only your lane's dir · never commit weights/`.onnx`/`.litertlm`/runtime
   binaries/`.env`/`resource/` (`.gitignore` already blocks them).
7. **Done = it shows in sim.** If your JSON appears on the dashboard or
   `pytest sim/tests` passes, your piece works — regardless of hardware.

## Give YOUR Claude Code this kickoff (copy-paste)

**Alpha (vision + engine):**
> You are Alpha on CrowdVision. Read `CLAUDE.md` and `docs/MESSAGES.md` first, then
> the stubs in `zone-brain/vision/` and `zone-brain/engine/` — they already define
> the exact topics + payloads. Implement ONLY files under `zone-brain/vision/`,
> `zone-brain/engine/`, and `zone-brain/scripts/verify_npu.py`. Code to
> `docs/MESSAGES.md`; publish `zone.density.update` + `camera.health`; consume
> nothing outside the contract. Do NOT edit `docs/MESSAGES.md`, `_lib/`,
> `pyproject.toml`, `config/*`, or any other lane's files — if you need a contract
> or config change, stop and tell me (Gamma). Use `crowdvision._lib.messages` for
> envelopes/badges. Badges must be honest (`qnn-npu-hexagon-v73` only when the QNN
> EP is truly attached — verify with `get_ep_devices()`, never
> `get_available_providers()`; else `cpu`). No new deps. Test against
> `python -m crowdvision.sim --all` and `pytest sim/tests`. `git pull --rebase`
> before push; commit only `zone-brain/`.

**Beta (gate node + officer app):**
> You are Beta on CrowdVision. Read `CLAUDE.md` and `docs/MESSAGES.md` first, then
> `gate-node/python/main.py`, `gate-node/sketch/sketch.ino`, and
> `field-app/README_FIELD_APP.md` — the topics + payloads are specified there.
> Implement ONLY files under `gate-node/` and `field-app/`. Subscribe
> `cv/gate/{id}/cmd`, actuate over the Bridge, publish `cv/gate/{id}/telemetry`;
> subscribe `cv/dispatch/{officer_id}`, publish `officer.beacon` + `incident.new`.
> **Bridge RPC method names must be pinned from the App Lab built-in examples /
> UNO Q User Manual — never invent them.** Do NOT edit `docs/MESSAGES.md`, `_lib/`,
> `pyproject.toml`, or other lanes' files — ping me (Gamma) for contract changes.
> Badges honest (`litert-gpu` for FunctionGemma). No new deps beyond
> `gate-node/python/requirements.txt`. Test your MQTT against
> `python -m crowdvision.sim --all` (the sim gate/officer mirror your topics).
> `git pull --rebase` before push; commit only `gate-node/` / `field-app/`.

**Delta (story + docs + compliance + clock):**
> You are Delta on CrowdVision. Read `CLAUDE.md` first. You own `README.md`,
> `docs/*` prose (ARCHITECTURE/DEMO/DEVICES — seeded, expand them),
> `THIRD_PARTY_LICENSES.md`, running the bench scripts + embedding results, the
> compliance checklists (§n/§o), and the clock/gates. Do NOT write or edit code,
> `_lib/`, or `docs/MESSAGES.md` (that's the contract — Gamma owns changes). Fill
> the 5 team names+emails in `README.md` (verify the 5th is present). Enforce
> gates; call the compressed timeline below.

## Compressed timeline — finish by 22:00 IST (Delta owns the clock)
> Times assume a ~15:00 start; Delta shifts the anchors. Two-strike bug rule
> (two 20-min tries, then the pre-agreed workaround). Nothing new after M4.

| Milestone | Target | Everyone's exit condition |
|---|---|---|
| **M0 — Onboard** | +30 min | pulled · `pip install -e .` ok · read CLAUDE.md + MESSAGES.md · lane claimed |
| **M1 — First JSON** | +2 h | each lane emits/consumes ITS message types correctly against sim (Gamma's sim harness is up by M0+45m) |
| **M2 — Wired** | +4 h | density → risk → `gate.command` → telemetry ACK; dispatch → ack; dashboard renders zones/gates/officers/log |
| **M3 — Full loop in sim** | 20:00 | one command shows the kill-shot end-to-end: surge → AMBER→RED → gate flips → officer acks → provenance in the log |
| **M4 — Freeze core** | 21:00 | venue tier + template fallback · per-gate override · feed-health chips · `pytest sim/tests` green · **feature freeze** |
| **M5 — Polish + dry-run** | 22:00 | benchmarks (stub→real where hardware allows) · README pass · one timed demo dry-run · commit + push |

## Where things are
- Contract: `docs/MESSAGES.md` · Rules + lanes: `CLAUDE.md` · Shared code:
  `crowdvision._lib` · Config: `config/*.yaml` · Sim: `sim/` (Gamma, landing next)
  · Dashboard: `zone-brain/server/` (Gamma) · Status: bottom of `CLAUDE.md`.
