"""python -m crowdvision.sim [--all|--feeds|--gate|--officer|--zones]

OWNER: Gamma. Placeholder — the real harness lands in the next commit (Phase B1:
embedded amqtt broker + 5 looping feeds + scripted kill-shot + virtual gate +
virtual officer). Until then this prints guidance instead of crashing.
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="crowdvision.sim")
    ap.add_argument("--all", action="store_true", help="full simulated mesh")
    ap.add_argument("--feeds", action="store_true", help="density + camera health only")
    ap.add_argument("--gate", action="store_true", help="virtual gate only")
    ap.add_argument("--officer", action="store_true", help="virtual officer only")
    ap.add_argument("--zones", action="store_true", help="venue-tier sim zones only")
    ap.parse_args(argv)
    print("[sim] Harness lands in Gamma commit #2 (Phase B1). "
          "Structure is in place; code to docs/MESSAGES.md meanwhile.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
