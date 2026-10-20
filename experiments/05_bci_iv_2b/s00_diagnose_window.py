"""
s00_diagnose_window.py  -  where in the trial does the laterality actually sit?

s02 came out at chance everywhere, which for BCI IV 2b means the epoch window is
wrong, not that the data is empty. The 2b paradigm is:

    0 s  fixation cross + beep        3 s  CUE        3-7 s  motor imagery

so if the `trial` field indexes the TRIAL START rather than the cue, a window of
0.5-3.5 s after `trial` sits entirely inside the fixation period and must score
exactly 50 %.

This script does not assume either convention. It slides a 2 s window across
0-7 s after `trial` and, at each offset, measures how well the C3-vs-C4
log-power difference separates left from right, pooled over subjects. The
offset where separation appears IS the imagery window.
"""

import os

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, detrend, filtfilt
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FS = 250.0
WIN = 2.0
OFFSETS = np.arange(0.0, 6.01, 0.5)


def load(path):
    m = loadmat(path, squeeze_me=True, struct_as_record=False)
    for s in np.atleast_1d(m["data"]):
        X = np.nan_to_num(np.asarray(s.X, float)[:, :3])
        yield detrend(X, axis=0, type="constant"), \
            np.atleast_1d(np.asarray(s.trial)).astype(int), \
            np.atleast_1d(np.asarray(s.y)).astype(int)


def main():
    b, a = butter(4, [8, 30], btype="band", fs=FS)
    n = int(WIN * FS)
    rows = {o: ([], []) for o in OFFSETS}

    for sub in [f"B{i:02d}" for i in range(1, 10)]:
        for suf in ("T", "E"):
            p = os.path.join(DATA, f"{sub}{suf}.mat")
            if not os.path.exists(p):
                continue
            for X, trial, y in load(p):
                Xf = filtfilt(b, a, X, axis=0)
                for o in OFFSETS:
                    s0 = int(o * FS)
                    ok = (trial + s0 + n) <= Xf.shape[0]
                    seg = np.stack([Xf[t + s0:t + s0 + n] for t in trial[ok]])
                    lv = np.log(seg.var(axis=1) + 1e-20)      # (ntr, 3)
                    rows[o][0].append(lv[:, 0] - lv[:, 2])     # C3 - C4
                    rows[o][1].append(y[ok])

    print(f"sliding {WIN:g} s window, 8-30 Hz, feature = log power C3 - C4")
    print(f"pooled over all subjects and sessions\n")
    print(f"{'offset after `trial` (s)':<26}{'AUC':>8}{'|AUC-0.5|':>11}")
    best = (0, 0.5)
    for o in OFFSETS:
        f = np.concatenate(rows[o][0])
        y = np.concatenate(rows[o][1])
        auc = roc_auc_score((y == 2).astype(int), f)
        flag = ""
        if abs(auc - 0.5) > abs(best[1] - 0.5):
            best = (o, auc)
        if abs(auc - 0.5) > 0.05:
            flag = "   <-- laterality here"
        print(f"{o:<26.1f}{auc:>8.4f}{abs(auc - 0.5):>11.4f}{flag}")

    print(f"\nstrongest separation at offset {best[0]:.1f} s "
          f"(AUC {best[1]:.4f})")
    print("Expected if `trial` = trial start : imagery begins at 3.0 s")
    print("Expected if `trial` = cue onset   : imagery begins at 0.0 s")


if __name__ == "__main__":
    main()
