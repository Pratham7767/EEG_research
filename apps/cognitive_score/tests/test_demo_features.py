"""Demo / real modes, demo scenes, the infinite-resistance fix and the replay engine (no DLL)."""
import csv
import math
import os

import numpy as np
import pytest

from cogscore import config
from cogscore.monitor import scene_rows
from cogscore.rules import BreakRule, SelfReportScheduler, StressEpisodes
from tests.test_monitor import FREQS, FS, emotions, go_live_real, run, spectrum
from tests.test_monitor import rig  # noqa: F401,F811  (pytest fixture)


@pytest.fixture
def demo():
    config.apply_mode("demo")
    yield
    config.apply_mode("real")


@pytest.fixture(autouse=True)
def _always_restore_real():
    yield
    config.apply_mode("real")


# ── modes ─────────────────────────────────────────────────────────
def test_demo_mode_changes_only_timings():
    real = {k: getattr(config, k) for k in config.DEMO_OVERRIDES}
    formulas = (config.HIGH_BETA, config.RAW_BANDS, config.STRESS_EPISODE_ON, config.FATIGUE_BREAK_SCORE)
    config.apply_mode("demo")
    assert config.MODE == "demo" and config.WORK_REF_S == 60 and config.FATIGUE_MIN_LIVE_S == 180
    assert (config.HIGH_BETA, config.RAW_BANDS, config.STRESS_EPISODE_ON, config.FATIGUE_BREAK_SCORE) == formulas
    assert config.mode_settings()["mode"] == "demo"
    config.apply_mode("real")
    assert {k: getattr(config, k) for k in config.DEMO_OVERRIDES} == real
    with pytest.raises(ValueError):
        config.apply_mode("fast")


def test_rules_read_the_mode_at_creation(demo):
    """Defaults used to be frozen at import time, so a mode switch would have been ignored."""
    assert BreakRule(0).min_live_s == 180 and BreakRule(0).sustain_s == 30 and BreakRule(0).work_block_s == 360
    assert StressEpisodes().hold_s == 15
    assert SelfReportScheduler(0).interval_s == 240
    config.apply_mode("real")
    assert BreakRule(0).min_live_s == 600 and StressEpisodes().hold_s == 30 and SelfReportScheduler(0).interval_s == 600


def test_demo_break_prompt_comes_within_the_talk(demo, rig):
    """With the demo timings the sure (time-based) prompt arrives at 6 min even with low fatigue."""
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    run(clock, engine, 6 * 60 + 2, tick=mon.tick)
    assert got["break"] and "without a break" in got["break"][0]
    assert mon.stress_episodes.hold_s == 15               # monitor picked up the demo timings at live start


