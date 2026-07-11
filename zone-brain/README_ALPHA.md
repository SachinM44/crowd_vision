# README_ALPHA — the zone-brain (vision + engine) handoff

**Audience:** the next developer taking the Alpha lane forward. Read this once, top
to bottom, before touching any file. It explains what exists, why it is shaped the
way it is, how to run and verify it with zero hardware, and exactly what is left to
do on the X Elite. Nothing here is aspirational — every "verified" claim below was
run and passed on a Windows dev machine with no cameras, no model weights, and no
NPU.

---

## 1. What Alpha is, in one paragraph

CrowdVision is an edge crowd-safety loop: **SENSE → PREDICT → ACT → INFORM**, frame
to red-gate in under 2 seconds, no human in the loop, no video leaving the venue.
**Alpha owns the entire zone-brain** — everything the NPU touches and everything
that makes a safety decision. Concretely: ingest 5 camera feeds, run one shared
YOLOv8-INT8 NPU session across all of them, turn detections into people/m² per zone,
predict each zone's time-to-danger with an analytic (non-ML) risk engine, and fire
pre-approved gate playbooks on risk transitions. Everything else — the MQTT broker,
the dashboard, the sim, the cloud venue tier, the gate hardware, the officer phone —
belongs to Gamma or Beta. Alpha talks to them **only** through MQTT messages defined
in `docs/MESSAGES.md`.

Alpha owns: `zone-brain/vision/*`, `zone-brain/engine/*`, `zone-brain/scripts/verify_npu.py`,
`zone-brain/bench/{detect_bench,mesh_bench}.py`, `zone-brain/bench/power_delta.ps1`.

---

## 2. Current status (what works, what's left)

**Everything in the Alpha lane is implemented and verified hardware-free.** The lane
went from all-stubs (`raise NotImplementedError`) to a running pipeline that drives
the full kill-shot in simulation.

Verified green on the dev machine:
- **10/10 module self-tests** (`python zone-brain/<path>.py --selftest`).
- **Full kill-shot end-to-end**: zone A GREEN → AMBER → RED → recover, firing
  `gate.command` **P1 `DIVERT_LEFT` → P2 `CLOSE_DIVERT_LEFT` → P3 `SAFE_FLASH`**,
  every MQTT envelope passing `validate_envelope()`.
- **Stale-feed policy**: a LOST feed publishes `camera.health = LOST` and
  `zone.density.update` with `risk = UNKNOWN` (null count), gates hold.
- **Cross-camera gate line**: C4's real crossings populate zone A's `flow_check`
  as `real-gate-line/c4`.
- **Live integration**: with `python -m crowdvision.sim --all --no-feeds` running
  (broker + dashboard + sim gate + officer + venue), the real pipeline publishes
  density for all 4 zones, its engine fires the gate commands, and the sim gate
  ACKs them with telemetry.
