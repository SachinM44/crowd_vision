"""bench/net_bench.py — LAN/MQTT throughput + round-trip latency (BENCHMARKS #3).

OWNER: Gamma. Measures the message-bus performance of the CrowdVision LAN:
throughput (msg/s) and round-trip latency (publish -> subscriber receipt) through
the broker. On the venue hotspot this doubles as the transport health number; the
RTSP per-stream drop rate needs live cameras and is captured at the venue.

Standalone:  python bench/net_bench.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crowdvision.sim import broker as B          # noqa: E402
from crowdvision._lib import mqttc, messages as M  # noqa: E402
from bench import _util                            # noqa: E402


def run(n_latency: int = 100, n_throughput: int = 500) -> dict:
    br = B.EmbeddedBroker().start()
    sub = mqttc.MqttNode("net-sub").connect()
    got = {}
    sub.on("cv/zone/+/density", lambda t, m: got.__setitem__(m["seq"], time.perf_counter()))
    time.sleep(0.4)
    pub = mqttc.MqttNode("net-pub").connect()
    time.sleep(0.3)

    # Round-trip latency: publish, wait for receipt, measure.
    lat_ms = []
    for _ in range(n_latency):
        t0 = time.perf_counter()
        env = pub.publish(M.topic_zone_density("B"), M.T_ZONE_DENSITY,
                          {"zone_id": "B", "density_per_m2": 1.0, "risk": "GREEN",
                           "model_id": "sim", "inference_backend": M.BACKEND_SIM,
                           "latency_ms": 0.0}, qos=0)
        seq = env["seq"]
        while seq not in got and time.perf_counter() - t0 < 1.0:
            time.sleep(0.0005)
        if seq in got:
            lat_ms.append((got[seq] - t0) * 1000.0)

    # Throughput: burst-publish and time until all received.
    got.clear()
    start = time.perf_counter()
    for _ in range(n_throughput):
        pub.publish(M.topic_zone_density("B"), M.T_ZONE_DENSITY,
                    {"zone_id": "B", "density_per_m2": 1.0, "risk": "GREEN",
                     "model_id": "sim", "inference_backend": M.BACKEND_SIM,
                     "latency_ms": 0.0}, qos=0)
    while len(got) < n_throughput and time.perf_counter() - start < 10.0:
        time.sleep(0.002)
    elapsed = time.perf_counter() - start
    thru = round(len(got) / elapsed, 1) if elapsed else 0.0

    pub.disconnect(); sub.disconnect(); br.stop()

    lat = _util.stats(lat_ms)
    md = (f"| metric | value |\n|---|---|\n"
          f"| MQTT round-trip latency p50 | {lat['p50']} ms |\n"
          f"| MQTT round-trip latency p95 | {lat['p95']} ms |\n"
          f"| MQTT throughput | {thru} msg/s ({len(got)}/{n_throughput} delivered) |\n"
          f"| RTSP per-stream drop rate | _pending live cameras (venue)_ |\n"
          f"\n_Broker: embedded amqtt (dev). Venue broker: mosquitto._")
    return {"title": "LAN / MQTT transport", "device": "dev-host",
            "latency_ms": lat, "throughput_msg_s": thru,
            "delivered": len(got), "sent": n_throughput, "markdown": md}


if __name__ == "__main__":
    _util.write("net", run())
