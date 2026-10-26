"""Look inside one subject's recordings: timing, data integrity, and ERD done the classic way.

Classic ERD (Pfurtscheller): band-pass, square, AVERAGE OVER TRIALS, then % change from the
reference period. Reported per run type separately (real movement and imagery are different tasks).
Usage: python tools/inspect_session.py P01
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci import config as C                       # noqa: E402
from mibci.dsp import apply_montage                 # noqa: E402
from mibci.recorder import list_runs, load_run      # noqa: E402

FS = C.FS
BANDS = {"mu 8-13": (8, 13), "beta 13-30": (13, 30)}


def main(subject):
    out = {}
    for r in list_runs(subject):
        run = load_run(r)
        rt = run["meta"].get("run_type")
        x = run["eeg"]
        ev = run["events"]
        cues = [(s, c) for s, n, c in ev if n in ("cue_left", "cue_right")]
        starts = [s for s, n, c in ev if n == "trial_start"]
        info = dict(run_type=rt, seconds=round(len(x) / FS, 1), nan_rows=int(np.isnan(x).any(1).sum()),
                    trials=len(cues), left=sum(c == 1 for _, c in cues), right=sum(c == 2 for _, c in cues))
        if cues:
            info["cue_minus_start_s"] = sorted({round((c - s) / FS, 3) for (c, _), s in zip(cues, starts)})
        m = apply_montage(np.nan_to_num(x))
        f, p = welch(m[:, 1:3] - m[:, 1:3].mean(0), fs=FS, nperseg=2 * FS, axis=0)
        info["psd_peak_hz_C3A1_C4A2"] = [float(f[(f > 4) & (f < 40)][np.argmax(p[(f > 4) & (f < 40), k])]) for k in (0, 1)]
        info["line50_ratio"] = [float(p[np.argmin(abs(f - 50)), k] / np.median(p[(f > 20) & (f < 40), k])) for k in (0, 1)]
        if cues and rt in ("movement", "screening", "feedback"):
            info["erd"] = {}
            for bname, band in BANDS.items():
                sos = butter(4, band, btype="bandpass", fs=FS, output="sos")
                pw = sosfiltfilt(sos, m[:, 1:3] - m[:, 1:3].mean(0), axis=0) ** 2
                res = {}
                for cls, cname in ((1, "left"), (2, "right")):
                    ep = []
                    for s, c in cues:
                        if c == cls and s - 2 * FS >= 0 and s + 4 * FS <= len(pw):
                            ep.append(pw[s - 2 * FS:s + 4 * FS])
                    ep = np.array(ep)                                # trials x time x 2
                    avg = ep.mean(0)
                    ref = avg[0:FS].mean(0)                          # -2 .. -1 s before the cue
                    task = avg[int(2.5 * FS):int(5.5 * FS)].mean(0)  # +0.5 .. +3.5 s after the cue
                    curve = 100 * (avg / ref - 1)
                    # 0.5 s bins from -2 to +4 s, for the time course
                    bins = [[round(float(curve[i:i + FS // 2, k].mean()), 1) for i in range(0, 6 * FS, FS // 2)]
                            for k in (0, 1)]
                    res[cname] = dict(n=len(ep), ERD_C3A1=round(float(100 * (task[0] / ref[0] - 1)), 1),
                                      ERD_C4A2=round(float(100 * (task[1] / ref[1] - 1)), 1),
                                      timecourse_C3A1=bins[0], timecourse_C4A2=bins[1])
                info["erd"][bname] = res
        out[r.name] = info
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "P01")
