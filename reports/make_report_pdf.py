"""Turn EXPERIMENT_REPORT.txt into a plain PDF (EXPERIMENT_REPORT.pdf). Same text, simple layout:
headings in bold, prose in Helvetica, tables / aligned blocks in Courier so columns stay aligned."""
import re
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer

SRC, OUT = r"D:\trainsvm\reports\EXPERIMENT_REPORT_2026-09-19.txt", r"D:\trainsvm\reports\EXPERIMENT_REPORT_2026-09-19.pdf"

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=13, spaceAfter=3)
PRE = ParagraphStyle("pre", fontName="Courier", fontSize=7.8, leading=9.6)
TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=4)
H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=14, leading=18, spaceBefore=14,
                    spaceAfter=6)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=15, spaceBefore=12,
                    spaceAfter=5)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=13, spaceBefore=8,
                    spaceAfter=3)

RULE_EQ = re.compile(r"^=+$")
RULE_DASH = re.compile(r"^-{20,}$")
TABLE_ROW = re.compile(r"^\s*-{3,}(\s+-{3,})+\s*$")
SUBHEAD = re.compile(r"^(\s*\d+\.\d+ \S.*|STEP [A-Z]\d+ - .*)$")
BULLET = re.compile(r"^(\s*)(- |\* |\d+\. |\([a-z]\) )(.*)$")
KEYVAL = re.compile(r"^(\s*)([A-Z][A-Za-z ]{0,12}?) +: (.*)$")


def is_table(block):
    return any(TABLE_ROW.match(l) or re.search(r"\S {3,}\S", l) or "....." in l for l in block)


def para_items(block):
    """Group wrapped lines into items: (indent, marker, text)."""
    items = []
    for line in block:
        ind = len(line) - len(line.lstrip())
        b, k = BULLET.match(line), KEYVAL.match(line)
        if b:
            items.append([ind, b.group(2).strip(), b.group(3).strip()])
        elif k:
            items.append([ind, f"<b>{escape(k.group(2))}:</b>", k.group(3).strip(), True])
        elif items and (ind > items[-1][0] or (ind == items[-1][0] and not items[-1][1])):
            items[-1][2] += " " + line.strip()
        else:
            items.append([ind, "", line.strip()])
    return items


def render_block(block, story):
    if SUBHEAD.match(block[0]):
        story.append(Paragraph(escape(block[0].strip()), H3))
        block = block[1:]
        if not block:
            return
    if is_table(block):
        base = min(len(l) - len(l.lstrip()) for l in block)
        story.append(Preformatted("\n".join(l[base:] for l in block), PRE))
        story.append(Spacer(1, 5))
        return
    for it in para_items(block):
        ind, marker, text = it[0], it[1], escape(it[2])
        style = ParagraphStyle("b", parent=BODY, leftIndent=ind * 4)
        if len(it) == 4:                      # "Key : value"
            story.append(Paragraph(f"{marker} {text}", style))
        elif marker:
            style.leftIndent, style.firstLineIndent = ind * 4 + 12, -12
            story.append(Paragraph(f"{escape(marker)}&nbsp;{text}", style))
        else:
            story.append(Paragraph(text, style))


def build():
    lines = open(SRC, encoding="utf-8").read().splitlines()
    story, i, block = [], 0, []

    def flush():
        if block:
            render_block(block, story)
            block.clear()

    first_title = True
    while i < len(lines):
        line = lines[i].rstrip()
        # heading wrapped in ===== or ----- rules
        if RULE_EQ.match(line.strip()) or RULE_DASH.match(line.strip()):
            flush()
            j = i + 1
            inner = []
            while j < len(lines) and not (RULE_EQ.match(lines[j].strip()) or
                                          RULE_DASH.match(lines[j].strip())):
                inner.append(lines[j].strip())
                j += 1
            if j < len(lines) and 0 < len(inner) <= 3 and all(inner):
                text = " ".join(inner)
                if "END OF REPORT" not in text:
                    if first_title:
                        for t in inner:
                            story.append(Paragraph(escape(t), TITLE if t is inner[0] else BODY))
                        first_title = False
                    else:
                        story.append(Paragraph(escape(text), H1 if RULE_EQ.match(line.strip())
                                               else H2))
                i = j + 1
            else:
                i += 1
            continue
        if not line.strip():
            flush()
        else:
            block.append(line)
        i += 1
    flush()

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(A4[0] / 2, 25, f"Page {doc.page}")

    SimpleDocTemplate(OUT, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=45,
                      bottomMargin=45, title="Left vs Right Motor Imagery with an SVM",
                      author="trainsvm").build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build()
    print("written", OUT)
