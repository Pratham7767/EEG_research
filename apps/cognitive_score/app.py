"""Cognitive Score: guided focus & fatigue session monitor for Capsule EEG headphones.

    python app.py                                  real headphones
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
    ap.add_argument("--simulate", choices=["noise", "sinwave"], help="use the SDK's simulated device")
    ap.add_argument("--fast", action="store_true", help="offer imported calibration/baseline (simulator only)")
    ap.add_argument("--record-eeg", action="store_true", help="also save raw + processed EEG (eeg.csv)")
    ap.add_argument("--selftest", action="store_true", help="run the whole UI flow automatically (simulator)")
    ap.add_argument("--selftest-live", type=float, default=30, help="seconds of live session in --selftest")
    ap.add_argument("--screenshots", help="with --selftest: save a PNG of every step to this folder")
    ap.add_argument("--sessions", default=config.SESSIONS_DIR, help="folder for session recordings")
    ap.add_argument("--no-sound", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        args.simulate = args.simulate or "noise"
        args.fast = True
    if args.fast and not args.simulate:
        ap.error("--fast imports generic calibration values and is only allowed with --simulate")

    os.makedirs(config.SDK_LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(os.path.join(config.SDK_LOG_DIR, "app.log"), encoding="utf-8"),
                                  logging.StreamHandler(sys.stderr)])

    from cogscore.engine import CapsuleEngine
    from cogscore.monitor import Monitor
    from cogscore.ui.app_window import App, Autopilot

    engine = CapsuleEngine(simulate=args.simulate, record_eeg=args.record_eeg)
    monitor = Monitor(engine, sessions_root=args.sessions)
    app = App(engine, monitor, simulate=args.simulate, fast=args.fast, sound=not (args.no_sound or args.selftest))
    pilot = Autopilot(app, live_seconds=args.selftest_live, screenshots_dir=args.screenshots) if args.selftest else None
    app.mainloop()

    if pilot:
        print(f"[selftest] {pilot.result}", flush=True)
        return 0 if pilot.result == "PASS" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
