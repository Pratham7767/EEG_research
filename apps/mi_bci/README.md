# MI-BCI: move a smiley with left/right hand imagery (real time)

A real-time left/right motor-imagery BCI for our LEHeadPhones2 headset, built on the design of the
Graz system that recorded BCI Competition IV 2b (Leeb et al. 2007). The model is **our SVM**
(CSP + SVM + Euclidean Alignment), starting from a base trained on BCI 2008 (2b) and improved with
each person's recordings. Background: the doc *Real-time Left/Right BCI: How Graz Did It and How We
Build It*, and `PROJECT_HISTORY.md` in the repo root.

## Start

| What | How |
|---|---|
| With the headphones | double-click `run.bat` |
| Without a headset | double-click `run_simulator.bat` (subject "SIM", never mixed with real data) |
| Check the whole app | `C:\Python313\python.exe app.py --selftest` (opens the window, runs everything on the simulator, closes; result in `_out/selftest.json`) |
| Automated tests | `C:\Python313\python.exe -m pytest -q tests` (21 tests) |
| SVM on real EEG (2b) | `C:\Python313\python.exe tools\svm_check_2b.py` (each 2b subject as a new user) |
| Rebuild the base SVM | `C:\Python313\python.exe tools\build_base_svm.py` (needs the 2b data; ~7 min once) |
| Beeps / headset SDK | `tools\check_sound.py`, `tools\check_sdk.py` |

Needs `C:\Python313\python.exe` with numpy, scipy, scikit-learn and sounddevice (installed on this PC).
The headset SDK is loaded from `hardware/eeg_headphones/brain_bit/pyneurosdk2-1.0.15`.

## One session, step by step (the app's tabs)

Before you start: laptop charger unplugged, hands off the laptop, sound on the laptop speakers.

1. **Connect.** Type the subject code at the top (e.g. `P01`; each code has its own runs and model).
   Scan, pick the headphones, Connect. Every electrode should read *good* (< 500 kOhm) or *fair*.
   Then **10 s signal test**: wait for GOOD (5-50 uV of EEG). **Test beep** should be audible.
2. **Record.**
   - *Baseline* first in every session (also aligns the SVM to that day): eyes open 60 s, eyes closed
     60 s, blinks 30 s, jaw clenches 30 s.
   - *Movement check*: really squeeze the cued hand. 2-3 runs on the first visit.
   - *Screening*: imagine squeezing the cued hand, hands still. 4-6 runs of 10 + 10 trials.
     Trial: cross + beep at 0 s, arrow 3-4.25 s, keep imagining until 7 s, rest 1.5-2.5 s.
3. **Check & Train.**
   - *Alpha check* on the baseline: alpha should rise with eyes closed.
   - *ERD check*: movement and imagery checked separately. PASS = power drops on the side opposite the
     hand (left hand -> C4) with p < 0.05. Needs about 30 trials per hand to judge.
   - *Train decoder*: retrains the SVM on 2b + your screening/feedback runs. Shows SCORE (accuracy on
     your runs, each tested by a model that never saw it), the weighting chosen and a VERDICT.
4. **Feedback** (when the verdict says READY). Grey smiley, beep at 2 s, arrow and live feedback
   3-7.5 s. Keep the smiley on the arrow's side: green = correct side, red = wrong. 4 runs of 20 + 20.
   *Retrain* afterwards: the new model is used only if >= 5 points better on the latest feedback run.
5. **Log.** Everything the app did. `Esc` stops a running run (what was recorded is kept).

## The model: our SVM

The same pipeline as `experiments/05_bci_iv_2b/gelo_svm_pipeline.py`, rebuilt to run live (`mibci/svm.py`):

| | Original (offline) | App (live) |
|---|---|---|
| Method | CSP (2 filters, log) + scaler + linear SVM, Euclidean Alignment | same |
| Base data | BCI IV 2b, 9 subjects, C3/C4 | same (`models/base_2b_svm.json`) |
| Window | 3 s per trial | last 2 s, new output every 40 ms |
| Filter | 8-30 Hz zero-phase | 8-30 Hz causal (past samples only) |
| SVM C | grid search | 0.1 |
| Channels | C3, C4 (gel bipolar) | C3-A1, C4-A2 (dry, ear-referenced) |

