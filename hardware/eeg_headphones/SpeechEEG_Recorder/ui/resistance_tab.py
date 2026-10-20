"""Resistance Tab — live per-channel electrode impedance display with smoothing and trend."""
import time
import tkinter as tk
import customtkinter as ctk
from collections import deque


class ResistanceTab(ctk.CTkFrame):
    """Tab for monitoring electrode resistance/impedance."""

    # Thresholds in Ohms (relaxed for headphone-style electrodes)
    GOOD_THRESHOLD = 20000       # < 20kΩ = Good
    ACCEPTABLE_THRESHOLD = 40000 # < 40kΩ = Acceptable
    # > 40kΩ = Bad

    # Smoothing: keep last N readings per channel for moving average
    SMOOTHING_WINDOW = 10

    def __init__(self, parent, device_manager, tabview=None):
        super().__init__(parent)
        self._dm = device_manager
        self._tabview = tabview
        self._channel_widgets = {}
        self._channel_history = {}   # channel_name -> deque of recent values
        self._channel_min = {}       # track best (lowest) value seen
        self._monitoring = False
        self._start_time = None

        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Electrode Resistance", font=("", 20, "bold")).pack(pady=(15, 5))

        # Tips
        tips_frame = ctk.CTkFrame(self)
        tips_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(tips_frame, text="Tips for faster settling:", font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(5, 2))
        ctk.CTkLabel(tips_frame, text="  - Adjust headphone position so electrodes press firmly on skin",
                     font=("", 12), text_color="gray").pack(anchor="w", padx=10)
        ctk.CTkLabel(tips_frame, text="  - Slightly wet the electrode area (use saline or water on a cotton pad)",
                     font=("", 12), text_color="gray").pack(anchor="w", padx=10)
        ctk.CTkLabel(tips_frame, text="  - Wait 1-2 minutes for skin-electrode contact to stabilize",
                     font=("", 12), text_color="gray").pack(anchor="w", padx=10)
        ctk.CTkLabel(tips_frame, text="  - Minimize head movement during settling",
                     font=("", 12), text_color="gray").pack(anchor="w", padx=10, pady=(0, 5))

        # Legend
        legend = ctk.CTkFrame(self)
        legend.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(legend, text="Good (< 20 kΩ)", text_color="green", font=("", 12)).pack(side="left", padx=15)
        ctk.CTkLabel(legend, text="Acceptable (< 40 kΩ)", text_color="orange", font=("", 12)).pack(side="left", padx=15)
        ctk.CTkLabel(legend, text="Bad (> 40 kΩ)", text_color="red", font=("", 12)).pack(side="left", padx=15)

        # Channel display area
        self._channels_frame = ctk.CTkFrame(self)
        self._channels_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self._placeholder = ctk.CTkLabel(self._channels_frame,
                                          text="Connect device and click 'Start Monitoring' to see resistance values",
                                          font=("", 14), text_color="gray")
        self._placeholder.pack(expand=True)

        # Buttons and elapsed time
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=20, pady=10)

        self._start_btn = ctk.CTkButton(btn_frame, text="Start Monitoring", command=self._start_monitoring)
        self._start_btn.pack(side="left", padx=10)

        self._stop_btn = ctk.CTkButton(btn_frame, text="Stop Monitoring", command=self._stop_monitoring,
                                        state="disabled", fg_color="gray")
        self._stop_btn.pack(side="left", padx=10)

        self._elapsed_label = ctk.CTkLabel(btn_frame, text="", font=("", 13))
        self._elapsed_label.pack(side="left", padx=20)

        self._skip_btn = ctk.CTkButton(btn_frame, text="Proceed Anyway →",
                                        command=self._skip_to_calibration,
                                        fg_color="#8B5E00", hover_color="#6B4700",
                                        font=("", 13, "bold"))
        self._skip_btn.pack(side="right", padx=10)

        self._overall_status = ctk.CTkLabel(btn_frame, text="", font=("", 14, "bold"))
        self._overall_status.pack(side="right", padx=10)

    def _start_monitoring(self):
        if not self._dm.is_connected:
            return
        self._monitoring = True
        self._start_time = time.time()
        self._channel_history = {}
        self._channel_min = {}
        # Subscribe via event bus (no overwrite)
        self._unsub_resistance = self._dm.events.subscribe("resistance", self._on_resistance_data)
        if not self._dm.is_resist_streaming:
            self._dm.start_resistance()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._update_elapsed()

    def _stop_monitoring(self):
        self._monitoring = False
        if hasattr(self, '_unsub_resistance') and self._unsub_resistance:
            self._unsub_resistance()
            self._unsub_resistance = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    def _update_elapsed(self):
        if not self._monitoring or self._start_time is None:
            return
        elapsed = int(time.time() - self._start_time)
        m, s = divmod(elapsed, 60)
        self._elapsed_label.configure(text=f"Monitoring: {m:02d}:{s:02d}")
        self.after(1000, self._update_elapsed)

    def _on_resistance_data(self, data):
        """Called from SDK thread with list of {channel, value} dicts."""
        if not self._monitoring:
            return
        self.after(0, lambda d=data: self._update_display(d))

    def _update_display(self, data):
        if self._placeholder:
            self._placeholder.destroy()
            self._placeholder = None

        for item in data:
            ch_name = item["channel"]
            raw_value = item["value"]

            # Initialize history for new channels
            if ch_name not in self._channel_history:
                self._channel_history[ch_name] = deque(maxlen=self.SMOOTHING_WINDOW)
                self._channel_min[ch_name] = float('inf')

            # Add to history
            self._channel_history[ch_name].append(raw_value)

            # Track best value
            if raw_value < self._channel_min[ch_name]:
                self._channel_min[ch_name] = raw_value

            # Compute smoothed (moving average)
            history = self._channel_history[ch_name]
            smoothed = sum(history) / len(history)

            # Compute trend
            if len(history) >= 3:
                recent_avg = sum(list(history)[-3:]) / 3
                older_avg = sum(list(history)[:3]) / 3
                if recent_avg < older_avg * 0.9:
                    trend = "improving"
                elif recent_avg > older_avg * 1.1:
                    trend = "worsening"
                else:
                    trend = "stable"
            else:
                trend = "measuring..."

            if ch_name not in self._channel_widgets:
                self._create_channel_widget(ch_name)

            self._update_channel(ch_name, smoothed, raw_value, trend)

        # Update overall status
        self._update_overall_status()

    def _create_channel_widget(self, name):
        frame = ctk.CTkFrame(self._channels_frame)
        frame.pack(fill="x", padx=10, pady=8)

        name_label = ctk.CTkLabel(frame, text=name, font=("", 16, "bold"), width=80)
        name_label.pack(side="left", padx=10)

        bar = ctk.CTkProgressBar(frame, width=250)
        bar.pack(side="left", padx=10, expand=True, fill="x")
        bar.set(0)

        value_label = ctk.CTkLabel(frame, text="-- kΩ", font=("", 14), width=100)
        value_label.pack(side="left", padx=5)

        status_label = ctk.CTkLabel(frame, text="--", font=("", 14, "bold"), width=90)
        status_label.pack(side="left", padx=5)

        trend_label = ctk.CTkLabel(frame, text="", font=("", 12), width=100)
        trend_label.pack(side="left", padx=5)

        best_label = ctk.CTkLabel(frame, text="", font=("", 11), text_color="gray", width=90)
        best_label.pack(side="left", padx=5)

        self._channel_widgets[name] = {
            "frame": frame,
            "bar": bar,
            "value_label": value_label,
            "status_label": status_label,
            "trend_label": trend_label,
            "best_label": best_label,
        }

    def _update_channel(self, name, smoothed_ohms, raw_ohms, trend):
        w = self._channel_widgets[name]
        kohms = smoothed_ohms / 1000.0
        best_kohms = self._channel_min.get(name, 0) / 1000.0

        # Update text
        w["value_label"].configure(text=f"{kohms:.1f} kΩ")
        w["best_label"].configure(text=f"Best: {best_kohms:.1f}")

        # Update bar (normalize: 0-50kΩ range, inverted so lower = more filled)
        bar_val = max(0, min(1.0, 1.0 - (smoothed_ohms / 50000.0)))
        w["bar"].set(bar_val)

        # Update status and colors
        if smoothed_ohms < self.GOOD_THRESHOLD:
            w["status_label"].configure(text="Good", text_color="green")
            w["bar"].configure(progress_color="green")
        elif smoothed_ohms < self.ACCEPTABLE_THRESHOLD:
            w["status_label"].configure(text="Acceptable", text_color="orange")
            w["bar"].configure(progress_color="orange")
        else:
            w["status_label"].configure(text="Bad", text_color="red")
            w["bar"].configure(progress_color="red")

        # Update trend
        if trend == "improving":
            w["trend_label"].configure(text="Settling...", text_color="cyan")
        elif trend == "worsening":
            w["trend_label"].configure(text="Adjust fit", text_color="yellow")
        elif trend == "stable":
            w["trend_label"].configure(text="Stable", text_color="gray")
        else:
            w["trend_label"].configure(text=trend, text_color="gray")

    def _update_overall_status(self):
        if not self._channel_widgets:
            return

        all_good = True
        all_acceptable = True
        for name in self._channel_widgets:
            history = self._channel_history.get(name, [])
            if history:
                avg = sum(history) / len(history)
                if avg >= self.GOOD_THRESHOLD:
                    all_good = False
                if avg >= self.ACCEPTABLE_THRESHOLD:
                    all_acceptable = False

        if all_good:
            self._overall_status.configure(text="All electrodes GOOD - ready to proceed!", text_color="green")
        elif all_acceptable:
            self._overall_status.configure(text="Acceptable - can proceed (better contact recommended)", text_color="orange")
        else:
            self._overall_status.configure(text="Waiting for electrodes to settle...", text_color="red")

    def _skip_to_calibration(self):
        """Skip resistance check and go directly to calibration tab."""
        if self._tabview:
            self._tabview.set("3. Calibrate")

    def is_all_good(self):
        """Check if all channels have acceptable resistance."""
        for name in self._channel_widgets:
            history = self._channel_history.get(name, [])
            if history:
                avg = sum(history) / len(history)
                if avg >= self.ACCEPTABLE_THRESHOLD:
                    return False
        return len(self._channel_widgets) > 0
