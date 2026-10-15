"""Shared rendering engine for the LLM Gateway interview-prep PDFs.

Reproduces the reference style: a title band, per-question difficulty badges,
the Answer / Simple explanation / Real-world example / Interview tip layout,
light dividers between questions, tables, and code blocks.
"""

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, ListFlowable, ListItem, PageBreak,
    PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle,
)

# --- Palette -------------------------------------------------------------
INK = colors.HexColor("#1f2430")
MUTED = colors.HexColor("#5b6472")
ACCENT = colors.HexColor("#3b6fd6")
RULE = colors.HexColor("#e2e6ec")
CODE_BG = colors.HexColor("#f4f6f9")

LEVELS = {
    "EASY":   (colors.HexColor("#e6f4ea"), colors.HexColor("#137333")),
    "MEDIUM": (colors.HexColor("#fef7e0"), colors.HexColor("#9a6700")),
    "HARD":   (colors.HexColor("#fce8e6"), colors.HexColor("#c5221f")),
}

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

# --- Styles --------------------------------------------------------------
_ss = getSampleStyleSheet()


def _style(name, **kw):
    base = kw.pop("parent", _ss["Normal"])
    return ParagraphStyle(name, parent=base, **kw)


TITLE = _style("t_title", fontName="Helvetica-Bold", fontSize=22, leading=26,
               textColor=colors.white)
SUBTITLE = _style("t_sub", fontName="Helvetica", fontSize=10.5, leading=14,
                  textColor=colors.HexColor("#dce6fb"))
SECTION = _style("t_section", fontName="Helvetica-Bold", fontSize=15, leading=19,
                 textColor=INK, spaceBefore=6, spaceAfter=2)
SECTION_INTRO = _style("t_section_intro", fontName="Helvetica", fontSize=9.5,
                       leading=13, textColor=MUTED, spaceAfter=4)
QUESTION = _style("t_q", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                  textColor=INK)
BODY = _style("t_body", fontName="Helvetica", fontSize=10, leading=15,
              textColor=INK, alignment=TA_LEFT, spaceAfter=5)
TIP = _style("t_tip", fontName="Helvetica-Oblique", fontSize=9.5, leading=13,
             textColor=MUTED, spaceAfter=2)
BADGE = _style("t_badge", fontName="Helvetica-Bold", fontSize=7.5, leading=9,
               alignment=1)
CODE = _style("t_code", fontName="Courier", fontSize=8.2, leading=11.5,
              textColor=colors.HexColor("#243049"))
BULLET = _style("t_bullet", fontName="Helvetica", fontSize=9.5, leading=13.5,
                textColor=INK)


def _badge(level):
    bg, fg = LEVELS[level]
    lab = Paragraph(f'<font color="{fg.hexval()}">{level}</font>', BADGE)
    t = Table([[lab]], colWidths=[62])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _labeled(label, text):
    return Paragraph(f'<b>{label}:</b> {text}', BODY)


