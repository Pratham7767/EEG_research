"""Train any live model on BCI IV 2b (C3, C4), the same way tools/compare_models.py did.

Training rows: per 2b session, covariances of 2 s windows ending 1.5-4.0 s after the cue (every 5th output,
0.2 s apart), clean trials only (2b artifact flag), each session aligned to its own mean covariance.
Classifier input = the model's features, standardised; label 1 = right.
Rows are cached per subject in _out/train2b_cache/B0x.npz (built once from the 2b .mat files).
"""
import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, sosfilt
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from mibci import config as C

from . import settings as S
from .dsp_extra import Notch
from .models import LinearCovModel, features, fit_csp, inv_sqrt, unflat

FS, HOP, WIN = 250, 10, 500
BROAD = (8.0, 30.0)
FB = [(4.0, 8.0), (8.0, 12.0), (12.0, 16.0), (16.0, 20.0), (20.0, 24.0), (24.0, 28.0), (28.0, 32.0),
      (32.0, 36.0), (36.0, 40.0)]
ALL_BANDS = [BROAD] + FB
CACHE = S.OUT_DIR / "train2b_cache_notch"

SPECS = {
    "csp_svm": dict(bands=[BROAD], feature="csp", clf="svm", name="CSP + SVM 8-30 Hz"),
    "csp_lda": dict(bands=[BROAD], feature="csp", clf="lda", name="CSP + LDA 8-30 Hz"),
    "logvar_svm": dict(bands=[BROAD], feature="logvar", clf="svm", name="log power + SVM 8-30 Hz"),
    "ts_svm": dict(bands=[BROAD], feature="ts", clf="svm", name="tangent space + SVM 8-30 Hz"),
    "ts_lda": dict(bands=[BROAD], feature="ts", clf="lda", name="tangent space + LDA 8-30 Hz"),
    "fbcsp_svm": dict(bands=FB, feature="csp", clf="svm", name="filter-bank CSP (9 bands 4-40 Hz) + SVM"),
    "fbcsp_lda": dict(bands=FB, feature="csp", clf="lda", name="filter-bank CSP (9 bands 4-40 Hz) + LDA"),
    "fbts_svm": dict(bands=FB, feature="ts", clf="svm", name="filter-bank tangent space + SVM"),
}


def prep(x):
    """x (n, 2) C3, C4 -> causal 50 Hz notch, exactly as live (milive.dsp_extra.Notch)."""
    return Notch([0, 1]).process(np.asarray(x, float))


def covs(x, band):
    """x = prep()ed (n, 2). Same numbers as the live Notch + mibci.svm.CovWindow (tests/test_live.py),
    computed in one go."""
    sos = butter(4, band, btype="bandpass", fs=FS, output="sos")
    y = sosfilt(sos, x - x[0], axis=0)
    ends = np.arange(WIN - 1, len(y))
    ends = ends[(ends + 1) % HOP == 0]
    prod = np.stack([y[:, 0], y[:, 1], y[:, 0] ** 2, y[:, 0] * y[:, 1], y[:, 1] ** 2], 1)
    c = np.vstack([np.zeros((1, 5)), np.cumsum(prod, 0)])
    Sm = c[ends + 1] - c[ends + 1 - WIN]
    m0, m1 = Sm[:, 0] / WIN, Sm[:, 1] / WIN
    F = np.stack([Sm[:, 2] - WIN * m0 * m0, Sm[:, 3] - WIN * m0 * m1, Sm[:, 4] - WIN * m1 * m1], 1) / (WIN - 1)
    return ends, F


def sessions(sub):
    for split, ids in (("T", (1, 2, 3)), ("E", (4, 5))):
        m = loadmat(C.BCI2B_DIR / f"B{sub:02d}{split}.mat", squeeze_me=True, struct_as_record=False)
        for sid, s in zip(ids, np.atleast_1d(m["data"])):
            X = np.nan_to_num(np.asarray(s.X, float))
            yield (sid, X[:, [0, 2]], np.atleast_1d(s.trial).astype(int) - 1, np.atleast_1d(s.y).astype(int),
                   np.atleast_1d(s.artifacts).astype(bool))


def subject_rows(sub):
    """{band: aligned rows (n, 2, 2)}, labels — all 5 sessions of one subject. Cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"B{sub:02d}.npz"
    if f.exists():
        z = np.load(f)
        return {b: z[f"A{k}"] for k, b in enumerate(ALL_BANDS)}, z["y"]
    if not (C.BCI2B_DIR / f"B{sub:02d}T.mat").exists():
        raise FileNotFoundError(f"BCI IV 2b data not found in {C.BCI2B_DIR}")
    A = {b: [] for b in ALL_BANDS}
    Y = []
    for sid, X, trial, y, art in sessions(sub):
        cues = trial + 3 * FS                      # 2b: cue = trial start + 3 s
        Xp = prep(X)
        per = {b: covs(Xp, b) for b in ALL_BANDS}
        ends = per[BROAD][0]
        rows, lab = [], []
        for cu, c, a in zip(cues, y, art):
            if a:
                continue
            m = np.flatnonzero((ends >= cu + 1.5 * FS) & (ends <= cu + 4.0 * FS))[::5]
            rows.append(m)
            lab += [c] * len(m)
        rows = np.concatenate(rows)
        for b in ALL_BANDS:
            F = per[b][1]
            P = inv_sqrt(unflat(F.mean(0)))         # this session's alignment (no labels)
            A[b].append(P @ unflat(F[rows]) @ P)
        Y.append(np.array(lab))
    A = {b: np.concatenate(v) for b, v in A.items()}
    Y = np.concatenate(Y)
    np.savez_compressed(f, y=Y, **{f"A{k}": A[b] for k, b in enumerate(ALL_BANDS)})
    return A, Y


def train(spec_name, subjects=range(1, 10)):
    spec = SPECS[spec_name]
    data = [subject_rows(s) for s in subjects]
    y = np.concatenate([d[1] for d in data])
    A = [np.concatenate([d[0][b] for d in data]) for b in spec["bands"]]
    W = fit_csp(A, y) if spec["feature"] == "csp" else None
    Z = features(spec["feature"], A, W)
    sc = StandardScaler().fit(Z)
    yy = (y == C.RIGHT).astype(int)
    if spec["clf"] == "svm":
        clf = LinearSVC(C=0.1, class_weight="balanced", dual="auto", max_iter=20000, random_state=42)
    else:
        clf = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    clf.fit(sc.transform(Z), yy)
    meta = dict(name=spec["name"], spec=spec_name, trained_on="BCI IV 2b subjects " + ",".join(map(str, subjects)),
                montage=C.MONTAGE, win_s=2.0, train_win=[1.5, 4.0], eval_win=list(S.EVAL_WIN), n_rows=int(len(y)))
    return LinearCovModel(spec["bands"], spec["feature"], W, sc.mean_, sc.scale_, clf.coef_[0], clf.intercept_[0], meta)
