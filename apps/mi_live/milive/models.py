"""Live models. Every model here is the same shape, which covers all the 2b models we compared:

   per band: aligned covariance A (2 x 2)  ->  features  ('csp': log diag(W' A W), 'ts': tangent space,
   'logvar': log diag(A))  ->  standardise  ->  linear decision (linear SVM or shrinkage LDA)  ->  d

Saved as plain JSON (kind 'live_linear_cov'). apps/mi_bci's SVM files (kind 'csp_svm_ea') load as the
same thing: one band 8-30 Hz, CSP, SVM.
"""
import json
from pathlib import Path

import numpy as np

from mibci import config as C
from mibci.svm import CovWindow

from . import settings as S


def unflat(f):
    f = np.asarray(f, float)
    M = np.empty(f.shape[:-1] + (2, 2))
    M[..., 0, 0], M[..., 0, 1], M[..., 1, 0], M[..., 1, 1] = f[..., 0], f[..., 1], f[..., 1], f[..., 2]
    return M


def matfun(M, f):
    w, V = np.linalg.eigh(M)
    return (V * f(np.maximum(w, 1e-12))[..., None, :]) @ np.swapaxes(V, -1, -2)


def inv_sqrt(M):
    return matfun((M + np.swapaxes(M, -1, -2)) / 2, lambda w: w ** -0.5)


def features(kind, A_by_band, W=None):
    out = []
    for b, A in enumerate(A_by_band):
        if kind == "csp":
            Wb = np.asarray(W[b])
            out.append(np.log(np.maximum(np.einsum("ij,nik,kj->nj", Wb, A, Wb), 1e-20)))
        elif kind == "logvar":
            out.append(np.log(np.maximum(np.stack([A[:, 0, 0], A[:, 1, 1]], 1), 1e-20)))
        elif kind == "ts":                       # tangent space at the identity (data are aligned)
            L = matfun(A, np.log)
            out.append(np.stack([L[:, 0, 0], np.sqrt(2) * L[:, 0, 1], L[:, 1, 1]], 1))
        else:
            raise ValueError(kind)
    return np.hstack(out)


def fit_csp(A_by_band, y, w=None):
    Ws = []
    w = np.ones(len(y)) if w is None else np.asarray(w, float)
    for A in A_by_band:
        m = [(A[y == c] * w[y == c, None, None]).sum(0) / w[y == c].sum() for c in (C.LEFT, C.RIGHT)]
        ev, V = np.linalg.eig(np.linalg.solve(m[0] + m[1], m[0]))
        Ws.append(np.real(V[:, np.argsort(-np.real(ev))]))
    return Ws


class MultiCov:
    """One mibci CovWindow per band on the same samples; rows = the flat covariances of all bands."""

    def __init__(self, channel_idx, bands, win_s=2.0):
        self.cws = [CovWindow(channel_idx, tuple(b), win_s) for b in bands]

    def process(self, x):
        res = [cw.process(x) for cw in self.cws]
        return res[0][0], np.hstack([r[1] for r in res])


class LinearCovModel:
    kind = "live_linear_cov"

    def __init__(self, bands, feature, W, mean, scale, coef, intercept, meta=None):
        self.bands = [tuple(map(float, b)) for b in bands]
        self.feature = feature
        self.W = None if W is None else [np.asarray(w, float) for w in W]
        self.mean, self.scale = np.asarray(mean, float), np.asarray(scale, float)
        self.coef, self.intercept = np.asarray(coef, float), float(intercept)
        self.meta = dict(meta or {})
        self.montage = self.meta.get("montage", C.MONTAGE)
        self.channel_idx = [C.CHANNELS.index(c) for c in C.DECODE_CHANNELS]
        self.rms_band = next((k for k, b in enumerate(self.bands) if b == (8.0, 30.0)), 0)

    @property
    def name(self):
        return self.meta.get("name", f"{self.feature} {len(self.bands)} band(s)")

    def make_extractor(self):
        return MultiCov(self.channel_idx, self.bands, self.meta.get("win_s", 2.0))

    def decide(self, A_by_band):
        f = features(self.feature, A_by_band, self.W)
        return ((f - self.mean) / self.scale) @ self.coef + self.intercept

    def to_dict(self):
        return dict(kind=self.kind, bands=self.bands, feature=self.feature,
                    W=None if self.W is None else [w.tolist() for w in self.W], mean=self.mean.tolist(),
                    scale=self.scale.tolist(), coef=self.coef.tolist(), intercept=self.intercept, meta=self.meta,
                    fs=C.FS, hop=C.HOP)

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=1, default=float))

    @staticmethod
    def from_dict(d):
        if d.get("kind") == "csp_svm_ea":                     # an apps/mi_bci SVM
            p, m = d["params"], dict(d.get("meta", {}))
            m.setdefault("montage", d.get("montage", C.MONTAGE))
            m.setdefault("name", "CSP + SVM 8-30 Hz")
            return LinearCovModel([m.get("band", (8, 30))], "csp", [p["W"]], p["mean"], p["scale"], p["coef"],
                                  p["intercept"], m)
        if d.get("kind") != LinearCovModel.kind:
            raise ValueError(f"unknown model kind {d.get('kind')}")
        return LinearCovModel(d["bands"], d["feature"], d["W"], d["mean"], d["scale"], d["coef"], d["intercept"],
                              d.get("meta"))


def load_model(path):
    return LinearCovModel.from_dict(json.loads(Path(path).read_text()))


def available_models(subject):
    """[(label, path)]: the live base model first, then mi_bci's 2b base SVM, then this subject's SVMs."""
    out = []
    best = S.LIVE_DIR / "models" / "base_2b_live.json"
    if best.exists():
        j = json.loads(best.read_text())
        out.append((f"BEST 2b model for a new person: {j['meta'].get('name')} "
                    f"({100 * j['meta'].get('unseen_accuracy', 0):.1f} % on unseen 2b people)", best))
    if subject:                                              # personal models trained in mi_live (newest first)
        mine = []
        for root in (C.DATA_DIR, S.DATA_LIVE):
            d = Path(root) / subject / "decoders_live"
            mine += list(d.glob("live_*.json")) if d.exists() else []
        for p in sorted(mine, key=lambda q: q.name, reverse=True):
            try:
                m = json.loads(p.read_text())["meta"]
            except Exception:
                continue
            sc = m.get("score")
            s = f"{100 * sc:.0f} %" if isinstance(sc, (int, float)) else "no score"
            out.append((f"YOURS {p.stem[5:]}: {m.get('name')} ({s}, {m.get('verdict')})", p))
    out.append(("mi_bci base SVM - BCI IV 2b, 9 people (CSP + SVM 8-30 Hz)", Path(S.BASE_JSON)))
    d = C.DATA_DIR / subject / "decoders" if subject else None
    if d and d.exists():
        for p in sorted(d.glob("decoder_*.json"), reverse=True):
            try:
                j = json.loads(p.read_text())
            except Exception:
                continue
            if j.get("kind") == "csp_svm_ea":
                m = j.get("meta", {})
                score = m.get("score")
                s = f"{100 * score:.0f} %" if isinstance(score, (int, float)) else "no score"
                out.append((f"{subject} SVM {p.stem[8:]} ({m.get('weighting', '?')}, {s})", p))
    return out
