"""Host control actions for an active meeting — mute_all / unmute_all,
toggle_{chat,reactions,hand_raise,screen_share,lobby}.

Extracted from routes/meetings/reports.py (Iter 93). Broadcasts every
state change over the WebSocket for live-UI updates.
"""
from __future__ import annotations

from typing import Dict, Any

from fastapi import HTTPException

from database import db
from services.ws_manager import ws_manager


# Mapping of action string → Meeting document field that holds the toggled flag.
_TOGGLE_MAP = {
    "toggle_chat": "chat_enabled",
    "toggle_reactions": "reactions_enabled",
    "toggle_hand_raise": "hand_raise_enabled",
    "toggle_screen_share": "screen_share_enabled",
    "toggle_lobby": "lobby_enabled",
}


async def _assert_host_or_cohost(meeting_id: str, user: Dict[str, Any]) -> None:
    hp = await db.meeting_participants.find_one(
        {"meeting_id": meeting_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not hp or hp["role"] not in ("host", "co-host"):
        raise HTTPException(status_code=403, detail="Not authorized")


async def host_control(meeting_id: str, action: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch host-control action. Returns a result dict suitable for the
    JSON response. Raises HTTPException(403) if caller is not host/co-host."""
    await _assert_host_or_cohost(meeting_id, user)
    by = {"by": user["name"], "by_id": user["user_id"]}

    if action == "mute_all":
        await db.meeting_participants.update_many(
            {"meeting_id": meeting_id, "role": {"$nin": ["host", "co-host"]}},
            {"$set": {"mic_on": False}},
        )
        await ws_manager.broadcast(meeting_id, {"type": "host-control", "action": "mute_all", **by})
        return {"action": "mute_all", "status": "done"}

    if action == "unmute_all":
        await db.meeting_participants.update_many(
            {"meeting_id": meeting_id},
            {"$set": {"mic_on": True}},
        )
        await ws_manager.broadcast(meeting_id, {"type": "host-control", "action": "unmute_all", **by})
        return {"action": "unmute_all", "status": "done"}

    if action in _TOGGLE_MAP:
        field = _TOGGLE_MAP[action]
        meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
        new_val = not meeting.get(field, True)
        await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {field: new_val}})
        await ws_manager.broadcast(
            meeting_id,
            {"type": "host-control", "action": action, "field": field, "value": new_val, **by},
        )
        return {"action": action, "status": "toggled", "value": new_val}

    return {"action": action, "status": "unknown"}


async def send_invitations(meeting_id: str, emails_override, user: Dict[str, Any]) -> Dict[str, Any]:
    """Manually (re-)send ICS meeting invitations. If `emails_override` is
    falsy, all non-host participants are used. Returns the service result
    (total/sent/failed counts)."""
    from services.permissions import has_cap
    meeting = await db.meetings.find_one(
        {"meeting_id": meeting_id}, {"_id": 0, "host_id": 1, "title": 1}
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting["host_id"] != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    emails = emails_override
    if not emails:
        participants = await db.meeting_participants.find(
            {"meeting_id": meeting_id, "role": {"$ne": "host"}},
            {"_id": 0, "email": 1},
        ).to_list(500)
        emails = [p["email"] for p in participants if p.get("email")]
    if not emails:
        return {"total": 0, "sent": 0, "failed": 0, "reason": "no_recipients"}
    from services.ics_invites import send_meeting_invitations
    return await send_meeting_invitations(meeting_id, emails, host_name=user.get("name", ""))


async def lobby_action(meeting_id: str, target_user_id: str, action: str, host: Dict[str, Any]) -> Dict[str, Any]:
    """Host approves/rejects a user waiting in the lobby."""
    from datetime import datetime, timezone
    await _assert_host_or_cohost(meeting_id, host)
    if action == "approve":
        await db.meeting_participants.update_one(
            {"meeting_id": meeting_id, "user_id": target_user_id},
            {"$set": {"lobby_status": "approved", "joined_at": datetime.now(timezone.utc).isoformat()}},
        )
        await ws_manager.broadcast(meeting_id, {
            "type": "lobby-approved", "user_id": target_user_id, "by": host.get("name", ""),
        })
    elif action == "reject":
        await db.meeting_participants.update_one(
            {"meeting_id": meeting_id, "user_id": target_user_id},
            {"$set": {"lobby_status": "rejected"}},
        )
        await ws_manager.broadcast(meeting_id, {
            "type": "lobby-rejected", "user_id": target_user_id, "by": host.get("name", ""),
        })
    return await db.meeting_participants.find_one(
        {"meeting_id": meeting_id, "user_id": target_user_id}, {"_id": 0}
    )
