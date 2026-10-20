# Speech + EEG Recorder

A desktop application for **simultaneous speech and EEG recording** using pyneurosdk2 (NeuroSDK) for Capsule Headphones2 (4 EEG channels: **A1, C3, C4, A2** @ 250 Hz) and PvRecorder for microphone audio (16 kHz mono). Built for BCI speech-decoding research.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Step-by-Step Workflow](#step-by-step-workflow)
   - [Tab 1 : Connect](#tab-1--connect)
   - [Tab 2 : Resistance](#tab-2--resistance)
   - [Tab 3 : Calibrate](#tab-3--calibrate)
   - [Tab 4 : Record + Monitor](#tab-4--record--monitor)
5. [Live EEG Features](#live-eeg-features)
6. [Export Formats](#export-formats)
7. [Project Structure](#project-structure)
8. [Troubleshooting](#troubleshooting)

---

## Requirements

| Component | Version |
|-----------|---------|
| Python | 3.9+ (tested with 3.11.9) |
| pyneurosdk2 | 1.0.15 (NeuroSDK for device control) |
| Capsule API | v2.0.40 (optional, for IAPF calibration) |
| Capsule Headphones2 | Any model supported by NeuroSDK |
| OS | Windows 10/11 |
| Microphone | Default system input (PvRecorder) |

### EEG Channel Mapping

| SDK Channel | Electrode | Location |
|------------|-----------|----------|
| Ch1 | A1 | Left mastoid |
| Ch2 | C3 | Left central |
| Ch3 | C4 | Right central |
| Ch4 | A2 | Right mastoid |

### Python Dependencies

```
customtkinter >= 5.2.0    # Dark-themed modern GUI
numpy         >= 1.21.0   # Array operations, FFT
scipy         >= 1.7.0    # Signal processing (Butterworth, Hilbert, resampling)
matplotlib    >= 3.5.0    # Live EEG / PSD graphs
h5py          >= 3.7.0    # HDF5 export
pvrecorder    >= 1.2.0    # Picovoice audio recorder (16 kHz mono)
pyedflib      >= 0.1.30   # BDF/EDF file writing
```

---

## Installation

1. **Clone or copy** the `SpeechEEG_Recorder` folder to your machine.

2. **Install Python dependencies:**

   ```bash
   cd SpeechEEG_Recorder
   pip install -r requirements.txt
   ```

3. **Verify SDK locations.** The app expects:

   **pyneurosdk2** (NeuroSDK for device control):
   ```
   D:\sit_secrets\brain_bit\pyneurosdk2-1.0.15\
   ```

   **Capsule API v2.0.40** (optional, for IAPF calibration):
   ```
   D:\sit_secrets\brain_bit\Capsule_API\Capsule v2.0.40\CapsuleAPI\Windows\Capsule Python\CapsuleClientPython\
   ```

   If your SDKs are in a different location, edit the paths in `core/device_manager.py` (lines 12-20).

4. **Run the application:**

   ```bash
   python app.py
   ```

---

## Quick Start

The app follows a linear 4-tab workflow. Complete each tab before moving to the next:

```
Connect  -->  Resistance  -->  Calibrate  -->  Record + Monitor
```

1. Scan and connect your Capsule headphones.
2. Check electrode impedances (aim for < 20 kOhm on all channels).
3. Run IAPF calibration (30 seconds, eyes closed).
4. Set up your word list, hit START, and speak each prompted word.
5. Data is auto-exported when you stop recording.

---

## Step-by-Step Workflow

### Tab 1 : Connect

This tab discovers and connects to your Capsule headphones.

1. **Set search time** (default: 10 seconds) and click **Scan for Devices**.
2. The device list will populate with discovered headphones showing Name, Serial, and Type.
3. **Select a device** from the list and click **Connect**.
4. The app auto-retries up to 3 times if the first connection attempt fails (2s, 5s, 10s delays).
5. Once connected, the header bar turns green and shows battery percentage.
6. EEG streaming starts automatically after connection (bipolar mode).

> **Tip:** Make sure your Capsule headphones are charged and in pairing mode before scanning.

---

### Tab 2 : Resistance

This tab monitors electrode impedance in real time to ensure good signal quality.

| Quality | Impedance | Indicator |
|---------|-----------|-----------|
| Good | < 20 kOhm | Green |
| Acceptable | 20 - 40 kOhm | Yellow |
| Bad | > 40 kOhm | Red |

**What to check:**

- All 4 channels (C3, C4, A1, A2) should show **green** or at least **yellow**.
- Trend arrows show if impedance is improving, stable, or worsening.
- The "Best" column shows the lowest impedance achieved per channel.

**If impedance is high:**

- Adjust electrode placement and ensure good contact with the scalp.
- Apply saline solution to the electrode pads.
- Wait 30-60 seconds for electrodes to settle.
- Minimize head movement during monitoring.

Click **Proceed to Calibration** (or **Proceed Anyway** to skip) when ready.

---

### Tab 3 : Calibrate

Calibration optimizes the SDK's signal processing for your individual brain signals. **Calibration is recommended before recording** for accurate filtered EEG and PSD data.

#### IAPF Calibration (Recommended)

- Click **Quick IAPF (30s)**.
- **Close your eyes** and sit relaxed for 30 seconds.
- The SDK measures your Individual Alpha Peak Frequency.
- Results show: IAF frequency, peak power, bandwidth, and frequency band.

#### Productivity Baseline (Optional)

- Measures baseline levels for gravity, productivity, fatigue, relaxation, and concentration.
- Sit still with eyes closed during the calibration.

#### Physiological States Baseline (Optional)

- Measures alpha/beta/concentration baselines.
- Similar procedure: sit still, eyes closed.

#### Save / Import Calibration

- Click **Save All Calibration Data** to export to a `.json` file.
- Use **Import Saved Calibration** to load a previous calibration (avoids re-doing IAPF each session).

> **Note:** The Record tab shows a red banner if IAPF calibration hasn't been done. You can still record without it, but filtered EEG signals and PSD will be less accurate.

---

### Tab 4 : Record + Monitor

This is the main tab where everything happens: word prompting, live EEG visualization, audio capture, PSD display, artifact monitoring, and data export.

#### Setting Up a Recording Session

1. **Word List** -- Edit the words that will be prompted during recording:
   - Type a word and click **Add**, or use the **Quick add** buttons.
   - Click **Remove** to delete a word, or **Clear** to remove all.
   - Default words: right, left, up, down, yes, no.

2. **Trial Settings:**
   - **Reps per word**: How many times each word is repeated (default: 5).
   - **Rest between (s)**: Seconds of rest between trials (default: 3).
   - Order is always **sequential** (no randomization).

3. **Microphone**: Select your audio input device from the dropdown. Click **Refresh** if it doesn't appear.

#### Recording

1. Click **START RECORDING** (green button).
   - If IAPF calibration hasn't been done, a warning dialog appears.
   - Recording begins: audio capture, EEG capture, and trial prompting all start simultaneously.

2. **During recording**, you will see:
   - **Word prompt** -- The current word to speak appears in large blue text.
   - **Trial counter** -- Shows "Trial: X/Total".
   - **Timer** -- Running clock (HH:MM:SS).
   - **EEG sample count** -- Total EEG samples collected.
   - **Rest period countdown** -- Shows remaining seconds between trials.
   - **SPEAKING indicator** -- Turns green when speech is detected.

3. Click **PAUSE** to pause recording (and **RESUME** to continue).

4. Click **STOP** (red button) to end the session.
   - Data is automatically exported to `data/session_YYYY-MM-DD_HHMMSS/`.
   - A summary dialog shows EEG sample count, audio samples, and trial count.

5. Click **EXPORT H5/CSV** (purple button) after stopping to re-export the session to a custom folder.

#### Speech Detection

The app detects speech onset/offset automatically using audio RMS level thresholds:

- **Onset threshold**: 0.05 RMS (speech starts)
- **Offset threshold**: 0.02 RMS (speech ends, with 300ms hold)
- Pre-trial window: 500ms of EEG captured before speech onset
- Post-trial window: 1000ms of EEG captured after speech offset
- If no speech is detected within 5 seconds, the trial is marked as "skipped".

---

## Live EEG Features

All live monitoring features are built into the **Record + Monitor** tab.

### EEG Waveforms

- **4-channel real-time display** at ~12 FPS, 5-second rolling window.
- **Signal toggle** (Raw / Filtered):
  - **Raw**: Unprocessed EEG straight from the device.
  - **Filtered**: Note — NeuroSDK does not provide real-time filtered signals. Filtering (4-30 Hz Butterworth bandpass) is applied post-recording during export. The live "Filtered" view shows raw data in real-time.
- **Mode toggle** (Monopolar / Bipolar):
  - **Monopolar**: Shows each channel independently (C3, C4, A1, A2).
  - **Bipolar**: Shows computed difference derivations (C3-C4, C3-A1, C4-A2, A1-A2).
- All 4 combinations work: Raw Monopolar, Filtered Monopolar, Raw Bipolar, Filtered Bipolar.
- Auto-scaling Y-axis adjusts to the signal amplitude.

### PSD Band Powers (Bar Graph)

- Grouped bar chart showing power in 4 frequency bands per channel:

  | Band | Frequency Range |
  |------|----------------|
  | Delta | 0.5 - 4 Hz |
  | Theta | 4 - 8 Hz |
  | Alpha | 8 - 13 Hz |
  | Beta | 15 - 30 Hz |

- Log scale for better visibility.
- Updates every 500ms.
- Shows "IAPF Calibrated" label when individual alpha calibration is active.

### Artifact Status

- Per-channel indicators show **Clean** (green) or **Artifact!** (red).
- Quality rating per channel: Good / OK / Fair / Poor / Bad.
- Use this to verify your electrode contact during recording.

### Audio Spectrum Visualizer

- 40 rainbow-colored frequency bars showing real-time microphone input.
- Logarithmic frequency spacing (more detail in speech-relevant bass range).
- Smoothed transitions for visual clarity.
- dB level readout below the bars.

### Pop-Out Window

- Click **Pop-Out Graphs** to open a separate window.
- Useful for multi-monitor setups where you want the graphs on a second screen.

---

## Export Formats

Every recording session is saved to `data/session_YYYY-MM-DD_HHMMSS/` with the following files:

### Individual Files

| File | Format | Contents |
|------|--------|----------|
| `{timestamp}_eeg.csv` | CSV | Raw EEG: time_s, A1, C3, C4, A2 |
| `{timestamp}_eeg_filt.csv` | CSV | Filtered EEG (4-30 Hz Butterworth bandpass) |
| `{timestamp}_eeg.bdf` | BDF | Raw EEG in BioSemi Data Format |
| `{timestamp}_eeg_filt.bdf` | BDF | Filtered EEG in BDF |
| `{timestamp}_audio.wav` | WAV | Speech recording (16 kHz, mono, int16) |
| `eeg_raw.npy` | NumPy | Raw EEG array (n_samples x 4), float64 |
| `eeg_filtered.npy` | NumPy | Filtered EEG array (n_samples x 4), float64 |
| `eeg_timestamps.npy` | NumPy | Per-sample timestamps in ms (int64) |
| `speech_envelope.npy` | NumPy | Speech amplitude envelope at EEG rate (250 Hz) |
| `trials.csv` | CSV | Trial event markers with timing and EEG/audio indices |
| `metadata.json` | JSON | Session metadata, sync info, filtering params |
| `calibration.json` | JSON | Calibration parameters (IAPF, baselines) |

### Combined Aligned CSV (`combined_aligned.csv`)

One row per EEG sample (250 rows/second) with all modalities aligned:

```
timestamp_ms, time_s, C3_raw, C4_raw, A1_raw, A2_raw,
C3_filt, C4_filt, A1_filt, A2_filt,
speech_envelope, trial_id, word, phase
```

- **phase** values: `rest`, `pre` (before speech), `speech`, `post` (after speech), `trial`
- Speech envelope is computed via Hilbert transform and resampled to EEG rate.

### HDF5 Session File (`session.h5`)

Hierarchical structure optimized for ML pipelines:

```
/continuous/
    eeg_raw          (n_samples x 4) float32, gzip compressed
    eeg_filtered     (n_samples x 4) float32, gzip compressed
    timestamps_ms    (n_samples,) int64
    speech_envelope  (n_samples,) float64 @ EEG rate
    audio_raw        (n_audio_samples,) float32 @ original rate

/epochs/
    trial_001/
        eeg_raw, eeg_filtered, timestamps_ms, speech_envelope, audio_raw
        Attributes: word, trial_id, speech_start_ms, speech_end_ms, skipped
    trial_002/
        ...

/metadata/
    channel_names, eeg_sample_rate, audio_sample_rate, t0_unix, word_list
    calibration/ (IAPF parameters if available)
```

### Research Rationale

The export strategy follows established practices in speech-EEG decoding:

- **Speech envelope via Hilbert transform** -- standard in BrainMagick (Defossez et al., 2023), VLAAI, and Broderick et al. (2018).
- **Continuous + event markers** -- canonical format following BIDS-style conventions.
- **HDF5 as single-file ML cache** -- avoids scattered files, supports compression, stores both continuous and epoched data.
- **Time synchronization** via shared `perf_counter_ns` reference ensures EEG and audio timestamps are aligned to sub-millisecond precision.

---

## Project Structure

```
SpeechEEG_Recorder/
|-- app.py                          # Entry point
|-- requirements.txt                # Python dependencies
|
|-- core/
|   |-- device_manager.py           # Capsule SDK device lifecycle + EventBus
|   |-- calibration_manager.py      # IAPF / Productivity / Physio calibration
|   |-- recording_engine.py         # Parallel EEG + audio capture with time sync
|   |-- trial_manager.py            # Word prompting, speech detection, trial log
|   |-- export_manager.py           # NPY, WAV, CSV, H5 export pipeline
|
|-- ui/
|   |-- main_window.py              # Tabbed GUI shell (4 tabs)
|   |-- connection_tab.py           # Device scan + connect
|   |-- resistance_tab.py           # Electrode impedance monitoring
|   |-- calibration_tab.py          # IAPF + baseline calibration UI
|   |-- recording_tab.py            # Unified recording + live EEG monitor
|   |-- audio_visualizer.py         # Rainbow spectrum bar widget
|
|-- data/                           # Exported sessions (auto-created)
|-- logs/                           # Application and SDK logs
|-- config/                         # Configuration files
```

### Architecture Highlights

- **EventBus** (`device_manager.py`): Pub/sub system allowing multiple UI components to listen to the same device events without overwriting callbacks. Each subscriber gets an unsubscribe function for clean teardown.

- **Time Synchronization**: Both EEG and audio streams reference a shared `time.perf_counter_ns()` origin (`t0`). This ensures sub-millisecond alignment when combining modalities.

- **Dual EEG Buffers**: Raw and filtered EEG are captured simultaneously using `get_raw_value()` and `get_processed_value()` from the SDK, enabling toggle between signal types without re-recording.

---

## Troubleshooting

### "Failed to initialize NeuroSDK"

- Verify `pyneurosdk2-1.0.15` folder exists at `D:\sit_secrets\brain_bit\`.
- Make sure the native library (`neurosdk-shared`) is accessible.
- Check that no other application is using the headphones simultaneously.

### Device not found during scan

- Ensure headphones are charged and in pairing mode.
- Try increasing the search time (default: 10s).
- Restart the headphones and try again.

### High electrode impedance

- Reposition the headphones for better electrode-skin contact.
- Apply conductive gel or saline to electrode pads.
- Clean the electrodes if residue has built up.
- Wait 1-2 minutes for impedance to settle.

### PSD chart shows no data

- PSD requires the device to be streaming (connected and active).
- IAPF calibration improves PSD accuracy but is not strictly required.
- If PSD still doesn't update after 10+ seconds, the SDK may not be emitting PSD events -- check `logs/app.log` for errors.

### Audio not recording

- Verify the correct microphone is selected in the dropdown.
- Click **Refresh** to re-scan audio devices.
- Check that `pvrecorder` is installed: `pip install pvrecorder`
- On Windows, ensure the BrainBit/Capsule headphones are set as default microphone input under **System > Sound > Input**.
- Audio records at 16 kHz mono (matching brain_bit reference implementation).

### Export errors

- Ensure `h5py` is installed for HDF5 export: `pip install h5py`
- Check that the `data/` directory is writable.
- If a specific export format fails, others will still be saved -- check `logs/app.log` for details.

### Application crashes on close

- This can happen if event callbacks fire after UI destruction. The app includes cleanup handlers, but if you see this, force-close is safe -- all data is saved to disk during `_stop_recording()`.

---

## License

Internal research tool. Not for distribution.
