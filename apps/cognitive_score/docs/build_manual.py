"""Build docs/manual.html: the user manual, with figures computed from a recorded session.

    python docs/build_manual.py                        # latest real session + docs/screens
    python docs/build_manual.py --session sessions/2026-09-30_135243

Screens come from the self-test:  python app.py --selftest --selftest-live 45 --screenshots docs/screens
The figures replay the recorded session through the app's own rules (cogscore.metrics / rules / config),
so the manual always describes what the current version would show for that data.
"""
import argparse
import base64
import csv
import glob
import html
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matplotlib                                                  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402

from cogscore import config                                        # noqa: E402
from cogscore.metrics import RollingMedian, score_vs_baseline      # noqa: E402
from cogscore.rules import BreakRule, StressEpisodes               # noqa: E402

# ── figure style (light page; same series colours as the app, validated on #fcfcfb) ──
INK, INK_2, MUTED, GRID, SURFACE = "#1f1f1d", "#4a4a46", "#8a8a86", "#e6e6e2", "#fcfcfb"
C = {"attention": "#3987e5", "stress": "#d95926", "cognitive_load": "#199e70", "band": "#9085e9",
     "old": "#a3a39e", "e1": "#3987e5", "e2": "#d95926", "e3": "#199e70", "e4": "#c98500",
     "good": "#0ca30c", "warn": "#c98500"}
BANDS = list(config.RAW_BANDS)
BAND_NAMES = {"delta": "Delta\n1–4 Hz", "theta": "Theta\n4–8 Hz", "alpha": "Alpha\n8–13 Hz",
              "beta": "Beta\n13–30 Hz", "gamma": "Gamma\n30–45 Hz"}

plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "legend.frameon": False, "lines.linewidth": 2,
})


