"""What is in a person's recordings? Signal quality, ERD (the left/right pattern), and how well models
TRAINED ON THEIR OWN DATA decode them (leave-one-run-out: the model never sees the run it is tested on).
    C:\\Python313\\python.exe tools\\analyze_subject.py P01 Pratham     -> _out/analyze_<names>.txt / .json
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch
from scipy.stats import binomtest, ttest_ind
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import milive  # noqa: E402,F401
from mibci import config as C  # noqa: E402
from mibci.recorder import list_runs, load_run  # noqa: E402
from milive import settings as S  # noqa: E402
from milive.models import LinearCovModel, features, fit_csp, inv_sqrt, load_model, unflat  # noqa: E402
from milive.train2b import FB  # noqa: E402

FS = 250
MONTAGES = {
    "ear_bipolar (C3-A1, C4-A2)": lambda x: np.column_stack([x[:, 1] - x[:, 0], x[:, 2] - x[:, 3]]),
    "linked ears (C3-(A1+A2)/2 ...)": lambda x: np.column_stack([x[:, 1] - (x[:, 0] + x[:, 3]) / 2,
                                                                  x[:, 2] - (x[:, 0] + x[:, 3]) / 2]),
    "raw (C3, C4 vs device ref)": lambda x: x[:, [1, 2]],
}


def trials(run, montage, t0=-2.0, t1=5.0):
    """Epochs -2..5 s around the cue. The continuous signal is high-passed (1 Hz) and notch-filtered (50 Hz)
    BEFORE cutting, so filter edge effects and DC offsets of the dry electrodes do not enter the epochs."""
    from scipy.signal import iirnotch, filtfilt
    x = MONTAGES[montage](np.nan_to_num(run["eeg"]))
    x = sosfiltfilt(butter(2, 1.0, btype="highpass", fs=FS, output="sos"), x - x[0], axis=0)
    bn, an = iirnotch(50.0, 30.0, fs=FS)
    x = filtfilt(bn, an, x, axis=0)
    cues = [(s, c) for s, name, c in run["events"] if name in ("cue_left", "cue_right")]
    out, y = [], []
    for s, c in cues:
        a, b = s + int(t0 * FS), s + int(t1 * FS)
        if a >= 0 and b <= len(x):
            out.append(x[a:b])
            y.append(c)
    return np.array(out), np.array(y)


def bp(X, band):
    sos = butter(4, band, btype="bandpass", fs=FS, output="sos")
    return sosfiltfilt(sos, X - X.mean(1, keepdims=True), axis=1, padtype="even")


def quality(run):
    x = np.nan_to_num(run["eeg"])
    m = MONTAGES["ear_bipolar (C3-A1, C4-A2)"](x)
    f, P = welch(m - m.mean(0), fs=FS, nperseg=FS * 2, axis=0)
    band = lambda lo, hi: P[(f >= lo) & (f < hi)].mean(0)  # noqa: E731
    hum = band(49, 51) / ((band(44, 48) + band(52, 56)) / 2)
    rms = np.sqrt(band(8, 30) * 22)
    hum_uv = np.sqrt(band(49, 51) * 2)                      # rms of the 50 Hz line, uV
    nan = int(np.isnan(run["eeg"]).any(1).sum())
    ptp = np.ptp(m, axis=0)
    return dict(hum_ratio=[round(float(h), 1) for h in hum], rms_8_30_uV=[round(float(r), 1) for r in rms],
                hum_uV=[round(float(h), 1) for h in hum_uv],
                nan_samples=nan, ptp_uV=[round(float(p)) for p in ptp])


def erd(X, y):
    """log power task (0.5-4 s after cue) minus baseline (-2..-0.5 s), per trial, mu and beta, C3/C4."""
    res = {}
    for name, band in (("mu 8-13", (8, 13)), ("beta 13-30", (13, 30))):
        Z = bp(X, band) ** 2
        base = np.log(Z[:, 0:int(1.5 * FS)].mean(1))
        task = np.log(Z[:, int(2.5 * FS):int(6.0 * FS)].mean(1))
        r = task - base                                                # (trials, 2) C3, C4
        lat = r[:, 1] - r[:, 0]                                        # C4 change - C3 change
        # left MI: C4 drops -> lat < 0; right MI: C3 drops -> lat > 0
        L, R = lat[y == C.LEFT], lat[y == C.RIGHT]
        t = ttest_ind(R, L)
        res[name] = dict(C3_left=float(r[y == C.LEFT, 0].mean()), C4_left=float(r[y == C.LEFT, 1].mean()),
                         C3_right=float(r[y == C.RIGHT, 0].mean()), C4_right=float(r[y == C.RIGHT, 1].mean()),
                         lateral_right_minus_left=float(R.mean() - L.mean()), t=float(t.statistic),
                         p_one_sided=float(t.pvalue / 2 if t.statistic > 0 else 1 - t.pvalue / 2))
    return res


def covs_windows(X, band, ends_s=(1.5, 4.0), step_s=0.2):
    """2 s window covariances ending 1.5-4.0 s after the cue (cue at index 2*FS in X), zero-phase filter here."""
    Y = bp(X, band)
    out = []
    for e in np.arange(ends_s[0], ends_s[1] + 1e-9, step_s):
        b = int((2.0 + e) * FS)
        W = Y[:, b - 2 * FS:b]
        W = W - W.mean(1, keepdims=True)
        out.append(np.einsum("nti,ntj->nij", W, W) / (2 * FS - 1))
    return np.stack(out, 1)                                            # (trials, windows, 2, 2)


def loro(runs_xy, bands, feature, clf):
    """leave-one-run-out, each run aligned to its own mean covariance (as live EA)."""
    k = n = 0
    per = []
    A_runs = []
    for X, y in runs_xy:
        Ab = []
        for b in bands:
            Cw = covs_windows(X, b)
            P = inv_sqrt(Cw.reshape(-1, 2, 2).mean(0))
            Ab.append(P @ Cw @ P)
        A_runs.append(Ab)
    for i in range(len(runs_xy)):
        tr = [j for j in range(len(runs_xy)) if j != i]
        ytr = np.concatenate([np.repeat(runs_xy[j][1], A_runs[j][0].shape[1]) for j in tr])
        Atr = [np.concatenate([A_runs[j][b].reshape(-1, 2, 2) for j in tr]) for b in range(len(bands))]
        if len(set(ytr.tolist())) < 2:
            continue
        W = fit_csp(Atr, ytr) if feature == "csp" else None
        Z = features(feature, Atr, W)
        sc = StandardScaler().fit(Z)
        c = (LinearSVC(C=0.1, class_weight="balanced", dual="auto", max_iter=20000) if clf == "svm"
             else LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))
        c.fit(sc.transform(Z), (ytr == C.RIGHT).astype(int))
        X, y = runs_xy[i]
        nw = A_runs[i][0].shape[1]
        Ate = [A_runs[i][b].reshape(-1, 2, 2) for b in range(len(bands))]
        d = c.decision_function(sc.transform(features(feature, Ate, W))).reshape(len(y), nw)
        pred = np.where(np.mean(np.sign(d), 1) >= 0, C.RIGHT, C.LEFT)
        kk = int((pred == y).sum())
        per.append(round(kk / len(y), 2))
        k += kk
        n += len(y)
    return k, n, per


def base_model_on(runs_xy, model, bands):
    k = n = 0
    for X, y in runs_xy:
        Ab = []
        for b in bands:
            Cw = covs_windows(X, b)
            P = inv_sqrt(Cw.reshape(-1, 2, 2).mean(0))
            Ab.append((P @ Cw @ P).reshape(-1, 2, 2))
        d = model.decide(Ab).reshape(len(y), -1)
        d = d - d.mean()
        pred = np.where(np.mean(np.sign(d), 1) >= 0, C.RIGHT, C.LEFT)
        k += int((pred == y).sum())
        n += len(y)
    return k, n


def main(subjects):
    lines = []
    say = lambda s="": (print(s, flush=True), lines.append(s))  # noqa: E731
    runs = [p for s in subjects for p in list_runs(s)]
    loaded = {p: load_run(p) for p in runs}
    say(f"Subjects {subjects}: {len(runs)} runs")
    for p, r in loaded.items():
        q = quality(r)
        nt = sum(1 for e in r["events"] if e[1] in ("cue_left", "cue_right"))
        say(f"  {p.parent.name}/{p.name:30s} {r['meta'].get('run_type', ''):9s} {len(r['eeg']) / FS:6.0f} s  "
            f"cued trials {nt:3d} | 8-30 Hz rms C3 {q['rms_8_30_uV'][0]} C4 {q['rms_8_30_uV'][1]} uV | "
            f"50 Hz hum {q['hum_uV'][0]} / {q['hum_uV'][1]} uV (x{q['hum_ratio'][0]} / x{q['hum_ratio'][1]}) | NaN {q['nan_samples']}")
    imag = [p for p in runs if loaded[p]["meta"].get("run_type") in ("screening", "feedback")]
    mov = [p for p in runs if loaded[p]["meta"].get("run_type") == "movement"]
    res = {}
    for montage in MONTAGES:
        say(f"\n=== montage {montage} ===")
        for label, group in (("IMAGERY", imag), ("REAL MOVEMENT", mov)):
            xy = [trials(loaded[p], montage) for p in group]
            xy = [(X, y) for X, y in xy if len(y)]
            if not xy:
                continue
            X = np.concatenate([a for a, _ in xy])
            y = np.concatenate([b for _, b in xy])
            e = erd(X, y)
            say(f"{label}: {len(y)} trials ({int((y == 1).sum())} left / {int((y == 2).sum())} right)")
            for bn, v in e.items():
                say(f"  ERD {bn:10s} log-power change task vs rest:  LEFT hand: C3 {v['C3_left']:+.2f} C4 {v['C4_left']:+.2f}"
                    f" | RIGHT hand: C3 {v['C3_right']:+.2f} C4 {v['C4_right']:+.2f} | lateralisation "
                    f"{v['lateral_right_minus_left']:+.3f} (expected > 0) p = {v['p_one_sided']:.3f}")
            res[(montage, label)] = dict(erd=e)
            if label == "IMAGERY" and len(xy) >= 2:
                for name, bands, feat, clf in (("csp_svm 8-30", [(8, 30)], "csp", "svm"),
                                               ("logvar_lda 8-30", [(8, 30)], "logvar", "lda"),
                                               ("mu-only logvar_lda 8-13", [(8, 13)], "logvar", "lda"),
                                               ("beta-only logvar_lda 13-30", [(13, 30)], "logvar", "lda"),
                                               ("fbcsp_svm 4-40", FB, "csp", "svm"),
                                               ("fbcsp_lda 4-40", FB, "csp", "lda")):
                    k, n, per = loro(xy, bands, feat, clf)
                    p = binomtest(k, n, 0.5, alternative="greater").pvalue if n else 1
                    say(f"  own-data model {name:26s} leave-one-run-out {k}/{n} = {100 * k / max(n, 1):.0f} % p = {p:.3f}  per run {per}")
                for mf in (S.LIVE_DIR / "models" / "base_2b_live.json", S.BASE_JSON):
                    m = load_model(mf)
                    k, n = base_model_on(xy, m, m.bands)
                    p = binomtest(k, n, 0.5, alternative="greater").pvalue
                    say(f"  2b model (no own data) {m.name:40s} {k}/{n} = {100 * k / n:.0f} % p = {p:.3f}")
    out = S.OUT_DIR / f"analyze_{'_'.join(subjects)}.txt"
    out.write_text("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1:] or ["P01", "Pratham"])
