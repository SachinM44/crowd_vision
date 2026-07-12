#!/usr/bin/env bash
# tools/run_live_wsl.sh — run the LIVE camera bridge from WSL.
#
# Why WSL: live capture needs cv2 (+ ultralytics for person boxes), and neither
# has a win-arm64 wheel — but both ship aarch64-Linux wheels. The bridge runs
# here and publishes density/health over MQTT to the Windows-side broker, so
# the rest of the mesh doesn't know or care where the frames were decoded.
#
# Prereq (once):  bash tools/run_live_wsl.sh --setup
# Run:            bash tools/run_live_wsl.sh          # broker = Windows host
#                 CV_BROKER_HOST=10.0.0.5 bash tools/run_live_wsl.sh
#
# From Windows:   wsl -e bash tools/run_live_wsl.sh
#
# Note: the dashboard's per-camera preview tiles use an in-process frame bus,
# so tiles stay on the placeholder when capture runs out-of-process here. The
# density/risk/health flow — the part on the safety path — is identical.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$HOME/cvexport/py312/bin/python"
[ -x "$PY" ] || PY="$HOME/cvexport/venv/bin/python"
[ -x "$PY" ] || { echo "no WSL python env — run zone-brain/scripts/export_yolo_wsl.sh once first"; exit 1; }

# `pip install -e` fails on the OneDrive-synced /mnt/c mount (setuptools cannot
# write its egg-info temp files there), so the package is aliased instead: a
# symlink on native WSL fs named `crowdvision` pointing at the repo root (the
# repo root IS the package — see pyproject.toml), put on PYTHONPATH. Path
# resolution inside _lib.config follows the symlink back to the real repo, so
# config/*.yaml load normally.
PKG="$HOME/cvpkg"
mkdir -p "$PKG"
[ -L "$PKG/crowdvision" ] || ln -s "$REPO" "$PKG/crowdvision"
export PYTHONPATH="$PKG"

if [ "${1:-}" = "--setup" ]; then
  "$PY" -m pip -q install paho-mqtt pyyaml numpy opencv-python-headless ultralytics
  "$PY" -c "import cv2, crowdvision; from crowdvision._lib import config; print('WSL live env OK: cv2', cv2.__version__, '| repo:', config.repo_root())"
  exit 0
fi

# Windows host as seen from WSL = the default-route gateway (NAT networking).
HOST="${CV_BROKER_HOST:-$(ip route show default | awk '{print $3}' | head -1)}"
echo "[run_live_wsl] broker -> $HOST:1883"
exec "$PY" "$REPO/tools/live_capture.py" --host "$HOST"
