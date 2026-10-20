"""
s07_confusion.py  -  confusion matrices for our SVM, trained and tested on 2b.

TRAINED ON 2b, TESTED ON 2b. This is the decoder working as intended, which is
the thing worth showing a supervisor. (The Gelo transfer is a separate result
and is at chance - see REPORT.md section 9.)

Two protocols, both honest:

  P1  within-subject   train on that person's sessions 1-3, test on 4-5.
                       Matches the competition's own split, where sessions
                       01T/02T/03T are training and 04E/05E evaluation.
  P2  cross-subject    train on 8 subjects, test on the 9th. Harder, and the
                       one that matters for deploying to a new user.

CONVENTIONS TAKEN FROM THE OFFICIAL DATASET DESCRIPTION
(Leeb, Brunner, Mueller-Putz, Schloegl & Pfurtscheller, "BCI Competition
2008 - Graz data set B"):

  * class 1 = LEFT hand (cue event 769), class 2 = RIGHT hand (event 770).
  * cue onset is at second 3 of the trial, after a 3 s fixation period with a
    warning beep at second 2; imagery then runs for 4 s. Our epoch window of
    0.5-3.5 s after cue therefore sits inside the imagery period.
  * the EOG channels "must not be used for classification" - we drop them.
  * "A confusion matrix will then be built from all artifact-free trials."
    So the headline matrices here EXCLUDE trials flagged in ArtifactSelection.
    The all-trials version is printed alongside, never instead.
  * kappa is the competition's ranking metric, so it is reported beside
    accuracy.

Run:  C:\\Python313\\python.exe s07_confusion.py
"""

import csv
import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import (balanced_accuracy_score, cohen_kappa_score,
                             confusion_matrix)

import s04_gelo_transfer as S4
from gelo_svm_pipeline import build_model, epoch_covariances, euclidean_align

warnings.filterwarnings("ignore")

RES = os.path.join(S4.HERE, "results")
FIG = os.path.join(RES, "figures")
DATA = os.path.join(S4.HERE, "data")
SUBJECTS = [f"B{i:02d}" for i in range(1, 10)]
MODEL = "csp_svm"          # the model gelo_svm_pipeline.py ships with
CLASSES = ["LEFT", "RIGHT"]


def load(channels):
    """channels=(0,1,2) for C3,Cz,C4 or (0,2) for C3,C4 only."""
    out = {}
    for i, s in enumerate(SUBJECTS, 1):
        p = os.path.join(DATA, f"sub-{s}.npz")
        if not os.path.exists(p):
            continue
        d = np.load(p)
        out[s] = dict(cov=epoch_covariances(d["X"][:, list(channels), :]),
                      y=d["y"], sess=d["sess"], art=d["art"])
    return out


def predictions(subs, protocol):
    """Return (y_true, y_pred, art, subject) pooled over all held-out folds."""
    yt, yp, ar, sb = [], [], [], []
    for held in subs:
        np.random.seed(S4.SEED)
        pipe, grid = build_model(MODEL)
        ca = {s: euclidean_align(subs[s]["cov"], subs[s]["sess"]) for s in subs}

        if protocol == "P1":
            m = subs[held]["sess"] <= 3
            Xtr, ytr = ca[held][m], subs[held]["y"][m]
            te = ~m
        else:
            Xtr = np.concatenate([ca[s] for s in subs if s != held])
            ytr = np.concatenate([subs[s]["y"] for s in subs if s != held])
            te = np.ones(len(subs[held]["y"]), bool)

        if grid:   # fix C at the value chosen by the full pipeline's inner CV
            pipe.set_params(clf__C=0.1)
        mdl = pipe.fit(Xtr, ytr)
        pred = mdl.predict(ca[held][te])
        yt.append(subs[held]["y"][te])
        yp.append(pred)
        ar.append(subs[held]["art"][te])
        sb.append(np.full(int(te.sum()), held))
    return (np.concatenate(yt), np.concatenate(yp), np.concatenate(ar),
            np.concatenate(sb))


