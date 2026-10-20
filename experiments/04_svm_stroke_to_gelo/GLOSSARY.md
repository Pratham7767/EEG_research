# GLOSSARY  -  every term used in this experiment

Written for the slides. Each entry: what it is, why it is here, and the
number from our own results that shows it.

===========================================================================
## 1.  abs vs erd   (the two flavours)
===========================================================================

Every model was run twice, on the same epochs, differing only in how the
power was expressed.

ABS = ABSOLUTE ENERGY
  The raw squared amplitude of the filtered signal, in the recording's own
  units. E(t) = x(t)^2, then mean / median / skewness / kurtosis of that.
  Problem: it carries the recording device. Electrode contact, amplifier
  gain, skull thickness and hair all scale it. Measured here: our median
  C3_mean is 17.73 against the stroke data's 5.64, a factor of 3.1 - and
  that is hardware, not brain.

ERD = BASELINE-NORMALISED (event-related desynchronisation)
  The same energy, expressed as percent change from that same epoch's own
  1-second pre-onset baseline:

      ERD% = (E_imagery - E_baseline) / E_baseline  x 100

  Negative = power fell during imagery = that patch of cortex activated.
  Positive = power rose = ERS, the opposite.
  Because every epoch is divided by its OWN baseline, the device gain
  cancels. This is why the erd flavour is the one that transfers between
  two different headsets.

  Measured ERD% (median):
      stroke, left hand   C3  -4.8%   C4  -4.9%
      stroke, right hand  C3  -7.7%   C4 -12.1%     <- real ERD
      our data, left hand C3 +15.3%   C4 +42.1%     <- ERS, the wrong sign

IMPORTANT DETAIL worth a footnote on the slide:
  ERD% is an AFFINE transform of E (a scale and a shift). Skewness and
  kurtosis are invariant under affine transforms, so C3_skew, C3_kurt,
  C4_skew and C4_kurt are NUMERICALLY IDENTICAL in both flavours. Only
  mean, median and the ratio actually change.

===========================================================================
## 2.  Signal-processing terms
===========================================================================

ERD / ERS
  Event-related desynchronisation / synchronisation. When a patch of motor
  cortex becomes active, its 8-30 Hz rhythm gets WEAKER (ERD). At rest it
  is strong (ERS). The brain is cross-wired, so imagining the LEFT hand
  should desynchronise C4 (right hemisphere), and vice versa. That
  asymmetry is the entire signal this experiment hunts for.

MU RHYTHM
  The 8-13 Hz oscillation over sensorimotor cortex. It is the specific
  rhythm that shows ERD during movement and motor imagery. Our recordings
  do contain a clean mu peak near 12 Hz at C4, so the electrodes work.

C3 / C4
  10-10 system electrode positions over left and right motor cortex.
  C3 = left hemisphere = controls the RIGHT hand.
  C4 = right hemisphere = controls the LEFT hand.

BAND POWER
  How much energy the signal carries inside a frequency band (here
  8-30 Hz). Computed either as mean of x(t)^2 after filtering, or by
  integrating the PSD across the band. Both were used; they agree.

PSD  (power spectral density)
  Power per unit frequency - how the signal's energy is distributed across
  frequencies. The x-axis of the spectrum plots.

WELCH'S METHOD
  The standard way to estimate a PSD: cut the signal into overlapping
  windows, take each window's spectrum, average them. Averaging trades
  frequency resolution for a much less noisy estimate. Ours: 1-second
  Hamming window, 50% overlap.

BUTTERWORTH FILTER, ZERO-PHASE
  Butterworth = a filter with a maximally flat passband. Order 2 = gentle
  roll-off. Zero-phase (filtfilt) = the filter is run forwards and then
  backwards, so it introduces NO time shift. That matters because we are
  measuring when power changes relative to a marker.

SKEWNESS  (3rd moment)
  Asymmetry of a distribution. On the energy series it measures whether
  power arrives in occasional large bursts (positive skew) or evenly.
  Ours run around +2.6 to +3.7, i.e. strongly bursty, as EEG should be.

KURTOSIS  (4th moment)
  Tailedness / peakedness. High kurtosis = rare extreme values dominate;
  low = steady. A Gaussian has kurtosis 3. Ours run 11-26, so the energy
  is far spikier than Gaussian - again normal for EEG.

  Why these two at all: mean and median say HOW MUCH power there is;
  skewness and kurtosis say HOW IT IS DISTRIBUTED IN TIME. Two epochs can
  have identical power but different burst structure.

===========================================================================
## 3.  Model terms
===========================================================================

SVM  (support vector machine)
  A classifier that finds the boundary separating two classes with the
  widest possible margin. Only the points nearest the boundary (the
  support vectors) determine it.

