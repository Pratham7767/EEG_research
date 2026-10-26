"""Milestone M0 checks: does the headset see the motor cortex?

alpha_check(baseline run)  eyes-closed vs eyes-open 8-13 Hz power at C3/C4 (alpha should rise)
erd_check(runs)            done SEPARATELY for each run type (real movement and imagery are different
                           tasks). Two numbers per band and channel:
  * classic ERD% (Pfurtscheller): power averaged over trials first, then % change from the reference
    period. Negative = desynchronisation. Expected: left hand -> C4 drops more; right hand -> C3.
  * the test: per trial, log(task power / reference power) at C3 and C4; lateralisation
    LI = logratio(C4) - logratio(C3); right-hand trials should have higher LI than left-hand trials.
    One-sided permutation test. Log ratios are used because single-trial % changes are dominated by a
    few noisy trials.
Offline only, so zero-phase filtering is fine here.
"""
import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

from . import config as C
from .dsp import apply_montage
from .recorder import load_run
from .trainer import cues

I_C3, I_C4 = C.CHANNELS.index("C3"), C.CHANNELS.index("C4")
BANDS = {"mu": (8, 13), "beta": (13, 30)}
BASE_WIN = (-2.0, -1.0)      # before the warning beep / cue, as in RUN_ERD_PSD_2b.m
TASK_WIN = (0.5, 3.5)


MIN_TRIALS = 30              # per hand, before a failed test means anything


def trial_powers(eeg, cue_list, band):
    """Per trial: (class, ref C3, ref C4, task C3, task C4) mean band power."""
    sos = butter(4, band, btype="bandpass", fs=C.FS, output="sos")
    m = np.nan_to_num(apply_montage(eeg)[:, [I_C3, I_C4]])
    p = sosfiltfilt(sos, m - m.mean(0), axis=0) ** 2
    out = []
    for s, c in cue_list:
        b0, b1 = s + int(BASE_WIN[0] * C.FS), s + int(BASE_WIN[1] * C.FS)
        t0, t1 = s + int(TASK_WIN[0] * C.FS), s + int(TASK_WIN[1] * C.FS)
        if b0 < 0 or t1 > len(p):
            continue
        out.append((c, *p[b0:b1].mean(0), *p[t0:t1].mean(0)))
    return np.array(out)


def _erd_one(rows, n_perm, rng):
    cls = rows[:, 0].astype(int)
    ref, task = rows[:, 1:3], rows[:, 3:5]
    out = dict(trials_left=int((cls == C.LEFT).sum()), trials_right=int((cls == C.RIGHT).sum()))
    for c, name in ((C.LEFT, "left"), (C.RIGHT, "right")):        # classic ERD%: average power first
        k = cls == c
        erd = 100 * (task[k].mean(0) / ref[k].mean(0) - 1)
        out[f"{name}_hand_ERD_C3"] = round(float(erd[0]), 1)
        out[f"{name}_hand_ERD_C4"] = round(float(erd[1]), 1)
    lr = np.log(task / ref)
    li = lr[:, 1] - lr[:, 0]
    stat = li[cls == C.RIGHT].mean() - li[cls == C.LEFT].mean()        # expected > 0
    null = np.empty(n_perm)
    for i in range(n_perm):
        pc = rng.permutation(cls)
        null[i] = li[pc == C.RIGHT].mean() - li[pc == C.LEFT].mean()
    pval = float((np.sum(null >= stat) + 1) / (n_perm + 1))
    enough = min(out["trials_left"], out["trials_right"]) >= MIN_TRIALS
    right_way = stat > 0
    out.update(lateralisation=round(float(stat), 3), right_direction=bool(right_way), p_one_sided=round(pval, 4),
               passes=bool(pval < 0.05 and right_way),
               verdict=("PASS: opposite-side ERD, p < 0.05" if pval < 0.05 and right_way else
                        f"TOO FEW TRIALS ({min(out['trials_left'], out['trials_right'])} per hand, need "
                        f"{MIN_TRIALS}+): " + ("pointing the right way, keep recording" if right_way
                                               else "not visible yet, keep recording") if not enough else
                        "FAIL: no opposite-side ERD with enough trials"))
    return out


def erd_check(run_paths, n_perm=5000, seed=0):
    """Per run type and band. Top-level 'passes' = any run type passes in any band."""
    rng = np.random.default_rng(seed)
    groups = {}
    for p in run_paths:
        r = load_run(p)
        groups.setdefault(r["meta"].get("run_type", "unknown"), []).append(r)
    res, summary = {}, []
    for rt, runs in groups.items():
        res[rt] = {}
        for name, band in BANDS.items():
            rows = [trial_powers(r["eeg"], cues(r["events"]), band) for r in runs]
            rows = [x for x in rows if len(x)]
            if not rows:
                continue
            res[rt][name] = _erd_one(np.vstack(rows), n_perm, rng)
            v = res[rt][name]
            summary.append(f"{rt:9s} {name:4s} ({len(runs)} run(s)): {v['verdict']}  "
                           f"| left hand: C3 {v['left_hand_ERD_C3']:+.0f}% C4 {v['left_hand_ERD_C4']:+.0f}%  "
                           f"| right hand: C3 {v['right_hand_ERD_C3']:+.0f}% C4 {v['right_hand_ERD_C4']:+.0f}%  "
                           f"| p = {v['p_one_sided']:.3f}")
    if not summary:
        return dict(error="no cued trials found")
    res["summary"] = summary
    res["how_to_read"] = ("ERD% < 0 = rhythm drops (that brain side is active). Expected: left hand -> C4 drops "
                          "more than C3; right hand -> C3 drops more than C4. Judge only with 30+ trials per hand.")
    res["passes"] = any(v.get("passes") for rt in groups for v in res.get(rt, {}).values())
    return res


