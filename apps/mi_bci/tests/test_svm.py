"""Tests for the app's SVM (CSP + SVM + Euclidean Alignment). Simulated data only (no 2b files needed)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci import config as C                                                 # noqa: E402
from mibci.cli import run_session                                             # noqa: E402
from mibci.decoder import load_decoder                                        # noqa: E402
from mibci.engine import Engine                                               # noqa: E402
from mibci.paradigm import RecordedParadigm                                   # noqa: E402
from mibci.recorder import load_run                                           # noqa: E402
from mibci.sources import ReplaySource, SimulatedSource                       # noqa: E402
from mibci.svm import CovWindow, align, covwindow_offline, fit_params, reference, unflat  # noqa: E402
from mibci.svm_trainer import RunCov, day_refs, score_run, stack, train_from_runs  # noqa: E402


def test_covwindow_chunking_and_values():
    rng = np.random.default_rng(0)
    x = rng.standard_normal((4000, 4)) * 10
    i1, f1 = covwindow_offline(x, [1, 2], chunk=4000)
    cw = CovWindow([1, 2])
    parts, pos = [], 0
    while pos < len(x):
        n = int(rng.integers(1, 30))
        parts.append(cw.process(x[pos:pos + n]))
        pos += n
    assert np.array_equal(i1, np.concatenate([p[0] for p in parts]))
    assert np.allclose(f1, np.vstack([p[1] for p in parts]), atol=1e-9)
    assert np.all(np.linalg.eigvalsh(unflat(f1)) > 0)          # valid covariances


def test_alignment_whitens_session_mean():
    rng = np.random.default_rng(1)
    A = rng.standard_normal((2, 2))
    covs = np.array([A @ np.diag(rng.uniform(1, 3, 2)) @ A.T for _ in range(200)])
    f = np.stack([covs[:, 0, 0], covs[:, 0, 1], covs[:, 1, 1]], -1)
    al = align(f, reference(f))
    assert np.allclose(al.mean(0), np.eye(2), atol=1e-8)


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    root = tmp_path_factory.mktemp("svm")

    def runs(subject, skill, seeds):
        return [run_session(SimulatedSource(skill=skill, seed=s, realtime=False), "screening", subject, 8,
                            seed=s, root=root)[1] for s in seeds]
    return root, runs("base", 0.6, [50, 51]), runs("user", 0.6, [1, 2, 3]), runs("none", 0.0, [4, 5, 6]), \
        runs("nbase", 0.0, [52, 53])


def _base(paths):
    rcs = [RunCov.from_path(p) for p in paths]
    return stack(rcs, day_refs(rcs))


def test_svm_improves_and_scores(sim):
    root, base, user, _, _ = sim
    dec, rep = train_from_runs([RunCov.from_path(p) for p in user], "user", out_dir=root / "dec", base=_base(base))
    assert set(rep["weightings"]) == {"2b only", "2b + yours", "yours only"}
    assert rep["nested_run_accuracy"] >= 0.8 and rep["verdict"].startswith("READY")
    d2 = load_decoder(root / "dec" / "current.json")              # saved and reloaded as JSON
    assert d2.kind == "csp_svm_ea" and np.allclose(d2.p["coef"], dec.p["coef"])


def test_svm_no_signal_is_not_ready(sim):
    """No information in user or base data: the SVM must not look good (leak check)."""
    root, _, _, none, nbase = sim
    dec, rep = train_from_runs([RunCov.from_path(p) for p in none], "none", base=_base(nbase))
    assert rep["nested_run_accuracy"] < 0.8 and not rep["verdict"].startswith("READY")


def test_svm_live_feedback_equals_offline(sim, tmp_path):
    root, base, user, _, _ = sim
    rcs = [RunCov.from_path(p) for p in user]
    dec, _ = train_from_runs(rcs, "user", base=_base(base))
    dec.set_reference(day_refs(rcs)[rcs[0].day])
    summ, d = run_session(SimulatedSource(skill=0.6, seed=9, realtime=False), "feedback", "user", 6,
                          decoder=dec, seed=9, root=tmp_path)
    assert summ["accuracy"] >= 0.75
    run = load_run(d)
    rc = RunCov(run["eeg"], run["events"], "x")
    acc, _, n, _ = score_run(dec.p, rc, dec.ref)
    assert n == summ["trials_scored"] and acc == pytest.approx(summ["accuracy"])
    live = run["outputs"]
    assert np.array_equal(live[:, 0].astype(int), rc.idx)
    from mibci.svm import decide
    off = decide(dec.p, align(rc.F, dec.ref))
    assert np.max(np.abs(live[:, 1] - off)) < 1e-3                # file keeps EEG to 0.001 uV
    src = ReplaySource(run["eeg"], chunk=7)                        # replay: exact
    eng = Engine(src, RecordedParadigm("feedback", run["events"]), dec, None)
    while not src.finished:
        eng.pump()
    assert eng.finish()["accuracy"] == pytest.approx(acc)
