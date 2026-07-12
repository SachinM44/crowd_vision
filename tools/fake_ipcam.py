#!/usr/bin/env python
"""tools/fake_ipcam.py — a phone-free IP Webcam stand-in (stdlib only).

Serves a folder of JPEGs exactly like the Android "IP Webcam" app serves a
phone camera, so the ENTIRE live-camera path (tools/live_capture.py -> YOLO ->
density -> dashboard) can be exercised with zero phones — e.g. with the real
CrowdHuman calibration images from github.com/Santhosh121805/crwoddata.

  GET /shot.jpg   -> current frame (rotates through the folder; what the
                     'ipwebcam' transport in config/cameras.yaml polls)
  GET /video      -> MJPEG stream (multipart/x-mixed-replace)
  GET /           -> tiny index

Point a camera at it in config/cameras.yaml:
    c1:
      transport: ipwebcam
      url: "http://127.0.0.1:8090"
      zone_id: B

    python tools/fake_ipcam.py --dir <folder-of-jpgs> [--port 8090] [--period 3]
"""
from __future__ import annotations

import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FRAMES: list[bytes] = []
PERIOD_S = 3.0
T0 = time.monotonic()


def current_frame() -> bytes:
    idx = int((time.monotonic() - T0) / PERIOD_S) % len(FRAMES)
    return FRAMES[idx]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        if self.path.startswith("/shot.jpg"):
            data = current_frame()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/video"):
            self.send_response(200)
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    data = current_frame()
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                     + f"Content-Length: {len(data)}\r\n\r\n".encode())
                    self.wfile.write(data + b"\r\n")
                    time.sleep(1.0 / 12)          # the mesh's 12 fps budget
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            body = (b"<html><body><h3>fake_ipcam</h3>"
                    b"<p><a href='/shot.jpg'>/shot.jpg</a> | "
                    b"<a href='/video'>/video</a></p></body></html>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main() -> int:
    global PERIOD_S
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True, help="folder of .jpg frames to serve")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--period", type=float, default=3.0,
                    help="seconds per frame before rotating to the next")
    args = ap.parse_args()
    PERIOD_S = args.period

    for p in sorted(Path(args.dir).glob("*.jpg")):
        FRAMES.append(p.read_bytes())
    if not FRAMES:
        print(f"no .jpg files in {args.dir}")
        return 1
    print(f"[fake_ipcam] {len(FRAMES)} frames from {args.dir} "
          f"on http://0.0.0.0:{args.port}  (/shot.jpg, /video)")
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
