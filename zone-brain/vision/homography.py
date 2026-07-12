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
    """Map image-pixel points (Nx2) to floor-plane metres (Nx2) via H.

    numpy only. This used to call cv2.perspectiveTransform, but opencv-python has
    no win-arm64 wheel and the X Elite (the NPU host) is win-arm64 — a projective
    transform of a few points does not justify making the safety path depend on a
    library that cannot be installed on the target device.
    """
    pts = np.asarray(points_px, dtype=np.float64).reshape(-1, 2)
    if pts.size == 0:
        return np.empty((0, 2), dtype=np.float64)
    H = np.asarray(H, dtype=np.float64)
    homo = np.hstack([pts, np.ones((len(pts), 1))])          # (N,3)
    out = homo @ H.T                                          # (N,3)
    w = out[:, 2:3]
    # Points on the horizon (w == 0) have no finite floor position; NaN says so
    # rather than inventing a coordinate.
    with np.errstate(divide="ignore", invalid="ignore"):
        xy = np.where(np.abs(w) > 1e-12, out[:, :2] / w, np.nan)
    return xy


def perspective_from_points(src, dst) -> np.ndarray:
    """3x3 homography mapping 4 src points -> 4 dst points (cv2.getPerspectiveTransform).

    Solves the standard 8x8 DLT system with numpy so calibration works headless
    and on win-arm64.
    """
    src = np.asarray(src, dtype=np.float64).reshape(4, 2)
    dst = np.asarray(dst, dtype=np.float64).reshape(4, 2)
    A = np.zeros((8, 8), dtype=np.float64)
    b = np.zeros(8, dtype=np.float64)
    for i in range(4):
        x, y = src[i]
        u, v = dst[i]
        A[i * 2] = [x, y, 1, 0, 0, 0, -u * x, -u * y]
        A[i * 2 + 1] = [0, 0, 0, x, y, 1, -v * x, -v * y]
        b[i * 2], b[i * 2 + 1] = u, v
    h = np.linalg.solve(A, b)
    return np.append(h, 1.0).reshape(3, 3)


def _selftest() -> int:
    # Identity: pixels pass through as metres.
    ident = np.eye(3)
    pts = [[10, 20], [0, 0], [4.5, 5.5]]
    got = to_floor(ident, pts)
    assert np.allclose(got, pts), got
    # A known perspective: image corners must land exactly on an 8x5 floor rect.
    src = [[0, 0], [640, 0], [640, 480], [0, 480]]
    dst = [[0, 0], [8, 0], [8, 5], [0, 5]]
    H = perspective_from_points(src, dst)
    mapped = to_floor(H, src)
    assert np.allclose(mapped, dst, atol=1e-6), mapped
    # Empty input is safe.
    assert to_floor(H, []).shape == (0, 2)
    # Cross-check against cv2 when it is available (x64 dev boxes).
    try:
        import cv2
        H_cv = cv2.getPerspectiveTransform(np.float32(src), np.float32(dst))
        assert np.allclose(H, H_cv, atol=1e-6), (H, H_cv)
        print("homography.py selftest OK: matches cv2.getPerspectiveTransform exactly")
    except ImportError:
        print("homography.py selftest OK: identity + 640x480 -> 8x5 floor rect exact "
              "(numpy path; cv2 absent, as on win-arm64)")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
