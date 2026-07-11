# CrowdVision — Benchmarks

**All numbers captured on the actual demo hardware by `bench/` scripts emitting
JSON.** The tables below are **auto-embedded** between the `BENCH:*` markers — no
hand-typed numbers, no cloud compile-time estimates. Regenerate with
`python bench/embed.py` (fills every marker from `bench/out/*.json`).

Power-profile rationale: sustained multi-stream → **burst**; single interactive
inference → **balanced**; background sensing → **efficiency**. Measured, defensible.

---

## 1. Detection latency — NPU vs CPU (X Elite, 300 timed frames @640² INT8)
<!-- BENCH:detect START -->
_pending — run `zone-brain/bench/detect_bench.py` (Alpha)._
<!-- BENCH:detect END -->

## 2. 5-feed sustained mesh — aggregate inferences/s + effective fps/feed (10-min soak)
<!-- BENCH:mesh START -->
_pending — run `zone-brain/bench/mesh_bench.py` (Alpha)._
<!-- BENCH:mesh END -->

## 3. Network — hotspot throughput + per-stream RTSP drop rate + reconnects
<!-- BENCH:net START -->
_pending — run `bench/net_bench.py` (Gamma)._
<!-- BENCH:net END -->

## 4. End-to-end frame → gate-actuated (p50/p95, 50 playbook fires)
<!-- BENCH:e2e START -->
_pending — run `bench/e2e_bench.py` / `zone-brain/bench/e2e_bench.py`._
<!-- BENCH:e2e END -->

## 5. Gate actuation internals (bridge_rpc_ms ×100 + actuated_ms/command)
<!-- BENCH:gate START -->
_pending — Beta (device benches)._
<!-- BENCH:gate END -->

## 6. FunctionGemma — TTFT + tok/s + e2e parse + schema-valid rate (20+5)
<!-- BENCH:functiongemma START -->
_pending — Beta, badged `litert-gpu`._
<!-- BENCH:functiongemma END -->

## 7. Gemma-4-E2B NPU probe (Hexagon v81) — loads? TTFT + tok/s
<!-- BENCH:e2b_probe START -->
_pending — Sat 13:30 timeboxed probe; success → `litert-npu`, failure → exact error._
<!-- BENCH:e2b_probe END -->

## 8. Energy — battery-delta per power profile (burst vs balanced, mesh running)
<!-- BENCH:power START -->
_pending — `zone-brain/bench/power_delta.ps1` (Alpha)._
<!-- BENCH:power END -->

## 9. NPU proof artifact — `verify_npu.py` (`get_ep_devices()`), raw output
<!-- BENCH:verify_npu START -->
_pending — commit raw, timestamped output of `zone-brain/scripts/verify_npu.py`._
<!-- BENCH:verify_npu END -->

## 10. Venue-tier RTT distribution (Cloud AI 100, 30 advisory calls)
<!-- BENCH:cloud_rtt START -->
_pending — run `bench/cloud_rtt_bench.py` (Gamma)._
<!-- BENCH:cloud_rtt END -->
