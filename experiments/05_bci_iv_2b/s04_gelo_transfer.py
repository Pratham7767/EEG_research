"""
s04_gelo_transfer.py  -  train on BCI IV 2b, test on our Gelo recordings.

This is the actual goal of the project: a model that has never seen the user,
trained on a public dataset, pointed at our headset.

THREE THINGS MAKE THIS HARDER THAN P2 IN s02
  1. Our headset gives C3 and C4 only. 2b gives C3, Cz, C4. So the 2b model
     has to be retrained on two channels. PART A measures what that costs,
     because a transfer result is unreadable without knowing the ceiling it is
     being compared to.
  2. Device shift on top of subject shift: different reference, a built-in
     lowpass already attenuating upper beta, 3.1x amplitude difference, and a
     self-clicked cue rather than a software one. Euclidean Alignment is
     applied per FILE on our side, which is the correct domain unit and the
     whole reason EA was validated in s02.
  3. Every one of our files holds exactly one class, so class is perfectly
     confounded with session. That does NOT invalidate training (the model
     never sees our data), but it does mean the honest evaluation unit is the
     FILE, not the epoch. 72 epochs from 15 files is not 72 independent
     decisions. PART B therefore reports file-level accuracy and a file-level
     permutation test as the headline, with epoch-level numbers alongside and
     explicitly labelled as optimistic.

The permutation is exact and cheap here: the model is fixed (trained on 2b and
never refitted), so permuting which files are "left" costs nothing but a
relabel. 10,000 shuffles preserving the real 5-left / 10-right split.

Run:  C:\\Python313\\python.exe s04_gelo_transfer.py
"""

import csv
import glob
import os
import warnings

import numpy as np
from pyriemann.classification import FgMDM
from pyriemann.spatialfilters import CSP
from pyriemann.tangentspace import TangentSpace
from scipy.signal import butter, detrend, filtfilt
from sklearn.covariance import ledoit_wolf
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
from sklearn.metrics import balanced_accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RES = os.path.join(HERE, "results")
SUBJECTS = [f"B{i:02d}" for i in range(1, 10)]
SEED = 42
NPERM = 10000

GELO_ROOT = r"D:\trainsvm\data\gelo"
FS_G = 250.0          # our headset, verified in EXPERIMENT_REPORT.txt section 4.2
C3_COL, C4_COL = 1, 2  # of ch1..ch4 -> ch2 = C3, ch3 = C4
MARKS = [1, 2, 3, 4, 5]
MIN_REST = 1.5        # s of rest required before onset, as in gelo_erd.m
TMIN, TMAX = 0.5, 3.5  # s after onset -- identical window to the 2b side
PAD = 0.5
BAND = (8.0, 30.0)
ORDER = 4
NSAMP = int(round((TMAX - TMIN) * FS_G))


# --------------------------------------------------------------------------- #
def invsqrtm(M):
    w, V = np.linalg.eigh(M)
    return (V * (np.maximum(w, 1e-12) ** -0.5)) @ V.T


def align(cov, groups):
    """Euclidean Alignment: whiten each group (session / file) by its own mean."""
    out = np.empty_like(cov)
    for g in np.unique(groups):
        m = groups == g
        P = invsqrtm(cov[m].mean(axis=0))
        out[m] = np.einsum("ij,njk,kl->nil", P, cov[m], P)
    return out


def covs(epochs):
    return np.stack([ledoit_wolf(np.asarray(e, float).T)[0] for e in epochs])


def models():
    svc = LinearSVC(class_weight="balanced", random_state=SEED, dual="auto",
                    max_iter=20000, C=1.0)
    return {
        "csp_lda": Pipeline([("csp", CSP(nfilter=2, metric="euclid", log=True)),
                             ("clf", LDA())]),
        "ts_svm": Pipeline([("ts", TangentSpace(metric="riemann")),
                            ("sc", StandardScaler()), ("clf", svc)]),
        "fgmdm": Pipeline([("clf", FgMDM(metric="riemann"))]),
        "logvar_svm": Pipeline([("lv", _LogVar()), ("sc", StandardScaler()),
                                ("clf", svc)]),
    }


