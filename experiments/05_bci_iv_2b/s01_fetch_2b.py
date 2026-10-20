"""
s01_fetch_2b.py  -  fetch BCI Competition IV dataset 2b and build epochs.

Source : BNCI Horizon 2020, dataset 004-2014 (= BCI Competition IV 2b).
         https://lampx.tugraz.at/~bci/database/004-2014/
         18 files, B01T..B09T (sessions 1-3) and B01E..B09E (sessions 4-5),
         ~34 MB each.  Downloaded once into data\\ and never re-fetched.

Output : data\\checksums.csv          sha256 of every downloaded file
         data\\sub-BXX.npz            per subject:
             X      (ntrials, 3, 750)  float32, 8-30 Hz
             y      (ntrials,)         int8, 0 = left, 1 = right
             sess   (ntrials,)         int8, 1..5
             art    (ntrials,)         int8, the file's own artifact flag
             cov    (nband+1, ntrials, 3, 3)  float64 Ledoit-Wolf covariances
                                       index 0 = main band 8-30 Hz,
                                       index 1.. = the filter bank
         data\\epoch_meta.csv          one row per session, what was kept/dropped

Channels kept are the three bipolar EEG recordings C3, Cz, C4 (columns 0-2).
Columns 3-5 are EOG and are dropped.

The imagery window is 0.5-3.5 s after CUE onset. The cue is 3.0 s after the
`trial` index the file stores -- see CUE_OFFSET and s00_diagnose_window.py.

Run:  C:\\Python313\\python.exe s01_fetch_2b.py
"""

import csv
import hashlib
import os
import sys

import numpy as np
import requests
from scipy.io import loadmat
from scipy.signal import butter, detrend, filtfilt
from sklearn.covariance import ledoit_wolf

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

BASE_URLS = [
    "https://lampx.tugraz.at/~bci/database/004-2014/",
    "https://bnci-horizon-2020.eu/database/data-sets/004-2014/",
]
SUBJECTS = [f"B{i:02d}" for i in range(1, 10)]
SUFFIXES = ["T", "E"]  # T = sessions 1-3, E = sessions 4-5

FS = 250.0
# The `trial` field indexes the TRIAL START, not the cue. The 2b paradigm is
# 0-3 s fixation + beep, CUE at 3 s, motor imagery 3-7 s. Verified empirically by
# s00_diagnose_window.py: a sliding 2 s window finds no laterality at all before
# 2 s and peaks at 3.5-4.0 s after `trial`. Epoching from `trial` directly - the
# first version of this script - lands inside the fixation period and scores
# exactly chance, which is what it did.
CUE_OFFSET = 3.0  # seconds from the `trial` index to cue onset
TMIN, TMAX = 0.5, 3.5  # seconds after CUE onset
NSAMP = int(round((TMAX - TMIN) * FS))  # 750
MAIN_BAND = (8.0, 30.0)
FB_BANDS = [(4, 8), (8, 12), (12, 16), (16, 20), (20, 24), (24, 28), (28, 32)]
ORDER = 4


# --------------------------------------------------------------------------- #
# download
# --------------------------------------------------------------------------- #
def download(name: str) -> str:
    """Fetch <name>.mat into data/ if not already there. Returns the path."""
    path = os.path.join(DATA, name + ".mat")
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return path
    last = None
    for base in BASE_URLS:
        url = base + name + ".mat"
        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                tmp = path + ".part"
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = 100 * done / total
                            print(f"\r  {name}  {pct:5.1f}%", end="", flush=True)
                os.replace(tmp, path)
                print(f"\r  {name}  done ({done/1e6:.1f} MB)      ")
                return path
        except Exception as exc:  # try the mirror
            last = exc
            print(f"\r  {name}  failed on {base} -> {type(exc).__name__}")
    raise RuntimeError(f"could not download {name}: {last}")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# signal
# --------------------------------------------------------------------------- #
def bandpass(x, lo, hi):
    """Zero-phase Butterworth on (nsamples, nchan)."""
    b, a = butter(ORDER, [lo, hi], btype="band", fs=FS)
    return filtfilt(b, a, x, axis=0)


def sessions_in(mat_path):
    """Yield one dict per session held in a 2b .mat file."""
    m = loadmat(mat_path, squeeze_me=True, struct_as_record=False)
    for s in np.atleast_1d(m["data"]):
        X = np.asarray(s.X, dtype=np.float64)
        trial = np.atleast_1d(np.asarray(s.trial)).astype(int)
        y = np.atleast_1d(np.asarray(s.y)).astype(int)
        art = np.atleast_1d(np.asarray(s.artifacts)).astype(int)
        fs = float(np.atleast_1d(s.fs)[0])
        yield dict(X=X, trial=trial, y=y, art=art, fs=fs)


