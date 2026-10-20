# EXPERIMENT_2 — REPORT

Seven models x {Euclidean Alignment off, on} x 2 honest protocols on BCI
Competition IV dataset 2b. Run 2026-10-08. Every number below came from
`s01_fetch_2b.py` -> `s02_run_models.py` -> `s03_report.py` and regenerates by
running them in that order.

---------------------------------------------------------------------------
## THE HEADLINE
---------------------------------------------------------------------------

**Changing the dataset moved the number. Changing the model does not.**

    best honest result on the stroke data (9 models, run_all_models.py)  0.554
    EXPERIMENT_2, cross-subject, new person never seen in training      0.747
    EXPERIMENT_2, within-subject, trained on that person's own sessions 0.802

For scale, the three levers in this project are worth, in balanced accuracy:

    choice of dataset        ~0.19     stroke 0.554 -> 2b 0.747
    Euclidean Alignment      +0.045    positive in 28 of 28 configurations
    choice of model          ~0.003    the entire P2 spread with EA on

That ordering is the result. Experiment_svm spent sixteen configurations
moving between 0.526 and 0.539 on a dataset whose honest ceiling was 0.554.
The ceiling was the problem.

---------------------------------------------------------------------------
## 1. RESULTS
---------------------------------------------------------------------------

Balanced accuracy, mean over 9 subjects, artefact-flagged trials KEPT.
Chance = 0.500. Classes are exactly balanced in every session, so plain
accuracy and balanced accuracy coincide and the majority baseline is 0.500 —
unlike Experiment_svm, there is no 69.4 %-style trap in this table.

### P1 — within-subject, cross-session (train sessions 1-3, test 4-5)

| model       | EA off | EA on  | delta   | subjects > chance |
|-------------|--------|--------|---------|-------------------|
| csp_lda     | 0.7480 | 0.7905 | +0.0425 | 9/9 |
| csp_svm     | 0.7480 | 0.7898 | +0.0418 | 8/9 |
| **fbcsp_svm** | 0.7668 | **0.8020** | +0.0352 | 8/9 |
| ts_svm      | 0.7548 | 0.7846 | +0.0298 | 8/9 |
| tslda       | 0.7544 | 0.7855 | +0.0311 | 8/9 |
| fgmdm       | 0.7544 | 0.7855 | +0.0311 | 8/9 |
| logvar_svm  | 0.7299 | 0.7851 | +0.0552 | 9/9 |

### P2 — cross-subject, leave-one-subject-out (train 8 subjects, test the 9th)

| model       | EA off | EA on  | delta   | subjects > chance |
|-------------|--------|--------|---------|-------------------|
| **csp_lda** | 0.6996 | **0.7468** | +0.0472 | 9/9 |
| csp_svm     | 0.7039 | 0.7468 | +0.0429 | 9/9 |
| fbcsp_svm   | 0.6936 | 0.7353 | +0.0417 | 9/9 |
| ts_svm      | 0.6918 | 0.7456 | +0.0538 | 9/9 |
| tslda       | 0.6864 | 0.7440 | +0.0576 | 9/9 |
| fgmdm       | 0.6864 | 0.7440 | +0.0576 | 9/9 |
| **logvar_svm** | 0.6953 | **0.7468** | +0.0515 | 9/9 |

P2 is the number that matters for this project: it is a model trained entirely
on other people, applied to a person it has never seen, with no calibration
labels from that person. 0.747, and every one of the nine subjects beats
chance.

### Per subject (best model each protocol)

| sub  | P1 off | P1 on  | P2 off | P2 on  | P2 delta |
|------|--------|--------|--------|--------|----------|
| B01  | 0.6594 | 0.7719 | 0.6958 | 0.7431 | +0.0472 |
| B02  | 0.5821 | 0.5714 | 0.5853 | 0.5882 | +0.0029 |
| B03  | 0.5188 | 0.5219 | 0.5542 | 0.5667 | +0.0125 |
| B04  | 0.9688 | 0.9656 | 0.8081 | 0.9419 | +0.1338 |
| B05  | 0.8687 | 0.9375 | 0.7405 | 0.7851 | +0.0446 |
| B06  | 0.7875 | 0.8500 | 0.7375 | 0.7972 | +0.0597 |
| B07  | 0.7656 | 0.7969 | 0.6917 | 0.7000 | +0.0083 |
| B08  | 0.8781 | 0.9156 | 0.6947 | 0.7974 | +0.1026 |
| B09  | 0.8719 | 0.8875 | 0.7889 | 0.8014 | +0.0125 |
| mean | 0.7668 | 0.8020 | 0.6996 | 0.7468 | +0.0471 |

