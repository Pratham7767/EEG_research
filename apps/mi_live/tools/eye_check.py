"""Do the eyes follow the arrow? Eye movements to the left / right make a slow (< 4 Hz) voltage step that the
ear electrodes (A1, A2, next to the eyes) pick up strongly: the difference (C3-A1) - (C4-A2) jumps one way for a
look to the left and the other way for a look to the right. Here: per trial, the mean of that slow difference
0.2-1.5 s and 1.5-4 s after the cue minus the 1 s before the cue, left vs right trials (t-test).
    C:\\Python313\\python.exe tools\\eye_check.py <run folder> [...]"""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt
from scipy.stats import ttest_ind

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.recorder import load_run  # noqa: E402

FS = 250
allL, allR = {}, {}
for p in sys.argv[1:]:
    r = load_run(p)
    x = np.nan_to_num(r["eeg"])
    h = (x[:, 1] - x[:, 0]) - (x[:, 2] - x[:, 3])                       # (C3-A1) - (C4-A2)
    h = sosfiltfilt(butter(2, [0.3, 4], btype="bandpass", fs=FS, output="sos"), h - h[0])
    cues = [(s, c) for s, n, c in r["events"] if n in ("cue_left", "cue_right")]
    line = f"{Path(p).name:30s}"
    for win in ((0.2, 1.5), (1.5, 4.0)):
        L, R = [], []
        for s, c in cues:
            if s - FS < 0 or s + 4 * FS > len(h):
                continue
            v = h[s + int(win[0] * FS):s + int(win[1] * FS)].mean() - h[s - FS:s].mean()
            (L if c == C.LEFT else R).append(v)
        allL.setdefault(win, []).extend(L)
        allR.setdefault(win, []).extend(R)
        t = ttest_ind(L, R)
        line += f" | {win[0]}-{win[1]} s: left {np.mean(L):+6.1f} uV, right {np.mean(R):+6.1f} uV, p = {t.pvalue:.3f}"
    print(line)
for win in allL:
    t = ttest_ind(allL[win], allR[win])
    print(f"ALL RUNS {win[0]}-{win[1]} s after cue: left {np.mean(allL[win]):+6.1f} uV, right {np.mean(allR[win]):+6.1f} uV, "
          f"p = {t.pvalue:.4f}  ({len(allL[win])} + {len(allR[win])} trials)")
