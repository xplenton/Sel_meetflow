"""PDF invoice rendering.

Extracted from `routes/resources/_common.py` in iter 349. Public API:

    `build_invoice_pdf(*, title, subtitle, header_info, lines, total,
                       currency="EUR") -> bytes`

Returns raw A4 PDF bytes. `header_info` is a list of (label, value) tuples;
`lines` is a list of dicts with keys label/quantity/unit/unit_price/subtotal.

The legacy underscore-prefixed name `_build_invoice_pdf` is kept as a thin
shim in `routes/resources/_common.py` for backwards compatibility with
existing call sites in `invoices.py` and `invoice_tracking.py`.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

BRAND = colors.HexColor("#4A5D4E")
MUTED = colors.HexColor("#6B7280")
BORDER = colors.HexColor("#E2E4E0")


def build_invoice_pdf(
    *,
    title: str,
    subtitle: str,
    header_info: List,
    lines: List,
    total: float,
    currency: str = "EUR",
) -> bytes:
    """Render a polished A4 PDF invoice with reportlab. Returns raw PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    p_title = ParagraphStyle("title", parent=styles["Title"], fontSize=20,
                             textColor=BRAND, spaceAfter=4, leading=24)
    p_sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10,
                           textColor=MUTED, spaceAfter=16)
    p_h = ParagraphStyle("h", parent=styles["Heading4"], textColor=BRAND,
                         spaceBefore=8, spaceAfter=4)
    p_n = ParagraphStyle("n", parent=styles["Normal"], fontSize=10, leading=14)

    flow = [
        Paragraph(title, p_title),
        Paragraph(subtitle, p_sub),
    ]

    # Header info as a 2-col table
    if header_info:
        rows = [[Paragraph(f"<b>{k}</b>", p_n), Paragraph(str(v or ''), p_n)]
                for k, v in header_info if v not in (None, "")]
        if rows:
            t = Table(rows, colWidths=[45 * mm, None])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]))
            flow.append(t)
            flow.append(Spacer(1, 12))

    flow.append(Paragraph("Posten", p_h))

    head = [["Position", "Menge", "Einheit", "Einzelpreis", "Gesamt"]]
    body = []
    for ln in lines:
        body.append([
            ln.get("label", ""),
            f"{ln.get('quantity', 0)}",
            ln.get("unit", "") or "",
            f"{float(ln.get('unit_price', 0)):.2f} {currency}",
            f"{float(ln.get('subtotal', 0)):.2f} {currency}",
        ])
    if not body:
        body = [["(keine Posten)", "", "", "", ""]]

    table = Table(head + body, colWidths=[None, 18 * mm, 22 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBF9")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("LINEBELOW", (0, -1), (-1, -1), 1, BRAND),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow.append(table)
    flow.append(Spacer(1, 12))

    total_row = Table(
        [["Gesamtsumme", f"{total:.2f} {currency}"]],
        colWidths=[None, 30 * mm],
    )
    total_row.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 12),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
    ]))
    flow.append(total_row)
    flow.append(Spacer(1, 24))
    flow.append(Paragraph(
        "<font color='#6B7280' size='8'>Interne Leistungsverrechnung &middot; "
        "Erzeugt durch MeetFlow &middot; "
        f"{datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC</font>",
        p_n,
    ))

    doc.build(flow)
    return buf.getvalue()
