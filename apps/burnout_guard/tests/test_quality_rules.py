import math

import pytest

from bguard.quality import AVERAGE, BAD, GOOD, ArtifactWindow, ContactGate, grade_resistance
from bguard.rules import BreakPlanner, SelfReportScheduler, StressEpisodes


@pytest.mark.parametrize("ohms,grade", [
    (499_999, GOOD), (500_000, AVERAGE), (1_000_000, AVERAGE), (1_000_001, BAD),
    (0, BAD), (-5, BAD), (math.inf, BAD), (math.nan, BAD), (None, BAD),
])
def test_grade_resistance_boundaries(ohms, grade):
    assert grade_resistance(ohms) == grade


def test_contact_gate_needs_continuous_hold_and_resets():
    gate = ContactGate(hold_s=5)
    ok = {"T3": 100_000, "T4": 700_000}
    gate.update(0, ok)
    gate.update(4.9, ok)
    assert not gate.is_open(4.9) and gate.progress(4.9) == pytest.approx(0.98)
    gate.update(5.0, {"T3": 100_000, "T4": 2_000_000})      # one bad reading resets
    assert gate.progress(5.0) == 0 and not gate.is_open(5.0)
    gate.update(6, ok)
    gate.update(11, ok)
    assert gate.is_open(11)
    assert not gate.all_good                                   # T4 only "average"


def test_contact_gate_empty_is_closed():
    gate = ContactGate(hold_s=0)
    gate.update(0, {})
    assert not gate.is_open(10)


def test_artifact_window_fraction_and_session_total():
    w = ArtifactWindow(window_s=10)
    for t in range(10):
        w.add(t, t % 2 == 0)
    assert w.fraction(9) == pytest.approx(0.5)
    assert not w.is_poor(9, threshold=0.5)
    w.add(20, True)                                           # old items fall out
    assert w.fraction(20) == 1.0 and w.is_poor(20)
    assert w.session_fraction == pytest.approx(6 / 11)


def P(**kw):
    """Planner with the anti-nagging limits switched off unless a test sets them."""
    base = dict(start=0, fatigue_score=70, sustain_s=180, min_live_s=0, work_block_s=10**9, min_break_s=120,
                min_gap_s=0, after_break_quiet_s=0, snooze_s=600, after_task_s=1200, max_per_day=99)
    base.update(kw)
    return BreakPlanner(**base)


def test_planner_fatigue_needs_sustain_and_min_session_time():
    r = P(min_live_s=600, min_gap_s=600)
    assert r.update(100, 90) is None                            # high, but session too young
    assert r.update(280, 90) is None                            # sustained 180 s, still < 600 s in
    assert r.update(599, 90) is None
    s = r.update(600, 90)
    assert s["kind"] == "fatigue" and s["minutes"] == 3
    assert r.update(601, 90) is None                            # one prompt at a time


def test_planner_dip_resets_fatigue_timer():
    r = P()
    r.update(0, 80)
    r.update(100, 60)                                           # dropped below threshold
    assert r.update(200, 80) is None
    assert r.update(380, 80) is not None


def test_planner_schedule_and_no_prompt_during_break():
    r = P(work_block_s=3000, after_break_quiet_s=2700)
    assert r.update(2999, 50) is None
    s = r.update(3000, 50)
    assert s["kind"] == "schedule" and "50 min without a break" in s["reason"]
    r.start_break(3010)                                         # starting a break accepts the prompt
    assert r.counts["accept"] == 1 and r.pending is None
    assert r.update(3500, 95) is None                           # never during a break
    assert r.end_break(3600) is True
    assert r.update(6299, 99) is None                           # 45 min quiet after a real break
    assert r.update(6600, 50)["kind"] == "schedule"             # fresh 50-min block from 3600
    assert P().update(10, math.nan) is None


def test_planner_short_break_does_not_reset_work_block():
    r = P(work_block_s=3000)
    r.start_break(1000)
    assert r.end_break(1002) is False                           # 2 s pause: recorded, not counted
    assert r.update(1500, 50) is None
    assert "50 min" in r.update(3000, 50)["reason"]             # still measured from 0


