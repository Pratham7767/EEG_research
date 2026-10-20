import csv
import json
import os

import pytest

from cogscore.engine import Flow, InvalidTransition, State
from cogscore.session import STREAMS, SessionWriter, load_meta


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def test_session_writes_exact_headers_and_rows(tmp_path):
    s = SessionWriter(tmp_path, name="t1", clock=lambda: 1727690000.125)
    s.write("emotions", {"attention": 50.0, "relaxation": float("nan"), "unknown_key": 1})
    s.event("marker", "task A")
    s.close()
    rows = read_csv(os.path.join(s.path, "emotions.csv"))
    assert rows[0] == STREAMS["emotions"]
    assert rows[1][0] == "1727690000.125"                      # timestamps keep ms precision
    assert rows[1][2] == "50" and rows[1][3] == ""             # NaN → empty
    events = read_csv(os.path.join(s.path, "events.csv"))
    assert events[1][2:] == ["marker", "task A"]


def test_session_meta_is_valid_json_and_close_is_idempotent(tmp_path):
    s = SessionWriter(tmp_path, name="t2")
    s.set_meta("calibration", {"iapf": float("nan"), "ok": True, "vals": (1, 2.5)})
    s.close()
    s.close()
    s.write("emotions", {"attention": 1.0})                   # ignored after close
    raw = open(os.path.join(s.path, "session.json"), encoding="utf-8").read()
    meta = json.loads(raw)                                    # strict JSON: no NaN tokens
    assert meta["calibration"] == {"iapf": None, "ok": True, "vals": [1, 2.5]}
    assert "duration_s" in meta and load_meta(s.path)["session"] == "t2"


def test_eeg_stream_header_from_channels(tmp_path):
    s = SessionWriter(tmp_path, name="t3")
    s.open_eeg(["T3-O1", "T4-O2"])
    s.write_values("eeg", [1.0, 5, 0.1, 0.2, 0.01, 0.02])
    s.close()
    rows = read_csv(os.path.join(s.path, "eeg.csv"))
    assert rows[0] == ["unix_time", "sdk_ms", "T3-O1_raw", "T4-O2_raw", "T3-O1_processed", "T4-O2_processed"]
    assert len(rows) == 2


def test_unknown_stream_rejected(tmp_path):
    s = SessionWriter(tmp_path, name="t4")
    with pytest.raises(KeyError):
        s.write("eeg", {})                                     # eeg needs open_eeg first
    s.close()


def test_flow_happy_path():
    seen = []
    f = Flow(on_change=lambda a, b: seen.append(b))
    for st in (State.SCANNING, State.DEVICES_FOUND, State.CONNECTING, State.STREAMING,
               State.CALIBRATING, State.CALIBRATED, State.BASELINE, State.LIVE, State.STOPPED):
        f.go(st)
    assert seen[-1] == State.STOPPED and len(seen) == 9


@pytest.mark.parametrize("path", [
    [State.SCANNING, State.DEVICES_FOUND, State.CONNECTING, State.STREAMING, State.BASELINE],  # baseline before calibration
    [State.CONNECTING],                                                                     # connect before scan
    [State.SCANNING, State.DEVICES_FOUND, State.CONNECTING, State.STREAMING, State.LIVE],      # skip calibration
])
def test_flow_rejects_out_of_order_steps(path):
    f = Flow()
    with pytest.raises(InvalidTransition):
        for st in path:
            f.go(st)


def test_flow_calibration_retry_and_redo():
    f = Flow()
    for st in (State.SCANNING, State.DEVICES_FOUND, State.CONNECTING, State.STREAMING, State.CALIBRATING):
        f.go(st)
    f.go(State.STREAMING)            # failed → back to streaming
    f.go(State.CALIBRATING)
    f.go(State.CALIBRATED)
    f.go(State.CALIBRATING)          # user chose to redo
    assert f.state == State.CALIBRATING
    with pytest.raises(InvalidTransition):
        f.require(State.LIVE)
