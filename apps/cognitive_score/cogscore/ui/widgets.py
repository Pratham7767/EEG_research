"""Reusable widgets: metric cards, meters, electrode tiles, live charts, KSS prompt."""
import math
from collections import deque

import customtkinter as ctk
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator, MultipleLocator

from .. import config
from ..rules import KSS_LABELS
from . import theme

BAND_LABELS = {"delta": "Delta\n1–4 Hz", "theta": "Theta\n4–8 Hz", "alpha": "Alpha\n8–13 Hz",
               "beta": "Beta\n13–30 Hz", "gamma": "Gamma\n30–45 Hz"}


def legend_row(parent, items):
    """Legend as small colour chips + labels (keeps the plot area free)."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    for label, colour in items:
        ctk.CTkFrame(row, width=14, height=3, corner_radius=1, fg_color=colour).pack(side="left", padx=(12, 6))
        ctk.CTkLabel(row, text=label, font=theme.font(12), text_color=theme.INK_2).pack(side="left")
    return row


def _mmss(minutes, _pos=None):
    total = int(round(minutes * 60))
    return f"{total // 60}:{total % 60:02d}"


def valid(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def fmt_int(x):
    return f"{x:.0f}" if valid(x) else "—"


class Card(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        kw.setdefault("fg_color", theme.SURFACE)
        kw.setdefault("corner_radius", 12)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", theme.BORDER)
        super().__init__(parent, **kw)


class HeroMetric(Card):
    """Large 0-100 value, level word and a meter in the metric's series colour."""

    def __init__(self, parent, title, colour):
        super().__init__(parent)
        self.colour = colour
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkFrame(top, width=10, height=10, corner_radius=5, fg_color=colour).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(top, text=title, font=theme.font(15, "bold"), text_color=theme.INK_2).pack(side="left")
        self.flag = ctk.CTkLabel(top, text="", font=theme.font(12, "bold"), text_color=theme.PAGE,
                                 fg_color=theme.WARNING, corner_radius=6)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20)
        self.value = ctk.CTkLabel(row, text="—", font=theme.font(54, "bold"), text_color=theme.INK)
        self.value.pack(side="left")
        self.level = ctk.CTkLabel(row, text="", font=theme.font(16), text_color=theme.INK_2)
        self.level.pack(side="left", padx=(12, 0), pady=(18, 0))
        self.meter = ctk.CTkProgressBar(self, height=8, progress_color=colour, fg_color=theme.RAISED)
        self.meter.set(0)
        self.meter.pack(fill="x", padx=20, pady=(4, 18))

    def set(self, value, level_text, dim=False, flag=None):
        if valid(value):
            self.value.configure(text=f"{value:.0f}", text_color=theme.MUTED if dim else theme.INK)
            self.level.configure(text=level_text)
            self.meter.set(max(0.0, min(1.0, value / 100)))
        else:
            self.value.configure(text="—", text_color=theme.MUTED)
            self.level.configure(text=level_text)
            self.meter.set(0)
        if flag:
            self.flag.configure(text=f"  {flag}  ")
            self.flag.pack(side="right")
            self.configure(border_color=theme.WARNING, border_width=2)
        else:
            self.flag.pack_forget()
            self.configure(border_color=theme.BORDER, border_width=1)


class SmallMeter(ctk.CTkFrame):
    """Label · value · thin neutral meter (secondary metrics)."""

    def __init__(self, parent, title, suffix=""):
        super().__init__(parent, fg_color="transparent")
        self.suffix = suffix
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=title, font=theme.font(13), text_color=theme.MUTED).pack(side="left")
        self.value = ctk.CTkLabel(row, text="—", font=theme.font(13, "bold"), text_color=theme.INK)
        self.value.pack(side="right")
        self.meter = ctk.CTkProgressBar(self, height=5, progress_color=theme.INK_2, fg_color=theme.RAISED)
        self.meter.set(0)
        self.meter.pack(fill="x", pady=(4, 0))

    def set(self, value, text=None, fraction=None):
        self.value.configure(text=text if text is not None else (fmt_int(value) + self.suffix if valid(value) else "—"))
        f = fraction if fraction is not None else (value / 100 if valid(value) else 0)
        self.meter.set(max(0.0, min(1.0, f)))


