"""Approval flow: approve/reject, pending-count, check-in/out, no-show auto-release."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from database import db
from dependencies import get_current_user
from services.permissions import has_cap, require_cap

from .._common import _audit_booking

router = APIRouter(tags=["resources-bookings"])


@router.post("/resource-bookings/{booking_id}/approve")
async def approve_booking(booking_id: str, payload: Optional[dict] = None, user=Depends(get_current_user)):
    await require_cap(user, "resources.approve", db)
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    if bk.get("status") != "pending_approval":
        raise HTTPException(400, "Buchung wartet nicht auf Freigabe")
    decision = (payload or {}).get("decision", "approve")
    if decision == "reject":
        updates = {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc),
            "cancelled_by": user["user_id"],
            "cancellation_reason": (payload or {}).get("reason") or "Abgelehnt",
        }
    else:
        updates = {
            "status": "confirmed",
            "approved_by": user["user_id"],
            "approved_at": datetime.now(timezone.utc),
        }
    updates["updated_at"] = datetime.now(timezone.utc)
    res = await db.resource_bookings.find_one_and_update(
        {"booking_id": booking_id}, {"$set": updates},
        return_document=True, projection={"_id": 0},
    )
    # Iter 367 — Wenn die Buchung positiv freigegeben wurde und ein Catering
    # angehängt ist, das noch im Status "requested" wartet, markieren wir das
    # Catering als „ready_to_confirm" (über ein `booking_approved_at`-Feld)
    # und pushen eine Notification ans Catering-Team. Ergänzt das Gating aus
    # Iter 366: das Team muss nicht aktiv prüfen, wann der Approver die
    # Buchung freischaltet.
    if decision != "reject" and res and res.get("catering_request_id"):
        cr_id = res["catering_request_id"]
        cr_doc = await db.catering_requests.find_one(
            {"request_id": cr_id}, {"_id": 0}
        )
        if cr_doc and cr_doc.get("status") == "requested":
            await db.catering_requests.update_one(
                {"request_id": cr_id},
                {"$set": {
                    "booking_approved_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            try:
                resource = await db.resources.find_one(
                    {"resource_id": res.get("resource_id")},
                    {"_id": 0, "name": 1},
                ) or {}
                from services.booking_notifications import notify_catering_team_booking_approved
                await notify_catering_team_booking_approved(cr_id, res, resource)
            except Exception:
                pass  # Notification-Fehler darf Approval nicht blocken
    # Iter 368 — Wenn die Buchung abgelehnt wurde und ein Catering hängt
    # dran, kaskadieren wir die Stornierung mit demselben Helper, den auch
    # der reguläre Storno-Pfad benutzt. Reason-Präfix unterscheidet sich,
    # damit Audit/Inbox-Body klar zwischen „storniert" und „abgelehnt"
    # unterscheidet.
    if decision == "reject" and res and res.get("catering_request_id"):
        from services.booking_notifications import cancel_catering_for_booking
        try:
            await cancel_catering_for_booking(
                booking=res,
                actor_user_id=user["user_id"],
                reason_prefix="Buchung wurde abgelehnt",
                reason=(payload or {}).get("reason"),
            )
        except Exception:
            pass
    return res


@router.get("/resource-bookings/approvals/pending-count")
async def approvals_pending_count(user=Depends(get_current_user)):
    """Sidebar/Inbox badge: how many bookings wait for me to approve."""
    if not await has_cap(user, "resources.approve", db):
        return {"count": 0}
    cnt = await db.resource_bookings.count_documents({"status": "pending_approval"})
    return {"count": cnt}


@router.post("/resource-bookings/{booking_id}/check-in")
async def check_in_booking(booking_id: str, user=Depends(get_current_user)):
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    # Iter 283 — Begünstigter (booked_for_user_id) darf ebenfalls einchecken.
    if (bk["user_id"] != user["user_id"]
            and bk.get("booked_for_user_id") != user["user_id"]
            and not await has_cap(user, "resources.view_all_bookings", db)):
        raise HTTPException(403, "Nicht deine Buchung")
    if bk.get("checked_in_at"):
        return bk
    res = await db.resource_bookings.find_one_and_update(
        {"booking_id": booking_id},
        {"$set": {"checked_in_at": datetime.now(timezone.utc),
                  "updated_at": datetime.now(timezone.utc)}},
        return_document=True, projection={"_id": 0},
    )
    await _audit_booking(user, booking_id, "checked_in", {})
    return res


@router.post("/resource-bookings/{booking_id}/check-out")
async def check_out_booking(booking_id: str, payload: Optional[dict] = None, user=Depends(get_current_user)):
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    # Iter 283 — Begünstigter (booked_for_user_id) darf ebenfalls auschecken.
    if (bk["user_id"] != user["user_id"]
            and bk.get("booked_for_user_id") != user["user_id"]
            and not await has_cap(user, "resources.view_all_bookings", db)):
        raise HTTPException(403, "Nicht deine Buchung")
    update = {
        "checked_out_at": datetime.now(timezone.utc),
        "status": "completed",
        "updated_at": datetime.now(timezone.utc),
    }
    if payload and isinstance(payload, dict) and payload.get("mileage_after") is not None:
        update["mileage_after"] = int(payload["mileage_after"])
        # Persist new mileage to vehicle record for next booking convenience.
        await db.resources.update_one(
            {"resource_id": bk["resource_id"]},
            {"$set": {"mileage": int(payload["mileage_after"])}}
        )
    res = await db.resource_bookings.find_one_and_update(
        {"booking_id": booking_id}, {"$set": update},
        return_document=True, projection={"_id": 0},
    )
    await _audit_booking(user, booking_id, "checked_out", {"mileage_after": update.get("mileage_after")})
    return res


@router.post("/resource-bookings/auto-release-no-shows")
async def auto_release_no_shows(grace_min: int = 15, user=Depends(get_current_user)):
    """Marks bookings as no_show where start_at + grace_min has passed
    without check_in. Should be called by a cron / from the reminder loop.
    """
    await require_cap(user, "resources.view_all_bookings", db)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=grace_min)
    result = await db.resource_bookings.update_many({
        "status": "confirmed",
        "checked_in_at": None,
        "start_at": {"$lt": cutoff},
        "end_at": {"$gt": datetime.now(timezone.utc)},
    }, {"$set": {"status": "no_show", "updated_at": datetime.now(timezone.utc)}})
    return {"released": result.modified_count}
