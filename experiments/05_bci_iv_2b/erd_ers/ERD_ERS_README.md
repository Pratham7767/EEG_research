# ERD/ERS and PSD on BCI Competition IV dataset 2b

Updated 16 Oct 2026. Companion to `00_PLAN.md` and `REPORT.md` in the parent
folder.

**To reproduce everything in this folder: open
`D:\trainsvm\EXPERIMENT_2\RUN_ERD_PSD_2b.m` in MATLAB and press Run.**
One script, no arguments, ~45 s with the cache warm and ~4 min cold. It writes
the figures, the CSVs and `RUN_ERD_PSD_2b.log` (the full console output) into
this folder.

> Note: the earlier two-script version (`erd_ers_2b.m` + `psd_equivalence.m`)
> has been deleted. It contained a reporting bug — see §6 — and its numbers
> should not be quoted. Everything below comes from the single script.

---

## 1. The database

BCI Competition IV dataset 2b = BNCI Horizon 2020 id **004-2014**, described in
Leeb, Brunner, Müller-Putz, Schlögl & Pfurtscheller, *BCI Competition 2008 —
Graz data set B* (`https://bbci.de/competition/IV/desc_2b.pdf`), from the study
in Leeb et al., *IEEE TNSRE* 15:473–482, 2007.

### How it is stored