def png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def screen(path, width=1400):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def rows(path, name):
    with open(os.path.join(path, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ── load and replay ────────────────────────────────────────────────
class Session:
    def __init__(self, path):
        self.path = path
        with open(os.path.join(path, "session.json"), encoding="utf-8") as fh:
            self.meta = json.load(fh)
        ev = rows(path, "events.csv")
        self.events = ev
        t_of = {e["kind"]: float(e["unix_time"]) for e in reversed(ev)}
        self.t_connect = t_of["connected"]
        self.t_cal = t_of.get("calibrated")
        self.t_live = t_of["live_start"]
        self.t_end = t_of.get("session_end", self.t_live + self.meta["summary"]["live_duration_s"])
        self.live_s = self.t_end - self.t_live
        self.breaks = [b for b in self.meta["summary"]["breaks"] if b[1] is not None]

        ind = rows(path, "indices.csv")
        self.ind_t = np.array([num(r["unix_time"]) for r in ind]) - self.t_live
        self.arousal = np.array([num(r["arousal"]) for r in ind])
        self.fatigue = np.array([num(r["fatigue"]) for r in ind])

        sc = rows(path, "scores.csv")
        self.sc_t = np.array([num(r["elapsed_s"]) for r in sc])
        self.recorded = {k: np.array([num(r[k]) for r in sc]) for k in ("attention", "cognitive_load", "stress",
                                                                         "relaxation", "fatigue")}
        bd = rows(path, "bands.csv")
        self.bd_t = np.array([num(r["unix_time"]) for r in bd]) - self.t_live
        self.bd_ok = np.array([r["rejected"] == "" for r in bd])
        self.bd_abs = {b: np.array([num(r[f"{b}_uv2"]) for r in bd]) for b in BANDS}
        res = rows(path, "resistances.csv")
        self.res = {}
        for r in res:
            self.res.setdefault(r["electrode"], []).append((num(r["unix_time"]) - self.t_connect, num(r["ohms"])))

    def in_break(self, t):
        return any(a <= t < b for a, b in self.breaks)

    def replay(self):
        """Stress / fatigue exactly as the current Monitor computes them (1 Hz output)."""
        ref_s = config.WORK_REF_S
        ref_vals = {"arousal": [], "fatigue": []}
        ref = None
        sm_s, sm_f = RollingMedian(config.SCORE_SMOOTHING_S), RollingMedian(config.FATIGUE_SMOOTHING_S)
        ep = StressEpisodes()
        rule = BreakRule(0.0)
        out_t, out_s, out_f, prompts = [], [], [], []
        last, break_state = -1.0, False
        self.ref_ready_at = None
        for t, a, f in zip(self.ind_t, self.arousal, self.fatigue):
            if t < 0:
                continue
            brk = self.in_break(t)
            if brk != break_state:
                (rule.start_break if brk else rule.end_break)(t)
                if brk and ep.active:
                    ep.close(t)
                break_state = brk
            work = t - sum(min(t, b) - a0 for a0, b in self.breaks if a0 < t)
            if ref is None and not brk:
                for k, v in (("arousal", a), ("fatigue", f)):
                    if np.isfinite(v) and v > 0:
                        ref_vals[k].append(v)
                if work >= ref_s and len(ref_vals["arousal"]) >= config.OWN_BASELINE_MIN_SAMPLES:
                    ref = {k: float(np.median(v)) for k, v in ref_vals.items()}
                    self.ref_ready_at = t
            if ref is not None:
                sm_s.add(t, score_vs_baseline(a, ref["arousal"]))
                sm_f.add(t, score_vs_baseline(f, ref["fatigue"]))
            if t - last >= 1.0:
                last = t
                s, fat = sm_s.value(t), sm_f.value(t)
                out_t.append(t)
                out_s.append(s)
                out_f.append(fat)
                ep.update(t, None if brk else s)
                reason = rule.update(t, fat)
                if reason:
                    prompts.append((t, reason))
        ep.close(self.live_s)
        self.ref = ref
        self.new_t, self.new_stress, self.new_fatigue = np.array(out_t), np.array(out_s), np.array(out_f)
        self.new_episodes, self.prompts = ep.episodes, prompts
        # time until the 50-min prompt, given the breaks actually taken
        counted = [b for a, b in self.breaks if b - a >= config.MIN_BREAK_S]
        self.next_prompt_min = ((counted[-1] if counted else 0.0) + config.WORK_BLOCK_S) / 60

    def band_change(self):
        rest_from = (self.t_cal - self.t_live) if self.t_cal else -40
        rest = self.bd_ok & (self.bd_t >= rest_from) & (self.bd_t < 0)
        live = self.bd_ok & (self.bd_t >= 0) & ~np.array([self.in_break(t) for t in self.bd_t])
        return {b: 100 * (np.median(self.bd_abs[b][live]) / np.median(self.bd_abs[b][rest]) - 1) for b in BANDS}


# ── figures ────────────────────────────────────────────────────────
def fig_contact(s):
    fig, ax = plt.subplots(figsize=(8, 3.0))
    cols = [C["e1"], C["e2"], C["e3"], C["e4"]]
    for (name, pts), col in zip(sorted(s.res.items()), cols):
        t = np.array([p[0] for p in pts]) / 60
        v = np.array([p[1] for p in pts]) / 1e3
        ax.plot(t, v, color=col, label=name, linewidth=1.8)
    ax.axhline(config.RES_GOOD_OHM / 1e3, color=C["good"], linestyle="--", linewidth=1)
    ax.text(0.02, config.RES_GOOD_OHM / 1e3 + 8, "Good below this line (500 kΩ)", color=INK_2, fontsize=9)
    for x, label, y in ((s.t_cal, "Calibration done", 590), (s.t_live, "Session starts", 545)):
        if x:
            ax.axvline((x - s.t_connect) / 60, color=MUTED, linewidth=1, linestyle=":")
            ax.text((x - s.t_connect) / 60 + 0.05, y, label, color=INK_2, fontsize=9, va="center")
    ax.set_ylim(0, 620)
    ax.set_xlabel("Minutes since connecting")
    ax.set_ylabel("Electrode resistance (kΩ)")
    ax.legend(ncol=4, loc="upper right", bbox_to_anchor=(1, 1.18), fontsize=9)
    return png(fig)


def fig_scores(s):
    fig, ax = plt.subplots(figsize=(8, 3.3))
    m = s.sc_t / 60
    ax.plot(m, s.recorded["attention"], color=C["attention"], label="Attention")
    ax.plot(m, s.recorded["cognitive_load"], color=C["cognitive_load"], label="Cognitive load")
    ax.plot(s.new_t / 60, s.new_stress, color=C["stress"], label="Stress")
    ref_end = (s.ref_ready_at or config.WORK_REF_S) / 60
    ax.axvspan(0, ref_end, color=GRID, alpha=0.6, linewidth=0)
    ax.text(ref_end / 2, 4, "Stress: learning\nyour working level", ha="center", va="bottom", fontsize=8.5, color=INK_2)
    ax.axhline(50, color=MUTED, linestyle="--", linewidth=1)
    ax.axhline(config.STRESS_EPISODE_ON, color=C["stress"], linestyle=":", linewidth=1)
    for y, text in ((config.STRESS_EPISODE_ON, "stress episode\nthreshold"), (50, "reference")):
        ax.annotate(text, xy=(1.0, y), xycoords=("axes fraction", "data"), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=INK_2)
    for a, b in s.breaks:
        ax.axvspan(a / 60, b / 60, color=MUTED, alpha=0.35, linewidth=0)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlim(0, s.live_s / 60)
    ax.set_xlabel("Minutes into the session")
    ax.set_ylabel("Score (0–100)")
    ax.legend(ncol=3, loc="upper right", bbox_to_anchor=(1, 1.16), fontsize=9)
    return png(fig)


def fig_stress_fix(s):
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.plot(s.sc_t / 60, s.recorded["stress"], color=C["old"], label="Before the fix (compared with eyes-open rest)")
    ax.plot(s.new_t / 60, s.new_stress, color=C["stress"], label="Now (compared with your first 2 minutes of work)")
    for a, b in s.meta["summary"]["stress_episodes"]:
        ax.axvspan(a / 60, (b if b is not None else s.live_s) / 60, color=C["old"], alpha=0.18, linewidth=0)
    ax.axhline(50, color=MUTED, linestyle="--", linewidth=1)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlim(0, s.live_s / 60)
    ax.set_xlabel("Minutes into the session (shaded: the old version's 'stress episode')")
    ax.set_ylabel("Stress (0–100)")
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.22), fontsize=9)
    return png(fig)


