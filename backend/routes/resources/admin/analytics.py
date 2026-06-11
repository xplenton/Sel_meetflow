"""
Resources/admin · Analytics & Dashboards.

Aggregations for the admin dashboard tab, availability snapshot for the
resource cards, multi-resource Gantt-style occupancy view, hybrid-work
"who's in office today" widget, no-show / by-department analytics, vehicle
driving log, deprecated driver-license stubs, Outlook OAuth stub, plus
the resource upload-config (lives here because it's a "settings" surface).
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta
import os

from database import db
from dependencies import get_current_user
from services.permissions import require_cap, has_cap

from .._common import (
    DEFAULT_UPLOAD_MAX_MB, DEFAULT_UPLOAD_MIMES, _parse_iso, _get_upload_config,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dashboard overview
# ---------------------------------------------------------------------------

@router.get("/resources/dashboard/overview")
async def resources_dashboard(
    days: int = 30,
    user=Depends(get_current_user),
):
    """Aggregated stats for the admin dashboard tab (utilisation + counts)."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)

    # Top-level by type
    by_type = {}
    async for r in db.resources.find({"parent_resource_id": None}, {"_id": 0, "type": 1}):
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    # Booking aggregates
    pipeline = [
        {"$match": {"created_at": {"$gte": window_start}}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    bookings_by_status = {}
    async for row in db.resource_bookings.aggregate(pipeline):
        bookings_by_status[row["_id"]] = row["count"]

    # Top 5 most-used resources (by hours booked, confirmed only)
    res_index = {r["resource_id"]: r for r in
                 await db.resources.find({}, {"_id": 0, "resource_id": 1, "name": 1, "type": 1}).to_list(500)}
    top_pipeline = [
        {"$match": {"status": "confirmed", "start_at": {"$gte": window_start}}},
        {"$project": {
            "resource_id": 1,
            "minutes": {"$divide": [{"$subtract": ["$end_at", "$start_at"]}, 60000]},
        }},
        {"$group": {"_id": "$resource_id", "minutes": {"$sum": "$minutes"}, "bookings": {"$sum": 1}}},
        {"$sort": {"minutes": -1}},
        {"$limit": 5},
    ]
    top_resources = []
    async for row in db.resource_bookings.aggregate(top_pipeline):
        r = res_index.get(row["_id"])
        top_resources.append({
            "resource_id": row["_id"],
            "name": (r or {}).get("name", row["_id"]),
            "type": (r or {}).get("type", "?"),
            "hours": round(row["minutes"] / 60, 1),
            "bookings": row["bookings"],
        })

    # Catering revenue (sum of price * quantity over completed requests)
    items_index = {i["item_id"]: i for i in
                   await db.catering_items.find({}, {"_id": 0}).to_list(500)}
    catering_total = 0.0
    catering_count = 0
    async for cr in db.catering_requests.find(
            {"created_at": {"$gte": window_start}, "status": {"$in": ["confirmed", "in_progress", "delivered", "completed"]}},
            {"_id": 0, "items": 1, "status": 1},
    ):
        catering_count += 1
        for line in cr.get("items", []):
            it = items_index.get(line.get("item_id"))
            if it:
                catering_total += float(it.get("price", 0)) * int(line.get("quantity", 0))

    return {
        "window_days": days,
        "resources_by_type": by_type,
        "bookings_by_status": bookings_by_status,
        "top_resources": top_resources,
        "catering": {
            "request_count": catering_count,
            "estimated_revenue": round(catering_total, 2),
        },
    }


# ---------------------------------------------------------------------------
# Availability snapshot (resource cards)
# ---------------------------------------------------------------------------

@router.get("/resource-availability-snapshot")
async def availability_snapshot(user=Depends(get_current_user)):
    """Legacy: Snapshot-only response for the resource cards.

    Iter 356 — Body now delegates to `_compute_availability` so the new
    `/api/resource-availability` hybrid endpoint and this legacy alias share
    a single source of truth (no chance of drift between badge + slot grid).
    """
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    by_res, _ = await _compute_availability(resource_ids=None, with_bookings=False)
    return {"snapshot": by_res}


async def _compute_availability(
    resource_ids: Optional[list] = None,
    with_bookings: bool = False,
    horizon_hours: int = 12,
):
    """Shared availability computation.

    Returns ``(snapshot, bookings_by_resource)`` where:

    - ``snapshot`` is ``{<resource_id>: {busy_now, next_free, next_busy}}``
      with sub-room bookings folded into the parent entry (iter 351).
    - ``bookings_by_resource`` is ``{<resource_id>: [{booking_id, start_at,
      end_at, status, resource_id}, ...]}`` — privacy-safe slot-picker data.
      Only populated when ``with_bookings=True`` (caller asked for it).

    A single Mongo query underlies both pieces so status filter + hierarchy
    expansion can never drift between the two values.
    """
    from services.resource_hierarchy import child_to_parent_map
    child_to_parent = await child_to_parent_map()

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=horizon_hours)

    q: dict = {
        "status": {"$in": ["confirmed", "pending_approval"]},
        "end_at": {"$gt": now},
        "start_at": {"$lt": horizon},
    }
    if resource_ids:
        # Hierarchy expansion: for each requested id, also include its
        # parent (if it's a sub-room) and children (if it's a splittable
        # parent), so we see the bookings that block it.
        expanded: set = set(resource_ids)
        # Add parents of any requested children
        for rid in resource_ids:
            pid = child_to_parent.get(rid)
            if pid:
                expanded.add(pid)
        # Add children of any requested parents
        kids = await db.resources.find(
            {"parent_resource_id": {"$in": list(resource_ids)}},
            {"_id": 0, "resource_id": 1},
        ).to_list(200)
        for k in kids:
            expanded.add(k["resource_id"])
        q["resource_id"] = {"$in": list(expanded)}

    bookings = await db.resource_bookings.find(
        q, {"_id": 0, "booking_id": 1, "resource_id": 1, "start_at": 1, "end_at": 1, "status": 1},
    ).sort("start_at", 1).to_list(3000)

    by_res: dict = {}

    def _apply(rid, s, e):
        entry = by_res.setdefault(
            rid, {"busy_now": False, "next_free": None, "next_busy": None}
        )
        if s <= now < e:
            entry["busy_now"] = True
            cur_free = entry.get("next_free")
            if not cur_free or e > _parse_iso(cur_free):
                entry["next_free"] = e.isoformat()
        elif s > now:
            cur_busy = entry.get("next_busy")
            if not cur_busy or s < _parse_iso(cur_busy):
                entry["next_busy"] = s.isoformat()

    bookings_by_res: dict = {}
    for b in bookings:
        rid = b["resource_id"]
        s = b.get("start_at")
        e = b.get("end_at")
        if not (isinstance(s, datetime) and isinstance(e, datetime)):
            continue
        if s.tzinfo is None:
            s = s.replace(tzinfo=timezone.utc)
        if e.tzinfo is None:
            e = e.replace(tzinfo=timezone.utc)
        _apply(rid, s, e)
        parent_id = child_to_parent.get(rid)
        if parent_id:
            _apply(parent_id, s, e)

        if with_bookings:
            # Privacy-safe entry: only times + status, no user info.
            slim = {
                "booking_id": b.get("booking_id"),
                "resource_id": rid,
                "start_at": s.isoformat(),
                "end_at": e.isoformat(),
                "status": b.get("status"),
            }
            bookings_by_res.setdefault(rid, []).append(slim)
            # Parent gets a "phantom" booking entry so the slot-picker on
            # the parent shows the same blocked hours as the sub-rooms.
            if parent_id:
                bookings_by_res.setdefault(parent_id, []).append({
                    **slim, "resource_id": parent_id,
                })

    return by_res, bookings_by_res


@router.get("/resource-availability")
async def resource_availability(
    resource_ids: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Iter 356 — Hybrid endpoint: snapshot + slot-picker bookings in one
    request. ``resource_ids`` is an optional comma-separated allow-list. If
    omitted, the snapshot is computed for ALL resources (no bookings list).

    Replaces the N+1 round-trips that the resources page used to make
    (1× /resource-availability-snapshot + N× /resource-bookings?availability
    _only=true) and makes status drift between the badge and the slot grid
    physically impossible — both pieces derive from a single Mongo read.
    """
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    ids = None
    if resource_ids:
        ids = [r.strip() for r in resource_ids.split(",") if r.strip()]
    by_res, bookings_by_res = await _compute_availability(
        resource_ids=ids, with_bookings=bool(ids),
    )
    return {"snapshot": by_res, "bookings_by_resource": bookings_by_res}


# ---------------------------------------------------------------------------
# Multi-resource occupancy timeline (Gantt) + in-office widget
# ---------------------------------------------------------------------------

@router.get("/resource-occupancy")
async def resource_occupancy(
    from_date: str,
    to_date: str,
    type: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Liefert eine Multi-Resource-Belegungs-Uebersicht (Gantt-Style).
    Antwort: {resources: [...], bookings: [...]}  — Frontend rendert daraus
    eine Timeline mit einer Zeile pro Ressource."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    start = _parse_iso(from_date)
    end = _parse_iso(to_date)
    if (end - start).days > 60:
        raise HTTPException(400, "Zeitfenster zu gross (max. 60 Tage)")
    q: dict = {}
    if type in ("room", "desk", "vehicle"):
        q["type"] = type
    # Inkludiere Sub-Resources (sie haben parent_resource_id) — fuer teilbare
    # Raeume zeigen wir Parent + Subs separat.
    resources = await db.resources.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    rids = [r["resource_id"] for r in resources]
    bookings = await db.resource_bookings.find({
        "resource_id": {"$in": rids},
        "status": {"$in": ["confirmed", "pending_approval"]},
        "start_at": {"$lt": end},
        "end_at": {"$gt": start},
    }, {
        "_id": 0, "booking_id": 1, "resource_id": 1, "title": 1,
        "start_at": 1, "end_at": 1, "status": 1, "user_id": 1,
        # Iter 324 — expose catering link so the Belegung timeline can
        # render a small "Catering" badge on the booking bar.
        "catering_request_id": 1,
    }).to_list(5000)
    blackouts = await db.blackout_periods.find({
        "resource_id": {"$in": rids},
        "start_at": {"$lt": end},
        "end_at": {"$gt": start},
    }, {"_id": 0}).to_list(1000)
    # Iter 324 — fetch catering statuses in one batch so the UI knows
    # whether the booking has *active* catering (vs. cancelled / rejected).
    cr_ids = [b.get("catering_request_id") for b in bookings if b.get("catering_request_id")]
    cr_status: dict = {}
    if cr_ids:
        async for c in db.catering_requests.find(
            {"request_id": {"$in": cr_ids}},
            {"_id": 0, "request_id": 1, "status": 1, "items": 1},
        ):
            cr_status[c["request_id"]] = {
                "status": c.get("status"),
                "item_count": len(c.get("items") or []),
            }
    # Iter 237 — Privacy-Filter: User ohne 'resources.view_all_bookings' duerfen
    # nur die Titel der EIGENEN Buchungen sehen. Fremd-Buchungen werden auf
    # generisches "Belegt" maskiert — Zeitslots bleiben sichtbar.
    can_view_all = await has_cap(user, "resources.view_all_bookings", db)
    uid = user["user_id"]
    for b in bookings + blackouts:
        for k in ("start_at", "end_at"):
            if isinstance(b.get(k), datetime):
                b[k] = b[k].isoformat()
    if not can_view_all:
        for bk in bookings:
            if bk.get("user_id") != uid:
                bk["title"] = "Belegt"
                bk["user_id"] = None  # do not leak user ids either
                # Iter 324 — strip catering details for foreign bookings to
                # avoid leaking what other teams ordered.
                bk.pop("catering_request_id", None)
    # Attach catering status to the bookings dict last (post-privacy).
    for bk in bookings:
        cri = bk.get("catering_request_id")
        if cri and cri in cr_status:
            bk["catering_status"] = cr_status[cri]["status"]
            bk["catering_item_count"] = cr_status[cri]["item_count"]
    # Iter 339 — Issue #4: hover-tooltip braucht den Buchungs-Inhaber im
    # Klartext. user_id ist bereits oben gefiltert (None bei fremden Bookings),
    # also ist nur ein Lookup für Eigene + (mit view_all) fremde User nötig.
    uids_to_hydrate = list({b.get("user_id") for b in bookings if b.get("user_id")})
    if uids_to_hydrate:
        users = await db.users.find(
            {"user_id": {"$in": uids_to_hydrate}},
            {"_id": 0, "user_id": 1, "name": 1},
        ).to_list(len(uids_to_hydrate))
        umap = {u["user_id"]: u.get("name") for u in users}
        for bk in bookings:
            if bk.get("user_id") and bk["user_id"] in umap:
                bk["user_name"] = umap[bk["user_id"]]
    return {
        "from_date": from_date,
        "to_date": to_date,
        "resources": resources,
        "bookings": bookings,
        "blackouts": blackouts,
    }


@router.get("/resources-in-office")
async def in_office_today(user=Depends(get_current_user)):
    """Iter 238 — Hybrid-Work-Widget: Wer ist heute im Buero?

    Aggregiert aktive Desk-Buchungen fuer den heutigen Tag und liefert eine
    Liste von Kollegen mit Avatar, Name, Desk-Nr, Stockwerk/Gebaeude und
    Zeitfenster. Respektiert Privacy-Opt-Out via `users.hide_from_office_widget`.
    """
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # 1. Today's desk bookings (confirmed only)
    bookings = await db.resource_bookings.find({
        "status": "confirmed",
        "start_at": {"$lt": day_end},
        "end_at": {"$gt": day_start},
    }, {
        "_id": 0, "booking_id": 1, "resource_id": 1, "user_id": 1,
        "start_at": 1, "end_at": 1,
    }).to_list(2000)
    if not bookings:
        return {"date": day_start.date().isoformat(), "people": [], "total": 0, "active_now": 0}

    # 2. Filter to desk resources only
    rids = list({b["resource_id"] for b in bookings})
    desks = await db.resources.find(
        {"resource_id": {"$in": rids}, "type": "desk"},
        {"_id": 0, "resource_id": 1, "desk_number": 1, "name": 1,
         "building": 1, "floor": 1, "floor_plan_id": 1},
    ).to_list(2000)
    desk_map = {d["resource_id"]: d for d in desks}
    desk_bookings = [b for b in bookings if b["resource_id"] in desk_map]

    if not desk_bookings:
        return {"date": day_start.date().isoformat(), "people": [], "total": 0, "active_now": 0}

    # 3. Fetch user profiles (respect opt-out)
    uids = list({b["user_id"] for b in desk_bookings if b.get("user_id")})
    users_docs = await db.users.find(
        {"user_id": {"$in": uids}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar": 1,
         "department": 1, "hide_from_office_widget": 1},
    ).to_list(2000)
    user_map = {u["user_id"]: u for u in users_docs}

    # 4. Build people list (dedup: a user may have multiple desk bookings today;
    #    pick the earliest active or upcoming one)
    by_user: dict = {}
    for b in desk_bookings:
        uid = b.get("user_id")
        if not uid:
            continue
        u = user_map.get(uid)
        if not u or u.get("hide_from_office_widget"):
            continue
        existing = by_user.get(uid)
        if existing and existing["start_at"] <= b["start_at"]:
            continue  # keep the earlier one
        by_user[uid] = b

    people = []
    for uid, b in by_user.items():
        u = user_map[uid]
        d = desk_map[b["resource_id"]]
        start = b["start_at"]
        end = b["end_at"]
        # Normalise tz: MongoDB BSON datetimes are UTC but tz-naive.
        if isinstance(start, datetime) and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if isinstance(end, datetime) and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        is_active_now = start <= now <= end
        people.append({
            "user_id": uid,
            "name": u.get("name") or u.get("email", "").split("@")[0],
            "email": u.get("email"),
            "avatar_url": u.get("avatar") or None,
            "department": u.get("department"),
            "desk_number": d.get("desk_number") or d.get("name"),
            "building": d.get("building"),
            "floor": d.get("floor"),
            "floor_plan_id": d.get("floor_plan_id"),
            "start_at": start.isoformat() if isinstance(start, datetime) else start,
            "end_at": end.isoformat() if isinstance(end, datetime) else end,
            "is_active_now": is_active_now,
        })
    # Sort: active-now first, then by start time
    people.sort(key=lambda p: (not p["is_active_now"], p["start_at"]))

    return {
        "date": day_start.date().isoformat(),
        "people": people,
        "total": len(people),
        "active_now": sum(1 for p in people if p["is_active_now"]),
    }


# ---------------------------------------------------------------------------
# No-show / per-department analytics
# ---------------------------------------------------------------------------

@router.get("/resources/dashboard/no-show")
async def no_show_analytics(days: int = 90, user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    window_start = datetime.now(timezone.utc) - timedelta(days=days)
    total = await db.resource_bookings.count_documents({"start_at": {"$gte": window_start}})
    no_show = await db.resource_bookings.count_documents({
        "start_at": {"$gte": window_start}, "status": "no_show",
    })
    cancelled = await db.resource_bookings.count_documents({
        "start_at": {"$gte": window_start}, "status": "cancelled",
    })
    return {
        "window_days": days,
        "total_bookings": total,
        "no_show_count": no_show,
        "no_show_rate": round(no_show / total, 3) if total else 0,
        "cancelled_count": cancelled,
        "cancellation_rate": round(cancelled / total, 3) if total else 0,
    }


@router.get("/resources/dashboard/by-department")
async def bookings_by_department(days: int = 90, user=Depends(get_current_user)):
    """Per-cost-center booking stats (department proxy via cost_center)."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    window_start = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"start_at": {"$gte": window_start},
                    "cost_center": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$cost_center", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    rows = []
    async for r in db.resource_bookings.aggregate(pipeline):
        rows.append({"cost_center": r["_id"], "count": r["count"]})
    return {"window_days": days, "rows": rows}


# ---------------------------------------------------------------------------
# Vehicle driving log + deprecated driver-license endpoints
# ---------------------------------------------------------------------------

@router.get("/resources/{vehicle_id}/driving-log")
async def driving_log(vehicle_id: str, user=Depends(get_current_user)):
    """Fahrtenbuch: all completed vehicle bookings for analysis."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    bookings = await db.resource_bookings.find({
        "resource_id": vehicle_id,
        "status": {"$in": ["confirmed", "completed"]},
    }, {"_id": 0}).sort("start_at", -1).to_list(500)
    for b in bookings:
        for k in ("start_at", "end_at", "checked_in_at", "checked_out_at"):
            if isinstance(b.get(k), datetime):
                b[k] = b[k].isoformat()
    return bookings


@router.get("/users/{user_id}/driver-license", deprecated=True)
async def get_driver_license_deprecated(user_id: str, actor=Depends(get_current_user)):
    """Deprecated since Iter 292 — read via /users/{user_id}/drivers-licenses
    (plural). Kept temporarily so any external caller gets a 410 Gone instead
    of a silent 404."""
    raise HTTPException(
        410,
        "Endpoint entfernt. Bitte /api/users/{user_id}/drivers-licenses (plural) verwenden."
    )


@router.put("/users/{user_id}/driver-license", deprecated=True)
async def set_driver_license_deprecated(user_id: str, payload: dict, actor=Depends(get_current_user)):
    raise HTTPException(
        410,
        "Endpoint entfernt. Bitte /api/users/me/drivers-licenses (plural) verwenden."
    )


# ---------------------------------------------------------------------------
# Outlook OAuth stub
# ---------------------------------------------------------------------------

@router.get("/calendar-sync/outlook/auth-url")
async def outlook_auth_url(user=Depends(get_current_user)):
    """Returns the URL the user should visit to authorise Outlook sync.
    Configured via OUTLOOK_CLIENT_ID + OUTLOOK_TENANT env vars.
    Returns 503 if not configured (admin must set up the app in Azure first)."""
    client_id = os.environ.get("OUTLOOK_CLIENT_ID")
    tenant = os.environ.get("OUTLOOK_TENANT", "common")
    redirect = os.environ.get("OUTLOOK_REDIRECT_URI")
    if not client_id or not redirect:
        raise HTTPException(503, "Outlook-Sync nicht konfiguriert. Admin muss "
                                 "OUTLOOK_CLIENT_ID + OUTLOOK_REDIRECT_URI setzen.")
    import urllib.parse as _u
    params = _u.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": "openid Calendars.ReadWrite offline_access",
        "state": user["user_id"],
    })
    return {
        "url": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{params}",
    }


# ---------------------------------------------------------------------------
# Resource upload config (org-wide setting)
# ---------------------------------------------------------------------------

@router.get("/resource-upload-config")
async def get_resource_upload_config(user=Depends(get_current_user)):
    """Beliebige eingeloggte User koennen die aktive Konfiguration lesen
    (z.B. um vor dem Upload bereits eine clientseitige Warnung anzuzeigen)."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    return await _get_upload_config()


@router.put("/resource-upload-config")
async def set_resource_upload_config(payload: dict, user=Depends(get_current_user)):
    """Admin/resources.manage darf die globalen Upload-Limits ändern."""
    await require_cap(user, "resources.manage", db)
    raw_mb = payload.get("max_size_mb")
    max_mb = DEFAULT_UPLOAD_MAX_MB if raw_mb is None else int(raw_mb)
    if max_mb < 1 or max_mb > 100:
        raise HTTPException(400, "max_size_mb muss zwischen 1 und 100 liegen")
    mimes = payload.get("allowed_mimes")
    if mimes is not None and not isinstance(mimes, list):
        raise HTTPException(400, "allowed_mimes muss eine Liste sein")
    update = {
        "max_size_mb": max_mb,
        "allowed_mimes": [str(m).lower() for m in (mimes or DEFAULT_UPLOAD_MIMES)],
        "updated_at": datetime.now(timezone.utc),
        "updated_by": user["user_id"],
    }
    await db.app_settings.update_one(
        {"key": "resource_uploads"},
        {"$set": update, "$setOnInsert": {"key": "resource_uploads"}},
        upsert=True,
    )
    return await _get_upload_config()
