# trainsvm: left vs right hand motor-imagery decoding for a low-channel EEG headset

Goal: decode **imagined left-hand vs right-hand movement** from EEG, with the end target of our own
2-to-4-channel headset (Gelo BCI headband / Neiry–Capsule headphones). The project has gone
through public stroke data → our own recordings → the BCI Competition IV 2b benchmark.

**Start here:** [PROJECT_HISTORY.md](PROJECT_HISTORY.md), the full story from the first day,
with every result in one place. The most complete write-up is
[experiments/05_bci_iv_2b/STUDY.pdf](experiments/05_bci_iv_2b/STUDY.pdf).

Repository restructured on 2026-10-20. Every move is listed in
`archive/restructure_moves_2026-10-20.csv` and every hard-coded `D:\trainsvm\...` path in the
scripts was updated to match.

---

## Folder structure

```
D:\trainsvm
├── README.md                     ← this file
├── PROJECT_HISTORY.md            ← timeline + key results of every stage
├── .gitignore                    ← keeps raw data, archives and binaries out of git
│
├── data/                         RAW DATA (never modified by any script)
│   ├── gelo/                     our own Gelo BCI headband recordings, 250 Hz, ch2 = C3, ch3 = C4
│   │   ├── left/                 5 CSV files, left-hand MI only  (Left1_5.csv … left21_25.csv)
│   │   └── right/                10 CSV files, right-hand MI only (Right1_5.csv … right46_50.csv)
│   └── stroke_liu2024/           Liu et al. 2024 acute-stroke MI dataset (BIDS), 50 patients, 500 Hz, ~9 GB
│       ├── sourcedata/           per-subject .mat (40 trials × 33 ch × 4000 samples)
│       ├── edffile/, csv/        EDF and per-subject CSV exports
│       ├── code/code/            the AUTHORS' MATLAB code (CSP, FBCSP_SVM, TWFB_DGFMDM, …)
│       ├── ERD_ERS/              our reproduction of the paper's ERD/ERS figure (Fig. 4)
│       └── own_data/             authors' pipeline applied to our Gelo data
│
├── experiments/                  ONE FOLDER PER STAGE, numbered in the order they were done
│   ├── 01_gelo_svm/              Sep 18  SVMs on our Gelo recordings (+ permutation test)
│   ├── 02_stroke_paper_repro/    Sep 18  reproducing Liu et al. 2024; 9 models, honest CV
│   ├── 03_gelo_erd/              Sep 27  ERD/ERS on Gelo data with the paper's recipe
│   ├── 04_svm_stroke_to_gelo/    Sep 28  3 feature-SVMs trained on stroke data, tested on Gelo
│   └── 05_bci_iv_2b/             Oct 8–20  BCI Competition IV 2b (2008 Graz data set B)
│       ├── 00_PLAN.md, REPORT.md, STUDY.md/.pdf, HOW_TO_RUN.md
│       ├── s00…s07_*.py          Python pipeline: fetch → models (EA) → report → Gelo transfer → calibration
│       ├── gelo_svm_pipeline.py  standalone decoder (train on 2b, predict Gelo CSVs)
│       ├── RUN_ERD_PSD_2b.m      ERD/ERS + PSD analysis (MATLAB) → erd_ers/
│       ├── classifier/           Oct 20  FBCSP competition-winner replication + improved models (MATLAB)
│       ├── data/                 18 BNCI .mat files (B01T…B09E) + cached covariances sub-B0x.npz
│       ├── subjectwise/          Oct 20  per-subject Left/Right × Training/Evaluation (.mat + .csv)
│       └── results/              CSVs, logs, figures
│
├── apps/
│   └── cognitive_score/          Sep 30–Oct 1  desktop focus/fatigue monitor for the Capsule headphones (Python, tested)
│
├── hardware/
│   └── eeg_headphones/           device SDKs (Capsule 2.0.59, pyneurosdk2, BrainBit), Bluetooth driver,
│                                 EEG_Recorder and SpeechEEG_Recorder apps (Apr 2026)
│
├── third_party/
│   └── covariancetoolbox/        Riemannian geometry toolbox for MATLAB (Barachant), own git repo
│
├── reports/
│   ├── EXPERIMENT_REPORT_2026-09-19.txt/.pdf   plain-English report on stages 01–02
│   └── make_report_pdf.py
│
└── archive/                      old zips, the pre-restructure README, the move log
```

## Where to find things

| I want… | Go to |
|---|---|
| The whole story and every headline number | `PROJECT_HISTORY.md` |
| The best write-up (methods, results, literature, recommendations) | `experiments/05_bci_iv_2b/STUDY.pdf` |
| Our own recordings | `data/gelo/left`, `data/gelo/right` |
| BCI IV 2b raw data | `experiments/05_bci_iv_2b/data/B0xT.mat`, `B0xE.mat` |
| 2b split per subject into Left/Right × Training/Evaluation | `experiments/05_bci_iv_2b/subjectwise/` |
| Competition-style classifier and kappa table | `experiments/05_bci_iv_2b/classifier/run_bci2b.m`, `results_kappa_max.csv` |
| A decoder you can point at a new Gelo CSV | `experiments/05_bci_iv_2b/gelo_svm_pipeline.py` |
| The focus/fatigue app | `apps/cognitive_score/README.md` |

## How to run

* **Python:** use `C:\Python313\python.exe` (numpy, scipy, scikit-learn, pyriemann, matplotlib,
  reportlab installed). The bare `python` on PATH is 3.8 with nothing installed.
* **MATLAB:** R2025a with Signal Processing + Statistics and ML toolboxes.
* Each experiment folder has its own `HOW_TO_RUN.md` or README. The scripts are numbered
  `s01, s02, …` and run in that order.

## Notes

* Scripts use absolute paths under `D:\trainsvm\`. If the repo moves, search for `D:\trainsvm`.
* `.git` exists but has **no commits yet**, and `.git/objects` holds ~1.1 GB from an earlier
  `git add` of the data. See `PROJECT_HISTORY.md` → "Repository housekeeping".
