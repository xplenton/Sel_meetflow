"""Recurring + combo (multi sub-room) booking endpoints."""
from __future__ import annotations

import uuid
from datetime import date as _date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from database import db
from dependencies import get_current_user
from services.permissions import require_cap

from .._common import (
    ResourceBooking,
    _audit_booking, _check_conflicts, _parse_iso,
)

router = APIRouter(tags=["resources-bookings"])


@router.post("/resource-bookings/series")
async def create_series_booking(payload: dict, user=Depends(get_current_user)):
    """Create a recurring booking.

    Variante A — periodisch:
       {resource_id, title, start_at, end_at,
        recurrence: 'daily'|'weekly'|'biweekly'|'every_4_weeks'|'monthly',
        occurrences: N, ...}

    Iter 334 — Variante B — explizit gewählte Daten (Kalender):
       {resource_id, title, start_at, end_at,
        recurrence: 'custom',
        custom_dates: ['YYYY-MM-DD', ...],   # mind. 1, max 52
        ...}
       Die Tageszeit (HH:MM) wird aus base_start/base_end übernommen, die
       Datums-Komponente von custom_dates. So kann der User in einem
       Kalender mehrere Tage über mehrere Monate hinweg auswählen.
    """
    # Local import to avoid circular module load — crud imports from series? no,
    # but isolating this keeps the per-module dependency surface visible.
    from .crud import create_booking

    await require_cap(user, "resources.book", db)
    recurrence = payload.get("recurrence", "weekly")
    base_start = _parse_iso(payload["start_at"])
    base_end = _parse_iso(payload["end_at"])
    if base_end <= base_start:
        raise HTTPException(400, "Endzeit muss nach Startzeit liegen")

    starts_ends: list[tuple[datetime, datetime]] = []
    if recurrence == "custom":
        dates = payload.get("custom_dates") or []
        if not isinstance(dates, list) or not dates:
            raise HTTPException(400, "custom_dates (Liste) erforderlich für recurrence=custom")
        if len(dates) > 52:
            raise HTTPException(400, "Maximal 52 Termine pro Serie")
        for d_str in dates:
            try:
                d = _date.fromisoformat(d_str)
            except Exception:
                raise HTTPException(400, f"Ungültiges Datum: {d_str}")
            s = base_start.replace(year=d.year, month=d.month, day=d.day)
            e = base_end.replace(year=d.year, month=d.month, day=d.day)
            # Über Mitternacht hinweg: tag-überschreitende Buchungen behalten ihre Dauer
            if e <= s:
                e = s + (base_end - base_start)
            starts_ends.append((s, e))
        occurrences = len(starts_ends)
    else:
        # Iter 334 — Neu: every_4_weeks + monthly (kalender-monat).
        delta_map = {
            "daily": timedelta(days=1),
            "weekly": timedelta(days=7),
            "biweekly": timedelta(days=14),
            "every_4_weeks": timedelta(days=28),
        }
        occurrences = max(1, min(int(payload.get("occurrences", 4)), 52))
        if recurrence == "monthly":
            # Robust gegen Monatslängen: addiere ganze Monate ohne dateutil.
            import calendar as _cal
            for i in range(occurrences):
                year = base_start.year + (base_start.month - 1 + i) // 12
                month = (base_start.month - 1 + i) % 12 + 1
                # Tag begrenzen auf gültigen Tag (z.B. 31. Januar → 28. Februar)
                day = min(base_start.day, _cal.monthrange(year, month)[1])
                s = base_start.replace(year=year, month=month, day=day)
                e_year = base_end.year + (base_end.month - 1 + i) // 12
                e_month = (base_end.month - 1 + i) % 12 + 1
                e_day = min(base_end.day, _cal.monthrange(e_year, e_month)[1])
                e = base_end.replace(year=e_year, month=e_month, day=e_day)
                starts_ends.append((s, e))
        elif recurrence in delta_map:
            delta = delta_map[recurrence]
            for i in range(occurrences):
                starts_ends.append((base_start + delta * i, base_end + delta * i))
        else:
            raise HTTPException(400, "recurrence muss daily/weekly/biweekly/every_4_weeks/monthly/custom sein")

    series_id = f"sb_{uuid.uuid4().hex[:10]}"
    created = []
    conflicts_total = []
    for i, (s, e) in enumerate(starts_ends):
        confs = await _check_conflicts(payload["resource_id"], s, e)
        if confs:
            conflicts_total.append({"occurrence": i + 1, "start": s.isoformat()})
            continue
        body = {**payload, "start_at": s.isoformat(), "end_at": e.isoformat()}
        body.pop("recurrence", None)
        body.pop("occurrences", None)
        body.pop("custom_dates", None)
        try:
            doc = await create_booking(body, user)
            await db.resource_bookings.update_one(
                {"booking_id": doc["booking_id"]},
                {"$set": {"series_id": series_id, "series_index": i + 1, "series_total": occurrences}}
            )
            created.append(doc["booking_id"])
        except HTTPException as e:
            conflicts_total.append({"occurrence": i + 1, "start": s.isoformat(), "error": str(e.detail)})
    return {"series_id": series_id, "created": created, "skipped": conflicts_total}


