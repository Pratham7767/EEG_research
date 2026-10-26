# CONTEXT FOR CLAUDE: read this first in any new chat about this project

Last updated: 2026-10-20. Owner: Pratham Srivastava (prathamsrivastava915@gmail.com), Bengaluru (IST).
GitHub: https://github.com/Pratham7767/EEG_research (branch `main`). Local repo: `D:\trainsvm`.
Data (not in git): `D:\EEG_research_data` (4.2 GB bundle for Google Drive, link not yet added).
Human-readable story: `PROJECT_HISTORY.md`. Best full report: `experiments/05_bci_iv_2b/STUDY.pdf`.

---

## 1. Goal

Decode **imagined left-hand vs right-hand movement** (motor imagery, MI) from EEG, aiming at our own
2–4 electrode headsets (Gelo BCI headband; Neiry/Capsule "LEHeadphones2"/USAMS-YX05 headphones).
Physiology used: ERD, a drop in mu (8–13 Hz) and beta (13–30 Hz) power over the hemisphere
opposite to the imagined hand (left MI → C4 drops, right MI → C3 drops).

## 2. How to work with this user

* Explain in **simple English**, short and concrete. Uses MATLAB a lot; also Python.
* Likes: tables of results, confusion matrices, per-subject breakdowns, "what feature / how was
  the data given" explanations, git commands to commit after each change.
* Sometimes uses loose wording, e.g. called BCI IV 2b "the BCI 2008 dataset that we recorded".
  **It was downloaded, not recorded by them.** Gently correct.
* Be honest about leakage and caveats; earlier work in this project values honest protocols
  (plans with predictions written before running).

## 3. Environment (Windows PC "pratham", user folder C:\Users\dellc)

* Python: **`C:\Python313\python.exe`** (numpy, scipy, sklearn 1.7.2, pyriemann 0.12, matplotlib,
  reportlab). Bare `python` = 3.8 with nothing installed.
* MATLAB **R2025a** with Signal Processing, Statistics & ML, DSP, Deep Learning, etc.
* Claude access used so far: Filesystem MCP (allowed: `D:\trainsvm`, `D:\Matlab_ECE`,
  `D:\clean_data`, `D:\Data_plotting`), MATLAB MCP (evaluate code / run file), device_bash
  (Linux VM, Python 3.10, numpy only, no scipy, no internet pip), Gmail + Google Drive connectors.
* Quirks learned:
  * MATLAB tool calls time out after ~60 s, but the job keeps running. Poll for output files.
  * A folder that is separately mounted/connected can be locked against moving (happened to `EXPERIMENT_2`).
  * Launching hidden PowerShell with `-ExecutionPolicy Bypass` was **blocked**. Use plain `robocopy`
    via MATLAB `system()` instead.
  * Deleting files needs explicit user permission; git may leave .lock files if deletion is blocked.
* Other folders on the PC: `D:\clean_data\LEFT_excel`, `RIGHT_excel` (Gelo CSVs, cols
  timestamp, ch1–ch8, mark), `C:\Users\dellc\Downloads\eeg_ratio_batch.m` (PSD C3/C4 ratio script,
  plots in Downloads\psd_plots).

## 4. Repo layout (restructured 2026-10-20; move log in archive/restructure_moves_2026-10-20.csv)