def test_demo_reference_after_one_minute(demo, rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    run(clock, engine, 55)
    assert not mon.reference_ready
    run(clock, engine, 7)
    assert mon.reference_ready


# ── scenes ────────────────────────────────────────────────────────
def test_scene_ends_by_itself_and_is_compared_with_rest(rig):
    clock, engine, mon, got = rig
    scenes = []
    mon.events.subscribe("scene", scenes.append)
    go_live_real(clock, engine, mon)
    assert not mon.start_scene("nope")
    assert mon.start_scene("rest", duration=20)
    run(clock, engine, 22, emo=emotions(40.0), tick=mon.tick)
    assert mon.scene is None and scenes == ["rest", None]
    mon.start_scene("mental_math", duration=20)
    run(clock, engine, 22, emo=emotions(80.0), tick=mon.tick)
    s = mon.summary()
    kinds = {k["key"]: k for k in s["scenes"]["by_kind"]}
    assert set(kinds) == {"rest", "mental_math"} and s["scenes"]["reference"]["label"] == "Rest"
    # settle: the first 5 s of each scene are skipped, so the means are clean
    assert kinds["rest"]["scores"]["attention"] == pytest.approx(40, abs=0.5)
    assert kinds["mental_math"]["scores"]["attention"] == pytest.approx(80, abs=0.5)
    ref, rows = scene_rows(s)
    assert ref == "Rest" and [r[0] for r in rows] == ["Mental math"]
    attention = rows[0][2][1]
    assert attention == pytest.approx(40, abs=1)
    assert [m[1] for m in s["markers"]] == ["Rest", "Mental math"]


def test_eyes_closed_scene_shows_alpha_increase(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    run(clock, engine, 10)
    mon.start_scene("eyes_closed", duration=20)
    rng = np.random.default_rng(3)
    n = int(FS * 0.5)
    for i in range(44):                                         # 22 s with a strong 10 Hz rhythm
        clock.t += 0.5
        t = (np.arange(n) + i * n) / FS
        raw = rng.normal(0, 20e-6, (n, 2)) + (25e-6 * np.sin(2 * np.pi * 10 * t))[:, None]
        engine.events.emit("eeg", list(range(n)), raw, raw)
        engine.events.emit("psd", FREQS, spectrum(), 0)
        engine.events.emit("emotions", emotions())
        mon.tick()
    run(clock, engine, 10)
    ref, rows = scene_rows(mon.summary())
    assert ref == "Rest of the session"
    alpha_pts = rows[0][2][0]
    assert rows[0][0] == "Eyes closed" and alpha_pts > 300


def test_check_in_waits_for_the_scene_and_break_ends_scene(demo, rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    run(clock, engine, config.SELF_REPORT_INTERVAL_S - 10, tick=mon.tick)
    mon.start_scene("relax", duration=45)
    run(clock, engine, 30, tick=mon.tick)
    assert got["kss"] == 0                                   # due, but a scene is running
    run(clock, engine, 20, tick=mon.tick)
    assert got["kss"] == 1                                   # scene over → check-in
    mon.start_scene("rest")
    mon.start_break()
    assert mon.scene is None and not mon.start_scene("rest")   # no scenes during a break


# ── bug fix: infinite resistance ─────────────────────────────────
def test_infinite_resistance_is_recorded_not_lost(rig):
    clock, engine, mon, got = rig
    engine.events.emit("resistances", {"A1": math.inf, "C3": 250_000.0, "T3": float("nan")})
    path = mon.session.path
    mon.close()
    with open(os.path.join(path, "resistances.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert {r["electrode"]: (r["ohms"], r["grade"]) for r in rows} == {
        "A1": ("inf", "bad"), "C3": ("250000", "good"), "T3": ("inf", "bad")}


# ── replay ────────────────────────────────────────────────────────
def _record(tmp_path):
    """A short real-flow session recorded by the Monitor (fake engine), to replay afterwards."""
    from cogscore.monitor import Monitor
    from tests.test_monitor import FakeClock, FakeEngine
    clock, engine = FakeClock(), FakeEngine()
    mon = Monitor(engine, sessions_root=str(tmp_path / "rec"), clock=clock,
                  wall_clock=lambda: 1_700_000_000 + clock.t)
    engine.events.emit("connected", {"serial": "X1", "channels": engine.channel_names, "sample_rate": FS})
    for t in range(3):
        clock.t += 1
        engine.events.emit("resistances", {"A1": 300_000.0, "C3": 200_000.0})
    go_live_real(clock, engine, mon)
    run(clock, engine, config.WORK_REF_S + 15, emo=emotions(70.0), tick=mon.tick)
    mon.start_scene("mental_math", duration=20)
    run(clock, engine, 30, psd=spectrum(high_beta=2.0), emo=emotions(85.0), tick=mon.tick)
    summary = mon.summary()
    mon.close()
    return mon.session.path, summary


def test_replay_reproduces_the_recorded_session(tmp_path):
    from cogscore import headless
    from cogscore.replay import list_sessions
    path, original = _record(tmp_path)
    assert [p for p, *_ in list_sessions(str(tmp_path / "rec"))] == [path]
    replay_path, replayed = headless.run(replay=path, virtual=True, live_seconds=10_000,
                                         sessions_root=str(tmp_path / "out"), log=lambda *_: None)
    problems = headless.check_session(replay_path)
    assert [p for p in problems if "productivity" not in p] == []      # the fake recording has no vendor stream
    for k in ("attention", "stress", "fatigue"):
        assert math.isfinite(original["scores"][k]["mean"]), k
        assert replayed["scores"][k]["mean"] == pytest.approx(original["scores"][k]["mean"], abs=2.0), k
    assert replayed["live_duration_s"] == pytest.approx(original["live_duration_s"], abs=2)
    assert [k["key"] for k in replayed["scenes"]["by_kind"]] == ["mental_math"]     # scene replayed too
    import json
    with open(os.path.join(replay_path, "session.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["replay_of"] == path and meta["device"]["simulated"] is True       # labelled as a replay
    assert list_sessions(str(tmp_path / "out")) == []                               # replays are not replayable


def test_replay_refuses_a_session_without_live_part(tmp_path):
    from cogscore.replay import ReplayEngine, ReplayError
    d = tmp_path / "s"
    d.mkdir()
    (d / "session.json").write_text("{}", encoding="utf-8")
    (d / "events.csv").write_text("unix_time,elapsed_s,kind,detail\n1,0,connected,\n", encoding="utf-8")
    with pytest.raises(ReplayError):
        ReplayEngine(str(d))
