# CrowdVision — Devices (labels · IPs · power-profile rationale)

> Seeded stub. **Delta owns; filled with real values at check-in Saturday.**
> Runtime IPs live in `config/devices.yaml`. Nine physical devices; **seven
> orchestrated runtime roles** across four form factors + cloud (count honestly).

## Device roster
| Device | Role | LAN IP | Notes |
|---|---|---|---|
| Surface Laptop 7 (X Elite, NPU v73) | Zone-brain: 5-feed density, risk, playbooks, broker, dashboard, dispatch | `TODO` | 2 s safety loop lives here |
| Arduino UNO Q 4 GB | Gate node (Surface USB-C powered) | `TODO` | runs no model; Gate-3 eye = C4 on PC pipeline |
| OnePlus 15 (SM8850, Hexagon v81) | Officer-1: beacon, dispatch/ack, FunctionGemma incident | `TODO` | Sat 13:30 E2B NPU probe |
| Phone-C1 | Camera node — Zone B wide (the judges, live) | `TODO` | RTSP 640×480@12 |
| Phone-C2 | Camera node — Zone C | `TODO` | live or looped file per feed-mix lock |
| Phone-C3 | Camera node — Zone D | `TODO` | hotspot backup profile pre-cloned |
| Phone-C4 | Camera node — Gate-3 lane (dedicated) | `TODO` | real line-crossing counts |
| Phone-H | Hotspot LAN + cellular uplink + Officer-2 instance | `TODO` | network infra; uplink-cut beat |
| Cloud AI 100 | Venue tier (REST) | endpoint in `.env` | never in the safety path |

## X Elite device label (for AI Hub export)
```
TODO(alpha): paste exact `qai-hub list-devices` label here on July 8.
```

## Power-profile rationale (verbatim on the numbers slide)
- Sustained real-time multi-stream video → **burst** (pins NPU clocks, kills
  frame-to-frame variance).
- Single interactive inference → **balanced**.
- Background sensing → **efficiency**.

Chosen per workload, measured (`bench/`, `power_delta.ps1`), defensible.

## Charging map (18+ h)
Surface USB-C #1 → UNO Q (permanent) · USB-C #2 → OnePlus top-ups · USB-A →
Phone-H · personal-laptop ports + wall chargers → C1–C4 continuous. Charging
audits: 17:00 / 23:00 / 02:30 / 08:30.
