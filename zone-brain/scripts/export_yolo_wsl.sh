#!/usr/bin/env bash
# export_yolo_wsl.sh — produce weights/vision/yolov8n_det_int8.onnx ON THIS
# MACHINE, inside WSL, with real-crowd calibration.
#
# Why WSL: the X Elite is win-arm64, where neither torch nor opencv-python has
# a wheel — but BOTH ship aarch64 manylinux wheels, so the export runs in an
# aarch64 Ubuntu WSL and the artifact is consumed by the Windows-side QNN EP.
# (The AI Hub QNN-context export remains the ideal; this is the equivalent,
# fully local path: ultralytics ONNX export -> ORT static INT8/QDQ.)
#
# Prereqs: WSL Ubuntu; the calibration repo cloned at $CAL (below):
#   git clone https://github.com/Santhosh121805/crwoddata C:\Users\<you>\cv_staging\crwoddata
# Run FROM WINDOWS:  wsl -e bash zone-brain/scripts/export_yolo_wsl.sh
#
# Licenses: yolov8n.pt is Ultralytics AGPL-3.0 — fetched here, staged into the
# gitignored weights/, NEVER committed (Hard Rule 4 / THIRD_PARTY_LICENSES.md).
set -uo pipefail

REPO_WIN="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$HOME/cvexport"
CAL="${CAL:-/mnt/c/Users/qcwor/cv_staging/crwoddata/calibration_images}"
OUTDIR="$REPO_WIN/weights/vision"
mkdir -p "$WORK" "$OUTDIR"
cd "$WORK"

# Python with torch: distro python if its wheels exist, else micromamba py3.12
# (raw static binary — the .tar.bz2 route needs bzip2, which minimal WSL lacks).
PY=""
if [ ! -d venv ]; then python3 -m venv venv || true; fi
if [ -x venv/bin/pip ]; then
  venv/bin/pip -q install --upgrade pip
  if venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu; then
    PY="$WORK/venv/bin/python"
  fi
fi
if [ -z "$PY" ]; then
  mkdir -p bin
  [ -x bin/micromamba ] || {
    curl -Lso bin/micromamba \
      https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-aarch64
    chmod +x bin/micromamba
  }
  export MAMBA_ROOT_PREFIX="$WORK/mamba"
  ./bin/micromamba create -y -q -p "$WORK/py312" python=3.12 pip -c conda-forge
  PY="$WORK/py312/bin/python"
  "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
fi
[ -x "$PY" ] || { echo "FATAL: no python with torch"; exit 1; }

"$PY" -m pip -q install ultralytics onnx onnxruntime opencv-python-headless

"$PY" - <<'PYEOF'
from ultralytics import YOLO
m = YOLO("yolov8n.pt")
print("exported:", m.export(format="onnx", imgsz=640, opset=13, simplify=True, dynamic=False))
PYEOF

"$PY" - <<PYEOF
from onnxruntime.quantization.shape_inference import quant_pre_process
quant_pre_process("$WORK/yolov8n.onnx", "$WORK/yolov8n_pre.onnx")
print("pre-processed for quantization")
PYEOF

"$PY" "$REPO_WIN/zone-brain/scripts/quantize_yolo_int8.py" \
      "$WORK/yolov8n_pre.onnx" "$WORK/yolov8n_det_int8.onnx" "$CAL"

cp -f "$WORK/yolov8n_det_int8.onnx" "$OUTDIR/yolov8n_det_int8.onnx"
echo "staged -> $OUTDIR/yolov8n_det_int8.onnx"
echo "next (Windows): python zone-brain/scripts/verify_npu.py && python zone-brain/bench/detect_bench.py"
