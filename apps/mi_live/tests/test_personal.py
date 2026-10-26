"""Tests for the notch filter, the signal check and the personal model.   python -m pytest -q tests"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.paradigm import Paradigm, make_schedule  # noqa: E402
from mibci.recorder import Recorder  # noqa: E402
from mibci.sources import SimulatedSource  # noqa: E402
from mibci.svm import covwindow_offline  # noqa: E402
from milive import settings as S  # noqa: E402
from milive.cued import CuedSession  # noqa: E402
from milive.dsp_extra import Notch, signal_check  # noqa: E402
from milive.models import load_model  # noqa: E402
from milive.personal import train_personal  # noqa: E402
from milive.pipeline import LivePipeline  # noqa: E402
from milive.train2b import covs, prep  # noqa: E402

FS = C.FS


def test_notch_removes_50hz_and_keeps_10hz():
    t = np.arange(20 * FS) / FS
    x = np.column_stack([np.zeros_like(t), 60 * np.sin(2 * np.pi * 50 * t) + 5 * np.sin(2 * np.pi * 10 * t),
                         np.zeros_like(t), np.zeros_like(t)])
    y = Notch([1, 2]).process(x)[5 * FS:, 1]
    amp = lambda f: 2 * abs(np.mean(y * np.exp(-2j * np.pi * f * t[5 * FS:])))  # noqa: E731
    assert amp(50) < 0.6 and abs(amp(10) - 5) < 0.3


def test_notch_is_chunk_independent_and_holds_nan():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(3000, 4)) * 10 + 500
    x[1200:1210, 1] = np.nan
    a = Notch([1, 2]).process(x)
    n = Notch([1, 2])
    b = np.vstack([n.process(x[i:i + 37]) for i in range(0, len(x), 37)])
    assert np.allclose(a[:, 1:3], b[:, 1:3]) and not np.isnan(a[:, 1:3]).any()
    assert np.max(np.abs(a[1195:1215, 1])) < 100           # no big step at the gap


def test_train2b_covariances_equal_live_notch_plus_covwindow():
    rng = np.random.default_rng(1)
    xx = np.cumsum(rng.normal(size=(6000, 2)), 0) + rng.normal(size=(6000, 2)) * 20
    x4 = Notch([1, 2]).process(np.column_stack([np.zeros(len(xx)), xx, np.zeros(len(xx))]))
    for band in ((8.0, 30.0), (36.0, 40.0)):
        i1, F1 = covwindow_offline(x4, [1, 2], band=band)
        i2, F2 = covs(prep(xx), band)
        assert np.array_equal(i1, i2) and np.allclose(F1, F2, rtol=1e-6, atol=1e-6)


def test_signal_check_flags_hum():
    t = np.arange(15 * FS) / FS
    rng = np.random.default_rng(2)
    eeg = rng.normal(size=(len(t), 2)) * 8
    good = signal_check(eeg)
    bad = signal_check(eeg + 60 * np.sin(2 * np.pi * 50 * t)[:, None])
    assert good["verdict"] == "GOOD" and bad["verdict"] == "BAD" and bad["hum_50"][0] > 30


def record_blocks(tmp_path, skill, n_blocks=3, n=8, seed=0):
    src = SimulatedSource(skill=skill, seed=seed, realtime=False, packet=10)
    p = LivePipeline(load_model(S.BASE_JSON))
    for _ in range(5 * FS // 10):
        p.feed(src.read())
    paths = []
    for b in range(n_blocks):
        rec = Recorder("TST", "screening", root=tmp_path)
        s = CuedSession(Paradigm("screening", make_schedule(n, seed=seed + b), seed=seed + b), offset=p.n,
                        recorder=rec, feedback=False)
        while not s.done:
            src.set_task(s.cls if s.phase in ("cue", "task") else None)
            x = src.read()
            s.process(x, p.n + len(x), p.feed(x))
        rec.close()
        paths.append(rec.dir)
    return paths


def test_personal_model_ready_with_signal_and_not_ready_without(tmp_path):
    good, rep, seeds = train_personal(record_blocks(tmp_path / "a", 0.8), "TST", out_dir=tmp_path / "a" / "dec",
                                      progress=lambda m: None)
    assert rep["verdict"].startswith("PROMISING") and rep["accuracy"] >= 0.8, rep.get("accuracy")
    assert Path(rep["model_path"]).exists() and seeds.shape[1] == 3 * len(good.bands)
    p = LivePipeline(load_model(rep["model_path"]))
    assert p.seed_alignment(seeds)
    _, rep0, _ = train_personal(record_blocks(tmp_path / "b", 0.0, seed=5), "TST", progress=lambda m: None)
    assert rep0["verdict"] == "NOT READY"
