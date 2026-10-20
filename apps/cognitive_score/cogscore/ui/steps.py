"""The seven wizard steps. Each step unlocks Continue only when its gate is met."""
import math
import os
import time
from tkinter import messagebox

import customtkinter as ctk

from .. import config
from ..engine import State
from . import theme
from .widgets import (BandPlot, Card, EEGPlot, ElectrodeTile, HeroMetric, KSSDialog, SmallMeter, TimelinePlot,
                      fmt_int, legend_row, valid)


class Step(ctk.CTkFrame):
    title = ""
    subtitle = ""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.engine, self.monitor = app.engine, app.monitor
        self._subs, self._timers = [], []
        if self.title:
            ctk.CTkLabel(self, text=self.title, font=theme.font(26, "bold"), text_color=theme.INK).pack(anchor="w")
        if self.subtitle:
            ctk.CTkLabel(self, text=self.subtitle, font=theme.font(14), text_color=theme.MUTED,
                         justify="left").pack(anchor="w", pady=(2, 18))
        self.build()

    def build(self):
        pass

    def enter(self):
        pass

    def leave(self):
        for unsubscribe in self._subs:
            unsubscribe()
        self._subs.clear()
        for timer in self._timers:
            try:
                self.after_cancel(timer)
            except Exception:
                pass
        self._timers.clear()

    def sub(self, bus, event, callback):
        self._subs.append(bus.subscribe(event, callback))

    def every(self, ms, fn):
        def _run():
            fn()
            self._timers.append(self.after(ms, _run))
        self._timers.append(self.after(ms, _run))


def button(parent, text, command, kind="primary", width=180, **kw):
    styles = {
        "primary": {},
        "secondary": {"fg_color": theme.SURFACE, "hover_color": theme.RAISED, "border_width": 1,
                      "border_color": theme.BORDER, "text_color": theme.INK},
        "danger": {"fg_color": theme.CRITICAL, "hover_color": "#a82e2e"},
    }
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=38, corner_radius=8,
                         font=theme.font(14, "bold"), **styles[kind], **kw)


# ── 0. Setup ──────────────────────────────────────────────────────
class ChecklistStep(Step):
    title = "Before you start"
    ITEMS = [
        "Headphones charged and switched on",
        "Paired in Windows Bluetooth settings (USAMS-YX05)",
        "Electrodes resting on skin, hair moved aside",
        "Seated comfortably, notifications off",
    ]

    def build(self):
        self.vars = []
        box = Card(self)
        box.pack(anchor="w", pady=(18, 0))
        for text in self.ITEMS:
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(box, text=text, variable=var, font=theme.font(15), command=self._check,
                            checkbox_width=22, checkbox_height=22).pack(anchor="w", padx=22, pady=11)
            self.vars.append(var)

    def enter(self):
        self._check()

    def tick_all(self):
        for var in self.vars:
            var.set(True)
        self._check()

    def _check(self):
        self.app.set_next(all(v.get() for v in self.vars))


