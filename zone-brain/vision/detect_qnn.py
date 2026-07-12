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


def _qnn_npu_devices():
    """QNN NPU OrtEpDevices per Hard Rule 3 (get_ep_devices, NEVER
    get_available_providers — the QNN EP is a plugin EP and never shows up there).
    Returns [] when the NPU is absent."""
    try:
        import onnxruntime as ort
        import onnxruntime_qnn as q
        os.add_dll_directory(os.path.dirname(q.__file__))
        try:
            ort.register_execution_provider_library("QNNExecutionProvider", q.get_library_path())
        except Exception:  # noqa: BLE001 — already registered is fine
            pass
        return [d for d in ort.get_ep_devices()
                if d.ep_name == "QNNExecutionProvider"
                and str(d.device.type).endswith("NPU")]
    except ImportError:
        return []
    except Exception as exc:  # noqa: BLE001
        print(f"[detect_qnn] QNN probe error ({exc}) -> treating NPU as absent")
        return []


def _qnn_attached() -> bool:
    """True iff a QNN NPU device is visible. NOTE: device visible != session runs
    on it — build_session() re-checks the session's real providers before badging."""
    return bool(_qnn_npu_devices())


def build_session(model_path: str, *, performance_mode: str = "burst",
                  require_npu: bool = False,
                  force_cpu: bool = False) -> DetectSession:
    """Create the single shared session. Refuses silent CPU fallback.

    The badge is derived from the session's ACTUAL providers, never from mere
    device visibility. That distinction is not academic: in onnxruntime 2.x the
    QNN EP is a plugin EP, and the legacy
        InferenceSession(..., providers=["QNNExecutionProvider"])
    call is silently IGNORED — you get a CPU session on a machine whose NPU is
    plainly visible. Badging off `get_ep_devices()` alone would therefore have
    stamped 'qnn-npu-hexagon-v73' on CPU inference (Hard Rule 2 violation).
    Plugin EPs must be bound with SessionOptions.add_provider_for_devices().
    """
    if force_cpu and require_npu:
        raise ValueError("force_cpu and require_npu are mutually exclusive")
    devices = [] if force_cpu else _qnn_npu_devices()
    if not devices and require_npu:
        raise RuntimeError(
            "QNN NPU EP required (demo path) but get_ep_devices() found no NPU. "
            "Refusing silent CPU fallback (Hard Rule 2) — run verify_npu.py / "
            "setup.ps1 on the X Elite, or start with require_npu=False for dev.")
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"model not found: {model_path} (download_models.py stages weights; "
            "weights are never committed — Hard Rule 4)")

    import onnxruntime as ort  # lazy — only needed once we actually build
    sess = None
    if devices:
        try:
            so = ort.SessionOptions()
            so.add_provider_for_devices(
                devices, {"htp_performance_mode": performance_mode})
            sess = ort.InferenceSession(model_path, sess_options=so)
        except Exception as exc:  # noqa: BLE001
            if require_npu:
                raise RuntimeError(
                    f"QNN NPU session failed to build ({exc}). Refusing silent CPU "
                    "fallback (Hard Rule 2).") from exc
            print(f"[detect_qnn] QNN session build failed ({exc}) -> CPU EP")
            sess = None
    if sess is None:
        sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    # The one source of truth for the badge: what the session ACTUALLY got.
    on_npu = "QNNExecutionProvider" in sess.get_providers()
    if on_npu:
        backend = M.BACKEND_QNN_NPU
        print(f"[detect_qnn] QNN EP attached ({performance_mode}) — backend {backend} "
              f"[providers={sess.get_providers()}]")
    else:
        backend = M.BACKEND_CPU
        if require_npu:
            raise RuntimeError(
                "QNN NPU EP required (demo path) but the session actually runs on "
                f"{sess.get_providers()}. Refusing to badge NPU for CPU work "
                "(Hard Rule 2).")
        if force_cpu:
            print(f"[detect_qnn] CPU EP forced (bench baseline) — backend '{backend}'")
        else:
            print(f"[detect_qnn] *** QNN EP NOT attached — CPU EP, backend '{backend}'. "
                  "Honest dev fallback; NOT the demo path. ***")
    return DetectSession(sess, backend, model_path, sess.get_inputs()[0].name)


def active_backend(session: DetectSession) -> str:
    """Return the honest badge for the EP that actually built the session."""
    return session.backend


