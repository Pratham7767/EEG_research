"""Build docs/how_it_works.html + .pdf: every processing step explained (how, why, from where),
with figures computed from the recorded sessions and the app's own code.

    python docs/build_explainer.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_manual as bm                                            # noqa: E402  (figure style, helpers, replay)
from build_manual import C, GRID, INK, INK_2, MUTED, png  # noqa: E402

import matplotlib.pyplot as plt                                      # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch  # noqa: E402

from cogscore.metrics import RollingMedian                           # noqa: E402
from cogscore.spectral import design_filter                          # noqa: E402

GOOD_SESSION = os.path.join(bm.ROOT, "sessions", "2026-09-30_135243")
NOISY_SESSION = os.path.join(bm.ROOT, "sessions", "2026-09-30_180933")


# ── teaching figures ───────────────────────────────────────────────
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(8.6, 3.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 44)
    ax.axis("off")

    def box(x, y, w, h, title, lines, colour):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.5",
                                    facecolor=colour, edgecolor=INK_2, linewidth=1))
        ax.text(x + w / 2, y + h - 3, title, ha="center", va="top", fontsize=9.5, weight="bold", color=INK)
        ax.text(x + w / 2, y + h - 8, "\n".join(lines), ha="center", va="top", fontsize=7.8, color=INK_2,
                linespacing=1.35)

    def arrow(x0, y0, x1, y1):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12, color=INK_2, lw=1.2))

    box(1, 12, 14, 26, "Headphones", ["4 dry electrodes", "A1 A2 C3 C4", "250 samples/s", "Bluetooth"], "#eef3fb")
    box(20, 12, 24, 26, "Capsule SDK (DLL)", ["vendor, closed source", "resistance, artifacts",
                                               "4–35 Hz filter", "spectrum (PSD) 0.1 Hz",
                                               "calibration (alpha peak)", "Emotions classifier"], "#f6efe9")
    box(49, 24, 22, 17, "Our code: stress path", ["SDK spectrum", "band ratios", "vs first 2 min of work"],
        "#eef6f1")
    box(49, 3, 22, 17, "Our code: bands path", ["raw EEG", "filter + Welch", "vs rest baseline"], "#eef6f1")
    box(76, 24, 22, 17, "Screen", ["scores, timeline", "brain-wave bars", "break prompts"], "#f4f4f1")
    box(76, 3, 22, 17, "Session folder", ["CSV + JSON files", "every value saved"], "#f4f4f1")
    arrow(15.5, 25, 19.5, 25)
    arrow(44.5, 30, 48.5, 32)
    arrow(44.5, 18, 48.5, 12)
    arrow(71.5, 32, 75.5, 32)
    arrow(71.5, 12, 75.5, 12)
    arrow(71.5, 30, 75.5, 14)
    ax.text(32, 10, "Attention, Cognitive load and Relaxation\ngo straight to the screen", ha="center", va="top",
            fontsize=7.8, color=INK_2, style="italic")
    return png(fig)


def fig_head():
    fig, ax = plt.subplots(figsize=(4.4, 3.9))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Circle((0, 0), 1, fill=False, edgecolor=INK_2, linewidth=1.5))
    ax.plot([-0.12, 0, 0.12], [0.99, 1.13, 0.99], color=INK_2, linewidth=1.5)          # nose
    ax.text(0, 1.2, "front (nose)", ha="center", fontsize=8, color=MUTED)
    pts = {"C3": (-0.45, 0.0), "C4": (0.45, 0.0), "A1": (-1.12, -0.12), "A2": (1.12, -0.12)}
    for (a, b), col in ((("A1", "C3"), C["e1"]), (("A2", "C4"), C["e2"])):
        ax.plot(*zip(pts[a], pts[b]), color=col, linewidth=3, alpha=0.8)
    for name, (x, y) in pts.items():
        ax.add_patch(Circle((x, y), 0.08, facecolor="#ffffff", edgecolor=INK, linewidth=1.3, zorder=3))
        ax.text(x, y - 0.17, name, ha="center", va="top", fontsize=9, color=INK)
    ax.text(-0.72, 0.32, "channel A1-C3", ha="center", fontsize=8, color=C["e1"])
    ax.text(0.72, 0.32, "channel A2-C4", ha="center", fontsize=8, color=C["e2"])
    ax.text(0, -0.55, "C3 / C4: over the motor strip\nA1 / A2: behind the ears (reference)", ha="center",
            fontsize=7.8, color=INK_2)
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-1.1, 1.3)
    return png(fig)


def fig_sdk_filter():
    """Gain of the SDK's processed signal vs raw, measured on the simulator (plan.md §9.2)."""
    bands = ["1–2", "3–4", "4–7", "7–13", "13–30", "30–35", "40–45", ">45"]
    gain = [0.004, 0.14, 0.71, 1.0, 0.96, 0.55, 0.14, 0.0]
    fig, ax = plt.subplots(figsize=(7.6, 2.8))
    x = np.arange(len(bands))
    ax.bar(x, gain, width=0.6, color=C["band"])
    for xi, g in zip(x, gain):
        ax.text(xi, g + 0.03, f"{g:.2f}" if g else "≈0", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([b + " Hz" for b in bands], fontsize=8.5)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Amplitude kept\n(1 = unchanged)")
    ax.grid(axis="x", visible=False)
    ax.axvspan(1.5, 5.5, color=C["good"], alpha=0.06, linewidth=0)
    ax.text(3.5, 1.08, "usable: about 4–30 Hz", ha="center", fontsize=8.5, color=INK_2)
    return png(fig)


def fig_psd_bins(iapf):
    """Illustrative EEG spectrum at the SDK's 0.1 Hz bins, with the vendor band ranges shaded."""
    f = np.round(np.arange(1.0, 30.01, 0.1), 1)
    p = 1.0 / f + 0.35 * np.exp(-0.5 * ((f - iapf) / 1.0) ** 2)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.6, 3.0), gridspec_kw={"width_ratios": [2.3, 1], "wspace": 0.25})
    spans = [("θ", 4, 7, C["cognitive_load"]), ("α", 7, 13, C["attention"]), ("β", 15, 30, C["stress"])]
    for name, lo, hi, col in spans:
        a1.axvspan(lo, hi, color=col, alpha=0.12, linewidth=0)
        a1.text((lo + hi) / 2, 1.04, name, ha="center", fontsize=10, color=INK)
    a1.axvspan(20, 30, ymax=0.08, color=C["stress"], alpha=0.5, linewidth=0)
    a1.text(25, 0.1, "high β 20–30", ha="center", fontsize=8, color=INK)
    a1.plot(f, p, color=INK_2, linewidth=1.6)
    a1.set_xlim(1, 30)
    a1.set_ylim(0, 1.1)
    a1.set_xlabel("Frequency (Hz)")
    a1.set_ylabel("Power (illustration)")
    a1.set_title(f"Spectrum with an alpha peak at {iapf:.1f} Hz", loc="left", fontsize=9.5, color=INK)
    # zoom: individual bins
    m = (f >= 6.5) & (f < 7.6)
    a2.bar(f[m], p[m], width=0.08, color=[C["cognitive_load"] if v < 7 else C["attention"] for v in f[m]])
    a2.axvline(6.95, color=INK_2, linestyle=":", linewidth=1)
    a2.set_title("Zoom: one bar = one 0.1 Hz bin", loc="left", fontsize=9.5, color=INK)
    a2.set_xticks([6.5, 6.9, 7.0, 7.5])
    a2.set_xticklabels(["6.5", "6.9", "7.0", "7.5"], fontsize=8)
    a2.text(6.72, max(p[m]) * 1.02, "θ", ha="center", fontsize=10)
    a2.text(7.3, max(p[m]) * 1.02, "α", ha="center", fontsize=10)
    a2.set_ylim(0, max(p[m]) * 1.12)
    a2.grid(axis="x", visible=False)
    return png(fig)