@router.post("/resource-bookings/combo")
async def create_combo_booking(payload: dict, user=Depends(get_current_user)):
    """Book multiple sub-rooms at once (e.g. Bereich A + B).
    payload: {parent_resource_id, sub_ids: ["A","B"], title, start_at, end_at, ...}

    Validates against `parent.allowed_combinations` (whitelist). Either all
    requested subs get booked or NONE — atomic via rollback on failure.
    """
    await require_cap(user, "resources.book", db)
    parent_id = payload.get("parent_resource_id")
    sub_ids = payload.get("sub_ids") or []
    if not parent_id or len(sub_ids) < 2:
        raise HTTPException(400, "parent_resource_id und mindestens 2 sub_ids noetig")
    parent = await db.resources.find_one({"resource_id": parent_id}, {"_id": 0})
    if not parent or not parent.get("is_splitable"):
        raise HTTPException(400, "Kein teilbarer Parent-Raum")

    # Whitelist-Check
    combos = parent.get("allowed_combinations") or []
    if combos and not any(set(c) == set(sub_ids) for c in combos):
        raise HTTPException(400, f"Kombination {sub_ids} nicht erlaubt")

    # Resolve sub-resource IDs
    children = await db.resources.find(
        {"parent_resource_id": parent_id, "sub_id": {"$in": sub_ids}}, {"_id": 0}
    ).to_list(10)
    if len(children) != len(sub_ids):
        raise HTTPException(404, "Nicht alle Teilbereiche gefunden")

    start = _parse_iso(payload["start_at"])
    end = _parse_iso(payload["end_at"])
    if end <= start:
        raise HTTPException(400, "Endzeit muss nach Startzeit liegen")

    # Conflict-check for each child
    for ch in children:
        confs = await _check_conflicts(ch["resource_id"], start, end)
        if confs:
            raise HTTPException(409, {"detail": f"Konflikt bei Teilbereich {ch['sub_id']}",
                                      "conflicts": confs})

    # Create N bookings with a shared combo_id; if any insert fails, roll back.
    combo_id = f"cb_{uuid.uuid4().hex[:10]}"
    created_ids = []
    try:
        for ch in children:
            bk = ResourceBooking(
                resource_id=ch["resource_id"],
                user_id=user["user_id"],
                title=payload.get("title", "Kombi-Buchung"),
                description=payload.get("description"),
                start_at=start, end_at=end,
                cost_center=payload.get("cost_center"),
                account=payload.get("account"),
                status="pending_approval" if parent.get("requires_approval") else "confirmed",
            )
            doc = bk.model_dump()
            doc["combo_id"] = combo_id
            doc["combo_parent_id"] = parent_id
            doc["combo_sub_ids"] = sub_ids
            await db.resource_bookings.insert_one(doc)
            created_ids.append(bk.booking_id)
            await _audit_booking(user, bk.booking_id, "combo_booking_created", {"combo_id": combo_id})
    except Exception as e:
        for bid in created_ids:
            await db.resource_bookings.delete_one({"booking_id": bid})
        raise HTTPException(500, f"Combo-Buchung fehlgeschlagen: {e}")
    return {"combo_id": combo_id, "booking_ids": created_ids, "sub_ids": sub_ids}
