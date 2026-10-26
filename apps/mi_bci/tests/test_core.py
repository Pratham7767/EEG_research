"""Unit and end-to-end tests. Run from apps/mi_bci:  python -m pytest -q"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci import config as C                                          # noqa: E402
from mibci.cli import run_session                                      # noqa: E402
from mibci.decoder import Decoder, Integrator                          # noqa: E402
from mibci.dsp import BandPower, bandpower_offline                     # noqa: E402
from mibci.engine import Engine                                        # noqa: E402
from mibci.paradigm import BaselineParadigm, Paradigm, RecordedParadigm, make_schedule  # noqa: E402
from mibci.recorder import load_run                                    # noqa: E402
from mibci.sources import ReplaySource, SimulatedSource                # noqa: E402
from mibci.trainer import RunFeatures, artifact_flags, train           # noqa: E402
from mibci.analysis import erd_check                                   # noqa: E402

BANDS = [(8, 13), (13, 30)]
CH = [1, 2]


def test_bandpower_chunking_does_not_matter():
    rng = np.random.default_rng(1)
    x = rng.standard_normal((5000, 4)) * 10
    i1, f1 = bandpower_offline(x, CH, BANDS, chunk=5000)
    bp = BandPower(CH, BANDS)
    parts, pos = [], 0
    while pos < len(x):
        n = int(rng.integers(1, 40))
        parts.append(bp.process(x[pos:pos + n]))
        pos += n
    i2 = np.concatenate([p[0] for p in parts])
    f2 = np.vstack([p[1] for p in parts])
    assert np.array_equal(i1, i2)
    assert np.allclose(f1, f2, rtol=0, atol=1e-9)
    assert i1[0] == C.FS - 1 and np.all(np.diff(i1) == C.HOP)


def test_bandpower_is_causal():
    rng = np.random.default_rng(2)
    x = rng.standard_normal((3000, 4))
    i, f = bandpower_offline(x, CH, BANDS)
    y = x.copy()
    y[2000:] += 100 * rng.standard_normal((1000, 4))     # change the future only
    j, g = bandpower_offline(y, CH, BANDS)
    past = i < 2000
    assert np.allclose(f[past], g[past], atol=1e-12)


def test_bandpower_tracks_power():
    t = np.arange(20 * C.FS) / C.FS
    x = np.zeros((len(t), 4))
    x[:, 1] = 10 * np.sin(2 * np.pi * 10 * t)            # C3: 10 Hz, amplitude 10 -> power 50
    i, f = bandpower_offline(x, CH, BANDS)
    assert abs(np.exp(f[-1, 0]) - 50) / 50 < 0.1          # mu band at C3 recovers the power
    assert np.exp(f[-1, 2]) < 1.0                         # beta band at C3 sees almost nothing


def test_schedule_balanced_and_limited_runs():
    for seed in range(20):
        s = make_schedule(10, seed)
        assert s.count(C.LEFT) == s.count(C.RIGHT) == 10
        run = 1
        for a, b in zip(s[:-1], s[1:]):
            run = run + 1 if a == b else 1
            assert run <= C.MAX_SAME_IN_A_ROW


def test_paradigm_timing_in_samples():
    par = Paradigm("screening", [C.LEFT, C.RIGHT], seed=0)
    ev = []
    for idx in range(0, 40 * C.FS):
        ev += par.tick(idx)
        if par.done:
            break
    starts = [s for s, n, _ in ev if n == "trial_start"]
    cuesl = [s for s, n, _ in ev if n in ("cue_left", "cue_right")]
    ends = [s for s, n, _ in ev if n == "task_end"]
    assert len(starts) == 2 and len(cuesl) == 2
    assert all(c - s == 3 * C.FS for s, c in zip(starts, cuesl))
    assert all(e - s == 7 * C.FS for s, e in zip(starts, ends))
    gap = starts[1] - ends[0]
    assert 1.5 * C.FS <= gap <= 2.5 * C.FS
    assert par.done


def test_baseline_paradigm_blocks():
    par = BaselineParadigm(scale=0.1, gap_s=1)
    names = []
    for idx in range(0, 200 * C.FS):
        names += [n for _, n, _ in par.tick(idx)]
        if par.done:
            break
    assert names[0] == "run_start" and names[-1] == "run_end"
    assert "eyes_closed_start" in names and "jaw_end" in names


def test_integrator():
    it = Integrator(n=4)
    for d in (1, 1, -1, 1):
        it.push(d)
    assert it.value() == 0.5
    it.reset()
    assert it.value() == 0.0


def test_decoder_roundtrip(tmp_path):
    d = Decoder([(8, 13)], ["C3", "C4"], [0.5, -0.25], 0.1, {"x": 1})
    d.save(tmp_path / "d.json")
    e = Decoder.load(tmp_path / "d.json")
    assert e.bands == d.bands and np.allclose(e.w, d.w) and e.b == d.b
    assert e.predict(np.array([[0.0, 1.0]]))[0] == C.LEFT


@pytest.fixture(scope="module")
def sim_runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")

    def make(skill, subj):
        paths = []
        for r in range(3):
            _, d = run_session(SimulatedSource(skill=skill, seed=r, realtime=False), "screening", subj, 8,
                               seed=r, root=root)
            paths.append(d)
        return paths
    return root, make(0.6, "good"), make(0.0, "none")


def test_training_finds_signal_when_present(sim_runs):
    root, good, _ = sim_runs
    dec, rep = train(good, "good", out_dir=root / "dec_good", n_perm=50)
    assert rep["nested_run_accuracy"] >= 0.8
    assert rep["permutation_p"] < 0.05


def test_no_signal_means_chance(sim_runs):
    """skill 0: the simulator carries no class information. Anything far above chance = a leak."""
    root, _, none = sim_runs
    dec, rep = train(none, "none", out_dir=root / "dec_none", n_perm=50)
    assert rep["nested_run_accuracy"] <= 0.8
    assert rep["permutation_p"] > 0.05


def test_erd_check(sim_runs):
    _, good, none = sim_runs
    g = erd_check(good, n_perm=500)
    assert g["passes"]
    mu = g["screening"]["mu"]
    # classic ERD: left hand -> C4 drops more than C3; right hand -> C3 drops more than C4
    assert mu["left_hand_ERD_C4"] < mu["left_hand_ERD_C3"]
    assert mu["right_hand_ERD_C3"] < mu["right_hand_ERD_C4"]
    assert g["summary"]
    assert not erd_check(none, n_perm=500)["passes"]


def test_score_verdicts():
    from mibci.trainer import score_verdict
    assert score_verdict({})["verdict"].startswith("NO SCORE")
    assert score_verdict({"nested_run_accuracy": 0.8, "permutation_p": 0.01})["verdict"].startswith("READY")
    assert score_verdict({"nested_run_accuracy": 0.6, "permutation_p": 0.02})["verdict"].startswith("WEAK")
    assert score_verdict({"nested_run_accuracy": 0.55, "permutation_p": 0.4})["verdict"].startswith("NOT READY")


def test_live_feedback_equals_offline(sim_runs, tmp_path):
    """Replay a feedback run through the engine with odd packet sizes; outputs must equal the trainer's."""
    root, good, _ = sim_runs
    dec, _ = train(good, "good", n_perm=10)
    summ, d = run_session(SimulatedSource(skill=0.6, seed=9, realtime=False), "feedback", "good", 6,
                          decoder=dec, seed=9, root=tmp_path)
    assert summ["accuracy"] >= 0.75
    run = load_run(d)
    rf = RunFeatures(run, bands=dec.bands)
    d_off = rf.F @ dec.w + dec.b
    # 1) the original live run vs offline recomputation from the saved file: the file stores EEG to
    #    0.001 uV, so tiny differences are expected, but every decision must be the same
    live = run["outputs"]
    assert np.array_equal(live[:, 0].astype(int), rf.idx)
    assert np.max(np.abs(live[:, 1] - d_off)) < 1e-3
    assert np.array_equal(np.sign(live[:, 1]) >= 0, d_off >= 0) or np.mean((live[:, 1] >= 0) != (d_off >= 0)) < 1e-3
    # 2) replaying the saved file through the live engine (odd packet sizes) must equal offline exactly
    from mibci.recorder import Recorder
    rec = Recorder("good", "replay", root=tmp_path / "replay")
    src = ReplaySource(run["eeg"], chunk=7)
    eng = Engine(src, RecordedParadigm("feedback", run["events"]), dec, rec)
    while not src.finished:
        eng.pump()
    eng.finish()
    rep = load_run(rec.dir)["outputs"]
    assert np.array_equal(rep[:, 0].astype(int), rf.idx)
    assert np.max(np.abs(rep[:, 1] - d_off)) < 1e-6          # outputs.csv keeps 6 decimals
    assert np.array_equal(rep[:, 3].astype(bool), rf.art)
    assert eng.summary()["accuracy"] == pytest.approx(rf.score(dec.w, dec.b, list(range(len(dec.w))))[0])


