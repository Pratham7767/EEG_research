"""
Run every model from Liu et al. (Sci Data 2024) plus the improved SVMs on the per-subject CSV
export, under ONE honest evaluation protocol.

Fixes relative to the authors' MATLAB code (see mismatch_analysis.py for why):
  - Stratified 10-fold CV per subject, the SAME folds for every model (paired comparison).
    Every trial is predicted exactly once; no unbalanced random 24/16 splits.
  - No choice is ever made on test data:
      * TSLDA+FgMDM "fusion" = average of the two predicted probabilities
        (the paper kept whichever classifier scored higher on the test fold).
      * TWFB+FgMDM picks its frequency band AND time window by inner 5-fold CV on the
        training fold (the paper kept the max test accuracy over 8 bands).
      * SVM C and selected features are tuned inside the training fold.
  - Zero-phase filtering with padding, per-trial DC removal, shrinkage covariances.
  - Data read from eeg_stroke/csv (raw signals); the MI onset comes from events.csv, which also
    handles the 18 "window_shifted" trials (warm-up padding is taken from the continuous stream).

Output: results/per_subject_accuracy.csv, results/summary.csv, results/confusion_matrices.csv
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from pyriemann.classification import FgMDM
from pyriemann.estimation import Covariances
from pyriemann.tangentspace import TangentSpace as RTangentSpace
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt
from sklearn.base import clone
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.metrics import cohen_kappa_score, confusion_matrix
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from train_improved_svm import FBCSP, TangentSpace as MultiBandTS

CSV = r"D:\trainsvm\data\stroke_liu2024\csv"
OUT = r"D:\trainsvm\experiments\02_stroke_paper_repro\results"
FS, N_SAMP, PAD = 500, 4000, 750
EEG = ["Fp1", "Fp2", "Fz", "F3", "F4", "F7", "F8", "FCz", "FC3", "FC4", "FT7", "FT8", "Cz",
       "C3", "C4", "T3", "T4", "CP3", "CP4", "TP7", "TP8", "Pz", "P3", "P4", "T5", "T6", "Oz",
       "O1", "O2"]                                      # 29 channels: CPz ref, EOG, marker dropped
SEED = 0
C_GRID = {"svc__C": [0.001, 0.01, 0.1, 1, 10]}

FULL = (0.0, 4.0)
CORE = (0.5, 3.5)
PAPER_FB = [(10, 13), (13, 16), (16, 19), (19, 22), (22, 25)]            # FBCSP_SVM.m
WIDE_FB = [(8, 12), (12, 16), (16, 20), (20, 24), (24, 28), (26, 30)]
TS_FB = [(8, 13), (13, 20), (20, 30)]
TWFB_BANDS = [(8, 12), (8, 20), (8, 30), (12, 20), (15, 20), (15, 30), (20, 30), (8, 15)]
TWFB_WINDOWS = [(0, 4), (0, 2), (1, 3), (2, 4)]

PAPER = {"csp_lda": 55.57, "fbcsp_svm_paper": 57.57, "tslda_fgmdm_fusion": 61.20,
         "twfb_fgmdm_nested": 72.21}


# ------------------------------------------------------------------ data
class Subject:
    """Filtered epochs and shrinkage covariances, built lazily and cached per (band, window)."""

    def __init__(self, sub):
        raw = pd.read_csv(os.path.join(CSV, sub, f"{sub}_raw.csv"), engine="pyarrow",
                          usecols=EEG)[EEG].to_numpy().T                 # (29, 160000)
        ev = pd.read_csv(os.path.join(CSV, sub, f"{sub}_events.csv"))
        self.y = ev["label"].to_numpy()
        onsets = (ev["trial"].to_numpy() - 1) * N_SAMP + ev["mi_onset_sample"].to_numpy()
        assert onsets[0] >= PAD and onsets[-1] + 4 * FS + PAD <= raw.shape[1]
        segs = np.stack([raw[:, o - PAD:o + 4 * FS + PAD] for o in onsets])
        segs -= segs.mean(axis=-1, keepdims=True)                         # DC offsets ~10,000 uV
        b, a = iirnotch(50, 6, fs=FS)
        self.segs = filtfilt(b, a, segs, axis=-1)
        self._band, self._cov = {}, {}

    def band(self, band):
        if band not in self._band:
            sos = butter(4, band, "band", fs=FS, output="sos")
            self._band[band] = sosfiltfilt(sos, self.segs, axis=-1)[..., PAD:PAD + 4 * FS]
        return self._band[band]

    def cov(self, band, win):
        key = (band, win)
        if key not in self._cov:
            x = self.band(band)[..., int(win[0] * FS):int(win[1] * FS)]
            self._cov[key] = Covariances("lwf").fit_transform(x)
        return self._cov[key]

    def stack(self, bands, win):
        return np.stack([self.cov(b, win) for b in bands], axis=1)     # (trials, bands, ch, ch)


# ------------------------------------------------------------------ models
# each model: (S, train_idx, test_idx) -> predicted labels for the test trials
def _fit_predict(est, X, y, tr, te):
    return clone(est).fit(X[tr], y[tr]).predict(X[te])


def _tuned_svm(steps):
    inner = StratifiedKFold(5, shuffle=True, random_state=SEED)
    return GridSearchCV(make_pipeline(*steps, StandardScaler(), SVC(kernel="linear")),
                        C_GRID, cv=inner)


def csp_lda(S, tr, te):
    """CSP_LDA.m: 8-30 Hz, 0-4 s, 2 CSP pairs, LDA."""
    est = make_pipeline(FBCSP(m=2), LinearDiscriminantAnalysis())
    return _fit_predict(est, S.stack([(8, 30)], FULL), S.y, tr, te)


def fbcsp_svm_paper(S, tr, te):
    """FBCSP_SVM.m settings: 5 bands 10-25 Hz, 2 pairs each, linear SVM C=1, no scaling."""
    est = make_pipeline(FBCSP(m=2), SVC(kernel="linear", C=1))
    return _fit_predict(est, S.stack(PAPER_FB, FULL), S.y, tr, te)


def fbcsp_svm_tuned(S, tr, te):
    """6 bands 8-30 Hz, 0.5-3.5 s, best 8 CSP features by mutual information, tuned SVM."""
    sel = SelectKBest(lambda X, y: mutual_info_classif(X, y, random_state=SEED), k=8)
    return _fit_predict(_tuned_svm([FBCSP(m=2), sel]), S.stack(WIDE_FB, CORE), S.y, tr, te)


def ts_svm(S, tr, te):
    """Riemannian tangent space, 8-30 Hz, 0.5-3.5 s, tuned linear SVM."""
    return _fit_predict(_tuned_svm([RTangentSpace(metric="riemann")]),
                        S.cov((8, 30), CORE), S.y, tr, te)


def fbts_svm(S, tr, te):
    """Tangent space on 3 bands (8-13, 13-20, 20-30 Hz), 0.5-3.5 s, tuned linear SVM."""
    return _fit_predict(_tuned_svm([MultiBandTS()]), S.stack(TS_FB, CORE), S.y, tr, te)


def _tslda():
    return make_pipeline(RTangentSpace(metric="riemann"),
                         LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))


def tslda(S, tr, te):
    """TSLDA part of TSLDA_DGFMDM.m: 8-30 Hz, 0-4 s."""
    return _fit_predict(_tslda(), S.cov((8, 30), FULL), S.y, tr, te)


def fgmdm(S, tr, te):
    """DGFMDRM part of TSLDA_DGFMDM.m (Fisher geodesic filtering + MDM): 8-30 Hz, 0-4 s."""
    return _fit_predict(FgMDM(metric="riemann"), S.cov((8, 30), FULL), S.y, tr, te)


def tslda_fgmdm_fusion(S, tr, te):
    """Decision fusion done properly: average the two models' class probabilities."""
    X, y = S.cov((8, 30), FULL), S.y
    p = sum(clone(m).fit(X[tr], y[tr]).predict_proba(X[te]) for m in (_tslda(), FgMDM()))
    return np.unique(y[tr])[p.argmax(axis=1)]


