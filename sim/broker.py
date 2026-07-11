"""sim/broker.py — embedded pure-Python amqtt broker for the sim/dev path.

Hard Rule 8: mosquitto is the venue broker; sim/dev embeds amqtt so the judges'
`python -m crowdvision.sim --all` needs ZERO external install. Runs the async
amqtt Broker in a background thread with its own event loop; sync paho clients
connect to it on 127.0.0.1:1883 like any other broker.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time

# amqtt is chatty (INFO + benign "No more data" lines on abrupt client disconnect)
# — silence it for a clean demo console. Our own port-check catches real failures.
logging.getLogger("amqtt").setLevel(logging.CRITICAL)
logging.getLogger("transitions").setLevel(logging.CRITICAL)


def _broker_config(host: str, port: int) -> dict:
    # Bind ALL interfaces so real LAN devices (UNO Q, OnePlus, phones) can
    # connect — matching the dashboard and mosquitto.conf. Local clients still
    # connect via 127.0.0.1 (0.0.0.0 includes loopback).
    return {
        "listeners": {"default": {"type": "tcp", "bind": f"0.0.0.0:{port}",
                                  "max_connections": 100}},
        "plugins": {
            "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
        },
    }


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class EmbeddedBroker:
    """Start/stop an in-process amqtt broker; block until it accepts sockets."""

    def __init__(self, host: str = "127.0.0.1", port: int = 1883):
        self.host = host
        self.port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broker = None
        self._thread: threading.Thread | None = None

    def start(self, wait_s: float = 8.0) -> "EmbeddedBroker":
        if _port_open(self.host, self.port):
            # Something is already listening (e.g. mosquitto) — reuse it.
            return self
        ready = threading.Event()

        def _run():
            from amqtt.broker import Broker
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            async def _boot():
                # Construct INSIDE the running loop — Broker.__init__ calls
                # asyncio.get_running_loop().
                self._broker = Broker(_broker_config(self.host, self.port))
                await self._broker.start()
                ready.set()

            loop.create_task(_boot())
            loop.run_forever()

        self._thread = threading.Thread(target=_run, name="amqtt-broker", daemon=True)
        self._thread.start()
        ready.wait(timeout=wait_s)
        # Confirm the socket is actually accepting before returning.
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if _port_open(self.host, self.port):
                return self
            time.sleep(0.05)
        raise RuntimeError(f"embedded broker failed to bind {self.host}:{self.port}")

    def stop(self) -> None:
        if self._loop and self._broker:
            async def _shutdown():
                try:
                    await self._broker.shutdown()
                except Exception:  # noqa: BLE001
                    pass
                self._loop.stop()
            try:
                asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
            except Exception:  # noqa: BLE001
                pass
        if self._thread:
            self._thread.join(timeout=3.0)


if __name__ == "__main__":
    b = EmbeddedBroker().start()
    print(f"[broker] amqtt listening on {b.host}:{b.port} — Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        b.stop()
