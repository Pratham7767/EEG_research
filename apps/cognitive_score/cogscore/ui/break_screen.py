"""Full-screen stress break: prompt -> guided breathing with live stress -> before/after.

Esc always closes it (prompt: "not now", breathing: ends the break early, done: back to work).
"""
import math
import time
import tkinter as tk

import customtkinter as ctk

from .. import config
from ..metrics import is_valid
from . import theme
from .screen import cover, monitor_rect

BG = "#0b1220"
CIRCLE = "#3987e5"
CIRCLE_SOFT = "#1d3557"


def _duration_text(seconds):
    seconds = int(round(seconds))
    if seconds >= 60:
        m = round(seconds / 60)
        return ("about " if seconds % 60 else "") + f"{m} minute" + ("" if m == 1 else "s")
    return f"{seconds} seconds"


def _num(x):
    return f"{x:.0f}" if is_valid(x) else "—"


class StressBreakScreen(ctk.CTkToplevel):
    def __init__(self, app, info, length_s=None):
        super().__init__(app)
        self.app, self.monitor = app, app.monitor
        self.info = info
        self.length_s = float(length_s or config.STRESS_BREAK_LENGTH_S)
        self.phase = "prompt"
        self.stress = info.get("stress")
        self.history = []                   # stress values during the breathing break (1 per s)
        self._t0 = None
        self._anim = None
        self._anim_t0 = time.monotonic()
        self._size = 300
        self._closed = False
        self.rect = (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())
        self.result = None                  # summary dict from monitor.stress_break_done()

        self.configure(fg_color=BG)
        self.title("Stress break")
        self.protocol("WM_DELETE_WINDOW", self.escape)
        self._cover_screen()
        self.after(150, self._cover_screen)        # customtkinter re-sizes new windows shortly after creation
        self.after(600, self._cover_screen)
        self.bind("<Escape>", lambda _e: self.escape())
        self.monitor.stress_screen_open = True
        self._unsub = self.monitor.events.subscribe("scores", self._on_scores)

        self.body = ctk.CTkFrame(self, fg_color=BG)
        self.body.place(relx=0.5, rely=0.5, anchor="center")
        self._show_prompt()
        self.after(100, self.focus_force)
        app.beep("prompt")

    def _cover_screen(self):
        """Cover the whole monitor the app is on, in real pixels (see screen.py: "-fullscreen" covered
        only 80 % of the screen at 125 % display scaling)."""
        if self._closed:
            return
        self.rect = cover(self, monitor_rect(self.app))
        tk.Wm.wm_attributes(self, "-topmost", True)
        self.lift()
        self.focus_force()

    def _circle(self, size):
        """Breathing circle, animated in every phase until the break is over."""
        self.canvas = tk.Canvas(self.body, width=size, height=size, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(0, 18))
        self._size = size
        if self._anim is None:
            self._anim_t0 = time.monotonic()
            self._animate()

    # ── screens ──────────────────────────────────────────────────
    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _label(self, text, size, weight="normal", colour=theme.INK, pady=(0, 0)):
        lbl = ctk.CTkLabel(self.body, text=text, font=theme.font(size, weight), text_color=colour, justify="center")
        lbl.pack(pady=pady)
        return lbl

    def _show_prompt(self):
        self._clear()
        self._circle(int(self.rect[3] * 0.26))
        if self.info.get("trigger") == "auto":
            title = "Your stress has been high for a while"
        else:
            title = "Time for a short break"
        self._label("STRESS BREAK", 14, "bold", theme.MUTED, pady=(0, 8))
        self._label(title, 40, "bold")
        n = int(round(self.length_s))
        length = f"{n // 60}-minute" if n >= 60 and n % 60 == 0 else f"{n}-second"
        self._label(f"A {length} breathing break. Follow the circle.", 20,
                    colour=theme.INK_2, pady=(10, 30))
        self.stress_lbl = self._label(f"Stress now  {_num(self.stress)}", 22, colour=theme.INK_2, pady=(0, 36))
        row = ctk.CTkFrame(self.body, fg_color=BG)
        row.pack()
        kw = dict(height=52, corner_radius=10, font=theme.font(17, "bold"))
        ctk.CTkButton(row, text="Start break", width=220, command=self.start, **kw).pack(side="left", padx=8)
        ghost = dict(fg_color="transparent", border_width=1, border_color=theme.AXIS, hover_color=CIRCLE_SOFT,
                     text_color=theme.INK_2)
        ctk.CTkButton(row, text=f"Snooze {_duration_text(config.STRESS_BREAK_SNOOZE_S)}", width=200,
                      command=lambda: self.respond("snooze"), **kw, **ghost).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Not now", width=140, command=lambda: self.respond("dismiss"),
                      **kw, **ghost).pack(side="left", padx=8)
        self._label("Esc closes this screen", 12, colour=theme.MUTED, pady=(24, 0))

    def start(self, length_s=None):
        if self.phase != "prompt":                 # double click / Enter twice
            return
        if length_s:
            self.length_s = float(length_s)
        self.monitor.stress_break_response("start")
        self.phase = "breathing"
        self._t0 = time.monotonic()
        self._clear()
        self._anim_t0 = self._t0                   # start on "breathe in"
        self._circle(int(self.rect[3] * 0.42))
        self.cue = self._label("Breathe in", 30, "bold", pady=(0, 4))
        self.count = self._label("", 18, colour=theme.INK_2)
        self.stress_lbl = self._label(f"Stress now  {_num(self.stress)}", 22, colour=theme.INK_2, pady=(22, 6))
        self.spark = tk.Canvas(self.body, width=420, height=70, bg=BG, highlightthickness=0)
        self.spark.pack()
        ctk.CTkButton(self.body, text="End break", width=160, height=44, corner_radius=10, font=theme.font(15),
                      fg_color="transparent", border_width=1, border_color=theme.AXIS, hover_color=CIRCLE_SOFT,
                      text_color=theme.INK_2, command=self.finish).pack(pady=(26, 0))
        self._sample()                             # the circle animation is already running (_circle)

    def finish(self):
        """Breathing over (time up, End break or Esc): show before → after."""
        if self.phase != "breathing":
            return
        self.phase = "done"
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None
        self.result = self.monitor.stress_break_done() or {}
        self.app.beep("done")
        self._clear()
        before, after = self.result.get("before"), self.result.get("after")
        self._label("Break finished", 40, "bold", pady=(0, 24))
        if is_valid(before) and is_valid(after):
            before, after = round(before), round(after)
            diff = after - before
            self._label(f"Stress   {before:.0f}  →  {after:.0f}", 34, "bold", colour=theme.INK)
            word = "lower" if diff < 0 else "higher" if diff > 0 else "the same"
            self._label(f"{abs(diff):.0f} points {word} than before the break" if diff else "No change", 18,
                        colour=theme.INK_2, pady=(8, 0))
        else:
            self._label("Stress could not be measured during the break (signal).", 18, colour=theme.INK_2)
        ctk.CTkButton(self.body, text="Back to work", width=220, height=52, corner_radius=10,
                      font=theme.font(17, "bold"), command=self.close).pack(pady=(36, 0))

    def respond(self, action):
        self.monitor.stress_break_response(action)
        self.close()

    def escape(self):
        if self.phase == "prompt":
            self.respond("dismiss")
        elif self.phase == "breathing":
            self.finish()
        else:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.phase == "breathing":          # closed from outside (e.g. session ended)
            self.monitor.stress_break_done()
        self.monitor.stress_screen_open = False
        self._unsub()
        if self._anim:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass
        self.destroy()

    # ── animation and live values ────────────────────────────────
    def _on_scores(self, snap):
        self.stress = snap.get("stress")
        if hasattr(self, "stress_lbl") and self.stress_lbl.winfo_exists():
            self.stress_lbl.configure(text=f"Stress now  {_num(self.stress)}")

    def _animate(self):
        """Circle grows for BREATH_IN_S (breathe in), shrinks for BREATH_OUT_S (breathe out)."""
        if self._closed or self.phase == "done":
            self._anim = None
            return
        if self.phase == "breathing":
            left = self.length_s - (time.monotonic() - self._t0)
            if left <= 0:
                self._anim = None
                self.finish()
                return
        t = (time.monotonic() - self._anim_t0) % (config.BREATH_IN_S + config.BREATH_OUT_S)
        if t < config.BREATH_IN_S:
            x, cue = 0.5 - 0.5 * math.cos(math.pi * t / config.BREATH_IN_S), "Breathe in"
        else:
            x, cue = 0.5 + 0.5 * math.cos(math.pi * (t - config.BREATH_IN_S) / config.BREATH_OUT_S), "Breathe out"
        try:
            c = self._size / 2
            ring = c - 3
            r = ring * (0.38 + 0.6 * x)
            self.canvas.delete("all")
            self.canvas.create_oval(c - ring, c - ring, c + ring, c + ring, outline=CIRCLE_SOFT, width=2)
            self.canvas.create_oval(c - r, c - r, c + r, c + r, fill=CIRCLE, outline="")
            if self.phase == "breathing":
                self.cue.configure(text=cue)
                secs = int(math.ceil(left))
                self.count.configure(text=f"{secs // 60}:{secs % 60:02d} left")
        except tk.TclError:                        # widgets replaced between frames
            pass
        self._anim = self.after(33, self._animate)

    def _sample(self):
        if self.phase != "breathing":
            return
        if is_valid(self.stress):
            self.history.append(self.stress)
        self._draw_spark()
        self.after(1000, self._sample)

    def _draw_spark(self):
        sp = self.spark
        sp.delete("all")
        w, h = 420, 70
        sp.create_line(0, h / 2, w, h / 2, fill=theme.AXIS, dash=(3, 4))      # 50 = your usual level
        pts = self.history[-int(self.length_s) - 1:]
        if len(pts) < 2:
            return
        n = max(len(pts) - 1, 1)
        span = max(int(self.length_s), n)
        coords = []
        for i, v in enumerate(pts):
            coords += [i * w / span, h - (max(0.0, min(100.0, v)) / 100) * h]
        sp.create_line(*coords, fill=theme.SERIES[1], width=2, smooth=True)