# ── 1. Connect ────────────────────────────────────────────────────
class ConnectStep(Step):
    title = "Connect"
    subtitle = "Select your headphones and connect."

    def build(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        self.scan_btn = button(row, "Search", self.scan)
        self.scan_btn.pack(side="left")
        self.connect_btn = button(row, "Connect", self.connect, kind="secondary", state="disabled")
        self.connect_btn.pack(side="left", padx=10)
        self.list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, height=200, corner_radius=12,
                                           border_width=1, border_color=theme.BORDER)
        self.list.pack(fill="x", pady=16)
        self._placeholder("No devices yet")
        self.selected = ctk.StringVar(value="")
        self.state_lbl = ctk.CTkLabel(self, text="", font=theme.font(15, "bold"), text_color=theme.INK_2)
        self.state_lbl.pack(anchor="w")
        self._devices = []

    def _placeholder(self, text):
        for child in self.list.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.list, text=text, text_color=theme.MUTED, font=theme.font(14)).pack(pady=24)

    def enter(self):
        self.sub(self.engine.events, "devices", self._on_devices)
        self.sub(self.engine.events, "state", lambda old, new: self._refresh())
        self._refresh()

    def scan(self):
        self._placeholder("Searching…")
        self.selected.set("")
        self.engine.scan()

    def connect(self):
        if self.selected.get():
            self.engine.connect(self.selected.get())

    def select_first(self):
        if self._devices:
            self.selected.set(self._devices[0]["serial"])
            self._refresh()

    def _on_devices(self, devices):
        self._devices = devices
        for child in self.list.winfo_children():
            child.destroy()
        for d in devices:
            ctk.CTkRadioButton(self.list, text=f"{d['name']}    {d['serial']}", value=d["serial"],
                               variable=self.selected, font=theme.font(15), command=self._refresh).pack(anchor="w", padx=18, pady=8)
        if len(devices) == 1:
            self.selected.set(devices[0]["serial"])
        self._refresh()

    def _refresh(self):
        st = self.engine.state
        if st == State.IDLE and not self._devices:
            self._placeholder("No devices found")
        self.scan_btn.configure(state="normal" if st in (State.IDLE, State.DEVICES_FOUND) else "disabled")
        self.connect_btn.configure(state="normal" if st == State.DEVICES_FOUND and self.selected.get() else "disabled")
        connected = st not in (State.IDLE, State.SCANNING, State.DEVICES_FOUND, State.CONNECTING)
        text = {State.SCANNING: "Searching…", State.CONNECTING: "Connecting…"}.get(st, "")
        if connected:
            text = "✓  Connected"
            self.app.header_device(self.engine.device_info)
        self.state_lbl.configure(text=text, text_color=theme.GOOD if connected else theme.INK_2)
        self.app.set_next(connected)


# ── 2. Signal quality ─────────────────────────────────────────────
class SignalStep(Step):
    title = "Signal quality"
    subtitle = "Adjust the headphones until every electrode shows Good or Fair."

    def build(self):
        self.tiles_row = ctk.CTkFrame(self, fg_color="transparent")
        self.tiles_row.pack(fill="x")
        self.tiles = {}
        bar_row = ctk.CTkFrame(self, fg_color="transparent")
        bar_row.pack(fill="x", pady=(16, 6))
        self.gate_lbl = ctk.CTkLabel(bar_row, text="Waiting for electrodes…", font=theme.font(14), text_color=theme.INK_2)
        self.gate_lbl.pack(side="left")
        self.override_btn = ctk.CTkButton(bar_row, text="Skip check", width=100, fg_color="transparent",
                                          hover_color=theme.RAISED, text_color=theme.MUTED, command=self.proceed_anyway)
        self.override_btn.pack(side="right")
        self.gate_bar = ctk.CTkProgressBar(self, height=6, progress_color=theme.GOOD, fg_color=theme.RAISED)
        self.gate_bar.set(0)
        self.gate_bar.pack(fill="x")
        card = Card(self)
        card.pack(fill="both", expand=True, pady=(16, 0))
        self.eeg = EEGPlot(card)
        self.eeg.widget.pack(fill="both", expand=True, padx=10, pady=10)
        self.opened = False

    def enter(self):
        self.eeg.setup(self.engine.channel_names, self.engine.sample_rate)
        self.sub(self.monitor.events, "quality", self._on_quality)
        self.sub(self.engine.events, "eeg", lambda ts, processed, raw: self.eeg.push(processed))
        self.every(250, self.eeg.refresh)
        self.app.set_next(self.opened)

    def proceed_anyway(self):
        self.monitor.override_gate("signal_quality", self.gate_lbl.cget("text"))
        self.opened = True
        self.app.set_next(True)

    def _on_quality(self, grades, progress, is_open):
        for name in grades:
            if name not in self.tiles:
                tile = ElectrodeTile(self.tiles_row, name)
                tile.pack(side="left", padx=(0, 12))
                self.tiles[name] = tile
        for name, tile in self.tiles.items():
            tile.set(self.monitor.gate_last_values.get(name, math.nan), grades.get(name, "bad"))
        self.gate_bar.set(progress)
        bad = [n for n, g in grades.items() if g == "bad"]
        if is_open:
            self.opened = True
            text, colour = "✓  Signal is ready", theme.GOOD
        elif bad:
            text, colour = f"Adjust {', '.join(bad)}", theme.INK_2
        else:
            text, colour = "Hold still…", theme.INK_2
        self.gate_lbl.configure(text=text, text_color=colour)
        self.app.set_next(self.opened)


