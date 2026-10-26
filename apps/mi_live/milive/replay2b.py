"""BCI Competition IV 2b replayed as if it were a headset, and the honest model for it.

The model for subject B0x is the base SVM trained on the OTHER 8 subjects only (leave-one-subject-out),
so the replay shows how the model does on a person it has never seen, like you.
"""
import numpy as np
from scipy.io import loadmat

from mibci import config as C
from mibci.sources import ReplaySource

from . import settings as S


def load_session(sub, session=4):
    """2b session (1-5) as (eeg (n, 4) A1,C3,C4,A2 with A1 = A2 = 0, events, cue samples flagged as artifact)."""
    split = "T" if session <= 3 else "E"
    m = loadmat(C.BCI2B_DIR / f"B{sub:02d}{split}.mat", squeeze_me=True, struct_as_record=False)
    s = np.atleast_1d(m["data"])[session - 1 if split == "T" else session - 4]
    X = np.asarray(s.X, float)
    trial = np.atleast_1d(s.trial).astype(int) - 1
    y = np.atleast_1d(s.y).astype(int)
    art = np.atleast_1d(getattr(s, "artifacts", np.zeros(len(y)))).astype(bool)
    eeg = np.zeros((len(X), 4))
    eeg[:, 1], eeg[:, 2] = X[:, 0], X[:, 2]                 # C3, C4 (Cz and EOG dropped: headphones have none)
    fs = C.FS
    ev = [(0, "run_start", None)]
    for tr, c in zip(trial, y):
        cue = tr + 3 * fs                                   # 2b: cue = trial start + 3 s
        ev += [(int(tr), "trial_start", int(c)), (int(cue), "cue_left" if c == C.LEFT else "cue_right", int(c)),
               (int(cue), "feedback_start", int(c)), (int(tr + int(7.5 * fs)), "task_end", int(c))]
    ev.append((len(X) - 1, "run_end", None))
    ev.sort(key=lambda e: e[0])
    art_cues = {int(tr + 3 * fs) for tr, a in zip(trial, art) if a}
    return np.nan_to_num(eeg), ev, art_cues


class Replay2bSource(ReplaySource):
    name = "replay_2b"

    def __init__(self, eeg, speed=1.0, realtime=True, chunk=10):
        super().__init__(eeg, chunk=chunk, speed=speed, realtime=realtime)


def best_spec():
    """The model type chosen by tools/compare_models.py (saved in models/base_2b_live.json), else CSP + SVM."""
    import json
    p = S.LIVE_DIR / "models" / "base_2b_live.json"
    if p.exists():
        return json.loads(p.read_text())["meta"].get("spec", "csp_svm")
    return "csp_svm"


def loso_model(sub, spec=None):
    """The live model type, trained on the 8 OTHER 2b subjects (B0x never seen)."""
    from .train2b import train
    m = train(spec or best_spec(), [s for s in range(1, 10) if s != sub])
    m.meta["trained_on"] = f"BCI IV 2b without B{sub:02d} (8 subjects)"
    return m
