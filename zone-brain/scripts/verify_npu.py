#!/usr/bin/env python
"""verify_npu.py — prove the QNN Execution Provider is attached on the X Elite.

OWNER: Alpha (runs it first thing Saturday; owns the proof artifact).

Hard Rule 3: uses onnxruntime.get_ep_devices(), NEVER get_available_providers()
(the ORT 2.x QNN EP is a plugin EP and will NOT appear in get_available_providers()).

This is the exact pattern from the Qualcomm Developer Guide. Its raw, timestamped
output is written to docs/verify_npu.out (Saturday proof artifact) and printed
to stdout. Run on the Surface X Elite after setup.ps1 installs the onnxruntime-qnn
wheel.

    python zone-brain/scripts/verify_npu.py

Exit 0 = NPU device found. Exit 2 = QNN EP present but no NPU device. Exit 3 =
onnxruntime-qnn not installed (expected on non-X-Elite dev machines).

The startup assertion (for the demo path in detect_qnn.py) is proven by the
detect_qnn.build_session(require_npu=True) path — it hard-fails if get_ep_devices()
returns no QNN NPU device, refusing any silent CPU fallback (Hard Rule 2).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
_OUT_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "verify_npu.out"


def _write_artifact(lines: list[str]) -> None:
    """Append timestamped run output to docs/verify_npu.out (Saturday proof artifact)."""
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _OUT_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    stamp = datetime.now(IST).isoformat(timespec="seconds")
    lines: list[str] = [f"# verify_npu.py  @ {stamp}"]
    print(lines[-1])

    try:
        import onnxruntime as o
        import onnxruntime_qnn as q
    except ImportError as exc:
        msg = f"onnxruntime-qnn not available: {exc}"
        note = "Install the pinned win-arm64 wheelhouse via setup.ps1 on the X Elite."
        print(msg)
        print(note)
        lines += [msg, note, "RESULT: QNN EP absent (expected on dev machine; exit 3)"]
        _write_artifact(lines)
        return 3

    # Register the QNN plugin EP (guide's snippet).
    os.add_dll_directory(os.path.dirname(q.__file__))
    try:
        o.register_execution_provider_library("QNNExecutionProvider", q.get_library_path())
    except Exception:  # noqa: BLE001 — already registered is fine
        pass

    ep_devices = o.get_ep_devices()
    header = f"onnxruntime {o.__version__}; {len(ep_devices)} EP device(s):"
    print(header)
    lines.append(header)

    for d in ep_devices:
        row = f"  - ep={d.ep_name}  type={d.device.type}"
        print(row)
        lines.append(row)

    npu_devices = [
        d for d in ep_devices
        if d.ep_name == "QNNExecutionProvider" and str(d.device.type).endswith("NPU")
    ]
    found = bool(npu_devices)
    result_line = f"NPU device found: {found}"
    print(result_line)
    lines.append(result_line)

    if found:
        lines.append("RESULT: PASS — QNN NPU EP confirmed; demo path safe to use require_npu=True")
    else:
        lines.append("RESULT: QNN EP present but no NPU device found; demo path will hard-fail")

    _write_artifact(lines)
    print(f"[verify_npu] proof artifact written -> {_OUT_PATH}")
    return 0 if found else 2


if __name__ == "__main__":
    sys.exit(main())
