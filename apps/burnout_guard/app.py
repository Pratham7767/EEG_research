"""Burnout Guard: break, recovery and weekly check-in companion for Capsule EEG headphones.

    python app.py                                  real headphones
    python app.py --simulate noise                 SDK simulator, real 30 s calibration
    python app.py --simulate noise --fast          simulator, imported calibration (seconds)
    python app.py --simulate noise --fast --demo --data demo_data
                                                   try the dashboard with five weeks of made-up history
    python app.py --selftest                       drive every screen automatically; exit 0 = PASS
                                                   (uses a temporary data folder, your data is untouched)
"""
import argparse
import logging
import os
import shutil
import sys
import tempfile

from bguard import config


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulate", choices=["noise", "sinwave"], help="use the SDK's simulated device")
    ap.add_argument("--fast", action="store_true", help="offer imported calibration/baseline (simulator only)")
    ap.add_argument("--record-eeg", action="store_true", help="also save raw + processed EEG (eeg.csv)")
    ap.add_argument("--data", default=config.DATA_DIR, help="folder for your journal and sessions")
    ap.add_argument("--demo", action="store_true", help="seed five weeks of made-up history if the folder is empty")
    ap.add_argument("--selftest", action="store_true", help="run the whole UI flow automatically (simulator)")
    ap.add_argument("--selftest-live", type=float, default=30, help="seconds of live session in --selftest")
    ap.add_argument("--screenshots", help="with --selftest: save a PNG of every step to this folder")
    ap.add_argument("--keep", action="store_true", help="with --selftest: keep the temporary data folder")
    ap.add_argument("--no-sound", action="store_true")
    args = ap.parse_args(argv)

    temp_dir = None
    if args.selftest:
        args.simulate = args.simulate or "noise"
        args.fast = True
        if args.data == config.DATA_DIR:
            temp_dir = tempfile.mkdtemp(prefix="burnout_guard_selftest_")
            args.data = temp_dir
            args.demo = True
    if args.fast and not args.simulate:
        ap.error("--fast imports generic calibration values and is only allowed with --simulate")

    os.makedirs(config.SDK_LOG_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(os.path.join(config.SDK_LOG_DIR, "app.log"), encoding="utf-8"),
                                  logging.StreamHandler(sys.stderr)])

    from bguard.journal import Journal
    journal = Journal(args.data)
    sessions = os.path.join(args.data, "sessions")
    if args.demo and not journal.entries():
        from bguard.demo import seed
        seed(journal)
        if args.selftest:                      # the self-test must see the real first-run consent screen
            os.replace(journal.path, journal.path + ".tmp")
            with open(journal.path + ".tmp", encoding="utf-8") as src, open(journal.path, "w", encoding="utf-8") as dst:
                dst.writelines(line for line in src if '"type": "consent"' not in line)
            os.remove(journal.path + ".tmp")
    removed = journal.apply_retention(sessions)
    if removed:
        logging.info("retention: deleted %d old session folders", len(removed))

    from bguard.engine import CapsuleEngine
    from bguard.monitor import Monitor
    from bguard.ui.app_window import App, Autopilot

    restart = [os.path.abspath(__file__)] + [a for a in argv if a not in ("--selftest",)]
    engine = CapsuleEngine(simulate=args.simulate, record_eeg=args.record_eeg)
    monitor = Monitor(engine, sessions_root=sessions, journal=journal)
    app = App(engine, monitor, simulate=args.simulate, fast=args.fast,
              sound=not (args.no_sound or args.selftest) and journal.settings().get("sound", True),
              journal=journal, restart_argv=None if args.selftest else restart)
    pilot = Autopilot(app, live_seconds=args.selftest_live, screenshots_dir=args.screenshots) if args.selftest else None
    app.mainloop()

    code = 0
    if pilot:
        print(f"[selftest] {pilot.result}", flush=True)
        code = 0 if pilot.result == "PASS" else 1
    if temp_dir and not args.keep:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
