"""Burnout Guard dialogs: privacy notice, privacy & data, questionnaires, end-of-day check-in, break room."""
import math
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import config, questionnaires as q, recovery
from . import theme

PRIVACY_TEXT = (
    "How Burnout Guard handles your data\n\n"
    "•  Everything stays on this computer, in the app's data folder. Nothing is uploaded, there is no "
    "account and no telemetry.\n"
    "•  Only you can see it. There is no manager or employer view, and the app never sends reports.\n"
    "•  Raw EEG is not saved unless you start the app with --record-eeg. The app keeps scores, "
    "break times and your check-in answers.\n"
    "•  Session recordings are deleted automatically after {days} days; you can export or delete "
    "everything at any time from Privacy & data.\n"
    "•  If this is a work laptop managed by your employer, its IT department may be able to read files "
    "on it. Use a personal device if that worries you.\n\n"
    "What it is, and what it is not\n\n"
    "•  It is a wellbeing aid: it suggests breaks, guides short recovery exercises and tracks how you "
    "say you feel over the weeks.\n"
    "•  It is not a medical device and cannot detect, diagnose or treat burnout or any illness. The EEG "
    "fatigue and tension signals are approximate and can be wrong.\n"
    "•  If you feel overwhelmed, please talk to a doctor, a counsellor or {helpline}."
)


class _Dialog(ctk.CTkToplevel):
    def __init__(self, parent, title, width=560):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=theme.PAGE)
        self.attributes("-topmost", True)
        self.resizable(False, True)
        self._width = width
        self.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        self.destroy()

    def label(self, parent, text, size=14, weight="normal", colour=None, wrap=None, **pack):
        lbl = ctk.CTkLabel(parent, text=text, font=theme.font(size, weight), text_color=colour or theme.INK,
                           justify="left", anchor="w", wraplength=wrap or self._width - 60)
        lbl.pack(**({"anchor": "w", "padx": 24} | pack))
        return lbl


def _btn(parent, text, command, kind="primary", width=150):
    styles = {"primary": {},
              "secondary": {"fg_color": theme.SURFACE, "hover_color": theme.RAISED, "border_width": 1,
                            "border_color": theme.BORDER, "text_color": theme.INK},
              "danger": {"fg_color": theme.CRITICAL, "hover_color": "#a82e2e"},
              "ghost": {"fg_color": "transparent", "hover_color": theme.RAISED, "text_color": theme.MUTED}}
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=36, corner_radius=8,
                         font=theme.font(14, "bold"), **styles[kind])


# ── privacy notice (first run) ────────────────────────────────────
class ConsentDialog(_Dialog):
    def __init__(self, parent, journal, on_done):
        super().__init__(parent, "Before you start", width=620)
        self.journal, self.on_done = journal, on_done
        box = ctk.CTkTextbox(self, width=580, height=400, font=theme.font(13), fg_color=theme.SURFACE,
                             wrap="word", border_width=0)
        box.insert("1.0", PRIVACY_TEXT.format(days=config.RETENTION_DAYS, helpline=config.HELPLINE))
        box.configure(state="disabled")
        box.pack(padx=20, pady=(20, 10))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 18))
        _btn(row, "I understand, continue", self.accept, width=200).pack(side="right")
        _btn(row, "Quit", self.decline, kind="ghost", width=90).pack(side="right", padx=8)

    def accept(self):
        self.journal.record_consent(True)
        self.destroy()
        self.on_done(True)

    def decline(self):
        self.destroy()
        self.on_done(False)

    close = decline


