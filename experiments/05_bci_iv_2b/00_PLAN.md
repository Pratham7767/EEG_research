# EXPERIMENT_2 — PLAN (v1)

Written 2026-10-08, before anything was computed. Nothing in this file is a result.

## WHY THIS EXPERIMENT EXISTS

Experiment_svm and stroke_paper between them established three things:

  1. The Liu et al. 2024 headline accuracy (72.21 %) is not reproducible because
     TWFB_DGFMDM.m selects its frequency band by TEST accuracy. On randomly
     shuffled labels the same procedure still scores 63.79 %. There is no gap to
     close.
  2. Nine models run through one honest protocol on that dataset top out at
     55.40 % (TWFB+FgMDM), with CSP+LDA at 50.45 % and tangent space+SVM at
     53.30 %. Only ~12 of 50 patients beat chance, and it is the same patients
     every time. CSP, FBCSP, Riemannian tangent space and FgMDM have ALREADY
     been tried on the full 29 channels. The ceiling is a property of the
     cohort, not of the feature set.
  3. Our own Gelo recordings cannot measure anything yet, because every file
     holds exactly one class, so class is perfectly confounded with session.

So the binding constraint is the TRAINING DATA, not the classifier. This
experiment changes the training data.

## THE DATASET

BCI Competition IV dataset 2b (BNCI Horizon 2020 id 004-2014).

  * 9 healthy right-handed subjects, B01-B09
  * 5 sessions each, recorded on different days
      sessions 1-2  screening, no feedback   (T files, ~120 trials each)
      session  3    with smiley feedback     (T file)
      sessions 4-5  with smiley feedback     (E files, ~160 trials each)
  * 2 classes only: LEFT hand vs RIGHT hand MI. Balanced.
  * 3 bipolar EEG channels: C3, Cz, C4.  Plus 3 EOG channels (dropped here).
  * 250 Hz, bandpass 0.5-100 Hz, 50 Hz notch applied at recording time.
  * ~720 trials per subject, ~6500 trials total.

Why this dataset and not the stroke one:

  * 250 Hz is OUR headset's native rate. No resampling step at all.
  * C3 / Cz / C4 is almost exactly our montage (ch2 = C3, ch3 = C4). The
    "throw away 27 good channels" compromise that dominated Experiment_svm
    simply does not arise — 2b only ever had three.
  * Healthy subjects, so no mixed-hemiplegia cancellation.
  * Properly randomised cue order inside every session, so class is NOT
    confounded with session. This is the thing our own recordings lack.
  * The montage was deliberately minimal to emulate portable BCI scenarios,
    which is exactly our use case.
  * Published accuracies on 2b sit in the 75-85 % range rather than 55 %.

## PIPELINE

Step 0  Fetch
  18 .mat files (B01T..B09T, B01E..B09E) from
  https://lampx.tugraz.at/~bci/database/004-2014/
  ~34 MB each, ~615 MB total, cached in data\ and never re-downloaded.
  SHA256 of every file recorded in data\checksums.csv.

Step 1  Epoching
  Per session: drop EOG, keep [C3 Cz C4], replace the NaN gaps the format uses
  at breaks with zeros (counted and reported), detrend, then zero-phase
  Butterworth order 4.
  Imagery window = 0.5 s to 3.5 s after cue onset (3.0 s, 750 samples).
  Cue onset is read per trial from the file's own `trial` index, never assumed.
  Trials whose window runs past the end of a session are dropped and counted.

Step 2  Representations
  Everything downstream operates on per-trial covariance matrices (3x3), which
  is both correct and cheap:
    * main band 8-30 Hz          -> one 3x3 covariance per trial
    * filter bank 4-8, 8-12, 12-16, 16-20, 20-24, 24-28, 28-32 Hz
                                 -> seven 3x3 covariances per trial
  Covariance estimator: Ledoit-Wolf shrinkage, as in run_all_models.py.
  Log-variance features are the diagonal of the same matrices, so the cheap
  baseline and the Riemannian models share one code path.

Step 3  Euclidean Alignment (the new ingredient)
  Per SESSION, compute the reference matrix R = mean of that session's trial
  covariances, then map every covariance C -> R^-1/2 C R^-1/2.
  Properties that matter here:
    * it is unsupervised — it uses no labels at all, so computing it on a test
      session is NOT leakage, and it needs no calibration labels from a new
      user;
    * the session is the correct domain unit, because that is what differs
      (electrode contact, impedance, day);
    * it is the principled version of what the ERD% normalisation in
      Experiment_svm was reaching for, and it also cancels the 3.1x gain
      mismatch that collapsed the absolute-energy models onto one class.
  Every model is run twice, EA off and EA on, so the effect of EA is measured
  rather than assumed.

