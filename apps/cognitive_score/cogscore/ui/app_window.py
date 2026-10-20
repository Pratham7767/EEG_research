"""Main window: step sidebar, header, content area, footer with Next.

The SDK is pumped from the Tk loop every 20 ms (single-threaded mode), so all
engine and monitor callbacks arrive on the UI thread.
"""
import logging
import os
import sys
import threading
import time

import customtkinter as ctk

from ..engine import State
from . import theme
from .steps import STEP_NAMES, STEPS

logger = logging.getLogger(__name__)

BEEPS = {"start": [(880, 200)], "done": [(880, 150), (1175, 250)], "prompt": [(660, 180), (880, 180)],
         "error": [(330, 400)]}


class App(ctk.CTk):
    def __init__(self, engine, monitor, simulate=None, fast=False, sound=True):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.engine, self.monitor = engine, monitor
        self.simulate, self.fast, self.sound = simulate, fast, sound
        self.title("Cognitive Score: Focus & Fatigue Monitor")
        # Fit the screen (a 1320x840 window does not fit a 125 %-scaled laptop once the
        # taskbar is counted, which hid the Next button), then maximise.
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1320, sw - 40)}x{min(840, sh - 90)}+10+10")
        self.minsize(1000, 620)
        if sys.platform == "win32":
            self.after(50, lambda: self.state("zoomed"))
        self.configure(fg_color=theme.PAGE)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._closing = False
        self._pump_count = 0
        self._build()
        self.steps = []
        self.index = -1
        engine.events.subscribe("status", self.status)
        engine.events.subscribe("error", lambda m: self.status(m, error=True))
        engine.events.subscribe("battery", lambda b: self.battery_lbl.configure(text=f"Battery {b}%"))
        engine.events.subscribe("disconnected", lambda: self.device_lbl.configure(text="✕ Disconnected",
                                                                                   text_color=theme.CRITICAL))
        self.goto(0)
        self.after(20, self._pump)

    # ── layout ───────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, fg_color=theme.SIDEBAR, corner_radius=0, width=210)
        side.grid(row=0, column=0, rowspan=2, sticky="nsw")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="Cognitive Score", font=theme.font(18, "bold"),
                     text_color=theme.INK).pack(anchor="w", padx=22, pady=(24, 26))
        self.step_lbls = []
        for i, name in enumerate(STEP_NAMES):
            lbl = ctk.CTkLabel(side, text=name, font=theme.font(15), text_color=theme.MUTED, anchor="w",
                               corner_radius=8, height=36)
            lbl.pack(fill="x", padx=12, pady=2)
            self.step_lbls.append(lbl)
        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=22, pady=20)
        if self.simulate:
            ctk.CTkLabel(bottom, text="SIMULATOR", font=theme.font(11, "bold"), text_color=theme.PAGE,
                         fg_color=theme.WARNING, corner_radius=6).pack(anchor="w", pady=(0, 10))
        self.device_lbl = ctk.CTkLabel(bottom, text="Not connected", font=theme.font(12), text_color=theme.MUTED,
                                       anchor="w", justify="left")
        self.device_lbl.pack(anchor="w")
        self.battery_lbl = ctk.CTkLabel(bottom, text="", font=theme.font(12), text_color=theme.MUTED, anchor="w")
        self.battery_lbl.pack(anchor="w")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=32, pady=(26, 8))

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=1, column=1, sticky="ew", padx=32, pady=(0, 20))
        self.status_lbl = ctk.CTkLabel(foot, text="", font=theme.font(13), text_color=theme.MUTED, anchor="w")
        self.status_lbl.pack(side="left", fill="x", expand=True)
        self.next_btn = ctk.CTkButton(foot, text="Continue", width=150, height=40, corner_radius=8,
                                      font=theme.font(15, "bold"), command=self.go_next, state="disabled")
        self.next_btn.pack(side="right")

    # ── navigation ───────────────────────────────────────────────
    def goto(self, index):
        if 0 <= self.index < len(self.steps):
            self.steps[self.index].leave()
            self.steps[self.index].pack_forget()
        self.index = index
        while len(self.steps) <= index:
            self.steps.append(STEPS[len(self.steps)](self.content, self))
        for i, lbl in enumerate(self.step_lbls):
            done, current = i < index, i == index
            lbl.configure(text=f"  {'✓' if done else i + 1}   {STEP_NAMES[i]}",
                          text_color=theme.INK if current else theme.INK_2 if done else theme.MUTED,
                          fg_color=theme.RAISED if current else "transparent",
                          font=theme.font(15, "bold" if current else "normal"))
        step = self.steps[index]
        self.status("")                          # messages belong to the step that produced them
        step.pack(fill="both", expand=True)
        step.enter()

    def go_next(self):
        if self.index + 1 < len(STEPS):
            self.goto(self.index + 1)

    @property
    def step(self):
        return self.steps[self.index]

    def set_next(self, enabled, visible=True):
        if visible:
            self.next_btn.pack(side="right")
            self.next_btn.configure(state="normal" if enabled else "disabled")
        else:
            self.next_btn.pack_forget()

    def status(self, text, error=False):
        self.status_lbl.configure(text=text, text_color=theme.CRITICAL if error else theme.MUTED)

    def header_device(self, info):
        self.device_lbl.configure(text=f"● {info.get('name', 'Headphones')}  {info.get('serial', '')}",
                                  text_color=theme.INK_2)

    def beep(self, kind):
        if not self.sound or sys.platform != "win32":
            return

        def _play():
            import winsound
            for freq, ms in BEEPS.get(kind, []):
                winsound.Beep(freq, ms)
        threading.Thread(target=_play, daemon=True).start()

    # ── SDK pump and shutdown ────────────────────────────────────
    def _pump(self):
        if self._closing:
            return
        try:
            self.engine.pump()
            self._pump_count += 1
            if self._pump_count % 25 == 0:
                self.monitor.tick()
        except Exception:
            logger.exception("pump failed")
        self.after(20, self._pump)

    def finish_session(self):
        self.engine.stop()
        self.monitor.close()
        self.goto(len(STEPS) - 1)

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        try:
            if self.engine.state != State.STOPPED:
                self.engine.stop()
            self.monitor.close()
        finally:
            self.quit()


