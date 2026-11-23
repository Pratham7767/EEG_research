"""Main window: step sidebar, header, content area, footer with Next.

The SDK is pumped from the Tk loop every 20 ms (single-threaded mode), so all
engine and monitor callbacks arrive on the UI thread.
"""
import logging
import os
import sys
import time

import customtkinter as ctk

from .. import config
from ..engine import State
from . import theme
from .screen import cover, monitor_rect, window_rect
from .steps import STEP_NAMES, STEPS

logger = logging.getLogger(__name__)

BEEPS = {"start": [(880, 200)], "done": [(880, 150), (1175, 250)], "prompt": [(660, 180), (880, 180)],
         "error": [(330, 400)]}


class App(ctk.CTk):
    def __init__(self, engine, monitor, simulate=None, fast=False, sound=True, mode="real", replay=None,
                 fullscreen=False):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.engine, self.monitor = engine, monitor
        self.simulate, self.fast, self.sound = simulate, fast, sound
        self.mode, self.replay = mode, replay
        self.demo = mode == "demo"
        self.relaunch = False                    # set by "New session"; app.py starts a fresh process
        self._finished = False
        self._auto_reconnect_left = 0
        title = "Cognitive Score: Focus & Fatigue Monitor"
        if replay:
            title += f"   (REPLAY of {os.path.basename(os.path.normpath(replay))})"
        self.title(title)
        # Fit the screen (a 1320x840 window does not fit a 125 %-scaled laptop once the
        # taskbar is counted, which hid the Next button), then maximise.
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1320, sw - 40)}x{min(840, sh - 90)}+10+10")
        self.minsize(1000, 620)
        if sys.platform == "win32":
            self.after(50, lambda: self.state("zoomed"))
        self.configure(fg_color=theme.PAGE)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<F11>", lambda _e: self.toggle_fullscreen())
        self.bind("<Control-b>", lambda _e: self._manual_stress_break())
        self.bind("<Control-B>", lambda _e: self._manual_stress_break())
        self.bind("<Escape>", lambda _e: self._on_escape())
        self._fullscreen = False
        if fullscreen:
            self.after(300, lambda: self.toggle_fullscreen(True))
        self._closing = False
        self._pump_count = 0
        from ..sound import Sound
        self.sounds = Sound(BEEPS, enabled=sound)          # laptop speakers, never the EEG headset
        self._build()
        self.steps = []
        self.index = -1
        engine.events.subscribe("status", self.status)
        engine.events.subscribe("error", lambda m: self.status(m, error=True))
        engine.events.subscribe("battery", lambda b: self.battery_lbl.configure(text=f"Battery {b}%"))
        engine.events.subscribe("disconnected", self._on_disconnected)
        engine.events.subscribe("connected", lambda info: self.header_device(info))
        engine.events.subscribe("reconnected", self._on_reconnected)
        engine.events.subscribe("state", lambda old, new: self._refresh_reconnect())
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
        ctk.CTkLabel(bottom, text=f"  {config.MODE_LABELS[self.mode].upper()} MODE  ", font=theme.font(11, "bold"),
                     text_color=theme.PAGE, fg_color=theme.ACCENT if self.demo else theme.INK_2,
                     corner_radius=6).pack(anchor="w", pady=(0, 6))
        if self.replay:
            ctk.CTkLabel(bottom, text="  REPLAY: RECORDED DATA  ", font=theme.font(11, "bold"), text_color=theme.PAGE,
                         fg_color=theme.WARNING, corner_radius=6).pack(anchor="w", pady=(0, 6))
        elif self.simulate:
            ctk.CTkLabel(bottom, text="  SIMULATOR  ", font=theme.font(11, "bold"), text_color=theme.PAGE,
                         fg_color=theme.WARNING, corner_radius=6).pack(anchor="w", pady=(0, 6))
        self.full_btn = ctk.CTkButton(bottom, text="Full screen  (F11)", height=28, width=160, font=theme.font(12),
                                      fg_color="transparent", hover_color=theme.RAISED, border_width=1,
                                      border_color=theme.BORDER, text_color=theme.INK_2,
                                      command=self.toggle_fullscreen)
        self.full_btn.pack(anchor="w", pady=(4, 12))
        self.device_lbl = ctk.CTkLabel(bottom, text="Not connected", font=theme.font(12), text_color=theme.MUTED,
                                       anchor="w", justify="left")
        self.device_lbl.pack(anchor="w")
        self.battery_lbl = ctk.CTkLabel(bottom, text="", font=theme.font(12), text_color=theme.MUTED, anchor="w")
        self.battery_lbl.pack(anchor="w")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=32, pady=(26, 8))

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=1, column=1, sticky="ew", padx=32, pady=(0, 20))
        self.status_lbl = ctk.CTkLabel(foot, text="", font=theme.font(13), text_color=theme.MUTED, anchor="w",
                                       wraplength=760, justify="left")
        self.status_lbl.pack(side="left", fill="x", expand=True)
        self.reconnect_btn = ctk.CTkButton(foot, text="Reconnect", width=130, height=40, corner_radius=8,
                                           font=theme.font(15, "bold"), fg_color=theme.WARNING,
                                           hover_color=theme.SERIOUS, text_color=theme.PAGE,
                                           command=self.reconnect)
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
        if not info:
            return
        self.device_lbl.configure(text=f"● {info.get('name', 'Headphones')}  {info.get('serial', '')}",
                                  text_color=theme.INK_2)

    def toggle_fullscreen(self, on=None):
        """F11: full screen for a projector; Esc leaves it. Not Tk's "-fullscreen": at 125 % display
        scaling it covered only 80 % of the screen (see screen.py)."""
        on = (not self._fullscreen) if on is None else on
        if on == self._fullscreen:
            return
        self._fullscreen = on
        if on:
            rect = monitor_rect(self)
            if sys.platform == "win32":
                self.state("normal")
            cover(self, rect)
        else:
            import tkinter as tk
            tk.Wm.wm_overrideredirect(self, False)
            if sys.platform == "win32":
                self.state("zoomed")
        self.lift()
        self.focus_force()
        self.full_btn.configure(text="Exit full screen  (Esc)" if on else "Full screen  (F11)")

    # ── disconnect / reconnect ───────────────────────────────────
    def _on_disconnected(self):
        self.device_lbl.configure(text="✕ Disconnected", text_color=theme.CRITICAL)
        if self._finished or self._closing:
            return
        self.beep("error")
        self.status("Headphones disconnected. Reconnecting automatically… (data so far is saved)", error=True)
        self._auto_reconnect_left = 1                # one automatic attempt (the engine retries 3 more times)
        self.after(1500, self._auto_reconnect)

    def _auto_reconnect(self):
        if self._auto_reconnect_left > 0 and not self._finished and self.engine.state == State.DISCONNECTED:
            self._auto_reconnect_left -= 1
            self.reconnect()

    def reconnect(self):
        if self.engine.state != State.DISCONNECTED or self._finished:
            return
        try:
            self.engine.reconnect()
        except Exception as exc:
            logger.exception("reconnect failed")
            self.status(f"Reconnect failed: {exc}", error=True)
        self._refresh_reconnect()

    def _on_reconnected(self):
        self.beep("done")
        self.status("Reconnected. The session continues.")

    def _refresh_reconnect(self):
        if self.engine.state == State.DISCONNECTED and not self._finished:
            self.reconnect_btn.pack(side="right", padx=(0, 10))
        else:
            self.reconnect_btn.pack_forget()

    def _on_escape(self):
        """Esc: the stress break screen first (a borderless window may not get the keyboard on Windows,
        so Esc can arrive here), otherwise leave full screen."""
        screen = getattr(self.step, "_stress_screen", None)
        if screen is not None and screen.winfo_exists():
            screen.escape()
        else:
            self.toggle_fullscreen(False)

    def _manual_stress_break(self):
        if self.demo and hasattr(self.step, "manual_stress_break"):
            self.step.manual_stress_break()

    def new_session(self):
        """Close this session and start a fresh window (one headset connection per process)."""
        self.relaunch = True
        self.on_close()

    def beep(self, kind):
        if self.sound:
            self.sounds.play(kind)

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
        self._finished = True
        self.engine.stop()
        self.monitor.close()
        self._refresh_reconnect()
        self.goto(len(STEPS) - 1)

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        try:
            if self.engine.state != State.STOPPED:
                self.engine.stop()
            self.monitor.close()
            self.sounds.close()
        except Exception:
            logger.exception("error while closing")
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
                if app.demo and since > 20 and self._once("scene"):
                    live.start_scene("eyes_closed", duration=6)
                if app.demo and since > 22 and self._once("scene_shot"):
                    self._shot("5e_scene")
                if since > 27 and self._once("sb_open"):
                    app.monitor.request_stress_break("manual")
                if since > 28.5 and self._once("sb_prompt_shot"):
                    scr = live._stress_screen
                    if scr is None or not scr.winfo_exists():
                        self.result = "FAIL: stress break screen did not open"
                    else:
                        scr.update()
                        got, want = window_rect(scr), monitor_rect(app)
                        self.say(f"stress break screen {got}, monitor {want}")
                        if got != want:
                            self.result = f"FAIL: stress break screen {got} does not cover the monitor {want}"
                        self._shot("5f_stress_prompt", window=scr)
                        scr.start(length_s=6)
                if since > 31.2 and self._once("sb_breath_shot") and live._stress_screen is not None:
                    self._shot("5g_stress_breathing", window=live._stress_screen)
                if since > 34 and self._once("sb_done"):
                    scr = live._stress_screen
                    if scr is not None and scr.winfo_exists():
                        self._shot("5h_stress_done", window=scr)
                        scr.close()
                if since > 36 and self._once("f11_on"):
                    app.toggle_fullscreen(True)
                if since > 37 and self._once("f11_check"):
                    app.update()
                    got, want = window_rect(app), monitor_rect(app)
                    self.say(f"F11 window {got}, monitor {want}")
                    if got != want:
                        self.result = f"FAIL: F11 full screen {got} does not cover the monitor {want}"
                    app.toggle_fullscreen(False)
                if since > self.live_seconds:
                    self._shot("5_live")
                    # forced drop + automatic reconnect (simulator only; a replay cannot drop)
                    if app.simulate and getattr(eng, "device", None) is not None:
                        self._advance("reconnect")
                    else:
                        live.stop(confirm=False)
                        self._advance("summary")
            elif p == "reconnect":
                if self._once("drop"):
                    self.say("forcing a disconnect")
                    eng.device.disconnect()
                if app.monitor.disconnects:
                    self._did.add("dropped")
                if "dropped" in self._did and eng.state == State.LIVE and eng.reconnects >= 1 and since > 3:
                    self.say(f"reconnected after {since:.1f} s")
                    self.app.step.stop(confirm=False)
                    self._advance("summary")
                elif since > 75:
                    self.result = (f"FAIL: no reconnect (state={eng.state}, reconnects={eng.reconnects}, "
                                   f"dropped={'dropped' in self._did})")
                    self.app.step.stop(confirm=False)
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
        if len(s["breaks"]) != 2 or any(end is None for _start, end in s["breaks"]):    # manual + stress break
            problems.append(f"breaks not recorded correctly: {s['breaks']}")
        if [k for _, k in s["self_reports_kss"]] != [5]:
            problems.append(f"KSS not recorded: {s['self_reports_kss']}")
        sb = s.get("stress_breaks") or []
        if len(sb) != 1 or sb[0]["action"] != "start" or self.app.monitor.in_break:
            problems.append(f"stress break not recorded correctly: {sb}")
        if self.app.demo and not (s.get("scenes") or {}).get("by_kind"):
            problems.append("demo scene not recorded")
        if self.app.simulate and getattr(self.app.engine, "device", None) is not None and not s["disconnects"]:
            problems.append("forced disconnect not recorded")
        if self.result is None:
            self.result = "PASS" if not problems else "FAIL: " + "; ".join(problems)
        self.say(f"session: {s['session_path']}")
        self.app.on_close()
