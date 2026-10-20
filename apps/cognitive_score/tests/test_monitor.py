"""Monitor driven by a fake engine: no DLL, deterministic clock."""
import csv
import math
import os

import numpy as np
import pytest

from cogscore import config
from cogscore.events import EventBus
from cogscore.monitor import Monitor

FS = 250.0


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeEngine:
    def __init__(self):
        self.events = EventBus()
        self.calibration = None
        self.baseline = None
        self.channel_names = ["A1-C3", "A2-C4"]
        self.sample_rate = FS
        self.record_eeg = False
        self.ppg_seen = False


FREQS = np.round(np.arange(1.0, 30.01, 0.1), 2)


def spectrum(high_beta=1.0, theta=1.0):
    """SDK-like spectrum: flat 1 except scaled theta and 20-30 Hz."""
    s = np.ones_like(FREQS)
    s[(FREQS >= 4) & (FREQS < 7)] *= theta
    s[(FREQS >= 20) & (FREQS <= 30)] *= high_beta
    return np.vstack([s, s])


def emotions(attention=60.0):
    return {"sdk_ms": 1, "attention": attention, "relaxation": 40.0, "cognitive_load": 30.0,
            "cognitive_control": 20.0, "self_control": 10.0}


@pytest.fixture
def rig(tmp_path):
    clock, engine = FakeClock(), FakeEngine()
    mon = Monitor(engine, sessions_root=tmp_path, clock=clock, wall_clock=lambda: 1_700_000_000 + clock.t)
    got = {"scores": [], "quality": [], "break": [], "kss": 0, "warn": [], "episode": []}
    mon.events.subscribe("scores", got["scores"].append)
    mon.events.subscribe("quality", lambda g, p, o: got["quality"].append((g, p, o)))
    mon.events.subscribe("break_suggested", got["break"].append)
    mon.events.subscribe("signal_warning", got["warn"].append)
    mon.events.subscribe("stress_episode", got["episode"].append)

    def _kss():
        got["kss"] += 1
    mon.events.subscribe("self_report_due", _kss)
    engine.events.emit("connected", {"serial": "X1", "channels": engine.channel_names, "sample_rate": FS,
                                     "simulated": True})
    return clock, engine, mon, got


def run(clock, engine, seconds, psd=None, emo=None, rng=None, eeg_scale=20e-6, step=0.5, tick=None):
    """Advance the fake session: every `step` s emit one PSD frame, emotions and `step` s of raw EEG."""
    rng = rng or np.random.default_rng(0)
    n = int(FS * step)
    for _ in range(int(round(seconds / step))):
        clock.t += step
        raw = rng.normal(0, eeg_scale, (n, 2))
        engine.events.emit("eeg", list(range(n)), raw, raw)
        engine.events.emit("psd", FREQS, psd if psd is not None else spectrum(), 0)
        engine.events.emit("emotions", emo or emotions())
        if tick:
            tick()


def go_live_real(clock, engine, mon, baseline_s=30):
    """Real flow: baseline step with data, then live."""
    engine.calibration = {"iapf": 10.0, "fail_reason": 0}
    engine.events.emit("calibrated", engine.calibration)
    engine.events.emit("state", "calibrated", "baseline")
    run(clock, engine, baseline_s)
    engine.baseline = {"concentration": 1.0, "relaxation": 1.0, "imported": False}
    engine.events.emit("baseline", engine.baseline)


def test_quality_gate_opens_after_hold(rig):
    clock, engine, mon, got = rig
    for t in range(0, 7):
        clock.t = t
        engine.events.emit("resistances", {"T3": 200_000.0, "T4": 300_000.0})
    grades, progress, is_open = got["quality"][-1]
    assert grades == {"T3": "good", "T4": "good"} and is_open and progress == 1.0


def work(clock, engine, mon):
    """Real flow up to the end of the 2-min working-level reference."""
    go_live_real(clock, engine, mon)
    run(clock, engine, config.WORK_REF_S + 1)
    assert mon.reference_ready


