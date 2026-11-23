"""Guided recovery exercises for breaks, and an honest EEG "relaxation signal".

Research basis: research_notes/recovery_exercises.md.
    * Slow breathing (~5-6 breaths/min): small reliable effects on stress (g = -0.35) and anxiety
      (Fincham 2023); raises HRV during and after (Laborde 2022).
    * Cyclic sighing beat mindfulness on positive mood in one 28-day RCT (Balban 2023).
    * Micro-breaks <= 10 min: more vigour, less fatigue (Albulescu 2022); a 40 s view of greenery
      helped attention (Lee 2015); 20-20-20 helped eye strain only while it was used.
    * EEG cannot prove recovery: alpha rises with relaxation, with closed eyes AND with fatigue, and a
      rest break restored reaction time without an EEG change (Wang 2022). So the app compares the
      minute before the break with the last minute of an eyes-open exercise, calls the result a
      "relaxation signal vs before", and always asks how refreshed you feel.
Safety: gentle breathing only, no breath holds required, no hyperventilation; stop if dizzy.
"""
import math

# Each phase: (label, seconds). A cycle repeats until the duration is reached.
EXERCISES = {
    "cyclic_sigh": {
        "name": "Cyclic sigh",
        "minutes": 5,
        "phases": [("Breathe in through the nose", 3.0), ("Top up with a short second sniff", 1.0),
                   ("Long, slow breath out through the mouth", 6.0)],
        "steps": "Two inhales through the nose (the second one short), then a long, relaxed exhale. "
                 "Gentle, not deep. Two minutes already help.",
        "evidence": "Moderate: beat mindfulness on positive mood in a 28-day trial (Balban et al. 2023).",
        "eeg": True,
    },
    "resonance": {
        "name": "Slow breathing 4-6",
        "minutes": 5,
        "phases": [("Breathe in", 4.0), ("Breathe out", 6.0)],
        "steps": "In for 4 seconds, out for 6: six breaths a minute. Keep it soft and quiet.",
        "evidence": "Moderate: small reliable drop in stress (Fincham et al. 2023); raises heart-rate "
                    "variability (Laborde et al. 2022).",
        "eeg": True,
    },
    "box": {
        "name": "Gentle box breathing",
        "minutes": 4,
        "phases": [("Breathe in", 4.0), ("Hold (optional)", 4.0), ("Breathe out", 4.0), ("Hold (optional)", 4.0)],
        "steps": "In 4, hold 4, out 4, hold 4. Skip the holds if they feel uncomfortable.",
        "evidence": "Low-moderate: similar effects to other slow breathing in one trial.",
        "eeg": True,
    },
    "eyes_closed": {
        "name": "Eyes-closed reset",
        "minutes": 5,
        "phases": [("Eyes closed. Notice your feet and legs", 30.0), ("Notice your hands and shoulders", 30.0),
                   ("Let your jaw and face soften", 30.0), ("Just rest and breathe", 30.0)],
        "steps": "Close your eyes and slowly scan the body. A tone tells you when the time is up.",
        "evidence": "Low-moderate: short rest and body scans reduce felt fatigue.",
        "eeg": False,           # closing the eyes raises alpha by itself: not comparable with work
    },
    "green_window": {
        "name": "Look far away (20-20-20)",
        "minutes": 1,
        "phases": [("Look at something at least 6 m away, ideally green", 20.0), ("Blink slowly", 10.0)],
        "steps": "Look out of a window or across the room at something far away. Plants or trees are best.",
        "evidence": "Low-moderate: a 40-second green view helped attention (Lee et al. 2015); "
                    "20-20-20 eased eye strain while used.",
        "eeg": False,
    },
    "mobility": {
        "name": "Desk stretch and walk",
        "minutes": 3,
        "phases": [("Stand up and roll your shoulders", 30.0), ("Stretch arms overhead", 30.0),
                   ("Turn your head slowly left and right", 30.0), ("Walk around, fetch some water", 90.0)],
        "steps": "Get up and move. Take the headphones off if you like; the signal is not used here.",
        "evidence": "Moderate for energy and fatigue (micro-break meta-analysis, Albulescu et al. 2022).",
        "eeg": False,           # movement ruins EEG
    },
}
ORDER = ["cyclic_sigh", "resonance", "box", "eyes_closed", "green_window", "mobility"]
REFRESH_LABELS = {1: "Not at all", 2: "A little", 3: "Somewhat", 4: "Quite", 5: "Very refreshed"}


def cycle_seconds(exercise_id):
    return sum(s for _, s in EXERCISES[exercise_id]["phases"])


def phase_at(exercise_id, t):
    """(phase index, phase label, fraction of the phase done, seconds left in the phase) at time t."""
    phases = EXERCISES[exercise_id]["phases"]
    t = t % cycle_seconds(exercise_id)
    for i, (label, sec) in enumerate(phases):
        if t < sec:
            return i, label, t / sec, sec - t
        t -= sec
    label, sec = phases[-1]
    return len(phases) - 1, label, 1.0, 0.0


def suggest(kind, minutes, done_today=()):
    """Pick an exercise for a break suggestion: long sitting -> move; fatigue -> breathing.
    Rotates so the same one is not offered every time."""
    if kind == "schedule":
        prefs = ["mobility", "green_window", "resonance"]
    elif kind == "fatigue":
        prefs = ["cyclic_sigh", "resonance", "mobility"] if minutes <= 5 else ["eyes_closed", "mobility", "resonance"]
    else:
        prefs = ["mobility", "cyclic_sigh", "green_window"]
    for p in prefs:
        if p not in done_today:
            return p
    return prefs[0]


class RelaxationSignal:
    """Median relative alpha in the minute before the break vs the last minute of an eyes-open exercise.
    Feed `add(t, rel_alpha, clean)` continuously; mark the exercise with `begin(t)` / `end(t)`."""

    WINDOW_S = 60.0
    MIN_SAMPLES = 20                 # >= 10 s of clean 2 Hz spectra

    def __init__(self):
        self._buf = []               # (t, alpha) clean samples, last few minutes
        self.before = None
        self._start = None

    def add(self, t, rel_alpha, clean=True):
        if clean and rel_alpha is not None and math.isfinite(rel_alpha) and rel_alpha > 0:
            self._buf.append((t, rel_alpha))
        cutoff = t - 600
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.pop(0)

    def _median(self, t0, t1):
        vals = sorted(a for t, a in self._buf if t0 <= t < t1)
        if len(vals) < self.MIN_SAMPLES:
            return None
        n = len(vals)
        return vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])

    def begin(self, t):
        self._start = t
        self.before = self._median(t - self.WINDOW_S, t)

    def end(self, t):
        """Percent change of relative alpha (None if either window was too noisy)."""
        if self._start is None or self.before is None:
            return None
        after = self._median(max(self._start, t - self.WINDOW_S), t)
        if after is None:
            return None
        return 100.0 * (after / self.before - 1.0)


def describe_change(pct):
    if pct is None:
        return "Not enough clean signal to compare (that is fine; how you feel matters more)."
    if pct >= 10:
        word = "higher"
    elif pct <= -10:
        word = "lower"
    else:
        word = "about the same"
    return (f"Relaxation signal (alpha) {pct:+.0f}% vs the minute before: {word}. "
            f"EEG cannot prove recovery; use it alongside how you feel.")
