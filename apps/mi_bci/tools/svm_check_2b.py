"""Verify the app's SVM on real EEG (BCI IV 2b), the way it will be used on a new person:

For each 2b subject S (treated as a NEW user):
  base      SVM trained on the OTHER 8 subjects only
  improve   train_from_runs() with S's two screening sessions as 'their recordings' (the app's Train
            button): picks 2b only / 2b + yours / yours only by leave-one-run-out on those runs
  live      S's feedback sessions (3, 4, 5) streamed through the live Engine, run by run. Alignment uses
            only EARLIER runs of the same session (the first run of a session uses the running mean),
            exactly as it would live. Reported for the base model and for the improved model.
  check     Engine outputs vs the offline scorer: must be identical.
Needs the converted runs in _out/replay_2b (tools/replay_2b.py) and the cache (tools/build_base_svm.py).
Usage: python tools/svm_check_2b.py [subjects...]
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci import config as C                                                    # noqa: E402
from mibci.engine import Engine                                                  # noqa: E402
from mibci.paradigm import RecordedParadigm                                      # noqa: E402
from mibci.recorder import load_run                                              # noqa: E402
from mibci.sources import ReplaySource                                           # noqa: E402
from mibci.svm import SvmDecoder, reference                                      # noqa: E402
from mibci.svm_trainer import base_rows, fit_params, runs_2b, score_run, train_from_runs  # noqa: E402

RUNS = C.APP_DIR / "_out" / "replay_2b"
OUT = C.APP_DIR / "_out" / "svm_check_2b.json"


def live(dec_params, meta, sub, cache_runs):
    """Stream S3-S5 runs through the Engine; returns (accuracy, all_identical)."""
    k = n = 0
    same = True
    for sid in (3, 4, 5):
        sess = [r for r in cache_runs if r.day == f"B{sub:02d}_S{sid}"]
        for j, rc in enumerate(sess):
            R = reference(np.vstack([p.F[~p.art] for p in sess[:j]])) if j else None
            dec = SvmDecoder(dec_params, meta, ref=R)
            run = load_run(RUNS / f"B{sub:02d}" / "runs" / f"s{sid}_feedback_run{j + 1}")
            src = ReplaySource(run["eeg"], chunk=13)
            eng = Engine(src, RecordedParadigm("feedback", run["events"]), dec, None)
            while not src.finished:
                eng.pump()
            s = eng.finish()
            if R is not None:                       # offline scorer must give the same result
                acc, _, nt, _ = score_run(dec.p, rc, R)
                same = same and abs(acc - s["accuracy"]) < 1e-12 and nt == s["trials_scored"]
            k += round(s["accuracy"] * s["trials_scored"])
            n += s["trials_scored"]
    return k / n, n, same


def main(subs):
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    meta = dict(eval_win=[1.5, 4.0], montage=C.MONTAGE)
    for sub in subs:
        others = [s for s in range(1, 10) if s != sub]
        base = base_rows(others)
        mine = runs_2b(sub)
        screening = [r for r in mine if r.day in (f"B{sub:02d}_S1", f"B{sub:02d}_S2")]
        dec, rep = train_from_runs(screening, f"B{sub:02d}", base=base)
        a_base, n, same_b = live(fit_params(*base), meta, sub, mine)
        a_imp, _, same_i = live(dec.p, dict(meta, **dec.meta), sub, mine)
        res[f"B{sub:02d}"] = dict(base_only_live=round(a_base, 3), improved_live=round(a_imp, 3), trials=n,
                                  chosen=rep["weighting"], screening_scores=rep.get("weightings"),
                                  identical_to_offline=bool(same_b and same_i))
        print(f"B{sub:02d}: base-only {a_base:.3f} | improved {a_imp:.3f} ({rep['weighting']}) | "
              f"screening LORO {rep.get('weightings')} | identical {same_b and same_i}", flush=True)
        OUT.write_text(json.dumps(res, indent=2))
    if len(res) > 1:
        print("MEAN base-only", round(np.mean([v['base_only_live'] for v in res.values()]), 3),
              "improved", round(np.mean([v['improved_live'] for v in res.values()]), 3))


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or list(range(1, 10)))
