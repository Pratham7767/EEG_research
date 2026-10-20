"""
build_study_pdf.py  -  render STUDY.md to STUDY.pdf.

Markdown subset: # ## ### headings, | tables |, ``` blocks, indented blocks,
**bold**, *italic*, - bullets, --- rules. Figures from results\\figures are
inserted at the markers listed in FIGURES.

Run:  C:\\Python313\\python.exe build_study_pdf.py
"""

import os
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, Image,
                                KeepTogether, PageBreak, PageTemplate,
                                Paragraph, Preformatted, Spacer, Table,
                                TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "STUDY.md")
OUT = os.path.join(HERE, "STUDY.pdf")
FIGDIR = os.path.join(HERE, "results", "figures")

ACCENT = colors.HexColor("#2f6f9f")
GREY = colors.HexColor("#555555")

# figure -> the heading after which it is inserted
FIGURES = [
    ("## 2.3 The comparative study", "fig1_ea_effect.png",
     "Figure 1. Euclidean Alignment improves every model under both protocols, "
     "and improves cross-subject transfer most. Numbers above the bars are the "
     "gain from alignment."),
    ("### The three levers, measured", "fig3_vs_stroke.png",
     "Figure 2. Changing the dataset moved the result; four years of "
     "model-swapping on the stroke data did not. The dotted line is the "
     "accuracy claimed by Liu et al., which scores 63.8% on shuffled labels."),
    ("## 2.5 Stage three: testing our own headset", "fig2_per_subject.png",
     "Figure 3. Cross-subject results per subject. Every subject is above "
     "chance, but the spread is wide: B03 at 0.57 against B04 at 0.94. BCI "
     "illiteracy is visible in the data."),
    ("## 2.6 Stage four: how much calibration data would a new user need?",
     "fig4_calibration_curve.png",
     "Figure 4. Calibration data buys very little once Euclidean Alignment is "
     "applied, and naive concatenation wastes it entirely. The public dataset "
     "is worth roughly 160 trials of the user's own time."),
]

S = dict(
    title=ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=19, leading=24,
                         spaceAfter=6, textColor=ACCENT),
    sub=ParagraphStyle("s", fontName="Helvetica", fontSize=12.5, leading=16,
                       spaceAfter=14, textColor=GREY),
    h1=ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=19,
                      spaceBefore=16, spaceAfter=7, textColor=ACCENT),
    h2=ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.3,
                      leading=16, spaceBefore=13, spaceAfter=5),
    h3=ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.6,
                      leading=14, spaceBefore=10, spaceAfter=4,
                      textColor=GREY),
    body=ParagraphStyle("b", fontName="Helvetica", fontSize=9.6, leading=13.6,
                        spaceAfter=5),
    bullet=ParagraphStyle("bu", fontName="Helvetica", fontSize=9.6,
                          leading=13.4, leftIndent=13, bulletIndent=3,
                          spaceAfter=2.5),
    pre=ParagraphStyle("p", fontName="Courier", fontSize=7.9, leading=9.9,
                       leftIndent=7, textColor=colors.HexColor("#1f2933")),
    cap=ParagraphStyle("c", fontName="Helvetica-Oblique", fontSize=8.3,
                       leading=11, alignment=TA_CENTER, textColor=GREY,
                       spaceBefore=3, spaceAfter=12),
)


def inline(t):
    t = escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\*\w])\*([^\*]+?)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', t)
    return t


