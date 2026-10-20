# Experiment_svm — PLAN (v1, awaiting sign-off)

Written 2026-09-28. Nothing has been computed yet beyond the reconnaissance
numbers quoted below. Do not treat this as results.

Goal as stated: build three SVMs on features derived from the Liu et al. 2024
acute-stroke MI dataset (50 subjects), then feed our own Gelo/LEHeadphones2
4-second epochs in as a pure, untouched test set.

  SVM-A : mean, median, skewness, kurtosis   (time-domain energy features)
  SVM-B : those four + C3/C4 PSD ratio       (all five)
  SVM-C : C3/C4 PSD ratio only               (one feature)

---------------------------------------------------------------------------
## 1. WHAT IS ACTUALLY IN THE TRAINING DATA (verified, not assumed)
---------------------------------------------------------------------------

Path: D:\trainsvm\eeg_stroke\sourcedata\sourcedata\sub-XX\sub-XX_task-motor-imagery_eeg.mat
Each file holds one struct `eeg` with two fields.

  eeg.rawdata : [40 x 33 x 4000]  double   (trials x channels x samples)
  eeg.label   : [40 x 1]          1 = LEFT hand MI, 2 = RIGHT hand MI

Checked across all 50 subjects:
  * every subject is exactly [40 x 33 x 4000]. No exceptions.
  * every subject is exactly 20 left / 20 right, strictly alternating
    L,R,L,R,... from trial 1.
  * total = 2000 trials = 1000 left + 1000 right. Perfectly balanced.
  * fs = 500 Hz, so 4000 samples = 8 s per trial. Matches the paper.

Channel 33 is the marker channel. Per trial it carries exactly three non-zero
samples: value 1 (instruction onset), value 2 (MI onset), value 3 (break
onset). Verified over all 2000 trials:
  * no trial is missing a marker,
  * (marker3 index - marker2 index) is 2000-2003 samples in every trial,
    i.e. the imagery window is 4.000-4.006 s. Consistent.
  * marker 2 normally lands near sample 1004 (2 s in), BUT in subjects
    08, 13, 14, 20, 22, 24, 25, 29, 30, 40, 48 some trials have marker 2 at
    sample 2 — those trials were cut without the instruction period.
    => the epoch MUST be taken from the per-trial marker-2 index, never from
       a hard-coded sample 1004. This is a real trap and I will avoid it.

Channel map (paper Table 2), 1-indexed:
  1 Fp1  2 Fp2  3 Fz   4 F3   5 F4   6 F7   7 F8   8 FCz  9 FC3 10 FC4
 11 FT7 12 FT8 13 Cz  14 C3  15 C4  16 T3  17 T4  18 CPz 19 CP3 20 CP4
 21 TP7 22 TP8 23 Pz  24 P3  25 P4  26 T5  27 T6  28 Oz  29 O1  30 O2
 31 HEOL 32 VEOR 33 marker

  => C3 = channel 14, C4 = channel 15.
  => channel 18 (CPz) is the reference. Verified: it is a flat constant
     (187500 for sub-01, std = 0) in 49/50 subjects. Useless, must be dropped.
  => The paper's own Table 2 prints FT7 twice, at channel 11 and channel 21.
     Channel 21 is TP7 (it is bracketed by CP4 and TP8, and TP7 is otherwise
     absent while the 10-10 montage needs it). This is a typo in the paper.

Raw values carry large per-channel DC offsets (sub-01 trial 1: C3 sits around
+3200, C4 around +16600). Any "energy" computed before filtering would be
almost pure DC. Bandpass first, always.

---------------------------------------------------------------------------
## 2. WHAT IS ACTUALLY IN THE TEST DATA (verified)
---------------------------------------------------------------------------

Source: D:\trainsvm\left\*.csv and D:\trainsvm\right\*.csv, cut by gelo_erd.m.
Existing product: D:\trainsvm\erd\epochs_paper_format.mat
  datar1  [1250 x 15 x 72]   (samples x channels x trials), fs = 250 Hz
  labelr1 [72 x 1]           1 = left, 2 = right
  1250 samples = 1 s baseline + 4 s imagery. C3 at ch14, C4 at ch15 (only
  those two channels are populated; the other 13 are zeros).

From matlab_epoch_meta.csv:
  LEFT  : 5 files x 5 marks = 25 candidates, 22 kept
          (Left1_5 mark 3 MISSING; Left6_10 mark 3 and left16_20 mark 2
           dropped as NO_BASELINE)
  RIGHT : 10 files x 5 marks = 50 candidates, 50 kept
  => TEST SET IS 22 LEFT vs 50 RIGHT. Badly imbalanced. See section 6.

