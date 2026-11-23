"""Pure signal-quality logic: electrode grading, contact gate, artifact window."""
import math
from collections import deque

from . import config

GOOD, AVERAGE, BAD = "good", "average", "bad"


def grade_resistance(ohms, good=config.RES_GOOD_OHM, average=config.RES_AVERAGE_OHM):
    """Capsule thresholds: < 500 kΩ good, ≤ 1 MΩ average, above that (or unreadable) bad."""
    try:
        ohms = float(ohms)
    except (TypeError, ValueError):
        return BAD
    if not math.isfinite(ohms) or ohms <= 0:
        return BAD
    if ohms < good:
        return GOOD
    if ohms <= average:
        return AVERAGE
    return BAD


class ContactGate:
    """Opens once every electrode has been acceptable for `hold_s` without a break."""

    def __init__(self, hold_s=config.CONTACT_HOLD_S):
        self.hold_s = hold_s
        self._ok_since = None
        self.grades = {}

    def update(self, now, resistances):
        """resistances: {electrode: ohms}. Returns the grade dict."""
        self.grades = {name: grade_resistance(v) for name, v in resistances.items()}
        all_ok = bool(self.grades) and all(g != BAD for g in self.grades.values())
        if not all_ok:
            self._ok_since = None
        elif self._ok_since is None:
            self._ok_since = now
        return self.grades

    def progress(self, now):
        if self._ok_since is None:
            return 0.0
        return min(1.0, (now - self._ok_since) / self.hold_s) if self.hold_s > 0 else 1.0

    def is_open(self, now):
        return self._ok_since is not None and now - self._ok_since >= self.hold_s

    @property
    def all_good(self):
        return bool(self.grades) and all(g == GOOD for g in self.grades.values())


class ArtifactWindow:
    """Fraction of artifact-flagged updates in the last `window_s` seconds."""

    def __init__(self, window_s=config.ARTIFACT_WINDOW_S):
        self.window_s = window_s
        self._items = deque()
        self.total = 0
        self.total_artifacted = 0

    def add(self, now, artifacted):
        artifacted = bool(artifacted)
        self._items.append((now, artifacted))
        self.total += 1
        self.total_artifacted += artifacted
        self._trim(now)

    def _trim(self, now):
        while self._items and now - self._items[0][0] > self.window_s:
            self._items.popleft()

    def fraction(self, now=None):
        if now is not None:
            self._trim(now)
        if not self._items:
            return 0.0
        return sum(a for _, a in self._items) / len(self._items)

    def is_poor(self, now=None, threshold=config.ARTIFACT_WARN_FRACTION):
        return self.fraction(now) > threshold

    @property
    def session_fraction(self):
        return self.total_artifacted / self.total if self.total else 0.0
