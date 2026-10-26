"""Train and improve the SVM (CSP + SVM + Euclidean Alignment).

Base model    the SVM trained on all 9 BCI IV 2b subjects (C3, C4), each 2b session aligned to itself.
Improving it  every time you train, the SVM is refitted on 2b PLUS your runs, with three weightings:
                 "2b only"        your data not used (pure base model)
                 "2b + yours"     your trials together count as much as all 2b trials
                 "yours only"     2b not used
              Each weighting is scored on YOUR runs, leaving one run out at a time (the model never
              sees the run it is tested on). The best one is kept. Score = accuracy over those
              held-out trials; p = one-sided binomial test against 50 %.
Alignment     each recording day is one session: its reference is the mean covariance of all that
              day's recordings (baseline included). No labels are used for this.
"""
import json
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.stats import binomtest

from . import config as C
from .dsp import apply_montage
from .recorder import load_run
from .svm import SvmDecoder, align, covwindow_offline, decide, fit_params, new_meta, reference
from .trainer import artifact_flags, cues, score_verdict

DEC_CH = [C.CHANNELS.index(c) for c in C.DECODE_CHANNELS]
TRAIN_WIN = (1.5, 4.0)     # ends of the 2 s windows used for fitting, seconds after the cue
EVAL_WIN = (1.5, 4.0)      # outputs integrated to score one trial (the live engine uses the same)
SUBSAMPLE = 5              # use every 5th output (0.2 s apart) for fitting
WEIGHTINGS = {"2b only": 0.0, "2b + yours": 1.0, "yours only": float("inf")}
CACHE = C.APP_DIR / "_out" / "base_2b_cache"
BASE_JSON = C.APP_DIR / "models" / "base_2b_svm.json"


class RunCov:
    def __init__(self, eeg, events, day, name=""):
        m = apply_montage(np.asarray(eeg, float))
        self.idx, self.F = covwindow_offline(m, DEC_CH)
        self.art = artifact_flags(m, self.idx)
        self.cues = cues(events)
        self.day, self.name = day, name
        self._rows = {}

    @staticmethod
    def from_path(p):
        r = load_run(p)
        return RunCov(r["eeg"], r["events"], Path(p).name[:10], Path(p).name)

    def rows(self, win, step=1):
        key = (tuple(win), step)
        if key not in self._rows:
            F, y, t = [], [], []
            for k, (s, c) in enumerate(self.cues):
                tt = (self.idx - s) / C.FS
                m = np.flatnonzero((tt >= win[0]) & (tt <= win[1]) & ~self.art)[::step]
                F.append(self.F[m])
                y += [c] * len(m)
                t += [k] * len(m)
            self._rows[key] = ((np.vstack(F) if F else np.zeros((0, 3))), np.array(y, int), np.array(t, int))
        return self._rows[key]


def day_refs(rcs):
    out = {}
    for d in {r.day for r in rcs}:
        F = np.vstack([r.F[~r.art] for r in rcs if r.day == d])
        out[d] = reference(F)
    return out


def stack(rcs, refs, win=TRAIN_WIN, step=SUBSAMPLE):
    X, Y = [], []
    for r in rcs:
        F, y, _ = r.rows(win, step)
        if len(y):
            X.append(align(F, refs[r.day]))
            Y.append(y)
    return (np.concatenate(X), np.concatenate(Y)) if X else (np.zeros((0, 2, 2)), np.zeros(0, int))


def score_run(params, r, R):
    """Trial accuracy and integrated error of the model on one run, like the live engine."""
    F, y, tid = r.rows(EVAL_WIN, 1)
    if len(y) == 0:
        return np.nan, np.nan, 0, 0
    sign = np.where(decide(params, align(F, R)) >= 0, 1.0, -1.0)
    want = np.where(y == C.RIGHT, 1.0, -1.0)
    ut, inv, cnt = np.unique(tid, return_inverse=True, return_counts=True)
    pred = np.where(np.bincount(inv, sign) / cnt >= 0, 1.0, -1.0)
    truth = np.bincount(inv, want) / cnt
    k = int((pred == truth).sum())
    return k / len(ut), float(np.mean(np.bincount(inv, (sign != want).astype(float)) / cnt)), len(ut), k


