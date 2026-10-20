"""
s06_calibration_curve.py  -  how many trials must a NEW user record?

THE QUESTION THIS ANSWERS

s02 showed two numbers: 0.747 for a model trained on other people only, and
0.802 for a model trained on the user's own earlier sessions. The gap is worth
+0.055. But "train on your own sessions" in s02 meant ~400 trials, which is
roughly an hour in the chair. Nobody will do that before every use.

So: starting from the subject-independent model, how fast does accuracy climb
as the new user contributes labelled trials? And is the public dataset worth
anything at all, or would you be better off just training on the user alone?

THREE ARMS, all on 2 channels (C3+C4) to match our headset, all with EA:

  transfer_only     trained on 8 other subjects, 0 trials from the target.
                    A flat line - the s02 P2 number.
  transfer+calib    the 8 other subjects PLUS N labelled trials from the
                    target's own sessions 1-3, simply concatenated. This is
                    what most people do, and it is why this arm is here.
  transfer+weighted the same, but the target's N trials are replicated so they
                    carry HALF the total training mass. 5,760 source trials
                    otherwise drown 40 target trials completely.
  calib_only        ONLY the target's N trials, no public data at all. This is
                    the arm that says whether the public dataset earns its
                    place, and it is the honest control that most papers omit.

Tested on the target's sessions 4-5, which are never touched in training, for
every arm. N is drawn balanced (N/2 per class) and each N is repeated 10 times
with different draws, because a single draw of 10 trials is mostly luck.

Run:  C:\\Python313\\python.exe s06_calibration_curve.py
"""

import csv
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import balanced_accuracy_score

import s04_gelo_transfer as S4

warnings.filterwarnings("ignore")

RES = os.path.join(S4.HERE, "results")
FIG = os.path.join(RES, "figures")
NS = [0, 10, 20, 40, 80, 160, 320]
NREP = 10
MODEL = "csp_lda"   # simplest of the four, and tied for best on 2 channels


def main():
    os.makedirs(FIG, exist_ok=True)
    rng = np.random.default_rng(S4.SEED)
    two = S4.load_2b_2ch()
    subs = list(two)

    rows = []
    for held in subs:
        # target: calibration pool = sessions 1-3, test = sessions 4-5
        c = S4.align(two[held]["cov"], two[held]["sess"])
        y, ss = two[held]["y"], two[held]["sess"]
        pool, test = ss <= 3, ss >= 4
        Xp, yp = c[pool], y[pool]
        Xt, yt = c[test], y[test]

        # source: the other 8 subjects, aligned per session
        Xs, ys = [], []
        for s in subs:
            if s == held:
                continue
            Xs.append(S4.align(two[s]["cov"], two[s]["sess"]))
            ys.append(two[s]["y"])
        Xs, ys = np.concatenate(Xs), np.concatenate(ys)

        for n in NS:
            for rep in range(NREP if n > 0 else 1):
                np.random.seed(S4.SEED + rep)
                if n == 0:
                    idx = np.array([], int)
                else:
                    idx = np.concatenate([
                        rng.choice(np.flatnonzero(yp == cl), n // 2,
                                   replace=False) for cl in (0, 1)])

                # arm 1 + 2: source, optionally plus calibration (concatenated)
                Xtr = np.concatenate([Xs, Xp[idx]]) if n else Xs
                ytr = np.concatenate([ys, yp[idx]]) if n else ys
                m = S4.models()[MODEL].fit(Xtr, ytr)
                b_tr = balanced_accuracy_score(yt, m.predict(Xt))

                # arm 3: source + calibration, target up-weighted to half the
                # training mass by replication (works with any estimator,
                # unlike sample_weight which LDA does not accept)
                b_w = b_tr
                if n:
                    k = max(1, int(round(len(ys) / len(idx))))
                    Xw = np.concatenate([Xs] + [Xp[idx]] * k)
                    yw = np.concatenate([ys] + [yp[idx]] * k)
                    mw = S4.models()[MODEL].fit(Xw, yw)
                    b_w = balanced_accuracy_score(yt, mw.predict(Xt))

                # arm 4: calibration only
                b_cal = np.nan
                if n >= 10 and len(np.unique(yp[idx])) == 2:
                    m2 = S4.models()[MODEL].fit(Xp[idx], yp[idx])
                    b_cal = balanced_accuracy_score(yt, m2.predict(Xt))

                rows.append(dict(subject=held, n=n, rep=rep,
                                 transfer_calib=round(b_tr, 4),
                                 transfer_weighted=round(b_w, 4),
                                 calib_only=round(b_cal, 4)))
        print(f"  {held} done")

    with open(os.path.join(RES, "calibration_curve.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- aggregate and plot ------------------------------------------------
    def agg(field):
        mu, se = [], []
        for n in NS:
            per_sub = [np.nanmean([r[field] for r in rows
                                   if r["subject"] == s and r["n"] == n])
                       for s in subs]
            per_sub = np.array(per_sub, float)
            mu.append(np.nanmean(per_sub))
            se.append(np.nanstd(per_sub, ddof=1) / np.sqrt(len(subs)))
        return np.array(mu), np.array(se)

    m_tc, s_tc = agg("transfer_calib")
    m_w, s_w = agg("transfer_weighted")
    m_co, s_co = agg("calib_only")
    base = m_tc[0]

    print(f"\n{'N trials':<9}{'minutes':>8}{'concat':>10}{'weighted':>11}"
          f"{'calib only':>12}{'best gain':>11}")
    for i, n in enumerate(NS):
        mins = n * 8 / 60  # 2b trial is 8 s cue-to-cue
        co = "      -- " if np.isnan(m_co[i]) else f"{m_co[i]:>12.4f}"
        best = max(m_tc[i], m_w[i], 0 if np.isnan(m_co[i]) else m_co[i])
        print(f"{n:<9}{mins:>8.1f}{m_tc[i]:>10.4f}{m_w[i]:>11.4f}{co}"
              f"{best-base:>+11.4f}")

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    x = np.arange(len(NS))
    ax.errorbar(x, m_w, yerr=s_w, marker="o", lw=2.2, capsize=3,
                color="#2f6f9f", label="public data + N trials, target up-weighted")
    ax.errorbar(x, m_tc, yerr=s_tc, marker="^", lw=1.6, capsize=3,
                color="#7a9bb5", ls="-.",
                label="public data + N trials, naively concatenated")
    ok = ~np.isnan(m_co)
    ax.errorbar(x[ok], m_co[ok], yerr=s_co[ok], marker="s", lw=2, capsize=3,
                color="#c0695f", ls="--",
                label="N trials only (no public data)")
    ax.axhline(base, color="#2f6f9f", ls=":", lw=1.5)
    ax.text(len(NS) - 0.1, base + 0.004,
            f"zero-calibration transfer = {base:.3f}", fontsize=8, ha="right",
            color="#2f6f9f")
    ax.axhline(0.5, color="k", ls="--", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{n}\n({n*8/60:.0f} min)" for n in NS])
    ax.set_xlabel("labelled trials recorded by the new user")
    ax.set_ylabel("balanced accuracy on unseen sessions 4-5")
    ax.set_ylim(0.45, 0.85)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title("Calibration data only helps if you WEIGHT it:\n"
                 "5,760 source trials otherwise drown 40 of the user's own",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig4_calibration_curve.png"), dpi=150)
    plt.close(fig)
    print(f"\nWrote results\\calibration_curve.csv and "
          f"figures\\fig4_calibration_curve.png")


if __name__ == "__main__":
    main()
