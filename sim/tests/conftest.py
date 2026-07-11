"""Shared pytest fixtures for the sim harness. Headless (Hard Rule 6)."""
from __future__ import annotations

import socket
import time

import pytest

from crowdvision.sim import broker as B
from crowdvision._lib import mqttc


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for(pred, timeout: float = 5.0, interval: float = 0.05) -> bool:
    """Poll pred() until true or timeout. Returns whether it became true."""
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(interval)
    return False


@pytest.fixture()
def broker():
    """A fresh embedded amqtt broker on an isolated port per test."""
    host, port = "127.0.0.1", free_port()
    br = B.EmbeddedBroker(host, port).start()
    yield host, port
    br.stop()


@pytest.fixture()
def monitor(broker):
    """A connected subscriber that records every cv/# message."""
    host, port = broker
    node = mqttc.MqttNode("test-monitor", host=host, port=port).connect()
    msgs: list[tuple[str, dict]] = []
    node.on("cv/#", lambda t, m: msgs.append((t, m)))
    time.sleep(0.3)
    node.messages = msgs
    yield node
    node.disconnect()
