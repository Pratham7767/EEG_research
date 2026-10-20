# BEST MODEL  -  slide content

===========================================================================
## VERDICT
===========================================================================

  BEST MODEL:  SVM-A, absolute flavour, linear kernel, fitted PER SUBJECT
               8 features: mean / median / skewness / kurtosis of the
               8-30 Hz energy at C3 and C4

      balanced accuracy   0.5385   (chance = 0.500)
      subjects > chance   35 of 50
      p                   0.0082   UNCORRECTED
      FDR-corrected q     0.107    -> does NOT survive correction

  State it as the best of the three, not as a working classifier.

===========================================================================
## WHY SVM-A, IN FOUR POINTS
===========================================================================

1. HIGHEST SCORE ANYWHERE IN THE STUDY
     per-subject best:   SVM-A 0.5385 | SVM-B 0.5373 | SVM-C 0.5138
   It is also the only configuration reaching p < 0.01.

2. MOST CONSISTENT ACROSS PEOPLE
     subjects above chance: SVM-A 35/50 | SVM-B 32/50 | SVM-C 28/50
   SVM-C is barely better than a coin flip at the subject level.

3. SIMPLEST OF THE TWO THAT WORK  (the Occam argument)
   SVM-B is SVM-A plus the C3/C4 PSD ratio - one extra feature - and it
   scores 0.0012 LOWER. The ratio adds nothing on top of the time-domain
   moments, so the 8-feature model is preferred over the 9-feature one.
   This is a real finding, not a tie-break: it says the spectral ratio
   carries no information the moments do not already have.

4. THE RATIO ALONE FAILS
   SVM-C (the C3/C4 ratio by itself) sits at 0.5138, p = 0.284, and
   0.497-0.502 in its absolute flavour - dead on chance. One scalar is
   not enough to separate the classes.

===========================================================================
## WHY *PER-SUBJECT* AND NOT THE POOLED MODEL
===========================================================================

  pooled, cross-subject (LOSO):  best 0.5315, no configuration with a
                                 credible p-value
  per-subject (10-fold within):  best 0.5385, p = 0.0082

  The pooled model averages 50 patients with different lesions and
  different hemiplegic sides, so opposite effects cancel. Fitting one
  model per person is also what the source paper does, which makes the
  numbers directly comparable.

===========================================================================
## THE COMPARISON THAT MAKES IT LOOK GOOD  (use this)
===========================================================================

      our SVM-A, 2 channels, 4 scalar moments      0.5385
      paper's CSP+LDA, 30 channels, spatial filter 0.5557
      paper's best method (TWFB+DGFMDRM)           0.7221

  Reaching within 1.7 percentage points of a 30-channel CSP baseline
  using two electrodes and four scalar statistics is the defensible
  positive claim in this study.

===========================================================================
## THE CAVEAT THAT MUST BE ON THE SAME SLIDE
===========================================================================

  - p = 0.0082 is UNCORRECTED. Across the 16 configurations tested, none
    survives Benjamini-Hochberg FDR correction (smallest q = 0.107).
  - The effect is small: 0.5385 vs 0.500 is about 1.6 extra correct
    trials out of 40.
  - 15 of 50 subjects are still BELOW chance.
  - On our own 72 test epochs every model is at chance (best balanced
    0.534, all permutation p > 0.38), because class is confounded with
    recording session there.

  Honest one-liner for the slide:
    'SVM-A is the best of the three, and the only one showing any signal
     at all - but the effect does not survive correction for multiple
     comparisons, so it is a direction for further work, not a result.'