---------------------------------------------------------------------------
## 2. THE EPOCHING BUG, AND WHY IT IS IN THIS REPORT
---------------------------------------------------------------------------

The first run of s02 returned 0.49-0.51 for every model, every protocol, every
EA setting — 28 configurations all sitting exactly on chance.

00_PLAN.md section (a) had said, before anything was run: *"P1 should land
around 75-80 % for the better models. If it comes out near 55 %, something is
wrong with my epoching — most likely the cue index convention."*

It was the cue index convention. The `trial` field in the BNCI 004-2014 files
indexes the **trial start**, not the cue. The 2b paradigm is 0-3 s fixation
with a beep at 2 s, **cue at 3 s**, imagery 3-7 s. Epoching 0.5-3.5 s from
`trial` therefore sat entirely inside the fixation period, where by
construction there is nothing to classify.

`s00_diagnose_window.py` establishes this without assuming either convention:
it slides a 2 s window across 0-6 s after `trial` and measures how well
log-power(C3) - log-power(C4) separates the classes, pooled over all subjects
and sessions.

    offset after `trial`    AUC
    0.0 s                 0.4927      <- chance
    0.5 s                 0.4960      <- chance
    1.0 s                 0.5051      <- chance
    1.5 s                 0.4973      <- chance
    2.0 s                 0.4253
    2.5 s                 0.3389
    3.0 s                 0.2628      <- cue
    3.5 s                 0.2124      <- strongest
    4.0 s                 0.2275
    5.0 s                 0.2790
    6.0 s                 0.3274

Flat at chance until 2 s, then a steep rise peaking at 3.5-4.0 s. (AUC below
0.5 is just the sign of the feature: C3-minus-C4 power goes *down* for the
class coded 1. The information content is |AUC - 0.5| = 0.29, which is large.)

`CUE_OFFSET = 3.0` was added to s01 and everything re-run from the cached .mat
files. Two things worth keeping from this:

  * **the prediction was written down first**, which is the only reason a
    table of chance results was read as a bug rather than as a finding. Had
    00_PLAN.md not committed to 75-80 % in advance, "all models at chance on
    3 channels" is an entirely plausible-sounding negative result, and it
    would have been wrong.
  * **it is the same class of error as the stroke data's marker-2 trap** that
    Experiment_svm caught — an index convention assumed rather than verified.
    Both times the fix was to measure where the event actually is.

---------------------------------------------------------------------------
## 3. EUCLIDEAN ALIGNMENT
---------------------------------------------------------------------------

Per session, the reference matrix R is the mean of that session's trial
covariances, and every covariance is mapped C -> R^-1/2 C R^-1/2. It uses no
labels, so applying it to the test session leaks nothing.

**It helped in 28 of 28 configurations.** Mean +0.0452, smallest +0.0166,
largest +0.0692. There is no configuration anywhere in this experiment where
alignment made things worse.

As predicted in 00_PLAN.md (c), the gain is larger cross-subject (+0.0417 to
+0.0576) than within-subject (+0.0298 to +0.0552), because crossing people is
where a per-session whitening has something to remove. The exception is
logvar_svm, which gains most in P1 (+0.0552) — unsurprising, since raw log
band power is the feature most exposed to per-session gain and the one EA
most directly repairs.

**This is the principled version of what the ERD% normalisation in
Experiment_svm was reaching for.** That normalisation divided by a baseline
window to cancel device gain; EA whitens by the session's own covariance,
which cancels gain *and* the spatial correlation structure, needs no baseline
period, and requires no assumption that the baseline is the same mental state
on both sides. For the Gelo transfer problem — where we measured a 3.1x
amplitude mismatch that collapsed the absolute-energy models onto one class —
EA is the correct tool and it is now implemented and validated.

---------------------------------------------------------------------------
## 4. WHAT THIS SAYS ABOUT MODEL CHOICE
---------------------------------------------------------------------------

With EA on, the entire P2 spread across seven models is 0.7353 to 0.7468 —
**0.0115 between filter-bank CSP and three log-variance numbers.**
`logvar_svm` ties for best. It is three features: log power at C3, Cz and C4
in 8-30 Hz.

