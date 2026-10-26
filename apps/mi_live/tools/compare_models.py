"""Which BCI IV 2b model is best FOR A NEW PERSON, used live?

Setting = exactly how mi_live runs: C3 + C4 only, causal filters, 2 s covariance every 40 ms,
adaptive Euclidean Alignment (running mean, no labels) + running bias removal, decision = mean sign of
outputs 1.5-4.0 s after the cue. Each subject B0x is tested on its evaluation sessions 4 + 5 by a model
trained on the OTHER 8 subjects (all 5 sessions, each session aligned to its own mean). First 60 s of each
test session not scored; 2b artifact trials left out (as in the competition).

Models (all trained on 2b):
  csp_svm     8-30 Hz CSP + linear SVM            (mi_live's current model)
  csp_lda     8-30 Hz CSP + shrinkage LDA
  logvar_svm  8-30 Hz log power C3, C4 + SVM
  ts_svm      8-30 Hz Riemannian tangent space + SVM
  ts_lda      8-30 Hz tangent space + shrinkage LDA
  fbcsp_svm   filter bank 4-40 Hz (9 x 4 Hz bands, as the 2008 winner) CSP + SVM
  fbcsp_lda   same + shrinkage LDA (our best within-subject variant, kappa 0.601)
  fbts_svm    filter bank tangent space + SVM
Input: causal 50 Hz notch (as live). Covariances with cumulative sums; identical to the live code (checked at start).
    C:\\Python313\\python.exe tools\\compare_models.py    -> _out/compare_models.json / .txt
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, sosfilt
from scipy.stats import wilcoxon
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.svm import covwindow_offline  # noqa: E402
from mibci.trainer import artifact_flags  # noqa: E402
from milive.dsp_extra import Notch  # noqa: E402
from milive.train2b import prep  # noqa: E402

FS, HOP, WIN = 250, 10, 500
BROAD = (8.0, 30.0)
FB = [(4, 8), (8, 12), (12, 16), (16, 20), (20, 24), (24, 28), (28, 32), (32, 36), (36, 40)]
BANDS = [BROAD] + FB
OUT = Path(__file__).resolve().parents[1] / "_out" / "compare_models.json"

MODELS = {   # name: (bands, feature, classifier)
    "csp_svm": ([BROAD], "csp", "svm"), "csp_lda": ([BROAD], "csp", "lda"),
    "logvar_svm": ([BROAD], "logvar", "svm"), "ts_svm": ([BROAD], "ts", "svm"), "ts_lda": ([BROAD], "ts", "lda"),
    "fbcsp_svm": (FB, "csp", "svm"), "fbcsp_lda": (FB, "csp", "lda"), "fbts_svm": (FB, "ts", "svm"),
}


def covs(x, band):
    """x (n, 2) C3, C4. Same as CovWindow: subtract first sample, causal Butterworth-4, cov of last 500 samples
    every 10 samples."""
    sos = butter(4, band, btype="bandpass", fs=FS, output="sos")
    y = sosfilt(sos, x - x[0], axis=0)
    ends = np.arange(WIN - 1, len(y))
    ends = ends[(ends + 1) % HOP == 0]
    prod = np.stack([y[:, 0], y[:, 1], y[:, 0] ** 2, y[:, 0] * y[:, 1], y[:, 1] ** 2], 1)
    c = np.vstack([np.zeros((1, 5)), np.cumsum(prod, 0)])
    S = c[ends + 1] - c[ends + 1 - WIN]
    m0, m1 = S[:, 0] / WIN, S[:, 1] / WIN
    F = np.stack([(S[:, 2] - WIN * m0 * m0), (S[:, 3] - WIN * m0 * m1), (S[:, 4] - WIN * m1 * m1)], 1) / (WIN - 1)
    return ends, F


def unflat(F):
    M = np.empty(F.shape[:-1] + (2, 2))
    M[..., 0, 0], M[..., 0, 1], M[..., 1, 0], M[..., 1, 1] = F[..., 0], F[..., 1], F[..., 1], F[..., 2]
    return M


def fun(M, f):
    w, V = np.linalg.eigh(M)
    return (V * f(np.maximum(w, 1e-12))[..., None, :]) @ np.swapaxes(V, -1, -2)


def align_fixed(F):
    P = fun(unflat(F.mean(0)), lambda w: w ** -0.5)
    return P @ unflat(F) @ P


def align_running(F):
    cs = np.cumsum(F, 0) / np.arange(1, len(F) + 1)[:, None]
    P = fun(unflat(cs), lambda w: w ** -0.5)
    return P @ unflat(F) @ P


def sessions(sub):
    for split, ids in (("T", (1, 2, 3)), ("E", (4, 5))):
        m = loadmat(C.BCI2B_DIR / f"B{sub:02d}{split}.mat", squeeze_me=True, struct_as_record=False)
        for sid, s in zip(ids, np.atleast_1d(m["data"])):
            X = np.nan_to_num(np.asarray(s.X, float))
            yield (sid, X[:, [0, 2]], np.atleast_1d(s.trial).astype(int) - 1, np.atleast_1d(s.y).astype(int),
                   np.atleast_1d(s.artifacts).astype(bool))


class Feat:
    def __init__(self, kind):
        self.kind = kind

    def fit(self, A_by_band, y):
        if self.kind == "csp":
            self.W = []
            for A in A_by_band:
                m = [A[y == c].mean(0) for c in (C.LEFT, C.RIGHT)]
                ev, V = np.linalg.eig(np.linalg.solve(m[0] + m[1], m[0]))
                self.W.append(np.real(V[:, np.argsort(-np.real(ev))]))
        return self

    def __call__(self, A_by_band):
        out = []
        for b, A in enumerate(A_by_band):
            if self.kind == "csp":
                W = self.W[b]
                out.append(np.log(np.maximum(np.einsum("ij,nik,kj->nj", W, A, W), 1e-20)))
            elif self.kind == "logvar":
                out.append(np.log(np.maximum(np.stack([A[:, 0, 0], A[:, 1, 1]], 1), 1e-20)))
            else:   # tangent space at identity (data are aligned)
                L = fun(A, np.log)
                out.append(np.stack([L[:, 0, 0], np.sqrt(2) * L[:, 0, 1], L[:, 1, 1]], 1))
        return np.hstack(out)


def make_clf(kind):
    if kind == "svm":
        return LinearSVC(C=0.1, class_weight="balanced", dual="auto", max_iter=20000, random_state=42)
    return LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")


def main():
    t0 = time.time()
    # ---- sanity: our fast covariances == mibci CovWindow ----
    _, X, _, _, _ = next(sessions(1))
    xx = X[:20000]
    x4 = Notch([1, 2]).process(np.column_stack([np.zeros(len(xx)), xx, np.zeros(len(xx))]))
    i1, F1 = covwindow_offline(x4, [1, 2])
    i2, F2 = covs(prep(xx), BROAD)
    assert np.array_equal(i1, i2) and np.allclose(F1, F2, rtol=1e-6, atol=1e-6), "covariance mismatch"
    print("covariances identical to the live CovWindow: OK", flush=True)

    train, test = {}, {}
    for sub in range(1, 10):
        for sid, X, trial, y, art in sessions(sub):
            cues = trial + 3 * FS
            per_band = {}
            Xp = prep(X)                                     # 50 Hz notch, as live
            for band in BANDS:
                ends, F = covs(Xp, band)
                per_band[band] = (ends, F)
            ends = per_band[BROAD][0]
            # training rows: fixed EA per session, windows ending 1.5-4.0 s after cue, every 5th, clean trials
            rel_rows, labels = [], []
            for cu, c, a in zip(cues, y, art):
                if a:
                    continue
                m = np.flatnonzero((ends >= cu + 1.5 * FS) & (ends <= cu + 4.0 * FS))[::5]
                rel_rows.append(m)
                labels += [c] * len(m)
            rows = np.concatenate(rel_rows)
            train[(sub, sid)] = ({b: align_fixed(per_band[b][1])[rows] for b in BANDS}, np.array(labels))
            if sid >= 4:
                eeg4 = np.zeros((len(X), 4))
                eeg4[:, 1], eeg4[:, 2] = Xp[:, 0], Xp[:, 1]
                bad = artifact_flags(eeg4, ends)
                test[(sub, sid)] = dict(ends=ends, bad=bad, cues=list(zip(cues, y, art)),
                                        A={b: align_running(per_band[b][1]) for b in BANDS})
        print(f"features B{sub:02d} done ({time.time() - t0:.0f} s)", flush=True)

    res = {m: {} for m in MODELS}
    for sub in range(1, 10):
        tr = [train[k] for k in train if k[0] != sub]
        y_tr = np.concatenate([t[1] for t in tr])
        for name, (bands, fk, ck) in MODELS.items():
            A_tr = [np.concatenate([t[0][b] for t in tr]) for b in bands]
            feat = Feat(fk).fit(A_tr, y_tr)
            Z = feat(A_tr)
            sc = StandardScaler().fit(Z)
            clf = make_clf(ck).fit(sc.transform(Z), (y_tr == C.RIGHT).astype(int))
            k = n = 0
            for sid in (4, 5):
                T = test[(sub, sid)]
                d = clf.decision_function(sc.transform(feat([T["A"][b] for b in bands])))
                d = d - np.cumsum(d) / np.arange(1, len(d) + 1)          # running bias removal
                I, bad = T["ends"], T["bad"]
                for cu, c, a in T["cues"]:
                    if a or cu < 60 * FS:
                        continue
                    m = (I >= cu + 1.5 * FS) & (I <= cu + 4.0 * FS) & ~bad
                    if m.any():
                        pred = C.RIGHT if np.mean(np.where(d[m] >= 0, 1, -1)) >= 0 else C.LEFT
                        k += int(pred == c)
                        n += 1
            res[name][f"B{sub:02d}"] = k / n
        print(f"B{sub:02d}: " + "  ".join(f"{m} {res[m][f'B{sub:02d}']:.3f}" for m in MODELS), flush=True)

    base = np.array(list(res["csp_svm"].values()))
    summary = {}
    for m in MODELS:
        v = np.array(list(res[m].values()))
        p = float(wilcoxon(v, base).pvalue) if m != "csp_svm" and np.any(v != base) else 1.0
        summary[m] = dict(mean=float(v.mean()), better_than_current=int(np.sum(v > base + 1e-9)),
                          worse=int(np.sum(v < base - 1e-9)), wilcoxon_p_vs_current=p)
    order = sorted(summary, key=lambda m: -summary[m]["mean"])
    print("\nRANKING (mean accuracy over 9 unseen subjects):")
    for m in order:
        s = summary[m]
        print(f"  {m:11s} {100 * s['mean']:5.1f} %   vs current: better in {s['better_than_current']}/9, "
              f"worse in {s['worse']}/9, p = {s['wilcoxon_p_vs_current']:.3f}")
    OUT.write_text(json.dumps(dict(per_subject=res, summary=summary, ranking=order), indent=1))
    print(f"total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
