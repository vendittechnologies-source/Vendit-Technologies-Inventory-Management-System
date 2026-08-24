"""Turns a report's rows into a downloadable PDF, via reportlab.

Every report route in this app can produce the exact same JSON it always
has, or -- when the request includes ?format=pdf -- the exact same query
results rendered as a simple table PDF instead, via build_pdf_response().
"""
import io
import os
from datetime import datetime, timezone

from flask import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

# Vendit brand colors, matching static/css/style.css
BRAND = colors.HexColor("#d9232b")
HEADER_BG = colors.HexColor("#d9232b")
ROW_ALT_BG = colors.HexColor("#fbe9ea")

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "vendit-logo-pdf.png")


def build_pdf_response(filename, title, columns, rows, subtitle=None):
    """columns: list of (header_label, row_key, align) tuples.
    rows: list of dicts (or dict-likes) with those keys.
    Returns a Flask Response with the finished PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(letter),
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = styles["Heading2"]
    title_style.textColor = BRAND
    elements = []

    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=1.4 * inch, height=1.4 * inch * (182 / 300))
        elements.append(logo)
        elements.append(Spacer(1, 0.1 * inch))
    else:
        elements.append(Paragraph("Vendit Technologies", styles["Title"]))
    elements.append(Paragraph(title, title_style))
    if subtitle:
        elements.append(Paragraph(subtitle, styles["Normal"]))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(Paragraph(f"Generated {generated}", styles["Normal"]))
    elements.append(Spacer(1, 0.25 * inch))

    header = [c[0] for c in columns]
    table_data = [header]
    for row in rows:
        table_data.append([_fmt(row.get(c[1])) for c in columns])

    if len(table_data) == 1:
        table_data.append(["No data." for _ in columns])

    col_aligns = [c[2] if len(c) > 2 else "LEFT" for c in columns]
    table = Table(table_data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dfe6e4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, align in enumerate(col_aligns):
        if align == "RIGHT":
            style.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT_BG))
    table.setStyle(TableStyle(style))
    elements.append(table)

    doc.build(elements)
    buf.seek(0)
    return Response(
        buf.read(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)
