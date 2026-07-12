#!/usr/bin/env python
"""quantize_yolo_int8.py — YOLOv8n ONNX -> INT8 (QDQ) for the QNN EP.

Run inside WSL/Linux (torch + cv2 have aarch64-Linux wheels; win-arm64 has
neither — see export_yolo_wsl.sh, which drives this end-to-end).

Calibration: the 60 real CrowdHuman images from
https://github.com/Santhosh121805/crwoddata, preprocessed EXACTLY like
zone-brain/vision/detect_qnn.py (letterbox 640, 114 pad, RGB, /255) so the
calibration distribution is the deploy distribution.

The Detect head (/model.22/) is EXCLUDED from quantization: quantizing the
DFL/sigmoid/box-decode blinds the model (verified: 0 detections vs a 75-person
fp32 baseline). Backbone+neck INT8 carries the compute; the head stays float.
Sanity-checks int8 vs fp32 person hits on 3 images before accepting the output.

    python quantize_yolo_int8.py <model_pre.onnx> <out_int8.onnx> <calib_dir>
"""
import glob
import sys

import cv2
import numpy as np
import onnx
import onnxruntime as ort
from onnxruntime.quantization import (CalibrationDataReader, QuantFormat,
                                      QuantType, quantize_static)

model_pre, model_out, calib_dir = sys.argv[1:4]
imgs = sorted(glob.glob(calib_dir + "/*.jpg"))
assert imgs, f"no calibration images in {calib_dir}"


def letterbox(img, size=640):
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    im = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, np.uint8)
    t, l = (size - nh) // 2, (size - nw) // 2
    canvas[t:t + nh, l:l + nw] = im
    return canvas


def blob_of(path):
    img = cv2.imread(path)
    if img is None:
        return None
    c = letterbox(img)
    return c[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0


def person_hits(sess, inp, path, thres=0.30):
    out = sess.run(None, {inp: blob_of(path)})[0]
    pred = out[0].T if out.shape[1] < out.shape[2] else out[0]
    conf = pred[:, 4:].max(1)
    cls = pred[:, 4:].argmax(1)
    return int(((cls == 0) & (conf >= thres)).sum())


base = ort.InferenceSession(model_pre, providers=["CPUExecutionProvider"])
inp = base.get_inputs()[0].name
print(f"calibrating on {len(imgs)} images; input {inp}")

m = onnx.load(model_pre)
exclude = [n.name for n in m.graph.node if "model.22" in n.name]
print(f"excluding {len(exclude)} Detect-head nodes from quantization")


class Reader(CalibrationDataReader):
    def __init__(self):
        self.i = 0

    def get_next(self):
        while self.i < len(imgs):
            b = blob_of(imgs[self.i])
            self.i += 1
            if b is not None:
                return {inp: b}
        return None


quantize_static(model_pre, model_out, Reader(),
                quant_format=QuantFormat.QDQ,
                activation_type=QuantType.QUInt8,
                weight_type=QuantType.QInt8,
                per_channel=True,
                nodes_to_exclude=exclude)

q = ort.InferenceSession(model_out, providers=["CPUExecutionProvider"])
ok = True
for p in imgs[:3]:
    n_f, n_q = person_hits(base, inp, p), person_hits(q, inp, p)
    print(f"  {p.rsplit('/', 1)[-1]}: fp32={n_f} int8={n_q}")
    if n_f > 0 and n_q == 0:
        ok = False
assert ok, "int8 blind where fp32 sees people — do not ship this file"
print(f"OK -> {model_out}")
