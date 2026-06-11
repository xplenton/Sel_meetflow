"""Reporting & analytics endpoints: damage reports + free-slot suggestions."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from database import db
from dependencies import get_current_user
from services.permissions import has_cap

from .._common import _audit_booking, _parse_iso

router = APIRouter(tags=["resources-bookings"])


@router.post("/resource-bookings/{booking_id}/damage-report")
async def report_damage(booking_id: str, payload: dict, user=Depends(get_current_user)):
    """Vehicle damage report — stored on the booking + on the resource."""
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    report = {
        "report_id": f"dmg_{uuid.uuid4().hex[:10]}",
        "booking_id": booking_id,
        "resource_id": bk["resource_id"],
        "reporter_user_id": user["user_id"],
        "description": payload.get("description", ""),
        "severity": payload.get("severity", "minor"),
        "attachments": payload.get("attachments", []),
        "created_at": datetime.now(timezone.utc),
        "status": "open",
    }
    await db.damage_reports.insert_one(report)
    await _audit_booking(user, booking_id, "damage_reported", {"report_id": report["report_id"]})
    report.pop("_id", None)
    return report


@router.get("/resources/{resource_id}/damage-reports")
async def list_damage_reports(resource_id: str, user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    items = await db.damage_reports.find({"resource_id": resource_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for it in items:
        if isinstance(it.get("created_at"), datetime):
            it["created_at"] = it["created_at"].isoformat()
    return items


@router.post("/resources/{resource_id}/suggest-slots")
async def suggest_free_slots(
    resource_id: str, payload: dict, user=Depends(get_current_user),
):
    """Findet die naechsten N freien Zeitfenster ab `start_at` mit Laenge
    `duration_min`. Beruecksichtigt sowohl bestaetigte/pending-Buchungen als
    auch Sperrzeiten. Reines Lese-API fuer das BookingDialog-UI.

    payload: {start_at: ISO, duration_min: int, count?: int=3, max_days?: int=14}
    """
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")

    start_iso = payload.get("start_at")
    if not start_iso:
        raise HTTPException(400, "start_at fehlt")
    duration_min = int(payload.get("duration_min") or 60)
    if duration_min < 5 or duration_min > 24 * 60:
        raise HTTPException(400, "duration_min muss zwischen 5 und 1440 sein")
    count = max(1, min(int(payload.get("count") or 3), 10))
    max_days = max(1, min(int(payload.get("max_days") or 14), 60))

    start = _parse_iso(start_iso)
    horizon = start + timedelta(days=max_days)

    # Bestehende Buchungen + Blackouts im Horizont laden
    bookings = await db.resource_bookings.find({
        "resource_id": resource_id,
        "status": {"$in": ["confirmed", "pending_approval"]},
        "end_at": {"$gt": start},
        "start_at": {"$lt": horizon},
    }, {"_id": 0, "start_at": 1, "end_at": 1}).sort("start_at", 1).to_list(500)
    blackouts = await db.blackout_periods.find({
        "resource_id": resource_id,
        "end_at": {"$gt": start},
        "start_at": {"$lt": horizon},
    }, {"_id": 0, "start_at": 1, "end_at": 1}).sort("start_at", 1).to_list(500)

    busy = []
    for b in (bookings + blackouts):
        s, e = b.get("start_at"), b.get("end_at")
        if isinstance(s, datetime) and isinstance(e, datetime):
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if e.tzinfo is None:
                e = e.replace(tzinfo=timezone.utc)
            busy.append((s, e))
    busy.sort(key=lambda x: x[0])

    # 15-Minuten-Snap auf der Suche, beginnend bei `start` (oder nun)
    def snap_up(dt: datetime) -> datetime:
        minutes = dt.minute
        delta = (15 - (minutes % 15)) % 15
        return (dt + timedelta(minutes=delta)).replace(second=0, microsecond=0)

    candidate = snap_up(start)
    suggestions = []
    while candidate < horizon and len(suggestions) < count:
        candidate_end = candidate + timedelta(minutes=duration_min)
        # Office-Hours-Heuristic: 07:00–20:00 lokal (UTC: einfach hier)
        if candidate.hour < 7 or candidate_end.hour > 20 or candidate_end.day != candidate.day:
            # Springe auf naechsten 07:00
            next_day = (candidate + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
            candidate = next_day
            continue
        # Konflikt-Check
        overlap = next(((s, e) for (s, e) in busy
                        if s < candidate_end and e > candidate), None)
        if overlap is None:
            suggestions.append({
                "start_at": candidate.isoformat(),
                "end_at": candidate_end.isoformat(),
            })
            candidate = candidate + timedelta(minutes=duration_min)
        else:
            # Springe ans Ende des Konflikts (auf 15-Min snap)
            candidate = snap_up(overlap[1])

    return {
        "resource_id": resource_id,
        "duration_min": duration_min,
        "suggestions": suggestions,
    }
