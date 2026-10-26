"""Builds docs/MI_Live_User_Guide.pdf (the MI Live user guide).
    C:\\Python313\\python.exe docs\\build_user_guide.py            (from apps/mi_live)
Needs reportlab. Text is plain Latin-1 so the built-in fonts render everything."""
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "MI_Live_User_Guide.pdf"

INK = colors.HexColor("#1d2733")
MUTED = colors.HexColor("#5b6672")
ACCENT = colors.HexColor("#2f6fb3")
LEFTC = colors.HexColor("#4a90d9")
RIGHTC = colors.HexColor("#e8962e")
GOOD = colors.HexColor("#2e9e5b")
BAD = colors.HexColor("#d64545")
WARN = colors.HexColor("#c9a227")
PALE = colors.HexColor("#eef2f6")
LINE = colors.HexColor("#c8d0d9")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=21,
                    textColor=INK, spaceBefore=4, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                    textColor=ACCENT, spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                    textColor=INK, spaceBefore=6, spaceAfter=2)
B = ParagraphStyle("B", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.6, leading=13.4, textColor=INK,
                   spaceAfter=4)
SMALL = ParagraphStyle("S", parent=B, fontSize=8.4, leading=11, textColor=MUTED)
CELL = ParagraphStyle("C", parent=B, fontSize=8.8, leading=11.4, spaceAfter=0)
CELLB = ParagraphStyle("CB", parent=CELL, fontName="Helvetica-Bold")
BUL = ParagraphStyle("BU", parent=B, leftIndent=12, bulletIndent=2, spaceAfter=2)
NUM = ParagraphStyle("NU", parent=B, leftIndent=16, bulletIndent=0, spaceAfter=3)
CODE = ParagraphStyle("CO", parent=B, fontName="Courier", fontSize=8.6, leading=11, backColor=PALE,
                      borderPadding=(4, 5, 4, 5), spaceBefore=3, spaceAfter=7)


def P(t, st=B):
    return Paragraph(t, st)


def bullets(items, st=BUL):
    return [Paragraph(t, st, bulletText="-") for t in items]


def steps(items):
    return [Paragraph(t, NUM, bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def table(rows, widths, header=True, zebra=True, bold_first_col=False):
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c, v in enumerate(row):
            st = CELLB if (header and r == 0) or (bold_first_col and c == 0) else CELL
            cells.append(Paragraph(v, st) if isinstance(v, str) else v)
        data.append(cells)
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), PALE), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK)]
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f8fafc")))
    t.setStyle(TableStyle(style))
    return t


