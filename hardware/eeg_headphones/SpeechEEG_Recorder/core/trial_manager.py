"""
Trial Manager — manages word prompts, trial timing, and trial log.
Supports custom word input, random/sequential ordering, configurable reps and rest.
"""
import time
import random
import logging
import threading

logger = logging.getLogger(__name__)


class Trial:
    """Represents a single recording trial."""

    def __init__(self, trial_id, word, prompt_time_ms):
        self.trial_id = trial_id
        self.word = word
        self.prompt_time_ms = prompt_time_ms  # ms since t0
        self.speech_start_ms = None
        self.speech_end_ms = None
        self.eeg_start_idx = None
        self.eeg_end_idx = None
        self.audio_start_sample = None
        self.audio_end_sample = None
        self.skipped = False

    def to_dict(self):
        return {
            "trial_id": self.trial_id,
            "word": self.word,
            "prompt_time_ms": self.prompt_time_ms,
            "speech_start_ms": self.speech_start_ms,
            "speech_end_ms": self.speech_end_ms,
            "eeg_start_idx": self.eeg_start_idx,
            "eeg_end_idx": self.eeg_end_idx,
            "audio_start_sample": self.audio_start_sample,
            "audio_end_sample": self.audio_end_sample,
            "skipped": self.skipped,
        }


