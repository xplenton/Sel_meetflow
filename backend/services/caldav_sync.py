"""
Read-only external calendar sync via ICS subscription URLs.

Supported: Outlook "Publish Calendar" ICS link, Google Calendar "Secret Address
in iCal format", Apple Calendar public ICS, any RFC 5545 compliant feed.

Stored per user in `caldav_configs` (one active ICS URL + optional basic-auth).
Fetched events land in `external_calendar_events` with a hash-based upsert so
re-syncs don't duplicate.

Conflicts are checked via `find_conflicts(user_id, start, end)` used by
meeting-create routes to warn the user before booking.
"""
from __future__ import annotations

import hashlib
import logging
from base64 import b64encode
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import httpx
from icalendar import Calendar

from database import db

logger = logging.getLogger(__name__)


def _to_iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _event_hash(user_id: str, uid: str, start_iso: Optional[str]) -> str:
    h = hashlib.sha256(f"{user_id}|{uid}|{start_iso or ''}".encode()).hexdigest()
    return h[:24]


async def get_user_config(user_id: str) -> Dict[str, Any]:
    cfg = await db.caldav_configs.find_one({"user_id": user_id}, {"_id": 0})
    if not cfg:
        return {"user_id": user_id, "enabled": False, "url": "",
                "username": "", "has_password": False,
                "last_sync_at": None, "last_sync_error": None,
                "events_count": 0, "auto_sync": True}
    # Ensure all expected fields are present with defaults
    defaults = {"enabled": False, "url": "", "username": "", "has_password": False,
                "last_sync_at": None, "last_sync_error": None, "events_count": 0, "auto_sync": True}
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
    # Compute has_password from actual password field
    cfg["has_password"] = bool(cfg.get("password"))
    # Remove password from response
    cfg.pop("password", None)
    return cfg


