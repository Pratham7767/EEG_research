"""LDA decoder on log band power (the Graz recipe) and the 2 s output integrator.

Sign convention (as in Leeb 2007): distance < 0 -> left, >= 0 -> right.
Saved as plain JSON (weights, bias, which features), never pickle.
"""
import json
import time
from collections import deque

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

from . import config as C


class Decoder:
    def __init__(self, bands, channel_names, weights, bias, meta=None):
        self.bands = [tuple(b) for b in bands]            # bands actually used
        self.channel_names = list(channel_names)          # e.g. ["C3", "C4"]
        self.w = np.asarray(weights, float)
        self.b = float(bias)
        self.meta = dict(meta or {})

    @property
    def channel_idx(self):
        return [C.CHANNELS.index(c) for c in self.channel_names]

    def feature_spec(self):
        """(channel indices into the raw stream, bands) for BandPower."""
        return self.channel_idx, self.bands

    def make_extractor(self):
        from .dsp import BandPower
        return BandPower(self.channel_idx, self.bands)

    def distance(self, feats):
        return np.asarray(feats, float) @ self.w + self.b

    def predict(self, feats):
        return np.where(self.distance(feats) < 0, C.LEFT, C.RIGHT)

    # ---- persistence ----
    def to_dict(self):
        return dict(kind="lda_logbp", bands=self.bands, channel_names=self.channel_names,
                    weights=self.w.tolist(), bias=self.b, meta=self.meta, fs=C.FS,
                    win_s=C.FEATURE_WIN_S, hop=C.HOP, order=C.FILTER_ORDER)

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @staticmethod
    def load(path):
        with open(path) as f:
            d = json.load(f)
        return Decoder(d["bands"], d["channel_names"], d["weights"], d["bias"], d.get("meta"))


def load_decoder(path):
    """Load either model type from its JSON file."""
    with open(path) as f:
        d = json.load(f)
    if d.get("kind") == "csp_svm_ea":
        from .svm import SvmDecoder
        return SvmDecoder.from_dict(d)
    return Decoder(d["bands"], d["channel_names"], d["weights"], d["bias"], d.get("meta"))


def fit_lda(X, y):
    """Shrinkage LDA (Ledoit-Wolf), returns (w, b) with negative = left."""
    lda = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    lda.fit(X, (np.asarray(y) == C.RIGHT).astype(int))
    return lda.coef_[0].copy(), float(lda.intercept_[0])


def build_decoder(X_full, y, feat_cols, all_bands, channel_names, meta=None):
    """X_full holds every candidate feature (band-major, channel-minor). feat_cols picks some.
    The decoder keeps only the bands needed, so the live BandPower is as small as possible."""
    nch = len(channel_names)
    bands_used = sorted({c // nch for c in feat_cols})
    cols_kept = [b * nch + k for b in bands_used for k in range(nch)]   # all channels of used bands
    w_small, b0 = fit_lda(X_full[:, feat_cols], y)
    w = np.zeros(len(cols_kept))
    for wi, c in zip(w_small, feat_cols):
        w[cols_kept.index(c)] = wi
    m = dict(meta or {})
    m.setdefault("created", time.strftime("%Y-%m-%d %H:%M:%S"))
    m["features"] = [f"{channel_names[c % nch]}_{all_bands[c // nch][0]}-{all_bands[c // nch][1]}Hz"
                     for c in feat_cols]
    return Decoder([all_bands[b] for b in bands_used], channel_names, w, b0, m)


class Integrator:
    """Mean sign of the last INTEGRATE_S of decoder outputs: -1 = fully left, +1 = fully right.
    Artifact outputs are skipped (they neither push nor pull)."""

    def __init__(self, n=int(C.INTEGRATE_S * C.FS / C.HOP)):
        self.buf = deque(maxlen=n)

    def reset(self):
        self.buf.clear()

    def push(self, d):
        self.buf.append(1.0 if d >= 0 else -1.0)
        return self.value()

    def value(self):
        return float(np.mean(self.buf)) if self.buf else 0.0