18 `.mat` files in `..\data\`:

    B01T .. B09T     sessions 1, 2, 3   (3 session structs per file)
    B01E .. B09E     sessions 4, 5      (labelled in this BNCI release)

Each file holds one cell array `data`; each cell is one **session**:

| field | size (B01, session 1) | meaning |
|---|---|---|
| `X` | `[604803 x 6]` | continuous signal. Cols 1–3 = bipolar **C3, Cz, C4**; cols 4–6 = EOG, dropped |
| `trial` | `[120 x 1]` | sample index of each **trial start** — *not* the cue |
| `y` | `[120 x 1]` | `1` = left hand, `2` = right hand |
| `artifacts` | `[120 x 1]` | expert artefact flag |
| `fs` | `250` | Hz |
| `classes` | `{'left hand','right hand'}` | |

Recording: three **bipolar** derivations around C3, Cz and C4 (exact placement
differs slightly per subject), 250 Hz, 0.5–100 Hz bandpass and a 50 Hz notch
applied at recording time, Fz as ground. Range ±100 µV for the screening
sessions, ±50 µV for the feedback sessions.

### Trial timing — the thing that matters

Both paradigms put the cue at **second 3** after the stored `trial` index:

    screening (sessions 1-2)   fixation cross   0 s
                               warning beep     2 s
                               CUE              3 s   (arrow, 1.25 s)
                               imagery          4 s
                               pause            >= 1.5 s + up to 1 s jitter

    feedback  (sessions 3-5)   grey smiley      0 s
                               warning beep     2 s
                               CUE              3 s -> 7.5 s (smiley feedback)
                               blank            + 1.0-2.0 s random

So `CFG.cueOffsetSec = 3.0`, the same constant `s01_fetch_2b.py` uses. The
script does not take this on trust — SECTION 2 re-derives it (see §3).

### Trials per subject

| sessions | trials each | type |
|---|---|---|
| 1, 2 | 120 | screening, no feedback |
| 3, 4, 5 | 160 | smiley feedback |

Nominal **720 per subject**, 360 left / 360 right. Actual (`erd_trialcount.csv`):

    B01 720   B02 680   B03 720   B04 740   B05 740
    B06 720   B07 720   B08 760   B09 720            TOTAL 6520

Nothing dropped at epoch edges, no NaN gaps. ~30 hours of recording in total.

### Against the stroke dataset

| | Liu et al. stroke | 2b |
|---|---|---|
| subjects | 50 patients | 9 healthy |
| rate | 500 Hz | **250 Hz** (the headset's rate) |
| channels | 29 monopolar, ref CPz | **3 bipolar: C3, Cz, C4** |
| trials/subject | 40 | **720** |
| sessions | 1 | **5, different days** |
| class order | alternating | randomised within session |
| labels | 1 = left, 2 = right | identical convention |

---

## 2. How many figures you get

**13 figures:**

    erd_B01.png .. erd_B09.png     9 per-subject, 2 panels each (left / right
                                   hand MI), C3+Cz+C4 per panel, with 95%
                                   bootstrap confidence bands on C3 and C4
    erd_grand_average.png          the same, averaged over the 9 subjects,
                                   band = 95% interval ACROSS subjects
    erd_overlay.png                C3/C4 x left/right on one pair of axes
    erd_timefrequency.png          4 time-frequency ERD maps
    psd_spectra.png                baseline vs imagery spectra, 4 panels
    psd_vs_bandpower.png           band power vs integrated PSD, 3 panels

That is 18 subject × class ERD panels plus 2 in the grand average, and 54
individual curves (9 × 2 classes × 3 channels), all also in `erd_curves.csv`
with their confidence bounds. One figure per *session* instead of pooled would
be 45; that is a one-line change (group by `sess` in `loadSubject`).

---

## 3. The method, and the five things it fixes

The recipe is the published one from `PlotEvent.m` / `plotERDERS.m`:

1. band-pass each trial, 8–30 Hz, 2nd-order Butterworth
2. **square**
3. **average** across trials of one class
4. **smooth** (0.4 s — the paper's 200 samples at 500 Hz)
5. `ERD/ERS% = (A − R) / R × 100`

Each departure below is a flag in SECTION 1 of the script, so the original
behaviour can be restored and the difference shown side by side.

**(1) Baseline window.** `PlotEvent.m` sets `R_start=1; R_end=2` and reads
`C3(500:999)` — with its epoch starting at −1 s and Fs = 500 that is **0–1 s,
the first second of imagery**, not the pre-cue rest the paper text describes.
Normalising imagery against imagery cancels part of the effect. Here the
baseline is −2.0 to −1.0 s relative to the cue: pre-cue *and* before the 2 s
warning beep, so no auditory evoked response contaminates it.
→ `CFG.baseWin`, `CFG.useCodeBaseline`

**(2) Filter phase.** `filter_param.m` calls `filter`, which is causal and
delays the signal by a frequency-dependent amount — it smears the very time
axis the plot is read from. The paper *text* says zero-phase. → `CFG.zeroPhase`

**(3) Outlier sensitivity.** Step 2 squares before averaging, so the class mean
is a mean of squares and a few loud trials dominate. A 20% trimmed mean across
trials fixes it. The script prints every cell where the two estimators disagree
by more than 20 pp, so the correction is visible rather than silent.
→ `CFG.estimator`, `CFG.trimPct`

**(4) No uncertainty.** The published code plots a bare line. Every C3/C4 curve
here carries a 200-resample bootstrap 95% band (per-subject) or the
across-subject 95% interval (grand average), so "C4 is below C3" can be judged
rather than eyeballed. → `CFG.nBoot`

**(5) One fixed band.** 8–30 Hz merges mu and beta. SECTION 7 produces
time-frequency ERD maps and the per-subject peak-ERD frequency. → `CFG.doTF`

**Plus two verification steps the original has no equivalent of.**

SECTION 2 re-derives the cue offset *from the data*: it slides a 1 s window
across 0–6.5 s after `trial` and measures the AUC of log(C3) − log(C4) for
predicting right-hand MI. Result, pooled over 1120 trials:

    offset   0.00 .. 2.50 s    AUC 0.492 - 0.508     flat at chance (fixation)
    offset   2.75 s            AUC 0.456
    offset   3.00 s            AUC 0.416             <-- leaves chance
    offset   3.75 s            AUC 0.317             strongest
    ...stays strong to 6.50 s (window ends 7.50 s)

The statistic first leaves chance at exactly **3.00 s**, and a 1 s window
starting there covers [3.00, 4.00], so the cue must lie inside that interval.
`CFG.cueOffsetSec = 3.0` is confirmed. The effect then persists to 7.5 s —
about 4.5 s of imagery after the cue, matching the paradigm's 4 s period.

*Read the onset, not the argmax.* Imagery lasts 4 s, so the statistic stays
strong for seconds and its peak is a noisy tie anywhere inside that plateau.
An earlier version of this check used a 2 s window and reported the argmax; it
landed at 5.5 s and wrongly declared the cue offset inconsistent. The onset is
what localises the cue.

SECTION 6 proves the PSD identity by measurement — see §5.

---

## 4. Result

`erd_grand_average.png`, mean ERD% over 0.5–3.5 s after the cue:

    LEFT  hand MI :  C3 -14.81%   Cz -18.45%   C4 -29.82%   (contralateral = C4)
    RIGHT hand MI :  C3 -34.31%   Cz -19.04%   C4  +0.19%   (contralateral = C3)

Textbook contralateral dominance in both directions. ERD begins within ~200 ms
of the cue, bottoms at ~1.0–1.1 s, recovers slowly through the imagery period.
Right-hand MI additionally shows ipsilateral C4 sitting at baseline or slightly
above — the classic ERD/ERS pair.

The contralateral channel is the more desynchronised one in **16 of 18
subject × class cells** (`erd_stats.csv`). The two exceptions are B02
right-hand (+6.06, p = 0.027) and B03 right-hand (+10.71, p = 0.137) — the same
two subjects `REPORT.md` §5.2 flags as near chance for every classifier.
Ordinary BCI illiteracy, well documented for 2b. The ERD plots and the
classification results agree about which subjects carry signal.

This also independently confirms the sign in `REPORT.md` §9.3: AUC of
log(C3) − log(C4) for right-hand MI was 0.217, i.e. C3 power drops. It does,
by 34.3%.

### What the refinements actually changed

**Estimator.** Exactly one cell moved by more than 20 pp: B08 right-hand,
C3 −41.4 → −48.7 and C4 +55.7 → **+76.0**. Note the direction — trimming made
C4's ipsilateral ERS *larger*, not smaller. B08's +76% is a real effect, not an
outlier artefact. B08 is one of the strongest subjects in `REPORT.md`
(P1 = 0.9156), and a very large ipsilateral synchronisation is consistent with
that. Largest change anywhere: 20.2 pp.

**Artefact flags.** Keeping vs removing the dataset's own flagged trials moves
no cell by more than 5.1 pp (C3) or 10.3 pp (C4), and the C3-vs-C4 ordering is
unchanged in 18 of 18 cells. Artefact rejection is not doing hidden work in
either direction. Both columns are in `erd_stats.csv`.

**Peak-ERD frequency** (`erd_peak_frequency.csv`), C3 during right-hand MI:

    B01 11.7   B02  9.8   B03 31.2   B04 10.7   B05  9.8
    B06 34.2   B07 20.5   B08  7.8   B09 23.4      Hz

Range 7.8–34.2 Hz, median 11.7. Six subjects peak in mu, three in beta. That
spread is the cost of assuming one band fits everyone, and it is the honest
argument for per-subject band selection — chosen on *training data only*, which
is exactly where `TWFB_DGFMDM.m` went wrong in the stroke paper.

---

## 5. Where the PSD is

**The ERD method never calls `fft`.** There is no Welch estimate in
`PlotEvent.m` and none in the ERD path here. Power comes the Pfurtscheller way:
*band-pass → square → average*. That is not an approximation of a PSD; by
Parseval's theorem it **is** the integral of the PSD over the passband:

        mean( x_band(t)² )  =  ∫[f1..f2] S_xx(f) df

One number, not a spectrum. The ERD curve is that number tracked over time and
expressed as a percentage of its own baseline.

SECTION 6 measures it on B04's 740 trials (`psd_equivalence.csv`):

    channel   mean(x_band²)    ∫PSD df     ratio    Pearson r
    C3            5.49 µV²     6.10 µV²    1.112      0.9841
    Cz            3.80 µV²     4.22 µV²    1.112      0.9777
    C4            4.37 µV²     4.87 µV²    1.114      0.9871

r ≈ 0.98 trial by trial. The constant ~1.11 offset is the filter, not a
discrepancy: a 2nd-order Butterworth is not a brick wall, so it already
attenuates inside 8–30 Hz while the Welch integral cuts sharply at the band
edges. Raise `CFG.order` and the ratio moves toward 1. Because the offset is
*constant*, it cancels exactly in `(A−R)/R` — which is why the ERD percentage
does not care which of the two is used.

### The same quantity a third time

`s01_fetch_2b.py` stores a per-trial 3×3 Ledoit-Wolf covariance and every model
in `s02_run_models.py` reads it. The **diagonal of that matrix is the band
power** — `var(x)` equals `mean(x²)` once the mean is removed. Measured here:
max relative difference 1.3×10⁻³, correlation 1.0000.

| name | computed as | used by |
|---|---|---|
| ERD/ERS % | band-pass → square → smooth → `(A−R)/R` | these plots |
| band power / integrated PSD | `∫ S_xx(f) df` over 8–30 Hz | `psd_spectra.png` |
| `logvar_svm` features | `log` of the covariance diagonal | `s02_run_models.py` |

`logvar_svm` reaching 0.7468 in P2 — tying the best model in the table — is
therefore the same physical measurement these ERD curves plot, fed to a linear
classifier instead of to a figure. That is the direct link between this folder
and `REPORT.md` §4.

`psd_spectra.png` shows the spectra the single number summarises: a mu peak near
11 Hz and beta near 19 Hz, suppressed contralaterally during imagery.

---

## 6. The reporting bug in the previous version, and why it is recorded here

The first version of this analysis printed a table whose numbers **did not come
from the curves it plotted.** The table's per-channel ERD% was computed by
normalising *each trial* to its own baseline and then averaging those
percentages; the figures normalised the *trial-averaged* power once, which is
what the paper's recipe does. Both are legitimate statistics, but they are
different quantities and they differ substantially:

    B01 left-hand C3    curve-based  -17.3%     per-trial   -5.9%
    B08 right-hand C4   curve-based  +76.0%     per-trial  +163.8%

The B08 figure was reported at the time as a +150% outlier produced by the
mean-of-squares. **That was wrong on both counts.** It was the per-trial
statistic, not the plotted one, and the curve-based value is +76%, which the
robust estimator *increases* rather than suppresses. It is a genuine
ipsilateral ERS in a strong subject.

The current script makes this error impossible by construction: the table's
`C3_pct`, `Cz_pct`, `C4_pct` and `contra_minus_ipsi` columns are read from the
same `curv` array that is plotted. The per-trial statistic is still computed —
a *paired* t-test needs it, because it compares two channels within each trial
— but it is reported in its own `pertrial_diff` column, next to the p-value it
belongs to, and the console says plainly that the two can differ in size and
occasionally in sign.

Quoting one statistic while plotting another is easy to do and hard to notice.
It is the same class of error as the cue-offset bug in `REPORT.md` §2 and the
marker-2 trap in Experiment_svm: an assumption never checked against the thing
it was supposed to describe.

---

## 7. Are these methods good?

**The ERD/ERS recipe: yes, with the fixes above.** Band-pass → square → average
→ percent-of-baseline is Pfurtscheller & Lopes da Silva's standard method
(*Clin Neurophysiol* 110:1842, 1999). It is simple, interpretable, and the grand
average here looks exactly as the literature says it should — which is itself
evidence that the epoching and the cue offset are right. **Do not use the
published stroke code unmodified**: its baseline sits inside the imagery period,
its filter is causal, and at 250 Hz its hardcoded `xlim([500 2500])` and
`sampleRate*1 : sampleRate*2-1` baseline are both wrong in ways that do not
announce themselves.

**Remaining limitations.**

1. **ERD is descriptive, not predictive.** It pools hundreds of trials to show
   an effect invisible in any single one. B01 has a −20 pp lateralisation and
   still only reaches 0.743 cross-subject. Do not read these curves as a
   forecast of classifier accuracy.
2. **The bootstrap bands cover sampling variation over trials only.** They say
   nothing about session or electrode-placement variability, which for a single
   subject is the larger source of uncertainty.
3. **One window, one band, fixed for everyone.** §4 quantifies what that costs:
   peak ERD ranges 7.8–34.2 Hz across subjects.
4. **The time-frequency map uses a 0.5 s window**, so frequency resolution is
   ~2 Hz and nothing below ~6 Hz is trustworthy. `CFG.tfShow` and `CFG.tfPeak`
   enforce that. An earlier version searched from 4 Hz and returned 4.9 Hz as
   the "peak ERD frequency" for B01 — that was the cue-evoked potential at the
   unresolvable bottom bin, not an ERD.
5. **No multiple-comparison correction** on the 18 t-tests. With 16/18 cells in
   the predicted direction this does not change any conclusion, but it should be
   stated if the table is published.

**ERD% versus Euclidean Alignment.** `REPORT.md` §3 argues EA is the principled
version of what ERD% normalisation reaches for: both cancel per-session gain,
but EA also removes the spatial correlation structure, needs no baseline period,
and makes no assumption that the baseline is the same mental state on both
sides. For **classification** EA is the better tool and 28/28 settles it. For
**looking at the physiology**, ERD% is the right one — interpretable units, and
a time axis. They are not competitors.

**The most useful thing this folder provides.** A reference ERD picture from a
dataset known to contain signal, computed with the identical formula and window
as `D:\trainsvm\erd\gelo_erd.m`. When the Gelo recordings are redone with
interleaved classes and software cues — still the top recommendation of both
`REPORT.md` §6.1 and the Experiment_svm report — running `gelo_erd.m` and
putting its output beside `erd_grand_average.png` is a direct, visual,
classifier-free test of whether the new recordings contain a motor rhythm.
Worth running *before* any model is trained. It would have caught the problem
with the current recordings months before the classifiers did.

---

## 8. Files

    ..\RUN_ERD_PSD_2b.m            THE SCRIPT. Open it and press Run.
    RUN_ERD_PSD_2b.log             full console output of the last run
    erd_B01.png .. erd_B09.png     per subject, with confidence bands
    erd_grand_average.png          mean of the 9 subjects
    erd_overlay.png                C3/C4 x left/right on one axes
    erd_timefrequency.png          time-frequency ERD maps
    psd_spectra.png                baseline vs imagery spectra
    psd_vs_bandpower.png           band power = integrated PSD
    erd_stats.csv                  per subject x class, curve-based and
                                   per-trial, plus the artefact-free pass
    erd_estimator_comparison.csv   paper mean vs trimmed mean, every cell
    erd_peak_frequency.csv         per-subject peak ERD frequency
    erd_curves.csv                 every curve, long format, with CI bounds
    erd_trialcount.csv             trials per subject per class
    psd_equivalence.csv            the equivalence table
    cache\cache_B0*.mat            epoch cache, ~285 MB. Safe to delete;
                                   deleting only costs a slower next run.

Nothing outside `EXPERIMENT_2\` was written.