LINEAR vs RBF KERNEL
  Linear = the boundary is a straight line / flat plane.
  RBF (radial basis function) = the boundary can curve arbitrarily, by
  implicitly mapping the data into a higher-dimensional space.
  Both were run because we had no reason to assume the classes separate
  linearly. With features this close to noise, it made almost no
  difference: LOSO balanced accuracy spans only 0.493-0.531 across all 12.

BOXCONSTRAINT  (C)
  How harshly the SVM is punished for misclassifying a training point.
  Low C = a wide, soft margin, tolerates errors, simpler boundary.
  High C = a narrow, hard margin, tries to get every training point right,
  risks memorising noise. Searched over {0.01, 0.1, 1, 10}.

KERNELSCALE  (the RBF width; often called gamma or sigma elsewhere)
  How far a single training point's influence reaches. Small scale = each
  point only affects its immediate neighbourhood = very wiggly boundary.
  Large scale = smooth, almost linear. Searched over
  {0.5, 1, 2, 4} x sqrt(number of features).

Z-SCORE / STANDARDISATION
  Rescaling each feature to mean 0 and standard deviation 1, so a feature
  measured in large numbers does not dominate one measured in small ones.
  CRITICAL DETAIL: the mean and SD were computed on the TRAINING data only
  and then applied unchanged to the test set. Computing them on the
  combined data would leak test information into training.

===========================================================================
## 4.  Evaluation terms  -  the ones an examiner will ask about
===========================================================================

ACCURACY
  Fraction of all predictions that are correct. Misleading whenever the
  classes are unbalanced, which ours are (22 left vs 50 right).

MAJORITY-CLASS BASELINE
  The accuracy you get by always guessing the commoner class. Here
  50/72 = 0.694. Any accuracy at or below that is worthless.

BALANCED ACCURACY   <- the primary metric in this study
  The mean of the two per-class recalls, so each class counts equally
  regardless of how many epochs it has. Chance is always 0.500.

  Worked example, SVM-A abs linear, confusion matrix [1 21 ; 5 45]:
      recall LEFT   =  1/22 = 0.045
      recall RIGHT  = 45/50 = 0.900
      balanced acc  = (0.045 + 0.900)/2 = 0.473   <- below chance
      plain accuracy= 46/72 = 0.639                <- looks respectable
  Same model, same predictions, two very different impressions.

SENSITIVITY / SPECIFICITY
  Here: sensitivity = recall on LEFT, specificity = recall on RIGHT.
  They are the two numbers balanced accuracy averages.

COHEN'S KAPPA
  Agreement corrected for the agreement you would get by chance alone.
  0 = no better than guessing; 1 = perfect; negative = worse than chance.
  Ours span -0.104 to +0.050, i.e. from slightly worse than guessing to
  indistinguishable from it. Kappa is immune to the accuracy illusion:
  the 0.694 model has kappa exactly 0.000.

LOSO  (leave-one-subject-out cross-validation)
  Train on 49 of the 50 stroke patients, test on the held-out one, repeat
  50 times. This is the honest way to estimate whether a model generalises
  to a NEW PERSON. Ordinary random k-fold would put trials from the same
  patient in both training and test, so the model could recognise the
  person rather than the task, and the number would be inflated.

SUBJECT-DISJOINT FOLDS
  The same principle applied inside the hyperparameter search: no subject
  appears in both the training and validation half of any fold.

PERMUTATION TEST
  Shuffle the true labels at random, re-score, repeat 1000 times. This
  builds the distribution of scores obtainable from pure noise. The
  p-value is the fraction of shuffles that did as well as the real model.
  High p = the real result is indistinguishable from noise. Our best
  round-1 p is 0.385, i.e. 38% of random shufflings beat or matched it.

FDR  (false discovery rate, Benjamini-Hochberg)
  A correction for testing many configurations at once. Test 16 things at
  p < 0.05 and you expect roughly one 'significant' result by luck alone.
  FDR adjusts the p-values into q-values accordingly. Our best per-subject
  result is p = 0.0082 but q = 0.107 - so it does NOT survive correction,
  and the p-value must be labelled UNCORRECTED on any slide.

AUC  (area under the ROC curve)
  Probability that a randomly chosen left-hand epoch scores higher than a
  randomly chosen right-hand one, on a single feature. 0.5 = chance.
  All nine of our features sit within 0.016 of 0.500 on the training data,
  which is the root cause of everything else in this study.

DOMAIN SHIFT
  When training and test data come from systematically different
  distributions - here two different headsets, montages, references and
  populations. Ours differ by 3.1x in absolute energy, plus a
  frequency-dependent difference from our device's own pre-filtering.
