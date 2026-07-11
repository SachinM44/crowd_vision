# setup.ps1 — AI PC (Surface X Elite, Windows ARM64) one-time setup.
# OWNER: Alpha/Gamma (cross-lane setup — edit by agreement).
#
# Installs the pinned win-arm64 wheelhouse WITHOUT touching venue Wi-Fi, then
# proves the NPU. The wheelhouse (paho/fastapi/uvicorn/numpy/opencv/onnxruntime-qnn)
# is staged on the personal laptop July 8-10 (see §h).
#
#   ./zone-brain/scripts/setup.ps1                 # use bundled wheelhouse if present
#   ./zone-brain/scripts/setup.ps1 -Wheelhouse D:\cv-wheels
param(
    [string]$Wheelhouse = "$PSScriptRoot\..\..\wheelhouse"
)
$ErrorActionPreference = "Stop"
$Repo = Resolve-Path "$PSScriptRoot\..\.."

Write-Host "== CrowdVision setup (X Elite / ARM64) =="

# 1. Editable install of crowdvision + approved deps.
if (Test-Path $Wheelhouse) {
    Write-Host "Installing from offline wheelhouse: $Wheelhouse"
    python -m pip install --no-index --find-links $Wheelhouse -e $Repo
} else {
    Write-Host "No wheelhouse found; installing from index (needs network)."
    python -m pip install -e $Repo
}

# 2. Add the QNN onnxruntime wheel (vision NPU). Pinned; provided via pip (Rules §8.d).
python -m pip install onnxruntime-qnn 2>$null; if (-not $?) {
    Write-Host "onnxruntime-qnn not installed from index — use the staged wheelhouse." -ForegroundColor Yellow
}

# 3. Broker: mosquitto is the venue/production broker. Sim/dev uses embedded amqtt.
Write-Host "Broker: install Eclipse Mosquitto for the venue (config: mosquitto.conf)."
Write-Host "        Sim/dev needs no broker install — 'python -m crowdvision.sim --all' embeds amqtt."

# 4. Prove the NPU (Hard Rule 3: get_ep_devices()).
Write-Host "== Verifying NPU =="
python "$Repo\zone-brain\scripts\verify_npu.py"

Write-Host "Setup done. Run:  ./zone-brain/scripts/run_demo.ps1"
