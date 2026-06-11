"""Meeting lifecycle state transitions — delete / restore / join / leave.

Extracted from routes/meetings/core.py (Iter 92) to keep state-transition
logic isolated from CRUD. Behaviour is preserved byte-for-byte — these are
pure moves with minimal decomposition.

Side effects handled here:
- participant counts + meeting status (scheduled → active → ended)
- user's status_mode (online → dnd on join, restored on leave)
- WebSocket broadcast of status changes
- Fire-and-forget auto-send of summary e-mail when the last participant leaves
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import HTTPException

from database import db
from services.permissions import has_cap

logger = logging.getLogger(__name__)


# ---------- Delete / Restore ----------

async def delete_meeting(meeting_id: str, user: Dict[str, Any], *, soft: bool = False) -> Dict[str, Any]:
    """Delete a meeting. If `soft=true` AND it belongs to a series, mark
    status='cancelled' instead of hard-deleting — preserves audit trail."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting["host_id"] != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    if soft and meeting.get("series_id"):
        await db.meetings.update_one(
            {"meeting_id": meeting_id},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_by": user["user_id"],
            }},
        )
        return {"message": "Meeting cancelled", "soft": True}
    await db.meetings.delete_one({"meeting_id": meeting_id})
    await db.meeting_participants.delete_many({"meeting_id": meeting_id})
    await db.chat_messages.delete_many({"meeting_id": meeting_id})
    return {"message": "Meeting deleted"}


async def restore_meeting(meeting_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Undo a soft-cancellation — reverts status to 'scheduled'."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.get("status") != "cancelled":
        raise HTTPException(status_code=400, detail="Meeting ist nicht abgesagt")
    if meeting["host_id"] != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.meetings.update_one(
        {"meeting_id": meeting_id},
        {"$set": {"status": "scheduled"}, "$unset": {"cancelled_at": "", "cancelled_by": ""}},
    )
    return {"message": "Meeting wiederhergestellt"}


# ---------- Join / Leave ----------

async def _set_user_in_meeting(user_id: str, user_name: str, mid: str) -> None:
    """Switch the user's status_mode to DND for the duration of the meeting,
    remember the previous status so we can restore it on leave."""
    try:
        prev = await db.users.find_one({"user_id": user_id}, {"_id": 0, "status_mode": 1})
        prev_status = (prev or {}).get("status_mode") or "online"
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "status_mode": "dnd",
                "in_meeting": mid,
                "status_before_meeting": prev_status,
                "status_updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        from routes.chat import chat_ws
        await chat_ws.broadcast_status(user_id, "dnd", user_name)
    except Exception as e:
        logger.warning(f"[auto-status] join failed: {e}")


async def _restore_user_status(user_id: str, user_name: str, mid: str) -> None:
    """Restore the user's pre-meeting status + broadcast over WS."""
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "status_before_meeting": 1, "in_meeting": 1})
        if u and u.get("in_meeting") == mid:
            restored = u.get("status_before_meeting") or "online"
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"status_mode": restored, "in_meeting": None, "status_before_meeting": None}},
            )
            from routes.chat import chat_ws
            await chat_ws.broadcast_status(user_id, restored, user_name)
    except Exception as e:
        logger.warning(f"[auto-status] leave failed: {e}")


