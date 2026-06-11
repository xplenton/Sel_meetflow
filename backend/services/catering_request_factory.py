"""Catering-request creation pipeline.

Extracted from `routes/resources/bookings/crud.py` in iter 348 to lift the
~145-line catering block out of `create_booking`. The pipeline is invoked
once a booking has been persisted and `payload.catering` is present and
the resource allows catering.

Public API:
    `attach_catering_to_booking(booking, resource, user, catering_payload,
                                fallback_start_at) -> (catering_request_id,
                                lead_time_warning_or_None)`

Side-effects (in order):
    1. Insert a `CateringRequest` document
    2. Compute `lead_time_breach` from per-item `lead_time_min` and persist
       breach flags on the catering_request
    3. Create an auto-task in `tasks` assigned to `catering.process` holders
       + admins (max 20)
    4. Cross-link `task_id` ↔ `catering_request_id` ↔ `booking_id`
    5. Fire-and-forget `notify_catering_team` push/inbox
    6. Fire-and-forget `_send_short_notice_email` if lead_time was breached

Behaviour is byte-identical to the inline block that lived in iter 347's
`crud.py`; this is purely a code-organisation refactor.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from routes.resources._common import CateringLine, CateringRequest, _parse_iso
from services.booking_notifications import notify_catering_team


# ---------------------------------------------------------------------------
# Short-notice e-mail (moved from routes/resources/bookings/_helpers.py)
# ---------------------------------------------------------------------------

async def _send_short_notice_email(
    cr,
    booking,
    resource,
    assignee_ids,
    required_min: int,
    available_min: int,
    worst_item: Optional[str],
    line_summary: list,
) -> None:
    """Urgency e-mail to the cafeteria team when lead-time was breached.

    Best-effort. Fails silently if SMTP is misconfigured — the
    `lead_time_breach` flag persisted on the catering_request is the source
    of truth for the UI.
    """
    if not assignee_ids:
        return

    recipients: list[tuple[str, str]] = []
    async for u in db.users.find(
        {"user_id": {"$in": assignee_ids}, "is_active": {"$ne": False}},
        {"_id": 0, "email": 1, "name": 1},
    ):
        if u.get("email"):
            recipients.append((u["email"], u.get("name") or u["email"]))
    if not recipients:
        return

    delivery_dt = cr.delivery_at or booking.start_at
    if delivery_dt.tzinfo is None:
        delivery_dt = delivery_dt.replace(tzinfo=timezone.utc)
    delivery_str = delivery_dt.strftime("%d.%m.%Y um %H:%M Uhr")
    avail_human = (
        "bereits in der Vergangenheit" if available_min < 0
        else f"in {available_min // 60} Std. {available_min % 60} Min." if available_min >= 60
        else f"in {available_min} Min."
    )
    req_human = (
        f"{required_min // 60} Std. {required_min % 60} Min." if required_min >= 60
        else f"{required_min} Min."
    )
    lines_html = "".join(f"<li>{ln.strip(' •')}</li>" for ln in line_summary) or "<li>(keine)</li>"

    subject = f"⚠️ Kurzfristige Catering-Anfrage — nur {avail_human}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;color:#1C1F1D">
      <div style="background:#FFF7E6;border-left:4px solid #F0C75A;padding:14px 18px;border-radius:6px;margin-bottom:18px">
        <div style="font-size:14px;font-weight:700;color:#7A4D00;margin-bottom:4px">
          Vorlaufzeit unterschritten
        </div>
        <div style="font-size:13px;color:#7A4D00">
          Diese Catering-Anfrage benötigt mindestens <strong>{req_human}</strong> Vorlaufzeit
          {f'(strengster Artikel: <em>{worst_item}</em>)' if worst_item else ''}, soll aber
          bereits <strong>{avail_human}</strong> bereitgestellt werden.
        </div>
      </div>
      <div style="font-size:14px;line-height:1.5">
        <strong>Bereitstellung:</strong> {delivery_str}<br>
        <strong>Raum:</strong> {resource.get('name', '—')}{f" · Lieferort: {cr.delivery_target}" if cr.delivery_target else ''}<br>
        <strong>Anlass:</strong> {booking.title}<br>
        <strong>Ansprechpartner:</strong> {cr.contact or '—'}<br>
        <strong>Kostenstelle / Konto:</strong> {cr.cost_center or '—'} · {cr.account or '—'}
        {f"<br><strong>Notiz:</strong> {cr.notes}" if cr.notes else ''}
      </div>
      <div style="font-size:13px;margin-top:14px">
        <strong>Bestellung:</strong>
        <ul style="margin:6px 0 0 18px;padding:0">{lines_html}</ul>
      </div>
      <div style="font-size:12px;color:#6B7280;margin-top:18px;border-top:1px solid #E2E4E0;padding-top:10px">
        Bitte prüfen Sie die Aufgabe in MeetFlow und bestätigen oder lehnen Sie die
        Anfrage ab. Diese E-Mail wurde automatisch versandt, weil die Vorlaufzeit
        der gewählten Artikel unterschritten wurde.
      </div>
    </div>
    """
    from services.email import send_email_real
    for email, _name in recipients:
        try:
            await send_email_real(email, subject, html, category="catering_short_notice")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Catering attach pipeline
