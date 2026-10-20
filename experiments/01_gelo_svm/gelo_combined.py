r"""
Combine left and right iterations in random order and evaluate the SVMs on the mix.

Writes gelo_bci\output\combined_shuffled.xlsx: all 74 iterations (left + right) in a random order,
with a 'label' column (left/right), sheet 'data' + sheet 'order'.

Validation on the combined data:
  random_windows   : plain shuffled stratified 10-fold over 2 s windows (what "mix randomly"
                     gives). Overlapping windows of the same iteration end up in both train
                     and test, so this leaks and is optimistic.
  random_iterations: shuffled 10-fold over whole iterations (no leakage between windows).
"""
import os

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, StratifiedKFold

from gelo_svm import CH, DIR, GRID, INPUT, MODELS, SEED, build

MODELS_USED = ["svm_c3c4", "svm_bandpower", "svm_tangent"]


def combine():
    parts = [pd.read_excel(os.path.join(DIR, f"{c}.xlsx"), sheet_name="data") for c in ("left", "right")]
    d = pd.concat(parts, ignore_index=True)
    order = np.random.default_rng(SEED).permutation(d["iteration"].unique())
    d = pd.concat([d[d["iteration"] == it] for it in order], ignore_index=True)
    meta = (d.groupby("iteration", sort=False)
            .agg(label=("label", "first"), file=("file", "first"), samples=("sample", "size"))
            .reset_index())
    meta.insert(0, "position", range(1, len(meta) + 1))
    with pd.ExcelWriter(os.path.join(DIR, "combined_shuffled.xlsx"), engine="xlsxwriter") as xw:
        d.to_excel(xw, sheet_name="data", index=False)
        meta.to_excel(xw, sheet_name="order", index=False)
    return d, meta


def cv_score(name, X, y, g, outer, groups):
    pred = np.empty_like(y)
    for tr, te in outer.split(X, y, groups):
        inner = (StratifiedGroupKFold(3, shuffle=True, random_state=SEED) if groups is not None
                 else StratifiedKFold(3, shuffle=True, random_state=SEED))
        gs = GridSearchCV(MODELS[name](), GRID, cv=inner, scoring="balanced_accuracy", n_jobs=-1)
        gs.fit(X[tr], y[tr], groups=None if groups is None else groups[tr])
        pred[te] = gs.predict(X[te])
    win = balanced_accuracy_score(y, pred)
    it = pd.DataFrame({"g": g, "y": y, "p": pred}).groupby("g").agg(y=("y", "first"), p=("p", "mean"))
    return 100 * win, 100 * balanced_accuracy_score(it["y"], (it["p"] > 0.5).astype(int))


if __name__ == "__main__":
    d, meta = combine()
    print("first 15 iterations in the shuffled file:", " ".join(meta["iteration"].head(15)))
    blocks = [(int(p["label"].iat[0] == "right"), it, p["file"].iat[0], p[CH].to_numpy().T)
              for it, p in d.groupby("iteration", sort=False)]
    Xb, Xm, y, g, f = build(blocks)
    rows = []
    for name in MODELS_USED:
        X = (Xb, Xm)[INPUT[name]]
        for scheme, outer, groups in (
                ("random_windows", StratifiedKFold(10, shuffle=True, random_state=SEED), None),
                ("random_iterations", StratifiedGroupKFold(10, shuffle=True, random_state=SEED), g)):
            w, i = cv_score(name, X, y, g, outer, groups)
            rows.append({"model": name, "validation": scheme, "window_bal_acc": w, "iteration_bal_acc": i})
            print(f"{scheme:18} {name:14} window {w:5.1f} %   iteration {i:5.1f} %", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(DIR, "combined_results.csv"), index=False, float_format="%.2f")
