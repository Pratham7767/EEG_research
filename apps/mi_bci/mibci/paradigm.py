"""Trial schedule and timing, driven by the EEG sample clock.

The paradigm never looks at the wall clock: it advances when EEG samples arrive, so every
marker is stamped with the exact sample index at which the screen changed. (What the
Bluetooth delay does to that is logged separately; see Engine.)
"""
import numpy as np

from . import config as C


def make_schedule(n_per_class, seed=None, max_run=C.MAX_SAME_IN_A_ROW):
    """Balanced random left/right order with no more than max_run of one class in a row."""
    rng = np.random.default_rng(seed)
    for _ in range(10000):
        s = np.array([C.LEFT] * n_per_class + [C.RIGHT] * n_per_class)
        rng.shuffle(s)
        runs, ok = 1, True
        for a, b in zip(s[:-1], s[1:]):
            runs = runs + 1 if a == b else 1
            if runs > max_run:
                ok = False
                break
        if ok:
            return [int(v) for v in s]
    raise RuntimeError("could not build a schedule")


class Paradigm:
    """State machine for one run. tick(sample_idx) returns new events [(sample_idx, name, cls)].

    Phases: 'wait' (before run) -> per trial 'fixation' -> 'cue' -> 'task' -> 'rest' -> ... 'done'.
    'feedback' runs show the smiley from trial start; it moves only between cue and task_end.
    """

    def __init__(self, run_type, schedule, fs=C.FS, seed=None, lead_in_s=5.0):
        # 5 s before the first trial: the headphones need a few seconds to settle after the stream
        # starts (seen in the first real signal test, 2026-10-26)
        self.run_type = run_type
        self.t = C.TIMING[run_type]
        self.schedule = list(schedule)
        self.fs = fs
        self.rng = np.random.default_rng(seed)
        self.lead_in = int(lead_in_s * fs)
        self.trial = -1
        self.phase = "wait"
        self.trial_start = None
        self.next_change = None
        self.start_idx = None
        self.cls = None
        self._pending = []                  # remaining (offset_samples, event, phase) in this trial
        self.rest_len = 0

    def s(self, sec):
        return int(round(sec * self.fs))

    @property
    def done(self):
        return self.phase == "done"

    @property
    def feedback_active(self):
        return self.run_type == "feedback" and self.phase == "task"

    def _start_trial(self, idx):
        self.trial += 1
        if self.trial >= len(self.schedule):
            self.phase = "done"
            return [(idx, "run_end", None)]
        self.cls = self.schedule[self.trial]
        self.trial_start = idx
        t = self.t
        cue_ev = "cue_left" if self.cls == C.LEFT else "cue_right"
        self.rest_len = self.s(self.rng.uniform(*t["rest"]))
        plan = [(self.s(t["cue"]), cue_ev, "cue")]
        if self.run_type == "feedback":
            plan.append((self.s(t["cue"]), "feedback_start", "task"))
        else:
            plan.append((self.s(t["cue_off"]), "cue_off", "task"))
        plan.append((self.s(t["task_end"]), "task_end", "rest"))
        plan.append((self.s(t["task_end"]) + self.rest_len, None, "next"))
        if t["beep"] > 0:
            plan.insert(0, (self.s(t["beep"]), "beep", None))
        self._pending = sorted(plan, key=lambda p: p[0])
        self.phase = "fixation"
        ev = [(idx, "trial_start", self.cls)]
        if t["beep"] == 0:
            ev.append((idx, "beep", None))
        return ev

    def tick(self, idx):
        """Call with the index of the newest sample. Returns events that happen at or before it."""
        events = []
        if self.phase == "done":
            return events
        if self.phase == "wait":
            if self.start_idx is None:
                self.start_idx = idx
                events.append((idx, "run_start", None))
            if idx - self.start_idx < self.lead_in:
                return events
            events += self._start_trial(self.start_idx + self.lead_in)
        while self.phase != "done" and self._pending and \
                idx >= self.trial_start + self._pending[0][0]:
            off, ev, ph = self._pending.pop(0)
            at = self.trial_start + off
            if ph == "next":
                events += self._start_trial(at)
                continue
            if ev:
                events.append((at, ev, self.cls))
            if ph:
                self.phase = ph
        return events

    def ui_state(self):
        return dict(run_type=self.run_type, phase=self.phase, cls=self.cls, trial=self.trial,
                    n_trials=len(self.schedule))


