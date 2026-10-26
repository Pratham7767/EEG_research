"""The live pipeline. One output every 40 ms:

  raw A1, C3, C4, A2 (uV)
   -> montage C3-A1, C4-A2                                    (mibci.dsp.apply_montage)
   -> causal 50 Hz notch (as BCI IV 2b was recorded)          (milive.dsp_extra.Notch)
   -> per band: causal Butterworth band-pass, covariance of the last 2 s   (mibci.svm.CovWindow)
   -> Euclidean Alignment, per band. Default 'adaptive': reference = running mean of the covariances
      since the last calibration started, artifact windows skipped (causal, no labels)
   -> the model (CSP / tangent space ... + classifier) -> distance; negative = LEFT
   -> minus the bias = running mean of the clean outputs (no labels)
      'fixed' (adaptive off): the reference and bias are frozen (at the calibration, or when switched off)
   -> 2 s integrator: v = mean sign of the last 2 s of outputs, -1 (all left) .. +1 (all right)
   -> command: LEFT if v <= -threshold for hold_s, RIGHT if v >= +threshold for hold_s, else NEUTRAL;
      STOP if the signal has been an artifact for more than 0.5 s.

On BCI IV 2b E sessions (each subject unseen by its model) adaptive alignment beat a fixed 60 s
calibration: 75.6 % vs 71.3 % (tools/compare_alignment.py).
Samples are processed in pieces that end on output boundaries (as mibci.engine), so the outputs do not
depend on how Bluetooth packets are split.
"""
from collections import deque, namedtuple

import numpy as np

from mibci import config as C
from mibci.dsp import ArtifactCheck, apply_montage

from . import settings as S
from .dsp_extra import Notch
from .models import inv_sqrt, unflat

Out = namedtuple("Out", "i d v bad cmd rms")      # i = sample index of the window's last sample


class CommandLogic:
    def __init__(self, threshold=S.THRESHOLD, hold_s=S.HOLD_S, neutral=S.NEUTRAL,
                 artifact_stop_s=S.ARTIFACT_STOP_S):
        self.threshold, self.hold_s, self.neutral = threshold, hold_s, neutral
        self.artifact_stop_s = artifact_stop_s
        self.reset()

    def reset(self):
        self.cmd, self.cand, self.count, self.bad_run = "STOP", None, 0, 0

    def update(self, v, bad):
        if bad:
            self.bad_run += 1
            if self.bad_run * S.OUT_DT >= self.artifact_stop_s - 1e-9:
                self.cmd, self.cand, self.count = "STOP", None, 0
            return self.cmd
        self.bad_run = 0
        if v <= -self.threshold:
            cand = "LEFT"
        elif v >= self.threshold:
            cand = "RIGHT"
        else:
            cand = self.neutral
        if cand == self.cand:
            self.count += 1
        else:
            self.cand, self.count = cand, 1
        if self.count * S.OUT_DT >= self.hold_s - 1e-9:
            self.cmd = cand
        return self.cmd


class Calibration:
    """Blocks on the EEG sample clock. Keeps rows, outputs and block names (names only for the check)."""

    def __init__(self, start_n, blocks=S.CALIB_BLOCKS):
        self.plan, t = [], start_n
        for name, sec in blocks:
            n = int(round(sec * S.FS))
            self.plan.append((name, t, t + n))
            t += n
        self.start, self.end = start_n, t
        self.rows, self.labels, self.bad, self.raw = [], [], [], []

    def block_at(self, n):
        for name, a, b in self.plan:
            if a <= n < b:
                return name, (b - n) / S.FS
        return None, 0.0

    def add(self, i, row, bad, raw):
        name, _ = self.block_at(i)
        if name is not None:
            self.rows.append(np.asarray(row, float))
            self.labels.append(name)
            self.bad.append(bool(bad))
            self.raw.append(float(raw))

    def done(self, n):
        return n >= self.end

    def fraction(self, n):
        return min(1.0, max(0.0, (n - self.start) / max(1, self.end - self.start)))


