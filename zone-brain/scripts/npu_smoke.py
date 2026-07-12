#!/usr/bin/env python
"""npu_smoke.py — prove the Hexagon NPU actually EXECUTES ops, not just that the
QNN EP is registered.

verify_npu.py answers "is a QNN NPU device visible?" (Hard Rule 3, get_ep_devices).
That is necessary but not sufficient: the EP can be present and still fail to
build a session or silently fall back. This builds a real ONNX graph, creates the
session on QNNExecutionProvider with the HTP backend, runs it, and compares the
output against a numpy reference.

It is a WIRING proof, not a benchmark: the graph is a small conv+relu, NOT
YOLOv8, so no timing number from here may ever be published as a detection
benchmark (Hard Rule 2). Real detection numbers come from zone-brain/bench/.

    python zone-brain/scripts/npu_smoke.py
    exit 0 = ops ran on the NPU · 2 = ran, but on CPU · 3 = QNN EP unavailable
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def build_conv_onnx(path: Path) -> None:
    """A minimal but genuine NCHW conv graph the HTP can take."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(0)
    w = rng.standard_normal((8, 3, 3, 3)).astype(np.float32) * 0.1
    b = np.zeros((8,), dtype=np.float32)

    node_conv = helper.make_node(
        "Conv", ["input", "W", "B"], ["conv_out"],
        kernel_shape=[3, 3], pads=[1, 1, 1, 1], strides=[1, 1])
    node_relu = helper.make_node("Relu", ["conv_out"], ["output"])

    graph = helper.make_graph(
        [node_conv, node_relu], "npu_smoke",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 64, 64])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 8, 64, 64])],
        [numpy_helper.from_array(w, "W"), numpy_helper.from_array(b, "B")],
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 13)],
        producer_name="crowdvision-npu-smoke")
    model.ir_version = 9          # ORT 1.27 rejects newer IR versions
    onnx.checker.check_model(model)
    onnx.save(model, str(path))


def reference(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Direct conv+relu in numpy — the ground truth the NPU must match."""
    n, c, h, wd = x.shape
    out_c = w.shape[0]
    xp = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
    out = np.zeros((n, out_c, h, wd), dtype=np.float32)
    for oc in range(out_c):
        acc = np.zeros((n, h, wd), dtype=np.float32)
        for ic in range(c):
            for kh in range(3):
                for kw in range(3):
                    acc += w[oc, ic, kh, kw] * xp[:, ic, kh:kh + h, kw:kw + wd]
        out[:, oc] = acc + b[oc]
    return np.maximum(out, 0.0)


if __name__ == "__main__":
    # Import the lane's own probe so this proves the SAME code path the pipeline
    # uses (Hard Rule 3: get_ep_devices, never get_available_providers).
    sys.path.insert(0, str(REPO / "zone-brain" / "vision"))
    from detect_qnn import _qnn_attached, active_backend, build_session

    tmp = REPO / "weights" / "vision"
    tmp.mkdir(parents=True, exist_ok=True)
    model_path = tmp / "_npu_smoke_conv.onnx"
    build_conv_onnx(model_path)
    print(f"[npu_smoke] built {model_path.name}")

    if not _qnn_attached():
        print("[npu_smoke] QNN EP unavailable — run setup.ps1 on the X Elite.")
        raise SystemExit(3)
    print("[npu_smoke] QNN NPU device present (get_ep_devices): True")

    # Build through the SAME function the pipeline uses, so this proves the
    # shipping code path — not a bespoke one that happens to work.
    ds = build_session(str(model_path), performance_mode="burst", require_npu=False)
    sess = ds.session
    eps = sess.get_providers()
    print(f"[npu_smoke] session providers: {eps}")
    print(f"[npu_smoke] detect_qnn badge: {active_backend(ds)}")

    rng = np.random.default_rng(1)
    x = rng.standard_normal((1, 3, 64, 64)).astype(np.float32)

    t0 = time.perf_counter()
    out = sess.run(None, {"input": x})[0]
    first_ms = (time.perf_counter() - t0) * 1000.0
    for _ in range(20):
        sess.run(None, {"input": x})
    t1 = time.perf_counter()
    for _ in range(50):
        sess.run(None, {"input": x})
    per_ms = (time.perf_counter() - t1) * 1000.0 / 50

    import onnx
    from onnx import numpy_helper
    m = onnx.load(str(model_path))
    w = numpy_helper.to_array(m.graph.initializer[0])
    b = numpy_helper.to_array(m.graph.initializer[1])
    ref = reference(x, w, b)
    max_err = float(np.abs(out - ref).max())

    print(f"[npu_smoke] output {out.shape}  max|npu-numpy| = {max_err:.2e}")
    print(f"[npu_smoke] first inference {first_ms:.1f} ms, warm {per_ms:.2f} ms "
          f"(conv+relu toy graph — NOT a detection benchmark)")

    if max_err > 1e-2:
        print("[npu_smoke] FAIL: NPU output does not match the numpy reference")
        raise SystemExit(1)
    if "QNNExecutionProvider" not in eps:
        print("[npu_smoke] ran, but NOT on QNN — CPU fallback (badge 'cpu', honest)")
        raise SystemExit(2)
    if active_backend(ds) != "qnn-npu-hexagon-v73":
        print(f"[npu_smoke] FAIL: session is on QNN but badge says "
              f"'{active_backend(ds)}' — badges must not lie (Hard Rule 2)")
        raise SystemExit(1)
    print("[npu_smoke] PASS: real ops executed on the Hexagon NPU via QNN HTP, "
          "numerically correct, and the badge matches the session's real EP.")
    raise SystemExit(0)
