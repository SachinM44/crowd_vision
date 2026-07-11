#!/usr/bin/env python
"""verify_npu.py — prove the QNN Execution Provider is attached on the X Elite.

OWNER: Alpha (runs it first thing Saturday; owns the proof artifact).

Hard Rule 3: uses onnxruntime.get_ep_devices(), NEVER get_available_providers()
(the ORT 2.x QNN EP is a plugin EP and will NOT appear in get_available_providers()).

This is the exact pattern from the Qualcomm Developer Guide. Its raw, timestamped
output is committed into docs/BENCHMARKS.md (section 9). Run on the Surface X Elite
after setup.ps1 installs the onnxruntime-qnn wheel.

    python zone-brain/scripts/verify_npu.py

Exit 0 = NPU device found. Exit 2 = QNN EP present but no NPU device. Exit 3 =
onnxruntime-qnn not installed (expected on non-X-Elite dev machines).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def main() -> int:
    stamp = datetime.now(IST).isoformat(timespec="seconds")
    print(f"# verify_npu.py  @ {stamp}")
    try:
        import onnxruntime as o
        import onnxruntime_qnn as q
    except ImportError as exc:  # not the X Elite / wheel not installed
        print(f"onnxruntime-qnn not available: {exc}")
        print("Install the pinned win-arm64 wheelhouse via setup.ps1 on the X Elite.")
        return 3

    # Register the QNN plugin EP (guide's snippet).
    os.add_dll_directory(os.path.dirname(q.__file__))
    o.register_execution_provider_library("QNNExecutionProvider", q.get_library_path())

    ep_devices = o.get_ep_devices()
    print(f"onnxruntime {o.__version__}; {len(ep_devices)} EP device(s):")
    for d in ep_devices:
        print(f"  - ep={d.ep_name}  type={d.device.type}")

    npu_devices = [
        d for d in ep_devices
        if d.ep_name == "QNNExecutionProvider" and str(d.device.type).endswith("NPU")
    ]
    print("NPU device found:", bool(npu_devices))
    return 0 if npu_devices else 2


if __name__ == "__main__":
    sys.exit(main())