# ── 3. Calibration ────────────────────────────────────────────────
class CalibrationStep(Step):
    title = "Eyes-closed calibration"
    subtitle = "Press Start, close your eyes and relax for 30 seconds. A tone tells you when to open them."

    def build(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        self.start_btn = button(row, "Start", self.start)
        self.start_btn.pack(side="left")
        if self.app.fast:
            button(row, "Use defaults", self.use_typical, kind="secondary").pack(side="left", padx=10)
        self.count = ctk.CTkLabel(self, text="30", font=theme.font(120, "bold"), text_color=theme.RAISED)
        self.count.pack(pady=(40, 0))
        self.bar = ctk.CTkProgressBar(self, height=6, fg_color=theme.RAISED, width=520)
        self.bar.set(0)
        self.bar.pack(pady=10)
        self.result = ctk.CTkLabel(self, text="", font=theme.font(16), text_color=theme.INK_2)
        self.result.pack(pady=10)
        self._started = None

    def enter(self):
        self.sub(self.engine.events, "calibrated", self._on_done)
        self.sub(self.engine.events, "calibration_failed", self._on_failed)
        self.every(200, self._tick)
        self.app.set_next(self.engine.state == State.CALIBRATED)

    def start(self):
        self.engine.start_calibration()
        self._started = time.monotonic()
        self.start_btn.configure(state="disabled")
        self.count.configure(text_color=theme.INK)
        self.result.configure(text="Eyes closed", text_color=theme.INK_2)
        self.app.beep("start")

    def use_typical(self):
        self.engine.import_calibration()

    def _tick(self):
        if self._started is None or self.engine.state != State.CALIBRATING:
            return
        elapsed = time.monotonic() - self._started
        remaining = max(0, config.CALIBRATION_SECONDS - elapsed)
        self.count.configure(text=f"{math.ceil(remaining)}" if remaining > 0 else "…")
        self.bar.set(min(1.0, elapsed / config.CALIBRATION_SECONDS))

    def _on_done(self, data):
        self._started = None
        self.app.status("")
        self.count.configure(text="✓", text_color=theme.GOOD)
        self.bar.set(1)
        self.result.configure(text=f"Alpha peak  {data.get('iapf', math.nan):.1f} Hz" +
                              ("   (defaults)" if data.get("imported") else ""), text_color=theme.INK)
        self.start_btn.configure(state="normal", text="Redo")
        self.app.beep("done")
        self.app.set_next(True)

    def _on_failed(self, reason):
        self._started = None
        self.app.status("")
        self.count.configure(text="✕", text_color=theme.CRITICAL)
        self.result.configure(text=reason, text_color=theme.CRITICAL)
        self.start_btn.configure(state="normal", text="Try again")
        self.app.beep("error")
        self.app.set_next(False)


# ── 4. Baseline ───────────────────────────────────────────────────
class BaselineStep(Step):
    title = "Baseline"
    subtitle = "Eyes open. Look at the cross, breathe normally and stay still."

    def build(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        self.start_btn = button(row, "Start", self.start)
        self.start_btn.pack(side="left")
        if self.app.fast:
            button(row, "Use defaults", self.use_typical, kind="secondary").pack(side="left", padx=10)
        ctk.CTkLabel(self, text="+", font=theme.font(150), text_color=theme.INK).pack(pady=(10, 0))
        self.bar = ctk.CTkProgressBar(self, height=6, fg_color=theme.RAISED, width=520)
        self.bar.set(0)
        self.bar.pack(pady=10)
        self.msg = ctk.CTkLabel(self, text="", font=theme.font(15), text_color=theme.INK_2)
        self.msg.pack()

    def enter(self):
        self.sub(self.engine.events, "baseline_progress", lambda p: self.bar.set(min(1.0, max(0.0, p))))
        self.sub(self.engine.events, "baseline", self._on_done)
        self.sub(self.engine.events, "error", self._on_error)
        self.app.set_next(False)

    def start(self):
        self.engine.start_baseline()
        self.start_btn.configure(state="disabled")
        self.msg.configure(text="Recording…", text_color=theme.INK_2)

    def use_typical(self):
        self.engine.import_baseline()

    def _on_done(self, data):
        self.bar.set(1)
        self.app.status("")
        self.msg.configure(text="✓  Done", text_color=theme.GOOD)
        self.app.beep("done")
        self.after(700, self.app.go_next)

    def _on_error(self, message):
        if self.engine.state == State.CALIBRATED:
            self.start_btn.configure(state="normal")
            self.msg.configure(text=message, text_color=theme.CRITICAL)


# ── 5. Live session ───────────────────────────────────────────────
class LiveStep(Step):
    def build(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        self.clock_lbl = ctk.CTkLabel(top, text="00:00", font=theme.font(30, "bold"), text_color=theme.INK)
        self.clock_lbl.pack(side="left")
        self.signal_lbl = ctk.CTkLabel(top, text="", font=theme.font(13, "bold"))
        self.signal_lbl.pack(side="left", padx=20)
        button(top, "End session", self.stop, kind="danger", width=130).pack(side="right")
        self.break_btn = button(top, "Take a break", self.toggle_break, kind="secondary", width=130)
        self.break_btn.pack(side="right", padx=8)
        button(top, "Marker", self.ask_marker, kind="secondary", width=100).pack(side="right")

        self.banner = ctk.CTkFrame(self, fg_color=theme.RAISED, corner_radius=10)
        self.banner_lbl = ctk.CTkLabel(self.banner, text="", font=theme.font(14, "bold"), text_color=theme.INK)
        self.banner_lbl.pack(side="left", padx=16, pady=10)
        self.banner_close = ctk.CTkButton(self.banner, text="Dismiss", width=90, fg_color="transparent",
                                          hover_color=theme.SURFACE, text_color=theme.MUTED, command=self._hide_banner)
        self.banner_close.pack(side="right", padx=8)
        self.banner_btn = button(self.banner, "Take a break", self.toggle_break, width=130)
        self.banner_btn.pack(side="right", padx=4, pady=6)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, pady=(14, 0))
        heroes = ctk.CTkFrame(self.body, fg_color="transparent")
        heroes.pack(fill="x")
        self.hero = {k: HeroMetric(heroes, label, theme.METRIC_COLOURS[k])
                     for k, label in (("attention", "Attention"), ("cognitive_load", "Cognitive load"),
                                      ("stress", "Stress"))}
        for i, card in enumerate(self.hero.values()):
            heroes.grid_columnconfigure(i, weight=1, uniform="hero")
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 2 else 6))

        charts = ctk.CTkFrame(self.body, fg_color="transparent")
        charts.pack(fill="both", expand=True, pady=(12, 0))
        charts.grid_columnconfigure(0, weight=3)
        charts.grid_columnconfigure(1, weight=2)
        charts.grid_rowconfigure(0, weight=1)

        self.timeline = _timeline_card(charts, "Session")

        bc = Card(charts)
        bc.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        head = ctk.CTkFrame(bc, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(12, 0))
        ctk.CTkLabel(head, text="Brain waves", font=theme.font(14, "bold"), text_color=theme.INK_2).pack(side="left")
        self.bands = BandPlot(bc)
        self.bands.widget.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        strip = Card(self.body)
        strip.pack(fill="x", pady=(12, 0))
        self.small = {"relaxation": SmallMeter(strip, "Relaxation"), "fatigue": SmallMeter(strip, "Fatigue"),
                      "heart_rate": SmallMeter(strip, "Heart rate", " bpm")}
        self.small["relaxation"].pack(side="left", fill="x", expand=True, padx=18, pady=12)
        self.small["fatigue"].pack(side="left", fill="x", expand=True, padx=18, pady=12)
        self._hr_shown = False
        self._kss_dialog = None
        self._disconnected = False
        self._last_snap = None

    def enter(self):
        self.app.set_next(False, visible=False)
        self.sub(self.monitor.events, "scores", self._on_scores)
        self.sub(self.monitor.events, "break_suggested", self._on_break_suggested)
        self.sub(self.monitor.events, "self_report_due", self.open_kss)
        self.sub(self.monitor.events, "stress_episode", self._on_stress_episode)
        self.sub(self.engine.events, "disconnected", self._on_disconnected)
        self.every(1000, self._tick)

    # actions
    def ask_marker(self):
        dialog = ctk.CTkInputDialog(title="Marker", text="Label")
        text = dialog.get_input()
        if text:
            self.add_marker(text)

    def add_marker(self, text):
        text = text.strip()
        if text:
            self.monitor.add_marker(text)
            self.app.status(f"Marker: {text}")

    def toggle_break(self):
        if self.monitor.in_break:
            self.monitor.end_break()
            self.break_btn.configure(text="Take a break")
            self._hide_banner()
        else:
            self.monitor.start_break()
            self.break_btn.configure(text="Resume")
            self._show_banner("On a break", button="Resume", dismiss=False)

    def open_kss(self):
        if self._kss_dialog is None or not self._kss_dialog.winfo_exists():
            self.app.beep("prompt")
            self._kss_dialog = KSSDialog(self.app, self.monitor.record_self_report, self.monitor.skip_self_report)

    def stop(self, confirm=True):
        if confirm and not messagebox.askyesno("End session", "End the session?"):
            return
        self.leave()
        if self._kss_dialog is not None and self._kss_dialog.winfo_exists():
            self._kss_dialog.destroy()
        self.app.finish_session()

    # events
    def _on_scores(self, s):
        self._last_snap = s
        ref_ready = s["reference_ready"]
        wait = int(math.ceil(s["reference_remaining_s"]))
        wait_text = f"Starts in {wait // 60}:{wait % 60:02d}"
        for key, card in self.hero.items():
            ready = ref_ready or key != "stress"
            flag = "Stress episode" if key == "stress" and s["stress_episode"] else None
            card.set(s[key] if ready else math.nan, s["levels"][key] if ready else wait_text,
                     dim=s["signal_poor"], flag=flag)
        self.small["relaxation"].set(s["relaxation"])
        if ref_ready:
            self.small["fatigue"].set(s["fatigue"])
        else:
            self.small["fatigue"].set(math.nan, text=wait_text)
        if valid(s["heart_rate"]):
            if not self._hr_shown:
                self.small["heart_rate"].pack(side="left", fill="x", expand=True, padx=18, pady=12)
                self._hr_shown = True
            self.small["heart_rate"].set(s["heart_rate"], fraction=(s["heart_rate"] - 40) / 140)
        if self._disconnected:
            text, colour = "✕  Disconnected", theme.CRITICAL
        elif s["signal_poor"]:
            text, colour = "▲  Adjust headphones", theme.WARNING
        else:
            text, colour = "●  Signal good", theme.GOOD
        self.signal_lbl.configure(text=text, text_color=colour)

    def _draw_bands(self):
        s = self._last_snap
        if s:
            self.bands.update_from(s["bands_change"], s["bands_ready"])

    def _on_break_suggested(self, reason):
        self.app.beep("prompt")
        self._show_banner(f"Time for a short break  ·  {reason}", button="Take a break")

    def _on_stress_episode(self, active):
        if active:
            self.app.beep("prompt")

    def _on_disconnected(self):
        self._disconnected = True
        self.app.beep("error")
        self._show_banner("Headphones disconnected. Data so far is saved.", button=None)

    def _tick(self):
        e = int(self.monitor.elapsed_live)
        self.clock_lbl.configure(text=f"{e // 60:02d}:{e % 60:02d}")
        self.timeline.update_from(self.monitor.trend, self.monitor.stress_episodes.episodes,
                                  self.monitor.breaks, now_s=self.monitor.elapsed_live,
                                  window_s=config.TREND_WINDOW_S)
        self._draw_bands()

    def _show_banner(self, text, button=None, dismiss=True):
        self.banner_lbl.configure(text=text)
        if button:
            self.banner_btn.configure(text=button)
            self.banner_btn.pack(side="right", padx=4, pady=6)
        else:
            self.banner_btn.pack_forget()
        if dismiss:
            self.banner_close.pack(side="right", padx=8)
        else:
            self.banner_close.pack_forget()
        self.banner.pack(fill="x", pady=(12, 0), before=self.body)

    def _hide_banner(self):
        self.banner.pack_forget()