Amplitude scale check I ran (8-30 Hz, 4 s imagery window, RMS in the file's
own units):
  stroke subs 1-5 : C3 median 3.17, C4 median 2.74
  our data        : C3 median 4.23, C4 median 4.63
  ratio our/stroke: C3 1.34x, C4 1.69x
So the two datasets are on a comparable scale (the stroke .mat is effectively
microvolts) — but 1.3-1.7x in amplitude is 1.8-2.9x in ENERGY, which directly
biases the mean/median energy features. The C3/C4 ratio is immune to this.

---------------------------------------------------------------------------
## 3. PROPOSED PIPELINE (identical code path for train and test)
---------------------------------------------------------------------------

Step 0  Epoching
  train: per trial, onset = index of marker value 2 in channel 33;
         take onset : onset+1999  (4.000 s at 500 Hz) from channels 14 and 15.
  test : per epoch, take the 4 s after onset, i.e. samples 251:1250 of
         datar1 (1000 samples at 250 Hz), channels 14 and 15.
  (I would rather re-cut the test epochs from the CSVs inside our own script
   with exactly the same rules gelo_erd.m uses, so the whole experiment is
   reproducible from raw. See Q9.)

Step 1  Resample train 500 Hz -> 250 Hz
  So both sets are literally the same sampling rate before any statistic is
  taken. Skewness and kurtosis of a squared time series are not invariant to
  sampling rate, so this is not cosmetic.

Step 2  Per-epoch detrend (remove mean) then 8-30 Hz zero-phase Butterworth,
  order 2 (filtfilt). Same band and order the paper uses in its Technical
  Validation, and the same one gelo_erd.m uses.

Step 3  Energy series
  E_c(t) = x_c(t)^2   for c in {C3, C4}, one value per sample.
  ("the energy of each point" as requested)

Step 4  Time-domain features, per epoch, per channel:
    mean(E), median(E), skewness(E), kurtosis(E)
  -> 8 numbers per epoch (4 stats x C3, C4).

Step 5  Spectral feature, per epoch:
    Welch PSD (Hamming, 1 s window, 50% overlap) on the filtered signal.
    P_c = band power 8-30 Hz.
    ratio = log10(P_C3 / P_C4)    (log so left/right are symmetric around 0
                                   and the feature is not scale-dependent)
  -> 1 number per epoch.
  PSD plots will be produced as figures (class-averaged C3 and C4 spectra for
  left and right, train and test) but the SVM gets the scalar ratio.

Step 6  Feature matrices
    A : 8 features   B : 9 features   C : 1 feature
  z-score standardisation fitted ONLY on the 2000 training epochs and then
  applied unchanged to the 72 test epochs. Never refitted on test.

Step 7  Models
    fitcsvm, tried with linear and RBF kernels, BoxConstraint/KernelScale
    chosen by grid search inside the TRAINING data only.
    Model selection uses leave-one-SUBJECT-out CV over the 50 stroke
    subjects — not random k-fold, because random folds leak subject identity
    and inflate the number.

Step 8  Reporting, for each of A, B, C:
    - leave-one-subject-out accuracy on the stroke data (the honest internal
      number)
    - accuracy, balanced accuracy, sensitivity, specificity, kappa and
      confusion matrix on our 72 test epochs
    - the majority-class baseline printed alongside every number

---------------------------------------------------------------------------
## 4. WHAT I EXPECT TO HAPPEN, SAID PLAINLY BEFORE RUNNING IT
---------------------------------------------------------------------------

(a) The test set probably contains no left/right information at all.
    GELO_ERD_EXPLAINED.txt section 13/14 already established, on this exact
    data, that the contralateral effect is absent (diff +2.67 and +1.72,
    p = 0.77 and 0.84, i.e. the wrong sign and no significance), that every
    class lives in its own file/session, and that leave-one-FILE-out
    classification is 53-66% with a permutation p of 0.089. Nothing in this
    SVM experiment can create information that is not in the recording.

(b) The 69.4% trap. 50 of 72 test epochs are right-hand. A classifier that
    outputs "right" every single time scores 69.4%. That number will look
    like success and will mean nothing. Every headline number in this
    experiment must therefore be balanced accuracy plus the confusion matrix.
    I will refuse to report bare accuracy on its own.

(c) The training model itself will be weak. The paper's own per-subject
    CSP+LDA reached 55.57% and their best custom method 72.21% — using 30
    channels, spatial filtering and a model fitted per subject. We are using
    2 channels, 4 scalar moments, and one pooled model across 50 stroke
    patients with different lesions and different hemiplegic sides. A
    leave-one-subject-out result anywhere in 52-58% would be the realistic
    outcome. Above ~65% I would suspect a leak, not a breakthrough.

