"""Signal steps mi_live adds in front of mi_bci's filters, and the signal check.

Notch: causal 50 Hz IIR notch (Q = 30), filter state kept between calls, so it gives the same numbers
however the samples are split. BCI IV 2b was recorded with a 50 Hz notch, so this makes our input match the
training data. Found on 2026-10-26: 50 Hz hum of 54-69 uV at C3 (EEG 6-8 uV); about 9 uV of it passed the
8-30 Hz band-pass and steered the decoder.
Missing samples (NaN, from dropped Bluetooth packets) are held at the last good value instead of 0, which
would have made a big step.
"""
import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, tf2sos, welch

from mibci import config as C

FS = C.FS


class Notch:
    def __init__(self, cols, f0=50.0, q=30.0, fs=FS):
        b, a = iirnotch(f0, q, fs=fs)
        self.sos = tf2sos(b, a)
        self.cols = list(cols)
        self.zi = np.zeros((self.sos.shape[0], 2, len(self.cols)))
        self.offset = None
        self.last = None

    def process(self, x):
        """x: (n, n_channels). Returns a copy with the chosen columns notch-filtered (offset removed)."""
        x = np.array(x, float, copy=True)
        if len(x) == 0:
            return x
        xs = x[:, self.cols]
        bad = np.isnan(xs)
        if bad.any():                                   # hold the last good value
            for j in range(xs.shape[1]):
                col = xs[:, j]
                prev = self.last[j] if self.last is not None else np.nan
                for i in np.flatnonzero(np.isnan(col)):
                    col[i] = prev if i == 0 else col[i - 1]
                if np.isnan(col).all():
                    col[:] = 0.0
                elif np.isnan(col).any():               # leading NaN before any good value
                    col[np.isnan(col)] = col[~np.isnan(col)][0]
        if self.offset is None:
            self.offset = xs[0].copy()
        self.last = xs[-1].copy()
        y, self.zi = sosfilt(self.sos, xs - self.offset, axis=0, zi=self.zi)
        x[:, self.cols] = y
        return x


def signal_check(m, fs=FS):
    """m: (n, 2) montaged C3, C4 (uV), ~10-15 s. Returns numbers + verdict + advice."""
    m = np.nan_to_num(np.asarray(m, float))
    m = sosfilt(butter(2, 1.0, btype="highpass", fs=fs, output="sos"), m - m[0], axis=0)[fs:]   # drop 1 s
    f, P = welch(m, fs=fs, nperseg=2 * fs, axis=0)
    band = lambda lo, hi: P[(f >= lo) & (f < hi)].sum(0) * (f[1] - f[0])   # noqa: E731  power in band
    rms = np.sqrt(band(8, 30))
    hum = np.sqrt(band(49, 51))
    low = np.sqrt(band(1, 4))
    alpha_peak = float(f[(f >= 7) & (f <= 14)][np.argmax(P[(f >= 7) & (f <= 14)].mean(1))])
    ptp = np.ptp(m, axis=0)
    res = dict(rms_8_30=rms.round(1).tolist(), hum_50=hum.round(1).tolist(), slow_1_4=low.round(1).tolist(),
               ptp=ptp.round(0).tolist(), alpha_peak_hz=alpha_peak)
    advice, level = [], 0                                      # 0 good, 1 fair, 2 bad
    for k, ch in enumerate(("C3", "C4")):
        if hum[k] > 25:
            level = 2
            advice.append(f"{ch}: 50 Hz hum {hum[k]:.0f} uV (very high). Unplug the charger; press the {ch} pad "
                          f"and the {'left' if k == 0 else 'right'} ear clip firmly onto skin; move away from cables.")
        elif hum[k] > 10:
            level = max(level, 1)
            advice.append(f"{ch}: 50 Hz hum {hum[k]:.0f} uV (high). Improve contact / unplug charger.")
        if rms[k] < 2:
            level = 2
            advice.append(f"{ch}: almost no EEG ({rms[k]:.1f} uV) - pad not touching the scalp?")
        elif rms[k] > 50:
            level = 2
            advice.append(f"{ch}: very large signal ({rms[k]:.0f} uV) - loose contact or muscle tension.")
        if ptp[k] > 1500:
            level = max(level, 1)
            advice.append(f"{ch}: big jumps (peak-to-peak {ptp[k]:.0f} uV) - keep still, relax jaw.")
    res["level"] = level
    res["verdict"] = ["GOOD", "FAIR", "BAD"][level]
    res["advice"] = advice or ["Signal looks fine."]
    return res
