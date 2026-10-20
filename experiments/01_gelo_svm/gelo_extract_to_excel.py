r"""
Extract the marked motor-imagery iterations from the Gelo BCI headband recordings into Excel.

Input : D:\trainsvm\data\gelo\left\*.csv, D:\trainsvm\data\gelo\right\*.csv
        columns timestamp (us, 4000 us step -> 250 Hz), ch1..ch8, mark
        ch5..ch8 are unused placeholders (constant 1.18e-38) -> dropped.
        mark 1..5 = the five iterations in a file; 0, 6, 7 are ignored for the task
        (6 and 7 are ~30 s blocks before the task; kept separately as 'baseline' for a
        confound check in gelo_svm.py).
Output: D:\trainsvm\experiments\01_gelo_svm\output\left.xlsx, D:\trainsvm\experiments\01_gelo_svm\output\right.xlsx
        sheet 'data'       one row per sample of every iteration (ch1..ch4 in microvolts, raw)
        sheet 'iterations' one row per iteration: file, number, length, anomalies
        D:\trainsvm\experiments\01_gelo_svm\output\baseline.csv  the mark-6/7 blocks (not in Excel, used only as a control)
"""
import glob
import os
import re

import numpy as np
import pandas as pd

BASE = r"D:\trainsvm\data\gelo"
OUT = r"D:\trainsvm\experiments\01_gelo_svm\output"
FS = 250
CH = ["ch1", "ch2", "ch3", "ch4"]


def file_start(path):
    """Left6_10.csv -> 6: the iteration number of mark 1 in this file."""
    return int(re.search(r"(\d+)_(\d+)", os.path.basename(path)).group(1))


def extract(cls):
    rows, info, base = [], [], []
    for path in sorted(glob.glob(os.path.join(BASE, cls, "*.csv")), key=file_start):
        d = pd.read_csv(path)
        x = d[CH].to_numpy() * 1e6                      # volts -> microvolts
        m = d["mark"].to_numpy().astype(int)
        fname = os.path.basename(path)
        for mark in range(1, 6):
            idx = np.flatnonzero(m == mark)
            if idx.size == 0:
                info.append({"file": fname, "mark": mark, "iteration": file_start(path) + mark - 1,
                             "samples": 0, "seconds": 0.0, "note": "MISSING in file"})
                continue
            it = file_start(path) + mark - 1
            n_runs = 1 + int((np.diff(idx) > 1).sum())
            note = f"split into {n_runs} runs (merged)" if n_runs > 1 else ""
            if idx.size > 60 * FS:
                note = (note + "; " if note else "") + f"unusually long ({idx.size / FS:.0f} s)"
            info.append({"file": fname, "mark": mark, "iteration": it, "samples": idx.size,
                         "seconds": idx.size / FS, "note": note})
            rows.append(pd.DataFrame({
                "label": cls, "iteration": f"{cls}_{it:02d}", "file": fname, "mark": mark,
                "sample": np.arange(idx.size), "time_s": np.arange(idx.size) / FS,
                **{c: x[idx, i] for i, c in enumerate(CH)}}))
        for mark in (6, 7):
            idx = np.flatnonzero(m == mark)
            base.append(pd.DataFrame({"label": cls, "block": f"{fname}_m{mark}", "file": fname,
                                      **{c: x[idx, i] for i, c in enumerate(CH)}}))
    return pd.concat(rows, ignore_index=True), pd.DataFrame(info), pd.concat(base, ignore_index=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    baselines = []
    for cls in ("left", "right"):
        data, info, base = extract(cls)
        baselines.append(base)
        with pd.ExcelWriter(os.path.join(OUT, f"{cls}.xlsx"), engine="xlsxwriter") as xw:
            data.to_excel(xw, sheet_name="data", index=False)
            info.to_excel(xw, sheet_name="iterations", index=False)
        print(f"{cls}.xlsx: {data['iteration'].nunique()} iterations, {len(data)} rows")
        print(info.to_string(index=False), "\n")
    pd.concat(baselines).to_csv(os.path.join(OUT, "baseline.csv"), index=False)
