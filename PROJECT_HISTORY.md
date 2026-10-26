# PROJECT HISTORY: from the first recording to today

Compiled 2026-10-20 from the reports, plans and logs inside this repo (the chats themselves
are not readable from here, so this is reconstructed from what each stage wrote down).
Folder names are the **new** ones; old names are in brackets.

---

## The question

Can we tell **imagined left-hand vs right-hand movement** apart from EEG, using a cheap
headset with only a couple of electrodes over the motor cortex (C3 and C4)?

The textbook signal is **ERD (event-related desynchronisation)**. Imagining a hand movement
weakens the 8–30 Hz mu/beta rhythm over the *opposite* hemisphere:
left hand → power drops at C4; right hand → power drops at C3.

---

## Timeline

### Apr 2026: hardware and recording tools  →  `hardware/eeg_headphones/`
* Got the Neiry/Capsule EEG headphones and the Gelo BCI headband working: SDKs
  (Capsule 2.0.59, pyneurosdk2, BrainBit), the USB-BT500 Bluetooth driver.
* Built two desktop recorders: **EEG_Recorder** (Apr 5) and **SpeechEEG_Recorder**
  (Apr 10–14, imagined/overt speech sessions with audio).

### Sep 8–12: our own MI recordings  →  `data/gelo/left`, `data/gelo/right`
* 15 CSV files from the Gelo headband, 250 Hz. ch2 = C3, ch3 = C4 (ch1/ch4 unconfirmed).
* 5 iterations per file, marks 1–5 = trials, 6/7 = eyes-open/closed baseline.
* **Design flaw found later:** every file contains only one class (all-left or all-right),
  onsets were a manual mouse click, and trial lengths ranged from 4.9 s to 148 s.

### Sep 18: first SVMs on Gelo data  →  `experiments/01_gelo_svm/` [gelo_bci]
* Extracted iterations to Excel, trained 3 SVMs × 3 validation schemes, plus a file-level
  permutation test.
* Result: **78–98 % with random splits (leaky)**, but only **57–65 % when testing on an unseen
  recording**, and even 65 % was not significant (p = 0.089). The model was recognising the
  *session*, not the hand, because class = file.

### Sep 18: reproducing the stroke paper  →  `experiments/02_stroke_paper_repro/` [stroke_paper]
* Liu et al. 2024, *Scientific Data*: 50 acute-stroke patients, 30 channels, 500 Hz,
  paper claims up to **72.21 %**.
* Ported the authors' FBCSP_SVM.m and ran 9 models under honest stratified 10-fold CV.
* Result: best honest **55.4 %** (TWFB + FgMDM), CSP + LDA 50.5 %. The 72 % is not
  reproducible: the authors' TWFB_DGFMDM.m **picks its frequency band by test accuracy**,
  and the same procedure scores 63.8 % even on **shuffled labels**.
* Written up in plain English: `reports/EXPERIMENT_REPORT_2026-09-19.txt/.pdf`.

### Sep 25: stroke-data ERD/ERS  →  `data/stroke_liu2024/ERD_ERS/`
* Reproduced the paper's ERD/ERS figure (Fig. 4) with the authors' own code, with and without
  smoothing and with C3/C4 swapped, to check what the published figure actually shows.

### Sep 27: ERD on our Gelo data  →  `experiments/03_gelo_erd/` [erd]
* Applied the paper's ERD recipe to our 72 Gelo epochs (MATLAB `gelo_erd.m` + Python).
* Grand averages looked mildly in the right direction, but did not hold up statistically.
  Diagnosed causes: the **mouse click at t = 0** (a real hand movement at the onset),
  one class per file, and variable trial lengths.
* `epochs_paper_format.mat` = our data cut into the paper's format, used by the next stage.
* Sep 30: `plot_representative_trials.m` / `_v2.m` show single example trials.