BASELINE_BLOCKS = [("eyes_open", 60), ("eyes_closed", 60), ("blinks", 30), ("jaw", 30)]
BASELINE_TEXT = {
    "eyes_open": "Look at the cross. Relax, keep still.",
    "eyes_closed": "Close your eyes and relax until the high beep.",
    "blinks": "Blink normally, about once a second.",
    "jaw": "Clench your jaw for a second, relax, repeat.",
    "gap": "Get ready for the next block...",
}


class BaselineParadigm:
    """About 3 min of reference blocks: eyes open, eyes closed (alpha check), blinks and jaw clenches
    (to see what artifacts look like on our electrodes; we have no EOG channels to regress them)."""

    def __init__(self, blocks=BASELINE_BLOCKS, fs=C.FS, gap_s=4.0, scale=1.0):
        self.run_type = "baseline"
        self.blocks = [(n, int(d * scale * fs)) for n, d in blocks]
        self.gap = int(gap_s * fs)
        self.fs = fs
        self.plan = []
        self.start_idx = None
        self.phase, self.cls, self.trial = "wait", None, -1
        self.schedule = [b[0] for b in blocks]

    @property
    def done(self):
        return self.phase == "done"

    @property
    def feedback_active(self):
        return False

    def tick(self, idx):
        ev = []
        if self.start_idx is None:
            self.start_idx = idx
            ev.append((idx, "run_start", None))
            t = idx + self.gap
            for name, n in self.blocks:
                self.plan += [(t, f"{name}_start", name), (t + n, f"{name}_end", "gap")]
                t += n + self.gap
            self.plan.append((t - self.gap, "run_end", "done"))
            self.phase = "gap"
        while self.plan and idx >= self.plan[0][0]:
            s, name, ph = self.plan.pop(0)
            ev.append((s, name, None))
            self.phase = ph
            if name.endswith("_start"):
                self.trial += 1
        return ev

    def ui_state(self):
        return dict(run_type="baseline", phase=self.phase, cls=None, trial=self.trial,
                    n_trials=len(self.blocks), text=BASELINE_TEXT.get(self.phase, ""))


class RecordedParadigm:
    """Replays the events of a recorded run at their recorded sample indices (for replay checks)."""

    def __init__(self, run_type, events):
        self.run_type = run_type
        self.events = sorted(events, key=lambda e: e[0])
        self.i = 0
        self.phase, self.cls, self.trial = "wait", None, -1
        self.n = sum(1 for e in self.events if e[1] == "trial_start")

    @property
    def done(self):
        return self.i >= len(self.events)

    @property
    def feedback_active(self):
        return self.phase == "task"

    def tick(self, idx):
        out = []
        while self.i < len(self.events) and self.events[self.i][0] <= idx:
            e = self.events[self.i]
            self.i += 1
            out.append(e)
            name = e[1]
            if name == "trial_start":
                self.trial += 1
                self.cls, self.phase = e[2], "fixation"
            elif name in ("cue_left", "cue_right"):
                self.phase = "cue" if self.run_type != "feedback" else "task"
            elif name in ("cue_off", "feedback_start"):
                self.phase = "task"
            elif name == "task_end":
                self.phase = "rest"
            elif name == "run_end":
                self.phase = "done"
        return out

    def ui_state(self):
        return dict(run_type=self.run_type, phase=self.phase, cls=self.cls, trial=self.trial, n_trials=self.n)
