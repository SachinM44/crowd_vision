"""zone-brain/vision/homography.py — image -> floor-plane coordinates.

OWNER: Alpha. Applies the per-camera homography (from config/cameras.yaml,
authored by Gamma's tools/calibrate.py) to map detected head points into
floor-plane metres, so density.py / tracker.py / gatelines.py work in one metric
frame (the same local-CRS the dashboard and zones.yaml polygons use).

cv2 is lazily imported (Hard Rule 8 — keep module import pure).

CONTRACT:
  load(camera_id) -> 3x3 homography matrix H   (from cameras.yaml profile)
  to_floor(H, points_px) -> points_m           (Nx2 image px -> Nx2 floor metres)
"""
from __future__ import annotations

import numpy as np

from crowdvision._lib import config as C


def load(camera_id: str) -> np.ndarray:
    """Load the 3x3 homography matrix for a camera profile."""
    cam = C.cameras().get("cameras", {}).get(camera_id)
    if cam is None:
        raise KeyError(f"camera '{camera_id}' not in config/cameras.yaml")
    H = np.asarray(cam.get("homography", np.eye(3).tolist()), dtype=np.float64)
    if H.shape != (3, 3):
        raise ValueError(f"camera '{camera_id}' homography must be 3x3, got {H.shape}")
    return H


def to_floor(H, points_px) -> np.ndarray:
    """Map image-pixel points (Nx2) to floor-plane metres (Nx2) via H."""
    pts = np.asarray(points_px, dtype=np.float64).reshape(-1, 1, 2)
    if pts.size == 0:
        return np.empty((0, 2), dtype=np.float64)
    import cv2  # lazy
    out = cv2.perspectiveTransform(pts, np.asarray(H, dtype=np.float64))
    return out.reshape(-1, 2)


def _selftest() -> int:
    import cv2
    # Identity: pixels pass through as metres.
    ident = np.eye(3)
    pts = [[10, 20], [0, 0], [4.5, 5.5]]
    got = to_floor(ident, pts)
    assert np.allclose(got, pts), got
    # A known perspective: image corners must land exactly on an 8x5 floor rect.
    src = np.float32([[0, 0], [640, 0], [640, 480], [0, 480]])
    dst = np.float32([[0, 0], [8, 0], [8, 5], [0, 5]])
    H = cv2.getPerspectiveTransform(src, dst)
    mapped = to_floor(H, src)
    assert np.allclose(mapped, dst, atol=1e-6), mapped
    # Empty input is safe.
    assert to_floor(H, []).shape == (0, 2)
    print("homography.py selftest OK: identity + 640x480 -> 8x5 floor rect exact")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
