"""All tunable thresholds and timings in one place. See plan.md §9 for the research behind them."""
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")             # everything personal stays here, on this PC only
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
SDK_LOG_DIR = os.path.join(PROJECT_DIR, "logs")
APP_NAME = "Burnout Guard"

# ── Device / connection ───────────────────────────────────────────
SCAN_SECONDS = 10
CONNECT_TIMEOUT_S = 20
CONNECT_RETRY_DELAYS_S = [2, 5, 10]          # 3 attempts after the first failure
BIPOLAR = True                               # Capsule classifiers expect bipolar mode

# ── Signal quality (Capsule docs: <500k good, 500k-1M average, >1M bad) ──
RES_GOOD_OHM = 500_000
RES_AVERAGE_OHM = 1_000_000
CONTACT_HOLD_S = 5.0                         # all electrodes acceptable this long → gate opens
ARTIFACT_WINDOW_S = 30.0
ARTIFACT_WARN_FRACTION = 0.30                # grey out scores above this

# ── Calibration ───────────────────────────────────────────────────
CALIBRATION_SECONDS = 30                     # quick eyes-closed iAPF calibration
CALIBRATION_TIMEOUT_S = 60
BASELINE_TIMEOUT_S = 240

# ── SDK spectrum (vendor band definitions, Hz) ────────────────────
# The SDK PSD is computed on its processed signal, which is band-passed to
# roughly 4-30 Hz (measured on the simulator: gain 0.14 at 3-4 Hz, 0.14 at
# 40-45 Hz). It is used for the vendor-comparable indices and for stress /
# fatigue, which only need 4-30 Hz and are expressed relative to baseline.
BANDS = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 7.0),
    "alpha": (7.0, 13.0),
    "smr":   (13.0, 15.0),
    "beta":  (15.0, 30.0),
}
TOTAL_RANGE = (1.0, 30.0)
HIGH_BETA = (20.0, 30.0)                     # arousal marker used for the stress score
PSD_PROCESS_INTERVAL_S = 0.5                 # SDK sends ~23 PSD frames/s; we read 2/s
MAX_VALID_RATIO = 100.0                      # ratios above this are treated as invalid (e.g. SinWave)
MAX_VALID_VENDOR_SCORE = 1_000.0

# ── Raw-EEG band powers (IFCN 2017 band definitions) ─────────────
# Computed by us from raw EEG because the SDK removes delta and most gamma.
RAW_BANDS = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta":  (13.0, 30.0),
    "gamma": (30.0, 45.0),                   # stops below 50 Hz mains
}
RAW_TOTAL = (1.0, 45.0)
MAINS_HZ = 50.0                              # India; notch filter frequency
HIGHPASS_HZ = 0.5
RAW_WINDOW_S = 4.0                           # analysis window
WELCH_SEGMENT_S = 2.0                        # 0.5 Hz resolution, 50 % overlap
RAW_PROCESS_INTERVAL_S = 0.5
ARTIFACT_PTP_FACTOR = 4.0                    # reject window if peak-to-peak > 4 × running median
ARTIFACT_PTP_WARMUP = 8                      # windows accepted before the running median is trusted

# ── Scores (0-100) ───────────────────────────────────────────────
# Attention / cognitive load / relaxation: SDK Emotions (its own rest baseline).
# Stress and fatigue: 50 = your level in the first WORK_REF_S of the session. The first real
# session showed the eyes-open rest baseline is the wrong reference: high-beta/alpha was ×1.8
# higher during normal screen work than while fixating a cross, so stress read "High" all session.
SCORE_SMOOTHING_S = 30.0                     # stress (10 s medians still vary ±47 % on real data)
EMOTION_SMOOTHING_S = 5.0                    # attention, cognitive load, relaxation (SDK already smooths)
FATIGUE_SMOOTHING_S = 60.0                   # fatigue changes over minutes, not seconds
BAND_SMOOTHING_S = 5.0
WORK_REF_S = 120.0                           # stress/fatigue reference: first 2 min of the session
FAST_WORK_REF_S = 20.0                       # simulator / imported baseline
OWN_BASELINE_MIN_SAMPLES = 20                # ≥ 10 s of spectra at 2 Hz
FAST_OWN_BASELINE_S = 20.0                   # imported baseline: band reference from the first 20 s of live data
LEVEL_LOW, LEVEL_HIGH = 35.0, 65.0           # Low < 35 ≤ Moderate < 65 ≤ High