# ── 6. Summary ────────────────────────────────────────────────────
class SummaryStep(Step):
    title = "Session summary"

    def build(self):
        self.tiles = ctk.CTkFrame(self, fg_color="transparent")
        self.tiles.pack(fill="x", pady=(16, 0))
        charts = ctk.CTkFrame(self, fg_color="transparent")
        charts.pack(fill="both", expand=True, pady=(12, 0))
        charts.grid_columnconfigure(0, weight=3)
        charts.grid_columnconfigure(1, weight=2)
        charts.grid_rowconfigure(0, weight=1)
        self.timeline = _timeline_card(charts, "Session")
        bc = Card(charts)
        bc.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(bc, text="Brain waves vs baseline (average)", font=theme.font(14, "bold"),
                     text_color=theme.INK_2).pack(anchor="w", padx=18, pady=(12, 0))
        self.bands = BandPlot(bc)
        self.bands.widget.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        self.path_lbl = ctk.CTkLabel(row, text="", font=theme.font(12), text_color=theme.MUTED)
        self.path_lbl.pack(side="left")
        button(row, "Close", self.app.on_close, width=120).pack(side="right")
        button(row, "Open folder", self.open_folder, kind="secondary", width=130).pack(side="right", padx=8)
        self.summary = None

    def _tile(self, parent, label, value, sub=""):
        card = Card(parent)
        ctk.CTkLabel(card, text=label, font=theme.font(13), text_color=theme.MUTED).pack(anchor="w", padx=18, pady=(12, 0))
        ctk.CTkLabel(card, text=value, font=theme.font(30, "bold"), text_color=theme.INK).pack(anchor="w", padx=18)
        ctk.CTkLabel(card, text=sub, font=theme.font(12), text_color=theme.MUTED).pack(anchor="w", padx=18, pady=(0, 12))
        return card

    def enter(self):
        self.app.set_next(False, visible=False)
        s = self.summary = self.monitor.summary()
        sc = s["scores"]
        mins = s["live_duration_s"] / 60
        tiles = [
            ("Duration", f"{int(mins)}:{int(s['live_duration_s'] % 60):02d}", _plural(len(s["breaks"]), "break")),
            ("Attention", fmt_int(sc["attention"]["mean"]), "average"),
            ("Cognitive load", fmt_int(sc["cognitive_load"]["mean"]), "average"),
            ("Stress", fmt_int(sc["stress"]["mean"]), "average"),
            ("Stress episodes", str(len(s["stress_episodes"])),
             f"{s['stress_time_s'] / 60:.1f} min in total" if s["stress_episodes"] else "None"),
            ("Signal", f"{100 - 100 * s['artifact_fraction']:.0f}%", "clean"),
        ]
        for i, (label, value, sub) in enumerate(tiles):
            self.tiles.grid_columnconfigure(i, weight=1, uniform="t")
            self._tile(self.tiles, label, value, sub).grid(row=0, column=i, sticky="nsew",
                                                          padx=(0 if i == 0 else 5, 0 if i == len(tiles) - 1 else 5))
        self.timeline.update_from(list(self.monitor.trend), s["stress_episodes"], s["breaks"],
                                  now_s=s["live_duration_s"])
        self.bands.update_from(s["bands_change_mean"], any(valid(v) for v in s["bands_change_mean"].values()))
        self.path_lbl.configure(text=f"Saved  ·  {os.path.basename(s['session_path'])}" if s["session_path"] else "")

    def open_folder(self):
        if self.summary and self.summary["session_path"]:
            os.startfile(self.summary["session_path"])


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def _timeline_card(parent, title):
    card = Card(parent)
    card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    head = ctk.CTkFrame(card, fg_color="transparent")
    head.pack(fill="x", padx=18, pady=(12, 4))
    ctk.CTkLabel(head, text=title, font=theme.font(14, "bold"), text_color=theme.INK_2).pack(side="left")
    legend_row(head, TimelinePlot.legend_items()).pack(side="right")
    plot = TimelinePlot(card)
    plot.widget.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    return plot


STEPS = [ChecklistStep, ConnectStep, SignalStep, CalibrationStep, BaselineStep, LiveStep, SummaryStep]
STEP_NAMES = ["Setup", "Connect", "Signal", "Calibration", "Baseline", "Session", "Summary"]
