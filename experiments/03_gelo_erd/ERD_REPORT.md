# ERD/ERS for the Gelo recordings — method, parameters, and an honest result

Written 27 Sep 2026. Covers: how the paper recorded its data, how to identify and chop
your iterations, what parameters change between 500 Hz and 250 Hz, and what the ERD
analysis actually shows.

---

## 1. How the paper recorded its data

Liu et al. 2024, *Scientific Data* 11:131 — "An EEG motor imagery dataset for brain
computer interface in acute stroke patients".

| | |
|---|---|
| Subjects | 50 acute stroke patients (1–30 days post-stroke) |
| Device | ZhenTec NT1 wireless, 29 EEG + 2 EOG, Ag/AgCl semi-dry saline sponge |
| Montage | international **10-10**, reference **CPz**, ground **FPz** |
| Sampling | **500 Hz**, 24-bit, impedance ≤ 20 kΩ |
| Session | ~20 min total, ~10 min recorded. **1 min eyes-open + 1 min eyes-closed first** |
| Trials | **40 per subject, 8 s each** = instruction → **MI (4 s)** → break |
| Cue | a video of a hand gripping a ball plays for 4 s; patient imagines gripping |
| Order | left and right hand **alternating** |
| Labels | `1` = left hand, `2` = right hand |
| Stored | `rawdata` = 40 trials × 33 ch × **4000 samples** (4000/500 = 8 s ✓) |
| Preproc | mean-removal baseline correction, 0.5–40 Hz, split into trials by marker `1` |

Two structural details matter for you:

- **The 8 s trial is split by marker `1`; marker `2` is MI onset = t = 0.** The plot axis
  runs −1 s to +4 s, so their epoch is 1 s of preparation followed by the 4 s MI video.
  Everything after +4 s (the break) exists in the array but is never plotted.
- **Left and right alternate inside one recording session.** This is the single most
  important difference from your setup, and section 8 explains why it matters so much.

Your own protocol already mirrors theirs more than you may realise: your `mark 6` and
`mark 7` blocks (~30 s each, at the start of every file) are the eyes-open/eyes-closed
baselines the paper records for 1 min each.

### The paper's ERD/ERS recipe (Technical Validation)

1. Band-pass C3 and C4 at **8–30 Hz** (text says 2nd-order **zero-phase** Butterworth).
2. **Square** each trial, then stack and average across all trials of the same label.
3. **Smooth** the averaged curve (smoothness coefficient = **200**).
4. `ERD/ERS% = (X − M) / M × 100`, where **M = mean of the preparation period (−1 to 0 s)**.

Negative = desynchronisation = that cortex is active. Contralateral rule: imagining the
**left** hand should desynchronise **C4**; imagining the **right** hand should
desynchronise **C3**.

---

## 2. Two bugs in the authors' own code

I read `plotERDERS.m`, `PlotEvent.m` and `filter_param.m`. Two places where the published
code does **not** do what the paper text says. You should know which one you are copying.

**(a) The baseline window is wrong in the code.**
`PlotEvent.m` sets `R_start = 1; R_end = 2` and takes
`C3mean = C3(sampleRate*1 : sampleRate*2 - 1)` → samples 500…999. But the plot maps
sample 500 to the label `0` and sample 2500 to `4`. So the code's baseline is **0–1 s,
the first second of motor imagery** — not the −1…0 s preparation period the paper
describes. Normalising MI against MI partially cancels the very effect you are looking
for. `erd_codebaseline.png` shows your data under the code's choice so you can compare.
**I used the paper text's −1…0 s.** That is also standard Pfurtscheller ERD practice.

**(b) The filter is causal, not zero-phase.**
`filter_param.m` calls MATLAB `filter(b,a,...)`, not `filtfilt`. A causal IIR band-pass
delays the signal by a frequency-dependent amount, which smears and shifts the ERD in
time — and time is the x-axis you are reading. The paper text says "zero-phase".
**I used `filtfilt`** (zero-phase). `erd_causal.png` shows the causal version.

