# zone-brain/server — Dashboard (FastAPI + WebSocket + Leaflet)

OWNER: **Gamma** (Phase B3). **Building now — don't touch; ping Gamma if blocked.**

Lands as: `app.py` (FastAPI on `0.0.0.0:8000`), `mqtt_bridge.py` (paho → WS
fan-out), `static/` (Leaflet local floorplan CRS, zone polygons by risk, gate
icons, officer dots, feed-health chips, provenance event log, per-gate override
buttons). Consumes every topic in `docs/MESSAGES.md`; renders provenance
(`playbook_id`, `triggered_by`, `inference_backend`, `latency_ms`). Override
buttons publish `gate.command` with `triggered_by:"operator-override"`.

Open from any LAN device — it's a URL. *"If the dashboard doesn't show it, it
didn't happen."*