class ElectrodeTile(Card):
    """Electrode name, resistance and a status label (colour never carries meaning alone)."""

    def __init__(self, parent, name):
        super().__init__(parent, border_width=2)
        ctk.CTkLabel(self, text=name, font=theme.font(15, "bold"), text_color=theme.INK).pack(padx=22, pady=(12, 0))
        self.ohms = ctk.CTkLabel(self, text="—", font=theme.font(22), text_color=theme.INK)
        self.ohms.pack(padx=22)
        self.status = ctk.CTkLabel(self, text="", font=theme.font(12, "bold"), text_color=theme.MUTED)
        self.status.pack(padx=22, pady=(0, 12))

    def set(self, ohms, grade):
        colour = theme.GRADE_COLOURS[grade]
        kohm = ohms / 1000 if valid(ohms) else math.inf
        self.ohms.configure(text=f"{kohm:,.0f} kΩ" if kohm < 1e5 else "open")
        icon = {"good": "●", "average": "▲", "bad": "✕"}[grade]
        self.status.configure(text=f"{icon} {theme.GRADE_LABELS[grade]}", text_color=colour)
        self.configure(border_color=colour)


class _Plot:
    def __init__(self, parent, figsize, rows=1):
        theme.style_matplotlib()
        self.fig = Figure(figsize=figsize, dpi=100)
        self.axes = [self.fig.add_subplot(rows, 1, i + 1) for i in range(rows)]
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(bg=theme.SURFACE, highlightthickness=0)
        self.widget.bind("<Configure>", self._blank_photo, add="+")

    def _blank_photo(self, _event=None):
        """Matplotlib renders int(inches × dpi) rows, which can be one row fewer than the Tk photo after a
        resize (4.52 in × 100 → 451 px); that last row would keep a strip of the previous, larger image."""
        photo = getattr(self.canvas, "_tkphoto", None)
        if photo is not None:
            photo.blank()

    def draw(self):
        self.canvas.draw_idle()


class EEGPlot(_Plot):
    """Last `seconds` of processed EEG, one trace per channel, each auto-scaled and offset."""

    def __init__(self, parent, seconds=5.0):
        super().__init__(parent, (6.0, 1.6))
        self.seconds = seconds
        self.buffers, self.lines, self.names = [], [], []
        self.fig.subplots_adjust(left=0.08, right=0.99, top=0.96, bottom=0.14)

    def setup(self, names, sample_rate):
        ax = self.axes[0]
        ax.clear()
        self.names = list(names)
        n = max(2, int(self.seconds * (sample_rate or 250.0)))
        self.x = np.linspace(-self.seconds, 0, n)
        self.buffers = [deque([np.nan] * n, maxlen=n) for _ in names]
        self.lines = [ax.plot(self.x, np.full(n, np.nan), color=theme.SERIES[i % 4], linewidth=1.1)[0]
                      for i in range(len(names))]
        ax.set_xlim(-self.seconds, 0)
        ax.set_ylim(-0.7, len(names) - 0.3)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(list(reversed(self.names)))
        ax.grid(axis="y", visible=False)
        ax.set_xticks([-5, -4, -3, -2, -1, 0])
        ax.set_xticklabels(["-5 s", "", "", "", "", "now"])

    def push(self, processed):
        for row in processed:
            for i, buf in enumerate(self.buffers):
                if i < len(row):
                    buf.append(row[i])

    def refresh(self):
        n_ch = len(self.buffers)
        for i, (buf, line) in enumerate(zip(self.buffers, self.lines)):
            y = np.array(buf, dtype=float)
            finite = y[np.isfinite(y)]
            if finite.size < 10:
                continue
            centre = np.median(finite)
            spread = np.percentile(np.abs(finite - centre), 98) or 1.0
            line.set_ydata((y - centre) / (2.4 * spread) + (n_ch - 1 - i))
        self.draw()


