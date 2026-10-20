"""Run the whole flow without a UI and check the recorded session.

    python -m cogscore.headless --simulate noise --fast --live 20
    python -m cogscore.headless --simulate noise --live 30          # real 30 s calibration + baseline
    python -m cogscore.headless --live 120                          # real headphones

Exit code 0 means every check passed. Used by tests/test_sim_integration.py.
"""
import argparse
import csv
import json
import math
import os
import sys
import time

from . import config
from .engine import CapsuleEngine, State
from .monitor import Monitor

REQUIRED_FILES = ("session.json", "productivity.csv", "emotions.csv", "indices.csv", "bands.csv",
                  "scores.csv", "resistances.csv", "events.csv")


class Failed(RuntimeError):
    pass


def _pump_until(engine, monitor, cond, timeout, what):
    end = time.monotonic() + timeout
    last_tick = 0.0
    while time.monotonic() < end:
        engine.pump()
        if time.monotonic() - last_tick >= 0.5:
            monitor.tick()
            last_tick = time.monotonic()
        if cond():
            return
        time.sleep(0.02)
    raise Failed(f"timed out after {timeout}s waiting for {what} (state={engine.state})")


def run(simulate=None, fast=False, live_seconds=20, sessions_root=config.SESSIONS_DIR,
        record_eeg=False, log=print):
    if fast and not simulate:
        raise ValueError("--fast imports a generic calibration; only allowed with --simulate")
    engine = CapsuleEngine(simulate=simulate, record_eeg=record_eeg)
    monitor = Monitor(engine, sessions_root=sessions_root)
    seen = {"devices": [], "errors": [], "calibration_failed": [], "gate_open": False}
    engine.events.subscribe("devices", lambda d: seen.__setitem__("devices", d))
    engine.events.subscribe("error", seen["errors"].append)
    engine.events.subscribe("calibration_failed", seen["calibration_failed"].append)
    engine.events.subscribe("status", lambda s: log(f"  - {s}"))
    monitor.events.subscribe("quality", lambda g, p, o: seen.__setitem__("gate_open", seen["gate_open"] or o))

    log(f"SDK {engine.sdk_version}")
    try:
        engine.scan()
        _pump_until(engine, monitor, lambda: engine.state != State.SCANNING, config.SCAN_SECONDS + 8, "device list")
        if not seen["devices"]:
            raise Failed(f"no device found: {seen['errors']}")
        log(f"found {seen['devices']}")
        engine.connect(seen["devices"][0]["serial"])
        _pump_until(engine, monitor, lambda: engine.state == State.STREAMING, 60, "connection")
        log(f"connected {engine.device_info}")

        try:
            _pump_until(engine, monitor, lambda: seen["gate_open"], 20, "electrode contact")
            log("signal quality gate open")
        except Failed:
            monitor.override_gate("signal_quality", "headless run")
            log("signal quality gate NOT open, continuing (recorded as override)")

        if fast:
            engine.import_calibration()
        else:
            engine.start_calibration()
            _pump_until(engine, monitor, lambda: engine.state != State.CALIBRATING,
                        config.CALIBRATION_TIMEOUT_S + 5, "calibration")
            if engine.state != State.CALIBRATED:
                raise Failed(f"calibration failed: {seen['calibration_failed']}")
        log(f"calibrated {engine.calibration}")

        if fast:
            engine.import_baseline()
        else:
            engine.start_baseline()
            _pump_until(engine, monitor, lambda: engine.state != State.BASELINE,
                        config.BASELINE_TIMEOUT_S + 5, "baseline")
        if engine.state != State.LIVE:
            raise Failed(f"baseline failed (state={engine.state})")
        log(f"baseline {engine.baseline}")

        _pump_until(engine, monitor, lambda: False if monitor.elapsed_live < live_seconds else True,
                    live_seconds + 10, "live data")
        monitor.add_marker("headless end")
    finally:
        engine.stop()
        monitor.close()

    path = monitor.session.path if monitor.session else None
    return path, monitor.summary()


def check_session(path, min_live_rows=5):
    """Return a list of problems with a recorded session folder (empty = OK)."""
    problems = []
    for name in REQUIRED_FILES:
        f = os.path.join(path, name)
        if not os.path.isfile(f) or os.path.getsize(f) == 0:
            problems.append(f"missing or empty: {name}")
    if problems:
        return problems
    with open(os.path.join(path, "session.json"), encoding="utf-8") as fh:
        meta = json.load(fh)                    # strict JSON check
    for key in ("device", "calibration", "baseline", "own_baseline_bands", "summary", "duration_s"):
        if key not in meta:
            problems.append(f"session.json lacks {key!r}")
    ref_s = config.FAST_WORK_REF_S if meta.get("baseline", {}).get("imported") else config.WORK_REF_S
    expect_stress = meta.get("summary", {}).get("live_duration_s", 0) >= ref_s + 10
    if expect_stress and "own_baseline_ratios" not in meta:
        problems.append("stress/fatigue reference never set")
    with open(os.path.join(path, "bands.csv"), newline="", encoding="utf-8") as fh:
        bands = [r for r in csv.DictReader(fh) if not r["rejected"]]
    if len(bands) < min_live_rows:
        problems.append(f"only {len(bands)} accepted band-power windows")
    for row in bands:
        total = sum(float(row[f"{b}_rel"]) for b in config.RAW_BANDS)
        if not 0.5 <= total <= 1.0001:
            problems.append(f"band relative powers sum to {total:.3f}")
            break
    with open(os.path.join(path, "scores.csv"), newline="", encoding="utf-8") as fh:
        scores = list(csv.DictReader(fh))
    for key in ("attention", "cognitive_load", "relaxation") + (("stress",) if expect_stress else ()):
        vals = [float(r[key]) for r in scores if r[key]]
        if not vals:
            problems.append(f"no {key} scores recorded")
        elif not all(0 <= v <= 100 for v in vals):
            problems.append(f"{key} outside 0-100")
    with open(os.path.join(path, "productivity.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) < min_live_rows:
        problems.append(f"only {len(rows)} productivity rows")
    for row in rows:
        for key in ("concentration", "relaxation", "fatigue", "accumulated_fatigue"):
            v = row[key]
            if v and (not math.isfinite(float(v)) or abs(float(v)) > config.MAX_VALID_VENDOR_SCORE):
                problems.append(f"unsanitised {key}={v}")
                break
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulate", choices=list(CapsuleEngine.SIMULATORS))
    ap.add_argument("--fast", action="store_true", help="import calibration/baseline (simulator only)")
    ap.add_argument("--live", type=float, default=20, help="seconds of live data to record")
    ap.add_argument("--sessions", default=config.SESSIONS_DIR)
    ap.add_argument("--record-eeg", action="store_true")
    args = ap.parse_args(argv)
    try:
        path, summary = run(args.simulate, args.fast, args.live, args.sessions, args.record_eeg)
    except Failed as exc:
        print(f"FAIL: {exc}")
        return 1
    problems = check_session(path)
    print(f"session: {path}")
    print(f"artifact fraction: {summary['artifact_fraction']}, raw windows rejected: {summary['raw_windows_rejected']}, "
          f"ppg: {summary['ppg_detected']}")
    print("mean scores:", {k: round(v['mean'], 1) for k, v in summary['scores'].items() if v['mean'] == v['mean']})
    print("mean band share:", {k: round(v, 3) for k, v in summary['bands_rel_mean'].items() if v == v})
    for p in problems:
        print(f"FAIL: {p}")
    print("PASS" if not problems else "FAIL")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