def test_stress_waits_for_working_reference_then_50_at_reference(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    assert mon.band_base.frozen is not None and not mon.reference_ready   # bands: rest; stress: not yet
    run(clock, engine, 60)
    snap = got["scores"][-1]
    assert math.isnan(snap["stress"]) and not snap["reference_ready"]
    assert snap["reference_remaining_s"] == pytest.approx(config.WORK_REF_S - 60, abs=1)
    run(clock, engine, config.WORK_REF_S - 60 + 1)
    assert mon.reference_ready
    run(clock, engine, 30)
    snap = got["scores"][-1]
    assert snap["stress"] == pytest.approx(50, abs=0.5)         # unchanged spectrum → reference level
    assert snap["fatigue"] == pytest.approx(50, abs=0.5)
    assert snap["attention"] == pytest.approx(60)
    assert snap["levels"]["stress"] == "Moderate"
    assert all(abs(v) < 25 for v in snap["bands_change"].values())   # white noise stays near its baseline


def test_breaks_pause_the_working_reference(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    run(clock, engine, 60)
    mon.start_break()
    run(clock, engine, 300)
    mon.end_break()
    assert not mon.reference_ready
    assert mon.reference_remaining() == pytest.approx(config.WORK_REF_S - 60, abs=1)
    run(clock, engine, config.WORK_REF_S - 60 + 1)
    assert mon.reference_ready


def test_stress_rises_with_high_beta_and_episode_is_marked(rig):
    clock, engine, mon, got = rig
    work(clock, engine, mon)
    run(clock, engine, 70, psd=spectrum(high_beta=3.0))         # arousal ratio ×~2.4 over the reference
    snap = got["scores"][-1]
    assert snap["stress"] > 85 and snap["levels"]["stress"] == "High"
    assert got["episode"] == [True] and snap["stress_episode"]
    run(clock, engine, 70)                                      # back to the reference level
    assert got["episode"] == [True, False]
    ep = mon.stress_episodes.episodes
    assert len(ep) == 1 and ep[0][1] > ep[0][0]


def test_short_stress_burst_is_not_an_episode(rig):
    clock, engine, mon, got = rig
    work(clock, engine, mon)
    run(clock, engine, 40)                                      # fill the 30 s smoothing window
    run(clock, engine, 20, psd=spectrum(high_beta=3.0))         # 20 s burst: median crosses 80 only briefly
    run(clock, engine, 60)
    assert got["episode"] == []


def test_imported_baseline_uses_first_seconds_of_live(rig):
    clock, engine, mon, got = rig
    engine.events.emit("calibrated", {"iapf": 10.0})
    engine.baseline = {"imported": True}
    engine.events.emit("baseline", engine.baseline)
    run(clock, engine, config.FAST_WORK_REF_S - 2)
    assert not mon.reference_ready and math.isnan(got["scores"][-1]["stress"])
    run(clock, engine, 5)
    assert mon.reference_ready and mon.band_base.frozen is not None


def test_band_change_detects_alpha_increase(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    rng = np.random.default_rng(1)
    n = int(FS * 0.5)
    for i in range(40):                                         # 20 s of added 10 Hz rhythm
        clock.t += 0.5
        t = (np.arange(n) + i * n) / FS
        raw = rng.normal(0, 20e-6, (n, 2)) + (25e-6 * np.sin(2 * np.pi * 10 * t))[:, None]
        engine.events.emit("eeg", list(range(n)), raw, raw)
        engine.events.emit("psd", FREQS, spectrum(), 0)
    snap = mon.snapshot()
    change = snap["bands_change"]
    assert change["alpha"] > 100 and max(change, key=change.get) == "alpha"
    assert change["alpha"] > 1000
    assert all(abs(change[b]) < 50 for b in ("delta", "theta", "beta", "gamma"))   # others: estimator noise only
    assert snap["bands_rel"]["alpha"] > snap["bands_rel"]["theta"]


def test_band_change_is_per_band_not_share(rig):
    """Real session: slow drift during the rest baseline settled later. With relative shares that
    made every other band read +70 %; with absolute power only delta may change."""
    clock, engine, mon, got = rig
    rng = np.random.default_rng(2)
    n = int(FS * 0.5)
    engine.calibration = {"iapf": 10.0, "fail_reason": 0}
    engine.events.emit("calibrated", engine.calibration)
    engine.events.emit("state", "calibrated", "baseline")
    for i in range(60):                                         # 30 s rest with strong 2 Hz drift
        clock.t += 0.5
        t = (np.arange(n) + i * n) / FS
        raw = rng.normal(0, 20e-6, (n, 2)) + (60e-6 * np.sin(2 * np.pi * 2 * t))[:, None]
        engine.events.emit("eeg", list(range(n)), raw, raw)
        engine.events.emit("psd", FREQS, spectrum(), 0)
    engine.baseline = {"concentration": 1.0, "relaxation": 1.0, "imported": False}
    engine.events.emit("baseline", engine.baseline)
    run(clock, engine, 20, rng=rng)                             # drift gone
    change = mon.snapshot()["bands_change"]
    assert change["delta"] < -50
    assert all(abs(change[b]) < 25 for b in ("theta", "alpha", "beta", "gamma")), change


def test_break_after_work_block_and_break_flow(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    mon.break_rule.work_block_s = 60
    run(clock, engine, 61, tick=mon.tick)
    assert got["break"] and "without a break" in got["break"][0]
    mon.start_break()
    run(clock, engine, 10)
    mon.end_break()
    assert len(mon.breaks) == 1 and mon.breaks[0][1] - mon.breaks[0][0] == pytest.approx(10, abs=0.6)
    with open(os.path.join(mon.session.path, "events.csv"), newline="") as fh:
        ends = [r for r in csv.DictReader(fh) if r["kind"] == "break_end"]
    assert "not reset" in ends[0]["detail"]                     # 10 s is not a real break


def test_no_checkin_during_break(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    start = clock.t
    mon.start_break()
    clock.t = start + config.SELF_REPORT_INTERVAL_S + 5
    mon.tick()
    assert got["kss"] == 0
    mon.end_break()
    mon.tick()
    assert got["kss"] == 1


def test_break_ends_stress_episode(rig):
    clock, engine, mon, got = rig
    work(clock, engine, mon)
    run(clock, engine, 70, psd=spectrum(high_beta=3.0))
    assert mon.stress_episodes.active
    mon.start_break()
    assert not mon.stress_episodes.active and got["episode"] == [True, False]
    run(clock, engine, 60, psd=spectrum(high_beta=3.0))         # no new episode while on a break
    assert got["episode"] == [True, False]


def test_self_report_prompt_every_interval(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    live_start = clock.t
    clock.t = live_start + 599
    mon.tick()
    assert got["kss"] == 0
    clock.t = live_start + 600
    mon.tick()
    mon.tick()
    assert got["kss"] == 1
    mon.record_self_report(6)
    assert mon.kss == [(600.0, 6)]


def test_artifact_warning_toggles(rig):
    clock, engine, mon, got = rig
    for t in range(10):
        clock.t = t
        engine.events.emit("artifacts", 0, [(1, 3.0), (0, 0.0)])
    mon.tick()
    assert got["warn"] == [True]


def test_session_files_and_summary(rig):
    clock, engine, mon, got = rig
    go_live_real(clock, engine, mon)
    run(clock, engine, 190, emo=emotions(attention=80))
    mon.add_marker("task A")
    mon.close()
    path = mon.session.path
    for name in ("emotions", "indices", "bands", "scores", "events"):
        with open(os.path.join(path, f"{name}.csv"), newline="") as fh:
            assert len(list(csv.reader(fh))) > 1, name
    s = mon.summary()
    assert s["live_duration_s"] == pytest.approx(190)
    assert [c["minute"] for c in s["curve"]] == [0, 1, 2, 3]
    assert s["scores"]["attention"]["mean"] == pytest.approx(80, abs=2)   # 5 s smoothing carries a few pre-live values
    assert s["scores"]["stress"]["mean"] == pytest.approx(50, abs=1)
    assert set(s["bands_rel_mean"]) == set(config.RAW_BANDS)
    assert s["markers"] == [(190.0, "task A")]
    assert all(abs(v) < 25 for v in s["bands_change_mean"].values())
    assert "arousal" in s["own_baseline"] and "abs_alpha" in s["own_baseline"]
