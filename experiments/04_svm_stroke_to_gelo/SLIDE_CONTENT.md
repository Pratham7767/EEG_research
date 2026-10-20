# SLIDE CONTENT  -  features and hyperparameters per SVM

Numbers taken from results_summary.csv (round 1) and results_round2.csv
(round 2). Regenerate with s01 -> s02 -> s03 -> s04.

===========================================================================
## SHARED PIPELINE  (identical for all three models, train and test)
===========================================================================

  Channels           C3 and C4 only (stroke ch14 / ch15)
  Epoch              1 s baseline + 4 s motor imagery, cut at the
                     per-trial MI marker (marker value 2)
  Sampling rate      resampled to 250 Hz (stroke 500 -> 250)
  Filter             8-30 Hz Butterworth, order 2, zero-phase (filtfilt)
  Detrend            per-epoch mean removal before filtering
  Energy series      E(t) = x(t)^2 on the filtered signal
  PSD                Welch, 1 s Hamming window, 50% overlap, nfft 512
  Standardisation    z-score, fitted on TRAINING DATA ONLY, applied
                     unchanged to the test set

  Training set       1982 epochs, 50 acute-stroke subjects (990 L / 992 R)
  Test set           72 epochs, our own recordings (22 L / 50 R)

===========================================================================
## THE NINE CANDIDATE FEATURES
===========================================================================

  #   name             definition
  1   C3_mean          mean of E(t) at C3      = band power
  2   C3_median        median of E(t) at C3    = robust band power
  3   C3_skew          skewness of E(t) at C3  = burst asymmetry
  4   C3_kurt          kurtosis of E(t) at C3  = burstiness vs steadiness
  5   C4_mean          the same four at C4
  6   C4_median
  7   C4_skew
  8   C4_kurt
  9   logC3C4          log10( P_C3 / P_C4 ), Welch band power 8-30 Hz

  ERD flavour replaces 1/2/5/6/9 with baseline-normalised versions
  (percent change from that epoch's own 1 s baseline):
     E_C3_mean, E_C3_median, E_C4_mean, E_C4_median, E_logC3C4
  Skewness and kurtosis are affine-invariant, so features 3/4/7/8 are
  numerically IDENTICAL in both flavours.

===========================================================================
## MODEL DEFINITIONS
===========================================================================

  SVM-A   8 features   time domain only
          C3_mean, C3_median, C3_skew, C3_kurt,
          C4_mean, C4_median, C4_skew, C4_kurt

  SVM-B   9 features   time domain + spectral ratio
          the eight above  +  logC3C4

  SVM-C   1 feature    spectral ratio only
          logC3C4

===========================================================================
## HYPERPARAMETERS  -  ROUND 1 (pooled cross-subject model)
===========================================================================

SEARCH PROTOCOL
  BoxConstraint grid   C in {0.01, 0.1, 1, 10}
  KernelScale grid     RBF only: {0.5, 1, 2, 4} x sqrt(nFeatures)
                         nF=1 -> {0.5, 1, 2, 4}
                         nF=8 -> {1.414, 2.828, 5.657, 11.314}
                         nF=9 -> {1.5, 3, 6, 12}
  Selection            5-fold cross-validation with SUBJECT-DISJOINT folds
                       (no subject appears in both train and validation),
                       scored by balanced accuracy
  Solver               SMO, IterationLimit 2e5, ClassNames [1 2]
  Seed                 rng(1234) reset before every configuration

SELECTED VALUES

  model  flavour  kernel   nF   BoxConstraint   KernelScale
  A      abs      linear    8       1            -
  A      abs      rbf       8      10            5.657
  B      abs      linear    9       0.1          -
  B      abs      rbf       9       0.1          1.500
  C      abs      linear    1       0.01         -
  C      abs      rbf       1      10            4.000
  A      erd      linear    8      10            -
  A      erd      rbf       8       0.1          2.828
  B      erd      linear    9      10            -
  B      erd      rbf       9       0.1          3.000
  C      erd      linear    1       0.1          -
  C      erd      rbf       1       0.1          2.000

EVALUATION
  Internal   leave-one-SUBJECT-out over the 50 stroke subjects
  External   the 72 own-recording epochs, never seen in training
  Metrics    balanced accuracy (primary), accuracy, sensitivity,
             specificity, Cohen's kappa, 1000-fold 22-vs-22 balanced
             subsample, 1000-permutation test

===========================================================================
## HYPERPARAMETERS  -  ROUND 2 (per-subject models)
===========================================================================

  No search. Fixed values, to avoid overfitting 40 trials per subject:
      BoxConstraint = 1
      KernelScale   = sqrt(nFeatures)   (RBF only)
      Validation    = 10-fold cross-validation INSIDE each subject
      One model per subject, 50 models per configuration

  model  flavour  kernel   nF   balanced acc   p (uncorrected)
  A      abs      linear    8      0.5385         0.0082
  A      abs      rbf       8      0.5299         0.0427
  B      abs      linear    9      0.5373         0.0277
  B      abs      rbf       9      0.5267         0.0960
  C      abs      linear    1      0.4971         0.8281
  C      abs      rbf       1      0.5019         0.9035
  A      erd      linear    8      0.5242         0.1140
  A      erd      rbf       8      0.5312         0.0334
  B      erd      linear    9      0.5206         0.1575
  B      erd      rbf       9      0.5349         0.0147
  C      erd      linear    1      0.5116         0.4313
  C      erd      rbf       1      0.5138         0.2836

  Report p-values as UNCORRECTED. Across the 16 round-2 configurations
  none survives Benjamini-Hochberg FDR correction (smallest q = 0.107).

===========================================================================
## ONE-SLIDE SUMMARY TABLE
===========================================================================

  model   features                                    n   best C   best gamma-scale
  SVM-A   4 moments x 2 channels                      8   0.1-10   1.4-11.3
  SVM-B   SVM-A + log10(P_C3/P_C4)                    9   0.1-10   1.5-12
  SVM-C   log10(P_C3/P_C4) only                       1   0.01-10  0.5-4

  All three: 8-30 Hz, C3/C4, 4 s window, z-scored on train only,
  linear and RBF kernels both run.