def _code_block(src):
    inner = Preformatted(src, CODE)
    t = Table([[inner]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _data_table(headers, rows):
    data = [[Paragraph(f'<b>{h}</b>', BULLET) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c), BULLET) for c in r])
    ncol = len(headers)
    cw = CONTENT_W / ncol
    t = Table(data, colWidths=[cw] * ncol, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f8")),
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _question_flowables(q):
    out = []
    head = Table([[Paragraph(q["q"], QUESTION), _badge(q.get("level", "EASY"))]],
                 colWidths=[CONTENT_W - 66, 66])
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
        ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    out.append(head)
    out.append(Spacer(1, 5))
    if q.get("answer"):
        out.append(_labeled("Answer", q["answer"]))
    if q.get("simple"):
        out.append(_labeled("Simple explanation", q["simple"]))
    if q.get("example"):
        out.append(_labeled("Project example", q["example"]))
    if q.get("code"):
        out.append(_code_block(q["code"]))
        out.append(Spacer(1, 4))
    if q.get("table"):
        out.append(_data_table(q["table"][0], q["table"][1]))
        out.append(Spacer(1, 4))
    if q.get("followups"):
        items = [ListItem(Paragraph(f, BULLET), leftIndent=6) for f in q["followups"]]
        out.append(Paragraph('<b>Likely follow-ups:</b>', TIP))
        out.append(ListFlowable(items, bulletType="bullet", start="•",
                                bulletColor=ACCENT, leftIndent=12, spaceBefore=1))
        out.append(Spacer(1, 2))
    if q.get("tip"):
        out.append(Paragraph(f'<i>Interview tip: {q["tip"]}</i>', TIP))
    out.append(Spacer(1, 7))
    out.append(HRFlowable(width="100%", thickness=0.6, color=RULE,
                          spaceBefore=1, spaceAfter=10))
    return out


def _make_header_footer(doc_title):
    def _draw(canvas, doc):
        canvas.saveState()
        # Footer
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 8 * mm, "LLM Gateway V1 — Interview Prep")
        canvas.drawRightString(PAGE_W - MARGIN, 8 * mm, f"Page {doc.page}")
        # Running header (not on page 1 band)
        if doc.page > 1:
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(MUTED)
            canvas.drawString(MARGIN, PAGE_H - 10 * mm, doc_title)
            canvas.setStrokeColor(RULE)
            canvas.line(MARGIN, PAGE_H - 11 * mm, PAGE_W - MARGIN, PAGE_H - 11 * mm)
        canvas.restoreState()
    return _draw


def section_header(name, intro=None):
    out = [Paragraph(name, SECTION),
           HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                      spaceBefore=1, spaceAfter=6)]
    if intro:
        out.append(Paragraph(intro, SECTION_INTRO))
        out.append(Spacer(1, 2))
    return out


def para(text):
    return Paragraph(text, BODY)


def bullet_list(items):
    its = [ListItem(Paragraph(i, BULLET), leftIndent=6) for i in items]
    return ListFlowable(its, bulletType="bullet", start="•", bulletColor=ACCENT,
                        leftIndent=12, spaceBefore=1, spaceAfter=4)


def code_block(src):
    return _code_block(src)


def data_table(headers, rows):
    return _data_table(headers, rows)


def _setup_doc(filename, doc_title, doc_subtitle):
    doc = BaseDocTemplate(
        filename, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=16 * mm,
        title=doc_title, author="LLM Gateway V1",
    )
    frame = Frame(MARGIN, 16 * mm, CONTENT_W, PAGE_H - 18 * mm - 16 * mm, id="main")
    draw = _make_header_footer(doc_title)
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=draw)])
    band = Table([[Paragraph(doc_title, TITLE)], [Paragraph(doc_subtitle, SUBTITLE)]],
                 colWidths=[CONTENT_W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2b4a8b")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (0, 0), 14),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 14),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    return doc, [band, Spacer(1, 14)]


def build_doc(filename, doc_title, doc_subtitle, flowables):
    """Build a free-form document (title band + footer + provided flowables)."""
    doc, story = _setup_doc(filename, doc_title, doc_subtitle)
    story.extend(flowables)
    doc.build(story)
    print(f"wrote {filename}")


def build_pdf(filename, doc_title, doc_subtitle, sections):
    doc = BaseDocTemplate(
        filename, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=16 * mm,
        title=doc_title, author="LLM Gateway V1",
    )
    frame = Frame(MARGIN, 16 * mm, CONTENT_W, PAGE_H - 18 * mm - 16 * mm, id="main")
    draw = _make_header_footer(doc_title)
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=draw)])

    story = []
    # Title band
    band = Table([[Paragraph(doc_title, TITLE)], [Paragraph(doc_subtitle, SUBTITLE)]],
                 colWidths=[CONTENT_W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2b4a8b")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (0, 0), 14),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 14),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(band)
    story.append(Spacer(1, 14))

    for si, sec in enumerate(sections):
        if si > 0:
            story.append(Spacer(1, 6))
        story.append(Paragraph(sec["name"], SECTION))
        story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT,
                                spaceBefore=1, spaceAfter=6))
        if sec.get("intro"):
            story.append(Paragraph(sec["intro"], SECTION_INTRO))
            story.append(Spacer(1, 2))
        for q in sec["questions"]:
            story.extend(_question_flowables(q))

    doc.build(story)
    print(f"wrote {filename}")
