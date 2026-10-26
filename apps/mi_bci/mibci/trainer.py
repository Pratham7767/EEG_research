"""Offline training and honest evaluation on our own recordings.

Same feature code as the live engine (dsp.BandPower, dsp.ArtifactCheck), so a decoder trained here
behaves identically when it runs live. Rules carried over from the rest of the project:
  * evaluate on held-out RUNS (never random splits: neighbouring samples are not independent)
  * any choice (which bands) is made inside the training folds only (nested)
  * a shuffled-label permutation test says whether there is signal at all
"""
import json
import time
from pathlib import Path

import numpy as np

from . import config as C
from .decoder import Decoder, build_decoder, fit_lda
from .dsp import ArtifactCheck, apply_montage, bandpower_offline
from .recorder import load_run

DEC_CH = [C.CHANNELS.index(c) for c in C.DECODE_CHANNELS]


def artifact_flags(eeg, out_idx):
    """Exactly what the live engine flags at each output index."""
    ac = ArtifactCheck(DEC_CH)
    flags, last = np.zeros(len(out_idx), bool), 0
    for k, i in enumerate(out_idx):
        ac.push(eeg[last:i + 1])
        last = i + 1
        flags[k] = ac.check()
    return flags


def cues(events):
    return [(s, c) for s, name, c in events if name in ("cue_left", "cue_right")]


class RunFeatures:
    """All candidate features for one run, plus cue positions."""

    def __init__(self, run, bands=C.CANDIDATE_BANDS, montage=None):
        self.path = run.get("path")
        self.bands = list(bands)
        eeg = apply_montage(run["eeg"], montage)
        self.idx, self.F = bandpower_offline(eeg, DEC_CH, self.bands)
        self.art = artifact_flags(eeg, self.idx)
        self.cues = cues(run["events"])
        self.run_type = run.get("meta", {}).get("run_type")
        self._cache = {}

    def rows(self, win):
        """Feature rows in [cue+win0, cue+win1], not artifacts. Returns X, y, trial id (cached)."""
        key = tuple(win)
        if key not in self._cache:
            self._cache[key] = self._rows(win)
        return self._cache[key]

    def _rows(self, win):
        X, y, tid = [], [], []
        for k, (s, c) in enumerate(self.cues):
            t = (self.idx - s) / C.FS
            m = (t >= win[0]) & (t <= win[1]) & ~self.art
            X.append(self.F[m])
            y += [c] * int(m.sum())
            tid += [k] * int(m.sum())
        if not X:
            return np.zeros((0, self.F.shape[1])), np.zeros(0, int), np.zeros(0, int)
        return np.vstack(X), np.array(y), np.array(tid)

    def score(self, w, b, cols, labels=None):
        """Trial accuracy and integrated error (Graz iCE) of a linear rule on this run."""
        X, y, tid = self.rows(C.EVAL_WIN)
        if labels is not None:
            y = np.array([labels[t] for t in tid])
        if len(y) == 0:
            return np.nan, np.nan, 0
        sign = np.where(X[:, cols] @ w + b >= 0, 1.0, -1.0)
        want = np.where(y == C.RIGHT, 1.0, -1.0)
        ut, inv, cnt = np.unique(tid, return_inverse=True, return_counts=True)
        mean_sign = np.bincount(inv, sign) / cnt
        want_t = np.bincount(inv, want) / cnt
        pred = np.where(mean_sign >= 0, 1.0, -1.0)
        err = np.bincount(inv, (sign != want).astype(float)) / cnt
        return float(np.mean(pred == want_t)), float(np.mean(err)), len(ut)


def _stack(rfs, win, cols=None, relabel=None):
    Xs, ys = [], []
    for k, rf in enumerate(rfs):
        X, y, tid = rf.rows(win)
        if relabel is not None:
            y = np.array([relabel[k][t] for t in tid])
        Xs.append(X if cols is None else X[:, cols])
        ys.append(y)
    return np.vstack(Xs), np.concatenate(ys)


def loro(rfs, cols, relabel=None):
    """Leave-one-run-out trial accuracy for a fixed feature set."""
    accs, n = [], []
    for k in range(len(rfs)):
        tr = [r for j, r in enumerate(rfs) if j != k]
        rl = None if relabel is None else [relabel[j] for j in range(len(rfs)) if j != k]
        X, y = _stack(tr, C.TRAIN_WIN, cols, rl)
        if len(np.unique(y)) < 2:
            continue
        w, b = fit_lda(X, y)
        a, _, nt = rfs[k].score(w, b, cols, None if relabel is None else relabel[k])
        if nt:
            accs.append(a)
            n.append(nt)
    return float(np.average(accs, weights=n)) if accs else np.nan


def select_features(rfs, max_feat=C.MAX_FEATURES):
    """Greedy forward selection by leave-one-run-out accuracy (Graz used SFFS, <= 6 features).
    Adds a feature only if it improves accuracy."""
    n_all = rfs[0].F.shape[1]
    chosen, best = [], -1.0
    while len(chosen) < max_feat:
        cand = [(loro(rfs, chosen + [c]), c) for c in range(n_all) if c not in chosen]
        acc, c = max(cand)
        if acc <= best + 1e-9:
            break
        chosen.append(c)
        best = acc
    return chosen, best


