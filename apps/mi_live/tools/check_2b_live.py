"""Competition-style check on real EEG: every BCI IV 2b subject streamed through mi_live exactly as live.

For each subject B0x: model = base SVM trained on the other 8 subjects (never saw B0x). Evaluation
sessions 4 and 5 (the competition's E sessions) are streamed with random packet sizes. Adaptive alignment
(running mean, no labels); the first 60 s are warm-up and not scored, then every trial is scored: trial accuracy (1.5-4 s, as the app)
and the competition metric (max kappa over time), artifact trials left out as in the competition.
Also checks live outputs == an independent offline computation (milive/offline.py).
    Optional --model=<name> from milive/train2b.SPECS (default: the chosen best model).
    C:\\Python313\\python.exe tools\\check_2b_live.py [subjects]     -> _out/check_2b_live.json
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.paradigm import RecordedParadigm  # noqa: E402
from milive import settings as S  # noqa: E402
from milive.cued import CuedSession  # noqa: E402
from milive.pipeline import LivePipeline  # noqa: E402
from milive.models import LinearCovModel  # noqa: E402
from milive.offline import offline_outputs  # noqa: E402
from milive.replay2b import best_spec, load_session, loso_model  # noqa: E402

OUT = S.OUT_DIR / "check_2b_live.json"


def one(dec_dict, sub, ses):
    eeg, events, art = load_session(sub, ses)
    p = LivePipeline(LinearCovModel.from_dict(dec_dict))
    p.start_calibration([("data", 60)])
    s = CuedSession(RecordedParadigm("feedback", events), 0, min_cue=60 * S.FS)
    rng = np.random.default_rng(sub * 10 + ses)
    pos = 0
    while pos < len(eeg):
        k = int(rng.integers(1, 38))
        x = eeg[pos:pos + k]
        s.process(x, p.n + len(x), p.feed(x))
        pos += k
    idx, d_off, _ = offline_outputs(p.model, eeg)                   # independent re-computation
    I, D = np.array(s.I), np.array(s.D)
    same = np.array_equal(I, idx) and float(np.max(np.abs(D - d_off))) < 1e-9
    return s.results(exclude=art), s.results(), same


def main(subs, spec=None):
    global OUT
    if len(subs) == 1:                               # one subject per process can run in parallel
        OUT = S.OUT_DIR / f"check_2b_live_B{subs[0]:02d}.json"
    spec = spec or best_spec()
    print("model:", spec, flush=True)
    res = {"model": spec}
    for sub in subs:
        t0 = time.time()
        dec = loso_model(sub, spec).to_dict()
        r = {}
        for ses in (4, 5):
            clean, allt, same = one(dec, sub, ses)
            r[ses] = dict(accuracy=clean["accuracy"], trials=clean["trials"], p=clean["p"],
                          accuracy_all_trials=allt["accuracy"], trials_all=allt["trials"],
                          max_kappa=clean["max_kappa_raw"], t_max_kappa=clean["max_kappa_raw_t"],
                          max_kappa_smoothed=clean["max_kappa_smoothed"],
                          chance95=clean["max_kappa_chance95"], confusion=clean["confusion"], identical_to_offline=same)
        k = sum(r[s]["accuracy"] * r[s]["trials"] for s in r)
        n = sum(r[s]["trials"] for s in r)
        res[f"B{sub:02d}"] = dict(sessions=r, accuracy=k / n, trials=n,
                                  max_kappa_mean=float(np.mean([r[s]["max_kappa"] for s in r])),
                                  seconds=round(time.time() - t0, 1))
        print(f"B{sub:02d}: acc S4 {r[4]['accuracy']:.3f} S5 {r[5]['accuracy']:.3f} | max kappa S4 {r[4]['max_kappa']:.2f} "
              f"S5 {r[5]['max_kappa']:.2f} | identical {r[4]['identical_to_offline'] and r[5]['identical_to_offline']} "
              f"| {res[f'B{sub:02d}']['seconds']} s", flush=True)
        OUT.write_text(json.dumps(res, indent=1, default=float))
    subs_res = [v for k, v in res.items() if k != "model"]
    if len(subs_res) > 1:
        print("MEAN accuracy", round(np.mean([v["accuracy"] for v in subs_res]), 3),
              "| mean max kappa", round(np.mean([v["max_kappa_mean"] for v in subs_res]), 3))


if __name__ == "__main__":
    S.OUT_DIR.mkdir(exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--model=")]
    spec = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--model=")), None)
    main([int(a) for a in args] or list(range(1, 10)), spec)
