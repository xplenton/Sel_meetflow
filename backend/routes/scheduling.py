from fastapi import APIRouter, HTTPException, Request, Response
import os
import uuid
import csv
import io
import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import db, logger
from dependencies import get_current_user
from services.email import send_email_real
from services.permissions import has_cap
from models import (
    SchedulePollCreateRequest, SchedulePollVoteRequest, SchedulePollCommentRequest,
    BookingAvailabilityRequest, GeneralPollCreateRequest, GeneralPollVoteRequest
)

async def _get_llm_key():
    """Get LLM key from DB config or env."""
    config = await db.api_config.find_one({"config_id": "global"}, {"_id": 0})
    if config and config.get("llm_enabled") and config.get("llm_key"):
        return config["llm_key"]
    return os.environ.get("EMERGENT_LLM_KEY", "")


async def _find_user_by_identifier(identifier: str):
    """Find user by user_id, exact name, or slugified name (spaces→hyphens)."""
    if identifier.startswith("user_"):
        return await db.users.find_one({"user_id": identifier}, {"_id": 0})
    # Try exact name match first
    user = await db.users.find_one({"name": {"$regex": f"^{identifier}$", "$options": "i"}}, {"_id": 0})
    if user:
        return user
    # Try slug match: replace hyphens with flexible whitespace pattern
    slug_pattern = identifier.replace("-", "\\s+")
    user = await db.users.find_one({"name": {"$regex": f"^{slug_pattern}$", "$options": "i"}}, {"_id": 0})
    return user


router = APIRouter()


