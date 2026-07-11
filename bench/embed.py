"""bench/embed.py — embed bench/out/*.json into docs/BENCHMARKS.md markers.

OWNER: Gamma (Phase B6). Building now — don't touch.

Reads bench/out/<name>.json, renders a markdown table, and replaces the content
between <!-- BENCH:<name> START --> and <!-- BENCH:<name> END --> in
docs/BENCHMARKS.md. No hand-typed numbers (Rules §7.c.v; Presentation-15).
"""
from __future__ import annotations


def main() -> int:
    raise NotImplementedError("TODO(gamma B6): fill BENCH:* markers from bench/out/*.json")


if __name__ == "__main__":
    raise SystemExit(main())
