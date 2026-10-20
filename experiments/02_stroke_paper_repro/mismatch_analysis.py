"""
Why can't the paper's accuracies (Liu et al., Sci Data 2024, Table 4) be reproduced?

Re-implements the authors' evaluation protocols from code/code/*.m in Python and runs each one
twice: on the true labels, and on randomly permuted labels (true accuracy = 50 % by construction).
If a protocol scores well above 50 % on permuted labels, its number comes from selecting on the
test set, not from the EEG.

Protocols (all: 29 ch, 50 Hz notch, causal Butterworth, 0-4 s after MI onset, 10 x random 24/16):
  fbcsp_svm       FBCSP_SVM.m      one fixed pipeline, no selection
  tslda / fgmdm   TSLDA_DGFMDM.m   the two classifiers on their own
  tslda+fgmdm     TSLDA_DGFMDM.m   per split, keep whichever of the two scored higher ON TEST
  twfb_fgmdm      TWFB_DGFMDM.m    per repeat, 8 bands x new split each, keep MAX test accuracy
  fgmdm_8-30      honest version: one fixed band (8-30 Hz) with FgMDM, no selection
"""
import glob
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
from joblib import Parallel, delayed
from pyriemann.classification import FgMDM
from pyriemann.tangentspace import TangentSpace
from scipy.signal import butter, iirnotch, lfilter
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.pipeline import make_pipeline
from sklearn.svm import SVC

from train_fbcsp_svm import CHANNELS, FS, MARKER_CH, ROOT, fbcsp_fit_transform, load_subject

PAD, WIN = 800, 2000
TWFB_BANDS = [(8, 12), (8, 20), (8, 30), (12, 20), (15, 20), (15, 30), (20, 30), (8, 15)]


def epoch(raw, low, high):
    """As in the .m files: concatenate trials, notch, 2nd-order causal Butterworth, 0-4 s."""
    stream = np.concatenate(list(raw), axis=1)
    onsets = np.flatnonzero(stream[MARKER_CH] == 2)
    b_n, a_n = iirnotch(50, 6, fs=FS)
    b, a = butter(2, [low, high], "band", fs=FS)
    segs = np.stack([stream[CHANNELS, o - PAD:o + WIN] for o in onsets])
    return lfilter(b, a, lfilter(b_n, a_n, segs, axis=-1), axis=-1)[..., PAD:]


def cov(x):
    return np.einsum("tcs,tds->tcd", x, x)  # SS' * SS, as in the MATLAB code


def split(rng):
    idx = rng.permutation(40)
    return idx[:24], idx[24:]


def acc(model, xtr, ytr, xte, yte):
    return (model.fit(xtr, ytr).predict(xte) == yte).mean() * 100


def tslda():
    return make_pipeline(TangentSpace(metric="riemann"),
                         LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))


def run_subject(path, permute, seed):
    rng = np.random.default_rng(seed)
    raw, y = load_subject(path)
    if permute:
        y = rng.permutation(y)
    x430 = epoch(raw, 4, 30)                    # PlotAccuracy.m: LowFreq=4, UpFreq=30
    c430 = cov(x430)
    c830 = cov(epoch(raw, 8, 30))
    band_covs = [cov(epoch(raw, lo, hi)) for lo, hi in TWFB_BANDS]
    r = {k: [] for k in ["fbcsp_svm", "tslda", "fgmdm", "tslda+fgmdm", "twfb_fgmdm", "fgmdm_8-30"]}
    for _ in range(10):
        tr, te = split(rng)
        ftr, fte = fbcsp_fit_transform(x430[tr], y[tr], x430[te])
        r["fbcsp_svm"].append(acc(SVC(kernel="linear", C=1), ftr, y[tr], fte, y[te]))
        a1 = acc(tslda(), c430[tr], y[tr], c430[te], y[te])
        a2 = acc(FgMDM(metric="riemann"), c430[tr], y[tr], c430[te], y[te])
        r["tslda"].append(a1)
        r["fgmdm"].append(a2)
        r["tslda+fgmdm"].append(max(a1, a2))                   # chosen on the test set
        r["fgmdm_8-30"].append(acc(FgMDM(metric="riemann"), c830[tr], y[tr], c830[te], y[te]))
        per_band = []
        for cb in band_covs:                                    # new split for every band
            btr, bte = split(rng)
            per_band.append(acc(FgMDM(metric="riemann"), cb[btr], y[btr], cb[bte], y[bte]))
        r["twfb_fgmdm"].append(max(per_band))                   # best band chosen on the test set
    return {k: float(np.mean(v)) for k, v in r.items()}


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(ROOT, "sub-*", "*.mat")))
    paper = {"fbcsp_svm": "57.57", "tslda+fgmdm": "61.20", "twfb_fgmdm": "72.21"}
    out = {}
    for permute in (False, True):
        res = Parallel(n_jobs=-1)(delayed(run_subject)(f, permute, i) for i, f in enumerate(files))
        out[permute] = {k: np.mean([r[k] for r in res]) for k in res[0]}
    print(f"{'protocol':14} {'true labels':>12} {'SHUFFLED labels':>16} {'paper':>7}")
    for k in out[False]:
        print(f"{k:14} {out[False][k]:11.2f}% {out[True][k]:15.2f}% {paper.get(k, '-'):>7}")
