from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import csv
import io
from datetime import datetime, timezone
from database import db, logger
from dependencies import get_current_user
from models import (
    LobbyActionRequest, HostControlRequest
)

router = APIRouter()


@router.get("/meetings/{meeting_id}/report/csv")
async def meeting_report_csv(meeting_id: str, request: Request):
    await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(200)
    messages = await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MeetFlow Meeting Report"])
    writer.writerow([])
    writer.writerow(["Meeting Title", meeting["title"]])
    writer.writerow(["Meeting ID", meeting["meeting_id"]])
    writer.writerow(["Meeting Code", meeting.get("meeting_code", "")])
    writer.writerow(["Status", meeting.get("status", "")])
    writer.writerow(["Mode", meeting.get("meeting_mode", "standard")])
    writer.writerow(["Duration (min)", meeting.get("duration", 0)])
    writer.writerow(["Created At", meeting.get("created_at", "")])
    writer.writerow(["Scheduled At", meeting.get("scheduled_at", "")])
    writer.writerow(["Host", meeting.get("host_name", "")])
    writer.writerow([])
    writer.writerow(["--- Participants ---"])
    writer.writerow(["Name", "Email", "Role", "Joined At", "Left At", "Mic", "Camera"])
    for p in participants:
        writer.writerow([p.get("name",""), p.get("email",""), p.get("role",""),
                        p.get("joined_at",""), p.get("left_at",""),
                        "On" if p.get("mic_on") else "Off", "On" if p.get("camera_on") else "Off"])
    writer.writerow([])
    writer.writerow(["--- Chat Messages ---"])
    writer.writerow(["Time", "User", "Message"])
    for m in messages:
        writer.writerow([m.get("created_at",""), m.get("user_name",""), m.get("message","")])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="meetflow_report_{meeting_id}.csv"'}
    )

@router.get("/meetings/{meeting_id}/report/pdf")
async def meeting_report_pdf(meeting_id: str, request: Request):
    await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(200)
    messages = await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    buf = io.BytesIO()
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=18, textColor=colors.HexColor('#4A5D4E'))
        elements = []
        elements.append(Paragraph("MeetFlow Meeting Report", title_style))
        elements.append(Spacer(1, 10))
        info_data = [
            ["Title", meeting["title"]], ["Status", meeting.get("status","")],
            ["Mode", meeting.get("meeting_mode","standard")], ["Duration", f"{meeting.get('duration',0)} min"],
            ["Host", meeting.get("host_name","")], ["Created", meeting.get("created_at","")[:19]],
            ["Scheduled", (meeting.get("scheduled_at","") or "N/A")[:19]],
        ]
        t = Table(info_data, colWidths=[100, 350])
        t.setStyle(TableStyle([
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#4A5D4E')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))
        elements.append(Paragraph("Participants", styles['Heading2']))
        p_data = [["Name", "Email", "Role", "Joined", "Left"]]
        for p in participants:
            p_data.append([p.get("name",""), p.get("email",""), p.get("role",""),
                          (p.get("joined_at","") or "—")[:19], (p.get("left_at","") or "—")[:19]])
        pt = Table(p_data, colWidths=[90, 140, 60, 90, 90])
        pt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4A5D4E')), ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E4E0')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(pt)
        if messages:
            elements.append(Spacer(1, 15))
            elements.append(Paragraph("Chat Messages", styles['Heading2']))
            m_data = [["Time", "User", "Message"]]
            for m in messages[:50]:
                m_data.append([(m.get("created_at",""))[:19], m.get("user_name",""), m.get("message","")[:80]])
            mt = Table(m_data, colWidths=[90, 80, 300])
            mt.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4A5D4E')), ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 7),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E4E0')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3), ('TOPPADDING', (0,0), (-1,-1), 3),
            ]))
            elements.append(mt)
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
        doc.build(elements)
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="meetflow_report_{meeting_id}.pdf"'}
    )




@router.get("/meetings/{meeting_id}/lobby")
async def get_lobby(meeting_id: str, request: Request):
    await get_current_user(request)
    waiting = await db.meeting_participants.find(
        {"meeting_id": meeting_id, "lobby_status": "waiting"}, {"_id": 0}
    ).to_list(50)
    return waiting

@router.post("/meetings/{meeting_id}/lobby/{user_id}")
async def lobby_action(meeting_id: str, user_id: str, req: LobbyActionRequest, request: Request):
    from services.meetings_host import lobby_action as _lobby
    host = await get_current_user(request)
    return await _lobby(meeting_id, user_id, req.action, host)

@router.post("/meetings/{meeting_id}/join-lobby")
async def join_lobby(meeting_id: str, request: Request):
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not meeting.get("lobby_enabled"):
        return {"lobby": False, "status": "direct_join"}
    existing = await db.meeting_participants.find_one({"meeting_id": meeting_id, "user_id": user["user_id"]}, {"_id": 0})
    if existing and existing.get("role") in ["host", "co-host"]:
        return {"lobby": False, "status": "host_bypass"}
    if existing:
        await db.meeting_participants.update_one(
            {"meeting_id": meeting_id, "user_id": user["user_id"]},
            {"$set": {"lobby_status": "waiting"}}
        )
    else:
        await db.meeting_participants.insert_one({
            "meeting_id": meeting_id, "user_id": user["user_id"],
            "name": user["name"], "email": user["email"],
            "avatar": user.get("avatar", ""), "role": "participant",
            "joined_at": None, "left_at": None, "mic_on": True,
            "camera_on": True, "hand_raised": False, "is_presenting": False,
            "lobby_status": "waiting",
        })
    return {"lobby": True, "status": "waiting"}

@router.get("/meetings/{meeting_id}/lobby-status")
async def check_lobby_status(meeting_id: str, request: Request):
    user = await get_current_user(request)
    p = await db.meeting_participants.find_one(
        {"meeting_id": meeting_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not p:
        return {"status": "not_found"}
    return {"status": p.get("lobby_status", "unknown")}




@router.post("/meetings/{meeting_id}/host-control")
async def host_control(meeting_id: str, req: HostControlRequest, request: Request):
    from services.meetings_host import host_control as _hc
    user = await get_current_user(request)
    return await _hc(meeting_id, req.action, user)




@router.post("/meetings/{meeting_id}/recording/request")
async def request_recording(meeting_id: str, request: Request):
    """Host requests to start recording - creates consent request for all participants."""
    from services.meetings_consent import request_consent
    user = await get_current_user(request)
    return await request_consent(meeting_id, "recording", user)

@router.post("/meetings/{meeting_id}/transcript/request")
async def request_transcript(meeting_id: str, request: Request):
    """Host requests to start transcript - creates consent request for all participants."""
    from services.meetings_consent import request_consent
    user = await get_current_user(request)
    return await request_consent(meeting_id, "transcript", user)

@router.post("/meetings/{meeting_id}/consent/{consent_id}/respond")
async def respond_consent(meeting_id: str, consent_id: str, request: Request):
    """Participant responds to a consent request (accept/decline)."""
    from services.meetings_consent import respond_consent as _respond
    user = await get_current_user(request)
    body = await request.json()
    response_status = body.get("response", "accepted")
    return await _respond(meeting_id, consent_id, response_status, user)

@router.get("/meetings/{meeting_id}/consent/active")
async def get_active_consents(meeting_id: str, request: Request):
    """Get active (pending) consent requests for a meeting."""
    from services.meetings_consent import list_active_consents
    await get_current_user(request)
    return await list_active_consents(meeting_id)

