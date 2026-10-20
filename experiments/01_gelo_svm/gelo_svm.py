r"""
Left vs right motor imagery with an SVM on the Gelo BCI headband data (4 channels, 250 Hz).

Reads gelo_bci\output\left.xlsx and right.xlsx (made by gelo_extract_to_excel.py).

Pipeline
  1. Each iteration (mark 1-5) is filtered on its own: 50 Hz notch + 1-40 Hz Butterworth
     (zero phase). Iterations are capped at the first 40 s (one right iteration lasts 148 s).
  2. Cut into 2 s windows with 1 s step. Every window inherits its iteration's label.
  3. Two SVMs, hyper-parameters tuned in an inner CV on training data only
     (linear / RBF kernel, C, gamma; class_weight='balanced' since right has 2x the data):
       svm_bandpower : log + relative power per channel in 4-8, 8-13, 13-20, 20-30 Hz
       svm_tangent   : Riemannian tangent space of the 8-30 Hz 4x4 covariance
  4. Validation. Windows from one iteration never land in both train and test.
       A  by_iteration : 5-fold stratified, grouped by iteration
       B  by_file      : leave one recording file out (the model never sees the test recording)
       C  baseline     : same as A but on the mark 6/7 blocks recorded before the task.
                         Nobody imagines left/right there, so accuracy above 50 % means the
                         SVM recognizes the recording session, not the imagery.
  Scores: balanced accuracy over windows, and over iterations (majority vote of its windows).
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from pyriemann.estimation import Covariances
from pyriemann.tangentspace import TangentSpace
from scipy.signal import butter, iirnotch, filtfilt, sosfiltfilt, welch
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import GridSearchCV, LeaveOneGroupOut, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

DIR = r"D:\trainsvm\experiments\01_gelo_svm\output"
FS, WIN, STEP, MAX_S = 250, 500, 250, 40
CH = ["ch1", "ch2", "ch3", "ch4"]
BANDS = [(4, 8), (8, 13), (13, 20), (20, 30)]
SEED = 0
GRID = [{"svc__kernel": ["linear"], "svc__C": [0.01, 0.1, 1, 10]},
        {"svc__kernel": ["rbf"], "svc__C": [0.1, 1, 10, 100], "svc__gamma": ["scale", 0.01, 0.1]}]


# ------------------------------------------------------------------ data
def preprocess(x):
    """x: (4, n) microvolts -> notch + 1-40 Hz, and the 8-30 Hz version for covariances."""
    b, a = iirnotch(50, 30, fs=FS)
    x = filtfilt(b, a, x - x.mean(axis=1, keepdims=True), axis=1)
    broad = sosfiltfilt(butter(4, [1, 40], "band", fs=FS, output="sos"), x, axis=1)
    mu_beta = sosfiltfilt(butter(4, [8, 30], "band", fs=FS, output="sos"), x, axis=1)
    return broad, mu_beta


def windows(x):
    starts = range(0, x.shape[1] - WIN + 1, STEP)
    return np.stack([x[:, s:s + WIN] for s in starts])


def build(blocks):
    """blocks: iterable of (label, group, file, (4, n) array) -> window-level arrays."""
    Xb, Xm, y, g, f = [], [], [], [], []
    for label, group, fname, x in blocks:
        broad, mb = preprocess(x[:, :MAX_S * FS])
        wb, wm = windows(broad), windows(mb)
        Xb.append(wb)
        Xm.append(wm)
        y += [label] * len(wb)
        g += [group] * len(wb)
        f += [fname] * len(wb)
    return np.concatenate(Xb), np.concatenate(Xm), np.array(y), np.array(g), np.array(f)


def load_task():
    blocks = []
    for cls in ("left", "right"):
        d = pd.read_excel(os.path.join(DIR, f"{cls}.xlsx"), sheet_name="data")
        for it, part in d.groupby("iteration", sort=False):
            blocks.append((int(cls == "right"), it, part["file"].iat[0], part[CH].to_numpy().T))
    return build(blocks)


def load_baseline():
    d = pd.read_csv(os.path.join(DIR, "baseline.csv"))
    return build((int(lab == "right"), blk, part["file"].iat[0], part[CH].to_numpy().T)
                 for (lab, blk), part in d.groupby(["label", "block"], sort=False))


# ------------------------------------------------------------------ features
class BandPower(BaseEstimator, TransformerMixin):
    """(n, 4, samples) -> log band power and relative band power per channel (32 features)."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        fr, p = welch(X, FS, nperseg=FS, axis=-1)
        bp = np.stack([p[..., (fr >= lo) & (fr < hi)].mean(-1) for lo, hi in BANDS], -1)
        rel = bp / bp.sum(-1, keepdims=True)
        return np.concatenate([np.log(bp).reshape(len(X), -1), rel.reshape(len(X), -1)], 1)


