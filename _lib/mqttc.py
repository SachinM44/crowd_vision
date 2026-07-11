"""crowdvision._lib.mqttc — thin paho-mqtt wrapper with LWT + heartbeat.

Every device connects through here so that:
  * a Last-Will-and-Testament marks it offline on cv/sys/heartbeat/{device}
    (retained), and
  * an online heartbeat is published (retained) on connect.

Hard Rule 8: paho-mqtt client; broker is mosquitto at the venue, amqtt in
sim/dev. This wrapper does not care which broker it talks to.
"""
from __future__ import annotations

import threading
from typing import Callable

import paho.mqtt.client as mqtt

from . import messages as M

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1883

OnMessage = Callable[[str, dict], None]


def _new_client(client_id: str) -> mqtt.Client:
    """Create a paho client, tolerant of paho 1.x and 2.x APIs."""
    try:  # paho-mqtt >= 2.0
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except (AttributeError, TypeError):  # paho-mqtt 1.x
        return mqtt.Client(client_id=client_id)


class MqttNode:
    """A connected MQTT participant with LWT + heartbeat wiring."""

    def __init__(self, device: str, *, host: str = DEFAULT_HOST,
                 port: int = DEFAULT_PORT, seq_start: int = 0):
        self.device = device
        self.host = host
        self.port = port
        self._seq = seq_start
        self._handlers: list[tuple[str, OnMessage]] = []
        self._lock = threading.Lock()
        self.client = _new_client(f"cv-{device}")

        # LWT: broker publishes this (retained) if we drop without a clean DISCONNECT.
        will = M.envelope(M.T_HEARTBEAT, device, -1,
                          {"device": device, "state": "offline", "reason": "lwt"})
        self.client.will_set(M.topic_heartbeat(device), M.dumps(will),
                             qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # -- lifecycle --------------------------------------------------------
    def connect(self) -> "MqttNode":
        self.client.connect(self.host, self.port, keepalive=15)
        self.client.loop_start()
        return self

    def disconnect(self) -> None:
        # Clean offline heartbeat, then disconnect (suppresses the LWT).
        try:
            self.publish_heartbeat("offline")
        finally:
            self.client.loop_stop()
            self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        for topic, _ in self._handlers:
            client.subscribe(topic, qos=1)
        self.publish_heartbeat("online")

    def _on_message(self, client, userdata, msg):
        try:
            parsed = M.loads(msg.payload)
        except Exception:  # noqa: BLE001 - never let a bad payload kill the loop
            return
        for topic, handler in self._handlers:
            if mqtt.topic_matches_sub(topic, msg.topic):
                handler(msg.topic, parsed)

    # -- pub/sub ----------------------------------------------------------
    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def publish(self, topic: str, msg_type: str, payload: dict, *,
                qos: int = 1, retain: bool = False,
                properties=None) -> dict:
        env = M.envelope(msg_type, self.device, self.next_seq(), payload)
        self.client.publish(topic, M.dumps(env), qos=qos, retain=retain,
                            properties=properties)
        return env

    def publish_heartbeat(self, state: str) -> None:
        env = M.envelope(M.T_HEARTBEAT, self.device, self.next_seq(),
                         {"device": self.device, "state": state})
        self.client.publish(M.topic_heartbeat(self.device), M.dumps(env),
                            qos=1, retain=True)

    def on(self, topic: str, handler: OnMessage) -> "MqttNode":
        """Register a handler for a topic (subscribe filter). Chainable."""
        self._handlers.append((topic, handler))
        if self.client.is_connected():
            self.client.subscribe(topic, qos=1)
        return self


def ttl_properties(ttl_s: int):
    """MQTT v5 message-expiry properties for gate.command TTL (best-effort).

    Returns None if the paho build lacks v5 properties (falls back to the
    ttl_s field carried in the payload, which the gate node honors anyway).
    """
    try:
        from paho.mqtt.properties import Properties
        from paho.mqtt.packettypes import PacketTypes
        props = Properties(PacketTypes.PUBLISH)
        props.MessageExpiryInterval = int(ttl_s)
        return props
    except Exception:  # noqa: BLE001
        return None
