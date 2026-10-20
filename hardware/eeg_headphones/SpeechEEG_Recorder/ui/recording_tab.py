"""
Recording Tab — unified speech + EEG recording with live monitoring.

Merges previous Recording Tab and Live EEG Tab into one view:
  - Word list + trial settings + mic selection
  - Live EEG waveforms (all 4 channels) with Raw/Filtered + Monopolar/Bipolar toggles
  - PSD bar graph (Delta, Theta, Alpha, Beta)
  - Per-channel artifact status indicators
  - Audio spectrum visualizer (rainbow bars)
  - Calibration gate — recording only starts after calibration
  - Export to H5 / CSV / NPY
  - Pop-out window option for EEG graphs
"""
import os
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
import time
import numpy as np
from collections import deque

from ui.audio_visualizer import AudioVisualizer

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import logging
logger = logging.getLogger(__name__)

# ── Graph constants ──────────────────────────────────────────────
GRAPH_WINDOW_SECONDS = 5
GRAPH_UPDATE_MS      = 80   # ~12 FPS
PSD_UPDATE_MS        = 500  # PSD bars refresh every 500 ms

# Bipolar derivation definitions (label, ch_A_name_pattern, ch_B_name_pattern)
# These are matched against actual channel_names from the device at runtime.
BIPOLAR_DEFS = [
    ("C3-C4", "C3", "C4"),
    ("C3-A1", "C3", "A1"),
    ("C4-A2", "C4", "A2"),
    ("A1-A2", "A1", "A2"),
]


def _resolve_bipolar_pairs(channel_names):
    """Resolve bipolar pair definitions into (label, idx_a, idx_b) tuples
    using the actual channel name list from the device. Falls back to
    sequential index pairs if channel names don't match the expected pattern."""
    # Build name → index map (case-insensitive, strip whitespace)
    name_map = {}
    for i, name in enumerate(channel_names):
        name_map[name.strip().upper()] = i

    pairs = []
    for label, name_a, name_b in BIPOLAR_DEFS:
        idx_a = name_map.get(name_a.upper())
        idx_b = name_map.get(name_b.upper())
        if idx_a is not None and idx_b is not None:
            pairs.append((label, idx_a, idx_b))

    # Fallback: if no named channels matched, use sequential pairs
    if not pairs and len(channel_names) >= 2:
        n = len(channel_names)
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append((f"{channel_names[i]}-{channel_names[j]}", i, j))

    return pairs


