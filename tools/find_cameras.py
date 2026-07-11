"""tools/find_cameras.py — discover IP Webcam phone cameras on the local network.

Phone IPs change whenever the Wi-Fi / hotspot changes. Run this to find them,
then paste the URLs into config/cameras.yaml.

    python tools/find_cameras.py

Scans your subnet for hosts serving on :8080 and confirms each is an IP Webcam
(reachable /shot.jpg). Prints ready-to-paste cameras.yaml lines.
"""
from __future__ import annotations

import concurrent.futures
import socket
import sys
import urllib.request

import cv2
import numpy as np


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"
    finally:
        s.close()


def scan(subnet: str, port: int = 8080, timeout: float = 0.5) -> list[str]:
    def probe(i):
        ip = f"{subnet}.{i}"
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return ip
        except Exception:  # noqa: BLE001
            return None
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=120) as ex:
        for r in ex.map(probe, range(1, 255)):
            if r:
                found.append(r)
    return found


def main() -> int:
    myip = local_ip()
    subnet = ".".join(myip.split(".")[:3])
    print(f"laptop IP: {myip}   scanning {subnet}.1-254 on :8080 ...")
    hosts = scan(subnet)
    cams = []
    for ip in hosts:
        url = f"http://{ip}:8080"
        try:
            data = urllib.request.urlopen(url + "/shot.jpg", timeout=5).read()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            res = f"{img.shape[1]}x{img.shape[0]}" if img is not None else "?"
            bright = int(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()) if img is not None else -1
            state = "covered/dark" if bright < 15 else "live"
            print(f"  FOUND  {url}   {res}  ({state}, brightness {bright})")
            cams.append(url)
        except Exception:  # noqa: BLE001
            print(f"  {url}: :8080 open but not an IP Webcam /shot.jpg")
    if not cams:
        print("  no IP Webcam cameras found. Start the app + 'Start server' on each phone,"
              " and make sure the phones + laptop share the same Wi-Fi/hotspot.")
        return 1
    print("\nPaste into config/cameras.yaml (map each to a zone: B, C, D):")
    for i, url in enumerate(cams):
        zone = ["B", "C", "D", "A"][i % 4]
        print(f'  c{i+1}: {{ transport: ipwebcam, url: "{url}", zone_id: {zone} }}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
