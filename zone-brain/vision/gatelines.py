"""zone-brain/vision/gatelines.py — real + virtual gate-line flow counting.

OWNER: Alpha. Hybrid gate-flow counting:
  * REAL gate lines on Feed G (C4's dedicated Gate-3 lane view) — directed
    in/out counters from tracker.py tracks (higher accuracy).
  * VIRTUAL gate lines derived from zone views for un-camera'd gates.
The method is badged per gate in the flow_check block of zone.density.update
(docs/MESSAGES.md #1): method in "real-gate-line/c4" | "virtual-gate-line/zone-view".

A crossing is a track whose previous->current segment intersects the gate-line
segment. Convention: a crossing counts as `in` when the track ends on the LEFT of
the directed line a->b (positive orientation), times `direction` (pass -1 to
flip). Calibrate the gate_line's a->b point order so `in` matches the real entry
direction. Rates are per-minute over a rolling window so the value is directly
usable in the density payload.

CONTRACT:
  count(tracks, line, direction=1, method=..., ts_ms=None) -> {in_per_min, out_per_min, method}
  GateLine(line, method, direction, window_s)  # the stateful counter the pipeline uses
"""
from __future__ import annotations

import time
from collections import deque


def _orient(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4) -> bool:
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


class GateLine:
    """Stateful directed line-crossing counter with a rolling per-minute window."""

    def __init__(self, line, method: str, direction: int = 1, window_s: float = 60.0):
        self.a, self.b = tuple(line[0]), tuple(line[1])
        self.method = method
        self.direction = 1 if direction >= 0 else -1
        self.window_ms = window_s * 1000.0
        self._events: deque = deque()  # (ts_ms, +1 in | -1 out)

    def step(self, tracks, ts_ms: float) -> tuple[int, int]:
        """Record this frame's crossings; return (n_in, n_out) for the frame."""
        items = getattr(tracks, "tracks", tracks) or []
        n_in = n_out = 0
        for t in items:
            prev, cur = (t.px, t.py), (t.x, t.y)
            if prev == cur:
                continue
            if _segments_cross(prev, cur, self.a, self.b):
                ended = _orient(self.a, self.b, cur)
                signed = self.direction * (1 if ended > 0 else -1)
                self._events.append((ts_ms, signed))
                if signed > 0:
                    n_in += 1
                else:
                    n_out += 1
        while self._events and ts_ms - self._events[0][0] > self.window_ms:
            self._events.popleft()
        return n_in, n_out

    def rates(self, ts_ms: float) -> tuple[float, float]:
        while self._events and ts_ms - self._events[0][0] > self.window_ms:
            self._events.popleft()
        per_min = 60000.0 / self.window_ms
        ins = sum(1 for _t, s in self._events if s > 0) * per_min
        outs = sum(1 for _t, s in self._events if s < 0) * per_min
        return round(ins, 2), round(outs, 2)

    def block(self, tracks, ts_ms: float) -> dict:
        self.step(tracks, ts_ms)
        ins, outs = self.rates(ts_ms)
        return {"gateline_in_per_min": ins, "gateline_out_per_min": outs,
                "method": self.method}


_REGISTRY: dict = {}


def count(tracks, line, direction: int = 1,
          method: str = "virtual-gate-line/zone-view", ts_ms=None) -> dict:
    """Stateless-looking convenience over a cached GateLine (keyed by line+method)."""
    key = (method, tuple(map(tuple, line)))
    gl = _REGISTRY.get(key)
    if gl is None:
        gl = _REGISTRY[key] = GateLine(line, method, direction)
    if ts_ms is None:
        ts_ms = time.monotonic() * 1000.0
    return gl.block(tracks, ts_ms)


def _selftest() -> int:
    from types import SimpleNamespace as NS
    line = [[4.0, 0.0], [4.0, 5.0]]          # vertical gate line at x=4
    gl = GateLine(line, "real-gate-line/c4", direction=1, window_s=60.0)
    # Line a->b points up (+y); ending LEFT (x<4, positive orientation) == in.
    into = NS(px=5.0, py=2.0, x=3.0, y=2.0)     # right->left, ends left  -> in
    outof = NS(px=3.0, py=3.0, x=5.0, y=3.0)    # left->right, ends right -> out
    n_in, n_out = gl.step([into, outof], 1000.0)
    assert (n_in, n_out) == (1, 1), (n_in, n_out)
    # a track that does not reach the line does not count.
    gl.step([NS(px=1.0, py=1.0, x=2.0, y=1.0)], 2000.0)
    ins, outs = gl.rates(2000.0)
    assert ins == 1.0 and outs == 1.0, (ins, outs)
    blk = count([NS(px=5.0, py=1.0, x=3.0, y=1.0)], line, method="virtual-gate-line/zone-view")
    assert blk["method"] == "virtual-gate-line/zone-view" and blk["gateline_in_per_min"] == 1.0, blk
    print("gatelines.py selftest OK: directed crossings in=1 out=1, per-min rates, badged method")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
