"""Dashboard & agenda builders for the MeetFlow landing widgets.

Extracted from routes/meetings/live.py (Iter 96). The route handlers just
call `build_stats(user)` / `build_agenda(user)` — heavy queries + formatting
live here so they can be unit-tested without FastAPI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from database import db


async def _my_meeting_ids(user_id: str) -> List[str]:
    docs = await db.meeting_participants.find(
        {"user_id": user_id}, {"_id": 0, "meeting_id": 1}
    ).to_list(5000)
    return [d["meeting_id"] for d in docs]


def _parse_iso(s: str) -> datetime | None:
    try:
        from dateutil import parser as dtparser
        return dtparser.isoparse(s)
    except Exception:
        return None


async def _compute_total_hours(my_ids: List[str]) -> float:
    """Sum duration of ended meetings, fallback to created/ended delta."""
    ended = await db.meetings.find(
        {"meeting_id": {"$in": my_ids}, "status": "ended"},
        {"_id": 0, "duration": 1, "created_at": 1, "ended_at": 1},
    ).to_list(5000)
    total = 0.0
    for m in ended:
        dur = m.get("duration")
        if dur and isinstance(dur, (int, float)) and dur > 0:
            total += dur
        elif m.get("created_at") and m.get("ended_at"):
            s = _parse_iso(m["created_at"])
            e = _parse_iso(m["ended_at"])
            if s and e:
                diff = (e - s).total_seconds() / 60
                if 0 < diff < 1440:
                    total += diff
    return round(total / 60, 1)


async def build_stats(user: Dict[str, Any]) -> Dict[str, Any]:
    uid = user["user_id"]
    now_iso = datetime.now(timezone.utc).isoformat()
    my_ids = await _my_meeting_ids(uid)

    total_meetings = await db.meetings.count_documents({"meeting_id": {"$in": my_ids}})
    active_meetings = await db.meetings.count_documents({"meeting_id": {"$in": my_ids}, "status": "active"})
    upcoming_meetings = await db.meetings.count_documents({
        "meeting_id": {"$in": my_ids},
        "status": "scheduled",
        "scheduled_at": {"$gte": now_iso},
    })
    ended_meetings = await db.meetings.count_documents({"meeting_id": {"$in": my_ids}, "status": "ended"})
    total_recordings = await db.recordings.count_documents({"meeting_id": {"$in": my_ids}})
    conversations_count = await db.conversations.count_documents({"members.user_id": uid})
    total_hours = await _compute_total_hours(my_ids)

    next_meetings = await db.meetings.find(
        {
            "meeting_id": {"$in": my_ids},
            "$or": [
                {"status": "active"},
                {"status": "scheduled", "scheduled_at": {"$gte": now_iso}},
            ],
        },
        {"_id": 0, "meeting_id": 1, "title": 1, "scheduled_at": 1, "status": 1,
         "meeting_code": 1, "host_name": 1, "participant_count": 1},
    ).sort("scheduled_at", 1).limit(5).to_list(5)

    # Last 7 days sparkline
    daily_counts = []
    for i in range(6, -1, -1):
        day = datetime.now(timezone.utc) - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        count = await db.meetings.count_documents({
            "meeting_id": {"$in": my_ids},
            "created_at": {"$gte": day_start, "$lte": day_end},
        })
        daily_counts.append({"date": day.strftime("%a"), "count": count})

    return {
        "total_meetings": total_meetings,
        "active_meetings": active_meetings,
        "upcoming_meetings": upcoming_meetings,
        "ended_meetings": ended_meetings,
        "total_recordings": total_recordings,
        "conversations_count": conversations_count,
        "total_hours": total_hours,
        "next_meetings": next_meetings,
        "daily_counts": daily_counts,
    }


_AGENDA_FIELDS = {
    "_id": 0, "meeting_id": 1, "title": 1, "scheduled_at": 1, "status": 1,
    "meeting_code": 1, "host_name": 1, "participant_count": 1, "duration": 1,
    "meeting_type": 1, "meeting_mode": 1,
}


async def build_agenda(user: Dict[str, Any]) -> Dict[str, Any]:
    uid = user["user_id"]
    my_ids = await _my_meeting_ids(uid)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_end = (now + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

    today_meetings = await db.meetings.find({
        "meeting_id": {"$in": my_ids},
        "$or": [
            {"status": "active"},
            {"scheduled_at": {"$gte": today_start, "$lte": today_end}},
        ],
    }, _AGENDA_FIELDS).sort("scheduled_at", 1).to_list(50)

    week_meetings = await db.meetings.find({
        "meeting_id": {"$in": my_ids},
        "scheduled_at": {"$gte": tomorrow_start, "$lte": week_end},
        "status": {"$in": ["scheduled", "active"]},
    }, _AGENDA_FIELDS).sort("scheduled_at", 1).to_list(100)

    week_grouped: Dict[str, Dict[str, Any]] = {}
    for m in week_meetings:
        dt = _parse_iso(m.get("scheduled_at") or "")
        if not dt:
            continue
        key = dt.strftime("%Y-%m-%d")
        label = dt.strftime("%a %d.%m.")
        week_grouped.setdefault(key, {"date": key, "label": label, "meetings": []})["meetings"].append(m)
    week_days = sorted(week_grouped.values(), key=lambda x: x["date"])

    recent = await _build_recent_activity(uid, my_ids)

    return {
        "today": today_meetings,
        "week_days": week_days,
        "recent": recent[:8],
        "meetings_today": len(today_meetings),
        "meetings_week": len(week_meetings) + len(today_meetings),
    }


async def _build_recent_activity(uid: str, my_ids: List[str]) -> List[Dict[str, Any]]:
    recent: List[Dict[str, Any]] = []

    ended = await db.meetings.find(
        {"meeting_id": {"$in": my_ids}, "status": "ended"},
        {"_id": 0, "meeting_id": 1, "title": 1, "ended_at": 1},
    ).sort("ended_at", -1).limit(5).to_list(5)
    for m in ended:
        if m.get("ended_at"):
            recent.append({"type": "meeting_ended", "title": m["title"],
                           "time": m["ended_at"], "id": m["meeting_id"]})

    recs = await db.recordings.find(
        {"meeting_id": {"$in": my_ids}},
        {"_id": 0, "title": 1, "created_at": 1, "recording_id": 1},
    ).sort("created_at", -1).limit(3).to_list(3)
    for r in recs:
        recent.append({"type": "recording", "title": r.get("title", "Aufnahme"),
                       "time": r.get("created_at", ""), "id": r.get("recording_id", "")})

    convs = await db.conversations.find(
        {"members.user_id": uid, "last_message": {"$ne": None}},
        {"_id": 0, "conversation_id": 1, "display_name": 1, "name": 1,
         "last_message": 1, "updated_at": 1},
    ).sort("updated_at", -1).limit(3).to_list(3)
    for c in convs:
        lm = c.get("last_message", {}) or {}
        recent.append({
            "type": "chat",
            "title": c.get("display_name") or c.get("name", "Chat"),
            "time": c.get("updated_at", ""),
            "id": c["conversation_id"],
            "detail": f"{lm.get('sender_name', '')}: {lm.get('content', '')[:50]}",
        })

    recent.sort(key=lambda x: x.get("time", ""), reverse=True)
    return recent


# ---------- Calendar events (for CalendarPage) ----------

async def build_calendar_events(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return meetings + booking-meetings where `user` participates, enriched
    with the user's role, rsvp status, and booking metadata.

    iter 189 — also surfaces CONFIRMED schedule-polls (Doodle-style) where
    the user is creator or voter but no meeting was auto-created (user
    chose `create_meeting_on_confirm = false`). Without this the booked
    appointment was invisible in the calendar.
    """
    uid = user["user_id"]
    participant_meetings = await db.meeting_participants.find(
        {"user_id": uid}, {"_id": 0, "meeting_id": 1}
    ).to_list(1000)
    meeting_ids = [p["meeting_id"] for p in participant_meetings]
    meetings = await db.meetings.find({"meeting_id": {"$in": meeting_ids}}, {"_id": 0}).to_list(500)

    bookings = await db.bookings.find(
        {"host_id": uid, "status": {"$ne": "cancelled"}}, {"_id": 0}
    ).to_list(500)
    booking_map = {b.get("meeting_id"): b for b in bookings}

    # Iter 335 — Perf: previously did N+1 (one find_one per meeting). Now
    # batch-fetch this user's participant rows for ALL meeting_ids in one
    # query so we don't pay a round-trip per event. This was the dominant
    # cost of /calendar/events (p95 20s) under load.
    parts_for_me = await db.meeting_participants.find(
        {"meeting_id": {"$in": meeting_ids}, "user_id": uid},
        {"_id": 0, "meeting_id": 1, "role": 1, "rsvp_status": 1},
    ).to_list(len(meeting_ids) or 1)
    parts_by_meeting = {p["meeting_id"]: p for p in parts_for_me}

    events: List[Dict[str, Any]] = []
    seen_ids: set = set()
    seen_polls: set = set()
    for m in meetings:
        mid = m["meeting_id"]
        seen_ids.add(mid)
        if m.get("from_schedule_poll"):
            seen_polls.add(m["from_schedule_poll"])
        my_part = parts_by_meeting.get(mid)
        bk = booking_map.get(mid)
        events.append({
            "meeting_id": mid, "title": m["title"],
            "scheduled_at": m.get("scheduled_at") or m.get("created_at"),
            "duration": m.get("duration", 60), "status": m.get("status"),
            "meeting_mode": m.get("meeting_mode", "standard"),
            "host_name": m.get("host_name", ""),
            "my_role": my_part.get("role", "participant") if my_part else "participant",
            "rsvp_status": my_part.get("rsvp_status", "pending") if my_part else "pending",
            "recurring": m.get("recurring", False),
            "from_booking": m.get("from_booking", bk.get("booking_id") if bk else ""),
            "guest_name": bk.get("guest_name", "") if bk else "",
            "meeting_type": "booking" if bk else m.get("meeting_type", "instant"),
        })

    # Add bookings whose meetings weren't found via participants
    for b in bookings:
        mid = b.get("meeting_id")
        if mid and mid not in seen_ids:
            m = await db.meetings.find_one({"meeting_id": mid}, {"_id": 0})
            if m:
                events.append({
                    "meeting_id": m["meeting_id"], "title": m["title"],
                    "scheduled_at": m.get("scheduled_at") or f"{b['date']}T{b['start_time']}",
                    "duration": b.get("duration", 30), "status": m.get("status", "scheduled"),
                    "meeting_mode": "standard", "host_name": user.get("name", ""),
                    "my_role": "host", "rsvp_status": "accepted",
                    "recurring": False,
                    "from_booking": b.get("booking_id", ""),
                    "guest_name": b.get("guest_name", ""),
                    "meeting_type": "booking",
                })

    # iter 189 — confirmed schedule-polls without a corresponding meeting
    poll_filter = {
        "status": "confirmed",
        "$or": [
            {"created_by": uid},
            {"time_slots.votes.user_id": uid},
        ],
    }
    confirmed_polls = await db.schedule_polls.find(
        poll_filter,
        {"_id": 0, "poll_id": 1, "title": 1, "confirmed_slot_id": 1,
         "time_slots": 1, "created_by": 1, "duration_min": 1},
    ).to_list(500)
    for poll in confirmed_polls:
        pid = poll.get("poll_id")
        if pid in seen_polls:
            continue  # already represented via the auto-created meeting
        slot = next((s for s in poll.get("time_slots", []) if s.get("slot_id") == poll.get("confirmed_slot_id")), None)
        if not slot:
            continue
        scheduled_at = f"{slot.get('date')}T{slot.get('start_time')}"
        try:
            sh, sm = map(int, slot.get("start_time", "0:0").split(":"))
            eh, em = map(int, slot.get("end_time", "0:0").split(":"))
            duration = max(15, (eh * 60 + em) - (sh * 60 + sm))
        except Exception:
            duration = poll.get("duration_min") or 60
        is_host = poll.get("created_by") == uid
        events.append({
            "meeting_id": f"poll_{pid}",  # synthetic id (no /room link)
            "title": poll.get("title", "Terminplanung"),
            "scheduled_at": scheduled_at,
            "duration": duration, "status": "scheduled",
            "meeting_mode": "standard", "host_name": "",
            "my_role": "host" if is_host else "participant",
            "rsvp_status": "accepted",
            "recurring": False,
            "from_schedule_poll": pid,
            "meeting_type": "schedule_poll",
            "no_room": True,  # FE hint: no /room/<id> button
        })

    # iter 192 — also include tasks with a due_date as calendar entries.
    try:
        from services.tasks_service import tasks_for_calendar
        for t in await tasks_for_calendar(user):
            due = t.get("due_date")
            if not due:
                continue
            # Normalise — accept both "2026-01-15" and full ISO with time
            scheduled_at = due if "T" in str(due) else f"{due}T09:00:00"
            is_owner = t.get("creator_id") == uid
            events.append({
                "meeting_id": f"task_{t['task_id']}",  # synthetic ID, no /room link
                "title": f"📋 {t.get('title','Aufgabe')}",
                "scheduled_at": scheduled_at,
                "duration": 30,
                "status": t.get("status", "open"),
                "meeting_mode": "standard",
                "host_name": "",
                "my_role": "host" if is_owner else "participant",
                "rsvp_status": "accepted",
                "recurring": False,
                "from_task": t["task_id"],
                "task_priority": t.get("priority"),
                "task_status": t.get("status"),
                "meeting_type": "task",
                "no_room": True,
            })
    except Exception:
        pass

    return events
