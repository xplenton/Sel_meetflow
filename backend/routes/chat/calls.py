from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import db, logger
from dependencies import get_current_user
import uuid
import os

from ._shared import (
    chat_ws, _send_system_message,
)

router = APIRouter()

@router.post("/chat/conversations/{conv_id}/call")
async def start_call_from_chat(conv_id: str, request: Request):
    user = await get_current_user(request)
    # Optional body: { "urgent": true } — bypasses callee DND + louder ring
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    urgent = bool(body.get("urgent"))
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden")
    meeting_id = f"meet_{uuid.uuid4().hex[:10]}"
    meeting_code = f"{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:3]}"
    title = f"Anruf: {conv.get('name') or 'Chat'}"
    meeting = {
        "meeting_id": meeting_id, "meeting_code": meeting_code,
        "title": title, "description": "Gestartet aus Chat",
        "meeting_type": "instant", "scheduled_at": None,
        "duration": 60, "timezone": "Europe/Berlin",
        "recurring": False, "lobby_enabled": False, "guest_access": True,
        "meeting_mode": "standard", "chat_enabled": True,
        "reactions_enabled": True, "recording_enabled": False,
        "transcript_enabled": False, "reminder_minutes": 0, "reminder_sent": False,
        "host_id": user["user_id"], "host_name": user.get("name", ""),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(), "ended_at": None,
        "participant_count": 0,
    }
    await db.meetings.insert_one(meeting)
    await db.meeting_participants.insert_one({
        "meeting_id": meeting_id, "user_id": user["user_id"],
        "name": user.get("name", ""), "email": user.get("email", ""),
        "avatar": user.get("avatar", ""), "role": "host",
        "joined_at": datetime.now(timezone.utc).isoformat(),
        "left_at": None, "mic_on": True, "camera_on": True,
        "hand_raised": False, "is_presenting": False,
    })
    frontend_url = os.environ.get("FRONTEND_URL", "")
    join_url = f"{frontend_url}/meetings/{meeting_id}/join"
    await _send_system_message(conv_id, f"{user.get('name', '')} hat einen Anruf gestartet")
    call_msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    call_msg = {
        "message_id": call_msg_id, "conversation_id": conv_id,
        "sender_id": user["user_id"], "sender_name": user.get("name", ""),
        "sender_avatar": user.get("avatar", ""),
        "content": join_url, "type": "call",
        "meeting_id": meeting_id, "meeting_code": meeting_code,
        "file_url": None, "file_name": None, "file_type": None,
        "mentions": [], "priority": "normal", "reply_to": None, "reply_preview": None,
        "reactions": [], "edited": False, "deleted": False, "thread_count": 0,
        "urgent": urgent,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(call_msg)
    msg_clean = {k: v for k, v in call_msg.items() if k != "_id"}
    await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": msg_clean, "conversation_id": conv_id})
    # Dedicated incoming-call event — the global IncomingCallModal listens on
    # the user's chat WS and pops up a ringing fullscreen UI for every callee,
    # regardless of which page they're currently viewing.
    for member in (conv.get("members") or []):
        uid = member.get("user_id") if isinstance(member, dict) else member
        if uid and uid != user["user_id"]:
            await chat_ws.send_to_user(uid, {
                "type": "incoming-call",
                "conversation_id": conv_id,
                "conversation_name": conv.get("name") or "",
                "conversation_type": conv.get("type") or "direct",
                "meeting_id": meeting_id,
                "meeting_code": meeting_code,
                "join_url": join_url,
                "caller_id": user["user_id"],
                "caller_name": user.get("name", ""),
                "caller_avatar": user.get("avatar", ""),
                "message_id": call_msg_id,
                "call_kind": "chat",
                "urgent": urgent,
                "started_at": call_msg["created_at"],
            })
    # Push notification to callees — they likely have their phone locked
    # (log with exc_info so a failed fan-out is diagnosable; before iter 138
    # we only logged the exception message, which hid member-structure bugs).
    try:
        from services.chat_push import push_new_chat_message
        push_res = await push_new_chat_message(
            conv_id, user["user_id"], user.get("name", ""),
            "call", join_url,
            target_url=f"/meetings/{meeting_id}/join",
            urgent=urgent,
        )
        logger.info(f"[chat] call push dispatched: sent={push_res.get('sent')} failed={push_res.get('failed')} recipients={push_res.get('recipients')}")
    except Exception as e:
        logger.exception(f"[chat] call push dispatch failed: {e}")
    # Schedule missed-call watcher — if nobody (other than the caller) joins
    # within 45 seconds the message gets re-labeled "Verpasster Anruf".
    try:
        from services.chat_call_watcher import schedule_missed_call_check
        schedule_missed_call_check(meeting_id=meeting_id, message_id=call_msg_id, caller_id=user["user_id"])
    except Exception as e:
        logger.warning(f"[chat] missed-call watcher failed: {e}")
    return {"meeting_id": meeting_id, "join_url": join_url}



# ============ SEARCH ============