def fig_bands(s, new, old):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    x = np.arange(len(BANDS))
    w = 0.36
    ov = [old.get(b, np.nan) for b in BANDS]
    nv = [new[b] for b in BANDS]
    ax.bar(x - w / 2 - 0.01, ov, width=w, color=C["old"], label="Before the fix (change in share of power)")
    ax.bar(x + w / 2 + 0.01, nv, width=w, color=C["band"], label="Now (change in each band's own power)")
    for xi, v in zip(x + w / 2 + 0.01, nv):
        ax.text(xi, v + (3 if v >= 0 else -3), f"{v:+.0f}%", ha="center", va="bottom" if v >= 0 else "top",
                fontsize=9, color=INK)
    ax.axhline(0, color=INK_2, linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels([BAND_NAMES[b] for b in BANDS])
    ax.grid(axis="x", visible=False)
    lim = max(60, max(abs(v) for v in ov + nv if np.isfinite(v)) * 1.3)
    ax.set_ylim(-min(100, lim), lim)
    ax.set_ylabel("% change vs rest")
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.2), fontsize=9)
    return png(fig)


def fig_mapping():
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    r = np.logspace(np.log10(0.25), np.log10(4), 200)
    ax.plot(r, [score_vs_baseline(v, 1.0) for v in r], color=INK_2)
    for ratio, text in ((0.5, "half"), (1.0, "same as\nreference"), (1.6, "×1.6"), (2.0, "double")):
        sc = score_vs_baseline(ratio, 1.0)
        ax.plot([ratio], [sc], "o", color=C["stress"], markersize=7, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(ratio * 1.06, sc - 9, f"{text}: {sc:.0f}", fontsize=9, color=INK)
    ax.set_xscale("log")
    ax.set_xticks([0.25, 0.5, 1, 2, 4])
    ax.set_xticklabels(["¼×", "½×", "1×", "2×", "4×"])
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylim(0, 100)
    ax.set_xlabel("Brain-wave ratio compared with your reference")
    ax.set_ylabel("Score")
    return png(fig)


def fig_breaks():
    """Illustration of the two break triggers (not recorded data)."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True, gridspec_kw={"hspace": 0.55})
    # A: work timer
    a1.set_title("A · The 50-minute timer", loc="left", fontsize=10, color=INK)
    a1.broken_barh([(0, 50), (50, 10), (65, 15)], (0.35, 0.3), facecolors=[C["attention"], C["attention"], C["attention"]])
    a1.broken_barh([(60, 5)], (0.35, 0.3), facecolors=[MUTED])
    for x, text in ((50, "Prompt\n(50 min)"), (60, "Ignored →\nasks again"), (62.5, "")):
        if text:
            a1.annotate(text, (x, 0.65), (x, 1.15), ha="center", fontsize=8.5, color=INK,
                        arrowprops=dict(arrowstyle="-", color=INK_2, lw=1))
    a1.text(62.5, 0.1, "5-min break:\ntimer restarts", ha="center", va="top", fontsize=8.5, color=INK_2)
    a1.set_ylim(-0.6, 1.6)
    a1.set_yticks([])
    a1.grid(False)
    # B: fatigue
    a2.set_title("B · Fatigue stays high for 3 minutes (checked after the first 10 minutes)", loc="left",
                 fontsize=10, color=INK)
    t = np.linspace(0, 80, 400)
    fat = 50 + 26 / (1 + np.exp(-(t - 22) / 3)) + 3 * np.sin(t / 2.3)
    a2.plot(t, fat, color=C["stress"])
    a2.axhline(config.FATIGUE_BREAK_SCORE, color=INK_2, linestyle=":", linewidth=1)
    a2.text(79, config.FATIGUE_BREAK_SCORE + 2, "70", ha="right", fontsize=8.5, color=INK_2)
    a2.axvspan(0, 10, color=GRID, alpha=0.7, linewidth=0)
    a2.text(5, 90, "no fatigue\nprompts yet", ha="center", va="top", fontsize=8.5, color=INK_2)
    above = t[np.argmax(fat >= config.FATIGUE_BREAK_SCORE)]
    stay = above + np.argmax(np.all([np.interp(np.arange(x, x + 3.01, 0.25), t, fat) >= 70 for x in [above]])) * 0
    a2.axvspan(above, above + 3, color=C["stress"], alpha=0.15, linewidth=0)
    a2.annotate("Prompt", (above + 3, 80), (above + 9, 93), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="-", color=INK_2, lw=1))
    del stay
    a2.set_ylim(30, 100)
    a2.set_yticks([50, 70, 100])
    a2.set_ylabel("Fatigue")
    a2.set_xlabel("Minutes of work (illustration)")
    a2.set_xlim(0, 80)
    return png(fig)


# ── page ───────────────────────────────────────────────────────────
CSS = """
:root{--ink:#1f1f1d;--ink2:#4a4a46;--muted:#77776f;--line:#e6e6e2;--page:#fcfcfb;--card:#f4f4f1;--accent:#3987e5;--warn:#9a6400}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 "Segoe UI",system-ui,sans-serif}
main{max-width:880px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:34px;line-height:1.2;margin:0 0 6px}
h2{font-size:24px;margin:56px 0 12px;padding-top:12px;border-top:1px solid var(--line)}
h3{font-size:18px;margin:28px 0 8px}
p,li{color:var(--ink2)} strong{color:var(--ink)}
.lede{font-size:18px;color:var(--ink2);margin-top:0}
nav{background:var(--card);border-radius:10px;padding:14px 20px;margin:24px 0}
nav ol{margin:0;padding-left:20px;columns:2} nav a{color:var(--ink);text-decoration:none} nav a:hover{text-decoration:underline}
figure{margin:20px 0 28px} figure img{max-width:100%;border:1px solid var(--line);border-radius:8px;display:block}
figcaption{font-size:14px;color:var(--muted);margin-top:8px}
table{border-collapse:collapse;width:100%;margin:12px 0 20px;font-size:15px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--ink);font-weight:600;background:var(--card)}
td{color:var(--ink2)}
.note{background:var(--card);border-left:4px solid var(--accent);padding:12px 16px;border-radius:6px;margin:16px 0}
.warn{border-left-color:#c98500}
.step{display:inline-block;background:var(--ink);color:var(--page);border-radius:50%;width:26px;height:26px;
      text-align:center;line-height:26px;font-size:14px;margin-right:8px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:700px){.grid2{grid-template-columns:1fr} nav ol{columns:1}}
.small{font-size:14px;color:var(--muted)}
code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:14px}
@page{size:A4;margin:16mm 14mm}
@media print{
  body{font-size:11pt;background:#fff}
  main{max-width:none;padding:0}
  h1{font-size:24pt} h2{font-size:16pt;margin-top:28px} h3{font-size:12.5pt}
  h2,h3{break-after:avoid} p,li{orphans:3;widows:3}
  figure,table,tr,.note,.grid2{break-inside:avoid}
  figure img{max-height:118mm;width:auto;max-width:100%}
  nav,th,.note,code{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  a{color:inherit;text-decoration:none}
  h2#steps,h2#example{break-before:page}
}
"""


def build(session_path, screens_dir, out):
    s = Session(session_path)
    s.replay()
    new_bands = s.band_change()
    old_bands = s.meta["summary"].get("bands_change_mean", {})
    shots = {os.path.splitext(os.path.basename(p))[0]: screen(p) for p in glob.glob(os.path.join(screens_dir, "*.png"))}

    def shot(name, caption):
        if name not in shots:
            return f'<p class="small">[screen "{name}" not captured]</p>'
        return (f'<figure><img alt="{html.escape(caption)}" src="data:image/jpeg;base64,{shots[name]}">'
                f"<figcaption>{caption}</figcaption></figure>")

    def fig(b64, caption):
        return f'<figure><img alt="{html.escape(caption)}" src="data:image/png;base64,{b64}"><figcaption>{caption}</figcaption></figure>'

    cal = s.meta.get("calibration", {})
    summ = s.meta["summary"]
    res_live = {k: np.median([v for t, v in pts if t >= s.t_live - s.t_connect]) / 1e3 for k, pts in s.res.items()}
    res_start = {k: np.median([v for t, v in pts if t < (s.t_cal or s.t_live) - s.t_connect]) / 1e3
                 for k, pts in s.res.items()}
    old_ep = summ["stress_episodes"]
    old_ep_s = sum((b if b is not None else s.live_s) - a for a, b in old_ep)
    new_ep_s = sum((b if b is not None else s.live_s) - a for a, b in s.new_episodes)
    valid_new = s.new_stress[np.isfinite(s.new_stress)]
    fat_valid = s.new_fatigue[np.isfinite(s.new_fatigue)]
    date = s.meta.get("started_at", "")[:10]
    live_min = s.live_s / 60
    short_breaks = [b for b in s.breaks if b[1] - b[0] < config.MIN_BREAK_S]
    n_ep = len(s.new_episodes)
    episodes_text = ("<strong>no stress episodes</strong>" if not n_ep else
                     f"<strong>{n_ep} stress episode{'s' if n_ep != 1 else ''}</strong> ({new_ep_s / 60:.1f} minutes in total)")
    ref_end = s.ref_ready_at or config.WORK_REF_S
    early = s.bd_ok & (s.bd_t >= 0) & (s.bd_t < ref_end)
    after = s.bd_ok & (s.bd_t >= ref_end)
    late = {b: 100 * (np.median(s.bd_abs[b][after]) / np.median(s.bd_abs[b][early]) - 1) for b in BANDS}

    body = f"""
<h1>Focus &amp; Stress Monitor: user manual</h1>
<p class="lede">How to set up the EEG headphones, what each screen means, when the app asks you to take a break,
and what the numbers can and cannot tell you.</p>

<nav><ol>
<li><a href="#what">What the app does</a></li><li><a href="#need">What you need</a></li>
<li><a href="#steps">Step by step</a></li><li><a href="#screen">Reading the session screen</a></li>
<li><a href="#breaks">When it asks you to take a break</a></li><li><a href="#checkin">Sleepiness check-in</a></li>
<li><a href="#example">A real session, explained</a></li><li><a href="#signal">Getting a good signal</a></li>
<li><a href="#files">What gets saved</a></li><li><a href="#limits">What the numbers cannot tell you</a></li>
</ol></nav>

<h2 id="what">1. What the app does</h2>
<p>The app reads your brain waves through the electrodes in the headphones while you work. It shows three live
scores, <strong>Attention</strong>, <strong>Cognitive load</strong> and <strong>Stress</strong>, a chart of your
brain-wave bands, and it suggests breaks. Everything is saved so you can look at it later.</p>
<p>All scores are <strong>personal</strong>: they compare you with yourself earlier in the same session, not with
other people. A stress score of 80 means "much higher than your own normal level today", not "80% stressed".</p>

<h2 id="need">2. What you need</h2>
<ul>
<li>The Neiry headphones, charged, and paired with Windows (they appear as <code>USAMS-YX05</code> in Bluetooth settings).</li>
<li>This app: double-click <code>run.bat</code> in the <code>cognitive_score</code> folder.</li>
<li>About 3 minutes for setup, then as long as you want to work.</li>
</ul>

<h2 id="steps">3. Step by step</h2>
<p>The app walks you through seven steps in order. The list on the left shows where you are. You cannot skip ahead
until each step is done, because every later number depends on it.</p>

<h3><span class="step">1</span>Setup</h3>
<p>Tick the four checks: headphones charged and on, paired in Windows, electrodes touching skin (move hair away),
seated comfortably with notifications off. Then press <strong>Continue</strong>.</p>
{shot("0_checklist", "Setup: four quick checks before connecting.")}

<h3><span class="step">2</span>Connect</h3>
<p>Press <strong>Search</strong>. Your headset appears within about 10 seconds. Select it and press <strong>Connect</strong>.
If it fails, the app retries three times by itself. If it still fails, switch the headphones off and on and search again.</p>
{shot("1_connect", "Connect: search, choose the headset, connect.")}

<h3><span class="step">3</span>Signal</h3>
<p>Each electrode shows its contact quality. <strong>Good</strong> is below 500 kΩ, <strong>Fair</strong> is up to 1 MΩ,
<strong>Poor</strong> is above that. All electrodes must stay Good or Fair for 5 seconds before you can continue.
The wavy line is your live brain signal. It should look calm when you sit still.</p>
<p>If an electrode stays Poor: press the headphones gently onto your head, move hair away, wait 30 seconds. Dry electrodes
get better over the first few minutes as the skin warms up (see <a href="#example">the real session</a>).
<strong>Skip check</strong> lets you continue anyway, but the scores will be less reliable.</p>
{shot("2_signal", "Signal: every electrode needs Good or Fair contact.")}

<h3><span class="step">4</span>Calibration (30 seconds, eyes closed)</h3>
<p>Press <strong>Start</strong>, close your eyes and relax. A tone plays at the start and at the end. The app measures your
personal <strong>alpha peak</strong>, the frequency your brain idles at with eyes closed (typically 8–13 Hz).
All later calculations are tuned to it.</p>
{shot("3_calibration", "Calibration: eyes closed for 30 seconds, then your alpha peak is shown.")}

<h3><span class="step">5</span>Baseline (30–90 seconds, eyes open)</h3>
<p>Look at the cross in the middle of the screen and stay still. This is your <strong>rest</strong> level. Attention,
cognitive load and the brain-wave chart are compared with it. The app moves on by itself when it is done.</p>
{shot("4_baseline", "Baseline: eyes open on the cross, keep still.")}

<h3><span class="step">6</span>Session</h3>
<p>Now just work. The next section explains everything on this screen.</p>
{shot("5_live", "Session screen (from the simulator, so the numbers here are not real brain data).")}

<h3><span class="step">7</span>Summary</h3>
<p>When you press <strong>End session</strong>, you see your averages, how many stress episodes you had, how clean
the signal was, the whole-session timeline and the average brain-wave change. <strong>Open folder</strong> shows the
saved files.</p>
{shot("6_summary", "Summary after ending the session.")}

<h2 id="screen">4. Reading the session screen</h2>
<h3>The three big numbers</h3>
<table>
<tr><th>Score</th><th>What it tracks</th><th>Compared with</th></tr>
<tr><td><strong>Attention</strong></td><td>Fast (beta) waves relative to idle (alpha) waves. Goes up when you focus.</td>
<td>Your rest baseline (step 5)</td></tr>
<tr><td><strong>Cognitive load</strong></td><td>Theta waves relative to alpha. Goes up when a task is mentally demanding
(holding many things in mind).</td><td>Your rest baseline (step 5)</td></tr>
<tr><td><strong>Stress</strong></td><td>High-beta waves (20–30 Hz) relative to alpha: a measure of how "revved up"
you are.</td><td>Your <strong>first 2 minutes of work</strong></td></tr>
</table>
<p>Each score runs from 0 to 100. Next to the number is a word: <strong>Low</strong> (below 35),
<strong>Moderate</strong> (35–64) or <strong>High</strong> (65 and above).</p>
<p><strong>Why stress waits 2 minutes.</strong> For the first 2 minutes of the session the Stress card shows
"Starts in 1:59" and counts down. During that time the app learns your normal working level. From then on,
<strong>50 means "same as your first 2 minutes"</strong>. We changed this after a real session showed that
comparing with the eyes-open rest made stress read "High" all the time, just because working at a screen is
different from staring at a cross (details in <a href="#example">section 7</a>).</p>
{fig(fig_mapping(), "How a ratio becomes a score. 50 = same as your reference, double = 88, half = 12. "
                    "The scale flattens at the ends so one odd reading cannot jump to 0 or 100.")}

<h3>Stress episodes</h3>
<p>A <strong>stress episode</strong> starts when stress stays at <strong>80 or above for 30 seconds</strong> (about 1.6 times
your working level). The Stress card then shows an orange "Stress episode" tag, you hear one tone, and the timeline is
shaded orange. The episode ends when stress stays <strong>below 65 for 30 seconds</strong>. Short spikes are ignored on
purpose. Episodes pause during a break.</p>

<h3>Session timeline</h3>
<p>The three scores over the last 30 minutes, on the same 0–100 scale. The dashed line at 50 is your reference.
Grey bands are breaks, orange bands are stress episodes.</p>

<h3>Brain waves</h3>
<p>Five bars, one per frequency band. Each bar shows how much that band's power has <strong>changed compared with your rest
baseline</strong>: +50% means half as much again, −50% means half as much.</p>
<table>
<tr><th>Band</th><th>Frequency</th><th>Usually goes up when…</th></tr>
<tr><td>Delta</td><td>1–4 Hz</td><td>deep sleep; with dry electrodes, mostly <em>movement and sweat drift</em>. Ignore it while awake.</td></tr>
<tr><td>Theta</td><td>4–8 Hz</td><td>drowsiness, or holding a lot in memory</td></tr>
<tr><td>Alpha</td><td>8–13 Hz</td><td>relaxing, eyes closed, mind wandering. Drops when you look and focus.</td></tr>
<tr><td>Beta</td><td>13–30 Hz</td><td>active thinking and focus</td></tr>
<tr><td>Gamma</td><td>30–45 Hz</td><td>mainly <em>jaw clenching, chewing, talking and neck tension</em> at these electrode spots</td></tr>
</table>
<p>The bars update every second from the last 5 seconds of clean signal. Movement bursts are removed automatically.</p>

<h3>The small meters and the top bar</h3>
<ul>
<li><strong>Relaxation</strong>: the vendor's relaxation score (alpha relative to beta), 0–100.</li>
<li><strong>Fatigue</strong>: slow waves (theta + alpha) relative to beta, 50 = your first 2 minutes of work. It is smoothed over
1 minute because tiredness builds up slowly. This is the number the break rule watches.</li>
<li><strong>Heart rate</strong> appears only on headsets with a pulse sensor.</li>
<li><strong>Signal pill</strong>: green "Signal good", or amber "Adjust headphones" when more than 30% of the last 30 seconds
had movement or poor contact. While amber, the numbers are greyed and not counted in your averages.</li>
<li><strong>Marker</strong>: type a label (for example "started report") to find that moment later in the files.</li>
<li><strong>Take a break / Resume</strong> and <strong>End session</strong>.</li>
</ul>

<h2 id="breaks">5. When it asks you to take a break</h2>
<p>A banner appears at the top with a tone and a <strong>Take a break</strong> button. It is triggered by
<strong>either</strong> of two rules:</p>
<table>
<tr><th>Rule</th><th>Exactly when</th><th>Why</th></tr>
<tr><td><strong>A. 50-minute timer</strong></td><td>50 minutes of work since the session started or since your last
real break. The banner says "50 min without a break".</td><td>A safe default, even if the EEG cannot see fatigue.</td></tr>
<tr><td><strong>B. Fatigue</strong></td><td>The fatigue meter stays at <strong>70 or above for 3 minutes in a row</strong>,
and at least 10 minutes have passed since the session started. The banner says "Fatigue has been high for several minutes".</td>
<td>Slow waves grow as you tire. 70 means about 1.4× your level at the start.</td></tr>
</table>
{fig(fig_breaks(), "Illustration of the two rules (made-up data). A: the timer, a repeat after an ignored prompt, "
                   "and a restart after a real break. B: fatigue above 70 for 3 minutes.")}

<h3>The fine print</h3>
<ul>
<li><strong>At most one prompt every 10 minutes.</strong> If you press Dismiss or ignore it, it comes back 10 minutes later
(with the new count, e.g. "60 min without a break").</li>
<li><strong>A break must last at least 2 minutes to count.</strong> Shorter breaks are saved, but the 50-minute timer keeps
running. (In the real session below, a 1.5-second break would previously have restarted the timer.)</li>
<li><strong>No prompts during a break</strong>, and none for 10 minutes after you press Resume.</li>
<li><strong>Fatigue during a break does not count.</strong> The 3-minute fatigue clock starts again after you resume.</li>
<li>No fatigue prompts in the first 10 minutes. The first minutes of a session are not a fair test of tiredness.</li>
</ul>

<h3>How to take a break</h3>
<p>Press <strong>Take a break</strong> (top bar or banner). The banner changes to "On a break". Stand up, look away from the
screen, move around. You can keep the headphones on. When you come back, press <strong>Resume</strong>. Break time is not
counted in your averages and is shown grey on the timeline.</p>
<div class="grid2">{shot("5d_break_prompt", "A break prompt.")}{shot("5c_on_break", "During a break.")}</div>

<h2 id="checkin">6. Sleepiness check-in</h2>
<p>Every 10 minutes a small window asks "How sleepy do you feel?" with a 1–9 scale (the Karolinska Sleepiness Scale, a standard
questionnaire). Click the number that fits, or Skip. It does not stop the recording. It does not appear during a break
(it waits until you resume). Your answers are saved next to the brain data, so later you can check whether the fatigue
meter agrees with how you actually felt.</p>
{shot("5b_kss", "The check-in window.")}

<h2 id="example">7. A real session, explained ({date})</h2>
<p>This section uses a real {live_min:.1f}-minute recording from the headphones (folder
<code>{html.escape(os.path.basename(s.path))}</code>). The figures show what the <strong>current</strong> version of the app
computes from that data. This session is what led to the fixes described below.</p>

<h3>Setup went well</h3>
<p>Calibration found an alpha peak of <strong>{cal.get("iapf", float("nan")):.1f} Hz</strong> (normal range 8–13 Hz). Only
{100 * summ["artifact_fraction"]:.1f}% of the signal was disturbed by movement. Electrode resistance was already Good at the start
(median {min(res_start.values()):.0f}–{max(res_start.values()):.0f} kΩ) and kept falling to
{min(res_live.values()):.0f}–{max(res_live.values()):.0f} kΩ during the session as the dry electrodes settled on the skin.</p>
{fig(fig_contact(s), "Electrode resistance over the whole session. Lower is better. All four electrodes stayed well inside "
                     "Good and improved for several minutes.")}

<h3>The scores</h3>
{fig(fig_scores(s), "Attention, cognitive load and stress during the session. Stress starts after 2 minutes. "
                    "The grey band on the left is the 2-minute reference period.")}
<p>Attention was high throughout (average {summ["scores"]["attention"]["mean"]:.0f}). Cognitive load moved a lot from moment to
moment (average {summ["scores"]["cognitive_load"]["mean"]:.0f}). Stress, once it started, averaged
<strong>{np.mean(valid_new):.0f}</strong>, with {episodes_text}.</p>

<h3>Fix 1: stress was stuck on "High"</h3>
<p>The first version compared stress with the eyes-open rest (step 5). In this session that version showed an average stress of
<strong>{summ["scores"]["stress"]["mean"]:.0f}</strong> and a single stress episode lasting <strong>{old_ep_s / 60:.1f} of
{live_min:.1f} minutes</strong>. The reason: high-beta relative to alpha was about 1.8 times higher while working than
while looking at the cross, simply because looking at a busy screen lowers alpha. That is a change of activity, not stress.</p>
<p>Now stress is compared with your <strong>first 2 minutes of work</strong>, smoothed over 30 seconds, and an episode needs
80 or more for 30 seconds. On the same data, that gives {episodes_text}.</p>
{fig(fig_stress_fix(s), "Stress on the same recording, before and after the fix.")}
<p>Stress still read <strong>High</strong> after minute 2 (about {np.mean(valid_new):.0f}), because high-beta relative to alpha kept
rising during the session. At the same time the fastest band (gamma) rose by {late["gamma"]:+.0f}% and beta by
{late["beta"]:+.0f}%, while alpha hardly changed ({late["alpha"]:+.0f}%). A broad rise at high frequencies with no alpha
change is the typical pattern of <strong>muscle tension</strong> (jaw, neck, frowning) rather than a change in brain state.
So in this short test, part of the "stress" was probably muscle. That is still useful: tensing up is part of stress.
But check your jaw and shoulders before trusting a high reading (see <a href="#limits">section 10</a>).</p>

<h3>Fix 2: the brain-wave bars all went up together</h3>
<p>The first version showed each band's <em>share</em> of total power. During the rest baseline the slow drift of the freshly-placed
electrodes (delta) made up about three quarters of all power. As the electrodes settled, delta shrank, so every other band's
share grew automatically. The old chart showed alpha, beta and gamma all at about +75%. Now each bar compares a band's
<em>own</em> power with rest, so one band's change cannot move the others.</p>
{fig(fig_bands(s, new_bands, old_bands), "Average change of each band vs rest for this session, before and after the fix. "
                                          "Now: delta dropped as the electrodes settled, theta and alpha dropped a little "
                                          "(eyes open and busy), beta and gamma stayed about the same.")}

<h3>Fix 3: breaks</h3>
<p>In this session you pressed <strong>Take a break</strong> and <strong>Resume</strong> within
{(short_breaks[0][1] - short_breaks[0][0]) if short_breaks else 0:.1f} seconds. The old version treated that as a full break and
restarted the 50-minute timer. Now a break must last 2 minutes to count. No break prompt would have appeared in this session:
it was shorter than 10 minutes (fatigue prompts are off), fatigue stayed between {np.min(fat_valid):.0f} and
{np.max(fat_valid):.0f} (below 70), and the 50-minute timer would have first fired at minute
<strong>{s.next_prompt_min:.0f}</strong>.</p>
<p>Also fixed: the check-in no longer pops up during a break, stress episodes end when a break starts, and fatigue measured
while on a break no longer counts towards a prompt.</p>

<h2 id="signal">8. Getting a good signal</h2>
<table>
<tr><th>Problem</th><th>What to do</th></tr>
<tr><td>Headset not found</td><td>Check it is on and charged; check it is paired in Windows Bluetooth; switch it off and on; search again.</td></tr>
<tr><td>Electrode stays Poor</td><td>Move hair aside, press the ear cups gently, wait 30–60 s. A drop of water on the skin helps dry electrodes.</td></tr>
<tr><td>"Adjust headphones" during the session</td><td>You moved, talked or clenched your jaw. Sit still for a moment; it clears by itself.</td></tr>
<tr><td>Gamma bar very high</td><td>Relax your jaw and shoulders. Gamma at these spots is mostly muscle.</td></tr>
<tr><td>Delta bar very negative or positive</td><td>Normal in the first minutes (electrodes settling) or after moving. Ignore delta while awake.</td></tr>
<tr><td>Calibration failed</td><td>Try again with eyes fully closed and without moving. The app falls back to typical values if needed.</td></tr>
<tr><td>Headphones disconnected</td><td>A red banner appears. Everything up to that point is saved. End the session and start again.</td></tr>
</table>
<p><strong>Calibrate every session.</strong> Your brain waves and the electrode contact change from day to day; earlier recordings
varied up to 7 times between days.</p>

<h2 id="files">9. What gets saved</h2>
<p>Each session gets a folder in <code>sessions</code>, named by date and time. <strong>Open folder</strong> on the summary opens it.</p>
<table>
<tr><th>File</th><th>What is in it</th></tr>
<tr><td><code>session.json</code></td><td>Device, calibration, baselines and the summary you saw at the end</td></tr>
<tr><td><code>scores.csv</code></td><td>The five scores once per second, plus whether the signal was poor or you were on a break</td></tr>
<tr><td><code>bands.csv</code></td><td>Power of each brain-wave band twice per second, and why a window was rejected (movement)</td></tr>
<tr><td><code>events.csv</code></td><td>Markers, breaks, break prompts, stress episodes, check-in answers, signal warnings</td></tr>
<tr><td>other <code>.csv</code> files</td><td>The raw outputs of the headset software, for later analysis</td></tr>
</table>
<p class="small">To rebuild this manual with figures from a newer session:
<code>python docs/build_manual.py --session sessions/&lt;folder&gt;</code></p>

<h2 id="limits">10. What the numbers cannot tell you</h2>
<div class="note warn">
<p><strong>This is not a medical device.</strong> The scores are estimates from two electrode pairs near the ears.</p>
</div>
<ul>
<li><strong>Stress</strong> from brain waves alone is weak evidence. Studies disagree on which brain-wave change means stress. Read it
as "more revved up than at the start of this session". Heart-rate based stress (on headsets with a pulse sensor) is stronger.</li>
<li><strong>Muscles look like brain waves</strong> above about 20 Hz. Jaw clenching, chewing and talking raise gamma, high beta and
therefore stress. Keep your jaw relaxed if you want a clean reading.</li>
<li><strong>Scores compare you with yourself today.</strong> Do not compare numbers between people or between days.</li>
<li><strong>The break prompt is advice.</strong> The 50-minute timer works even when the EEG cannot see fatigue. Use the check-in
answers to see whether the fatigue meter matches how you felt.</li>
</ul>
"""
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Focus Monitor Manual</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    return s, new_bands


EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]


def to_pdf(html_path):
    """Print the page to PDF with headless Edge (ships with Windows)."""
    import subprocess
    import tempfile
    exe = next((e for e in EDGE if os.path.isfile(e)), None)
    if exe is None:
        raise SystemExit("Microsoft Edge not found: open manual.html and print to PDF instead")
    pdf = os.path.splitext(html_path)[0] + ".pdf"
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    with tempfile.TemporaryDirectory() as profile:           # separate profile: works while Edge is open
        subprocess.run([exe, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf}", url],
                       check=True, capture_output=True, timeout=120)
    return pdf


def latest_real_session():
    for p in sorted(glob.glob(os.path.join(ROOT, "sessions", "*")), reverse=True):
        meta = os.path.join(p, "session.json")
        if os.path.isfile(os.path.join(p, "scores.csv")) and os.path.isfile(meta):
            with open(meta, encoding="utf-8") as fh:
                if not json.load(fh).get("simulated", True):
                    return p
    raise SystemExit("no real session with scores.csv found in sessions/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", default=None)
    ap.add_argument("--screens", default=os.path.join(HERE, "screens"))
    ap.add_argument("--out", default=os.path.join(HERE, "manual.html"))
    ap.add_argument("--no-pdf", action="store_true", help="skip the PDF (needs Microsoft Edge)")
    args = ap.parse_args()
    s, bands = build(args.session or latest_real_session(), args.screens, args.out)
    print(f"manual: {args.out}")
    if not args.no_pdf:
        print(f"pdf: {to_pdf(args.out)}")
    print(f"session {os.path.basename(s.path)}: live {s.live_s / 60:.1f} min, reference {s.ref}")
    print(f"stress now: mean {np.nanmean(s.new_stress):.1f}, episodes {s.new_episodes}; prompts {s.prompts}")
    print("band change vs rest:", {b: round(v) for b, v in bands.items()})


if __name__ == "__main__":
    main()