# ── Stress episodes (marked on the timeline) ─────────────────────
STRESS_EPISODE_ON = 80.0                     # ≈ 1.6 × your working level
STRESS_EPISODE_OFF = 65.0
STRESS_EPISODE_HOLD_S = 30.0

# ── Breaks (research notes: break_timing.md) ─────────────────────
# Physiological trigger + schedule fallback + anti-nagging rules. HSE: "5-10 min every hour is
# better than 20 min every 2 hours"; micro-breaks <= 10 min raise vigour and lower fatigue
# (Albulescu 2022, d ~ 0.35); mid-morning breaks restore more than late ones (Hunter & Wu 2016).
FATIGUE_BREAK_SCORE = 70.0                   # ≈ (θ+α)/β 34 % above your working level
FATIGUE_BREAK_SUSTAIN_S = 180.0              # must stay high for 3 min
FATIGUE_MIN_LIVE_S = 600.0                   # no fatigue prompt in the first 10 min
WORK_BLOCK_S = 3000.0                        # schedule fallback: 50 min without a real break
MIN_BREAK_S = 120.0                          # shorter breaks are recorded but do not restart the 50 min
MIN_PROMPT_GAP_S = 1200.0                    # at least 20 min between two prompts
AFTER_BREAK_QUIET_S = 2700.0                 # 45 min of quiet after a completed (counted) break
SNOOZE_S = 600.0                             # "Snooze": ask again in 10 min
AFTER_TASK_S = 1200.0                        # "After this task": ask again in 20 min
MAX_PROMPTS_PER_DAY = 8
DECLINE_BACKOFF_COUNT = 2                    # 2 skips in a row → double the gap for the next prompt
MID_MORNING_HOUR = 11                        # one guaranteed break by 11:00 …
MID_MORNING_MIN_WORK_S = 1800.0              # … if you have worked at least 30 min without one
MICRO_BREAK_MIN = 3                          # suggested length of a normal break
LONGER_BREAK_MIN = 10                        # suggested when fatigue stays high after a recent break
EYE_REST_INTERVAL_S = 1200.0                 # optional 20-20-20 nudge (off by default)
SELF_REPORT_INTERVAL_S = 3600.0              # KSS once an hour (EMA: 1-3 prompts/day keep compliance high)
SELF_REPORT_FIRST_S = 60.0                   # … and once at the start of every session

# ── Long-hours context (WHO/ILO 2021: >= 55 h/week raises stroke and heart-disease risk) ──
WEEK_HOURS_WATCH = 45.0
WEEK_HOURS_HIGH = 55.0

# ── Privacy ───────────────────────────────────────────────────────
RETENTION_DAYS = 90                          # session recordings older than this are deleted on start
HELPLINE = "Tele-MANAS (Govt. of India, free): 14416 or 1-800-891-4416"
TREND_WINDOW_S = 1800.0                      # live timeline shows the last 30 min

# ── Fast / simulator mode: neutral imported calibration ──────────
FAST_IAPF = dict(individual_frequency=10.0, individual_peak_frequency=10.0,
                 individual_peak_frequency_power=1.0, individual_peak_frequency_suppression=2.0,
                 individual_bandwidth=6.0, individual_normalized_power=0.5,
                 lower_frequency=7.0, upper_frequency=13.0)
FAST_BASELINE = dict(concentration=1.0, fatigue=1.0, gravity=0.5, productivity=0.5,
                     relax=1.0, reverse_fatigue=1.0)