```
data/gelo/{left,right}          own Gelo recordings (15 CSVs, 250 Hz, ch2=C3, ch3=C4, marks 1-5 trials, 6/7 baselines)
data/stroke_liu2024/            Liu et al. 2024 stroke MI dataset (BIDS) + authors' code (code/code) + ERD_ERS/
experiments/01_gelo_svm/        Sep 18  first SVMs on Gelo data
experiments/02_stroke_paper_repro/ Sep 18  reproduce Liu 2024 (9 models, honest CV)
experiments/03_gelo_erd/        Sep 27  ERD on Gelo data (gelo_erd.m), representative-trial plots
experiments/04_svm_stroke_to_gelo/ Sep 28  3 feature-SVMs stroke -> Gelo (MATLAB s01..s05)
experiments/05_bci_iv_2b/       Oct 8-20  BCI Competition IV 2b, the main work
  s00..s07_*.py, gelo_svm_pipeline.py, RUN_ERD_PSD_2b.m, 00_PLAN.md, REPORT.md, STUDY.md/pdf
  data/          B01T..B09T.mat, B01E..B09E.mat (BNCI 004-2014), checksums.csv, sub-B0x.npz, epoch_meta.csv
  subjectwise/   Training|Evaluation / Left|Right / B0x_<split>_<class>.mat + .csv, summary.csv
  classifier/    run_bci2b.m (FBCSP winner replication + improvements), results_kappa_*.csv
  erd_svm/       run_erd_svm.m (within-subject), run_erd_svm_loso.m (leave-one-subject-out)
  erd_ers/       ERD/ERS + PSD outputs; results/ figures and CSVs
apps/cognitive_score/           focus/fatigue desktop app for Capsule headphones (Python, tests, docs PDFs)
hardware/eeg_headphones/        EEG_Recorder, SpeechEEG_Recorder apps (+ vendor SDKs, gitignored)
third_party/covariancetoolbox/  Barachant Riemannian toolbox (gitignored)
reports/                        EXPERIMENT_REPORT_2026-09-19.txt/pdf (stages 01-02)
archive/                        old zips, old README, move log, drive_bundle scripts (gitignored)
```
* All scripts use absolute paths `D:\trainsvm\...` (updated to the new layout). The 2b Python
  scripts use paths relative to their own folder.
* `.gitignore` excludes data/, 2b data/ and subjectwise/, *.npz, *.pkl, archive/, vendor SDKs,
  third_party, app sessions/logs. The commit holds ~252 files, ~26 MB. Only vendor file committed:
  `apps/cognitive_score/cogscore/capsule_sdk/CapsuleClient.dll`.
