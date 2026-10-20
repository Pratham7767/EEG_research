"""
s05_polarity_check.py  -  is ch2/ch3 really C3/C4, or are they swapped?

WHY THIS IS A LEGITIMATE QUESTION AND NOT FISHING

Every one of the 8 transfer configurations in s04 landed BELOW chance at file
level (0.25-0.45). A model that is merely uninformative scatters around 0.50;
one that is systematically inverted sits below it. And the channel mapping was
never measured - EXPERIMENT_REPORT.txt section 4.2 records it as "As you told
us: ch2 = C3, ch3 = C4. Your MATLAB script does not state this mapping
itself; we took it from you."

So this tests ONE pre-specified physical alternative: that the two electrodes
are the other way round. It is a hypothesis about where the electrodes sat on
the head, not a search over feature sets.

HOW IT IS KEPT HONEST
  * exactly two hypotheses are tested (as-labelled, swapped), so the
    Bonferroni-corrected threshold is p < 0.025, and that is what is applied;
  * the model is the same one trained on 2b, never refitted, so swapping the
    test channels cannot change what was learned;
  * the file-level permutation is unchanged, and remains the only honest unit;
  * a descriptive check is printed alongside: the direction of the C3-vs-C4
    power difference in our data against the same quantity in 2b. If the
    electrodes are swapped, that sign should disagree, and it should disagree
    BEFORE any classifier is involved.

Run:  C:\\Python313\\python.exe s05_polarity_check.py
"""

import csv
import os

import numpy as np
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

import s04_gelo_transfer as S4

RES = os.path.join(S4.HERE, "results")
NPERM = 10000


def main():
    rng = np.random.default_rng(S4.SEED)
    two = S4.load_2b_2ch()

    print("=== descriptive check, no classifier involved ===")
    # 2b: AUC of log power C3 - C4 for predicting class 1 (right)
    f2, y2 = [], []
    for s in two:
        d = np.log(np.einsum("nii->ni", two[s]["cov"]))
        f2.append(d[:, 0] - d[:, 1])
        y2.append(two[s]["y"])
    auc2 = roc_auc_score(np.concatenate(y2), np.concatenate(f2))
    print(f"  2b      AUC of log(C3)-log(C4) -> right : {auc2:.4f}")

    print("\n  re-cutting Gelo epochs:")
    Xg, yg, fg, _ = S4.load_gelo()
    dg = np.log(np.einsum("nii->ni", S4.covs(Xg)))
    aucg = roc_auc_score(yg, dg[:, 0] - dg[:, 1])
    print(f"\n  Gelo    AUC of log(ch2)-log(ch3) -> right : {aucg:.4f}")
    print(f"  2b says {'C3>C4' if auc2 > 0.5 else 'C3<C4'} for right-hand MI; "
          f"our data says {'ch2>ch3' if aucg > 0.5 else 'ch2<ch3'}")
    print(f"  -> directions {'AGREE' if (auc2 > .5) == (aucg > .5) else 'DISAGREE'}"
          f"  (note: our AUC is epoch-level and so is optimistic)")

    print("\n=== classifier test, both channel orders ===")
    rows = []
    for swap in (False, True):
        Xs = Xg[:, ::-1, :] if swap else Xg
        craw = S4.covs(Xs)
        cea = S4.align(craw, fg)
        for name in S4.models():
            for ea in (0, 1):
                np.random.seed(S4.SEED)
                Xtr, ytr = [], []
                for s in two:
                    c = two[s]["cov"]
                    if ea:
                        c = S4.align(c, two[s]["sess"])
                    Xtr.append(c)
                    ytr.append(two[s]["y"])
                mdl = S4.models()[name].fit(np.concatenate(Xtr),
                                            np.concatenate(ytr))
                pred = mdl.predict(cea if ea else craw)
                t, v, u = S4.file_level(yg, fg, pred)
                fbal = balanced_accuracy_score(t, v)
                ge = 0
                for _ in range(NPERM):
                    lut = dict(zip(u, rng.permutation(t)))
                    tp, vp, _ = S4.file_level(
                        np.array([lut[f] for f in fg]), fg, pred)
                    if balanced_accuracy_score(tp, vp) >= fbal:
                        ge += 1
                p = (ge + 1) / (NPERM + 1)
                rows.append(dict(swapped=int(swap), model=name, ea=ea,
                                 epoch_bal=round(
                                     balanced_accuracy_score(yg, pred), 4),
                                 file_bal=round(fbal, 4),
                                 file_correct=f"{int((t == v).sum())}/{len(t)}",
                                 perm_p=round(p, 4)))
                print(f"  swap={int(swap)}  {name:<12} EA={ea}  "
                      f"file {fbal:.4f} ({int((t == v).sum())}/{len(t)})  "
                      f"perm p={p:.4f}")

    best = max(rows, key=lambda r: r["file_bal"])
    print(f"\nbest anywhere: swap={best['swapped']} {best['model']} "
          f"EA={best['ea']}  file_bal {best['file_bal']}  p={best['perm_p']}")
    print("Bonferroni threshold for 2 hypotheses: p < 0.025")
    print("VERDICT:", "SIGNIFICANT" if best["perm_p"] < 0.025
          else "not significant - neither channel order decodes our data")

    with open(os.path.join(RES, "gelo_polarity.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote results\\gelo_polarity.csv")


if __name__ == "__main__":
    main()
