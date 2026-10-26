# MI Live: left / right from imagination, in real time, for a bot

Imagine squeezing your LEFT or RIGHT hand; the window turns it into a bot command (LEFT / RIGHT / STOP or
FORWARD) 25 times a second. An on-screen bot follows it; the same command can go to a real bot by UDP
(Wi-Fi, Raspberry Pi, ESP32) or USB/Bluetooth serial (Arduino).

Models: the best BCI IV 2b model for a new person (**filter-bank CSP + SVM with Euclidean Alignment**,
`models/base_2b_live.json`), and **your own model**, trained after a calm calibration from your trials plus 2b.
The code of `apps/mi_bci` is used read-only.

**User guide (PDF): `docs/MI_Live_User_Guide.pdf`** - how to use the app and what each step does, for anyone (rebuild: `C:\Python313\python.exe docs\build_user_guide.py`).

## Start

| What | How |
|---|---|
| With the headphones | double-click `run.bat` (Scan -> Connect) |
| No headset: simulator | `run_simulator.bat`, hold the Left / Right arrow keys to "imagine" |
| Real EEG demo (2b) | `run_demo_2b.bat`: B04 session 4 streamed live; the model never saw B04. Edit `--sub 1..9`, `--speed 2` |
| Tests | `C:\Python313\python.exe -m pytest -q tests` (17 tests) |
| Whole flow check | `C:\Python313\python.exe live.py --source sim --speed 8 --selftest` -> `_out/selftest.json` |
| Score your recordings | `C:\Python313\python.exe tools\train_personal_cli.py Pratham P01` |
| Competition-style check, all 9 | `tools\check_2b_live_parallel.bat`, then `C:\Python313\python.exe tools\merge_check.py` |
| Compare all 2b model types | `C:\Python313\python.exe tools\compare_models.py`; rebuild with `tools\build_live_model.py` |
| See UDP commands | `C:\Python313\python.exe tools\udp_listen.py` then tick "Send to bot by UDP" |

## How to use it (headset)

1. **Signal check (15 s).** Sit still. Shows EEG and 50 Hz hum in uV with GOOD / FAIR / BAD and what to fix.
   Hum above ~10 uV: unplug the charger, press the C3/C4 pads and ear clips firmly on skin, move away from cables.
2. **Calibrate (calm screen).** A separate full-screen black window: only a cross and, for ~1 s, an arrow.
   Left and right trials are mixed at random, in blocks (default 3 x 10 + 10) with a break between blocks
   (Space = next block, Esc = stop). Nothing moves, no numbers, no feedback. The arrow is small and sits on
   the cross: keep your eyes on the cross (eye movements are picked up by the ear clips). Optional first block of REAL
   squeezes (a warm-up and a check that the electrodes see hand activity). Each block is saved as a run.
3. **Your model** is trained automatically: 3 model types x 3 weightings (2b only / 2b + yours / yours only),
   each scored by leave-one-run-out (never tested on a run it saw). Runs with a BAD signal are left out.
   Shows the left/right pattern (ERD), all scores, the choice and a verdict: PROMISING (p < 0.05 after
   correcting for the 9 tries) or NOT READY.
4. **Cued test** on the same calm full screen (no feedback by default). Accuracy, p, confusion, kappa.
   A PROMISING model becomes **READY only when this test on new trials is also above chance** (found on
   2026-10-26: a 65 % leave-one-run-out model scored 4/20 on the next run).
5. **Free mode**: just imagine. "Calm display" (on by default) hides the jittery trace; you see the bar,
   the big LEFT / RIGHT word and the bot.

## The pipeline (one output every 40 ms)

| Step | What | Where |
|---|---|---|
| 1 | C3-A1, C4-A2 (ear reference) | `mibci.dsp.apply_montage` |
| 2 | **50 Hz notch** (causal; 2b was recorded with one), dropped samples held | `milive/dsp_extra.py` |
| 3 | per band (9 bands 4-40 Hz): causal Butterworth, covariance of the last 2 s | `mibci.svm.CovWindow` |
| 4 | Euclidean Alignment per band: running mean since calibration, artifact windows skipped (no labels) | `milive/pipeline.py` |
| 5 | CSP per band -> scaler -> linear SVM -> distance d (negative = left), minus running bias | `milive/models.py`, `pipeline.py` |
| 6 | 2 s integrator v = mean sign (-1..+1); LEFT if v <= -0.5 for 0.5 s, RIGHT if >= +0.5, else STOP / FORWARD | `milive/pipeline.py` |

Safety: STOP during signal check, calibration, test, training, artifacts (> 0.5 s) and when no EEG has
arrived for 1 s. Delay: a command follows a change of imagery after about 2-4 s.

## What the first recordings showed (2026-10-26, P01 + Pratham, 100 imagery trials)

