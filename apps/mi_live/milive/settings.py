"""All mi_live settings. Times in seconds."""
from mibci import config as C
from mibci.svm_trainer import BASE_JSON, EVAL_WIN  # noqa: F401  (EVAL_WIN = 1.5-4.0 s after the cue)

from . import LIVE_DIR

FS = C.FS                       # 250 Hz
HOP = C.HOP                     # 10 samples -> one output every 40 ms
OUT_DT = HOP / FS

# 2 s integrator, as Graz (Leeb 2007) and apps/mi_bci: v = mean sign of the last 2 s of outputs, -1..+1
INTEGRATE_S = 2.0

# Bot command rule (can be changed live in the window)
THRESHOLD = 0.5                 # |v| >= 0.5 means >= 75 % of the last 2 s of outputs agree
HOLD_S = 0.5                    # ... and that has stayed so for 0.5 s
NEUTRAL = "STOP"                # what the bot does when neither side wins: "STOP" or "FORWARD"
ARTIFACT_STOP_S = 0.5           # signal is an artifact for this long -> STOP (safety)

# Calibration: 60 s at the start. Used ONLY without labels: the alignment reference (mean covariance)
# and the bias (mean output) are taken over all 60 s. The blocks just make sure both hands and rest are in it.
CALIB_BLOCKS = [("relax", 20), ("left", 20), ("right", 20)]

# Kappa-over-time window (seconds after the cue), as in the competition scoring
CURVE_T = (-1.0, 4.5)

DATA_LIVE = C.REPO / "data" / "mi_live"
OUT_DIR = LIVE_DIR / "_out"
