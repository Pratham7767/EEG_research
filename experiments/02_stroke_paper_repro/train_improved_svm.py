"""
Improved, leakage-free SVM pipelines for the acute-stroke MI dataset (Liu et al., Sci Data 2024).

Everything label-dependent (CSP filters, feature selection, SVM C, tangent-space reference)
is fitted inside the training folds only. Filtering and per-trial covariances are
label-free, so they are computed once per subject up front.

Pipelines (all per subject, stratified 10-fold CV):
  fbcsp_svm  : 6 bands 8-30 Hz -> CSP (m=2) -> MI feature selection -> scaled linear SVM, C tuned
  ts_svm     : 8-30 Hz shrinkage covariance -> Riemannian tangent space -> scaled linear SVM, C tuned
  fbts_svm   : tangent space per band (3 bands) concatenated -> scaled linear SVM, C tuned
"""
import glob
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")       # small matrices: threads only add overhead
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
from joblib import Parallel, delayed
from scipy.signal import butter, sosfiltfilt, iirnotch, filtfilt
from scipy.stats import binom
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.covariance import ledoit_wolf
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from train_fbcsp_svm import CHANNELS, FS, MARKER_CH, ROOT, load_subject

TMIN, TMAX = 0.5, 3.5                  # skip the cue-evoked first 0.5 s and the tail
PAD = 800                              # filter padding taken around the window, then dropped
FB_BANDS = [(8, 12), (12, 16), (16, 20), (20, 24), (24, 28), (26, 30)]
TS_BANDS = [(8, 13), (13, 20), (20, 30)]
C_GRID = {"svc__C": [0.001, 0.01, 0.1, 1, 10]}
SEED = 0


# ---------------------------------------------------------------- preprocessing (label-free)
def epochs(raw, bands):
    """Return {band: (trials, ch, samples)} for the TMIN-TMAX window after the MI marker."""
    stream = np.concatenate(list(raw), axis=1)
    onsets = np.flatnonzero(stream[MARKER_CH] == 2)
    b_n, a_n = iirnotch(50, 6, fs=FS)
    s0, s1 = int(TMIN * FS), int(TMAX * FS)
    segs = np.stack([stream[CHANNELS, o - PAD:o + s1 + PAD] for o in onsets])
    segs = filtfilt(b_n, a_n, segs, axis=-1)
    out = {}
    for band in bands:
        sos = butter(4, band, "band", fs=FS, output="sos")
        out[band] = sosfiltfilt(sos, segs, axis=-1)[..., PAD + s0:PAD + s1]
    return out


def covariances(x):
    """Per-trial Ledoit-Wolf shrinkage covariance, (trials, ch, ch)."""
    return np.stack([ledoit_wolf(t.T)[0] for t in x])


# ---------------------------------------------------------------- SPD helpers
def _fn(c, f):
    """Apply f to the eigenvalues of one SPD matrix or a stack of them."""
    w, v = np.linalg.eigh(c)
    return (v * f(w)[..., None, :]) @ np.swapaxes(v, -1, -2)


def riemann_mean(covs, iters=20):
    m = np.mean(covs, axis=0)
    for _ in range(iters):
        isq, sq = _fn(m, lambda w: w ** -0.5), _fn(m, np.sqrt)
        t = _fn(isq @ covs @ isq, np.log).mean(axis=0)
        m = sq @ _fn(t, np.exp) @ sq
        if np.linalg.norm(t) < 1e-8:
            break
    return m


# ---------------------------------------------------------------- transformers
class TangentSpace(BaseEstimator, TransformerMixin):
    """X: (trials, n_bands, ch, ch). Reference = Riemannian mean of the TRAINING covariances."""

    def fit(self, X, y=None):
        self.isq_ = [_fn(riemann_mean(X[:, b]), lambda w: w ** -0.5) for b in range(X.shape[1])]
        n = X.shape[-1]
        iu = np.triu_indices(n)
        self.iu_, self.coef_ = iu, np.where(iu[0] == iu[1], 1.0, np.sqrt(2))
        return self

    def transform(self, X):
        feats = []
        for b, isq in enumerate(self.isq_):
            s = _fn(isq @ X[:, b] @ isq, np.log)
            feats.append(s[:, self.iu_[0], self.iu_[1]] * self.coef_)
        return np.hstack(feats)


