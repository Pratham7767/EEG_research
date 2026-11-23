"""Session folder with one CSV per data stream plus session.json."""
import csv
import datetime
import json
import math
import os
import time

from . import config
from .metrics import INDEX_DEFINITIONS

STREAMS = {
    "productivity": ["unix_time", "sdk_ms", "concentration", "relaxation", "fatigue",
                     "reverse_fatigue", "gravity", "productivity", "current_value", "alpha",
                     "accumulated_fatigue", "fatigue_growth_rate"],
    "indexes":      ["unix_time", "sdk_ms", "recommendation", "stress", "has_artifacts"],
    "emotions":     ["unix_time", "sdk_ms", "attention", "relaxation", "cognitive_load",
                     "cognitive_control", "self_control"],
    "indices":      ["unix_time", "delta", "theta", "alpha", "smr", "beta", *INDEX_DEFINITIONS],
    "resistances":  ["unix_time", "electrode", "ohms", "grade"],
    "artifacts":    ["unix_time", "sdk_ms", "channel", "artifact", "quality"],
    "cardio":       ["unix_time", "sdk_ms", "heart_rate", "stress_index", "kaplan_index",
                     "has_artifacts", "skin_contact", "motion_artifacts", "metrics_available"],
    "bands":        ["unix_time", "rejected", "ptp_uv", *[f"{b}_rel" for b in config.RAW_BANDS],
                     *[f"{b}_uv2" for b in config.RAW_BANDS]],
    "scores":       ["unix_time", "elapsed_s", "attention", "cognitive_load", "stress", "relaxation", "fatigue",
                     "signal_poor", "in_break"],
    "events":       ["unix_time", "elapsed_s", "kind", "detail"],
    "eeg":          None,   # header depends on the channel names; see open_eeg()
}


def _fmt(value):
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        # Large values are timestamps: keep millisecond precision instead of 6 significant digits.
        return f"{value:.3f}" if abs(value) >= 1e6 else f"{value:.6g}"
    return value


class SessionWriter:
    """Creates sessions/<timestamp>/ and appends rows to per-stream CSV files."""

    def __init__(self, root=config.SESSIONS_DIR, name=None, clock=time.time):
        self._clock = clock
        self.started_at = clock()
        name = name or datetime.datetime.fromtimestamp(self.started_at).strftime("%Y-%m-%d_%H%M%S")
        self.path = os.path.join(root, name)
        os.makedirs(self.path, exist_ok=True)
        self.meta = {"session": name, "started_at": datetime.datetime.fromtimestamp(self.started_at).isoformat(timespec="seconds")}
        self._files = {}
        self._writers = {}
        self._headers = {}
        self.row_counts = {}
        self.closed = False

    # ── writing ──────────────────────────────────────────────────
    def open_eeg(self, channel_names):
        header = ["unix_time", "sdk_ms"] + [f"{c}_raw" for c in channel_names] + [f"{c}_processed" for c in channel_names]
        self._open("eeg", header)

    def _open(self, stream, header):
        if stream in self._writers:
            return
        fh = open(os.path.join(self.path, f"{stream}.csv"), "w", newline="", encoding="utf-8", buffering=1)
        writer = csv.writer(fh)
        writer.writerow(header)
        self._files[stream], self._writers[stream], self._headers[stream] = fh, writer, header
        self.row_counts[stream] = 0

    def write(self, stream, row):
        """row: dict keyed by the stream's header (missing keys → empty)."""
        if self.closed:
            return
        if stream not in self._writers:
            header = STREAMS.get(stream)
            if header is None:
                raise KeyError(f"stream {stream!r} has no fixed header")
            self._open(stream, header)
        row = dict(row)
        row.setdefault("unix_time", round(self._clock(), 3))
        self._writers[stream].writerow([_fmt(row.get(col, "")) for col in self._headers[stream]])
        self.row_counts[stream] += 1

    def write_values(self, stream, values):
        """Fast path for high-rate streams (EEG): values already in header order."""
        if not self.closed:
            self._writers[stream].writerow([_fmt(v) for v in values])
            self.row_counts[stream] += 1

    def event(self, kind, detail=""):
        now = self._clock()
        self.write("events", {"unix_time": round(now, 3), "elapsed_s": round(now - self.started_at, 1),
                              "kind": kind, "detail": detail})

    def set_meta(self, key, value):
        self.meta[key] = value
        if not self.closed:
            self._dump_meta()

    def _dump_meta(self):
        data = _clean(dict(self.meta, row_counts=self.row_counts))
        tmp = os.path.join(self.path, "session.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, allow_nan=False)
        os.replace(tmp, os.path.join(self.path, "session.json"))

    def close(self):
        if self.closed:
            return
        self.meta["ended_at"] = datetime.datetime.fromtimestamp(self._clock()).isoformat(timespec="seconds")
        self.meta["duration_s"] = round(self._clock() - self.started_at, 1)
        self._dump_meta()
        for fh in self._files.values():
            fh.close()
        self.closed = True


def _clean(obj):
    """Make meta JSON-safe: NaN/inf → null, numpy scalars → float, unknown → str."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if obj is None or isinstance(obj, (bool, str, int)):
        return obj
    try:
        value = float(obj)
    except (TypeError, ValueError):
        return str(obj)
    return value if math.isfinite(value) else None


def load_meta(path):
    with open(os.path.join(path, "session.json"), encoding="utf-8") as fh:
        return json.load(fh)
