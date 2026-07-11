"""zone-brain/vision/tracker.py — lightweight centroid tracker.

OWNER: Alpha. Associates detections across frames (greedy nearest-centroid) to
produce stable tracks used by gatelines.py for directed line-crossing counts.
Counts, never identities — no face recognition, no re-ID (deliberate non-goal).

Works in whatever 2D frame it is fed; the pipeline feeds floor-plane metres (after
homography) so gate lines (also metres) and tracks share one frame.

CONTRACT:
  new_tracks() -> TrackSet
  update(tracks, detections, ts_ms) -> TrackSet   (id-stable centroids + velocity;
        each Track keeps its previous position for crossing detection)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Algorithmic (not safety) tunables — a person cannot jump this far between
# frames, and a track survives a few missed frames through occlusion.
MAX_ASSOC_DIST_M = 1.5
MAX_MISSED = 5


@dataclass
class Track:
    id: int
    x: float
    y: float
    px: float          # previous x (for gate-line crossing)
    py: float          # previous y
    vx: float = 0.0
    vy: float = 0.0
    last_ts: float = 0.0
    missed: int = 0
    hits: int = 1


@dataclass
class TrackSet:
    tracks: list = field(default_factory=list)
    next_id: int = 1


def new_tracks() -> TrackSet:
    return TrackSet()


def update(tracks: TrackSet, detections, ts_ms: float) -> TrackSet:
    """Greedy centroid association; returns the (mutated) TrackSet."""
    if tracks is None:
        tracks = new_tracks()
    dets = np.asarray(detections, dtype=np.float64).reshape(-1, 2)
    live = tracks.tracks
    matched_det = set()
    matched_trk = set()

    if live and len(dets):
        pairs = []
        for ti, t in enumerate(live):
            for di, d in enumerate(dets):
                dist = float(np.hypot(d[0] - t.x, d[1] - t.y))
                if dist <= MAX_ASSOC_DIST_M:
                    pairs.append((dist, ti, di))
        for dist, ti, di in sorted(pairs):
            if ti in matched_trk or di in matched_det:
                continue
            t, d = live[ti], dets[di]
            dt = max((ts_ms - t.last_ts) / 1000.0, 1e-3)
            t.px, t.py = t.x, t.y
            t.vx, t.vy = (d[0] - t.x) / dt, (d[1] - t.y) / dt
            t.x, t.y = float(d[0]), float(d[1])
            t.last_ts, t.missed, t.hits = ts_ms, 0, t.hits + 1
            matched_trk.add(ti)
            matched_det.add(di)

    # Unmatched detections -> new tracks.
    for di, d in enumerate(dets):
        if di in matched_det:
            continue
        tracks.tracks.append(Track(id=tracks.next_id, x=float(d[0]), y=float(d[1]),
                                    px=float(d[0]), py=float(d[1]), last_ts=ts_ms))
        tracks.next_id += 1

    # Unmatched tracks -> age out.
    for ti, t in enumerate(live):
        if ti not in matched_trk:
            t.missed += 1
    tracks.tracks = [t for t in tracks.tracks if t.missed <= MAX_MISSED]
    return tracks


def _selftest() -> int:
    ts = new_tracks()
    update(ts, [[0.0, 1.0], [5.0, 1.0]], 0.0)
    assert len(ts.tracks) == 2
    ids = sorted(t.id for t in ts.tracks)
    # move both ~1 m to the right over 1 s.
    update(ts, [[1.0, 1.0], [6.0, 1.0]], 1000.0)
    assert sorted(t.id for t in ts.tracks) == ids, "ids must stay stable"
    t0 = min(ts.tracks, key=lambda t: t.x)
    assert abs(t0.vx - 1.0) < 1e-6 and abs(t0.px - 0.0) < 1e-6, (t0.vx, t0.px)
    # a track that disappears ages out after MAX_MISSED frames.
    for i in range(MAX_MISSED + 1):
        update(ts, [[1.0, 1.0]], 2000.0 + i * 1000.0)
    assert len(ts.tracks) == 1, [t.id for t in ts.tracks]
    print(f"tracker.py selftest OK: stable ids {ids}, vx=1.0 m/s, occlusion age-out")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