def _cv2_or_none():
    """cv2 is OPTIONAL here. opencv-python publishes NO win-arm64 wheel, and the
    X Elite (our NPU host) is win-arm64 — so the inference path must not depend
    on it. numpy fallbacks below are equivalent for our two uses (resize + NMS)."""
    try:
        import cv2  # noqa: PLC0415 — lazy by design (Hard Rule 8)
        return cv2
    except ImportError:
        return None


def _resize_bilinear(img, nw: int, nh: int):
    """Bilinear resize, numpy only — matches cv2.INTER_LINEAR closely enough for
    detection input (half-pixel centres, clamped edges)."""
    h, w = img.shape[:2]
    ys = (np.arange(nh) + 0.5) * (h / nh) - 0.5
    xs = (np.arange(nw) + 0.5) * (w / nw) - 0.5
    ys = np.clip(ys, 0, h - 1)
    xs = np.clip(xs, 0, w - 1)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = np.minimum(y0 + 1, h - 1)
    x1 = np.minimum(x0 + 1, w - 1)
    wy = (ys - y0)[:, None, None]
    wx = (xs - x0)[None, :, None]
    src = img.astype(np.float32)
    top = src[y0][:, x0] * (1 - wx) + src[y0][:, x1] * wx
    bot = src[y1][:, x0] * (1 - wx) + src[y1][:, x1] * wx
    return (top * (1 - wy) + bot * wy).astype(np.uint8)


def _nms_numpy(boxes_xyxy, scores, iou_thres: float):
    """Greedy NMS, numpy only (stand-in for cv2.dnn.NMSBoxes)."""
    if len(boxes_xyxy) == 0:
        return []
    x1, y1, x2, y2 = (boxes_xyxy[:, i] for i in range(4))
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / np.maximum(areas[i] + areas[rest] - inter, 1e-9)
        order = rest[iou <= iou_thres]
    return keep


def _letterbox(img, size):
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    if (nh, nw) == (h, w):
        resized = img                      # already at target scale — skip resize
    else:
        cv2 = _cv2_or_none()
        if cv2 is not None:
            resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        else:
            resized = _resize_bilinear(img, nw, nh)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas, r, left, top


def detect(session: DetectSession, image):
    """Run person detection; return (boxes_xyxy, head_points_px, latency_ms)."""
    import time
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
        cv2 = _cv2_or_none()
        if cv2 is not None:
            idxs = cv2.dnn.NMSBoxes(
                [[float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
                 for x1, y1, x2, y2 in xyxy],
                conf.tolist(), CONF_THRES, NMS_THRES)
            idxs = np.asarray(idxs).flatten().astype(int)
        else:
            idxs = _nms_numpy(xyxy, conf, NMS_THRES)
        for i in idxs:
            x1, y1, x2, y2 = xyxy[i]
            boxes.append((float(x1), float(y1), float(x2), float(y2)))
            heads.append((float((x1 + x2) / 2), float(y1)))   # head = top-centre
    return boxes, heads, latency_ms


def _selftest() -> int:
    """Runs on BOTH hosts: an NPU box (X Elite) and a plain dev laptop."""
    mp = "weights/vision/yolov8n_det_int8.onnx"
    has_npu = _qnn_attached()
    print(f"detect_qnn selftest: QNN NPU visible = {has_npu}")

    if not has_npu:
        # Dev laptop: require_npu must refuse rather than quietly use the CPU.
        try:
            build_session(mp, require_npu=True)
            raise AssertionError("require_npu must hard-fail when NPU is absent")
        except RuntimeError as exc:
            assert "Refusing silent CPU fallback" in str(exc)
        print("  OK: NPU absent -> require_npu hard-fails; dev path badges 'cpu' loudly")

    if not os.path.exists(mp):
        print(f"  (no staged model at {mp} -> inference skipped; "
              "stage it with download_models.py --local)")
        return 0

    s = build_session(mp, require_npu=False)
    b, _heads, ms = detect(s, np.zeros((480, 640, 3), np.uint8))
    backend = active_backend(s)
    print(f"  real inference: backend={backend} boxes={len(b)} latency={ms:.1f}ms")

    # The badge must describe the session's real EP — never device visibility.
    on_npu = "QNNExecutionProvider" in s.session.get_providers()
    expected = M.BACKEND_QNN_NPU if on_npu else M.BACKEND_CPU
    assert backend == expected, f"badge {backend} != actual EP ({expected})"
    print(f"  OK: badge '{backend}' matches the session's real providers")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