def fit_weighted(base, user, lam):
    (Xb, yb), (Xu, yu) = base, user
    if lam == 0 or len(yu) == 0:
        return fit_params(Xb, yb)
    if np.isinf(lam) or len(yb) == 0:
        return fit_params(Xu, yu)
    w = np.concatenate([np.ones(len(yb)), np.full(len(yu), lam * len(yb) / len(yu))])
    return fit_params(np.concatenate([Xb, Xu]), np.concatenate([yb, yu]), w)


# ------------------------------------------------------------------ 2b base data
def _sessions_2b(sub):
    for split, ids in (("T", (1, 2, 3)), ("E", (4, 5))):
        m = loadmat(C.BCI2B_DIR / f"B{sub:02d}{split}.mat", squeeze_me=True, struct_as_record=False)
        for sid, s in zip(ids, np.atleast_1d(m["data"])):
            yield sid, np.asarray(s.X, float), np.atleast_1d(s.trial).astype(int) - 1, np.atleast_1d(s.y).astype(int)


def runs_2b(sub):
    """Subject's 2b data as RunCov runs (screening runs of 20 trials, feedback runs of 40), cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"B{sub:02d}.npz"
    if f.exists():
        z = np.load(f, allow_pickle=True)
        out = []
        for k in range(int(z["n"])):
            r = RunCov.__new__(RunCov)
            r.idx, r.F, r.art = z[f"idx{k}"], z[f"F{k}"], z[f"art{k}"]
            r.cues = [tuple(map(int, c)) for c in z[f"cues{k}"]]
            r.day, r.name, r._rows = str(z[f"day{k}"]), str(z[f"name{k}"]), {}
            out.append(r)
        return out
    if not (C.BCI2B_DIR / f"B{sub:02d}T.mat").exists():
        raise FileNotFoundError(
            f"The SVM base needs the BCI IV 2b data in {C.BCI2B_DIR} (from the Drive bundle or "
            f"experiments/05_bci_iv_2b/s01_fetch_2b.py), then run tools/build_base_svm.py once.")
    out = []
    for sid, X, trial, y in _sessions_2b(sub):
        per = 20 if sid <= 2 else 40
        for r0 in range(0, len(trial), per):
            tr, yy = trial[r0:r0 + per], y[r0:r0 + per]
            a, b = max(0, tr[0] - 2 * C.FS), min(len(X), tr[-1] + int(9.5 * C.FS))
            eeg = np.zeros((b - a, 4))
            eeg[:, 1], eeg[:, 2] = X[a:b, 0], X[a:b, 2]
            ev = [(int(s0 - a + 3 * C.FS), "cue_left" if c == C.LEFT else "cue_right", int(c)) for s0, c in zip(tr, yy)]
            out.append(RunCov(eeg, ev, f"B{sub:02d}_S{sid}", f"B{sub:02d}_s{sid}_run{r0 // per + 1}"))
    np.savez_compressed(f, n=len(out), **{f"{k}{i}": v for i, r in enumerate(out) for k, v in
                                          (("idx", r.idx), ("F", r.F), ("art", r.art), ("cues", np.array(r.cues)),
                                           ("day", r.day), ("name", r.name))})
    return out


def base_rows(subjects=range(1, 10)):
    rcs = [r for s in subjects for r in runs_2b(s)]
    return stack(rcs, day_refs(rcs))


def build_base(subjects=range(1, 10)):
    """The base model: SVM on all 2b subjects. Saved to apps/mi_bci/models/base_2b_svm.json."""
    params = fit_params(*base_rows(subjects))
    dec = SvmDecoder(params, new_meta(trained_on="BCI IV 2b, subjects " + ",".join(map(str, subjects)),
                                      weighting="2b only", eval_win=list(EVAL_WIN), score=None,
                                      verdict="BASE MODEL: not yet tested on you - train with your runs"))
    BASE_JSON.parent.mkdir(parents=True, exist_ok=True)
    dec.save(BASE_JSON)
    return dec


# ------------------------------------------------------------------ improve with the user's runs
def evaluate_weightings(user, base, refs):
    """Leave-one-run-out over the user's runs for each weighting. Returns {name: (acc, n, k, per_run)}."""
    res = {}
    for name, lam in WEIGHTINGS.items():
        n_tot = k_tot = 0
        per = []
        for i, r in enumerate(user):
            others = [u for j, u in enumerate(user) if j != i]
            Xu, yu = stack(others, refs)
            if np.isinf(lam) and len(set(yu.tolist())) < 2:
                continue                                  # 'yours only' needs both hands in training
            params = fit_weighted(base, (Xu, yu), lam)
            acc, ice, n, k = score_run(params, r, refs[r.day])
            if n:
                per.append(dict(run=r.name, accuracy=acc, integrated_error=ice, trials=n))
                n_tot, k_tot = n_tot + n, k_tot + k
        if n_tot:
            p = binomtest(k_tot, n_tot, 0.5, alternative="greater").pvalue
            res[name] = dict(accuracy=k_tot / n_tot, trials=n_tot, p=float(p), per_run=per)
    return res


