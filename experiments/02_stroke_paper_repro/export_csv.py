"""
Export the acute-stroke MI dataset (Liu et al., Sci Data 2024) to per-subject CSV files.

Output: eeg_stroke/csv/
  participants.csv                    clinical table (copy of participants.tsv)
  channels.csv                        channel index -> name / type, as stored in the files
  sub-XX/sub-XX_raw.csv               sourcedata .mat  (raw, unfiltered, large DC offsets)
  sub-XX/sub-XX_preprocessed.csv      edffile .edf     (mean removed, 0.5-40 Hz filtered)
  sub-XX/sub-XX_events.csv            one row per trial: label + marker positions

Data quirks found while exporting (kept as-is, flagged instead of "fixed"):
  - CPz_ref is a constant 187500 in the raw .mat (0 in the EDF).
  - 18 trials in 11 subjects are "window_shifted": the MI marker is at sample 1, i.e. the 8 s
    window starts at the MI cue, and its last ~1 s duplicates the start of the next trial.
  - 10 subjects have non-integer marker values after the break marker (mostly trial 40's tail);
    the EDF rounds them, so edf_markers_match is False there. Outside the 0-4 s MI window.

Both signal files have one row per sample (40 trials x 4000 samples = 160000 rows) and the
same leading columns, so they line up row for row:
  trial (1-40), label (1=left, 2=right), hand, sample (0-3999 within trial),
  time_s (seconds since the trial's MI onset, i.e. marker 2), then the 33 channels.
"""
import os

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.io import loadmat

BASE = r"D:\trainsvm\data\stroke_liu2024"
SRC = os.path.join(BASE, "sourcedata", "sourcedata")
EDF = os.path.join(BASE, "edffile", "edffile")
OUT = os.path.join(BASE, "csv")
FS, N_TRIALS, N_SAMP = 500, 40, 4000

# Order as stored in the .mat / .edf (EDF header labels). Channel 18 (CPz) is the reference
# (constant: 187500 in raw, 0 in EDF). Channel 32 is labelled HEOR in the EDF and .locs, VEOR in the paper/channels.tsv.
CHANNELS = ["Fp1", "Fp2", "Fz", "F3", "F4", "F7", "F8", "FCz", "FC3", "FC4", "FT7", "FT8",
            "Cz", "C3", "C4", "T3", "T4", "CPz_ref", "CP3", "CP4", "TP7", "TP8", "Pz", "P3",
            "P4", "T5", "T6", "Oz", "O1", "O2", "EOG_HEOL", "EOG_VEOR", "marker"]
TYPES = ["EEG"] * 17 + ["REF"] + ["EEG"] * 12 + ["EOG", "EOG", "MARKER"]


def read_edf(path):
    """Minimal EDF reader: returns (n_signals, n_samples) in physical units."""
    with open(path, "rb") as f:
        h = f.read(256)
        n_rec, ns = int(h[236:244]), int(h[252:256])
        sh = f.read(256 * ns)
        fields, off = {}, 0
        for name, w in [("label", 16), ("trans", 80), ("dim", 8), ("pmin", 8), ("pmax", 8),
                        ("dmin", 8), ("dmax", 8), ("prefilt", 80), ("nsamp", 8), ("res", 32)]:
            fields[name] = [sh[off + i * w: off + (i + 1) * w].decode("latin1").strip()
                            for i in range(ns)]
            off += w * ns
        spr = int(fields["nsamp"][0])
        data = np.frombuffer(f.read(), "<i2").reshape(n_rec, ns, spr)
    data = data.transpose(1, 0, 2).reshape(ns, -1).astype(np.float64)
    pmin, pmax, dmin, dmax = (np.array(fields[k], float)[:, None]
                              for k in ("pmin", "pmax", "dmin", "dmax"))
    return (data - dmin) * (pmax - pmin) / (dmax - dmin) + pmin


def export_subject(sub):
    mat = loadmat(os.path.join(SRC, sub, f"{sub}_task-motor-imagery_eeg.mat"))["eeg"][0, 0]
    raw, labels = mat["rawdata"], mat["label"].ravel().astype(int)      # (40,33,4000), (40,)
    edf = read_edf(os.path.join(EDF, sub, "eeg", f"{sub}_task-motor-imagery_eeg.edf"))
    edf = edf.reshape(33, N_TRIALS, N_SAMP).transpose(1, 0, 2)          # -> (40,33,4000)
    edf[:, 32] = np.round(edf[:, 32])                                   # marker back to ints

    # events: marker positions per trial (sample index within the 8 s trial window)
    events, onsets = [], []
    for t in range(N_TRIALS):
        m = raw[t, 32]
        pos = {v: np.flatnonzero(m == v).tolist() for v in (1, 2, 3)}
        onset = pos[2][0]
        onsets.append(onset)
        events.append({
            "trial": t + 1, "label": labels[t], "hand": "left" if labels[t] == 1 else "right",
            "instruction_samples": ";".join(map(str, pos[1])),
            "mi_onset_sample": onset, "break_sample": ";".join(map(str, pos[3])),
            "mi_onset_s": onset / FS,
            "window_shifted": onset < 10,   # trial window starts at the MI cue, not the instruction
            "odd_marker_samples": int((~np.isin(m, [0, 1, 2, 3])).sum()),
            "edf_markers_match": bool(np.array_equal(edf[t, 32], m)),
        })

    lead = pd.DataFrame({
        "trial": np.repeat(np.arange(1, N_TRIALS + 1), N_SAMP),
        "label": np.repeat(labels, N_SAMP),
        "hand": np.repeat(np.where(labels == 1, "left", "right"), N_SAMP),
        "sample": np.tile(np.arange(N_SAMP), N_TRIALS),
        "time_s": np.concatenate([(np.arange(N_SAMP) - o) / FS for o in onsets]),
    })

    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    for kind, arr in (("raw", raw), ("preprocessed", edf)):
        sig = pd.DataFrame(arr.transpose(0, 2, 1).reshape(-1, 33), columns=CHANNELS)
        if kind == "preprocessed":
            sig["marker"] = sig["marker"].astype(int)
        # raw: kept as stored; a few trials carry non-integer marker values after the break
        # marker (see events.csv, odd_marker_samples), casting them would create fake events
        pd.concat([lead, sig], axis=1).to_csv(
            os.path.join(OUT, sub, f"{sub}_{kind}.csv"), index=False, float_format="%.4f")
    pd.DataFrame(events).to_csv(os.path.join(OUT, sub, f"{sub}_events.csv"), index=False)
    return sub, sum(e["window_shifted"] for e in events), all(e["edf_markers_match"] for e in events)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    pd.read_csv(os.path.join(BASE, "participants.tsv"), sep="\t").to_csv(
        os.path.join(OUT, "participants.csv"), index=False)
    pd.DataFrame({"index": range(1, 34), "name": CHANNELS, "type": TYPES}).to_csv(
        os.path.join(OUT, "channels.csv"), index=False)
    subs = sorted(d for d in os.listdir(SRC) if d.startswith("sub-"))
    for sub, shifted, ok in Parallel(n_jobs=8)(delayed(export_subject)(s) for s in subs):
        print(f"{sub}: shifted trials={shifted}  edf markers match raw={ok}", flush=True)
