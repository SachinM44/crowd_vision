"""zone-brain/vision/density.py — head points → per-zone density/m² → publish.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Counts head points inside each zone polygon (config/zones.yaml), divides by
zone area_m2, and publishes zone.density.update. Feeds risk.py.

PUBLISHES (docs/MESSAGES.md #1) topic cv/zone/{zone_id}/density (1 Hz/zone):
  payload {zone_id, camera_id, transport, fps_effective, people_count, area_m2,
           density_per_m2, trend_per_min, ttt_red_s, risk, flow_check{...},
           temp_c, temp_source, model_id, inference_backend, latency_ms}

STALE-FEED (Hard Rule 7): if the feed's health is LOST, publish risk="UNKNOWN"
with people_count/density omitted or null — never a guessed number.

CONTRACT:
  publish_zone(node, zone_id, head_points_m, feed_health, badges) -> envelope
"""
from __future__ import annotations


def publish_zone(node, zone_id: str, head_points_m, feed_health, badges) -> dict:
    """Compute density for a zone and publish zone.density.update. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): count-in-polygon / area_m2, honest UNKNOWN")
