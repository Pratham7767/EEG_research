"""Independent re-computation of ERD_ERS_2b_summary.csv (written by the MATLAB
script erd_ers_2b_stroke_method.m) in Python/scipy. Same recipe:
8-30 Hz Butterworth-2 filtfilt over the 8 s trial plus 0.5 s padding each
side, keep trial time 0..8 s (cue at 3 s), square, mean per class, smooth
0.4 s (re-implementation of MATLAB smooth(y,100): odd span 99, shrinking
centred window at the ends), baseline = 1 s before the cue (2..3 s); the
numbers are taken from 0..4 s after the cue.
Prints the largest difference to the MATLAB numbers.
Run:  C:\\Python313\\python.exe check_with_python.py"""
import csv, os
import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, filtfilt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
FS, PAD, N = 250, 125, 2000                          # 0.5 s padding, 8 s trial
b, a = butter(2, [8 / (FS / 2), 30 / (FS / 2)], btype="bandpass")
BASE = slice(2 * FS, 3 * FS)                         # 2..3 s = 1 s before cue
AFTER = slice(3 * FS, 7 * FS)                        # 0..4 s after the cue
t = np.arange(4 * FS) / FS
mi = (t >= 0.5) & (t < 3.5)

def smooth(y, span=100):
    half = (span - 1 + span % 2 - 1) // 2          # 99-sample window -> 49 each side
    n = len(y)
    return np.array([y[i - h:i + h + 1].mean() for i in range(n) for h in [min(i, n - 1 - i, half)]])

def erd(c):
    c = smooth(c)
    m = c[BASE].mean()
    return ((c - m) / m * 100)[AFTER]

ref = {r["subject"]: r for r in csv.DictReader(open(os.path.join(HERE, "ERD_ERS_2b_summary.csv")))}
worst = 0.0
print("sub   py 0.5-3.5 s: L:C3  L:C4  R:C3  R:C4   max|py-matlab| (pct points)")
for s in range(1, 10):
    name = f"B{s:02d}"
    P3, P4, y = [], [], []
    for f in ("T", "E"):
        m = loadmat(os.path.join(DATA, name + f + ".mat"), simplify_cells=True)
        sess = m["data"] if isinstance(m["data"], (list, np.ndarray)) else [m["data"]]
        for ss in sess:
            X = np.asarray(ss["X"], float)[:, [0, 2]]
            for tr, lab in zip(np.atleast_1d(ss["trial"]).astype(int), np.atleast_1d(ss["y"]).astype(int)):
                i0 = tr - 1 - PAD                           # MATLAB index -> 0-based
                seg = X[max(i0, 0): tr - 1 + N + PAD]
                if i0 < 0 or len(seg) < N + 2 * PAD or np.isnan(seg).any():
                    continue
                xf = filtfilt(b, a, seg, axis=0)[PAD:PAD + N] ** 2
                P3.append(xf[:, 0]); P4.append(xf[:, 1]); y.append(lab)
    P3, P4, y = np.array(P3), np.array(P4), np.array(y)
    vals = {}
    for hand, k in (("L", 1), ("R", 2)):
        vals[hand + "_C3"] = erd(P3[y == k].mean(0))
        vals[hand + "_C4"] = erd(P4[y == k].mean(0))
    r = ref[name]
    diffs = []
    for key, v in vals.items():
        diffs += [abs(v[mi].mean() - float(r["m05_35_" + key])),
                  abs(np.median(v) - float(r["med_" + key])),
                  abs(v.mean() - float(r["mean_" + key]))]
    diffs += [abs((y == 1).sum() - int(r["nLeft"])), abs((y == 2).sum() - int(r["nRight"]))]
    worst = max(worst, max(diffs))
    print(f"{name}   {vals['L_C3'][mi].mean():+6.1f}{vals['L_C4'][mi].mean():+6.1f}"
          f"{vals['R_C3'][mi].mean():+6.1f}{vals['R_C4'][mi].mean():+6.1f}   {max(diffs):.2e}")
print(f"\nworst difference anywhere: {worst:.2e}  ->  {'MATCH' if worst < 1e-6 else 'MISMATCH'}")
