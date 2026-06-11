"""
Calendar sync — iCal / ICS export (iter 123).

Provides three user-facing capabilities, none of which require an
external OAuth:

1. **Download a single meeting as `.ics`** (auth required).
   `GET /api/calendar/meetings/{meeting_id}/ical`
   Users can add a one-off meeting to any calendar app in one click.

2. **Personal subscribable feed** containing all meetings the user is
   either host of or invited to.
   `GET /api/calendar/feed/{token}.ics`  — no auth, token in URL.
   `GET /api/calendar/my-feed-token`     — authenticated: returns/creates
   the user's feed token + full subscription URL.
   `POST /api/calendar/my-feed-token/regenerate` — rotates the token.

3. Structured Google OAuth-based sync is left to a separate module that
   will ship once the user provides `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`.

The `.ics` payload is generated with the already-installed `icalendar`
lib (RFC 5545 compliant, supports VTIMEZONE, alarms, RRULE).
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from icalendar import Alarm, Calendar, Event, vText

from database import db, logger
from dependencies import get_current_user

router = APIRouter()

_FRONTEND_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _meeting_dtstart(meeting: dict) -> datetime:
    """Parse scheduled_at → tz-aware UTC datetime. Falls back to now()
    for instant meetings that never had a scheduled time."""
    raw = meeting.get("scheduled_at")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            pass
    created = meeting.get("created_at")
    if created:
        try:
            return datetime.fromisoformat(created.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _meeting_join_url(meeting_id: str) -> str:
    base = _FRONTEND_URL or ""
    return f"{base}/meetings/{meeting_id}/join" if base else f"/meetings/{meeting_id}/join"


def _meeting_to_vevent(meeting: dict, organizer_email: str | None = None) -> Event:
    """Render one meeting as an RFC-5545 VEVENT."""
    ev = Event()
    mid = meeting.get("meeting_id") or uuid.uuid4().hex
    ev.add("uid", f"{mid}@meetflow")
    dtstart = _meeting_dtstart(meeting)
    duration = int(meeting.get("duration") or meeting.get("duration_minutes") or 60)
    ev.add("dtstart", dtstart)
    ev.add("dtend", dtstart + timedelta(minutes=duration))
    ev.add("summary", meeting.get("title") or "Meeting")
    desc_parts: list[str] = []
    if meeting.get("description"):
        desc_parts.append(meeting["description"])
    desc_parts.append(f"Beitritt: {_meeting_join_url(mid)}")
    if meeting.get("meeting_code"):
        desc_parts.append(f"Meeting-Code: {meeting['meeting_code']}")
    ev.add("description", "\n\n".join(desc_parts))
    ev.add("location", vText(_meeting_join_url(mid)))
    ev.add("url", _meeting_join_url(mid))
    ev.add("status", "CONFIRMED" if meeting.get("status") != "ended" else "CANCELLED")
    ev.add("dtstamp", datetime.now(timezone.utc))
    if meeting.get("created_at"):
        try:
            ev.add("created", datetime.fromisoformat(meeting["created_at"].replace("Z", "+00:00")))
        except Exception:
            pass
    if organizer_email:
        ev["organizer"] = vText(f"mailto:{organizer_email}")
    # 15-minute-before reminder
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", meeting.get("title") or "Meeting")
    alarm.add("trigger", timedelta(minutes=-15))
    ev.add_component(alarm)
    return ev


def _calendar_wrapper(prodid: str = "-//MeetFlow//Calendar Sync 1.0//EN") -> Calendar:
    cal = Calendar()
    cal.add("prodid", prodid)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "MeetFlow")
    cal.add("x-wr-timezone", "Europe/Berlin")
    return cal


# ---------------------------------------------------------------------------
# 1) Single-meeting .ics is already provided by routes/scheduling.py
#    (`GET /api/meetings/{meeting_id}/ical`) — it supports RRULE for recurring
#    meetings + ATTENDEE lines + ORGANIZER. We don't duplicate it here.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 2) Personal subscribable feed — token-based, no auth on the ICS URL
# ---------------------------------------------------------------------------
async def _get_or_create_feed_token(user_id: str) -> str:
    existing = await db.calendar_feed_tokens.find_one({"user_id": user_id}, {"_id": 0})
    if existing and existing.get("token"):
        return existing["token"]
    token = secrets.token_urlsafe(24)
    await db.calendar_feed_tokens.update_one(
        {"user_id": user_id},
        {"$set": {"token": token, "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return token


def _feed_url(token: str) -> str:
    base = _FRONTEND_URL or ""
    return f"{base}/api/calendar/feed/{token}.ics" if base else f"/api/calendar/feed/{token}.ics"


def _webcal_url(token: str) -> str:
    """Calendar-app-friendly webcal:// variant — triggers a native
    'Subscribe to calendar' prompt in Google Cal / Apple Cal / Outlook."""
    url = _feed_url(token)
    return url.replace("https://", "webcal://", 1).replace("http://", "webcal://", 1)


@router.get("/calendar/my-feed-token")
async def get_my_feed_token(request: Request):
    user = await get_current_user(request)
    token = await _get_or_create_feed_token(user["user_id"])
    return {
        "token": token,
        "subscribe_url": _feed_url(token),
        "webcal_url": _webcal_url(token),
    }


@router.post("/calendar/my-feed-token/regenerate")
async def regenerate_my_feed_token(request: Request):
    user = await get_current_user(request)
    token = secrets.token_urlsafe(24)
    await db.calendar_feed_tokens.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"token": token, "rotated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {
        "token": token,
        "subscribe_url": _feed_url(token),
        "webcal_url": _webcal_url(token),
    }


@router.get("/calendar/feed/{token}.ics")
async def personal_ical_feed(token: str):
    """Public iCal feed — calendar apps can't send an Authorization
    header so we authenticate via a secret token in the URL instead.
    The token is revocable via `/calendar/my-feed-token/regenerate`."""
    token_doc = await db.calendar_feed_tokens.find_one({"token": token}, {"_id": 0})
    if not token_doc:
        raise HTTPException(status_code=404, detail="Feed not found")
    user_id = token_doc["user_id"]
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Hosted meetings
    hosted = await db.meetings.find(
        {"host_id": user_id, "status": {"$ne": "deleted"}},
        {"_id": 0},
    ).to_list(500)
    # Attended/invited meetings (participant records)
    part_ids: set[str] = set()
    async for p in db.meeting_participants.find({"user_id": user_id}, {"_id": 0, "meeting_id": 1}):
        if p.get("meeting_id"):
            part_ids.add(p["meeting_id"])
    # Invitations by email
    invite_ids: set[str] = set()
    async for inv in db.meeting_invitations.find(
        {"email": user.get("email", "")}, {"_id": 0, "meeting_id": 1}
    ):
        if inv.get("meeting_id"):
            invite_ids.add(inv["meeting_id"])
    extra_ids = list((part_ids | invite_ids) - {m["meeting_id"] for m in hosted if m.get("meeting_id")})
    extras = []
    if extra_ids:
        extras = await db.meetings.find(
            {"meeting_id": {"$in": extra_ids}, "status": {"$ne": "deleted"}},
            {"_id": 0},
        ).to_list(500)
    cal = _calendar_wrapper()
    seen: set[str] = set()
    for m in hosted + extras:
        mid = m.get("meeting_id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        try:
            cal.add_component(_meeting_to_vevent(m, organizer_email=user.get("email")))
        except Exception as e:
            logger.warning(f"[ical-feed] skip meeting {mid}: {e}")
    return Response(
        content=cal.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300"},
    )
