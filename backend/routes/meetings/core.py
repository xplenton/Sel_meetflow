from fastapi import APIRouter, HTTPException, Request, Response
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import db, read_db, logger
from dependencies import get_current_user
from services.permissions import has_cap, require_cap
from services.email import send_email_real, build_summary_email_html
from services.ws_manager import ws_manager
from services.llm_key import get_llm_key as _get_llm_key
from models import (
    MeetingCreateRequest, ChatMessageRequest, PollCreateRequest, PollVoteRequest,
    QuestionCreateRequest, QuestionUpdateRequest, BreakoutRoomCreateRequest
)

router = APIRouter()



@router.get("/meetings/conflicts")
async def check_meeting_conflicts(
    request: Request, scheduled_at: str, duration: int = 60,
):
    """Return external-calendar conflicts for the caller's CalDAV feed at the
    given slot. Used by the meeting-create UI to warn before booking."""
    user = await get_current_user(request)
    from services.caldav_sync import find_conflicts
    from datetime import datetime
    try:
        start = datetime.fromisoformat((scheduled_at or "").replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges Datum")
    end_iso = (start + timedelta(minutes=max(5, int(duration or 60)))).isoformat()
    conflicts = await find_conflicts(user["user_id"], start.isoformat(), end_iso)
    return {"conflicts": conflicts, "count": len(conflicts)}


@router.post("/meetings/conflicts/bulk")
async def check_meeting_conflicts_bulk(request: Request):
    """Bulk variant for the Schedule-Preview widget. Accepts a list of slots
    and returns the conflict counts per slot in order. Caps at 200 slots."""
    user = await get_current_user(request)
    from services.caldav_sync import find_conflicts
    from datetime import datetime
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    slots = body.get("slots") or []
    if not isinstance(slots, list):
        raise HTTPException(status_code=400, detail="slots must be a list")
    slots = slots[:200]
    results = []
    for s in slots:
        try:
            start = datetime.fromisoformat(str(s.get("scheduled_at", "")).replace("Z", "+00:00"))
            dur = max(5, int(s.get("duration") or 60))
            end_iso = (start + timedelta(minutes=dur)).isoformat()
            conflicts = await find_conflicts(user["user_id"], start.isoformat(), end_iso)
            results.append({"count": len(conflicts), "titles": [c.get("summary") or c.get("title") for c in conflicts][:3]})
        except Exception:
            results.append({"count": 0, "titles": []})
    return {"results": results}


@router.post("/meetings/conflicts/suggest-shift")
async def suggest_conflict_free_shift(request: Request):
    """Find the smallest time-shift (in minutes) that eliminates ALL conflicts
    across a set of recurring slot occurrences. Used by the Auto-Verschieben
    popover in the Schedule-Preview widget. Returns {shift_minutes: N} or
    {shift_minutes: null} if no conflict-free shift is found within ±4h."""
    user = await get_current_user(request)
    from services.caldav_sync import find_conflicts
    from datetime import datetime
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    occurrences = body.get("occurrences") or []
    duration = max(5, int(body.get("duration") or 60))
    if not isinstance(occurrences, list) or not occurrences:
        return {"shift_minutes": None}
    occurrences = occurrences[:50]

    parsed = []
    for iso in occurrences:
        try:
            parsed.append(datetime.fromisoformat(str(iso).replace("Z", "+00:00")))
        except Exception:
            continue
    if not parsed:
        return {"shift_minutes": None}

    # Ordered by smallest absolute shift, prefer positive (later in day)
    candidates = [30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180, -180, 210, 240, -240]
    for shift in candidates:
        all_clear = True
        for base in parsed:
            new_start = base + timedelta(minutes=shift)
            new_end = new_start + timedelta(minutes=duration)
            conflicts = await find_conflicts(user["user_id"], new_start.isoformat(), new_end.isoformat())
            if conflicts:
                all_clear = False
                break
        if all_clear:
            return {"shift_minutes": shift}
    return {"shift_minutes": None}


@router.post("/meetings")
async def create_meeting(req: MeetingCreateRequest, request: Request):
    from services.meetings_crud import create_meeting as _create
    user = await get_current_user(request)
    # Iter 372 — IAM-Audit Fix: enforce meetings.create cap (Guests dürfen nicht).
    await require_cap(user, "meetings.create", db)
    # Iter 252 — validate title. Reject empty / very short / unset (sentinel default).
    title = (req.title or "").strip()
    if not title or len(title) < 3 or title == "Untitled Meeting":
        raise HTTPException(status_code=400, detail="title is required (min 3 chars)")
    req.title = title
    return await _create(req, user)

@router.get("/meetings")
async def list_meetings(request: Request, meeting_type: Optional[str] = None, search: Optional[str] = None, page: int = 1, limit: int = 20):
    user = await get_current_user(request)
    # Iter 187 — heavy list endpoint, route through read-scaled handle.
    participant_meetings = await read_db.meeting_participants.find(
        {"user_id": user["user_id"]}, {"_id": 0, "meeting_id": 1}
    ).to_list(5000)
    meeting_ids = [p["meeting_id"] for p in participant_meetings]
    query = {"meeting_id": {"$in": meeting_ids}}
    now_iso = datetime.now(timezone.utc).isoformat()
    if meeting_type == "upcoming":
        query["$or"] = [{"status": "scheduled", "scheduled_at": {"$gte": now_iso}}, {"status": "active"}, {"status": "scheduled", "scheduled_at": {"$in": [None, ""]}}]
    elif meeting_type == "past":
        query["$or"] = [{"status": "ended"}, {"status": "scheduled", "scheduled_at": {"$lt": now_iso, "$nin": [None, ""]}}]
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    total = await read_db.meetings.count_documents(query)
    skip = (max(1, page) - 1) * limit
    meetings = await read_db.meetings.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    # Enrich with series_index / series_total for recurring meetings
    series_ids = list({m["series_id"] for m in meetings if m.get("series_id")})
    if series_ids:
        series_lookup: dict = {}
        for sid in series_ids:
            chrono = await read_db.meetings.find(
                {"series_id": sid}, {"_id": 0, "meeting_id": 1, "scheduled_at": 1}
            ).sort("scheduled_at", 1).to_list(500)
            series_lookup[sid] = {m["meeting_id"]: (i + 1, len(chrono)) for i, m in enumerate(chrono)}
        for m in meetings:
            sid = m.get("series_id")
            if sid and sid in series_lookup and m["meeting_id"] in series_lookup[sid]:
                idx, tot = series_lookup[sid][m["meeting_id"]]
                m["series_index"] = idx
                m["series_total"] = tot
    return {"meetings": meetings, "total": total, "page": page, "limit": limit, "pages": max(1, -(-total // limit))}

@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    meeting = await assert_can_view_meeting(user, meeting_id)
    participants = await db.meeting_participants.find({"meeting_id": meeting["meeting_id"]}, {"_id": 0}).to_list(100)
    meeting["participants"] = participants
    return meeting

@router.put("/meetings/{meeting_id}")
async def update_meeting(meeting_id: str, request: Request):
    from services.meetings_crud import update_meeting as _update
    user = await get_current_user(request)
    body = await request.json()
    return await _update(meeting_id, body, user)

@router.post("/meetings/{meeting_id}/send-invitations")
async def send_meeting_invitations_endpoint(meeting_id: str, request: Request):
    """Manually (re-)send ICS meeting invitations to all or specific participants."""
    from services.meetings_host import send_invitations
    user = await get_current_user(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    emails = body.get("emails") if isinstance(body, dict) else None
    return await send_invitations(meeting_id, emails, user)


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str, request: Request, soft: bool = False):
    """Delete a meeting. If `soft=true` AND the meeting belongs to a series,
    the meeting is marked status='cancelled' instead of being removed — this
    preserves audit history and DSGVO-relevant traces."""
    from services.meetings_lifecycle import delete_meeting as _delete
    user = await get_current_user(request)
    return await _delete(meeting_id, user, soft=soft)


@router.post("/meetings/{meeting_id}/restore")
async def restore_meeting(meeting_id: str, request: Request):
    """Undo a soft-cancellation of a series occurrence — reverts status to 'scheduled'."""
    from services.meetings_lifecycle import restore_meeting as _restore
    user = await get_current_user(request)
    return await _restore(meeting_id, user)


@router.post("/meetings/{meeting_id}/join")
async def join_meeting(meeting_id: str, request: Request):
    from services.meetings_lifecycle import join_meeting as _join
    user = await get_current_user(request)
    return await _join(meeting_id, user)

@router.post("/meetings/{meeting_id}/leave")
async def leave_meeting(meeting_id: str, request: Request):
    from services.meetings_lifecycle import leave_meeting as _leave
    user = await get_current_user(request)
    return await _leave(meeting_id, user)


@router.post("/meetings/{meeting_id}/ring")
async def ring_meeting(meeting_id: str, request: Request):
    """Host-initiated manual re-ring for latecomers. Sends incoming-call
    WS + web-push to invitees who are not currently in the room."""
    from services.meetings_lifecycle import ring_meeting as _ring
    user = await get_current_user(request)
    return await _ring(meeting_id, user)


@router.get("/meetings/{meeting_id}/reachability")
async def meeting_reachability(meeting_id: str, request: Request):
    """Per-invitee reachability summary for the host before ringing.

    For every invited user with a user_id, report:
      * `push_enabled` — user has at least one active push_subscription
      * `online` — user currently has an open chat-WS connection
      * `in_meeting` — already joined this meeting's LiveKit room
    Guests (invited by e-mail only, no user_id) are returned with all
    flags false so the host knows they can only be reached out-of-band.
    """
    from routes.chat import chat_ws
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0, "host_id": 1, "meeting_id": 1})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    is_host = meeting["host_id"] == user["user_id"]
    if not is_host:
        from services.permissions import has_cap
        if not await has_cap(user, "meetings.manage_others", db):
            raise HTTPException(status_code=403, detail="Not authorized")

    rows = await db.meeting_participants.find(
        {"meeting_id": meeting["meeting_id"]},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1, "role": 1, "joined_at": 1, "left_at": 1},
    ).to_list(200)

    result = []
    for r in rows:
        uid = r.get("user_id")
        if r.get("role") == "host":
            continue  # skip host — they don't need to ring themselves
        push_enabled = False
        if uid:
            push_enabled = await db.push_subscriptions.count_documents({"user_id": uid}) > 0
        online = bool(uid and chat_ws.is_online(uid))
        in_meeting = bool(r.get("joined_at") and not r.get("left_at"))
        result.append({
            "user_id": uid,
            "name": r.get("name") or (r.get("email") or "").split("@")[0] or "Gast",
            "email": r.get("email") or "",
            "avatar": r.get("avatar") or "",
            "push_enabled": push_enabled,
            "online": online,
            "in_meeting": in_meeting,
            "is_guest": not uid,
        })
    reachable = sum(1 for r in result if r["push_enabled"] or r["online"] or r["in_meeting"])
    return {"invitees": result, "total": len(result), "reachable": reachable}


async def auto_send_summary_email(meeting_id: str):
    """Trampoline to the service for backward compatibility within the module."""
    from services.meetings_summaries import auto_send_summary_email as _impl
    await _impl(meeting_id)

@router.get("/meetings/{meeting_id}/participants")
async def get_participants(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    return await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)

@router.get("/meetings/{meeting_id}/attendance-report")
async def get_attendance_report(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    meeting = await assert_can_view_meeting(user, meeting_id)
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)
    chat_msgs = await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(1000)
    docs = await db.meeting_documents.find({"meeting_id": meeting_id}, {"_id": 0, "storage_path": 0}).to_list(50)
    from services.meeting_attendance import build_attendance_report
    meeting["meeting_id"] = meeting_id  # ensure id is present for service
    return build_attendance_report(meeting, participants, chat_msgs, docs)

@router.get("/meetings/{meeting_id}/attendance-report/pdf")
async def get_attendance_report_pdf(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    meeting = await assert_can_view_meeting(user, meeting_id)
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)
    chat_msgs = await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(1000)
    from services.meeting_attendance import generate_attendance_pdf
    content = generate_attendance_pdf(meeting_id, meeting, participants, chat_msgs)
    title = meeting.get("title", "meeting").replace(" ", "_")
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="anwesenheit_{title}.pdf"'})

@router.put("/meetings/{meeting_id}/participants/{user_id}")
async def update_participant(meeting_id: str, user_id: str, request: Request):
    current_user = await get_current_user(request)
    body = await request.json()
    cp = await db.meeting_participants.find_one({"meeting_id": meeting_id, "user_id": current_user["user_id"]}, {"_id": 0})
    if not cp or cp["role"] not in ["host", "co-host"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    allowed = ["role", "mic_on", "camera_on", "hand_raised", "is_presenting"]
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        await db.meeting_participants.update_one({"meeting_id": meeting_id, "user_id": user_id}, {"$set": updates})

    # iter 190 — broadcast targeted mute/cam-off so the remote client actually
    # disables its local audio/video track. Previously we only persisted the DB
    # flag and the remote participant never heard/obeyed the request.
    if user_id != current_user["user_id"]:
        host_name = current_user.get("name", "Host")
        if updates.get("mic_on") is False:
            await ws_manager.broadcast(meeting_id, {
                "type": "host-control", "action": "mute_user",
                "target_user_id": user_id,
                "by": host_name, "by_id": current_user["user_id"],
            })
        if updates.get("camera_on") is False:
            await ws_manager.broadcast(meeting_id, {
                "type": "host-control", "action": "disable_camera_user",
                "target_user_id": user_id,
                "by": host_name, "by_id": current_user["user_id"],
            })
        if updates.get("role") == "removed":
            await ws_manager.broadcast(meeting_id, {
                "type": "host-control", "action": "remove_user",
                "target_user_id": user_id,
                "by": host_name, "by_id": current_user["user_id"],
            })
    return await db.meeting_participants.find_one({"meeting_id": meeting_id, "user_id": user_id}, {"_id": 0})




@router.post("/meetings/{meeting_id}/chat")
async def send_chat_message(meeting_id: str, req: ChatMessageRequest, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    msg = {
        "message_id": f"msg_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "user_id": user["user_id"], "user_name": user["name"],
        "avatar": user.get("avatar", ""), "message": req.message,
        "message_type": req.message_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_messages.insert_one(msg)
    return await db.chat_messages.find_one({"message_id": msg["message_id"]}, {"_id": 0})

@router.get("/meetings/{meeting_id}/chat")
async def get_chat_messages(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    return await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", 1).to_list(500)




@router.post("/meetings/{meeting_id}/ai/summarize")
async def summarize_meeting(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    meeting = await assert_can_view_meeting(user, meeting_id)
    messages = await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)
    chat_text = "\n".join([f"{m['user_name']}: {m['message']}" for m in messages])
    participant_names = ", ".join([p["name"] for p in participants])
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = await _get_llm_key()
        chat = LlmChat(api_key=api_key, session_id=f"summary_{meeting_id}", system_message="You are a meeting assistant. Summarize the meeting and extract action items.")
        chat.with_model("openai", "gpt-5.2")
        prompt = f"Meeting: {meeting['title']}\nParticipants: {participant_names}\nDuration: {meeting['duration']} min\n\nChat:\n{chat_text or 'No messages.'}\n\nProvide: 1) Brief summary 2) Key points 3) Action items"
        ai_response = await chat.send_message(UserMessage(text=prompt))
        summary_doc = {
            "summary_id": f"sum_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
            "content": ai_response, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.meeting_summaries.insert_one(summary_doc)
        return {"summary": ai_response, "summary_id": summary_doc["summary_id"]}
    except Exception as e:
        logger.error(f"AI summarization error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")

@router.post("/meetings/{meeting_id}/send-summary-email")
async def send_summary_email(meeting_id: str, request: Request):
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting["host_id"] != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Only host or admin can send summary emails")

    existing_summary = await db.meeting_summaries.find_one({"meeting_id": meeting_id}, {"_id": 0})
    summary_text = existing_summary["content"] if existing_summary else None

    if not summary_text:
        messages = await db.chat_messages.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
        participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)
        chat_text = "\n".join([f"{m['user_name']}: {m['message']}" for m in messages])
        participant_names = ", ".join([p["name"] for p in participants])
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            api_key = await _get_llm_key()
            chat = LlmChat(api_key=api_key, session_id=f"summary_email_{meeting_id}", system_message="You are a professional meeting assistant. Create a clear, structured meeting summary in the language of the meeting title. Include key decisions and action items.")
            chat.with_model("openai", "gpt-5.2")
            prompt = f"Meeting: {meeting['title']}\nParticipants: {participant_names}\nDuration: {meeting.get('duration', 60)} min\nDate: {meeting.get('scheduled_at', meeting.get('created_at', 'N/A'))}\n\nChat:\n{chat_text or 'No messages recorded.'}\n\nProvide a professional summary with: 1) Overview 2) Key decisions 3) Action items with responsible persons"
            summary_text = await chat.send_message(UserMessage(text=prompt))
            summary_doc = {
                "summary_id": f"sum_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
                "content": summary_text, "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.meeting_summaries.insert_one(summary_doc)
        except Exception as e:
            logger.error(f"AI summary generation failed: {e}")
            summary_text = f"Meeting: {meeting['title']}\nAI-Zusammenfassung konnte nicht generiert werden."

    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)
    participant_emails = []
    for p in participants:
        p_user = await db.users.find_one({"user_id": p["user_id"]}, {"_id": 0})
        if p_user and p_user.get("email"):
            participant_emails.append(p_user["email"])

    if not participant_emails:
        return {"message": "No participant emails found", "sent_to": 0}

    html = build_summary_email_html(meeting["title"], meeting.get("scheduled_at") or meeting.get("created_at", ""), participants, summary_text)
    sent_count = 0
    for email in participant_emails:
        result = await send_email_real(email, f"Meeting-Zusammenfassung: {meeting['title']}", html, category="meetings")
        if result.get("status") in ("sent", "logged"):
            sent_count += 1

    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {"summary_email_sent": True, "summary_email_sent_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": f"Summary email sent to {sent_count} participants", "sent_to": sent_count, "summary": summary_text}

@router.get("/meetings/{meeting_id}/summary")
async def get_meeting_summary(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    meeting = await assert_can_view_meeting(user, meeting_id)
    summary = await db.meeting_summaries.find_one({"meeting_id": meeting_id}, {"_id": 0})
    participants = await db.meeting_participants.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(100)
    return {
        "meeting": meeting,
        "summary": summary.get("content") if summary else None,
        "summary_id": summary.get("summary_id") if summary else None,
        "participants": participants,
        "email_sent": meeting.get("summary_email_sent", False),
    }




@router.post("/meetings/{meeting_id}/polls")
async def create_poll(meeting_id: str, req: PollCreateRequest, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    poll = {
        "poll_id": f"poll_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "question": req.question, "options": [{"text": o, "votes": 0, "voters": []} for o in req.options],
        "created_by": user["user_id"], "created_by_name": user["name"],
        "status": "active", "total_votes": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.polls.insert_one(poll)
    return await db.polls.find_one({"poll_id": poll["poll_id"]}, {"_id": 0})

@router.get("/meetings/{meeting_id}/polls")
async def get_polls(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    return await db.polls.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", -1).to_list(50)

@router.post("/meetings/{meeting_id}/polls/{poll_id}/vote")
async def vote_poll(meeting_id: str, poll_id: str, req: PollVoteRequest, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    poll = await db.polls.find_one({"poll_id": poll_id, "meeting_id": meeting_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll["status"] != "active":
        raise HTTPException(status_code=400, detail="Poll is closed")
    if req.option_index < 0 or req.option_index >= len(poll["options"]):
        raise HTTPException(status_code=400, detail="Invalid option")
    # Iter 252 — Race-safe vote: do TOCTOU check + update atomically.
    # The matchFilter requires that the user has NOT voted in ANY option yet;
    # if a concurrent call has already pushed them, modified_count is 0 here.
    result = await db.polls.update_one(
        {"poll_id": poll_id, "status": "active", "options.voters": {"$ne": user["user_id"]}},
        {"$inc": {f"options.{req.option_index}.votes": 1, "total_votes": 1},
         "$push": {f"options.{req.option_index}.voters": user["user_id"]}}
    )
    if result.modified_count == 0:
        # Either already voted OR poll became inactive between the read and write.
        fresh = await db.polls.find_one({"poll_id": poll_id}, {"_id": 0})
        if fresh and fresh.get("status") != "active":
            raise HTTPException(status_code=400, detail="Poll is closed")
        raise HTTPException(status_code=400, detail="Already voted")
    return await db.polls.find_one({"poll_id": poll_id}, {"_id": 0})

@router.put("/meetings/{meeting_id}/polls/{poll_id}/close")
async def close_poll(meeting_id: str, poll_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    await db.polls.update_one({"poll_id": poll_id}, {"$set": {"status": "closed"}})
    return await db.polls.find_one({"poll_id": poll_id}, {"_id": 0})



@router.post("/meetings/{meeting_id}/questions")
async def create_question(meeting_id: str, req: QuestionCreateRequest, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    question = {
        "question_id": f"q_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "text": req.text, "asked_by": user["user_id"], "asked_by_name": user["name"],
        "status": "pending", "priority": 0, "answer": None, "upvotes": 0, "upvoters": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.questions.insert_one(question)
    return await db.questions.find_one({"question_id": question["question_id"]}, {"_id": 0})

@router.get("/meetings/{meeting_id}/questions")
async def get_questions(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    return await db.questions.find({"meeting_id": meeting_id}, {"_id": 0}).sort("created_at", -1).to_list(100)

@router.put("/meetings/{meeting_id}/questions/{question_id}")
async def update_question(meeting_id: str, question_id: str, req: QuestionUpdateRequest, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    updates = {}
    if req.status: updates["status"] = req.status
    if req.priority is not None: updates["priority"] = req.priority
    if req.answer is not None: updates["answer"] = req.answer
    if updates:
        await db.questions.update_one({"question_id": question_id}, {"$set": updates})
    return await db.questions.find_one({"question_id": question_id}, {"_id": 0})

@router.post("/meetings/{meeting_id}/questions/{question_id}/upvote")
async def upvote_question(meeting_id: str, question_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    q = await db.questions.find_one({"question_id": question_id}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    if user["user_id"] in q.get("upvoters", []):
        raise HTTPException(status_code=400, detail="Already upvoted")
    await db.questions.update_one(
        {"question_id": question_id},
        {"$inc": {"upvotes": 1}, "$push": {"upvoters": user["user_id"]}}
    )
    return await db.questions.find_one({"question_id": question_id}, {"_id": 0})




@router.post("/meetings/{meeting_id}/breakout-rooms")
async def create_breakout_room(meeting_id: str, req: BreakoutRoomCreateRequest, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    room = {
        "room_id": f"br_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "name": req.name, "participant_ids": req.participant_ids,
        "status": "open", "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.breakout_rooms.insert_one(room)
    return await db.breakout_rooms.find_one({"room_id": room["room_id"]}, {"_id": 0})

@router.get("/meetings/{meeting_id}/breakout-rooms")
async def get_breakout_rooms(meeting_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    return await db.breakout_rooms.find({"meeting_id": meeting_id}, {"_id": 0}).to_list(20)

@router.put("/meetings/{meeting_id}/breakout-rooms/{room_id}")
async def update_breakout_room(meeting_id: str, room_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    body = await request.json()
    allowed = ["name", "participant_ids", "status"]
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        await db.breakout_rooms.update_one({"room_id": room_id}, {"$set": updates})
    return await db.breakout_rooms.find_one({"room_id": room_id}, {"_id": 0})

@router.delete("/meetings/{meeting_id}/breakout-rooms/{room_id}")
async def delete_breakout_room(meeting_id: str, room_id: str, request: Request):
    from services.audience_guards import assert_can_view_meeting
    user = await get_current_user(request)
    await assert_can_view_meeting(user, meeting_id)
    await db.breakout_rooms.delete_one({"room_id": room_id})
    return {"message": "Room deleted"}




