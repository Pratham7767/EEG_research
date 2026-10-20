# Decoding Left vs Right Hand Motor Imagery from a Two-Channel EEG Headset
## A methods study, a comparative evaluation, and a route forward

Project folder: D:\trainsvm
Written: 8 October 2026

---

# PART I - BACKGROUND, IN PLAIN LANGUAGE

## 1.1 What we are trying to do

When you imagine moving your left hand, the part of your brain that controls it
becomes active. That part sits on the RIGHT side of the head, because the brain
is crossed over. An electrode placed there - called C4 in the standard naming
scheme - can pick up the change. For the right hand, the relevant electrode is
C3 on the left side.

The change itself is a weakening, not a strengthening. At rest, the sensorimotor
cortex produces a steady background rhythm: the mu rhythm at 8-13 Hz and the
beta rhythm at 13-30 Hz. Think of it as an engine idling. When that patch of
cortex gets busy - whether you move, or merely imagine moving - the idling
stops and the rhythm gets quieter. This is called event-related
desynchronisation, or ERD.

So the textbook signature is:

    imagine LEFT hand   ->  rhythm WEAKENS at C4 (right side of head)
    imagine RIGHT hand  ->  rhythm WEAKENS at C3 (left side of head)

A classifier's job is to look at the power at C3 and C4 in those bands and
decide which hand was imagined.

In practice the effect is small, it varies enormously between people, and for
a substantial minority of people it is absent altogether. That last fact has a
name and we return to it in section 5.4.

## 1.2 What a classifier actually sees

The classifier never sees raw EEG. It sees FEATURES: a handful of numbers
computed from each trial. The art is almost entirely in choosing those numbers.

The most useful single object is the COVARIANCE MATRIX of a trial. For a
2-channel recording it is a 2x2 table:

              C3        C4
    C3   [ var(C3)   cov(C3,C4) ]
    C4   [ cov(C3,C4)  var(C4)  ]

Its diagonal is the band power in each channel - exactly the quantity ERD
changes. Its off-diagonal says how the two channels move together. Because the
matrix is symmetric, a 2-channel recording gives **three independent numbers per
trial per frequency band**. That is the whole information budget of this
headset, and it explains a result that recurs throughout this study: the choice
of classifier matters far less than people expect, because every classifier is
reading the same three numbers.

## 1.3 The methods, and what each one adds

**Log band power.** Take the logarithm of the diagonal. Two numbers. The
simplest thing that could possibly work.

**CSP (Common Spatial Patterns).** Instead of looking at C3 and C4 separately,
find the weighted MIXTURE of channels whose power differs most between the two
classes - one mixture tuned to be large for left and small for right, another
the reverse. With many electrodes this is powerful, because it can effectively
synthesise a virtual electrode sitting exactly over the hand area. With 2
channels it can only produce 2 components, so it amounts to a rotation of the
same information.

**FBCSP (Filter-Bank CSP).** Run CSP separately in several narrow frequency
bands (say 4-8, 8-12, 12-16 Hz and so on), then select the most informative
outputs. The motivation is that the exact frequency of a person's mu rhythm
varies - one person peaks at 10 Hz, another at 12. A filter bank lets the
method find each person's band rather than assuming one.

**Riemannian tangent space.** Covariance matrices do not live in ordinary flat
space. They live on a curved surface (a manifold), and the straight-line average
of two covariance matrices is not the natural average of them. The tangent-space
method projects the matrices onto a flat space laid against the curved surface
at the geometric mean, after which ordinary linear classifiers become valid.
On many-channel data this is usually the strongest classical approach.

**SVM (Support Vector Machine).** The classifier itself. Given features, it
finds the boundary separating the two classes with the widest possible margin.
Its main setting is C: large C fits the training data tightly and risks
memorising noise, small C gives a smoother boundary.

## 1.4 The two ideas that decide whether any of this works

Everything above is standard. The two ideas below are where the real gains
turned out to be, and both are about the DATA rather than the model.