def fig_arousal_reason(s):
    fig, ax = plt.subplots(figsize=(8, 3.0))
    rm, sm = RollingMedian(10), []
    for t, v in zip(s.ind_t, s.arousal):
        rm.add(t, v)
        sm.append(rm.value(t))
    t = s.ind_t / 60
    ax.plot(t, sm, color=C["stress"], label="high β / α (10 s median)")
    rest = np.nanmedian(s.arousal[(s.ind_t < 0) & (s.ind_t >= (s.t_cal - s.t_live))])
    ax.axhline(rest, color=MUTED, linestyle="--", linewidth=1)
    ax.axhline(s.ref["arousal"], color=INK_2, linestyle=":", linewidth=1.2)
    ax.annotate(f"rest reference {rest:.2f}", xy=(1.0, rest), xycoords=("axes fraction", "data"), xytext=(6, -2),
                textcoords="offset points", fontsize=8.5, color=INK_2, va="center")
    ax.annotate(f"work reference {s.ref['arousal']:.2f}", xy=(1.0, s.ref["arousal"]),
                xycoords=("axes fraction", "data"), xytext=(6, 4), textcoords="offset points", fontsize=8.5,
                color=INK_2, va="center")
    ax.axvspan((s.t_cal - s.t_live) / 60, 0, color=GRID, alpha=0.7, linewidth=0)
    ax.text((s.t_cal - s.t_live) / 120, 1.55, "eyes-open\nbaseline", ha="center", fontsize=8, color=INK_2)
    ax.axvspan(0, 2, color=C["stress"], alpha=0.07, linewidth=0)
    ax.text(1, 1.55, "first 2 min\nof work", ha="center", fontsize=8, color=INK_2)
    ax.set_ylim(0, 1.75)
    ax.set_xlim((s.t_cal - s.t_live) / 60 - 0.1, s.live_s / 60)
    ax.set_xlabel("Minutes from the start of the session (negative = setup)")
    ax.set_ylabel("Ratio")
    return png(fig)


def fig_filter_response():
    from scipy.signal import sosfreqz
    sos = design_filter(250.0)
    w, h = sosfreqz(sos, worN=8192, fs=250.0)
    db = 20 * np.log10(np.maximum(np.abs(h), 1e-6))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.6, 2.8), gridspec_kw={"wspace": 0.3})
    for ax, lo, hi, title in ((a1, 0, 5, "Low end: 0.5 Hz high-pass"), (a2, 40, 60, "50 Hz notch (mains hum)")):
        m = (w >= lo) & (w <= hi)
        ax.plot(w[m], db[m], color=C["attention"])
        ax.set_xlim(lo, hi)
        ax.set_ylim(-45, 3)
        ax.set_title(title, loc="left", fontsize=9.5, color=INK)
        ax.set_xlabel("Frequency (Hz)")
    a1.set_ylabel("Gain (dB)\n0 dB = unchanged")
    a1.axvspan(1, 5, color=C["good"], alpha=0.06, linewidth=0)
    a1.text(3, -40, "delta band kept", ha="center", fontsize=8.5, color=INK_2)
    return png(fig)


def fig_welch():
    fig, ax = plt.subplots(figsize=(8, 1.9))
    ax.set_xlim(-0.1, 4.1)
    ax.set_ylim(0, 4.2)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 3.1), 4, 0.7, boxstyle="round,pad=0.02", facecolor="#eef3fb", edgecolor=INK_2))
    ax.text(2, 3.45, "4 s window = 1000 samples (the newest data, recomputed every 0.5 s)", ha="center",
            va="center", fontsize=8.5)
    for i, (x0, y) in enumerate(((0, 2.2), (1, 1.3), (2, 0.4))):
        ax.add_patch(FancyBboxPatch((x0, y), 2, 0.6, boxstyle="round,pad=0.02", facecolor="#f6efe9",
                                    edgecolor=INK_2))
        ax.text(x0 + 1, y + 0.3, f"segment {i + 1}: 2 s = 500 samples → spectrum {i + 1}", ha="center",
                va="center", fontsize=8)
    ax.text(4.05, 1.3, "average of\n3 spectra\n= Welch PSD", fontsize=8.5, va="center", color=INK)
    return png(fig)


def fig_noisy_baseline(n):
    """Theta and alpha power over time vs the frozen rest reference (18:09 session)."""
    fig, ax = plt.subplots(figsize=(8, 2.9))
    base = n.meta.get("own_baseline_bands", {})
    for band, col in (("theta", C["cognitive_load"]), ("alpha", C["attention"])):
        rm, t_out, v_out = RollingMedian(5), [], []
        for t, v, ok in zip(n.bd_t, n.bd_abs[band], n.bd_ok):
            if ok:
                rm.add(t, v)
                t_out.append(t)
                v_out.append(rm.value(t))
        ax.plot(t_out, v_out, color=col, label=f"{band} power (5 s median)")
        ref = base.get(f"abs_{band}", np.nan) * 1e12
        ax.axhline(ref, color=col, linestyle=":", linewidth=1.2)
        ax.annotate(f"{band} reference", xy=(1.0, ref), xycoords=("axes fraction", "data"), xytext=(6, 0),
                    textcoords="offset points", fontsize=8, color=INK_2, va="center")
    ax.axvspan(n.t_cal - n.t_live, 0, color=GRID, alpha=0.7, linewidth=0)
    ax.text((n.t_cal - n.t_live) / 2, 0.95, "rest baseline", ha="center", va="top", fontsize=8.5, color=INK_2,
            transform=ax.get_xaxis_transform())
    ax.set_yscale("log")
    ax.set_xlabel("Seconds from the start of the session (negative = setup)")
    ax.set_ylabel("Band power (µV²)")
    ax.legend(loc="upper right", fontsize=8.5, bbox_to_anchor=(1, 1.22), ncol=2)
    return png(fig)


