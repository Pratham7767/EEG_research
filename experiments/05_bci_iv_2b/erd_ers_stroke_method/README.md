# ERD/ERS of every BCI IV 2b subject, with the stroke-patient method

Made 2026-11-01. Script: `erd_ers_2b_stroke_method.m` (MATLAB, ~50 s). Check: `check_with_python.py`.

BCI IV 2b ("BCI 2008", Graz data set B) was **downloaded** from BNCI, not recorded by us.

## Method (identical to `data/stroke_liu2024/ERD_ERS/erd_ers_all_subjects.m`)

1. Band-pass C3 and C4, 8-30 Hz, Butterworth order 2, `filtfilt`, over the 8 s trial + 0.5 s padding each side
   (padding cut off afterwards, so filter edges never show in the plot).
2. Square every trial.
3. Plain mean of the squared trials per class (left / right), then smoothed with the paper's
   smoothing: 200 samples at 500 Hz = 0.4 s = 100 samples at 250 Hz (`smoothMA.m` = `smooth()`,
   which uses 99 because an even span is reduced by 1, just as 200 -> 199 for the stroke data).
4. ERD/ERS % = (X - M) / M x 100, M = mean of the 1 s before the cue (trial time 2..3 s), X = each sample.

Plots show the **whole trial, 0..8 s, cue at 3 s** (dashed line), like the timing figure in the
BCI 2008 / Graz data set B paper, so you see before and after the cue. Numbers in the table use
0..4 s and 0.5..3.5 s after the cue, as before.

Only the data-specific parts change: 250 Hz, cue = `trial` + 3 s, X(:,1) = C3, X(:,3) = C4,
all 5 sessions pooled (340-380 trials per hand), artefact-flagged trials kept (the stroke recipe
has no rejection). No trial had NaN. Note: in 2b the warning beep is at -1 s, at the start of the baseline.

## Files

| file | what |
|---|---|
| `figures/B0x_ERD_ERS.png` | one figure per subject (smoothed 0.4 s, 0..8 s, cue line at 3 s), plain report style like `03_gelo_erd` (C3 red dashed, C4 blue, no shading, no Cz, same y-scale in both panels) |
| `ERD_ERS_2b_all_subjects.png` | all 9 subjects on one page (smoothed) |
| `ERD_ERS_2b_summary.csv` | stroke columns (median/mean over 0-4 s, band power) + mean over 0.5-3.5 s + 'opposite side drops more' check |
| `ERD_ERS_2b_stroke_method.mat` | all smoothed curves (`ERD_all`, `M_*`, `t`) |
| `run_log.txt`, `check_with_python_log.txt` | console output; Python re-computation (max difference 1.5e-13) |

## Result (mean ERD/ERS % over 0.5-3.5 s after the cue, smoothed)

| subject | Left MI: C3 | C4 | Right MI: C3 | C4 | opposite side drops more? |
|---|---|---|---|---|---|
| B01 | -15.4 | **-40.0** | **-24.3** | -15.7 | yes / yes |
| B02 | -13.7 | **-31.8** | **-17.1** | -23.4 | yes / NO |
| B03 | -14.5 | **-25.3** | **-20.4** | -17.3 | yes / yes |
| B04 | -1.2 | **-31.1** | **-42.2** | +33.8 | yes / yes |
| B05 | -27.6 | **-30.3** | **-35.1** | -16.2 | yes / yes |
| B06 | -10.1 | **-30.9** | **-29.9** | -16.6 | yes / yes |
| B07 | -2.4 | **-17.0** | **-27.8** | +6.7 | yes / yes |
| B08 | -7.7 | **-23.8** | **-37.6** | +52.2 | yes / yes |
| B09 | -18.7 | **-16.2** | **-45.6** | -2.6 | NO / yes |

Before the cue (0..2 s) power is often ABOVE baseline (up to +150 % for B06 near 0 s): the rhythm
is strong at rest at the start of a trial and drops once the warning beep (2 s) and cue (3 s) come.

The side opposite the hand (C4 for left, C3 for right) drops more in 16/18 cases (B09 left is close: 3 points). Bold = the side that should drop.

## Difference from `../erd_ers/` (RUN_ERD_PSD_2b.m, 16 Oct)

That folder already has per-subject ERD/ERS plots, but with a **modified** recipe: baseline -2..-1 s,
20 % trimmed mean, Cz added, bootstrap bands, -2.5..5 s axis. This folder is the
**unmodified stroke recipe (smoothed version)**, so it can be compared 1:1 with the stroke figures. Both give 16/18
cases in the expected direction; the exceptions move (old: B02 R, B03 R; here: B02 R, B09 L).

---

# PSD and "which number best separates left from right" (psd_2b_stroke_method.m)

Same trials, channels and windows as the ERD/ERS plots above. Run:
`cd D:\trainsvm\experiments\05_bci_iv_2b\erd_ers_stroke_method` then `psd_2b_stroke_method` (~60 s).

**PSD method** (same as the earlier `../erd_ers/psd_spectra.png`, which was B04 only): Welch, 0.5 s Hamming
window, 50 % overlap, nfft 256 (~1 Hz bins), one PSD per trial, averaged per hand.
Baseline = 1 s before the cue, imagery = 0-4 s after the cue. Grey = baseline, red = imagery, log scale.

| file | what |
|---|---|
| `figures_psd/B0x_PSD.png` | per subject, 2 x 2 (left/right hand x C3/C4), 8-30 Hz change in each title |
| `PSD_2b_grand_average.png` | mean over the 9 subjects |
| `differentiator_2b.png` | accuracy of 18 single features (6 kinds x 3 bands), bar = mean, dot = subject |
| `differentiator_best.png` | the best feature, left vs right single-trial histograms, every subject |
| `differentiator_2b.csv`, `differentiator_summary.csv` | all numbers |

8-30 Hz power change, imagery vs baseline (%), median of 9 subjects:
left-hand MI C3 -11.8, **C4 -25.8**; right-hand MI **C3 -28.1**, C4 -10.3.

## Best differentiator

Single trials, 0.5-3.5 s after the cue. Threshold learned on sessions 1-3, tested on sessions 4-5 (unseen days).

| rank | feature | mean acc (S4-5) | worst subject | subjects p < .05 | new user (LOSO) |
|---|---|---|---|---|---|
| 1 | **log(C3 power / C4 power), 8-30 Hz** | **73.5 %** | 55.7 % | 9/9 | 70.8 % |
| 2 | log(C3/C4), mu 8-13 Hz | 71.9 % | 53.7 % | 8/9 | 68.2 % |
| 3 | log(C3/C4), beta 13-30 Hz | 69.3 % | 51.2 % | 7/9 | 66.7 % |
| 4 | ERD C3 - ERD C4, 8-30 Hz | 67.8 % | 55.7 % | 9/9 | 65.2 % |
| ... | C3 or C4 power alone | 59-63 % | | | 55-57 % |
| last | ERD of one channel alone | 54-60 % | | | 55-59 % |

Per subject (log C3/C4, 8-30 Hz, S4-5): B01 61, B02 56, B03 56, B04 97, B05 69, B06 79, B07 69, B08 91, B09 84 %.

Why: the ratio compares the two sides **in the same moment**, so anything that raises or lowers power on
both sides together (general alertness, tiredness, a common amplitude change) cancels. A single-channel power changes
for many reasons besides the hand. Per-trial ERD needs a 1 s baseline from the same trial, which is noisy,
so it loses ~6 points to the plain ratio. This is the same quantity the `logvar_svm` model in
`s02_run_models.py` uses (log band power), so it fits the earlier results.
