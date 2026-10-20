"""Raw-EEG band pipeline checked against signals with known spectra."""
import numpy as np
import pytest
from scipy.signal import sosfreqz

from cogscore import config
from cogscore.spectral import RawBandAnalyzer, StreamFilter, design_filter

FS = 250.0
WIDTHS = {b: hi - lo for b, (lo, hi) in config.RAW_BANDS.items()}
TOTAL = config.RAW_TOTAL[1] - config.RAW_TOTAL[0]


def feed(analyzer, signal, block=10):
    frames = []
    for i in range(0, len(signal), block):
        analyzer.push(signal[i:i + block])
        if analyzer.ready():
            frames.append(analyzer.compute())
    return frames


def accepted(frames):
    return [f for f in frames if f["rel"]]


def mean_rel(frames):
    return {b: np.mean([f["rel"][b] for f in accepted(frames)]) for b in config.RAW_BANDS}


def test_white_noise_band_share_equals_bandwidth():
    """Flat spectrum → each band's share = its width / 44 Hz. Averaged over 4 × 60 s
    (a single 60 s run scatters by ~5 % per band; measured bias over 12 seeds < 2.5 %)."""
    runs = []
    for seed in range(4):
        x = np.random.default_rng(seed).normal(0, 20e-6, size=(int(FS * 60), 2))
        runs.append(mean_rel(feed(RawBandAnalyzer(FS, 2), x)))
    for band, width in WIDTHS.items():
        assert np.mean([r[band] for r in runs]) == pytest.approx(width / TOTAL, rel=0.06), band


def test_alpha_rhythm_dominates_and_dc_offset_is_removed():
    t = np.arange(int(FS * 30)) / FS
    rng = np.random.default_rng(1)
    alpha = 30e-6 * np.sin(2 * np.pi * 10 * t)
    x = np.column_stack([alpha, alpha]) + rng.normal(0, 2e-6, (t.size, 2)) + np.array([-0.06, 0.03])  # real DC levels
    frames = feed(RawBandAnalyzer(FS, 2), x)
    rel = mean_rel(frames)
    assert rel["alpha"] > 0.8
    assert max(rel, key=rel.get) == "alpha"
    assert not [f for f in frames if f["rejected"] == "amplitude"]


def test_mains_notch_attenuates_50hz():
    sos = design_filter(FS)
    w, h = sosfreqz(sos, worN=[10.0, 45.0, 50.0], fs=FS)
    gain_db = 20 * np.log10(np.abs(h))
    assert gain_db[0] > -0.5                                   # 10 Hz untouched
    assert gain_db[1] > -3                                     # gamma band edge mostly kept
    assert gain_db[2] < -30                                    # 50 Hz removed


def test_strong_mains_hum_does_not_leak_into_gamma():
    t = np.arange(int(FS * 30)) / FS
    rng = np.random.default_rng(2)
    base = rng.normal(0, 10e-6, (t.size, 1))
    hum = 300e-6 * np.sin(2 * np.pi * 50 * t)[:, None]           # 30× the EEG, as seen on the real headset
    clean = mean_rel(feed(RawBandAnalyzer(FS, 1), base))
    humming = mean_rel(feed(RawBandAnalyzer(FS, 1), base + hum))
    assert humming["gamma"] == pytest.approx(clean["gamma"], abs=0.03)


def test_streaming_filter_matches_one_pass():
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, (1000, 2)) + 5.0
    f = StreamFilter(FS, 2)
    chunked = np.vstack([f.process(x[i:i + 37]) for i in range(0, 1000, 37)])
    g = StreamFilter(FS, 2)
    whole = g.process(x)
    assert np.allclose(chunked, whole)


def test_sdk_artifact_flag_rejects_current_window():
    rng = np.random.default_rng(4)
    a = RawBandAnalyzer(FS, 2)
    feed(a, rng.normal(0, 20e-6, (int(FS * 8), 2)))
    a.mark_artifact()
    frames = feed(a, rng.normal(0, 20e-6, (int(FS * 2), 2)))
    assert frames and all(f["rejected"] == "sdk_artifact" for f in frames)
    later = feed(a, rng.normal(0, 20e-6, (int(FS * 6), 2)))
    assert accepted(later), "windows after the artifact has left the 4 s window are accepted again"


def test_amplitude_spike_is_rejected_after_warmup():
    rng = np.random.default_rng(5)
    a = RawBandAnalyzer(FS, 2)
    feed(a, rng.normal(0, 20e-6, (int(FS * 15), 2)))
    burst = rng.normal(0, 20e-6, (int(FS * 1), 2))
    burst[100:110] += 2e-3                                       # movement / jaw artifact
    frames = feed(a, burst)
    assert any(f["rejected"] == "amplitude" for f in frames)
    assert 0 < a.rejected_fraction < 0.5


def test_flat_signal_is_rejected_not_divided_by_zero():
    a = RawBandAnalyzer(FS, 2)
    frames = feed(a, np.zeros((int(FS * 8), 2)))
    assert frames and all(f["rejected"] for f in frames)
