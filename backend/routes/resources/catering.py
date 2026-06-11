"""
Resources package — sub-module catering.
Split out from the original monolithic routes/resources.py in iter 234.
Helpers, models and `db` live in `_common`.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user
from services.permissions import require_cap, has_cap

# Shared helpers + models + type aliases from _common
from ._common import (
    CateringStatus,
    CATERING_REJECTION_REASONS,
    CateringItem, _audit_booking,
    _parse_iso, _notify_catering_status, _validate_attachment,
)

router = APIRouter(tags=["resources-catering"])


# ============================================================================
# Iter 246 — Catering Storno-Frist mit Gebühr
# ============================================================================
DEFAULT_CANCEL_CFG = {
    "cancellation_deadline_hours": 24,
    "late_fee_percent": 50,
    "very_late_threshold_hours": 4,
    "very_late_fee_percent": 100,
    # Iter 322c — Global default lead time for catering items (admin-tunable).
    # Used when an item has no `lead_time_min` set + for breach detection
    # when the booking is placed too close to start_at. 0 disables warnings.
    "default_lead_time_min": 60,
}


async def _get_cancel_cfg() -> dict:
    doc = await db.catering_config.find_one({"_id": "default"}, {"_id": 0}) or {}
    return {**DEFAULT_CANCEL_CFG, **doc}


def _compute_cancel_fee(cr: dict, cancel_cfg: dict, now: Optional[datetime] = None) -> dict:
    """Berechnet Storno-Gebühr basierend auf 'hours_until_event'.

    Returns:
        {fee_percent, fee_amount, hours_until_event, tier, deadline_passed, total}
    """
    now = now or datetime.now(timezone.utc)
    event_start = cr.get("delivery_at") or cr.get("event_start_at")
    if isinstance(event_start, str):
        try:
            event_start = _parse_iso(event_start)
        except Exception:
            event_start = None
    if isinstance(event_start, datetime) and event_start.tzinfo is None:
        event_start = event_start.replace(tzinfo=timezone.utc)
    hours_until = ((event_start - now).total_seconds() / 3600) if event_start else 9999.0
    total = float(cr.get("total_amount") or cr.get("total") or 0.0)
    if hours_until >= cancel_cfg["cancellation_deadline_hours"]:
        fee_pct, tier = 0, "free"
    elif hours_until < cancel_cfg["very_late_threshold_hours"]:
        fee_pct, tier = cancel_cfg["very_late_fee_percent"], "very_late"
    else:
        fee_pct, tier = cancel_cfg["late_fee_percent"], "late"
    fee_amount = round(total * fee_pct / 100, 2)
    return {
        "fee_percent": fee_pct,
        "fee_amount": fee_amount,
        "hours_until_event": round(hours_until, 1),
        "tier": tier,
        "deadline_passed": fee_pct > 0,
        "total": total,
    }


@router.get("/catering-config")
async def get_catering_config(user=Depends(get_current_user)):
    """Storno-Frist + Gebuehren-Config (Admin lesbar)."""
    if not (await has_cap(user, "catering.process", db)
            or await has_cap(user, "resources.manage", db)):
        raise HTTPException(403, "Kein Zugriff")
    return await _get_cancel_cfg()


@router.put("/catering-config")
async def set_catering_config(payload: dict, user=Depends(get_current_user)):
    """Storno-Frist + Gebühren-Config + globaler Catering-Vorlauf (Admin/resources.manage)."""
    if not await has_cap(user, "resources.manage", db):
        raise HTTPException(403, "Verwaltungsrechte erforderlich")
    clean = {}
    for k in DEFAULT_CANCEL_CFG.keys():
        v = payload.get(k)
        if v is None:
            continue
        try:
            v = float(v) if "percent" in k else int(v)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Ungültiger Wert für {k}")
        if "percent" in k and not (0 <= v <= 100):
            raise HTTPException(400, f"{k} muss zwischen 0 und 100 liegen")
        if "hours" in k and v < 0:
            raise HTTPException(400, f"{k} muss >= 0 sein")
        # Iter 322c — Bounds for the global lead-time default: 0 (none) up to
        # 14 days. Larger values are almost certainly typos.
        if k == "default_lead_time_min" and not (0 <= v <= 60 * 24 * 14):
            raise HTTPException(400, "default_lead_time_min muss zwischen 0 und 20160 Min. (14 Tage) liegen")
        clean[k] = v
    if not clean:
        raise HTTPException(400, "Keine gültigen Felder")
    await db.catering_config.update_one(
        {"_id": "default"}, {"$set": clean}, upsert=True,
    )
    return await _get_cancel_cfg()


@router.get("/catering-requests/{request_id}/cancel-preview")
async def cancel_preview(request_id: str, user=Depends(get_current_user)):
    """Vorschau der Storno-Gebühr — wird vor Klick auf Stornieren angezeigt."""
    cr = await db.catering_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not cr:
        raise HTTPException(404, "Anfrage nicht gefunden")
    is_owner = cr.get("user_id") == user["user_id"]
    can_process = await has_cap(user, "catering.process", db)
    if not (is_owner or can_process):
        raise HTTPException(403, "Kein Zugriff")
    if cr.get("status") in ("completed", "cancelled"):
        return {"already_finalized": True, "status": cr["status"]}
    cfg = await _get_cancel_cfg()
    fee = _compute_cancel_fee(cr, cfg)
    return {"already_finalized": False, **fee, "cancel_cfg": cfg}


@router.get("/catering-items")
async def list_catering_items(user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    items = await db.catering_items.find({"status": "active"}, {"_id": 0}).sort("name", 1).to_list(200)
    return items


@router.post("/catering-items")
async def create_catering_item(payload: CateringItem, user=Depends(get_current_user)):
    await require_cap(user, "catering.manage_items", db)
    doc = payload.model_dump()
    await db.catering_items.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/catering-items/{item_id}")
async def update_catering_item(item_id: str, payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "catering.manage_items", db)
    payload.pop("_id", None)
    payload.pop("item_id", None)
    res = await db.catering_items.find_one_and_update(
        {"item_id": item_id}, {"$set": payload},
        return_document=True, projection={"_id": 0},
    )
    if not res:
        raise HTTPException(404, "Artikel nicht gefunden")
    return res


@router.delete("/catering-items/{item_id}")
async def delete_catering_item(item_id: str, user=Depends(get_current_user)):
    await require_cap(user, "catering.manage_items", db)
    await db.catering_items.update_one({"item_id": item_id}, {"$set": {"status": "inactive"}})
    return {"deactivated": True}


@router.get("/catering-requests")
async def list_catering_requests(
    status: Optional[CateringStatus] = None,
    user=Depends(get_current_user),
):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    q: dict = {}
    if status:
        q["status"] = status
    # If not catering staff, only see your own requests
    if not await has_cap(user, "catering.process", db):
        q["user_id"] = user["user_id"]
    items = await db.catering_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)

    # Iter 286 — hydrate item names, requester names, booking title/resource/time
    # so the UI shows real labels instead of opaque IDs.
    if items:
        item_ids = list({ln.get("item_id") for cr in items for ln in (cr.get("items") or []) if ln.get("item_id")})
        booking_ids = list({cr.get("booking_id") for cr in items if cr.get("booking_id")})
        user_ids = list({cr.get("user_id") for cr in items if cr.get("user_id")})

        items_idx = {}
        if item_ids:
            for it in await db.catering_items.find({"item_id": {"$in": item_ids}}, {"_id": 0, "item_id": 1, "name": 1, "unit": 1}).to_list(500):
                items_idx[it["item_id"]] = it

        bookings_idx = {}
        if booking_ids:
            for b in await db.resource_bookings.find({"booking_id": {"$in": booking_ids}}, {"_id": 0, "booking_id": 1, "title": 1, "resource_id": 1, "start_at": 1, "end_at": 1, "status": 1}).to_list(500):
                if isinstance(b.get("start_at"), datetime):
                    b["start_at"] = b["start_at"].isoformat()
                if isinstance(b.get("end_at"), datetime):
                    b["end_at"] = b["end_at"].isoformat()
                bookings_idx[b["booking_id"]] = b

        resource_ids = list({b.get("resource_id") for b in bookings_idx.values() if b.get("resource_id")})
        resources_idx = {}
        if resource_ids:
            # Iter 343 — Issue #1: also load parent + sub-room context so the
            # catering inbox can render "Großer Saal — Bereich A" instead of
            # only the parent name (which was misleading for sub-rooms).
            # Iter 366 — Auch `requires_approval` mitliefern, damit das
            # Frontend den „Freigeben"-Button für freigabepflichtige Räume
            # gating-en kann, solange die Buchung nicht bestätigt ist.
            for r in await db.resources.find(
                {"resource_id": {"$in": resource_ids}},
                {"_id": 0, "resource_id": 1, "name": 1, "type": 1,
                 "license_plate": 1, "building": 1, "floor": 1,
                 "desk_number": 1, "location": 1, "parking_location": 1,
                 "parent_resource_id": 1, "sub_id": 1, "is_splitable": 1,
                 "requires_approval": 1},
            ).to_list(500):
                resources_idx[r["resource_id"]] = r
        parent_ids = {r.get("parent_resource_id") for r in resources_idx.values() if r.get("parent_resource_id")}
        parent_name_map = {}
        if parent_ids:
            async for pr in db.resources.find(
                {"resource_id": {"$in": list(parent_ids)}},
                {"_id": 0, "resource_id": 1, "name": 1},
            ):
                parent_name_map[pr["resource_id"]] = pr.get("name")

        users_idx = {}
        if user_ids:
            for u in await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(500):
                users_idx[u["user_id"]] = u

        for cr in items:
            for ln in (cr.get("items") or []):
                meta = items_idx.get(ln.get("item_id"))
                if meta:
                    ln["item_name"] = meta.get("name")
                    ln["item_unit"] = meta.get("unit")
            bk = bookings_idx.get(cr.get("booking_id")) if cr.get("booking_id") else None
            if bk:
                res = resources_idx.get(bk.get("resource_id")) or {}
                bk_out = {
                    "booking_id": bk.get("booking_id"),
                    "title": bk.get("title"),
                    "start_at": bk.get("start_at"),
                    "end_at": bk.get("end_at"),
                    "status": bk.get("status"),  # Iter 366 — gating in inbox
                    "resource_id": bk.get("resource_id"),
                    "resource_name": res.get("name"),
                    "resource_type": res.get("type"),
                    "resource_building": res.get("building"),
                    "resource_floor": res.get("floor"),
                    "resource_license_plate": res.get("license_plate"),
                    "resource_location": res.get("location"),
                    "resource_requires_approval": bool(res.get("requires_approval")),
                }
                # Iter 343 — Sub-Raum-Kontext für Catering-Inbox.
                if res.get("parent_resource_id"):
                    bk_out["resource_sub_id"] = res.get("sub_id")
                    bk_out["resource_parent_id"] = res.get("parent_resource_id")
                    bk_out["resource_parent_name"] = parent_name_map.get(res["parent_resource_id"])
                cr["booking"] = bk_out
            req = users_idx.get(cr.get("user_id"))
            if req:
                cr["requester"] = {
                    "user_id": req.get("user_id"),
                    "name": req.get("name"),
                    "email": req.get("email"),
                }
    return items


@router.post("/catering-requests/{request_id}/transition")
async def transition_catering(request_id: str, payload: dict, user=Depends(get_current_user)):
    """Status transition: confirmed/rejected/in_progress/delivered/completed/cancelled.

    Iter 244 — Storno ('cancelled') ist auch durch den Anforderer (User) erlaubt
    solange noch nicht 'completed'. Alle anderen Transitions erfordern
    `catering.process`.
    """
    new_status = payload.get("status")
    if new_status not in ("confirmed", "rejected", "in_progress", "delivered", "completed", "cancelled"):
        raise HTTPException(400, "Ungültiger Status")

    # Cancel-Flow: Anforderer (Owner) darf solange stornieren, bis CR nicht
    # bereits abgeschlossen ist. Catering-Team darf jederzeit.
    existing = await db.catering_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Anfrage nicht gefunden")
    is_owner = existing.get("user_id") == user["user_id"]
    can_process = await has_cap(user, "catering.process", db)

    if new_status == "cancelled":
        if not (is_owner or can_process):
            raise HTTPException(403, "Nur Anforderer oder Catering-Team kann stornieren")
        if existing.get("status") in ("completed", "cancelled"):
            raise HTTPException(409, f"Anfrage ist bereits {existing['status']}")
    else:
        if not can_process:
            raise HTTPException(403, "Catering-Team-Berechtigung erforderlich")
        # Iter 366 — Catering darf erst freigegeben werden, wenn die zugehörige
        # Buchung (sofern freigabepflichtig) ebenfalls freigegeben ist.
        # Schützt vor „Catering bestätigt, Raum aber noch nicht genehmigt"-
        # Inkonsistenzen.
        if new_status == "confirmed" and existing.get("booking_id"):
            bk = await db.resource_bookings.find_one(
                {"booking_id": existing["booking_id"]},
                {"_id": 0, "status": 1, "resource_id": 1, "title": 1},
            )
            if bk:
                res = await db.resources.find_one(
                    {"resource_id": bk.get("resource_id")},
                    {"_id": 0, "requires_approval": 1, "name": 1},
                )
                if res and res.get("requires_approval") and bk.get("status") != "confirmed":
                    raise HTTPException(
                        409,
                        "Buchung muss erst freigegeben werden, bevor das Catering bestätigt werden kann.",
                    )

    update = {
        "status": new_status,
        "processed_by": user["user_id"],
        "processed_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    if new_status == "rejected":
        update["rejection_reason"] = payload.get("reason", "")
    if new_status == "cancelled":
        update["cancellation_reason"] = payload.get("reason", "")
        # Iter 246 — Storno-Gebuehr persistieren (Snapshot zum Zeitpunkt der Stornierung)
        cfg = await _get_cancel_cfg()
        fee = _compute_cancel_fee(existing, cfg)
        update["cancellation_fee_percent"] = fee["fee_percent"]
        update["cancellation_fee_amount"] = fee["fee_amount"]
        update["cancellation_fee_tier"] = fee["tier"]
        update["cancellation_hours_until_event"] = fee["hours_until_event"]
    res = await db.catering_requests.find_one_and_update(
        {"request_id": request_id}, {"$set": update},
        return_document=True, projection={"_id": 0},
    )
    if not res:
        raise HTTPException(404, "Anfrage nicht gefunden")
    # Mirror to task if linked
    if res.get("task_id"):
        task_status_map = {
            "confirmed": "in_progress",
            "rejected": "cancelled",
            "in_progress": "in_progress",
            "delivered": "review",
            "completed": "done",
            "cancelled": "cancelled",
        }
        await db.tasks.update_one(
            {"task_id": res["task_id"]},
            {"$set": {"status": task_status_map[new_status]}}
        )

    # P0 #2 — notify the booking creator about the catering status change.
    await _notify_catering_status(res, new_status)
    return res


# ============================================================================
# Sprint 3: approvers, dashboard, billing
# ============================================================================

@router.delete("/catering-requests/{request_id}/attachments/{attachment_id}")
async def remove_catering_attachment(request_id: str, attachment_id: str, user=Depends(get_current_user)):
    cr = await db.catering_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not cr:
        raise HTTPException(404, "Anfrage nicht gefunden")
    # Owner or catering processor or admin
    if cr["user_id"] != user["user_id"] and not await has_cap(user, "catering.process", db):
        raise HTTPException(403, "Kein Zugriff")
    new_attachments = [a for a in cr.get("attachments", []) if a != attachment_id]
    await db.catering_requests.update_one(
        {"request_id": request_id},
        {"$set": {"attachments": new_attachments, "updated_at": datetime.now(timezone.utc)}},
    )
    # Audit log
    await _audit_booking(user, cr.get("booking_id", request_id), "attachment_removed", {
        "request_id": request_id, "attachment_id": attachment_id,
    })
    return {"removed": True, "attachments": new_attachments}


# ----- P0 §14 — Desks within a parent "Desk-Room" container -----------------
# Already supported via parent_resource_id on Resource. Endpoint to list all
# desks of one room.
@router.get("/catering-requests/rejection-reasons")
async def list_rejection_reasons(user=Depends(get_current_user)):
    return {"reasons": CATERING_REJECTION_REASONS}



# ============================================================================
# Iter 229 — Audit Polish (5 Mikro-Gaps)
# §10 Upload-Limits konfigurierbar · §13 ERP-Export (DATEV-CSV)
# §14 Lageplan-Hintergrund · §15 Tankkarte + Antriebsart (Model schon erweitert)
# §18 Auslastung pro Teilbereich (Combo-Sub-IDs separat)
# ============================================================================

# ----- §10 — Konfigurierbare Upload-Limits ----------------------------------
# DEFAULT_UPLOAD_MAX_MB + DEFAULT_UPLOAD_MIMES now live in _common.py


@router.post("/catering-requests/{request_id}/attachments/{attachment_id}")
async def link_catering_attachment(
    request_id: str, attachment_id: str, user=Depends(get_current_user),
):
    """Verlinkt einen bereits hochgeladenen Anhang mit einer Catering-Anfrage.
    Validiert serverseitig gegen die konfigurierten Limits (groesse/mime)."""
    cr = await db.catering_requests.find_one(
        {"request_id": request_id}, {"_id": 0})
    if not cr:
        raise HTTPException(404, "Anfrage nicht gefunden")
    # Owner oder catering.process darf Anhaenge ergaenzen
    if cr.get("user_id") != user["user_id"] and not await has_cap(user, "catering.process", db):
        raise HTTPException(403, "Kein Zugriff")
    await _validate_attachment(attachment_id)
    new_atts = list(cr.get("attachments") or [])
    if attachment_id not in new_atts:
        new_atts.append(attachment_id)
    await db.catering_requests.update_one(
        {"request_id": request_id},
        {"$set": {"attachments": new_atts,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    await _audit_booking(user, cr.get("booking_id", request_id),
                         "attachment_added",
                         {"request_id": request_id, "attachment_id": attachment_id})
    return {"linked": attachment_id, "attachments": new_atts}


# ----- §13 — ERP-Export (DATEV-konform) -------------------------------------