def twfb_fgmdm_nested(S, tr, te):
    """TWFB_DGFMDM.m done properly: band x window chosen by inner CV on the training fold."""
    inner = StratifiedKFold(5, shuffle=True, random_state=SEED)
    best, best_acc = None, -1
    for band in TWFB_BANDS:
        for win in TWFB_WINDOWS:
            X = S.cov(band, win)[tr]
            acc = np.mean([(FgMDM().fit(X[a], S.y[tr][a]).predict(X[b]) == S.y[tr][b]).mean()
                           for a, b in inner.split(X, S.y[tr])])
            if acc > best_acc:
                best, best_acc = (band, win), acc
    return _fit_predict(FgMDM(), S.cov(*best), S.y, tr, te)


MODELS = {f.__name__: f for f in (csp_lda, fbcsp_svm_paper, fbcsp_svm_tuned, ts_svm, fbts_svm,
                                  tslda, fgmdm, tslda_fgmdm_fusion, twfb_fgmdm_nested)}


# ------------------------------------------------------------------ evaluation
def evaluate(sub):
    S = Subject(sub)
    pred = {m: np.zeros_like(S.y) for m in MODELS}
    for tr, te in StratifiedKFold(10, shuffle=True, random_state=SEED).split(S.y, S.y):
        for name, model in MODELS.items():
            pred[name][te] = model(S, tr, te)
    return sub, S.y, pred


