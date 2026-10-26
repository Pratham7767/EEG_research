"""mi_live: real-time LEFT / RIGHT output from our CSP + SVM + Euclidean Alignment model, for a bot.

It reuses (read-only, nothing is copied or changed) the headset, filter and SVM code of apps/mi_bci,
so the numbers here are exactly the numbers that apps/mi_bci was verified with.
"""
import sys
from pathlib import Path

LIVE_DIR = Path(__file__).resolve().parents[1]          # apps/mi_live
MIBCI_DIR = LIVE_DIR.parent / "mi_bci"                  # apps/mi_bci
if str(MIBCI_DIR) not in sys.path:
    sys.path.insert(0, str(MIBCI_DIR))