* Leftover duplicate `D:\trainsvm\EXPERIMENT_2\` may still exist (locked at move time). Safe to delete.

## 5. BCI Competition IV 2b: facts that matter

* 9 healthy subjects B01–B09, 5 sessions each. S1–S2 screening (no feedback, 120 trials each),
  S3–S5 smiley feedback (160 each; some subjects 140/120). T files = S1–3, E files = S4–5
  (this BNCI release **includes E labels**).
* 3 bipolar EEG channels C3, Cz, C4 (+3 EOG, never used for classification), 250 Hz,
  0.5–100 Hz bandpass, 50 Hz notch. Labels 1 = left, 2 = right. `artifacts` flag per trial.
* `.mat` layout: `data` = cell of sessions, each with X [samples×6], trial, y, fs, classes,
  artifacts, gender, age.
* **`trial` = trial START, the cue is at +3 s.** (A past bug: epoching from `trial` gave chance.)
  Screening: beep 2 s, cue 3 s (1.25 s arrow), imagery ~4 s. Feedback: smiley 0 s, beep 2 s,
  cue/imagery 3–7.5 s. Standard imagery window = 0.5–3.5 s after cue.
* `subjectwise/*.mat`: X [trials×3×2000] single (0–8 s from trial start, C3/Cz/C4), sess (1–5),
  art, tpos, fs, ch, t_s, label. CSV = long format trial,session,artifact,time_s,C3,Cz,C4.
* Official metric: Cohen's kappa, max over time of a causal per-sample output, artifact-free trials.

## 6. Key results (all honest protocols)

| Stage | Result |
|---|---|
| 01 Gelo SVM | 78–98 % with random splits (leaky); 57–65 % on unseen recording, p = 0.089. Class = file confound. |
| 02 Stroke paper | Paper claims 72.21 %; honest best 55.4 % (TWFB+FgMDM); authors' code picks band by test acc (63.8 % on shuffled labels). |
| 04 Stroke → Gelo SVMs | All at chance (best 0.531 LOSO, 0.534 on Gelo). Per-subject SVM-A 0.5385, p = 0.008, fails FDR. |
| 05 2b, 7 models × EA | Within-subject (train S1–3, test S4–5) best 0.802 bal. acc (FBCSP-SVM+EA); cross-subject LOSO 0.747; EA +0.045 in 28/28 configs; model choice ≈ 0.003; C3+C4 only ≈ same as 3 ch. |
| 05 Gelo transfer | Same decoder → chance on Gelo (p = 0.83). The cause is the recording protocol (one class per file, mouse click at onset, variable trial length). |
| 05 Calibration curve | With EA, 320 own trials add < 0.01. Public data ≈ 160 user trials. |
| 05 ERD/ERS (Oct 16) | Left MI C4 −29.8 %, right MI C3 −34.3 %; contralateral in 16/18 cells (B02, B03 exceptions). |
| 05 FBCSP winner replication (Oct 20) | Winner = Ang/Chin et al. (I2R), FBCSP: 9 Chebyshev-II bands 4–40 Hz, CSP m=1, MIBIF k=4 (+pairs), **Naive Bayes Parzen Window** (not SVM), published κ 0.600. Ours κ 0.583; FBCSP + shrinkage-LDA (CV-chosen window/sessions) **κ 0.601 ≈ 80 %**; Riemannian TS κ 0.582. Fixed-window single-trial κ ~0.56 (≈78 %). Filter note: use cheb2ord passband = band, stopband ±2 Hz (cheby2 Wn = stopband edges bug gave poor results first). |
| 05 ERD% + SVM, within-subject (Oct 20) | 6 features (ERD% C3/Cz/C4 × mu/beta; baseline −2..−1 s, task 0.5–3.5 s after cue; power averaged over N same-class trials then ERD%). Linear SVM: single trial 66 %, 5-avg 78 %, 10-avg 81 % (B04, B08 100 %; B02, B03 ≤ chance). Linear > RBF. |
| 05 ERD% + SVM, LOSO (Oct 20) | Train 8 subjects (all sessions), test 9th. Single 62.0 %, 10-avg **74.4 %**. Pooled CM (10-avg): TL→L 209, TL→R 49, TR→L 80, TR→R 179 (bias to Left). Weights: C4β +1.14, C3β −0.73, C3μ −0.62, C4μ +0.38, Cz ≈ 0. |

Caveat to repeat whenever 10-trial averaging is discussed: one decision per 10 same-class trials,
with groups formed using known labels, so it is a block-level decision, not single-trial control.

## 6b. Real-time app `apps/mi_bci/` (built 2026-10-25)

* Python 3.13 + tkinter. `run.bat`, `run_simulator.bat`, `app.py --selftest`, `python -m pytest -q tests`,
  `tools/replay_2b.py [subj]` (2b streamed through the live engine), `tools/check_sdk.py`,
  `tools/check_real_signal.py <csv> --volts`. Package `mibci/`: config, sources (HeadphonesSource via
  pyneurosdk2 from `hardware/eeg_headphones/brain_bit/pyneurosdk2-1.0.15`, SimulatedSource, ReplaySource),
  dsp (causal Butterworth-5 log band power, 1 s window, output every 10 samples; artifact = 1 Hz high-passed
  1 s ptp > 4x running median or > 1500 uV; montage ear_bipolar C3-A1, C4-A2), decoder (shrinkage LDA JSON,
  neg = left; 2 s sign integrator), paradigm (sample-clock state machine; Graz timings; baseline blocks;
  RecordedParadigm), engine (pieces split on output boundaries -> packet-independent), recorder
  (data/mi_bci/<subj>/<stamp>_<type>/eeg.csv events.csv outputs.csv run.json), trainer (nested
  leave-one-run-out greedy selection <= 6 features, permutation p on fixed mu/beta, Graz >= 5-pt switch rule),
  analysis (alpha, contralateral ERD permutation test, signal_quality), cli.
* Verified: 21 tests, UI self-test (canvas read-back checks, no screen capture), 2b replay identical to offline.
* MODEL (config.MODEL="svm", since 2026-10-26, user's explicit wish): CSP+SVM+EA live (`mibci/svm.py`,
  `svm_trainer.py`): 8-30 Hz causal, 2 s window covariance every 40 ms, EA per recording day, CSP log-var,
  scaler, LinearSVC C=0.1 balanced; JSON params. Base `models/base_2b_svm.json` (all 9 2b; cache in
  _out/base_2b_cache, `tools/build_base_svm.py`). Train = 3 weightings chosen by leave-one-run-out; score =
  pooled held-out accuracy, binomial p. `tools/svm_check_2b.py`: base-only 75.9 %, improved 76.0 % live.
* Sound: `mibci/sound.py`, one sounddevice stream on laptop speakers (Windows default was the EEG headset).
* P01 (2026-10-26): alpha OK, movement mu lateralised p=0.041 (10 trials/hand), imagery not yet; mains hum
  high in task runs. Next: 2 more movement runs, 4-6 screening runs, then train.
* Running Python from Claude: use MATLAB `system('start "x" /b cmd /c "... > _out\log.txt 2>&1"')` and poll the
  log via device_bash (foreground calls time out at 60 s). Do NOT screen-capture: the user's other windows
  (a video) ended up in screenshots once; those files were overwritten.
* Open: never run on the headset; units assumed volts; 2026-04-14 raw recording is bad contact (13 % pinned);
  Bluetooth delay unmeasured; PackNum-per-sample assumption; montage untested on real data.

## 7. Rules / pitfalls established in this project

1. Cue = `trial` + 3 s in 2b. Always verify event indices (the stroke data had a marker-2 trap too).
2. Euclidean Alignment must stay **unsupervised** (per-session mean covariance) or it leaks.
3. Keep CSP / tangent space / feature selection **inside** the CV pipeline.
4. Reseed RNG per configuration (an old MATLAB bug: a variable named `rng` shadowed the function).
5. Use LinearSVC for cross-subject sizes (libsvm too slow).
6. Write the plan + expected range before running (that is how the cue bug was caught).
7. Gelo data: class is confounded with file/session. Never report random-split accuracy on it.

## 8. Open next steps

1. **Re-record Gelo data**: left/right interleaved in one session, software-timed cues, fixed
   4 s trials, hands still, equal counts, several sessions, note electrode positions. Then run
   `experiments/05_bci_iv_2b/s04_gelo_transfer.py` unchanged.
2. Possible model work on 2b: an SVM variant in `classifier/run_bci2b.m`, Euclidean alignment
   added to FBCSP, EEGNet. Show MIBIF-selected bands per subject (offered, not done).
3. Add the Google Drive link to README.md once `D:\EEG_research_data` is uploaded (keep it
   private: contains vendor `License key.docx`).
4. Confirm what Gelo ch1/ch4 are.

## 9. Git / data housekeeping state

* Pushed: "Initial commit: EEG motor-imagery project, restructured". After that: README rewritten
  in simple English, erd_svm/ folder, CLAUDE.md. Check `git status` to see whether these are committed.
* Old `.git` had ~777 MB garbage from an early add of the data (`git gc --prune=now` frees it).
* Drive bundle `D:\EEG_research_data`: 1_raw_recordings, 2_public_datasets, 3_derived_and_results,
  4_vendor_sdks, 5_archive, README_DATA.md, MANIFEST.csv, restore_into_repo.bat. Excludes stroke
  csv/ + csv.zip (regenerable via export_csv.py) and erd_ers/cache.
