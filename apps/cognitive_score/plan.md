# Cognitive Score — Focus & Fatigue Session Monitor

A one-click desktop app that walks the user through every step needed to get
trustworthy cognitive scores from the Neiry/Capsule EEG headphones, then shows
live **concentration, relaxation, cognitive load and accumulated fatigue** with
break prompts, and records everything for later validation.

---

## 1. Goal and scope

| In scope (v1) | Out of scope (later) |
|---|---|
| Guided wizard: checklist → connect → signal quality → eyes-closed calibration → baseline → live session → summary | Physiological States (needs PPG, Headphones **Pro** only) |
| Vendor scores: Productivity (concentration, relaxation, fatigue, accumulated fatigue, growth rate, stress level, recommendation) and Emotions (attention, relaxation, cognitive load, cognitive control, self-control) | Speech-therapy trial integration (option 2) |
| Our own transparent indices computed from the SDK's cleaned PSD with the vendor's published formulas | ML models trained on our own data |
| Break prompts, markers, periodic self-report (KSS) | Cloud sync, multi-user accounts |
| Session recording (CSV + JSON) | PyInstaller single .exe (optional, M6) |
| Simulator mode (Capsule `Noise` / `SinWave` devices) so everything runs without hardware | |
| PPG probe: if the headset has a pulse sensor, show heart rate + Baevsky stress index | |

---

## 2. Facts established before planning (verified on this machine)

Probed `CapsuleClient.dll` (reports **v2.0.40**) with the SDK's simulated devices:

| Fact | Consequence for the design |
|---|---|
| Full pipeline runs with `DeviceType.Noise` / `SinWave`: connect, 30 s quick calibration (32 s), productivity baseline (31 s), live metrics | App and tests can run end-to-end without headphones |
| Resistances arrive **only after `device.start()`** | Signal-quality step comes after start |
| PSD, Emotions and artifact flags arrive ~**5.4 s after start**, no calibration needed | Quality step can show live signal immediately |
| Productivity metrics arrive only after calibration **and** baseline (~25/s on real hardware) | Live screen is gated on both |
| `import_alpha` + `import_baselines` → metrics in ~1.3 s | Fast integration tests and `--fast` demo mode |
| `SinWave` produces degenerate ratios (fatigue ≈ 1e6) | All scores are sanitised (non-finite / absurd → NaN, clamped) |
| PSD: 0–125 Hz at 0.1 Hz, ~23 callbacks/s × all channels | Throttle PSD reads to 2 Hz and only 1–30 Hz bins |
| Classifiers must be created **before** `device.start()` | Engine creates them right after connect |
| Single-threaded mode: callbacks fire inside `device_locator.update()` | Pump `update()` from the Tk main loop every 20 ms → no locking needed |
| Your past sessions: baselines varied up to 7× between days | Always recalibrate each session; never auto-import old baselines for real use |

Known SDK wrapper bugs to fix in our vendored copy:
1. `Emotions.py` field names are wrong (`focus, chill, stress, anger` are really `attention, relaxation, cognitiveLoad, cognitiveControl`, per `CEmotions.h`).
2. `Calibrator.calibrate()` calls the *Quick* C function.
3. `PSDData.get_band_lower/upper` are swapped.
4. `Productivity_FatigueGrowthRate` etc. come back as ctypes objects → need `.value`.

---

## 3. The guided flow (what the user sees)

Each step has a **gate**: the Next button unlocks only when the condition is met
(some gates offer "Proceed anyway", which is recorded in the session file).