async def join_meeting(meeting_id_or_code: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Join a meeting by meeting_id or meeting_code. Upserts the participant,
    recomputes active-count, flips meeting status to 'active', and sets the
    user's DND status."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id_or_code}, {"_id": 0})
    if not meeting:
        meeting = await db.meetings.find_one({"meeting_code": meeting_id_or_code}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    mid = meeting["meeting_id"]
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.meeting_participants.find_one(
        {"meeting_id": mid, "user_id": user["user_id"]}, {"_id": 0}
    )
    if existing:
        await db.meeting_participants.update_one(
            {"meeting_id": mid, "user_id": user["user_id"]},
            {"$set": {"joined_at": now, "left_at": None}},
        )
    else:
        await db.meeting_participants.insert_one({
            "meeting_id": mid, "user_id": user["user_id"],
            "name": user["name"], "email": user["email"],
            "avatar": user.get("avatar", ""), "role": "participant",
            "joined_at": now, "left_at": None, "mic_on": True,
            "camera_on": True, "hand_raised": False, "is_presenting": False,
        })
    count = await db.meeting_participants.count_documents(
        {"meeting_id": mid, "joined_at": {"$ne": None}, "left_at": None}
    )
    was_scheduled = meeting.get("status") == "scheduled"
    await db.meetings.update_one({"meeting_id": mid}, {"$set": {"participant_count": count, "status": "active"}})
    await _set_user_in_meeting(user["user_id"], user.get("name", ""), mid)

    # Ring invitees when host kicks off a scheduled meeting (iter 142).
    # We only fire when `was_scheduled` AND this join flips the status to
    # `active` for the first time — so subsequent late joiners don't
    # re-ring the people who are already inside.
    if was_scheduled and count == 1:
        await _fan_out_ring(meeting, user, only_missing=False)
        # iter 147 — Auto-Nachklingeln: if the meeting is flagged
        # `auto_rering`, schedule up to 3 follow-up rings at 30 s intervals
        # to nudge invitees who haven't joined yet. Perfect for time-critical
        # clinical contexts where the host doesn't want to manually press
        # "Klingeln" while starting the meeting.
        if meeting.get("auto_rering"):
            asyncio.create_task(_auto_rering_loop(mid, user, attempts=3, interval_s=30))

    return await db.meetings.find_one({"meeting_id": mid}, {"_id": 0})


# ---------- Ring Fan-Out (shared helper — iter 142 / iter 143) ----------

async def _fan_out_ring(meeting: Dict[str, Any], caller: Dict[str, Any], *, only_missing: bool) -> int:
    """Send `incoming-call` WS event + Web-Push to meeting invitees.

    * When `only_missing=False` (called from join_meeting at first-join):
      Rings every invitee with a user_id except the caller themselves.
    * When `only_missing=True` (called from the manual "Jetzt klingeln"
      button by the host): Rings only invitees who are not currently in
      the room — someone who already sits inside doesn't need a ring.
    Returns the number of users we attempted to ring.
    """
    mid = meeting["meeting_id"]
    caller_id = caller["user_id"]
    now = datetime.now(timezone.utc).isoformat()
    try:
        from routes.chat import chat_ws
        from services.news_push import send_push_to_user
        import os
        frontend_url = os.environ.get("FRONTEND_URL", "")
        join_url = f"{frontend_url}/meetings/{mid}/join"

        invitee_rows = await db.meeting_participants.find(
            {"meeting_id": mid, "user_id": {"$ne": None, "$exists": True}},
            {"_id": 0, "user_id": 1, "joined_at": 1, "left_at": 1},
        ).to_list(200)

        targets = []
        for row in invitee_rows:
            uid = row.get("user_id")
            if not uid or uid == caller_id:
                continue
            if only_missing:
                # Skip users currently in the room
                if row.get("joined_at") and not row.get("left_at"):
                    continue
            targets.append(uid)

        call_payload = {
            "type": "incoming-call",
            "conversation_id": None,
            "conversation_name": meeting.get("title") or "",
            "conversation_type": "meeting",
            "meeting_id": mid,
            "meeting_code": meeting.get("meeting_code") or "",
            "join_url": join_url,
            "caller_id": caller_id,
            "caller_name": caller.get("name", ""),
            "caller_avatar": caller.get("avatar", ""),
            "call_kind": "meeting",
            "started_at": now,
        }
        push_title = f"📞 {caller.get('name', 'Jemand')}"
        push_body = meeting.get("title") or "Meeting startet jetzt"
        push_data = {
            "url": f"/meetings/{mid}/join",
            "tag": f"meeting-{mid}",
            "kind": "meeting_call",
            "meeting_id": mid,
            "caller_id": caller_id,
            "urgent": True,
        }

        for uid in targets:
            try:
                await chat_ws.send_to_user(uid, call_payload)
            except Exception as ws_err:
                logger.warning(f"[meeting-ring] WS to {uid} failed: {ws_err}")
            try:
                await send_push_to_user(uid, title=push_title, body=push_body, data=push_data)
            except Exception as push_err:
                logger.warning(f"[meeting-ring] push to {uid} failed: {push_err}")

        return len(targets)
    except Exception as e:
        logger.warning(f"[meeting-ring] fan-out failed for {mid}: {e}")
        return 0


async def ring_meeting(meeting_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Host-initiated manual re-ring — pings invitees who are not currently
    in the room. Used by the 'Jetzt klingeln' button in the meeting detail
    dialog to nudge latecomers without restarting the meeting."""
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting["host_id"] != user["user_id"] and not await has_cap(user, "meetings.manage_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    rang = await _fan_out_ring(meeting, user, only_missing=True)
    return {"rang": rang}


async def _auto_rering_loop(meeting_id: str, caller: Dict[str, Any], *, attempts: int, interval_s: int) -> None:
    """Background task that re-rings missing invitees every `interval_s`
    seconds, up to `attempts` times. Stops early when:
      * the meeting is no longer active (ended / cancelled)
      * every invitee with a user_id has joined
      * a ring-out finds no targets (everyone inside or unreachable)
    """
    for i in range(attempts):
        try:
            await asyncio.sleep(interval_s)
            meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
            if not meeting or meeting.get("status") != "active":
                logger.info(f"[auto-rering] {meeting_id} stopped — status={meeting and meeting.get('status')}")
                return
            rang = await _fan_out_ring(meeting, caller, only_missing=True)
            logger.info(f"[auto-rering] {meeting_id} attempt {i + 1}/{attempts} → rang={rang}")
            if rang == 0:
                return
        except Exception as e:
            logger.warning(f"[auto-rering] {meeting_id} attempt {i + 1} failed: {e}")
            return


async def leave_meeting(meeting_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Record left_at, recompute count, restore user status, and auto-end +
    trigger summary e-mail when the last participant leaves."""
    await db.meeting_participants.update_one(
        {"meeting_id": meeting_id, "user_id": user["user_id"]},
        {"$set": {"left_at": datetime.now(timezone.utc).isoformat()}},
    )
    count = await db.meeting_participants.count_documents(
        {"meeting_id": meeting_id, "joined_at": {"$ne": None}, "left_at": None}
    )
    await db.meetings.update_one({"meeting_id": meeting_id}, {"$set": {"participant_count": count}})
    await _restore_user_status(user["user_id"], user.get("name", ""), meeting_id)
    if count == 0:
        await db.meetings.update_one(
            {"meeting_id": meeting_id},
            {"$set": {"status": "ended", "ended_at": datetime.now(timezone.utc).isoformat()}},
        )
        # iter 153 — When the last participant leaves (meeting auto-ends),
        # send a `call-cancelled` WS event so any invitee whose phone is
        # still ringing (IncomingCallModal open) dismisses the modal and
        # stops the ringtone. Without this the callee's phone keeps
        # ringing until the 45 s auto-dismiss timeout fires — super
        # annoying when the caller just hung up.
        try:
            from routes.chat import chat_ws
            invitee_rows = await db.meeting_participants.find(
                {"meeting_id": meeting_id, "user_id": {"$ne": None, "$exists": True}},
                {"_id": 0, "user_id": 1},
            ).to_list(200)
            payload = {
                "type": "call-cancelled",
                "meeting_id": meeting_id,
                "reason": "ended_by_caller",
                "ended_by": user["user_id"],
            }
            for row in invitee_rows:
                uid = row.get("user_id")
                if uid and uid != user["user_id"]:
                    try:
                        await chat_ws.send_to_user(uid, payload)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[call-cancelled] broadcast failed for {meeting_id}: {e}")

        from services.meetings_summaries import auto_send_summary_email
        asyncio.create_task(auto_send_summary_email(meeting_id))
    return {"message": "Left meeting"}