class TimelinePlot(_Plot):
    """Attention, cognitive load and stress on one 0-100 axis (same scale, so one axis is correct).
    Stress episodes and breaks are shaded; the dashed line at 50 is the personal baseline.
    The legend lives in the card header (see `legend_items`)."""

    KEYS = ("attention", "cognitive_load", "stress")
    LABELS = {"attention": "Attention", "cognitive_load": "Cognitive load", "stress": "Stress"}

    @classmethod
    def legend_items(cls):
        return [(cls.LABELS[k], theme.METRIC_COLOURS[k]) for k in cls.KEYS] + [("Stress episode", theme.WARNING)]

    def __init__(self, parent, figsize=(6.4, 2.6)):
        super().__init__(parent, figsize)
        ax = self.axes[0]
        self.lines = {k: ax.plot([], [], color=theme.METRIC_COLOURS[k])[0] for k in self.KEYS}
        ax.axhline(50, color=theme.MUTED, linewidth=1, linestyle=(0, (4, 4)))
        ax.set_ylim(0, 100)
        ax.set_yticks([25, 50, 75, 100])          # no 0 tick: it collided with the 0:00 x tick
        ax.xaxis.set_major_formatter(FuncFormatter(_mmss))
        self.fig.subplots_adjust(left=0.05, right=0.99, top=0.97, bottom=0.12)
        self._spans = []

    def update_from(self, trend, episodes=(), breaks=(), now_s=None, window_s=None):
        ax = self.axes[0]
        for span in self._spans:
            span.remove()
        self._spans = []
        end_s = now_s if now_s else (trend[-1][0] if trend else 60.0)
        start_s = max(0.0, end_s - window_s) if window_s else 0.0
        trend = [p for p in trend if p[0] >= start_s]
        if trend:
            t = np.array([e for e, _ in trend]) / 60.0
            for k, line in self.lines.items():
                line.set_data(t, np.array([v[k] for _, v in trend], dtype=float))
        span_min = max(1.0, (end_s - start_s) / 60)
        ax.set_xlim(start_s / 60, start_s / 60 + span_min)
        step = next(x for x in (0.25, 0.5, 1, 2, 5, 10, 15, 30, 60) if span_min / x <= 8)
        ax.xaxis.set_major_locator(MultipleLocator(step))
        for start, stop in episodes:
            stop = stop if stop is not None else end_s
            self._spans.append(ax.axvspan(start / 60, stop / 60, color=theme.WARNING, alpha=0.14, linewidth=0))
        for start, stop in breaks:
            stop = stop if stop is not None else end_s
            self._spans.append(ax.axvspan(start / 60, stop / 60, color=theme.INK_2, alpha=0.07, linewidth=0))
        self.draw()


class BandPlot(_Plot):
    """Five bars: % change of each band's power vs the rest baseline."""

    def __init__(self, parent, figsize=(4.2, 2.6)):
        super().__init__(parent, figsize)
        self.names = list(config.RAW_BANDS)
        ax = self.axes[0]
        self.x = np.arange(len(self.names))
        self.bars = ax.bar(self.x, np.zeros(len(self.names)), width=0.56, color=theme.BAND_COLOUR)
        self.zero = ax.axhline(0, color=theme.AXIS, linewidth=1)
        ax.set_xticks(self.x)
        ax.set_xticklabels([BAND_LABELS[n] for n in self.names], fontsize=9, color=theme.INK_2)
        ax.set_ylabel("% change vs rest")
        ax.grid(axis="x", visible=False)
        self.value_labels = [ax.text(i, 0, "", ha="center", va="bottom", fontsize=9, color=theme.INK_2)
                             for i in self.x]
        self.note = ax.text(0.5, 0.55, "", transform=ax.transAxes, ha="center", va="center", color=theme.MUTED, fontsize=10)
        self.fig.subplots_adjust(left=0.14, right=0.98, top=0.93, bottom=0.2)

    def update_from(self, bands_change, ready):
        ax = self.axes[0]
        values = [bands_change.get(n, np.nan) for n in self.names] if ready else [np.nan] * len(self.names)
        self.note.set_text("" if ready else "Collecting baseline…")
        finite = [v for v in values if valid(v)]
        span = max([60.0] + [abs(v) * 1.25 for v in finite])
        ax.set_ylim(-min(100.0, span), span)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        for bar, label, v in zip(self.bars, self.value_labels, values):
            v_plot = v if valid(v) else 0.0
            bar.set_height(v_plot)
            label.set_position((bar.get_x() + bar.get_width() / 2, v_plot))
            label.set_va("bottom" if v_plot >= 0 else "top")
            label.set_text(("0%" if round(v) == 0 else f"{v:+.0f}%") if valid(v) else "")   # never "-0%" / "+0%"
        self.draw()


class KSSDialog(ctk.CTkToplevel):
    """Non-blocking Karolinska Sleepiness Scale prompt (1-9)."""

    def __init__(self, parent, on_answer, on_skip):
        super().__init__(parent)
        self.title("Check-in")
        self.configure(fg_color=theme.PAGE)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self._on_answer, self._on_skip = on_answer, on_skip
        ctk.CTkLabel(self, text="How sleepy do you feel?", font=theme.font(17, "bold")).pack(padx=24, pady=(18, 10))
        for score, label in KSS_LABELS.items():
            ctk.CTkButton(self, text=f"{score}   {label}", anchor="w", width=340, height=32, font=theme.font(13),
                          fg_color=theme.SURFACE, hover_color=theme.RAISED, border_width=1, border_color=theme.BORDER,
                          command=lambda s=score: self._answer(s)).pack(padx=24, pady=2)
        ctk.CTkButton(self, text="Skip", width=100, fg_color="transparent", hover_color=theme.RAISED,
                      text_color=theme.MUTED, command=self._skip).pack(pady=(10, 18))
        self.protocol("WM_DELETE_WINDOW", self._skip)

    def _answer(self, score):
        self._on_answer(score)
        self.destroy()

    def _skip(self):
        self._on_skip()
        self.destroy()