### Sep 28: three SVMs, stroke → Gelo  →  `experiments/04_svm_stroke_to_gelo/` [Experiment_svm]
* SVM-A (mean/median/skew/kurtosis of 8–30 Hz energy at C3/C4), SVM-B (+ C3/C4 PSD ratio),
  SVM-C (ratio only). Trained on the stroke data, tested on our 72 Gelo epochs.
* Result: **all at chance**. Best 0.531 leave-one-subject-out, 0.534 on our data, best
  permutation p = 0.385. Round 2 (per-subject fitting): SVM-A 0.5385, p = 0.008 uncorrected,
  does **not** survive FDR correction. Slide material in `BEST_MODEL.md`, `SLIDE_CONTENT.md`.
* Lesson: the stroke data's ceiling, not the classifier, was the limit.

### Sep 30–Oct 1: Cognitive Score app  →  `apps/cognitive_score/`
* A separate deliverable: a desktop focus/fatigue session monitor for the Capsule headphones.
  Guided setup → impedance check → eyes-closed alpha calibration → baseline → live attention,
  cognitive load, stress and fatigue scores with break suggestions. Simulator mode, test suite,
  user manual and "how it works" PDFs in `docs/`.

### Oct 8: switch to BCI Competition IV 2b  →  `experiments/05_bci_iv_2b/` [EXPERIMENT_2]
* **Public dataset, downloaded by `s01_fetch_2b.py` (not recorded by us):** Graz 2008 data set B,
  9 healthy subjects, 5 sessions each, C3/Cz/C4 bipolar, 250 Hz. Chosen because it matches
  our headset's rate and montage and has properly interleaved classes.
* Plan written first with predicted ranges (`00_PLAN.md`). The first run gave chance everywhere,
  and the prediction made it obvious it was a bug: the `trial` field marks the trial start and
  **the cue is 3 s later**. Fixed with `CUE_OFFSET = 3.0` (diagnosed by `s00_diagnose_window.py`).
* 7 models × Euclidean Alignment (EA) off/on × 2 protocols:
  * **P1 within-subject** (train sessions 1–3, test 4–5): best **0.802** (FBCSP-SVM + EA)
  * **P2 cross-subject** (new person never seen): best **0.747**, 9/9 subjects above chance
  * EA helped in 28/28 configurations (+0.045 on average). The choice of model was worth only
    ~0.003. Dropping Cz (3 → 2 channels) cost ~0.003.
* **Gelo transfer** (`s04`, `s05`): the same validated decoder scores **chance on our recordings**
  (best file-level p = 0.83); swapping ch2/ch3 doesn't help. This isolates the problem to our
  **recording protocol / placement**, not the classifier or channel count.
* **Calibration curve** (`s06`): with EA, 320 of the user's own trials add < 0.01, so a
  zero-calibration decoder is viable. The public data is worth ~160 user trials.
* Full write-up: `STUDY.md` / `STUDY.pdf` (methods, results, literature review, recommendations).

### Oct 16: ERD/ERS and PSD on 2b  →  `experiments/05_bci_iv_2b/erd_ers/`
* One MATLAB script, `RUN_ERD_PSD_2b.m`. Textbook contralateral ERD: left MI C4 −29.8 %,
  right MI C3 −34.3 %. Correct in 16/18 subject × class cells; the exceptions are B02/B03,
  the same subjects every classifier struggles with. An earlier two-script version had a
  reporting bug and was replaced.

### Oct 20 (today): subject-wise data + competition-winner replication
* Confirmed the "BCI 2008" folder **is** BCI Competition IV 2b, checked against the official
  description and checksums.
* `subjectwise/`: every subject split into **Training / Evaluation × Left / Right**
  (0–8 s trials, C3/Cz/C4, artifact flag kept), as `.mat` and `.csv`.
