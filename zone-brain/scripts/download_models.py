#!/usr/bin/env python
"""download_models.py — the first of the judges' 3 commands.

Two jobs:
  1. Make `crowdvision` importable so `python -m crowdvision.sim --all` resolves:
     runs `pip install -e .` (idempotent) unless already installed.
  2. Fetch model weights into weights/ (gitignored) with license notices printed.
     Supports `--local <path>` to copy from a staged folder (venue has no Wi-Fi
     for large downloads). Weights are NEVER committed (Hard Rule 4).

The SIM path needs NO weights — so if fetching fails or URLs are unset, this
still exits 0 after the editable install, and `sim --all` works. Real weights
(YOLOv8 QNN, FunctionGemma) are only needed for the on-hardware pipeline.

    python zone-brain/scripts/download_models.py            # install + best-effort fetch
    python zone-brain/scripts/download_models.py --local D:/cv-models
    python zone-brain/scripts/download_models.py --no-install   # skip pip step

License notices (Rules §8.c/§8.d): Ultralytics YOLOv8/YOLO11 = AGPL-3.0 (weights
kept out of the MIT repo); Gemma/FunctionGemma = Gemma Terms of Use. See
THIRD_PARTY_LICENSES.md.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEIGHTS = REPO / "weights"

# name -> (relative dest, license line). URLs are staged/fetched per-model; kept
# out of the repo. Populated by Alpha as exports land (AI Hub, HuggingFace).
MODELS = {
    "yolov8n-det-int8-qnn": ("vision/yolov8n_det_int8.onnx",
                             "Ultralytics AGPL-3.0 -- weights excluded from the MIT repo"),
    "functiongemma-270m":   ("phone/Mobile_actions_q8_ekv1024.litertlm",
                             "Gemma Terms of Use -- not MIT-relicensable"),
}


def ensure_installed() -> None:
    try:
        import crowdvision  # noqa: F401
        print("crowdvision already importable -- skipping editable install.")
        return
    except ImportError:
        print("Installing crowdvision (editable) + approved dependencies ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", str(REPO)])


def fetch(local: str | None) -> None:
    WEIGHTS.mkdir(exist_ok=True)
    print("\nModel licenses (fetched artifacts, NOT committed):")
    for name, (dest, lic) in MODELS.items():
        print(f"  - {name}: {lic}")
    for name, (dest, _lic) in MODELS.items():
        target = WEIGHTS / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            print(f"  ok   {name} present")
            continue
        if local:
            src = Path(local) / dest
            if src.exists():
                shutil.copy2(src, target)
                print(f"  copy {name} <- {src}")
                continue
        print(f"  skip {name} (stage it under --local or via Alpha's export; "
              f"sim needs no weights)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--local", help="copy weights from this staged folder")
    ap.add_argument("--no-install", action="store_true", help="skip pip install -e .")
    args = ap.parse_args()
    if not args.no_install:
        ensure_installed()
    fetch(args.local)
    print("\nDone. Next:  python -m crowdvision.sim --all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
