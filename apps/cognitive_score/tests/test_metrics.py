import math

import numpy as np
import pytest

from cogscore import metrics
from cogscore.metrics import (BaselineCollector, RollingMedian, RunningStats, alpha_split, band_power, compute_indices,
                              formula_indices, level, percent_of_baseline, relative_band_powers, safe_ratio, sanitize,
                              score_vs_baseline)

FREQS = np.round(np.arange(1.0, 30.01, 0.1), 2)


def flat_spectrum_with(bands):
    """Spectrum with a constant density inside each given band, zero elsewhere."""
    s = np.zeros_like(FREQS)
    for (lo, hi), density in bands.items():
        s[(FREQS >= lo) & (FREQS < hi)] = density
    return s


def test_band_power_sums_bins_in_half_open_range():
    s = np.ones_like(FREQS)
    assert band_power(FREQS, s, 7.0, 13.0) == pytest.approx(60)      # 7.0 … 12.9
    assert band_power(FREQS, np.vstack([s, 2 * s]), 7.0, 13.0).tolist() == pytest.approx([60, 120])


def test_relative_powers_sum_to_one_and_known_ratios():
    s = flat_spectrum_with({(4, 7): 1.0, (7, 13): 2.0, (15, 30): 1.0})
    rel = relative_band_powers(FREQS, s)
    total = 30 * 1 + 60 * 2 + 150 * 1
    assert rel["theta"] == pytest.approx(30 / total)
    assert rel["alpha"] == pytest.approx(120 / total)
    assert rel["beta"] == pytest.approx(150 / total)
    assert rel["smr"] == pytest.approx(0)
    assert sum(rel.values()) == pytest.approx(1.0)


def test_channels_normalised_individually_before_averaging():
    quiet = flat_spectrum_with({(7, 13): 1.0, (15, 30): 1.0})
    loud = 1000 * flat_spectrum_with({(7, 13): 1.0, (15, 30): 1.0})
    rel = relative_band_powers(FREQS, np.vstack([quiet, loud]))
    assert rel["alpha"] == pytest.approx(60 / 210)


def test_dead_channel_is_ignored_and_all_dead_gives_nan():
    good = flat_spectrum_with({(7, 13): 1.0, (15, 30): 1.0})
    rel = relative_band_powers(FREQS, np.vstack([good, np.zeros_like(FREQS)]))
    assert rel["alpha"] == pytest.approx(60 / 210)
    assert all(math.isnan(v) for v in relative_band_powers(FREQS, np.zeros((2, FREQS.size))).values())
    assert all(math.isnan(v) for v in relative_band_powers(FREQS, np.full(FREQS.size, np.nan)).values())


@pytest.mark.parametrize("num,den,expected", [
    (2.0, 1.0, 2.0), (1.0, 0.0, math.nan), (math.nan, 1.0, math.nan), (1.0, math.inf, math.nan),
    (-1.0, 1.0, math.nan), (1e6, 1.0, math.nan),          # absurd (SinWave-like) → NaN
])
def test_safe_ratio(num, den, expected):
    out = safe_ratio(num, den)
    assert (math.isnan(out) and math.isnan(expected)) or out == pytest.approx(expected)


def test_formula_indices_match_published_formulas():
    rel = {"theta": 0.2, "alpha": 0.4, "beta": 0.3}
    out = formula_indices({**rel, "high_beta": 0.1}, alpha1=1.0, alpha2=3.0)
    assert out["concentration"] == pytest.approx(0.3 / 0.4)
    assert out["relaxation"] == pytest.approx(0.4 / 0.3)
    assert out["fatigue"] == pytest.approx(0.6 / 0.3)
    assert out["reverse_fatigue"] == pytest.approx(0.3 / 0.6)
    assert out["cognitive_load"] == pytest.approx(0.2 / 0.4)
    assert out["cognitive_control"] == pytest.approx(0.3 / 0.2)
    assert out["alpha_gravity"] == pytest.approx(3.0)
    assert out["arousal"] == pytest.approx(0.1 / 0.4)
    assert list(out) == list(metrics.INDEX_DEFINITIONS)


def test_alpha_split_at_iapf():
    s = flat_spectrum_with({(7, 10): 1.0, (10, 13): 2.0})
    a1, a2 = alpha_split(FREQS, s, 10.0)
    assert (a1, a2) == (pytest.approx(30), pytest.approx(60))
    assert all(math.isnan(v) for v in alpha_split(FREQS, s, 13.0))   # peak on the border is invalid
    assert all(math.isnan(v) for v in alpha_split(FREQS, s, None))


def test_compute_indices_pipeline_without_iapf_has_nan_gravity():
    s = flat_spectrum_with({(4, 7): 1.0, (7, 13): 1.0, (15, 30): 1.0})
    rel, idx = compute_indices(FREQS, s)
    assert math.isnan(idx["alpha_gravity"])
    assert idx["concentration"] == pytest.approx(150 / 60)


def test_sanitize_and_percent_of_baseline():
    assert math.isnan(sanitize(999996.6))
    assert math.isnan(sanitize(float("inf")))
    assert math.isnan(sanitize("x"))
    assert sanitize(2.5) == 2.5
    assert percent_of_baseline(1.25, 1.0) == pytest.approx(25.0)
    assert math.isnan(percent_of_baseline(1.0, 0.0))
    assert math.isnan(percent_of_baseline(math.nan, 1.0))


def test_rolling_median_window_and_nan():
    m = RollingMedian(window_s=5)
    for t, v in [(0, 1.0), (1, math.nan), (2, 3.0), (3, 100.0)]:
        m.add(t, v)
    assert m.value() == 3.0
    assert m.value(now=7.5) == 100.0          # items older than 5 s dropped
    assert math.isnan(RollingMedian().value())


def test_running_stats_skips_invalid():
    s = RunningStats()
    for v in (1.0, math.nan, 3.0, None):
        s.add(v)
    assert (s.n, s.mean, s.max, s.last) == (2, 2.0, 3.0, 3.0)


def test_score_vs_baseline_mapping():
    assert score_vs_baseline(1.0, 1.0) == pytest.approx(50)
    assert score_vs_baseline(2.0, 1.0) == pytest.approx(50 + 50 * math.tanh(1))      # ≈ 88
    assert score_vs_baseline(0.5, 1.0) == pytest.approx(50 - 50 * math.tanh(1))      # symmetric in log space
    assert 0 <= score_vs_baseline(1e-6, 1.0) < 1 and 99 < score_vs_baseline(1e6, 1.0) <= 100
    for bad in [(math.nan, 1), (1, 0), (0, 1), (-1, 1)]:
        assert math.isnan(score_vs_baseline(*bad))


def test_level_words():
    assert [level(v) for v in (0, 34.9, 35, 64.9, 65, 100)] == ["Low", "Low", "Moderate", "Moderate", "High", "High"]
    assert level(math.nan) == ""


def test_baseline_collector_median_min_samples_and_freeze():
    c = BaselineCollector(min_samples=3)
    c.add({"a": 1.0, "b": math.nan})
    c.add({"a": 3.0, "b": -1})                                   # invalid values ignored
    c.add({"c": 5.0})
    assert not c.enough
    c.add({"a": 100.0})
    assert c.enough and c.count("a") == 3 and c.count("b") == 0
    assert c.freeze() == {"a": 3.0}                             # median; "c" (1 sample) left out, not blocking
    c.add({"a": 1000.0})                                        # frozen: ignored
    assert c.get("a") == 3.0 and math.isnan(c.get("b"))