async def set_user_config(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"enabled", "url", "username", "password", "auto_sync"}
    clean: Dict[str, Any] = {}
    for k, v in (updates or {}).items():
        if k in allowed:
            clean[k] = v
    # Keep existing password when client submits a masked placeholder
    pw = clean.get("password")
    if pw is None or str(pw).startswith("***"):
        clean.pop("password", None)
    if "url" in clean:
        clean["url"] = (clean["url"] or "").strip()
    clean["user_id"] = user_id
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.caldav_configs.update_one(
        {"user_id": user_id},
        {"$set": clean, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    out = await db.caldav_configs.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    out["has_password"] = bool((await db.caldav_configs.find_one({"user_id": user_id}, {"password": 1}) or {}).get("password"))
    return out


async def _fetch_ics(url: str, username: str = "", password: str = "") -> str:
    """Download the ICS feed. Raises ValueError on HTTP errors."""
    headers = {"User-Agent": "MeetFlow-CalDAV-Sync/1.0",
               "Accept": "text/calendar, */*"}
    if username and password:
        token = b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
    if r.status_code >= 400:
        # Iter 277 — generate a user-friendly message instead of dumping raw
        # HTML from a login-wall response (Outlook private URL, Emergent
        # ingress auth-redirect, etc.). The first 160 chars of an HTML
        # redirect are unreadable to admins and look like a backend crash.
        body_preview = (r.text or "").strip()
        looks_like_html = body_preview.lower().startswith("<!doctype") or body_preview.startswith("<html") or "<style" in body_preview[:200].lower()
        if r.status_code == 401 or r.status_code == 403:
            if looks_like_html:
                raise ValueError(
                    "Die ICS-URL erfordert Anmeldung. Verwende eine OEFFENTLICHE "
                    "Veroeffentlichungs-URL (Outlook: 'Kalender veroeffentlichen' -> ICS-Link; "
                    "Google: Kalender-Einstellungen -> 'Geheime Adresse im iCal-Format'). "
                    "Die normale Outlook-Webadresse funktioniert nicht."
                )
            raise ValueError(f"Zugriff verweigert (HTTP {r.status_code}). Benutzer/Passwort prüfen oder oeffentliche ICS-URL verwenden.")
        if r.status_code == 404:
            raise ValueError("ICS-URL nicht gefunden (HTTP 404). URL prüfen.")
        if looks_like_html:
            raise ValueError(f"Server lieferte HTML statt einer ICS-Datei (HTTP {r.status_code}). Bitte oeffentliche ICS-URL verwenden.")
        raise ValueError(f"HTTP {r.status_code}: {body_preview[:160]}")
    body = r.text
    if "BEGIN:VCALENDAR" not in body:
        # Empty / wrong content-type / HTML again
        preview = body.strip()
        if preview.lower().startswith("<!doctype") or preview.startswith("<html"):
            raise ValueError(
                "Die URL liefert eine HTML-Seite statt eines ICS-Kalenders. "
                "Bitte oeffentliche ICS-URL aus Outlook ('Kalender veroeffentlichen') "
                "oder Google ('Geheime Adresse im iCal-Format') verwenden."
            )
        raise ValueError("Kein gültiger ICS-Feed (BEGIN:VCALENDAR fehlt)")
    return body


def _parse_ics_events(ics_text: str, user_id: str, *, horizon_days_past: int = 7,
                      horizon_days_future: int = 120) -> List[Dict[str, Any]]:
    """Extract event dicts within the given time horizon."""
    cal = Calendar.from_ical(ics_text)
    now = datetime.now(timezone.utc)
    lower = now - timedelta(days=horizon_days_past)
    upper = now + timedelta(days=horizon_days_future)
    events: List[Dict[str, Any]] = []
    for comp in cal.walk("VEVENT"):
        try:
            uid = str(comp.get("UID") or "")
            summary = str(comp.get("SUMMARY") or "").strip()
            location = str(comp.get("LOCATION") or "").strip()
            dtstart = comp.get("DTSTART")
            dtend = comp.get("DTEND")
            start = dtstart.dt if dtstart else None
            end = dtend.dt if dtend else None
            # Normalise date-only to full-day UTC interval
            if isinstance(start, datetime) is False and start is not None:
                start = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
            if isinstance(end, datetime) is False and end is not None:
                end = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
            if start and start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end and end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if not start:
                continue
            if start > upper or (end and end < lower):
                continue
            status = str(comp.get("STATUS") or "CONFIRMED").upper()
            start_iso = _to_iso(start)
            events.append({
                "event_hash": _event_hash(user_id, uid, start_iso),
                "user_id": user_id,
                "uid": uid,
                "summary": summary or "(ohne Titel)",
                "location": location,
                "start": start_iso,
                "end": _to_iso(end),
                "status": status,
                "all_day": not isinstance(dtstart.dt, datetime) if dtstart else False,
                "source": "caldav",
            })
        except Exception as e:
            logger.debug(f"[caldav] skip event: {e}")
    return events


async def sync_user_calendar(user_id: str) -> Dict[str, Any]:
    """Fetch + parse + upsert events for a single user. Returns stats."""
    cfg = await db.caldav_configs.find_one({"user_id": user_id}, {"_id": 0})
    if not cfg:
        raise ValueError("Kein CalDAV-Profil für diesen Nutzer")
    if not cfg.get("enabled"):
        raise ValueError("CalDAV ist deaktiviert")
    url = (cfg.get("url") or "").strip()
    if not url:
        raise ValueError("Keine ICS-URL hinterlegt")

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        ics = await _fetch_ics(url, cfg.get("username", "") or "", cfg.get("password", "") or "")
        events = _parse_ics_events(ics, user_id)
    except Exception as e:
        await db.caldav_configs.update_one(
            {"user_id": user_id},
            {"$set": {"last_sync_error": str(e), "last_sync_at": now_iso}},
        )
        raise

    upserts = 0
    seen: List[str] = []
    for ev in events:
        ev["last_seen_at"] = now_iso
        seen.append(ev["event_hash"])
        await db.external_calendar_events.update_one(
            {"event_hash": ev["event_hash"]},
            {"$set": ev, "$setOnInsert": {"first_seen_at": now_iso}},
            upsert=True,
        )
        upserts += 1
    # Purge stale events for this user that weren't in this feed
    if seen:
        purge = await db.external_calendar_events.delete_many({
            "user_id": user_id,
            "event_hash": {"$nin": seen},
        })
        purged = purge.deleted_count
    else:
        purged = 0

    await db.caldav_configs.update_one(
        {"user_id": user_id},
        {"$set": {"last_sync_at": now_iso, "last_sync_error": None,
                  "events_count": len(events)}},
    )
    return {"synced": upserts, "purged": purged, "events": len(events), "at": now_iso}


async def sync_all_enabled_users(limit: int = 500) -> Dict[str, Any]:
    """Iterate auto_sync users — called from maintenance cron."""
    cursor = db.caldav_configs.find({"enabled": True, "auto_sync": {"$ne": False}},
                                    {"_id": 0, "user_id": 1}).limit(limit)
    configs = await cursor.to_list(limit)
    ok = fail = 0
    for c in configs:
        try:
            await sync_user_calendar(c["user_id"])
            ok += 1
        except Exception as e:
            fail += 1
            logger.info(f"[caldav] sync failed for {c['user_id']}: {e}")
    return {"ok": ok, "fail": fail, "total": len(configs)}


async def find_conflicts(user_id: str, start_iso: str, end_iso: Optional[str] = None,
                         *, buffer_minutes: int = 0) -> List[Dict[str, Any]]:
    """Return external events that overlap with the given [start, end] window."""
    if not start_iso:
        return []
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except Exception:
        return []
    if end_iso:
        try:
            end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        except Exception:
            end = start + timedelta(minutes=60)
    else:
        end = start + timedelta(minutes=60)
    if buffer_minutes:
        start = start - timedelta(minutes=buffer_minutes)
        end = end + timedelta(minutes=buffer_minutes)
    # An external event conflicts iff ev.start < end AND (ev.end or ev.start + 1h) > start
    cursor = db.external_calendar_events.find({
        "user_id": user_id,
        "start": {"$lt": end.isoformat()},
        "status": {"$ne": "CANCELLED"},
    }, {"_id": 0}).sort("start", 1).limit(50)
    events = await cursor.to_list(50)
    conflicts: List[Dict[str, Any]] = []
    for ev in events:
        try:
            ev_end_iso = ev.get("end") or ev["start"]
            ev_end = datetime.fromisoformat(ev_end_iso.replace("Z", "+00:00"))
        except Exception:
            continue
        if ev_end > start:
            conflicts.append(ev)
    return conflicts
