"""python -m crowdvision.sim [--all|--feeds|--gate|--officer|--zones]

Zero-hardware simulation harness. `--all` starts the embedded amqtt broker and
every sim component so judges reproduce the full mesh with no phones:
  broker -> sim_gate + sim_officer + sim_feeds + decider (replay).

Selective flags run single components against an already-running broker (or start
one if none is up). Open the dashboard at http://localhost:8000 (Gamma B3).

`--all --no-feeds` starts everything EXCEPT the sim feeds + sim decider, so the
real Alpha pipeline (zone-brain/vision/pipeline.py) can supply density + engine
against a live broker, dashboard, gate, officer, and venue tier.
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


def _load_venue_tier():
    """Load venue-tier/sim_zones.py (hyphenated dir, not importable) via importlib."""
    import importlib.util
    path = config.repo_root() / "venue-tier" / "sim_zones.py"
    spec = importlib.util.spec_from_file_location("cv_venue_tier", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_live_capture():
    """Load tools/live_capture.py (real-camera bridge) via importlib."""
    import importlib.util
    path = config.repo_root() / "tools" / "live_capture.py"
    spec = importlib.util.spec_from_file_location("cv_live_capture", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _start_dashboard(broker_host: str, broker_port: int):
    """Load zone-brain/server/app.py (hyphenated dir, not importable) and serve
    it in a daemon thread so `sim --all` is truly one command."""
    import importlib.util
    import threading
    app_path = config.repo_root() / "zone-brain" / "server" / "app.py"
    spec = importlib.util.spec_from_file_location("cv_dashboard_app", app_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        d = config.devices().get("dashboard", {})
    except Exception:  # noqa: BLE001
        d = {}
    host, port = d.get("host", "0.0.0.0"), int(d.get("port", 8000))
    threading.Thread(
        target=lambda: mod.serve(host, port, broker_host, broker_port, in_thread=True),
        name="dashboard", daemon=True).start()
    return port


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="crowdvision.sim", description=__doc__)
    ap.add_argument("--all", action="store_true", help="full simulated mesh")
    ap.add_argument("--feeds", action="store_true", help="density + camera health only")
    ap.add_argument("--gate", action="store_true", help="virtual gate only")
    ap.add_argument("--officer", action="store_true", help="virtual officer only")
    ap.add_argument("--zones", action="store_true", help="venue-tier sim zones only")
    ap.add_argument("--live", action="store_true",
                    help="drive zones from REAL cameras (config/cameras.yaml) instead "
                         "of simulated feeds; runs broker+dashboard+gate+officer+decider")
    ap.add_argument("--surge", action="store_true",
                    help="with --live: also run the scripted surge on one zone so the "
                         "kill-shot still fires while real cameras stay calm")
    ap.add_argument("--surge-zone", default="A", help="zone for --surge (default A)")
    ap.add_argument("--no-dashboard", action="store_true",
                    help="do not launch the dashboard with --all / --live")
    ap.add_argument("--no-feeds", action="store_true",
                    help="skip sim feeds + sim decider so Alpha's real pipeline "
                         "supplies density + engine (broker+dashboard+gate+officer+venue)")
    ap.add_argument("--real-gates", default="",
                    help="comma list of gate ids a REAL UNO Q owns (e.g. G3) — "
                         "the sim gate stops emulating them so telemetry never fights")
    ap.add_argument("--real-officers", default="",
                    help="comma list of officer ids a REAL phone owns (e.g. officer-1) — "
                         "the sim officer stops emulating them")
    ap.add_argument("--no-gate", action="store_true", help="no sim gate at all (all real)")
    ap.add_argument("--no-officer", action="store_true", help="no sim officers at all")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="auto-stop after N seconds (0 = run forever)")
    args = ap.parse_args(argv)

    real_gates = {g.strip() for g in args.real_gates.split(",") if g.strip()}
    sim_gate_ids = tuple(g for g in ("G1", "G2", "G3") if g not in real_gates)
    real_off = {o.strip() for o in args.real_officers.split(",") if o.strip()}
    sim_officer_ids = tuple(o for o in ("officer-1", "officer-2") if o not in real_off)

    if not any([args.all, args.feeds, args.gate, args.officer, args.zones, args.live]):
        args.all = True  # default

    host, port = _broker_hostport()

    # Broker: embed amqtt for --all, or if nothing is already listening.
    embedded = None
    embedded = broker_mod.EmbeddedBroker(host, port).start()
    print(f"[sim] broker ready on {host}:{port}")

    comps = []
    if args.live:
        # REAL cameras drive the zones; keep the full react/inform loop.
        from . import sim_gate, sim_officer, replay
        if not args.no_gate and sim_gate_ids:
            comps.append(("gate", sim_gate.run(host, port, gate_ids=sim_gate_ids)))
        if not args.no_officer and sim_officer_ids:
            comps.append(("officer", sim_officer.run(host, port, officer_ids=sim_officer_ids)))
        try:
            vt = _load_venue_tier()
            comps.append(("venue-tier", vt.run(host, port)))
        except Exception as exc:  # noqa: BLE001
            print(f"[sim] venue tier failed to start ({exc}) -- skipping")
        comps.append(("decider", replay.run(host, port)))
        if args.surge:
            from . import sim_feeds
            comps.append((f"surge:{args.surge_zone}",
                          sim_feeds.run_surge(host, port, args.surge_zone)))
        live = _load_live_capture()
        comps.append(("live-capture", live.run(host, port)))
    else:
        # Import lazily so single-component runs don't import everything.
        if (args.all or args.gate) and not args.no_gate and sim_gate_ids:
            from . import sim_gate
            comps.append(("gate", sim_gate.run(host, port, gate_ids=sim_gate_ids)))
        if (args.all or args.officer) and not args.no_officer and sim_officer_ids:
            from . import sim_officer
            comps.append(("officer", sim_officer.run(host, port, officer_ids=sim_officer_ids)))
        if args.all or args.zones:
            try:
                vt = _load_venue_tier()
                comps.append(("venue-tier", vt.run(host, port)))
            except Exception as exc:  # noqa: BLE001
                print(f"[sim] venue tier failed to start ({exc}) -- skipping")
        if (args.all or args.feeds) and not args.no_feeds:
            from . import sim_feeds
            comps.append(("feeds", sim_feeds.run(host, port)))
        if args.all and not args.no_feeds:
            # Sim decider stands in for Alpha's engine; skip it with --no-feeds so
            # the real pipeline (zone-brain/vision/pipeline.py) fires the playbooks.
            from . import replay
            comps.append(("decider", replay.run(host, port)))
        elif args.all and args.no_feeds:
            # Alpha's engine owns gate.command, but dispatch stays in Gamma's glue:
            # escalation-only decider (incident.report + nearest-officer dispatch
            # on RED) so the officer loop still fires in the real-hardware path.
            from . import replay
            comps.append(("dispatcher", replay.run(host, port, dispatch_only=True)))

    dashboard_up = False
    if (args.all or args.live) and not args.no_dashboard:
        try:
            _start_dashboard(host, port)
            dashboard_up = True
        except Exception as exc:  # noqa: BLE001
            print(f"[sim] dashboard failed to start ({exc}) — run it separately: "
                  f"python zone-brain/server/app.py")

    started = ", ".join(name for name, _ in comps)
    print(f"[sim] running: {started}")
    if dashboard_up:
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
