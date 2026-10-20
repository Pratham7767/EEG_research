"""
Export Manager — saves session data in research-ready formats.

Output files per session:
  {timestamp}_eeg.csv            — raw EEG (time_s, A1, C3, C4, A2)
  {timestamp}_eeg_filt.csv       — filtered EEG (4-30 Hz Butterworth bandpass)
  {timestamp}_eeg.bdf            — raw EEG in BioSemi Data Format
  {timestamp}_eeg_filt.bdf       — filtered EEG in BDF
  {timestamp}_audio.wav          — speech recording (16 kHz, mono, int16)
  eeg_raw.npy                    — raw EEG numpy array
  eeg_filtered.npy               — filtered EEG numpy array
  eeg_timestamps.npy             — per-sample ms timestamps
  speech_envelope.npy            — Hilbert envelope at EEG rate
  trials.csv                     — trial event markers
  metadata.json                  — session metadata
  calibration.json               — calibration data
  combined_aligned.csv           — time-aligned EEG + speech envelope + trial labels
  session.h5                     — HDF5 (continuous + epochs)
"""
import os
import json
import csv
import time
import struct
import wave
import logging
import datetime
import numpy as np
from scipy.signal import butter, lfilter, hilbert, resample_poly
from math import gcd

logger = logging.getLogger(__name__)

try:
    import h5py
    HAS_H5PY = True
except ImportError:
    HAS_H5PY = False
    logger.warning("h5py not installed — HDF5 export disabled. Run: pip install h5py")

try:
    import pyedflib
    HAS_PYEDFLIB = True
except ImportError:
    HAS_PYEDFLIB = False
    logger.warning("pyedflib not installed — BDF export disabled. Run: pip install pyedflib")

CHANNEL_NAMES = ["A1", "C3", "C4", "A2"]


def bandpass_filter(data, lowcut=4, highcut=30, fs=250, order=4):
    """Apply Butterworth bandpass filter (4-30 Hz by default)."""
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    b, a = butter(order, [low, high], btype='band')
    return lfilter(b, a, data, axis=0)


def compute_speech_envelope(audio_int16, audio_sr, target_sr):
    """Hilbert envelope of audio resampled to EEG sample rate."""
    if len(audio_int16) == 0:
        return np.array([], dtype=np.float64)
    audio_float = audio_int16.astype(np.float64) / 32768.0
    analytic = hilbert(audio_float)
    envelope = np.abs(analytic)
    g = gcd(int(target_sr), int(audio_sr))
    up = int(target_sr) // g
    down = int(audio_sr) // g
    return resample_poly(envelope, up, down)


def _align_to_length(array, target_len):
    if len(array) >= target_len:
        return array[:target_len]
    return np.pad(array, (0, target_len - len(array)))