(d) SVM-C is a single scalar, so it is a threshold on log(P_C3/P_C4). It can
    only work if the contralateral ERD is strong and consistent. In this
    dataset it is not: the paper itself reports the expected C3<C4 pattern in
    only 46% and 42% of subjects, and notes that some subjects show the
    reverse. So expect SVM-C near chance.

(e) Domain shift is severe and not repairable by scaling. Train: 32-channel
    saline cap, CPz reference, 500 Hz, acute stroke patients, software video
    cue, 4 s fixed. Test: 8-channel headset (only ch1-4 used), unknown
    reference, 250 Hz, one healthy user, self-clicked cue of 4.9-148 s. The
    paper's own Usage Notes flag non-stationarity and feature covariance
    shift as a known problem even within their dataset.

(f) Known-artefact subjects flagged by the paper: 4, 5, 13, 14, 18, 24, 28,
    33, 42, 43, 47, 48, 49. I propose keeping them in the main run and
    reporting a second run without them, rather than quietly dropping them.

None of this is a reason not to run the experiment. It is a reason to write
the expected outcome down first, which is what this section is.

---------------------------------------------------------------------------
## 5. OPEN QUESTIONS (need answers before I write code)
---------------------------------------------------------------------------

Q1  "Energy of each point" = square each filtered sample, then take the four
    moments of that squared series. Is that what you mean? The alternative
    reading is the analytic-signal envelope, or a short-window running
    energy. I will assume plain x^2 unless told otherwise.

Q2  Moments per channel (C3 and C4 separately -> 8 features) or on some
    combination (e.g. C3+C4 averaged -> 4 features)? You wrote "mean, median,
    skewness and kurtosis" as four features, which reads like 4, not 8.
    My recommendation: 8 (keep C3 and C4 separate). Confirm.

Q3  Only C3 and C4, correct? Our test recording has nothing else, so the
    training side is forced down to those two channels whatever the stroke
    data offers. Confirming that you accept throwing away 27 good channels.

Q4  C3/C4 ratio: over the whole 8-30 Hz band as one number, or split into
    alpha 8-13 and beta 13-30 (two ratios)? And linear ratio or log ratio?
    My recommendation: log10 of the 8-30 Hz ratio, one number, to keep SVM-C
    genuinely one-dimensional as you specified.

Q5  One pooled model over all 50 subjects (my assumption), or 50 per-subject
    models? You said "this would be our training data", which reads pooled.

Q6  Do you want the 500 -> 250 Hz resampling of the training data, or would
    you rather upsample ours 250 -> 500? I recommend downsampling the stroke
    data — upsampling invents nothing and doubles compute.

Q7  Kernel: linear, RBF, or both compared? I recommend running both and
    reporting both, since with 1-9 features it costs nothing.

Q8  Test-set imbalance (22 L / 50 R). Options: (i) report balanced accuracy
    and leave all 72 in, (ii) also report a 22 vs 22 subsampled version.
    I recommend doing both. Confirm you want (ii) as well.

Q9  Test epochs: re-cut from D:\trainsvm\left and \right CSVs inside the new
    script (reproducible end-to-end), or just load the existing
    epochs_paper_format.mat? I recommend re-cutting with identical rules.

Q10 MATLAB or Python? Everything else of yours is MATLAB and MATLAB is live
    on this machine, so I propose MATLAB (fitcsvm, Statistics and Machine
    Learning Toolbox). Tell me if you want Python/scikit-learn instead.

Q11 The 2 s instruction window before MI onset is available in the training
    data but our epochs only have 1 s of baseline. If you ever want
    baseline-normalised (ERD%) features instead of absolute energy, the
    window has to be 1 s to match. Do you want an ERD-normalised variant as
    a fourth model, or keep strictly to the three you specified?

---------------------------------------------------------------------------
## 6. FILES THIS EXPERIMENT WILL WRITE (all under D:\trainsvm\Experiment_svm)
---------------------------------------------------------------------------

  00_PLAN.md                  this file
  01_extract_features.m       epoching + filtering + feature extraction
  02_train_svm.m              the three models, CV, evaluation
  03_make_figures.m           PSD plots, feature distributions, confusions
  features_train.csv          2000 rows x (subject, trial, label, 9 features)
  features_test.csv           72 rows   x (file, mark, label, 9 features)
  results_summary.csv         every model x every metric
  figures\                    PSD plots, confusion matrices, feature scatters
  REPORT.md                   the honest write-up, written last

Nothing is written outside this folder.