class Autopilot:
    """--selftest: drives the real UI through every step on the simulator, then
    validates the session folder. Calls the same methods the buttons call."""

    def __init__(self, app, live_seconds=30, timeout_s=240, screenshots_dir=None):
        self.app, self.live_seconds = app, live_seconds
        self.deadline = time.monotonic() + timeout_s
        self.result = None
        self.log = []
        self.shots = screenshots_dir
        self._phase = "checklist"
        self._t = time.monotonic()
        self._did = set()
        app.after(500, self._step)

    def say(self, msg):
        self.log.append(msg)
        print(f"[selftest] {msg}", flush=True)

    def _shot(self, name, window=None):
        if not self.shots:
            return
        os.makedirs(self.shots, exist_ok=True)
        from .capture import grab_window
        win = window or self.app
        win.update()
        time.sleep(0.3)
        win.update()
        grab_window(win).save(os.path.join(self.shots, f"{name}.png"))

    def _once(self, key):
        if key in self._did:
            return False
        self._did.add(key)
        return True

    def _advance(self, phase):
        self._phase, self._t = phase, time.monotonic()
        self.say(f"-> {phase}")

    def _step(self):
        app, eng = self.app, self.app.engine
        if time.monotonic() > self.deadline:
            self.result = f"FAIL: timed out in phase {self._phase} (state={eng.state})"
            app.on_close()
            return
        since = time.monotonic() - self._t
        p = self._phase
        try:
            if p == "checklist":
                app.step.tick_all()
                self._shot("0_checklist")
                app.go_next()
                self._advance("connect")
            elif p == "connect":
                if self._once("scan"):
                    app.step.scan()
                if eng.state == State.DEVICES_FOUND and self._once("connect"):
                    app.step.select_first()
                    app.step.connect()
                if eng.state == State.STREAMING and app.next_btn.cget("state") == "normal":
                    self._shot("1_connect")
                    app.go_next()
                    self._advance("signal")
            elif p == "signal":
                if app.next_btn.cget("state") == "normal" and since > 6:
                    self._shot("2_signal")
                    app.go_next()
                    self._advance("calibration")
                elif since > 20 and self._once("override"):
                    app.step.proceed_anyway()
            elif p == "calibration":
                if self._once("cal"):
                    app.step.use_typical()
                if eng.state == State.CALIBRATED and since > 1:
                    self._shot("3_calibration")
                    app.go_next()
                    self._advance("baseline")
            elif p == "baseline":
                if self._once("base"):
                    self._shot("4_baseline")
                    app.step.use_typical()
                if eng.state == State.LIVE and app.index == 5:
                    self._advance("live")
            elif p == "live":
                live = app.step
                if since > 4 and self._once("marker"):
                    live.add_marker("selftest marker")
                if since > 8 and self._once("break"):
                    live.toggle_break()
                if since > 10 and self._once("break_shot"):
                    self._shot("5c_on_break")
                if since > 12 and self._once("resume"):
                    live.toggle_break()
                if since > 14 and self._once("kss"):
                    app.monitor.events.emit("self_report_due")
                if since > 16 and self._once("kss_answer"):
                    dlg = live._kss_dialog
                    if dlg is not None and dlg.winfo_exists():
                        self._shot("5b_kss", window=dlg)
                        dlg._answer(5)
                    else:
                        self.result = "FAIL: KSS dialog did not open"
                if since > 18 and self._once("suggest"):
                    live._on_break_suggested("50 min without a break")    # banner only; rule timing is unit-tested
                if since > 19 and self._once("suggest_shot"):
                    self._shot("5d_break_prompt")
                    live._hide_banner()
                if since > self.live_seconds:
                    self._shot("5_live")
                    live.stop(confirm=False)
                    self._advance("summary")
            elif p == "summary":
                if since > 2:
                    self._shot("6_summary")
                    self._finish()
                    return
        except Exception as exc:
            logger.exception("selftest step failed")
            self.result = f"FAIL: {p}: {exc!r}"
            app.on_close()
            return
        app.after(200, self._step)

    def _finish(self):
        from ..headless import check_session
        s = self.app.monitor.summary()
        problems = check_session(s["session_path"]) if s["session_path"] else ["no session folder"]
        if not s["markers"]:
            problems.append("marker not recorded")
        if len(s["breaks"]) != 1 or s["breaks"][0][1] is None:
            problems.append(f"break not recorded correctly: {s['breaks']}")
        if [k for _, k in s["self_reports_kss"]] != [5]:
            problems.append(f"KSS not recorded: {s['self_reports_kss']}")
        if self.result is None:
            self.result = "PASS" if not problems else "FAIL: " + "; ".join(problems)
        self.say(f"session: {s['session_path']}")
        self.app.on_close()