**(c) A third, smaller one I worked around.** MATLAB `smooth` shrinks its window at the
array edges, so the first and last ~0.2 s of the curve are effectively unsmoothed. The
authors never see this because they plot samples 500–2500 out of 4000 — their edges are
far outside the window. Your iterations are short, so if you epoch exactly −1…+4 s the
artefact lands *inside* the plot. **Fix: extract −1.5…+4.5 s, filter and smooth, then
crop to −1…+4.** That is what `extract_epochs.py` does.

---

## 3. What is actually in your data (verified, not taken from the old README)

Files: `D:\trainsvm\left\*.csv` (5 files), `D:\trainsvm\right\*.csv` (10 files).
Columns `timestamp, ch1..ch8, mark`; timestamps step 4000 µs → **250 Hz**, no gaps.
`ch5..ch8` are constant `1.1754944e-38` (float min) = unused.

**Channel mapping — verified from the device SDK, not the README.**
`eeg_headphones/brain_bit/headphones.py` writes the header
`['time (s)', 'A1', 'C3', 'C4', 'A2']`, and `EEG_Recorder/config/config.json` declares
`"device": {"type": "LEHeadphones2"}`. Therefore:

| column | electrode | role |
|---|---|---|
| ch1 | **A1** | left earlobe — reference |
| ch2 | **C3** | left motor cortex |
| ch3 | **C4** | right motor cortex |
| ch4 | **A2** | right earlobe — reference |

The *other* SDK in your folder (`headband.py`, the BrainBit headband) is **T3, T4, O1, O2**
— temporal and occipital, no motor coverage at all. Confirm every session used the
headphones, not the headband; a single session recorded on the wrong device would be
pure noise in the average.

