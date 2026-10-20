"""Colours and fonts. Chart colours follow the dataviz reference palette (dark mode);
the series slots used here pass validate_palette.js on surface #1a1a19."""
import matplotlib

PAGE = "#0d0d0d"             # window background
SIDEBAR = "#141413"
SURFACE = "#1a1a19"          # cards and chart surface
RAISED = "#232321"           # inputs, hover
INK = "#ffffff"
INK_2 = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"
BORDER = "#2c2c2a"

# Categorical slots in fixed order (identity, not meaning).
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9"]
METRIC_COLOURS = {"attention": SERIES[0], "stress": SERIES[1], "cognitive_load": SERIES[2]}
BAND_COLOUR = SERIES[6]      # one hue for the band chart; bands are named on the axis

# Status colours are reserved for state and always shown with a text label or icon.
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
GRADE_COLOURS = {"good": GOOD, "average": WARNING, "bad": CRITICAL}
GRADE_LABELS = {"good": "Good", "average": "Fair", "bad": "Poor"}

ACCENT = SERIES[0]
FONT = "Segoe UI"


def font(size=14, weight="normal"):
    import customtkinter as ctk
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def style_matplotlib():
    matplotlib.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": MUTED, "axes.grid": True, "axes.axisbelow": True,
        "grid.color": GRID, "grid.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.major.size": 0, "ytick.major.size": 0,
        "text.color": INK_2, "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9,
        "lines.linewidth": 2.0, "legend.frameon": False, "legend.labelcolor": INK_2,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    })