def epoch_session(sess):
    """Return (epochs_mainband, epochs_per_fbband, y, art, stats)."""
    if abs(sess["fs"] - FS) > 1e-6:
        raise RuntimeError(f"unexpected sampling rate {sess['fs']}")

    X = sess["X"][:, :3]  # C3, Cz, C4 -- drop the three EOG channels
    n_nan = int(np.isnan(X).sum())
    X = np.nan_to_num(X, nan=0.0)  # the format uses NaN for the breaks
    X = detrend(X, axis=0, type="constant")

    a0 = int(round((CUE_OFFSET + TMIN) * FS))
    a1 = a0 + NSAMP
    onsets = sess["trial"]
    keep = (onsets + a1) <= X.shape[0]
    n_edge = int((~keep).sum())
    onsets, y, art = onsets[keep], sess["y"][keep], sess["art"][keep]

    def cut(xf):
        return np.stack([xf[o + a0:o + a1, :].T for o in onsets]).astype(np.float32)

    main = cut(bandpass(X, *MAIN_BAND))
    bank = [cut(bandpass(X, lo, hi)) for lo, hi in FB_BANDS]
    stats = dict(n_trials=len(onsets), n_edge=n_edge, n_nan=n_nan)
    return main, bank, y, art, stats


def covariances(epochs):
    """Ledoit-Wolf shrinkage covariance per trial. (ntrials, 3, 3)."""
    out = np.empty((epochs.shape[0], epochs.shape[1], epochs.shape[1]))
    for i, e in enumerate(epochs):
        out[i] = ledoit_wolf(np.asarray(e, dtype=np.float64).T)[0]
    return out


# --------------------------------------------------------------------------- #
def main():
    os.makedirs(DATA, exist_ok=True)
    print("=== s01_fetch_2b ===")
    print(f"window {TMIN}-{TMAX} s after CUE, cue at +{CUE_OFFSET:g} s from "
          f"`trial` ({NSAMP} samples at {FS:g} Hz)")
    print(f"main band {MAIN_BAND[0]:g}-{MAIN_BAND[1]:g} Hz, "
          f"{len(FB_BANDS)} filter-bank bands\n")

    print("--- download ---")
    paths, checks = {}, []
    for sub in SUBJECTS:
        for suf in SUFFIXES:
            name = sub + suf
            p = download(name)
            paths[name] = p
            checks.append((name, os.path.getsize(p), sha256(p)))
    with open(os.path.join(DATA, "checksums.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "bytes", "sha256"])
        w.writerows(checks)

    print("\n--- epoch ---")
    meta = []
    for sub in SUBJECTS:
        Xs, ys, ss, arts, covs = [], [], [], [], []
        sess_id = 0
        for suf in SUFFIXES:
            for sess in sessions_in(paths[sub + suf]):
                sess_id += 1
                main_ep, bank_ep, y, art, st = epoch_session(sess)
                if len(np.unique(y)) < 2:
                    print(f"  {sub} session {sess_id}: labels unusable, skipped")
                    meta.append([sub, sess_id, 0, st["n_edge"], st["n_nan"], "NO_LABELS"])
                    continue
                stack = [covariances(main_ep)] + [covariances(b) for b in bank_ep]
                Xs.append(main_ep)
                ys.append(y)
                arts.append(art)
                ss.append(np.full(len(y), sess_id, dtype=np.int8))
                covs.append(np.stack(stack))  # (nband+1, ntrials, 3, 3)
                meta.append([sub, sess_id, st["n_trials"], st["n_edge"],
                             st["n_nan"], "OK"])
                print(f"  {sub} session {sess_id}: {st['n_trials']:4d} trials "
                      f"(left {int((y == 1).sum())}, right {int((y == 2).sum())}, "
                      f"artefact-flagged {int((art == 1).sum())}, "
                      f"dropped at edge {st['n_edge']})")

        if not Xs:
            print(f"  {sub}: NOTHING USABLE")
            continue
        X = np.concatenate(Xs)
        y = np.concatenate(ys)
        y = (y == 2).astype(np.int8)          # 0 = left, 1 = right
        sarr = np.concatenate(ss)
        aarr = np.concatenate(arts).astype(np.int8)
        cov = np.concatenate(covs, axis=1)    # (nband+1, ntrials, 3, 3)
        np.savez_compressed(os.path.join(DATA, f"sub-{sub}.npz"),
                            X=X, y=y, sess=sarr, art=aarr, cov=cov,
                            bands=np.array([MAIN_BAND] + FB_BANDS, dtype=float))
        print(f"  {sub} TOTAL {len(y)} trials, {len(np.unique(sarr))} sessions, "
              f"balance {np.bincount(y)}\n")

    with open(os.path.join(DATA, "epoch_meta.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["subject", "session", "trials_kept", "dropped_at_edge",
                    "nan_samples_zeroed", "status"])
        w.writerows(meta)

    print("Wrote data\\sub-BXX.npz, checksums.csv, epoch_meta.csv")


if __name__ == "__main__":
    sys.exit(main())
