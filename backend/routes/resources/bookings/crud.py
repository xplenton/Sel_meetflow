"""Booking CRUD: check-conflicts + list / get / create / update / cancel."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from database import db
from dependencies import get_current_user
from services.permissions import has_cap, require_cap

from .._common import (
    BookingStatus, ResourceBooking,
    _audit_booking, _check_conflicts, _notify_approvers,
    _notify_catering_team, _parse_iso, _validate_allowed_combination,
    _verify_booking_winner,
)

router = APIRouter(tags=["resources-bookings"])


@router.post("/resources/{resource_id}/check-conflicts")
async def check_conflicts(resource_id: str, payload: dict, user=Depends(get_current_user)):
    """Return list of conflicting bookings (used by UI before submit)."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    start = _parse_iso(payload["start_at"])
    end = _parse_iso(payload["end_at"])
    exclude = payload.get("exclude_booking_id")
    return {"conflicts": await _check_conflicts(resource_id, start, end, exclude)}


@router.get("/resource-bookings")
async def list_bookings(
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[BookingStatus] = None,
    mine_only: bool = False,
    # Iter 342 — when the slot-picker on a resource card requests bookings
    # for availability rendering, return ALL bookings on that resource as
    # privacy-safe stubs (only start_at / end_at / status), regardless of
    # owner. Otherwise non-privileged users saw "Belegt bis 12:00" in the
    # snapshot (which is unfiltered) but slot grid said "free" because
    # owner-filter hid the conflicting booking.
    availability_only: bool = False,
    user=Depends(get_current_user),
):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    q: dict = {}
    if resource_id:
        q["resource_id"] = resource_id
    if user_id:
        q["user_id"] = user_id
    if status:
        q["status"] = status
    # Members only see their own bookings unless they have view_all_bookings.
    # `availability_only` bypasses this filter but strips PII before returning.
    has_view_all = await has_cap(user, "resources.view_all_bookings", db)
    if not availability_only and (mine_only or not has_view_all):
        q["$or"] = [{"user_id": user["user_id"]}, {"booked_for_user_id": user["user_id"]}]
    if from_date:
        q["end_at"] = {"$gte": _parse_iso(from_date)}
    if to_date:
        q.setdefault("start_at", {})
        if not isinstance(q["start_at"], dict):
            q["start_at"] = {}
        q["start_at"]["$lte"] = _parse_iso(to_date)
    if availability_only:
        # Iter 350 — Align with `availability_snapshot` so the "Frei bis HH:MM"
        # badge on the resource card MATCHES the slot grid below it. Without
        # this filter, bookings with status `no_show`, `completed` or
        # `cancelled` were still rendered as blocked slots in the frontend
        # while the snapshot already considered them as free → mismatch.
        if "status" not in q:
            q["status"] = {"$in": ["confirmed", "pending_approval"]}
        # Iter 352 — Parent/Children expansion centralised in
        # services.resource_hierarchy. Same rules as `check_conflicts`:
        #   parent  → include all children
        #   child   → include the parent (parent-level bookings block subs)
        if resource_id:
            from services.resource_hierarchy import expand_blocking_ids
            blocking_ids, _res, _buf = await expand_blocking_ids(resource_id)
            if len(blocking_ids) > 1:
                q["resource_id"] = {"$in": blocking_ids}
        # Privacy-safe slim payload so the slot-picker doesn't leak who booked.
        items = await db.resource_bookings.find(
            q,
            {"_id": 0, "booking_id": 1, "resource_id": 1, "start_at": 1, "end_at": 1, "status": 1},
        ).sort("start_at", 1).to_list(500)
        for b in items:
            if not (b.get("user_id") == user["user_id"]
                    or b.get("booked_for_user_id") == user["user_id"]):
                b["title"] = "Belegt"
        return items
    items = await db.resource_bookings.find(q, {"_id": 0}).sort("start_at", 1).to_list(500)
    # Iter 325 — hydrate resource + user metadata so the frontend can render
    # the booking summary in clear text (Resource-Name + Standort/Kennzeichen,
    # plus "gebucht von / für" Anzeige). Without these joins the list only
    # shows opaque IDs.
    res_ids = list({b["resource_id"] for b in items if b.get("resource_id")})
    res_map: dict = {}
    if res_ids:
        async for r in db.resources.find(
            {"resource_id": {"$in": res_ids}},
            {"_id": 0, "resource_id": 1, "name": 1, "type": 1,
             "license_plate": 1, "building": 1, "floor": 1,
             "desk_number": 1, "location": 1, "parking_location": 1,
             # Iter 339 — Sub-Räume: damit das Frontend "↳ Bereich A · Großer Saal"
             # anzeigen kann, müssen wir parent_resource_id + sub_id mitliefern.
             "parent_resource_id": 1, "sub_id": 1, "is_splitable": 1},
        ):
            res_map[r["resource_id"]] = r
    # Iter 339 — second pass: load any parents we need names for.
    parent_ids = {r.get("parent_resource_id") for r in res_map.values() if r.get("parent_resource_id")}
    parent_map: dict = {}
    if parent_ids:
        async for r in db.resources.find(
            {"resource_id": {"$in": list(parent_ids)}},
            {"_id": 0, "resource_id": 1, "name": 1},
        ):
            parent_map[r["resource_id"]] = r.get("name")
    user_ids = set()
    for b in items:
        if b.get("user_id"):
            user_ids.add(b["user_id"])
        if b.get("booked_for_user_id"):
            user_ids.add(b["booked_for_user_id"])
    user_map: dict = {}
    if user_ids:
        async for u in db.users.find(
            {"user_id": {"$in": list(user_ids)}},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1},
        ):
            user_map[u["user_id"]] = u
    for b in items:
        r = res_map.get(b.get("resource_id"))
        if r:
            b["resource_name"] = r.get("name")
            b["resource_type"] = r.get("type")
            b["resource_license_plate"] = r.get("license_plate")
            b["resource_building"] = r.get("building")
            b["resource_floor"] = r.get("floor")
            b["resource_desk_number"] = r.get("desk_number")
            b["resource_location"] = r.get("location")
            b["resource_parking_location"] = r.get("parking_location")
            # Iter 339 — Sub-Room context. If the booking sits on a sub-room
            # we expose parent name + sub_id so the UI can render
            # "Großer Saal — Bereich A" instead of just bare "A".
            if r.get("parent_resource_id"):
                b["resource_sub_id"] = r.get("sub_id")
                b["resource_parent_id"] = r.get("parent_resource_id")
                b["resource_parent_name"] = parent_map.get(r["parent_resource_id"])
        bu = user_map.get(b.get("user_id"))
        if bu:
            b["user_name"] = bu.get("name")
            b["user_email"] = bu.get("email")
        if b.get("booked_for_user_id"):
            fu = user_map.get(b["booked_for_user_id"])
            if fu:
                b["booked_for_name"] = fu.get("name")
                b["booked_for_email"] = fu.get("email")
    # Iter 286 — hydrate catering status so the "Meine Buchungen" Tab can show
    # whether a catering request was confirmed/rejected/etc. The frontend
    # otherwise has no way to surface the catering decision to end users.
    cr_ids = [b.get("catering_request_id") for b in items if b.get("catering_request_id")]
    if cr_ids:
        cr_status = {
            c["request_id"]: c.get("status")
            for c in await db.catering_requests.find(
                {"request_id": {"$in": list(set(cr_ids))}},
                {"_id": 0, "request_id": 1, "status": 1, "rejection_reason": 1},
            ).to_list(500)
        }
        cr_reasons = {
            c["request_id"]: c.get("rejection_reason")
            for c in await db.catering_requests.find(
                {"request_id": {"$in": list(set(cr_ids))}},
                {"_id": 0, "request_id": 1, "rejection_reason": 1},
            ).to_list(500)
        }
        for b in items:
            if b.get("catering_request_id"):
                b["catering_status"] = cr_status.get(b["catering_request_id"])
                rr = cr_reasons.get(b["catering_request_id"])
                if rr:
                    b["catering_rejection_reason"] = rr
    return items