**Idea 1: honest evaluation.** To know how good a model is you must test it on
data it did not learn from, and you must not make ANY decision - which band,
which classifier, which settings - by looking at the test score. Two specific
traps bit this project:

  - *Leakage*: pieces of the same recording appearing in both training and test,
    so the model partly recognises data it has seen.
  - *Confounding*: something other than left/right also differs between the
    classes. If every left trial was recorded on Monday and every right trial on
    Tuesday, a model can score beautifully by learning the day.

**Idea 2: alignment.** EEG amplitude varies hugely between people, sessions and
devices - electrode contact, impedance, hair, amplifier gain. A decision
boundary fitted at one scale is meaningless at another. Euclidean Alignment
(He & Wu, 2018) fixes this: for each recording session, compute the average
covariance R over its trials, then transform every covariance

    C  ->  R^(-1/2) C R^(-1/2)

After this each session's own average becomes the identity matrix, so all
sessions arrive at the classifier in a common frame. Critically it uses **no
labels**, so it can be applied to a new user's recording before you know what
they were imagining. It needs no calibration and it is not cheating.

---

# PART II - WHAT WE DID, AND WHAT HAPPENED

## 2.1 Stage one: the acute-stroke dataset

The project began with Liu et al. (2024), a published dataset of 50 acute
stroke patients, 40 motor-imagery trials each, 30 electrodes. The paper reports
up to 72.21 % accuracy.

