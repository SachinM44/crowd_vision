"""tools/calibrate.py --camera cN [--verify] — homography + zone polygon.

OWNER: Gamma (Phase B5). Building now — don't touch.

Click 4 floor points per camera -> homography (cv2.getPerspectiveTransform) +
zone polygon -> write the profile into config/cameras.yaml. --verify overlays the
grid live. Degrades gracefully headless (no display).

    python tools/calibrate.py --camera c1
    python tools/calibrate.py --camera c4 --verify
"""
from __future__ import annotations

import argparse


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--camera", required=True, help="camera id (c1..c4)")
    ap.add_argument("--verify", action="store_true", help="overlay the grid live")
    ap.parse_args()
    raise NotImplementedError("TODO(gamma B5): 4-click homography -> config/cameras.yaml")


if __name__ == "__main__":
    raise SystemExit(main())
