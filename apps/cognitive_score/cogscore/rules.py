"""Pure session rules: when to suggest a break, when to ask for a self-report."""
import math

from . import config

# Productivity_RecommendationValue codes (Productivity.py / vendor docs)
RECOMMENDATIONS = {
    0: "No recommendation",
    1: "Involvement",
    2: "Relaxation",
    3: "Slight fatigue",
    4: "Severe fatigue",
    5: "Chronic fatigue",
}
FATIGUE_RECOMMENDATIONS = {3, 4, 5}

# Productivity_StressValue codes
STRESS_LEVELS = {0: "No stress", 1: "Anxiety", 2: "Stress"}

# Productivity_FatigueGrowthRate codes
GROWTH_RATES = {0: "None", 1: "Low", 2: "Medium", 3: "High"}

# Karolinska Sleepiness Scale labels
KSS_LABELS = {
    1: "Extremely alert", 2: "Very alert", 3: "Alert", 4: "Rather alert",
    5: "Neither alert nor sleepy", 6: "Some signs of sleepiness",
    7: "Sleepy, no effort to stay awake", 8: "Sleepy, some effort to stay awake",
    9: "Very sleepy, fighting sleep",
}


class BreakRule:
    """Suggest a break when
      * the fatigue score stays ≥ `fatigue_score` for `sustain_s` (after the first
        `min_live_s` of the session: theta/alpha rise with time on task), or
      * `work_block_s` have passed since the session start or the last real break
        (one lasting at least `min_break_s`; a 2-second pause is not a break).

    Silent during a break and for `cooldown_s` after a suggestion or a break; an ignored
    suggestion therefore repeats every `cooldown_s`. Fatigue measured during a break does
    not count towards the next suggestion.
    (The vendor's accumulated-fatigue counter is not used: in real sessions it grew at
    its maximum rate whenever the baseline concentration was above 1.7 and reached
    6/10 within 3 minutes.)
    """

    def __init__(self, start, fatigue_score=config.FATIGUE_BREAK_SCORE,
                 sustain_s=config.FATIGUE_BREAK_SUSTAIN_S, min_live_s=config.FATIGUE_MIN_LIVE_S,
                 work_block_s=config.WORK_BLOCK_S, cooldown_s=config.BREAK_COOLDOWN_S,
                 min_break_s=config.MIN_BREAK_S):
        self.start = start
        self.fatigue_score, self.sustain_s, self.min_live_s = fatigue_score, sustain_s, min_live_s
        self.work_block_s, self.cooldown_s, self.min_break_s = work_block_s, cooldown_s, min_break_s
        self.in_break = False
        self._break_since = None
        self._work_since = start
        self._high_since = None
        self._quiet_until = -math.inf

    def start_break(self, now):
        self.in_break = True
        self._break_since = now
        self._high_since = None

    def end_break(self, now):
        """Returns True when the break was long enough to restart the work block."""
        self.in_break = False
        self._high_since = None
        self._quiet_until = now + self.cooldown_s
        counted = now - self._break_since >= self.min_break_s
        if counted:
            self._work_since = now
        return counted

    def work_minutes(self, now):
        return (now - self._work_since) / 60.0

    def update(self, now, fatigue=None):
        """Returns a short reason when a break should be suggested, else None."""
        if self.in_break:
            self._high_since = None
            return None
        if fatigue is not None and math.isfinite(fatigue) and fatigue >= self.fatigue_score:
            if self._high_since is None:
                self._high_since = now
        else:
            self._high_since = None

        if now < self._quiet_until:
            return None
        reason = None
        if (self._high_since is not None and now - self._high_since >= self.sustain_s
                and now - self.start >= self.min_live_s):
            reason = "Fatigue has been high for several minutes"
        elif now - self._work_since >= self.work_block_s:
            reason = f"{int((now - self._work_since) // 60)} min without a break"
        if reason:
            self._quiet_until = now + self.cooldown_s
        return reason


class StressEpisodes:
    """Hysteresis detector: an episode starts when the score stays ≥ `on` for `hold_s`
    and ends when it stays < `off` for `hold_s`. Episodes are [start, end] in session seconds."""

    def __init__(self, on=config.STRESS_EPISODE_ON, off=config.STRESS_EPISODE_OFF,
                 hold_s=config.STRESS_EPISODE_HOLD_S):
        self.on, self.off, self.hold_s = on, off, hold_s
        self.active = False
        self.episodes = []
        self._candidate = None

    def update(self, t, score):
        """Returns "start", "end" or None."""
        if score is None or not math.isfinite(score):
            self._candidate = None
            return None
        crossing = score < self.off if self.active else score >= self.on
        if not crossing:
            self._candidate = None
            return None
        if self._candidate is None:
            self._candidate = t
        if t - self._candidate < self.hold_s:
            return None
        began, self._candidate = self._candidate, None
        if self.active:
            self.active = False
            self.episodes[-1][1] = began
            return "end"
        self.active = True
        self.episodes.append([began, None])
        return "start"

    def close(self, t):
        if self.active:
            self.episodes[-1][1] = t
            self.active = False

    def total_s(self, now):
        return sum((end if end is not None else now) - start for start, end in self.episodes)


class SelfReportScheduler:
    """Due every `interval_s` since the session started or the last answer."""

    def __init__(self, start, interval_s=config.SELF_REPORT_INTERVAL_S):
        self.interval_s = interval_s
        self._last = start
        self._pending = False

    def due(self, now):
        """True once per interval (stays pending until answered or skipped)."""
        if not self._pending and now - self._last >= self.interval_s:
            self._pending = True
            return True
        return False

    @property
    def pending(self):
        return self._pending

    def answered(self, now):
        self._pending = False
        self._last = now
