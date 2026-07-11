# run_demo.ps1 — start the zone-brain: broker + dashboard (+ real pipeline).
# OWNER: Gamma (dashboard/broker) + Alpha (pipeline). Edit by agreement.
#
#   ./zone-brain/scripts/run_demo.ps1            # dashboard + broker (real pipeline attaches)
#   ./zone-brain/scripts/run_demo.ps1 -Sim       # full simulated mesh, zero hardware
param(
    [switch]$Sim
)
$ErrorActionPreference = "Stop"
$Repo = Resolve-Path "$PSScriptRoot\..\.."

if ($Sim) {
    Write-Host "Starting FULL SIM mesh (embedded amqtt broker + 5 feeds + gate + officer)..."
    python -m crowdvision.sim --all
    exit $LASTEXITCODE
}

# Real venue run: assumes mosquitto is up (see setup.ps1) OR falls back to sim broker.
Write-Host "Starting dashboard on http://0.0.0.0:8000 (open from any LAN device)..."
# Dashboard entrypoint (Gamma, Phase B): zone-brain/server/app.py
python "$Repo\zone-brain\server\app.py"
