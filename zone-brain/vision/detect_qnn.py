"""zone-brain/vision/detect_qnn.py — ONE shared YOLOv8-INT8 QNN session.

OWNER: Alpha (TODO(alpha)). STUB — contract only.

Loads the QNN-exported YOLOv8-Det INT8 model into a SINGLE onnxruntime session
with the QNN EP (htp_performance_mode: burst) and runs person-class detection.
The session is created ONCE and shared by scheduler.py across all feeds.

NPU proof is separate: zone-brain/scripts/verify_npu.py uses get_ep_devices()
(NEVER get_available_providers() — Hard Rule 3).

BADGES (Hard Rule 2): emit model_id="yolov8n-det-int8-qnn",
inference_backend="qnn-npu-hexagon-v73" when the QNN EP is truly attached;
inference_backend="cpu" on honest CPU fallback.

CONTRACT:
  build_session(model_path, *, performance_mode="burst") -> session
  detect(session, image) -> (boxes, head_points, latency_ms)
"""
from __future__ import annotations


def build_session(model_path: str, *, performance_mode: str = "burst"):
    """Create the single shared QNN session. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha): onnxruntime QNN EP, burst, shared")


def detect(session, image):
    """Run person detection; return (boxes, head_points, latency_ms). TODO(alpha)."""
    raise NotImplementedError("TODO(alpha)")


def active_backend(session) -> str:
    """Return the honest badge for the EP that actually ran. TODO(alpha)."""
    raise NotImplementedError("TODO(alpha)")
