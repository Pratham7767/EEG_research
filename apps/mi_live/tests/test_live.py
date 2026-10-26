"""C:\\Python313\\python.exe -m pytest -q tests"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.paradigm import Paradigm, make_schedule  # noqa: E402
from mibci.recorder import Recorder, load_run  # noqa: E402
from mibci.sources import SimulatedSource  # noqa: E402
from milive import settings as S  # noqa: E402
from milive.commands import CommandSender  # noqa: E402
from milive.cued import CuedSession, cohen_kappa  # noqa: E402
from milive.models import LinearCovModel, inv_sqrt, load_model, unflat  # noqa: E402
from milive.offline import offline_outputs  # noqa: E402
from milive.pipeline import CommandLogic, LivePipeline  # noqa: E402

MODEL_FILES = [S.BASE_JSON] + ([S.LIVE_DIR / "models" / "base_2b_live.json"]
                               if (S.LIVE_DIR / "models" / "base_2b_live.json").exists() else [])


def sim_data(n_s=120, skill=0.6, seed=1, blink_at=None):
    src = SimulatedSource(skill=skill, seed=seed, realtime=False, packet=250)
    X = []
    for k in range(n_s):
        src.set_task([None, C.LEFT, C.RIGHT][k // 10 % 3])
        X.append(src.read())
    X = np.vstack(X)
    if blink_at is not None:                         # a big artifact, to test the artifact path
        X[blink_at:blink_at + 60, 1] += 3000.0
    return X


def run_pipe(X, seed, model_file=S.BASE_JSON, calib_s=30, adaptive=True):
    p = LivePipeline(load_model(model_file), adaptive=adaptive)
    p.start_calibration([("data", calib_s)])
    outs, pos, rng = [], 0, np.random.default_rng(seed)
    while pos < len(X):
        k = int(rng.integers(1, 40))
        outs += p.feed(X[pos:pos + k])
        pos += k
    return p, outs


def test_chunking_does_not_change_outputs():
    X = sim_data(60)
    _, a = run_pipe(X, 1)
    _, b = run_pipe(X, 2)
    assert [o.i for o in a] == [o.i for o in b]
    assert np.allclose([o.d for o in a], [o.d for o in b])
    assert [o.cmd for o in a] == [o.cmd for o in b]


def test_live_equals_independent_offline_adaptive_all_models():
    X = sim_data(70, blink_at=40 * C.FS)
    for f in MODEL_FILES:
        p, outs = run_pipe(X, 5, model_file=f)
        idx, d_off, bad = offline_outputs(p.model, X)
        assert bad.any(), "the test needs some artifact windows"
        assert [o.i for o in outs] == idx.tolist()
        assert [o.bad for o in outs] == bad.tolist()
        assert np.max(np.abs(np.array([o.d for o in outs]) - d_off)) < 1e-9, f


def test_mibci_svm_file_gives_the_same_decision_as_mibci():
    from mibci.svm import SvmDecoder, align, decide
    j = json.loads(Path(S.BASE_JSON).read_text())
    m = load_model(S.BASE_JSON)
    rng = np.random.default_rng(0)
    F = np.abs(rng.normal(size=(50, 3))) + np.array([5, 0, 5])
    R = unflat(F.mean(0))
    P = inv_sqrt(R)
    assert np.allclose(m.decide([P @ unflat(F) @ P]), decide(SvmDecoder.from_dict(j).p, align(F, R)))


def test_fixed_mode_freezes_reference_and_bias_from_calibration():
    X = sim_data(60)
    p, outs = run_pipe(X, 4, calib_s=30, adaptive=False)
    assert p.calib_result["ok"] and p.R_fixed is not None
    d = np.array([o.d for o in outs if 30 * C.FS <= o.i < 60 * C.FS])
    assert abs(np.mean(d)) < 1.0


def test_freeze_and_resume():
    X = sim_data(40)
    p, _ = run_pipe(X, 6)
    p.set_adaptive(False)
    R = p.R_fixed
    assert R is not None
    p.feed(sim_data(10, seed=9))
    assert p.R_fixed is R
    p.set_adaptive(True)
    assert p.R_fixed is None


def test_calibration_restarts_alignment():
    X = sim_data(40)
    p, _ = run_pipe(X, 7)
    n_before = p._cn
    p.start_calibration()
    assert n_before > 0 and p._cn == 0 and p._dn == 0


def test_command_logic_threshold_hold_and_artifact_stop():
    L = CommandLogic(threshold=0.5, hold_s=0.2, neutral="STOP")
    assert [L.update(-0.8, False) for _ in range(4)][-1] == "STOP"     # 4 x 40 ms < 0.2 s
    assert L.update(-0.8, False) == "LEFT"                              # 5 x 40 ms = 0.2 s
    assert [L.update(0.1, False) for _ in range(5)][-1] == "STOP"
    assert [L.update(0.9, False) for _ in range(5)][-1] == "RIGHT"
    assert [L.update(0.9, True) for _ in range(13)][-1] == "STOP"      # artifact for 0.5 s
    L.neutral = "FORWARD"
    assert [L.update(0.0, False) for _ in range(5)][-1] == "FORWARD"


def test_udp_sender_sends_changes_and_heartbeat():
    import socket
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(1)
    s = CommandSender()
    s.set_udp(f"127.0.0.1:{rx.getsockname()[1]}")
    assert s.send("LEFT", -0.7, -1.2)
    assert not s.send("LEFT", -0.7, -1.2)            # same command within 0.25 s: not repeated
    assert s.send("RIGHT", 0.6, 0.9)
    got = [json.loads(rx.recvfrom(1024)[0])["cmd"] for _ in range(2)]
    s.close()
    assert got == ["LEFT", "RIGHT"] and json.loads(rx.recvfrom(1024)[0])["cmd"] == "STOP"


def test_kappa():
    t = np.array([1, 1, -1, -1])
    assert cohen_kappa(t, t) == 1.0
    assert cohen_kappa(t, -t) == -1.0
    assert abs(cohen_kappa(t, np.array([1, -1, 1, -1]))) < 1e-12


def cued_run(skill, n=12, seed=0, recorder=None, feedback=True):
    src = SimulatedSource(skill=skill, seed=seed, realtime=False, packet=10)
    p = LivePipeline(load_model(S.BASE_JSON))
    p.start_calibration([("relax", 10), ("left", 10), ("right", 10)])
    while p.calib is not None:
        name, _ = p.calib.block_at(p.n)
        src.set_task({"left": C.LEFT, "right": C.RIGHT}.get(name))
        p.feed(src.read())
    run_type = "feedback" if feedback else "screening"
    s = CuedSession(Paradigm(run_type, make_schedule(n, seed=seed), seed=seed), offset=p.n,
                    recorder=recorder, feedback=feedback)
    while not s.done:
        src.set_task(s.cls if s.phase in ("cue", "task") else None)
        x = src.read()
        s.process(x, p.n + len(x), p.feed(x))
    return s.results(n_perm=50), s


def test_cued_test_finds_a_strong_signal():
    r, _ = cued_run(0.8)
    assert r["trials"] == 24 and r["accuracy"] >= 0.8 and r["p"] < 0.01
    assert r["max_kappa_raw"] > r["max_kappa_chance95"]


def test_cued_test_no_signal_is_not_above_chance():
    accs = [cued_run(0.0, seed=s)[0]["accuracy"] for s in range(3)]
    assert np.mean(accs) < 0.72


def test_saved_run_is_usable_by_mi_bci(tmp_path):
    """A mi_live test run must be a normal mi_bci run: events in place, cues found, trainer reads it."""
    from mibci.svm_trainer import RunCov
    for fb in (False, True):
        rec = Recorder("TST", "feedback" if fb else "screening", root=tmp_path)
        r, s = cued_run(0.8, n=5, seed=3, recorder=rec, feedback=fb)
        rec.close(dict(summary={k: v for k, v in r.items() if not k.startswith(("curve", "kappa"))}))
        run = load_run(rec.dir)
        assert run["meta"]["run_type"] == ("feedback" if fb else "screening")
        cue_ev = [e for e in run["events"] if e[1] in ("cue_left", "cue_right")]
        assert len(cue_ev) == 10
        # events and samples line up: the recorded cue samples = the session's cues minus the offset
        assert [e[0] for e in cue_ev] == [c - s.offset for c, _ in s.cues]
        assert len(run["eeg"]) >= cue_ev[-1][0] + 4 * C.FS
        rc = RunCov.from_path(rec.dir)
        assert len(rc.cues) == 10
