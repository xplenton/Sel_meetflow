"""Booking & catering notification fan-out.

Extracted from `routes/resources/_common.py` in iter 347 to keep `_common.py`
focused on models/constants and to give a single home for the notification
side-effects (push, in-app, e-mail) that fire on the booking lifecycle.

The public API mirrors the original underscore-prefixed helpers 1:1; thin
shims in `_common.py` re-export them under the legacy names so existing
call sites in `routes/resources/bookings.py` / `catering.py` keep working.

  - `notify_approvers(...)`        ↔ legacy `_notify_approvers`
  - `notify_catering_team(...)`    ↔ legacy `_notify_catering_team`
  - `notify_catering_status(...)`  ↔ legacy `_notify_catering_status`
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from database import db


async def notify_approvers(resource: dict, booking) -> None:
    """Push + in-app notification to anyone with `resources.approve`.

    Bulk-inserts all notifications in a single round-trip and fan-outs push
    in parallel so this scales O(1) regardless of approver count instead of
    N awaits. Caller can fire-and-forget this — notifications must never
    block the booking response.
    """
    try:
        approvers = await db.users.find(
            {"$or": [
                {"role": "admin"},
                {"cap_grants": "resources.approve"},
            ]},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(200)
        if not approvers:
            return
        from services.news_push import send_push_to_user

        title = "Neue Buchungsfreigabe noetig"
        body = f"{booking.title} · {resource.get('name')} · {booking.start_at.strftime('%d.%m. %H:%M')}"
        data = {
            "type": "resource_booking_pending",
            "booking_id": booking.booking_id,
            "resource_id": resource.get("resource_id"),
            "url": "/resources?tab=approvals",
        }
        uids = [a["user_id"] for a in approvers if a.get("user_id")]
        now = datetime.now(timezone.utc)
        if uids:
            try:
                await db.notifications.insert_many([{
                    "user_id": uid, "type": "resource_booking_pending",
                    "title": title, "body": body, "data": data,
                    "read": False, "created_at": now,
                } for uid in uids], ordered=False)
            except Exception:
                pass
            await asyncio.gather(
                *(send_push_to_user(uid, title=title, body=body, data=data) for uid in uids),
                return_exceptions=True,
            )
    except Exception:
        # Notifications must never break booking creation.
        pass


def _parse_iso_local(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def notify_catering_team(catering: Any, resource: dict, booking: Any) -> None:
    """Notify everyone with `catering.process` about a new/changed catering request."""
    try:
        recipients = await db.users.find(
            {"$or": [{"role": "admin"}, {"cap_grants": "catering.process"}]},
            {"_id": 0, "user_id": 1},
        ).to_list(50)
        if not recipients:
            return
        from services.news_push import send_push_to_user

        title = "Neue Catering-Anfrage"
        start = booking.start_at if isinstance(booking.start_at, datetime) else _parse_iso_local(booking.start_at)
        body = f"{booking.title} · {resource.get('name')} · {start.strftime('%d.%m. %H:%M')}"
        data = {"type": "catering_requested", "booking_id": booking.booking_id, "url": "/resources?tab=catering"}
        for r in recipients:
            uid = r.get("user_id")
            try:
                await db.notifications.insert_one({
                    "user_id": uid, "type": "catering_requested",
                    "title": title, "body": body, "data": data,
                    "read": False, "created_at": datetime.now(timezone.utc),
                })
            except Exception:
                pass
            try:
                await send_push_to_user(uid, title=title, body=body, data=data)
            except Exception:
                pass
    except Exception:
        pass


async def notify_catering_team_booking_approved(catering_request_id: str, booking: dict, resource: dict) -> None:
    """Iter 367 — Push ans Catering-Team, sobald die zugehörige Buchung
    freigegeben wurde. Ergänzt das Gating aus Iter 366: das Team muss nicht
    aktiv prüfen, wann der Approver die Buchung freischaltet — es bekommt
    eine Direkt-Notification mit Deep-Link in die Catering-Inbox.
    """
    try:
        recipients = await db.users.find(
            {"$or": [{"role": "admin"}, {"cap_grants": "catering.process"}]},
            {"_id": 0, "user_id": 1},
        ).to_list(50)
        if not recipients:
            return
        from services.news_push import send_push_to_user

        title = "Catering kann jetzt bestätigt werden"
        start_iso = booking.get("start_at")
        start_dt = start_iso if isinstance(start_iso, datetime) else _parse_iso_local(start_iso)
        body = (
            f"{booking.get('title','Buchung')} freigegeben · "
            f"{resource.get('name','')} · {start_dt.strftime('%d.%m. %H:%M')}"
        )
        data = {
            "type": "catering_booking_approved",
            "booking_id": booking.get("booking_id"),
            "catering_request_id": catering_request_id,
            "url": "/resources?tab=catering",
        }
        for r in recipients:
            uid = r.get("user_id")
            try:
                await db.notifications.insert_one({
                    "user_id": uid, "type": "catering_booking_approved",
                    "title": title, "body": body, "data": data,
                    "read": False, "created_at": datetime.now(timezone.utc),
                })
            except Exception:
                pass
            try:
                await send_push_to_user(uid, title=title, body=body, data=data)
            except Exception:
                pass
    except Exception:
        pass


async def notify_catering_status(cr: dict, new_status: str) -> None:
    """Notify the creator when the catering status changes (confirmed/rejected/…)."""
    try:
        uid = cr.get("user_id")
        if not uid:
            return
        labels = {
            "confirmed": "Catering bestätigt",
            "rejected": "Catering abgelehnt",
            "in_progress": "Catering in Vorbereitung",
            "delivered": "Catering geliefert",
            "completed": "Catering abgeschlossen",
            "cancelled": "Catering storniert",
        }
        title = labels.get(new_status, f"Catering: {new_status}")
        body_parts = [cr.get("request_id", "")]
        if cr.get("rejection_reason"):
            body_parts.append(f"Grund: {cr['rejection_reason']}")
        if cr.get("cancellation_reason"):
            body_parts.append(f"Stornogrund: {cr['cancellation_reason']}")
        data = {
            "type": "catering_status",
            "request_id": cr.get("request_id"),
            "booking_id": cr.get("booking_id"),
            "status": new_status,
            "url": "/resources?tab=mine",
        }
        await db.notifications.insert_one({
            "user_id": uid, "type": "catering_status", "title": title,
            "body": " · ".join(body_parts), "data": data,
            "read": False, "created_at": datetime.now(timezone.utc),
        })
        try:
            from services.news_push import send_push_to_user
            await send_push_to_user(uid, title=title, body=" · ".join(body_parts), data=data)
        except Exception:
            pass

        # Polished e-mail via shared template (iter 227)
        try:
            user_doc = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1, "name": 1})
            if user_doc and user_doc.get("email"):
                from services.email_templates import render_email, render_kv_list
                from services.email import send_email_real
                bk = await db.resource_bookings.find_one({"booking_id": cr.get("booking_id")}, {"_id": 0}) or {}
                res = await db.resources.find_one({"resource_id": bk.get("resource_id")}, {"_id": 0}) or {}
                kv = render_kv_list([
                    ("Buchung", bk.get("title")),
                    ("Ressource", res.get("name")),
                    ("Status", title),
                    ("Grund", cr.get("rejection_reason")),
                ])
                msg = {
                    "confirmed": "deine Catering-Bestellung wurde bestätigt.",
                    "rejected": "deine Catering-Bestellung musste leider abgelehnt werden.",
                    "in_progress": "deine Catering-Bestellung ist in Vorbereitung.",
                    "delivered": "dein Catering wurde geliefert.",
                    "completed": "dein Catering wurde abgeschlossen.",
                }.get(new_status, "Status deines Catering hat sich geaendert.")
                front_url = os.environ.get("FRONTEND_URL", "")
                html = render_email(
                    title=title,
                    preheader=msg,
                    body_html=f"<p>Hallo {user_doc.get('name','')},</p><p>{msg}</p>{kv}",
                    cta_label="Buchung oeffnen",
                    cta_url=f"{front_url}/resources?tab=mine" if front_url else None,
                    accent=(new_status == "rejected"),
                )
                await send_email_real(user_doc["email"], title, html)
        except Exception:
            pass
    except Exception:
        pass



async def cancel_catering_for_booking(
    booking: dict,
    actor_user_id: str,
    reason_prefix: str,
    reason: str | None = None,
) -> None:
    """Iter 368 — gemeinsamer Cascade-Helper: storniert das verknüpfte
    Catering, schreibt Stornogebühr-Stufe, deaktiviert den verknüpften Task
    und pusht eine Notification an den Buchungs-Owner.

    Wird sowohl beim regulären Storno (Iter 366) als auch beim Reject im
    Approval-Flow (Iter 368) aufgerufen, damit beide Pfade konsistent sind.

    Args:
        booking: Aktuelles Buchungs-Doc mit mindestens `catering_request_id`,
                 `title`, optional `start_at`.
        actor_user_id: Wer hat die Aktion ausgelöst (für `cancelled_by`).
        reason_prefix: Menschenlesbarer Präfix wie „Buchung wurde storniert"
                       oder „Buchung wurde abgelehnt".
        reason: Optionaler Freitext-Grund vom User.
    """
    from database import db
    from routes.resources.catering import _get_cancel_cfg, _compute_cancel_fee

    cr_id = booking.get("catering_request_id")
    if not cr_id:
        return
    cr_doc = await db.catering_requests.find_one({"request_id": cr_id}, {"_id": 0})
    if not cr_doc or cr_doc.get("status") in ("cancelled", "completed"):
        return
    now = datetime.now(timezone.utc)
    cfg = await _get_cancel_cfg()
    fee = _compute_cancel_fee(cr_doc, cfg)
    cancellation_reason = reason_prefix
    if booking.get("title"):
        cancellation_reason += f": {booking['title']}"
    if reason:
        cancellation_reason += f" — Grund: {reason}"
    await db.catering_requests.update_one(
        {"request_id": cr_id},
        {"$set": {
            "status": "cancelled",
            "cancellation_reason": cancellation_reason,
            "cancelled_by": actor_user_id,
            "cancelled_at": now,
            "cancellation_fee_percent": fee["fee_percent"],
            "cancellation_fee_amount": fee["fee_amount"],
            "cancellation_fee_tier": fee["tier"],
            "cancellation_hours_until_event": fee["hours_until_event"],
            "updated_at": now,
        }},
    )
    if cr_doc.get("task_id"):
        try:
            await db.tasks.update_one(
                {"task_id": cr_doc["task_id"]},
                {"$set": {"status": "cancelled"}},
            )
        except Exception:
            pass
    # Notification mit dem frischen Catering-Doc (enthält dann den neuen
    # cancellation_reason) — `notify_catering_status` baut daraus den
    # Push/Inbox-Body.
    try:
        fresh_cr = await db.catering_requests.find_one({"request_id": cr_id}, {"_id": 0})
        await notify_catering_status(fresh_cr, "cancelled")
    except Exception:
        pass
