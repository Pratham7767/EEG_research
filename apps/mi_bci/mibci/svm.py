"""The app's model: CSP + SVM with Euclidean Alignment (the 2b pipeline from
experiments/05_bci_iv_2b/gelo_svm_pipeline.py: CSP(2 filters, log) -> StandardScaler -> LinearSVC(balanced)),
rebuilt so it can run live and be saved as plain JSON.

Live features, every 40 ms:
  C3-A1, C4-A2 -> causal Butterworth 8-30 Hz (order 4, state kept) -> covariance of the last 2 s (2 x 2)
Model:
  EA:   C_aligned = R^-1/2 C R^-1/2, R = mean covariance of the SAME SESSION (no labels needed)
  CSP:  W from the class-mean aligned covariances; features log(diag(W' C_aligned W))
  SVM:  standardise, linear SVM -> distance (negative = left, positive = right)
The same CovWindow class computes features offline (training) and live (engine), so they are identical.
"""
import json
import time

import numpy as np
from scipy.signal import butter, sosfilt
from sklearn.svm import LinearSVC

from . import config as C

BAND = (8.0, 30.0)
WIN_S = 2.0
ORDER = 4
SVM_C = 0.1
SEED = 42


def _inv_sqrtm(M):
    w, V = np.linalg.eigh((M + M.T) / 2)
    return (V * (np.maximum(w, 1e-12) ** -0.5)) @ V.T


def flat(c):           # (..., 2, 2) -> (..., 3)
    return np.stack([c[..., 0, 0], c[..., 0, 1], c[..., 1, 1]], -1)


def unflat(f):         # (..., 3) -> (..., 2, 2)
    f = np.asarray(f, float)
    out = np.empty(f.shape[:-1] + (2, 2))
    out[..., 0, 0], out[..., 0, 1], out[..., 1, 0], out[..., 1, 1] = f[..., 0], f[..., 1], f[..., 1], f[..., 2]
    return out


class CovWindow:
    """Causal 8-30 Hz band-pass with kept state; every HOP samples, the covariance of the last WIN_S."""

    def __init__(self, channels, band=BAND, win_s=WIN_S, hop=C.HOP, order=ORDER, fs=C.FS):
        self.channels, self.hop = list(channels), hop
        self.win = int(round(win_s * fs))
        self.sos = butter(order, band, btype="bandpass", fs=fs, output="sos")
        self.zi = np.zeros((self.sos.shape[0], 2, len(self.channels)))
        self.tail = np.zeros((0, len(self.channels)))
        self.n_seen = 0
        self.n_feat = 3

    def process(self, x):
        x = np.asarray(x, float)
        if x.ndim == 1:
            x = x[None, :]
        n = len(x)
        if n == 0:
            return np.zeros(0, int), np.zeros((0, 3))
        xs = np.nan_to_num(x[:, self.channels])
        if self.n_seen == 0:
            self._offset = xs[0].copy()
        y, self.zi = sosfilt(self.sos, xs - self._offset, axis=0, zi=self.zi)
        z = np.vstack([self.tail, y])
        t0 = len(self.tail)
        idx, feats = [], []
        for j in range(n):
            i = self.n_seen + j
            if (i + 1) % self.hop == 0 and i + 1 >= self.win:
                w = z[t0 + j + 1 - self.win:t0 + j + 1]
                w = w - w.mean(0)
                c = w.T @ w / (self.win - 1)
                idx.append(i)
                feats.append((c[0, 0], c[0, 1], c[1, 1]))
        self.tail = z[-(self.win - 1):]
        self.n_seen += n
        return np.array(idx, int), (np.array(feats) if feats else np.zeros((0, 3)))


def covwindow_offline(x, channels, chunk=25, **kw):
    cw = CovWindow(channels, **kw)
    I, F = [], []
    for s in range(0, len(x), chunk):
        i, f = cw.process(x[s:s + chunk])
        I.append(i)
        F.append(f)
    return np.concatenate(I), np.vstack(F)


