#!/usr/bin/env python
"""tools/check_field_contract.py — validate the OFFICER APP's real messages.

The Android app cannot `import crowdvision`, so it hand-builds the docs/MESSAGES.md
envelope. That is exactly the kind of seam that rots silently. This closes it:

  1. `gradle :app:test` runs field-app's ContractTest, which dumps one of every
     message FieldService publishes (built by the SHIPPED Envelope code) to
     field-app/app/build/contract-out/officer_messages.json
  2. this script feeds those bytes to the authoritative validator,
     crowdvision._lib.messages.validate_envelope()

A green Kotlin test that emits a payload the broker would reject is worthless —
Python is the gate.

    cd field-app && gradle :app:test        # produces the dump
    python tools/check_field_contract.py    # validates it
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from crowdvision._lib import messages as M

DUMP = (Path(__file__).resolve().parents[1]
        / "field-app" / "app" / "build" / "contract-out" / "officer_messages.json")

# What the officer app is allowed to say, and the badges each path may claim.
EXPECTED_TYPES = {M.T_OFFICER_BEACON, M.T_INCIDENT_REPORT, M.T_HEARTBEAT}
HONEST_BACKENDS = {M.BACKEND_LITERT_GPU, M.BACKEND_LITERT_NPU, M.BACKEND_CPU}


def main() -> int:
    if not DUMP.exists():
        print(f"no dump at {DUMP}\nrun:  cd field-app && gradle :app:test")
        return 1

    msgs = json.loads(DUMP.read_text(encoding="utf-8"))
    failures: list[str] = []

    for i, msg in enumerate(msgs):
        errs = M.validate_envelope(msg)
        if errs:
            failures.append(f"[{i}] {msg.get('type')}: {errs}")
            continue

        t, p = msg["type"], msg["payload"]
        if t not in EXPECTED_TYPES:
            failures.append(f"[{i}] unexpected type for an officer: {t}")

        if t == M.T_INCIDENT_REPORT:
            backend = p.get("inference_backend")
            if backend not in HONEST_BACKENDS:
                failures.append(f"[{i}] dishonest/unknown badge: {backend}")
            # The form path must never masquerade as the model path.
            if p.get("model_id") == "dropdown-form" and backend != M.BACKEND_CPU:
                failures.append(f"[{i}] dropdown-form claims backend {backend}")
            if p.get("model_id") == "functiongemma-270m" and backend == M.BACKEND_LITERT_NPU:
                failures.append(
                    f"[{i}] FunctionGemma claims litert-npu — the provided artifact "
                    "is a CPU/GPU build (Hard Rule 2)")
            s = p.get("structured") or {}
            if s.get("type") not in ("medical", "crush-risk", "fire", "security",
                                     "lost-person", "other"):
                failures.append(f"[{i}] structured.type out of enum: {s.get('type')}")

        if t == M.T_OFFICER_BEACON:
            for k in ("officer_id", "lat", "lon", "status"):
                if k not in p:
                    failures.append(f"[{i}] beacon missing {k}")
            if p.get("status") == "enroute" and not p.get("ack_dispatch_id"):
                failures.append(f"[{i}] enroute beacon carries no ack_dispatch_id "
                                "(the beacon IS the ack)")

    print(f"checked {len(msgs)} officer messages from {DUMP.name}")
    for m in msgs:
        extra = ""
        if m["type"] == M.T_INCIDENT_REPORT:
            extra = (f"  model={m['payload'].get('model_id')} "
                     f"backend={m['payload'].get('inference_backend')}")
        elif m["type"] == M.T_OFFICER_BEACON:
            extra = (f"  status={m['payload'].get('status')} "
                     f"ack={m['payload'].get('ack_dispatch_id')}")
        elif m["type"] == M.T_HEARTBEAT:
            extra = f"  state={m['payload'].get('state')}"
        print(f"  ok  {m['type']:18s}{extra}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nPASS: every officer message conforms to docs/MESSAGES.md; badges honest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