* `classifier/run_bci2b.m`: re-implemented the **competition winner, FBCSP** (Ang et al. 2012:
  9 Chebyshev-II bands, CSP m = 1, MIBIF feature selection, Naive Bayes Parzen classifier) and
  scored it the official way (causal sliding window, max kappa over time, artifact-free trials):
  * our replication **κ = 0.583** vs published 0.585 (MIBIF) / 0.600 (winner)
  * FBCSP + shrinkage LDA, window + sessions chosen by CV on training data only:
    **κ = 0.601 (~80 % accuracy)**, on par with the winner
  * Note: the winner used **Naive Bayes**, not an SVM. An SVM variant is a natural next test.
* `erd_svm/`: **SVM on ERD% values** (C3/Cz/C4 x mu/beta = 6 features), with power averaged
  over N trials of the same hand before computing ERD%:
  * same person (train sessions 1-3, test 4-5): single trial 66 %, 10-trial average **81 %**
  * new person (leave-one-subject-out): single trial 62 %, 10-trial average **74 %**, with a
    confusion matrix in `confusion_loso.png`
  * Caveat: one decision per 10 same-hand trials, so this is a block-level decision, not
    real-time single-trial control.

### Oct 25: real-time BCI app  →  `apps/mi_bci/`
* Researched how Graz ran the 2b sessions live (Leeb et al. 2007 + Scherer et al., same lab): 1 s log
  band power + LDA every sample, smiley moved by the sign of the output integrated over 2 s, classifier
  retrained between sessions only if ≥ 5 % better. Plan written as a doc ("Real-time Left/Right BCI: How
  Graz Did It and How We Build It").
* Built the whole loop as a desktop app: Connect (scan, impedance, 10 s signal test) → Record (baseline,
  movement check, screening) → Check & Train (alpha check, ERD check, nested run-wise training +
  permutation test) → Feedback (smiley, 25 Hz) → Retrain (Graz ≥ 5-point rule). Works with the
  headphones (pyneurosdk2), a simulator, or replayed recordings.
* Verified: 15/15 tests (incl. a leak check: no signal → chance), app self-test through the real window
  (signal test, all run types, training, feedback; every drawn frame checked against the state), and
  BCI IV 2b streamed through the live engine with random packet sizes: outputs identical to offline.
  Trained on the 2 screening sessions only (as Graz did), then run live on the 3 feedback sessions with
  no retraining: **mean live accuracy 73 % (S3), 72 % (S4), 73 % (S5); integrated error 33 %** (Graz
  reported ~28–30 % for their cue-based feedback sessions). Best B04 94–98 %, weakest B02/B03 at 51–56 %,
  the same subjects every method struggles with. Details: `apps/mi_bci/_out/replay_2b/summary.json`.
* Not verified (needs the headset on a person): see Open problems below.

### Oct 26: first real session, P01  →  `data/mi_bci/P01/`
* Headset works: signal test 9–18 µV (C3-A1, C4-A2), 250 Hz, eyes-closed alpha ×2.6–4.2 at 11.5 Hz.
* Recorded 1 baseline, 1 movement run, 1 screening run (10 + 10 trials each), 1 feedback run.
* ERD check rewritten (separate per run type; classic trial-averaged ERD; log-ratio permutation test). With it,
  **real hand movement shows the expected opposite-side mu change** (p = 0.041, only 10 trials per hand):
  right hand C3 −15 % / C4 +25 %, left hand C3 +23 % / C4 −1 %. Imagery (1 run) shows nothing yet.
* Feedback was run with an unvalidated model (1 run only) → 50 %, as expected. The app now shows a
  score + verdict after training and warns before feedback when the model is not READY.
* 2b as a base model (`tools/base_model_check.py`): 2b only 45 %, 2b + P01 45 %, P01 only 41 % on 80
  trials, all at chance. Not enough P01 imagery data yet to tell whether the base helps.
* Mains hum rose from 13x to 80–330x the background during task runs (charger / hands near laptop);
  the app now warns after each run. Beep was inaudible: the headphones are also a Windows audio device
  ("Headphones (USAMS-YX05)") and Windows' default output, so beeps went over Bluetooth and were sometimes
  lost. Now `mibci/sound.py` keeps one audio stream open on the laptop speakers (chosen automatically,
  selectable on tab 1, never the headset by default); 300 ms tones; `tools/check_sound.py` = 5/5 played.
* **The app now uses our SVM** (CSP + SVM + Euclidean Alignment, as `gelo_svm_pipeline.py`), rebuilt to
  run live (2 s covariance every 40 ms). Base = all 9 2b subjects (`apps/mi_bci/models/base_2b_svm.json`);
  Train = refit on 2b + the subject's runs, choosing 2b only / 2b + yours / yours only by leave-one-run-out.
  Checked on 2b, each subject as a new user (base from the other 8, improved with their screening
  sessions, then streamed live on their 3 feedback sessions): **base only 75.9 %, improved 76.0 %**
  (Graz LDA trained on own screening: 72–73 %); live engine = offline in every subject.
  P01 so far (2 cued runs): 50 %, NOT READY, too little imagery data.

---

## What we know now

1. **The dataset sets the ceiling, not the model.** Stroke data: 0.55. 2b: 0.75–0.80. Swapping
   classifiers on the same data moves results by less than 0.01.
2. **Two channels are enough.** C3 + C4 alone keep ~0.744 cross-subject on 2b.
3. **Euclidean Alignment is the most useful single trick:** label-free, always positive, and it
   removes the need for long user calibration.
4. **Our recordings are the blocker.** One class per file + a click at onset + variable trials
   means class is confounded with session. Nothing measured on them is interpretable yet.

## Recommended next steps (from STUDY.pdf §4, still open)

1. **Re-record** with left/right interleaved in one session, software-timed cues, fixed 4 s
   trials, hands still, equal counts, several sessions, and note the electrode positions.
2. Run `experiments/05_bci_iv_2b/s04_gelo_transfer.py` on the new recordings (unchanged code).
3. Add online feedback and co-adaptive calibration.
4. Confirm what ch1/ch4 are on the headband.

---

## Open problems with the real-time app (updated 2026-10-26)

Solved since 2026-10-25: the app has run on the headset (P01: connect, 250 Hz stream, signal test 9–18 µV,
so the volts assumption holds); beeps; the ERD check; the score/verdict before feedback; per-subject model.

1. **Imagery on our headset is not shown yet.** P01 has 1 imagery run (10 trials per hand). Real movement
   already shows the expected opposite-side mu change (p = 0.041). Needs 4–6 imagery runs.
2. **Does the 2b base SVM help on our montage?** On 2b itself the base gives 75.9 % on new people; on P01
   everything is at chance so far. `tools/base_model_check.py` / the Train report answer it once there is data.
3. **Mains hum** rose 6–25× during P01's task runs (charger / hands near the laptop). The app warns.
4. **Montage** (C3−A1, C4−A2) is untested against alternatives on real data. Switch in `config.py`.
5. **Bluetooth delay is not measured.** Markers may be early by tens of ms. Small next to 2 s windows.
6. **PackNum = samples is an assumption.** P01 had 8 NaN-filled samples per run, so drops are rare.
7. The 2026-04-14 raw recording is bad contact (13 % pinned) and should not be used.

## Repository housekeeping (2026-10-20)

* Restructured into `data/ experiments/ apps/ hardware/ third_party/ reports/ archive/`. The move
  log is `archive/restructure_moves_2026-10-20.csv`.
* All hard-coded `D:\trainsvm\...` paths in `.m` / `.py` files were rewritten to the new layout.
  Two scripts in `experiments/03_gelo_erd/` that pointed at temporary sandbox paths now use
  their own folder.
* **`D:\trainsvm\EXPERIMENT_2\` is a leftover duplicate.** It was fully copied to
  `experiments/05_bci_iv_2b/` (every file verified identical, .mat checksums OK), but Windows
  kept it locked during the move. Delete it once nothing has it open.
* Git: the repo has no commits, and `.git/objects` holds ~1.1 GB from an earlier add of the raw
  data. A `.gitignore` now excludes data, archives and binaries. To start clean:
  `git gc --prune=now`, then `git add .` and commit.