def panel(ax, cm, title, sub):
    pct = cm / cm.sum(axis=1, keepdims=True) * 100
    im = ax.imshow(pct, cmap="Blues", vmin=0, vmax=100)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j]}\n{pct[i, j]:.1f}%", ha="center",
                    va="center", fontsize=11,
                    color="white" if pct[i, j] > 55 else "#15202b",
                    fontweight="bold" if i == j else "normal")
    ax.set_xticks([0, 1]); ax.set_xticklabels(CLASSES)
    ax.set_yticks([0, 1]); ax.set_yticklabels(CLASSES)
    ax.set_xlabel("predicted"); ax.set_ylabel("true")
    ax.set_title(title, fontsize=10.5, pad=8)
    ax.text(0.5, -0.34, sub, transform=ax.transAxes, ha="center", fontsize=8.6,
            color="#555555")
    return im


def main():
    os.makedirs(FIG, exist_ok=True)
    rows = []
    cms = {}

    for chname, chans in (("3ch (C3,Cz,C4)", (0, 1, 2)),
                          ("2ch (C3,C4)", (0, 2))):
        subs = load(chans)
        for proto, plabel in (("P1", "within-subject"),
                              ("P2", "cross-subject")):
            yt, yp, ar, sb = predictions(subs, proto)
            for mode, keep in (("artefact-free", ar == 0),
                               ("all trials", np.ones(len(ar), bool))):
                t, p = yt[keep], yp[keep]
                cm = confusion_matrix(t, p, labels=[0, 1])
                rec = dict(channels=chname, protocol=proto, trials=mode,
                           n=int(keep.sum()),
                           acc=round(float((t == p).mean()), 4),
                           bal=round(balanced_accuracy_score(t, p), 4),
                           kappa=round(cohen_kappa_score(t, p), 4),
                           TL_L=int(cm[0, 0]), TL_R=int(cm[0, 1]),
                           TR_L=int(cm[1, 0]), TR_R=int(cm[1, 1]),
                           sens_left=round(cm[0, 0] / cm[0].sum(), 4),
                           sens_right=round(cm[1, 1] / cm[1].sum(), 4))
                rows.append(rec)
                if mode == "artefact-free":
                    cms[(chname, proto)] = (cm, rec)
                print(f"  {chname:<16}{proto}  {mode:<14} n={rec['n']:<5} "
                      f"acc={rec['acc']:.4f} bal={rec['bal']:.4f} "
                      f"kappa={rec['kappa']:.4f}")

    with open(os.path.join(RES, "confusion_2b.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- figure: 2x2 grid ------------------------------------------------- #
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 9))
    order = [("3ch (C3,Cz,C4)", "P1"), ("3ch (C3,Cz,C4)", "P2"),
             ("2ch (C3,C4)", "P1"), ("2ch (C3,C4)", "P2")]
    titles = ["3 channels - within-subject\n(train sessions 1-3, test 4-5)",
              "3 channels - cross-subject\n(train 8 subjects, test the 9th)",
              "2 channels C3+C4 - within-subject\n(our headset's montage)",
              "2 channels C3+C4 - cross-subject\n(our headset, a new person)"]
    for ax, key, ttl in zip(axes.ravel(), order, titles):
        cm, rec = cms[key]
        panel(ax, cm, ttl,
              f"acc {rec['acc']:.3f}   balanced {rec['bal']:.3f}   "
              f"kappa {rec['kappa']:.3f}")
    fig.suptitle(f"SVM ({MODEL}, Euclidean Alignment) trained and tested on "
                 f"BCI IV 2b\nartefact-free trials, pooled over all 9 subjects",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0.01, 1, 0.95])
    fig.subplots_adjust(hspace=0.42)
    fig.savefig(os.path.join(FIG, "fig5_confusion_2b.png"), dpi=150)
    plt.close(fig)
    print(f"\nWrote results\\confusion_2b.csv and "
          f"figures\\fig5_confusion_2b.png")


if __name__ == "__main__":
    main()