class FBCSP(BaseEstimator, TransformerMixin):
    """X: (trials, n_bands, ch, ch) covariances. m filter pairs per band, log-variance features."""

    def __init__(self, m=2):
        self.m = m

    def fit(self, X, y):
        self.w_ = []
        for b in range(X.shape[1]):
            c = X[:, b] / np.trace(X[:, b], axis1=1, axis2=2)[:, None, None]
            c1, c2 = c[y == 1].mean(0), c[y == 2].mean(0)
            # generalized eigenproblem c1 w = l (c1 + c2) w
            isq = _fn(c1 + c2, lambda w: w ** -0.5)
            _, u = np.linalg.eigh(isq @ c1 @ isq)
            w = u.T @ isq
            self.w_.append(np.vstack([w[:self.m], w[-self.m:]]))
        return self

    def transform(self, X):
        return np.hstack([
            np.log(np.einsum("fc,tcd,fd->tf", w, X[:, b], w)) for b, w in enumerate(self.w_)
        ])


def svm():
    return SVC(kernel="linear")


PIPELINES = {
    "fbcsp_svm": (FB_BANDS, lambda: make_pipeline(
        FBCSP(m=2),
        SelectKBest(lambda X, y: mutual_info_classif(X, y, random_state=SEED), k=8),
        StandardScaler(), svm())),
    "ts_svm": ([(8, 30)], lambda: make_pipeline(TangentSpace(), StandardScaler(), svm())),
    "fbts_svm": (TS_BANDS, lambda: make_pipeline(TangentSpace(), StandardScaler(), svm())),
}


def evaluate_subject(path):
    raw, y = load_subject(path)
    all_bands = sorted({b for bands, _ in PIPELINES.values() for b in bands})
    ep = epochs(raw, all_bands)
    cov = {b: covariances(ep[b]) for b in all_bands}
    outer = StratifiedKFold(10, shuffle=True, random_state=SEED)
    inner = StratifiedKFold(5, shuffle=True, random_state=SEED)
    res = {}
    for name, (bands, make) in PIPELINES.items():
        X = np.stack([cov[b] for b in bands], axis=1)          # (trials, n_bands, ch, ch)
        model = GridSearchCV(make(), C_GRID, cv=inner)          # C chosen on training folds only
        res[name] = cross_val_score(model, X, y, cv=outer).mean() * 100
    return res


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(ROOT, "sub-*", "*.mat")))
    names = list(PIPELINES)
    results = Parallel(n_jobs=-1, verbose=0)(delayed(evaluate_subject)(f) for f in files)
    table = []
    print("subject   " + "  ".join(f"{n:>9}" for n in names))
    for f, r in zip(files, results):
        table.append([r[n] for n in names])
        sub = os.path.basename(os.path.dirname(f))
        print(f"{sub:9} " + "  ".join(f"{r[n]:9.2f}" for n in names))

    table = np.array(table)
    # accuracy needed to beat chance at p < 0.05 with 40 trials (one-sided binomial)
    thresh = binom.ppf(0.95, 40, 0.5) / 40 * 100
    print(f"\nChance threshold (40 trials, p<0.05): {thresh:.1f} %")
    for i, n in enumerate(names):
        col = table[:, i]
        print(f"{n:9}: mean {col.mean():.2f} %  sd {col.std():.2f}  "
              f"subjects above chance {int((col > thresh).sum())}/{len(col)}")
    print("Paper reference: CSP+LDA 55.57, FBCSP+SVM 57.57, TSLDA+DGFMDRM 61.20, TWFB+DGFMDRM 72.21")
