# HOW TO RUN  -  Experiment_svm

A practical guide to running the three-SVM motor-imagery experiment.
Everything lives in D:\trainsvm\Experiment_svm

===========================================================================
## 1. QUICK START
===========================================================================

Open MATLAB, then paste these four lines one at a time, waiting for each
to finish before starting the next:

    cd('D:\trainsvm\Experiment_svm')
    run('s01_extract_features.m')      % ~1 min
    run('s02_train_svm.m')             % ~2-3 min
    run('s03_make_figures.m')          % ~1 min
    run('s04_round2.m')                % ~4-5 min\n    run('s05_native_rate.m')           % ~5 min, optional variant

Total: about 10 minutes. That reproduces every number and every figure in
REPORT.md from the raw data.

IMPORTANT: run them in that order. Each one uses files the previous one
wrote. s01 must always run first.

===========================================================================
## 2. WHAT YOU NEED
===========================================================================

MATLAB R2025a (or any release from R2020b up - nothing exotic is used).

Three toolboxes, all confirmed installed on this machine:

    Signal Processing Toolbox              butter, filtfilt, pwelch, resample
    Statistics and Machine Learning        fitcsvm, skewness, kurtosis,
                                           perfcurve, cvpartition, ttest
    (Curve Fitting Toolbox is NOT needed by these scripts)

To check your own machine:

    license('test','Signal_Toolbox')       % should print 1
    license('test','Statistics_Toolbox')   % should print 1

Input data that must already be on disk:

    D:\trainsvm\eeg_stroke\sourcedata\sourcedata\sub-01 ... sub-50
        each containing sub-XX_task-motor-imagery_eeg.mat
    D:\trainsvm\eeg_stroke\participants.tsv            (needed by s04)
    D:\trainsvm\eeg_stroke\ERD_ERS\ERD_ERS_summary.csv (needed by s04)
    D:\trainsvm\left\*.csv                             (5 files)
    D:\trainsvm\right\*.csv                            (10 files)

===========================================================================
## 3. WHAT EACH SCRIPT DOES
===========================================================================

--- s01_extract_features.m --------------------------------- ~1 min ------

  Turns raw EEG into the feature tables. This is the only script that
  touches the raw recordings.

  Reads : the 50 stroke .mat files, and your left\ and right\ CSVs
  Does  : cuts epochs at the per-trial marker, resamples 500->250 Hz,
          bandpasses 8-30 Hz, squares each sample, takes mean/median/
          skewness/kurtosis at C3 and C4, and the Welch C3/C4 PSD ratio
  Writes: features_train.csv   (1982 rows)
          features_test.csv    (72 rows)
          test_epoch_meta.csv  (why each epoch was kept or dropped)
          psd_curves.mat

  You should see it end with:
      TOTAL train epochs: 1982  (left 990, right 992)
      TOTAL test epochs: 72  (left 22, right 50)
  If those two lines differ, something changed in the input data - stop
  and find out why before trusting anything downstream.

--- s02_train_svm.m -------------------------------------- ~2-3 min ------

  Trains the three SVMs, 12 configurations in total
  (A/B/C x absolute/ERD x linear/RBF).

  Reads : features_train.csv, features_test.csv
  Writes: results_summary.csv       (the main results table, read by s03)
          results_partial.mat       (raw, resumable)
          confusion_matrices.mat

  The summary CSV is only written once all 12 configurations are done.
  If you run it in chunks, it appears after the final chunk.

  ** THE ONE GOTCHA **  This script is resumable, and it RESUMES BY
  DEFAULT. It appends to results_partial.mat rather than overwriting it.
  So if you run it twice you get 24 rows instead of 12.

  Before a clean re-run, always delete the partial file first:

      delete('D:\trainsvm\Experiment_svm\results_partial.mat')
      run('s02_train_svm.m')

  If your MATLAB session is slow and the script seems to hang, you can run
  it in pieces by setting RUN_SETS before running it:

      RUN_SETS = 1:3;  run('s02_train_svm.m')    % feature sets 1-3
      RUN_SETS = 4:6;  run('s02_train_svm.m')    % feature sets 4-6

  Results are identical either way - the random seed is reset per
  configuration specifically so that chunking cannot change the numbers.

--- s03_make_figures.m ------------------------------------- ~1 min ------

  Reads : features_*.csv, psd_curves.mat, results_summary.csv,
          confusion_matrices.mat
  Writes: figures\fig1_psd_c3c4.png       C3/C4 spectra by class
          figures\fig2_ratio_dist.png     the single feature SVM-C uses
          figures\fig3_domain_shift.png   train vs test feature ranges
          figures\fig4_confusions.png     all 12 confusion matrices
          figures\fig5_per_subject.png    per-subject laterality
          per_subject_laterality.csv

  It closes all figure windows when it finishes. That is intentional.

--- s04_round2.m ----------------------------------------- ~4-5 min ------

  The round-2 follow-ups: per-subject models, hemiplegic-side split,
  sign-corrected pooling, and the alpha/beta split. Also validates the
  feature extraction against an independent implementation.

  Reads : features_*.csv, participants.tsv, ERD_ERS_summary.csv
  Writes: results_round2.csv  (72 rows)

  This one overwrites cleanly - no partial file, safe to re-run.

