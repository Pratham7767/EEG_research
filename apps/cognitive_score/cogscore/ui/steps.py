"""The seven wizard steps. Each step unlocks Continue only when its gate is met."""
import math
import os
import time
from tkinter import messagebox

import customtkinter as ctk

from .. import config
from ..engine import State
from ..monitor import COMPARE, scene_rows
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

        if self.app.demo or self.app.replay:
            button(self, "All set", self.tick_all, kind="secondary", width=120).pack(anchor="w", pady=(14, 0))

    def enter(self):
        if self.app.replay:
            self.tick_all()
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
        connected = st in (State.STREAMING, State.CALIBRATING, State.CALIBRATED, State.BASELINE, State.LIVE)
        text = {State.SCANNING: "Searching…", State.CONNECTING: "Connecting…",
                State.DISCONNECTED: "✕  Disconnected"}.get(st, "")
        colour = theme.CRITICAL if st == State.DISCONNECTED else theme.INK_2
        if connected:
            text, colour = "✓  Connected", theme.GOOD
            self.app.header_device(self.engine.device_info)
        self.state_lbl.configure(text=text, text_color=colour)
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

    @property
    def seconds(self):
        return config.REPLAY_STEP_S if self.app.replay else config.CALIBRATION_SECONDS

    def enter(self):
        self.sub(self.engine.events, "calibrated", self._on_done)
        self.sub(self.engine.events, "calibration_failed", self._on_failed)
        self.sub(self.engine.events, "state", self._on_state)
        self.every(200, self._tick)
        self.count.configure(text=f"{self.seconds:.0f}")
        self.app.set_next(self.engine.state == State.CALIBRATED)
        self._on_state(None, self.engine.state)

    def _on_state(self, old, new):
        if new == State.DISCONNECTED:
            if old == State.CALIBRATING:
                self._started = None
                self.count.configure(text="✕", text_color=theme.CRITICAL)
                self.result.configure(text="Headphones disconnected: calibration stopped. Start again once "
                                           "they are reconnected.", text_color=theme.CRITICAL)
            self.start_btn.configure(state="disabled")
        elif new in (State.STREAMING, State.CALIBRATED):
            self.start_btn.configure(state="normal")
            self.app.set_next(new == State.CALIBRATED)
        elif new in (State.CONNECTING, State.CALIBRATING):
            self.start_btn.configure(state="disabled")

    def start(self):
        if self.engine.state not in (State.STREAMING, State.CALIBRATED):
            return
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
        remaining = max(0, self.seconds - elapsed)
        self.count.configure(text=f"{math.ceil(remaining)}" if remaining > 0 else "…")
        self.bar.set(min(1.0, elapsed / self.seconds))

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
        self.sub(self.engine.events, "state", self._on_state)
        self.app.set_next(False)

    def _on_state(self, old, new):
        if new == State.DISCONNECTED:
            self.start_btn.configure(state="disabled")
            if old == State.BASELINE:
                self.bar.set(0)
                self.msg.configure(text="Headphones disconnected: baseline stopped. Start again once they are "
                                        "reconnected.", text_color=theme.CRITICAL)
        elif new == State.CALIBRATED:
            self.start_btn.configure(state="normal")

    def start(self):
        if self.engine.state != State.CALIBRATED:
            return
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
        self.after(700, self._advance)

    def _advance(self):
        if self.app.step is self:               # only once, and only from this screen
            self.app.go_next()

    def _on_error(self, message):
        if self.engine.state == State.CALIBRATED:
            self.start_btn.configure(state="normal")
            self.msg.configure(text=message, text_color=theme.CRITICAL)


