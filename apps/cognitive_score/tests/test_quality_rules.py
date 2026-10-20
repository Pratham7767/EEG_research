import math

import pytest

from cogscore.quality import AVERAGE, BAD, GOOD, ArtifactWindow, ContactGate, grade_resistance
from cogscore.rules import BreakRule, SelfReportScheduler, StressEpisodes


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


def test_break_rule_fatigue_needs_sustain_and_min_session_time():
    r = BreakRule(start=0, fatigue_score=70, sustain_s=180, min_live_s=600, work_block_s=10**9, cooldown_s=600)
    assert r.update(100, 90) is None                            # high, but session too young
    assert r.update(280, 90) is None                            # sustained 180 s, still < 600 s in
    assert r.update(599, 90) is None
    assert "Fatigue" in r.update(600, 90)                       # sustained since 100 s and past 10 min
    assert r.update(601, 90) is None                            # cooldown


def test_break_rule_dip_resets_fatigue_timer():
    r = BreakRule(start=0, fatigue_score=70, sustain_s=180, min_live_s=0, work_block_s=10**9)
    r.update(0, 80)
    r.update(100, 60)                                           # dropped below threshold
    assert r.update(200, 80) is None
    assert r.update(380, 80) is not None


def test_break_rule_work_block_and_break_suppression():
    r = BreakRule(start=0, fatigue_score=70, sustain_s=180, min_live_s=0, work_block_s=3000, cooldown_s=100)
    assert r.update(2999, 50) is None
    assert "50 min without a break" in r.update(3000, 50)
    r.start_break(3010)
    assert r.update(3500, 95) is None                           # never during a break
    r.end_break(3600)
    assert r.update(3650, 50) is None                           # cooldown + fresh work block
    assert r.update(6599, 50) is None and r.update(6600, 50) is not None
    assert BreakRule(start=0).update(10, math.nan) is None


def test_break_rule_short_break_does_not_reset_work_block():
    """Real session: a 1.5 s break restarted the 50-min timer. Now it must last ≥ min_break_s."""
    r = BreakRule(start=0, min_live_s=0, work_block_s=3000, cooldown_s=600, min_break_s=120)
    r.start_break(1000)
    assert r.end_break(1002) is False                           # 2 s pause: recorded, not counted
    assert r.update(1500, 50) is None                           # cooldown after the break
    assert "50 min" in r.update(3000, 50)                       # still measured from 0
    r.start_break(3100)
    assert r.end_break(3400) is True                            # 5 min break restarts the block
    assert r.update(6399, 50) is None and r.update(6400, 50) is not None


def test_break_rule_ignored_suggestion_repeats_after_cooldown():
    r = BreakRule(start=0, min_live_s=0, work_block_s=3000, cooldown_s=600)
    assert "50 min" in r.update(3000, 50)
    assert r.update(3599, 50) is None
    assert "60 min" in r.update(3600, 50)


def test_break_rule_fatigue_during_break_does_not_count():
    r = BreakRule(start=0, fatigue_score=70, sustain_s=180, min_live_s=0, work_block_s=10**9, cooldown_s=0)
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
    s = SelfReportScheduler(start=0, interval_s=600)
    assert not s.due(599)
    assert s.due(600) and s.pending
    assert not s.due(700)                                     # already pending, no repeat
    s.answered(700)
    assert not s.due(1299) and s.due(1300)
