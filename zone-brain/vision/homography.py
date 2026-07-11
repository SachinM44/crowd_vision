"""zone-brain/vision/homography.py — image → floor-plane coordinates.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Applies the per-camera homography (from config/cameras.yaml, authored by Gamma's
tools/calibrate.py) to map detected head points into floor-plane metres, so
density.py can compute people/m² against each zone polygon.

CONTRACT:
  load(camera_id) -> 3x3 homography matrix H   (from cameras.yaml profile)
  to_floor(H, points_px) -> points_m           (Nx2 image px -> Nx2 floor metres)
"""
from __future__ import annotations


def load(camera_id: str):
    """Load the 3x3 homography matrix for a camera profile. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): read config/cameras.yaml[camera_id].homography")


def to_floor(H, points_px):
    """Map image-pixel points to floor-plane metres via H. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): cv2.perspectiveTransform")