if __name__ == "__main__":
    import time
    t0 = time.time()
    subs = sorted(d for d in os.listdir(CSV) if d.startswith("sub-"))
    results = Parallel(n_jobs=-1, verbose=5)(delayed(evaluate)(s) for s in subs)
    os.makedirs(OUT, exist_ok=True)

    rows, cms = [], []
    for sub, y, pred in results:
        rows.append({"subject": sub, **{m: (p == y).mean() * 100 for m, p in pred.items()}})
    per_sub = pd.DataFrame(rows)
    per_sub.to_csv(os.path.join(OUT, "per_subject_accuracy.csv"), index=False, float_format="%.2f")

    y_all = np.concatenate([r[1] for r in results])
    summary = []
    for m in MODELS:
        p_all = np.concatenate([r[2][m] for r in results])
        (ll, lr), (rl, rr) = confusion_matrix(y_all, p_all, labels=[1, 2])
        cms.append({"model": m, "true_left_pred_left": ll, "true_left_pred_right": lr,
                    "true_right_pred_left": rl, "true_right_pred_right": rr})
        kappas = [cohen_kappa_score(r[1], r[2][m]) for r in results]
        summary.append({
            "model": m, "mean_acc": per_sub[m].mean(), "sd_acc": per_sub[m].std(),
            "median_acc": per_sub[m].median(), "mean_kappa": np.mean(kappas),
            "subjects_above_chance": int((per_sub[m] >= 65).sum()),   # >=26/40, binomial p<0.05
            "paper_acc": PAPER.get(m, np.nan),
        })
    summary = pd.DataFrame(summary)
    summary.to_csv(os.path.join(OUT, "summary.csv"), index=False, float_format="%.3f")
    pd.DataFrame(cms).to_csv(os.path.join(OUT, "confusion_matrices.csv"), index=False)

    pd.set_option("display.width", 200)
    print(summary.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print(f"\nChance level 50 %; per subject, >= 65 % (26/40) beats chance at p < 0.05.")
    print(f"By chance alone, ~2 of 50 subjects would pass. Elapsed {time.time() - t0:.0f} s")
