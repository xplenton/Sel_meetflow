from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import db, logger
from dependencies import get_current_user
from services.storage import put_object, get_object, APP_STORAGE_PREFIX
from services.permissions import has_cap
from services.email import send_email_real, build_meeting_email_html
from services.meetings_recurring import generate_custom_schedule, generate_simple_pattern
from models import (
    MeetingCreateRequest, RecordingCreateRequest, TranscriptCreateRequest, MeetingInviteRequest,
    RecurringGenerateRequest, TemplateCreateRequest, BrandingUpdateRequest
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Iter 263 — Notification Center: classification + deep-link resolution
# ---------------------------------------------------------------------------

CATEGORY_TYPES = {
    "chat":     {"mention", "chat_message", "chat_call"},
    "news":     {"news", "news_post", "news_comment", "news_reaction", "news_question"},
    "tasks":    {"task_assigned", "task_due", "task_comment", "task_status"},
    "meetings": {"invitation", "reminder", "meeting_ended", "meeting_started", "recording"},
    "bookings": {"resource_booking_pending", "resource_booking_approved",
                 "resource_booking_rejected", "catering_requested", "catering_status",
                 "damage_report"},
    "surveys":  {"new_survey", "survey_reminder", "survey_response"},
    "filetransfer": {"filetransfer.new_transfer", "filetransfer.download",
                     "filetransfer.expiring"},
    "system":   {"feedback_reply", "diag_report", "health_alert", "system",
                 "grant", "role", "force_logout"},
}

_TYPE_TO_CATEGORY = {t: cat for cat, ts in CATEGORY_TYPES.items() for t in ts}


def _classify_category(notif_type: str) -> str:
    """Return one of: chat, news, tasks, meetings, bookings, surveys,
    filetransfer, system. Unknown types fall into 'system' so they're
    still visible. Types prefixed with `filetransfer.` map automatically
    (defense-in-depth for new sub-types we add later)."""
    if notif_type in _TYPE_TO_CATEGORY:
        return _TYPE_TO_CATEGORY[notif_type]
    if notif_type.startswith("filetransfer."):
        return "filetransfer"
    return "system"


def _resolve_link_target(notif: dict) -> str:
    """Resolve a deep-link URL for the Notification Center based on the
    notification payload. Returns a frontend route (no host prefix)."""
    # Explicit link wins
    if notif.get("link"):
        return notif["link"]

    t = notif.get("type", "")
    data = notif.get("data") or {}

    if notif.get("meeting_id"):
        return f"/meetings/{notif['meeting_id']}/join"
    if notif.get("survey_id"):
        return f"/surveys/{notif['survey_id']}"
    if notif.get("post_id"):
        return f"/news?post={notif['post_id']}"
    if notif.get("task_id") or data.get("task_id"):
        return f"/tasks?id={notif.get('task_id') or data.get('task_id')}"
    if notif.get("transfer_id") or data.get("transfer_id"):
        return f"/filetransfer/{notif.get('transfer_id') or data.get('transfer_id')}"

    if t.startswith("resource_booking") or t.startswith("catering") or t == "damage_report":
        bid = data.get("booking_id") or data.get("resource_id")
        if t == "resource_booking_pending":
            return "/ressourcen?tab=approvals" + (f"&id={bid}" if bid else "")
        if t.startswith("catering"):
            return "/ressourcen?tab=catering" + (f"&id={bid}" if bid else "")
        return "/ressourcen?tab=mine" + (f"&id={bid}" if bid else "")

    if t in ("mention", "chat_message", "chat_call"):
        conv_id = data.get("conversation_id") or notif.get("conversation_id")
        return "/chat" + (f"?c={conv_id}" if conv_id else "")

    if t == "feedback_reply":
        return "/profile#my-feedback"
    if t == "diag_report":
        return f"/diag/{notif.get('diag_token', '')}" if notif.get("diag_token") else "/profile"

    # Sensible fallbacks per category
    cat = _classify_category(t)
    return {"news": "/news", "tasks": "/tasks", "meetings": "/meetings",
            "bookings": "/ressourcen", "surveys": "/surveys",
            "filetransfer": "/filetransfer",
            "chat": "/chat", "system": "/profile"}.get(cat, "/dashboard")


@router.get("/recordings")
async def list_recordings(request: Request, search: Optional[str] = None, page: int = 1, limit: int = 20):
    user = await get_current_user(request)
    participant_meetings = await db.meeting_participants.find(
        {"user_id": user["user_id"]}, {"_id": 0, "meeting_id": 1}
    ).to_list(5000)
    meeting_ids = [p["meeting_id"] for p in participant_meetings]
    query = {"meeting_id": {"$in": meeting_ids}}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    total = await db.recordings.count_documents(query)
    skip = (max(1, page) - 1) * limit
    recordings = await db.recordings.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"recordings": recordings, "total": total, "page": page, "pages": max(1, -(-total // limit))}

@router.post("/meetings/{meeting_id}/recordings")
async def create_recording(meeting_id: str, req: RecordingCreateRequest, request: Request):
    user = await get_current_user(request)
    recording = {
        "recording_id": f"rec_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "title": req.title, "url": req.url, "duration": req.duration,
        "created_by": user["user_id"], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.recordings.insert_one(recording)
    return await db.recordings.find_one({"recording_id": recording["recording_id"]}, {"_id": 0})

@router.get("/transcripts")
async def list_transcripts(request: Request, search: Optional[str] = None, page: int = 1, limit: int = 20):
    user = await get_current_user(request)
    participant_meetings = await db.meeting_participants.find(
        {"user_id": user["user_id"]}, {"_id": 0, "meeting_id": 1}
    ).to_list(5000)
    meeting_ids = [p["meeting_id"] for p in participant_meetings]
    query = {"meeting_id": {"$in": meeting_ids}}
    if search:
        query["meeting_title"] = {"$regex": search, "$options": "i"}
    total = await db.transcripts.count_documents(query)
    skip = (max(1, page) - 1) * limit
    transcripts = await db.transcripts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"transcripts": transcripts, "total": total, "page": page, "pages": max(1, -(-total // limit))}

@router.post("/meetings/{meeting_id}/transcripts")
async def create_transcript(meeting_id: str, request: Request):
    # Iter 257 — auth check BEFORE payload validation so unauthenticated calls
    # get 401 instead of 422 (FastAPI default is to validate body first).
    user = await get_current_user(request)
    try:
        body = await request.json()
        req = TranscriptCreateRequest(**body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    transcript = {
        "transcript_id": f"tr_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "meeting_title": meeting["title"] if meeting else "Unknown",
        "content": req.content, "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.transcripts.insert_one(transcript)
    return await db.transcripts.find_one({"transcript_id": transcript["transcript_id"]}, {"_id": 0})


@router.post("/recordings/{recording_id}/summarize")
async def summarize_recording(recording_id: str, request: Request):
    """Generate AI summary for a recording using available transcript OR meeting chat.

    Uses GPT-5.2 via emergentintegrations. Stores summary on the recording document.
    """
    user = await get_current_user(request)
    recording = await db.recordings.find_one({"recording_id": recording_id}, {"_id": 0})
    if not recording:
        raise HTTPException(status_code=404, detail="Aufnahme nicht gefunden")
    # Verify user has access (was in meeting or is admin)
    mid = recording.get("meeting_id")
    has_access = user.get("role") == "admin"
    if not has_access and mid:
        participant = await db.meeting_participants.find_one({"meeting_id": mid, "user_id": user["user_id"]})
        has_access = participant is not None or recording.get("created_by") == user["user_id"]
    if not has_access:
        raise HTTPException(status_code=403, detail="Kein Zugriff")

    # Source text: transcript first, fallback to chat messages
    transcript_doc = await db.transcripts.find_one({"meeting_id": mid}, {"_id": 0})
    source_text = (transcript_doc or {}).get("content", "") or ""
    if not source_text:
        msgs = await db.chat_messages.find({"meeting_id": mid}, {"_id": 0}).sort("created_at", 1).to_list(500)
        source_text = "\n".join([f"{m.get('sender_name', '?')}: {m.get('content', '')}" for m in msgs if m.get("content")])
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="Kein Transkript oder Chat-Inhalt vorhanden")

    api_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM Key fehlt")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        session = f"recsum_{recording_id}"
        chat = LlmChat(api_key=api_key, session_id=session,
                       system_message="Du bist ein hilfreicher Assistent und fasst Klinik-Meeting-Inhalte für ein medizinisches Team praezise zusammen.")
        chat.with_model("openai", "gpt-5")
        prompt = f"""Fasse den folgenden Meeting-Inhalt in 3 Teilen zusammen:

1. EXECUTIVE SUMMARY (1-2 Saetze)
2. KEY POINTS (3-5 Bullet-Punkte)
3. ACTION ITEMS (Liste aller Aufgaben/Entscheidungen mit Verantwortlichen wenn genannt)

Antworte in gut strukturiertem Markdown auf Deutsch. Sei knapp und medizinisch praezise.

MEETING-INHALT:
\"\"\"
{source_text[:12000]}
\"\"\""""
        reply = await chat.send_message(UserMessage(text=prompt))
        summary = reply or ""
    except Exception as e:
        logger.error(f"LLM summary error: {e}")
        raise HTTPException(status_code=500, detail=f"LLM Fehler: {str(e)[:120]}")

    await db.recordings.update_one(
        {"recording_id": recording_id},
        {"$set": {
            "ai_summary": summary,
            "ai_summary_at": datetime.now(timezone.utc).isoformat(),
            "ai_summary_by": user.get("name", ""),
        }},
    )
    return {"recording_id": recording_id, "summary": summary}




async def send_notification(user_id: str, ntype: str, title: str, body: str, meeting_id: str = None, email: str = None):
    notif = {
        "notification_id": f"notif_{uuid.uuid4().hex[:10]}", "user_id": user_id,
        "type": ntype, "title": title, "body": body,
        "meeting_id": meeting_id, "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one(notif)
    if email:
        await send_email_real(email, title, f"<p>{body.replace(chr(10), '<br>')}</p>")
    else:
        logger.info(f"[NOTIFICATION] To: {user_id} | {title}")
    return notif

@router.post("/meetings/{meeting_id}/invite")
async def invite_to_meeting(meeting_id: str, req: MeetingInviteRequest, request: Request):
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    invited = []
    for email_addr in req.emails:
        email_lower = email_addr.lower().strip()
        inv_user = await db.users.find_one({"email": email_lower}, {"_id": 0})
        existing_p = await db.meeting_participants.find_one({"meeting_id": meeting_id, "email": email_lower})
        if not existing_p:
            await db.meeting_participants.insert_one({
                "meeting_id": meeting_id, "user_id": inv_user["user_id"] if inv_user else None,
                "name": inv_user["name"] if inv_user else email_lower.split("@")[0],
                "email": email_lower, "avatar": inv_user.get("avatar", "") if inv_user else "",
                "role": "participant", "joined_at": None, "left_at": None,
                "mic_on": True, "camera_on": True, "hand_raised": False, "is_presenting": False,
            })
        if inv_user:
            frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
            join_link = f"{frontend_url}/meetings/{meeting_id}/join"
            body = f"{user['name']} invited you to '{meeting['title']}'. {req.message}\n\nJoin: {join_link}"
            html = build_meeting_email_html(user['name'], meeting['title'], join_link, req.message)
            await send_notification(inv_user["user_id"], "invitation", f"Meeting Invitation: {meeting['title']}", body, meeting_id, inv_user.get("email"))
        else:
            frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
            join_link = f"{frontend_url}/meetings/{meeting_id}/join"
            html = build_meeting_email_html(user['name'], meeting['title'], join_link, req.message)
            await send_email_real(email_lower, f"Meeting Invitation: {meeting['title']}", html)
        invited.append(email_lower)
    return {"invited": invited, "count": len(invited)}

@router.get("/notifications")
async def get_notifications(request: Request, since_days: int = 30,
                            only_unread: bool = False, limit: int = 100,
                            category: str = ""):
    """Iter 256 — supports since_days (default 30) and only_unread filter.
    Iter 263 — Notification Center: enrichment with `category` field
    (chat, news, tasks, meetings, bookings, surveys, system) plus an
    optional `category` query-param to filter server-side. Backward-compat
    — the existing `type` field stays untouched."""
    user = await get_current_user(request)
    q = {"user_id": user["user_id"]}
    if only_unread:
        q["read"] = False
    if since_days > 0:
        # Iter 287 — Fix: created_at is stored as datetime, but the previous
        # ISO-string cutoff caused MongoDB type-mismatch → no matches at all.
        # Use a tz-aware datetime so newer catering/push notifs surface.
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        q["created_at"] = {"$gte": cutoff}
    if category and category in CATEGORY_TYPES:
        q["type"] = {"$in": list(CATEGORY_TYPES[category])}
    limit = max(1, min(int(limit), 500))
    notifs = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    # Iter 263 — enrich with category, normalized body, deep-link target
    for n in notifs:
        n["category"] = _classify_category(n.get("type", ""))
        # unify body field (some inserters use "message" instead of "body")
        if not n.get("body") and n.get("message"):
            n["body"] = n["message"]
        # ensure notification_id (some older notifications were inserted
        # without one — provide a stable fallback so /read endpoint works)
        if not n.get("notification_id"):
            n["notification_id"] = f"legacy_{abs(hash(str(n.get('created_at',''))+(n.get('type','')))) % 10**10}"
        n["link_target"] = _resolve_link_target(n)
    return notifs


@router.get("/notifications/categories")
async def get_notification_categories(request: Request, since_days: int = 30):
    """Iter 263 — returns per-category unread counts for the Notification
    Center tabs. Cheap aggregation; refreshed every 15 s by the frontend."""
    user = await get_current_user(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, since_days))).isoformat()
    counts = {k: 0 for k in CATEGORY_TYPES}
    counts["all"] = 0
    pipe = [
        {"$match": {"user_id": user["user_id"], "read": False,
                    "created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]
    async for row in db.notifications.aggregate(pipe):
        t = row["_id"] or ""
        cat = _classify_category(t)
        counts[cat] = counts.get(cat, 0) + row["count"]
        counts["all"] += row["count"]
    return counts


@router.get("/notifications/unread-count")
async def get_unread_count(request: Request):
    user = await get_current_user(request)
    count = await db.notifications.count_documents({"user_id": user["user_id"], "read": False})
    return {"count": count}

@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, request: Request):
    user = await get_current_user(request)
    await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": user["user_id"]},
        {"$set": {"read": True}}
    )
    return {"message": "Marked as read"}

@router.put("/notifications/read-all")
async def mark_all_read(request: Request):
    user = await get_current_user(request)
    await db.notifications.update_many({"user_id": user["user_id"], "read": False}, {"$set": {"read": True}})
    return {"message": "All marked as read"}




@router.post("/meetings/{meeting_id}/recurring/generate")
async def generate_recurring(meeting_id: str, req: RecurringGenerateRequest, request: Request):
    user = await get_current_user(request)
    template = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not template:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not template.get("recurring"):
        raise HTTPException(status_code=400, detail="Meeting is not recurring")
    pattern = template.get("recurring_pattern", "weekly")
    if pattern == "custom":
        schedule = req.recurring_schedule or template.get("recurring_schedule") or []
        weeks = req.weeks or template.get("recurring_weeks") or 8
        generated = await generate_custom_schedule(
            meeting_id=meeting_id, template=template, schedule=schedule, weeks=weeks, user=user
        )
    else:
        generated = await generate_simple_pattern(
            meeting_id=meeting_id, template=template, count=req.count, user=user
        )
    refreshed = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0, "series_id": 1}) or {}
    return {"series_id": refreshed.get("series_id"), "generated": generated, "count": len(generated)}

@router.get("/meetings/recurring/{series_id}")
async def get_recurring_series(series_id: str, request: Request):
    await get_current_user(request)
    return await db.meetings.find({"series_id": series_id}, {"_id": 0}).sort("scheduled_at", 1).to_list(200)


# ---- Series bulk operations ----

_BULK_ALLOWED_FIELDS = {
    "lobby_enabled", "guest_access", "chat_enabled", "reactions_enabled",
    "recording_enabled", "transcript_enabled", "meeting_mode",
    "title", "description",
}


@router.patch("/meetings/series/{series_id}")
async def bulk_update_series(series_id: str, request: Request):
    """Bulk-update all scheduled meetings in a series. Skips already-ended meetings."""
    user = await get_current_user(request)
    series = await db.meetings.find(
        {"series_id": series_id}, {"_id": 0, "meeting_id": 1, "host_id": 1, "status": 1}
    ).to_list(500)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    # Authorization: host of the first meeting or user with meetings.manage_others
    any_host = series[0].get("host_id")
    if any_host != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    body = await request.json()
    updates = {k: v for k, v in (body or {}).items() if k in _BULK_ALLOWED_FIELDS}
    scope = (body or {}).get("scope", "upcoming")  # "upcoming" (default) | "all"
    if not updates:
        raise HTTPException(status_code=400, detail="Keine zulaessigen Felder")
    query = {"series_id": series_id}
    if scope != "all":
        query["status"] = {"$in": ["scheduled", "active"]}
    result = await db.meetings.update_many(query, {"$set": updates})
    return {"series_id": series_id, "updated": result.modified_count, "fields": list(updates.keys()), "scope": scope}


@router.delete("/meetings/series/{series_id}")
async def bulk_delete_series(series_id: str, request: Request, scope: str = "upcoming"):
    """Delete all (or only upcoming) meetings of a series."""
    user = await get_current_user(request)
    first = await db.meetings.find_one({"series_id": series_id}, {"_id": 0, "host_id": 1})
    if not first:
        raise HTTPException(status_code=404, detail="Series not found")
    if first.get("host_id") != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    query = {"series_id": series_id}
    if scope != "all":
        query["status"] = {"$in": ["scheduled"]}
    # Collect affected meeting_ids for cascade cleanup
    affected = await db.meetings.find(query, {"_id": 0, "meeting_id": 1}).to_list(500)
    ids = [m["meeting_id"] for m in affected]
    if not ids:
        return {"series_id": series_id, "deleted": 0, "scope": scope}
    await db.meetings.delete_many({"meeting_id": {"$in": ids}})
    await db.meeting_participants.delete_many({"meeting_id": {"$in": ids}})
    await db.chat_messages.delete_many({"meeting_id": {"$in": ids}})
    return {"series_id": series_id, "deleted": len(ids), "scope": scope}




from services.meetings_modes import get_mode_config_for

@router.get("/meetings/{meeting_id}/mode-config")
async def get_mode_config(meeting_id: str, request: Request):
    await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    mode = meeting.get("meeting_mode", "standard")
    config = get_mode_config_for(mode)
    return {"mode": mode, "config": config}




@router.post("/templates")
async def create_template(req: TemplateCreateRequest, request: Request):
    user = await get_current_user(request)
    template = {
        "template_id": f"tmpl_{uuid.uuid4().hex[:10]}",
        "name": req.name, "title": req.title, "description": req.description,
        "duration": req.duration, "meeting_mode": req.meeting_mode,
        "lobby_enabled": req.lobby_enabled, "guest_access": req.guest_access,
        "chat_enabled": req.chat_enabled, "reactions_enabled": req.reactions_enabled,
        "recording_enabled": req.recording_enabled, "transcript_enabled": req.transcript_enabled,
        "recurring": req.recurring, "recurring_pattern": req.recurring_pattern,
        "recurring_schedule": req.recurring_schedule or [],
        "recurring_weeks": int(req.recurring_weeks) if req.recurring_weeks else None,
        "invited_emails": req.invited_emails or [],
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.meeting_templates.insert_one(template)
    return await db.meeting_templates.find_one({"template_id": template["template_id"]}, {"_id": 0})

@router.get("/templates")
async def list_templates(request: Request):
    user = await get_current_user(request)
    return await db.meeting_templates.find({"created_by": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)

@router.get("/templates/{template_id}")
async def get_template(template_id: str, request: Request):
    await get_current_user(request)
    t = await db.meeting_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t

@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.meeting_templates.delete_one({"template_id": template_id, "created_by": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template deleted"}


@router.put("/templates/{template_id}")
async def update_template(template_id: str, req: TemplateCreateRequest, request: Request):
    user = await get_current_user(request)
    existing = await db.meeting_templates.find_one({"template_id": template_id, "created_by": user["user_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    updates = {
        "name": req.name, "title": req.title, "description": req.description,
        "duration": req.duration, "meeting_mode": req.meeting_mode,
        "lobby_enabled": req.lobby_enabled, "guest_access": req.guest_access,
        "chat_enabled": req.chat_enabled, "reactions_enabled": req.reactions_enabled,
        "recording_enabled": req.recording_enabled, "transcript_enabled": req.transcript_enabled,
        "recurring": req.recurring, "recurring_pattern": req.recurring_pattern,
        "recurring_schedule": req.recurring_schedule or [],
        "recurring_weeks": int(req.recurring_weeks) if req.recurring_weeks else None,
        "invited_emails": req.invited_emails or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.meeting_templates.update_one({"template_id": template_id}, {"$set": updates})
    return await db.meeting_templates.find_one({"template_id": template_id}, {"_id": 0})

@router.post("/templates/{template_id}/create-meeting")
async def create_from_template(template_id: str, request: Request):
    """Create a meeting using a template as defaults; delegate to services/meetings_crud
    so behaviour (host participant, invited/optional, custom recurring, ICS e-mails)
    stays consistent with POST /meetings."""
    from services.meetings_crud import create_meeting as _create
    user = await get_current_user(request)
    tmpl = await db.meeting_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}

    # Build MeetingCreateRequest by merging template defaults with body overrides
    generate_series = bool(body.get("generate_series", False))
    is_custom_tmpl = (
        tmpl.get("recurring") and (tmpl.get("recurring_pattern") or "") == "custom"
        and len(tmpl.get("recurring_schedule") or []) > 0
    )
    req_payload = {
        "title": body.get("title", tmpl["title"]),
        "description": tmpl.get("description", ""),
        "meeting_type": body.get("meeting_type", "scheduled"),
        "scheduled_at": body.get("scheduled_at"),
        "duration": tmpl["duration"],
        "timezone": body.get("timezone", "UTC"),
        "lobby_enabled": tmpl.get("lobby_enabled", False),
        "guest_access": tmpl.get("guest_access", True),
        "meeting_mode": tmpl["meeting_mode"],
        "chat_enabled": tmpl.get("chat_enabled", True),
        "reactions_enabled": tmpl.get("reactions_enabled", True),
        "recording_enabled": tmpl.get("recording_enabled", False),
        "transcript_enabled": tmpl.get("transcript_enabled", False),
        "invited_emails": tmpl.get("invited_emails") or [],
    }
    # Only pass recurring fields when caller explicitly wants the series generated.
    # For the default case (generate_series=false), we create a single meeting.
    if generate_series and is_custom_tmpl and req_payload["scheduled_at"]:
        req_payload.update({
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": tmpl.get("recurring_schedule") or [],
            "recurring_weeks": int(tmpl.get("recurring_weeks") or 8),
        })

    req = MeetingCreateRequest(**req_payload)
    result = await _create(req, user)

    # Post-stamp template_id for downstream analytics (not part of MeetingCreateRequest)
    await db.meetings.update_one({"meeting_id": result["meeting_id"]}, {"$set": {"template_id": template_id}})
    result["template_id"] = template_id

    # Report the number of generated occurrences (anchor's series_id minus the anchor itself)
    fresh = await db.meetings.find_one({"meeting_id": result["meeting_id"]}, {"_id": 0, "series_id": 1})
    series_id = (fresh or {}).get("series_id")
    if series_id:
        occ_count = await db.meetings.count_documents(
            {"series_id": series_id, "meeting_id": {"$ne": result["meeting_id"]}}
        )
        if occ_count:
            result["_series_generated"] = occ_count
    return result




@router.get("/organization/branding")
async def get_branding(request: Request):
    branding = await db.organization_branding.find_one({}, {"_id": 0})
    if not branding:
        return {
            "company_name": "MeetFlow", "primary_color": "#4A5D4E",
            "logo_url": "", "email_footer": "Sent via MeetFlow",
            "favicon_url": "",
        }
    return branding

@router.put("/organization/branding")
async def update_branding(req: BrandingUpdateRequest, request: Request):
    user = await get_current_user(request)
    if not await has_cap(user, "admin.manage_branding", db):
        raise HTTPException(status_code=403, detail="Admin access required")
    updates = {}
    if req.company_name is not None: updates["company_name"] = req.company_name
    if req.primary_color is not None: updates["primary_color"] = req.primary_color
    if req.logo_url is not None: updates["logo_url"] = req.logo_url
    if req.email_footer is not None: updates["email_footer"] = req.email_footer
    if req.favicon_url is not None: updates["favicon_url"] = req.favicon_url
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.organization_branding.update_one({}, {"$set": updates}, upsert=True)
    return await db.organization_branding.find_one({}, {"_id": 0})

@router.post("/organization/branding/logo")
async def upload_logo(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    if not await has_cap(user, "admin.manage_branding", db):
        raise HTTPException(status_code=403, detail="Admin access required")
    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    path = f"{APP_STORAGE_PREFIX}/branding/logo_{uuid.uuid4().hex[:8]}.{ext}"
    data = await file.read()
    try:
        result = await asyncio.to_thread(put_object, path, data, file.content_type or "image/png")
        logo_path = result.get("path", path)
        updated_at = datetime.now(timezone.utc).isoformat()
        # Iter 281 — also write `logo_url` so the frontend (Sidebar, Login,
        # Email-Templates …) actually picks the logo up. Without this, the
        # upload only sets `logo_storage_path` and the visible UI keeps
        # showing the old/empty logo until the admin manually pastes a URL.
        # The `?v=` cache-buster forces every client to refetch.
        logo_url = f"/api/organization/branding/logo?v={uuid.uuid4().hex[:8]}"
        await db.organization_branding.update_one(
            {},
            {"$set": {
                "logo_storage_path": logo_path,
                "logo_url": logo_url,
                "updated_at": updated_at,
            }},
            upsert=True,
        )
        return {"path": logo_path, "logo_url": logo_url, "updated_at": updated_at, "message": "Logo uploaded"}
    except Exception as e:
        logger.error(f"Logo upload failed: {e}")
        raise HTTPException(status_code=500, detail="Logo upload failed")

@router.get("/organization/branding/logo")
async def get_logo(request: Request):
    """Public endpoint — referenced via <img src> on login page, in emails
    and in the Sidebar. Must work without an auth cookie."""
    branding = await db.organization_branding.find_one({}, {"_id": 0})
    if not branding or not branding.get("logo_storage_path"):
        raise HTTPException(status_code=404, detail="No logo uploaded")
    try:
        data, ct = await asyncio.to_thread(get_object, branding["logo_storage_path"])
        # Iter 281 — short cache so logo updates appear within a minute;
        # the `?v=` cache-buster set in upload_logo flushes it instantly
        # for clients that read the updated branding doc.
        return Response(content=data, media_type=ct, headers={"Cache-Control": "public, max-age=60"})
    except Exception:
        raise HTTPException(status_code=500, detail="Logo not available")




@router.post("/meetings/{meeting_id}/files")
async def upload_meeting_file(meeting_id: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    path = f"{APP_STORAGE_PREFIX}/meetings/{meeting_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    try:
        result = await asyncio.to_thread(put_object, path, data, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
    file_doc = {
        "file_id": f"file_{uuid.uuid4().hex[:10]}", "meeting_id": meeting_id,
        "storage_path": result.get("path", path), "original_filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": result.get("size", len(data)), "uploaded_by": user["user_id"],
        "uploaded_by_name": user["name"], "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.meeting_files.insert_one(file_doc)
    return await db.meeting_files.find_one({"file_id": file_doc["file_id"]}, {"_id": 0})

@router.get("/meetings/{meeting_id}/files")
async def list_meeting_files(meeting_id: str):
    return await db.meeting_files.find({"meeting_id": meeting_id, "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(50)

@router.get("/files/{file_id}/download")
async def download_file(file_id: str, request: Request):
    await get_current_user(request)
    record = await db.meeting_files.find_one({"file_id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, ct = await asyncio.to_thread(get_object, record["storage_path"])
        return Response(content=data, media_type=record.get("content_type", ct),
                       headers={"Content-Disposition": f'attachment; filename="{record["original_filename"]}"'})
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail="Download failed")

@router.delete("/files/{file_id}")
async def delete_file(file_id: str, request: Request):
    await get_current_user(request)
    await db.meeting_files.update_one({"file_id": file_id}, {"$set": {"is_deleted": True}})
    return {"message": "File deleted"}




