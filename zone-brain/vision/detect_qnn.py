"""zone-brain/vision/detect_qnn.py — ONE shared YOLOv8-INT8 QNN session.

OWNER: Alpha. Loads the QNN-exported YOLOv8-Det INT8 model into a SINGLE
onnxruntime session with the QNN EP (htp_performance_mode: burst) and runs
person-class detection. The session is created ONCE and shared by scheduler.py
across all feeds (never 5 parallel sessions, never batch>1).

BADGES ARE HONEST (Hard Rule 2) and there is NO silent CPU fallback:
  * QNN EP truly attached (confirmed via onnxruntime.get_ep_devices(), NEVER
    get_available_providers() — Hard Rule 3) -> backend "qnn-npu-hexagon-v73".
  * otherwise the CPU EP is used but LOUDLY logged as backend "cpu"; and if
    build_session(require_npu=True) (the demo path) the mismatch RAISES instead
    of silently downgrading.

onnxruntime / cv2 are lazily imported (Hard Rule 8 — module import stays pure so
the sim never needs them).

CONTRACT:
  build_session(model_path, *, performance_mode="burst", require_npu=False) -> DetectSession
  detect(session, image) -> (boxes_xyxy, head_points_px, latency_ms)
  active_backend(session) -> honest badge string
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from crowdvision._lib import messages as M

MODEL_ID = "yolov8n-det-int8-qnn"
PERSON_CLASS = 0            # COCO person
CONF_THRES = 0.30
NMS_THRES = 0.45
IMGSZ = 640


@dataclass
class DetectSession:
    session: object
    backend: str
    model_path: str
    input_name: str
    imgsz: int = IMGSZ


def _qnn_attached() -> bool:
    """True iff onnxruntime.get_ep_devices() reports a QNN NPU device (Rule 3)."""
    try:
        import onnxruntime as ort
        import onnxruntime_qnn as q
        os.add_dll_directory(os.path.dirname(q.__file__))
        try:
            ort.register_execution_provider_library("QNNExecutionProvider", q.get_library_path())
        except Exception:  # noqa: BLE001 — already registered is fine
            pass
        return any(
            d.ep_name == "QNNExecutionProvider" and str(d.device.type).endswith("NPU")
            for d in ort.get_ep_devices()
        )
    except ImportError:
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[detect_qnn] QNN probe error ({exc}) -> treating NPU as absent")
        return False


def build_session(model_path: str, *, performance_mode: str = "burst",
                  require_npu: bool = False) -> DetectSession:
    """Create the single shared session. Refuses silent CPU fallback."""
    # Probe + policy checks first (no onnxruntime required to fail loudly).
    qnn = _qnn_attached()
    if not qnn and require_npu:
        raise RuntimeError(
            "QNN NPU EP required (demo path) but get_ep_devices() found no NPU. "
            "Refusing silent CPU fallback (Hard Rule 2) — run verify_npu.py / "
            "setup.ps1 on the X Elite, or start with require_npu=False for dev.")
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"model not found: {model_path} (download_models.py stages weights; "
            "weights are never committed — Hard Rule 4)")

    import onnxruntime as ort  # lazy — only needed once we actually build
    if qnn:
        opts = [{"htp_performance_mode": performance_mode, "backend_path": "QnnHtp.dll"}]
        sess = ort.InferenceSession(model_path, providers=["QNNExecutionProvider"],
                                    provider_options=opts)
        backend = M.BACKEND_QNN_NPU
        print(f"[detect_qnn] QNN EP attached (burst) — backend {backend}")
    else:
        sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        backend = M.BACKEND_CPU
        print(f"[detect_qnn] *** QNN EP NOT attached — CPU EP, backend '{backend}'. "
              "Honest dev fallback; NOT the demo path. ***")
    return DetectSession(sess, backend, model_path, sess.get_inputs()[0].name)


def active_backend(session: DetectSession) -> str:
    """Return the honest badge for the EP that actually built the session."""
    return session.backend


def _letterbox(img, size):
    import cv2  # lazy
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas, r, left, top


def detect(session: DetectSession, image):
    """Run person detection; return (boxes_xyxy, head_points_px, latency_ms)."""
    import time
    import cv2  # lazy
    h0, w0 = image.shape[:2]
    canvas, r, pad_x, pad_y = _letterbox(image, session.imgsz)
    blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0

    t0 = time.perf_counter()
    out = session.session.run(None, {session.input_name: blob})[0]
    latency_ms = (time.perf_counter() - t0) * 1000.0

    pred = np.asarray(out)
    if pred.ndim == 3:
        pred = pred[0]
    if pred.shape[0] < pred.shape[1]:      # (84, 8400) -> (8400, 84)
        pred = pred.T
    boxes_xywh = pred[:, :4]
    scores_all = pred[:, 4:]
    cls = scores_all.argmax(1)
    conf = scores_all.max(1)
    keep = (cls == PERSON_CLASS) & (conf >= CONF_THRES)
    boxes_xywh, conf = boxes_xywh[keep], conf[keep]

    boxes, heads = [], []
    if len(boxes_xywh):
        xyxy = np.empty_like(boxes_xywh)
        xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2
        # undo letterbox -> original image px
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - pad_x) / r
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - pad_y) / r
        xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clip(0, w0)
        xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clip(0, h0)
        idxs = cv2.dnn.NMSBoxes(
            [[float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
             for x1, y1, x2, y2 in xyxy],
            conf.tolist(), CONF_THRES, NMS_THRES)
        for i in np.asarray(idxs).flatten().astype(int):
            x1, y1, x2, y2 = xyxy[i]
            boxes.append((float(x1), float(y1), float(x2), float(y2)))
            heads.append((float((x1 + x2) / 2), float(y1)))   # head = top-centre
    return boxes, heads, latency_ms


def _selftest() -> int:
    # No hardware here: prove the honest-fallback contract without a model.
    assert not _qnn_attached(), "dev machine should report NO QNN NPU"
    try:
        build_session("weights/vision/yolov8n_det_int8.onnx", require_npu=True)
        raise AssertionError("require_npu must hard-fail when NPU is absent")
    except RuntimeError as exc:
        assert "Refusing silent CPU fallback" in str(exc)
    print("detect_qnn.py selftest OK: NPU absent -> require_npu hard-fails, "
          "dev path would badge 'cpu' loudly")
    # If a model happens to be staged, exercise a real CPU inference too.
    mp = "weights/vision/yolov8n_det_int8.onnx"
    if os.path.exists(mp):
        s = build_session(mp, require_npu=False)
        b, hpts, ms = detect(s, np.zeros((480, 640, 3), np.uint8))
        print(f"  real CPU inference: backend={active_backend(s)} "
              f"boxes={len(b)} latency={ms:.1f}ms")
    else:
        print("  (no staged model -> real inference skipped; wiring proven via pipeline)")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
