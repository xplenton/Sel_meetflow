"""
Recurring meeting generation logic — extracted from routes/meetings.py so it can
be reused (e.g., by a future scheduled-task/cron) and unit-tested independently.

Two patterns are supported here:
  * simple periodic (daily / weekly / biweekly / monthly)
  * custom per-weekday schedule with individual start/end times
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from database import db

logger = logging.getLogger(__name__)


def validate_schedule_slot(slot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a normalized slot {weekday, start_time, end_time, duration_minutes}
    or None if the input is invalid.

    weekday: 0 (Monday) .. 6 (Sunday) OR string like "mon", "tue", etc.
    start_time / end_time: HH:MM strings (or 'time' for single time with default 60min duration)
    """
    WEEKDAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    try:
        # Handle weekday as string or int
        wd_raw = slot.get("weekday")
        if isinstance(wd_raw, str):
            wd = WEEKDAY_MAP.get(wd_raw.lower()[:3])
            if wd is None:
                return None
        else:
            wd = int(wd_raw)
        
        if not (0 <= wd <= 6):
            return None
        
        # Handle 'time' field (single time with default duration) or start_time/end_time
        if slot.get("time") and not slot.get("start_time"):
            st = str(slot.get("time", "")).strip()
            # Default duration of 60 minutes
            sh, sm = map(int, st.split(":"))
            end_mins = sh * 60 + sm + 60
            eh, em = divmod(end_mins, 60)
            if eh >= 24:
                eh = 23
                em = 59
            et = f"{eh:02d}:{em:02d}"
        else:
            st = str(slot.get("start_time", "")).strip()
            et = str(slot.get("end_time", "")).strip()
        
        if not st or not et:
            return None
            
        sh, sm = st.split(":")
        eh, em = et.split(":")
        sh_i, sm_i, eh_i, em_i = int(sh), int(sm), int(eh), int(em)
        if not (0 <= sh_i <= 23 and 0 <= eh_i <= 23 and 0 <= sm_i <= 59 and 0 <= em_i <= 59):
            return None
        start_total = sh_i * 60 + sm_i
        end_total = eh_i * 60 + em_i
        if end_total <= start_total:
            return None
        return {
            "weekday": wd,
            "start_time": f"{sh_i:02d}:{sm_i:02d}",
            "end_time": f"{eh_i:02d}:{em_i:02d}",
            "duration_minutes": end_total - start_total,
        }
    except Exception:
        return None


def _clone_meeting_document(template: Dict[str, Any], *, scheduled_at_iso: str,
                            duration_minutes: int, series_id: str,
                            recurring_pattern: str, host: Dict[str, Any]) -> Dict[str, Any]:
    new_id = f"meet_{uuid.uuid4().hex[:10]}"
    new_code = f"{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:3]}"
    return {
        "meeting_id": new_id, "meeting_code": new_code,
        "title": template["title"], "description": template.get("description", ""),
        "meeting_type": "scheduled", "scheduled_at": scheduled_at_iso,
        "duration": duration_minutes, "timezone": template.get("timezone", "UTC"),
        "recurring": True, "recurring_pattern": recurring_pattern, "series_id": series_id,
        "lobby_enabled": template.get("lobby_enabled", False),
        "guest_access": template.get("guest_access", True),
        "meeting_mode": template.get("meeting_mode", "standard"),
        "chat_enabled": template.get("chat_enabled", True),
        "reactions_enabled": template.get("reactions_enabled", True),
        "recording_enabled": template.get("recording_enabled", False),
        "transcript_enabled": template.get("transcript_enabled", False),
        "host_id": host["user_id"], "host_name": host["name"],
        "status": "scheduled", "created_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None, "participant_count": 0,
    }


async def _ensure_series_id(template_id: str, template: Dict[str, Any]) -> str:
    series_id = template.get("series_id") or f"series_{uuid.uuid4().hex[:8]}"
    if not template.get("series_id"):
        await db.meetings.update_one({"meeting_id": template_id}, {"$set": {"series_id": series_id}})
    return series_id


