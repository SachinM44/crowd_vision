#!/usr/bin/env python
"""tools/webcam_ipcam.py — expose the LAPTOP webcam as an IP-Webcam-style feed.

Why this exists: on win-arm64 there is no cv2 wheel, and the frame decoder
(tools/live_capture.py) runs in WSL, which cannot see the laptop's webcam. So
this bridges the gap with zero non-approved Python deps: ffmpeg (dshow) grabs
the webcam, this stdlib server re-serves the latest frame at /shot.jpg — the
exact protocol the 'ipwebcam' transport in config/cameras.yaml polls.

    python tools/webcam_ipcam.py [--port 8091] [--device auto] [--ffmpeg <path>]

Then in config/cameras.yaml:
    c3:
      transport: ipwebcam
      url: "http://<laptop-ip>:8091"   # from WSL: the Windows host/gateway IP
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LATEST = {"jpg": b""}
SOI, EOI = b"\xff\xd8", b"\xff\xd9"


def find_ffmpeg(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    p = shutil.which("ffmpeg")
    if p:
        return p
    root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    for c in root.rglob("ffmpeg.exe"):
        return str(c)
    return None


def pick_device(ffmpeg: str) -> str | None:
    out = subprocess.run([ffmpeg, "-hide_banner", "-list_devices", "true",
                          "-f", "dshow", "-i", "dummy"],
                         capture_output=True, text=True, timeout=20).stderr
    names = re.findall(r'"([^"]+)"\s*\(video\)', out)
    return names[0] if names else None


def reader(proc):
    buf = b""
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        buf += chunk
        while True:
            s = buf.find(SOI)
            e = buf.find(EOI, s + 2)
            if s < 0 or e < 0:
                if s > 0:
                    buf = buf[s:]
                break
            LATEST["jpg"] = buf[s:e + 2]
            buf = buf[e + 2:]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/shot.jpg") and LATEST["jpg"]:
            d = LATEST["jpg"]
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(d)))
            self.end_headers()
            self.wfile.write(d)
        else:
            self.send_response(503 if not LATEST["jpg"] else 404)
            self.end_headers()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--ffmpeg", default=None)
    a = ap.parse_args()

    ff = find_ffmpeg(a.ffmpeg)
    if not ff:
        print("ffmpeg not found — winget install Gyan.FFmpeg")
        return 1
    dev = a.device if a.device != "auto" else pick_device(ff)
    if not dev:
        print("no dshow video device found")
        return 1
    print(f"[webcam_ipcam] ffmpeg={ff}")
    print(f"[webcam_ipcam] device={dev!r} -> http://0.0.0.0:{a.port}/shot.jpg")

    proc = subprocess.Popen(
        [ff, "-hide_banner", "-loglevel", "error",
         "-f", "dshow", "-i", f"video={dev}",
         "-vf", "fps=6,scale=640:-2",
         # webcams emit limited-range YUV; ffmpeg 8's mjpeg encoder refuses it
         # without this (its own error message suggests exactly this flag)
         "-strict", "unofficial",
         "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "6", "-"],
        stdout=subprocess.PIPE)
    threading.Thread(target=reader, args=(proc,), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