def train_svm(run_paths, subject, out_dir=None, base=None):
    user = [RunCov.from_path(p) for p in run_paths]
    return train_from_runs([u for u in user if u.cues], subject, out_dir, base)


def train_from_runs(user, subject, out_dir=None, base=None):
    t0 = time.time()
    refs = day_refs(user) if user else {}
    base = base if base is not None else base_rows()
    rep = dict(subject=subject, model="CSP + SVM + Euclidean Alignment", runs=[u.name for u in user],
               trials=int(sum(len(u.cues) for u in user)),
               artifact_fraction=float(np.mean(np.concatenate([u.art for u in user]))) if user else None)
    if len(user) >= 2:
        w = evaluate_weightings(user, base, refs)
        rep["weightings"] = {k: dict(accuracy=round(v["accuracy"], 3), trials=v["trials"], p=round(v["p"], 4))
                             for k, v in w.items()}
        prefer = {"2b + yours": 2, "yours only": 1, "2b only": 0}      # tie-break
        best = max(w, key=lambda k: (round(w[k]["accuracy"], 6), prefer[k]))
        rep.update(weighting=best, nested_run_accuracy=w[best]["accuracy"], permutation_p=w[best]["p"],
                   per_run=w[best]["per_run"])
        rep["note"] = ("score = accuracy on your runs, each tested by a model that did not see it; "
                       "p = binomial test against 50 %")
    else:
        best = "2b + yours" if user else "2b only"
        rep["weighting"] = best
        rep["note"] = "fewer than 2 runs: no held-out score possible; record at least 2 screening runs"
    rep.update(score_verdict(rep))
    Xu, yu = stack(user, refs) if user else (np.zeros((0, 2, 2)), np.zeros(0, int))
    params = fit_weighted(base, (Xu, yu), WEIGHTINGS[best])
    latest_day = sorted(refs)[-1] if refs else None
    dec = SvmDecoder(params, new_meta(subject=subject, trained_on=rep["runs"], weighting=best,
                                      eval_win=list(EVAL_WIN), score=rep.get("nested_run_accuracy"),
                                      permutation_p=rep.get("permutation_p"), verdict=rep["verdict"]),
                     ref=refs.get(latest_day) if latest_day else None)
    rep["seconds"] = round(time.time() - t0, 1)
    rep["features"] = [f"CSP+SVM ({best})"]
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        dec.save(out / f"decoder_{stamp}.json")
        dec.save(out / "current.json")
        (out / f"report_{stamp}.json").write_text(json.dumps(rep, indent=2, default=float))
        rep["decoder_path"] = str(out / f"decoder_{stamp}.json")
    return dec, rep


def session_reference(subject, day=None, root=C.DATA_DIR):
    """Alignment reference for a live run: mean covariance of today's recordings so far (no labels)."""
    from .recorder import list_runs
    day = day or time.strftime("%Y-%m-%d")
    runs = [p for p in list_runs(subject, None, root) if p.name.startswith(day)]
    if not runs:
        return None
    rcs = [RunCov.from_path(p) for p in runs]
    F = np.vstack([r.F[~r.art] for r in rcs if len(r.F)])
    return reference(F) if len(F) else None


def evaluate_on_run(dec, run_path):
    r = RunCov.from_path(run_path)
    return score_run(dec.p, r, reference(r.F[~r.art]))[:3]
