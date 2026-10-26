"""Competition-style cued test on the live stream.

Timing comes from mibci.paradigm (Graz / BCI IV 2b, driven by the EEG sample clock), or from the recorded
events of a 2b session (replay). Scored two ways:

  1. Trial decision (as apps/mi_bci): mean sign of the outputs 1.5-4.0 s after the cue -> LEFT/RIGHT.
     Accuracy, binomial p, confusion matrix.
  2. BCI Competition IV 2b metric: the output at EACH time point after the cue is a decision; Cohen's
     kappa over trials at each time point; the competition reported the MAXIMUM over time.
     With few trials the maximum is easily high by luck, so a shuffled-label 95 % chance level is given.

Runs on the headset are saved with apps/mi_bci's Recorder into data/mi_bci/<subject>/ as normal
'screening' (no feedback) or 'feedback' runs, so the mi_bci Train button can learn from them.
"""
import numpy as np
from scipy.stats import binomtest

from mibci import config as C

from . import settings as S


def cohen_kappa(truth, pred):
    """truth, pred: arrays of +1 (right) / -1 (left), same length."""
    truth, pred = np.asarray(truth), np.asarray(pred)
    if len(truth) == 0:
        return np.nan
    po = np.mean(truth == pred)
    pt, pp = np.mean(truth == 1), np.mean(pred == 1)
    pe = pt * pp + (1 - pt) * (1 - pp)
    return float((po - pe) / (1 - pe)) if pe < 1 else 0.0


def kappa_columns(P, truth):
    """P: (trials, bins) of +1/-1/nan. Kappa per bin (vectorised), nan if < 4 trials in a bin."""
    ok = ~np.isnan(P)
    n = ok.sum(0)
    t = truth[:, None]
    po = np.where(ok, P == t, False).sum(0) / np.maximum(n, 1)
    pt = np.where(ok, t == 1, False).sum(0) / np.maximum(n, 1)
    pp = np.where(ok, P == 1, False).sum(0) / np.maximum(n, 1)
    pe = pt * pp + (1 - pt) * (1 - pp)
    k = np.where(pe < 1, (po - pe) / np.where(pe < 1, 1 - pe, 1), 0.0)
    return np.where(n >= 4, k, np.nan)


