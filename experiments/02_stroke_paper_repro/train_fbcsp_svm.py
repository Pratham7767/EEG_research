"""
Python port of the authors' FBCSP + SVM pipeline (code/code/FBCSP_SVM.m + PlotAccuracy.m)
for the acute-stroke MI dataset (Liu et al., Sci Data 2024, 11:131).

Faithful to the MATLAB code, not only to the paper text:
  raw .mat -> 29 EEG ch -> 50 Hz notch -> 4-30 Hz Butterworth (causal) -> 0-4 s after MI cue
  -> 10 x random 24/16 split -> FBCSP (5 bands, m=2, 20 features) -> linear SVM (C=1)
"""
import glob
import os

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, iirnotch, lfilter, sosfilt
from sklearn.svm import SVC

ROOT = r"D:\trainsvm\data\stroke_liu2024\sourcedata\sourcedata"
FS = 500
LOW, HIGH = 4, 30                      # PlotAccuracy.m uses 4-30 Hz (paper text says 8-30)
CHANNELS = list(range(0, 17)) + list(range(18, 30))   # MATLAB [1:17 19:30]: drop CPz ref + EOG + marker
MARKER_CH = 32                          # 33rd row: 1=instruction, 2=MI onset, 3=break
PAD = 800                               # 1.6 s taken before onset only as filter warm-up, then discarded
WIN = 2000                              # 4 s * 500 Hz
FREQ_BANDS = [(10, 13), (13, 16), (16, 19), (19, 22), (22, 25)]
CSP_M = 2                               # 2 filter pairs -> 4 features per band
N_REPEATS, N_TRAIN = 10, 24             # 60 % / 40 % of 40 trials, repeated 10 times


def load_subject(path):
    e = loadmat(path)["eeg"][0, 0]
    return e["rawdata"].astype(np.float64), e["label"].ravel().astype(int)  # (40,33,4000), (40,)


def epoch(raw):
    """Notch + bandpass, then cut 0-4 s after the MI marker, as in FBCSP_SVM.m.

    Like PlotAccuracy.m, trials are concatenated into one stream first: in some trials the MI
    marker sits at sample 1 (the 8 s window starts at the cue), so the 1.6 s warm-up is taken
    from the end of the previous trial.
    """
    b_n, a_n = iirnotch(50, 6, fs=FS)                                   # NotchFilter.m, Q=6
    b_bp, a_bp = butter(2, [LOW / (FS / 2), HIGH / (FS / 2)], "band")   # BandpassFilter.m, N=2
    stream = np.concatenate(list(raw), axis=1)                          # (33, 40*4000)
    onsets = np.flatnonzero(stream[MARKER_CH] == 2)
    assert len(onsets) == raw.shape[0] and onsets[0] >= PAD
    out = np.zeros((raw.shape[0], len(CHANNELS), WIN))
    for t, onset in enumerate(onsets):
        seg = stream[CHANNELS, onset - PAD:onset + WIN]
        seg = lfilter(b_bp, a_bp, lfilter(b_n, a_n, seg, axis=1), axis=1)  # causal, like MATLAB filter()
        out[t] = seg[:, PAD:]
    return out                                                          # (trials, 29, 2000)


def band_filter(x, band):
    sos = butter(2, band, "band", fs=FS, output="sos")  # designfilt bandpassiir FilterOrder 4
    return sosfilt(sos, x, axis=-1)


def csp_fit(x, y, m):
    covs = np.array([c / np.trace(c) for c in (xi @ xi.T for xi in x)])
    c1, c2 = covs[y == 1].mean(0), covs[y == 2].mean(0)
    ev, u = np.linalg.eigh(c1 + c2)
    ev, u = ev[::-1], u[:, ::-1]
    p = np.diag(1 / np.sqrt(ev)) @ u.T                                  # whitening
    ev1, u1 = np.linalg.eigh(p @ c1 @ p.T)
    w = (u1[:, ::-1]).T @ p
    return np.vstack([w[:m], w[-m:]])                                   # first m + last m filters


def csp_features(x, w):
    return np.log(np.var(np.einsum("fc,tcs->tfs", w, x), axis=2, ddof=1))


def fbcsp_fit_transform(xtr, ytr, xte):
    ftr, fte = [], []
    for band in FREQ_BANDS:
        btr, bte = band_filter(xtr, band), band_filter(xte, band)
        w = csp_fit(btr, ytr, CSP_M)                                    # fit on TRAIN only
        ftr.append(csp_features(btr, w))
        fte.append(csp_features(bte, w))
    return np.hstack(ftr), np.hstack(fte)                               # (n, 20)


def run_subject(path, rng):
    raw, y = load_subject(path)
    x = epoch(raw)
    accs = []
    for _ in range(N_REPEATS):
        idx = rng.permutation(len(y))                                   # not stratified, like randperm
        tr, te = idx[:N_TRAIN], idx[N_TRAIN:]
        ftr, fte = fbcsp_fit_transform(x[tr], y[tr], x[te])
        clf = SVC(kernel="linear", C=1.0)                               # fitcecoc default for 2 classes
        clf.fit(ftr, y[tr])
        accs.append((clf.predict(fte) == y[te]).mean() * 100)
    return float(np.mean(accs))


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    files = sorted(glob.glob(os.path.join(ROOT, "sub-*", "*.mat")))
    results = []
    for f in files:
        acc = run_subject(f, rng)
        results.append(acc)
        print(f"{os.path.basename(os.path.dirname(f))}: {acc:5.2f} %")
    print(f"\nMean accuracy over {len(results)} subjects: {np.mean(results):.2f} % "
          f"(paper, FBCSP+SVM: 57.57 %)")
