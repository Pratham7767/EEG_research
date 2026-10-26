"""All fixed settings in one place. Times are in seconds unless the name says otherwise.

The values copy the Graz protocol that produced BCI Competition IV 2b (Leeb et al. 2007):
1 s log band power, LDA, 2 s integration of the output, smiley feedback from 3.0 to 7.5 s.
"""
from pathlib import Path

FS = 250                                   # headphones and 2b both sample at 250 Hz
CHANNELS = ["A1", "C3", "C4", "A2"]        # LEHeadPhones2 order (SDK Ch1..Ch4)
DECODE_CHANNELS = ["C3", "C4"]             # what the decoder may use
# "ear_bipolar": decode C3-A1 and C4-A2 (what the Capsule app records; cancels the large common
# DC offset seen on the raw NeuroSDK channels). "raw": C3 and C4 as delivered.
# The recorder always stores the 4 raw channels; the montage is applied before features.
MONTAGE = "ear_bipolar"
# The model the app trains and uses: "svm" = CSP + SVM + Euclidean Alignment, starting from the
# BCI IV 2b base model and improved with the subject's runs (mibci/svm.py, svm_trainer.py).
# "lda" = the Graz 2008 log-band-power LDA (kept for comparison only).
MODEL = "svm"

APP_DIR = Path(__file__).resolve().parents[1]          # apps/mi_bci
REPO = APP_DIR.parents[1]                               # D:/trainsvm
DATA_DIR = REPO / "data" / "mi_bci"                     # recordings live with the other raw data
NEUROSDK_PATH = REPO / "hardware" / "eeg_headphones" / "brain_bit" / "pyneurosdk2-1.0.15"
BCI2B_DIR = REPO / "experiments" / "05_bci_iv_2b" / "data"

# ---- features (Graz: band-pass, square, 1 s moving average, log) ----
FEATURE_WIN_S = 1.0
HOP = 10                                   # samples between decoder outputs: 10 / 250 Hz = 40 ms
FILTER_ORDER = 5                           # Butterworth, as in Leeb 2007
# candidate bands; the trainer picks the best few per person (Graz picked <= 6 features)
CANDIDATE_BANDS = [(8, 10), (10, 12), (12, 14), (8, 13), (14, 18), (18, 24), (24, 30), (13, 30), (16, 24)]
MAX_FEATURES = 6
INTEGRATE_S = 2.0                          # smiley position = mean sign of the last 2 s of outputs

# ---- artifact check on raw C3/C4 (relative, like the Cognitive Score app) ----
ARTIFACT_PTP_FACTOR = 4.0                  # 1 s peak-to-peak > 4 x running median -> artifact
ARTIFACT_WARMUP = 25                       # outputs before the median is trusted (1 s)
ARTIFACT_ABS_UV = 1500.0                   # always an artifact above this peak-to-peak
ARTIFACT_HIGHPASS_HZ = 1.0                 # remove DC/drift first (dry electrodes sit at tens of mV)

# ---- trial timing, seconds from trial start ----
TIMING = {
    # cued imagery without feedback (2b sessions 01T-02T) and the real-movement check
    "screening": dict(beep=0.0, cue=3.0, cue_off=4.25, task_end=7.0, rest=(1.5, 2.5)),
    "movement":  dict(beep=0.0, cue=3.0, cue_off=4.25, task_end=7.0, rest=(1.5, 2.5)),
    # smiley feedback (2b sessions 03T-05E): beep 2 s, cue + feedback 3.0-7.5 s, blank 1-2 s
    "feedback":  dict(beep=2.0, cue=3.0, cue_off=7.5, task_end=7.5, rest=(1.0, 2.0)),
}
DEFAULT_TRIALS_PER_CLASS = {"screening": 10, "movement": 10, "feedback": 20}
MAX_SAME_IN_A_ROW = 3

# ---- training / evaluation windows, seconds after the cue ----
TRAIN_WIN = (0.5, 4.0)                     # feature rows used to fit the LDA
EVAL_WIN = (1.0, 4.0)                      # outputs integrated to score one trial
RETRAIN_MIN_GAIN = 0.05                    # Graz rule: switch only if >= 5 points better

# ---- event codes (GDF-style, as in 2b) ----
EV = {
    "run_start": 32766, "trial_start": 768, "cue_left": 769, "cue_right": 770,
    "feedback_start": 781, "cue_off": 790, "task_end": 800, "run_end": 32767, "beep": 801,
}
LEFT, RIGHT = 1, 2                          # class labels (2b convention)
CLASS_NAME = {LEFT: "left", RIGHT: "right"}
