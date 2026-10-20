"""
s02_run_models.py  -  7 models x {EA off, EA on} x 2 protocols on BCI IV 2b.

Everything operates on the per-trial 3x3 covariance matrices cached by s01.
That is not a shortcut: CSP, tangent space and MDM are all functions of the
covariance alone, and log-variance is its diagonal, so one representation
serves every model and the whole grid runs in minutes.

PROTOCOLS
  P1  within-subject, cross-session : train sessions 1-3, test sessions 4-5.
      The standard 2b protocol, so the numbers are comparable to the
      literature.
  P2  cross-subject, leave-one-subject-out : train on 8 subjects, test on the
      9th. The structural analogue of "train on a public dataset, test on a new
      person", which is what this project actually needs.

HONESTY RULES (carried over from stroke_paper\\run_all_models.py)
  * every hyperparameter is chosen by an inner GroupKFold on TRAINING data
    only, grouped so that no session (P1) or subject (P2) straddles a split;
  * CSP, tangent-space projection and feature selection are all INSIDE the
    pipeline, so they are re-fitted in every inner fold and never see test
    data;
  * Euclidean Alignment is unsupervised (it uses no labels), so applying it to
    a test session is legitimate - that is the entire point of it;
  * the RNG is reseeded at the start of every configuration, so results do not
    depend on the order configurations are run in;
  * balanced accuracy and kappa are reported next to plain accuracy, always.

Run:  C:\\Python313\\python.exe s02_run_models.py
"""

import csv
import os
import sys
import time
import warnings

import numpy as np
from joblib import Parallel, delayed
from pyriemann.classification import FgMDM
from pyriemann.spatialfilters import CSP
from pyriemann.tangentspace import TangentSpace
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RES = os.path.join(HERE, "results")
SUBJECTS = [f"B{i:02d}" for i in range(1, 10)]
SEED = 42
CGRID = [0.01, 0.1, 1.0, 10.0]


# --------------------------------------------------------------------------- #
# Euclidean Alignment  (He & Wu 2018)
# --------------------------------------------------------------------------- #
def _invsqrtm(M):
    w, V = np.linalg.eigh(M)
    w = np.maximum(w, 1e-12)
    return (V * (w ** -0.5)) @ V.T


def euclidean_align(cov, sess):
    """
    Whiten each SESSION by its own reference covariance.

    cov  : (nband, ntrials, c, c)
    sess : (ntrials,) session id -- the domain unit, because what differs
           between sessions is electrode contact, impedance and day.

    R = mean of that session's trial covariances; C -> R^-1/2 C R^-1/2.
    Unsupervised: no labels are used, so this may be applied to the test
    session without leaking anything.
    """
    out = np.empty_like(cov)
    for b in range(cov.shape[0]):
        for s in np.unique(sess):
            m = sess == s
            P = _invsqrtm(cov[b, m].mean(axis=0))
            out[b, m] = np.einsum("ij,njk,kl->nil", P, cov[b, m], P)
    return out


