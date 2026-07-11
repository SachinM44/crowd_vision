"""crowdvision._lib.framebus — in-process latest-annotated-frame buffer.

The live-capture bridge (tools/live_capture.py) and the dashboard server run in
the SAME process under `sim --live`, so they share this module. Capture writes
the latest annotated JPEG per camera; the dashboard serves it at /api/cam/{id}.jpg.
Local only — frames never leave the machine.
"""
from __future__ import annotations

import threading

_frames: dict[str, bytes] = {}
_lock = threading.Lock()


def put(camera_id: str, jpeg: bytes) -> None:
    with _lock:
        _frames[camera_id] = jpeg


def get(camera_id: str) -> bytes | None:
    with _lock:
        return _frames.get(camera_id)


def ids() -> list[str]:
    with _lock:
        return list(_frames)
