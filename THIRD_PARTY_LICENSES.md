# Third-Party Licenses

CrowdVision's own code (**Entrant Materials**) is licensed **MIT** (see `LICENSE`),
as required by Official Rules §8.c. That MIT grant covers only our code — it does
**not** re-license third-party components. This file records the licenses of the
components CrowdVision depends on. Per Rules §8.d, Qualcomm/QTI Products are used
only for the hackathon Purpose; we never redistribute their binaries.

Nothing in this file is a model weight or a runtime binary — those are **fetched at
setup** by `zone-brain/scripts/download_models.py`, with license notices printed,
and are excluded from the repo by `.gitignore` (Rules §8.c/§8.d).

| Component | Use in CrowdVision | License | Distribution stance |
|---|---|---|---|
| **Ultralytics YOLOv8 / YOLO11** | Person-detection model exported to QNN INT8 (vision) | **AGPL-3.0** | Open-source ✔ but viral — weights **and** Ultralytics code stay **out** of this MIT repo; fetched at setup. |
| **Gemma / FunctionGemma** | On-phone incident structuring (`FunctionGemma 270M`), E2B NPU probe | **Gemma Terms of Use** | Not MIT-relicensable; weights fetched at setup, never committed. |
| **Qualcomm AI SDK / QNN runtime** | NPU execution provider (`onnxruntime-qnn`), LiteRT NPU `.so` set | Qualcomm SDK terms (via pip / official sample app) | Arrives via pip on PC; on Android copied from the official LiteRT-LM sample per the Developer Guide. **We do not redistribute** these binaries. |
| **onnxruntime / onnxruntime-qnn** | Vision inference session on the X Elite NPU | MIT (ORT) + Qualcomm terms (QNN EP) | Installed via pip. |
| **LiteRT / LiteRT-LM** | On-device generative runtime (phone) | Apache-2.0 | Installed via the app build. |
| **Leaflet** | Dashboard map (local floorplan CRS, zero internet tiles) | **BSD-2-Clause** | Vendored JS/CSS in `zone-brain/server/static/`. |
| **Eclipse Paho MQTT** (paho-mqtt Python; Paho/HiveMQ on Android) | MQTT clients | **EPL-2.0 / EDL-1.0** | Installed via pip / Gradle. |
| **amqtt** | Pure-Python MQTT broker (sim/dev + fallback) | MIT | Installed via pip. |
| **Eclipse Mosquitto** | Venue/production MQTT broker | EPL-2.0 / EDL-1.0 | External broker; not bundled. |
| **FastAPI / Starlette / Uvicorn** | Dashboard server + WebSocket fan-out | MIT / BSD | Installed via pip. |
| **NumPy** | Vision/geometry math | BSD-3-Clause | Installed via pip. |
| **OpenCV (opencv-python)** | Capture, homography, calibration | Apache-2.0 | Installed via pip. |
| **PyYAML** | Config loading | MIT | Installed via pip. |
| **Arduino App Lab / Bridge** | UNO Q gate node | Arduino (AGPL/LGPL per component) | On the provided device; app code is ours (MIT). |
| **AOSP LocationManager** | Officer GPS beacon | Apache-2.0 | Android platform API. |

**Camera-app note (Rules §7.c.i):** the demo uses an Android RTSP streamer app
(e.g., IP Webcam — freeware, not open-source) purely as an *input device*, like
closed-firmware CCTV or the OS itself. No closed code is included in this
submission; the pipeline consumes standard RTSP/MJPEG and the README requires only
"any RTSP source." An open-source streamer works identically.