# --------------------------------------------------------------------------- #
# transformers
# --------------------------------------------------------------------------- #
class LogVar(BaseEstimator, TransformerMixin):
    """log of the covariance diagonal = log band power per channel."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        d = np.einsum("nii->ni", X)
        return np.log(np.maximum(d, 1e-20))


class FBCSP(BaseEstimator, TransformerMixin):
    """
    Filter-bank CSP on stacked per-band covariances.

    X : (ntrials, nband, c, c).  One CSP per band, log-variance features
    concatenated, then the k most informative kept by mutual information.
    Both the CSP filters and the selection are fitted on training data only.
    """

    def __init__(self, nfilter=2, k=8):
        self.nfilter = nfilter
        self.k = k

    def fit(self, X, y):
        self.csps_ = []
        feats = []
        for b in range(X.shape[1]):
            c = CSP(nfilter=self.nfilter, metric="euclid", log=True)
            feats.append(c.fit_transform(X[:, b], y))
            self.csps_.append(c)
        F = np.concatenate(feats, axis=1)
        k = min(self.k, F.shape[1])
        self.sel_ = SelectKBest(
            lambda a, b_: mutual_info_classif(a, b_, random_state=SEED), k=k
        ).fit(F, y)
        return self

    def transform(self, X):
        F = np.concatenate(
            [c.transform(X[:, b]) for b, c in enumerate(self.csps_)], axis=1
        )
        return self.sel_.transform(F)


# --------------------------------------------------------------------------- #
# models.  "main" takes the 8-30 Hz covariance, "bank" the 7-band stack.
# --------------------------------------------------------------------------- #
def build(name):
    # liblinear, not libsvm: the cross-subject folds train on ~5,800 trials and
    # libsvm's quadratic scaling makes the grid search take hours there for no
    # gain. Both fit a linear decision boundary; LinearSVC uses squared hinge.
    svc = LinearSVC(class_weight="balanced", random_state=SEED,
                    dual="auto", max_iter=20000)
    if name == "csp_lda":
        return "main", Pipeline([("csp", CSP(nfilter=2, metric="euclid", log=True)),
                                 ("clf", LDA())]), {}
    if name == "csp_svm":
        return "main", Pipeline([("csp", CSP(nfilter=2, metric="euclid", log=True)),
                                 ("sc", StandardScaler()), ("clf", svc)]), \
            {"clf__C": CGRID}
    if name == "fbcsp_svm":
        return "bank", Pipeline([("fb", FBCSP(nfilter=2)), ("sc", StandardScaler()),
                                 ("clf", svc)]), \
            {"fb__k": [4, 8, 14], "clf__C": CGRID}
    if name == "ts_svm":
        return "main", Pipeline([("ts", TangentSpace(metric="riemann")),
                                 ("sc", StandardScaler()), ("clf", svc)]), \
            {"clf__C": CGRID}
    if name == "tslda":
        return "main", Pipeline([("ts", TangentSpace(metric="riemann")),
                                 ("clf", LDA(solver="lsqr", shrinkage="auto"))]), {}
    if name == "fgmdm":
        return "main", Pipeline([("clf", FgMDM(metric="riemann"))]), {}
    if name == "logvar_svm":
        return "main", Pipeline([("lv", LogVar()), ("sc", StandardScaler()),
                                 ("clf", svc)]), {"clf__C": CGRID}
    raise ValueError(name)


MODELS = ["csp_lda", "csp_svm", "fbcsp_svm", "ts_svm", "tslda", "fgmdm",
          "logvar_svm"]


# --------------------------------------------------------------------------- #
def load_all():
    subs = {}
    for s in SUBJECTS:
        p = os.path.join(DATA, f"sub-{s}.npz")
        if not os.path.exists(p):
            print(f"  missing {p}, skipping {s}")
            continue
        d = np.load(p)
        subs[s] = dict(cov=d["cov"], y=d["y"], sess=d["sess"], art=d["art"])
    return subs


def fit_eval(Xtr, ytr, gtr, Xte, yte, model, grid, nsplit):
    np.random.seed(SEED)
    if grid:
        nsplit = max(2, min(nsplit, len(np.unique(gtr))))
        cv = GroupKFold(n_splits=nsplit)
        gs = GridSearchCV(model, grid, cv=cv.split(Xtr, ytr, gtr),
                          scoring="balanced_accuracy", n_jobs=1, refit=True)
        gs.fit(Xtr, ytr)
        est, best = gs.best_estimator_, gs.best_params_
    else:
        est, best = model.fit(Xtr, ytr), {}
    pred = est.predict(Xte)
    return dict(
        acc=float((pred == yte).mean()),
        bal=float(balanced_accuracy_score(yte, pred)),
        kappa=float(cohen_kappa_score(yte, pred)),
        n_test=int(len(yte)),
        majority=float(max(np.bincount(yte, minlength=2)) / len(yte)),
        params=str(best),
    )


def run_one(subs, model_name, ea, protocol, art_mode, held):
    """One (model, EA, protocol, artefact mode, held-out subject) cell."""
    np.random.seed(SEED)
    which, pipe, grid = build(model_name)
    bidx = slice(0, 1) if which == "main" else slice(1, None)

    def prep(s):
        d = subs[s]
        cov = d["cov"][bidx]
        if ea:
            cov = euclidean_align(cov, d["sess"])
        X = cov[0] if which == "main" else np.transpose(cov, (1, 0, 2, 3))
        keep = np.ones(len(d["y"]), bool) if art_mode == "all" else (d["art"] == 0)
        return X[keep], d["y"][keep], d["sess"][keep]

    if protocol == "P1_within_subject":
        X, y, sess = prep(held)
        tr, te = sess <= 3, sess >= 4
        if te.sum() == 0 or len(np.unique(y[tr])) < 2:
            return None
        r = fit_eval(X[tr], y[tr], sess[tr], X[te], y[te], pipe, grid, 3)
    else:  # P2_cross_subject
        Xl, yl, gl = [], [], []
        for i, s in enumerate(subs):
            if s == held:
                continue
            Xs, ys, _ = prep(s)
            Xl.append(Xs)
            yl.append(ys)
            gl.append(np.full(len(ys), i))
        Xtr = np.concatenate(Xl)
        ytr = np.concatenate(yl)
        gtr = np.concatenate(gl)
        Xte, yte, _ = prep(held)
        r = fit_eval(Xtr, ytr, gtr, Xte, yte, pipe, grid, 4)

    r.update(model=model_name, ea=int(ea), protocol=protocol,
             artefacts=art_mode, subject=held)
    return r


def main():
    os.makedirs(RES, exist_ok=True)
    subs = load_all()
    if not subs:
        print("No data. Run s01_fetch_2b.py first.")
        return 1
    print(f"=== s02_run_models ===\n{len(subs)} subjects, "
          f"{sum(len(d['y']) for d in subs.values())} trials total\n")

    jobs = [(m, ea, p, a, s)
            for p in ("P1_within_subject", "P2_cross_subject")
            for a in ("all", "clean")
            for m in MODELS
            for ea in (False, True)
            for s in subs]
    print(f"{len(jobs)} cells to run")

    t0 = time.time()
    rows = Parallel(n_jobs=-1, verbose=5)(
        delayed(run_one)(subs, m, ea, p, a, s) for m, ea, p, a, s in jobs
    )
    rows = [r for r in rows if r]
    print(f"\ndone in {time.time() - t0:.0f} s, {len(rows)} results")

    cols = ["protocol", "artefacts", "model", "ea", "subject", "n_test",
            "acc", "bal", "kappa", "majority", "params"]
    with open(os.path.join(RES, "per_subject.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # aggregate
    agg = {}
    for r in rows:
        k = (r["protocol"], r["artefacts"], r["model"], r["ea"])
        agg.setdefault(k, []).append(r)
    out = []
    for k, rs in sorted(agg.items()):
        bal = np.array([x["bal"] for x in rs])
        acc = np.array([x["acc"] for x in rs])
        kap = np.array([x["kappa"] for x in rs])
        # per-subject binomial threshold at p<0.05, two-sided, per test size
        above = sum(1 for x in rs
                    if x["acc"] >= 0.5 + 1.96 * np.sqrt(0.25 / x["n_test"]))
        out.append(dict(protocol=k[0], artefacts=k[1], model=k[2], ea=k[3],
                        n_subjects=len(rs),
                        mean_acc=round(acc.mean(), 4),
                        mean_bal=round(bal.mean(), 4),
                        sd_bal=round(bal.std(ddof=1), 4),
                        median_bal=round(float(np.median(bal)), 4),
                        mean_kappa=round(kap.mean(), 4),
                        subjects_above_chance=above,
                        mean_majority=round(
                            np.mean([x["majority"] for x in rs]), 4)))
    with open(os.path.join(RES, "summary.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    for proto in ("P1_within_subject", "P2_cross_subject"):
        print(f"\n--- {proto}  (artefact-flagged trials KEPT) ---")
        print(f"{'model':<12}{'EA off':>10}{'EA on':>10}{'delta':>9}"
              f"{'>chance':>9}")
        for m in MODELS:
            g = {o["ea"]: o for o in out
                 if o["protocol"] == proto and o["artefacts"] == "all"
                 and o["model"] == m}
            if 0 in g and 1 in g:
                print(f"{m:<12}{g[0]['mean_bal']:>10.4f}{g[1]['mean_bal']:>10.4f}"
                      f"{g[1]['mean_bal'] - g[0]['mean_bal']:>+9.4f}"
                      f"{g[1]['subjects_above_chance']:>6}/{len(subs)}")
    print("\nWrote results\\per_subject.csv and results\\summary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
