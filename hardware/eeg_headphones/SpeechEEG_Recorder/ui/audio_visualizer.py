"""Audio Spectrum Visualizer — colorful frequency bar display like an equalizer."""
import tkinter as tk
import numpy as np
import customtkinter as ctk

sd = None  # Audio capture handled by PvRecorder in recording_engine

# Number of frequency bars to display
NUM_BARS = 40
UPDATE_MS = 50  # ~20 FPS
BAR_GAP = 2
SMOOTHING = 0.4  # lower = smoother, 0-1

# Rainbow color gradient (red -> orange -> yellow -> green -> cyan -> blue -> purple)
def _rainbow_colors(n):
    """Generate n rainbow colors as hex strings."""
    colors = []
    for i in range(n):
        hue = i / n  # 0 to 1
        # HSV to RGB with full saturation and value
        h = hue * 6.0
        c = 1.0
        x = 1.0 - abs(h % 2 - 1)
        if h < 1:
            r, g, b = c, x, 0
        elif h < 2:
            r, g, b = x, c, 0
        elif h < 3:
            r, g, b = 0, c, x
        elif h < 4:
            r, g, b = 0, x, c
        elif h < 5:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        colors.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
    return colors


class AudioVisualizer(ctk.CTkFrame):
    """Real-time audio spectrum visualizer with rainbow-colored frequency bars."""

    def __init__(self, parent, width=600, height=150):
        super().__init__(parent, fg_color="transparent")
        self._width = width
        self._height = height
        self._running = False
        self._stream = None
        self._device_index = None
        self._sample_rate = 44100
        self._audio_buffer = np.zeros(2048, dtype=np.float32)
        self._bar_heights = np.zeros(NUM_BARS)  # smoothed heights
        self._colors = _rainbow_colors(NUM_BARS)

        # Audio level callback (for speech detection etc.)
        self.on_audio_level = None

        self._build_ui()

    def _build_ui(self):
        # Canvas for drawing bars
        self._canvas = tk.Canvas(self, width=self._width, height=self._height,
                                  bg="#1a1a1a", highlightthickness=0, bd=0)
        self._canvas.pack(fill="x", expand=True)

        # Pre-create bar rectangles
        self._bar_ids = []
        bar_w = max(1, (self._width - (NUM_BARS + 1) * BAR_GAP) // NUM_BARS)
        for i in range(NUM_BARS):
            x0 = BAR_GAP + i * (bar_w + BAR_GAP)
            x1 = x0 + bar_w
            rect = self._canvas.create_rectangle(x0, self._height, x1, self._height,
                                                   fill=self._colors[i], outline="")
            self._bar_ids.append(rect)

        # Level label
        self._level_label = ctk.CTkLabel(self, text="Mic Level: --", font=("", 11))
        self._level_label.pack(pady=(2, 0))

    def set_device(self, device_index):
        self._device_index = device_index

    def set_sample_rate(self, sr):
        self._sample_rate = int(sr)

    def start(self):
        """Start audio capture and visualization."""
        if self._running or sd is None:
            return

        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                device=self._device_index,
                callback=self._audio_callback,
                blocksize=2048,
            )
            self._stream.start()
            self._running = True
            self._update_bars()
        except Exception as e:
            self._level_label.configure(text=f"Mic error: {e}")

    def stop(self):
        """Stop audio capture and visualization."""
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        # Reset bars
        self._bar_heights = np.zeros(NUM_BARS)
        self._draw_bars()
        self._level_label.configure(text="Mic Level: --")

    def start_with_external_feed(self):
        """Start visualization without own audio stream — call feed_audio() externally."""
        self._running = True
        self._update_bars()

    def feed_audio(self, audio_data):
        """Feed audio data from an external source (e.g., recording engine)."""
        if len(audio_data) > 0:
            self._audio_buffer = audio_data[-2048:].copy() if len(audio_data) > 2048 else audio_data.copy()

    def _audio_callback(self, indata, frames, time_info, status):
        """Sounddevice callback — stores latest audio chunk."""
        self._audio_buffer = indata[:, 0].copy()

        # Compute RMS for level callback
        if self.on_audio_level:
            rms = np.sqrt(np.mean(self._audio_buffer ** 2))
            level = min(1.0, rms / 0.3)
            self.on_audio_level(level)

    def _compute_spectrum(self):
        """Compute frequency spectrum from current audio buffer."""
        data = self._audio_buffer
        if len(data) < 64:
            return np.zeros(NUM_BARS)

        # Apply Hann window
        windowed = data * np.hanning(len(data))

        # FFT
        fft = np.abs(np.fft.rfft(windowed))

        # Only use lower half of spectrum (most interesting audio content)
        useful = fft[:len(fft) // 2]
        if len(useful) < NUM_BARS:
            return np.zeros(NUM_BARS)

        # Group into NUM_BARS bins (logarithmic spacing for more bass detail)
        indices = np.logspace(0, np.log10(len(useful) - 1), NUM_BARS + 1, dtype=int)
        indices = np.clip(indices, 0, len(useful) - 1)

        bars = np.zeros(NUM_BARS)
        for i in range(NUM_BARS):
            start = indices[i]
            end = max(start + 1, indices[i + 1])
            bars[i] = np.mean(useful[start:end])

        # Normalize to 0-1
        max_val = np.max(bars) if np.max(bars) > 0 else 1.0
        bars = bars / max_val

        return bars

    def _update_bars(self):
        """Periodic update of bar heights."""
        if not self._running:
            return

        spectrum = self._compute_spectrum()

        # Smooth transitions
        self._bar_heights = SMOOTHING * spectrum + (1 - SMOOTHING) * self._bar_heights

        self._draw_bars()

        # Update level label
        rms = np.sqrt(np.mean(self._audio_buffer ** 2)) if len(self._audio_buffer) > 0 else 0
        db = max(-60, 20 * np.log10(rms + 1e-10))
        self._level_label.configure(text=f"Mic Level: {db:.0f} dB")

        self.after(UPDATE_MS, self._update_bars)

    def _draw_bars(self):
        """Redraw all bars based on current heights."""
        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()
        if canvas_w < 10:
            canvas_w = self._width
        if canvas_h < 10:
            canvas_h = self._height

        bar_w = max(2, (canvas_w - (NUM_BARS + 1) * BAR_GAP) // NUM_BARS)

        for i in range(NUM_BARS):
            x0 = BAR_GAP + i * (bar_w + BAR_GAP)
            x1 = x0 + bar_w
            h = int(self._bar_heights[i] * (canvas_h - 10))
            y0 = canvas_h - h
            y1 = canvas_h

            self._canvas.coords(self._bar_ids[i], x0, y0, x1, y1)

    @property
    def is_running(self):
        return self._running

    def destroy(self):
        self.stop()
        super().destroy()