class _LogVar:
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.log(np.maximum(np.einsum("nii->ni", X), 1e-20))

    def fit_transform(self, X, y=None):
        return self.transform(X)

    def get_params(self, deep=True):
        return {}

    def set_params(self, **kw):
        return self


# --------------------------------------------------------------------------- #
# 2b side, two channels (C3, C4) recomputed from the cached epochs
# --------------------------------------------------------------------------- #
def load_2b_2ch():
    out = {}
    for s in SUBJECTS:
        p = os.path.join(DATA, f"sub-{s}.npz")
        if not os.path.exists(p):
            continue
        d = np.load(p)
        X = d["X"][:, [0, 2], :]          # C3, C4 -- drop Cz
        out[s] = dict(cov=covs(X), y=d["y"], sess=d["sess"])
    return out


# --------------------------------------------------------------------------- #
# Gelo side
# --------------------------------------------------------------------------- #
def load_gelo():
    b, a = butter(ORDER, list(BAND), btype="band", fs=FS_G)
    pre = int(round(PAD * FS_G))
    s0 = int(round(TMIN * FS_G))
    need = int(round((TMAX + PAD) * FS_G))
    eps, ys, files, meta = [], [], [], []

    for cls, folder in ((0, "left"), (1, "right")):
        for path in sorted(glob.glob(os.path.join(GELO_ROOT, folder, "*.csv"))):
            name = os.path.basename(path)
            M = np.genfromtxt(path, delimiter=",", skip_header=1)
            M = M[~np.isnan(M[:, -1])]
            X = M[:, 1:5] * 1e6
            mk = M[:, -1]
            kept = 0
            for m in MARKS:
                idx = np.flatnonzero(mk == m)
                if idx.size == 0:
                    meta.append([folder, name, m, "MISSING"])
                    continue
                on = int(idx[0])
                j = on - 1
                while j >= 0 and mk[j] == 0:
                    j -= 1
                if (on - 1 - j) / FS_G < MIN_REST:
                    meta.append([folder, name, m, "NO_BASELINE"])
                    continue
                if on - pre < 0 or on + need > X.shape[0]:
                    meta.append([folder, name, m, "EDGE"])
                    continue
                seg = X[on - pre: on + need, [C3_COL, C4_COL]]
                seg = detrend(seg, axis=0, type="constant")
                segf = filtfilt(b, a, seg, axis=0)
                ep = segf[pre + s0: pre + s0 + NSAMP, :].T
                eps.append(ep)
                ys.append(cls)
                files.append(name)
                meta.append([folder, name, m, "OK"])
                kept += 1
            print(f"    {name:<18} {kept}/{len(MARKS)} kept")
    return (np.stack(eps), np.array(ys), np.array(files), meta)


# --------------------------------------------------------------------------- #
def file_level(y, files, pred):
    """Majority vote per file. Returns (true, voted) arrays, one per file."""
    u = np.unique(files)
    t = np.array([y[files == f][0] for f in u])
    v = np.array([int(pred[files == f].mean() >= 0.5) for f in u])
    return t, v, u


