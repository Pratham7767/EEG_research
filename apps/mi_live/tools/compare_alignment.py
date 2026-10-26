"""Which alignment works best live? On 2b E sessions (each subject unseen by its model):
  A  60 s calibration -> fixed reference + bias           (the window's default)
  B  60 s calibration -> fixed reference, no bias
  C  no calibration: running mean of ALL past covariances (keeps updating; causal, no labels)
  D  like C, plus running-mean bias removal (mean of all past outputs)
Fast, offline but causal (each output only uses the past).  -> _out/compare_alignment.txt"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.dsp import apply_montage  # noqa: E402
from mibci.svm import align, covwindow_offline, decide, reference, unflat  # noqa: E402
from mibci.svm_trainer import RunCov  # noqa: E402,F401
from mibci.trainer import artifact_flags  # noqa: E402
from milive import settings as S  # noqa: E402
from milive.replay2b import load_session, loso_decoder  # noqa: E402

DEC_CH = [C.CHANNELS.index(c) for c in C.DECODE_CHANNELS]


def score(I, d, bad, cues, art):
    k = n = 0
    for cue, cls in cues:
        if cue < 60 * S.FS or cue in art:
            continue
        m = (I >= cue + 1.5 * S.FS) & (I <= cue + 4 * S.FS) & ~bad
        if m.any():
            pred = C.RIGHT if np.mean(np.where(d[m] >= 0, 1, -1)) >= 0 else C.LEFT
            k += pred == cls
            n += 1
    return k / n


res = {m: [] for m in "ABCD"}
for sub in range(1, 10):
    p = loso_decoder(sub).p
    for ses in (4, 5):
        eeg, ev, art = load_session(sub, ses)
        cues = [(s, c) for s, e, c in ev if e.startswith("cue_")]
        x = apply_montage(eeg)
        I, F = covwindow_offline(x, DEC_CH)
        bad = artifact_flags(x, I)
        cal = (I < 60 * S.FS) & ~bad
        R = reference(F[cal])
        dA = decide(p, align(F, R))
        bias = dA[cal].mean()
        cs = np.cumsum(F, 0) / np.arange(1, len(F) + 1)[:, None]          # running mean (causal)
        dC = np.array([decide(p, align(F[j:j + 1], unflat(cs[j])))[0] for j in range(len(F))])
        rb = np.cumsum(dC) / np.arange(1, len(dC) + 1)
        for m, d in (("A", dA - bias), ("B", dA), ("C", dC), ("D", dC - rb)):
            res[m].append(score(I, d, bad, cues, art))
    print(f"B{sub:02d}", {m: round(np.mean(v[-2:]), 3) for m, v in res.items()}, flush=True)
print("MEAN", {m: round(float(np.mean(v)), 3) for m, v in res.items()})