# ── 5. Live session ───────────────────────────────────────────────
SCENE_ORDER = ("rest", "eyes_closed", "mental_math", "relax")


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

        # demo scenes: one click = marker + big instruction + countdown + tone at the end
        self.scene_btns = {}
        self.show_scenes = bool(self.app.demo or self.app.replay)
        if self.show_scenes:
            bar = ctk.CTkFrame(self, fg_color="transparent")
            bar.pack(fill="x", pady=(10, 0))
            ctk.CTkLabel(bar, text="Scenes" if not self.app.replay else "Scenes (from the recording)",
                         font=theme.font(13, "bold"), text_color=theme.MUTED).pack(side="left", padx=(0, 10))
            for i, key in enumerate(SCENE_ORDER):
                label, secs, _ = config.SCENES[key]
                btn = button(bar, f"{i + 1}  {label}  ·  {secs} s", lambda k=key: self.start_scene(k),
                             kind="secondary", width=150)
                btn.pack(side="left", padx=(0, 8))
                self.scene_btns[key] = btn
                if self.app.replay:
                    btn.configure(state="disabled")
        self.scene_panel = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=12, border_width=2,
                                        border_color=theme.SCENE)
        left = ctk.CTkFrame(self.scene_panel, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=20, pady=12)
        self.scene_title = ctk.CTkLabel(left, text="", font=theme.font(26, "bold"), text_color=theme.INK, anchor="w")
        self.scene_title.pack(anchor="w")
        self.scene_text = ctk.CTkLabel(left, text="", font=theme.font(16), text_color=theme.INK_2, anchor="w",
                                       justify="left", wraplength=800)
        self.scene_text.pack(anchor="w")
        self.scene_count = ctk.CTkLabel(self.scene_panel, text="", font=theme.font(44, "bold"), text_color=theme.SCENE)
        self.scene_count.pack(side="left", padx=16)
        self.scene_stop = button(self.scene_panel, "End scene", self.end_scene, kind="secondary", width=110)
        self.scene_stop.pack(side="left", padx=(0, 16))

        self.banner = ctk.CTkFrame(self, fg_color=theme.RAISED, corner_radius=10)
        self.banner_lbl = ctk.CTkLabel(self.banner, text="", font=theme.font(14, "bold"), text_color=theme.INK)
        self.banner_lbl.pack(side="left", padx=16, pady=10)
        self.banner_close = ctk.CTkButton(self.banner, text="Dismiss", width=90, fg_color="transparent",
                                          hover_color=theme.SURFACE, text_color=theme.MUTED, command=self._hide_banner)
        self.banner_close.pack(side="right", padx=8)
        self.banner_btn = button(self.banner, "Take a break", self._banner_action, width=130)
        self.banner_btn.pack(side="right", padx=4, pady=6)
        self._banner_kind = None

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
        ctk.CTkLabel(head, text="Brain waves vs rest", font=theme.font(14, "bold"), text_color=theme.INK_2).pack(side="left")
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
        self._last_count = None
        self._switching = False

    def enter(self):
        self.app.set_next(False, visible=False)
        self.sub(self.monitor.events, "scores", self._on_scores)
        self.sub(self.monitor.events, "break_suggested", self._on_break_suggested)
        self.sub(self.monitor.events, "self_report_due", self.open_kss)
        self.sub(self.monitor.events, "stress_episode", self._on_stress_episode)
        self.sub(self.monitor.events, "scene", self._on_scene)
        self.sub(self.engine.events, "disconnected", self._on_disconnected)
        self.sub(self.engine.events, "reconnected", self._on_reconnected)
        self.sub(self.engine.events, "replay_break", self._on_replay_break)     # the Monitor handles scenes/markers
        self.sub(self.engine.events, "replay_finished", self._on_replay_finished)
        self.every(1000, self._tick)
        self.every(250, self._scene_tick)

    # actions
    def ask_marker(self):
        dialog = ctk.CTkInputDialog(title="Marker", text="Label")
        text = dialog.get_input()
        if text:
            self.add_marker(text)

    def add_marker(self, text):
        text = (text or "").strip()
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
            self._show_banner("On a break", button="Resume", dismiss=False, kind="break")

    def start_scene(self, key, duration=None):
        if self.monitor.in_break:
            self.app.status("End the break first.", error=True)
            return
        self._switching = self.monitor.scene is not None      # no "finished" tone when switching scenes
        try:
            started = self.monitor.start_scene(key, duration)
        finally:
            self._switching = False
        if started:
            self.app.beep("start")

    def end_scene(self):
        self.monitor.end_scene()

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
        self._draw_signal(s["signal_poor"])

    def _draw_signal(self, poor):
        if self._disconnected:
            text, colour = "✕  Disconnected", theme.CRITICAL
        elif poor:
            text, colour = "▲  Adjust headphones", theme.WARNING
        else:
            text, colour = "●  Signal good", theme.GOOD
        self.signal_lbl.configure(text=text, text_color=colour)

    def _draw_bands(self):
        s = self._last_snap
        if s:
            self.bands.update_from(s["bands_change"], s["bands_ready"])

    def _on_scene(self, key):
        if key is None:
            self.scene_panel.pack_forget()
            if not self._switching:
                self.app.beep("done")              # the tone matters: eyes may be closed
            self.app.status("Scene finished")
            for btn in self.scene_btns.values():
                btn.configure(border_color=theme.BORDER)
            return
        label, _secs, text = config.SCENES[key]
        self.scene_title.configure(text=label)
        self.scene_text.configure(text=text)
        self.scene_stop.configure(state="disabled" if self.app.replay else "normal")
        self._last_count = None
        self._scene_tick()
        self.scene_panel.pack(fill="x", pady=(10, 0), before=self.body)
        for k, btn in self.scene_btns.items():
            btn.configure(border_color=theme.SCENE if k == key else theme.BORDER)

    def _scene_tick(self):
        if self.monitor.scene is None:
            return
        left = int(math.ceil(self.monitor.scene_remaining()))
        if left != self._last_count:
            self._last_count = left
            self.scene_count.configure(text=f"{left // 60}:{left % 60:02d}")

    def _on_replay_break(self, _started):
        """The Monitor already started / ended the break; mirror it on the button and banner."""
        if self.monitor.in_break:
            self.break_btn.configure(text="Resume")
            self._show_banner("On a break (recorded)", button=None, dismiss=False, kind="break")
        else:
            self.break_btn.configure(text="Take a break")
            if self._banner_kind == "break":
                self._hide_banner()

    def _on_replay_finished(self):
        self._show_banner("The recording has ended. Press End session to see the summary.", button="End session",
                          kind="end")

    def _on_break_suggested(self, reason):
        self.app.beep("prompt")
        self._show_banner(f"Time for a short break  ·  {reason}", button="Take a break", kind="suggest")

    def _on_stress_episode(self, active):
        if active:
            self.app.beep("prompt")

    def _on_disconnected(self):
        self._disconnected = True
        self._draw_signal(False)
        self._show_banner("Headphones disconnected. Reconnecting… Data so far is saved.", button=None,
                          dismiss=False, kind="disconnect")

    def _on_reconnected(self):
        self._disconnected = False
        self._draw_signal(False)
        if self._banner_kind == "disconnect":
            self._hide_banner()
        self.app.status("Reconnected. The session continues.")

    def _tick(self):
        e = int(self.monitor.elapsed_live)
        self.clock_lbl.configure(text=f"{e // 60:02d}:{e % 60:02d}")
        self.timeline.update_from(self.monitor.trend, self.monitor.stress_episodes.episodes,
                                  self.monitor.breaks, now_s=self.monitor.elapsed_live,
                                  window_s=config.TREND_WINDOW_S, scenes=self.monitor.scenes,
                                  drops=self.monitor.disconnects)
        self._draw_bands()
        if self._disconnected and self.engine.state == "disconnected" and self._banner_kind == "disconnect":
            self.banner_lbl.configure(text="Headphones disconnected. Press Reconnect (bottom right). "
                                           "Data so far is saved.")

    def _banner_action(self):
        kind = self._banner_kind
        if kind == "end":
            self.stop(confirm=False)
        else:
            self.toggle_break()

    def _show_banner(self, text, button=None, dismiss=True, kind=None):
        self._banner_kind = kind
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
        self._banner_kind = None
        self.banner.pack_forget()