def test_dry_electrode_offset_and_drift():
    """Raw NeuroSDK channels sit at tens of mV with drift (seen in our April recordings).
    The montage must cancel the common part, and drift must not count as an artifact."""
    from mibci.dsp import apply_montage
    rng = np.random.default_rng(5)
    n = 60 * C.FS
    t = np.arange(n) / C.FS
    common = 45000 + 3000 * np.sin(2 * np.pi * 0.05 * t)          # 45 mV offset + slow 3 mV drift (uV)
    x = rng.standard_normal((n, 4)) * 10 + common[:, None]
    m = apply_montage(x)
    assert abs(np.median(m[:, 1])) < 100 and abs(np.median(m[:, 2])) < 100
    i, _ = bandpower_offline(m, CH, BANDS)
    assert artifact_flags(m, i).mean() < 0.02
    i2, _ = bandpower_offline(x, CH, BANDS)                         # even without the montage
    assert artifact_flags(x, i2).mean() < 0.02


def test_signal_quality_verdicts():
    from mibci.analysis import signal_quality
    rng = np.random.default_rng(7)
    good = rng.standard_normal((10 * C.FS, 4)) * 15 + 30000           # 15 uV noise on a 30 mV offset
    assert signal_quality(good)["verdict"] == "GOOD"
    bad = rng.standard_normal((10 * C.FS, 4)) * 30000                  # like the 2026-04-14 recording
    bad = np.clip(bad, -400000, 400000)
    bad[::8] = 400000                                                  # pinned at the amplifier limit
    assert signal_quality(bad)["verdict"].startswith("BAD")


def test_artifact_check_flags_spikes():
    rng = np.random.default_rng(3)
    x = rng.standard_normal((20 * C.FS, 4)) * 10
    x[10 * C.FS:10 * C.FS + 20, 1] += 2000                 # a 2 mV jump on C3
    i, _ = bandpower_offline(x, CH, BANDS)
    flags = artifact_flags(x, i)
    t = i / C.FS
    assert flags[(t > 10.1) & (t < 10.9)].all()
    assert not flags[t < 9.5].any()
