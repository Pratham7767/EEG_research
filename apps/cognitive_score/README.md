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
| Real headphones | double-click `run.bat` (or `python app.py`) |
| No hardware (simulator) | double-click `run_simulator.bat` (or `python app.py --simulate noise --fast`) |
| Also save raw EEG | `python app.py --record-eeg` |
| Automatic UI self-test | `python app.py --selftest` (exit code 0 = PASS) |
| Headless check (no window) | `python -m cogscore.headless --live 120` (real device) |

Requires Windows 64-bit and Python 3.11+ (tested with 3.13.5). `pip install -r requirements.txt`.

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
**Stress episode:** stress ≥ 80 for 30 s (ends below 65 for 30 s); ends when a break starts. Shaded on the timeline and logged.
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
python -m pytest -m "not sim"          :: 71 unit tests, ~9 s, no DLL needed
python -m pytest -m "sim and not slow" :: SDK contract + headless + UI self-test on the simulator (~2 min)
python -m pytest                       :: all 80, incl. real 30 s calibration on the simulator (~3.5 min)
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
cogscore/headless.py   full flow without UI + session validator
cogscore/ui/           customtkinter wizard
docs/build_manual.py   builds docs/manual.html + .pdf (via Edge) from a recorded session + self-test screenshots (docs/screens)
cogscore/capsule_sdk/  minimal vendored Capsule wrapper + DLL (fixes listed in CHANGES.md)
```
