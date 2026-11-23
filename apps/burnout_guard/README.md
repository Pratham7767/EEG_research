# Burnout Guard

A private desktop companion for the Neiry/Capsule EEG headphones that helps **one employee** keep a healthy
work rhythm: it suggests breaks at sensible moments, guides short recovery exercises, and tracks how you say you feel
over the weeks. It grew out of `apps/cognitive_score` (which is left unchanged) and reuses its device engine,
signal checks and EEG scoring.

**It is not a medical device.** It cannot detect, diagnose or treat burnout. Everything stays on this computer and
only you can see it.

## Run

| What | How |
|---|---|
| Real headphones | double-click `run.bat` |
| Try it without headphones, with 5 weeks of made-up history | double-click `run_simulator.bat` (uses a separate `demo_data/` folder) |
| Automatic check of every screen | double-click `run_selftest.bat` (temporary data folder; exit code 0 = PASS) |
| Unit + simulator tests | `C:\Python313\python.exe -m pytest` (98 tests, about 3 min; `-m "not sim"` for the fast 89) |

Requires Windows 64-bit and Python 3.11+ (tested with 3.13). `pip install -r requirements.txt`.
Each new work session starts a fresh app process ("Back to home" on the summary screen does this), because the
Capsule wrapper allows one device per process.

## What you see

1. **Home**: a strain-and-recovery indicator (Balanced / Keep an eye on it / Talk to someone / Not enough data yet)
   with the reasons behind it, today's monitored work, real breaks and exercises, hours in the last 7 days,
   a 14-day chart of work hours and breaks, the weekly burnout pulse against your own usual level, and the
   check-ins that are due. **Privacy & data**: open the folder, export everything as a zip, delete everything,
   retention period, and the optional 20-20-20 eye-rest reminder.
2. **Session** (setup → connect → signal → eyes-closed calibration → baseline → live): the live screen shows
   **Fatigue**, **Focus** and **Tension (experimental)** on a 0-100 scale where 50 is your level in the first
   2 minutes of work, plus cognitive load and minutes since your last real break.
3. **Break suggestions** appear as a banner with *Start break*, *Snooze 10 min*, *After this task* and *Skip*.
4. **Break room**: six guided exercises with a breathing pacer, a "how refreshed do you feel?" rating, and an
   honest EEG relaxation signal (see below). *Back to work* ends the break.
5. **Summary**: duration, real breaks, prompts and how many you took, exercises, average fatigue, signal quality.

Screens from the self-test are in `docs/screens/`.

## How it decides (and why)

The full evidence review is in `docs/research/EEG burnout prevention app evidence.md` (with the five research notes
next to it). The thresholds marked *design default* are reasoned choices, not validated values.

| Feature | Rule | Basis |
|---|---|---|
| Fatigue-triggered break | fatigue ≥ 70 (≈ 34 % above your start-of-work level) for 3 min, not in the first 10 min | theta and alpha rise with time on task (Tran 2020 meta-analysis, g ≈ 1.0 / 0.85); *design default* |
| Schedule fallback | 50 min without a real break (≥ 2 min) | HSE: "5-10 min every hour is better than 20 min every 2 hours" |
| Mid-morning anchor | one suggestion between 11:00 and 12:00 if you worked ≥ 30 min with no break today | mid-morning breaks restore more than late ones (Hunter & Wu 2016) |
| Not nagging | one prompt at a time; ≥ 20 min between prompts (40 min after 2 skips in a row); 45 min quiet after a real break; ≤ 8 a day; unanswered for 10 min = ignored | ~40 % of prompts are accepted in field studies (Luo et al. CHI 2018); prompt fatigue (Künzler et al.) |
| Break length | 3 min normally, 10 min when fatigue comes back after a recent fatigue prompt | micro-breaks ≤ 10 min: vigour d = 0.36, fatigue d = 0.35 (Albulescu 2022) |
| Exercises | cyclic sigh, slow breathing 4-6, gentle box breathing, eyes-closed reset, look far away (20-20-20), desk stretch and walk | slow breathing g ≈ −0.35 on stress (Fincham 2023); cyclic sighing (Balban 2023); green view (Lee 2015) |
| Relaxation signal | median relative alpha in the minute before the break vs the last minute of an eyes-open exercise; not computed for eyes-closed or movement exercises | alpha also rises with closed eyes and with fatigue, so it cannot prove recovery; always shown next to your own rating |
| KSS check-in | 1 min after the session starts, then hourly | experience sampling: 1-3 short prompts a day keep compliance high (Williams 2021) |
| Weekly pulse | BAT4, weekly; compared with your own baseline (median of your first 4 weeks); 2 weeks ≥ 0.5 above → *keep an eye on it*, 4 weeks → *talk to someone* | BAT4 has no published cut-off (Hadzibajramović 2024); *design default* |
| Wellbeing | WHO-5 every 2 weeks; ≤ 50 → *talk to someone* | Topp et al. 2015 |
| Monthly check | Copenhagen Burnout Inventory (personal + work); ≥ 50 → *talk to someone* | Kristensen et al. 2005 |
| End-of-day check-in | energy, demand (0-10), breaks taken; 7-day strain ≥ 7 with energy ≤ 3 → *keep an eye on it* | the app's own items, labelled as not validated |
| Work hours | 45 h / 55 h in 7 days are shown as context, never change the level | WHO/ILO 2021: ≥ 55 h/week raises stroke and heart-disease risk |
| Help | *talk to someone* shows Tele-MANAS 14416 / 1-800-891-4416 and suggests a doctor, counsellor or EAP | PIB press release |