# ── 6. Summary ────────────────────────────────────────────────────
class SummaryStep(Step):
    title = "Session summary"

    def build(self):
        self.tiles = ctk.CTkFrame(self, fg_color="transparent")
        self.tiles.pack(fill="x", pady=(16, 0))
        self.changed = Card(self)
        charts = ctk.CTkFrame(self, fg_color="transparent")
        charts.pack(fill="both", expand=True, pady=(12, 0))
        self.charts = charts
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
        button(row, "Close", self.app.on_close, width=110).pack(side="right")
        button(row, "New session", self.app.new_session, kind="secondary", width=130).pack(side="right", padx=8)
        button(row, "Open folder", self.open_folder, kind="secondary", width=130).pack(side="right")
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
        need = f"needs {config.WORK_REF_S / 60:.0f}+ min"
        tiles = [
            ("Duration", f"{int(mins)}:{int(s['live_duration_s'] % 60):02d}", _plural(len(s["breaks"]), "break")),
            ("Attention", fmt_int(sc["attention"]["mean"]), "average"),
            ("Cognitive load", fmt_int(sc["cognitive_load"]["mean"]), "average"),
            ("Stress", fmt_int(sc["stress"]["mean"]), "average" if valid(sc["stress"]["mean"]) else need),
            ("Stress episodes", str(len(s["stress_episodes"])),
             f"{s['stress_time_s'] / 60:.1f} min in total" if s["stress_episodes"] else "None"),
            ("Signal", f"{100 - 100 * s['artifact_fraction']:.0f}%",
             "clean" + (f" · {_plural(len(s['disconnects']), 'drop')}" if s.get("disconnects") else "")),
        ]
        for i, (label, value, sub) in enumerate(tiles):
            self.tiles.grid_columnconfigure(i, weight=1, uniform="t")
            self._tile(self.tiles, label, value, sub).grid(row=0, column=i, sticky="nsew",
                                                          padx=(0 if i == 0 else 5, 0 if i == len(tiles) - 1 else 5))
        self._build_changed(s)
        self.timeline.update_from(list(self.monitor.trend), s["stress_episodes"], s["breaks"],
                                  now_s=s["live_duration_s"], scenes=(s.get("scenes") or {}).get("list", []),
                                  drops=s.get("disconnects") or [])
        self.bands.update_from(s["bands_change_mean"], any(valid(v) for v in s["bands_change_mean"].values()))
        label = config.MODE_LABELS.get(s.get("mode"), "")
        replay = "  ·  REPLAY of recorded data" if self.app.replay else ""
        self.path_lbl.configure(text=(f"{label} mode{replay}  ·  Saved  ·  {os.path.basename(s['session_path'])}"
                                      if s["session_path"] else ""))

    def _build_changed(self, s):
        ref_label, rows = scene_rows(s)
        if not rows:
            return
        card = self.changed
        ctk.CTkLabel(card, text=f"What changed in each scene   (compared with {ref_label})",
                     font=theme.font(14, "bold"), text_color=theme.INK_2).grid(row=0, column=0, columnspan=7,
                                                                               sticky="w", padx=18, pady=(12, 4))
        heads = ["Scene", "Time"] + [lbl + (" (% pts)" if typ == "band" else "") for _k, lbl, typ in COMPARE]
        for c, h in enumerate(heads):
            ctk.CTkLabel(card, text=h, font=theme.font(12), text_color=theme.MUTED).grid(
                row=1, column=c, sticky="w", padx=(18 if c == 0 else 10, 10))
            card.grid_columnconfigure(c, weight=1 if c else 2)
        for r, (name, secs, cells) in enumerate(rows, start=2):
            ctk.CTkLabel(card, text=name, font=theme.font(15, "bold"), text_color=theme.INK).grid(
                row=r, column=0, sticky="w", padx=18, pady=2)
            ctk.CTkLabel(card, text=f"{secs:.0f} s", font=theme.font(13), text_color=theme.INK_2).grid(
                row=r, column=1, sticky="w", padx=10)
            for c, v in enumerate(cells, start=2):
                text = "—" if not valid(v) else ("0" if round(v) == 0 else f"{v:+.0f}")
                colour = theme.INK if valid(v) and abs(v) >= 10 else theme.INK_2
                ctk.CTkLabel(card, text=text, font=theme.font(15, "bold" if valid(v) and abs(v) >= 10 else "normal"),
                             text_color=colour).grid(row=r, column=c, sticky="w", padx=10)
        ctk.CTkLabel(card, text="Scores: difference of the 0-100 average. Alpha: change of alpha power vs the eyes-open "
                                "rest baseline, minus the same change in the comparison period. The first 5 s of each "
                                "scene are skipped.", font=theme.font(11), text_color=theme.MUTED, wraplength=1000,
                     justify="left").grid(row=len(rows) + 2, column=0, columnspan=7, sticky="w", padx=18, pady=(4, 12))
        card.pack(fill="x", pady=(12, 0), before=self.charts)

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
