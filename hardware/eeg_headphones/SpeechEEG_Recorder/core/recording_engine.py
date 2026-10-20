"""
Recording Engine — parallel EEG + audio capture with shared timestamp reference.

EEG: via pyneurosdk2 signalDataReceived callback (Ch1=A1, Ch2=C3, Ch3=C4, Ch4=A2)
Audio: via PvRecorder (Picovoice) at 16 kHz mono
"""
import time
import threading
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    from pvrecorder import PvRecorder
    HAS_PVRECORDER = True
except ImportError:
    HAS_PVRECORDER = False
    logger.warning("pvrecorder not installed — audio recording disabled. Run: pip install pvrecorder")


class RecordingEngine:
    """Captures EEG and audio simultaneously with shared time reference."""

    AUDIO_SAMPLE_RATE = 16000
    AUDIO_FRAME_LENGTH = 512

    def __init__(self, device_manager):
        self._dm = device_manager
        self._recording = False
        self._paused = False

        # Shared time reference
        self._t0 = None
        self._t0_unix = None

        # EEG buffers — each row is [A1, C3, C4, A2]
        self._eeg_raw = []
        self._eeg_timestamps = []
        self._eeg_sample_count = 0

        # Audio buffers (int16 samples from PvRecorder)
        self._audio_frames = []
        self._audio_sample_rate = self.AUDIO_SAMPLE_RATE
        self._audio_channels = 1
        self._recorder = None
        self._audio_device_index = -1

        # Stats
        self._audio_sample_count = 0

        # Callbacks
        self.on_audio_level = None
        self.on_eeg_sample = None
        self.on_recording_error = None

        # Previous EEG callback (to restore on stop)
        self._prev_eeg_cb = None

    @property
    def is_recording(self):
        return self._recording

    @property
    def is_paused(self):
        return self._paused

    @property
    def duration_seconds(self):
        if self._t0 is None:
            return 0.0
        return (time.perf_counter_ns() - self._t0) / 1e9

    @property
    def eeg_sample_count(self):
        return self._eeg_sample_count

    @property
    def audio_sample_count(self):
        return self._audio_sample_count

    @property
    def audio_sample_rate(self):
        return self._audio_sample_rate

    @property
    def eeg_sample_rate(self):
        return self._dm.eeg_sample_rate

    @property
    def latest_audio_frame(self):
        """Return the most recent audio frame as float32 array (for visualizer)."""
        if self._audio_frames:
            raw = self._audio_frames[-1]
            return np.array(raw, dtype=np.float32) / 32768.0
        return None

    @staticmethod
    def list_audio_devices():
        """Return list of available input audio devices from PvRecorder."""
        if not HAS_PVRECORDER:
            return []
        try:
            devices = PvRecorder.get_available_devices()
            result = []
            for i, name in enumerate(devices):
                result.append({
                    "index": i,
                    "name": name,
                    "channels": 1,
                    "sample_rate": 16000,
                })
            return result
        except Exception as e:
            logger.error(f"Failed to list audio devices: {e}")
            return []

    def set_audio_device(self, device_index):
        self._audio_device_index = device_index

    def set_audio_sample_rate(self, rate):
        self._audio_sample_rate = int(rate)

    def start(self):
        """Start recording both EEG and audio."""
        if self._recording:
            return
        if not HAS_PVRECORDER:
            if self.on_recording_error:
                self.on_recording_error("pvrecorder not installed. Run: pip install pvrecorder")
            return

        # Clear buffers
        self._eeg_raw = []
        self._eeg_timestamps = []
        self._audio_frames = []
        self._eeg_sample_count = 0
        self._audio_sample_count = 0

        # Set shared time reference
        self._t0_unix = time.time()
        self._t0 = time.perf_counter_ns()

        # Register EEG callback (save previous so we can restore on stop)
        self._prev_eeg_cb = self._dm.on_eeg_data
        self._dm.on_eeg_data = self._on_eeg_data

        # Ensure signal streaming is active
        if not self._dm.is_streaming:
            self._dm.start_signal()

        # Start audio recorder
        try:
            self._recorder = PvRecorder(
                device_index=self._audio_device_index,
                frame_length=self.AUDIO_FRAME_LENGTH
            )
            self._recorder.start()
            self._recording = True
            self._paused = False

            # Start audio capture thread
            self._audio_thread = threading.Thread(
                target=self._audio_loop, daemon=True)
            self._audio_thread.start()

        except Exception as e:
            logger.error(f"Failed to start audio: {e}")
            if self.on_recording_error:
                self.on_recording_error(f"Audio error: {e}")
            return

        self._recording = True
        self._paused = False
        logger.info(f"Recording started | Audio SR={self._audio_sample_rate} | "
                     f"EEG SR={self._dm.eeg_sample_rate}")

    def stop(self):
        """Stop recording and return buffered data."""
        if not self._recording:
            return None

        self._recording = False
        self._paused = False

        # Stop audio
        if self._recorder:
            try:
                self._recorder.stop()
                self._recorder.delete()
            except Exception:
                pass
            self._recorder = None

        # Restore previous EEG callback
        self._dm.on_eeg_data = getattr(self, '_prev_eeg_cb', None)

        # Compile results
        eeg_array = (np.array(self._eeg_raw, dtype=np.float64)
                     if self._eeg_raw else np.array([], dtype=np.float64))
        eeg_ts = (np.array(self._eeg_timestamps, dtype=np.int64)
                  if self._eeg_timestamps else np.array([], dtype=np.int64))

        # Flatten audio frames into one array (int16)
        if self._audio_frames:
            audio_flat = []
            for frame in self._audio_frames:
                audio_flat.extend(frame)
            audio_array = np.array(audio_flat, dtype=np.int16)
        else:
            audio_array = np.array([], dtype=np.int16)

        result = {
            "eeg_raw": eeg_array,
            "eeg_timestamps": eeg_ts,
            "audio": audio_array,
            "audio_sample_rate": self._audio_sample_rate,
            "eeg_sample_rate": self._dm.eeg_sample_rate,
            "t0_unix": self._t0_unix,
            "t0_perf_ns": self._t0,
            "channel_names": self._dm.channel_names,
            "duration_seconds": self.duration_seconds,
        }

        logger.info(f"Recording stopped | EEG={self._eeg_sample_count} samples | "
                     f"Audio={self._audio_sample_count} samples")
        return result

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def get_t0_perf_ns(self):
        return self._t0

    def get_current_offset_ms(self):
        if self._t0 is None:
            return 0
        return (time.perf_counter_ns() - self._t0) / 1e6

    def _on_eeg_data(self, data_list):
        """Callback from device_manager — data_list is List[Headphones2SignalData]."""
        # Forward to previous callback (e.g., Live EEG display)
        if self._prev_eeg_cb:
            self._prev_eeg_cb(data_list)

        if not self._recording or self._paused:
            return

        try:
            for sample in data_list:
                sync_ts_ms = int((time.perf_counter_ns() - self._t0) / 1e6)
                # Ch1=A1, Ch2=C3, Ch3=C4, Ch4=A2
                raw_row = [sample.Ch1, sample.Ch2, sample.Ch3, sample.Ch4]
                self._eeg_raw.append(raw_row)
                self._eeg_timestamps.append(sync_ts_ms)
                self._eeg_sample_count += 1

            # Notify UI with latest sample
            if self.on_eeg_sample and self._eeg_raw:
                latest = self._eeg_raw[-1]
                self.on_eeg_sample({
                    "channels": latest,
                    "timestamp_ms": self._eeg_timestamps[-1],
                    "total_samples": self._eeg_sample_count,
                })

        except Exception as e:
            logger.error(f"EEG data processing error: {e}")

    def _audio_loop(self):
        """Background thread reading audio frames from PvRecorder."""
        while self._recording:
            if self._paused:
                time.sleep(0.01)
                continue
            try:
                frame = self._recorder.read()  # blocking, returns list of int16
                self._audio_frames.append(frame)
                self._audio_sample_count += len(frame)

                # Compute RMS for speech detection
                if self.on_audio_level and frame:
                    arr = np.array(frame, dtype=np.float32) / 32768.0
                    rms = np.sqrt(np.mean(arr ** 2))
                    level = min(1.0, rms / 0.3)
                    self.on_audio_level(level)

            except Exception as e:
                if self._recording:
                    logger.error(f"Audio read error: {e}")
                break
