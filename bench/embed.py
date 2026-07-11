"""bench/embed.py — embed bench/out/*.json into docs/BENCHMARKS.md markers.

OWNER: Gamma. Each bench writes bench/out/<stem>.json with a rendered "markdown"
field; this injects it between <!-- BENCH:<stem> START --> and <!-- END -->. No
hand-typed numbers (Rules §7.c.v; Presentation-15). Idempotent.

    python bench/embed.py            # embed everything in bench/out/
    python bench/net_bench.py && python bench/embed.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bench" / "out"
DOC = ROOT / "docs" / "BENCHMARKS.md"


def embed_one(text: str, stem: str, markdown: str, captured_at: str) -> tuple[str, bool]:
    pat = re.compile(
        rf"(<!-- BENCH:{re.escape(stem)} START -->)(.*?)(<!-- BENCH:{re.escape(stem)} END -->)",
        re.DOTALL)
    if not pat.search(text):
        return text, False
    body = f"\n{markdown}\n\n_captured: {captured_at}_\n"
    return pat.sub(lambda m: m.group(1) + body + m.group(3), text), True


def main() -> int:
    if not DOC.exists():
        print(f"missing {DOC}")
        return 1
    if not OUT.exists() or not any(OUT.glob("*.json")):
        print("no bench/out/*.json yet — run the bench scripts first")
        return 0
    text = DOC.read_text(encoding="utf-8")
    embedded = []
    for jf in sorted(OUT.glob("*.json")):
        data = json.loads(jf.read_text(encoding="utf-8"))
        md = data.get("markdown")
        if not md:
            continue
        text, ok = embed_one(text, jf.stem, md, data.get("captured_at", "?"))
        if ok:
            embedded.append(jf.stem)
        else:
            print(f"  (no BENCH:{jf.stem} marker in BENCHMARKS.md — skipped)")
    DOC.write_text(text, encoding="utf-8")
    print(f"[embed] updated markers: {embedded or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
