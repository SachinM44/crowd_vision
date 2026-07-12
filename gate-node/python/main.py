"""gate-node/python/main.py — UNO Q MPU: MQTT + fail-safe state machine + LWT.

OWNER: Beta. Contract: docs/MESSAGES.md #3/#4 + BETA_HANDOFF.md §4A-§4E.

SUBSCRIBES cv/gate/{gate_id}/cmd (QoS 1, RETAINED, TTL):
  {gate_id, action, allowed, reason, playbook_id, triggered_by, ttl_s}
  Retained commands replay on every (re)connect — any command whose envelope
  `ts` is older than `ttl_s` is DISCARDED (never actuate a stale command).

PUBLISHES cv/gate/{gate_id}/telemetry:
  * immediately after actuating (QoS 1, actuated_ms > 0 — the ACK, echoes
    triggered_by/playbook_id), and
  * ~1 Hz steady state (QoS 0, actuated_ms 0).

LWT + heartbeat: cv/sys/heartbeat/uno-q-{gate_id} (QoS 1, retained). The will is
registered BEFORE connect; clean shutdown publishes "offline" itself.

DUAL-MODE: on the UNO Q `arduino.app_bridge.Bridge` drives the MCU (sketch.ino
provides gate_set_state/gate_chirp/gate_read_knob/gate_read_thermo). Off-board a
MockBridge stands in so the whole node integration-tests on a laptop against
`python -m crowdvision.sim --all --real-gates G3`. Provenance NEVER lies:
"deterministic-mcu" only when the real Bridge is driving the MCU.

Runs standalone on the board (App Lab) and on a laptop:
    python main.py --broker <laptop-ip> --gate-id G3
    python main.py --bench            # 100x Bridge RPC timing -> gate_bench.json
No `crowdvision` import here — the UNO Q only has this file + requirements.txt.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

IST = timezone(timedelta(hours=5, minutes=30))
GATE_ACTIONS = [
    "OPEN", "CLOSE", "DIVERT_LEFT", "DIVERT_RIGHT",
    "CLOSE_DIVERT_LEFT", "CLOSE_DIVERT_RIGHT", "SAFE_FLASH",
]
DEFAULT_TTL_S = 120.0          # matches config/playbooks.yaml P1/P2 ttl_s
DEFAULT_TEMP_C = 33.5          # reported when no Thermo Modulino is present

# --- Bridge: real on the UNO Q, mock on a laptop (provenance stays honest). --
try:
    from arduino.app_bridge import Bridge  # exists ONLY on the UNO Q (App Lab)
    IS_MOCK = False
except ImportError:
    IS_MOCK = True

    class Bridge:  # type: ignore[no-redef]
        """Laptop stand-in: ~2 ms per RPC, no Modulinos, no MCU."""

        def call(self, fn: str, *args):
            time.sleep(0.002)
            if fn == "gate_read_knob":
                return -1          # -1 = no knob
            if fn == "gate_read_thermo":
                return None
            return "ok"

PROVENANCE = "deterministic-mcu" if not IS_MOCK else "mock-bridge (laptop)"


def now_ts() -> str:
    """ISO-8601 IST with milliseconds — the v9 §e envelope timestamp."""
    return datetime.now(IST).isoformat(timespec="milliseconds")


def is_stale(ts_str, ttl_s) -> bool:
    """True if a (retained) command outlived its TTL. Unparseable => stale.

    Fail safe: a command we cannot date is a command we do not run.
    """
    try:
        ts = datetime.fromisoformat(str(ts_str))
    except (ValueError, TypeError):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    try:
        ttl = float(ttl_s)
    except (ValueError, TypeError):
        ttl = DEFAULT_TTL_S
    return (datetime.now(timezone.utc) - ts).total_seconds() > ttl


class GateNode:
    def __init__(self, broker: str, port: int, gate_id: str,
                 temp_default: float = DEFAULT_TEMP_C):
        self.gate_id = gate_id
        self.device = f"uno-q-{gate_id}"
        self.broker, self.port = broker, port
        self.temp_default = temp_default
        self.state = "OPEN"
        self.override = "NONE"
        self.link_ok = False
        self.last_cmd: dict = {}
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._stop = threading.Event()
        self._last_knob = -1

        self.bridge = Bridge()
        self.modulinos = self._detect_modulinos()

        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                        client_id=f"cv-{self.device}")
        # LWT BEFORE connect (§4C): broker flips us offline if we vanish.
        c.will_set(f"cv/sys/heartbeat/{self.device}",
                   json.dumps(self._envelope("sys.heartbeat", {
                       "device": self.device, "state": "offline",
                       "reason": "lwt"})),
                   qos=1, retain=True)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client = c

    # -- envelope (hand-built; must pass _lib.messages.validate_envelope) -----
    def _envelope(self, mtype: str, payload: dict) -> dict:
        with self._seq_lock:
            self._seq += 1
            seq = self._seq
        return {"type": mtype, "v": 1, "ts": now_ts(), "src": self.device,
                "seq": seq, "payload": payload}

    def _publish(self, topic: str, mtype: str, payload: dict,
                 qos: int = 1, retain: bool = False) -> None:
        env = self._envelope(mtype, payload)
        self.client.publish(topic, json.dumps(env, separators=(",", ":")),
                            qos=qos, retain=retain)

    # -- Modulinos: OPTIONAL, auto-detected, honest flags (§4D) ---------------
    def _detect_modulinos(self) -> dict:
        found = {"knob": False, "buzzer": False, "thermo": False}
        if IS_MOCK:
            return found
        probes = {"knob": "gate_read_knob", "buzzer": "gate_chirp",
                  "thermo": "gate_read_thermo"}
        for name, fn in probes.items():
            try:
                r = self.bridge.call(fn)
                found[name] = r is not None and r != -1
            except Exception:
                found[name] = False
        return found

    # -- MQTT callbacks -------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        client.subscribe(f"cv/gate/{self.gate_id}/cmd", qos=1)
        self._heartbeat("online")
        self.link_ok = True
        print(f"[gate {self.gate_id}] connected to {self.broker}:{self.port} "
              f"(bridge={'MOCK' if IS_MOCK else 'REAL'})")
        if self.modulinos["buzzer"]:
            try:
                self.bridge.call("gate_chirp")   # steward chirp on (re)join
            except Exception:
                pass

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.link_ok = False   # MCU holds LAST_SAFE on its own (sketch watchdog)
        print(f"[gate {self.gate_id}] broker link lost — MCU holds LAST_SAFE, "
              f"reconnecting with backoff")

    def _on_message(self, client, userdata, msg):
        try:
            env = json.loads(msg.payload)
        except (ValueError, UnicodeDecodeError):
            return
        p = env.get("payload", {})
        if p.get("gate_id") != self.gate_id or p.get("action") not in GATE_ACTIONS:
            return
        if is_stale(env.get("ts"), p.get("ttl_s", DEFAULT_TTL_S)):
            print(f"[gate {self.gate_id}] DISCARDED stale retained cmd "
                  f"(ts={env.get('ts')} ttl_s={p.get('ttl_s')}) — holding "
                  f"{self.state}")
            return
        self._actuate(p["action"], override="NONE",
                      triggered_by=p.get("triggered_by"),
                      playbook_id=p.get("playbook_id"))
        self.last_cmd = p

    # -- actuation + telemetry ------------------------------------------------
    def _actuate(self, action: str, override: str, triggered_by=None,
                 playbook_id=None) -> None:
        t0 = time.perf_counter()
        try:
            self.bridge.call("gate_set_state", action)
        except Exception as exc:
            print(f"[gate {self.gate_id}] Bridge RPC FAILED ({exc}) — state held")
            return
        rpc_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        self.state, self.override = action, override
        print(f"[gate {self.gate_id}] {action}  (rpc {rpc_ms} ms, "
              f"by {triggered_by or override})")
        self._telemetry(actuated_ms=max(rpc_ms, 1.0), bridge_rpc_ms=rpc_ms,
                        qos=1, triggered_by=triggered_by, playbook_id=playbook_id)

    def _read_temp(self) -> float:
        if self.modulinos["thermo"]:
            try:
                t = self.bridge.call("gate_read_thermo")
                if t is not None:
                    return round(float(t), 1)
            except Exception:
                pass
        return self.temp_default

    def _telemetry(self, actuated_ms: float, bridge_rpc_ms: float, qos: int,
                   triggered_by=None, playbook_id=None) -> None:
        payload = {
            "gate_id": self.gate_id, "state": self.state,
            "actuated_ms": actuated_ms, "bridge_rpc_ms": bridge_rpc_ms,
            "override": self.override, "failsafe_active": not self.link_ok,
            "temp_c": self._read_temp(), "modulinos": self.modulinos,
            "link_ok": self.link_ok, "provenance": PROVENANCE,
        }
        if triggered_by is not None:
            payload["triggered_by"] = triggered_by
        if playbook_id is not None:
            payload["playbook_id"] = playbook_id
        self._publish(f"cv/gate/{self.gate_id}/telemetry", "gate.telemetry",
                      payload, qos=qos)

    def _heartbeat(self, state: str) -> None:
        self._publish(f"cv/sys/heartbeat/{self.device}", "sys.heartbeat",
                      {"device": self.device, "state": state}, qos=1, retain=True)

    # -- physical Knob override (§4D): actuate + telemetry override:"KNOB" ----
    def _poll_knob(self) -> None:
        if not self.modulinos["knob"]:
            return
        try:
            v = int(self.bridge.call("gate_read_knob"))
        except Exception:
            return
        if v < 0 or v == self._last_knob:
            return
        if self._last_knob >= 0:   # ignore the first read (baseline)
            action = GATE_ACTIONS[v % len(GATE_ACTIONS)]
            self._actuate(action, override="KNOB", triggered_by="knob-override")
        self._last_knob = v

    # -- main loop ------------------------------------------------------------
    def run(self) -> None:
        delay = 1
        while not self._stop.is_set():   # initial connect w/ backoff (§4D)
            try:
                self.client.connect(self.broker, self.port, keepalive=15)
                break
            except OSError as exc:
                print(f"[gate {self.gate_id}] broker unreachable ({exc}) — "
                      f"retry in {delay}s")
                if self._stop.wait(delay):
                    return
                delay = min(delay * 2, 30)
        self.client.loop_start()
        try:
            while not self._stop.wait(1.0):          # 1 Hz steady state (§4B)
                if self.client.is_connected():
                    self.override = "NONE" if self.override == "NONE" else self.override
                    self._telemetry(actuated_ms=0, bridge_rpc_ms=0, qos=0)
                    self._poll_knob()
        finally:
            if self.client.is_connected():
                self._heartbeat("offline")            # clean exit, no LWT fire
                time.sleep(0.2)
            self.client.loop_stop()
            self.client.disconnect()
            print(f"[gate {self.gate_id}] stopped.")

    def stop(self, *_):
        self._stop.set()


# -- bench: BENCH:gate numbers (bridge_rpc_ms x100 + actuated_ms) -------------
def run_bench(out_path: str) -> int:
    bridge = Bridge()
    samples = []
    for i in range(100):
        action = GATE_ACTIONS[i % len(GATE_ACTIONS)]
        t0 = time.perf_counter()
        bridge.call("gate_set_state", action)
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    p = lambda q: round(samples[min(int(len(samples) * q), len(samples) - 1)], 2)
    stats = {"min": round(samples[0], 2), "p50": p(0.50), "p95": p(0.95),
             "max": round(samples[-1], 2),
             "mean": round(statistics.fmean(samples), 2)}
    mode = "MOCK (laptop — not hardware numbers)" if IS_MOCK else "REAL UNO Q Bridge RPC"
    md = ("| metric | value |\n|---|---|\n"
          f"| mode | {mode} |\n"
          f"| bridge_rpc_ms min | {stats['min']} |\n"
          f"| bridge_rpc_ms p50 | {stats['p50']} |\n"
          f"| bridge_rpc_ms p95 | {stats['p95']} |\n"
          f"| bridge_rpc_ms max | {stats['max']} |\n"
          f"| bridge_rpc_ms mean | {stats['mean']} |\n"
          f"| samples | 100 (gate_set_state, all 7 actions round-robin) |")
    doc = {"markdown": md, "captured_at": now_ts(), "mock": IS_MOCK,
           "samples_ms": [round(s, 3) for s in samples]}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print(md)
    print(f"\n[bench] wrote {out_path}"
          + ("  (MOCK — do NOT embed as hardware numbers)" if IS_MOCK else
             "  -> copy to bench/out/gate.json and run: python bench/embed.py"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--broker", default=os.environ.get("CV_BROKER_HOST", "127.0.0.1"),
                    help="broker host — the LAPTOP LAN IP from the UNO Q, "
                         "never 127.0.0.1 on the board")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("CV_BROKER_PORT", "1883")))
    ap.add_argument("--gate-id", default=os.environ.get("CV_GATE_ID", "G3"))
    ap.add_argument("--temp-default", type=float,
                    default=float(os.environ.get("CV_TEMP_DEFAULT", DEFAULT_TEMP_C)))
    ap.add_argument("--bench", action="store_true",
                    help="100x Bridge RPC timing -> gate_bench.json, then exit")
    args = ap.parse_args(argv)

    # Line-buffer stdout: App Lab captures the MPU's stdout for `app logs`, and
    # block buffering would hide every gate event until the process exits.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if args.bench:
        # *.bench.json is gitignored — copy real (non-mock) numbers into
        # bench/out/gate.json, then: python bench/embed.py
        return run_bench(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "gate.bench.json"))

    node = GateNode(args.broker, args.port, args.gate_id,
                    temp_default=args.temp_default)
    signal.signal(signal.SIGINT, node.stop)
    signal.signal(signal.SIGTERM, node.stop)
    node.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