--- s05_native_rate.m (optional variant) ----------------- ~5 min ------

  Repeats the experiment with each dataset at its NATIVE sampling rate
  (stroke 500 Hz, ours 250 Hz) instead of resampling both to 250 Hz.
  Writes features_*_native.csv and results_native.csv. Independent of
  s02/s03/s04 - it neither reads nor overwrites their outputs.
  Needs only s01's raw inputs, so it can be run any time after s01.

  Note: fig6_round2.png was produced separately and is not regenerated by
  this script.

===========================================================================
## 4. HOW TO TELL IT WORKED
===========================================================================

After all four scripts, check the headline numbers:

    T = readtable('D:\trainsvm\Experiment_svm\results_summary.csv');
    max(T.LOSO_balanced_accuracy)      % expect 0.5315
    max(T.test_balanced_accuracy)      % expect 0.5336
    height(T)                          % expect 12

    R = readtable('D:\trainsvm\Experiment_svm\results_round2.csv');
    height(R)                          % expect 72

If height(T) is 24 instead of 12, you ran s02 twice without deleting
results_partial.mat. Delete it and run s02 again.

Expected final file list:

    HOW_TO_RUN.md                this guide
    00_PLAN.md                   the original plan and open questions
    REPORT.md                    the full write-up, both rounds
    s01_extract_features.m       -\
    s02_train_svm.m               |  the four scripts, run in this order
    s03_make_figures.m            |
    s04_round2.m                 -/
    features_train.csv           1982 epochs x 9 features
    features_test.csv            72 epochs x 9 features
    test_epoch_meta.csv          every candidate epoch and its fate
    per_subject_laterality.csv   per-subject laterality and AUC
    results_summary.csv          round 1: 12 configurations
    results_round2.csv           round 2: 72 rows
    results_partial.mat          resumable raw results from s02
    confusion_matrices.mat       all 12 confusion matrices
    psd_curves.mat               class-averaged spectra
    features_train_native.csv    variant: stroke kept at 500 Hz
    features_test_native.csv     variant: ours kept at 250 Hz
    results_native.csv           variant: native-rate results
    figures\                     7 PNGs

===========================================================================
## 5. IF YOU MOVE THE FOLDER
===========================================================================

Paths are hard-coded at the top of each script. If the project moves,
edit these lines - there are only eight in total:

    s01_extract_features.m  line 20  CFG.outDir
    s01_extract_features.m  line 21  CFG.strokeRoot
    s01_extract_features.m  line 22  CFG.ownRoot
    s02_train_svm.m         line 26  OUT
    s03_make_figures.m      line 14  OUT
    s04_round2.m            line 18  OUT
    s04_round2.m            line 21  participants.tsv
    s04_round2.m            line 58  ERD_ERS_summary.csv

===========================================================================
## 6. TROUBLESHOOTING
===========================================================================

ERROR: Invalid MATLAB file name  /  Invalid text character
    You tried to run a file whose name starts with a digit. MATLAB script
    names must start with a letter - that is why the files are named
    s01... to s04... and not 01... to 04...

ERROR: Unable to read file sub-01_task-motor-imagery_eeg.mat
    The stroke dataset is not where s01 expects it. Check CFG.strokeRoot.

ERROR: No CSV files found in D:\trainsvm\left
    Your own recordings are missing or in a different folder.
    CFG.ownRoot must be the folder CONTAINING left\ and right\,
    not the left\ folder itself.

PROBLEM: s02's numbers change between runs
    A variable in the workspace is shadowing a MATLAB function. s02 does
    not call clear (so RUN_SETS survives), so a leftover variable named
    rng would silently disable all seeding. s01 no longer creates one and
    s02 now guards against it, but if you add code, never name a variable
    rng, psd, mean, max, i or j. To check: which('rng') should print a
    toolbox path, not the word "variable".

ERROR: Undefined function fitcsvm
    Statistics and Machine Learning Toolbox is not installed or licensed.

ERROR: Undefined function butter / pwelch / resample
    Signal Processing Toolbox is not installed or licensed.

PROBLEM: results_summary.csv has 24 or 36 rows
    s02 was run more than once without deleting results_partial.mat.
    Delete that file, then run s02 again.

PROBLEM: the script appears to hang
    s02 and s04 genuinely take minutes - s04 fits several thousand small
    SVMs. Watch the Command Window: both print one line per configuration
    as they go. If new lines are still appearing, it is working.

===========================================================================
## 7. FULL CLEAN RE-RUN
===========================================================================

To rebuild everything from the raw data with nothing carried over:

    cd('D:\trainsvm\Experiment_svm')
    delete('results_partial.mat')
    run('s01_extract_features.m')
    run('s02_train_svm.m')
    run('s03_make_figures.m')
    run('s04_round2.m')

Nothing outside D:\trainsvm\Experiment_svm is written or modified. The raw
data folders are only ever read from.

===========================================================================
## 8. WHERE TO LOOK FOR THE ANSWERS
===========================================================================

    REPORT.md          section 3   the three models' results
    REPORT.md          section 4   why they are at chance
    REPORT.md          ROUND 2     per-subject models and the follow-ups
    results_summary.csv            every round-1 number
    results_round2.csv             every round-2 number
    figures\fig4_confusions.png    what each model actually predicted
    figures\fig5_per_subject.png   whether the effect exists at all