class CuedSession:
    def __init__(self, paradigm, offset, recorder=None, sound=None, feedback=True, min_cue=None):
        self.par, self.offset, self.rec, self.sound = paradigm, int(offset), recorder, sound
        self.feedback = feedback
        self.min_cue = min_cue                  # cues before this absolute sample are not scored
        self.I, self.D, self.V, self.B = [], [], [], []
        self.cues = []                          # (absolute cue sample, class)
        self.trial_log = []                     # live, one line per finished trial
        self.done = False

    @property
    def phase(self):
        return self.par.phase

    @property
    def cls(self):
        return self.par.cls

    def ui_state(self):
        return self.par.ui_state()

    def process(self, x, n_end, outs):
        """x = raw samples just fed to the pipeline (the last one is absolute sample n_end - 1); outs = their outputs."""
        if self.done:
            return
        if self.rec is not None:
            self.rec.eeg(x)
        for o in outs:
            self.I.append(o.i)
            self.D.append(o.d)
            self.V.append(o.v)
            self.B.append(o.bad)
            if self.rec is not None:
                self.rec.output(o.i - self.offset, o.d, o.v, o.bad)
        for s, name, cls in self.par.tick(n_end - 1 - self.offset):
            a = s + self.offset
            if self.rec is not None:
                self.rec.event(s, name, cls)
            if name in ("cue_left", "cue_right"):
                self.cues.append((a, cls))
            elif name == "beep" and self.sound is not None:
                self.sound.play("beep")
            elif name == "task_end" and self.cues:
                self._log_trial(*self.cues[-1])
        if self.par.done:
            self.done = True

    def _arrays(self):
        return np.asarray(self.I, int), np.asarray(self.D, float), np.asarray(self.V, float), np.asarray(self.B, bool)

    def _decide(self, I, D, B, cue):
        m = (I >= cue + S.EVAL_WIN[0] * S.FS) & (I <= cue + S.EVAL_WIN[1] * S.FS) & ~B
        if not m.any():
            return None
        return C.RIGHT if np.mean(np.where(D[m] >= 0, 1.0, -1.0)) >= 0 else C.LEFT

    def _log_trial(self, cue, cls):
        I, D, V, B = self._arrays()
        pred = self._decide(I, D, B, cue)
        k = len(self.trial_log) + 1
        name = {C.LEFT: "LEFT", C.RIGHT: "RIGHT"}
        if pred is None:
            line = f"Trial {k}: cued {name[cls]} -> no clean output (artifact)"
        else:
            line = f"Trial {k}: cued {name[cls]:5s} -> decoded {name[pred]:5s} {'OK' if pred == cls else 'x'}"
        if self.min_cue is not None and cue < self.min_cue:
            line += "  (during calibration, not scored)"
        self.trial_log.append(line)

    # ------------------------------------------------------------------
    def results(self, exclude=(), n_perm=200, seed=0):
        I, D, V, B = self._arrays()
        exclude = set(exclude)
        rows = []
        for cue, cls in self.cues:
            if (self.min_cue is not None and cue < self.min_cue) or cue in exclude:
                continue
            if len(I) == 0 or I.max() < cue + S.EVAL_WIN[1] * S.FS:
                continue                               # trial not finished
            pred = self._decide(I, D, B, cue)
            if pred is not None:
                rows.append((cue, cls, pred))
        n = len(rows)
        res = dict(trials=n, excluded=len(exclude & {c for c, _ in self.cues}))
        if n == 0:
            return res
        cls = np.array([r[1] for r in rows])
        pred = np.array([r[2] for r in rows])
        k = int(np.sum(cls == pred))
        res.update(accuracy=k / n, correct=k, p=float(binomtest(k, n, 0.5, alternative="greater").pvalue),
                   n_left=int(np.sum(cls == C.LEFT)), n_right=int(np.sum(cls == C.RIGHT)),
                   confusion=[[int(np.sum((cls == a) & (pred == b))) for b in (C.LEFT, C.RIGHT)]
                              for a in (C.LEFT, C.RIGHT)])
        # ---- kappa over time (competition metric) ----
        b0, b1 = int(round(S.CURVE_T[0] * S.FS / S.HOP)), int(round(S.CURVE_T[1] * S.FS / S.HOP))
        nb = b1 - b0 + 1
        Pd = np.full((n, nb), np.nan)
        Pv = np.full((n, nb), np.nan)
        for r, (cue, _, _) in enumerate(rows):
            rel = I - cue
            sel = (rel > (b0 - 0.5) * S.HOP) & (rel < (b1 + 0.5) * S.HOP) & ~B
            j = np.round(rel[sel] / S.HOP).astype(int) - b0
            Pd[r, j] = np.where(D[sel] >= 0, 1.0, -1.0)
            Pv[r, j] = np.where(V[sel] >= 0, 1.0, -1.0)
        truth = np.where(cls == C.RIGHT, 1.0, -1.0)
        t = (np.arange(nb) + b0) * S.HOP / S.FS
        kd, kv = kappa_columns(Pd, truth), kappa_columns(Pv, truth)
        after = (t >= 0) & (t <= S.CURVE_T[1])
        res["curve_t"] = t.tolist()
        res["kappa_raw"] = np.nan_to_num(kd, nan=0.0).tolist()
        res["kappa_smoothed"] = np.nan_to_num(kv, nan=0.0).tolist()
        for key, kk in (("raw", kd), ("smoothed", kv)):
            if np.any(after & ~np.isnan(kk)):
                j = int(np.nanargmax(np.where(after, kk, np.nan)))
                res[f"max_kappa_{key}"] = float(kk[j])
                res[f"max_kappa_{key}_t"] = float(t[j])
        rng = np.random.default_rng(seed)
        mx = []
        for _ in range(n_perm):
            kp = kappa_columns(Pd, rng.permutation(truth))
            mx.append(np.nanmax(np.where(after, kp, np.nan)) if np.any(after & ~np.isnan(kp)) else 0.0)
        res["max_kappa_chance95"] = float(np.percentile(mx, 95))
        return res


def format_results(res, title="Results"):
    if not res.get("trials"):
        return f"{title}: no scored trials yet."
    cm = res["confusion"]
    lines = [
        f"{title}",
        f"Trials scored {res['trials']} (left {res['n_left']}, right {res['n_right']})"
        + (f", {res['excluded']} artifact trials left out" if res.get("excluded") else ""),
        f"Accuracy {100 * res['accuracy']:.1f} %  ({res['correct']}/{res['trials']}), "
        f"binomial p = {res['p']:.3g}  ->  {'ABOVE CHANCE' if res['p'] < 0.05 else 'not above chance'}",
        "Confusion (rows = cued, columns = decoded):",
        "             dec LEFT  dec RIGHT",
        f"  cued LEFT   {cm[0][0]:6d}   {cm[0][1]:7d}",
        f"  cued RIGHT  {cm[1][0]:6d}   {cm[1][1]:7d}",
    ]
    if "max_kappa_raw" in res:
        lines.append(f"Competition metric: max kappa {res['max_kappa_raw']:.2f} at {res['max_kappa_raw_t']:.2f} s "
                     f"after cue (raw output); smoothed {res.get('max_kappa_smoothed', float('nan')):.2f} "
                     f"at {res.get('max_kappa_smoothed_t', float('nan')):.2f} s")
        lines.append(f"  chance level for max kappa with this many trials (95 %): {res['max_kappa_chance95']:.2f}")
    return "\n".join(lines)
