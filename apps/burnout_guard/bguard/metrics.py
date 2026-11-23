"""Pure maths: relative band powers, formula indices, sanitising, smoothing.

The index formulas are the ones Neiry publishes in
`Capsule metrics_definitions.xlsx` / `Metrics API 2024.xlsx`, computed here
from the SDK's artifact-cleaned PSD so every number is reproducible.
"""
import math
from collections import deque

import numpy as np

from . import config

NAN = float("nan")

# Index name -> (label, formula text) — order is the display/CSV order.
INDEX_DEFINITIONS = {
    "concentration":     ("Concentration", "beta / alpha"),
    "relaxation":        ("Relaxation", "alpha / beta"),
    "fatigue":           ("Fatigue", "(alpha + theta) / beta"),
    "reverse_fatigue":   ("Engagement", "beta / (alpha + theta)"),
    "cognitive_load":    ("Cognitive load", "theta / alpha"),
    "cognitive_control": ("Cognitive control", "beta / theta"),
    "alpha_gravity":     ("Alpha gravity", "alpha2 / alpha1 (split at iAPF)"),
    "arousal":           ("Arousal", "high beta (20-30 Hz) / alpha"),
}


def is_valid(x):
    return x is not None and isinstance(x, (int, float, np.floating)) and math.isfinite(x)


def safe_ratio(num, den, max_valid=config.MAX_VALID_RATIO):
    """num/den, or NaN when either side is unusable or the result is absurd."""
    if not (is_valid(num) and is_valid(den)) or den <= 0 or num < 0:
        return NAN
    value = num / den
    return value if value <= max_valid else NAN


