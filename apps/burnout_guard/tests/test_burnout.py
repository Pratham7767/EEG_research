"""Burnout Guard additions: journal, questionnaires, trends/risk, recovery exercises."""
import datetime
import json
import math
import os
import time
import zipfile

import pytest

from bguard import questionnaires as q
from bguard import recovery, trends
from bguard.journal import Journal, local_date

DAY = 86400


@pytest.fixture
def jr(tmp_path):
    clock = {"t": time.mktime(datetime.datetime(2026, 11, 2, 10, 0).timetuple())}   # a Monday
    j = Journal(str(tmp_path / "data"), clock=lambda: clock["t"])
    return j, clock


# ── journal ──
def test_journal_append_read_and_nan_safe(jr):
    j, clock = jr
    j.add("kss", score=5)
    j.add("session", work_min=40.0, fatigue_mean=math.nan)
    with open(j.path, "a", encoding="utf-8") as fh:
        fh.write('{"type": "kss", "sc')                       # crash mid-write must not break reading
    assert [e["type"] for e in j.entries()] == ["kss", "session"]
    assert j.entries("session")[0]["fatigue_mean"] is None    # NaN stored as null (strict JSON)
    assert j.last("kss")["score"] == 5 and j.today("kss")
    clock["t"] += DAY
    assert j.today("kss") == []


def test_consent_settings_export_delete_retention(jr, tmp_path):
    j, clock = jr
    assert not j.has_consent()
    j.record_consent()
    assert j.has_consent()
    assert j.settings()["eye_rest"] is False
    j.save_settings(eye_rest=True)
    assert j.settings()["eye_rest"] is True
    sessions = os.path.join(j.data_dir, "sessions")
    old, new = os.path.join(sessions, "old"), os.path.join(sessions, "new")
    os.makedirs(old), os.makedirs(new)
    os.utime(old, (clock["t"] - 100 * DAY, clock["t"] - 100 * DAY))
    os.utime(new, (clock["t"], clock["t"]))
    assert j.apply_retention(sessions, days=90) == ["old"] and os.path.isdir(new)
    out = j.export_zip(str(tmp_path / "export.zip"))
    names = zipfile.ZipFile(out).namelist()
    assert "journal.jsonl" in names and "settings.json" in names
    j.delete_all()
    assert os.listdir(j.data_dir) == [] and not j.has_consent()


# ── questionnaires ──
def test_bat4_score_is_item_mean():
    assert q.score("BAT4", [0, 0, 0, 0])["score"] == 1.0          # never ×4
    assert q.score("BAT4", [4, 3, 2, 1])["score"] == 3.5
    with pytest.raises(ValueError):
        q.score("BAT4", [1, None, 1, 1])


def test_cbi_scoring_reverse_item_and_cutoff():
    best = [4] * 12 + [0]          # never tired …, "always" enough energy for family (reverse item)
    r = q.score("CBI", best)
    assert r["detail"] == {"personal": 0.0, "work": 0.0, "high_from": 50} and r["zone"] == "ok"
    worst = [0] * 12 + [4]
    assert q.score("CBI", worst)["detail"]["work"] == 100.0
    mid = [2] * 13                 # "sometimes"/"somewhat" everywhere = 50 → high
    assert q.score("CBI", mid)["zone"] == "high"
    with pytest.raises(ValueError):                         # fewer than 3 personal answers
        q.score("CBI", [None, None, None, None, 1, 1] + [1] * 7)


def test_who5_scoring():
    assert q.score("WHO5", [0] * 5)["score"] == 100             # "all of the time"
    r = q.score("WHO5", [3, 3, 3, 3, 2])                         # raw 2+2+2+2+3 = 11 → 44
    assert r["score"] == 44 and r["zone"] == "low"
    assert "not a diagnosis" in q.describe("WHO5", r)


def test_due_schedule():
    now = 100 * DAY
    assert q.due("BAT4", None, now, first_use_ts=now)            # weekly pulse from day one
    assert not q.due("CBI", None, now, first_use_ts=now)         # the long ones wait a day
    assert q.due("CBI", None, now, first_use_ts=now - 2 * DAY)
    assert not q.due("BAT4", now - 6 * DAY, now)
    assert q.due("BAT4", now - 7 * DAY + 1800, now)              # same weekday, a bit earlier


