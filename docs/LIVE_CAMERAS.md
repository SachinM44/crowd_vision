# Running CrowdVision on REAL cameras (your phones + laptop)

This connects real video (phone RTSP feeds + the laptop webcam) into the same
pipeline the simulator drives. It uses a **CPU occupancy detector** on the laptop
(`tools/live_capture.py`) as a stand-in for Alpha's NPU vision pipeline — same
messages, honest `cpu` badge. Great for proving the real-camera path today.

> Honest note: this measures **how occupied each camera's view is** (empty → low,
> people fill it → high). It is not a precise per-person count — that's Alpha's
> YOLOv8-on-NPU, which publishes the identical messages. Start each camera with an
> **empty view for ~2 seconds** (it learns the background), then people walk in.

## What you need
- The laptop (runs everything) + up to 3 phones as cameras.
- All devices on the **same Wi-Fi** (a laptop hotspot is easiest).
- An RTSP/MJPEG camera app on each phone. **Android:** "IP Webcam" (free). **iPhone:**
  any RTSP/MJPEG streamer (e.g. Larix Broadcaster). The pipeline takes any URL.

## Step 1 — Same network
Put the laptop and all phones on one Wi-Fi (or the laptop's hotspot). They must be
able to reach each other.

## Step 2 — Turn each phone into a camera
Using **IP Webcam** (Android):
1. Install + open it.
2. (Optional) Video preferences → resolution **640×480**.
3. Scroll down → **Start server**.
4. It shows a URL like `http://192.168.1.42:8080`. The video stream URL is:
   - **MJPEG (easiest):** `http://192.168.1.42:8080/video`
   - RTSP: `rtsp://192.168.1.42:8080/h264_ulaw.sdp`
5. Test it: open `http://192.168.1.42:8080` in the **laptop's** browser — you should
   see the phone's camera. If yes, the laptop can reach it. Note the IP for each phone.

## Step 3 — Put the URLs in `config/cameras.yaml`
Edit `config/cameras.yaml`. Recommended mapping (3 phones on the live zones,
laptop webcam optional). Replace IPs with yours:

```yaml
cameras:
  c1:                       # phone 1 -> Zone B
    transport: mjpeg
    url: "http://192.168.1.42:8080/video"
    zone_id: B
  c2:                       # phone 2 -> Zone C
    transport: mjpeg
    url: "http://192.168.1.43:8080/video"
    zone_id: C
  c3:                       # phone 3 -> Zone D
    transport: mjpeg
    url: "http://192.168.1.44:8080/video"
    zone_id: D
```
Optional — use the **laptop webcam** as Zone A instead of the scripted surge:
```yaml
  feed_a:
    transport: webcam
    url: 0                  # 0 = default laptop camera
    zone_id: A
```
(`transport` can be `mjpeg`, `rtsp`, `webcam`, or `file`. Leave a camera with the
`PHONE_..._IP` placeholder and it's simply skipped.)

## Step 4 — Run it on real cameras
```bash
# Real cameras drive the zones, plus the scripted surge on Zone A so the
# automatic gate-closure (kill-shot) still fires even if your rooms are calm:
python -m crowdvision.sim --live --surge

# OR fully live (no scripted surge — the gate only reacts if a camera gets busy):
python -m crowdvision.sim --live
```
Then open **http://localhost:8000**.

> If you mapped the laptop webcam to Zone A (Step 3 optional block), drop `--surge`
> so the surge doesn't fight the real camera on the same zone.

## Step 5 — What you should see (how to know it's working)
- Top **camera chips** turn green with each phone's real fps (e.g. `c1 · 11.8fps · OK`).
- Point a phone at an empty area → its **zone stays green**. Walk people into view →
  that **zone climbs green → amber → red** on the map, live.
- With `--surge`, **Zone A** still auto-cycles to red and **gate G3 flips to 🛑**,
  with the decision + dispatch appearing in the right-hand log.
- Badges in the log read **`cpu` / `motion-occupancy`** — honest: it's the laptop
  CPU, not the NPU.

## Troubleshooting
- **Zone stays grey/UNKNOWN or chip goes red (LOST):** the laptop can't reach that
  phone URL. Re-check Step 2.5 (open the URL in the laptop browser), same Wi-Fi,
  firewall. A feed stale > 10 s → zone UNKNOWN, gate holds (by design).
- **Everything reads high right away:** start with the view **empty** for ~2 s so it
  learns the background; or nudge `diff_thresh`/warmup in `tools/live_capture.py`.
- **Laptop webcam won't open:** another app may be using it; close Zoom/Teams/etc.
- **iPhone:** use the app's RTSP URL with `transport: rtsp`.

## Where this sits
`tools/live_capture.py` is a Gamma CPU bridge to test real cameras now. In the real
system, **Alpha's `zone-brain/vision/*` (YOLOv8 INT8 on the Snapdragon NPU)** replaces
it and publishes the same `zone.density.update` / `camera.health` — so nothing else
changes.
