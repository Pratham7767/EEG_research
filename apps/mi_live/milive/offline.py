"""An independent, vectorised re-computation of what LivePipeline outputs (adaptive alignment), used to
prove that the live code computes exactly this. Not used live."""
import numpy as np

from mibci.dsp import apply_montage
from mibci.trainer import artifact_flags

from .dsp_extra import Notch
from .models import inv_sqrt, unflat


def offline_outputs(model, eeg):
    """Returns (idx, d, bad) for a whole recording, adaptive alignment + running bias from sample 0."""
    m = Notch(model.channel_idx).process(apply_montage(np.asarray(eeg, float), model.montage))
    idx, F = model.make_extractor().process(m)
    bad = artifact_flags(m, idx)
    inc = ~bad
    inc[0] = True                                    # the first window always seeds the mean
    cs = np.cumsum(F * inc[:, None], 0) / np.cumsum(inc)[:, None]
    A = []
    for b in range(len(model.bands)):
        P = inv_sqrt(unflat(cs[:, 3 * b:3 * b + 3]))
        A.append(P @ unflat(F[:, 3 * b:3 * b + 3]) @ P)
    raw = model.decide(A)
    g = (~bad).astype(float)
    cnt = np.cumsum(g)
    bias = np.where(cnt > 0, np.cumsum(raw * g) / np.maximum(cnt, 1), 0.0)
    return idx, raw - bias, bad