def main():
    os.makedirs(RES, exist_ok=True)
    rng = np.random.default_rng(SEED)

    # ---------------- PART A : what does losing Cz cost? ------------------- #
    print("=== PART A: 2b cross-subject LOSO with C3+C4 only ===")
    two = load_2b_2ch()
    rowsA = []
    for name in models():
        for ea in (0, 1):
            bals = []
            for held in two:
                np.random.seed(SEED)
                Xtr, ytr = [], []
                for s in two:
                    if s == held:
                        continue
                    c = two[s]["cov"]
                    if ea:
                        c = align(c, two[s]["sess"])
                    Xtr.append(c)
                    ytr.append(two[s]["y"])
                Xtr, ytr = np.concatenate(Xtr), np.concatenate(ytr)
                cte = two[held]["cov"]
                if ea:
                    cte = align(cte, two[held]["sess"])
                mdl = models()[name].fit(Xtr, ytr)
                bals.append(balanced_accuracy_score(two[held]["y"],
                                                    mdl.predict(cte)))
            rowsA.append(dict(model=name, ea=ea, mean_bal=round(np.mean(bals), 4),
                              sd=round(np.std(bals, ddof=1), 4),
                              above=int(sum(b > 0.5 for b in bals))))
            print(f"  {name:<12} EA={ea}  {np.mean(bals):.4f}  "
                  f"({sum(b > 0.5 for b in bals)}/9 above chance)")

    # ---------------- PART B : transfer to the Gelo data ------------------- #
    print("\n=== PART B: train on ALL of 2b (C3+C4), test on our recordings ===")
    print("  re-cutting epochs:")
    Xg, yg, fg, meta = load_gelo()
    print(f"\n  {len(yg)} epochs from {len(np.unique(fg))} files "
          f"(left {int((yg == 0).sum())}, right {int((yg == 1).sum())})")
    print(f"  epoch-level majority baseline {max(np.bincount(yg))/len(yg):.4f}")
    print(f"  file-level  majority baseline "
          f"{max(np.bincount([yg[fg == f][0] for f in np.unique(fg)]))/len(np.unique(fg)):.4f}")

    cg_raw = covs(Xg)
    cg_ea = align(cg_raw, fg)          # per FILE -- the domain unit on our side

    rowsB = []
    for name in models():
        for ea in (0, 1):
            np.random.seed(SEED)
            Xtr, ytr = [], []
            for s in two:
                c = two[s]["cov"]
                if ea:
                    c = align(c, two[s]["sess"])
                Xtr.append(c)
                ytr.append(two[s]["y"])
            mdl = models()[name].fit(np.concatenate(Xtr), np.concatenate(ytr))
            pred = mdl.predict(cg_ea if ea else cg_raw)

            ep_bal = balanced_accuracy_score(yg, pred)
            t, v, u = file_level(yg, fg, pred)
            f_bal = balanced_accuracy_score(t, v)
            f_acc = float((t == v).mean())

            # file-level permutation: relabel whole files, model stays fixed
            nperm_ge = 0
            for _ in range(NPERM):
                perm = rng.permutation(t)
                lut = dict(zip(u, perm))
                yp = np.array([lut[f] for f in fg])
                tp, vp, _ = file_level(yp, fg, pred)
                if balanced_accuracy_score(tp, vp) >= f_bal:
                    nperm_ge += 1
            p = (nperm_ge + 1) / (NPERM + 1)

            rowsB.append(dict(model=name, ea=ea,
                              epoch_bal=round(ep_bal, 4),
                              file_bal=round(f_bal, 4),
                              file_correct=f"{int((t == v).sum())}/{len(t)}",
                              file_acc=round(f_acc, 4),
                              perm_p=round(p, 4),
                              frac_pred_right=round(float(pred.mean()), 4)))
            print(f"  {name:<12} EA={ea}  epoch {ep_bal:.4f} | "
                  f"file {f_bal:.4f} ({int((t == v).sum())}/{len(t)}) | "
                  f"perm p={p:.4f} | says right {pred.mean():.0%}")

    with open(os.path.join(RES, "gelo_2ch_ceiling.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rowsA[0]))
        w.writeheader()
        w.writerows(rowsA)
    with open(os.path.join(RES, "gelo_transfer.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rowsB[0]))
        w.writeheader()
        w.writerows(rowsB)
    with open(os.path.join(RES, "gelo_epoch_meta.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["class", "file", "mark", "status"])
        w.writerows(meta)

    print("\nWrote results\\gelo_2ch_ceiling.csv, gelo_transfer.csv, "
          "gelo_epoch_meta.csv")


if __name__ == "__main__":
    main()
