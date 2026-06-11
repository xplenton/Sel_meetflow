"""Attendance-report generation for MeetFlow meetings.

Pure business logic extracted from routes/meetings/core.py (Iter 88).
Behaviour preserved byte-for-byte — route handlers now just fetch the raw
documents and delegate formatting to these helpers.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Dict, Any, List


def _parse_duration_minutes(joined: str, left: str) -> float:
    """Return minutes between joined & left (left defaults to now when missing)."""
    if not joined:
        return 0
    try:
        from dateutil import parser as dtparser
        j = dtparser.isoparse(joined)
        lf = dtparser.isoparse(left) if left else datetime.now(timezone.utc)
        return round((lf - j).total_seconds() / 60, 1)
    except Exception:
        return 0


def _participant_status(joined: str, left: str) -> str:
    if joined and not left:
        return "aktiv"
    if not joined:
        return "abwesend"
    return "verlassen"


def _participant_status_de(joined: str, left: str) -> str:
    """Capitalised label used in the PDF."""
    return _participant_status(joined, left).capitalize()


def build_attendance_report(meeting: Dict[str, Any],
                            participants: List[Dict[str, Any]],
                            chat_msgs: List[Dict[str, Any]],
                            docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the JSON attendance report for /meetings/{id}/attendance-report."""
    report = []
    for p in participants:
        joined = p.get("joined_at")
        left = p.get("left_at")
        duration_min = _parse_duration_minutes(joined, left)
        chat_count = len([
            m for m in chat_msgs
            if m.get("user_id") == p.get("user_id") or m.get("sender") == p.get("user_id")
        ])
        sig_count = 0
        for d in docs:
            sig_count += len([s for s in d.get("signatures", []) if s.get("signer_id") == p.get("user_id")])
        report.append({
            "user_id": p.get("user_id"), "name": p.get("name", ""),
            "email": p.get("email", ""), "role": p.get("role", "participant"),
            "joined_at": joined, "left_at": left,
            "duration_minutes": duration_min,
            "status": _participant_status(joined, left),
            "chat_messages": chat_count, "signatures": sig_count,
            "hand_raised": p.get("hand_raised", False),
        })
    return {
        "meeting_id": meeting.get("meeting_id"),
        "title": meeting.get("title", ""),
        "created_at": meeting.get("created_at", ""),
        "status": meeting.get("status", ""),
        "total_participants": len(participants),
        "active_participants": len([r for r in report if r["status"] == "aktiv"]),
        "total_chat_messages": len(chat_msgs),
        "total_documents": len(docs),
        "participants": report,
    }


def generate_attendance_pdf(meeting_id: str,
                            meeting: Dict[str, Any],
                            participants: List[Dict[str, Any]],
                            chat_msgs: List[Dict[str, Any]]) -> bytes:
    """Return PDF bytes for /meetings/{id}/attendance-report/pdf."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("AT", parent=styles["Heading1"], fontSize=16, textColor=rl_colors.HexColor("#4A5D4E"), spaceAfter=4)
    sub_s = ParagraphStyle("AS", parent=styles["Normal"], fontSize=9, textColor=rl_colors.HexColor("#6B7280"), spaceAfter=10)
    elements = []
    elements.append(Paragraph("Anwesenheitsbericht", title_s))
    elements.append(Paragraph(f"Meeting: {meeting.get('title','')} | Status: {meeting.get('status','')}", sub_s))
    elements.append(Paragraph(f"Erstellt am: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC | Teilnehmer: {len(participants)}", sub_s))
    elements.append(Spacer(1, 4*mm))

    active = len([p for p in participants if p.get("joined_at") and not p.get("left_at")])
    elements.append(Paragraph(f"Aktiv: {active} | Gesamt: {len(participants)} | Chat-Nachrichten: {len(chat_msgs)}", sub_s))
    elements.append(Spacer(1, 4*mm))

    table_data = [["Name", "Rolle", "Beitritt", "Verlassen", "Dauer (Min)", "Chat", "Status"]]
    for p in participants:
        joined = p.get("joined_at")
        left = p.get("left_at")
        duration = _parse_duration_minutes(joined, left)
        chat_c = len([
            m for m in chat_msgs
            if m.get("user_id") == p.get("user_id") or m.get("sender") == p.get("user_id")
        ])
        status = _participant_status_de(joined, left)
        j_str = joined[:19].replace("T", " ") if joined else "-"
        l_str = left[:19].replace("T", " ") if left else "-"
        table_data.append([p.get("name", ""), p.get("role", ""), j_str, l_str, str(duration), str(chat_c), status])

    t = Table(table_data, colWidths=[35*mm, 20*mm, 33*mm, 33*mm, 18*mm, 12*mm, 20*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#4A5D4E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#E2E4E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F9F9F8")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(
        f"Generiert von MeetFlow | Meeting-ID: {meeting_id}",
        ParagraphStyle("F", parent=styles["Normal"], fontSize=7, textColor=rl_colors.HexColor("#9CA3AF"))
    ))
    pdf.build(elements)
    return buf.getvalue()
