"""Causal (real-time) signal processing. The same class is used live and offline, so the
numbers the trainer sees are exactly the numbers the live decoder sees.

BandPower: for every (channel, band) pair -> Butterworth band-pass with kept filter state,
square, mean over the last 1 s, natural log. One feature row every HOP samples.
ArtifactCheck: 1 s peak-to-peak of the raw decode channels against a running median.
"""
import numpy as np
from scipy.signal import butter, sosfilt

from . import config as C


def apply_montage(x, montage=None):
    """Raw columns A1, C3, C4, A2 -> same columns with C3 := C3 - A1 and C4 := C4 - A2 ('ear_bipolar').
    Used identically live and offline; the recorder keeps the raw channels."""
    montage = montage or C.MONTAGE
    x = np.asarray(x, float)
    if montage == "raw" or len(x) == 0:
        return x
    if montage != "ear_bipolar":
        raise ValueError(f"unknown montage {montage}")
    y = x.copy()
    y[:, 1] = x[:, 1] - x[:, 0]
    y[:, 2] = x[:, 2] - x[:, 3]
    return y


class BandPower:
    def __init__(self, channels, bands, fs=C.FS, win_s=C.FEATURE_WIN_S, hop=C.HOP, order=C.FILTER_ORDER):
        """channels: column indices into the incoming sample matrix. bands: list of (lo, hi) Hz.
        Feature order: for band in bands: for channel in channels."""
        self.channels = list(channels)
        self.bands = [tuple(b) for b in bands]
        self.fs, self.hop = fs, hop
        self.win = int(round(win_s * fs))
        self.sos = [butter(order, b, btype="bandpass", fs=fs, output="sos") for b in self.bands]
        nch = len(self.channels)
        self.zi = [np.zeros((s.shape[0], 2, nch)) for s in self.sos]
        self.n_feat = len(self.bands) * nch
        self.tail = np.zeros((0, self.n_feat))      # last win-1 squared samples
        self.n_seen = 0                              # samples processed so far (= next sample index)

    def names(self, channel_names):
        return [f"{channel_names[c]}_{lo}-{hi}Hz" for (lo, hi) in self.bands for c in self.channels]

    def process(self, x):
        """x: (n, n_all_channels) new samples, in order, no gaps.
        Returns (idx, feats): idx = sample index of the last sample in each 1 s window."""
        x = np.asarray(x, dtype=float)
        if x.ndim == 1:
            x = x[None, :]
        n = x.shape[0]
        if n == 0:
            return np.zeros(0, int), np.zeros((0, self.n_feat))
        xs = np.nan_to_num(x[:, self.channels])
        if self.n_seen == 0:                         # remove the starting DC level (no filter step)
            self._offset = xs[0].copy()
        xs = xs - self._offset
        sq = np.empty((n, self.n_feat))
        k = len(self.channels)
        for b, sos in enumerate(self.sos):
            y, self.zi[b] = sosfilt(sos, xs, axis=0, zi=self.zi[b])
            sq[:, b * k:(b + 1) * k] = y * y
        z = np.vstack([self.tail, sq])
        cs = np.vstack([np.zeros((1, self.n_feat)), np.cumsum(z, axis=0)])
        t0 = self.tail.shape[0]
        first = self.n_seen                          # sample index of sq[0]
        j = np.arange(n)
        sample_idx = first + j
        pos = t0 + j                                 # position of sample j inside z
        keep = ((sample_idx + 1) % self.hop == 0) & (sample_idx + 1 >= self.win)
        jj, pp = j[keep], pos[keep]
        if len(jj):
            sums = cs[pp + 1] - cs[pp + 1 - self.win]
            feats = np.log(np.maximum(sums / self.win, 1e-12))
        else:
            feats = np.zeros((0, self.n_feat))
        self.tail = z[-(self.win - 1):] if self.win > 1 else z[:0]
        self.n_seen += n
        return sample_idx[keep], feats


def bandpower_offline(x, channels, bands, chunk=25, **kw):
    """Run the live BandPower over a whole recording in chunks (identical code path)."""
    bp = BandPower(channels, bands, **kw)
    idx_all, f_all = [], []
    for s in range(0, len(x), chunk):
        i, f = bp.process(x[s:s + chunk])
        idx_all.append(i)
        f_all.append(f)
    return np.concatenate(idx_all), np.vstack(f_all)


class ArtifactCheck:
    """Flags a decoder output when the last 1 s of raw C3/C4 has an unusually large peak-to-peak."""

    def __init__(self, channels, fs=C.FS, win_s=C.FEATURE_WIN_S, factor=C.ARTIFACT_PTP_FACTOR,
                 warmup=C.ARTIFACT_WARMUP, abs_uv=C.ARTIFACT_ABS_UV, hp_hz=C.ARTIFACT_HIGHPASS_HZ):
        self.channels = list(channels)
        self.win = int(round(win_s * fs))
        self.buf = np.zeros((0, len(self.channels)))
        self.factor, self.warmup, self.abs_uv = factor, warmup, abs_uv
        self.history = []                            # ptp of clean windows (for the median)
        self.sos = butter(2, hp_hz, btype="highpass", fs=fs, output="sos")   # causal, state kept
        self.zi = np.zeros((self.sos.shape[0], 2, len(self.channels)))
        self.n = 0

    def push(self, x):
        x = np.nan_to_num(np.asarray(x, float)[:, self.channels])
        if len(x) == 0:
            return
        if self.n == 0:                                # start the filter at the first value (no step)
            self.zi = self.zi * 0 + 0
            self._offset = x[0].copy()
        x = x - self._offset
        y, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
        self.n += len(x)
        self.buf = np.vstack([self.buf, y])[-self.win:]

    def check(self):
        """True = artifact. Call once per decoder output, after push()."""
        if self.buf.shape[0] < self.win or self.n < 3 * self.win:   # let the high-pass settle (3 s)
            return False
        ptp = float(np.max(np.ptp(self.buf, axis=0)))
        bad = ptp > self.abs_uv
        if len(self.history) >= self.warmup:
            med = float(np.median(self.history[-500:]))
            bad = bad or ptp > self.factor * med
        if not bad:
            self.history.append(ptp)
        return bool(bad)
