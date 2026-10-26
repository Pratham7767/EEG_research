"""Your own model, trained on your cued runs plus BCI IV 2b, and scored honestly.

Candidates: 3 model types (filter-bank CSP + SVM, CSP + SVM 8-30 Hz, log power + SVM 8-30 Hz) x
3 weightings ('2b only' = your data not used, '2b + yours' = your trials together weigh as much as all 2b
trials, 'yours only'). Each candidate is scored by LEAVE-ONE-RUN-OUT on your runs: the model never sees the
run it is tested on. Score = trial accuracy (mean sign of the outputs 1.5-4.0 s after the cue). Because 9
candidates are tried, the binomial p of the best one is multiplied by 9 (Bonferroni) before the verdict.
PROMISING = corrected p < 0.05 and accuracy >= 60 %; it becomes READY only when a cued test on NEW trials agrees
(found 2026-10-26: a 65 % leave-one-run-out model scored 4/20 on the next run).
Runs whose signal was BAD (50 Hz hum > 25 uV, or no / huge EEG) are left out of training.
Your runs go through the same steps as live: montage -> 50 Hz notch -> causal band-pass -> 2 s covariances,
each run aligned to its own mean covariance (no labels), artifact windows dropped.
"""
import json
import time
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, ttest_ind
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from mibci import config as C
from mibci.dsp import apply_montage
from mibci.recorder import list_runs, load_run
from mibci.trainer import artifact_flags

from . import settings as S
from .dsp_extra import Notch
from .models import LinearCovModel, features, fit_csp, inv_sqrt, unflat
from .train2b import ALL_BANDS, BROAD, SPECS, covs, subject_rows

TYPES = ["fbcsp_svm", "csp_svm", "logvar_svm"]
WEIGHTINGS = {"2b only": 0.0, "2b + yours": 1.0, "yours only": float("inf")}
STEP = 5                                   # every 5th output (0.2 s apart), as for 2b


class UserRun:
    def __init__(self, path, swap=False):
        r = load_run(path)
        eeg = np.asarray(r["eeg"], float)
        if swap:                           # headset left/right sides exchanged: A1<->A2, C3<->C4
            eeg = eeg[:, [3, 2, 1, 0]]
        self.path, self.name = Path(path), Path(path).name
        self.run_type = r["meta"].get("run_type")
        m = Notch([1, 2]).process(apply_montage(eeg))
        x = m[:, [1, 2]]
        per = {b: covs(x, b) for b in ALL_BANDS}
        ends = per[BROAD][0]
        bad = artifact_flags(m, ends)
        good = ~bad if (~bad).sum() > 50 else np.ones(len(bad), bool)
        self.cues = [(s, c) for s, name, c in r["events"] if name in ("cue_left", "cue_right")]
        rows, y, tid = [], [], []
        for k, (s, c) in enumerate(self.cues):
            mm = np.flatnonzero((ends >= s + 1.5 * S.FS) & (ends <= s + 4.0 * S.FS) & good)[::STEP]
            rows.append(mm)
            y += [c] * len(mm)
            tid += [k] * len(mm)
        rows = np.concatenate(rows) if rows else np.zeros(0, int)
        self.y, self.tid = np.array(y, int), np.array(tid, int)
        self.A, self.Fall, self.good = {}, {}, good
        for b in ALL_BANDS:
            F = per[b][1]
            P = inv_sqrt(unflat(F[good].mean(0)))
            self.A[b] = P @ unflat(F[rows]) @ P
            self.Fall[b] = F
        self.artifact_fraction = float(bad.mean())
        self.erd = erd_lateralisation(x, self.cues)


def erd_lateralisation(x, cues):
    """Per trial: log power 0.5-4 s after the cue minus -2..-0.5 s before, C4 minus C3, mu and beta.
    Left-hand imagery should give < 0 (C4 drops), right-hand > 0 (C3 drops)."""
    from scipy.signal import sosfilt, butter
    out = {}
    for name, band in (("mu", (8, 13)), ("beta", (13, 30))):
        y = sosfilt(butter(4, band, btype="bandpass", fs=S.FS, output="sos"), x - x[0], axis=0) ** 2
        vals = []
        for s, c in cues:
            a, b0, t0, t1 = s - 2 * S.FS, s - int(0.5 * S.FS), s + int(0.5 * S.FS), s + 4 * S.FS
            if a < 0 or t1 > len(y):
                continue
            ch = np.log(y[t0:t1].mean(0) + 1e-12) - np.log(y[a:b0].mean(0) + 1e-12)
            vals.append((c, ch[1] - ch[0]))
        out[name] = vals
    return out