@router.get("/resource-bookings/{booking_id}")
async def get_booking(booking_id: str, user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    if (bk["user_id"] != user["user_id"]
            and bk.get("booked_for_user_id") != user["user_id"]
            and not await has_cap(user, "resources.view_all_bookings", db)):
        raise HTTPException(403, "Nicht deine Buchung")
    return bk


@router.post("/resource-bookings")
async def create_booking(payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "resources.book", db)
    resource_id = payload.get("resource_id")
    if not resource_id:
        raise HTTPException(400, "resource_id fehlt")
    res = await db.resources.find_one({"resource_id": resource_id}, {"_id": 0})
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    if res.get("status") in ("inactive", "blocked", "maintenance"):
        raise HTTPException(400, f"Ressource ist {res['status']}")

    start = _parse_iso(payload["start_at"])
    end = _parse_iso(payload["end_at"])
    if end <= start:
        raise HTTPException(400, "Endzeit muss nach Startzeit liegen")

    dur_min = (end - start).total_seconds() / 60
    if res.get("min_duration_min") and dur_min < res["min_duration_min"]:
        raise HTTPException(400, f"Mindestbuchungsdauer {res['min_duration_min']} Minuten")
    if res.get("max_duration_min") and dur_min > res["max_duration_min"]:
        raise HTTPException(400, f"Maximale Buchungsdauer {res['max_duration_min']} Minuten überschritten")

    booked_for = payload.get("booked_for_user_id")
    if booked_for and booked_for != user["user_id"]:
        # Iter 283 — allow if EITHER (a) caller has the org-wide capability,
        # OR (b) the target user has explicitly added the caller as their
        # delegate (consent-based "Stellvertreter" relationship).
        allowed = await has_cap(user, "resources.book_for_others", db)
        if not allowed:
            target = await db.users.find_one(
                {"user_id": booked_for}, {"_id": 0, "delegates": 1}
            )
            if target and user["user_id"] in (target.get("delegates") or []):
                allowed = True
        if not allowed:
            raise HTTPException(403, "Kein Recht, für andere zu buchen")

    # Iter 338 — Issue #3: support a "soft override" for `pending_approval`
    # collisions. The user has been shown a warning in the dialog ("Bereits
    # beantragt, aber noch nicht freigegeben") and consciously asks to file
    # a parallel pending request. Hard `confirmed` conflicts still block.
    allow_pending_overlap = bool(payload.get("allow_pending_overlap"))
    conflicts = await _check_conflicts(resource_id, start, end)
    if allow_pending_overlap:
        conflicts = [c for c in conflicts if c.get("status") != "pending_approval"]
    if conflicts:
        raise HTTPException(409, {"detail": "Konflikt mit bestehender Buchung", "conflicts": conflicts})

    # Iter 292 — Vehicle license check. The driver is the user the booking is
    # *for* (booked_for) so a delegate can still book on behalf of someone who
    # holds the right class. If the resource has `required_license_class` set
    # we look it up on the target user's `drivers_licenses` array.
    if res.get("type") == "vehicle" and res.get("required_license_class"):
        driver_id = booked_for or user["user_id"]
        driver = await db.users.find_one(
            {"user_id": driver_id}, {"_id": 0, "drivers_licenses": 1, "name": 1}
        )
        held = {
            (lic.get("license_class") or "").upper()
            for lic in (driver or {}).get("drivers_licenses") or []
            if not lic.get("is_custom")
        }
        required = res["required_license_class"].upper()
        if required not in held:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "license_missing",
                    "required_class": required,
                    "driver_user_id": driver_id,
                    "message": (
                        f"Fahrer hat keine Führerscheinklasse {required}. "
                        f"Bitte zuerst im Profil eintragen."
                    ),
                },
            )

    # P0 #4 — enforce allowed_combinations for sub-rooms
    await _validate_allowed_combination(resource_id)

    booking = ResourceBooking(
        resource_id=resource_id,
        user_id=user["user_id"],
        booked_for_user_id=booked_for,
        title=payload.get("title", "Buchung"),
        description=payload.get("description"),
        start_at=start, end_at=end,
        purpose=payload.get("purpose"),
        destination=payload.get("destination"),
        passengers=payload.get("passengers") or [],
        mileage_before=payload.get("mileage_before"),
        cost_center=payload.get("cost_center"),
        account=payload.get("account"),
        # Iter 338 — A pending-overlap booking ALWAYS needs human review
        # even on auto-confirm resources, otherwise two overlapping bookings
        # would both be 'confirmed'.
        status="pending_approval" if (res.get("requires_approval") or allow_pending_overlap) else "confirmed",
    )
    doc = booking.model_dump()
    await db.resource_bookings.insert_one(doc)
    doc.pop("_id", None)

    # Iter 248 — Race-condition-safe verification:
    # _check_conflicts above is NOT atomic with insert_one. Under concurrent
    # load, multiple requests can pass the initial check and all insert. Now
    # re-query and use deterministic winner-selection: if a peer booking
    # overlaps and has a smaller booking_id, we lose and delete ourselves.
    # Iter 338 — Skip winner-selection when the user explicitly accepts
    # pending-overlap: filing parallel pending bookings is then the desired
    # behavior, not a race to be resolved.
    if not allow_pending_overlap:
        lost_to = await _verify_booking_winner(
            booking.booking_id, resource_id, start, end,
        )
        if lost_to:
            await db.resource_bookings.delete_one({"booking_id": booking.booking_id})
            raise HTTPException(409, {
                "detail": "Konflikt mit gleichzeitiger Buchung (Race)",
                "conflicts": lost_to,
            })

    # P0 #9 — audit log.
    # Iter 342 — Fire-and-forget so the audit row write doesn't sit in the
    # critical path; the booking itself is already persisted at this point.
    asyncio.create_task(_audit_booking(user, booking.booking_id, "booking_created", {
        "resource_id": resource_id, "resource_name": res.get("name"),
        "start_at": start.isoformat(), "end_at": end.isoformat(),
        "title": booking.title, "status": booking.status,
    }))

    # Notify approvers via push when approval is required.
    # Iter 338 — fire-and-forget so notification fan-out does not block the
    # response. Users see "Buchung angelegt" within 50–100 ms; approvers
    # still get pushed within a heartbeat.
    if res.get("requires_approval") or allow_pending_overlap:
        asyncio.create_task(_notify_approvers(res, booking))

    # Optional catering attachment
    catering_payload = payload.get("catering")
    if catering_payload and res.get("allow_catering"):
        from services.catering_request_factory import attach_catering_to_booking
        cr_id, lead_time_warning = await attach_catering_to_booking(
            booking=booking,
            resource=res,
            user=user,
            catering_payload=catering_payload,
            fallback_start_at=start,
            fallback_cost_center=payload.get("cost_center"),
            fallback_account=payload.get("account"),
        )
        doc["catering_request_id"] = cr_id
        if lead_time_warning:
            # Iter 322b — Surface the lead-time breach to the frontend response
            # so the BookingDialog can show the same info that was emailed.
            doc["lead_time_warning"] = lead_time_warning
    return doc


