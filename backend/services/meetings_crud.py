"""Meeting CRUD business logic, extracted from routes/meetings/core.py (Iter 89-91).

Preserves exact behaviour. Route handlers become:
    return await meetings_crud.create_meeting(req, user)
    return await meetings_crud.update_meeting(meeting_id, body, user)
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import HTTPException

from database import db
from services.meetings_recurring import generate_custom_schedule, generate_custom_dates
from services.permissions import has_cap

logger = logging.getLogger(__name__)


# Fields that can be changed via PUT /meetings/{id}.
# Keep this list in one place so both the route's OpenAPI spec and the
# implementation stay in sync.
UPDATABLE_MEETING_FIELDS = [
    "title", "description", "scheduled_at", "duration",
    "lobby_enabled", "guest_access",
    "chat_enabled", "reactions_enabled",
    "recording_enabled", "transcript_enabled",
    "status",
    "auto_rering",
]


async def update_meeting(meeting_id: str, body: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Validate ownership/permission, apply whitelisted updates, return the
    fresh document. Raises HTTPException(404/403) as needed."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting["host_id"] != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    updates = {k: v for k, v in body.items() if k in UPDATABLE_MEETING_FIELDS}
    if updates:
        await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": updates})
    return await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})


async def create_meeting(req, user: Dict[str, Any]) -> Dict[str, Any]:
    """Create meeting doc + host participant + invited/optional participants,
    optionally generate custom-recurring occurrences, and schedule an ICS
    invitation e-mail dispatch. Returns the persisted meeting document.
    """
    meeting_id = f"meet_{uuid.uuid4().hex[:10]}"
    meeting_code = f"{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:3]}"
    scheduled = req.scheduled_at if req.scheduled_at and req.scheduled_at.strip() else None
    duration = req.duration_minutes if req.duration_minutes is not None else req.duration
    meeting = {
        "meeting_id": meeting_id, "meeting_code": meeting_code,
        "title": req.title, "description": req.description,
        "meeting_type": req.meeting_type, "scheduled_at": scheduled,
        "duration": duration, "timezone": req.timezone,
        "recurring": req.recurring, "recurring_pattern": req.recurring_pattern if req.recurring else None,
        "recurring_schedule": (req.recurring_schedule or []) if (req.recurring and req.recurring_pattern == "custom") else [],
        "recurring_weeks": req.recurring_weeks if (req.recurring and req.recurring_pattern == "custom") else None,
        "recurring_dates": (req.recurring_dates or []) if (req.recurring and req.recurring_pattern == "custom_dates") else [],
        "lobby_enabled": req.lobby_enabled, "guest_access": req.guest_access,
        "meeting_mode": req.meeting_mode, "chat_enabled": req.chat_enabled,
        "reactions_enabled": req.reactions_enabled,
        "recording_enabled": req.recording_enabled,
        "transcript_enabled": req.transcript_enabled,
        "auto_rering": req.auto_rering,
        "reminder_minutes": req.reminder_minutes, "reminder_sent": False,
        "host_id": user["user_id"], "host_name": user["name"],
        "status": "active" if req.meeting_type == "instant" else "scheduled",
        "created_at": datetime.now(timezone.utc).isoformat(), "ended_at": None,
        "participant_count": 1 if req.meeting_type == "instant" else 0,
    }
    await db.meetings.insert_one(meeting)
    participant = {
        "meeting_id": meeting_id, "user_id": user["user_id"],
        "name": user["name"], "email": user["email"],
        "avatar": user.get("avatar", ""), "role": "host",
        "joined_at": datetime.now(timezone.utc).isoformat() if req.meeting_type == "instant" else None,
        "left_at": None, "mic_on": True, "camera_on": True,
        "hand_raised": False, "is_presenting": False,
    }
    await db.meeting_participants.insert_one(participant)
    await _persist_invitees(meeting_id, req.invited_emails, is_optional=False)
    await _persist_invitees(meeting_id, req.optional_emails, is_optional=True)

    # Ring the invitees right now if this is an instant meeting — pops the
    # fullscreen IncomingCallModal on their screens.
    if req.meeting_type == "instant":
        try:
            from routes.chat import chat_ws
            frontend_url = os.environ.get("FRONTEND_URL", "")
            join_url = f"{frontend_url}/meetings/{meeting_id}/join"
            # Collect all invited user_ids (both lists)
            invitee_rows = await db.meeting_participants.find(
                {"meeting_id": meeting_id, "user_id": {"$ne": None, "$exists": True}},
                {"_id": 0, "user_id": 1}
            ).to_list(200)
            for row in invitee_rows:
                uid = row.get("user_id")
                if not uid or uid == user["user_id"]:
                    continue
                await chat_ws.send_to_user(uid, {
                    "type": "incoming-call",
                    "conversation_id": None,
                    "conversation_name": req.title,
                    "conversation_type": "meeting",
                    "meeting_id": meeting_id,
                    "meeting_code": meeting_code,
                    "join_url": join_url,
                    "caller_id": user["user_id"],
                    "caller_name": user.get("name", ""),
                    "caller_avatar": user.get("avatar", ""),
                    "call_kind": "meeting",
                    "started_at": meeting["created_at"],
                })
        except Exception as e:
            logger.warning(f"[meeting-ring] failed for {meeting_id}: {e}")

    # Auto-generate occurrences for custom recurring pattern
    if req.recurring and req.recurring_pattern == "custom" and req.recurring_schedule:
        try:
            await generate_custom_schedule(
                meeting_id=meeting_id,
                template=await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0}),
                schedule=req.recurring_schedule,
                weeks=req.recurring_weeks or 8,
                user=user,
            )
        except Exception as e:
            logger.warning(f"Custom recurring generation failed: {e}")

    # iter 168 — Explicit-date custom recurring pattern.
    if req.recurring and req.recurring_pattern == "custom_dates" and req.recurring_dates:
        try:
            await generate_custom_dates(
                meeting_id=meeting_id,
                template=await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0}),
                dates=req.recurring_dates,
                user=user,
            )
        except Exception as e:
            logger.warning(f"Custom-dates recurring generation failed: {e}")

    # ICS-Auto-Email to invited participants (fire-and-forget, failure is non-fatal)
    invitees = [e for e in ((req.invited_emails or []) + (req.optional_emails or [])) if e and e.strip()]
    if invitees and req.meeting_type == "scheduled":
        async def _dispatch():
            try:
                from services.ics_invites import send_meeting_invitations
                await send_meeting_invitations(meeting_id, invitees, host_name=user.get("name", ""))
            except Exception as e:
                logger.warning(f"ICS invitation send failed: {e}")
        asyncio.create_task(_dispatch())

    return await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})


async def _persist_invitees(meeting_id: str, emails, *, is_optional: bool) -> None:
    """Write one meeting_participants doc per e-mail in the list. Known users
    get their user_id + name + avatar; unknown e-mails are stored as 'guest'
    rows (user_id=None, name=email localpart)."""
    for email_addr in (emails or []):
        if not email_addr or not email_addr.strip():
            continue
        email_clean = email_addr.lower().strip()
        inv_user = await db.users.find_one({"email": email_clean}, {"_id": 0})
        await db.meeting_participants.insert_one({
            "meeting_id": meeting_id,
            "user_id": inv_user["user_id"] if inv_user else None,
            "name": inv_user["name"] if inv_user else email_clean.split("@")[0],
            "email": email_clean,
            "avatar": inv_user.get("avatar", "") if inv_user else "",
            "role": "participant", "joined_at": None, "left_at": None,
            "mic_on": True, "camera_on": True, "hand_raised": False, "is_presenting": False,
            "is_optional": is_optional,
        })