- **`pytest sim/tests` = 6 passed** (Gamma's lane, no regression).
- **Benches** emit JSON to `bench/out/`; `verify_npu.py` writes `docs/verify_npu.out`.

**Hardware-gated (deliberately deferred to the X Elite — NOT missing work):**
- Real YOLOv8 detection needs a model staged at `weights/vision/yolov8n_det_int8.onnx`
  (via `download_models.py`). Off-device the pipeline runs a scripted detector.
- The honest `qnn-npu-hexagon-v73` badge only appears when the QNN EP is truly
  attached (X Elite + `onnxruntime-qnn` from `setup.ps1`). Off-device it is `cpu`,
  loudly logged, and the `--require-npu` demo path hard-fails rather than lie.
- Real RTSP feeds + per-camera homography calibration (`cameras.yaml` currently has
  identity-matrix placeholders — see §7).
- The `detect_bench` / `mesh_bench` real numbers, and `power_delta.ps1`, run on the
  Surface. `e2e_bench.py` is a shared Alpha/Gamma seam (still a stub — see §9).

---

## 3. The data flow (what passes between modules)

This is the spine. Every arrow is a concrete Python data type; understanding these
contracts is 80% of understanding the lane.

```
config/cameras.yaml ─┐
                     ▼
   capture.CaptureFeed.latest() ──► Frame{camera_id, ts_ms, image, transport}
                     │  (per-feed watchdog; None if stale/LOST — never a queued stale frame)
                     ▼
   scheduler.Scheduler  (ONE shared session, round-robin, freshest-frame)
                     │  calls detect once per fresh frame
                     ▼
   detect_qnn.detect(session, image) ──► (boxes_xyxy, head_points_px, latency_ms)
                     │  head_point = top-centre of each person box, in IMAGE pixels
                     ▼
   scheduler.on_result(camera_id, frame, (boxes, heads_px), infer_ms)   ← the pipeline closure
                     │
                     ├─ homography.to_floor(H, heads_px) ──► heads_m   (Nx2 floor METRES)
                     ├─ tracker.update(trackset[cam], heads_m, ts) ──► TrackSet (id-stable + velocity)
                     ├─ gatelines.GateLine.block(tracks, ts) ──► {in_per_min, out_per_min, method}
                     │        (real gate cams only; stored by gate_id in a shared dict)
                     ▼
   density.publish_zone(node, zone_id, heads_m, feed_health, badges,
                        risk_state=…, gate_flow=…, fps_effective=…, ts_ms=…)
                     │  count heads-in-polygon / area_m2  → density/m²
                     ├─ risk.update(state, zone, density, ts, feed_state, temp) ──► RiskResult
                     ├─ flow.check(…) ──► flow_check{in,out,method,residual}
                     └─► publishes  cv/zone/{id}/density   (zone.density.update)
                     ▼
   playbooks.fire_if_needed(node, zone, risk, density, trend, ttt)
                     └─► on a risk TRANSITION, publishes  cv/gate/{gate_id}/cmd   (gate.command)
```

Frames are always in **image pixels** until `homography.to_floor`; everything
downstream (tracker, gatelines, density polygons in `zones.yaml`) is in **floor
metres** in the local-CRS the dashboard also uses. Keep that boundary crisp.

---

## 4. File-by-file

### engine/ (pure Python, no hardware, no cv2/ORT — the "safety brain")

- **`risk.py`** — the analytic predictor (deliberately NOT ML; this is a rehearsed
  strength, not a gap). `update(state, zone_id, density, ts_ms, feed_state, temp_c)
  -> RiskResult(zone_id, risk, density_per_m2, trend_per_min, ttt_red_s)`.
  - EWMA (`ewma_alpha`) smooths density → slope over `slope_window_s` → time-to-RED.
  - Hysteresis: a band change needs the new band to persist `dwell_s` before it
    commits (prevents flapping). Down-transitions use a `hysteresis_pct` margin.
  - Temp modifier: above 30 °C the bands shave up to 10% (hot crowds crush sooner).
  - **Stale feed (Hard Rule 7): `feed_state == LOST` returns `UNKNOWN` immediately** —
    no guessed density, gates hold.
  - `state` is caller-owned; the pipeline holds one `new_state()` per zone.
  - **Gotcha:** a *steep* surge can jump GREEN→RED, skipping AMBER, because AMBER
    can't dwell `dwell_s` before the smoothed value reaches the RED band. That is
    correct behaviour, but it's why the dry-run surge ramps gradually (§6).

- **`flow.py`** — `check(zone_id, in_per_min, out_per_min, density_trend, method)`
  returns the `flow_check` block. `residual` in [0,1] is the normalized disagreement
  between net gate inflow and the density trend (a conservation sanity check; large
  residual ≈ occlusion or a miscount). **`density_trend` must be in people/min** —
  `density.py` converts `trend_per_min × area_m2` before calling.

- **`playbooks.py`** — risk transition → `gate.command`. Reads `config/playbooks.yaml`.
  - `select_playbook(risk, trend, prev_risk)` → `(playbook_id, action, ttl)` honoring
    each playbook's `when` guards (`trend_per_min_gt`, `from`). Returns `(None,…)`
    when a guard blocks (e.g. AMBER without enough rising trend, or GREEN that didn't
    come down from AMBER/RED). If `playbooks.yaml` has an entry for the risk, that
    governs — the built-in `_DEFAULTS` only apply when config is silent for that risk.
  - `fire(node, pid, gate_id, reason, triggered_by)` publishes the `gate.command`
    (QoS 1, retained, MQTT-v5 TTL) with a contract-valid payload.
  - `fire_if_needed(node, zone, risk, density, trend, ttt)` is the transition tracker
    the pipeline calls every tick — it holds `_PREV_RISK` per zone (module global) and
    only fires on an actual level change. **Gotcha:** `_PREV_RISK` is process-global,
    fine for one pipeline process; reset it if you ever run two pipelines in-process.

### vision/ (cv2/onnxruntime are LAZILY imported inside functions — see §8)

- **`capture.py`** — N sources from `cameras.yaml` (file/webcam/rtsp) each with a
  watchdog thread: reconnect with exponential backoff, stale-frame detector,
  `OK/DEGRADED/LOST` states. `latest()` returns the freshest `Frame` or `None`
  (never a queued stale frame). `health()` → `FeedHealth`. `publish_health(node, feeds)`
  emits `cv/camera/{id}/health`. **The frame `reader` is injectable** (default is
  `cv2.VideoCapture`) which is how the watchdog is unit-tested headless.

- **`detect_qnn.py`** — the ONE shared session. `build_session(model_path,
  performance_mode="burst", require_npu=False)`:
  - Probes the NPU with `onnxruntime.get_ep_devices()` — **never
    `get_available_providers()`** (Hard Rule 3; the QNN EP is a plugin EP in ORT 2.x
    and won't show up there).
  - QNN attached → badge `qnn-npu-hexagon-v73`. Absent → CPU EP, badge `cpu`, LOUD log.
  - **`require_npu=True` (demo path) hard-fails** if the EP is CPU — no silent fallback
    (Hard Rule 2). `detect(session, image)` → `(boxes_xyxy, head_points_px, latency_ms)`;
    `active_backend(session)` → the honest badge.

- **`scheduler.py`** — THE headline mechanism. One shared session services all feeds
  round-robin; each round takes each feed's *newest* frame and drops it if unchanged
  (freshest-frame; stale frames dropped, never queued). Exposes per-stage counters
  (`capture/schedule/infer/decide`) and `fps_effective(camera_id)` for `mesh_bench`.
  Module `run(...)` sets a module singleton `_CURRENT` so `scheduler.fps_effective(cam)`
  works from inside `on_result`.

- **`homography.py`** — `load(camera_id)` reads the 3×3 matrix from `cameras.yaml`;
  `to_floor(H, points_px)` → Nx2 floor metres via `cv2.perspectiveTransform`.

- **`tracker.py`** — greedy nearest-centroid association → id-stable tracks with
  velocity, keeping each track's previous position for crossing detection. Counts,
  never identities (no face-rec, no re-ID). Tunables `MAX_ASSOC_DIST_M=1.5`,
  `MAX_MISSED=5`. **One TrackSet per camera** (the pipeline keeps a dict).

- **`gatelines.py`** — directed line-crossing counts. `GateLine(line, method, direction,
  window_s)` with `.block(tracks, ts)` → `{in_per_min, out_per_min, method}` over a
  rolling window. **Convention:** a crossing is `in` when the track ends on the LEFT
  of the directed line `a→b` (positive orientation), times `direction`. Calibrate the
  `gate_line`'s `a→b` point order (or pass `direction=-1`) so `in` matches the real
  entry direction.

- **`density.py`** — `publish_zone(node, zone_id, heads_m, feed_health, badges, *,
  risk_state, gate_flow, fps_effective, ts_ms, temp_c, temp_source)`. Counts heads
  inside the zone polygon (`zones.yaml`) / `area_m2`, calls `risk.update` to stamp
  `risk`/`ttt`/`trend`, builds `flow_check` from `gate_flow` (real gate line) or the
  trend (virtual line), and publishes `cv/zone/{id}/density`. **LOST feed → `risk =
  UNKNOWN`, `people_count`/`density` = null.** `gate_flow` is `(in_per_min,
  out_per_min, method)` or `None`.

- **`pipeline.py`** — the thin orchestrator (the only file with no stub ancestor;
  it's the runtime that wires everything). `run(model_path, require_npu, dry_run,
  max_iters, host)`:
  - Opens feeds (real `capture.open_all()` or scripted dry-run feeds), builds the
    shared session (or a scripted detector), and runs the scheduler.
  - `_make_on_result(...)` is the per-frame closure: homography → per-camera tracker →
    gate line → density → `fire_if_needed`. It keeps **per-camera trackers** and a
    **shared `gate_counts` keyed by `gate_id`** so a dedicated gate camera (C4, gate
    G3) feeds the zone whose gate that is (zone A). Badges are honest:
    `active_backend(session)` live, `sim-replay` in dry-run.
  - `_status_loop(...)` publishes `camera.health` every 5 s **and** publishes
    `risk = UNKNOWN` for any LOST feed — because `on_result` only runs on fresh
    frames, so without this a dead feed would go silent on the dashboard.
  - `--dry-run` scripts a zone-A surge (`_surge`/`_scatter`/`_DryFeed`/`_dry_detect`)
    that actually drives GREEN→AMBER→RED→recover and fires the playbooks, with no
    cameras and no model.

### scripts/ & bench/

- **`scripts/verify_npu.py`** — proves the QNN EP via `get_ep_devices()`, writes a
  timestamped artifact to `docs/verify_npu.out`. Exit 0 = NPU found, 2 = QNN EP but
  no NPU, 3 = `onnxruntime-qnn` absent (expected off-device).
- **`bench/detect_bench.py`** — 3 warmup + 300 frames, QNN vs CPU → `bench/out/detect.json`.
  Needs a staged model.
- **`bench/mesh_bench.py`** — 5-feed soak through the real scheduler → `bench/out/mesh.json`
  (aggregate inf/s, effective fps/feed, per-stage, thermal-decay). `--dry-run` for
  wiring (badged `sim-replay`), `--duration 600` for the real 10-min soak on the X Elite.

---

## 5. What Alpha publishes (the contract)

All via `crowdvision._lib.messages` + `mqttc.MqttNode`; validated by
`validate_envelope()`. Envelope: `{type, v, ts, src, seq, payload}`.

| Message | Topic | When | Key payload |
|---|---|---|---|
| `zone.density.update` | `cv/zone/{id}/density` | 1 Hz/zone | `people_count, area_m2, density_per_m2, trend_per_min, ttt_red_s, risk, flow_check{…}, fps_effective, model_id, inference_backend, latency_ms` |
| `camera.health` | `cv/camera/{id}/health` | ~0.2 Hz/feed | `state (OK/DEGRADED/LOST), fps_effective, drop_rate_pct, last_frame_age_ms, reconnects` |
| `gate.command` | `cv/gate/{id}/cmd` | on risk transition | `action ∈ GATE_ACTIONS, allowed, reason, playbook_id, triggered_by, ttl_s` |

**Honest badges (Hard Rule 2).** `inference_backend` reflects what ACTUALLY ran:
`qnn-npu-hexagon-v73` (real NPU) / `cpu` (honest fallback) / `sim-replay` (scripted
dry-run — no inference at all). Never derive the badge from anything except the EP
that built the session.

**Alpha does NOT publish `dispatch.order`.** `implementation.md` assigns Alpha only
gate.command + density + health. Dispatch is a PC-side decision but its ownership is
unstated — the sim `replay.py` does it as a stand-in. **Open coordination item with
Gamma** before wiring it anywhere (see §9).

---

## 6. Run & verify (all hardware-free)

Use the project venv (`python -m venv .venv; .venv/Scripts/python -m pip install -e ".[dev]"`).
`onnxruntime` is intentionally NOT installed in the venv — it's an X Elite dep (§8).

```bash
# 1. Every module self-checks itself (fast, no broker, no hardware):
python zone-brain/engine/risk.py --selftest        # GREEN->AMBER->RED->UNKNOWN + TTT + dwell
python zone-brain/engine/flow.py --selftest
python zone-brain/engine/playbooks.py --selftest   # P1/P2/P3 mapping + valid gate.command
python zone-brain/vision/homography.py --selftest
python zone-brain/vision/tracker.py --selftest
python zone-brain/vision/gatelines.py --selftest
python zone-brain/vision/detect_qnn.py --selftest  # NPU absent -> require_npu HARD-FAILS
python zone-brain/vision/density.py --selftest      # 80 pts / 20 m^2 = 4.0/m^2; LOST->UNKNOWN
python zone-brain/vision/capture.py --selftest      # OK->LOST, stale frame withheld
python zone-brain/vision/scheduler.py --selftest    # freshest-frame drop, counters

# 2. The kill-shot on the real dashboard (2 terminals):
python -m crowdvision.sim --all --no-feeds          # broker+dashboard+gate+officer+venue (NO sim feeds/decider)
#   -> open http://localhost:8000
python zone-brain/vision/pipeline.py --dry-run      # your real pipeline supplies density + engine

# 3. Gamma's regression must stay green:
pytest sim/tests                                    # 6 passed

# 4. Bench wiring (no model needed):
python zone-brain/bench/mesh_bench.py --dry-run --duration 60
```

`--no-feeds` (added to `sim/__main__.py`, a Gamma file — flagged for coordination)
is what makes the one-command integration clean: it skips the sim feeds AND the sim
decider so your pipeline isn't double-publishing density or double-firing gates.

---

## 7. On the X Elite (the remaining hardware path)

1. `zone-brain/scripts/setup.ps1` installs the pinned `onnxruntime-qnn` win-arm64 wheel.
2. `python zone-brain/scripts/download_models.py --local <staged>` stages
   `weights/vision/yolov8n_det_int8.onnx` (AGPL — **never commit weights**, `weights/`
   is gitignored).
3. `python zone-brain/scripts/verify_npu.py` → expect "NPU device found: True";
   commit the `docs/verify_npu.out` artifact.
4. Put real RTSP URLs into `config/cameras.yaml` (`c1..c4`) and calibrate each camera —
   Gamma runs `tools/calibrate.py --camera cN`, which overwrites the identity-matrix
   `homography` placeholders with the real 3×3. **Until calibrated, floor coordinates
   equal pixel coordinates**, so density/zone maths only line up once real homographies
   are in.
5. `python zone-brain/vision/pipeline.py --require-npu` — this asserts the QNN EP and
   hard-fails if it ever falls back to CPU in the demo path.
6. Benches: `detect_bench.py` (300-frame NPU-vs-CPU), `mesh_bench.py --duration 600`
   (10-min soak), `power_delta.ps1` (burst-vs-balanced battery). JSON lands in
   `bench/out/`; Gamma's `bench/embed.py` inlines it into `docs/BENCHMARKS.md`.

---

## 8. Non-obvious things that WILL bite you

- **`zone-brain/` is not a Python package.** These modules run as scripts and import
  each other as *siblings* via `sys.path` (the script's own dir is on `sys.path`, and
  `density.py` / `pipeline.py` / the benches also insert the `engine` dir). They import
  shared code from the installed `crowdvision._lib`. Do NOT try to make hyphenated dirs
  importable; follow the existing `sys.path.insert` pattern.
- **`onnxruntime` / `cv2` are lazily imported inside functions**, never at module top
  level, so the pure-Python sim never needs them and `onnxruntime` stays an X Elite dep
  (not in `pyproject`). Keep it that way.
- **All tunables live in `config/*.yaml`** (Hard Rule 5) — `zones.yaml` (bands,
  predictor, polygons, `area_m2`, `gate_id`), `cameras.yaml` (transport, url, homography,
  `c4.gate_line`+`gate_id`), `playbooks.yaml` (P1/P2/P3 `when`/`gate_action`/`ttl_s`).
  Read them with `crowdvision._lib.config`. Nothing hardcoded.
- **Dry-run "images" carry head points, not pixels.** In `--dry-run` the scripted
  detector reads the head list off `frame.image` — it is not a real ndarray. Only the
  dry path does this; real detection uses `detect_qnn.detect`.
- **Gate-line direction is a convention** — see gatelines §4. Get the `a→b` order right
  at calibration or your in/out counts invert.
- **Cross-camera gate association has a one-round lag** (C4 updates `gate_counts` after
  zone A reads it in the same round). Harmless — counts are per-minute rolling.
- **`config/cameras.yaml` c4 maps to `zone_id: G3-lane`, which is NOT a zone in
  `zones.yaml`.** That's intentional: c4 is a gate-lane sensor, not a density zone. Its
  crossings reach zone A via the shared `gate_id: G3`, not via a zone mapping.

---

## 9. Open coordination items (do not resolve unilaterally)

- **`dispatch.order` ownership** — Alpha's contract is density + health + gate.command
  only. Dispatch is PC-side but unassigned; sim `replay.py` stands in. Settle with Gamma
  before adding it to the engine.
- **`--no-feeds` flag** lives in `sim/__main__.py` (Gamma's lane). It's small and purely
  additive (opt-in; default behaviour unchanged), but tell Gamma it exists and is the
  intended Alpha-integration launcher.
- **`bench/e2e_bench.py`** (frame→gate p50/p95) is a shared Alpha/Gamma seam and is
  still a stub. The e2e semantics are Gamma's per the role split; align before G4.
- **Alpha has no home in `pytest sim/tests`** (that's Gamma's dir, pinned in
  `pyproject testpaths`). Alpha verifies via the module `--selftest` entrypoints and
  the sim integration above. Adding an Alpha `testpaths` entry means editing
  `pyproject.toml` (Gamma sign-off).

---

## 10. History — bugs fixed in the merged pipeline (so you don't reintroduce them)

The vision/engine modules were built first, then a second pass wired `pipeline.py`.
That pipeline had integration defects (it crashed on startup) which are now fixed —
listed here so nobody "restores" them:

1. Called `homography.build_H()` / `homography.px_to_floor()` — those never existed;
   the real API is `load()` / `to_floor()`.
2. Derived `inference_backend` from the feed *transport* (would badge `qnn` on a CPU
   run — a Hard-Rule-2 lie). Fixed to use `active_backend(session)` / `sim-replay`.
3. Used one shared tracker for all cameras (corrupts association + gate counts). Now
   one TrackSet per camera.
4. Dry-run put a single head at the pixel centre, which lands outside every zone
   polygon → 0 density forever, no kill-shot. Now a scripted in-polygon surge.
5. Never published `risk = UNKNOWN` for a LOST feed (on_result only runs on fresh
   frames). Now the status loop does it.
6. C4's real gate line was dead code (attached to no zone). Now wired to zone A via
   `gate_id`.
7. `mesh_bench --dry-run` badged `cpu` for synthetic runs. Now `sim-replay`.

---

*Protect the core: SENSE → PREDICT → ACT → INFORM, under two seconds, on the edge.*
*If your JSON appears on the dashboard or `pytest sim/tests` stays green, it works —
regardless of hardware.*