def reference(cov_flat):
    """Session reference for Euclidean Alignment: the plain mean covariance (no labels)."""
    return unflat(np.asarray(cov_flat).mean(0))


def align(cov_flat, R):
    P = _inv_sqrtm(R)
    return P @ unflat(cov_flat) @ P


# --------------------------------------------------------------------------------------------
def fit_params(covs_aligned, y, w=None, C_svm=SVM_C):
    """Weighted CSP + scaler + linear SVM on aligned (n, 2, 2) covariances. y in {LEFT, RIGHT}."""
    y = np.asarray(y)
    w = np.ones(len(y)) if w is None else np.asarray(w, float)
    m = []
    for c in (C.LEFT, C.RIGHT):
        k = y == c
        m.append((covs_aligned[k] * w[k, None, None]).sum(0) / w[k].sum())
    ev, V = np.linalg.eig(np.linalg.solve(m[0] + m[1], m[0]))
    W = np.real(V[:, np.argsort(-np.real(ev))])
    f = np.log(np.maximum(np.einsum("ij,nik,kj->nj", W, covs_aligned, W), 1e-20))
    mu = np.average(f, axis=0, weights=w)
    sd = np.sqrt(np.average((f - mu) ** 2, axis=0, weights=w)) + 1e-12
    svm = LinearSVC(C=C_svm, class_weight="balanced", random_state=SEED, dual="auto", max_iter=20000)
    svm.fit((f - mu) / sd, (y == C.RIGHT).astype(int), sample_weight=w)
    return dict(W=W, mean=mu, scale=sd, coef=svm.coef_[0].copy(), intercept=float(svm.intercept_[0]))


def decide(params, covs_aligned):
    W = np.asarray(params["W"])
    f = np.log(np.maximum(np.einsum("ij,nik,kj->nj", W, covs_aligned, W), 1e-20))
    return ((f - params["mean"]) / params["scale"]) @ np.asarray(params["coef"]) + params["intercept"]


class SvmDecoder:
    """Live-usable CSP+SVM+EA. Call set_reference(R) with the session reference before a run; without
    one, it uses the running mean of the covariances it has seen so far in this run."""
    kind = "csp_svm_ea"

    def __init__(self, params, meta=None, ref=None):
        self.p = {k: (np.asarray(v, float) if k != "intercept" else float(v)) for k, v in params.items()}
        self.meta = dict(meta or {})
        self.channel_names = list(C.DECODE_CHANNELS)
        self.ref = None if ref is None else np.asarray(ref, float)
        self._sum, self._n = np.zeros(3), 0

    @property
    def channel_idx(self):
        return [C.CHANNELS.index(c) for c in self.channel_names]

    def make_extractor(self):
        return CovWindow(self.channel_idx, tuple(self.meta.get("band", BAND)), self.meta.get("win_s", WIN_S))

    def set_reference(self, R):
        self.ref = None if R is None else np.asarray(R, float)
        self._sum, self._n = np.zeros(3), 0

    def distance(self, row):
        row = np.asarray(row, float)
        R = self.ref
        if R is None:                                   # running session mean
            self._sum += row
            self._n += 1
            R = unflat(self._sum / self._n)
        return float(decide(self.p, align(row[None, :], R))[0])

    def to_dict(self):
        return dict(kind=self.kind, params={k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in self.p.items()},
                    meta=self.meta, ref=None if self.ref is None else self.ref.tolist(),
                    fs=C.FS, hop=C.HOP, montage=self.meta.get("montage", C.MONTAGE))

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=float)

    @staticmethod
    def from_dict(d):
        return SvmDecoder(d["params"], d.get("meta"), d.get("ref"))


def new_meta(**kw):
    m = dict(model="CSP + SVM + Euclidean Alignment (as gelo_svm_pipeline.py)", band=list(BAND), win_s=WIN_S,
             svm_C=SVM_C, montage=C.MONTAGE, created=time.strftime("%Y-%m-%d %H:%M:%S"))
    m.update(kw)
    return m