@router.put("/resource-bookings/{booking_id}")
async def update_booking(booking_id: str, payload: dict, user=Depends(get_current_user)):
    """Edit time-window or details of an existing booking. Re-checks conflicts."""
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    if bk["user_id"] != user["user_id"] and not await has_cap(user, "resources.view_all_bookings", db):
        raise HTTPException(403, "Nicht deine Buchung")
    if bk.get("status") in ("cancelled", "completed"):
        raise HTTPException(400, "Buchung ist abgeschlossen oder storniert")

    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    allow_fields = {"title", "description", "purpose", "destination", "passengers",
                    "mileage_before", "mileage_after", "cost_center", "account"}
    for k in allow_fields:
        if k in payload:
            updates[k] = payload[k]

    # Iter 236 — Drag&Drop across resources: allow resource_id change (same type only).
    target_resource_id = bk["resource_id"]
    resource_changed = False
    if payload.get("resource_id") and payload["resource_id"] != bk["resource_id"]:
        new_res = await db.resources.find_one({"resource_id": payload["resource_id"]}, {"_id": 0})
        if not new_res:
            raise HTTPException(404, "Ziel-Ressource nicht gefunden")
        old_res = await db.resources.find_one({"resource_id": bk["resource_id"]}, {"_id": 0, "type": 1})
        if old_res and old_res.get("type") != new_res.get("type"):
            raise HTTPException(400, "Ziel-Ressource hat einen anderen Typ als die Buchung")
        if new_res.get("status") and new_res["status"] != "active":
            raise HTTPException(400, "Ziel-Ressource ist nicht aktiv")
        target_resource_id = payload["resource_id"]
        updates["resource_id"] = target_resource_id
        resource_changed = True

    new_start = _parse_iso(payload["start_at"]) if payload.get("start_at") else None
    new_end = _parse_iso(payload["end_at"]) if payload.get("end_at") else None
    time_changed = False
    if new_start or new_end or resource_changed:
        start = new_start or bk["start_at"]
        end = new_end or bk["end_at"]
        if isinstance(start, str):
            start = _parse_iso(start)
        if isinstance(end, str):
            end = _parse_iso(end)
        if end <= start:
            raise HTTPException(400, "Endzeit muss nach Startzeit liegen")
        conflicts = await _check_conflicts(target_resource_id, start, end, exclude_booking_id=booking_id)
        if conflicts:
            raise HTTPException(409, {"detail": "Konflikt mit bestehender Buchung", "conflicts": conflicts})
        if new_start or new_end:
            updates["start_at"] = start
            updates["end_at"] = end
            time_changed = True

    res = await db.resource_bookings.find_one_and_update(
        {"booking_id": booking_id}, {"$set": updates},
        return_document=True, projection={"_id": 0},
    )

    # Iter 252 — Race-condition-safe verification for MOVE/UPDATE.
    # Same TOCTOU pattern as create_booking: two concurrent updates could both
    # pass _check_conflicts then both write into overlapping windows on the
    # target resource. After the update, re-query competitors and revert if
    # we lost the deterministic-winner contest (smallest booking_id wins).
    if time_changed or resource_changed:
        final_start = updates.get("start_at", bk["start_at"])
        final_end = updates.get("end_at", bk["end_at"])
        if isinstance(final_start, str):
            final_start = _parse_iso(final_start)
        if isinstance(final_end, str):
            final_end = _parse_iso(final_end)
        lost_to = await _verify_booking_winner(
            booking_id, target_resource_id, final_start, final_end,
        )
        if lost_to:
            # Revert to previous state
            revert = {
                "resource_id": bk["resource_id"],
                "start_at": bk["start_at"],
                "end_at": bk["end_at"],
                "updated_at": datetime.now(timezone.utc),
            }
            await db.resource_bookings.update_one(
                {"booking_id": booking_id}, {"$set": revert},
            )
            raise HTTPException(409, {
                "detail": "Konflikt mit gleichzeitiger Buchung (Race)",
                "conflicts": lost_to,
            })

    # P0 #9 — audit log
    await _audit_booking(user, booking_id, "booking_updated", {
        "fields": list(updates.keys()),
        "time_changed": time_changed,
        "resource_changed": resource_changed,
    })

    # P0 #7 — time change must re-confirm linked catering
    if time_changed and bk.get("catering_request_id"):
        await db.catering_requests.update_one(
            {"request_id": bk["catering_request_id"]},
            {"$set": {
                "status": "requested",
                "delivery_at": updates["start_at"],
                "updated_at": datetime.now(timezone.utc),
            }}
        )
        cr = await db.catering_requests.find_one({"request_id": bk["catering_request_id"]}, {"_id": 0})
        if cr and cr.get("task_id"):
            await db.tasks.update_one({"task_id": cr["task_id"]}, {"$set": {"status": "todo"}})
        # Re-notify catering team
        if cr:
            resource = await db.resources.find_one({"resource_id": bk["resource_id"]}, {"_id": 0}) or {}
            from types import SimpleNamespace
            booking_ns = SimpleNamespace(
                booking_id=booking_id,
                title=res.get("title", bk.get("title")),
                start_at=updates["start_at"],
            )
            await _notify_catering_team(SimpleNamespace(**cr), resource, booking_ns)

    return res


@router.delete("/resource-bookings/{booking_id}")
async def cancel_booking(booking_id: str, payload: Optional[dict] = None, user=Depends(get_current_user)):
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    if bk["user_id"] != user["user_id"] and not await has_cap(user, "resources.view_all_bookings", db):
        raise HTTPException(403, "Nicht deine Buchung")
    reason = (payload or {}).get("reason") if isinstance(payload, dict) else None
    await db.resource_bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc),
            "cancelled_by": user["user_id"],
            "cancellation_reason": reason,
            "updated_at": datetime.now(timezone.utc),
        }}
    )
    # Cascade catering + task
    # Iter 366/368 — Wenn die Buchung storniert wird, muss das Catering automatisch
    # mit storniert werden, mit Grund + Notification an den Buchungs-Owner.
    # Shared Helper, damit Reject-Path aus dem Approval-Flow konsistent ist.
    if bk.get("catering_request_id"):
        from services.booking_notifications import cancel_catering_for_booking
        try:
            await cancel_catering_for_booking(
                booking=bk,
                actor_user_id=user["user_id"],
                reason_prefix="Buchung wurde storniert",
                reason=reason,
            )
        except Exception:
            pass
    return {"cancelled": True}
