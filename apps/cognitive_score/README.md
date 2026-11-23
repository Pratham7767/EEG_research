# Cognitive Score: Focus & Fatigue Session Monitor

A desktop app for the Neiry/Capsule EEG headphones. It walks you through every
setup step, then shows live concentration, relaxation, cognitive load and
accumulated fatigue, suggests breaks, and records everything. See [plan.md](plan.md)
for the design, the reasoning behind each step, and the full test plan.
**User manual (plain English, with figures from a real session): [docs/manual.pdf](docs/manual.pdf) (also [HTML](docs/manual.html)).**
**How it works (every step: how, why, from where): [docs/how_it_works.pdf](docs/how_it_works.pdf), built by `python docs/build_explainer.py`.**

## Run

| What | How |
|---|---|
| Real headphones, choose the mode | double-click `run.bat`: a start window offers **Demo** or **Real use** |
| Demo mode directly | double-click `run_demo.bat` |
| Real-use mode directly | double-click `run_real.bat` |
| Stage backup: replay a recorded session | in the start window, pick a session next to *Replay* (or `python app.py --replay sessions\<name>`) |
| No hardware (simulator) | double-click `run_simulator.bat` (start window, then the `noise` simulator) |
| Automatic check of every screen, both modes | double-click `run_selftest.bat` (simulator; prints SELF-TEST PASSED) |
| Also save raw EEG | add `--record-eeg` (then a replay also shows the EEG trace) |
| Full screen for a projector | **F11** or the *Full screen* button (Esc leaves it); `--fullscreen` starts full screen |
| Headless check (no window) | `python -m cogscore.headless --live 120 [--mode demo]` (real device) |

The `.bat` files use `C:\Python313\python.exe` (the plain `python` on this PC is 3.8 without the packages).
Requires Windows 64-bit and Python 3.11+ (tested with 3.13). `pip install -r requirements.txt`.

## Two modes

Both modes measure exactly the same way (same filters, formulas, thresholds). Only the timings differ.

| Timing | Real use | Demo |
|---|---|---|
| Stress / fatigue reference ("50 = your first minutes of work") | first 2 min | first 1 min |
| Fatigue break prompt possible after | 10 min | 3 min |
| Fatigue must stay ≥ 70 for | 3 min | 30 s |
| Time-based break prompt (sure to appear) | 50 min without a break | 6 min |
| A break counts as "real" (restarts the timer) after | 2 min | 20 s |
| At most one break prompt every | 10 min | 2 min |
| Stress episode: ≥ 80 (start) / < 65 (end) held for | 30 s | 15 s |
| Sleepiness check-in | every 10 min | at 4 min (then every 4 min) |
| Live timeline shows the last | 30 min | 10 min |
| Scene buttons and "What changed" table | – | yes |

The mode is saved in `session.json` (`mode`, `settings`) and shown in the sidebar and on the summary.

### Demo scenes

In demo mode the live screen has four buttons. Each one puts a labelled band on the timeline, shows a big
instruction with a countdown, and plays a tone at the end (the wearer may have their eyes closed).

| Scene | Length | Instruction | What usually happens |
|---|---|---|---|
| 1 Rest | 30 s | eyes open, sit still | the comparison period |
| 2 Eyes closed | 20 s | close your eyes and relax | **alpha power jumps** (the most reliable EEG effect) |
| 3 Mental math | 60 s | count down in 7s silently, jaw still | attention / cognitive load tend to rise |
| 4 Relax | 45 s | eyes closed, slow breathing | relaxation up; fatigue may build towards a break prompt |

The summary then shows **What changed in each scene**: the difference of each score's average versus *Rest*
(or versus the rest of the session if no Rest scene was run), and the change of alpha power. The first 5 s of
each scene are skipped. The sleepiness check-in waits until a scene is over; starting a break ends a scene.

### If the headphones drop out

The app reconnects by itself (one automatic try, which retries 3 more times). If that fails, a **Reconnect**
button appears at the bottom right. After reconnecting, the calibration and baseline are put back into the
SDK, and the session continues in the same folder; the drop is logged (`events.csv`: `disconnected`,
`reconnected`; summary: `disconnects`). During calibration or baseline, a drop stops that step; press
Start again once reconnected.

### Replay (stage backup)

Plays a recorded session back through the same app, at its original pace, with a yellow
**REPLAY: RECORDED DATA** badge and "(REPLAY of …)" in the window title. Nothing is re-measured: the values
are those the app computed in the original session, so the scores match it (checked on 2026-11-21_105125:
attention 64.2 vs 64.1, stress 55.8 vs 55.7, fatigue 43.3 vs 43.3). Scenes, markers and breaks of the
original are replayed too. The replay is saved as a new session with `replay_of` in `session.json`.
Record a good rehearsal in **demo mode** (ideally with `--record-eeg`) so it can be your backup.

### New session

