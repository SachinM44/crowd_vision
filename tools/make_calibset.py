"""tools/make_calibset.py — assemble the 60-image real-crowd calibration set.

OWNER: Gamma/Alpha (Phase B5). Building now — don't touch.

Assembles representative crowd frames (never random arrays) for the YOLOv8 QNN
INT8 export calibration. Output feeds `qai_hub_models ... --calibration-data`.
"""
from __future__ import annotations


def main() -> int:
    raise NotImplementedError("TODO(gamma B5): sample 60 real crowd frames")


if __name__ == "__main__":
    raise SystemExit(main())
