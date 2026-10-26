"""The live loop: source -> sample clock -> band power -> artifact check -> LDA -> 2 s integrator,
with the paradigm advancing on the same sample clock and everything written to the recorder.

Samples are processed in pieces that end exactly on decoder-output boundaries, so the outputs do
not depend on how the Bluetooth packets happened to be split. That is what lets a recorded run
be replayed through this code and give bit-for-bit the same outputs as the offline trainer.
"""
import time

import numpy as np

from . import config as C
from .decoder import Integrator
from .dsp import ArtifactCheck, BandPower, apply_montage


class Engine:
    def __init__(self, source, paradigm, decoder=None, recorder=None, on_event=None):
        self.source, self.paradigm, self.decoder, self.rec = source, paradigm, decoder, recorder
        self.on_event = on_event
        self.n = 0                                   # samples seen = next sample index
        self.montage = (decoder.meta.get("montage") if decoder is not None else None) or C.MONTAGE
        self.bp = None
        if decoder is not None:
            self.bp = decoder.make_extractor()        # BandPower (LDA) or CovWindow (SVM)
        self.eval_win = tuple((decoder.meta.get("eval_win") if decoder is not None else None) or C.EVAL_WIN)
        self.art = ArtifactCheck([C.CHANNELS.index(c) for c in C.DECODE_CHANNELS])
        self.integ = Integrator()
        self.last_d = 0.0
        self.n_out = 0
        self.n_art = 0
        self.trial_cue = None
        self.trial_cls = None
        self.trial_signs = []
        self.results = []                            # per trial: cls, predicted, correct, error
        self.wall_start = None
        self.events = []

    # ------------------------------------------------------------------
    def _handle_events(self, evs):
        for s, name, cls in evs:
            self.events.append((s, name, cls))
            if self.rec:
                self.rec.event(s, name, cls)
            if name == "trial_start":
                self.integ.reset()
                self._close_trial()
            elif name in ("cue_left", "cue_right"):
                self.trial_cue, self.trial_cls, self.trial_signs = s, cls, []
            elif name == "run_end":
                self._close_trial()
            if self.on_event:
                self.on_event(s, name, cls)
        ph = self.paradigm.phase
        imagining = ph in ("cue", "task") and self.paradigm.cls is not None
        self.source.set_task(self.paradigm.cls if imagining else None)

    def _close_trial(self):
        if self.trial_cue is not None and self.trial_signs:
            m = float(np.mean(self.trial_signs))
            pred = C.RIGHT if m >= 0 else C.LEFT
            want = 1.0 if self.trial_cls == C.RIGHT else -1.0
            err = float(np.mean(np.array(self.trial_signs) != want))
            self.results.append(dict(cls=self.trial_cls, pred=pred, correct=pred == self.trial_cls, error=err,
                                     cue_sample=self.trial_cue))
        self.trial_cue, self.trial_signs = None, []

    def _process_piece(self, x):
        start = self.n
        xm = apply_montage(x, self.montage)
        self.art.push(xm)
        if self.bp is not None:
            idx, f = self.bp.process(xm)
            for i, row in zip(idx, f):
                bad = self.art.check()
                self.n_out += 1
                d = float(self.decoder.distance(row))
                if bad:
                    self.n_art += 1
                else:
                    self.last_d = d
                    self.integ.push(d)
                    if self.trial_cue is not None:
                        t = (i - self.trial_cue) / C.FS
                        if self.eval_win[0] <= t <= self.eval_win[1]:
                            self.trial_signs.append(1.0 if d >= 0 else -1.0)
                if self.rec:
                    self.rec.output(int(i), d, self.integ.value(), bad)
        self.n += len(x)
        self._handle_events(self.paradigm.tick(self.n - 1))
        return start

    def pump(self):
        """Process everything the source has delivered. Returns False when the run is over."""
        if self.wall_start is None:
            self.wall_start = time.perf_counter()
        x = self.source.read()
        if len(x):
            if self.rec:
                self.rec.eeg(x)
            pos = 0
            while pos < len(x):
                to_boundary = C.HOP - (self.n % C.HOP)
                piece = x[pos:pos + to_boundary]
                self._process_piece(piece)
                pos += len(piece)
        return not self.paradigm.done

    def state(self):
        s = self.paradigm.ui_state()
        s.update(integrated=self.integ.value(), distance=self.last_d, n_samples=self.n,
                 feedback_active=self.paradigm.feedback_active,
                 artifact_rate=self.n_art / self.n_out if self.n_out else 0.0,
                 results=self.results)
        return s

    def summary(self):
        res = self.results
        acc = float(np.mean([r["correct"] for r in res])) if res else None
        ice = float(np.mean([r["error"] for r in res])) if res else None
        wall = time.perf_counter() - self.wall_start if self.wall_start else None
        rate = self.n / wall if wall else None
        return dict(trials_scored=len(res), accuracy=acc, integrated_error=ice,
                    outputs=self.n_out, artifact_outputs=self.n_art, samples=self.n,
                    wall_seconds=wall, effective_rate_hz=rate)

    def finish(self, extra=None):
        self._close_trial()
        summ = self.summary()
        if self.rec:
            meta = dict(summary=summ, schedule=getattr(self.paradigm, "schedule", None),
                        source=self.source.name, source_status=self.source.status(),
                        decoder=self.decoder.to_dict() if self.decoder else None)
            meta.update(extra or {})
            self.rec.close(meta)
        return summ
