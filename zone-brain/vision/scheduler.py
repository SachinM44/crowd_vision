"""zone-brain/vision/scheduler.py — shared-session round-robin, freshest-frame.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

THE headline Technical-40 mechanism. One shared QNN session (see detect_qnn.py)
services all feeds via a round-robin, freshest-frame scheduler: each feed
contributes its NEWEST frame; stale frames are dropped, never queued. NOT 5
parallel sessions (NPU contention), NOT batch>1 (kills per-frame determinism).

Target: ~10–25 ms/frame ⇒ ~50–75 inferences/s aggregate ⇒ 10–15 effective
fps/feed across 5 feeds. Measured by zone-brain/bench/mesh_bench.py.

INPUT: capture.CaptureFeed[] (each .latest()).
OUTPUT: yields (Frame, detections) to density.py / tracker.py / gatelines.py,
        plus per-feed fps_effective for the density payload.
"""
from __future__ import annotations

from typing import Iterator


def run(feeds, session, *, on_result) -> None:
    """Round-robin freshest-frame loop. TODO(alpha).

    on_result(camera_id, frame, detections, latency_ms) is called per inference.
    """
    raise NotImplementedError("TODO(alpha): round-robin freshest-frame scheduler")


def fps_effective(camera_id: str) -> float:
    """Rolling effective fps for a feed (goes into zone.density.update). TODO(alpha)."""
    raise NotImplementedError("TODO(alpha)")