| # | Step | What the app does | Gate to continue |
|---|---|---|---|
| 0 | **Setup** | Four checks: headphones charged/on, paired in Windows (`USAMS-YX05`), electrodes on skin, seated with notifications off. (The first real session paired fine through the built-in Intel adapter, so the vendor's "disable internal Bluetooth + dongle" step was dropped.) | All boxes ticked |
| 1 | **Connect** | Scan (Headphones / simulator), list devices, connect bipolar, retry 3× (2/5/10 s), create classifiers, `start()` | Connected and EEG flowing |
| 2 | **Signal quality** | Live resistance per electrode (good < 500 kΩ, average 500–1000, bad > 1000 — Capsule thresholds), live EEG trace, artifact flags, PPG probe | All electrodes ≤ 1000 kΩ held for 5 s (or "Proceed anyway") |
| 3 | **Eyes-closed calibration** | 30 s quick iAPF calibration; big countdown; **beep at start and end** (eyes are closed); shows iAPF result | `failReason == 0`; on failure explain (too many artifacts / peak at border) and offer retry |
| 4 | **Baseline** | Eyes open, relaxed, look at a fixation cross; progress bar from SDK | Baseline received |
| 5 | **Session** | Attention / Cognitive load / Stress hero cards, session timeline with stress episodes, brain-wave bars, relaxation + fatigue meters, break banner, markers, KSS every 10 min | User ends the session |
| 6 | **Summary** | Duration, average attention / load / stress, stress episodes, signal quality, whole-session timeline, average band change vs baseline | — |

### Live screen contents (v2, after the first real session)
- **Hero metrics (0-100):** Attention and Cognitive load from the SDK Emotions classifier; **Stress** = our
  arousal ratio high-β(20-30 Hz)/α from the SDK spectrum, mapped so **50 = your baseline**
  (score = 50 + 50·tanh(log₂(ratio/baseline)); ×2 ≈ 88, ×½ ≈ 12). Level words: Low < 35 ≤ Moderate < 65 ≤ High.
- **Stress episodes:** stress ≥ 70 for 15 s starts an episode, < 60 for 15 s ends it (hysteresis). Card is flagged,
  the timeline is shaded, start/end are logged in `events.csv`.
- **Session timeline:** the three hero metrics on one 0-100 axis (same scale, so one axis is correct), dashed
  line at 50 = baseline, breaks shaded grey, last 30 min.
- **Brain waves:** δ 1-4, θ 4-8, α 8-13, β 13-30, γ 30-45 Hz (IFCN 2017) from **raw** EEG (the SDK spectrum
  removes δ and most γ). Default view: % change of each band's relative power vs your baseline ("which band
  activates"); toggle: share of 1-45 Hz power.
- **Secondary:** Relaxation (SDK Emotions), Fatigue = (θ+α)/β vs baseline with 60 s smoothing; heart rate only
  if a pulse sensor is detected.
- **Break rule:** fatigue ≥ 70 for 3 min (not in the first 10 min), or 50 min without a break; 10 min cooldown.
- **Removed from the screen** (still recorded in CSV): vendor accumulated fatigue, vendor stress level, vendor
  recommendation, cognitive control, self-control, the formula table.
- **Self-report:** every 10 min a non-blocking KSS prompt (Karolinska Sleepiness Scale 1–9), the ground truth for validation.

---

## 4. Architecture

```
cognitive_score/
├── plan.md                  this file
├── README.md                how to run / test
├── requirements.txt
├── run.bat                  double-click launcher (real device)
├── run_simulator.bat        double-click launcher (Noise simulator)
├── app.py                   entry point: --simulate {noise,sinwave} --fast --selftest
├── cogscore/
│   ├── config.py            thresholds, timings, paths (one place to tune)
│   ├── events.py            tiny pub/sub bus (reused from SpeechEEG_Recorder)
│   ├── metrics.py           PURE: SDK-spectrum ratios, score mapping (50 = baseline), baseline collector, smoothing
│   ├── spectral.py          PURE: raw-EEG δ-γ band powers (high-pass, 50 Hz notch, Welch, artifact rejection)
│   ├── quality.py           PURE: resistance grading, artifact window, gate timers
│   ├── rules.py             PURE: break rule, self-report scheduler
│   ├── session.py           session folder + CSV/JSON writers
│   ├── engine.py            CapsuleEngine: owns locator/device/classifiers, state machine, pump()
│   ├── monitor.py           gates, smoothing, rules, recording (UI-free, testable with a fake engine)
│   ├── headless.py          whole flow without UI + session validator (tests / hardware checks)
│   ├── capsule_sdk/         vendored minimal Capsule wrapper (fixed) + CapsuleClient.dll
│   └── ui/                  customtkinter wizard: theme, widgets, steps, app window + self-test autopilot
└── tests/
    ├── test_metrics.py  test_quality_rules.py  test_session_engine_states.py  test_monitor.py
    └── test_sim_integration.py      (uses the DLL + simulated device; marked `sim` / `slow`)
```

**Vendored SDK — only what is needed** (from `eeg_headphones/Capsule_2.0.59/.../CapsuleClientPython`):
`Capsule, CapsulePointersImpl, Error, DeviceLocator, DeviceInfo, DeviceType, Device, EEGTimedData,
EEGArtifacts, PSDData, Resistances, PPGTimedData, Calibrator, Productivity, Emotions, Cardio` + `CapsuleClient.dll`.
Not copied: MEMS, PhysiologicalStates, examples, docs, other platforms, pyneurosdk2, BT drivers.
Imports are converted to package-relative; every edit is listed in `capsule_sdk/CHANGES.md`.

**Design rules**
- The engine never touches the UI; it emits events (`status`, `resistances`, `eeg`, `psd`, `emotions`,
  `productivity`, `indexes`, `calibrated`, `baseline`, `cardio`, `artifacts`, `error`). UI subscribes.
- All maths lives in pure modules → unit-testable without the DLL.
- Only pyneurosdk2-free Capsule connection (fixes the broken calibration in `SpeechEEG_Recorder`).

**Files written per session** (`sessions/<YYYY-mm-dd_HHMMSS>/`):
`session.json` (device, SDK version, settings, gates overridden, calibration & baseline values),
`productivity.csv`, `emotions.csv`, `indices.csv` (ours, 2 Hz), `resistances.csv`, `artifacts.csv`,
`events.csv` (markers, breaks, self-reports, warnings), optional `eeg.csv` (raw + processed).

---

## 5. Milestones

| M | Deliverable | Done when | Status (2026-09-30) |
|---|---|---|---|
| M0 | Project skeleton, vendored SDK with fixes, requirements | `import cogscore.capsule_sdk` loads the DLL | ✅ done, 6 wrapper fixes in `capsule_sdk/CHANGES.md` |
| M1 | Pure modules (`metrics`, `quality`, `rules`, `session`, `monitor`) + unit tests | `pytest -m "not sim"` green | ✅ 47 passed |
| M2 | `CapsuleEngine` + state machine + simulator integration tests | `pytest -m sim` green | ✅ incl. real 30 s calibration on the Noise simulator |
| M3 | Wizard UI steps 0–4 | Can reach the live screen on the simulator | ✅ screenshots reviewed; layout fixed for 125 % scaled laptop |
| M4 | Live screen, break rule, self-report, summary | `--selftest` run produces a complete session folder | ✅ `app.py --selftest` PASS |
| M5a | First real session (2026-09-30, serial 830817) | Connect → calibration → live works on hardware | ✅ iAPF 11.9 Hz, electrodes 180-236 kΩ, < 1.3 % artifacts; exposed the issues fixed in v2 (§9) |
| M4b | v2: hero metrics, stress episodes, raw-EEG bands, new break rule, minimal UI | 72 tests + self-test pass | ✅ 2026-09-30 |
| M5 | Hardware acceptance on real headphones (section 6.4), incl. v2 band chart | Checklist signed off | ⏳ re-run with v2 |
| M6 | (optional) PyInstaller one-file .exe | Runs on a clean Windows PC | not started |

Not yet automated: the real-time calibration countdown screen in the UI (the engine path is covered by
the slow headless test), and the §6.5 validity protocol screen.

---

## 6. Testing and checking

### 6.1 Unit tests (no hardware, no DLL) — `pytest -m "not sim"`
| Module | What is checked |
|---|---|
| `metrics` | Band power integration on synthetic spectra with known answers; each formula index (β/α, α/β, (α+θ)/β, θ/α, β/θ, α2/α1); zero / NaN / inf power → NaN, never a crash or 1e6; clamping; rolling median; baseline-relative % |
| `quality` | Resistance grading at 499/500/1000/1001 kΩ; gate needs 5 s continuous pass and resets on a bad reading; artifact-fraction window |
| `rules` | Break rule: fatigue must stay high 3 min and only after 10 min live; 50-min work block; silent during breaks and cooldown. Stress episodes: hysteresis start/end, interrupted candidates. KSS scheduler every 10 min |
| `spectral` | White noise → band share = bandwidth/44 Hz (< 2.5 % bias over 12 seeds); pure 10 Hz → alpha > 80 %; real DC offsets removed; 50 Hz notch < −30 dB and strong hum does not leak into γ; chunked filtering = one-pass; SDK-flagged and amplitude-spike windows rejected; flat signal rejected |
| `metrics` (v2) | Score mapping (50 = baseline, symmetric in log space), level words, baseline collector (median, one rare ratio cannot stall it) |
| `session` | Folder created; CSV headers exact; rows flushed; `session.json` round-trips; closing twice is safe |
| `engine` states | Illegal transitions rejected (e.g. baseline before calibration); retry path after calibration failure |

### 6.2 SDK contract / integration tests (DLL + simulated device) — `pytest -m sim`
1. Noise device is found within 8 s and connects.
2. Resistances arrive after start; PSD, Emotions and artifacts within 10 s.
3. Emotions come out with the **correct names** (attention … self-control) in 0–100.
4. `import_alpha` + `import_baselines` → Productivity metrics within 5 s, `fatigueGrowthRate` is a plain int.
5. Real 30 s quick calibration on Noise finishes with `failReason == 0` (slow test, ~70 s).
6. SinWave: absurd vendor values are sanitised to NaN/clamped by our pipeline.
7. Clean stop/disconnect; session folder contains all expected non-empty files.

### 6.3 End-to-end app check
- `python app.py --simulate noise` → click through all steps manually (real 30 s + baseline waits).
- `python app.py --simulate noise --fast` → imports calibration, reaches live screen in seconds (demo/dev).
- `python app.py --simulate noise --selftest` → drives the whole flow automatically for 60 s, then
  asserts output files exist and are non-empty; exit code 0 = pass.

### 6.4 Hardware acceptance checklist (real headphones, manual)
| # | Check | Pass criterion |
|---|---|---|
| H1 | Pairing per checklist, app finds device | Found within 15 s |
| H2 | Connect | Connected within 3 attempts |
| H3 | Resistances | All electrodes < 1000 kΩ within 2 min of adjusting |
| H4 | Blink ×5, jaw clench ×5 | Artifact flag appears within 2 s each time |
| H5 | Calibration | `failReason == 0`, iAPF between 7 and 13 Hz (your past: 10.2–11.6 Hz) |
| H6 | Baseline | Completes in < 2 min |
| H7 | PPG probe | Documents whether the unit is Lite (no HR) or Pro (HR appears) |
| H8 | 20-min session | No disconnects; scores update continuously; CSVs grow |
| H9 | Unplug dongle mid-session | App shows "disconnected", keeps data already recorded |

### 6.5 Signal validity checks (is it really brain signal?)
Built into a short "Checks" protocol in the app (M5):
1. **Eyes closed vs open (Berger effect):** 3 × (30 s closed / 30 s open). Relative alpha closed ≥ 1.3× open in ≥ 2 of 3 blocks. If this fails, the scores are not trustworthy.
2. **Mental arithmetic vs rest:** 2 min serial-7 subtraction vs 2 min rest. Expect concentration (β/α) and cognitive load higher during the task.
3. **Vendor vs our formula:** Spearman correlation between vendor `concentrationScore` and our β/α over a session ≥ 0.7. Confirms we understand the vendor scores.
4. **Artifact share:** < 20 % of the session artifacted, or the session is flagged as low quality.

### 6.6 Validation study (after M5)
- ≥ 10 participants × ≥ 2 sessions of 45–60 min focused work.
- Ground truth: KSS every 10 min (built in) + 3-min psychomotor vigilance task before and after.
- Metrics: within-person Spearman between accumulated fatigue / our (α+θ)/β and KSS; pre→post change in reaction time vs change in fatigue score.
- Success: median within-person ρ ≥ 0.4 and fatigue rising in ≥ 70 % of sessions where KSS rises.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Headphones are **Lite** (no PPG) | PPG panel hidden automatically; stress comes only from EEG indexes, labelled as such |
| Poor electrode contact (seen in the 2026-04-14 recording) | Hard gate at step 2, live artifact bar, scores greyed out when artifacted |
| Vendor formulas are black-box | Our own formula indices shown side by side and logged |
| Bluetooth conflicts | Checklist step 0 from the vendor manual; clear error text on scan failure |
| Wrapper uses module globals (one device per process) | One engine per app run; "Restart session" restarts the app process |
| License key file is plaintext in `E:\sit_secrets` | Not copied into this project; raw-data API does not need it |

---

## 8. How to run (target)

```bat
pip install -r requirements.txt
run.bat                     :: real headphones
run_simulator.bat           :: no hardware
python -m pytest            :: all tests (sim tests need the DLL, ~2 min)
python -m pytest -m "not sim"   :: fast unit tests only
```


---

## 9. Research and revalidation (v2, 2026-09-30)

### 9.1 What the first real session showed (`sessions/2026-09-30_130246`)
| Finding | Evidence | Change |
|---|---|---|
| Signal quality was good | electrodes 180-236 kΩ, artifacts 0.3 % / 1.3 %; channels **A1-C3, A2-C4** | — |
| Our formulas reproduce the vendor's | 5-s bins: vendor concentration vs β/α Spearman **ρ = 0.84**; vendor relaxation vs α/β **ρ = 0.85** (plan check §6.5-3 passes) | confidence in using the SDK spectrum for our own ratios |
| Vendor "stress" was stale | `indexes.csv` has **one** row in 3.5 min, emitted when the baseline finished | removed from screen; stress now computed continuously |
| Vendor accumulated fatigue is unusable for break timing | growth rate "High" whenever concentration > 1.7; baseline concentration was 2.2 → 6.0/10 after **3.3 min**, break prompt fired | new break rule on our fatigue ratio vs baseline + 50-min work block |
| Emotions are smooth, not noisy | lag-1 autocorrelation 0.99 at 2 Hz; swings happen over tens of seconds | 5 s median smoothing is enough |
| Productivity metrics arrive at ~25/s | 5 337 rows in 3.5 min | CSV throttled to 5/s |
| `EEGArtifacts.get_eeg_quality` misread | C header returns `float`, wrapper used `uint8` (constant "2") | wrapper fix #7 |

### 9.2 The SDK spectrum cannot show δ or γ
Measured on the Noise simulator (white noise in, processed/raw amplitude gain): 1-2 Hz **0.004**, 3-4 Hz 0.14,
4-7 Hz 0.71, 7-13 Hz 1.00, 13-30 Hz 0.96, 30-35 Hz 0.55, 40-45 Hz 0.14, > 45 Hz ≈ 0. In the real session δ was
0.7 % of SDK power. Therefore the band chart uses **raw** EEG: 0.5 Hz high-pass + 50 Hz notch (India mains), 4 s
Welch window every 0.5 s, rejection of SDK-flagged windows and of windows whose peak-to-peak exceeds 4× the running
median (relative, because raw dry-electrode amplitudes are hundreds of µV; a fixed µV threshold would reject
everything). Verified: the simulator's white raw EEG gives shares within 3 % of bandwidth/44 Hz; its SinWave
device (pure 10 Hz) gives alpha ≥ 95 %.

Real raw data from the April Capsule recordings showed strong 50 Hz hum (up to 290× the 40-45 Hz level) and
δ holding 34-56 % of raw power (movement/drift; EEG power always falls with frequency). That is why the default
band view is **change vs your own baseline**, not absolute share.

### 9.3 Interpretation limits (read before drawing conclusions)
- **Stress from EEG alone is weak evidence.** A meta-analysis of psychosocial-stress EEG studies found no
  consistent beta effect and mixed alpha effects (Vanhollebeke et al., 2022). High-β relative to α is the most
  used arousal marker in anxiety work, which is why it is used here, **relative to the person's own baseline**.
  Treat the stress score as "arousal vs your baseline", and validate it (arithmetic stress task vs rest, §6.5).
  Heart-rate variability (Pro headsets) is the stronger stress signal when available.
- **γ (30-45 Hz) and high β at these sites are muscle-sensitive.** Scalp recordings under paralysis show EEG
  above ~20 Hz is contaminated by EMG, increasingly with distance from the vertex (Whitham et al., 2007). The
  electrodes here are mastoid-to-central, near jaw and neck muscles: a γ jump usually means jaw clenching or
  movement. The artifact rejection removes gross bursts, not tonic muscle tension.
- **Fatigue**: θ and α rise with time on task (review evidence); the fatigue score tracks that ratio vs baseline
  over 60 s, and the break rule needs 3 min of elevation after the first 10 min. Short breaks alone do not
  prevent fatigue in long work days, so the prompt is advice, not a guarantee.
- **Attention / Cognitive load** are the vendor's normalised β/α and θ/α (their spreadsheet), which our own
  formulas correlate with (ρ 0.5-0.6 for the 0-100 versions, 0.84-0.85 for the raw vendor scores).

### 9.4 Sources
- Kane N. et al. (2017) A revised glossary of terms most commonly used by clinical electroencephalographers (IFCN) — band definitions.
- Vanhollebeke G. et al. (2022) The neural correlates of psychosocial stress: a systematic review and meta-analysis of spectral analysis EEG studies. *Neurobiology of Stress*.
- Whitham E.M. et al. (2007) Scalp electrical recording during paralysis: quantitative evidence that EEG frequencies above 20 Hz are contaminated by EMG. *Clin Neurophysiol*.
- Raufi B., Longo L. (2022) Alpha-to-theta and theta-to-alpha ratios as indexes of mental workload. *Front Neuroinform*.
- Schick L. et al. (2026) Rest Assured: detecting mental fatigue and recovery with EEG headphones. CHI '26.
- Neiry: `Capsule metrics_definitions.xlsx`, `Metrics API 2024.xlsx` (formulas, device support, update rates).


## 10. Second real session and v3 fixes (2026-09-30, `sessions/2026-09-30_135243`)

| Finding (4.4 min live, electrodes 180 → 90 kΩ, 0.5 % artifacts) | Change |
|---|---|
| Stress averaged 72 with one episode covering 3.5 of 4.4 min. High-β/α was 0.6 on the fixation cross and ~1.1 during screen work (alpha blocks with visual engagement), and 10-s medians of the ratio vary ±47 % (SD 0.56 in log₂), so the +34 % episode threshold was inside normal variation | Stress and fatigue reference = median of the **first 2 min of work** (breaks excluded, `WORK_REF_S`); stress smoothing 30 s; episode ≥ 80 for 30 s, ends < 65 for 30 s. Replayed on this session: 0 episodes. Time-on-task fatigue studies also compare with the start of the task, not with rest |
| After minute 2 stress still ~73: gamma +47 %, beta +33 %, alpha +7 % | Broadband high-frequency rise = muscle pattern; documented in the manual, not hidden |
| Band chart "vs baseline" showed α/β/γ all ≈ +75 %: δ held 74 % of rest power (fresh dry electrodes) and shrank as they settled, inflating every other band's *share* | Chart = % change of each band's **absolute** power vs rest (ERD/ERS convention). Same data: δ −54, θ −36, α −25, β −7, γ −15 %. "Share" view removed |
| A 1.5 s break restarted the 50-min timer | Breaks < 2 min (`MIN_BREAK_S`) are recorded but do not restart it |
| Break rule edge cases | fatigue during a break no longer counts; KSS waits until the break ends; stress episodes end when a break starts and are not detected during it |
| UI: 1-px strip of old axis labels under the band chart while a banner is shown | matplotlib renders int(4.52 in × 100) = 451 rows into a 452-row Tk photo; the photo is now blanked on every resize |

Tests: 80 (71 unit). New: work-reference timing and break pause, short burst ≠ episode, per-band change independent of
delta drift, short break does not reset timer, ignored prompt repeats, fatigue during break ignored, no KSS during break,
break ends episode. Manual: `docs/manual.html`, built by `docs/build_manual.py` from this session.