class RecordingTab(ctk.CTkFrame):
    """Unified tab for trial-based speech + EEG recording with live monitoring."""

    def __init__(self, parent, device_manager, recording_engine,
                 trial_manager, export_manager, calibration_manager):
        super().__init__(parent)
        self._dm   = device_manager
        self._engine = recording_engine
        self._tm   = trial_manager
        self._export = export_manager
        self._cm   = calibration_manager

        # Default words
        self._word_list = ["right", "left", "up", "down", "yes", "no"]
        self._tm.set_words(self._word_list)

        # ── EEG ring buffers (per channel, raw + filtered) ──
        self._eeg_buffers_raw      = {}
        self._eeg_buffers_filtered = {}
        self._graph_running   = False
        self._graph_initialized = False
        self._show_filtered   = False
        self._show_bipolar    = False

        # ── Artifact / PSD state ──
        self._latest_artifacts = {}
        self._latest_psd       = None
        self._psd_initialized  = False

        # ── Pop-out window ──
        self._popout_win = None

        # ── Timer ──
        self._timer_running = False

        # ── Audio visualizer feed ──
        self._viz_feed_running = False

        # ── Event-bus unsubscribers ──
        self._unsubs = []

        # ── Last recording data (for re-export) ──
        self._last_recording_data = None
        self._last_trials = None

        # ── Audio device list ──
        self._audio_devices = []

        self._build_ui()
        self._bind_callbacks()
        self._update_word_display()

        # Check calibration status on first load
        self.after(500, self._update_calibration_banner)

    # ================================================================
    #  UI BUILD
    # ================================================================

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Speech + EEG Recorder",
                     font=("", 22, "bold")).pack(pady=(12, 4))

        # ── Calibration status banner ──
        self._cal_banner = ctk.CTkFrame(scroll, fg_color="#3a1a1a", corner_radius=8)
        self._cal_banner.pack(fill="x", padx=20, pady=(5, 2))
        self._cal_banner_label = ctk.CTkLabel(
            self._cal_banner,
            text="Calibration required before recording.  Go to Calibrate tab first.",
            font=("", 13, "bold"), text_color="#FF6B6B")
        self._cal_banner_label.pack(padx=10, pady=6)

        # ── Word List Section ──
        word_frame = ctk.CTkFrame(scroll)
        word_frame.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(word_frame, text="Word List",
                     font=("", 15, "bold")).pack(anchor="w", padx=10, pady=(8, 3))

        self._word_display = ctk.CTkTextbox(word_frame, height=50, state="disabled")
        self._word_display.pack(fill="x", padx=10, pady=4)

        word_input = ctk.CTkFrame(word_frame, fg_color="transparent")
        word_input.pack(fill="x", padx=10, pady=4)

        self._word_entry = ctk.CTkEntry(word_input,
                                         placeholder_text="Type a word to add...")
        self._word_entry.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self._word_entry.bind("<Return>", lambda e: self._add_word())

        ctk.CTkButton(word_input, text="Add", width=70,
                       command=self._add_word).pack(side="left", padx=2)
        ctk.CTkButton(word_input, text="Remove", width=80, fg_color="gray",
                       command=self._remove_word).pack(side="left", padx=2)
        ctk.CTkButton(word_input, text="Clear", width=60, fg_color="gray",
                       command=self._clear_words).pack(side="left", padx=2)

        preset = ctk.CTkFrame(word_frame, fg_color="transparent")
        preset.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(preset, text="Quick:", font=("", 11)).pack(side="left", padx=4)
        for w in ["right", "left", "up", "down", "yes", "no",
                   "stop", "go", "forward", "backward"]:
            ctk.CTkButton(preset, text=w, width=65, height=26, font=("", 10),
                          command=lambda word=w: self._quick_add(word)
                          ).pack(side="left", padx=2)

        # ── Settings Section ──
        settings_frame = ctk.CTkFrame(scroll)
        settings_frame.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(settings_frame, text="Trial Settings",
                     font=("", 15, "bold")).pack(anchor="w", padx=10, pady=(8, 3))

        sg = ctk.CTkFrame(settings_frame, fg_color="transparent")
        sg.pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(sg, text="Reps per word:").grid(row=0, column=0,
                                                      padx=8, pady=4, sticky="w")
        self._reps_entry = ctk.CTkEntry(sg, width=55)
        self._reps_entry.insert(0, "5")
        self._reps_entry.grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkLabel(sg, text="Rest between (s):").grid(row=0, column=2,
                                                         padx=8, pady=4, sticky="w")
        self._rest_entry = ctk.CTkEntry(sg, width=55)
        self._rest_entry.insert(0, "3")
        self._rest_entry.grid(row=0, column=3, padx=4, pady=4)

        ctk.CTkLabel(sg, text="Mode:").grid(row=0, column=4,
                                              padx=8, pady=4, sticky="w")
        self._mode_order_var = ctk.StringVar(value="Sequential")
        self._mode_order_menu = ctk.CTkOptionMenu(
            sg, values=["None", "Sequential", "Random"],
            variable=self._mode_order_var, width=120,
            command=self._on_trial_mode_changed)
        self._mode_order_menu.grid(row=0, column=5, padx=4, pady=4)

        # ── "None" mode: single word selector (hidden by default) ──
        self._none_word_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        self._none_word_frame.pack(fill="x", padx=10, pady=4)
        self._none_word_frame.pack_forget()  # hidden initially

        ctk.CTkLabel(self._none_word_frame, text="Select word:").pack(
            side="left", padx=4)
        self._none_word_var = ctk.StringVar(value="")
        self._none_word_dropdown = ctk.CTkOptionMenu(
            self._none_word_frame, values=self._word_list or ["(empty)"],
            variable=self._none_word_var, width=160)
        self._none_word_dropdown.pack(side="left", padx=4)
        if self._word_list:
            self._none_word_var.set(self._word_list[0])

        # ── Mic selection ──
        mic_row = ctk.CTkFrame(settings_frame, fg_color="transparent")
        mic_row.pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(mic_row, text="Microphone:").pack(side="left", padx=4)
        self._mic_dropdown = ctk.CTkComboBox(mic_row, width=300, state="readonly")
        self._mic_dropdown.pack(side="left", padx=4)
        ctk.CTkButton(mic_row, text="Refresh", width=65,
                       command=self._refresh_mics).pack(side="left", padx=4)
        self._refresh_mics()

        # ── Recording Controls ──
        ctrl = ctk.CTkFrame(scroll)
        ctrl.pack(fill="x", padx=20, pady=8)

        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.pack(pady=8)

        self._start_btn = ctk.CTkButton(
            btn_row, text="START RECORDING", width=200, height=48,
            font=("", 15, "bold"), fg_color="green",
            command=self._start_recording)
        self._start_btn.pack(side="left", padx=8)

        self._pause_btn = ctk.CTkButton(
            btn_row, text="PAUSE", width=100, height=48,
            state="disabled", command=self._pause_recording)
        self._pause_btn.pack(side="left", padx=8)

        self._stop_btn = ctk.CTkButton(
            btn_row, text="STOP", width=100, height=48,
            fg_color="red", state="disabled", command=self._stop_recording)
        self._stop_btn.pack(side="left", padx=8)

        self._export_btn = ctk.CTkButton(
            btn_row, text="EXPORT H5/CSV", width=130, height=48,
            fg_color="#8B5CF6", state="disabled",
            command=self._manual_export)
        self._export_btn.pack(side="left", padx=8)

        self._popout_btn = ctk.CTkButton(
            btn_row, text="Pop-Out Graphs", width=120, height=36,
            fg_color="gray", command=self._toggle_popout)
        self._popout_btn.pack(side="left", padx=8)

        # ── Live Prompt Display ──
        live_frame = ctk.CTkFrame(scroll)
        live_frame.pack(fill="x", padx=20, pady=6)

        self._prompt_frame = ctk.CTkFrame(live_frame, height=100)
        self._prompt_frame.pack(fill="x", padx=10, pady=6)
        self._prompt_frame.pack_propagate(False)
        self._prompt_label = ctk.CTkLabel(self._prompt_frame, text="Ready",
                                           font=("", 44, "bold"))
        self._prompt_label.pack(expand=True)

        # Status bar
        sbar = ctk.CTkFrame(live_frame, fg_color="transparent")
        sbar.pack(fill="x", padx=10, pady=4)

        self._trial_count_label = ctk.CTkLabel(sbar, text="Trial: 0/0",
                                                font=("", 13))
        self._trial_count_label.pack(side="left", padx=12)
        self._timer_label = ctk.CTkLabel(sbar, text="00:00:00",
                                          font=("", 13, "bold"))
        self._timer_label.pack(side="left", padx=12)
        self._eeg_status_label = ctk.CTkLabel(sbar, text="EEG: --",
                                               font=("", 13))
        self._eeg_status_label.pack(side="left", padx=12)
        self._rest_label = ctk.CTkLabel(live_frame, text="", font=("", 13),
                                         text_color="gray")
        self._rest_label.pack(pady=2)

        # ── Artifact status bar ──
        art_frame = ctk.CTkFrame(scroll)
        art_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(art_frame, text="Artifact Status",
                     font=("", 13, "bold")).pack(anchor="w", padx=10, pady=(6, 2))
        self._artifact_container = ctk.CTkFrame(art_frame, fg_color="transparent")
        self._artifact_container.pack(fill="x", padx=10, pady=4)
        self._artifact_labels = {}

        # ── Audio Spectrum Visualizer ──
        viz_frame = ctk.CTkFrame(scroll)
        viz_frame.pack(fill="x", padx=20, pady=4)

        viz_header = ctk.CTkFrame(viz_frame, fg_color="transparent")
        viz_header.pack(fill="x", padx=5, pady=(4, 0))
        ctk.CTkLabel(viz_header, text="Audio Spectrum",
                     font=("", 13, "bold")).pack(side="left", padx=5)
        self._speech_indicator = ctk.CTkLabel(viz_header, text="",
                                               font=("", 13, "bold"), width=100)
        self._speech_indicator.pack(side="right", padx=5)

        self._audio_viz = AudioVisualizer(viz_frame, width=700, height=110)
        self._audio_viz.pack(fill="x", padx=5, pady=4)

        # ── EEG Graphs Section ──
        graph_section = ctk.CTkFrame(scroll)
        graph_section.pack(fill="x", padx=20, pady=6)

        gh = ctk.CTkFrame(graph_section, fg_color="transparent")
        gh.pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkLabel(gh, text="Live EEG", font=("", 15, "bold")).pack(side="left")

        # Signal toggles — Raw/Filtered + Monopolar/Bipolar
        toggle_frame = ctk.CTkFrame(gh, fg_color="transparent")
        toggle_frame.pack(side="right")

        ctk.CTkLabel(toggle_frame, text="Signal:",
                     font=("", 11)).pack(side="left", padx=(0, 4))
        self._signal_var = ctk.StringVar(value="Raw")
        ctk.CTkSegmentedButton(
            toggle_frame, values=["Raw", "Filtered"],
            variable=self._signal_var,
            command=self._on_signal_toggle
        ).pack(side="left", padx=4)

        ctk.CTkLabel(toggle_frame, text="Mode:",
                     font=("", 11)).pack(side="left", padx=(12, 4))
        self._mode_var = ctk.StringVar(value="Monopolar")
        ctk.CTkSegmentedButton(
            toggle_frame, values=["Monopolar", "Bipolar"],
            variable=self._mode_var,
            command=self._on_mode_toggle
        ).pack(side="left", padx=4)

        self._build_eeg_graph(graph_section)

        # ── PSD Band Power Section ──
        psd_section = ctk.CTkFrame(scroll)
        psd_section.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(psd_section, text="EEG Power Spectrum (Band Powers)",
                     font=("", 14, "bold")).pack(anchor="w", padx=10, pady=(6, 0))

        self._build_psd_chart(psd_section)

    # ================================================================
    #  MATPLOTLIB — EEG WAVEFORM GRAPH
    # ================================================================

    def _build_eeg_graph(self, parent):
        self._fig = Figure(figsize=(11, 4.5), dpi=90, facecolor="#2b2b2b")
        self._fig.subplots_adjust(left=0.07, right=0.97, top=0.95,
                                   bottom=0.07, hspace=0.38)
        self._ax_list = []
        self._lines   = []

        canvas_holder = tk.Frame(parent, bg="#2b2b2b")
        canvas_holder.pack(fill="x", padx=8, pady=6)

        self._canvas = FigureCanvasTkAgg(self._fig, master=canvas_holder)
        self._canvas.get_tk_widget().configure(height=360)
        self._canvas.get_tk_widget().pack(fill="x", expand=True)

    def _init_graph_axes(self, labels, n_points):
        """Create one subplot per label (channel or bipolar pair)."""
        self._fig.clear()
        n = len(labels)
        if n == 0:
            return

        colors = ["#00BFFF", "#FF6347", "#32CD32", "#FFD700",
                  "#FF69B4", "#00CED1", "#FFA500", "#BA55D3"]
        win = GRAPH_WINDOW_SECONDS

        self._ax_list = []
        self._lines   = []

        for i, lbl in enumerate(labels):
            ax = self._fig.add_subplot(n, 1, i + 1)
            ax.set_facecolor("#1a1a2e")
            ax.tick_params(colors="gray", labelsize=7)
            ax.set_ylabel(lbl, fontsize=9, color="white",
                          rotation=0, labelpad=35)
            ax.set_xlim(0, win)
            ax.grid(True, alpha=0.15, color="#444")
            if i < n - 1:
                ax.set_xticklabels([])
            else:
                ax.set_xlabel("Time (s)", fontsize=8, color="gray")
            for sp in ax.spines.values():
                sp.set_color("#333")

            x = np.linspace(0, win, n_points)
            y = np.zeros(n_points)
            line, = ax.plot(x, y, color=colors[i % len(colors)],
                            linewidth=0.9, antialiased=True)
            self._ax_list.append(ax)
            self._lines.append(line)

        self._fig.subplots_adjust(left=0.07, right=0.97, top=0.95,
                                   bottom=0.07, hspace=0.38)
        self._graph_initialized = True
        self._canvas.draw_idle()

    def _ensure_buffers(self, ch_names, n_points):
        """Ensure ring buffers exist for all channel names."""
        for ch in ch_names:
            if ch not in self._eeg_buffers_raw:
                self._eeg_buffers_raw[ch] = deque(maxlen=n_points)
                self._eeg_buffers_filtered[ch] = deque(maxlen=n_points)
                for _ in range(n_points):
                    self._eeg_buffers_raw[ch].append(0.0)
                    self._eeg_buffers_filtered[ch].append(0.0)

    def _get_display_labels(self):
        """Return labels based on current mode (monopolar / bipolar)."""
        ch = self._dm.channel_names
        if not ch:
            return []
        if self._show_bipolar:
            pairs = _resolve_bipolar_pairs(ch)
            return [p[0] for p in pairs] if pairs else list(ch)
        return list(ch)

    def _get_display_data(self, n_points):
        """Return list of numpy arrays (one per trace) for current mode."""
        ch_names = self._dm.channel_names
        if not ch_names:
            return []

        buffers = (self._eeg_buffers_filtered if self._show_filtered
                   else self._eeg_buffers_raw)

        if self._show_bipolar:
            # Compute bipolar derivations from the raw/filtered buffers
            pairs = _resolve_bipolar_pairs(ch_names)
            traces = []
            for _name, idx_a, idx_b in pairs:
                if idx_a < len(ch_names) and idx_b < len(ch_names):
                    a = np.array(buffers.get(ch_names[idx_a], []))
                    b = np.array(buffers.get(ch_names[idx_b], []))
                    mn = min(len(a), len(b))
                    if mn > 0:
                        diff = a[-mn:] - b[-mn:]
                        traces.append(diff)
                    else:
                        traces.append(np.zeros(n_points))
                else:
                    traces.append(np.zeros(n_points))
            return traces
        else:
            traces = []
            for ch in ch_names:
                buf = buffers.get(ch)
                if buf is not None:
                    traces.append(np.array(buf))
                else:
                    traces.append(np.zeros(n_points))
            return traces

    def _update_graph(self):
        if not self._graph_running:
            return

        sr = self._dm.eeg_sample_rate
        n_points = int(GRAPH_WINDOW_SECONDS * sr)
        ch_names = self._dm.channel_names

        if ch_names and not self._graph_initialized:
            self._ensure_buffers(ch_names, n_points)
            labels = self._get_display_labels()
            self._init_graph_axes(labels, n_points)

        if self._graph_initialized and self._ax_list:
            traces = self._get_display_data(n_points)
            for i, y in enumerate(traces):
                if i >= len(self._lines):
                    break
                if len(y) == 0:
                    continue
                padded = (y[-n_points:] if len(y) >= n_points
                          else np.pad(y, (n_points - len(y), 0)))
                self._lines[i].set_ydata(padded)
                y_min, y_max = np.min(padded), np.max(padded)
                margin = max(abs(y_max - y_min) * 0.15, 1e-6)
                self._ax_list[i].set_ylim(y_min - margin, y_max + margin)

            try:
                self._canvas.draw_idle()
            except Exception:
                pass

        self.after(GRAPH_UPDATE_MS, self._update_graph)

    # ================================================================
    #  SIGNAL / MODE TOGGLES
    # ================================================================

    def _on_signal_toggle(self, value):
        self._show_filtered = (value == "Filtered")

    def _on_mode_toggle(self, value):
        self._show_bipolar = (value == "Bipolar")
        # Re-init axes with new labels
        sr = self._dm.eeg_sample_rate
        n_points = int(GRAPH_WINDOW_SECONDS * sr)
        labels = self._get_display_labels()
        if labels:
            self._init_graph_axes(labels, n_points)

    # ================================================================
    #  MATPLOTLIB — PSD BAR CHART
    # ================================================================

    def _build_psd_chart(self, parent):
        self._psd_fig = Figure(figsize=(11, 3), dpi=90, facecolor="#2b2b2b")
        self._psd_fig.subplots_adjust(left=0.06, right=0.97, top=0.88, bottom=0.20)

        holder = tk.Frame(parent, bg="#2b2b2b")
        holder.pack(fill="x", padx=8, pady=6)

        self._psd_canvas = FigureCanvasTkAgg(self._psd_fig, master=holder)
        self._psd_canvas.get_tk_widget().configure(height=220)
        self._psd_canvas.get_tk_widget().pack(fill="x", expand=True)

        self._psd_ax = None

    def _draw_psd_bars(self, psd_data):
        """Draw grouped bar chart of Delta / Theta / Alpha / Beta per channel."""
        self._psd_fig.clear()
        ax = self._psd_fig.add_subplot(111)
        self._psd_ax = ax

        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="gray", labelsize=8)
        for sp in ax.spines.values():
            sp.set_color("#333")

        channels = psd_data.get("channels", [])
        if not channels:
            return

        # Band definitions (no SMR — user wants alpha, beta, theta, delta)
        band_keys   = ["delta",           "theta",          "alpha",           "beta"]
        band_labels = ["Delta\n(0.5-4Hz)", "Theta\n(4-8Hz)", "Alpha\n(8-13Hz)", "Beta\n(15-30Hz)"]
        band_colors = ["#9B59B6",          "#3498DB",         "#2ECC71",          "#E74C3C"]

        n_bands    = len(band_keys)
        n_channels = len(channels)
        bar_width  = 0.18
        x = np.arange(n_bands)

        for ch_idx, ch_data in enumerate(channels):
            powers = ch_data.get("band_powers", {})
            vals = [powers.get(b, 0.0) for b in band_keys]
            vals_log = [np.log10(max(v, 1e-12)) for v in vals]
            offset = (ch_idx - n_channels / 2 + 0.5) * bar_width

            ax.bar(x + offset, vals_log, bar_width,
                   label=ch_data.get("channel", f"Ch{ch_idx+1}"),
                   color=band_colors, alpha=0.7 + 0.08 * ch_idx,
                   edgecolor="#555", linewidth=0.5)

        ax.set_xticks(x)
        ax.set_xticklabels(band_labels, fontsize=9, color="white")
        ax.set_ylabel("Power (log)", fontsize=9, color="white")
        ax.legend(loc="upper right", fontsize=8, facecolor="#2b2b2b",
                  edgecolor="#555", labelcolor="white")
        ax.grid(True, alpha=0.15, axis="y", color="#444")

        ind_alpha = psd_data.get("has_individual_alpha", False)
        title = ("Band Powers (IAPF Calibrated)" if ind_alpha
                 else "Band Powers")
        ax.set_title(title, fontsize=10,
                     color="#2ECC71" if ind_alpha else "white")

        try:
            self._psd_canvas.draw_idle()
        except Exception:
            pass

    def _compute_psd_from_buffers(self):
        """Compute PSD band powers from current EEG ring buffers using FFT."""
        ch_names = self._dm.channel_names
        sr = self._dm.eeg_sample_rate
        if not ch_names or sr <= 0:
            return None

        buffers = self._eeg_buffers_raw
        channels = []

        for ch in ch_names:
            buf = buffers.get(ch)
            if buf is None or len(buf) < 64:
                channels.append({
                    "channel": ch,
                    "band_powers": {"delta": 0, "theta": 0, "alpha": 0, "beta": 0},
                })
                continue

            y = np.array(buf)
            # Use last 2 seconds of data for FFT
            n_use = min(len(y), int(sr * 2))
            y = y[-n_use:]

            # Hann window + FFT
            windowed = y * np.hanning(len(y))
            fft_vals = np.abs(np.fft.rfft(windowed)) ** 2
            freqs = np.fft.rfftfreq(len(y), 1.0 / sr)

            # Band powers
            bands = {
                "delta": (0.5, 4),
                "theta": (4, 8),
                "alpha": (8, 13),
                "beta": (15, 30),
            }
            band_powers = {}
            for band_name, (lo, hi) in bands.items():
                mask = (freqs >= lo) & (freqs <= hi)
                if np.any(mask):
                    band_powers[band_name] = float(np.mean(fft_vals[mask]))
                else:
                    band_powers[band_name] = 0.0

            channels.append({"channel": ch, "band_powers": band_powers})

        return {"channels": channels, "has_individual_alpha": False}

    def _compute_artifact_status(self):
        """Simple amplitude-based artifact detection from ring buffers."""
        ch_names = self._dm.channel_names
        if not ch_names:
            return

        ARTIFACT_THRESHOLD = 150.0  # uV — signals above this are artifacts

        for ch in ch_names:
            buf = self._eeg_buffers_raw.get(ch)
            if buf is None or len(buf) < 10:
                continue
            recent = np.array(list(buf)[-50:])  # last 50 samples
            peak = np.max(np.abs(recent))

            if peak > ARTIFACT_THRESHOLD:
                self._latest_artifacts[ch] = {"channel": ch, "artifact": 1, "quality": 3}
            else:
                self._latest_artifacts[ch] = {"channel": ch, "artifact": 0, "quality": 0}

        self.after(0, self._refresh_artifact_display)

    def _update_psd_chart(self):
        if not self._graph_running:
            return

        # Compute PSD from ring buffers (no SDK dependency)
        psd = self._compute_psd_from_buffers()
        if psd and psd.get("channels"):
            self._draw_psd_bars(psd)

        # Also compute artifact status
        self._compute_artifact_status()

        self.after(PSD_UPDATE_MS, self._update_psd_chart)

    # ================================================================
    #  ARTIFACT INDICATORS
    # ================================================================

    def _init_artifact_labels(self):
        for w in self._artifact_container.winfo_children():
            w.destroy()
        self._artifact_labels = {}

        ch_names = self._dm.channel_names
        if not ch_names:
            return
        for ch in ch_names:
            frame = ctk.CTkFrame(self._artifact_container, fg_color="#1a1a2e",
                                  corner_radius=8, width=200, height=48)
            frame.pack(side="left", padx=6, pady=4, expand=True, fill="x")
            frame.pack_propagate(False)

            inner = ctk.CTkFrame(frame, fg_color="transparent")
            inner.pack(expand=True, fill="both", padx=6, pady=4)

            name_lbl = ctk.CTkLabel(inner, text=ch, font=("", 12, "bold"))
            name_lbl.pack(side="left", padx=4)

            dot = ctk.CTkLabel(inner, text="●", font=("", 15),
                               text_color="gray")
            dot.pack(side="left", padx=2)

            status_lbl = ctk.CTkLabel(inner, text="--", font=("", 10))
            status_lbl.pack(side="left", padx=4)

            quality_lbl = ctk.CTkLabel(inner, text="Q: --", font=("", 10),
                                        text_color="gray")
            quality_lbl.pack(side="right", padx=4)

            self._artifact_labels[ch] = (status_lbl, quality_lbl, dot)

    def _on_artifact_status(self, status_list):
        for item in status_list:
            self._latest_artifacts[item["channel"]] = item
        self.after(0, self._refresh_artifact_display)

    def _refresh_artifact_display(self):
        quality_map  = {0: "Good", 1: "OK", 2: "Fair", 3: "Poor", 4: "Bad"}
        quality_color = {0: "#32CD32", 1: "#7FFF00", 2: "#FFD700",
                         3: "#FF8C00", 4: "#FF4444"}
        for ch, (s_lbl, q_lbl, dot) in self._artifact_labels.items():
            data = self._latest_artifacts.get(ch)
            if data is None:
                continue
            artifact = data.get("artifact", -1)
            quality  = data.get("quality", -1)
            if artifact == 0:
                dot.configure(text_color="#32CD32")
                s_lbl.configure(text="Clean", text_color="#32CD32")
            else:
                dot.configure(text_color="#FF4444")
                s_lbl.configure(text="Artifact!", text_color="#FF4444")
            q_text  = quality_map.get(quality, f"Q:{quality}")
            q_color = quality_color.get(quality, "gray")
            q_lbl.configure(text=f"Q: {q_text}", text_color=q_color)

    # ================================================================
    #  POP-OUT WINDOW
    # ================================================================

    def _toggle_popout(self):
        if self._popout_win and self._popout_win.winfo_exists():
            self._popout_win.destroy()
            self._popout_win = None
            self._popout_btn.configure(text="Pop-Out Graphs")
            return

        self._popout_win = ctk.CTkToplevel(self)
        self._popout_win.title("Live EEG + PSD — Pop-out")
        self._popout_win.geometry("1000x700")
        self._popout_win.protocol("WM_DELETE_WINDOW", self._toggle_popout)
        self._popout_btn.configure(text="Close Pop-out")

        ctk.CTkLabel(self._popout_win,
                     text="(Graphs update in main tab — this is a placeholder. "
                          "Drag the main window and this window side-by-side.)",
                     font=("", 12), text_color="gray", wraplength=900
                     ).pack(padx=20, pady=20)

    # ================================================================
    #  CALLBACKS / WIRING
    # ================================================================

    def _bind_callbacks(self):
        self._tm.on_trial_prompt     = self._on_trial_prompt
        self._tm.on_trial_complete   = self._on_trial_complete
        self._tm.on_session_complete = self._on_session_complete
        self._tm.on_rest_period      = self._on_rest_period
        self._tm.on_speech_detected  = self._on_speech_detected

    def _refresh_mics(self):
        from core.recording_engine import RecordingEngine
        devices = RecordingEngine.list_audio_devices()
        names = [f"{d['index']}: {d['name']}" for d in devices]
        if names:
            self._mic_dropdown.configure(values=names)
            self._mic_dropdown.set(names[0])
        else:
            self._mic_dropdown.configure(values=["No microphone found"])
            self._mic_dropdown.set("No microphone found")
        self._audio_devices = devices

    # ================================================================
    #  WORD LIST HELPERS
    # ================================================================

    def _update_word_display(self):
        self._word_display.configure(state="normal")
        self._word_display.delete("1.0", "end")
        self._word_display.insert("1.0", ", ".join(self._word_list))
        self._word_display.configure(state="disabled")
        # Also refresh the None-mode word selector if visible
        if hasattr(self, '_none_word_dropdown'):
            self._refresh_none_word_options()

    def _add_word(self):
        word = self._word_entry.get().strip()
        if word and word not in self._word_list:
            self._word_list.append(word)
            self._tm.add_word(word)
            self._update_word_display()
        self._word_entry.delete(0, "end")

    def _quick_add(self, word):
        if word not in self._word_list:
            self._word_list.append(word)
            self._tm.add_word(word)
            self._update_word_display()

    def _remove_word(self):
        dialog = ctk.CTkInputDialog(text="Enter word to remove:",
                                     title="Remove Word")
        word = dialog.get_input()
        if word and word in self._word_list:
            self._word_list.remove(word)
            self._tm.remove_word(word)
            self._update_word_display()

    def _clear_words(self):
        self._word_list = []
        self._tm.set_words([])
        self._update_word_display()

    def _on_trial_mode_changed(self, value):
        """Handle trial mode dropdown change (None / Sequential / Random)."""
        if value == "None":
            # Show the single-word selector
            self._none_word_frame.pack(fill="x", padx=10, pady=4)
            self._refresh_none_word_options()
        else:
            # Hide the single-word selector
            self._none_word_frame.pack_forget()

    def _refresh_none_word_options(self):
        """Update the None-mode word dropdown with current word list."""
        words = self._word_list if self._word_list else ["(empty)"]
        self._none_word_dropdown.configure(values=words)
        if self._none_word_var.get() not in words:
            self._none_word_var.set(words[0])

    # ================================================================
    #  CALIBRATION CHECK
    # ================================================================

    def _update_calibration_banner(self):
        """Update banner visibility based on calibration state."""
        cal = self._cm.iapf_calibrated
        if cal:
            self._cal_banner_label.configure(
                text="IAPF Calibrated  —  Ready to record",
                text_color="#32CD32")
            self._cal_banner.configure(fg_color="#1a3a1a")
        else:
            self._cal_banner_label.configure(
                text="Calibration recommended before recording.  "
                     "Go to Calibrate tab first.",
                text_color="#FF6B6B")
            self._cal_banner.configure(fg_color="#3a1a1a")

        # Re-check every 2 seconds (calibration happens asynchronously)
        self.after(2000, self._update_calibration_banner)

    def _is_calibrated(self):
        return self._cm.iapf_calibrated

    # ================================================================
    #  RECORDING START / PAUSE / STOP
    # ================================================================

    def _start_recording(self):
        if not self._dm.is_connected:
            messagebox.showwarning("Not Connected",
                                   "Connect to a device first.")
            return
        if not self._word_list:
            messagebox.showwarning("No Words",
                                   "Add at least one word to the list.")
            return

        # ── Calibration gate ──
        if not self._is_calibrated():
            proceed = messagebox.askyesno(
                "Calibration Recommended",
                "IAPF calibration has NOT been done.\n\n"
                "For best results (proper filtered signals and accurate PSD),\n"
                "calibrate first in the Calibrate tab.\n\n"
                "Do you want to record anyway?")
            if not proceed:
                return

        # Configure trial manager
        try:
            reps = int(self._reps_entry.get())
        except ValueError:
            reps = 5
        try:
            rest = float(self._rest_entry.get()) * 1000
        except ValueError:
            rest = 3000

        # Get selected trial mode
        mode = self._mode_order_var.get().lower()  # "none", "sequential", "random"

        self._tm.set_words(self._word_list)
        self._tm.set_reps(reps)
        self._tm.set_rest_between(rest)
        self._tm.set_order(mode)

        # In "none" mode, set the single selected word
        if mode == "none":
            none_word = self._none_word_var.get()
            if not none_word or none_word == "(empty)":
                messagebox.showwarning("No Word Selected",
                                       "Select a word for 'None' mode.")
                return
            self._tm.set_none_word(none_word)

        self._tm.build_trial_queue()

        if self._tm.total_trials == 0:
            messagebox.showwarning("No Trials",
                                   "No trials to run. Check word list and settings.")
            return

        # Mic
        mic_str = self._mic_dropdown.get()
        if mic_str and ":" in mic_str:
            try:
                dev_idx = int(mic_str.split(":")[0])
                self._engine.set_audio_device(dev_idx)
                self._audio_viz.set_device(dev_idx)
            except ValueError:
                pass

        # Wire audio level → speech detection
        self._engine.on_audio_level = lambda lvl: self._tm.process_audio_level(lvl)

        # Wire EEG status + live graph feed
        def _on_eeg(data):
            count = data.get("total_samples", 0)
            self.after(0, lambda c=count:
                       self._eeg_status_label.configure(text=f"EEG: {c} samples"))
            self._feed_eeg_to_graph(data)

        self._engine.on_eeg_sample = _on_eeg

        # Init artifact labels + subscribe EEG events
        # (NeuroSDK doesn't emit PSD or artifact events —
        #  we compute PSD ourselves from the ring buffers)
        self._init_artifact_labels()
        self._unsubs = [
            self._dm.events.subscribe("eeg", self._on_live_eeg_data),
        ]

        # Start recording engine
        self._engine.start()

        # Start audio visualizer — fed from engine
        self._audio_viz.start_with_external_feed()
        self._viz_feed_running = True
        self._feed_viz_audio()

        # Start trials
        self._tm.start()

        # UI state
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal")
        self._stop_btn.configure(state="normal")
        self._export_btn.configure(state="disabled")
        self._prompt_label.configure(text="Get ready...")
        self._trial_count_label.configure(
            text=f"Trial: 0/{self._tm.total_trials}")

        # Start timer
        self._timer_running = True
        self._update_timer()

        # Start live graph + PSD refresh
        self._graph_running = True
        self._graph_initialized = False  # force re-init
        self._update_graph()
        self._update_psd_chart()

    def _pause_recording(self):
        if self._engine.is_paused:
            self._engine.resume()
            self._tm.resume()
            self._pause_btn.configure(text="PAUSE")
        else:
            self._engine.pause()
            self._tm.pause()
            self._pause_btn.configure(text="RESUME")

    def _stop_recording(self):
        self._timer_running   = False
        self._graph_running   = False
        self._viz_feed_running = False

        try:
            self._audio_viz.stop()
        except Exception:
            pass

        # Unsubscribe events
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._unsubs = []

        try:
            self._tm.stop()
        except Exception:
            pass

        try:
            recording_data = self._engine.stop()
        except Exception:
            recording_data = None

        # UI state
        self._start_btn.configure(state="normal")
        self._pause_btn.configure(state="disabled")
        self._stop_btn.configure(state="disabled")
        self._prompt_label.configure(text="Stopped")

        if recording_data is None:
            return

        # Store for later export
        self._last_recording_data = recording_data
        self._last_trials = self._tm.get_all_trials()
        self._export_btn.configure(state="normal")

        # Auto-export
        trials = self._last_trials
        try:
            session_dir = self._export.export_session(
                recording_data, trials, self._cm)
            n_eeg = (recording_data.get("eeg_raw", np.array([])).shape[0]
                     if hasattr(recording_data.get("eeg_raw", np.array([])), "shape")
                     else 0)
            messagebox.showinfo(
                "Session Saved",
                f"Data exported to:\n{session_dir}\n\n"
                f"EEG samples: {n_eeg}\n"
                f"Audio samples: {len(recording_data.get('audio', []))}\n"
                f"Trials: {len(trials)}\n\n"
                f"Files: eeg_raw.npy, eeg_filtered.npy, speech.wav,\n"
                f"  combined_aligned.csv, session.h5, trials.csv,\n"
                f"  metadata.json, calibration.json")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {e}")

    # ================================================================
    #  MANUAL EXPORT  (re-export last session to custom location)
    # ================================================================

    def _manual_export(self):
        if not hasattr(self, '_last_recording_data') or self._last_recording_data is None:
            messagebox.showinfo("No Data", "No recording data to export.")
            return

        folder = filedialog.askdirectory(title="Choose export folder")
        if not folder:
            return

        session_name = time.strftime("session_%Y-%m-%d_%H%M%S")
        try:
            old_base = self._export._base_dir
            self._export._base_dir = folder
            session_dir = self._export.export_session(
                self._last_recording_data,
                self._last_trials,
                self._cm,
                session_name=session_name)
            self._export._base_dir = old_base

            messagebox.showinfo("Exported",
                                f"Session exported to:\n{session_dir}\n\n"
                                "Includes: H5, CSV, NPY, WAV, JSON")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ================================================================
    #  EEG DATA FEED  (from recording engine callback + event bus)
    # ================================================================

    def _feed_eeg_to_graph(self, data):
        """Push data from engine's on_eeg_sample into ring buffers."""
        channels_raw = data.get("channels", [])
        ch_names = self._dm.channel_names
        sr = self._dm.eeg_sample_rate
        n_points = int(GRAPH_WINDOW_SECONDS * sr)
        self._ensure_buffers(ch_names, n_points)

        for i, ch in enumerate(ch_names):
            if i < len(channels_raw):
                buf = self._eeg_buffers_raw.get(ch)
                if buf is not None:
                    buf.append(channels_raw[i])
                # NeuroSDK doesn't provide real-time filtered data —
                # put raw in both buffers (filtering is done post-hoc on export)
                buf_f = self._eeg_buffers_filtered.get(ch)
                if buf_f is not None:
                    buf_f.append(channels_raw[i])

    def _on_live_eeg_data(self, data_list):
        """Event-bus EEG callback — data_list is List[Headphones2SignalData].
        Feed ring buffers for live display even when recording engine is not running."""
        if self._engine.is_recording:
            # Engine callback already feeds buffers via _feed_eeg_to_graph
            return
        try:
            ch_names = self._dm.channel_names
            sr = self._dm.eeg_sample_rate
            n_points = int(GRAPH_WINDOW_SECONDS * sr)
            self._ensure_buffers(ch_names, n_points)

            for sample in data_list:
                # Ch1=A1, Ch2=C3, Ch3=C4, Ch4=A2
                vals = [sample.Ch1, sample.Ch2, sample.Ch3, sample.Ch4]
                for i, ch in enumerate(ch_names):
                    if i < len(vals):
                        self._eeg_buffers_raw[ch].append(vals[i])
                        # No filtered data from NeuroSDK — use raw
                        self._eeg_buffers_filtered[ch].append(vals[i])
        except Exception:
            pass

    def _on_psd_data(self, psd_dict):
        """PSD event bus callback."""
        self._latest_psd = psd_dict

    # ================================================================
    #  AUDIO VISUALIZER FEED
    # ================================================================

    def _feed_viz_audio(self):
        if not getattr(self, '_viz_feed_running', False):
            return
        latest = self._engine.latest_audio_frame
        if latest is not None and len(latest) > 0:
            self._audio_viz.feed_audio(latest)
        self.after(50, self._feed_viz_audio)

    # ================================================================
    #  TIMER
    # ================================================================

    def _update_timer(self):
        if not self._timer_running:
            return
        secs = self._engine.duration_seconds
        h, m, s = int(secs // 3600), int((secs % 3600) // 60), int(secs % 60)
        self._timer_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.after(500, self._update_timer)

    # ================================================================
    #  TRIAL MANAGER CALLBACKS  (from background thread)
    # ================================================================

    def _on_trial_prompt(self, trial):
        self.after(0, lambda: self._show_prompt(trial))

    def _show_prompt(self, trial):
        self._prompt_label.configure(text=trial.word, text_color="white")
        self._prompt_frame.configure(fg_color="#2563EB")
        self._trial_count_label.configure(
            text=f"Trial: {trial.trial_id}/{self._tm.total_trials}")
        self._rest_label.configure(text="")

    def _on_trial_complete(self, trial):
        self.after(0, lambda: self._prompt_label.configure(
            text="...", text_color="gray"))
        self.after(0, lambda: self._prompt_frame.configure(
            fg_color="transparent"))

    def _on_session_complete(self, trials):
        self.after(0, lambda: self._prompt_label.configure(
            text="Session Complete!", text_color="green"))
        self.after(0, self._stop_recording)

    def _on_rest_period(self, remaining):
        self.after(0, lambda r=remaining:
                   self._rest_label.configure(text=f"Rest: {r:.1f}s"))

    def _on_speech_detected(self, detected):
        if detected:
            self.after(0, lambda: self._speech_indicator.configure(
                text="SPEAKING", text_color="green"))
        else:
            self.after(0, lambda: self._speech_indicator.configure(
                text="", text_color="gray"))

    # ================================================================
    #  CLEANUP
    # ================================================================

    def destroy(self):
        self._graph_running = False
        self._timer_running = False
        self._viz_feed_running = False
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._unsubs = []
        if self._popout_win and self._popout_win.winfo_exists():
            self._popout_win.destroy()
        try:
            self._audio_viz.stop()
        except Exception:
            pass
        super().destroy()