def box(title, flow, color=ACCENT):
    inner = [Paragraph(f"<b>{title}</b>", ParagraphStyle("bt", parent=B, textColor=color))] + flow
    t = Table([[inner]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.9, color), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


# ------------------------------------------------------------------ diagrams
def flow_diagram():
    """The session flow: 5 boxes with arrows."""
    W, H = 170 * mm, 30 * mm
    d = Drawing(W, H)
    labels = [("Connect", "Scan + Connect"), ("1 Signal check", "15 s, GOOD?"),
              ("2 Calibrate", "3-4 calm blocks"), ("Your model", "trained by itself"),
              ("3 Cued test", "CONFIRMED?"), ("4 Free mode", "drive the bot")]
    n = len(labels)
    gap = 4 * mm
    bw = (W - gap * (n - 1)) / n
    for i, (a, b) in enumerate(labels):
        x = i * (bw + gap)
        fill = colors.HexColor("#e7f0fa") if i not in (3,) else colors.HexColor("#eef7ee")
        d.add(Rect(x, 6 * mm, bw, 18 * mm, rx=3, ry=3, fillColor=fill, strokeColor=ACCENT, strokeWidth=0.8))
        d.add(String(x + bw / 2, 17 * mm, a, fontName="Helvetica-Bold", fontSize=8.2, fillColor=INK,
                     textAnchor="middle"))
        d.add(String(x + bw / 2, 11 * mm, b, fontName="Helvetica", fontSize=6.8, fillColor=MUTED,
                     textAnchor="middle"))
        if i < n - 1:
            x1 = x + bw + 0.6 * mm
            x2 = x + bw + gap - 0.6 * mm
            d.add(Line(x1, 15 * mm, x2 - 1.2 * mm, 15 * mm, strokeColor=INK, strokeWidth=0.8))
            d.add(Polygon([x2, 15 * mm, x2 - 1.6 * mm, 16 * mm, x2 - 1.6 * mm, 14 * mm], fillColor=INK,
                          strokeColor=INK))
    return d


def window_diagram():
    """Sketch of the main window with lettered areas."""
    W, H = 170 * mm, 112 * mm
    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=colors.HexColor("#0f1317"), strokeColor=INK))

    def area(x, y, w, h, letter, label, fill="#1a2027"):
        d.add(Rect(x * mm, y * mm, w * mm, h * mm, fillColor=colors.HexColor(fill), strokeColor=colors.HexColor("#3a4552")))
        d.add(String((x + 2) * mm, (y + h - 4.2) * mm, letter, fontName="Helvetica-Bold", fontSize=9,
                     fillColor=colors.HexColor("#ffd25c")))
        d.add(String((x + 7) * mm, (y + h - 4.2) * mm, label, fontName="Helvetica", fontSize=6.8,
                     fillColor=colors.HexColor("#c9ced6")))

    area(2, 103, 166, 7, "A", "Subject  |  Model list  |  Scan  Connect  Disconnect", "#0f1317")
    area(2, 95, 166, 7, "B", "status line (yellow)  +  live numbers: EEG uV, artifacts, samples/s", "#0f1317")
    area(2, 60, 113, 34, "C", "left/right bar  (L  <-----|----->  R),  cross + arrow in a feedback test")
    # bar inside C
    d.add(Line(58.5 * mm, 64 * mm, 58.5 * mm, 88 * mm, strokeColor=colors.HexColor("#7b8794")))
    d.add(Rect(58.5 * mm, 72 * mm, 26 * mm, 8 * mm, fillColor=RIGHTC, strokeColor=None))
    d.add(String(6 * mm, 74 * mm, "L", fontName="Helvetica-Bold", fontSize=11, fillColor=LEFTC))
    d.add(String(109 * mm, 74 * mm, "R", fontName="Helvetica-Bold", fontSize=11, fillColor=RIGHTC))
    area(2, 37, 113, 22, "D", "trace of the last 10 s (hidden when 'calm display' is ticked)")
    area(117, 37, 51, 57, "E", "command + on-screen bot")
    d.add(String(142.5 * mm, 80 * mm, "RIGHT", fontName="Helvetica-Bold", fontSize=13, fillColor=RIGHTC,
                 textAnchor="middle"))
    d.add(Polygon([142 * mm, 62 * mm, 138 * mm, 54 * mm, 146 * mm, 54 * mm], fillColor=RIGHTC, strokeColor=None))
    area(2, 21, 166, 15, "F", "buttons: 1 Signal check | 2 Calibrate | Retrain | 3 Cued test | sliders | UDP / Serial", "#0f1317")
    area(2, 2, 118, 18, "G", "messages and results (signal check, model report, test result)")
    area(122, 2, 46, 18, "H", "kappa over time")
    return d


def trial_diagram():
    """One trial on the calm screen (time line)."""
    W, H = 170 * mm, 50 * mm
    d = Drawing(W, H)
    x0, x1 = 8 * mm, 162 * mm
    tmax = 9.5
    X = lambda t: x0 + (x1 - x0) * t / tmax  # noqa: E731
    y = 16 * mm
    d.add(Line(x0, y, x1, y, strokeColor=INK, strokeWidth=0.8))
    for t in range(0, 10):
        d.add(Line(X(t), y - 1.3 * mm, X(t), y + 1.3 * mm, strokeColor=INK, strokeWidth=0.6))
        d.add(String(X(t), y - 5 * mm, f"{t} s", fontName="Helvetica", fontSize=7, fillColor=MUTED, textAnchor="middle"))

    def seg(a, b, row, text, fill):
        yy = y + (4 + row * 8.5) * mm
        d.add(Rect(X(a), yy, X(b) - X(a), 6.5 * mm, fillColor=fill, strokeColor=None, rx=1.5, ry=1.5))
        d.add(String((X(a) + X(b)) / 2, yy + 2.1 * mm, text, fontName="Helvetica", fontSize=7, fillColor=INK,
                     textAnchor="middle"))

    seg(0, 7.0, 0, "cross on the screen - keep your eyes on it", colors.HexColor("#dfe6ee"))
    seg(3.0, 4.25, 1, "arrow on the cross", colors.HexColor("#ffe2b8"))
    seg(3.0, 7.0, 2, "IMAGINE the squeeze (hands still)", colors.HexColor("#d7ecd9"))
    seg(7.0, 9.5, 0, "blank: relax, blink", colors.HexColor("#f4f4f4"))
    d.add(String(X(0) + 1 * mm, y + 30.5 * mm, "beep", fontName="Helvetica-Bold", fontSize=7.5, fillColor=ACCENT,
                 textAnchor="middle"))
    d.add(Line(X(0), y + 29.5 * mm, X(0), y + 2 * mm, strokeColor=ACCENT, strokeDashArray=[2, 2]))
    d.add(String(X(5.25), y - 10.5 * mm, "the decoder is scored on 1.5 - 4.0 s after the arrow (4.5 - 7 s here)",
                 fontName="Helvetica-Oblique", fontSize=7, fillColor=MUTED, textAnchor="middle"))
    return d