class TrialManager:
    """Manages the trial-based word prompting workflow."""

    # Speech detection thresholds
    SPEECH_ONSET_THRESHOLD = 0.05   # RMS level to detect speech start
    SPEECH_OFFSET_THRESHOLD = 0.02  # RMS level to detect speech end
    SPEECH_OFFSET_HOLD_MS = 300     # Hold time before declaring speech end

    def __init__(self, recording_engine):
        self._engine = recording_engine
        self._words = []
        self._reps_per_word = 5
        self._rest_between_ms = 3000  # 3 seconds
        self._order = "sequential"  # "none", "sequential", or "random"
        self._none_word = None      # single word for "none" mode

        # Trial queue and state
        self._trial_queue = []
        self._trials = []
        self._current_trial = None
        self._current_trial_idx = 0
        self._running = False
        self._paused = False

        # Speech detection state
        self._speech_detected = False
        self._speech_start_time = None
        self._last_above_threshold = None

        # Pre/post trial EEG window (ms) for capturing context around the word
        self.pre_trial_ms = 500
        self.post_trial_ms = 1000

        # UI callbacks
        self.on_trial_prompt = None     # (Trial) -> None — show word to user
        self.on_trial_complete = None   # (Trial) -> None — trial finished
        self.on_session_complete = None # (list[Trial]) -> None — all trials done
        self.on_rest_period = None      # (float remaining_s) -> None
        self.on_speech_detected = None  # (bool) -> None — speech onset/offset

        # Thread
        self._thread = None

    @property
    def words(self):
        return self._words.copy()

    @property
    def total_trials(self):
        return len(self._trial_queue)

    @property
    def completed_trials(self):
        return len(self._trials)

    @property
    def current_trial_index(self):
        return self._current_trial_idx

    @property
    def is_running(self):
        return self._running

    def set_words(self, words):
        """Set the word list. words is a list of strings."""
        self._words = [w.strip() for w in words if w.strip()]

    def add_word(self, word):
        word = word.strip()
        if word and word not in self._words:
            self._words.append(word)

    def remove_word(self, word):
        if word in self._words:
            self._words.remove(word)

    def set_reps(self, reps):
        self._reps_per_word = max(1, int(reps))

    def set_rest_between(self, ms):
        self._rest_between_ms = max(500, int(ms))

    def set_order(self, order):
        """Set trial order mode: 'none', 'sequential', or 'random'."""
        order = order.lower().strip()
        if order in ("none", "sequential", "random"):
            self._order = order
        else:
            self._order = "sequential"

    def set_none_word(self, word):
        """Set the single word used in 'none' mode."""
        self._none_word = word.strip() if word else None

    def build_trial_queue(self):
        """Build the list of trials based on words, reps, and order mode.

        Modes:
          none       — single word repeated reps_per_word times
          sequential — all words in order, each repeated reps_per_word times
          random     — all words shuffled, each repeated reps_per_word times
        """
        self._trial_queue = []

        if self._order == "none":
            # Single word mode — repeat the chosen word
            word = self._none_word
            if not word and self._words:
                word = self._words[0]
            if word:
                for _ in range(self._reps_per_word):
                    self._trial_queue.append(word)
        else:
            # Sequential or Random — use full word list
            for word in self._words:
                for _ in range(self._reps_per_word):
                    self._trial_queue.append(word)

            if self._order == "random":
                random.shuffle(self._trial_queue)

        self._current_trial_idx = 0
        self._trials = []
        logger.info(f"Trial queue built: {len(self._trial_queue)} trials, order={self._order}")

    def start(self):
        """Start the trial session in a background thread."""
        if self._running or not self._trial_queue:
            return
        if not self._engine.is_recording:
            logger.error("Recording engine must be started before trials")
            return

        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._run_trials, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the trial session."""
        self._running = False
        self._paused = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def get_all_trials(self):
        return [t.to_dict() for t in self._trials]

    def process_audio_level(self, rms_level):
        """Called by recording engine's audio callback to detect speech."""
        if not self._current_trial or not self._running:
            return

        current_ms = self._engine.get_current_offset_ms()

        if not self._speech_detected:
            # Detect onset
            if rms_level > self.SPEECH_ONSET_THRESHOLD:
                self._speech_detected = True
                self._speech_start_time = current_ms
                self._current_trial.speech_start_ms = int(current_ms)

                # Calculate EEG index at speech start
                eeg_sr = self._engine.eeg_sample_rate
                self._current_trial.eeg_start_idx = max(0, int((current_ms / 1000.0) * eeg_sr) - int((self.pre_trial_ms / 1000.0) * eeg_sr))
                self._current_trial.audio_start_sample = max(0, int((current_ms / 1000.0) * self._engine.audio_sample_rate) - int((self.pre_trial_ms / 1000.0) * self._engine.audio_sample_rate))

                if self.on_speech_detected:
                    self.on_speech_detected(True)
        else:
            # Detect offset
            if rms_level > self.SPEECH_OFFSET_THRESHOLD:
                self._last_above_threshold = current_ms
            elif self._last_above_threshold and (current_ms - self._last_above_threshold) > self.SPEECH_OFFSET_HOLD_MS:
                self._speech_detected = False
                self._current_trial.speech_end_ms = int(current_ms)

                # Calculate EEG index at speech end
                eeg_sr = self._engine.eeg_sample_rate
                self._current_trial.eeg_end_idx = int((current_ms / 1000.0) * eeg_sr) + int((self.post_trial_ms / 1000.0) * eeg_sr)
                self._current_trial.audio_end_sample = int((current_ms / 1000.0) * self._engine.audio_sample_rate) + int((self.post_trial_ms / 1000.0) * self._engine.audio_sample_rate)

                if self.on_speech_detected:
                    self.on_speech_detected(False)

    def _run_trials(self):
        """Main trial loop running in background thread."""
        logger.info("Trial session started")

        for idx, word in enumerate(self._trial_queue):
            if not self._running:
                break

            # Wait if paused
            while self._paused and self._running:
                time.sleep(0.1)
            if not self._running:
                break

            self._current_trial_idx = idx

            # Rest period
            if idx > 0:
                if self._order == "none":
                    # In "none" mode, rest = display/taking time = rest_between
                    rest_s = self._rest_between_ms / 1000.0
                else:
                    rest_s = self._rest_between_ms / 1000.0
                rest_end = time.time() + rest_s
                while time.time() < rest_end and self._running:
                    remaining = rest_end - time.time()
                    if self.on_rest_period:
                        self.on_rest_period(remaining)
                    time.sleep(0.05)

            if not self._running:
                break

            # Create trial
            prompt_ms = self._engine.get_current_offset_ms()
            trial = Trial(trial_id=idx + 1, word=word, prompt_time_ms=int(prompt_ms))
            self._current_trial = trial
            self._speech_detected = False
            self._speech_start_time = None
            self._last_above_threshold = None

            # Show prompt
            if self.on_trial_prompt:
                self.on_trial_prompt(trial)

            # Wait for speech detection + completion (max 5 seconds per trial)
            trial_deadline = time.time() + 5.0
            while self._running and time.time() < trial_deadline:
                if trial.speech_end_ms is not None:
                    break
                time.sleep(0.02)

            # If speech wasn't detected, mark time window anyway
            if trial.speech_start_ms is None:
                trial.skipped = True
                trial.speech_start_ms = int(prompt_ms + 500)
                trial.speech_end_ms = int(prompt_ms + 2000)
                eeg_sr = self._engine.eeg_sample_rate
                audio_sr = self._engine.audio_sample_rate
                trial.eeg_start_idx = int((prompt_ms / 1000.0) * eeg_sr)
                trial.eeg_end_idx = int(((prompt_ms + 2000) / 1000.0) * eeg_sr)
                trial.audio_start_sample = int((prompt_ms / 1000.0) * audio_sr)
                trial.audio_end_sample = int(((prompt_ms + 2000) / 1000.0) * audio_sr)

            self._trials.append(trial)
            self._current_trial = None

            if self.on_trial_complete:
                self.on_trial_complete(trial)

        self._running = False
        logger.info(f"Trial session complete: {len(self._trials)} trials recorded")
        if self.on_session_complete:
            self.on_session_complete(self._trials)