def test_items_are_unmodified_bat4():
    items = [t for t, _ in q.INSTRUMENTS["BAT4"]["items"]]
    assert items == ["At work, I feel mentally exhausted", "I struggle to find any enthusiasm for my work",
                     "When I'm working, I have trouble concentrating", "At work I may overreact unintentionally"]


# ── trends / risk ──
def _add_week(j, clock, bat4, weeks):
    for w in range(weeks):
        j.add("questionnaire", ts=clock["t"] + w * 7 * DAY, instrument="BAT4", score=bat4[w])


def test_assess_unknown_then_balanced(jr):
    j, clock = jr
    assert trends.assess(j.entries(), clock["t"])["level"] == "unknown"
    j.add("questionnaire", instrument="WHO5", score=72, zone="ok")
    assert trends.assess(j.entries(), clock["t"])["level"] == "balanced"


def test_assess_who5_low_and_cbi_high_mean_talk(jr):
    j, clock = jr
    j.add("questionnaire", instrument="WHO5", score=40, zone="low")
    a = trends.assess(j.entries(), clock["t"])
    assert a["level"] == "talk" and "14416" in a["advice"]
    assert trends.assess(j.entries(), clock["t"] + 30 * DAY)["level"] == "unknown"   # stale after 3 weeks


def test_assess_bat4_rise_vs_personal_baseline(jr):
    j, clock = jr
    _add_week(j, clock, [2.0, 2.25, 2.0, 2.0, 2.75, 2.75], 6)
    now = clock["t"] + 5 * 7 * DAY
    a = trends.assess(j.entries(), now)
    assert a["level"] == "watch" and "above your usual 2.00" in a["reasons"][0]
    _add_week(j, {"t": clock["t"] + 6 * 7 * DAY}, [2.75, 2.75], 2)
    assert trends.assess(j.entries(), clock["t"] + 8 * 7 * DAY)["level"] == "talk"


def test_hours_are_context_not_level(jr):
    j, clock = jr
    for d in range(6):
        j.add("session", ts=clock["t"] - d * DAY, work_min=600, real_breaks=1,
              prompts={"prompts": 4, "skip": 3})
    a = trends.assess(j.entries(), clock["t"] + 3600)
    assert a["level"] == "unknown"                              # hours alone never raise the level
    assert any("55 h" in c for c in a["context"]) and any("skipped" in c for c in a["context"])


def test_daily_rows(jr):
    j, clock = jr
    j.add("session", work_min=50, break_min=5, real_breaks=1, prompts={"prompts": 2, "accept": 1, "skip": 1},
          fatigue_mean=60.0, tension_mean=50.0)
    j.add("kss", score=6)
    j.add("day_checkin", energy=4, strain=7, breaks_ok=False)
    rows = trends.daily(j.entries(), 3, datetime.date.fromtimestamp(clock["t"]))
    assert [r["date"] for r in rows][-1] == local_date(clock["t"]) and len(rows) == 3
    today = rows[-1]
    assert (today["work_min"], today["breaks"], today["accepted"], today["kss"], today["strain"]) == (50, 1, 1, 6, 7)


# ── recovery ──
def test_exercise_phases_and_suggestion():
    assert recovery.cycle_seconds("resonance") == 10                 # 6 breaths per minute
    i, label, frac, left = recovery.phase_at("resonance", 13.0)
    assert (i, label, round(frac, 2), left) == (0, "Breathe in", 0.75, 1.0)
    assert recovery.phase_at("resonance", 15.0)[1] == "Breathe out"
    assert recovery.suggest("schedule", 3) == "mobility"
    assert recovery.suggest("fatigue", 3, done_today={"cyclic_sigh"}) == "resonance"
    assert all(set(e) >= {"name", "minutes", "phases", "steps", "evidence", "eeg"} for e in recovery.EXERCISES.values())


def test_relaxation_signal_compares_before_and_after():
    s = recovery.RelaxationSignal()
    for k in range(240):                                          # 2 min before the break at 2 Hz
        s.add(k * 0.5, 0.20)
    s.begin(120.0)
    for k in range(240):
        s.add(120 + k * 0.5, 0.26)
    assert s.end(240.0) == pytest.approx(30.0)
    assert "+30%" in recovery.describe_change(30.0) and "cannot prove" in recovery.describe_change(30.0)
    noisy = recovery.RelaxationSignal()
    noisy.begin(10.0)
    assert noisy.end(70.0) is None                                 # no clean data → no claim