async def _copy_participants(source_meeting_id: str, target_meeting_id: str, host: Dict[str, Any]):
    """Insert host + copy invited/optional participants from the source template."""
    await db.meeting_participants.insert_one({
        "meeting_id": target_meeting_id, "user_id": host["user_id"],
        "name": host["name"], "email": host["email"],
        "avatar": host.get("avatar", ""), "role": "host",
        "joined_at": None, "left_at": None, "mic_on": True,
        "camera_on": True, "hand_raised": False, "is_presenting": False,
    })
    existing = await db.meeting_participants.find(
        {"meeting_id": source_meeting_id, "user_id": {"$ne": host["user_id"]}}, {"_id": 0}
    ).to_list(500)
    for p in existing:
        doc = {k: v for k, v in p.items() if k != "_id"}
        doc.update({"meeting_id": target_meeting_id, "joined_at": None, "left_at": None})
        await db.meeting_participants.insert_one(doc)


async def generate_custom_schedule(*, meeting_id: str, template: Dict[str, Any],
                                   schedule: List[Dict[str, Any]], weeks: int,
                                   user: Dict[str, Any]) -> List[str]:
    """Generate recurring occurrences from a weekly schedule with per-weekday times.

    The first matching slot that is strictly after the template's scheduled_at is
    the first generated occurrence. Slots that would fall on/before the template
    time are skipped to avoid duplicating the template meeting itself.
    """
    if not template or not schedule:
        return []
    weeks = max(1, min(int(weeks or 8), 52))
    slots = [s for s in (validate_schedule_slot(x) for x in schedule) if s]
    if not slots:
        return []

    base_dt: Optional[datetime] = None
    if template.get("scheduled_at"):
        try:
            base_dt = datetime.fromisoformat(template["scheduled_at"])
        except Exception:
            base_dt = None
    if not base_dt:
        base_dt = datetime.now(timezone.utc)

    start_monday = (base_dt - timedelta(days=base_dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    series_id = await _ensure_series_id(meeting_id, template)

    # iter 158 — Promote the template itself to the FIRST slot (instead of
    # keeping the user's "initial" time as a phantom meeting next to the
    # generated occurrences). Users reported the original flow produced an
    # extra meeting that they never scheduled. Now the series has exactly
    # weeks × slots meetings, no more, no less.
    first_occ_dt: Optional[datetime] = None
    for w in range(weeks):
        for slot in slots:
            day = start_monday + timedelta(days=(w * 7) + slot["weekday"])
            sh, sm = map(int, slot["start_time"].split(":"))
            candidate = day.replace(hour=sh, minute=sm)
            if candidate >= base_dt:
                first_occ_dt = candidate
                # Promote template
                await db.meetings.update_one(
                    {"meeting_id": meeting_id},
                    {"$set": {
                        "scheduled_at": candidate.isoformat(),
                        "duration": slot["duration_minutes"],
                    }},
                )
                break
        if first_occ_dt:
            break

    # If no slot matched (all in the past), leave the template as-is and
    # skip generation — the user will see their original meeting only.
    if not first_occ_dt:
        return []

    generated: List[str] = []
    for w in range(weeks):
        for slot in slots:
            day = start_monday + timedelta(days=(w * 7) + slot["weekday"])
            sh, sm = map(int, slot["start_time"].split(":"))
            occ_dt = day.replace(hour=sh, minute=sm)
            # Skip everything at or before the promoted template occurrence
            # (the template IS the first slot now).
            if occ_dt <= first_occ_dt:
                continue
            new_meeting = _clone_meeting_document(
                template,
                scheduled_at_iso=occ_dt.isoformat(),
                duration_minutes=slot["duration_minutes"],
                series_id=series_id,
                recurring_pattern="custom",
                host=user,
            )
            await db.meetings.insert_one(new_meeting)
            await _copy_participants(meeting_id, new_meeting["meeting_id"], user)
            generated.append(new_meeting["meeting_id"])
    return generated


def validate_date_slot(slot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate an explicit-date custom slot. Returns {date, start_time,
    end_time, duration_minutes} or None if invalid.

    date: "YYYY-MM-DD"  |  start_time/end_time: "HH:MM"
    """
    try:
        raw_date = str(slot.get("date", "")).strip()
        if not raw_date:
            return None
        # Parse to validate
        y, m, d = map(int, raw_date.split("-"))
        datetime(y, m, d)  # will raise on invalid
        st = str(slot.get("start_time", "")).strip()
        et = str(slot.get("end_time", "")).strip()
        if not st or not et:
            return None
        sh, sm = map(int, st.split(":"))
        eh, em = map(int, et.split(":"))
        if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59):
            return None
        duration = (eh * 60 + em) - (sh * 60 + sm)
        if duration <= 0:
            return None
        return {
            "date": f"{y:04d}-{m:02d}-{d:02d}",
            "start_time": f"{sh:02d}:{sm:02d}",
            "end_time": f"{eh:02d}:{em:02d}",
            "duration_minutes": duration,
        }
    except Exception:
        return None


async def generate_custom_dates(*, meeting_id: str, template: Dict[str, Any],
                                dates: List[Dict[str, Any]], user: Dict[str, Any]) -> List[str]:
    """Generate occurrences from an explicit list of dates + times.

    Behaviour mirrors `generate_custom_schedule`: the earliest valid slot
    replaces the template, remaining slots become child meetings in the
    same series. Invalid / past slots are skipped silently.
    """
    if not template or not dates:
        return []
    slots = [s for s in (validate_date_slot(x) for x in dates) if s]
    if not slots:
        return []
    # Sort by (date, start_time) to determine the "first" slot
    slots.sort(key=lambda s: (s["date"], s["start_time"]))
    # Dedupe on (date, start_time)
    seen = set()
    unique: List[Dict[str, Any]] = []
    for s in slots:
        key = (s["date"], s["start_time"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    slots = unique[:200]  # Safety cap

    now_utc = datetime.now(timezone.utc)
    first_slot = None
    for s in slots:
        y, m, d = map(int, s["date"].split("-"))
        sh, sm = map(int, s["start_time"].split(":"))
        dt = datetime(y, m, d, sh, sm, tzinfo=timezone.utc)
        if dt >= now_utc:
            first_slot = (s, dt)
            break
    if not first_slot:
        return []

    first_s, first_dt = first_slot
    series_id = await _ensure_series_id(meeting_id, template)
    # Promote template to the first slot
    await db.meetings.update_one(
        {"meeting_id": meeting_id},
        {"$set": {
            "scheduled_at": first_dt.isoformat(),
            "duration": first_s["duration_minutes"],
        }},
    )
    generated: List[str] = []
    for s in slots:
        y, m, d = map(int, s["date"].split("-"))
        sh, sm = map(int, s["start_time"].split(":"))
        dt = datetime(y, m, d, sh, sm, tzinfo=timezone.utc)
        if dt <= first_dt:
            continue
        new_meeting = _clone_meeting_document(
            template,
            scheduled_at_iso=dt.isoformat(),
            duration_minutes=s["duration_minutes"],
            series_id=series_id,
            recurring_pattern="custom_dates",
            host=user,
        )
        await db.meetings.insert_one(new_meeting)
        await _copy_participants(meeting_id, new_meeting["meeting_id"], user)
        generated.append(new_meeting["meeting_id"])
    return generated


async def generate_simple_pattern(*, meeting_id: str, template: Dict[str, Any],
                                  count: int, user: Dict[str, Any]) -> List[str]:
    """Generate N occurrences of a daily/weekly/biweekly/monthly recurring meeting."""
    pattern = template.get("recurring_pattern", "weekly")
    base_dt = datetime.fromisoformat(template["scheduled_at"]) if template.get("scheduled_at") else datetime.now(timezone.utc)
    deltas = {
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "biweekly": timedelta(weeks=2),
        "monthly": timedelta(days=30),
    }
    delta = deltas.get(pattern, timedelta(weeks=1))
    series_id = await _ensure_series_id(meeting_id, template)
    generated: List[str] = []
    for i in range(1, int(count or 1) + 1):
        new_dt = base_dt + delta * i
        new_meeting = _clone_meeting_document(
            template,
            scheduled_at_iso=new_dt.isoformat(),
            duration_minutes=template.get("duration", 60),
            series_id=series_id,
            recurring_pattern=pattern,
            host=user,
        )
        await db.meetings.insert_one(new_meeting)
        await db.meeting_participants.insert_one({
            "meeting_id": new_meeting["meeting_id"], "user_id": user["user_id"],
            "name": user["name"], "email": user["email"],
            "avatar": user.get("avatar", ""), "role": "host",
            "joined_at": None, "left_at": None, "mic_on": True,
            "camera_on": True, "hand_raised": False, "is_presenting": False,
        })
        generated.append(new_meeting["meeting_id"])
    return generated