def pipeline_diagram():
    W, H = 170 * mm, 30 * mm
    d = Drawing(W, H)
    boxes = ["headset\nA1 C3 C4 A2", "C3-A1\nC4-A2", "50 Hz\nnotch", "9 bands\n4-40 Hz", "2 s\ncovariance",
             "alignment\n(today's mean)", "CSP + SVM\n-> d", "2 s smooth\n-> v", "command\nL / R / STOP"]
    n = len(boxes)
    gap = 2.4 * mm
    bw = (W - gap * (n - 1)) / n
    for i, t in enumerate(boxes):
        x = i * (bw + gap)
        d.add(Rect(x, 6 * mm, bw, 18 * mm, rx=2.5, ry=2.5, fillColor=colors.HexColor("#f2f5f9"),
                   strokeColor=ACCENT, strokeWidth=0.7))
        a, b = t.split("\n")
        d.add(String(x + bw / 2, 16.5 * mm, a, fontName="Helvetica-Bold", fontSize=6.6, fillColor=INK, textAnchor="middle"))
        d.add(String(x + bw / 2, 11.5 * mm, b, fontName="Helvetica", fontSize=6.2, fillColor=MUTED, textAnchor="middle"))
        if i < n - 1:
            xa, xb = x + bw + 0.3 * mm, x + bw + gap - 0.3 * mm
            d.add(Polygon([xb, 15 * mm, xa, 16.3 * mm, xa, 13.7 * mm], fillColor=INK, strokeColor=INK))
    d.add(String(W / 2, 1.5 * mm, "one new output every 40 ms (25 per second); everything uses only past samples",
                 fontName="Helvetica-Oblique", fontSize=7, fillColor=MUTED, textAnchor="middle"))
    return d