class ExportManager:
    """Exports recording session data to structured files."""

    def __init__(self, base_dir="data"):
        self._base_dir = base_dir

    def export_session(self, recording_data, trials, calibration_manager,
                       session_name=None):
        """
        Export a complete recording session.

        Returns: path to the session directory
        """
        if session_name is None:
            session_name = time.strftime("session_%Y-%m-%d_%H%M%S")

        session_dir = os.path.join(self._base_dir, session_name)
        os.makedirs(session_dir, exist_ok=True)

        eeg_raw = recording_data.get("eeg_raw")
        eeg_ts  = recording_data.get("eeg_timestamps")
        audio   = recording_data.get("audio")      # int16 array
        audio_sr = recording_data.get("audio_sample_rate", 16000)
        eeg_sr  = recording_data.get("eeg_sample_rate", 250)
        channel_names = recording_data.get("channel_names", CHANNEL_NAMES)
        n_eeg = len(eeg_raw) if eeg_raw is not None and len(eeg_raw) > 0 else 0
        n_ch  = eeg_raw.shape[1] if n_eeg > 0 and len(eeg_raw.shape) > 1 else 0

        now_ts = datetime.datetime.now()
        ts_str = now_ts.strftime("%Y-%m-%d_%H-%M-%S")

        # ── 1. Raw EEG CSV (brain_bit format) ──
        if n_eeg > 0 and n_ch > 0:
            csv_path = os.path.join(session_dir, f"{ts_str}_eeg.csv")
            time_col = np.arange(n_eeg)[:, None] / eeg_sr
            csv_data = np.concatenate([time_col, eeg_raw], axis=1)
            header = ",".join(["time (s)"] + list(channel_names))
            fmt = "%.3f" + ",%.16f" * n_ch
            np.savetxt(csv_path, csv_data, header=header,
                       delimiter=",", comments="", fmt=fmt)
            logger.info(f"Saved {ts_str}_eeg.csv: {n_eeg} samples x {n_ch} channels")

        # ── 2. Filtered EEG CSV (4-30 Hz Butterworth) ──
        eeg_filtered = None
        if n_eeg > 0 and n_ch > 0:
            try:
                eeg_filtered = bandpass_filter(eeg_raw, lowcut=4, highcut=30,
                                               fs=eeg_sr, order=4)
                csv_filt_path = os.path.join(session_dir, f"{ts_str}_eeg_filt.csv")
                time_col = np.arange(n_eeg)[:, None] / eeg_sr
                csv_filt_data = np.concatenate([time_col, eeg_filtered], axis=1)
                header = ",".join(["time (s)"] + list(channel_names))
                fmt = "%.3f" + ",%.16f" * n_ch
                np.savetxt(csv_filt_path, csv_filt_data, header=header,
                           delimiter=",", comments="", fmt=fmt)
                logger.info(f"Saved {ts_str}_eeg_filt.csv: {n_eeg} samples (4-30 Hz filtered)")
            except Exception as e:
                logger.error(f"Filtered CSV export failed: {e}")

        # ── 3. Raw EEG BDF ──
        if HAS_PYEDFLIB and n_eeg > 0 and n_ch > 0:
            try:
                self._export_bdf(session_dir, f"{ts_str}_eeg.bdf",
                                 eeg_raw, channel_names, eeg_sr, now_ts)
            except Exception as e:
                logger.error(f"Raw BDF export failed: {e}")

        # ── 4. Filtered EEG BDF ──
        if HAS_PYEDFLIB and eeg_filtered is not None:
            try:
                self._export_bdf(session_dir, f"{ts_str}_eeg_filt.bdf",
                                 eeg_filtered, channel_names, eeg_sr, now_ts,
                                 prefilter="4-30 Hz Butterworth order 4")
            except Exception as e:
                logger.error(f"Filtered BDF export failed: {e}")

        # ── 5. Audio WAV (brain_bit format: 16 kHz mono int16) ──
        if audio is not None and len(audio) > 0:
            wav_path = os.path.join(session_dir, f"{ts_str}_audio.wav")
            try:
                with wave.open(wav_path, "w") as wf:
                    wf.setparams((1, 2, audio_sr, len(audio),
                                  "NONE", "NONE"))
                    wf.writeframes(
                        struct.pack("h" * len(audio), *audio.tolist()))
                logger.info(f"Saved {ts_str}_audio.wav: {len(audio)} samples @ {audio_sr} Hz")
            except Exception as e:
                logger.error(f"WAV export failed: {e}")

        # ── 6. NPY files ──
        if n_eeg > 0:
            np.save(os.path.join(session_dir, "eeg_raw.npy"), eeg_raw)
        if eeg_filtered is not None:
            np.save(os.path.join(session_dir, "eeg_filtered.npy"), eeg_filtered)
        if eeg_ts is not None and len(eeg_ts) > 0:
            np.save(os.path.join(session_dir, "eeg_timestamps.npy"), eeg_ts)

        # ── 7. Speech envelope at EEG rate ──
        speech_envelope = None
        if audio is not None and len(audio) > 0 and n_eeg > 0:
            try:
                speech_envelope = compute_speech_envelope(audio, audio_sr, eeg_sr)
                speech_envelope = _align_to_length(speech_envelope, n_eeg)
                np.save(os.path.join(session_dir, "speech_envelope.npy"),
                        speech_envelope)
                logger.info(f"Saved speech_envelope.npy @ {eeg_sr} Hz")
            except Exception as e:
                logger.error(f"Speech envelope failed: {e}")

        # ── 8. Trials CSV ──
        if trials:
            self._export_trials_csv(session_dir, trials)

        # ── 9. Metadata JSON ──
        word_list = list(dict.fromkeys(
            t["word"] for t in trials)) if trials else []

        metadata = {
            "session_name": session_name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "created_at_unix": time.time(),
            "t0_unix": recording_data.get("t0_unix"),
            "duration_seconds": recording_data.get("duration_seconds", 0),
            "device": {
                "type": "Headphones2 (pyneurosdk2)",
                "channel_names": list(channel_names),
                "channel_mapping": "Ch1=A1, Ch2=C3, Ch3=C4, Ch4=A2",
                "eeg_sample_rate": eeg_sr,
            },
            "audio": {
                "sample_rate": audio_sr,
                "channels": 1,
                "format": "int16",
                "recorder": "PvRecorder",
            },
            "recording": {
                "total_eeg_samples": n_eeg,
                "total_audio_samples": len(audio) if audio is not None else 0,
                "total_trials": len(trials) if trials else 0,
                "skipped_trials": sum(1 for t in trials if t.get("skipped")) if trials else 0,
                "word_list": word_list,
            },
            "filtering": {
                "method": "Butterworth bandpass",
                "lowcut_hz": 4,
                "highcut_hz": 30,
                "order": 4,
            },
            "export_files": {
                "raw_csv": f"{ts_str}_eeg.csv",
                "filtered_csv": f"{ts_str}_eeg_filt.csv",
                "raw_bdf": f"{ts_str}_eeg.bdf",
                "filtered_bdf": f"{ts_str}_eeg_filt.bdf",
                "audio_wav": f"{ts_str}_audio.wav",
                "npy": ["eeg_raw.npy", "eeg_filtered.npy",
                        "eeg_timestamps.npy", "speech_envelope.npy"],
                "h5": "session.h5",
                "csv": ["trials.csv", "combined_aligned.csv"],
            },
            "sync": {
                "method": "shared_perf_counter_ns",
                "t0_perf_ns": recording_data.get("t0_perf_ns"),
            },
        }

        if calibration_manager:
            metadata["calibration"] = {
                "iapf": calibration_manager.iapf_data,
                "productivity_baselines": calibration_manager.productivity_baselines,
                "physio_baselines": calibration_manager.physio_baselines,
            }

        with open(os.path.join(session_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2, default=str)
        logger.info("Saved metadata.json")

        # ── 10. Calibration JSON ──
        if calibration_manager:
            try:
                calibration_manager.save_calibration(
                    os.path.join(session_dir, "calibration.json"))
            except Exception:
                pass

        # ── 11. Combined aligned CSV ──
        if n_eeg > 0 and n_ch > 0:
            try:
                self._export_combined_csv(
                    session_dir, eeg_raw, eeg_filtered, eeg_ts,
                    speech_envelope, channel_names, trials, eeg_sr)
            except Exception as e:
                logger.error(f"Combined CSV failed: {e}")

        # ── 12. HDF5 session file ──
        if HAS_H5PY and n_eeg > 0:
            try:
                self._export_hdf5(
                    session_dir, recording_data, eeg_raw, eeg_filtered,
                    eeg_ts, audio, speech_envelope, trials,
                    channel_names, metadata)
            except Exception as e:
                logger.error(f"HDF5 export failed: {e}")

        logger.info(f"Session exported to: {session_dir}")
        return session_dir

    # Frame length constant for WAV header
    AUDIO_FRAME_LENGTH = 512

    # ── BDF Export ─────────────────────────────────────────────────

    def _export_bdf(self, session_dir, filename, eeg_data, channel_names,
                    fs, start_datetime, prefilter=""):
        """Export EEG data in BioSemi Data Format (BDF)."""
        path = os.path.join(session_dir, filename)
        n_ch = len(channel_names)
        dmin, dmax = -8388608, 8388607

        f_eeg = pyedflib.EdfWriter(path, n_channels=n_ch,
                                    file_type=pyedflib.FILETYPE_BDF)
        channel_info = []
        for i, label in enumerate(channel_names):
            ch_dict = {
                "label": label,
                "dimension": "uV",
                "sample_frequency": fs,
                "physical_min": float(eeg_data[:, i].min()),
                "physical_max": float(eeg_data[:, i].max()),
                "digital_min": dmin,
                "digital_max": dmax,
                "transducer": "",
                "prefilter": prefilter,
            }
            channel_info.append(ch_dict)

        f_eeg.setSignalHeaders(channel_info)
        f_eeg.setStartdatetime(start_datetime)
        f_eeg.writeSamples(eeg_data.T)
        f_eeg.close()
        logger.info(f"Saved {filename}")

    # ── Trials CSV ─────────────────────────────────────────────────

    def _export_trials_csv(self, session_dir, trials):
        csv_path = os.path.join(session_dir, "trials.csv")
        fieldnames = [
            "trial_id", "word", "prompt_time_ms",
            "speech_start_ms", "speech_end_ms",
            "eeg_start_idx", "eeg_end_idx",
            "audio_start_sample", "audio_end_sample", "skipped"
        ]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trials:
                writer.writerow(t)
        logger.info(f"Saved trials.csv: {len(trials)} trials")

    # ── Combined aligned CSV ───────────────────────────────────────

    def _export_combined_csv(self, session_dir, eeg_raw, eeg_filtered, eeg_ts,
                              speech_envelope, channel_names, trials, eeg_sr):
        csv_path = os.path.join(session_dir, "combined_aligned.csv")
        n_samples = len(eeg_raw)
        n_ch = eeg_raw.shape[1] if len(eeg_raw.shape) > 1 else 0

        if n_samples == 0 or n_ch == 0:
            logger.warning("No valid EEG data for combined CSV; skipping")
            return

        # Build trial lookup
        trial_lookup = np.zeros(n_samples, dtype=np.int32)
        word_lookup = [""] * n_samples
        phase_lookup = ["rest"] * n_samples

        if trials:
            for t in trials:
                if t.get("skipped"):
                    continue
                start = int(t.get("eeg_start_idx") or 0)
                end = int(t.get("eeg_end_idx") or 0)
                speech_s = int(t.get("speech_start_ms") or 0)
                speech_e = int(t.get("speech_end_ms") or 0)
                tid = int(t.get("trial_id") or 0)
                word = str(t.get("word") or "")

                for idx in range(max(0, start), min(n_samples, end)):
                    trial_lookup[idx] = tid
                    word_lookup[idx] = word
                    if eeg_ts is not None and idx < len(eeg_ts):
                        ts = eeg_ts[idx]
                        if speech_s and speech_e and speech_s <= ts <= speech_e:
                            phase_lookup[idx] = "speech"
                        elif speech_s and ts < speech_s:
                            phase_lookup[idx] = "pre"
                        elif speech_e and ts > speech_e:
                            phase_lookup[idx] = "post"
                        else:
                            phase_lookup[idx] = "trial"

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            header = ["timestamp_ms", "time_s"]
            for ch in channel_names:
                header.append(f"{ch}_raw")
            if eeg_filtered is not None:
                for ch in channel_names:
                    header.append(f"{ch}_filt")
            header.extend(["speech_envelope", "trial_id", "word", "phase"])
            writer.writerow(header)

            for i in range(n_samples):
                row = []
                ts_ms = int(eeg_ts[i]) if eeg_ts is not None and i < len(eeg_ts) else 0
                row.append(ts_ms)
                row.append(f"{ts_ms / 1000.0:.4f}")
                for ch in range(n_ch):
                    row.append(f"{eeg_raw[i, ch]:.6f}")
                if eeg_filtered is not None and i < len(eeg_filtered):
                    for ch in range(n_ch):
                        row.append(f"{eeg_filtered[i, ch]:.6f}")
                if speech_envelope is not None and i < len(speech_envelope):
                    row.append(f"{speech_envelope[i]:.6f}")
                else:
                    row.append("")
                row.append(trial_lookup[i] if trial_lookup[i] > 0 else "")
                row.append(word_lookup[i])
                row.append(phase_lookup[i])
                writer.writerow(row)

        logger.info(f"Saved combined_aligned.csv: {n_samples} rows")

    # ── HDF5 Export ────────────────────────────────────────────────

    def _export_hdf5(self, session_dir, recording_data, eeg_raw, eeg_filtered,
                      eeg_ts, audio, speech_envelope, trials,
                      channel_names, metadata):
        h5_path = os.path.join(session_dir, "session.h5")

        with h5py.File(h5_path, "w") as f:
            # /continuous
            cont = f.create_group("continuous")
            if eeg_raw is not None and len(eeg_raw) > 0:
                ds = cont.create_dataset("eeg_raw", data=eeg_raw,
                                          compression="gzip", compression_opts=4)
                ds.attrs["channels"] = list(channel_names)
            if eeg_filtered is not None and len(eeg_filtered) > 0:
                ds = cont.create_dataset("eeg_filtered", data=eeg_filtered,
                                          compression="gzip", compression_opts=4)
                ds.attrs["filter"] = "4-30 Hz Butterworth order 4"
            if eeg_ts is not None and len(eeg_ts) > 0:
                cont.create_dataset("timestamps_ms", data=eeg_ts,
                                     compression="gzip")
            if speech_envelope is not None and len(speech_envelope) > 0:
                cont.create_dataset("speech_envelope", data=speech_envelope,
                                     compression="gzip")
            if audio is not None and len(audio) > 0:
                cont.create_dataset("audio_raw", data=audio,
                                     compression="gzip", compression_opts=4)

            # /epochs
            if trials:
                epochs = f.create_group("epochs")
                for t in trials:
                    tid = int(t.get("trial_id") or 0)
                    grp = epochs.create_group(f"trial_{tid:03d}")
                    start_idx = int(t.get("eeg_start_idx") or 0)
                    end_idx = int(t.get("eeg_end_idx") or 0)
                    n_eeg = len(eeg_raw) if eeg_raw is not None else 0
                    start_idx = max(0, min(start_idx, n_eeg))
                    end_idx = max(start_idx, min(end_idx, n_eeg))
                    grp.attrs["word"] = str(t.get("word", ""))
                    grp.attrs["trial_id"] = tid
                    grp.attrs["skipped"] = bool(t.get("skipped", False))
                    if end_idx > start_idx and eeg_raw is not None:
                        grp.create_dataset("eeg_raw",
                                            data=eeg_raw[start_idx:end_idx])
                        if eeg_filtered is not None:
                            grp.create_dataset("eeg_filtered",
                                data=eeg_filtered[start_idx:end_idx])

            # /metadata
            meta = f.create_group("metadata")
            meta.attrs["session_name"] = metadata.get("session_name", "")
            meta.attrs["eeg_sample_rate"] = recording_data.get("eeg_sample_rate", 250)
            meta.attrs["audio_sample_rate"] = recording_data.get("audio_sample_rate", 16000)
            if channel_names:
                meta.create_dataset("channel_names",
                    data=np.array(channel_names, dtype="S10"))

        logger.info(f"Saved session.h5: {os.path.getsize(h5_path) / 1024:.1f} KB")