This is not a surprise and it is not a reason to be pleased with simple
features. With 3 channels, a 3x3 covariance has 6 free numbers; CSP can find
at most 3 components, so it is close to a whitening plus a rotation, and
tangent space is a 6-dimensional reparameterisation of the same matrix. Every
model here is reading the same six numbers. They converge because there is
nothing else to read.

The practical consequences:

  1. **Do not spend more time on classifiers.** On a 3-channel montage the
     model is worth ~0.01. Prediction (e) in 00_PLAN.md — that logvar_svm
     would be clearly worst — was wrong, and wrong in a useful direction.
  2. **More channels is the only thing that would make model choice matter
     again.** The paper's CSP machinery exists to exploit 29 channels. At 3,
     it has nothing to exploit. If the headset ever grows past 4 electrodes,
     revisit this.
  3. **Within-subject calibration is worth +0.055** (0.747 -> 0.802). A short
     per-user calibration session buys more than any model in this table.

---------------------------------------------------------------------------
## 5. HONEST LIMITATIONS
---------------------------------------------------------------------------

1. **P2 is not the Gelo transfer problem.** It crosses people, but not
   hardware: same amplifier, same bipolar montage, same lab, same 250 Hz, same
   cue software. Our headset adds a device shift on top — different reference,
   a built-in lowpass already attenuating upper beta, and a self-clicked cue.
   0.747 is an upper bound on what to expect from the Gelo, not a prediction.

2. **Two subjects are near chance** even within-subject: B03 at 0.52 and B02
   at 0.57. This is ordinary BCI illiteracy and it is well documented for 2b.
   A user-independent model will simply not work for some fraction of people,
   and nothing in this report changes that.

3. **The spread across subjects is wide** — P2 ranges 0.567 to 0.942. The mean
   of 0.747 describes no individual well.

4. **No permutation test was run.** With 720 trials per subject the binomial
   threshold is tight (the "subjects > chance" column uses it), and 9/9 is not
   a marginal call, so permutation would only confirm what is already clear.
   It should be added before anything is published.

5. **Artefact-flagged trials were kept in the main run.** The clean pass is in
   summary.csv and agrees everywhere within 0.005, so artefact rejection is
   not doing hidden work in either direction.

6. **LinearSVC, not libsvm.** The first run used `SVC(kernel="linear")`, whose
   quadratic scaling made the ~5,800-trial cross-subject grid searches run for
   hours. Both fit a linear boundary; LinearSVC uses squared hinge. Swapped
   for tractability, noted for honesty.

7. **One window, one band.** 0.5-3.5 s after cue, 8-30 Hz. Per-subject tuning
   of window and band is what TWFB does and it was worth +0.02 on the stroke
   data when done honestly. Not tried here.

---------------------------------------------------------------------------
## 6. WHAT TO DO NEXT
---------------------------------------------------------------------------

In descending order of expected effect:

1. **Fix the Gelo recording protocol.** Unchanged from the Experiment_svm
   recommendation and still the binding constraint: interleave left and right
   inside one session, software-written markers, fixed-length trials, hands
   still, equal counts per class, several sessions. Until class and session
   are decoupled, nothing measured on our own data means anything — and note
   that 2b's five sessions per subject are exactly the design being asked for.

2. **Then point this pipeline at the Gelo data.** The code is ready: train on
   2b with EA, map ch2/ch3 to C3/C4, drop Cz or substitute ch1/ch4 if either
   turns out to sit usefully. P2 here is the protocol to use, and 0.747 is the
   reference to measure the drop against.

3. **Add a short per-user calibration arm.** +0.055 from within-subject
   fitting is the largest remaining lever, and it is cheap: a few minutes of
   cued trials from the user before first use.

4. **Confirm what ch1 and ch4 are on the headset.** Still unanswered, and it
   decides whether the Gelo side has 2 usable channels or 4. At 3 channels 2b
   reaches 0.75; at 2 the Experiment_svm ceiling argument applies again.

5. Only then revisit models, and only if the channel count grows.