- **Alignment:** each recording day is re-centred on the mean covariance of that day's recordings. No labels.
- **Improving it:** *Train* refits on 2b + your runs three ways (2b only / 2b + yours / yours only), scores
  each on your runs leaving one run out at a time, keeps the best. The base is used until you train.
- **Smiley:** mean sign of the last 2 s of outputs (as Leeb 2007), redrawn 25 times a second.
- **Clock:** the paradigm runs on the EEG sample count, so every marker is the exact sample at which the
  screen changed, and outputs do not depend on how Bluetooth packets are split.
- **Artifacts:** no EOG channels, so outputs are skipped when the last 1 s of C3/C4 (high-passed at 1 Hz)
  has a peak-to-peak > 4 x its running median or > 1500 uV.
- **Sound:** beeps go to the laptop speakers through one always-open stream (`mibci/sound.py`). Windows'
  default output was the EEG headset itself, where beeps over Bluetooth were sometimes lost.
- The Graz LDA is still in the code for comparison (`MODEL = "lda"` in `mibci/config.py`), not used.

## Verified (2026-10-26)

- 21/21 automated tests, including leak checks (no signal in the data -> the model does NOT look good)
  and live engine = offline trainer, for both the SVM and the old LDA.
- App self-test through the real window: signal test, baseline, movement, 3 screening runs, SVM training,
  feedback; every drawn frame read back from the canvas (arrow side, smiley side and colour).
- SVM on real EEG (BCI IV 2b), each subject treated as a new user: base from the other 8 subjects, improved
  with their screening sessions, streamed live on their 3 feedback sessions. Live outputs identical to the
  offline scorer in all 9 subjects.

| Subject | B01 | B02 | B03 | B04 | B05 | B06 | B07 | B08 | B09 | Mean |
|---|---|---|---|---|---|---|---|---|---|---|
| SVM base only (live) | 72 % | 57 % | 53 % | 98 % | 77 % | 80 % | 75 % | 88 % | 82 % | 75.9 % |
| SVM improved with own screening (live) | 70 % | 57 % | 55 % | 98 % | 78 % | 80 % | 75 % | 88 % | 85 % | 76.0 % |

(The Graz LDA trained only on own screening data reached 72-73 % on the same sessions.)

## Where things go

```
apps/mi_bci/
  app.py                the window (tkinter)
  run.bat, run_simulator.bat
  models/base_2b_svm.json   the base SVM (in git)
  mibci/
    config.py           every setting: timing, windows, montage, model choice, paths
    sources.py          HeadphonesSource (pyneurosdk2), SimulatedSource, ReplaySource
    svm.py              live CSP+SVM+EA (feature window, alignment, JSON model)
    svm_trainer.py      base model from 2b, Train (3 weightings, leave-one-run-out), session alignment
    dsp.py              montage, artifact check (+ band power for the old LDA)
    decoder.py          model loading, 2 s integrator (+ old LDA)
    paradigm.py         trial schedule on the EEG sample clock; baseline blocks; replayed events
    engine.py           live loop: source -> features -> model -> integrator -> screen + recording
    recorder.py         run folders (eeg.csv, events.csv, outputs.csv, run.json)
    analysis.py         alpha check, ERD check, signal test
    sound.py            beeps on the laptop speakers
    trainer.py          shared scoring + the old LDA trainer
    cli.py              the same without a window
  tests/                test_core.py, test_svm.py
  tools/                svm_check_2b, build_base_svm, base_model_check, replay_2b, inspect_session,
                        check_real_signal, check_sound, check_sdk
  _out/                 caches and check outputs (not in git)
data/mi_bci/<subject>/<date_time>_<run type>/   recordings
data/mi_bci/<subject>/decoders/                  decoder_<date>.json, current.json, report_<date>.json
data/mi_bci/<subject>/signal_tests/              raw 13 s signal tests
```

## Not verified yet

See "Open problems" in `PROJECT_HISTORY.md`: imagery on our headset (P01 has 1 imagery run so far),
Bluetooth delay, the packet-numbering assumption, and whether the base SVM helps on our montage.
