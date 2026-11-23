"""ReplayEngine: plays a recorded session back through the app (stage backup when Bluetooth fails).

It has the same interface as CapsuleEngine (events, state, pump, scan, connect, calibration,
baseline, stop), so the Monitor and the UI cannot tell the difference, except that the UI shows a
permanent REPLAY badge. Nothing is re-measured: the values are the ones the app computed during the
original session (emotions.csv, indices.csv, bands.csv, ...), sent at their original times.
Stress and fatigue are recomputed by the Monitor from the replayed ratios, exactly as live.

    python app.py --replay sessions/2026-11-21_105125           (or pick one in the start window)
Always real time: the app's own timers (reference, break rule) must see the original pace.

Extra events (only from a replay):
    replay_scene(key or None)   replay_marker(text)   replay_break(started: bool)   replay_finished()
"""
import csv
import json
import math
import os
import time

from . import config
from .engine import Flow, State
from .events import EventBus

NAN = float("nan")
INDEX_KEYS = ("concentration", "relaxation", "fatigue", "reverse_fatigue", "cognitive_load",
              "cognitive_control", "alpha_gravity", "arousal")


class ReplayError(RuntimeError):
    pass


def _f(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return NAN
    return v


def _read(path, name):
    f = os.path.join(path, f"{name}.csv")
    if not os.path.isfile(f):
        return []
    with open(f, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["_t"] = _f(r.get("unix_time"))
    return [r for r in rows if math.isfinite(r["_t"])]


def _group(rows):
    """Rows sharing one unix_time (one resistance / artifact update) → [(t, [rows])]."""
    out = []
    for r in rows:
        if out and out[-1][0] == r["_t"]:
            out[-1][1].append(r)
        else:
            out.append((r["_t"], [r]))
    return out


def session_info(path):
    """(name, live seconds, mode) of a recorded session, or None if it cannot be replayed."""
    try:
        with open(os.path.join(path, "session.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        return None
    live = (meta.get("summary") or {}).get("live_duration_s") or 0
    if meta.get("simulated") or meta.get("replay_of") or live < 60:
        return None
    if not os.path.isfile(os.path.join(path, "emotions.csv")):
        return None
    return os.path.basename(path), float(live), meta.get("mode", "real")


def list_sessions(root=config.SESSIONS_DIR):
    """Replayable sessions, newest first: [(path, name, live_s, mode)]."""
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root), reverse=True):
        info = session_info(os.path.join(root, name))
        if info:
            out.append((os.path.join(root, name), *info))
    return out


class ReplayEngine:
    simulate = "replay"

    def __init__(self, session_path, clock=time.monotonic):
        self.path = os.path.abspath(session_path)
        self.speed = 1.0
        self._clock = clock
        self.events = EventBus()
        self.flow = Flow(on_change=lambda old, new: self.events.emit("state", old, new))
        try:
            with open(os.path.join(self.path, "session.json"), encoding="utf-8") as fh:
                self.meta = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ReplayError(f"cannot read {self.path}/session.json: {exc}") from exc

        self.record_eeg = False
        self.sdk_version = "replay"
        self.reconnecting, self.reconnects = False, 0
        self.ppg_supported, self.ppg_seen = False, False
        self.battery = None
        self.calibration = None
        self.baseline = None
        dev = self.meta.get("device") or {}
        self.channel_names = list(dev.get("channels") or ["A1-C3", "A2-C4"])
        self.sample_rate = float(dev.get("sample_rate") or 250.0)
        self.name = os.path.basename(self.path)
        self.device_info = {}

        self._streams = {name: _read(self.path, name) for name in
                         ("emotions", "indices", "bands", "productivity", "indexes", "events")}
        self._resist = _group(_read(self.path, "resistances"))
        self._artifacts = _group(_read(self.path, "artifacts"))
        self._eeg = _read(self.path, "eeg")
        events = self._streams["events"]
        live = [r["_t"] for r in events if r.get("kind") == "live_start"]
        if not live:
            raise ReplayError("this recording never reached the live session")
        self.t_live = live[0]
        base = [r["_t"] for r in events if r.get("kind") == "baseline_start" and r["_t"] <= self.t_live]
        cal = [r["_t"] for r in events if r.get("kind") == "calibrated" and r["_t"] <= self.t_live]
        self.t_base = base[-1] if base else (cal[-1] if cal else self.t_live - 60.0)
        ends = [rows[-1]["_t"] for rows in self._streams.values() if rows]
        self.t_end = max(ends) if ends else self.t_live
        self.live_seconds = max(0.0, self.t_end - self.t_live)

        self._deadline = None            # when the current fake step (scan, connect, ...) completes
        self._live_t0 = None
        self._ptr = {}
        self._pre_t0 = None              # replay clock for the steps before live
        self._finished = False

    # ── interface shared with CapsuleEngine ──────────────────────
    @property
    def state(self):
        return self.flow.state

    def scan(self, seconds=None):
        if self.state == State.DEVICES_FOUND:
            self.flow.go(State.SCANNING)
        else:
            self.flow.require(State.IDLE)
            self.flow.go(State.SCANNING)
        self.events.emit("status", "Opening the recording...")
        self._deadline = self._clock() + 0.5

    def connect(self, serial):
        self.flow.require(State.DEVICES_FOUND)
        self.flow.go(State.CONNECTING)
        self.events.emit("status", "Loading the recording...")
        self._deadline = self._clock() + 0.5

    def reconnect(self):
        pass

    def start_calibration(self):
        self.flow.require(State.STREAMING, State.CALIBRATED)
        self.flow.go(State.CALIBRATING)
        self._deadline = self._clock() + config.REPLAY_STEP_S
        self.events.emit("status", "Replay: calibration from the recording")

    def import_calibration(self, iapf=None):
        self.flow.require(State.STREAMING, State.CALIBRATED)
        self._finish_calibration()

    def start_baseline(self):
        self.flow.require(State.CALIBRATED)
        self.flow.go(State.BASELINE)
        self._deadline = self._clock() + config.REPLAY_STEP_S
        self._baseline_sent = False
        self.events.emit("status", "Replay: baseline from the recording")

    def import_baseline(self, values=None):
        self.flow.require(State.CALIBRATED)
        self.flow.go(State.BASELINE)
        self._send_baseline_rows()
        self._go_live()

    def reset_accumulated_fatigue(self):
        pass

    def stop(self):
        self._deadline = None
        if self.flow.can(State.STOPPED):
            self.flow.go(State.STOPPED)

    def pump(self):
        now = self._clock()
        st = self.state
        due = self._deadline is not None and now >= self._deadline
        if st == State.SCANNING and due:
            self._deadline = None
            self.flow.go(State.DEVICES_FOUND)
            self.events.emit("devices", [{"name": "Replay", "serial": self.name, "type": "replay"}])
        elif st == State.CONNECTING and due:
            self._deadline = None
            self._connected()
        elif st == State.CALIBRATING:
            if due:
                self._finish_calibration()
            else:
                self._pre_stream(now)
        elif st == State.BASELINE:
            span = config.REPLAY_STEP_S
            left = (self._deadline - now) if self._deadline else 0
            self.events.emit("baseline_progress", max(0.0, min(1.0, 1 - left / span)))
            if due:
                self._send_baseline_rows()
                self._go_live()
            else:
                self._pre_stream(now)
        elif st in (State.STREAMING, State.CALIBRATED):
            self._pre_stream(now)
        elif st == State.LIVE:
            self._live_stream(now)

    # ── internals ────────────────────────────────────────────────
    def _connected(self):
        cal = self.meta.get("calibration") or {}
        self.device_info = {"name": "Replay", "serial": self.name, "type": "replay",
                            "channels": self.channel_names, "sample_rate": self.sample_rate,
                            "sdk_version": "replay", "simulated": True, "replay_of": self.path,
                            "original_device": (self.meta.get("device") or {}).get("serial")}
        self.flow.go(State.STREAMING)
        self._pre_t0 = self._clock()
        self._ptr = {}
        self.events.emit("connected", dict(self.device_info))
        self.events.emit("status", f"Replaying {self.name} (recorded data, not live)")
        if not cal:
            self.events.emit("error", "This recording has no calibration; typical values will be used.")

    def _finish_calibration(self):
        cal = dict(self.meta.get("calibration") or {"iapf": 10.0, "iaf": 10.0})
        cal.update(fail_reason=0, imported=False, replayed=True)
        self.calibration = cal
        if self.state != State.CALIBRATED:
            self.flow.go(State.CALIBRATED)
        self._deadline = None
        self.events.emit("calibrated", dict(cal))

    def _pre_stream(self, now):
        """Before live: loop the recording's pre-live resistances and EEG so the signal screen moves."""
        if self._pre_t0 is None:
            return
        pre = [g for g in self._resist if g[0] < self.t_live] or self._resist
        if pre:
            span = max(1.0, pre[-1][0] - pre[0][0] + 1.0)
            pos = pre[0][0] + ((now - self._pre_t0) * self.speed) % span
            last = self._ptr.get("pre_res")
            idx = max((i for i, g in enumerate(pre) if g[0] <= pos), default=0)
            if idx != last:
                self._ptr["pre_res"] = idx
                self._emit_res(pre[idx][1])
        if self._eeg:
            self._emit_eeg_until(self._eeg[0]["_t"] + (now - self._pre_t0) * self.speed, key="pre_eeg")

    def _send_baseline_rows(self):
        """The recording's baseline period (band powers + ratios), sent in one go so the Monitor
        builds the same rest reference as in the original session."""
        for row in self._streams["bands"]:
            if self.t_base <= row["_t"] < self.t_live:
                self.events.emit("band_frame", self._band_frame(row))
        for row in self._streams["indices"]:
            if self.t_base <= row["_t"] < self.t_live:
                self.events.emit("index_values", *self._index_values(row))

    def _go_live(self):
        b = self.meta.get("baseline") or dict(config.FAST_BASELINE, relaxation=1.0)
        self.baseline = {k: b.get(k) for k in ("concentration", "relaxation", "fatigue", "reverse_fatigue",
                                               "gravity", "productivity")}
        self.baseline["imported"] = False
        self.baseline["replayed"] = True
        self._deadline = None
        self.flow.go(State.LIVE)
        self._live_t0 = self._clock()
        self._ptr = {name: 0 for name in self._streams}
        self._ptr.update(res=0, art=0, eeg=self._first_index(self._eeg, self.t_live))
        for name, rows in self._streams.items():
            self._ptr[name] = self._first_index(rows, self.t_live)
        self._ptr["res"] = self._first_index_g(self._resist, self.t_live)
        self._ptr["art"] = self._first_index_g(self._artifacts, self.t_live)
        self.events.emit("baseline", dict(self.baseline))

    @staticmethod
    def _first_index(rows, t):
        return next((i for i, r in enumerate(rows) if r["_t"] >= t), len(rows))

    @staticmethod
    def _first_index_g(groups, t):
        return next((i for i, g in enumerate(groups) if g[0] >= t), len(groups))

    def _live_stream(self, now):
        pos = self.t_live + (now - self._live_t0) * self.speed
        for name in ("indices", "bands", "emotions", "productivity", "indexes", "events"):
            rows, i = self._streams[name], self._ptr[name]
            while i < len(rows) and rows[i]["_t"] <= pos:
                self._emit_row(name, rows[i])
                i += 1
            self._ptr[name] = i
        for key, groups, emit in (("res", self._resist, self._emit_res), ("art", self._artifacts, self._emit_art)):
            i = self._ptr[key]
            while i < len(groups) and groups[i][0] <= pos:
                emit(groups[i][1])
                i += 1
            self._ptr[key] = i
        if self._eeg:
            self._emit_eeg_until(pos, key="eeg")
        if pos >= self.t_end and not self._finished:
            self._finished = True
            self.events.emit("replay_finished")
            self.events.emit("status", "The recording has ended.")

    def _emit_eeg_until(self, pos, key):
        """eeg.csv (only if the original ran with --record-eeg): processed values for the trace.
        Raw is not sent, so band powers come from bands.csv exactly as recorded."""
        i = self._ptr.get(key, 0)
        n_ch = len(self.channel_names)
        block = []
        while i < len(self._eeg) and self._eeg[i]["_t"] <= pos and len(block) < 2000:
            r = self._eeg[i]
            block.append([_f(r.get(f"{c}_processed")) for c in self.channel_names])
            i += 1
        if key == "pre_eeg" and i >= len(self._eeg):
            i = 0
        self._ptr[key] = i
        if block:
            import numpy as np
            self.events.emit("eeg", list(range(len(block))), np.array(block, dtype=float).reshape(-1, n_ch), None)

    def _emit_res(self, rows):
        values = {}
        for r in rows:
            v = r.get("ohms", "")
            values[r.get("electrode", "?")] = math.inf if v in ("inf", "") else _f(v)
        self.events.emit("resistances", values)

    def _emit_art(self, rows):
        flags = [(int(_f(r.get("artifact")) or 0) if math.isfinite(_f(r.get("artifact"))) else 0,
                  _f(r.get("quality"))) for r in rows]
        self.events.emit("artifacts", rows[0].get("sdk_ms"), flags)

    def _band_frame(self, row):
        rejected = row.get("rejected") or None
        ptp = _f(row.get("ptp_uv")) * 1e-6
        if rejected:
            return {"rel": None, "abs": None, "ptp": ptp, "rejected": rejected}
        rel = {b: _f(row.get(f"{b}_rel")) for b in config.RAW_BANDS}
        absolute = {b: _f(row.get(f"{b}_uv2")) * 1e-12 for b in config.RAW_BANDS}
        if not all(math.isfinite(v) for v in rel.values()):
            return {"rel": None, "abs": None, "ptp": ptp, "rejected": "missing"}
        return {"rel": rel, "abs": absolute, "ptp": ptp, "rejected": None}

    @staticmethod
    def _index_values(row):
        rel = {b: _f(row.get(b)) for b in ("delta", "theta", "alpha", "smr", "beta")}
        own = {k: _f(row.get(k)) for k in INDEX_KEYS}
        return rel, own

    def _emit_row(self, name, row):
        if name == "indices":
            self.events.emit("index_values", *self._index_values(row))
        elif name == "bands":
            self.events.emit("band_frame", self._band_frame(row))
        elif name == "emotions":
            self.events.emit("emotions", {"sdk_ms": row.get("sdk_ms"),
                                          **{k: _f(row.get(k)) for k in ("attention", "relaxation", "cognitive_load",
                                                                         "cognitive_control", "self_control")}})
        elif name == "productivity":
            self.events.emit("productivity", {k: _f(v) for k, v in row.items()
                                              if k not in ("unix_time", "_t", "sdk_ms")} | {"sdk_ms": row.get("sdk_ms")})
        elif name == "indexes":
            self.events.emit("indexes", {"sdk_ms": row.get("sdk_ms"), "recommendation": row.get("recommendation"),
                                         "stress": row.get("stress"), "has_artifacts": row.get("has_artifacts")})
        elif name == "events":
            kind, detail = row.get("kind", ""), row.get("detail", "") or ""
            if kind == "scene_start":
                self.events.emit("replay_scene", detail.split(" ", 1)[0])
            elif kind == "scene_end":
                self.events.emit("replay_scene", None)
            elif kind == "marker":
                self.events.emit("replay_marker", detail)
            elif kind in ("break_start", "break_end"):
                self.events.emit("replay_break", kind == "break_start")
