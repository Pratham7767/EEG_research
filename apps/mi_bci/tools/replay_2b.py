"""Verification on real EEG (milestone M3): replay BCI Competition IV 2b through the live engine.

For each subject:
  1. convert the 2b sessions into our run format (C3, C4 only; Cz and EOG dropped), split into the
     original runs (screening: 20 trials per run, feedback: 40 per run), cue at trial + 3 s
  2. train the Graz-style decoder on the two SCREENING sessions only (01T, 02T), as Graz did
  3. stream every feedback-session run (03T, 04E, 05E) through Engine with random packet sizes,
     exactly as if it came from a headset, and record the live outputs
  4. compare the live outputs with the offline trainer's numbers for the same run: they must be
     identical; report the online trial accuracy and the Graz integrated error per session

Usage (from apps/mi_bci):  python tools/replay_2b.py [subjects...]   e.g.  python tools/replay_2b.py 4 8
Writes _out/replay_2b/summary.json and per-subject folders.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci import config as C                                   # noqa: E402
from mibci.engine import Engine                                 # noqa: E402
from mibci.paradigm import RecordedParadigm                     # noqa: E402
from mibci.recorder import Recorder, load_run, write_run        # noqa: E402
from mibci.sources import ReplaySource                          # noqa: E402
from mibci.trainer import RunFeatures, evaluate_decoder, train  # noqa: E402

OUT = C.APP_DIR / "_out" / "replay_2b"


class RandomChunkReplay(ReplaySource):
    """Replay with random packet sizes (1-37 samples) to prove outputs do not depend on packetisation."""

    def __init__(self, data, seed=0):
        super().__init__(data)
        self.rng = np.random.default_rng(seed)

    def read(self):
        self.chunk = int(self.rng.integers(1, 38))
        return super().read()


def sessions(sub):
    for split, ids in (("T", (1, 2, 3)), ("E", (4, 5))):
        m = loadmat(C.BCI2B_DIR / f"B{sub:02d}{split}.mat", squeeze_me=True, struct_as_record=False)
        for sid, s in zip(ids, np.atleast_1d(m["data"])):
            yield sid, np.asarray(s.X, float), np.atleast_1d(s.trial).astype(int) - 1, np.atleast_1d(s.y).astype(int)


def convert(sub):
    """Write our run folders; returns {session_id: [run paths]}."""
    runs = {}
    for sid, X, trial, y in sessions(sub):
        per_run = 20 if sid <= 2 else 40
        rtype = "screening" if sid <= 2 else "feedback"
        t = C.TIMING[rtype]
        runs[sid] = []
        for r0 in range(0, len(trial), per_run):
            tr, yy = trial[r0:r0 + per_run], y[r0:r0 + per_run]
            a = max(0, tr[0] - 2 * C.FS)
            b = min(len(X), tr[-1] + int(9.5 * C.FS))
            eeg = np.zeros((b - a, 4))
            eeg[:, 1], eeg[:, 2] = X[a:b, 0], X[a:b, 2]          # C3, C4 (Cz dropped: headphones have none)
            ev = [(0, "run_start", None)]
            for s0, c in zip(tr - a, yy):
                ev.append((int(s0), "trial_start", int(c)))
                ev.append((int(s0 + 3 * C.FS), "cue_left" if c == C.LEFT else "cue_right", int(c)))
                if rtype == "feedback":
                    ev.append((int(s0 + 3 * C.FS), "feedback_start", int(c)))
                else:
                    ev.append((int(s0 + int(t["cue_off"] * C.FS)), "cue_off", int(c)))
                ev.append((int(s0 + int(t["task_end"] * C.FS)), "task_end", int(c)))
            ev.append((len(eeg) - 1, "run_end", None))
            p = OUT / f"B{sub:02d}" / "runs" / f"s{sid}_{rtype}_run{r0 // per_run + 1}"
            write_run(p, eeg, ev, dict(subject=f"B{sub:02d}", run_type=rtype, source="BCI IV 2b",
                                       session=sid, fs=C.FS, channels=C.CHANNELS))
            runs[sid].append(p)
    return runs


def replay(run_path, dec, sub, seed):
    r = load_run(run_path)
    src = RandomChunkReplay(r["eeg"], seed)
    par = RecordedParadigm("feedback", r["events"])
    rec = Recorder(f"B{sub:02d}", "replay", root=OUT / f"B{sub:02d}" / "live")
    eng = Engine(src, par, dec, rec)
    while not src.finished:
        eng.pump()
    summ = eng.finish(dict(replayed_from=str(run_path)))
    live = load_run(rec.dir)["outputs"]
    # offline: same decoder, same run, trainer code path
    rf = RunFeatures(r, bands=dec.bands, montage=dec.meta.get("montage"))
    d_off = rf.F @ dec.w + dec.b
    same_idx = np.array_equal(live[:, 0].astype(int), rf.idx)
    max_diff = float(np.max(np.abs(live[:, 1] - d_off))) if same_idx else float("nan")
    same_art = bool(np.array_equal(live[:, 3].astype(bool), rf.art)) if same_idx else False
    off_acc, off_ice, n = evaluate_decoder(dec, run_path)
    return dict(run=Path(run_path).name, live_accuracy=summ["accuracy"], live_integrated_error=summ["integrated_error"],
                offline_accuracy=off_acc, trials=n, same_output_samples=same_idx, max_abs_distance_diff=max_diff,
                same_artifact_flags=same_art, artifact_fraction=float(np.mean(rf.art)))


def main(subs):
    OUT.mkdir(parents=True, exist_ok=True)
    allres = {}
    for sub in subs:
        t0 = time.time()
        runs = convert(sub)
        screening = runs[1] + runs[2]
        dec, rep = train(screening, f"B{sub:02d}", out_dir=OUT / f"B{sub:02d}" / "decoders", n_perm=100)
        res = dict(training=rep, sessions={})
        for sid in (3, 4, 5):
            rr = [replay(p, dec, sub, seed=sid * 10 + k) for k, p in enumerate(runs[sid])]
            n = sum(x["trials"] for x in rr)
            res["sessions"][sid] = dict(
                runs=rr,
                live_accuracy=float(sum(x["live_accuracy"] * x["trials"] for x in rr) / n),
                live_integrated_error=float(np.mean([x["live_integrated_error"] for x in rr])),
                identical_to_offline=all(x["same_output_samples"] and x["max_abs_distance_diff"] < 1e-6  # csv: 6 decimals
                                         and x["same_artifact_flags"]
                                         and abs(x["live_accuracy"] - x["offline_accuracy"]) < 1e-12 for x in rr))
        res["seconds"] = round(time.time() - t0, 1)
        allres[f"B{sub:02d}"] = res
        s = res["sessions"]
        print(f"B{sub:02d}: screening nested acc {rep.get('nested_run_accuracy'):.3f} p={rep.get('permutation_p'):.3f} "
              f"features {rep['features']} | live acc S3 {s[3]['live_accuracy']:.3f} S4 {s[4]['live_accuracy']:.3f} "
              f"S5 {s[5]['live_accuracy']:.3f} | identical {[s[k]['identical_to_offline'] for k in (3, 4, 5)]} "
              f"| {res['seconds']} s", flush=True)
        (OUT / "summary.json").write_text(json.dumps(allres, indent=2, default=float))
    return allres


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or list(range(1, 10)))