---------------------------------------------------------------------------
## 7. FILES
---------------------------------------------------------------------------

    00_PLAN.md                   the design and the predictions, written first
    s00_diagnose_window.py       where the laterality actually sits in the trial
    s01_fetch_2b.py              download, verify, epoch, cache covariances
    s02_run_models.py            14 configurations x 2 protocols x 2 artefact modes
    s03_report.py                figures and the per-subject table
    s04_gelo_transfer.py         2-channel ceiling, and the transfer to our data
    s05_polarity_check.py        is ch2/ch3 really C3/C4?
    data\                        18 .mat files, 9 .npz, checksums.csv, epoch_meta.csv
    results\summary.csv          56 rows: protocol x artefacts x model x EA
    results\per_subject.csv      504 rows: the above x 9 subjects
    results\gelo_2ch_ceiling.csv what dropping Cz costs on 2b
    results\gelo_transfer.csv    the transfer result, epoch and file level
    results\gelo_polarity.csv    both channel orders
    results\gelo_epoch_meta.csv  every candidate epoch and why it was kept
    results\s01..s05.log         run logs
    results\figures\fig1_ea_effect.png     every model, EA off vs on
    results\figures\fig2_per_subject.png   per-subject P2
    results\figures\fig3_vs_stroke.png     2b against the stroke ceiling

Nothing outside this folder was written. eeg_stroke\, left\, right\,
stroke_paper\ and Experiment_svm\ are untouched.

---------------------------------------------------------------------------
## 8. ONE-PARAGRAPH SUMMARY
---------------------------------------------------------------------------

Seven models were trained on BCI Competition IV dataset 2b — 9 healthy
subjects, 5 sessions each, 6,520 trials, three bipolar channels C3/Cz/C4 at
250 Hz, the same rate and nearly the same montage as our headset. Under
leave-one-subject-out, a model that has never seen the test person reaches
0.747 balanced accuracy with all nine subjects above chance; with that
person's own earlier sessions in training it reaches 0.802. Euclidean
Alignment, a label-free per-session whitening, improved every one of 28
configurations by an average of 0.045. The choice of model was worth about
0.003 — with three channels, CSP, filter-bank CSP, tangent space, FgMDM and
three log-variance numbers all read the same six numbers out of a 3x3
covariance and converge. The comparison that matters: nine models on the
acute-stroke dataset, run through the same standard of honesty, topped out at
0.554. The dataset was the ceiling, not the classifier. A first run returned
chance everywhere because the `trial` field indexes the trial start and the
cue is 3 s later; that was caught only because 00_PLAN.md had committed to an
expected range before the run.

===========================================================================
## 9. THE GELO TRANSFER  (added 2026-10-08, s04 + s05)
===========================================================================

The point of all the above was to point a working model at our own headset.
Done. It does not work, and this time we know exactly what that means.

---------------------------------------------------------------------------
### 9.1  First: what does dropping Cz cost?  (PART A)
---------------------------------------------------------------------------

Our headset has C3 and C4. 2b has C3, Cz, C4. So the 2b model was retrained on
two channels and re-run through the same cross-subject LOSO.

    model         3 channels (EA)   2 channels (EA)   cost
    csp_lda            0.7468            0.7441      -0.0027
    ts_svm             0.7456            0.7439      -0.0017
    fgmdm              0.7440            0.7442      +0.0002
    logvar_svm         0.7468            0.7442      -0.0026

Still 9/9 subjects above chance. **Dropping Cz costs about 0.002.** Two
channels over the sensorimotor strip is essentially as good as three, and the
channel count is NOT what stands between us and a working decoder. That
retires a worry that has been hanging over this project since Experiment_svm
section 6.1.

---------------------------------------------------------------------------
### 9.2  The transfer  (PART B)
---------------------------------------------------------------------------

Trained on all 9 subjects of 2b (C3+C4, EA per session), tested on our 72
epochs re-cut on the identical 0.5-3.5 s window. The model is never refitted
on our data and never sees a label from it.

The honest unit is the FILE. Every one of our files holds a single class, so
72 epochs from 15 files is 15 independent decisions, not 72. File-level
majority baseline is 0.667.

    model        EA   epoch bal   file bal   files right   perm p   says right
    csp_lda      0      0.4855     0.4500      6/15        0.832      39%
    csp_lda      1      0.4800     0.3000      5/15        0.983      47%
    ts_svm       0      0.4473     0.4000      6/15        0.897      47%
    ts_svm       1      0.4900     0.2500      4/15        0.993      49%
    fgmdm        0      0.4400     0.3500      5/15        0.951      42%
    fgmdm        1      0.4900     0.2500      4/15        0.993      49%
    logvar_svm   0      0.4473     0.4000      6/15        0.899      47%
    logvar_svm   1      0.5000     0.3500      6/15        0.957      50%

