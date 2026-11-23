"""Pure session rules: when to suggest a break, tension episodes, when to ask for a self-report."""
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


class BreakPlanner:
    """Decides when to suggest a break. Research basis: research_notes/break_timing.md.

    Triggers (first match wins):
      * fatigue  - the fatigue score stays >= `fatigue_score` for `sustain_s`, after the first
                   `min_live_s` of the session (theta/alpha rise with time on task);
      * schedule - `work_block_s` since the session start or the last real break (HSE: short,
                   frequent breaks; a pause shorter than `min_break_s` is not a break);
      * mid_morning - by `mid_morning_hour` you have worked >= `mid_morning_min_work_s` and had
                   no real break today (mid-morning breaks restore more than late ones).

    Anti-nagging (users decline ~1/3 of prompts and ignore ~1/4; prompt fatigue is real):
      * one prompt at a time; an unanswered prompt counts as skipped after `snooze_s`;
      * >= `min_gap_s` between prompts (doubled after `backoff_count` skips in a row);
      * `after_break_quiet_s` of quiet after a real break, `max_per_day` prompts per day;
      * the user can Snooze (`snooze_s`), choose "After this task" (`after_task_s`) or Skip.
    Never silent forever: the schedule rule still fires after the gap, so a long stretch
    without breaks is always pointed out.
    """

    def __init__(self, start, fatigue_score=config.FATIGUE_BREAK_SCORE,
                 sustain_s=config.FATIGUE_BREAK_SUSTAIN_S, min_live_s=config.FATIGUE_MIN_LIVE_S,
                 work_block_s=config.WORK_BLOCK_S, min_break_s=config.MIN_BREAK_S,
                 min_gap_s=config.MIN_PROMPT_GAP_S, after_break_quiet_s=config.AFTER_BREAK_QUIET_S,
                 snooze_s=config.SNOOZE_S, after_task_s=config.AFTER_TASK_S,
                 max_per_day=config.MAX_PROMPTS_PER_DAY, backoff_count=config.DECLINE_BACKOFF_COUNT,
                 mid_morning_hour=config.MID_MORNING_HOUR,
                 mid_morning_min_work_s=config.MID_MORNING_MIN_WORK_S,
                 prompts_today=0, break_today=False, hour_of=None):
        self.start = start
        self.fatigue_score, self.sustain_s, self.min_live_s = fatigue_score, sustain_s, min_live_s
        self.work_block_s, self.min_break_s = work_block_s, min_break_s
        self.min_gap_s, self.after_break_quiet_s = min_gap_s, after_break_quiet_s
        self.snooze_s, self.after_task_s = snooze_s, after_task_s
        self.max_per_day, self.backoff_count = max_per_day, backoff_count
        self.mid_morning_hour, self.mid_morning_min_work_s = mid_morning_hour, mid_morning_min_work_s
        self.hour_of = hour_of                  # callable(now) -> local hour (float); None = rule off
        self.prompts_today = prompts_today
        self.break_today = break_today
        self.in_break = False
        self.pending = None                     # the suggestion currently on screen
        self.history = []                       # [(t, kind, response)]
        self.counts = {"prompts": 0, "accept": 0, "snooze": 0, "later": 0, "skip": 0, "ignored": 0}
        self._break_since = None
        self._work_since = start
        self._high_since = None
        self._quiet_until = -math.inf
        self._skips_in_row = 0
        self._mid_morning_done = False
        self._last_kind = None

    # ── breaks ──
    def start_break(self, now):
        if self.pending:
            self.respond(now, "accept")
        self.in_break = True
        self._break_since = now
        self._high_since = None

    def end_break(self, now):
        """Returns True when the break was long enough to count as a real break."""
        self.in_break = False
        self._high_since = None
        counted = now - self._break_since >= self.min_break_s
        if counted:
            self._work_since = now
            self.break_today = True
            self._quiet_until = max(self._quiet_until, now + self.after_break_quiet_s)
        else:
            self._quiet_until = max(self._quiet_until, now + self.snooze_s)
        return counted

    def work_minutes(self, now):
        return (now - self._work_since) / 60.0

    # ── prompts ──
    def respond(self, now, action):
        """action: accept | snooze | later | skip | ignored."""
        if self.pending is None:
            return
        self.history.append((now, self.pending["kind"], action))
        self.counts[action] += 1
        self.pending = None
        if action == "accept":
            self._skips_in_row = 0
        elif action == "snooze":
            self._quiet_until = now + self.snooze_s
        elif action == "later":
            self._quiet_until = now + self.after_task_s
        else:                                   # skip / ignored
            self._skips_in_row += 1
            self._quiet_until = now + self._gap()

    def _gap(self):
        return self.min_gap_s * (2 if self._skips_in_row >= self.backoff_count else 1)

    def update(self, now, fatigue=None):
        """Returns a suggestion dict {kind, reason, minutes} when a break should be suggested."""
        if self.in_break:
            self._high_since = None
            return None
        if fatigue is not None and math.isfinite(fatigue) and fatigue >= self.fatigue_score:
            if self._high_since is None:
                self._high_since = now
        else:
            self._high_since = None

        if self.pending is not None:
            if now - self.pending["t"] >= self.snooze_s:
                self.respond(now, "ignored")
            return None
        if now < self._quiet_until or self.prompts_today >= self.max_per_day:
            return None

        worked = now - self._work_since
        kind = None
        if (self._high_since is not None and now - self._high_since >= self.sustain_s
                and now - self.start >= self.min_live_s):
            kind = "fatigue"
            reason = "Your fatigue signal has stayed high for several minutes"
        elif worked >= self.work_block_s:
            kind = "schedule"
            reason = f"{int(worked // 60)} min without a break"
        elif (self.hour_of is not None and not self._mid_morning_done and not self.break_today
              and worked >= self.mid_morning_min_work_s
              and self.mid_morning_hour <= self.hour_of(now) < self.mid_morning_hour + 1):
            kind = "mid_morning"
            reason = "No break yet this morning; a mid-morning break restores the most"
        if kind is None:
            return None
        if kind == "mid_morning":
            self._mid_morning_done = True
        longer = kind == "fatigue" and self._last_kind == "fatigue"
        minutes = config.LONGER_BREAK_MIN if longer else config.MICRO_BREAK_MIN
        self._last_kind = kind
        self.prompts_today += 1
        self.counts["prompts"] += 1
        self._quiet_until = now + self._gap()
        self.pending = {"t": now, "kind": kind, "reason": reason, "minutes": minutes}
        return dict(self.pending)


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
    """KSS check-in: once `first_s` after the session starts, then every `interval_s`
    after the last answer (1-3 short prompts a day keep experience-sampling compliance high)."""

    def __init__(self, start, interval_s=config.SELF_REPORT_INTERVAL_S, first_s=config.SELF_REPORT_FIRST_S):
        self.interval_s = interval_s
        self._last = start
        self._next_gap = first_s
        self._pending = False

    def due(self, now):
        """True once per interval (stays pending until answered or skipped)."""
        if not self._pending and now - self._last >= self._next_gap:
            self._pending = True
            return True
        return False

    @property
    def pending(self):
        return self._pending

    def answered(self, now):
        self._pending = False
        self._last = now
        self._next_gap = self.interval_s
