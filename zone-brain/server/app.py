"""zone-brain/server/app.py — CrowdVision dashboard (FastAPI + WebSocket).

OWNER: Gamma. Serves the Leaflet local-CRS floorplan dashboard, streams live MQTT
over a WebSocket, and turns per-gate override buttons into gate.command
(operator-override). Bind 0.0.0.0 so any LAN device can open it (it's a URL).

Run standalone:   python zone-brain/server/app.py
From sim:         python -m crowdvision.sim --all   (launches this in a thread)
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import asyncio

# Make crowdvision._lib importable (repo root) AND `import mqtt_bridge` resolvable
# (this dir) whether app.py is run as a script or loaded via importlib from sim.
_ROOT = Path(__file__).resolve().parents[2]
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_HERE))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from crowdvision._lib import config, framebus  # noqa: E402
from mqtt_bridge import DashboardBridge  # noqa: E402  (same dir; on sys.path[0])

_PLACEHOLDER = None


def _placeholder_jpg() -> bytes:
    global _PLACEHOLDER
    if _PLACEHOLDER is None:
        img = np.full((270, 480, 3), 28, np.uint8)
        cv2.putText(img, "connecting camera...", (110, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (120, 120, 120), 2)
        _PLACEHOLDER = cv2.imencode(".jpg", img)[1].tobytes()
    return _PLACEHOLDER

STATIC = Path(__file__).resolve().parent / "static"

# Demo officer lat/lon box mapped onto the floorplan (officers carry GPS).
OFFICER_BBOX = {"lat": [12.9685, 12.9705], "lon": [77.7485, 77.7505]}


def _centroid(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


def build_config() -> dict:
    zcfg = config.zones()
    zones = zcfg.get("zones", {})
    bands = zcfg.get("risk_bands_default", {})
    out_zones, gate_pts = [], {}
    minx = miny = 1e9
    maxx = maxy = -1e9
    for zid, z in zones.items():
        poly = z.get("polygon", [])
        out_zones.append({"id": zid, "name": z.get("name", zid), "polygon": poly,
                          "gate_id": z.get("gate_id"), "camera_id": z.get("camera_id"),
                          "area_m2": z.get("area_m2")})
        for x, y in poly:
            minx, miny = min(minx, x), min(miny, y)
            maxx, maxy = max(maxx, x), max(maxy, y)
        gid = z.get("gate_id")
        if gid and poly:
            gate_pts.setdefault(gid, []).append(_centroid(poly))
    gates = [{"id": gid, "pos": _centroid(pts)} for gid, pts in gate_pts.items()]
    if minx > maxx:  # no polygons
        minx, miny, maxx, maxy = 0, 0, 16, 10
    # Camera preview URLs (operator sees the live feeds locally). Only IP Webcam
    # style snapshot sources get a browser-loadable thumbnail.
    cam_list = []
    live_tp = ("ipwebcam", "snapshot", "rtsp", "mjpeg", "webcam")
    for cid, c in config.cameras().get("cameras", {}).items():
        transport = (c.get("transport") or "").lower()
        url = str(c.get("url", ""))
        # Thumbnail = OUR annotated frame (video + person boxes), served locally.
        live = transport in live_tp and not any(t in url for t in ("PHONE_", "_IP"))
        shot = f"/api/cam/{cid}.jpg" if live else None
        cam_list.append({"id": cid, "zone_id": c.get("zone_id"), "shot_url": shot})
    return {"bounds": [[minx, miny], [maxx, maxy]], "zones": out_zones,
            "gates": gates, "officer_bbox": OFFICER_BBOX, "cameras": cam_list,
            "bands": {"amber_at": bands.get("amber_at", 3.0),
                      "red_at": bands.get("red_at", 5.0)}}


def create_app(broker_host: str = "127.0.0.1", broker_port: int = 1883) -> FastAPI:
    bridge = DashboardBridge(broker_host, broker_port)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bridge.start(asyncio.get_running_loop())
        yield
        bridge.stop()

    app = FastAPI(title="CrowdVision Dashboard", lifespan=lifespan)
    app.state.bridge = bridge

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/config")
    async def api_config():
        return JSONResponse(build_config())

    @app.get("/api/cam/{cam_id}.jpg")
    async def cam_frame(cam_id: str):
        data = framebus.get(cam_id) or _placeholder_jpg()
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    @app.post("/api/gate/override")
    async def override(body: dict):
        gate_id = body.get("gate_id")
        action = body.get("action")
        try:
            env = bridge.publish_override(gate_id, action)
            return {"ok": True, "seq": env["seq"]}
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        bridge.clients.add(sock)
        await sock.send_json(bridge.snapshot())
        try:
            while True:
                await sock.receive_text()  # keepalive; client may ping
        except WebSocketDisconnect:
            pass
        finally:
            bridge.clients.discard(sock)

    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
    return app


def serve(host: str = "0.0.0.0", port: int = 8000,
          broker_host: str = "127.0.0.1", broker_port: int = 1883,
          in_thread: bool = False) -> None:
    import uvicorn
    app = create_app(broker_host, broker_port)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port,
                                           log_level="warning"))
    if in_thread:
        server.install_signal_handlers = lambda: None  # not allowed off main thread
    server.run()


if __name__ == "__main__":
    d = {}
    try:
        d = config.devices().get("dashboard", {})
        b = config.devices().get("broker", {})
    except Exception:  # noqa: BLE001
        b = {}
    serve(host=d.get("host", "0.0.0.0"), port=int(d.get("port", 8000)),
          broker_host=b.get("host", "127.0.0.1"), broker_port=int(b.get("port", 1883)))
