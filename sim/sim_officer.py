"""sim/sim_officer.py — two virtual field officers.

Publishes cv/officer/{id}/beacon (docs/MESSAGES.md #7) ~every 3 s and acks
cv/dispatch/{id} (#6) by flipping status to "enroute" (referencing dispatch_id).
Two officers at different positions make nearest-dispatch visibly real:
officer-2 sits closer to the demo incident so the decider picks it.

Run standalone:  python -m crowdvision.sim --officer
"""
from __future__ import annotations

import threading
import time

from .._lib import mqttc, messages as M

# Fixed demo positions (venue-local lat/lon near Brookefield, Bengaluru).
OFFICERS = {
    "officer-1": {"lat": 12.9690, "lon": 77.7490, "battery_pct": 78},  # far (Zone C)
    "officer-2": {"lat": 12.9699, "lon": 77.7501, "battery_pct": 84},  # near the incident
}


class SimOfficer:
    def __init__(self, node: mqttc.MqttNode, officer_ids=None):
        """officer_ids: which officers to emulate (default both). Pass a subset
        when a REAL phone owns one (e.g. real officer-1 -> sim only officer-2),
        so the sim never publishes beacons/acks for the hardware's id."""
        self.node = node
        self.roster = {oid: o for oid, o in OFFICERS.items()
                       if not officer_ids or oid in officer_ids}
        self.status = {oid: "available" for oid in self.roster}
        self._last_dispatch = {oid: None for oid in self.roster}
        self._stop = threading.Event()
        for oid in self.roster:
            node.on(M.topic_dispatch(oid), self._on_dispatch)

    def _on_dispatch(self, topic: str, msg: dict) -> None:
        p = msg.get("payload", {})
        oid = p.get("officer_id")
        if oid not in self.roster:
            return
        self.status[oid] = "enroute"
        self._last_dispatch[oid] = p.get("dispatch_id")
        self._beacon(oid)  # immediate ack via beacon

    def _beacon(self, oid: str) -> None:
        o = self.roster[oid]
        self.node.publish(
            M.topic_officer_beacon(oid), M.T_OFFICER_BEACON,
            {"officer_id": oid, "lat": o["lat"], "lon": o["lon"], "accuracy_m": 5.0,
             "status": self.status[oid], "battery_pct": o["battery_pct"],
             "ack_dispatch_id": self._last_dispatch[oid]},
            qos=0)

    def _loop(self) -> None:
        while not self._stop.wait(3.0):
            for oid in self.roster:
                self._beacon(oid)

    def start(self) -> "SimOfficer":
        for oid in self.roster:  # initial beacons so the map populates immediately
            self._beacon(oid)
        threading.Thread(target=self._loop, name="sim-officer", daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()


def run(host="127.0.0.1", port=1883, officer_ids=None) -> SimOfficer:
    node = mqttc.MqttNode("officers-sim", host=host, port=port).connect()
    time.sleep(0.2)
    return SimOfficer(node, officer_ids).start()
