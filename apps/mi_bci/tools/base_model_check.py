"""Does a model trained on BCI IV 2b help on OUR headset? Compares, run by run:

  A  2b only     CSP+SVM with Euclidean Alignment trained on all 9 2b subjects (C3, C4); our run is
                 aligned with no labels and classified. Zero calibration.
  B  2b + own    the same, trained on 2b PLUS this subject's other runs; tested on the left-out run.
  C  own only    CSP+SVM with EA on this subject's other runs only; tested on the left-out run.

Epochs: 0.5-3.5 s after the cue, 8-30 Hz, C3-A1 and C4-A2 (the app's montage). p = one-sided binomial.
Usage: python tools/base_model_check.py P01
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, detrend, filtfilt
from scipy.stats import binomtest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from mibci import config as C                      # noqa: E402
from mibci.dsp import apply_montage                # noqa: E402
from mibci.recorder import list_runs, load_run     # noqa: E402

sys.path.insert(0, str(C.REPO / "experiments" / "05_bci_iv_2b"))
import gelo_svm_pipeline as G                      # noqa: E402

FS = C.FS
I = [C.CHANNELS.index("C3"), C.CHANNELS.index("C4")]


def epochs_from_run(path):
    r = load_run(path)
    x = apply_montage(np.nan_to_num(r["eeg"]))[:, I]
    b, a = butter(G.FILTER_ORDER, G.BAND, btype="band", fs=FS)
    x = filtfilt(b, a, detrend(x, axis=0, type="constant"), axis=0)
    eps, ys = [], []
    for s, name, c in r["events"]:
        if name in ("cue_left", "cue_right"):
            a0, a1 = s + int(G.TMIN * FS), s + int(G.TMAX * FS)
            if a1 <= len(x):
                eps.append(x[a0:a1].T)
                ys.append(0 if c == C.LEFT else 1)
    return np.stack(eps), np.array(ys), r["meta"].get("run_type")


def score(y, yhat):
    k, n = int((y == yhat).sum()), len(y)
    return dict(acc=round(k / n, 3), n=n, p=round(binomtest(k, n, 0.5, alternative="greater").pvalue, 4))


def main(subject):
    runs = [p for p in list_runs(subject) if json.loads((p / "run.json").read_text()).get("run_type")
            in ("movement", "screening", "feedback")]
    data = [epochs_from_run(p) for p in runs]
    X2b, y2b, g2b = G.load_2b(channels=(0, 2))
    base = G.GeloDecoder("csp_svm", use_ea=True).fit(X2b, y2b, g2b)
    out = {}
    for k, (p, (X, y, rt)) in enumerate(zip(runs, data)):
        res = dict(run_type=rt)
        res["A_2b_only"] = score(y, base.predict(X, np.zeros(len(y), int)))
        others = [d for j, d in enumerate(data) if j != k]
        if others:
            Xo = np.concatenate([d[0] for d in others])
            yo = np.concatenate([d[1] for d in others])
            go = np.concatenate([np.full(len(d[1]), 1000 + j) for j, d in enumerate(others)])
            both = G.GeloDecoder("csp_svm", use_ea=True).fit(np.concatenate([X2b, Xo]),
                                                                np.concatenate([y2b, yo]),
                                                                np.concatenate([g2b, go]))
            res["B_2b_plus_own"] = score(y, both.predict(X, np.zeros(len(y), int)))
            own = G.GeloDecoder("csp_svm", use_ea=True).fit(Xo, yo, go)
            res["C_own_only"] = score(y, own.predict(X, np.zeros(len(y), int)))
        out[p.name] = res
    tot = {}
    for key in ("A_2b_only", "B_2b_plus_own", "C_own_only"):
        ks = [(v[key]["acc"] * v[key]["n"], v[key]["n"]) for v in out.values() if key in v]
        if ks:
            k, n = sum(a for a, _ in ks), sum(b for _, b in ks)
            tot[key] = dict(acc=round(k / n, 3), n=n,
                            p=round(binomtest(int(round(k)), n, 0.5, alternative="greater").pvalue, 4))
    out["ALL_RUNS"] = tot
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "P01")
