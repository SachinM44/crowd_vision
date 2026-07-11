"""venue-tier/sim_zones.py — publish 2 SIM-labeled zones for the venue view.

OWNER: Gamma (Phase B4). Building now — don't touch.

Publishes venue.state with 1 real cluster + 2 simulated zones (SIM-1, SIM-2,
`simulated:true`) so the venue tier shows N-zone fusion honestly. Uplink-cut
handling: cloud dead => zones unaffected.
"""
from __future__ import annotations


def run(node) -> None:
    raise NotImplementedError("TODO(gamma B4): publish venue.state w/ 2 SIM zones")