# ── privacy & data ────────────────────────────────────────────────
class PrivacyDialog(_Dialog):
    def __init__(self, parent, journal, on_change):
        super().__init__(parent, "Privacy & data", width=560)
        self.journal, self.on_change = journal, on_change
        s = journal.settings()
        self.label(self, "Your data", 17, "bold", pady=(18, 4))
        self.label(self, f"Stored only here:\n{os.path.abspath(journal.data_dir)}", 12, colour=theme.MUTED)
        n = len(journal.entries())
        sessions = os.path.join(journal.data_dir, "sessions")
        n_sess = len(os.listdir(sessions)) if os.path.isdir(sessions) else 0
        self.label(self, f"{n} journal entries, {n_sess} session recordings.", 13, pady=(6, 12))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=4)
        _btn(row, "Open folder", self.open_folder, kind="secondary", width=130).pack(side="left")
        _btn(row, "Export (zip)", self.export, kind="secondary", width=130).pack(side="left", padx=8)
        _btn(row, "Delete everything", self.delete, kind="danger", width=170).pack(side="left")
        self.label(self, "Settings", 17, "bold", pady=(20, 4))
        self.eye = ctk.BooleanVar(value=s["eye_rest"])
        ctk.CTkSwitch(self, text="20-20-20 eye-rest reminder every 20 minutes", variable=self.eye,
                      font=theme.font(13), command=self._save).pack(anchor="w", padx=24, pady=4)
        self.keep = ctk.StringVar(value=str(s["retention_days"]))
        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(r2, text="Delete session recordings after (days)", font=theme.font(13)).pack(side="left")
        ctk.CTkOptionMenu(r2, values=["30", "90", "180", "365"], variable=self.keep, width=90,
                          command=lambda _v: self._save()).pack(side="left", padx=10)
        self.label(self, "Journal summaries (break counts, check-in answers) are kept until you delete them.",
                   12, colour=theme.MUTED, pady=(4, 18))
        _btn(self, "Close", self.close, width=110).pack(anchor="e", padx=24, pady=(0, 18))

    def _save(self):
        self.journal.save_settings(eye_rest=bool(self.eye.get()), retention_days=int(self.keep.get()))
        self.on_change()

    def open_folder(self):
        if hasattr(os, "startfile"):
            os.startfile(os.path.abspath(self.journal.data_dir))

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".zip",
                                            initialfile=f"burnout_guard_export_{time.strftime('%Y%m%d')}.zip")
        if path:
            self.journal.export_zip(path)
            messagebox.showinfo("Export", f"Saved {os.path.basename(path)}", parent=self)

    def delete(self):
        if messagebox.askyesno("Delete everything",
                               "Delete all journal entries, check-ins and session recordings?\n"
                               "This cannot be undone.", parent=self):
            self.journal.delete_all()
            self.destroy()
            self.on_change(deleted=True)


# ── questionnaire ─────────────────────────────────────────────────
class QuestionnaireDialog(_Dialog):
    def __init__(self, parent, journal, instrument, on_done):
        spec = q.INSTRUMENTS[instrument]
        super().__init__(parent, spec["title"], width=640)
        self.journal, self.instrument, self.on_done = journal, instrument, on_done
        self.label(self, spec["title"], 17, "bold", pady=(18, 2))
        self.label(self, spec["intro"], 13, colour=theme.INK_2, pady=(0, 8))
        height = min(520, 92 * len(spec["items"]))
        body = ctk.CTkScrollableFrame(self, width=590, height=height, fg_color=theme.SURFACE, corner_radius=10)
        body.pack(padx=20, pady=4, fill="both", expand=True)
        self.vars = []
        for i, (text, options) in enumerate(spec["items"]):
            ctk.CTkLabel(body, text=f"{i + 1}.  {text}", font=theme.font(13, "bold"), text_color=theme.INK,
                         anchor="w", justify="left", wraplength=560).pack(anchor="w", padx=12, pady=(10, 2))
            var = ctk.IntVar(value=-1)
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(anchor="w", padx=12)
            for k, opt in enumerate(options):
                ctk.CTkRadioButton(row, text=opt, value=k, variable=var, font=theme.font(12),
                                   command=self._check, radiobutton_width=16, radiobutton_height=16
                                   ).pack(side="left", padx=(0, 10))
            self.vars.append(var)
        self.label(self, spec["source"], 10, colour=theme.MUTED, pady=(6, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=12)
        self.submit_btn = _btn(row, "Submit", self.submit, width=120)
        self.submit_btn.configure(state="disabled")
        self.submit_btn.pack(side="right")
        _btn(row, "Not now", self.close, kind="ghost", width=90).pack(side="right", padx=8)
        self.result_lbl = None

    def _check(self):
        self.submit_btn.configure(state="normal" if all(v.get() >= 0 for v in self.vars) else "disabled")

    def answer_all(self, choice):
        """Self-test helper: answer every item with option `choice`."""
        for v in self.vars:
            v.set(choice)
        self._check()

    def submit(self):
        answers = [v.get() for v in self.vars]
        result = q.score(self.instrument, answers)
        self.journal.add("questionnaire", instrument=self.instrument, answers=answers, score=result["score"],
                         zone=result["zone"], detail=result["detail"])
        self.destroy()
        self.on_done(self.instrument, result)


# ── end-of-day check-in ───────────────────────────────────────────
class DayCheckinDialog(_Dialog):
    def __init__(self, parent, journal, on_done):
        super().__init__(parent, "End-of-day check-in", width=520)
        self.journal, self.on_done = journal, on_done
        self.label(self, "How was today?", 17, "bold", pady=(18, 2))
        self.label(self, "Three quick questions. These are the app's own items, not a validated scale.",
                   12, colour=theme.MUTED, pady=(0, 10))
        self.energy = self._slider("Energy left right now", "drained", "full of energy")
        self.strain = self._slider("How demanding was today?", "easy", "far too much")
        self.breaks_ok = ctk.StringVar(value="")
        self.label(self, "Did you take the breaks you needed?", 13, "bold", pady=(14, 4))
        ctk.CTkSegmentedButton(self, values=["Yes", "Partly", "No"], variable=self.breaks_ok,
                               font=theme.font(13)).pack(anchor="w", padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=16)
        _btn(row, "Save", self.save, width=110).pack(side="right")
        _btn(row, "Not now", self.close, kind="ghost", width=90).pack(side="right", padx=8)

    def _slider(self, title, lo, hi):
        self.label(self, title, 13, "bold", pady=(8, 2))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24)
        ctk.CTkLabel(row, text=lo, font=theme.font(11), text_color=theme.MUTED).pack(side="left")
        var = ctk.IntVar(value=5)
        val = ctk.CTkLabel(row, text="5", font=theme.font(13, "bold"), width=24)
        ctk.CTkSlider(row, from_=0, to=10, number_of_steps=10, variable=var, width=300,
                      command=lambda v: val.configure(text=f"{int(v)}")).pack(side="left", padx=8)
        ctk.CTkLabel(row, text=hi, font=theme.font(11), text_color=theme.MUTED).pack(side="left")
        val.pack(side="left", padx=8)
        return var

    def save(self):
        self.journal.add("day_checkin", energy=int(self.energy.get()), strain=int(self.strain.get()),
                         breaks_ok=self.breaks_ok.get() or None)
        self.destroy()
        self.on_done()


