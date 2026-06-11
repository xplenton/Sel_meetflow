"""Calendar-driven DND auto-status sync (iter 148).

User request: "nicht stören wenn im kalender termine drin sind. Davon
bleiben manuelle änderungen unberührt"

Every few minutes this task looks at each connected user and checks
whether they have an active (in-progress) meeting where they're either
the host or an invitee. If yes → auto-flip their status_mode to `dnd`.
If the calendar is clear AND the user is currently auto-dnd → revert
them to `online`.

Manual overrides are respected via the `status_manually_set_at` field —
any status set within the last 24 h through PUT /chat/my-status is
considered manual and left alone.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from database import db

logger = logging.getLogger(__name__)

MANUAL_STICKINESS_HOURS = 24


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _is_manual(user_id: str) -> bool:
    """True when the user set their status manually within the stickiness
    window. Auto-logic must not override a fresh manual pick."""
    u = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "status_manually_set_at": 1},
    )
    if not u:
        return False
    ts = u.get("status_manually_set_at")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return False
    return datetime.now(timezone.utc) - dt < timedelta(hours=MANUAL_STICKINESS_HOURS)


async def _has_active_meeting(user_id: str, now_dt: datetime) -> bool:
    """Check whether `user_id` has any meeting window covering `now_dt`.

    A "meeting" here is either:
      * a scheduled meeting where the user is host or invitee and
        scheduled_at <= now <= scheduled_at + duration
      * a focus_times entry spanning now (legacy, still supported)
    """
    now_iso = now_dt.isoformat()
    # Focus times (legacy — admins set these for themselves via the Profile UI)
    ft = await db.focus_times.find_one(
        {"user_id": user_id, "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
        {"_id": 0},
    )
    if ft:
        return True
    # Active scheduled meetings as host or participant
    hosted = await db.meetings.find(
        {"host_id": user_id, "status": {"$in": ["scheduled", "active"]}, "scheduled_at": {"$ne": None}},
        {"_id": 0, "scheduled_at": 1, "duration": 1},
    ).to_list(50)
    for m in hosted:
        try:
            start = datetime.fromisoformat(m["scheduled_at"].replace("Z", "+00:00"))
            dur = int(m.get("duration") or 60)
            end = start + timedelta(minutes=dur)
            if start <= now_dt <= end:
                return True
        except Exception:
            continue
    # As invitee (via meeting_participants)
    part_rows = await db.meeting_participants.find(
        {"user_id": user_id, "role": {"$in": ["participant", "host"]}},
        {"_id": 0, "meeting_id": 1},
    ).to_list(100)
    meeting_ids = [r["meeting_id"] for r in part_rows if r.get("meeting_id")]
    if not meeting_ids:
        return False
    meetings = await db.meetings.find(
        {"meeting_id": {"$in": meeting_ids}, "status": {"$in": ["scheduled", "active"]}, "scheduled_at": {"$ne": None}},
        {"_id": 0, "scheduled_at": 1, "duration": 1},
    ).to_list(200)
    for m in meetings:
        try:
            start = datetime.fromisoformat(m["scheduled_at"].replace("Z", "+00:00"))
            dur = int(m.get("duration") or 60)
            end = start + timedelta(minutes=dur)
            if start <= now_dt <= end:
                return True
        except Exception:
            continue
    return False


async def sync_calendar_dnd() -> dict:
    """One maintenance tick. Returns {auto_dnd, auto_online, skipped_manual}.

    Only affects users who are currently online (have an active chat WS).
    We can't flip offline users to DND — they're already offline.
    """
    from routes.chat import chat_ws
    now_dt = datetime.now(timezone.utc)
    auto_dnd = 0
    auto_online = 0
    skipped_manual = 0
    # Snapshot connected user_ids (dict iteration + WS churn safety)
    connected_ids = list(chat_ws.connections.keys())
    for uid in connected_ids:
        try:
            if await _is_manual(uid):
                skipped_manual += 1
                continue
            u = await db.users.find_one({"user_id": uid}, {"_id": 0, "status_mode": 1, "name": 1, "in_meeting": 1, "status_auto_dnd": 1})
            if not u:
                continue
            # Skip users already in a live meeting — _set_user_in_meeting has
            # them correctly marked dnd and will restore on leave.
            if u.get("in_meeting"):
                continue
            active = await _has_active_meeting(uid, now_dt)
            current = u.get("status_mode") or "online"
            was_auto_dnd = bool(u.get("status_auto_dnd"))
            if active and current != "dnd":
                await db.users.update_one(
                    {"user_id": uid},
                    {"$set": {"status_mode": "dnd", "status_auto_dnd": True, "status_updated_at": _now_iso()}},
                )
                auto_dnd += 1
                try:
                    await chat_ws.broadcast_status(uid, "dnd", u.get("name", ""))
                except Exception:
                    pass
            elif (not active) and was_auto_dnd and current == "dnd":
                await db.users.update_one(
                    {"user_id": uid},
                    {"$set": {"status_mode": "online", "status_auto_dnd": False, "status_updated_at": _now_iso()}},
                )
                auto_online += 1
                try:
                    await chat_ws.broadcast_status(uid, "online", u.get("name", ""))
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[calendar-status] sync failed for {uid}: {e}")
    logger.info(f"[calendar-status] auto_dnd={auto_dnd} auto_online={auto_online} skipped_manual={skipped_manual}")
    return {"auto_dnd": auto_dnd, "auto_online": auto_online, "skipped_manual": skipped_manual}
