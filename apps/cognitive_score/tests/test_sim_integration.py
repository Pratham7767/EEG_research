"""SDK contract tests against the Capsule simulated devices (plan §6.2).

Each scenario runs in its own Python process because the vendor wrapper keeps
its callbacks in module-level globals (one device per process).
Run with:  python -m pytest -m sim        (add -m "sim or slow" for the 70 s calibration test)
"""
import csv
import json
import os
import subprocess
import sys
import textwrap

import pytest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.sim


def run_py(code, timeout=150):
    proc = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=PROJECT,
                          capture_output=True, text=True, timeout=timeout)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


CONTRACT = """
import json, time
from cogscore.engine import CapsuleEngine, State
e = CapsuleEngine(simulate="noise")
got = {"devices": [], "res": None, "psd": None, "emo": None, "art": None, "prod": None, "idx": None, "states": []}
e.events.subscribe("state", lambda a, b: got["states"].append(b))
e.events.subscribe("devices", lambda d: got.__setitem__("devices", d))
t0 = [0.0]
def first(key, value):
    if got[key] is None:
        got[key] = value
e.events.subscribe("resistances", lambda r: first("res", r))
e.events.subscribe("psd", lambda f, s, ms: first("psd", {"shape": list(s.shape), "f0": float(f[0]), "f1": float(f[-1]), "t": round(time.monotonic() - t0[0], 1)}))
e.events.subscribe("emotions", lambda d: first("emo", d))
e.events.subscribe("artifacts", lambda ms, fl: first("art", fl))
e.events.subscribe("productivity", lambda d: first("prod", dict(d, t=round(time.monotonic() - t0[0], 1))))
e.events.subscribe("indexes", lambda d: first("idx", d))
def pump(sec, cond):
    end = time.monotonic() + sec
    while time.monotonic() < end and not cond():
        e.pump(); time.sleep(0.02)
    return cond()
t = time.monotonic(); e.scan(5)
found = pump(10, lambda: e.state == State.DEVICES_FOUND); t_found = round(time.monotonic() - t, 1)
e.connect(got["devices"][0]["serial"])
pump(30, lambda: e.state == State.STREAMING)
t0[0] = time.monotonic()
pump(12, lambda: None not in (got["res"], got["psd"], got["emo"], got["art"]))
t0[0] = time.monotonic()
e.import_calibration(); e.import_baseline()
pump(8, lambda: got["prod"] is not None and got["idx"] is not None)
state_live = e.state
e.stop()
print(json.dumps({"found": found, "t_found": t_found, "state_live": state_live, "final": e.state,
                  "channels": e.channel_names, "res": got["res"], "psd": got["psd"], "emo": got["emo"],
                  "art": got["art"], "prod": got["prod"], "idx": got["idx"], "states": got["states"]}))
"""


@pytest.fixture(scope="module")
def contract():
    return run_py(CONTRACT)


def test_noise_device_found_and_connected(contract):
    assert contract["found"] and contract["t_found"] <= 8
    assert contract["channels"], "no channel names after connect"
    assert contract["states"][:4] == ["scanning", "devices_found", "connecting", "streaming"]


def test_streams_arrive_after_start(contract):
    assert contract["res"] and all(v > 0 for v in contract["res"].values())
    psd = contract["psd"]
    assert psd and psd["t"] <= 10 and psd["f0"] >= 1.0 and psd["f1"] <= 30.0
    assert contract["art"] is not None


def test_emotions_have_correct_names_and_range(contract):
    emo = contract["emo"]
    for key in ("attention", "relaxation", "cognitive_load", "cognitive_control", "self_control"):
        assert 0 <= emo[key] <= 100, (key, emo[key])


def test_imported_calibration_gives_productivity_quickly(contract):
    assert contract["state_live"] == "live"
    prod = contract["prod"]
    assert prod["t"] <= 5
    assert isinstance(prod["fatigue_growth_rate"], int)
    assert isinstance(contract["idx"]["recommendation"], int)


def test_clean_stop(contract):
    assert contract["final"] == "stopped"


def _headless(tmp_path, *args, timeout=150):
    proc = subprocess.run([sys.executable, "-m", "cogscore.headless", "--sessions", str(tmp_path), *args],
                          cwd=PROJECT, capture_output=True, text=True, timeout=timeout)
    assert proc.returncode == 0 and "PASS" in proc.stdout, proc.stdout[-3000:] + proc.stderr[-3000:]
    return [os.path.join(tmp_path, d) for d in os.listdir(tmp_path)][0]


def test_headless_noise_fast_session_complete(tmp_path):
    path = _headless(tmp_path, "--simulate", "noise", "--fast", "--live", "30", "--record-eeg")
    with open(os.path.join(path, "eeg.csv"), newline="") as fh:
        assert sum(1 for _ in fh) > 250 * 25          # ~250 Hz for ≥ 30 s
    # The Noise device's raw EEG is white, so each band's share must equal its width / 44 Hz.
    with open(os.path.join(path, "bands.csv"), newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if not r["rejected"]]
    assert len(rows) > 40
    for band, (lo, hi) in {"delta": (1, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30),
                           "gamma": (30, 45)}.items():
        share = sum(float(r[f"{band}_rel"]) for r in rows) / len(rows)
        assert share == pytest.approx((hi - lo) / 44, rel=0.2), band


def test_headless_sinwave_values_are_sanitised(tmp_path):
    """SinWave has ~no beta power, so vendor ratios explode (≈1e6); check_session in the
    headless runner fails the run if any unsanitised value reaches productivity.csv."""
    path = _headless(tmp_path, "--simulate", "sinwave", "--fast", "--live", "30")   # > 20 s own-baseline window
    with open(os.path.join(path, "productivity.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and any(r["fatigue"] == "" for r in rows)
    # SinWave's raw EEG is a pure 10 Hz tone: the band pipeline must put ~all power in alpha.
    with open(os.path.join(path, "bands.csv"), newline="") as fh:
        bands = [r for r in csv.DictReader(fh) if not r["rejected"]]
    assert bands and min(float(r["alpha_rel"]) for r in bands) > 0.95


def test_ui_selftest_drives_every_step(tmp_path):
    """plan §6.3: the real window, driven through all 7 steps on the simulator."""
    proc = subprocess.run([sys.executable, "app.py", "--selftest", "--selftest-live", "22", "--sessions", str(tmp_path)],
                          cwd=PROJECT,
                          capture_output=True, text=True, timeout=240)
    assert proc.returncode == 0 and "[selftest] PASS" in proc.stdout, proc.stdout[-3000:] + proc.stderr[-3000:]


@pytest.mark.slow
def test_headless_noise_real_calibration_and_baseline(tmp_path):
    path = _headless(tmp_path, "--simulate", "noise", "--live", "10", timeout=300)
    with open(os.path.join(path, "session.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["calibration"]["fail_reason"] == 0 and meta["calibration"]["imported"] is False
    assert 7 <= meta["calibration"]["iapf"] <= 13
    assert meta["baseline"]["imported"] is False