def nested_accuracy(rfs):
    """Honest estimate: for each held-out run, select features on the other runs only."""
    accs, n, per_run = [], [], []
    for k in range(len(rfs)):
        tr = [r for j, r in enumerate(rfs) if j != k]
        cols, _ = select_features(tr) if len(tr) >= 2 else ([0, 1], None)
        X, y = _stack(tr, C.TRAIN_WIN, cols)
        w, b = fit_lda(X, y)
        a, e, nt = rfs[k].score(w, b, cols)
        per_run.append(dict(run=Path(rfs[k].path).name if rfs[k].path else k, accuracy=a, integrated_error=e,
                            trials=nt))
        if nt:
            accs.append(a)
            n.append(nt)
    return (float(np.average(accs, weights=n)) if accs else np.nan), per_run


def default_cols(bands=C.CANDIDATE_BANDS):
    """C3 and C4 in the standard mu (8-13) and broad beta (13-30) bands."""
    k = len(DEC_CH)
    return [bands.index((8, 13)) * k + j for j in range(k)] + [bands.index((13, 30)) * k + j for j in range(k)]


def permutation_p(rfs, n_perm=200, seed=0):
    """Shuffle trial labels within each run; how often does fixed-feature LORO do as well?"""
    rng = np.random.default_rng(seed)
    cols = default_cols(rfs[0].bands)
    real = loro(rfs, cols)
    true_labels = [[c for _, c in rf.cues] for rf in rfs]
    hits = 0
    for _ in range(n_perm):
        rl = [list(rng.permutation(t)) for t in true_labels]
        if loro(rfs, cols, rl) >= real:
            hits += 1
    return real, (hits + 1) / (n_perm + 1)


def train(run_paths, subject, out_dir=None, n_perm=200, meta=None):
    """Train a decoder on the given runs and write decoder JSON + report. Returns (decoder, report)."""
    runs = [load_run(p) for p in run_paths]
    rfs = [RunFeatures(r) for r in runs]
    rfs = [rf for rf in rfs if rf.cues]
    if not rfs:
        raise ValueError("no cued trials in these runs")
    t0 = time.time()
    report = dict(subject=subject, runs=[Path(p).name for p in run_paths],
                  trials=int(sum(len(rf.cues) for rf in rfs)),
                  artifact_fraction=float(np.mean(np.concatenate([rf.art for rf in rfs]))))
    if len(rfs) >= 2:
        report["nested_run_accuracy"], report["per_run"] = nested_accuracy(rfs)
        report["fixed_mu_beta_accuracy"], report["permutation_p"] = permutation_p(rfs, n_perm)
    else:
        report["note"] = "only one run: no held-out evaluation possible; record at least 2 runs"
    report.update(score_verdict(report))
    cols, cv = select_features(rfs) if len(rfs) >= 2 else (default_cols(), None)
    X, y = _stack(rfs, C.TRAIN_WIN)
    dec = build_decoder(X, y, cols, rfs[0].bands, C.DECODE_CHANNELS,
                        dict(subject=subject, trained_on=report["runs"], selection_loro=cv, montage=C.MONTAGE,
                             score=report.get("nested_run_accuracy"), permutation_p=report.get("permutation_p"),
                             verdict=report["verdict"], **(meta or {})))
    report["features"] = dec.meta["features"]
    report["seconds"] = round(time.time() - t0, 1)
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        dec.save(out / f"decoder_{stamp}.json")
        dec.save(out / "current.json")
        (out / f"report_{stamp}.json").write_text(json.dumps(report, indent=2, default=float))
        report["decoder_path"] = str(out / f"decoder_{stamp}.json")
    return dec, report


READY_ACC = 0.65          # held-out accuracy at which feedback is worth trying


def score_verdict(rep):
    """Plain-English verdict for the training report."""
    acc, p = rep.get("nested_run_accuracy"), rep.get("permutation_p")
    if acc is None or acc != acc:
        v = "NO SCORE: record at least 2 screening runs (4-6 is better), then train again"
    elif p is not None and p < 0.05 and acc >= READY_ACC:
        v = "READY: the decoder works on runs it never saw - go to Feedback"
    elif p is not None and p < 0.05:
        v = f"WEAK: above chance but under {READY_ACC:.0%} - record more screening runs before feedback"
    else:
        v = "NOT READY: no reliable left/right difference yet - record more screening runs"
    score = "no score" if acc is None or acc != acc else f"{acc:.0%} on held-out runs (chance = 50%)"
    if p is not None and acc == acc and acc is not None:
        score += f", p = {p:.3f}"
    return dict(verdict=v, score_text=score)


def evaluate_decoder(dec, run_path):
    """Score a saved decoder on a run the way the live engine would (no retraining)."""
    rf = RunFeatures(load_run(run_path), bands=dec.bands, montage=dec.meta.get("montage"))
    nb, k = len(dec.bands), len(dec.channel_names)
    cols = list(range(nb * k))
    return rf.score(dec.w, dec.b, cols)


def should_switch(new_dec, old_dec, run_path, min_gain=C.RETRAIN_MIN_GAIN):
    """Graz rule: use the new classifier only if it is clearly (>= 5 points) better on recent data."""
    a_new = evaluate_decoder(new_dec, run_path)[0]
    a_old = evaluate_decoder(old_dec, run_path)[0]
    return bool(a_new >= a_old + min_gain), a_new, a_old