# ------------------------------------------------------------------ page decoration
def on_page(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    if doc.page > 1:
        c.drawString(20 * mm, 12 * mm, "MI Live - User Guide")
        c.drawRightString(190 * mm, 12 * mm, f"page {doc.page}")
        c.setStrokeColor(LINE)
        c.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    c.restoreState()


def build():
    s = []
    # ================================================================== title
    s += [Spacer(1, 55 * mm),
          P("MI Live", ParagraphStyle("T", parent=H1, fontSize=34, leading=40, alignment=TA_CENTER)),
          P("Control a bot by imagining left or right hand movement",
            ParagraphStyle("ST", parent=B, fontSize=13, leading=17, alignment=TA_CENTER, textColor=MUTED)),
          Spacer(1, 10 * mm),
          P("User guide - what each step does and how to use it",
            ParagraphStyle("ST2", parent=B, fontSize=11, alignment=TA_CENTER)),
          Spacer(1, 70 * mm),
          P("EEG motor-imagery project (D:\\trainsvm, apps/mi_live)<br/>Headset: Neiry / Capsule LEHeadPhones2 "
            "(C3, C4, A1, A2 at 250 Hz)<br/>Version of 26 October 2026",
            ParagraphStyle("F", parent=SMALL, alignment=TA_CENTER, fontSize=9, leading=13)),
          PageBreak()]

    # ================================================================== 1 overview
    s += [P("1. What MI Live is", H1),
          P("When you <b>imagine</b> squeezing your left or right hand, the brain rhythms over the motor area on the "
            "<b>opposite</b> side become weaker for a few seconds (mu 8-13 Hz and beta 13-30 Hz). Imagining the left "
            "hand weakens them at C4 (right side of the head); imagining the right hand weakens them at C3. This is "
            "called <b>ERD</b> (event-related desynchronisation). MI Live measures C3 and C4 with the headphones, "
            "decides 25 times a second whether the pattern looks more like LEFT or RIGHT, and turns that into a bot "
            "command: <b>LEFT</b>, <b>RIGHT</b> or <b>STOP</b>."),
          P("Two kinds of models are used. A <b>base model</b> trained on BCI Competition IV dataset 2b (9 people, "
            "recorded in Graz in 2008, downloaded) works for a new person without any training, but less well on our "
            "dry headset. Your <b>own model</b> is trained from your calibration and usually suits you better. "
            "The app tells you honestly whether a model really works for you before you rely on it."),
          P("The whole session", H2), flow_diagram(), Spacer(1, 3 * mm),
          P("What you need", H2),
          table([["Item", "Details"],
                 ["Headset", "Neiry / Capsule headphones (LEHeadPhones2, shown as USAMS-YX05), charged"],
                 ["Laptop", "Windows with Bluetooth, <b>running on battery</b> (the charger adds 50 Hz hum)"],
                 ["Software", "C:\\Python313\\python.exe with numpy, scipy, scikit-learn, sounddevice (installed). "
                              "The app folder is D:\\trainsvm\\apps\\mi_live"],
                 ["Time", "about 25-30 minutes for a full session (check, calibration, test, free mode)"],
                 ["Optional bot", "Arduino 2-wheel bot over USB / Bluetooth serial, or any device on Wi-Fi (UDP)"]],
                [32, 138]),
          P("Start the app", H2),
          table([["Double-click", "What it opens"],
                 ["run.bat", "the real app with the headphones"],
                 ["run_simulator.bat", "practice without a headset: hold the Left / Right arrow keys to 'imagine'"],
                 ["run_demo_2b.bat", "a demo with real competition EEG (person B04) played as if live - shows what a "
                                     "working BCI looks like (about 95 % correct)"]],
                [40, 130]),
          PageBreak()]

    # ================================================================== 2 quick start
    s += [P("2. Quick start (one page)", H1),
          box("Before you sit down", bullets([
              "Unplug the laptop charger. Put the laptop where you can see it without turning your head.",
              "Put the headphones on the right way round (L on the left ear). Press the C3 / C4 pads onto the scalp "
              "(part the hair under them) and make sure the ear clips touch skin.",
              "Close other programs that use the headset (mi_bci, the Capsule app). Only one program can connect."])),
          Spacer(1, 4 * mm)]
    s += steps([
        "<b>Start:</b> double-click <b>run.bat</b>. Type your name in <b>Subject</b> (always the same spelling).",
        "<b>Connect:</b> press <b>Scan</b> (8 s), choose the headphones, press <b>Connect</b>. Wait about 10 seconds.",
        "<b>1. Signal check:</b> sit still for 15 s. Repeat until it says <font color='#2e9e5b'><b>GOOD</b></font>; "
        "follow its advice if it says FAIR or BAD.",
        "<b>2. Calibrate:</b> a black full screen opens. Press <b>Space</b>, look at the cross, and when the small "
        "arrow appears <b>imagine</b> squeezing that hand until the cross disappears. 3-4 blocks, Space between "
        "blocks. Your model is trained automatically at the end (about 1 minute).",
        "<b>Read the model report</b> in the message box: PROMISING or NOT READY.",
        "<b>3. Cued test:</b> same calm screen, new trials. If it says <b>CONFIRMED</b>, your model is READY.",
        "<b>4. Free mode:</b> just imagine left or right. The big word and the bot follow after about 2-4 seconds.",
        "<b>Finish:</b> close the window (the bot gets STOP and the headset disconnects)."])
    s += [Spacer(1, 3 * mm),
          box("Keys", [table([["Space", "start the next block on the calm screen"],
                              ["Esc", "stop the running test or calibration (what was recorded is kept)"],
                              ["Left / Right arrow", "simulator only: pretend to imagine left / right"]],
                             [40, 122], header=False, zebra=False)], color=MUTED),
          PageBreak()]

    # ================================================================== 3 the window
    s += [P("3. The main window", H1), window_diagram(), Spacer(1, 3 * mm),
          table([["Area", "What it shows / does"],
                 ["A", "<b>Subject</b>: your name - recordings and models are kept per name. <b>Model</b>: which model "
                       "decodes now (newest of yours first; the base 2b model at the top). <b>Scan / Connect / "
                       "Disconnect</b> for the headphones."],
                 ["B", "Yellow status line: what the app is doing or what to do next. Grey line: EEG strength at C3 and "
                       "C4 (uV), % of outputs flagged as artifacts, raw output d and smoothed output v, alignment state "
                       "and samples per second (should be about 250)."],
                 ["C", "The left/right bar. It grows to the left or right with the smoothed output v (from -1 = all "
                       "left to +1 = all right). The dashed lines are the threshold. During a test with feedback the "
                       "bar turns green when it points to the cued side and red when not."],
                 ["D", "The last 10 seconds of output. Hidden while 'calm display' is ticked (default), because a "
                       "jittering line pulls the eyes and attention."],
                 ["E", "The command sent to the bot (LEFT / RIGHT / STOP / FORWARD, or TEST / CHECK / TRAINING / "
                       "NO DATA) and the on-screen bot that obeys it. 'Reset bot' puts it back in the middle."],
                 ["F", "The step buttons and settings (see sections 4 to 8)."],
                 ["G", "Messages: signal check numbers and advice, your model report, every test trial and the test "
                       "result."],
                 ["H", "Kappa over time after the cue for the last test (the competition score; section 7)."]],
                [12, 158]),
          PageBreak()]

    # ================================================================== 4 connect + signal check
    s += [P("4. Connect and Signal check", H1),
          P("Connect", H2),
          P("<b>Scan</b> searches Bluetooth for 8 seconds; pick the headphones and press <b>Connect</b>. The app starts "
            "the 250 Hz EEG stream. Give it about 10 s: dry electrodes need a moment to settle. If nothing is found, "
            "check that the headphones are on and charged, that Bluetooth is on, and that no other program is "
            "connected to them."),
          P("Step 1 - Signal check (15 s)", H2),
          P("<b>What you do:</b> press the button and sit still with your eyes open on the screen, jaw relaxed."),
          P("<b>What it does:</b> it records 15 s of C3-A1 and C4-A2 and measures:"),
          table([["Measure", "Meaning", "Good value"],
                 ["EEG 8-30 Hz (uV)", "strength of the brain rhythms the decoder uses", "about 3 - 40 uV"],
                 ["50 Hz hum (uV)", "mains electricity picked up by loose contact or the charger. Hum is much bigger "
                                    "than EEG and can leak into the decoder", "below 10 uV (GOOD)"],
                 ["Peak-to-peak", "big jumps from movement, jaw clenching, cable pulls", "below 1500 uV"],
                 ["Alpha peak", "the frequency of the strongest 7-14 Hz rhythm (just information)", "about 8-12 Hz"]],
                [34, 96, 40]),
          Spacer(1, 2 * mm),
          table([["Verdict", "What to do"],
                 ["<font color='#2e9e5b'><b>GOOD</b></font>", "go on to Calibrate."],
                 ["<font color='#c9a227'><b>FAIR</b></font>", "usable, but improve contact if you can and check again."],
                 ["<font color='#d64545'><b>BAD</b></font>", "fix first: unplug the charger, press the named pad and its "
                                                             "ear clip firmly onto skin, move away from cables and "
                                                             "power bricks, keep still. Then check again. The app warns "
                                                             "you if you try to calibrate on a BAD signal."]],
                [24, 146]),
          Spacer(1, 2 * mm),
          box("Why this matters", [P("On the first evening the hum at C3 was 54-69 uV while the EEG was only 6-8 uV, "
                                     "so the decoder mostly saw electricity, not the brain. After fixing the contact "
                                     "and unplugging the charger it was 2-4 uV. No model can work on a BAD signal.",
                                     B)], color=WARN),
          PageBreak()]

    # ================================================================== 5 calibration
    s += [P("5. Step 2 - Calibration on the calm screen", H1),
          P("A separate black window fills the screen. It shows only a cross and, for about one second, a small "
            "arrow on the cross. Nothing moves, there are no numbers and no feedback, so nothing distracts you. Left "
            "and right trials are mixed in random order (never more than 3 of the same in a row)."),
          P("One trial", H2), trial_diagram(), Spacer(1, 1 * mm),
          table([["Time", "Screen", "What you do"],
                 ["0 s", "cross + beep", "look at the centre of the cross and stay still"],
                 ["3 s", "small arrow on the cross (1.25 s)", "start <b>imagining</b> squeezing the hand it points to"],
                 ["3 - 7 s", "cross only", "keep imagining a strong, slow squeeze you can feel; hands, face, eyes still"],
                 ["7 - 9.5 s", "empty", "stop, relax, blink, swallow"]],
                [20, 55, 95]),
          P("Blocks", H2),
          P("Choose the number of <b>blocks</b> (default 3, recommended 3-4) and <b>trials per hand</b> per block "
            "(default 10, so 20 trials, about 3 minutes per block). Between blocks the screen says 'Block k done': "
            "rest, move, and press <b>Space</b> when ready. <b>Esc</b> stops; finished blocks are kept."),
          P("Tick <b>+ real-squeeze warm-up block</b> to start with one block where you <b>really</b> squeeze "
            "(a firm fist). Real movement gives a much stronger pattern than imagination; it is a check that the "
            "electrodes see your hands at all and on the correct side. It is not used to train the imagery model."),
          box("How to imagine well", bullets([
              "Imagine the <b>feeling</b> of squeezing (pressure in the fingers, tension in the forearm), not a picture "
              "of a hand.",
              "Use the same imagery every time; a slow, strong squeeze held for the whole 4 seconds.",
              "Keep your eyes on the cross. Eye movements are picked up strongly by the ear clips and can fool the "
              "decoder.",
              "Do not move the hands, jaw or shoulders. Blink in the empty pause, not during the trial."])),
          P("What happens inside", H2),
          *bullets([
              "Each block is saved as its own recording in D:\\trainsvm\\data\\mi_bci\\&lt;Subject&gt;\\ "
              "(eeg.csv, events.csv, outputs.csv, run.json). The older mi_bci app can use them too.",
              "At the start of calibration the alignment is restarted, so the first unsettled seconds after "
              "connecting are not used.",
              "When the last block ends, your model is trained automatically (next section)."]),
          PageBreak()]

    # ================================================================== 6 your model
    s += [P("6. Your model (trained automatically)", H1),
          P("After calibration, MI Live trains 9 candidate models and picks the best one. It uses all of today's "
            "cued runs of this subject (tick <b>use all days</b> to include earlier days). Runs whose signal was BAD "
            "are left out and listed in the report. <b>Retrain my model</b> does the same at any time."),
          table([["", "2b only", "2b + yours", "yours only"],
                 ["filter-bank CSP + SVM (9 bands, 4-40 Hz)", "x", "x", "x"],
                 ["CSP + SVM (8-30 Hz)", "x", "x", "x"],
                 ["log power + SVM (8-30 Hz)", "x", "x", "x"]],
                [80, 30, 30, 30]),
          P("'2b only' does not use your data; '2b + yours' gives your trials together the same weight as all 2b "
            "trials; 'yours only' ignores 2b.", SMALL),
          P("How it is scored: leave-one-run-out", H2),
          P("Each candidate is trained on all your runs except one, and tested on the run it never saw; this is "
            "repeated for every run. The score is the share of trials decided correctly (decision = the average "
            "sign of the outputs 1.5-4.0 s after the arrow). Because 9 candidates are tried, the best one could look "
            "good by luck, so its p-value is multiplied by 9."),
          P("Reading the report", H2),
          table([["Line", "Meaning"],
                 ["left out: ...", "runs not used because the signal was BAD"],
                 ["left/right pattern (ERD) mu / beta", "is the expected opposite-side drop present in your data? "
                                                        "PRESENT (p &lt; 0.05) is a very good sign"],
                 ["list of 9 candidates", "accuracy on runs never seen, with the binomial p (chance = 50 %)"],
                 ["CHOSEN", "the best candidate; it is fitted on all your runs and used from now on"],
                 ["VERDICT", "<b>PROMISING</b>: above chance after the x9 correction (and at least 60 %). "
                             "<b>NOT READY</b>: not distinguishable from guessing yet"]],
                [55, 115]),
          box("PROMISING is not yet READY", [P(
              "A model only becomes <b>READY</b> when a cued test on <b>new</b> trials is also above chance. On the "
              "first evening a model scored 65 % in leave-one-run-out but only 4/20 on the next run, so the extra "
              "confirmation step was added.", B)], color=WARN),
          P("Your models are saved in data\\mi_bci\\&lt;Subject&gt;\\decoders_live\\ and appear in the Model list as "
            "'YOURS date: name (score, verdict)'. The newest is selected automatically after training.", SMALL),
          PageBreak()]

    # ================================================================== 7 cued test
    s += [P("7. Step 3 - Cued test", H1),
          P("The honest check. It uses the same calm full screen and the same trial timing as the calibration, with "
            "new random trials, and the model currently selected. Set <b>trials/hand</b> (10 is a good minimum; more "
            "trials give a surer answer). By default there is no feedback; tick <b>show feedback bar</b> for a "
            "Graz-style test in the main window where the bar shows the decoder during each trial."),
          P("The result in the message box", H2),
          table([["Line", "Meaning"],
                 ["Trial k: cued LEFT -> decoded LEFT OK", "each trial as it finishes (feedback test only)"],
                 ["Accuracy, binomial p", "share of trials correct, and the chance of getting at least that many by "
                                          "guessing. p &lt; 0.05 = ABOVE CHANCE"],
                 ["Confusion matrix", "rows = what was cued, columns = what was decoded. A good model has big numbers "
                                      "on the diagonal. All in one column = the model is biased to one side"],
                 ["Competition metric: max kappa", "how BCI Competition IV scored: kappa at each moment after the cue, "
                                                   "best moment reported. 0 = chance, 1 = perfect. Compare it with the "
                                                   "red 'chance' line; with few trials, chance can reach 0.5-0.6"],
                 ["CONFIRMED / NOT CONFIRMED", "only for your own models: CONFIRMED (p &lt; 0.05) marks the model "
                                               "READY for free mode"]],
                [58, 112]),
          P("How many correct is 'above chance'?", H2),
          table([["Trials", "20", "30", "40", "60", "80"],
                 ["needed for p &lt; 0.05", "15 (75 %)", "20 (67 %)", "26 (65 %)", "37 (62 %)", "48 (60 %)"]],
                [40, 26, 26, 26, 26, 26]),
          P("A test is saved like a calibration block, so it also becomes training data for the next model.", SMALL),
          P("8. Step 4 - Free mode", H1),
          P("Whenever no check, calibration, test or training is running, MI Live is in free mode: just imagine left "
            "or right and watch the big word and the bot. A change of imagery shows up after about 2-4 seconds "
            "(2 s of EEG per output plus 2 s of smoothing)."),
          table([["Setting", "Default", "Effect"],
                 ["Threshold |v|", "0.5", "how one-sided the last 2 s must be (0.5 = 75 % of outputs agree). Higher: "
                                         "fewer but surer commands"],
                 ["Hold (s)", "0.5", "how long it must stay past the threshold before the command changes. Higher: "
                                     "slower but steadier"],
                 ["When undecided", "STOP", "STOP: the bot stands still between commands. FORWARD: it drives straight"],
                 ["remove bias", "on", "removes a constant lean to one side (the running mean of the output)"],
                 ["keep adapting alignment", "on", "keeps following slow changes of today's signal. Untick to freeze "
                                                  "it as it is"],
                 ["calm display", "on", "hides the jittery trace and pointer; the bar, word and bot stay"]],
                [42, 20, 108]),
          PageBreak()]

    # ================================================================== 9 bot
    s += [P("9. Connecting a real bot", H1),
          P("The command can leave the laptop in two ways at the same time as the on-screen bot. A message is sent "
            "when the command changes and again every 0.25 s, so a bot can stop by itself if messages stop."),
          table([["Way", "How", "What is sent"],
                 ["UDP (Wi-Fi)", "tick 'Send to bot by UDP' and type the bot's address, e.g. 192.168.1.50:5005",
                  "one JSON line: {\"cmd\": \"LEFT\", \"v\": -0.72, \"d\": -1.31, \"t\": ...}"],
                 ["Serial (USB / Bluetooth HC-05)", "type the port (e.g. COM5), press Open", "one letter + newline: "
                                                                                              "L, R, S (stop), F (forward)"]],
                [38, 70, 62]),
          P("Ready-made examples", H2),
          *bullets(["<b>bot_examples\\arduino_bot\\arduino_bot.ino</b>: a 2-wheel Arduino bot with an L298N motor driver "
                    "(left motor pins 5/6, right motor 9/10, 115200 baud). L and R spin on the spot, F drives, S stops; "
                    "it stops by itself after 1 s without messages.",
                    "<b>tools\\udp_listen.py</b>: prints the UDP commands (run it, tick UDP with 127.0.0.1:5005). Use it as "
                    "a starting point for a Raspberry Pi bot."]),
          box("Safety rules built in", bullets([
              "STOP during the signal check, calibration, cued test and training.",
              "STOP when the signal is an artifact (movement, jaw) for more than 0.5 s.",
              "STOP and 'NO DATA' when no EEG arrived for 1 s (Bluetooth drop).",
              "STOP when the window is closed. Keep the real bot slow and on the floor."]), color=GOOD),
          P("10. How it works inside", H1), pipeline_diagram(), Spacer(1, 2 * mm),
          table([["Step", "What and why"],
                 ["Montage", "C3 minus left ear (A1), C4 minus right ear (A2): removes what both share, e.g. large "
                             "electrode offsets"],
                 ["50 Hz notch", "removes mains hum; the 2b training data was recorded with the same notch"],
                 ["Filter bank", "9 bands of 4 Hz from 4 to 40 Hz (the 2008 competition winner's idea); causal filters "
                                 "(past samples only)"],
                 ["Covariance", "for each band, how strong C3 and C4 are and how they move together over the last 2 s"],
                 ["Alignment", "'Euclidean Alignment': every covariance is re-centred on the mean of today's data, so "
                               "differences between days, people and headsets matter less. Uses no labels"],
                 ["CSP + SVM", "CSP finds the C3/C4 mix whose power differs most between left and right; a linear SVM "
                               "turns the 18 numbers into one output d (negative = left)"],
                 ["Bias, smoothing", "the running mean of d is removed; v = average sign of d over the last 2 s"],
                 ["Command", "LEFT if v &lt;= -threshold for 'hold' seconds, RIGHT if v &gt;= +threshold, else STOP"]],
                [30, 140]),
          PageBreak()]

    # ================================================================== 11 results, troubleshooting
    s += [P("11. How good is it?", H1),
          P("On the BCI IV 2b data, each person decoded by a base model that never saw them, exactly as live: "
            "<b>77.7 %</b> of trials correct on average (57 % to 95 % per person), competition kappa 0.60. On our dry "
            "headphones the first sessions (26 October 2026) were not yet above chance: a stable left/right pattern "
            "was not found. That is common at the start; imagery usually improves with practice, a GOOD signal and "
            "more calibration blocks. If it stays at chance after about three sessions, use <b>real hand squeezes</b> "
            "for control: the pattern is much stronger."),
          P("12. Troubleshooting", H1),
          table([["Problem", "What to do"],
                 ["Scan finds nothing", "close mi_bci and the Capsule app; switch the headphones off and on; Bluetooth on; "
                                        "scan again"],
                 ["Signal check BAD: hum", "unplug the charger; press the named pad and its ear clip onto skin; move away "
                                           "from cables"],
                 ["Signal check BAD: no EEG / huge EEG", "a pad is not touching the scalp, or you are tense; adjust the "
                                                          "headphones, relax"],
                 ["'NO DATA' / samples/s below 225", "Bluetooth is losing data: sit closer, reconnect"],
                 ["Many artifacts (&gt; 20 %)", "relax jaw and forehead, keep still, blink only in the pauses"],
                 ["Calibration screen text in a corner", "fixed on 26 Oct 2026; if seen, move the window or press "
                                                         "Esc and start again"],
                 ["Model NOT READY", "keep the signal GOOD; record 1-2 more blocks; check the real-squeeze block"],
                 ["Test NOT CONFIRMED", "do not rely on free mode yet; calibrate more blocks, retrain, test again"],
                 ["Bar stuck on one side", "keep 'remove bias' and 'keep adapting' ticked; give it 30 s, or calibrate"],
                 ["An error message", "see D:\\trainsvm\\apps\\mi_live\\_out\\error_log.txt"]],
                [52, 118]),
          P("13. Files", H1),
          table([["Where", "What"],
                 ["apps\\mi_live\\run*.bat, live.py", "start the app (headset, simulator, 2b demo)"],
                 ["data\\mi_bci\\&lt;Subject&gt;\\&lt;date_time&gt;_screening\\", "each calibration block or test: eeg.csv, "
                                                                                  "events.csv, outputs.csv, run.json"],
                 ["data\\mi_bci\\&lt;Subject&gt;\\decoders_live\\", "your models (live_*.json) and reports (report_*.json)"],
                 ["apps\\mi_live\\models\\base_2b_live.json", "the base model trained on BCI IV 2b"],
                 ["apps\\mi_live\\tools\\", "session_summary.py (a day's runs and results), train_personal_cli.py, "
                                          "check_test_run.py, eye_check.py, swap_check.py, udp_listen.py, and checks"],
                 ["apps\\mi_live\\README.md", "technical notes and verification results"]],
                [70, 100]),
          Spacer(1, 3 * mm),
          P("Useful command: <font face='Courier'>C:\\Python313\\python.exe tools\\session_summary.py &lt;Subject&gt;</font> "
            "(run in apps\\mi_live) lists today's runs with signal quality, test results and the model report.", SMALL),
          PageBreak(),
          P("14. Words used", H1),
          table([["Word", "Meaning"],
                 ["Motor imagery (MI)", "imagining a movement without doing it"],
                 ["ERD", "the drop of mu/beta power over the motor area opposite the (imagined) moving hand"],
                 ["C3, C4, A1, A2", "electrode places: left and right motor area, left and right ear"],
                 ["Artifact", "a signal that is not brain: blinks, eye movements, jaw, movement, cable pulls"],
                 ["Cued trial", "a trial where the screen tells you which hand (the label is known)"],
                 ["Leave-one-run-out", "test each model on a recording it was not trained on"],
                 ["Binomial p", "the chance of scoring at least this well by pure guessing"],
                 ["Kappa", "accuracy corrected for chance: 0 = guessing, 1 = perfect"]],
                [42, 128])]
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=20 * mm, title="MI Live - User Guide", author="EEG motor-imagery project",
                            subject="How to use MI Live")
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
