"""Summary of a subject's runs from one day: signal quality, ERD, model report, test results.
    C:\\Python313\\python.exe tools\\session_summary.py Pratham [YYYY-MM-DD]"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.dsp import apply_montage  # noqa: E402
from mibci.recorder import list_runs, load_run  # noqa: E402
from milive.dsp_extra import signal_check  # noqa: E402
from milive.personal import format_report  # noqa: E402

subj = sys.argv[1] if len(sys.argv) > 1 else "Pratham"
day = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%Y-%m-%d")
for p in list_runs(subj):
    if not p.name.startswith(day):
        continue
    r = load_run(p)
    m = r["meta"]
    q = signal_check(apply_montage(r["eeg"])[:, [1, 2]])
    s = m.get("summary") or {}
    tag = "calibration block" if m.get("calm_calibration") else ("cued test" if m.get("cued_test") else "")
    print(f"{p.name:30s} {m.get('run_type', ''):9s} {tag:17s} {len(r['eeg']) / 250:5.0f} s | EEG C3 {q['rms_8_30'][0]:5.1f} "
          f"C4 {q['rms_8_30'][1]:5.1f} uV | hum C3 {q['hum_50'][0]:5.1f} C4 {q['hum_50'][1]:5.1f} uV | {q['verdict']:4s} | "
          f"acc {s.get('accuracy', float('nan')):.2f} ({s.get('correct', '?')}/{s.get('trials', '?')}) p {s.get('p', float('nan')):.3f}"
          + (" | STOPPED EARLY" if m.get("stopped_early") else ""))
d = C.DATA_DIR / subj / "decoders_live"
for f in sorted(d.glob(f"report_{day}*.json")) if d.exists() else []:
    print("\n" + f.name)
    print(format_report(json.loads(f.read_text())))
    rep = json.loads(f.read_text())
    for k, v in rep.get("candidates", {}).items():
        print(f"    {k:26s} per run: " + ", ".join(f"{x['correct']}/{x['trials']}" for x in v["per_run"]))
