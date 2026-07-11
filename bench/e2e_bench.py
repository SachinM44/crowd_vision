"""bench/e2e_bench.py — end-to-end frame -> gate-actuated (BENCHMARKS #4).

OWNER: Gamma (Role Assignment gives Gamma the e2e semantics). Drives the sim
loop: publishes a RED zone.density and times until the gate ACKs the resulting
CLOSE_DIVERT_LEFT — i.e. the density -> decider -> gate.command -> telemetry path.
In sim this is MQTT + decider + gate echo; on hardware the same clock method
measures NPU frame -> UNO Q actuation (zone-brain/bench, real devices).

Standalone:  python bench/e2e_bench.py
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crowdvision.sim import broker as B, sim_gate, replay  # noqa: E402
from crowdvision._lib import mqttc, messages as M            # noqa: E402
from bench import _util                                      # noqa: E402


def run(n: int = 50) -> dict:
    br = B.EmbeddedBroker().start()
    gate = sim_gate.run()
    dec = replay.run()  # noqa: F841 (keeps the decider alive)
    hit = threading.Event()

    mon = mqttc.MqttNode("e2e-mon").connect()

    def on_telem(t, m):
        p = m["payload"]
        if (p.get("state") == "CLOSE_DIVERT_LEFT" and p.get("actuated_ms", 0) > 0):
            hit.set()

    mon.on("cv/gate/+/telemetry", on_telem)
    pub = mqttc.MqttNode("e2e-pub").connect()
    time.sleep(0.6)

    def dens(risk, d):
        pub.publish(M.topic_zone_density("A"), M.T_ZONE_DENSITY,
                    {"zone_id": "A", "density_per_m2": d, "risk": risk,
                     "trend_per_min": 0.5, "model_id": "sim",
                     "inference_backend": M.BACKEND_SIM, "latency_ms": 0.0}, qos=0)

    samples = []
    for _ in range(n):
        dens("GREEN", 0.4)      # reset so the next RED is a transition
        time.sleep(0.12)
        hit.clear()
        t0 = time.perf_counter()
        dens("RED", 5.6)
        if hit.wait(2.0):
            samples.append((time.perf_counter() - t0) * 1000.0)
        time.sleep(0.05)

    gate.stop(); mon.disconnect(); pub.disconnect(); br.stop()
    s = _util.stats(samples)
    md = (f"| metric | value |\n|---|---|\n"
          f"| fires | {s['n']} / {n} |\n"
          f"| e2e density->gate p50 | {s['p50']} ms |\n"
          f"| e2e density->gate p95 | {s['p95']} ms |\n"
          f"| e2e max | {s['max']} ms |\n"
          f"\n_Path: density -> decider -> gate.command -> telemetry ACK (sim, "
          f"MQTT + echo). On hardware: NPU frame -> UNO Q, target < 2 s._")
    return {"title": "End-to-end density -> gate", "e2e_ms": s, "markdown": md}


if __name__ == "__main__":
    _util.write("e2e", run())