def _col(sess, key):
    import csv
    with open(os.path.join(sess.path, "bands.csv"), newline="", encoding="utf-8") as fh:
        return [r[key] for r in csv.DictReader(fh)]


# ── page ───────────────────────────────────────────────────────────
EXTRA_CSS = """
.hw{display:grid;grid-template-columns:110px 1fr;gap:4px 14px;margin:10px 0 18px;padding:12px 16px;
    background:var(--card);border-radius:8px}
.hw b{color:var(--ink);font-size:14px;text-transform:uppercase;letter-spacing:.04em;padding-top:2px}
.hw div{color:var(--ink2)} .hw div p{margin:0 0 6px}
.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;margin-right:4px;font-weight:600}
.t-v{background:#f6e7dc;color:#8a3a12}.t-l{background:#e3eefb;color:#1d5aa6}.t-m{background:#e2f3ea;color:#0f6a44}
.t-d{background:#efefeb;color:#55554f}
.eq{font-family:Consolas,monospace;background:var(--card);padding:10px 14px;border-radius:6px;white-space:pre-wrap;
    font-size:14px;color:var(--ink)}
@media print{.hw,.eq{break-inside:avoid}}
"""

TAGS = {"v": ("t-v", "Vendor"), "l": ("t-l", "Literature"), "m": ("t-m", "Measured"), "d": ("t-d", "Design choice")}


def tag(*keys):
    return "".join(f'<span class="tag {TAGS[k][0]}">{TAGS[k][1]}</span>' for k in keys)


def hw(how, why, where):
    return (f'<div class="hw"><b>How</b><div>{how}</div><b>Why</b><div>{why}</div>'
            f'<b>From where</b><div>{where}</div></div>')


def fig(b64, caption):
    return (f'<figure><img alt="{caption}" src="data:image/png;base64,{b64}"><figcaption>{caption}</figcaption>'
            f"</figure>")


