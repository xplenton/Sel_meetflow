"""
Resources/admin · Floorplans + Blackouts.

Floorplan metadata CRUD, the generic "items on this plan" reader,
blackout periods, and the per-sub-area utilization aggregator (which is
specific to splitable rooms and shares the floorplan/sub_id mental model).
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid

from database import db
from dependencies import get_current_user
from services.permissions import require_cap, has_cap

from .._common import _parse_iso

router = APIRouter()


# ---------------------------------------------------------------------------
# Floorplan metadata CRUD
# ---------------------------------------------------------------------------

@router.get("/floorplans")
async def list_floorplans(user=Depends(get_current_user)):
    """Listet alle Lageplaene mit ihren Metadaten (Name, Backdrop-URL)."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    plans = await db.floorplans.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return plans


@router.get("/floorplans/{floor_plan_id}")
async def get_floorplan(floor_plan_id: str, user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    plan = await db.floorplans.find_one(
        {"floor_plan_id": floor_plan_id}, {"_id": 0})
    if not plan:
        # Fallback: leeres Dummy-Objekt, damit das UI nicht 404'd
        return {"floor_plan_id": floor_plan_id, "name": floor_plan_id,
                "background_attachment_id": None, "background_url": None}
    return plan


@router.put("/floorplans/{floor_plan_id}")
async def upsert_floorplan(
    floor_plan_id: str, payload: dict, user=Depends(get_current_user),
):
    """Setzt Name / Backdrop-Image fuer einen Lageplan.
    payload: {name?, background_attachment_id?, building?, floor?}
    `background_attachment_id` muss eine valide att_*-ID sein (vorher hochgeladen)."""
    await require_cap(user, "resources.manage", db)
    update = {"updated_at": datetime.now(timezone.utc),
              "updated_by": user["user_id"]}
    if "name" in payload:
        update["name"] = str(payload["name"])[:120]
    if "building" in payload:
        update["building"] = payload["building"]
    if "floor" in payload:
        update["floor"] = payload["floor"]
    if "background_attachment_id" in payload:
        att_id = payload["background_attachment_id"]
        if att_id:
            # Bild-MIME pruefen (statt der allgemeinen Liste)
            meta = await db.attachments.files.find_one(
                {"_id": att_id}, {"metadata": 1})
            if not meta:
                raise HTTPException(404, f"Anhang {att_id} nicht gefunden")
            mime = ((meta.get("metadata") or {}).get("mime") or "").lower()
            if not mime.startswith("image/"):
                raise HTTPException(415, f"Hintergrund muss ein Bild sein (war {mime})")
            update["background_attachment_id"] = att_id
            update["background_url"] = f"/api/attachments/{att_id}"
        else:
            update["background_attachment_id"] = None
            update["background_url"] = None
    await db.floorplans.update_one(
        {"floor_plan_id": floor_plan_id},
        {"$set": update,
         "$setOnInsert": {"floor_plan_id": floor_plan_id,
                          "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    plan = await db.floorplans.find_one(
        {"floor_plan_id": floor_plan_id}, {"_id": 0})
    return plan


@router.delete("/floorplans/{floor_plan_id}")
async def delete_floorplan(floor_plan_id: str, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    # Achtung: nur Metadaten loeschen, Desk-Positionen bleiben am Resource erhalten
    result = await db.floorplans.delete_one({"floor_plan_id": floor_plan_id})
    return {"deleted": result.deleted_count}


# ---------------------------------------------------------------------------
# Floorplan items (desks + generic) — share helper
# ---------------------------------------------------------------------------

async def _floorplan_items(floor_plan_id: str, rtype: Optional[str], at_iso: Optional[str], user):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    when = _parse_iso(at_iso) if at_iso else datetime.now(timezone.utc)
    q: dict = {"floor_plan_id": floor_plan_id}
    if rtype in ("room", "desk", "vehicle"):
        q["type"] = rtype
    items = await db.resources.find(q, {"_id": 0}).to_list(500)
    # Check current bookings for each item in a 15-min window around `when`.
    win_start = when
    win_end = when + timedelta(minutes=15)
    item_ids = [d["resource_id"] for d in items]
    busy = set()
    async for bk in db.resource_bookings.find({
        "resource_id": {"$in": item_ids},
        "status": {"$in": ["confirmed", "pending_approval"]},
        "start_at": {"$lt": win_end},
        "end_at": {"$gt": win_start},
    }, {"_id": 0, "resource_id": 1}):
        busy.add(bk["resource_id"])
    for d in items:
        d["is_busy"] = d["resource_id"] in busy
    # Keep legacy field name `desks` when only desks were requested for
    # backwards compatibility with existing frontend code.
    return {
        "floor_plan_id": floor_plan_id,
        "at": when.isoformat(),
        "desks": items if rtype == "desk" else [d for d in items if d.get("type") == "desk"],
        "items": items,
    }


@router.get("/floorplans/{floor_plan_id}/desks")
async def floorplan_desks(
    floor_plan_id: str,
    at: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Return all desks placed on a given floor-plan plus their current
    availability at the given timestamp (default: now).
    """
    return await _floorplan_items(floor_plan_id, "desk", at, user)


@router.get("/floorplans/{floor_plan_id}/items")
async def floorplan_items(
    floor_plan_id: str,
    type: Optional[str] = None,
    at: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Iter 240 — Generic: liefert alle platzierten Ressourcen (room/desk/vehicle)
    fuer einen Lageplan. type=None liefert alle Typen.
    """
    return await _floorplan_items(floor_plan_id, type, at, user)


# ---------------------------------------------------------------------------
# Blackout periods
# ---------------------------------------------------------------------------

@router.get("/resources/{resource_id}/blackouts")
async def list_blackouts(resource_id: str, user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    items = await db.blackout_periods.find({"resource_id": resource_id}, {"_id": 0}).sort("start_at", 1).to_list(100)
    for it in items:
        for k in ("start_at", "end_at"):
            if isinstance(it.get(k), datetime):
                it[k] = it[k].isoformat()
    return items


@router.post("/resources/{resource_id}/blackouts")
async def create_blackout(resource_id: str, payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    start = _parse_iso(payload["start_at"])
    end = _parse_iso(payload["end_at"])
    if end <= start:
        raise HTTPException(400, "Endzeit muss nach Startzeit liegen")
    doc = {
        "blackout_id": f"bo_{uuid.uuid4().hex[:10]}",
        "resource_id": resource_id,
        "title": payload.get("title", "Sperrzeit"),
        "reason": payload.get("reason", "maintenance"),
        "start_at": start, "end_at": end,
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc),
    }
    await db.blackout_periods.insert_one(doc)
    doc.pop("_id", None)
    for k in ("start_at", "end_at", "created_at"):
        doc[k] = doc[k].isoformat()
    return doc


@router.delete("/resources/blackouts/{blackout_id}")
async def delete_blackout(blackout_id: str, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    await db.blackout_periods.delete_one({"blackout_id": blackout_id})
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Utilization per sub-area (splitable rooms)
# ---------------------------------------------------------------------------

@router.get("/resources/{resource_id}/utilization-by-sub")
async def utilization_by_sub(
    resource_id: str, days: int = 30, user=Depends(get_current_user),
):
    """Auslastung eines teilbaren Raumes aufgeschluesselt nach Teilbereich
    (A/B/C jeweils separat + Kombi-Buchungen, die mehrere Subs umspannen).
    Liefert pro sub_id: bookings, total_minutes, utilization_pct (vom Fenster)."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    parent = await db.resources.find_one(
        {"resource_id": resource_id}, {"_id": 0})
    if not parent:
        raise HTTPException(404, "Ressource nicht gefunden")
    if not parent.get("is_splitable"):
        raise HTTPException(400, "Nur teilbare Raeume haben Teilbereiche")

    window_start = datetime.now(timezone.utc) - timedelta(days=days)
    window_minutes = days * 24 * 60

    # Alle Kinder samt sub_id einlesen
    children = await db.resources.find(
        {"parent_resource_id": resource_id}, {"_id": 0}).to_list(20)
    sub_index: dict = {}  # child_id -> sub_id
    sub_names: dict = {}
    for c in children:
        if c.get("sub_id"):
            sub_index[c["resource_id"]] = c["sub_id"]
            sub_names[c["sub_id"]] = c.get("name", c["sub_id"])

    # Buchungen lesen (sowohl auf Parent als auch Kindern)
    resource_ids = [resource_id] + list(sub_index.keys())
    bookings = await db.resource_bookings.find({
        "resource_id": {"$in": resource_ids},
        "status": {"$in": ["confirmed", "completed"]},
        "start_at": {"$gte": window_start},
    }, {"_id": 0, "resource_id": 1, "start_at": 1, "end_at": 1,
        "combo_group_id": 1}).to_list(2000)

    per_sub: dict = {sid: {"sub_id": sid, "name": sub_names.get(sid, sid),
                           "bookings": 0, "total_minutes": 0}
                     for sid in sub_names.keys()}
    combo_bookings_total = 0
    combo_minutes_total = 0
    for b in bookings:
        s = b.get("start_at")
        e = b.get("end_at")
        if not (isinstance(s, datetime) and isinstance(e, datetime)):
            continue
        mins = max(0, int((e - s).total_seconds() // 60))
        if b["resource_id"] == resource_id:
            # Buchung auf dem Parent (klassische Gesamtraum-Buchung)
            combo_bookings_total += 1
            combo_minutes_total += mins
            # Verteile auf alle Subs (Gesamtraum belegt jeden Sub)
            for sid in per_sub:
                per_sub[sid]["bookings"] += 1
                per_sub[sid]["total_minutes"] += mins
            continue
        sid = sub_index.get(b["resource_id"])
        if not sid:
            continue
        per_sub[sid]["bookings"] += 1
        per_sub[sid]["total_minutes"] += mins

    rows = []
    for sid, row in per_sub.items():
        row["utilization_pct"] = (
            round(row["total_minutes"] / window_minutes * 100, 1)
            if window_minutes else 0.0
        )
        rows.append(row)
    rows.sort(key=lambda r: r["sub_id"])
    return {
        "resource_id": resource_id,
        "name": parent.get("name"),
        "window_days": days,
        "sub_rows": rows,
        "combo_or_full_room_bookings": combo_bookings_total,
        "combo_or_full_room_minutes": combo_minutes_total,
    }