*New session* on the summary closes this window and opens a new one in the same mode (the vendor wrapper allows
one headset connection per process, so each session is a fresh process).

## The steps

1. **Setup**: four quick checks (charged, paired as `USAMS-YX05`, electrodes on skin, seated).
2. **Connect**: search, pick the headset, connect (3 automatic retries).
3. **Signal**: every electrode must be Good (< 500 kΩ) or Fair (≤ 1 MΩ) for 5 s.
4. **Eyes-closed calibration**: 30 s, with a tone at the start and end. Measures your alpha peak.
5. **Baseline**: eyes open on a cross, 30–90 s. Scores are relative to it.
6. **Session**: live scores, timeline, brain-wave bars, breaks, markers, sleepiness check-in every 10 min.
7. **Summary**: averages, stress episodes, whole-session timeline, band changes.

Recalibrate every session. Baselines varied up to 7× between days in earlier recordings.

## What the numbers mean

| Metric | Source | Scale |
|---|---|---|
| Attention | SDK Emotions (normalised β/α) | 0–100 |
| Cognitive load | SDK Emotions (normalised θ/α) | 0–100 |
| Stress | high-β (20–30 Hz) / α, 30 s smoothing | 0–100, **50 = your first 2 min of work**, ×2 ≈ 88 |
| Fatigue | (θ+α)/β, 60 s smoothing | 0–100, 50 = your first 2 min of work |
| Relaxation | SDK Emotions (normalised α/β) | 0–100 |
| Brain waves | raw EEG, δ 1–4 · θ 4–8 · α 8–13 · β 13–30 · γ 30–45 Hz | % change of each band's power vs the rest baseline |

Stress and fatigue show "Starts in m:ss" for the first 2 minutes (break time does not count).
**Stress episode** (real-use timings; demo: see the table above): stress ≥ 80 for 30 s (ends below 65 for 30 s); ends when a break starts. Shaded on the timeline and logged.
**Break prompt:** fatigue ≥ 70 for 3 minutes (after the first 10 minutes), or 50 minutes without a real break
(≥ 2 min). At most one prompt per 10 min, so an ignored prompt repeats every 10 min. Nothing during a break;
fatigue during a break does not count. The sleepiness check-in waits until the break is over.

Stress from EEG is an *arousal* measure relative to your own baseline, not a clinical stress test, and γ /
high-β at these electrode sites pick up jaw and neck muscle activity. See plan.md §9 for the evidence and limits.

## Output (`sessions/<date_time>/`)

| File | Contents |
|---|---|
| `session.json` | device, calibration, SDK baseline, our own baseline, summary |
| `scores.csv` | the five 0–100 scores at 1 Hz |
| `bands.csv` | δ–γ relative (and absolute µV²) power every 0.5 s, with rejection reason |
| `emotions.csv`, `productivity.csv`, `indexes.csv` | raw SDK classifier output |
| `indices.csv` | ratios from the SDK spectrum (vendor formulas + arousal) |
| `resistances.csv`, `artifacts.csv`, `cardio.csv` | signal quality, pulse (Pro headsets) |
| `events.csv` | markers, breaks, stress episodes, check-ins, warnings |
| `eeg.csv` | raw + processed EEG (only with `--record-eeg`) |

## Tests

```bat
python -m pytest -m "not sim"          :: 81 unit tests, ~20 s, no DLL needed (incl. modes, scenes, replay)
python -m pytest -m "sim and not slow" :: SDK contract + headless + UI self-test on the simulator (~2 min)
python -m pytest                       :: all 90, incl. real 30 s calibration on the simulator (~3.5 min)
```

Hardware acceptance and signal-validity checks (eyes closed vs open, blink/jaw
artifacts, arithmetic vs rest) are manual; see plan.md §6.4–6.5.

## Layout

```
app.py                 entry point / CLI
cogscore/config.py     every threshold and timing
cogscore/engine.py     Capsule SDK wrapper + state machine (pumped from the UI loop)
cogscore/monitor.py    gates, smoothing, break/self-report rules, recording
cogscore/metrics.py    SDK-spectrum ratios, 0-100 score mapping, baseline collector (pure)
cogscore/spectral.py   raw-EEG band powers: filtering, Welch, artifact rejection (pure)
cogscore/quality.py    electrode grading, contact gate, artifact window (pure)
cogscore/rules.py      break rule, KSS scheduler (pure)
cogscore/session.py    CSV/JSON writers
cogscore/headless.py   full flow without UI + session validator (also --replay, --mode, --scenes)
cogscore/replay.py     ReplayEngine: a recorded session played back with the CapsuleEngine interface
cogscore/ui/           customtkinter wizard (start.py = Demo / Real use / Replay start window)
docs/build_manual.py   builds docs/manual.html + .pdf (via Edge) from a recorded session + self-test screenshots (docs/screens)
cogscore/capsule_sdk/  minimal vendored Capsule wrapper + DLL (fixes listed in CHANGES.md)
```