| | Result |
|---|---|
| 50 Hz hum today | 54-69 uV at C3, 17-23 uV at C4 (EEG only 6-8 uV); earlier session 8-14 uV |
| Hum through the 8-30 Hz filter (before the notch) | ~9 uV - more than the EEG: it steered the decoder (fixed with the notch) |
| Left/right pattern in imagery (ERD) | none (mu +0.05 p = 0.35, beta -0.09 p = 0.81); power rose on BOTH sides after the cue (visual/attention, not motor) |
| Best model on your data (leave-one-run-out, 9 tried) | 49 % - NOT READY. The 2b models: 39-41 % |

So the limit today is the signal, not the model. Next session: GOOD signal check first, the calm calibration
(3-4 blocks), and the real-squeeze block to confirm the electrodes see hand activity on the correct side.
The 2b models scoring a little BELOW 50 % (39-41/100) could hint that left and right are swapped on the
headset, but P01's real-movement run showed the correct side; the squeeze block will settle it.

## Which model and why (2b, each person unseen, live setting with notch)

| Model | Mean accuracy | vs CSP + SVM |
|---|---|---|
| **filter-bank CSP (9 bands 4-40 Hz) + SVM** (used) | **77.4 %** | better 6/9, worse 3/9 (p = 0.20) |
| filter-bank CSP + LDA | 77.3 % | better 5/9 |
| filter-bank tangent space + SVM | 76.8 % | better 5/9 |
| log power + SVM 8-30 Hz | 75.9 % | better 5/9, worse 1/9 |
| CSP + SVM 8-30 Hz (mi_bci's model) | 75.4 % | - |

The 2008 winner (FBCSP, kappa 0.60) was trained on each person's own sessions, so it cannot be used on a new
person; this comparison is the one that matters for a new user.

## Verified (2026-10-26, after the notch, calm calibration and personal model were added)

* 17/17 tests: live = independent offline computation (both models, with artifacts), notch removes 50 Hz and is
  packet-independent, 2b training features = live features, signal check flags hum, personal model READY with a
  signal and NOT READY without, saved runs readable by mi_bci, UDP, command rule, freeze/resume.
* Whole flow on the simulator: signal check GOOD -> calm calibration 2 blocks -> personal model READY ->
  cued test 16/16 -> free mode RIGHT then LEFT.
* Real 2b EEG through the window: B04 session 4, 96.7 % (153 trials).
* BCI IV 2b sessions 4 + 5, each person decoded by a model that never saw them, live = offline in all 9:

| | B01 | B02 | B03 | B04 | B05 | B06 | B07 | B08 | B09 | Mean |
|---|---|---|---|---|---|---|---|---|---|---|
| Accuracy | 75 % | 64 % | 57 % | 95 % | 80 % | 87 % | 76 % | 85 % | 81 % | **77.7 %** |
| Max kappa | 0.53 | 0.33 | 0.18 | 0.90 | 0.67 | 0.76 | 0.58 | 0.79 | 0.73 | **0.60** |

## Files

```
live.py                     the window (signal check, calm calibration, training, test, free mode)
milive/pipeline.py          live steps, alignment, seeding from calibration
milive/dsp_extra.py         50 Hz notch, signal check
milive/personal.py          your model: yours + 2b, leave-one-run-out, verdict
milive/models.py            one model format for every type; model list
milive/train2b.py           2b training rows (cached in _out/train2b_cache_notch)
milive/cued.py              cued test scoring, kappa over time
milive/replay2b.py          2b session as a live source
milive/commands.py, bot.py  UDP / serial out, on-screen bot
bot_examples/arduino_bot/   Arduino 2-wheel bot (L / R / F / S, stops after 1 s silence)
tools/                      analyze_subject, train_personal_cli, compare_models, build_live_model, check_2b_live(_parallel), merge_check, udp_listen
```
Recordings: headset -> `data/mi_bci/<subject>/` (mi_bci can use them), models -> `data/mi_bci/<subject>/decoders_live/`;
simulator -> `data/mi_live/SIM/`.

## Session 2026-10-26 evening (Pratham), after the fixes
| Run | Signal | Result |
|---|---|---|
| 3 calm calibration blocks | GOOD (hum 2-4 uV, EEG 7-9 uV) | own model leave-one-run-out 65 % (p_corr 0.016) |
| cued test with that model | GOOD | 4/20 - not confirmed |
The left/right direction flipped between runs (2b model 7, 5, 7 of 20 in calibration, 15/20 in the test),
which is what 20-trial runs look like without a stable signal; not a headset swap (that would flip all runs).
Eye-movement check (tools/eye_check.py): weak, p = 0.08. Tools: session_summary.py, check_test_run.py,
swap_check.py, eye_check.py.