# ── break room ────────────────────────────────────────────────────
class BreakDialog(_Dialog):
    """Opened when a break starts. Offers exercises, runs a pacer, asks how refreshed you feel,
    shows the relaxation signal, and ends the break with 'Back to work'."""

    def __init__(self, parent, monitor, suggestion=None, beep=None, done_today=(), on_close=None):
        super().__init__(parent, "Break", width=620)
        self.monitor, self.beep = monitor, beep or (lambda kind: None)
        self.on_close = on_close
        self.geometry("660x650")
        self.suggestion = suggestion or {"kind": "manual", "minutes": config.MICRO_BREAK_MIN, "reason": ""}
        self.started = time.monotonic()
        self.ex_id, self.ex_t0, self._job = None, None, None
        self.choice = ctk.StringVar(value=recovery.suggest(self.suggestion["kind"], self.suggestion["minutes"],
                                                           done_today))
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(18, 0))
        ctk.CTkLabel(top, text=f"Break  ·  about {self.suggestion['minutes']} min", font=theme.font(18, "bold"),
                     text_color=theme.INK).pack(side="left")
        self.clock_lbl = ctk.CTkLabel(top, text="0:00", font=theme.font(18, "bold"), text_color=theme.INK_2)
        self.clock_lbl.pack(side="right")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=20, pady=10)
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(0, 16))
        self.back_btn = _btn(bottom, "Back to work", self.back_to_work, width=150)
        self.back_btn.pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.back_to_work)
        self.show_menu()
        self._tick()

    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    # menu
    def show_menu(self):
        self._clear()
        ctk.CTkLabel(self.body, text="Pick something to do, or just rest away from the screen.",
                     font=theme.font(13), text_color=theme.INK_2).pack(anchor="w", pady=(0, 6))
        for ex_id in recovery.ORDER:
            ex = recovery.EXERCISES[ex_id]
            row = ctk.CTkFrame(self.body, fg_color=theme.SURFACE, corner_radius=8)
            row.pack(fill="x", pady=3)
            ctk.CTkRadioButton(row, text=f"{ex['name']}  ·  {ex['minutes']} min", value=ex_id,
                               variable=self.choice, font=theme.font(13, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(row, text=ex["steps"], font=theme.font(11), text_color=theme.MUTED, justify="left",
                         wraplength=500, anchor="w").pack(anchor="w", padx=40, pady=(0, 8))
        _btn(self.body, "Start exercise", lambda: self.start_exercise(self.choice.get()), width=160
             ).pack(anchor="e", pady=(8, 0))

    # exercise
    def start_exercise(self, ex_id):
        self.ex_id, self.ex_t0 = ex_id, time.monotonic()
        self.monitor.start_exercise(ex_id)
        ex = recovery.EXERCISES[ex_id]
        self._clear()
        ctk.CTkLabel(self.body, text=ex["name"], font=theme.font(17, "bold"), text_color=theme.INK).pack(pady=(4, 0))
        self.canvas = tk.Canvas(self.body, width=300, height=300, bg=theme.PAGE, highlightthickness=0)
        self.canvas.pack(pady=6)
        self.phase_lbl = ctk.CTkLabel(self.body, text="", font=theme.font(16, "bold"), text_color=theme.INK,
                                      wraplength=520)
        self.phase_lbl.pack()
        self.left_lbl = ctk.CTkLabel(self.body, text="", font=theme.font(12), text_color=theme.MUTED)
        self.left_lbl.pack(pady=(2, 6))
        ctk.CTkLabel(self.body, text=ex["evidence"], font=theme.font(10), text_color=theme.MUTED,
                     wraplength=540).pack()
        _btn(self.body, "Finish", self.finish_exercise, kind="secondary", width=110).pack(pady=(10, 0))
        self.beep("start")
        self._animate()

    def _animate(self):
        if self.ex_id is None:
            return
        ex = recovery.EXERCISES[self.ex_id]
        t = time.monotonic() - self.ex_t0
        total = ex["minutes"] * 60
        if t >= total:
            self.finish_exercise()
            return
        _i, label, frac, left = recovery.phase_at(self.ex_id, t)
        low = label.lower()
        if low.startswith("top up"):
            r = 130 + 10 * frac                     # the short second sniff of a cyclic sigh
        elif "in" in low.split()[:3]:
            r = 50 + 80 * frac                      # grow while breathing in
        elif "out" in low:
            r = 130 - 80 * frac                     # shrink while breathing out
        elif "hold" in low:
            r = self._last_r if hasattr(self, "_last_r") else 95
        else:
            r = 95
        self._last_r = r
        c = self.canvas
        c.delete("all")
        c.create_oval(150 - 142, 150 - 142, 150 + 142, 150 + 142, outline=theme.BORDER, width=2)
        c.create_oval(150 - r, 150 - r, 150 + r, 150 + r, fill=theme.SERIES[0], outline="")
        c.create_text(150, 150, text=f"{math.ceil(left)}", fill=theme.INK, font=(theme.FONT, 28, "bold"))
        self.phase_lbl.configure(text=label)
        rem = int(total - t)
        self.left_lbl.configure(text=f"{rem // 60}:{rem % 60:02d} left")
        self._job = self.after(50, self._animate)

    def finish_exercise(self):
        if self.ex_id is None:
            return
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.beep("done")
        self._clear()
        ctk.CTkLabel(self.body, text="How refreshed do you feel?", font=theme.font(17, "bold"),
                     text_color=theme.INK).pack(pady=(30, 12))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack()
        for k, text in recovery.REFRESH_LABELS.items():
            _btn(row, f"{k}\n{text}", lambda k=k: self.rate(k), kind="secondary", width=100).pack(side="left", padx=4)

    def rate(self, rating):
        ex = recovery.EXERCISES[self.ex_id]
        _change, text = self.monitor.finish_exercise(rating=rating, eeg_comparable=ex["eeg"])
        self.ex_id = None
        self._clear()
        ctk.CTkLabel(self.body, text=f"Thanks. You rated it {rating}/5.", font=theme.font(16, "bold"),
                     text_color=theme.INK).pack(pady=(30, 8))
        ctk.CTkLabel(self.body, text=text, font=theme.font(13), text_color=theme.INK_2, wraplength=540).pack()
        _btn(self.body, "Another exercise", self.show_menu, kind="secondary", width=160).pack(pady=16)

    # clock and end
    def _tick(self):
        if not self.winfo_exists():
            return
        e = int(time.monotonic() - self.started)
        self.clock_lbl.configure(text=f"{e // 60}:{e % 60:02d}")
        self.after(1000, self._tick)

    def back_to_work(self):
        if self.ex_id is not None:
            if self._job:
                self.after_cancel(self._job)
            self.monitor.finish_exercise(rating=None, eeg_comparable=recovery.EXERCISES[self.ex_id]["eeg"])
            self.ex_id = None
        self.destroy()
        if self.on_close:
            self.on_close()