**Iteration inventory.** `mark` 1–5 are the five repetitions in a file (matching
`SpeechEEG_Recorder`'s `"reps_per_word": 5` and the `Left1_5` / `Left6_10` file naming);
`0` is rest; `6` and `7` are the two ~30 s eyes-open/eyes-closed baselines.

| | left | right |
|---|---|---|
| files | 5 | 10 |
| iterations found | **24** | **51** |
| duration min / median / max | 9.7 / 18.8 / 37.8 s | 4.9 / 18.9 / **148.1** s |

Anomalies, all verified in the raw files:

- `Left1_5.csv` has **no mark 3** — that iteration was never recorded (24, not 25).
- `Right1_5.csv` has **mark 4 twice**, separated by 0.5 s (51, not 50). Only the first
  has a usable baseline.
- `right46_50.csv` mark 4 runs **148.1 s** — the mark was left switched on. Harmless once
  you crop to 4 s, but it tells you the marking was manual and occasionally forgotten.
- `Left6_10.csv` mark 3 and `left16_20.csv` mark 2 begin **immediately after the previous
  iteration**, with no rest in between — so they have no clean baseline and are excluded.

**Minimum duration, which is what you asked for: 4.9 s overall; 9.7 s for left, 4.9 s for
right.**

---

## 4. How to identify the left and right iterations — the reasoning

You asked for the logic, so here it is explicitly. There are three candidate sources of
the label and only one of them is sound.

1. **The mark value (1–5).** Cannot work. The value is the *repetition index within the
   file*, not the class — `mark 3` means "third rep", and it appears in both left and
   right files. It carries zero class information.
2. **The signal itself.** Circular. Deciding which trials are "left" by looking for a
   left-like pattern, then reporting that left and right differ, is assuming the
   conclusion. Never label from the data you intend to test.
3. **The folder / filename.** This is the only ground truth you have: `left/` was
   recorded while you imagined the left hand, `right/` the right hand. The label is
   external to the signal, assigned by the experimental protocol.

So: **label = parent folder; iteration identity = (file, mark value); onset = the first
sample where that mark value appears.** Using the *first* sample matters because
`Right1_5.csv` mark 4 is split into two runs — taking the first run's start naturally
picks the one with a real baseline and discards the stray re-click.

And the cost of option 3 is the finding in section 8: because the folder *is* the label
and each file is single-class, folder identity and session identity are perfectly
confounded. You cannot fix that in analysis. Only in recording.

---

## 5. Chopping into equal-length epochs — the method and why

**Method: fixed-length, onset-locked, with the baseline taken from the rest period
immediately before the click.**

For each iteration:

```
onset  = first sample where mark == m
epoch  = samples[onset − 1.5 s  :  onset + 4.5 s]      # 1500 samples @250 Hz
         (filter + smooth on this padded window)
plot   = crop to [onset − 1 s : onset + 4 s]           # 1250 samples, -1..+4 s
```

Requirement: at least 1.5 s of contiguous `mark == 0` before the onset. 72 of 75
iterations pass (22 left, 50 right).

**Why 4 s and not 4.9 s (the true minimum).** 4 s is the paper's MI window, so your
x-axis is literally the same axis as their Fig. 4 and the figures are directly
comparable. It fits inside every iteration you have, including the 4.9 s one. Using the
literal 4.9 s minimum would buy 0.9 s of extra data at the cost of comparability, and
that extra 0.9 s is the least reliable part of the trial anyway — attention drifts and
the longer iterations show it.

**Why onset-locked and not "take the middle" or "take the whole thing".** ERD is a
*change* relative to a moment. Averaging across trials only builds up the effect if every
trial is aligned to the same event; if you centre epochs on the middle of a 10 s and a
30 s iteration, the same "moment of imagery" lands in different places and the average
smears toward zero. Fixed length from a common onset is what makes the average meaningful.

**Why the baseline comes from before the click, not from the mark 6/7 blocks.** You have
30 s eyes-open and eyes-closed baselines in every file, and they are tempting. Don't use
them for this: they are minutes away in time, so electrode drift, impedance change and
alertness differ. The second immediately before the click is contemporaneous with the
trial, which is exactly what ERD normalisation needs.

**What to do with the anomalies.** Keep the 148 s iteration (cropping to 4 s makes it
harmless), drop the duplicate mark 4 and the two iterations with no preceding rest, and
accept 24 vs 51 as genuinely unbalanced rather than discarding good right-hand data to
match — the two panels are averaged independently, so imbalance does not bias the plot.

---

## 6. 500 Hz → 250 Hz: exactly which parameters change

Your instinct about the window was right, and the reason is worth being precise about.
**Only parameters expressed in samples change. Parameters expressed in Hz or in seconds
do not.**

| Parameter | Paper @ 500 Hz | Yours @ 250 Hz | Changes? |
|---|---|---|---|
| Band-pass 8–30 Hz | 8–30 Hz | 8–30 Hz | **No** — `butter` normalises cutoffs by Fs |
| Butterworth order | 2 | 2 | **No** — dimensionless |
| Smoothing coefficient | **200 samples** | **100 samples** | **Yes** — 200/500 = 0.4 s; 0.4 × 250 = 100 |
| Baseline −1…0 s | 500 samples | 250 samples | **Yes** (same 1.0 s) |
| Epoch −1…+4 s | 2500 samples | 1250 samples | **Yes** (same 5 s) |
| `xlim` | [500 2500] | [250 1250] | **Yes** (same −1…4 s) |
| MI window | 4 s | 4 s | **No** |

So the honest answer to "we might need a smaller window size": yes — **100 instead of
200** for the smoothing — but not because 250 Hz is worse at representing the signal.
8–30 Hz needs only 60 Hz to sample without aliasing; 250 Hz is four times that. The
change is purely a unit conversion: the paper's `200` *means* 0.4 s, and 0.4 s at your
rate is 100 samples. If you left it at 200 you would be smoothing over 0.8 s and
flattening real structure.

Where 250 Hz genuinely costs you: frequency **resolution** in a time-frequency map is set
by window length in seconds, not by Fs, so that is unaffected; but your usable band tops
out at 125 Hz instead of 250 Hz, which only matters for EMG/gamma work, not for 8–30 Hz
motor imagery. **For this analysis, 250 Hz is not a limitation.** The 4-channel montage
and the trial count are.

---

## 7. The result — and it is not the result you want

All 72 epochs, paper's method, parameters rescaled as above → `erd_pooled.png`.

Grand-average curves (power averaged across trials, then normalised — the paper's order
of operations) look mildly encouraging: during left-hand MI, C4 sits below C3 for the
first ~2.5 s; during right-hand MI, C3 sits below C4 from ~1–3 s. Both are the correct
contralateral direction.

**That appearance does not survive a test.** Averaging power across trials *before*
normalising lets a few high-amplitude trials dominate the curve. Computing ERD per trial
and then testing across trials:

| task | n | contralateral | ipsilateral | difference | p (paired t) | p (Wilcoxon) |
|---|---|---|---|---|---|---|
| Left hand | 22 | +37.9 % | +35.2 % | **+2.7** | 0.773 | 0.874 |
| Right hand | 50 | +30.0 % | +28.3 % | **+1.7** | 0.839 | 0.674 |

A real contralateral ERD needs the difference to be **negative** and significant in both
rows. Both are positive and both p-values are ~0.8. The laterality index (C3 − C4 per
trial) is −2.7 for left trials and +1.7 for right trials, Mann-Whitney **p = 0.75** —
and even the sign is backwards from the prediction.

Also note every number above is **positive**: power *rises* during the marked period
relative to the preceding second. That is ERS, not ERD, across the board — and it points
straight at a confound, discussed next.

---

## 8. Why it probably came out this way, and what to fix

**(a) You clicked the mouse to start each trial.** You confirmed the mark is a manual
click at task start. That means a real hand movement happens at t ≈ 0, right at the
boundary between your baseline second and your MI window — and the hand doing the
clicking is the same motor cortex you are measuring. Whatever the click does to C3/C4, it
does it identically in every trial of both classes, and it lands exactly where the effect
should be. This alone could produce the uniform power increase after t = 0.
**Fix: software-driven cues.** Let the program show the prompt and write the marker
itself; keep your hands still throughout. `SpeechEEG_Recorder/core/trial_manager.py`
already does timed prompts with `prompt_time_ms` — it is most of the way there.

**(b) Reaction-time jitter destroys the average.** Even without the click artefact, a
manual mark means t = 0 varies by a few hundred milliseconds from trial to trial. ERD
averaging assumes alignment; jitter of ±300 ms smears a 1 s effect into mush. This is the
single biggest reason a real effect could be present and invisible here.

**(c) Every file is single-class.** This is the one that invalidates the classifier
numbers, and it is worth stating plainly: the previous work in this folder
(`gelo_bci/output/svm_results.csv`) shows **leave-one-iteration-out = 75–83 %** but
**leave-one-file-out = 53–66 %**, with a permutation test at
`observed 65.2 %, null mean 48.6 %, p = 0.089`. Both were reproduced against the real
data here. A model tested on a trial whose siblings are in the training set only has to
recognise the recording session — and since session ⇒ class, it scores well without
learning anything about hands. **The 75 % figure I gave you earlier in this conversation
came from exactly that leak and should be discarded.**
**Fix: interleave left and right randomly inside one session**, as the paper does. Until
the data is recorded that way, no cross-validation scheme can separate "hand" from
"session", because in this dataset they are the same variable.

**(d) Trial timing is uncontrolled.** 4.9 s to 148 s per iteration means the task was not
the same length twice. Fix a duration — the paper uses 4 s — and let the software end the
trial.

**(e) Two electrodes over motor cortex is thin, but it is not the bottleneck.** C3/C4 is
the correct pair and enough for a laterality index. Fix (a)–(d) first; more electrodes
will not rescue jittered, session-confounded trials.

### If you record again, the minimum changes worth making

1. Randomly interleave left and right within every session (the paper's alternation).
2. Software-timed prompt → fixed 4 s imagery → fixed rest, with the marker written by the
   program at cue onset, not by hand.
3. Hands completely still; no clicking to start a trial.
4. Keep the 30 s eyes-open/eyes-closed blocks — they are a genuine control, and you
   already record them.
5. Aim for 40+ trials per class per session, and more than one session per day-of-recording
   so session effects can at least be modelled.

---

## 9. Files

| file | what |
|---|---|
| `extract_epochs.py` | reads `left/`+`right/`, finds iterations, cuts padded onset-locked epochs → `epochs.npz` |
| `erd_analysis.py` | paper's ERD/ERS + the statistical tests + all figures |
| `erd_pooled.png` | **main figure** — paper's method, paper's axis, all trials |
| `erd_per_session.png` | same, one panel pair per recording session |
| `erd_codebaseline.png` | what you get with `PlotEvent.m`'s 0–1 s baseline instead |
| `erd_causal.png` | what you get with the causal `filter()` their code uses |
| `erd_stats.csv` | the per-trial test table from section 7 |
| `epoch_meta.csv` | every iteration: duration, pre-onset rest, why it was kept or dropped |