def make_table(rows):
    data = [[Paragraph(inline(c), ParagraphStyle(
        "th" if i == 0 else "td", fontName="Helvetica-Bold" if i == 0
        else "Helvetica", fontSize=8.1, leading=10.4,
        textColor=colors.white if i == 0 else colors.black))
        for c in r] for i, r in enumerate(rows)]
    t = Table(data, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f2f5f8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2da")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def figure_for(heading):
    for h, fn, cap in FIGURES:
        if heading.strip() == h:
            p = os.path.join(FIGDIR, fn)
            if not os.path.exists(p):
                return None
            from reportlab.lib.utils import ImageReader
            iw, ih = ImageReader(p).getSize()
            w = 160 * mm
            return KeepTogether([Spacer(1, 4), Image(p, w, w * ih / iw),
                                 Paragraph(cap, S["cap"])])
    return None


def parse(lines):
    flow, i, n = [], 0, len(lines)
    first_h1 = True
    while i < n:
        ln = lines[i]

        if ln.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            flow.append(Preformatted("\n".join(buf), S["pre"]))
            continue

        if ln.strip().startswith("|") and i + 1 < n and set(
                lines[i + 1].replace("|", "").strip()) <= set("-: "):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append([c.strip() for c in
                             lines[i].strip().strip("|").split("|")])
                i += 1
            flow += [Spacer(1, 4), make_table([head] + body), Spacer(1, 8)]
            continue

        if ln.startswith("    ") and ln.strip():
            buf = []
            while i < n and (lines[i].startswith("    ") or not lines[i].strip()):
                if lines[i].strip() or (buf and i + 1 < n
                                        and lines[i + 1].startswith("    ")):
                    buf.append(lines[i][4:] if lines[i].startswith("    ")
                               else "")
                else:
                    break
                i += 1
            flow.append(Preformatted("\n".join(buf), S["pre"]))
            continue

        if ln.startswith("# "):
            if not first_h1:
                flow.append(PageBreak())
            first_h1 = False
            flow.append(Paragraph(inline(ln[2:]), S["h1"]))
            flow.append(HRFlowable(width="100%", thickness=1, color=ACCENT,
                                   spaceAfter=7))
        elif ln.startswith("### "):
            flow.append(Paragraph(inline(ln[4:]), S["h3"]))
            f = figure_for(ln)
            if f:
                flow += f.contents if hasattr(f, "contents") else [f]
        elif ln.startswith("## "):
            flow.append(Paragraph(inline(ln[3:]), S["h2"]))
            f = figure_for(ln)
            if f:
                flow += f.contents if hasattr(f, "contents") else [f]
        elif ln.startswith("---") and not ln.strip("- "):
            flow.append(Spacer(1, 3))
        elif ln.strip().startswith(("- ", "* ")):
            flow.append(Paragraph(inline(ln.strip()[2:]), S["bullet"],
                                  bulletText="\u2022"))
        elif re.match(r"^\s*\d+\.\s", ln):
            m = re.match(r"^\s*(\d+)\.\s(.*)$", ln)
            flow.append(Paragraph(inline(m.group(2)), S["bullet"],
                                  bulletText=m.group(1) + "."))
        elif ln.strip():
            buf = [ln.strip()]
            while (i + 1 < n and lines[i + 1].strip()
                   and not lines[i + 1].startswith(("#", "|", "    ", "- ", "*",
                                                    "```", "---"))
                   and not re.match(r"^\s*\d+\.\s", lines[i + 1])):
                i += 1
                buf.append(lines[i].strip())
            flow.append(Paragraph(inline(" ".join(buf)), S["body"]))
        i += 1
    return flow


def decorate(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(GREY)
    canvas.drawString(20 * mm, 12 * mm,
                      "Two-channel motor imagery decoding - methods study")
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"{doc.page}")
    canvas.setStrokeColor(colors.HexColor("#d8dee4"))
    canvas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
    canvas.restoreState()


def main():
    with open(SRC, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    # title block from the first two headings
    flow = [Spacer(1, 22),
            Paragraph("Decoding Left vs Right Hand Motor Imagery<br/>"
                      "from a Two-Channel EEG Headset", S["title"]),
            Paragraph("A methods study, a comparative evaluation, "
                      "and a route forward", S["sub"]),
            HRFlowable(width="100%", thickness=1.4, color=ACCENT,
                       spaceAfter=10),
            Paragraph("Project folder <font face='Courier'>D:\\trainsvm</font> "
                      "&nbsp;&nbsp;|&nbsp;&nbsp; 8 October 2026", S["body"]),
            Spacer(1, 10)]
    # skip the original title lines
    start = 0
    for j, l in enumerate(lines):
        if l.startswith("# PART I"):
            start = j
            break
    flow += parse(lines[start:])

    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm,
                          rightMargin=20 * mm, topMargin=18 * mm,
                          bottomMargin=20 * mm,
                          title="Two-channel motor imagery decoding",
                          author="EXPERIMENT_2")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="f")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame],
                                       onPage=decorate)])
    doc.build(flow)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