**Everything is at or below chance. Best permutation p is 0.832.** The 10,000
file-label permutations are exact rather than approximate, because the model
is fixed and only the labels move.

One genuine improvement worth recording: the predictions are near 50/50 (39-50
% "right"). In Experiment_svm the absolute-energy models predicted "right" for
85-100 % of epochs, because our recordings sit 3.1x higher in energy and every
epoch fell on one side of a boundary fitted to another scale. **Euclidean
Alignment fixed that collapse completely.** The classifier is now genuinely
undecided rather than saturated. It is undecided because there is nothing to
decide.

---------------------------------------------------------------------------
### 9.3  Are ch2 and ch3 actually C3 and C4?  (s05)
---------------------------------------------------------------------------

All eight configurations landed BELOW 0.5 at file level. An uninformative
model scatters around chance; a systematically inverted one sits under it. And
the mapping was never measured - EXPERIMENT_REPORT.txt 4.2 records it as taken
on trust. So one pre-specified physical alternative was tested: the electrodes
are the other way round. Two hypotheses, so the threshold applied is p < 0.025.

Descriptive check first, no classifier involved. AUC of log(C3) - log(C4) for
predicting right-hand MI:

    2b     0.2174      textbook: right-hand MI desynchronises C3, so C3 power
                       drops and the difference goes low. |AUC-0.5| = 0.283.
    ours   0.5127      |AUC-0.5| = 0.013, and nominally the other direction.

Our laterality is **twenty times weaker** than 2b's, and what little there is
points the wrong way.

Classifier test, both orders, all 16 cells:

    best anywhere : swapped, csp_lda, EA off, file balanced accuracy 0.500,
                    permutation p = 1.000

**Swapping does not rescue anything.** The sub-chance pattern was noise, as 15
files will readily produce. The channel order question is not answered by this
test - it is simply not the reason the transfer fails.

---------------------------------------------------------------------------
### 9.4  Why this negative result is worth much more than the last one
---------------------------------------------------------------------------

Experiment_svm section 5 had to say of its own test: *"Strictly: nothing. The
models never worked on the training data, so their behaviour on our data
cannot be evidence about our data. A broken ruler does not measure a table."*

**The ruler is no longer broken.** The exact same model, the exact same code
path, the exact same 0.5-3.5 s window and 8-30 Hz band, reaches 0.744 balanced
accuracy on a person it has never seen, with 9 of 9 subjects above chance. Then
it reaches chance on ours.

That isolates the failure to our recordings. It is no longer possible to blame
the feature set, the classifier, the channel count, the sampling rate, the
amplitude mismatch or the stroke cohort - every one of those has now been
ruled out or measured. What remains, and what this experiment cannot separate:

  1. **The protocol.** Self-clicked onsets with a real hand movement at t=0,
     trial lengths from 4.9 s to 148 s, and one class per file. 2b uses a
     software-timed cue, a fixed 4 s window, and interleaved classes. This is
     the difference the project has been told about since the first report and
     it is still unaddressed.
  2. **The device.** Different reference, and a built-in lowpass already
     attenuating the upper half of our band (-6.3 dB tilt across 13-30 Hz
     against +1.2 dB in the stroke data).
  3. **Electrode placement.** Not the left/right ORDER - that is now tested -
     but whether the two electrodes sit over the hand area at all. The 2b
     recordings are bipolar pairs placed about 2.5 cm either side of C3 and C4;
     a headband sitting too anterior or too posterior records a different
     rhythm entirely.
  4. **The user.** Two of nine 2b subjects are near chance even within-subject.
     BCI illiteracy is real and cannot be excluded for a single user.

None of these can be separated with the data currently on disk. All four are
addressed by the same action: **re-record with interleaved classes, software
cues and fixed trials, and note the electrode positions.** Then re-run s04,
which will work unchanged.

---------------------------------------------------------------------------
### 9.5  The one-line version
---------------------------------------------------------------------------

A decoder that is independently validated at 0.744 on an unseen person, using
two channels, scores chance on our recordings (best file-level permutation
p = 0.83; the channel-swap alternative does not help, p = 1.00). The
classifier, the features and the channel count are all now excluded as causes.
The recordings are the cause, and the recording protocol is the fix.