class C3C4Power(BaseEstimator, TransformerMixin):
    """ch2 = C3, ch3 = C4 only: log power in mu/beta sub-bands per channel + C3/C4 log ratio."""
    bands = [(8, 10), (10, 13), (13, 20), (20, 30)]

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        fr, p = welch(X[:, 1:3], FS, nperseg=FS, axis=-1)
        bp = np.log(np.stack([p[..., (fr >= lo) & (fr < hi)].mean(-1) for lo, hi in self.bands], -1))
        return np.concatenate([bp[:, 0], bp[:, 1], bp[:, 0] - bp[:, 1]], 1)   # 12 features


MODELS = {
    "svm_c3c4": lambda: make_pipeline(C3C4Power(), StandardScaler(), SVC(class_weight="balanced")),
    "svm_bandpower": lambda: make_pipeline(BandPower(), StandardScaler(),
                                           SVC(class_weight="balanced")),
    "svm_tangent": lambda: make_pipeline(Covariances("oas"), TangentSpace(), StandardScaler(),
                                         SVC(class_weight="balanced")),
}
INPUT = {"svm_c3c4": 0, "svm_bandpower": 0, "svm_tangent": 1}     # which filtered version each model uses


# ------------------------------------------------------------------ evaluation
def run_fold(name, X, y, g, tr, te, inner_groups):
    inner = StratifiedGroupKFold(3, shuffle=True, random_state=SEED)
    gs = GridSearchCV(MODELS[name](), GRID, cv=inner, scoring="balanced_accuracy")
    gs.fit(X[tr], y[tr], groups=inner_groups[tr])
    return te, gs.predict(X[te]), gs.best_params_


def evaluate(name, data, scheme):
    Xb, Xm, y, g, f = data
    X = (Xb, Xm)[INPUT[name]]
    if scheme == "by_file":
        outer, groups, inner_groups = LeaveOneGroupOut(), f, f
    else:
        outer, groups, inner_groups = StratifiedGroupKFold(5, shuffle=True, random_state=SEED), g, g
    folds = Parallel(n_jobs=-1)(delayed(run_fold)(name, X, y, g, tr, te, inner_groups)
                                for tr, te in outer.split(X, y, groups))
    pred = np.empty_like(y)
    for te, p, _ in folds:
        pred[te] = p
    per_it = (pd.DataFrame({"iteration": g, "file": f, "true": y, "pred": pred})
              .groupby("iteration", sort=False)
              .agg(file=("file", "first"), true=("true", "first"),
                   frac_right=("pred", "mean"), windows=("pred", "size")))
    per_it["pred"] = (per_it["frac_right"] > 0.5).astype(int)
    return {
        "model": name, "validation": scheme,
        "window_bal_acc": 100 * balanced_accuracy_score(y, pred),
        "iteration_bal_acc": 100 * balanced_accuracy_score(per_it["true"], per_it["pred"]),
        "iterations_correct": f"{(per_it['true'] == per_it['pred']).sum()}/{len(per_it)}",
        "chosen_params": "; ".join(sorted({str(p) for _, _, p in folds})),
    }, per_it.assign(model=name, validation=scheme)


if __name__ == "__main__":
    import time
    t0 = time.time()
    task, base = load_task(), load_baseline()
    print(f"task windows: {len(task[2])} (left {np.sum(task[2] == 0)}, right {np.sum(task[2] == 1)}), "
          f"iterations {len(set(task[3]))}; baseline windows {len(base[2])}; load {time.time() - t0:.0f} s")

    results, preds = [], []
    for scheme, data in (("by_iteration", task), ("by_file", task), ("baseline_control", base)):
        for name in MODELS:
            r, p = evaluate(name, data, scheme)
            results.append(r)
            preds.append(p)
            print(f"{scheme:17} {name:14} window {r['window_bal_acc']:5.1f} %   "
                  f"iteration {r['iteration_bal_acc']:5.1f} % ({r['iterations_correct']})", flush=True)

    res = pd.DataFrame(results)
    res.to_csv(os.path.join(DIR, "svm_results.csv"), index=False, float_format="%.2f")
    pd.concat(preds).reset_index().to_csv(os.path.join(DIR, "svm_iteration_predictions.csv"),
                                          index=False, float_format="%.3f")
    print(f"\nChance = 50 % balanced accuracy. Elapsed {time.time() - t0:.0f} s")


def permutation_test(name="svm_tangent", n_perm=100):
    """File-level null for the by_file score: shuffle which recordings are called left/right
    (keeping 5 left / 10 right files) and rerun the whole nested procedure."""
    Xb, Xm, y, g, f = load_task()
    files = np.unique(f)
    file_label = {fn: y[f == fn][0] for fn in files}
    rng = np.random.default_rng(SEED)
    null = []
    for i in range(n_perm):
        perm = dict(zip(files, rng.permutation([file_label[fn] for fn in files])))
        y_perm = np.array([perm[fn] for fn in f])
        null.append(evaluate(name, (Xb, Xm, y_perm, g, f), "by_file")[0]["window_bal_acc"])
        print(f"perm {i + 1}/{n_perm}: {null[-1]:.1f}", flush=True)
    pd.Series(null, name="window_bal_acc").to_csv(os.path.join(DIR, f"permutation_{name}.csv"),
                                                  index=False)
    return np.array(null)
