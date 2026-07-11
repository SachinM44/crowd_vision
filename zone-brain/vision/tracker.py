"""zone-brain/vision/tracker.py — lightweight centroid tracker.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Associates detections across frames (centroid/IoU) to produce stable tracks used
by gatelines.py for directed line-crossing counts. Counts, never identities — no
face recognition, no re-ID (deliberate non-goal).

CONTRACT:
  update(tracks, detections, ts_ms) -> tracks   (id-stable centroids + velocity)
"""
from __future__ import annotations


def update(tracks, detections, ts_ms: float):
    """Update centroid tracks with new detections. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): greedy centroid association")