def sanitize(value, max_abs=config.MAX_VALID_VENDOR_SCORE):
    """Vendor scores: non-finite or absurd (SinWave gives ~1e6) → NaN."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return NAN
    if not math.isfinite(value) or abs(value) > max_abs:
        return NAN
    return value


def clip01_100(value):
    value = sanitize(value)
    return NAN if math.isnan(value) else min(100.0, max(0.0, value))


def band_power(freqs, spectrum, lo, hi):
    """Sum of PSD bins with lo <= f < hi. `spectrum` may be 1-D or (channels, freqs)."""
    freqs = np.asarray(freqs, dtype=float)
    spectrum = np.asarray(spectrum, dtype=float)
    mask = (freqs >= lo) & (freqs < hi)
    if not mask.any():
        return np.full(spectrum.shape[:-1], NAN) if spectrum.ndim > 1 else NAN
    return spectrum[..., mask].sum(axis=-1)


def relative_band_powers(freqs, spectrum, bands=None, total_range=None):
    """Relative power per band, averaged over channels.

    Each channel is normalised to its own total power in `total_range` first,
    so a channel with a louder amplifier does not dominate the average.
    Channels with no usable power are ignored. Returns {band: float or NaN}.
    """
    bands = bands or config.BANDS
    lo, hi = total_range or config.TOTAL_RANGE
    spectrum = np.atleast_2d(np.asarray(spectrum, dtype=float))
    spectrum = np.where(np.isfinite(spectrum) & (spectrum >= 0), spectrum, np.nan)

    total = band_power(freqs, np.nan_to_num(spectrum, nan=0.0), lo, hi)
    usable = np.isfinite(total) & (total > 0) & ~np.isnan(spectrum).all(axis=-1)
    if not usable.any():
        return {name: NAN for name in bands}

    out = {}
    clean = np.nan_to_num(spectrum[usable], nan=0.0)
    for name, (b_lo, b_hi) in bands.items():
        out[name] = float(np.mean(band_power(freqs, clean, b_lo, b_hi) / total[usable]))
    return out


def alpha_split(freqs, spectrum, iapf, alpha_range=None):
    """(alpha1, alpha2) absolute power below/above the individual alpha peak."""
    a_lo, a_hi = alpha_range or config.BANDS["alpha"]
    if not is_valid(iapf) or not (a_lo < iapf < a_hi):
        return NAN, NAN
    spectrum = np.nan_to_num(np.atleast_2d(np.asarray(spectrum, dtype=float)), nan=0.0)
    a1 = float(np.mean(band_power(freqs, spectrum, a_lo, iapf)))
    a2 = float(np.mean(band_power(freqs, spectrum, iapf, a_hi)))
    return a1, a2


def formula_indices(rel, alpha1=NAN, alpha2=NAN):
    """Vendor-published formulas applied to relative band powers, plus the arousal ratio."""
    theta, alpha, beta = rel.get("theta", NAN), rel.get("alpha", NAN), rel.get("beta", NAN)
    alpha_theta = alpha + theta if is_valid(alpha) and is_valid(theta) else NAN
    return {
        "concentration":     safe_ratio(beta, alpha),
        "relaxation":        safe_ratio(alpha, beta),
        "fatigue":           safe_ratio(alpha_theta, beta),
        "reverse_fatigue":   safe_ratio(beta, alpha_theta),
        "cognitive_load":    safe_ratio(theta, alpha),
        "cognitive_control": safe_ratio(beta, theta),
        "alpha_gravity":     safe_ratio(alpha2, alpha1),
        "arousal":           safe_ratio(rel.get("high_beta", NAN), alpha),
    }


def compute_indices(freqs, spectrum, iapf=None):
    """Full pipeline: spectrum → (relative powers incl. high beta, indices)."""
    rel = relative_band_powers(freqs, spectrum, bands={**config.BANDS, "high_beta": config.HIGH_BETA})
    a1, a2 = alpha_split(freqs, spectrum, iapf) if iapf is not None else (NAN, NAN)
    return rel, formula_indices(rel, a1, a2)


def percent_of_baseline(value, baseline):
    """+25.0 means 25 % above baseline. NaN if either is unusable."""
    if not (is_valid(value) and is_valid(baseline)) or baseline <= 0:
        return NAN
    return (value / baseline - 1.0) * 100.0


def score_vs_baseline(value, baseline):
    """Map a ratio to 0-100 where 50 = baseline, ×2 ≈ 88, ×0.5 ≈ 12 (symmetric in log space)."""
    if not (is_valid(value) and is_valid(baseline)) or value <= 0 or baseline <= 0:
        return NAN
    return 50.0 + 50.0 * math.tanh(math.log(value / baseline) / math.log(2.0))


def level(score, low=config.LEVEL_LOW, high=config.LEVEL_HIGH):
    if not is_valid(score):
        return ""
    return "Low" if score < low else "High" if score >= high else "Moderate"


class BaselineCollector:
    """Median of each named value over the baseline period (NaNs ignored)."""

    def __init__(self, min_samples=config.OWN_BASELINE_MIN_SAMPLES):
        self.min_samples = min_samples
        self._values = {}
        self.frozen = None

    def add(self, values):
        if self.frozen is not None:
            return
        for k, v in values.items():
            if is_valid(v) and v > 0:
                self._values.setdefault(k, []).append(float(v))

    def count(self, key):
        return len(self._values.get(key, []))

    @property
    def enough(self):
        """At least one value has enough samples (keys that never do are left out at freeze,
        so one rarely-valid ratio cannot stall the baseline)."""
        return any(len(v) >= self.min_samples for v in self._values.values())

    def freeze(self):
        """Fix the baseline (keys with too few samples are left out)."""
        self.frozen = {k: float(np.median(v)) for k, v in self._values.items() if len(v) >= self.min_samples}
        return self.frozen

    def get(self, key):
        return (self.frozen or {}).get(key, NAN)


class RollingMedian:
    """Median of the values seen in the last `window_s` seconds (NaNs ignored)."""

    def __init__(self, window_s=config.SCORE_SMOOTHING_S):
        self.window_s = window_s
        self._items = deque()

    def add(self, t, value):
        self._items.append((t, value))
        self._trim(t)

    def _trim(self, now):
        while self._items and now - self._items[0][0] > self.window_s:
            self._items.popleft()

    def value(self, now=None):
        if now is not None:
            self._trim(now)
        vals = [v for _, v in self._items if is_valid(v)]
        return float(np.median(vals)) if vals else NAN


class RunningStats:
    """Mean / max / count without keeping every sample (for the summary)."""

    def __init__(self):
        self.n = 0
        self.total = 0.0
        self.max = NAN
        self.last = NAN

    def add(self, value):
        if not is_valid(value):
            return
        self.n += 1
        self.total += value
        self.max = value if math.isnan(self.max) else max(self.max, value)
        self.last = value

    @property
    def mean(self):
        return self.total / self.n if self.n else NAN
