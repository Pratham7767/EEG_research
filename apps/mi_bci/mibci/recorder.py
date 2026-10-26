"""Writes one run to its own folder and reads it back.

data/mi_bci/<subject>/<YYYY-MM-DD_HHMMSS>_<run_type>/
    eeg.csv       sample, A1, C3, C4, A2           (microvolts, one row per sample)
    events.csv    sample, code, event, class, wall_time
    outputs.csv   sample, distance, integrated, artifact   (decoder outputs, if a decoder ran)
    run.json      subject, run type, schedule, timing, decoder, counts, problems seen
"""
import csv
import json
import time
from pathlib import Path

import numpy as np

from . import config as C


class Recorder:
    def __init__(self, subject, run_type, root=C.DATA_DIR, meta=None):
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        self.dir = Path(root) / subject / f"{stamp}_{run_type}"
        n = 1
        while self.dir.exists():
            n += 1
            self.dir = Path(root) / subject / f"{stamp}_{run_type}_{n}"
        self.dir.mkdir(parents=True)
        self.meta = dict(subject=subject, run_type=run_type, started=stamp, fs=C.FS,
                         channels=C.CHANNELS, timing=C.TIMING.get(run_type), **(meta or {}))
        self._eeg = open(self.dir / "eeg.csv", "w", newline="")
        self._eeg.write("sample," + ",".join(C.CHANNELS) + "\n")
        self._ev = open(self.dir / "events.csv", "w", newline="")
        self._ev.write("sample,code,event,class,wall_time\n")
        self._out = open(self.dir / "outputs.csv", "w", newline="")
        self._out.write("sample,distance,integrated,artifact\n")
        self.n = 0
        self.closed = False

    def eeg(self, x):
        if len(x) == 0:
            return
        idx = np.arange(self.n, self.n + len(x))[:, None]
        np.savetxt(self._eeg, np.hstack([idx, x]), fmt=["%d"] + ["%.3f"] * x.shape[1], delimiter=",")
        self.n += len(x)

    def event(self, sample, name, cls=None):
        self._ev.write(f"{sample},{C.EV.get(name, 0)},{name},{'' if cls is None else cls},{time.time():.4f}\n")

    def output(self, sample, d, integ, artifact):
        self._out.write(f"{sample},{d:.6f},{integ:.4f},{int(artifact)}\n")

    def close(self, extra=None):
        if self.closed:
            return
        for f in (self._eeg, self._ev, self._out):
            f.close()
        self.meta.update(extra or {})
        self.meta["n_samples"] = self.n
        self.meta["finished"] = time.strftime("%Y-%m-%d_%H%M%S")
        with open(self.dir / "run.json", "w") as f:
            json.dump(self.meta, f, indent=2, default=str)
        self.closed = True


def load_run(path):
    """Returns dict(eeg=(n,4) array, events=[(sample, name, cls)], outputs=array or None, meta)."""
    p = Path(path)
    eeg = np.loadtxt(p / "eeg.csv", delimiter=",", skiprows=1, ndmin=2)
    eeg = eeg[:, 1:] if eeg.size else np.zeros((0, 4))
    events = []
    with open(p / "events.csv") as f:
        for r in csv.DictReader(f):
            events.append((int(r["sample"]), r["event"], int(r["class"]) if r["class"] else None))
    out = None
    f_out = p / "outputs.csv"
    if f_out.exists() and len(f_out.read_text().splitlines()) > 1:
        out = np.loadtxt(f_out, delimiter=",", skiprows=1, ndmin=2)
    meta = json.loads((p / "run.json").read_text()) if (p / "run.json").exists() else {}
    return dict(eeg=eeg, events=events, outputs=out, meta=meta, path=str(p))


def write_run(path, eeg, events, meta):
    """Write a run folder from arrays (used to convert 2b sessions into our format)."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    idx = np.arange(len(eeg))[:, None]
    np.savetxt(p / "eeg.csv", np.hstack([idx, eeg]), fmt=["%d"] + ["%.3f"] * eeg.shape[1], delimiter=",",
               header="sample," + ",".join(C.CHANNELS), comments="")
    with open(p / "events.csv", "w", newline="") as f:
        f.write("sample,code,event,class,wall_time\n")
        for s, name, cls in events:
            f.write(f"{s},{C.EV.get(name, 0)},{name},{'' if cls is None else cls},\n")
    (p / "outputs.csv").write_text("sample,distance,integrated,artifact\n")
    (p / "run.json").write_text(json.dumps(meta, indent=2, default=str))


def list_runs(subject, run_types=None, root=C.DATA_DIR):
    d = Path(root) / subject
    if not d.exists():
        return []
    runs = sorted(p for p in d.iterdir() if p.is_dir() and (p / "eeg.csv").exists())
    if run_types:
        runs = [p for p in runs if json.loads((p / "run.json").read_text()).get("run_type") in run_types]
    return runs
