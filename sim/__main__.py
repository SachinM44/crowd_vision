"""python -m crowdvision.sim [--all|--feeds|--gate|--officer|--zones]

Zero-hardware simulation harness. `--all` starts the embedded amqtt broker and
every sim component so judges reproduce the full mesh with no phones:
  broker -> sim_gate + sim_officer + sim_feeds + decider (replay).

Selective flags run single components against an already-running broker (or start
one if none is up). Open the dashboard at http://localhost:8000 (Gamma B3).
"""
from __future__ import annotations

import argparse
import time

from .._lib import config
from . import broker as broker_mod


def _broker_hostport() -> tuple[str, int]:
    try:
        b = config.devices().get("broker", {})
        return b.get("host", "127.0.0.1"), int(b.get("port", 1883))
    except Exception:  # noqa: BLE001
        return "127.0.0.1", 1883


def _dash_url() -> str:
    try:
        d = config.devices().get("dashboard", {})
        port = int(d.get("port", 8000))
    except Exception:  # noqa: BLE001
        port = 8000
    return f"http://localhost:{port}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="crowdvision.sim", description=__doc__)
    ap.add_argument("--all", action="store_true", help="full simulated mesh")
    ap.add_argument("--feeds", action="store_true", help="density + camera health only")
    ap.add_argument("--gate", action="store_true", help="virtual gate only")
    ap.add_argument("--officer", action="store_true", help="virtual officer only")
    ap.add_argument("--zones", action="store_true", help="venue-tier sim zones only")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="auto-stop after N seconds (0 = run forever)")
    args = ap.parse_args(argv)

    if not any([args.all, args.feeds, args.gate, args.officer, args.zones]):
        args.all = True  # default

    host, port = _broker_hostport()

    # Broker: embed amqtt for --all, or if nothing is already listening.
    embedded = None
    embedded = broker_mod.EmbeddedBroker(host, port).start()
    print(f"[sim] broker ready on {host}:{port}")

    comps = []
    # Import lazily so single-component runs don't import everything.
    if args.all or args.gate:
        from . import sim_gate
        comps.append(("gate", sim_gate.run(host, port)))
    if args.all or args.officer:
        from . import sim_officer
        comps.append(("officer", sim_officer.run(host, port)))
    if args.all or args.zones:
        try:
            from . import sim_zones  # optional (Gamma B4)
            comps.append(("zones", sim_zones.run(host, port)))
        except Exception as exc:  # noqa: BLE001
            print(f"[sim] venue sim zones not wired yet ({exc}) -- skipping")
    if args.all or args.feeds:
        from . import sim_feeds
        comps.append(("feeds", sim_feeds.run(host, port)))
    if args.all:
        from . import replay
        comps.append(("decider", replay.run(host, port)))

    started = ", ".join(name for name, _ in comps)
    print(f"[sim] running: {started}")
    if args.all or args.feeds:
        print(f"[sim] open the dashboard: {_dash_url()}")
    print("[sim] Ctrl+C to stop.")

    try:
        if args.seconds > 0:
            time.sleep(args.seconds)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _name, c in comps:
            if hasattr(c, "stop"):
                c.stop()
        if embedded:
            embedded.stop()
        print("\n[sim] stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