# ---------------------------------------------------------------------------

async def attach_catering_to_booking(
    booking,
    resource: dict,
    user: dict,
    catering_payload: dict,
    fallback_start_at: datetime,
    fallback_cost_center: Optional[str] = None,
    fallback_account: Optional[str] = None,
) -> tuple[str, Optional[dict]]:
    """Create a catering_request + auto-task + cross-links for a booking.

    Returns `(catering_request_id, lead_time_warning)`. `lead_time_warning`
    is `None` if no breach, otherwise a dict with breach/required_min/
    available_min/worst_item keys ready to be merged into the booking's
    response payload.

    `fallback_cost_center` / `fallback_account` are used when the catering
    payload itself does not specify them (typically the values from the
    surrounding booking payload).

    Assumes the caller already verified `resource.allow_catering` and that
    `catering_payload` is non-empty.
    """
    cr = CateringRequest(
        booking_id=booking.booking_id,
        user_id=user["user_id"],
        items=[CateringLine(**i) for i in catering_payload.get("items", [])],
        delivery_at=_parse_iso(catering_payload["delivery_at"]) if catering_payload.get("delivery_at") else fallback_start_at,
        delivery_target=catering_payload.get("delivery_target"),
        contact=catering_payload.get("contact"),
        notes=catering_payload.get("notes"),
        cost_center=catering_payload.get("cost_center") or fallback_cost_center,
        account=catering_payload.get("account") or fallback_account,
        attachments=catering_payload.get("attachments") or [],
    )
    await db.catering_requests.insert_one(cr.model_dump())

    # P1 #12 — Auto-create a task for the catering team with full context.
    # P0 #8 — auto-assign to users with the catering.process capability.
    items_idx = {i["item_id"]: i for i in await db.catering_items.find({}, {"_id": 0}).to_list(500)}

    # Iter 322b — Server-side lead-time validation.
    # Each catering item has `lead_time_min` (default 60 min). If the
    # delivery_at (or meeting start) is sooner than the max required
    # lead-time across the selected items, flag the catering_request and
    # send a heads-up e-mail to the cafeteria team so they can confirm
    # the short-notice order.
    delivery_dt = cr.delivery_at or fallback_start_at
    if delivery_dt.tzinfo is None:
        delivery_dt = delivery_dt.replace(tzinfo=timezone.utc)
    # Iter 322c — Source is the unified catering_config collection (the
    # admin UI in Resources-Setup writes here).
    default_cfg = await db.catering_config.find_one(
        {"_id": "default"}, {"_id": 0, "default_lead_time_min": 1}
    )
    global_lead_min = int((default_cfg or {}).get("default_lead_time_min") or 60)
    max_lead = global_lead_min
    worst_item: Optional[str] = None
    for ln in cr.items:
        it = items_idx.get(ln.item_id)
        lt = int((it or {}).get("lead_time_min") or global_lead_min)
        if lt > max_lead:
            max_lead = lt
            worst_item = (it or {}).get("name") or ln.item_id
    mins_until = int((delivery_dt - datetime.now(timezone.utc)).total_seconds() // 60)
    lead_time_breach = mins_until < max_lead
    if lead_time_breach:
        await db.catering_requests.update_one(
            {"request_id": cr.request_id},
            {"$set": {
                "lead_time_breach": True,
                "lead_time_required_min": max_lead,
                "lead_time_available_min": mins_until,
                "lead_time_worst_item": worst_item,
            }},
        )

    # Build human-readable line summary + task description
    line_lines = []
    for ln in cr.items:
        it = items_idx.get(ln.item_id)
        label = it.get("name") if it else ln.item_id
        unit = it.get("unit") if it else ""
        line_lines.append(f"  • {ln.quantity} × {label} ({unit})")
    task_description = (
        f"Catering-Anfrage für Buchung am {fallback_start_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"Raum/Teilbereich: {resource.get('name')}\n"
        f"Lieferort: {cr.delivery_target or 'Hauptraum'}\n"
        f"Bereitstellung: {(cr.delivery_at or fallback_start_at).strftime('%d.%m.%Y %H:%M')}\n"
        f"Buchender: {user.get('name', user.get('email', ''))}\n"
        f"Ansprechpartner: {cr.contact or '-'}\n"
        f"Konto: {cr.account or '-'} · Kostenstelle: {cr.cost_center or '-'}\n"
        f"Artikel:\n" + ("\n".join(line_lines) or "  (keine)")
        + (f"\nNotiz: {cr.notes}" if cr.notes else "")
    )
    catering_assignees: list[str] = []
    async for u in db.users.find(
        {"$or": [{"cap_grants": "catering.process"}, {"role": "admin"}]},
        {"_id": 0, "user_id": 1},
    ).limit(20):
        catering_assignees.append(u["user_id"])
    task_doc: dict[str, Any] = {
        "task_id": f"task_{uuid.uuid4().hex[:12]}",
        "title": f"Catering: {booking.title} ({resource.get('name')})",
        "description": task_description,
        "status": "todo",
        "priority": "normal",
        "due_date": cr.delivery_at.isoformat() if cr.delivery_at else None,
        "created_by": user["user_id"],
        "assignee_ids": catering_assignees,
        "tags": ["catering", "auto-created"],
        "source_type": "catering_request",
        "source_id": cr.request_id,
        "attachments": cr.attachments,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.tasks.insert_one(task_doc)
    await db.catering_requests.update_one(
        {"request_id": cr.request_id}, {"$set": {"task_id": task_doc["task_id"]}}
    )
    await db.resource_bookings.update_one(
        {"booking_id": booking.booking_id}, {"$set": {"catering_request_id": cr.request_id}}
    )

    # P0 #2 — notify catering team about the new request.
    # Iter 342 — Fire-and-forget so the POST response returns to the user
    # in <100 ms even when the mailer is slow / the SMTP timeout fires.
    asyncio.create_task(notify_catering_team(cr, resource, booking))

    # Iter 322b — Additional urgency e-mail when lead-time is breached.
    if lead_time_breach and catering_assignees:
        async def _short_notice_safe():
            try:
                await _send_short_notice_email(
                    cr=cr, booking=booking, resource=resource,
                    assignee_ids=catering_assignees,
                    required_min=max_lead, available_min=mins_until,
                    worst_item=worst_item, line_summary=line_lines,
                )
            except Exception as e:
                logging.warning(f"[catering] short-notice email failed: {e}")
        asyncio.create_task(_short_notice_safe())

    lead_time_warning = None
    if lead_time_breach:
        lead_time_warning = {
            "breach": True,
            "required_min": max_lead,
            "available_min": mins_until,
            "worst_item": worst_item,
        }

    return cr.request_id, lead_time_warning
