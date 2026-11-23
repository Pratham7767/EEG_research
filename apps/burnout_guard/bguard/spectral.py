"""Band powers from RAW EEG (delta … gamma).

The SDK's own spectrum is computed on a signal band-passed to ~4-30 Hz, so it
cannot show delta or gamma. Here we filter the raw stream ourselves
(0.5 Hz high-pass + mains notch), take a Welch spectrum of the last 4 s every
0.5 s, and reject windows that the SDK flags as artifacts or whose
peak-to-peak amplitude is far above the running median (movement, jaw).

Relative power = band power / power in 1-45 Hz, averaged over channels.
Absolute power is in V² (the SDK delivers volts).
"""
from collections import deque

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, sosfilt_zi, tf2sos, welch

from . import config


def design_filter(fs, highpass_hz=config.HIGHPASS_HZ, mains_hz=config.MAINS_HZ):
    sos = butter(2, highpass_hz, btype="highpass", fs=fs, output="sos")
    if mains_hz and mains_hz < fs / 2:
        b, a = iirnotch(mains_hz, Q=30.0, fs=fs)
        sos = np.vstack([sos, tf2sos(b, a)])
    return sos


class StreamFilter:
    """Causal IIR filter that keeps its state between blocks (one state per channel)."""

    def __init__(self, fs, n_channels, **kw):
        self.sos = design_filter(fs, **kw)
        self._zi = None
        self.n_channels = n_channels

    def process(self, block):
        block = np.nan_to_num(np.asarray(block, dtype=float), nan=0.0)
        if self._zi is None:
            # start from the first sample's level to avoid a large step transient
            zi = sosfilt_zi(self.sos)                                   # (sections, 2)
            self._zi = zi[:, :, np.newaxis] * block[0][np.newaxis, np.newaxis, :]   # (sections, 2, channels)
        out, self._zi = sosfilt(self.sos, block, axis=0, zi=self._zi)
        return out


class RawBandAnalyzer:
    def __init__(self, fs, n_channels, bands=None, total=None, window_s=config.RAW_WINDOW_S,
                 segment_s=config.WELCH_SEGMENT_S, interval_s=config.RAW_PROCESS_INTERVAL_S,
                 ptp_factor=config.ARTIFACT_PTP_FACTOR, ptp_warmup=config.ARTIFACT_PTP_WARMUP, **filter_kw):
        self.fs = float(fs)
        self.bands = bands or config.RAW_BANDS
        self.total = total or config.RAW_TOTAL
        self.n_window = int(round(window_s * self.fs))
        self.n_segment = int(round(segment_s * self.fs))
        self.n_interval = max(1, int(round(interval_s * self.fs)))
        self.ptp_factor, self.ptp_warmup = ptp_factor, ptp_warmup
        self.filter = StreamFilter(self.fs, n_channels, **filter_kw)
        self._buf = deque(maxlen=self.n_window)
        self._samples = 0
        self._next_compute = self.n_window + int(self.fs)     # let the high-pass settle for 1 s
        self._last_artifact_sample = -10**9
        self._ptp_history = deque(maxlen=120)
        self.accepted = 0
        self.rejected = 0

    def push(self, raw_block):
        filtered = self.filter.process(raw_block)
        self._buf.extend(filtered)
        self._samples += len(filtered)

    def mark_artifact(self):
        """SDK reported an artifact now; the window containing this sample is rejected."""
        self._last_artifact_sample = self._samples

    def ready(self):
        return len(self._buf) == self.n_window and self._samples >= self._next_compute

    def compute(self):
        """Returns {"rel": {band: frac}, "abs": {band: V²}, "ptp": V, "rejected": None | reason}."""
        self._next_compute = self._samples + self.n_interval
        x = np.array(self._buf)                                  # (n_window, channels)
        ptp = float(np.max(np.ptp(x, axis=0)))
        self._ptp_history.append(ptp)
        reason = None
        if self._last_artifact_sample > self._samples - self.n_window:
            reason = "sdk_artifact"
        elif len(self._ptp_history) > self.ptp_warmup and ptp > self.ptp_factor * np.median(self._ptp_history):
            reason = "amplitude"
        if reason:
            self.rejected += 1
            return {"rel": None, "abs": None, "ptp": ptp, "rejected": reason}

        f, pxx = welch(x, fs=self.fs, nperseg=min(self.n_segment, len(x)), axis=0, detrend="linear")
        df = f[1] - f[0]
        lo, hi = self.total
        total = pxx[(f >= lo) & (f < hi)].sum(axis=0) * df          # per channel
        usable = np.isfinite(total) & (total > 0)
        if not usable.any():
            self.rejected += 1
            return {"rel": None, "abs": None, "ptp": ptp, "rejected": "flat"}
        rel, absolute = {}, {}
        for name, (b_lo, b_hi) in self.bands.items():
            p = pxx[(f >= b_lo) & (f < b_hi)].sum(axis=0) * df
            absolute[name] = float(np.mean(p[usable]))
            rel[name] = float(np.mean(p[usable] / total[usable]))
        self.accepted += 1
        return {"rel": rel, "abs": absolute, "ptp": ptp, "rejected": None}

    @property
    def rejected_fraction(self):
        n = self.accepted + self.rejected
        return self.rejected / n if n else 0.0