def test_planner_snooze_later_skip_and_backoff():
    r = P(work_block_s=3000, min_gap_s=1200, backoff_count=2)
    assert r.update(3000, 50)
    r.respond(3005, "snooze")
    assert r.update(3604, 50) is None and r.update(3605, 50)    # snooze = 10 min
    r.respond(3606, "later")
    assert r.update(4805, 50) is None and r.update(4806, 50)    # after this task = 20 min
    r.respond(4806, "skip")
    assert r.update(6005, 50) is None and r.update(6006, 50)    # gap 20 min after 1 skip
    r.respond(6006, "skip")                                     # 2 skips in a row → gap doubles
    assert r.update(8405, 50) is None and r.update(8406, 50)
    assert r.counts == {"prompts": 5, "accept": 0, "snooze": 1, "later": 1, "skip": 2, "ignored": 0}


def test_planner_unanswered_prompt_counts_as_ignored():
    r = P(work_block_s=3000, min_gap_s=1200)
    assert r.update(3000, 50)
    assert r.update(3599, 50) is None
    assert r.update(3600, 50) is None and r.counts["ignored"] == 1   # expired after 10 min
    assert r.update(4800, 50) is not None


def test_planner_daily_cap_and_mid_morning():
    r = P(work_block_s=600, max_per_day=2, prompts_today=1)
    assert r.update(600, 50)
    r.respond(601, "skip")
    assert r.update(10**6, 50) is None                          # cap of 2 reached (1 from earlier today)
    hours = {"h": 10.0}
    m = P(mid_morning_min_work_s=1800, hour_of=lambda t: hours["h"])
    assert m.update(2000, 50) is None                           # 10:00 → not yet
    hours["h"] = 11.2
    s = m.update(2001, 50)
    assert s["kind"] == "mid_morning"
    m.respond(2002, "skip")
    assert m.update(5000, 50) is None                           # only once a day
    assert P(mid_morning_min_work_s=0, hour_of=lambda t: 11.5, break_today=True).update(10, 50) is None


def test_planner_repeated_fatigue_suggests_longer_break():
    r = P()
    r.update(0, 90)
    assert r.update(180, 90)["minutes"] == 3
    r.respond(181, "skip")
    assert r.update(400, 90)["minutes"] == 10


def test_planner_fatigue_during_break_does_not_count():
    r = P()
    r.start_break(0)
    r.update(100, 90)                                           # high fatigue while resting
    r.end_break(200)
    assert r.update(201, 90) is None and r.update(380, 90) is None   # timer restarts after the break
    assert r.update(381, 90) is not None


def test_stress_episodes_hysteresis():
    ep = StressEpisodes(on=70, off=60, hold_s=15)
    assert [ep.update(t, 75) for t in (0, 10)] == [None, None]
    assert ep.update(15, 75) == "start" and ep.active
    assert ep.update(20, 65) is None                            # between off and on: stays active
    assert ep.update(30, 55) is None and ep.update(44, 55) is None
    assert ep.update(45, 55) == "end"
    assert ep.episodes == [[0, 30]]
    assert ep.update(50, math.nan) is None
    assert ep.total_s(100) == 30


def test_stress_episode_interrupted_candidate():
    ep = StressEpisodes(on=70, off=60, hold_s=15)
    ep.update(0, 80)
    ep.update(10, 50)                                           # dipped before hold time
    assert ep.update(20, 80) is None and ep.update(34, 80) is None
    assert ep.update(35, 80) == "start" and ep.episodes == [[20, None]]
    ep.close(40)
    assert ep.episodes == [[20, 40]] and not ep.active


def test_self_report_scheduler():
    s = SelfReportScheduler(start=0, interval_s=600, first_s=60)
    assert not s.due(59)
    assert s.due(60) and s.pending
    assert not s.due(700)                                     # already pending, no repeat
    s.answered(700)
    assert not s.due(1299) and s.due(1300)