@router.post("/schedule-polls")
async def create_schedule_poll(req: SchedulePollCreateRequest, request: Request):
    user = await get_current_user(request)
    poll_id = f"spoll_{uuid.uuid4().hex[:10]}"
    share_token = uuid.uuid4().hex[:12]
    slots = []
    for ts in req.time_slots:
        slot_id = f"slot_{uuid.uuid4().hex[:6]}"
        slots.append({"slot_id": slot_id, "date": ts.date, "start_time": ts.start_time, "end_time": ts.end_time})
    poll = {
        "poll_id": poll_id, "share_token": share_token,
        "title": req.title, "description": req.description,
        "time_slots": slots, "deadline": req.deadline,
        "allow_maybe": req.allow_maybe, "allow_suggestions": req.allow_suggestions,
        "is_private": req.is_private, "password_hash": bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode() if req.password else None,
        "create_meeting_on_confirm": req.create_meeting_on_confirm,
        "created_by": user["user_id"], "creator_name": user.get("name", ""),
        "status": "open", "confirmed_slot_id": None,
        "votes": [], "comments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.schedule_polls.insert_one(poll)
    return {"poll_id": poll_id, "share_token": share_token}

@router.get("/schedule-polls")
async def list_schedule_polls(request: Request, page: int = 1, limit: int = 20, search: Optional[str] = None):
    user = await get_current_user(request)
    query = {"created_by": user["user_id"]}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    total = await db.schedule_polls.count_documents(query)
    skip = (max(1, page) - 1) * limit
    polls = await db.schedule_polls.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"polls": polls, "total": total, "page": page, "pages": max(1, -(-total // limit))}

@router.get("/schedule-polls/{poll_id}")
async def get_schedule_poll(poll_id: str, request: Request):
    await get_current_user(request)
    poll = await db.schedule_polls.find_one({"poll_id": poll_id}, {"_id": 0, "password_hash": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    return poll

@router.get("/schedule-polls/public/{share_token}")
async def get_schedule_poll_public(share_token: str, pwd: Optional[str] = None):
    poll = await db.schedule_polls.find_one({"share_token": share_token}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll.get("password_hash"):
        if not pwd or not bcrypt.checkpw(pwd.encode(), poll["password_hash"].encode()):
            # iter 189 — surface "wrong password" vs "no password yet" so the
            # frontend can show a useful error toast instead of just re-rendering
            # the prompt silently.
            return {
                "poll_id": poll["poll_id"], "title": poll["title"],
                "requires_password": True,
                "wrong_password": bool(pwd),
            }
    poll.pop("password_hash", None)
    return poll

@router.post("/schedule-polls/public/{share_token}/vote")
async def vote_schedule_poll(share_token: str, req: SchedulePollVoteRequest):
    poll = await db.schedule_polls.find_one({"share_token": share_token}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll["status"] != "open":
        raise HTTPException(status_code=400, detail="Poll is closed")
    if poll.get("deadline"):
        if datetime.now(timezone.utc).isoformat() > poll["deadline"]:
            raise HTTPException(status_code=400, detail="Deadline has passed")
    vote_id = f"vote_{uuid.uuid4().hex[:6]}"
    vote = {
        "vote_id": vote_id, "voter_name": req.voter_name,
        "voter_email": req.voter_email, "votes": req.votes,
        "voted_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = None
    for i, v in enumerate(poll.get("votes", [])):
        if v["voter_name"].lower() == req.voter_name.lower():
            existing = i
            break
    if existing is not None:
        await db.schedule_polls.update_one(
            {"share_token": share_token},
            {"$set": {f"votes.{existing}": vote}}
        )
    else:
        await db.schedule_polls.update_one(
            {"share_token": share_token},
            {"$push": {"votes": vote}}
        )
    return {"message": "Vote recorded", "vote_id": vote_id}

@router.post("/schedule-polls/public/{share_token}/comment")
async def comment_schedule_poll(share_token: str, req: SchedulePollCommentRequest):
    poll = await db.schedule_polls.find_one({"share_token": share_token})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    comment = {
        "comment_id": f"cmt_{uuid.uuid4().hex[:6]}",
        "author_name": req.author_name, "text": req.text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.schedule_polls.update_one({"share_token": share_token}, {"$push": {"comments": comment}})
    return comment

@router.post("/schedule-polls/{poll_id}/confirm")
async def confirm_schedule_poll(poll_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    slot_id = body.get("slot_id")
    poll = await db.schedule_polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll["created_by"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only creator can confirm")
    slot = next((s for s in poll["time_slots"] if s["slot_id"] == slot_id), None)
    if not slot:
        raise HTTPException(status_code=400, detail="Slot not found")
    await db.schedule_polls.update_one({"poll_id": poll_id}, {"$set": {"status": "confirmed", "confirmed_slot_id": slot_id}})
    result = {"message": "Poll confirmed", "slot": slot}
    if poll.get("create_meeting_on_confirm"):
        scheduled_at = f"{slot['date']}T{slot['start_time']}"
        meeting_id = f"meet_{uuid.uuid4().hex[:10]}"
        meeting_code = uuid.uuid4().hex[:8].upper()
        duration_mins = 60
        try:
            from datetime import datetime as dt
            start = dt.fromisoformat(f"{slot['date']}T{slot['start_time']}")
            end = dt.fromisoformat(f"{slot['date']}T{slot['end_time']}")
            duration_mins = int((end - start).total_seconds() / 60) or 60
        except Exception:
            pass
        meet = {
            "meeting_id": meeting_id, "meeting_code": meeting_code,
            "title": poll["title"], "description": poll.get("description", ""),
            "meeting_type": "scheduled", "status": "scheduled",
            "host_id": user["user_id"], "scheduled_at": scheduled_at,
            "duration": duration_mins, "timezone": "UTC",
            "lobby_enabled": False, "guest_access": True, "meeting_mode": "standard",
            "chat_enabled": True, "reactions_enabled": True,
            "recording_enabled": False, "transcript_enabled": False,
            "recording_active": False, "transcript_active": False,
            "screen_share_enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(), "ended_at": None,
            "participant_count": 0, "from_schedule_poll": poll_id,
        }
        await db.meetings.insert_one(meet)
        await db.meeting_participants.insert_one({
            "meeting_id": meeting_id, "user_id": user["user_id"],
            "name": user.get("name", "Host"), "role": "host",
            "joined_at": datetime.now(timezone.utc).isoformat(),
        })
        # Auto-add all poll voters as meeting participants (Calendar visibility)
        voters = set()
        for s in poll.get("time_slots", []):
            for v in s.get("votes", []):
                uid = v.get("user_id")
                if uid and uid != user["user_id"]:
                    voters.add(uid)
        for uid in voters:
            voter_user = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1})
            if not voter_user:
                continue
            existing_part = await db.meeting_participants.find_one({"meeting_id": meeting_id, "user_id": uid})
            if not existing_part:
                await db.meeting_participants.insert_one({
                    "meeting_id": meeting_id, "user_id": uid,
                    "name": voter_user.get("name", ""), "role": "participant",
                    "joined_at": None, "left_at": None,
                })
        result["meeting_id"] = meeting_id
        result["meeting_code"] = meeting_code
        result["participants_added"] = len(voters)
    return result

@router.delete("/schedule-polls/{poll_id}")
async def delete_schedule_poll(poll_id: str, request: Request):
    user = await get_current_user(request)
    poll = await db.schedule_polls.find_one({"poll_id": poll_id})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll["created_by"] != user["user_id"] and not await has_cap(user, "scheduling.delete_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.schedule_polls.delete_one({"poll_id": poll_id})
    return {"message": "Poll deleted"}

@router.post("/schedule-polls/public/{share_token}/suggest")
async def suggest_time_slot(share_token: str, request: Request):
    body = await request.json()
    poll = await db.schedule_polls.find_one({"share_token": share_token})
    if not poll or not poll.get("allow_suggestions"):
        raise HTTPException(status_code=400, detail="Suggestions not allowed")
    slot_id = f"slot_{uuid.uuid4().hex[:6]}"
    new_slot = {"slot_id": slot_id, "date": body["date"], "start_time": body["start_time"], "end_time": body["end_time"], "suggested_by": body.get("name", "Anonym")}
    await db.schedule_polls.update_one({"share_token": share_token}, {"$push": {"time_slots": new_slot}})
    return new_slot






@router.get("/booking/availability")
async def get_my_availability(request: Request):
    user = await get_current_user(request)
    avail = await db.booking_availability.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not avail:
        avail = {
            "user_id": user["user_id"],
            "weekdays": {
                "mon": {"enabled": True, "start": "09:00", "end": "17:00"},
                "tue": {"enabled": True, "start": "09:00", "end": "17:00"},
                "wed": {"enabled": True, "start": "09:00", "end": "17:00"},
                "thu": {"enabled": True, "start": "09:00", "end": "17:00"},
                "fri": {"enabled": True, "start": "09:00", "end": "17:00"},
                "sat": {"enabled": False, "start": "09:00", "end": "17:00"},
                "sun": {"enabled": False, "start": "09:00", "end": "17:00"},
            },
            "slot_duration": 30, "buffer_time": 10,
            "blocked_dates": [], "booking_enabled": True,
        }
    return avail

@router.put("/booking/availability")
async def update_availability(req: BookingAvailabilityRequest, request: Request):
    user = await get_current_user(request)
    data = {
        "user_id": user["user_id"],
        "weekdays": req.weekdays, "slot_duration": req.slot_duration,
        "buffer_time": req.buffer_time, "blocked_dates": req.blocked_dates,
        "booking_enabled": req.booking_enabled,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.booking_availability.update_one({"user_id": user["user_id"]}, {"$set": data}, upsert=True)
    return {"message": "Availability updated"}

@router.get("/book/{username}/slots")
async def get_public_booking_slots(username: str, date: str):
    """Get available slots for a given date (public, no auth)."""
    user = await _find_user_by_identifier(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    avail = await db.booking_availability.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not avail or not avail.get("booking_enabled"):
        raise HTTPException(status_code=404, detail="Booking not available")
    from datetime import datetime as dt
    try:
        target = dt.fromisoformat(date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")
    day_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
    day_key = day_map.get(target.weekday())
    day_config = avail.get("weekdays", {}).get(day_key, {})
    if not day_config.get("enabled"):
        return {"slots": [], "user_name": user.get("name"), "date": date}
    if date in avail.get("blocked_dates", []):
        return {"slots": [], "user_name": user.get("name"), "date": date}
    duration = avail.get("slot_duration", 30)
    buffer = avail.get("buffer_time", 10)
    start_h, start_m = map(int, day_config["start"].split(":"))
    end_h, end_m = map(int, day_config["end"].split(":"))
    start_mins = start_h * 60 + start_m
    end_mins = end_h * 60 + end_m
    existing = await db.bookings.find({"host_id": user["user_id"], "date": date, "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(100)
    booked_times = set()
    for b in existing:
        booked_times.add(b["start_time"])
    # Load busy slots (manual blocks + CalDAV-imported) for this day
    day_start_iso = target.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    day_end_iso = target.replace(hour=23, minute=59, second=59).isoformat()
    from services.busy_slots import list_busy_slots
    busy_slots_today = await list_busy_slots(user["user_id"], day_start_iso, day_end_iso)
    def _slot_is_busy(slot_start_mins: int, slot_end_mins: int) -> bool:
        for bs in busy_slots_today:
            try:
                bs_start = datetime.fromisoformat(bs["start"].replace("Z", "+00:00"))
                bs_end = datetime.fromisoformat(bs["end"].replace("Z", "+00:00"))
                # Treat day-local minutes
                if bs_start.date() != target.date() and bs_end.date() != target.date():
                    continue
                bs_start_mins = bs_start.hour * 60 + bs_start.minute if bs_start.date() == target.date() else 0
                bs_end_mins = bs_end.hour * 60 + bs_end.minute if bs_end.date() == target.date() else 24 * 60
                if slot_start_mins < bs_end_mins and slot_end_mins > bs_start_mins:
                    return True
            except Exception:
                continue
        return False
    slots = []
    current = start_mins
    while current + duration <= end_mins:
        h, m = divmod(current, 60)
        time_str = f"{h:02d}:{m:02d}"
        eh, em = divmod(current + duration, 60)
        end_str = f"{eh:02d}:{em:02d}"
        if time_str not in booked_times and not _slot_is_busy(current, current + duration):
            slots.append({"start_time": time_str, "end_time": end_str})
        current += duration + buffer
    return {"slots": slots, "user_name": user.get("name"), "date": date, "slot_duration": duration}

@router.get("/book/{username}/info")
async def get_booking_page_info(username: str):
    """Get public booking page info (no auth)."""
    user = await _find_user_by_identifier(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    avail = await db.booking_availability.find_one({"user_id": user["user_id"]}, {"_id": 0})
    enabled = avail.get("booking_enabled", False) if avail else False
    avatar = user.get("avatar", "")
    return {
        "user_name": user.get("name", username),
        "user_id": user["user_id"],
        "avatar": avatar,
        "slot_duration": avail.get("slot_duration", 30) if avail else 30,
        "booking_enabled": enabled,
    }

@router.post("/book/{username}")
async def create_booking(username: str, request: Request):
    """Book a slot (public, no auth)."""
    body = await request.json()
    user = await _find_user_by_identifier(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    avail = await db.booking_availability.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not avail or not avail.get("booking_enabled"):
        raise HTTPException(status_code=400, detail="Booking not available")
    date = body.get("date")
    start_time = body.get("start_time")
    guest_name = body.get("guest_name", "")
    guest_email = body.get("guest_email", "")
    topic = body.get("topic", "")
    if not date or not start_time or not guest_name:
        raise HTTPException(status_code=400, detail="date, start_time, guest_name required")
    existing = await db.bookings.find_one({"host_id": user["user_id"], "date": date, "start_time": start_time, "status": {"$ne": "cancelled"}})
    if existing:
        raise HTTPException(status_code=409, detail="This slot is already booked")
    duration = avail.get("slot_duration", 30)
    sh, sm = map(int, start_time.split(":"))
    end_mins = sh * 60 + sm + duration
    eh, em = divmod(end_mins, 60)
    end_time = f"{eh:02d}:{em:02d}"
    booking_id = f"bk_{uuid.uuid4().hex[:10]}"
    meeting_id = f"meet_{uuid.uuid4().hex[:10]}"
    meeting_code = uuid.uuid4().hex[:8].upper()
    booking = {
        "booking_id": booking_id, "host_id": user["user_id"], "host_name": user.get("name", ""),
        "guest_name": guest_name, "guest_email": guest_email, "topic": topic,
        "date": date, "start_time": start_time, "end_time": end_time,
        "duration": duration, "status": "confirmed", "meeting_id": meeting_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bookings.insert_one(booking)
    meet = {
        "meeting_id": meeting_id, "meeting_code": meeting_code,
        "title": topic or f"Meeting mit {guest_name}",
        "description": f"1:1 Buchung von {guest_name}" + (f" ({guest_email})" if guest_email else ""),
        "meeting_type": "scheduled", "status": "scheduled",
        "host_id": user["user_id"], "scheduled_at": f"{date}T{start_time}",
        "duration": duration, "timezone": "UTC",
        "lobby_enabled": False, "guest_access": True, "meeting_mode": "standard",
        "chat_enabled": True, "reactions_enabled": True,
        "recording_enabled": False, "transcript_enabled": False,
        "recording_active": False, "transcript_active": False,
        "screen_share_enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(), "ended_at": None,
        "participant_count": 0, "from_booking": booking_id,
    }
    await db.meetings.insert_one(meet)
    await db.meeting_participants.insert_one({
        "meeting_id": meeting_id, "user_id": user["user_id"],
        "name": user.get("name", "Host"), "role": "host",
        "joined_at": datetime.now(timezone.utc).isoformat(),
    })
    if guest_email:
        join_link = f"{os.environ.get('CORS_ORIGINS', '').split(',')[0].strip()}/meetings/{meeting_id}/join"
        await send_email_real(guest_email, f"Terminbestaetigung: {topic or 'Meeting'}", f"<div style='font-family:Arial,sans-serif;padding:24px;'><h2 style='color:#4A5D4E;'>Termin bestätigt</h2><p>Dein Termin mit <b>{user.get('name','')}</b> am <b>{date}</b> um <b>{start_time}</b> wurde bestätigt.</p><p>Meeting-Code: <b>{meeting_code}</b></p><p><a href='{join_link}'>Zum Meeting beitreten</a></p></div>")
    return {"booking_id": booking_id, "meeting_id": meeting_id, "meeting_code": meeting_code, "date": date, "start_time": start_time, "end_time": end_time}

@router.get("/booking/my-bookings")
async def get_my_bookings(request: Request, page: int = 1, limit: int = 20):
    user = await get_current_user(request)
    query = {"host_id": user["user_id"]}
    total = await db.bookings.count_documents(query)
    skip = (max(1, page) - 1) * limit
    bookings = await db.bookings.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"bookings": bookings, "total": total, "page": page, "pages": max(1, -(-total // limit))}

@router.delete("/booking/{booking_id}")
async def cancel_booking(booking_id: str, request: Request):
    user = await get_current_user(request)
    booking = await db.bookings.find_one({"booking_id": booking_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["host_id"] != user["user_id"] and not await has_cap(user, "scheduling.delete_others", db):
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": "cancelled"}})
    return {"message": "Booking cancelled"}


# ============ BOOKING PAGES (Multi-Page) ============

@router.get("/booking/pages")
async def list_booking_pages(request: Request):
    user = await get_current_user(request)
    pages = await db.booking_pages.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", 1).to_list(10)
    return pages

@router.post("/booking/pages")
async def create_booking_page(request: Request):
    user = await get_current_user(request)
    count = await db.booking_pages.count_documents({"user_id": user["user_id"]})
    if count >= 5:
        raise HTTPException(status_code=400, detail="Maximal 5 Buchungsseiten erlaubt")
    body = await request.json()
    slug = body.get("slug", "").strip().lower().replace(" ", "-")
    if not slug or len(slug) < 2:
        raise HTTPException(status_code=400, detail="Slug muss mindestens 2 Zeichen haben")
    import re
    if not re.match(r'^[a-z0-9\-]+$', slug):
        raise HTTPException(status_code=400, detail="Slug darf nur Kleinbuchstaben, Zahlen und Bindestriche enthalten")
    existing = await db.booking_pages.find_one({"user_id": user["user_id"], "slug": slug})
    if existing:
        raise HTTPException(status_code=409, detail="Slug existiert bereits")
    page_id = f"bp_{uuid.uuid4().hex[:10]}"
    page = {
        "page_id": page_id, "user_id": user["user_id"], "slug": slug,
        "title": body.get("title", slug.replace("-", " ").title()),
        "description": body.get("description", ""),
        "weekdays": body.get("weekdays", {
            "mon": {"enabled": True, "start": "09:00", "end": "17:00"},
            "tue": {"enabled": True, "start": "09:00", "end": "17:00"},
            "wed": {"enabled": True, "start": "09:00", "end": "17:00"},
            "thu": {"enabled": True, "start": "09:00", "end": "17:00"},
            "fri": {"enabled": True, "start": "09:00", "end": "17:00"},
            "sat": {"enabled": False, "start": "09:00", "end": "17:00"},
            "sun": {"enabled": False, "start": "09:00", "end": "17:00"},
        }),
        "slot_duration": body.get("slot_duration", 30),
        "buffer_time": body.get("buffer_time", 10),
        "blocked_dates": body.get("blocked_dates", []),
        # iter 189 — booking horizon limits
        "booking_until": body.get("booking_until") or None,        # ISO date "YYYY-MM-DD" — hard cutoff date
        "max_advance_days": body.get("max_advance_days") or None,  # rolling: only N days into the future
        "enabled": body.get("enabled", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.booking_pages.insert_one(page)
    return {k: v for k, v in page.items() if k != "_id"}

@router.put("/booking/pages/{page_id}")
async def update_booking_page(page_id: str, request: Request):
    user = await get_current_user(request)
    page = await db.booking_pages.find_one({"page_id": page_id, "user_id": user["user_id"]})
    if not page:
        raise HTTPException(status_code=404, detail="Buchungsseite nicht gefunden")
    body = await request.json()
    update = {}
    for field in ["title", "description", "weekdays", "slot_duration", "buffer_time", "blocked_dates", "enabled", "booking_until", "max_advance_days"]:
        if field in body:
            update[field] = body[field]
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.booking_pages.update_one({"page_id": page_id}, {"$set": update})
    return {"message": "Buchungsseite aktualisiert"}

@router.delete("/booking/pages/{page_id}")
async def delete_booking_page(page_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.booking_pages.delete_one({"page_id": page_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Buchungsseite nicht gefunden")
    return {"message": "Buchungsseite gelöscht"}

@router.get("/booking/pages/{page_id}/bookings")
async def get_page_bookings(page_id: str, request: Request):
    user = await get_current_user(request)
    page = await db.booking_pages.find_one({"page_id": page_id, "user_id": user["user_id"]}, {"_id": 0})
    if not page:
        raise HTTPException(status_code=404, detail="Buchungsseite nicht gefunden")
    bookings = await db.bookings.find(
        {"host_id": user["user_id"], "$or": [{"page_id": page_id}, {"page_slug": page.get("slug")}]},
        {"_id": 0}
    ).sort("date", -1).to_list(200)
    return {"bookings": bookings, "page": page}

@router.get("/booking/all-bookings")
async def get_all_bookings(request: Request):
    user = await get_current_user(request)
    bookings = await db.bookings.find(
        {"host_id": user["user_id"]},
        {"_id": 0}
    ).sort("date", -1).to_list(500)
    return {"bookings": bookings}



@router.get("/book/{username}/{slug}/info")
async def get_booking_page_slug_info(username: str, slug: str):
    user = await _find_user_by_identifier(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    page = await db.booking_pages.find_one({"user_id": user["user_id"], "slug": slug}, {"_id": 0})
    if not page or not page.get("enabled"):
        raise HTTPException(status_code=404, detail="Buchungsseite nicht gefunden oder deaktiviert")
    return {
        "user_name": user.get("name", username), "avatar": user.get("avatar", ""),
        "title": page.get("title", ""), "description": page.get("description", ""),
        "slot_duration": page.get("slot_duration", 30), "page_id": page.get("page_id"),
        "booking_until": page.get("booking_until"),
        "max_advance_days": page.get("max_advance_days"),
    }

@router.get("/book/{username}/{slug}/slots")
async def get_booking_page_slug_slots(username: str, slug: str, date: str):
    user = await _find_user_by_identifier(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    page = await db.booking_pages.find_one({"user_id": user["user_id"], "slug": slug}, {"_id": 0})
    if not page or not page.get("enabled"):
        raise HTTPException(status_code=404, detail="Buchungsseite nicht gefunden")
    from datetime import datetime as dt
    try:
        target = dt.fromisoformat(date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")
    # iter 189 — booking horizon enforcement
    today = dt.now()
    booking_until = page.get("booking_until")
    if booking_until:
        try:
            cutoff = dt.fromisoformat(booking_until)
            if target.date() > cutoff.date():
                return {"slots": [], "user_name": user.get("name"), "date": date,
                        "blocked_reason": "booking_window_ended"}
        except Exception:
            pass
    max_advance = page.get("max_advance_days")
    if max_advance:
        try:
            from datetime import timedelta as _td
            limit = (today + _td(days=int(max_advance))).date()
            if target.date() > limit:
                return {"slots": [], "user_name": user.get("name"), "date": date,
                        "blocked_reason": "too_far_ahead"}
        except Exception:
            pass
    day_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
    day_key = day_map.get(target.weekday())
    day_config = page.get("weekdays", {}).get(day_key, {})
    if not day_config.get("enabled") or date in page.get("blocked_dates", []):
        return {"slots": [], "user_name": user.get("name"), "date": date}
    duration = page.get("slot_duration", 30)
    buffer = page.get("buffer_time", 10)
    start_h, start_m = map(int, day_config["start"].split(":"))
    end_h, end_m = map(int, day_config["end"].split(":"))
    start_mins = start_h * 60 + start_m
    end_mins = end_h * 60 + end_m
    existing = await db.bookings.find({"host_id": user["user_id"], "date": date, "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(100)
    booked_times = {b["start_time"] for b in existing}
    slots = []
    current = start_mins
    while current + duration <= end_mins:
        h, m = divmod(current, 60)
        time_str = f"{h:02d}:{m:02d}"
        eh, em = divmod(current + duration, 60)
        end_str = f"{eh:02d}:{em:02d}"
        if time_str not in booked_times:
            slots.append({"start_time": time_str, "end_time": end_str})
        current += duration + buffer
    return {"slots": slots, "user_name": user.get("name"), "date": date, "slot_duration": duration}

@router.post("/book/{username}/{slug}")
async def create_booking_slug(username: str, slug: str, request: Request):
    user = await _find_user_by_identifier(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    page = await db.booking_pages.find_one({"user_id": user["user_id"], "slug": slug}, {"_id": 0})
    if not page or not page.get("enabled"):
        raise HTTPException(status_code=400, detail="Buchungsseite nicht verfügbar")
    body = await request.json()
    date = body.get("date")
    start_time = body.get("start_time")
    guest_name = body.get("guest_name", "")
    guest_email = body.get("guest_email", "")
    topic = body.get("topic", page.get("title", ""))
    if not date or not start_time or not guest_name:
        raise HTTPException(status_code=400, detail="date, start_time, guest_name required")
    # iter 189 — server-side horizon enforcement (slot endpoint already filters
    # the calendar grid; this prevents direct-POST or stale-tab abuse).
    from datetime import datetime as _dt, timedelta as _td
    try:
        target_date = _dt.fromisoformat(date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")
    booking_until = page.get("booking_until")
    if booking_until:
        try:
            if target_date > _dt.fromisoformat(booking_until).date():
                raise HTTPException(status_code=400, detail=f"Buchungen sind nur bis {booking_until} möglich")
        except HTTPException:
            raise
        except Exception:
            pass
    max_advance = page.get("max_advance_days")
    if max_advance:
        try:
            limit = (_dt.now() + _td(days=int(max_advance))).date()
            if target_date > limit:
                raise HTTPException(status_code=400, detail=f"Buchungen sind nur bis {int(max_advance)} Tage im Voraus möglich")
        except HTTPException:
            raise
        except Exception:
            pass
    existing = await db.bookings.find_one({"host_id": user["user_id"], "date": date, "start_time": start_time, "status": {"$ne": "cancelled"}})
    if existing:
        raise HTTPException(status_code=409, detail="Slot bereits gebucht")
    duration = page.get("slot_duration", 30)
    sh, sm = map(int, start_time.split(":"))
    end_mins = sh * 60 + sm + duration
    eh, em = divmod(end_mins, 60)
    end_time = f"{eh:02d}:{em:02d}"
    booking_id = f"bk_{uuid.uuid4().hex[:10]}"
    meeting_id = f"meet_{uuid.uuid4().hex[:10]}"
    meeting_code = uuid.uuid4().hex[:8].upper()
    booking = {
        "booking_id": booking_id, "host_id": user["user_id"], "host_name": user.get("name", ""),
        "guest_name": guest_name, "guest_email": guest_email, "topic": topic,
        "date": date, "start_time": start_time, "end_time": end_time,
        "duration": duration, "status": "confirmed", "meeting_id": meeting_id,
        "page_id": page.get("page_id"), "page_slug": slug,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bookings.insert_one(booking)
    meet = {
        "meeting_id": meeting_id, "meeting_code": meeting_code,
        "title": topic or f"Meeting mit {guest_name}",
        "description": f"Buchung ({slug}) von {guest_name}" + (f" ({guest_email})" if guest_email else ""),
        "meeting_type": "scheduled", "status": "scheduled",
        "host_id": user["user_id"], "scheduled_at": f"{date}T{start_time}",
        "duration": duration, "timezone": "UTC",
        "lobby_enabled": False, "guest_access": True, "meeting_mode": "standard",
        "chat_enabled": True, "reactions_enabled": True,
        "recording_enabled": False, "screen_share_enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "participant_count": 0, "from_booking": booking_id,
    }
    await db.meetings.insert_one(meet)
    await db.meeting_participants.insert_one({
        "meeting_id": meeting_id, "user_id": user["user_id"],
        "name": user.get("name", "Host"), "role": "host",
        "joined_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"booking_id": booking_id, "meeting_id": meeting_id, "meeting_code": meeting_code,
            "date": date, "start_time": start_time, "end_time": end_time, "duration": duration,
            "guest_name": guest_name, "host_name": user.get("name", ""), "topic": topic}





@router.get("/meetings/{meeting_id}/ical")
async def export_meeting_ical(meeting_id: str):
    """Generate .ics file for a meeting (public for sharing).
    If the meeting belongs to a recurring series, an RRULE is added for
    simple patterns (daily/weekly/biweekly/monthly). For custom per-weekday
    schedules the user should fetch /api/meetings/series/{series_id}/ical instead.
    """
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    from icalendar import Calendar, Event, vCalAddress, vText
    from datetime import datetime as dt
    cal = Calendar()
    cal.add("prodid", "-//MeetFlow//Meeting//DE")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    event = Event()
    event.add("summary", meeting.get("title", "MeetFlow Meeting"))
    code = meeting.get("meeting_code", "")
    join_url = f"{os.environ.get('FRONTEND_URL', '').rstrip('/') or ''}/meetings/{meeting_id}/join"
    desc_parts = []
    if meeting.get("description"):
        desc_parts.append(meeting["description"])
    desc_parts.append(f"Meeting-Code: {code}")
    if join_url.startswith("http"):
        desc_parts.append(f"Beitreten: {join_url}")
    event.add("description", "\n\n".join(desc_parts))
    event.add("uid", f"{meeting_id}@meetflow")
    if meeting.get("scheduled_at"):
        try:
            start = dt.fromisoformat(meeting["scheduled_at"].replace("Z", "+00:00"))
            event.add("dtstart", start)
            event.add("dtend", start + timedelta(minutes=meeting.get("duration", 60)))
            event.add("dtstamp", dt.now(timezone.utc))
        except Exception:
            pass
    # Add RRULE for simple recurring patterns
    pattern = (meeting.get("recurring_pattern") or "").lower()
    pattern_to_rrule = {
        "daily": {"freq": "DAILY"},
        "weekly": {"freq": "WEEKLY"},
        "biweekly": {"freq": "WEEKLY", "interval": 2},
        "monthly": {"freq": "MONTHLY"},
    }
    if meeting.get("recurring") and pattern in pattern_to_rrule:
        event.add("rrule", pattern_to_rrule[pattern])
    event.add("location", f"MeetFlow Online (Code: {code})")
    if join_url.startswith("http"):
        event.add("url", join_url)
    # Attendees
    host_name = meeting.get("host_name") or "Host"
    host_email = None
    host_user = await db.users.find_one({"user_id": meeting.get("host_id")}, {"_id": 0, "email": 1, "name": 1})
    if host_user:
        host_email = host_user.get("email")
        host_name = host_user.get("name") or host_name
    if host_email:
        organizer = vCalAddress(f"MAILTO:{host_email}")
        organizer.params["cn"] = vText(host_name)
        event["organizer"] = organizer
    participants = await db.meeting_participants.find(
        {"meeting_id": meeting_id, "role": {"$ne": "host"}},
        {"_id": 0, "email": 1, "name": 1, "is_optional": 1}
    ).to_list(200)
    for p in participants:
        if not p.get("email"):
            continue
        att = vCalAddress(f"MAILTO:{p['email']}")
        att.params["cn"] = vText(p.get("name") or p["email"].split("@")[0])
        att.params["role"] = vText("OPT-PARTICIPANT" if p.get("is_optional") else "REQ-PARTICIPANT")
        att.params["partstat"] = vText("NEEDS-ACTION")
        att.params["rsvp"] = vText("TRUE")
        event.add("attendee", att, encode=0)
    cal.add_component(event)
    return Response(
        content=cal.to_ical(), media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="meetflow_{meeting_id}.ics"'}
    )


@router.get("/meetings/series/{series_id}/ical")
async def export_series_ical(series_id: str):
    """Generate a single .ics file containing one VEVENT per occurrence of a series.

    Useful for custom per-weekday schedules where a single RRULE cannot represent
    multiple distinct time slots in the same week.
    """
    occurrences = await db.meetings.find(
        {"series_id": series_id}, {"_id": 0}
    ).sort("scheduled_at", 1).to_list(500)
    if not occurrences:
        raise HTTPException(status_code=404, detail="Series not found")
    from icalendar import Calendar, Event, vCalAddress, vText
    from datetime import datetime as dt
    cal = Calendar()
    cal.add("prodid", "-//MeetFlow//Series//DE")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    public_root = (os.environ.get("FRONTEND_URL", "") or "").rstrip("/")
    for occ in occurrences:
        code = occ.get("meeting_code", "")
        event = Event()
        event.add("summary", occ.get("title", "MeetFlow Meeting"))
        desc = occ.get("description", "") or ""
        desc += f"\n\nMeeting-Code: {code}"
        join_url = f"{public_root}/meetings/{occ['meeting_id']}/join" if public_root else ""
        if join_url:
            desc += f"\nBeitreten: {join_url}"
            event.add("url", join_url)
        event.add("description", desc)
        event.add("uid", f"{occ['meeting_id']}@meetflow")
        if occ.get("scheduled_at"):
            try:
                start = dt.fromisoformat(occ["scheduled_at"].replace("Z", "+00:00"))
                event.add("dtstart", start)
                event.add("dtend", start + timedelta(minutes=occ.get("duration", 60)))
                event.add("dtstamp", dt.now(timezone.utc))
            except Exception:
                continue
        event.add("location", f"MeetFlow Online (Code: {code})")
        # Attendees
        participants = await db.meeting_participants.find(
            {"meeting_id": occ["meeting_id"], "role": {"$ne": "host"}},
            {"_id": 0, "email": 1, "name": 1, "is_optional": 1}
        ).to_list(200)
        for p in participants:
            if not p.get("email"):
                continue
            att = vCalAddress(f"MAILTO:{p['email']}")
            att.params["cn"] = vText(p.get("name") or p["email"].split("@")[0])
            att.params["role"] = vText("OPT-PARTICIPANT" if p.get("is_optional") else "REQ-PARTICIPANT")
            att.params["partstat"] = vText("NEEDS-ACTION")
            event.add("attendee", att, encode=0)
        cal.add_component(event)
    return Response(
        content=cal.to_ical(), media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="meetflow_series_{series_id}.ics"'}
    )



@router.get("/schedule-polls/{poll_id}/ical")
async def export_schedule_poll_ical(poll_id: str):
    """Generate .ics for a confirmed schedule poll."""
    poll = await db.schedule_polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll.get("status") != "confirmed" or not poll.get("confirmed_slot_id"):
        raise HTTPException(status_code=400, detail="Poll not yet confirmed")
    slot = next((s for s in poll.get("time_slots", []) if s["slot_id"] == poll["confirmed_slot_id"]), None)
    if not slot:
        raise HTTPException(status_code=400, detail="Confirmed slot not found")
    from icalendar import Calendar, Event
    from datetime import datetime as dt
    import pytz
    cal = Calendar()
    cal.add("prodid", "-//MeetFlow//Schedule//DE")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    event = Event()
    event.add("summary", poll.get("title") or "Termin")
    if poll.get("description"):
        event.add("description", poll.get("description"))
    event.add("uid", f"{poll_id}@meetflow.app")
    event.add("dtstamp", dt.now(timezone.utc))
    event.add("status", "CONFIRMED")
    try:
        tz = pytz.timezone("Europe/Berlin")
        start = tz.localize(dt.fromisoformat(f"{slot['date']}T{slot['start_time']}:00"))
        end = tz.localize(dt.fromisoformat(f"{slot['date']}T{slot['end_time']}:00"))
        event.add("dtstart", start)
        event.add("dtend", end)
    except Exception as e:
        logger.error(f"schedule-poll ical date parse error: {e}")
        # fallback: try without seconds
        try:
            tz = pytz.timezone("Europe/Berlin")
            start = tz.localize(dt.fromisoformat(f"{slot['date']}T{slot['start_time']}"))
            end = tz.localize(dt.fromisoformat(f"{slot['date']}T{slot['end_time']}"))
            event.add("dtstart", start)
            event.add("dtend", end)
        except Exception:
            raise HTTPException(status_code=500, detail="Could not build ical")
    cal.add_component(event)
    return Response(
        content=cal.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="termin_{poll_id}.ics"'},
    )

@router.get("/bookings/{booking_id}/ical")
async def export_booking_ical(booking_id: str):
    """Generate .ics for a booking."""
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    from icalendar import Calendar, Event
    from datetime import datetime as dt
    import pytz
    cal = Calendar()
    cal.add("prodid", "-//MeetFlow//Booking//DE")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    event = Event()
    event.add("summary", booking.get("topic") or f"Meeting mit {booking.get('host_name', '')}")
    description = f"Buchung mit {booking.get('host_name', '')}"
    if booking.get("guest_name"):
        description += f"\nGast: {booking['guest_name']}"
    meeting_id = booking.get("meeting_id")
    frontend_url = os.environ.get("FRONTEND_URL", "")
    meeting_link = f"{frontend_url}/meetings/{meeting_id}/join" if meeting_id and frontend_url else ""
    if meeting_id:
        description += f"\nMeeting-ID: {meeting_id}"
    if meeting_link:
        description += f"\nMeeting-Link: {meeting_link}"
    event.add("description", description)
    if meeting_link:
        event.add("url", meeting_link)
    event.add("uid", f"{booking_id}@meetflow.app")
    event.add("dtstamp", dt.now(timezone.utc))
    try:
        tz = pytz.timezone("Europe/Berlin")
        start = tz.localize(dt.fromisoformat(f"{booking['date']}T{booking['start_time']}:00"))
        end = tz.localize(dt.fromisoformat(f"{booking['date']}T{booking['end_time']}:00"))
        event.add("dtstart", start)
        event.add("dtend", end)
    except Exception as e:
        logger.error(f"iCal date parse error: {e}")
        try:
            start = dt.fromisoformat(f"{booking['date']}T{booking['start_time']}:00")
            end = dt.fromisoformat(f"{booking['date']}T{booking['end_time']}:00")
            event.add("dtstart", start)
            event.add("dtend", end)
        except Exception:
            pass
    event.add("location", "MeetFlow Video-Meeting")
    event.add("status", "CONFIRMED")
    cal.add_component(event)
    return Response(
        content=cal.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="buchung_{booking_id}.ics"'},
    )




@router.post("/general-polls")
async def create_general_poll(req: GeneralPollCreateRequest, request: Request):
    user = await get_current_user(request)
    poll_id = f"gpoll_{uuid.uuid4().hex[:10]}"
    share_token = uuid.uuid4().hex[:12]
    poll = {
        "poll_id": poll_id, "share_token": share_token,
        "title": req.title, "description": req.description,
        "poll_type": req.poll_type, "options": req.options,
        "allow_custom_options": req.allow_custom_options,
        "is_anonymous": req.is_anonymous, "deadline": req.deadline,
        "created_by": user["user_id"], "creator_name": user.get("name", ""),
        "status": "open", "votes": [], "comments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.general_polls.insert_one(poll)
    return {"poll_id": poll_id, "share_token": share_token}

@router.get("/general-polls")
async def list_general_polls(request: Request, page: int = 1, limit: int = 20, search: Optional[str] = None):
    user = await get_current_user(request)
    query = {"created_by": user["user_id"]}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    total = await db.general_polls.count_documents(query)
    skip = (max(1, page) - 1) * limit
    polls = await db.general_polls.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"polls": polls, "total": total, "page": page, "pages": max(1, -(-total // limit))}

@router.get("/general-polls/{poll_id}")
async def get_general_poll(poll_id: str, request: Request):
    await get_current_user(request)
    poll = await db.general_polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    return poll

@router.get("/general-polls/public/{share_token}")
async def get_general_poll_public(share_token: str):
    poll = await db.general_polls.find_one({"share_token": share_token}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    return poll

@router.post("/general-polls/public/{share_token}/vote")
async def vote_general_poll(share_token: str, req: GeneralPollVoteRequest):
    poll = await db.general_polls.find_one({"share_token": share_token}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if poll["status"] != "open":
        raise HTTPException(status_code=400, detail="Poll is closed")
    vote_id = f"gvote_{uuid.uuid4().hex[:6]}"
    raw_selected = req.selected_options if req.selected_options else req.selected
    # Convert indices to option text for consistency
    options = poll.get("options", [])
    selected = []
    for s in (raw_selected or []):
        if isinstance(s, int) and 0 <= s < len(options):
            selected.append(options[s])
        else:
            selected.append(s)
    vote = {
        "vote_id": vote_id, "voter_name": req.voter_name,
        "voter_email": req.voter_email, "selected_options": selected,
        "priority_order": req.priority_order,
        "voted_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = None
    for i, v in enumerate(poll.get("votes", [])):
        if v["voter_name"].lower() == req.voter_name.lower():
            existing = i
            break
    if existing is not None:
        await db.general_polls.update_one({"share_token": share_token}, {"$set": {f"votes.{existing}": vote}})
    else:
        await db.general_polls.update_one({"share_token": share_token}, {"$push": {"votes": vote}})
    return {"message": "Vote recorded", "vote_id": vote_id}

@router.post("/general-polls/public/{share_token}/comment")
async def comment_general_poll(share_token: str, request: Request):
    body = await request.json()
    poll = await db.general_polls.find_one({"share_token": share_token})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    comment = {"comment_id": f"cmt_{uuid.uuid4().hex[:6]}", "author_name": body.get("author_name", "Anonym"), "text": body.get("text", ""), "created_at": datetime.now(timezone.utc).isoformat()}
    await db.general_polls.update_one({"share_token": share_token}, {"$push": {"comments": comment}})
    return comment

@router.post("/general-polls/public/{share_token}/add-option")
async def add_custom_option(share_token: str, request: Request):
    body = await request.json()
    poll = await db.general_polls.find_one({"share_token": share_token}, {"_id": 0})
    if not poll or not poll.get("allow_custom_options"):
        raise HTTPException(status_code=400, detail="Custom options not allowed")
    option = body.get("option", "").strip()
    if not option or option in poll.get("options", []):
        raise HTTPException(status_code=400, detail="Invalid or duplicate option")
    await db.general_polls.update_one({"share_token": share_token}, {"$push": {"options": option}})
    return {"message": "Option added", "option": option}

@router.post("/general-polls/{poll_id}/close")
async def close_general_poll(poll_id: str, request: Request):
    user = await get_current_user(request)
    poll = await db.general_polls.find_one({"poll_id": poll_id})
    if not poll or poll["created_by"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.general_polls.update_one({"poll_id": poll_id}, {"$set": {"status": "closed"}})
    return {"message": "Poll closed"}

@router.delete("/general-polls/{poll_id}")
async def delete_general_poll(poll_id: str, request: Request):
    user = await get_current_user(request)
    poll = await db.general_polls.find_one({"poll_id": poll_id})
    if not poll or (poll["created_by"] != user["user_id"] and not await has_cap(user, "scheduling.delete_others", db)):
        raise HTTPException(status_code=403, detail="Not authorized")
    await db.general_polls.delete_one({"poll_id": poll_id})
    return {"message": "Poll deleted"}




@router.get("/schedule-polls/{poll_id}/export/csv")
async def export_schedule_poll_csv(poll_id: str, request: Request):
    await get_current_user(request)
    poll = await db.schedule_polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["Teilnehmer", "E-Mail"]
    for slot in poll.get("time_slots", []):
        headers.append(f"{slot['date']} {slot['start_time']}-{slot['end_time']}")
    writer.writerow(headers)
    for vote in poll.get("votes", []):
        row = [vote["voter_name"], vote.get("voter_email", "")]
        for slot in poll.get("time_slots", []):
            row.append(vote.get("votes", {}).get(slot["slot_id"], "-"))
        writer.writerow(row)
    score_row = ["Score", ""]
    for slot in poll.get("time_slots", []):
        s = sum(2 if v.get("votes", {}).get(slot["slot_id"]) == "yes" else (1 if v.get("votes", {}).get(slot["slot_id"]) == "maybe" else 0) for v in poll.get("votes", []))
        score_row.append(s)
    writer.writerow(score_row)
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="terminplanung_{poll_id}.csv"'})

@router.get("/schedule-polls/{poll_id}/export/pdf")
async def export_schedule_poll_pdf(poll_id: str, request: Request):
    await get_current_user(request)
    poll = await db.schedule_polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("<b>MeetFlow - Terminplanung</b>", styles["Title"]))
    elements.append(Paragraph(f"{poll['title']}", styles["Heading2"]))
    if poll.get("description"):
        elements.append(Paragraph(poll["description"], styles["Normal"]))
    elements.append(Spacer(1, 12))
    headers = ["Teilnehmer"]
    for slot in poll.get("time_slots", []):
        headers.append(f"{slot['date']}\n{slot['start_time']}-{slot['end_time']}")
    table_data = [headers]
    for vote in poll.get("votes", []):
        row = [vote["voter_name"]]
        for slot in poll.get("time_slots", []):
            v = vote.get("votes", {}).get(slot["slot_id"], "-")
            row.append({"yes": "Ja", "no": "Nein", "maybe": "Vielleicht"}.get(v, "-"))
        table_data.append(row)
    score_row = ["Score"]
    for slot in poll.get("time_slots", []):
        s = sum(2 if v.get("votes", {}).get(slot["slot_id"]) == "yes" else (1 if v.get("votes", {}).get(slot["slot_id"]) == "maybe" else 0) for v in poll.get("votes", []))
        score_row.append(str(s))
    table_data.append(score_row)
    t = Table(table_data)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5D4E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F3F4F1")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E4E0")),
    ])
    t.setStyle(style)
    elements.append(t)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"Erstellt von: {poll.get('creator_name', '')}", styles["Normal"]))
    elements.append(Paragraph(f"Status: {poll.get('status', 'open')}", styles["Normal"]))
    doc.build(elements)
    return Response(content=buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="terminplanung_{poll_id}.pdf"'})




@router.post("/schedule-polls/{poll_id}/ai-suggest")
async def ai_suggest_best_time(poll_id: str, request: Request):
    await get_current_user(request)
    poll = await db.schedule_polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    if len(poll.get("votes", [])) < 1:
        raise HTTPException(status_code=400, detail="Need at least 1 vote for AI analysis")
    api_key = await _get_llm_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="No LLM key configured")
    slot_data = []
    for slot in poll.get("time_slots", []):
        yes_count = sum(1 for v in poll["votes"] if v.get("votes", {}).get(slot["slot_id"]) == "yes")
        maybe_count = sum(1 for v in poll["votes"] if v.get("votes", {}).get(slot["slot_id"]) == "maybe")
        no_count = sum(1 for v in poll["votes"] if v.get("votes", {}).get(slot["slot_id"]) == "no")
        slot_data.append(f"{slot['date']} {slot['start_time']}-{slot['end_time']}: {yes_count} Ja, {maybe_count} Vielleicht, {no_count} Nein")
    voters = ", ".join([v["voter_name"] for v in poll["votes"]])
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=api_key, session_id=f"ai_sched_{poll_id}", system_message="Du bist ein Terminplanungs-Assistent. Analysiere die Abstimmungsergebnisse und gib eine klare Empfehlung auf Deutsch. Sei praezise und begruende deine Empfehlung.")
        chat.with_model("openai", "gpt-5.2")
        prompt = f"Terminplanung: {poll['title']}\nTeilnehmer: {voters}\n\nAbstimmungsergebnisse:\n" + "\n".join(slot_data) + f"\n\nGesamt: {len(poll['votes'])} Teilnehmer\n\nBitte analysiere und empfehle den besten Termin. Begruende warum und schlage ggf. Alternativen vor."
        suggestion = await chat.send_message(UserMessage(text=prompt))
        return {"suggestion": suggestion, "total_voters": len(poll["votes"]), "slots_analyzed": len(poll["time_slots"])}
    except Exception as e:
        logger.error(f"AI scheduling suggestion failed: {e}")
        raise HTTPException(status_code=500, detail="AI suggestion failed")




@router.get("/timezones")
async def list_timezones():
    common_tz = [
        "Europe/Berlin", "Europe/London", "Europe/Paris", "Europe/Zurich", "Europe/Vienna",
        "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
        "Asia/Tokyo", "Asia/Shanghai", "Asia/Dubai", "Asia/Kolkata",
        "Australia/Sydney", "Pacific/Auckland", "America/Sao_Paulo",
        "Africa/Cairo", "Africa/Johannesburg", "UTC",
    ]
    return {"timezones": common_tz}





