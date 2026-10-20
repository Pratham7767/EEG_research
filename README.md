# EEG_research: reading left vs right hand imagination from EEG

## What this project is about

When you **imagine** moving your left hand, the brain's right side changes its rhythm.
When you imagine your right hand, the left side changes. An EEG headset can pick this up
with electrodes called **C3** (left side of the head) and **C4** (right side).

The goal: build a program that looks at the EEG and says **"left"** or **"right"**, using a
cheap headset with only 2–4 electrodes (our Gelo headband and Neiry/Capsule headphones).

**To understand what we did and what we found, read [PROJECT_HISTORY.md](PROJECT_HISTORY.md).**
The longest, most complete report is [experiments/05_bci_iv_2b/STUDY.pdf](experiments/05_bci_iv_2b/STUDY.pdf).

---

## Main results so far

| What we tried | Accuracy | What it means |
|---|---|---|
| Public stroke-patient dataset (Liu et al. 2024) | about 55 % | Barely better than guessing (50 %). The paper's 72 % could not be repeated. |
| Our own Gelo recordings | at chance | The way we recorded was the problem: each file had only one hand. |
| Public BCI Competition IV 2b dataset, same person | about 80 % | Works well. |
| Same dataset, a new person never seen before | about 75 % | Still works, with no training on that person. |
| Copy of the 2008 competition winner (FBCSP) | κ 0.60, about 80 % | Same score as the winner. |

**Next step:** record our own data again, with left and right trials mixed in the same session.

---

## How the folders are organised

```
EEG_research/
├── README.md               ← you are here
├── PROJECT_HISTORY.md      ← the full story, step by step, with all results
│
├── data/                   ← raw EEG data (NOT on GitHub, see "Getting the data" below)
│   ├── gelo/left, right    our own headband recordings
│   └── stroke_liu2024/     public stroke-patient dataset
│
├── experiments/            ← one folder per stage, in the order we did them
│   ├── 01_gelo_svm/             first SVM tests on our own recordings
│   ├── 02_stroke_paper_repro/   trying to repeat the stroke paper's results
│   ├── 03_gelo_erd/             brain-rhythm (ERD) plots of our recordings
│   ├── 04_svm_stroke_to_gelo/   train on stroke data, test on our data
│   └── 05_bci_iv_2b/            the BCI Competition IV 2b work (best results)
│       ├── classifier/              copy of the competition winner + improvements
│       ├── data/                    the 2b data files (not on GitHub)
│       ├── subjectwise/             2b data split per person, left/right (not on GitHub)
│       └── results/                 tables and figures
│
├── apps/cognitive_score/   ← desktop app: live focus and tiredness scores from the headphones
├── hardware/eeg_headphones/← our recording apps (the device makers' SDKs are not on GitHub)
├── reports/                ← the first full report (Sept 2026)
├── third_party/            ← other people's code we use (not on GitHub)
└── archive/                ← old files kept just in case (not on GitHub)
```

## Where to find things

| I want to… | Look in |
|---|---|
| Understand the whole project | `PROJECT_HISTORY.md` |
| Read the best report | `experiments/05_bci_iv_2b/STUDY.pdf` |
| Run the best classifier | `experiments/05_bci_iv_2b/classifier/run_bci2b.m` (MATLAB) |
| Test a decoder on a new Gelo recording | `experiments/05_bci_iv_2b/gelo_svm_pipeline.py` |
| Use the focus/tiredness app | `apps/cognitive_score/README.md` |

---

## Getting the data

GitHub only holds the code and small results. All the data (about 4.2 GB) is on Google Drive:

**Google Drive link: _add link here_**

To set it up:
1. Clone this repo to `D:\trainsvm` (the scripts expect this path).
2. Download the Drive folder `EEG_research_data`.
3. Double-click `restore_into_repo.bat` inside it. It copies every file back to the right
   place. It never deletes anything.

## Running the code

* **Python:** use `C:\Python313\python.exe`. It has numpy, scipy, scikit-learn, pyriemann,
  matplotlib and reportlab. (The plain `python` command on this PC is an old version with
  nothing installed.)
* **MATLAB:** R2025a with the Signal Processing and Statistics and Machine Learning toolboxes.
* Each experiment folder has its own `HOW_TO_RUN.md` or README. Scripts are numbered
  `s01, s02, …`. Run them in that order.
* The scripts use the folder `D:\trainsvm\`. If you put the project somewhere else, search
  the scripts for `D:\trainsvm` and change it.