class LivePipeline:
    def __init__(self, model, montage=None, bias_correct=True, adaptive=True):
        self.model = model
        self.montage = montage or model.montage or C.MONTAGE
        self.cw = model.make_extractor()
        self.notch = Notch(model.channel_idx)
        self.nb = len(model.bands)
        self.art = ArtifactCheck(model.channel_idx)
        self.integ = deque(maxlen=int(round(S.INTEGRATE_S / S.OUT_DT)))
        self.logic = CommandLogic()
        self.adaptive = adaptive
        self.bias_correct = bias_correct
        self.n = 0                      # samples fed so far = index of the next sample
        self.n_out = self.n_bad = 0
        self.calib = None
        self.calib_result = None
        self.calib_count = 0
        self.last = None
        self.reset_alignment()

    # ---------------------------------------------------------------- alignment state
    def reset_alignment(self):
        self._csum = np.zeros(3 * self.nb)
        self._cn = 0
        self._dsum, self._dn = 0.0, 0
        self.R_fixed = None             # list of per-band (2, 2) references when frozen
        self.bias_fixed = 0.0

    def running_reference(self):
        if self._cn == 0:
            return None
        m = self._csum / self._cn
        return [unflat(m[3 * b:3 * b + 3]) for b in range(self.nb)]

    def current_bias(self):
        if self.R_fixed is not None:
            return self.bias_fixed
        return self._dsum / self._dn if self._dn else 0.0

    def set_adaptive(self, on):
        """Off = freeze the alignment and bias as they are now. On = continue adapting from the running sums."""
        self.adaptive = bool(on)
        if not on and self._cn:
            self.R_fixed = self.running_reference()
            self.bias_fixed = self.current_bias()
        elif on:
            self.R_fixed = None

    def _raw(self, row, R):
        A = [(lambda P: P @ unflat(row[3 * b:3 * b + 3]) @ P)(inv_sqrt(R[b])) for b in range(self.nb)]
        return float(self.model.decide([a[None] for a in A])[0])

    def seed_alignment(self, rows):
        """Start the adaptive alignment from recorded clean covariance rows (n, 3 * n_bands) of today's
        calibration, so a newly trained model is aligned from its first output. No labels used."""
        rows = np.asarray(rows, float)
        self.reset_alignment()
        if rows.ndim != 2 or len(rows) == 0 or rows.shape[1] != 3 * self.nb:
            return False
        self._csum, self._cn = rows.sum(0), len(rows)
        R = self.running_reference()
        A = [(lambda P: P @ unflat(rows[:, 3 * b:3 * b + 3]) @ P)(inv_sqrt(R[b])) for b in range(self.nb)]
        raw = np.asarray(self.model.decide(A), float)
        self._dsum, self._dn = float(raw.sum()), len(raw)
        return True

    # ---------------------------------------------------------------- calibration
    def start_calibration(self, blocks=S.CALIB_BLOCKS):
        """Starts the alignment afresh (drops the settling seconds after connecting) and collects 60 s."""
        self.reset_alignment()
        self.integ.clear()
        self.logic.reset()
        self.calib = Calibration(self.n, blocks)
        return self.calib

    def _finish_calibration(self):
        cal, self.calib = self.calib, None
        self.calib_count += 1
        if len(cal.rows) < 50:
            self.calib_result = dict(ok=False, reason="too few outputs during calibration")
            return
        F = np.array(cal.rows)
        bad = np.array(cal.bad)
        good = ~bad if (~bad).sum() >= 50 else np.ones(len(bad), bool)
        if self.adaptive:
            d = np.array(cal.raw) - self.current_bias()
        else:                                     # freeze reference + bias from these 60 s
            m = F[good].mean(0)
            self.R_fixed = [unflat(m[3 * b:3 * b + 3]) for b in range(self.nb)]
            raw = np.array([self._raw(r, self.R_fixed) for r in F])
            self.bias_fixed = float(raw[good].mean())
            d = raw - self.bias_fixed
            self.integ.clear()
        lab = np.array(cal.labels)
        blocks = {}
        for name in dict.fromkeys(cal.labels):
            mm = (lab == name) & good
            if mm.any():
                blocks[name] = dict(mean_d=float(d[mm].mean()), frac_right=float(np.mean(d[mm] >= 0)), n=int(mm.sum()))
        res = dict(ok=True, mode="adaptive" if self.adaptive else "fixed", bias=self.current_bias(),
                   artifact_fraction=float(bad.mean()), blocks=blocks, seconds=(cal.end - cal.start) / S.FS)
        if "left" in blocks and "right" in blocks:
            ml, mr = (lab == "left") & good, (lab == "right") & good
            sd = np.sqrt((d[ml].var() + d[mr].var()) / 2) + 1e-12
            res["separation"] = float((d[mr].mean() - d[ml].mean()) / sd)
            res["block_accuracy"] = float((np.sum(d[ml] < 0) + np.sum(d[mr] >= 0)) / (ml.sum() + mr.sum()))
        self.calib_result = res
        self.logic.reset()

    # ---------------------------------------------------------------- streaming
    def feed(self, x):
        """x: (n, 4) new raw samples (uV), columns A1, C3, C4, A2. Returns the new outputs."""
        x = np.asarray(x, float)
        if x.ndim == 1:
            x = x[None, :]
        outs, pos = [], 0
        while pos < len(x):
            piece = x[pos:pos + C.HOP - (self.n % C.HOP)]
            outs += self._piece(piece)
            pos += len(piece)
        return outs

    def _piece(self, x):
        xm = self.notch.process(apply_montage(x, self.montage))
        self.art.push(xm)
        idx, F = self.cw.process(xm)
        self.n += len(x)
        outs = []
        for i, row in zip(idx, F):
            bad = self.art.check()
            if self.R_fixed is None and (not bad or self._cn == 0):
                self._csum += row
                self._cn += 1
            R = self.R_fixed if self.R_fixed is not None else self.running_reference()
            raw = self._raw(row, R)
            if self.R_fixed is None and not bad:
                self._dsum += raw
                self._dn += 1
            d = raw - (self.current_bias() if self.bias_correct else 0.0)
            if self.calib is not None:
                self.calib.add(int(i), row, bad, raw)
            self.n_out += 1
            if bad:
                self.n_bad += 1
            else:
                self.integ.append(1.0 if d >= 0 else -1.0)
            v = float(np.mean(self.integ)) if self.integ else 0.0
            cmd = self.logic.update(v, bad)
            k = 3 * self.model.rms_band
            rms = (float(np.sqrt(max(row[k], 0))), float(np.sqrt(max(row[k + 2], 0))))
            o = Out(int(i), d, v, bool(bad), cmd, rms)
            outs.append(o)
            self.last = o
        if self.calib is not None and self.calib.done(self.n):
            self._finish_calibration()
        return outs