def _fit(spec_name, base, user, lam):
    spec = SPECS[spec_name]
    bands = spec["bands"]
    parts_A, parts_y, parts_w = [], [], []
    (A2b, y2b) = base
    n2b = len(y2b)
    nu = sum(len(u.y) for u in user)
    if lam != float("inf"):
        parts_A.append([A2b[b] for b in bands])
        parts_y.append(y2b)
        parts_w.append(np.ones(n2b))
    if lam > 0 and nu:
        wu = 1.0 if lam == float("inf") else lam * n2b / nu
        for u in user:
            if len(u.y):
                parts_A.append([u.A[b] for b in bands])
                parts_y.append(u.y)
                parts_w.append(np.full(len(u.y), wu))
    A = [np.concatenate([p[k] for p in parts_A]) for k in range(len(bands))]
    y, w = np.concatenate(parts_y), np.concatenate(parts_w)
    W = fit_csp(A, y, w) if spec["feature"] == "csp" else None
    Z = features(spec["feature"], A, W)
    sc = StandardScaler().fit(Z, sample_weight=w)
    clf = LinearSVC(C=0.1, class_weight="balanced", dual="auto", max_iter=20000, random_state=42)
    clf.fit(sc.transform(Z), (y == C.RIGHT).astype(int), sample_weight=w)
    return LinearCovModel(bands, spec["feature"], W, sc.mean_, sc.scale_, clf.coef_[0], clf.intercept_[0],
                          dict(name=spec["name"], spec=spec_name, montage=C.MONTAGE, win_s=2.0))


def _score(model, run):
    """Trial accuracy on one held-out run. The run's mean output is removed first (live does the same with
    its running bias; no labels)."""
    if len(run.y) == 0:
        return 0, 0
    d = model.decide([run.A[b] for b in model.bands])
    d = d - d.mean()
    k = n = 0
    for t in np.unique(run.tid):
        m = run.tid == t
        pred = C.RIGHT if np.mean(np.where(d[m] >= 0, 1, -1)) >= 0 else C.LEFT
        k += int(pred == run.y[m][0])
        n += 1
    return k, n


_BASE = {}


def base_rows():
    if "rows" not in _BASE:
        data = [subject_rows(s) for s in range(1, 10)]
        A = {b: np.concatenate([d[0][b] for d in data]) for b in ALL_BANDS}
        _BASE["rows"] = (A, np.concatenate([d[1] for d in data]))
    return _BASE["rows"]


def user_runs(subject, root=C.DATA_DIR, today_only=True, types=("screening", "feedback")):
    day = time.strftime("%Y-%m-%d")
    out = []
    for p in list_runs(subject, None, root):
        try:
            rt = json.loads((p / "run.json").read_text()).get("run_type")
        except Exception:
            continue
        if rt in types and (not today_only or p.name.startswith(day)):
            out.append(p)
    return out


