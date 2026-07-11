"""tools/calibrate.py — per-camera homography + zone polygon into cameras.yaml.

OWNER: Gamma. Click 4 known floor points in the camera image; the tool computes
the image->floor homography (cv2.getPerspectiveTransform) and writes it into
config/cameras.yaml under that camera. Alpha's vision/homography.py reads it back
to turn head pixels into people/m^2.

    # interactive (venue): click 4 floor corners of a known rectangle
    python tools/calibrate.py --camera c1
    python tools/calibrate.py --camera c1 --verify           # overlay the grid

    # non-interactive (scriptable / headless), e.g. from a still image:
    python tools/calibrate.py --camera c1 --image frame.png \
        --image-points "100,400;540,400;520,150;120,150" --floor-size 8x5

Floor points default to a rectangle [0,0],[W,0],[W,H],[0,H] metres from
--floor-size WxH, in clockwise order matching your 4 clicks.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crowdvision._lib import config as cvconfig  # noqa: E402

CAMERAS_YAML = cvconfig.config_dir() / "cameras.yaml"


def _parse_points(s: str) -> list[list[float]]:
    return [[float(v) for v in pair.split(",")] for pair in s.strip().split(";")]


def floor_rect(w: float, h: float) -> list[list[float]]:
    """Clockwise floor rectangle in metres, matching a clockwise click order."""
    return [[0, 0], [w, 0], [w, h], [0, h]]


def compute_homography(image_pts, floor_pts) -> np.ndarray:
    import cv2
    src = np.array(image_pts, dtype=np.float32)
    dst = np.array(floor_pts, dtype=np.float32)
    if len(src) == 4:
        return cv2.getPerspectiveTransform(src, dst)
    H, _ = cv2.findHomography(src, dst)
    return H


def grab_frame(camera_id: str, image: str | None):
    import cv2
    if image:
        frame = cv2.imread(image)
        if frame is None:
            raise SystemExit(f"could not read image: {image}")
        return frame
    cams = cvconfig.cameras().get("cameras", {})
    prof = cams.get(camera_id) or {}
    url = prof.get("url")
    if not url:
        raise SystemExit(f"no url for camera {camera_id} in cameras.yaml")
    cap = cv2.VideoCapture(url)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"could not open source for {camera_id}: {url}")
    return frame


def click_points(frame) -> list[list[float]]:
    import cv2
    pts: list[list[float]] = []

    def on_mouse(event, x, y, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append([x, y])

    win = "calibrate: click 4 floor corners (clockwise), then any key"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)
    while True:
        disp = frame.copy()
        for i, (x, y) in enumerate(pts):
            cv2.circle(disp, (int(x), int(y)), 5, (0, 255, 0), -1)
            cv2.putText(disp, str(i + 1), (int(x) + 6, int(y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow(win, disp)
        if cv2.waitKey(20) != -1 and len(pts) == 4:
            break
    cv2.destroyAllWindows()
    return pts


def write_homography(camera_id: str, H, out_path: Path) -> None:
    data = yaml.safe_load(out_path.read_text(encoding="utf-8")) or {}
    cams = data.setdefault("cameras", {})
    prof = cams.setdefault(camera_id, {})
    prof["homography"] = [[round(float(v), 6) for v in row] for row in H]
    banner = ("# config/cameras.yaml — camera mesh sources + homography profiles.\n"
              "# OWNER: Gamma. Homography rows written by tools/calibrate.py.\n")
    out_path.write_text(banner + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"[calibrate] wrote homography for {camera_id} -> {out_path}")


def verify(camera_id: str, image: str | None) -> None:
    import cv2
    prof = cvconfig.cameras().get("cameras", {}).get(camera_id, {})
    H = np.array(prof.get("homography"), dtype=np.float32)
    if H is None or H.shape != (3, 3):
        raise SystemExit(f"no homography for {camera_id} — run calibrate first")
    Hinv = np.linalg.inv(H)
    frame = grab_frame(camera_id, image)
    # Project a 1 m floor grid back into the image.
    for gx in range(0, 17):
        for gy in range(0, 11):
            p = Hinv @ np.array([gx, gy, 1.0])
            x, y = p[0] / p[2], p[1] / p[2]
            if 0 <= x < frame.shape[1] and 0 <= y < frame.shape[0]:
                cv2.circle(frame, (int(x), int(y)), 2, (0, 200, 255), -1)
    cv2.imshow(f"verify {camera_id} (any key to close)", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True, help="camera id (c1..c4)")
    ap.add_argument("--verify", action="store_true", help="overlay the floor grid")
    ap.add_argument("--image", help="use a still image instead of the live source")
    ap.add_argument("--image-points", help='4 image points "x,y;x,y;x,y;x,y" (non-interactive)')
    ap.add_argument("--floor-points", help='4 floor points in metres "X,Y;..." (optional)')
    ap.add_argument("--floor-size", default="8x5", help="floor rectangle WxH metres (default 8x5)")
    ap.add_argument("--out", default=str(CAMERAS_YAML), help="cameras.yaml path to update")
    args = ap.parse_args()

    if args.verify:
        verify(args.camera, args.image)
        return 0

    if args.image_points:
        img_pts = _parse_points(args.image_points)
    else:
        try:
            frame = grab_frame(args.camera, args.image)
        except SystemExit as e:
            print(e)
            return 2
        img_pts = click_points(frame)

    if args.floor_points:
        floor_pts = _parse_points(args.floor_points)
    else:
        w, h = (float(v) for v in args.floor_size.lower().split("x"))
        floor_pts = floor_rect(w, h)

    H = compute_homography(img_pts, floor_pts)
    write_homography(args.camera, H, Path(args.out))
    print(f"[calibrate] image_pts={img_pts} -> floor_pts={floor_pts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
