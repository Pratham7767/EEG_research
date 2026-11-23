"""Cognitive Score: guided focus & fatigue session monitor for Capsule EEG headphones.

    python app.py                                  start window: choose Demo or Real use
    python app.py --mode demo                      demo timings (10-minute presentation)
    python app.py --mode real                      real-use timings (work session)
    python app.py --replay sessions/<name>         stage backup: play a recorded session back
    python app.py --simulate noise                 SDK simulator, real 30 s calibration
    python app.py --simulate noise --fast          simulator, imported calibration (seconds)
    python app.py --simulate noise --selftest      drive every step automatically; exit 0 = PASS
"""
import argparse
import logging
import os
import sys

from cogscore import config


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=list(config.MODE_LABELS), help="skip the start window")
    ap.add_argument("--replay", help="play back a recorded session folder instead of using a device")
    ap.add_argument("--simulate", choices=["noise", "sinwave"], help="use the SDK's simulated device")
    ap.add_argument("--fast", action="store_true", help="offer imported calibration/baseline (simulator only)")
    ap.add_argument("--record-eeg", action="store_true", help="also save raw + processed EEG (eeg.csv)")
    ap.add_argument("--selftest", action="store_true", help="run the whole UI flow automatically (simulator)")
    ap.add_argument("--selftest-live", type=float, default=40, help="seconds of live session in --selftest")
    ap.add_argument("--screenshots", help="with --selftest: save a PNG of every step to this folder")
    ap.add_argument("--sessions", default=config.SESSIONS_DIR, help="folder for session recordings")
    ap.add_argument("--no-sound", action="store_true")
    ap.add_argument("--fullscreen", action="store_true", help="start full screen (F11 toggles)")
    ap.add_argument("--no-stress-break", action="store_true", help="turn the full-screen stress break off")
    args = ap.parse_args(argv)

    if args.selftest:
        args.simulate = args.simulate or ("noise" if not args.replay else None)
        args.fast = True
        args.mode = args.mode or "real"
    if args.fast and not (args.simulate or args.replay):
        ap.error("--fast imports generic calibration values and is only allowed with --simulate")
    if args.replay and args.simulate:
        ap.error("--replay and --simulate cannot be combined")

    os.makedirs(config.SDK_LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(os.path.join(config.SDK_LOG_DIR, "app.log"), encoding="utf-8"),
                                  logging.StreamHandler(sys.stderr)])

    if args.replay:
        args.mode = args.mode or "demo"
    if not args.mode:
        from cogscore.ui.start import choose
        picked = choose(args.sessions, args.simulate)
        if picked is None:
            return 0
        args.mode, replay, stress_break = picked
        args.replay = args.replay or replay
        args.no_stress_break = args.no_stress_break or not stress_break
    config.apply_mode(args.mode)
    config.STRESS_BREAK_ENABLED = not args.no_stress_break
    logging.getLogger(__name__).info("mode=%s replay=%s simulate=%s", args.mode, args.replay, args.simulate)

    from cogscore.monitor import Monitor
    from cogscore.ui.app_window import App, Autopilot

    if args.replay:
        from cogscore.replay import ReplayEngine, ReplayError
        try:
            engine = ReplayEngine(args.replay)
        except ReplayError as exc:
            print(f"Cannot replay {args.replay}: {exc}", file=sys.stderr)
            return 2
    else:
        from cogscore.engine import CapsuleEngine
        engine = CapsuleEngine(simulate=args.simulate, record_eeg=args.record_eeg)
    monitor = Monitor(engine, sessions_root=args.sessions)
    app = App(engine, monitor, simulate=args.simulate, fast=args.fast,
              sound=not (args.no_sound or args.selftest), mode=args.mode, replay=args.replay,
              fullscreen=args.fullscreen)
    pilot = Autopilot(app, live_seconds=args.selftest_live, screenshots_dir=args.screenshots) if args.selftest else None
    app.mainloop()

    if pilot:
        print(f"[selftest] {pilot.result}", flush=True)
        return 0 if pilot.result == "PASS" else 1
    if app.relaunch:
        # "New session": a fresh process (the vendor wrapper allows one device per process).
        import subprocess
        subprocess.Popen([sys.executable, os.path.abspath(__file__), *_relaunch_argv(argv, args.mode)],
                         cwd=os.path.dirname(os.path.abspath(__file__)))
    return 0


def _relaunch_argv(argv, mode):
    """Arguments for "New session": the same options and mode, without --replay (a replay is not repeated)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in ("--mode", "--replay"):
            skip = True
            continue
        if a.startswith(("--mode=", "--replay=")):
            continue
        out.append(a)
    return out + ["--mode", mode] + (["--no-stress-break"] if not config.STRESS_BREAK_ENABLED
                                     and "--no-stress-break" not in out else [])


if __name__ == "__main__":
    sys.exit(main())