def build(out):
    s = bm.Session(GOOD_SESSION)
    s.replay()
    n = bm.Session(NOISY_SESSION)
    bands_new = s.band_change()
    cal = s.meta["calibration"]
    ex = {"delta": 0.0098, "theta": 0.1954, "alpha": 0.3361, "smr": 0.0462, "beta": 0.4125, "high_beta": 0.2858}
    arousal = ex["high_beta"] / ex["alpha"]
    fatigue = (ex["theta"] + ex["alpha"]) / ex["beta"]
    ref_a, ref_f = s.ref["arousal"], s.ref["fatigue"]

    def score(v, r):
        return 50 + 50 * np.tanh(np.log2(v / r))

    rest_abs = {b: np.median(s.bd_abs[b][s.bd_ok & (s.bd_t >= s.t_cal - s.t_live) & (s.bd_t < 0)]) for b in bm.BANDS}
    live_abs = {b: np.median(s.bd_abs[b][s.bd_ok & (s.bd_t >= 0)]) for b in bm.BANDS}
    rest_share_delta = rest_abs["delta"] / sum(rest_abs.values())
    in_base = (n.bd_t >= n.t_cal - n.t_live) & (n.bd_t < 0)
    rej_base, n_base = int((~n.bd_ok & in_base).sum()), int(in_base.sum())
    theta_rest = n.meta["own_baseline_bands"]["abs_theta"] * 1e12
    theta_live = float(np.median(n.bd_abs["theta"][n.bd_ok & (n.bd_t >= 0)]))

    body = f"""
<h1>How the Cognitive Score app works</h1>
<p class="lede">Every step from the electrodes to the numbers on screen: <strong>how</strong> it is done,
<strong>why</strong> it is done that way, and <strong>where</strong> each method and number comes from.
Worked examples use your real recordings of 30 September 2026.</p>

<div class="note"><p><strong>Reading the "From where" tags</strong><br>
{tag("v")} the headset maker's SDK or documentation &nbsp; {tag("l")} a published study or standard &nbsp;
{tag("m")} measured on your recordings or the simulator &nbsp; {tag("d")} a choice made in this project, not yet validated.</p></div>

<nav><ol>
<li><a href="#big">The big picture</a></li><li><a href="#hw">The headset and its signal</a></li>
<li><a href="#connect">Connecting</a></li><li><a href="#contact">Electrode contact</a></li>
<li><a href="#cal">Calibration</a></li><li><a href="#base">Rest baseline</a></li>
<li><a href="#psd">The SDK spectrum</a></li><li><a href="#vendor">Attention, cognitive load, relaxation</a></li>
<li><a href="#stress">Stress</a></li><li><a href="#fatigue">Fatigue</a></li>
<li><a href="#bands">Brain-wave bars</a></li><li><a href="#breaks">Breaks and check-ins</a></li>
<li><a href="#save">Recording</a></li><li><a href="#tests">Testing</a></li>
<li><a href="#issues">Known issues</a></li><li><a href="#params">All numbers at a glance</a></li>
<li><a href="#check">Check yourself</a></li><li><a href="#refs">Sources</a></li>
</ol></nav>

<h2 id="big">1. The big picture</h2>
<p>The app is a chain of small steps. The headset measures voltages; the vendor's software (the Capsule SDK, a
closed-source Windows DLL) cleans them and computes some scores; our Python code computes the rest, decides when to
prompt you, draws the screen and saves everything.</p>
{fig(fig_pipeline(), "Where each number is computed. Only the green boxes are our own analysis.")}
<p>There are <strong>two separate analysis paths</strong> in our code, because the SDK's spectrum cannot show
the slowest and fastest waves (section 7):</p>
<table>
<tr><th>Path</th><th>Input</th><th>Produces</th><th>Compared with</th></tr>
<tr><td>Stress path</td><td>SDK spectrum, 0.1 Hz bins, 1–30 Hz</td><td>Stress, Fatigue</td><td>your first 2 minutes of work</td></tr>
<tr><td>Bands path</td><td>raw EEG, 250 samples/s</td><td>Brain-wave bars</td><td>your eyes-open rest baseline</td></tr>
<tr><td>(vendor)</td><td>SDK internal</td><td>Attention, Cognitive load, Relaxation</td><td>the SDK's own baseline</td></tr>
</table>

<h2 id="hw">2. The headset and its signal</h2>
{fig(fig_head(), "Electrode positions seen from above. Each channel is the voltage between an ear electrode and a scalp electrode.")}
{hw("<p>Four dry electrodes: A1 and A2 behind the ears, C3 and C4 on top of the head. The SDK is set to "
    "<strong>bipolar</strong> mode, so it reports two channels: <strong>A1-C3</strong> (left) and "
    "<strong>A2-C4</strong> (right). Each channel is sampled <strong>250 times per second</strong>.</p>",
    "<p>A bipolar channel subtracts two electrodes, which cancels noise they share (for example from the body or the "
    "room). The SDK's classifiers expect bipolar mode.</p>",
    f"<p>{tag('v')} Channel names, sample rate and mode come from the SDK at connection time "
    "(<code>Device.get_channel_names</code>, <code>get_eeg_sample_rate</code>). Electrode names follow the "
    f"international 10-20 system {tag('l')}. Your device: \"Headphone\", serial 830817.</p>")}

<h2 id="connect">3. Connecting</h2>
{hw("<p>The app asks the SDK's <code>DeviceLocator</code> to search for 10 s, lists what it finds, and connects to "
    "the one you pick. If connecting fails it retries after 2, 5 and 10 s. Everything the SDK reports (new data, "
    "status changes) arrives through <em>callbacks</em>, which only run when the app calls the SDK's "
    "<code>update()</code>; the app does that every 20 ms from the window's own timer.</p>",
    "<p>The SDK is single-threaded: calling it from one place avoids crashes and lets the window stay responsive. "
    "Bluetooth connections sometimes fail on the first try, so automatic retries save the user a restart.</p>",
    f"<p>{tag('v')} Connection flow from the SDK documentation (<em>Capsule flow</em>, <em>Device connection</em> "
    f"pages) and the vendor's Python examples. {tag('d')} The 10 s scan and the 2/5/10 s retry delays.</p>")}

<h2 id="contact">4. Electrode contact (the Signal step)</h2>
{hw("<p>The SDK measures each electrode's <strong>resistance</strong> (how well it touches the skin). The app grades "
    "it: <strong>Good</strong> below 500 kΩ, <strong>Fair</strong> 500–1000 kΩ, <strong>Poor</strong> above. "
    "You can continue once every electrode has been Good or Fair for 5 seconds in a row. During the session, the "
    "SDK also flags each moment as artifact or clean; if more than 30% of the last 30 s is flagged, the screen says "
    "\"Adjust headphones\" and those seconds are left out of your averages.</p>",
    "<p>Poor contact lets in noise that looks like brain activity. The 5-second hold stops a single lucky reading "
    "from opening the gate.</p>",
    f"<p>{tag('v')} The 500 kΩ / 1 MΩ thresholds are quoted from the SDK documentation page "
    "<em>Devices modes</em> (<code>Docs/html/devices_modes.html</code>): \"Above 1000 kOhm - bad quality, 500 to 1000 kOhm - "
    f"average quality, Below 500 kOhm - good quality\". Artifact flags: SDK <code>EEGArtifacts</code>. {tag('d')} The 5 s "
    "hold, the 30 s window and the 30% warning level.</p>")}
{fig(bm.fig_contact(s), "Your 13:52 session: dry electrodes keep improving for several minutes after you put the headset on.")}

<h2 id="cal">5. Calibration: your alpha peak</h2>
{hw("<p>You close your eyes for 30 seconds. The SDK's <code>CalibrateIndividualNFBQuick</code> finds the frequency "
    "where your alpha rhythm is strongest: the <strong>individual alpha peak frequency (iAPF)</strong>. It returns the "
    "peak and an individual alpha range. A result code tells whether it worked (0 = OK, 1 = too many artifacts, "
    "2 = peak on the edge of the range).</p>",
    "<p>Alpha is strongest with eyes closed, so that is the easiest moment to find its peak. People's alpha peaks "
    "differ (roughly 8–13 Hz) and the SDK tunes its later calculations to yours.</p>",
    f"<p>{tag('v')} Method and the 30-second closed-eyes procedure: SDK documentation page <em>Calibration</em> "
    "(\"CalibrateIndividualNFBQuick will require 1 stage: Closed eyes - 30 sec\") and the vendor's "
    f"<em>Instruction Manual.docx</em>. {tag('l')} The vendor cites Bazanova (2012) and Posthuma et al. (2001) for "
    f"iAPF. Your result: <strong>{cal['iapf']:.1f} Hz</strong> (13:52 session).</p>")}

<h2 id="base">6. Rest baseline (eyes open)</h2>
{hw("<p>You look at a cross for 30–90 seconds. The SDK's Productivity module records your resting levels "
    "(<code>StartBaselineCalibration</code>) and moves on by itself. At the same time, our code stores the median "
    "power of each brain-wave band from the raw EEG; that is the reference for the brain-wave bars.</p>",
    "<p>All scores are relative. \"Attention 70\" only means something compared with how you were at rest.</p>",
    f"<p>{tag('v')} SDK <em>Productivity metrics</em> page and Instruction Manual (\"Immediately after the 30-second window, "
    f"click Calibrate Baseline to set the reference point\"). {tag('d')} Using the same period as the band "
    "reference.</p>")}

<h2 id="psd">7. The SDK spectrum (PSD)</h2>
<p>A <strong>power spectrum</strong> (PSD, power spectral density) splits the signal into frequencies and says how
strong each is. The SDK sends one for each channel about 23 times per second, in <strong>0.1 Hz bins</strong>
from 1.0 to 30.0 Hz: 291 numbers per channel. One <strong>bin</strong> is one 0.1 Hz slice.</p>
{fig(fig_psd_bins(cal["iapf"]), "Illustration: a typical EEG spectrum (falling with frequency, with an alpha bump) and "
     "the vendor band ranges. Right: the individual bins at the theta/alpha border.")}
{hw("<p>The app reads 2 spectra per second. For each band it adds the bins with <code>lo ≤ f &lt; hi</code> "
    "(θ 4.0–6.9: 30 bins; α 7.0–12.9: 60; β 15.0–29.9: 150; high β 20.0–29.9: 100; total 1.0–29.9: 290), divides "
    "each band by the channel's total (relative power), and averages the two channels.</p>",
    "<p>Dividing by the total removes changes in overall loudness (contact getting better or worse), leaving the "
    "balance between rhythms. The \"&lt; hi\" rule stops a border bin from counting twice.</p>",
    f"<p>{tag('v')} Band ranges from the vendor's <em>Metrics API 2024.xlsx</em> (θ 4–7, α 7–12/13, β 15–30 Hz; SMR "
    "13–15 Hz is a separate vendor band) and the SDK's own band edges. We kept them so our ratios match the vendor's "
    f"formulas. {tag('m')} Bin spacing and count read from the SDK. {tag('m')} The SDK filters its signal: "
    "measured on the simulator (white noise in, compare processed with raw), the chart below. The SDK documentation "
    "confirms an \"effective EEG measurement bandwidth set from 4 to 35 Hz\".</p>")}
{fig(fig_sdk_filter(), "How much of each frequency survives the SDK's filter (measured). Below 4 Hz and above 30 Hz "
     "almost nothing is left, so this spectrum cannot show delta or gamma.")}

<h2 id="vendor">8. Attention, Cognitive load, Relaxation (vendor)</h2>
{hw("<p>These three come straight from the SDK's <strong>Emotions</strong> classifier as 0–100 values. Our code only "
    "clips them to 0–100 and shows the median of the last 5 seconds.</p>",
    "<p>The vendor designed and tuned these for this headset. Keeping them lets you compare with the vendor's own "
    "apps.</p>",
    f"<p>{tag('v')} SDK <em>Emotions</em> page (fields attention, relaxation, cognitiveLoad, cognitiveControl, "
    "selfControl). The vendor's <em>Capsule metrics_definitions.xlsx</em> describes them as "
    "<strong>normalised β/α</strong> (attention), <strong>normalised α/β</strong> (relaxation) and "
    "<strong>normalised θ/α</strong> (cognitive load), citing Raufi &amp; Longo (2022) for θ/α "
    f"{tag('l')}. The exact normalisation is not published. {tag('m')} Checked on your first session: the "
    "vendor's raw concentration and relaxation match our β/α and α/β (Spearman ρ = 0.84 and 0.85), but the 0–100 "
    "versions only moderately (ρ ≈ 0.5–0.6).</p>")}
<div class="note warn"><p><strong>Limit.</strong> In the 18:09 session the vendor's cognitive load rose from 42 to 70
while θ/α of the same spectrum fell from 1.10 to 0.79. We cannot see why inside the DLL.</p></div>

<h2 id="stress">9. Stress</h2>
<h3>Step 1: the ratio</h3>
<div class="eq">arousal = relative high β (20–30 Hz) / relative α (7–13 Hz)</div>
{hw("<p>Computed from each SDK spectrum, 2 times per second.</p>",
    "<p>Fast beta rises and alpha falls when you are tense or aroused, so their ratio goes up.</p>",
    f"<p>{tag('l')} High-β relative to α is a common arousal/anxiety marker. But a meta-analysis of stress EEG studies "
    "(Vanhollebeke et al., 2022) found <em>no consistent</em> beta effect and mixed alpha effects, and EEG above ~20 Hz "
    f"contains muscle activity (Whitham et al., 2007). {tag('d')} Using this ratio as the stress score. Treat it as "
    "\"arousal compared with your own normal\", not as a clinical stress measure.</p>")}
<h3>Step 2: the reference, your first 2 minutes of work</h3>
{hw("<p>For the first 120 s of the session (breaks and poor-signal moments do not count) the app stores every ratio "
    "and takes the <strong>median</strong>. The Stress card shows \"Starts in m:ss\" meanwhile.</p>",
    f"<p>{tag('m')} In your 13:52 session the ratio was about {np.nanmedian(s.arousal[(s.ind_t < 0) & (s.ind_t >= s.t_cal - s.t_live)]):.2f} "
    f"while looking at the cross and about 1.1 during screen work. Compared with rest, ordinary work already looked like stress "
    "(the first version showed a stress episode for 3.5 of 4.4 minutes). Looking at a busy screen lowers alpha. "
    "The median ignores single spikes.</p>",
    f"<p>{tag('m')} The mismatch was found in your recording. {tag('l')} Time-on-task studies also compare with "
    f"the start of the task rather than with rest. {tag('d')} The 2-minute length.</p>")}
{fig(fig_arousal_reason(s), "Your 13:52 session: high β / α at rest (grey) was well below its level during work. "
     "The work reference sits in between.")}
<h3>Step 3: ratio to score</h3>
<div class="eq">score = 50 + 50 × tanh( log₂( ratio / reference ) )</div>
{hw("<p>log₂ turns \"double\" into +1 and \"half\" into −1, so rises and falls are symmetric. tanh squeezes any value "
    "into −1…+1, so the score stays within 0–100 and one wild reading cannot jump to the end.</p>",
    "<p>A fixed, simple mapping everyone can check by hand, with 50 always meaning \"same as your reference\".</p>",
    f"<p>{tag('d')} Our own mapping. Check points: ½× → 12, 1× → 50, 1.6× → 80, 2× → 88.</p>")}
{fig(bm.fig_mapping(), "The mapping from ratio to score.")}
<p><strong>Worked example</strong> (13:52 session, 3 minutes in). Relative powers: θ {ex['theta']:.3f},
α {ex['alpha']:.3f}, β {ex['beta']:.3f}, high β {ex['high_beta']:.3f}.</p>
<div class="eq">arousal   = {ex['high_beta']:.3f} / {ex['alpha']:.3f}            = {arousal:.3f}
ratio/ref = {arousal:.3f} / {ref_a:.3f}            = {arousal / ref_a:.3f}
log₂      = {np.log2(arousal / ref_a):.3f}      tanh = {np.tanh(np.log2(arousal / ref_a)):.3f}
score     = 50 + 50 × {np.tanh(np.log2(arousal / ref_a)):.3f}           = {score(arousal, ref_a):.1f}</div>
<h3>Step 4: smoothing and stress episodes</h3>
{hw("<p>The card shows the median of the last <strong>30 s</strong> of scores. A <strong>stress episode</strong> starts "
    "when that stays ≥ 80 for 30 s and ends when it stays &lt; 65 for 30 s. Episodes end when a break starts.</p>",
    f"<p>{tag('m')} On your recording, even 10-second medians of the ratio swing by about ±47% "
    "(standard deviation 0.56 in log₂). The first version's thresholds (70 for 15 s) sat inside that normal wobble. "
    "Different start/end levels (hysteresis) stop an episode flickering on and off.</p>",
    f"<p>{tag('m')} Chosen by replaying your 13:52 recording under several settings: with these, ordinary work "
    f"gives no episode. {tag('d')} Not yet validated against a real stress task (plan.md §6.5).</p>")}
{fig(bm.fig_stress_fix(s), "Stress on the 13:52 recording with the first version (grey) and the current one (orange).")}

<h2 id="fatigue">10. Fatigue</h2>
<div class="eq">fatigue ratio = (relative θ + relative α) / relative β</div>
{hw("<p>Same steps as stress: SDK spectrum → ratio → reference = median of the first 2 minutes of work → "
    "the same 0–100 mapping → median of the last <strong>60 s</strong>.</p>",
    "<p>Slow waves (θ, α) grow relative to β as you tire during a long task. Tiredness builds over minutes, so "
    "a longer smoothing window suits it.</p>",
    f"<p>{tag('v')} The formula (α+θ)/β is the vendor's Fatigue Score (<em>Capsule metrics_definitions.xlsx</em>, citing "
    f"Tyas et al., 2020, and Jap et al., 2009 {tag('l')}). {tag('l')} Theta and alpha rise with time on task "
    f"(Psychophysiology, 2021). {tag('d')} 60 s smoothing and the work reference.</p>")}
<p><strong>Worked example</strong> (same moment):</p>
<div class="eq">ratio  = ({ex['theta']:.3f} + {ex['alpha']:.3f}) / {ex['beta']:.3f} = {fatigue:.3f}
vs ref = {fatigue:.3f} / {ref_f:.3f} = {fatigue / ref_f:.3f}   →   score = {score(fatigue, ref_f):.1f}</div>
<div class="note"><p><strong>Why not the vendor's fatigue?</strong> The SDK also offers "accumulated fatigue". In your
first session it grew at its fastest rate whenever concentration was above 1.7, and your resting concentration was
already 2.2, so it reached 6/10 in 3.3 minutes and asked for a break. It is still saved in
<code>productivity.csv</code> but not used.</p></div>

<h2 id="bands">11. Brain-wave bars (our own spectrum)</h2>
<p>The SDK spectrum has no delta or gamma left (section 7), so this path starts from the <strong>raw</strong>
EEG, which the SDK passes through unfiltered (1–120 Hz according to its documentation).</p>
<h3>Step 1: filter</h3>
{hw("<p>A 2nd-order Butterworth <strong>high-pass at 0.5 Hz</strong> plus a <strong>notch at 50 Hz</strong> (Q = 30), "
    "combined into one filter and run continuously, block by block, keeping the filter's memory between blocks.</p>",
    "<p>The high-pass removes very slow drift (sweat, electrodes settling) while keeping delta (1–4 Hz). The notch "
    "removes hum from the mains wiring, which in India is 50 Hz.</p>",
    f"<p>{tag('l')} Standard IIR designs from SciPy (<code>butter</code>, <code>iirnotch</code>, <code>sosfilt</code>). "
    f"{tag('m')} Earlier raw recordings from these headphones had 50 Hz hum up to 290× stronger than the 40–45 Hz "
    f"level. {tag('m')} Tested: hum reduced by more than 30 dB and does not leak into gamma.</p>")}
{fig(fig_filter_response(), "What the filter keeps (0 dB) and removes, computed from the app's own filter.")}
<h3>Step 2: windows and rejection</h3>
{hw("<p>Every 0.5 s, take the newest 4 s (1000 samples). Skip the window if the SDK flagged an artifact inside it, or "
    "if its peak-to-peak amplitude is more than 4× the median of earlier windows (after the first 8).</p>",
    "<p>Blinks and movements add huge slow waves that would swamp the real ones. A relative threshold is used "
    "because dry electrodes give hundreds of µV even when clean, so a fixed µV limit would reject everything.</p>",
    f"<p>{tag('v')} SDK artifact flags. {tag('d')} 4 s, 0.5 s step, 4× and 8 windows.</p>")}
<h3>Step 3: Welch spectrum</h3>
{fig(fig_welch(), "Welch's method: split the window into overlapping pieces, take a spectrum of each, average them.")}
{hw("<p>Three 2-second segments with 50% overlap, each tapered with a Hann window and linearly detrended, then "
    "averaged. Bin spacing = 1 / 2 s = <strong>0.5 Hz</strong>.</p>",
    "<p>A single spectrum of noisy data jumps around; averaging three is steadier. 2 s segments are the trade-off "
    "between detail (0.5 Hz bins, enough to separate the bands) and steadiness.</p>",
    f"<p>{tag('l')} Welch (1967), implemented by SciPy <code>signal.welch</code>. {tag('d')} Segment and window "
    "lengths.</p>")}
<h3>Step 4: band power</h3>
<div class="eq">band power (µV²) = Σ PSD(f) × Δf   over lo ≤ f &lt; hi,   Δf = 0.5 Hz
δ 1–4 (6 bins) · θ 4–8 (8) · α 8–13 (10) · β 13–30 (34) · γ 30–45 (30)</div>
{hw("<p>The PSD is a density (µV² per Hz); multiplying by the bin width gives power. The two channels are "
    "averaged.</p>",
    "<p>These bands are the textbook ones, so the chart reads like any EEG textbook. γ stops at 45 Hz, below the 50 Hz "
    "hum.</p>",
    f"<p>{tag('l')} Band definitions from the IFCN glossary (Kane et al., 2017). They differ slightly from the vendor "
    "ranges in section 7, which are only used for the stress path.</p>")}
<h3>Step 5: compare with rest</h3>
<div class="eq">bar = ( median power in the last 5 s / median power during the rest baseline − 1 ) × 100 %</div>
{hw("<p>Each band is compared with its <em>own</em> power at rest. +50% = one and a half times, −50% = half.</p>",
    f"<p>{tag('m')} The first version compared each band's <em>share</em> of total power. During your rest baseline "
    f"delta held {100 * rest_share_delta:.0f}% of the power (freshly placed electrodes). As the electrodes settled, "
    "delta shrank and every other band's share rose automatically, so alpha, beta and gamma all showed about +75%.</p>",
    f"<p>{tag('l')} Percent change of band power from a reference period is the standard event-related "
    f"(de)synchronisation measure (Pfurtscheller &amp; Lopes da Silva, 1999). {tag('m')} 5 s smoothing: on your data "
    "the bars then move about 2 points per second.</p>")}
<table><tr><th></th>{"".join(f"<th>{b.title()}</th>" for b in bm.BANDS)}</tr>
<tr><td>Rest (µV²)</td>{"".join(f"<td>{rest_abs[b]:.1f}</td>" for b in bm.BANDS)}</tr>
<tr><td>Session (µV²)</td>{"".join(f"<td>{live_abs[b]:.1f}</td>" for b in bm.BANDS)}</tr>
<tr><td><strong>Bar</strong></td>{"".join(f"<td><strong>{bands_new[b]:+.0f}%</strong></td>" for b in bm.BANDS)}</tr></table>
{fig(bm.fig_bands(s, bands_new, s.meta["summary"].get("bands_change_mean", {})),
     "Your 13:52 session: the first version (grey) against the current one (purple).")}

<h2 id="breaks">12. Breaks and check-ins</h2>
{hw("<p>A break prompt appears when <strong>(A)</strong> 50 minutes pass without a real break, or <strong>(B)</strong> "
    "the fatigue score stays ≥ 70 for 3 minutes in a row after the first 10 minutes. At most one prompt per 10 minutes, "
    "so an ignored prompt repeats. A break must last 2 minutes to restart the 50-minute timer. Nothing is prompted "
    "during a break or for 10 minutes after it, and fatigue measured during a break does not count. Every 10 minutes a "
    "sleepiness check-in (1–9) appears, except during a break.</p>",
    "<p>The timer is a safety net that works even when the EEG cannot see tiredness; the fatigue rule adds a "
    "personal signal. The check-in answers are the ground truth for testing whether the fatigue score works.</p>",
    f"<p>{tag('l')} Karolinska Sleepiness Scale (Åkerstedt &amp; Gillberg, 1990). Research on rest breaks and EEG "
    f"fatigue (Int. J. Psychophysiology 2023; Rest Assured, CHI 2026) motivated regular breaks. {tag('m')} The 2-minute "
    f"minimum: in your session a 1.5-second break had restarted the timer. {tag('d')} 50 min, 70 for 3 min, 10 min "
    "cooldown: common-sense defaults, not yet validated.</p>")}
{fig(bm.fig_breaks(), "Illustration (made-up data) of the two break rules.")}

<h2 id="save">13. Recording</h2>
{hw("<p>Each session gets a folder named by date and time with CSV files (one row per reading) and a "
    "<code>session.json</code> summary: <code>scores.csv</code> at 1 per second, <code>bands.csv</code> at 2 per "
    "second, <code>events.csv</code> for markers, breaks, prompts and episodes, plus the SDK's raw outputs.</p>",
    "<p>Everything on screen can be recomputed and checked later. This explainer's figures are rebuilt from these "
    "files.</p>",
    f"<p>{tag('d')} File layout. Python's <code>csv</code> and <code>json</code> modules.</p>")}

<h2 id="tests">14. Testing</h2>
{hw("<p>80 automated tests (pytest). Unit tests feed made-up signals with known answers; simulator tests run the real "
    "SDK with its simulated devices; a self-test drives the real window through all seven steps.</p>",
    "<p>A known input must give a known output before real brain data is trusted.</p>",
    f"<p>{tag('m')} Examples: white noise must give each band a share equal to its width (within 3%); a pure 10 Hz "
    "tone must be ≥ 95% alpha; the notch must cut 50 Hz by more than 30 dB; slow drift at rest must not move the "
    f"other bands. {tag('v')} The SDK's <em>Noise</em> and <em>SinWave</em> simulated devices.</p>")}

<h2 id="issues">15. Known issues</h2>
<h3>A noisy rest baseline makes every bar negative</h3>
<p>In the 18:09 session the SDK flagged {rej_base} of {n_base} windows during the eyes-open baseline as artifacts,
and the slow waves were several times stronger than a minute later (theta {theta_rest:.0f} µV² at rest against
{theta_live:.0f} µV² in the session). The rest reference was therefore far too high, so during the session every
band read lower (delta −92%, theta −83%, alpha −69%). The amplitude check did not catch it: it learns "normal" from
the first windows, and the signal was already large then.</p>
{fig(fig_noisy_baseline(n), "18:09 session: theta and alpha power over time. The dotted lines are the references "
     "frozen from the rest baseline (grey); the session sits far below them.")}
<p><strong>Proposed fix (not yet built):</strong> check the baseline's quality before accepting it, and repeat it
if more than about 20% is artifact.</p>
<h3>Vendor scores are a black box</h3>
<p>Attention, cognitive load and relaxation cannot be checked step by step (section 8). A possible change is to
replace them with our own β/α and θ/α computed like stress.</p>
<h3>Stress and fatigue are not yet validated</h3>
<p>The thresholds were tuned on short test sessions. The planned check (plan.md §6.5) is mental arithmetic vs rest for
stress, and the sleepiness check-ins vs the fatigue score over long sessions.</p>

<h2 id="params">16. All numbers at a glance</h2>
<table>
<tr><th>Setting</th><th>Value</th><th>From where</th></tr>
<tr><td>Channels, sample rate</td><td>A1-C3, A2-C4 bipolar, 250 Hz</td><td>{tag("v")}</td></tr>
<tr><td>Contact grades</td><td>Good &lt; 500 kΩ, Fair ≤ 1 MΩ, held 5 s</td><td>{tag("v")} thresholds, {tag("d")} 5 s</td></tr>
<tr><td>Calibration</td><td>30 s eyes closed, Quick iAPF</td><td>{tag("v")}</td></tr>
<tr><td>SDK spectrum</td><td>0.1 Hz bins, 1–30 Hz, read 2×/s</td><td>{tag("v")} {tag("m")}</td></tr>
<tr><td>Vendor bands (stress path)</td><td>θ 4–7, α 7–13, β 15–30, high β 20–30 Hz</td><td>{tag("v")}</td></tr>
<tr><td>Stress ratio</td><td>high β / α</td><td>{tag("l")} {tag("d")}</td></tr>
<tr><td>Fatigue ratio</td><td>(θ + α) / β</td><td>{tag("v")} {tag("l")}</td></tr>
<tr><td>Reference</td><td>median of first 120 s of work</td><td>{tag("m")} {tag("d")}</td></tr>
<tr><td>Score mapping</td><td>50 + 50·tanh(log₂(ratio/ref))</td><td>{tag("d")}</td></tr>
<tr><td>Smoothing</td><td>vendor scores 5 s, stress 30 s, fatigue 60 s, bars 5 s</td><td>{tag("m")} {tag("d")}</td></tr>
<tr><td>Stress episode</td><td>≥ 80 for 30 s, ends &lt; 65 for 30 s</td><td>{tag("m")} {tag("d")}</td></tr>
<tr><td>Level words</td><td>Low &lt; 35 ≤ Moderate &lt; 65 ≤ High</td><td>{tag("d")}</td></tr>
<tr><td>Raw filter</td><td>0.5 Hz high-pass (order 2), 50 Hz notch (Q 30)</td><td>{tag("l")} {tag("m")}</td></tr>
<tr><td>Welch</td><td>4 s window, 2 s Hann segments, 50% overlap, every 0.5 s</td><td>{tag("l")} {tag("d")}</td></tr>
<tr><td>Rejection</td><td>SDK artifact, or peak-to-peak &gt; 4× median</td><td>{tag("v")} {tag("d")}</td></tr>
<tr><td>Textbook bands (bars)</td><td>δ 1–4, θ 4–8, α 8–13, β 13–30, γ 30–45 Hz</td><td>{tag("l")}</td></tr>
<tr><td>Break prompt</td><td>50 min, or fatigue ≥ 70 for 3 min after 10 min; 10 min cooldown; break ≥ 2 min</td><td>{tag("d")} {tag("m")}</td></tr>
<tr><td>Check-in</td><td>KSS 1–9 every 10 min</td><td>{tag("l")}</td></tr>
</table>

<h2 id="check">17. Check yourself</h2>
<p>Try to answer from memory before looking at the answers below. If one is hard, reread the section in brackets.</p>
<ol>
<li>Why can't the brain-wave bars use the SDK's spectrum? (7, 11)</li>
<li>The SDK spectrum has 0.1 Hz bins. How many bins does the alpha band (7–13 Hz) add up, and why is the 13.0 Hz bin
not one of them? (7)</li>
<li>A ratio is 1.5× your reference. Without a calculator, is the score above or below 80? (9)</li>
<li>Why is stress compared with your first 2 minutes of work and not with the eyes-open rest? (9)</li>
<li>Our Welch segments are 2 s long. What bin spacing does that give, and what would 4 s segments give? (11)</li>
<li>Delta drops by half while the other bands stay the same. What would the old share-based chart have shown for
alpha, roughly? What does the current chart show? (11)</li>
<li>You take a 90-second break at minute 45. When does the 50-minute prompt come? (12)</li>
<li>Which three numbers on screen can you <em>not</em> recompute by hand from the saved data, and why? (8)</li>
</ol>
<h3>Answers</h3>
<ol class="small">
<li>The SDK filters its signal to about 4–30 Hz before computing the spectrum, so almost no delta (gain 0.004 at
1–2 Hz) or gamma is left.</li>
<li>60 bins (7.0, 7.1 … 12.9). The rule is lo ≤ f &lt; hi, so 13.0 is outside; that keeps a border bin from
counting in two bands.</li>
<li>Below. 1.6× gives 80, so 1.5× gives a little less: log₂ 1.5 = 0.585, tanh = 0.526, score ≈ 76.</li>
<li>Looking at a busy screen lowers alpha, so high β / α is higher during any screen work than at rest. Compared with
rest, ordinary work already looked like stress (first session: an "episode" for 3.5 of 4.4 minutes).</li>
<li>1 / 2 s = 0.5 Hz. 4 s segments would give 0.25 Hz bins, but only one segment would fit in the 4 s window, so the
spectrum would be much noisier.</li>
<li>If delta was most of the power (say 75%), halving it makes the total smaller, so every other band's share rises
by roughly half (about +60%). The current chart compares each band with its own rest power: alpha 0%.</li>
<li>At minute 50. 90 s is shorter than the 2-minute minimum, so the timer was not restarted. (A 2-minute break would
have moved it to about minute 97.)</li>
<li>Attention, Cognitive load and Relaxation. They come from the vendor's closed Emotions classifier, whose
normalisation is not published.</li>
</ol>

<h2 id="refs">18. Sources</h2>
<h3>Vendor (in <code>D:\\trainsvm\\hardware\\eeg_headphones\\Capsule_2.0.59</code>)</h3>
<ul>
<li>Capsule API documentation, <code>CapsuleAPI/Docs/html</code>: <em>Devices modes</em> (resistance thresholds, bipolar
mode), <em>Calibration</em> (Quick iAPF), <em>Productivity metrics</em>, <em>Emotions</em>, <em>PSD</em>,
<em>Raw and raw filtered signal</em> (1–120 Hz raw, 4–35 Hz filtered).</li>
<li><em>Capsule metrics_definitions.xlsx</em> and <em>Metrics API 2024.xlsx</em>: metric formulas, band ranges and the
studies the vendor cites.</li>
<li><em>Instruction Manual.docx</em>: calibration and baseline procedure.</li>
</ul>
<h3>Published work</h3>
<ul>
<li>Kane N. et al. (2017). A revised glossary of terms most commonly used by clinical electroencephalographers. IFCN. <em>Clin. Neurophysiol. Practice</em>.</li>
<li>Vanhollebeke G. et al. (2022). The neural correlates of psychosocial stress: a systematic review and meta-analysis of spectral analysis EEG studies. <em>Neurobiology of Stress</em>.</li>
<li>Whitham E.M. et al. (2007). Scalp electrical recording during paralysis: EEG frequencies above 20 Hz are contaminated by EMG. <em>Clin. Neurophysiol.</em></li>
<li>Raufi B., Longo L. (2022). An evaluation of the EEG alpha-to-theta and theta-to-alpha band ratios as indexes of mental workload. <em>Front. Neuroinform.</em></li>
<li>Pfurtscheller G., Lopes da Silva F.H. (1999). Event-related EEG/MEG synchronization and desynchronization: basic principles. <em>Clin. Neurophysiol.</em></li>
<li>Welch P. (1967). The use of the fast Fourier transform for the estimation of power spectra. <em>IEEE Trans. Audio Electroacoustics</em>.</li>
<li>Åkerstedt T., Gillberg M. (1990). Subjective and objective sleepiness in the active individual. <em>Int. J. Neuroscience</em>.</li>
<li>Time-on-task EEG: <em>Psychophysiology</em> (2021), doi:10.1111/psyp.13805.</li>
<li>Rest breaks: <em>Int. J. Psychophysiology</em> (2023), S0167876023000612; Schick L. et al. (2026) Rest Assured, CHI '26.</li>
<li>Vendor-cited: Tyas et al. (2020), Jap et al. (2009) for fatigue; Bazanova (2012), Posthuma et al. (2001) for iAPF.</li>
</ul>
<h3>Software</h3>
<p>Capsule SDK 2.0.40 (via ctypes), NumPy, SciPy (<code>butter</code>, <code>iirnotch</code>, <code>tf2sos</code>,
<code>sosfilt</code>, <code>welch</code>), Matplotlib, customtkinter, pytest. Code: <code>cogscore/metrics.py</code>
(stress path), <code>cogscore/spectral.py</code> (bands path), <code>cogscore/rules.py</code> (breaks, episodes),
<code>cogscore/config.py</code> (every number above).</p>
"""
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>How It Works</title><style>{bm.CSS}{EXTRA_CSS}</style></head><body><main>{body}</main>"
            f"</body></html>")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    return out


def main():
    out = build(os.path.join(HERE, "how_it_works.html"))
    print(f"html: {out}")
    print(f"pdf: {bm.to_pdf(out)}")


if __name__ == "__main__":
    main()
