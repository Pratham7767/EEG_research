"""Signal-quality check on a real headphone recording (ours, or a SpeechEEG_Recorder *_eeg.csv).

Reports per channel: DC level, how often the amplifier is pinned at its limit, noise level after a
1-45 Hz band-pass, and what fraction of decoder outputs our artifact check would throw away.
Usage: python tools/check_real_signal.py <eeg.csv or run folder> [--volts]
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mibci import config as C                                   # noqa: E402
from mibci.dsp import apply_montage, bandpower_offline          # noqa: E402
from mibci.trainer import artifact_flags                        # noqa: E402


def load(path, volts):
    p = Path(path)
    f = p / "eeg.csv" if p.is_dir() else p
    x = np.loadtxt(f, delimiter=",", skiprows=1)[:, 1:5]
    return x * 1e6 if volts else x


def main(path, volts=False):
    x = load(path, volts)
    rails = np.isclose(np.abs(x), np.abs(x).max(0), rtol=1e-6)
    sos = butter(4, (1, 45), btype="bandpass", fs=C.FS, output="sos")
    m = apply_montage(x)
    rep = dict(file=str(path), seconds=round(len(x) / C.FS, 1), montage=C.MONTAGE, channels={})
    for k, ch in enumerate(C.CHANNELS):
        y = sosfiltfilt(sos, np.nan_to_num(m[:, k]))
        f, pxx = welch(y, fs=C.FS, nperseg=2 * C.FS)
        a = (f >= 8) & (f <= 13)
        rep["channels"][ch if ch in ("A1", "A2") else f"{ch}-{'A1' if ch == 'C3' else 'A2'}"] = dict(
            raw_median_uV=round(float(np.median(x[:, k])), 1),
            pinned_at_limit_fraction=round(float(rails[:, k].mean()), 3),
            band_1_45Hz_std_uV=round(float(np.std(y)), 1),
            alpha_8_13Hz_share=round(float(pxx[a].sum() / pxx[(f >= 1) & (f <= 45)].sum()), 3))
    i, _ = bandpower_offline(m, [1, 2], [(8, 13)])
    rep["artifact_output_fraction"] = round(float(artifact_flags(m, i).mean()), 3)
    print(json.dumps(rep, indent=2))
    return rep


if __name__ == "__main__":
    main(sys.argv[1], "--volts" in sys.argv)