Step 4  Models (7, each x EA off/on = 14 configurations)
    csp_lda      CSP (1 pair, log-var) + LDA          the paper's own baseline
    csp_svm      CSP (1 pair, log-var) + linear SVM
    fbcsp_svm    7-band CSP + mutual-information selection + SVM
    ts_svm       tangent space (Riemann) + scaler + SVM
    tslda        tangent space + shrinkage LDA
    fgmdm        Fisher-geodesic MDM
    logvar_svm   log variance of C3/Cz/C4 in 8-30 Hz + SVM   (cheap baseline,
                 the closest thing to the mean/median/skew/kurt approach)

Step 5  Protocols (both honest, both reported)
  P1  WITHIN-SUBJECT, CROSS-SESSION
      train on sessions 1-3, test on sessions 4-5, per subject.
      This is the standard 2b protocol, so the numbers are directly comparable
      to the published literature. It answers: does this work for one person
      who calibrated earlier?

  P2  CROSS-SUBJECT, LEAVE-ONE-SUBJECT-OUT
      train on 8 subjects (all sessions), test on the 9th.
      This is the structural analogue of what we actually want — train on other
      people's data, test on a new person — and it is the number that predicts
      whether a model trained on a public dataset can ever be pointed at our
      headset without per-user calibration. P2 is the one that matters for the
      project; P1 is the sanity check that the data is sound.

  Hyperparameters (SVM C, and the number of FBCSP features kept) are chosen by
  an inner cross-validation on TRAINING data only, grouped by session so that
  no session straddles the inner split. Nothing is ever chosen on the test set.
  The RNG is reset at the start of every configuration (the shadowing bug from
  Experiment_svm is why).

Step 6  Reporting
  accuracy, balanced accuracy and kappa for every subject x model x EA x
  protocol; the per-subject binomial threshold for "beats chance"; and the
  majority-class baseline printed next to every number, as in Experiment_svm.
  Artefact-flagged trials are KEPT in the main run; a second pass excluding
  them is reported alongside, never substituted for it.

## WHAT I EXPECT, WRITTEN DOWN BEFORE RUNNING IT

(a) P1 should land around 75-80 % mean for the better models. If it comes out
    near 55 %, something is wrong with my epoching — most likely the cue index
    convention — and I should fix that before reading anything else.

(b) P2 will be substantially lower than P1, probably 60-70 %. Cross-subject is
    genuinely harder, and 3 channels gives CSP very little room: with 3
    channels there are only 3 spatial components, so CSP is close to a
    whitening plus a rotation. This is the same ceiling argument that applied
    to our 2-channel work, and it does not disappear just because the dataset
    is better.

(c) EA should help P2 clearly and P1 only a little. P1's train and test
    sessions are the same person on nearby days; P2 crosses people, which is
    where a per-session whitening has something to remove. If EA helps P1 more
    than P2 I have probably implemented the session grouping wrongly.

(d) The Riemannian models (ts_svm, tslda, fgmdm) should beat csp_lda. They did
    on the stroke data too (53.3-53.5 vs 50.45), just at a level where it
    didn't matter.

(e) logvar_svm will be the worst model, and that is the point of including it:
    it is the honest stand-in for the mean/median/skewness/kurtosis feature set
    from Experiment_svm. The distance between it and ts_svm on a dataset that
    actually contains signal is the clearest statement of what the feature
    choice was costing us.

(f) None of this says anything yet about our Gelo recordings. It establishes a
    working pipeline and a believable reference number. The session confound in
    our own data is unchanged and still has to be fixed by re-recording.

## FILES THIS EXPERIMENT WILL WRITE (all under D:\trainsvm\EXPERIMENT_2)

  00_PLAN.md            this file
  s01_fetch_2b.py       download, verify, epoch, cache covariances
  s02_run_models.py     the 14 configurations x 2 protocols
  s03_report.py         tables and figures
  data\                 the 18 .mat files + per-subject .npz + checksums.csv
  results\              per_trial_predictions.csv, summary.csv,
                        per_subject.csv, figures\
  REPORT.md             written last, after the numbers exist

Nothing outside this folder is written. eeg_stroke\, left\, right\ and
Experiment_svm\ are not touched.