We could not reproduce it. Re-implementing the authors' own evaluation
procedures and running each one twice - once on the true labels, once on
randomly shuffled labels - showed why:

    procedure (from the authors' code)   true labels   SHUFFLED labels   paper
    FBCSP + SVM                            48.27 %        47.05 %        57.57 %
    TSLDA + FgMDM "fusion"                 54.02 %        47.95 %        61.20 %
    TWFB + FgMDM  (their best)             65.95 %      **63.79 %**      72.21 %

A method that scores 63.79 % on labels containing no information is not
measuring the brain. Reading `TWFB_DGFMDM.m` explains it: the procedure tries
eight frequency bands, each on a fresh random split, and keeps the band with the
highest TEST accuracy. That is selecting on the test set, and the more options
you try the higher the luckiest one scores.

We then ran nine models through one honest protocol - identical folds for every
model, every choice made by inner cross-validation on training data only:

    CSP + LDA                     50.45 %
    FBCSP + SVM                   52.70 %
    Tangent space + SVM           53.30 %
    TSLDA / FgMDM / fusion        53.50 %
    TWFB + FgMDM                  55.40 %   <- best honest result

Only about 12 of 50 patients could be decoded above chance, and it was the same
patients every time. **The ceiling of this dataset is roughly 55 %**, and no
feature set or classifier moves it. In parallel we ran sixteen configurations of
hand-crafted features (mean, median, skewness, kurtosis of the band energy at
C3 and C4, plus the C3/C4 power ratio). They spanned 0.526 to 0.539 balanced
accuracy. A great deal of effort moved the number by thirteen thousandths,
underneath a ceiling of 0.554.

**Lesson: when a long sequence of model changes produces no movement, the
problem is upstream of the model.**

## 2.2 Stage two: changing the dataset

We switched to BCI Competition IV dataset 2b, which suits this project far
better:

  - 9 healthy subjects, 5 sessions each on different days, ~6,520 trials total
  - exactly two classes, left vs right hand, perfectly balanced
  - **three bipolar channels: C3, Cz, C4** - essentially our montage
  - **250 Hz** - our headset's native rate, so no resampling anywhere
  - cues randomised WITHIN each session, so class is not confounded with session
  - a deliberately minimal montage, chosen by its designers to emulate portable
    BCI scenarios

The pipeline: band-pass 8-30 Hz, epoch 0.5-3.5 s after the cue, one covariance
matrix per trial, optional Euclidean Alignment, then one of seven models. Two
evaluation protocols:

  - **P1, within-subject**: train on that person's sessions 1-3, test on 4-5.
  - **P2, cross-subject**: train on 8 subjects, test on the 9th. This is the
    structural analogue of what we actually want - train on public data, use on
    a new person.

## 2.3 The comparative study

Balanced accuracy, mean over 9 subjects. Chance = 0.500, and because the
classes are exactly balanced there is no majority-class trap in this table.

### P1 - within-subject (train sessions 1-3, test 4-5)

| model          | EA off | EA on  | gain from EA |
|----------------|--------|--------|--------------|
| CSP + LDA      | 0.7480 | 0.7905 | +0.0425 |
| CSP + SVM      | 0.7480 | 0.7898 | +0.0418 |
| **FBCSP + SVM**| 0.7668 | **0.8020** | +0.0352 |
| Tangent + SVM  | 0.7548 | 0.7846 | +0.0298 |
| TSLDA          | 0.7544 | 0.7855 | +0.0311 |
| FgMDM          | 0.7544 | 0.7855 | +0.0311 |
| Log variance   | 0.7299 | 0.7851 | +0.0552 |

### P2 - cross-subject, leave-one-subject-out

| model          | EA off | EA on  | gain from EA | subjects > chance |
|----------------|--------|--------|--------------|-------------------|
| **CSP + LDA**  | 0.6996 | **0.7468** | +0.0472 | 9/9 |
| CSP + SVM      | 0.7039 | 0.7468 | +0.0429 | 9/9 |
| FBCSP + SVM    | 0.6936 | 0.7353 | +0.0417 | 9/9 |
| Tangent + SVM  | 0.6918 | 0.7456 | +0.0538 | 9/9 |
| TSLDA          | 0.6864 | 0.7440 | +0.0576 | 9/9 |
| FgMDM          | 0.6864 | 0.7440 | +0.0576 | 9/9 |
| **Log variance**| 0.6953 | **0.7468** | +0.0515 | 9/9 |

### The three levers, measured

    choice of dataset        ~0.19     stroke 0.554  ->  2b 0.747
    Euclidean Alignment      +0.045    positive in 28 of 28 configurations
    choice of model          ~0.003    the entire P2 spread with EA on

**Euclidean Alignment helped in every single one of 28 configurations**: mean
+0.045, smallest +0.017, largest +0.069. The choice between filter-bank CSP and
three log-variance numbers was worth 0.0115, and log variance tied for best
cross-subject. This is the 2x2-covariance argument from section 1.2 showing up
in the measurements.

## 2.4 A bug worth describing

The first run of this experiment returned 0.49-0.51 for every model, every
protocol, every alignment setting - 28 configurations sitting exactly on chance.

The project's plan document, written BEFORE the run, had said: *"P1 should land
around 75-80 %. If it comes out near 55 %, something is wrong with my epoching -
most likely the cue index convention."*

It was the cue index convention. The `trial` field in the 2b files indexes the
TRIAL START; the paradigm is 3 s of fixation, then the cue, then 4 s of imagery.
Our window sat entirely inside the fixation period, where by construction there
is nothing to classify.

A diagnostic that assumes neither convention - slide a 2 s window across the
trial and measure how well C3-minus-C4 power separates the classes - located it
immediately:

    offset after `trial`:  0.0s  0.5s  1.0s  1.5s  2.0s  2.5s  3.0s  3.5s  4.0s
    AUC:                  0.493 0.496 0.505 0.497 0.425 0.339 0.263 0.212 0.228
                          <------ chance ------>              cue   peak

(AUC below 0.5 is just the sign of the feature: right-hand imagery
desynchronises C3, so C3-minus-C4 power goes DOWN. That is the textbook
direction, measured.)

**This matters as methodology, not just as a fix.** A table of chance results is
a perfectly plausible-looking negative finding - "three channels is not enough"
would have been believed. Writing the expected range down in advance is the only
reason it was read as a bug.

## 2.5 Stage three: testing our own headset

Our recordings: a Gelo BCI headband, 4 live electrodes of 8, ch2 and ch3 taken
as C3 and C4, 250 Hz, 15 files, 72 usable epochs.

**First, what does dropping Cz cost?** The 2b model was retrained on C3+C4 only:

    model           3 channels    2 channels    cost
    CSP + LDA         0.7468        0.7441    -0.0027
    Tangent + SVM     0.7456        0.7439    -0.0017
    FgMDM             0.7440        0.7442    +0.0002
    Log variance      0.7468        0.7442    -0.0026

Still 9/9 subjects above chance. **Two electrodes are as good as three.** The
channel count is not the obstacle.

**Then the transfer.** Trained on all nine 2b subjects, tested on our 72 epochs
with the identical window and band. Because each of our files holds a single
class, the honest unit is the file - 15 decisions, not 72.

| model | EA | epoch bal. | file bal. | files correct | permutation p |
|-------|----|-----------|-----------|---------------|---------------|
| CSP + LDA | off | 0.486 | 0.450 | 6/15 | 0.832 |
| CSP + LDA | on  | 0.480 | 0.300 | 5/15 | 0.983 |
| Tangent   | off | 0.447 | 0.400 | 6/15 | 0.897 |
| Tangent   | on  | 0.490 | 0.250 | 4/15 | 0.993 |
| FgMDM     | on  | 0.490 | 0.250 | 4/15 | 0.993 |
| Log var   | on  | 0.500 | 0.350 | 6/15 | 0.957 |

**Everything is at chance.** Best permutation p is 0.832 over 10,000 exact
file-label shuffles.

Because every configuration landed slightly BELOW chance, we tested one
pre-specified physical alternative - that ch2 and ch3 are swapped - with a
Bonferroni-corrected threshold of p < 0.025. Best result anywhere: 0.500 at
p = 1.000. Swapping does not rescue it.

A descriptive check without any classifier makes the situation clearest. AUC of
log(C3) - log(C4) for predicting right-hand imagery:

    2b        0.2174     |AUC - 0.5| = 0.283   textbook contralateral ERD
    our data  0.5127     |AUC - 0.5| = 0.013   twenty times weaker

**Why this negative result is strong.** An earlier report in this project had to
say of its own test: *"the models never worked on the training data, so their
behaviour on our data cannot be evidence about our data. A broken ruler does not
measure a table."* That is no longer the situation. The same model, same code,
same window, same band reaches 0.744 on a person it has never seen, with 9 of 9
subjects above chance - and then reaches chance on ours. The failure is isolated
to the recordings.

One genuine improvement is worth recording: predictions came out 39-50 % "right".
In the earlier experiment, absolute-energy models predicted "right" for 85-100 %
of epochs because our recordings sit 3.1x higher in energy and every epoch fell
on one side of a boundary fitted to another scale. **Euclidean Alignment removed
that collapse entirely.** The classifier is now genuinely undecided rather than
saturated - undecided because there is nothing to decide.

## 2.6 Stage four: how much calibration data would a new user need?

If a new user records some labelled trials of their own, how fast does accuracy
climb? We measured this on 2b: start from the model trained on 8 other subjects,
add N labelled trials from the target, test on the target's held-out sessions.
Each N repeated 10 times with different random draws.

| trials | minutes | public data + N, concatenated | + N, up-weighted | N only, no public data |
|--------|---------|-------------------------------|------------------|------------------------|
| 0   |  0  | 0.7678 | 0.7678 | -- |
| 10  |  1  | 0.7681 | 0.7584 | 0.7017 |
| 20  |  3  | 0.7683 | 0.7637 | 0.7430 |
| 40  |  5  | 0.7684 | 0.7694 | 0.7591 |
| 80  | 11  | 0.7684 | 0.7713 | 0.7644 |
| 160 | 21  | 0.7681 | 0.7704 | 0.7688 |
| 320 | 43  | 0.7691 | 0.7708 | 0.7733 |

Three findings, two of them surprising:

1. **Calibration barely helps.** 320 of the user's own trials - 43 minutes in
   the chair - moves accuracy by less than 0.01. Once Euclidean Alignment is in
   place, **the alignment does the work that calibration would otherwise do.**
   This is good news practically: a zero-calibration decoder is viable.

2. **Naive concatenation wastes calibration data entirely** (+0.001 at 320
   trials). 5,760 source trials simply drown 320 target trials. Up-weighting the
   target to half the training mass recovers a little (+0.004 at 80 trials) but
   not much. If anyone reports large gains from "adding calibration data", check
   how they weighted it.

3. **The public dataset is worth about 160 trials - 21 minutes - of the user's
   own time**, which is where the calibration-only curve crosses the transfer
   line.

---

# PART III - WHAT THE LITERATURE SAYS WOULD HELP

We surveyed current methods against this project's specific constraints: two
channels, a consumer headset, one user, and a small dataset.

## 3.1 Deep learning

EEGNet is a compact convolutional network widely used for BCI. The honest
finding across the literature is that **it does not beat classical methods on
motor imagery**. In its own paper, on the sensorimotor-rhythm task, EEGNet-8,2
achieved performance comparable to the established FBCSP method and
ShallowConvNet. Independent comparisons agree, with one noting it is
interesting that FBCSP with regularised LDA performs motor-imagery
classification as well as EEGNet even though it is not deep learning.

Analysis of what EEGNet learns explains why: comparison with FBCSP revealed
significant correlations between EEGNet's learned spatial filters and FBCSP's
optimal spatial patterns, suggesting the network implicitly rediscovers the same
variance-maximising features. On 22-channel data it rediscovers CSP. On 2
channels there is almost nothing to rediscover.

**Verdict for this project: not worth it.** It would add large complexity, a
GPU dependency and substantial overfitting risk to recover features we already
compute in closed form.

## 3.2 Data augmentation

The most thorough study compared 13 augmentations across two tasks, datasets and
models, and found that adequate augmentation can bring up to 45 % accuracy
improvement in low-data regimes - but also that there is no single best
augmentation strategy, as the good augmentations differ by task. A later study
on 12 augmentation methods confirmed the double edge: augmentation can
significantly affect classification accuracy, with some methods degrading
performance while others improve generalisation.

**Verdict: relevant only once a deep model is in use, and only with careful
validation.** Augmentation addresses overfitting. Our classical pipeline with
three features per trial is not overfitting - it is reading data that contains
no signal. Augmenting noise produces more noise.

## 3.3 Transfer learning and alignment

Already implemented, and the single largest methodological gain in this project.
Euclidean Alignment aligns EEG trials directly in Euclidean space, so any
downstream processing can be applied to the aligned trials; its computational
cost is very low; and it is unsupervised, needing no label information from the
new subject. It outperformed Riemannian alignment and several no-alignment
approaches, and generally improves decoding accuracy especially for shared
cross-subject models.

One caveat for future work: aligning across datasets recorded with different
acquisition systems, electrode numbers and positions remains an open problem,
because those differences introduce heterogeneous feature spaces. Our 2b-to-Gelo
transfer is exactly that harder case.

## 3.4 Self-supervised pretraining (JEPA and EEG foundation models)

Joint Embedding Predictive Architectures learn by predicting latent
representations rather than reconstructing the raw signal. Signal-JEPA was built
specifically for cross-dataset transfer, with a domain-specific spatial block
masking strategy, evaluated on 54 subjects across motor imagery, ERP and SSVEP.
Its central conclusion is directly relevant: the results highlight the
importance of spatial filtering for accurate downstream classification.

Related work includes EEG-VJEPA, which models multi-channel EEG as
spatiotemporally masked sequences and reaches state-of-the-art on the TUH
Abnormal dataset, and Laya, a LeJEPA-based EEG foundation model. The motivation
behind Laya is itself a warning about the whole family: reported improvements of
EEG foundation models over smaller task-specific models are often modest,
sensitive to downstream adaptation and fine-tuning strategy, and limited under
linear probing.

**Verdict: a legitimate future-work section, not a route to accuracy here.**
These models are pretrained on tens of thousands of sessions. We have 6,520
training trials and 72 test epochs, on two channels.

## 3.5 Reinforcement learning

RL needs a reward signal and a loop to close. On a fixed offline dataset with
known labels, the only available reward IS the label, so an RL agent collapses
into a higher-variance way of fitting the same boundary.

Where RL genuinely applies is the closed loop: error-related potentials combined
with RL, where the framework learns the user's intention directly from brain
signals and uses the neural signature of errors as the learning signal. That
requires a live session, a feedback display, and a second decoder for the ErrP
itself. Note the same study's warning: the use of motor imagery in a high-speed
interaction paradigm proved ineffective for most participants.

**Verdict: not applicable offline. Potentially relevant once there is a working
online system - which is several steps away.**

## 3.6 Co-adaptive calibration - the most relevant finding

This is the single most actionable item in the literature for this project, and
it builds directly on what we have already built.

Vidaurre et al.'s machine-learning-based co-adaptive calibration **starts with a
subject-independent classifier** - exactly the artefact produced by this study -
**and evolves it to a subject-optimised state within one session while the user
interacts continuously.** Early runs use supervised co-adaptive learning of user
and machine; later runs use unsupervised adaptation to track feature drift.
With this approach, and **without any offline calibration**, six users including
one novice obtained good performance after 3 to 6 minutes of adaptation. More
importantly, the guided learning allowed participants with BCI illiteracy to
gain significant control in under 60 minutes.

The hypothesis motivating it is that one main difficulty for a BCI user is the
transition from offline calibration to online feedback - which is precisely the
transition our recordings never made.

## 3.7 BCI illiteracy and user training

A non-negligible portion of users cannot control a motor-imagery BCI at all.
The commonly cited range is 15-30 %, and the phenomenon is generic to all
motor-imagery-based BCIs. Our own data shows it: two of nine 2b subjects (B02
at 0.57, B03 at 0.52) sit near chance even when trained on their own data.

It is not necessarily permanent. Feedback training has shown that subjects
previously categorised as BCI illiterate could gain BCI control within one
session, including one subject who had no sensorimotor idle rhythm at the start
and developed one through feedback training. Other routes under investigation
include hybrid somatosensory stimulation training aimed specifically at poorly
performing users.

**Verdict: directly relevant, and currently unaddressed.** All our recordings
were made without any feedback. The user has never seen whether their imagery
was being decoded correctly, and so has had no opportunity to learn.

---

# PART IV - RECOMMENDATIONS

In descending order of expected effect.

## 4.1 Re-record with a corrected protocol  [essential, blocks everything else]

Nothing measured on the current recordings can mean anything, because class is
perfectly confounded with session. Copy 2b's design, which is known to work:

  - **Interleave left and right randomly within every session.** This is the
    single most important change. As long as one file holds one class, any
    difference between recording sessions reproduces as apparent accuracy.
  - **Software-timed cues**, with the marker written by the program. Current
    trials are self-clicked, which means a real hand movement at t=0.
  - **Fixed-length trials**: 2 s rest, cue, 4 s imagery. Current trials run
    from 4.9 s to 148 s.
  - **At least 40 trials per class per session**, ideally 80, across several
    sessions on different days.
  - **Record the electrode positions** and photograph the placement.
  - Keep a rest block in every session as a control.

## 4.2 Add online feedback  [the largest untried lever]

Every recording so far has been open-loop. The user has never been shown whether
their imagery was decoded correctly. Given that feedback training can bring
previously BCI-illiterate users into control within a session, and that the
offline-to-online transition is itself identified as the main difficulty, this
is likely worth more than any remaining algorithmic change.

The decoder to put in the loop already exists: `gelo_svm_pipeline.py`, trained on
2b, requires no calibration, and is validated at 0.744 on unseen people.

## 4.3 Deploy co-adaptive calibration  [follows directly from 4.2]

Start each session with the subject-independent model, adapt it supervised for
the first few minutes while the user receives feedback, then switch to
unsupervised adaptation to track drift. This is the published recipe, it needs
no offline calibration session, and our calibration-curve experiment independently
shows that a static offline calibration would have bought under 0.01 anyway.

## 4.4 Verify electrode placement  [cheap, and currently unknown]

The left/right ORDER has been tested and is not the problem. What remains
untested is whether the two electrodes sit over the hand area at all. 2b uses
bipolar pairs placed about 2.5 cm either side of C3 and C4; a headband sitting
too far forward or back records a different rhythm entirely. Also still unknown:
what ch1 and ch4 are. If either is a usable scalp site, the montage grows.

## 4.5 Do not pursue, and why

  - **A better classifier.** Worth ~0.003 on two channels. Measured.
  - **More features.** Sixteen configurations of mean/median/skewness/kurtosis
    spanned 0.013 on the stroke data. Measured.
  - **Deep learning.** Comparable to FBCSP on motor imagery, at much greater
    cost and overfitting risk.
  - **Data augmentation.** Addresses overfitting, which is not our problem.
  - **Offline calibration sessions.** Under 0.01 once alignment is applied.
    Measured.

---

# PART V - WHAT TO TAKE AWAY

**On the science.** Left-vs-right motor imagery is decodable from two
electrodes. We measured 0.744 balanced accuracy on a person the model had never
seen, with all nine test subjects above chance, using C3 and C4 alone. The
limiting factor is not the number of electrodes, not the features, and not the
classifier.

**On the method.** Three practices earned their keep, each by catching a real
error:

  1. *Write the expected result down before running.* It is what turned a
     plausible-looking negative result into a located bug.
  2. *Test every procedure on shuffled labels.* It is what revealed that a
     published 72 % scores 63.8 % on random labels.
  3. *Score at the level of the independent unit.* 72 epochs from 15
     single-class files is 15 decisions.

**On the project.** The decoder is built, validated and ready. What it needs is
data recorded in a way that can be measured - interleaved classes, timed cues,
fixed trials - and a feedback loop so the user can learn. Both are recording
decisions, not modelling decisions.

---

# APPENDIX A - FILES

    gelo_svm_pipeline.py    the complete decoder, written to be read
    00_PLAN.md              design and predictions, written before any run
    s00_diagnose_window.py  locates the imagery window without assuming it
    s01_fetch_2b.py         download, epoch, cache covariances
    s02_run_models.py       7 models x 2 alignments x 2 protocols
    s03_report.py           figures
    s04_gelo_transfer.py    2-channel ceiling, and the transfer to our data
    s05_polarity_check.py   the channel-swap test
    s06_calibration_curve.py how many trials a new user needs
    REPORT.md               full technical report with all numbers
    HOW_TO_RUN.md           reproduction instructions
    results\                every CSV, log and figure

# APPENDIX B - REFERENCES

  He & Wu (2018). Transfer Learning for Brain-Computer Interfaces: A Euclidean
    Space Data Alignment Approach. arXiv:1808.05464
  Lawhern et al. (2018). EEGNet: A Compact Convolutional Network for EEG-based
    Brain-Computer Interfaces. arXiv:1611.08024
  Guetschel, Moreau & Tangermann (2024). S-JEPA: towards seamless cross-dataset
    transfer through dynamic spatial attention. arXiv:2403.11772
  Rommel, Paillard, Moreau & Gramfort (2022). Data augmentation for learning
    predictive models on EEG: a systematic comparison. arXiv:2206.14483
  Vidaurre et al. Machine-learning-based co-adaptive calibration for
    brain-computer interfaces.
  Xavier Fidencio et al. (2025). Error-related Potential driven Reinforcement
    Learning for adaptive Brain-Computer Interfaces. arXiv:2502.18594
  Panchavati et al. Laya: A LeJEPA Approach to EEG via Latent Prediction over
    Reconstruction. arXiv:2603.16281
  Leeuwis et al. (2021), via Park, Ha, Kim & Kim (2021). Improving Motor
    Imagery-Based BCI Performance Based on Sensory Stimulation Training.
    Front. Neurosci. 15:732545
  Liu et al. (2024). An EEG motor imagery dataset for brain computer interface
    in acute stroke patients. Scientific Data 11:131
  BCI Competition IV dataset 2b (Leeb et al.), BNCI Horizon 2020 id 004-2014
