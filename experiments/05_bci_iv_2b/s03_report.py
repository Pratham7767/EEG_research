"""
s03_report.py  -  figures and the per-subject table for EXPERIMENT_2.

Reads results\\summary.csv and results\\per_subject.csv (written by s02) and
produces:

  results\\figures\\fig1_ea_effect.png      every model, EA off vs on, both protocols
  results\\figures\\fig2_per_subject.png    per-subject balanced accuracy, P2
  results\\figures\\fig3_vs_stroke.png      this dataset against the stroke ceiling

and prints the per-subject table that goes into REPORT.md.

Run:  C:\\Python313\\python.exe s03_report.py
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
FIG = os.path.join(RES, "figures")

MODELS = ["csp_lda", "csp_svm", "fbcsp_svm", "ts_svm", "tslda", "fgmdm",
          "logvar_svm"]
SUBJECTS = [f"B{i:02d}" for i in range(1, 10)]

# honest numbers from stroke_paper\results\summary.csv, for the comparison plot
STROKE = {"CSP+LDA": 0.5045, "FBCSP+SVM": 0.5270, "TS+SVM": 0.5330,
          "TWFB+FgMDM": 0.5540}
STROKE_PAPER_CLAIM = 0.7221


def read(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    os.makedirs(FIG, exist_ok=True)
    summ = read(os.path.join(RES, "summary.csv"))
    per = read(os.path.join(RES, "per_subject.csv"))

    def S(proto, model, ea, art="all", field="mean_bal"):
        for r in summ:
            if (r["protocol"] == proto and r["model"] == model
                    and int(r["ea"]) == ea and r["artefacts"] == art):
                return float(r[field])
        return np.nan

    # ---- fig 1 : EA effect -------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, proto, title in zip(
            axes,
            ["P1_within_subject", "P2_cross_subject"],
            ["P1  within-subject, cross-session\n(train sessions 1-3, test 4-5)",
             "P2  cross-subject, leave-one-subject-out\n(train 8 subjects, test the 9th)"]):
        x = np.arange(len(MODELS))
        off = [S(proto, m, 0) for m in MODELS]
        on = [S(proto, m, 1) for m in MODELS]
        ax.bar(x - 0.2, off, 0.4, label="EA off", color="#9aa5b1")
        ax.bar(x + 0.2, on, 0.4, label="EA on", color="#2f6f9f")
        for i, (a, b) in enumerate(zip(off, on)):
            ax.annotate(f"+{b-a:.3f}", (i + 0.2, b), ha="center",
                        va="bottom", fontsize=8)
        ax.axhline(0.5, color="k", ls="--", lw=1)
        ax.text(len(MODELS) - 0.4, 0.507, "chance", fontsize=8, ha="right")
        ax.set_xticks(x)
        ax.set_xticklabels(MODELS, rotation=30, ha="right")
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0.45, 0.9)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("balanced accuracy (mean over 9 subjects)")
    axes[0].legend(loc="upper left")
    fig.suptitle("BCI IV 2b - Euclidean Alignment helps every model, "
                 "and helps cross-subject most", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig1_ea_effect.png"), dpi=150)
    plt.close(fig)

    # ---- fig 2 : per subject, P2 ------------------------------------------
    def P(proto, model, ea, art="all"):
        d = {r["subject"]: float(r["bal"]) for r in per
             if r["protocol"] == proto and r["model"] == model
             and int(r["ea"]) == ea and r["artefacts"] == art}
        return np.array([d.get(s, np.nan) for s in SUBJECTS])

    best2 = max(MODELS, key=lambda m: S("P2_cross_subject", m, 1))
    best1 = max(MODELS, key=lambda m: S("P1_within_subject", m, 1))

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(SUBJECTS))
    ax.bar(x - 0.2, P("P2_cross_subject", best2, 0), 0.4, label="EA off",
           color="#9aa5b1")
    ax.bar(x + 0.2, P("P2_cross_subject", best2, 1), 0.4, label="EA on",
           color="#2f6f9f")
    ax.axhline(0.5, color="k", ls="--", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(SUBJECTS)
    ax.set_ylabel("balanced accuracy")
    ax.set_ylim(0.4, 1.0)
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    ax.set_title(f"P2 cross-subject, {best2}: every subject is above chance, "
                 f"but the spread is wide")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig2_per_subject.png"), dpi=150)
    plt.close(fig)

    # ---- fig 3 : against the stroke dataset --------------------------------
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = list(STROKE) + [f"2b P2 cross-subject\n({best2}, EA)",
                             f"2b P1 within-subject\n({best1}, EA)"]
    vals = list(STROKE.values()) + [S("P2_cross_subject", best2, 1),
                                    S("P1_within_subject", best1, 1)]
    colors = ["#c0695f"] * len(STROKE) + ["#2f6f9f", "#2f6f9f"]
    ax.bar(labels, vals, color=colors)
    for i, v in enumerate(vals):
        ax.annotate(f"{v:.3f}", (i, v), ha="center", va="bottom", fontsize=9)
    ax.axhline(0.5, color="k", ls="--", lw=1)
    ax.axhline(STROKE_PAPER_CLAIM, color="#c0695f", ls=":", lw=1.5)
    ax.text(len(labels) - 0.4, STROKE_PAPER_CLAIM + 0.008,
            "Liu et al. claimed 0.7221 (test-set selection; "
            "63.8 % on shuffled labels)", fontsize=8, ha="right",
            color="#c0695f")
    ax.set_ylabel("balanced accuracy")
    ax.set_ylim(0.4, 0.88)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title("Changing the dataset moved the number; four years of "
                 "model-swapping on the stroke data did not")
    plt.setp(ax.get_xticklabels(), fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig3_vs_stroke.png"), dpi=150)
    plt.close(fig)

    # ---- per-subject table -------------------------------------------------
    print(f"best P1 model: {best1}   best P2 model: {best2}\n")
    print("per-subject balanced accuracy, artefact-flagged trials kept\n")
    print(f"{'sub':<6}{'P1 off':>9}{'P1 on':>9}{'P2 off':>9}{'P2 on':>9}"
          f"{'P2 delta':>10}")
    p1o, p1n = P("P1_within_subject", best1, 0), P("P1_within_subject", best1, 1)
    p2o, p2n = P("P2_cross_subject", best2, 0), P("P2_cross_subject", best2, 1)
    for i, s in enumerate(SUBJECTS):
        print(f"{s:<6}{p1o[i]:>9.4f}{p1n[i]:>9.4f}{p2o[i]:>9.4f}{p2n[i]:>9.4f}"
              f"{p2n[i]-p2o[i]:>+10.4f}")
    print(f"{'mean':<6}{p1o.mean():>9.4f}{p1n.mean():>9.4f}"
          f"{p2o.mean():>9.4f}{p2n.mean():>9.4f}{(p2n-p2o).mean():>+10.4f}")

    # EA effect across every configuration
    deltas = [S(p, m, 1, a) - S(p, m, 0, a)
              for p in ("P1_within_subject", "P2_cross_subject")
              for a in ("all", "clean") for m in MODELS]
    deltas = np.array(deltas)
    print(f"\nEA delta across all {len(deltas)} configurations: "
          f"mean {deltas.mean():+.4f}, min {deltas.min():+.4f}, "
          f"max {deltas.max():+.4f}, positive in "
          f"{int((deltas > 0).sum())}/{len(deltas)}")
    print(f"\nFigures written to {FIG}")


if __name__ == "__main__":
    main()
