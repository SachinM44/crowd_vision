"""zone-brain/vision/capture.py — multi-source capture + per-feed watchdog.

OWNER: Alpha (TODO(alpha)). This is a STUB — contract only, no implementation.

Reads N sources (file / webcam / RTSP) from config/cameras.yaml and provides the
freshest frame per feed to scheduler.py. Owns the per-feed watchdog: reconnect
with exponential backoff, stale-frame detector, and honest health states.

PUBLISHES (per docs/MESSAGES.md #2):
  topic  cv/camera/{camera_id}/health   (~0.2 Hz/feed)
  payload {camera_id, transport, resolution, fps_effective, drop_rate_pct,
           last_frame_age_ms, state:"OK"|"DEGRADED"|"LOST", reconnects, note}

STALE-FEED POLICY (Hard Rule 7): frame age > 10 s ⇒ state LOST ⇒ density.py must
emit that zone as UNKNOWN, gates hold, operator alerted. Never silently guess.

CONSUMES: config.cameras() — each camera profile: {transport, url, resolution,
fps_cap, homography, zone_id}.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np  # noqa: F401  (contract type)


@dataclass
class Frame:
    camera_id: str
    ts_ms: float
    image: "np.ndarray"
    transport: str


@dataclass
class FeedHealth:
    camera_id: str
    transport: str
    resolution: str
    fps_effective: float
    drop_rate_pct: float
    last_frame_age_ms: float
    state: str  # OK | DEGRADED | LOST
    reconnects: int


class CaptureFeed:
    """One camera source with a watchdog. TODO(alpha)."""

    def __init__(self, camera_id: str, profile: dict):
        raise NotImplementedError("TODO(alpha): open source + start watchdog")

    def latest(self) -> Optional[Frame]:
        """Freshest frame or None if stale/LOST (never a queued stale frame)."""
        raise NotImplementedError("TODO(alpha)")

    def health(self) -> FeedHealth:
        raise NotImplementedError("TODO(alpha)")


def open_all() -> list[CaptureFeed]:
    """Open every camera in config/cameras.yaml. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha)")


def iter_health() -> Iterator[FeedHealth]:
    """Yield health snapshots for publishing to cv/camera/{id}/health. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha)")