def train_personal(run_paths, subject, out_dir=None, progress=print, swap=False):
    progress(f"Loading {len(run_paths)} run(s) ...")
    from .dsp_extra import signal_check
    user, skipped = [], []
    for p in run_paths:
        r = load_run(p)
        q = signal_check(apply_montage(np.asarray(r["eeg"], float))[:, [1, 2]])
        if q["level"] == 2:
            skipped.append(f"{Path(p).name} (BAD signal: hum {q['hum_50']} uV, EEG {q['rms_8_30']} uV)")
            continue
        u = UserRun(p, swap=swap)
        if len(u.y):
            user.append(u)
    rep = dict(subject=subject, runs=[u.name for u in user], skipped=skipped,
               created=time.strftime("%Y-%m-%d %H:%M:%S"),
               trials=int(sum(len(u.cues) for u in user)))
    # ERD check over all runs
    for band in ("mu", "beta"):
        v = [x for u in user for x in u.erd[band]]
        L = np.array([d for c, d in v if c == C.LEFT])
        R = np.array([d for c, d in v if c == C.RIGHT])
        if len(L) > 2 and len(R) > 2:
            t = ttest_ind(R, L)
            p1 = float(t.pvalue / 2 if t.statistic > 0 else 1 - t.pvalue / 2)
            rep[f"erd_{band}"] = dict(lateralisation=float(R.mean() - L.mean()), p=p1)
    progress("Loading BCI IV 2b rows ...")
    base = base_rows()
    res = {}
    if len(user) >= 2:
        for typ in TYPES:
            m2b = _fit(typ, base, [], 0.0)
            for wname, lam in WEIGHTINGS.items():
                progress(f"Scoring {SPECS[typ]['name']} / {wname} (leave-one-run-out) ...")
                k = n = 0
                per = []
                for i, u in enumerate(user):
                    others = [x for j, x in enumerate(user) if j != i]
                    if lam == float("inf") and len({int(c) for x in others for c in np.unique(x.y)}) < 2:
                        continue
                    m = m2b if lam == 0 else _fit(typ, base, others, lam)
                    kk, nn = _score(m, u)
                    per.append(dict(run=u.name, correct=kk, trials=nn))
                    k, n = k + kk, n + nn
                if n:
                    p = float(binomtest(k, n, 0.5, alternative="greater").pvalue)
                    res[f"{typ} | {wname}"] = dict(type=typ, weighting=wname, accuracy=k / n, correct=k, trials=n,
                                                  p=p, per_run=per)
    rep["candidates"] = res
    if res:
        best_key = max(res, key=lambda k: (res[k]["accuracy"], -res[k]["p"]))
        best = res[best_key]
        p_corr = min(1.0, best["p"] * len(res))
        ready = p_corr < 0.05 and best["accuracy"] >= 0.6
        rep.update(chosen=best_key, accuracy=best["accuracy"], p=best["p"], p_corrected=p_corr,
                   verdict="PROMISING - confirm with a cued test" if ready else "NOT READY")
        typ, lam = best["type"], WEIGHTINGS[best["weighting"]]
    else:
        typ, lam = "fbcsp_svm", 0.0
        rep.update(chosen="fbcsp_svm | 2b only", verdict="NOT READY",
                   note="fewer than 2 runs: nothing can be tested; record at least 2 blocks")
    progress("Fitting the final model on all your runs ...")
    model = _fit(typ, base, user, lam)
    model.meta.update(subject=subject, weighting=rep["chosen"].split(" | ")[1], score=rep.get("accuracy"),
                      p_corrected=rep.get("p_corrected"), verdict=rep["verdict"], trained_on_runs=rep["runs"],
                      name=f"{SPECS[typ]['name']} - {subject}, {rep['chosen'].split(' | ')[1]}")
    rep["model_name"] = model.name
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        model.save(out_dir / f"live_{stamp}.json")
        (out_dir / f"report_{stamp}.json").write_text(json.dumps(rep, indent=1, default=float))
        rep["model_path"] = str(out_dir / f"live_{stamp}.json")
    seeds = {}
    if user:                                   # alignment seed for live use: the latest run's clean covariances
        u = user[-1]
        seeds = np.hstack([u.Fall[b][u.good] for b in model.bands])
    return model, rep, seeds


def format_report(rep):
    L = [f"YOUR MODEL ({rep['subject']}, {rep['trials']} trials in {len(rep['runs'])} runs)"]
    for s in rep.get("skipped", []):
        L.append(f"  left out: {s}")
    for band in ("mu", "beta"):
        e = rep.get(f"erd_{band}")
        if e:
            L.append(f"  left/right pattern (ERD) {band:4s}: {e['lateralisation']:+.3f} (should be > 0), "
                     f"p = {e['p']:.3f} -> {'PRESENT' if e['p'] < 0.05 and e['lateralisation'] > 0 else 'not shown yet'}")
    c = rep.get("candidates", {})
    if c:
        L.append("  leave-one-run-out accuracy (model never saw the run it was tested on):")
        for k in sorted(c, key=lambda k: -c[k]["accuracy"]):
            v = c[k]
            L.append(f"    {k:26s} {100 * v['accuracy']:5.1f} %  ({v['correct']}/{v['trials']})  p = {v['p']:.3f}")
        L.append(f"  CHOSEN: {rep['chosen']}  {100 * rep['accuracy']:.1f} %, p corrected for 9 tries = "
                 f"{rep['p_corrected']:.3f}")
    if rep.get("note"):
        L.append("  " + rep["note"])
    if rep["verdict"].startswith("PROMISING"):
        L.append("  VERDICT: PROMISING - run 3. Cued test (new trials). Only if that is also above chance is it READY.")
    else:
        L.append("  VERDICT: NOT READY - free mode will mostly guess. Keep the signal GOOD, record more blocks.")
    return "\n".join(L)