def signal_quality(x_uv, skip_s=0.0):
    """Quick contact check on a few seconds of raw samples (n x 4, microvolts).
    skip_s: seconds dropped at the start (the amplifier settles after leaving resistance mode).
    Reports the EEG-band level (1-40 Hz, 50 Hz notched), the 50 Hz mains level separately, and the
    level over the whole test per second, so a start-up jump, mains hum and real noise can be told apart."""
    from scipy.signal import butter as _b, iirnotch, sosfiltfilt as _f, filtfilt
    from .dsp import bandpower_offline
    from .trainer import artifact_flags
    x = np.nan_to_num(np.asarray(x_uv, float))[int(skip_s * C.FS):]
    if len(x) < 4 * C.FS:
        return dict(error="need at least 4 s of signal after the settling time")
    pinned = np.isclose(np.abs(x), np.abs(x).max(0), rtol=1e-6).mean(0)
    m = apply_montage(x)
    m = m - np.median(m, axis=0)
    bn, an = iirnotch(50.0, 30.0, fs=C.FS)
    eeg = _f(_b(4, (1, 40), btype="bandpass", fs=C.FS, output="sos"), filtfilt(bn, an, m, axis=0), axis=0)
    mains = _f(_b(4, (48, 52), btype="bandpass", fs=C.FS, output="sos"), m, axis=0)
    sd, sd50 = eeg.std(0), mains.std(0)
    per_s = [[round(float(eeg[s:s + C.FS, k].std()), 1) for s in range(0, len(eeg) - C.FS + 1, C.FS)]
             for k in range(4)]
    i, _ = bandpower_offline(m, [I_C3, I_C4], [(8, 13)])
    art = float(artifact_flags(m, i).mean()) if len(i) else 1.0
    ok = {ch: bool(pinned[k] < 0.01 and 2 < sd[k] < 200) for k, ch in enumerate(C.CHANNELS) if ch in ("C3", "C4")}
    names = {"A1": "A1", "C3": "C3-A1" if C.MONTAGE == "ear_bipolar" else "C3",
             "C4": "C4-A2" if C.MONTAGE == "ear_bipolar" else "C4", "A2": "A2"}
    verdict = "GOOD" if all(ok.values()) and art < 0.2 else (
        "MAINS HUM: unplug the laptop charger / move away from cables" if
        all(sd50[k] > 3 * sd[k] for k in (I_C3, I_C4)) and all(sd[k] < 200 for k in (I_C3, I_C4)) else
        "BAD CONTACT: fix the electrodes before recording")
    return dict(seconds=round(len(x) / C.FS, 1), skipped_s=skip_s,
                eeg_1_40Hz_uV={names[ch]: round(float(sd[k]), 1) for k, ch in enumerate(C.CHANNELS)},
                mains_50Hz_uV={names[ch]: round(float(sd50[k]), 1) for k, ch in enumerate(C.CHANNELS)},
                eeg_per_second_uV={names[ch]: per_s[k] for k, ch in enumerate(C.CHANNELS) if ch in ("C3", "C4")},
                pinned_fraction={names[ch]: round(float(pinned[k]), 3) for k, ch in enumerate(C.CHANNELS)},
                artifact_fraction=round(art, 3), decode_channels_ok=ok, verdict=verdict)


def alpha_check(run_path):
    r = load_run(run_path)
    ev = {name: s for s, name, _ in r["events"]}
    out = {}
    for blk in ("eyes_open", "eyes_closed"):
        if f"{blk}_start" not in ev or f"{blk}_end" not in ev:
            return dict(error=f"block {blk} missing")
        seg = np.nan_to_num(apply_montage(r["eeg"])[ev[f"{blk}_start"]:ev[f"{blk}_end"], [I_C3, I_C4]])
        f, pxx = welch(seg, fs=C.FS, nperseg=2 * C.FS, axis=0)
        out[blk] = (f, pxx)
    f = out["eyes_open"][0]
    a = (f >= 8) & (f <= 13)
    ratio = out["eyes_closed"][1][a].mean(0) / out["eyes_open"][1][a].mean(0)
    peak = f[a][np.argmax(out["eyes_closed"][1][a].mean(1))]
    return dict(alpha_ratio_closed_over_open={"C3": float(ratio[0]), "C4": float(ratio[1])},
                alpha_peak_hz=float(peak), passes=bool(ratio.min() > 1.2))