**Why "Tension (experimental)" and not "Stress".** At these ear/temporal electrodes, 20-30 Hz power is dominated by
jaw and neck muscle activity, so the old high-beta/alpha "stress" score mostly measures muscle tension. It is also
safer not to label emotions (EU AI Act Art. 5(1)(f) bans inferring emotions in the workplace; fatigue is outside it).

**What EEG does not do here.** No EEG measure of burnout is validated, so EEG never moves the Home indicator.
It drives break timing within a day and adds context.

## Privacy

* Local only: no network code, no account, no telemetry. Data lives in `data/` next to the app (git-ignored).
* Raw EEG is not saved unless you start with `--record-eeg`.
* Session recordings are deleted after 90 days (adjustable); journal summaries stay until you delete them.
* Export everything as a zip or delete everything from **Privacy & data**.
* No employer view exists. The first-run notice warns that IT can read files on an employer-managed laptop.
* The research notes cover India's DPDP Act (main duties from 13 May 2027), GDPR, the EU AI Act, the FDA wellness
  guidance and neural-data laws. None of this is legal advice.

## Files

```
app.py                     entry point (--simulate, --fast, --data, --demo, --selftest, --screenshots, --record-eeg)
bguard/journal.py          private journal (data/journal.jsonl), settings, consent, export, delete, retention
bguard/questionnaires.py   BAT4, CBI, WHO-5 items (unmodified), scoring, schedule, plain-English results
bguard/trends.py           daily/weekly aggregation and the strain-and-recovery indicator
bguard/rules.py            BreakPlanner (break timing + anti-nagging), tension episodes, KSS schedule
bguard/recovery.py         exercises, breathing pacer timing, relaxation signal
bguard/monitor.py          live scores, breaks, exercises, journal entry per session
bguard/demo.py             made-up history for --demo
bguard/ui/                 home dashboard, dialogs (privacy, questionnaires, check-in, break room), session wizard
bguard/engine.py, spectral.py, metrics.py, quality.py, session.py, capsule_sdk/   from cognitive_score
tests/                     98 tests (journal, questionnaires, trends, planner, recovery, monitor, simulator, UI self-test)
docs/research/             research report and notes   docs/screens/  self-test screenshots
```

## Limits and next steps

* Thresholds marked *design default* need checking against real use: run it for a few weeks and compare break
  suggestions with how you felt (the KSS and end-of-day answers are recorded for exactly this).
* The fatigue score still uses (θ+α)/β. The research suggests dropping or capping the β term at these sites; worth
  testing on real recordings before changing it.
* Licences: BAT is free if unmodified and cited; CBI is free; WHO-5 is free with attribution (check the current
  WHO licence before any commercial use). The MBI is not used (paid, no individual feedback).
* Not validated on people yet. Nothing here should be read as a measurement of burnout.
