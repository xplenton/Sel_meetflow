"""
Resources package — sub-module invoices.
Split out from the original monolithic routes/resources.py in iter 234.
Helpers, models and `db` live in `_common`.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone
import os
from database import db
from dependencies import get_current_user
from services.permissions import require_cap, has_cap

# Shared helpers + models + type aliases from _common
from ._common import (
    BookingStatus, CateringStatus,
    _audit_booking,
    _parse_iso, _csv_line, _build_invoice_pdf,
    _build_xlsx,
)

router = APIRouter(tags=["resources-invoices"])

@router.get("/resource-bookings/{booking_id}/invoice")
async def booking_invoice(booking_id: str, user=Depends(get_current_user)):
    """Return an itemised cost breakdown (catering + vehicle km).

    A simple internal-billing helper. The frontend renders it as a printable
    summary; later sprints can persist real invoices.
    """
    await require_cap(user, "bookings.invoice", db)
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    res = await db.resources.find_one({"resource_id": bk["resource_id"]}, {"_id": 0}) or {}

    lines = []
    total = 0.0

    # Vehicle km charge — €0.30/km default if mileage_before/after present
    if res.get("type") == "vehicle" and bk.get("mileage_after") and bk.get("mileage_before"):
        km = int(bk["mileage_after"]) - int(bk["mileage_before"])
        if km > 0:
            rate = float(os.environ.get("BILLING_KM_RATE", "0.30"))
            sub = round(km * rate, 2)
            lines.append({
                "kind": "km",
                "label": f"Fahrtkilometer ({km} km × {rate:.2f} EUR)",
                "quantity": km, "unit": "km", "unit_price": rate, "subtotal": sub,
            })
            total += sub

    # Catering items
    if bk.get("catering_request_id"):
        cr = await db.catering_requests.find_one({"request_id": bk["catering_request_id"]}, {"_id": 0})
        if cr:
            items_index = {i["item_id"]: i for i in
                           await db.catering_items.find({}, {"_id": 0}).to_list(500)}
            for line in cr.get("items", []):
                it = items_index.get(line.get("item_id"))
                if not it:
                    continue
                qty = int(line.get("quantity", 0))
                price = float(it.get("price", 0))
                sub = round(qty * price, 2)
                lines.append({
                    "kind": "catering",
                    "label": it.get("name"),
                    "quantity": qty,
                    "unit": it.get("unit"),
                    "unit_price": price,
                    "subtotal": sub,
                })
                total += sub

    return {
        "booking_id": booking_id,
        "resource_name": res.get("name"),
        "title": bk.get("title"),
        "cost_center": bk.get("cost_center"),
        "account": bk.get("account"),
        "lines": lines,
        "currency": os.environ.get("BILLING_CURRENCY", "EUR"),
        "total": round(total, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }



# ============================================================================
# Sprint 4 helpers (P0 #2 catering notifications, P0 #5 exports, P0 #6 ICS,
# P1 #10 reminders, P1 #11 per-resource calendar, P1 #13 image/QR upload)
# ============================================================================

@router.get("/resource-bookings/export/csv")
async def export_bookings_csv(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[BookingStatus] = None,
    resource_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    """CSV export of all bookings in a given window (admin/manager)."""
    from fastapi.responses import PlainTextResponse
    if not await has_cap(user, "resources.view_all_bookings", db):
        raise HTTPException(403, "Kein Zugriff")
    q: dict = {}
    if status:
        q["status"] = status
    if resource_id:
        q["resource_id"] = resource_id
    if from_date:
        q["end_at"] = {"$gte": _parse_iso(from_date)}
    if to_date:
        q.setdefault("start_at", {})["$lte"] = _parse_iso(to_date)

    items = await db.resource_bookings.find(q, {"_id": 0}).sort("start_at", -1).to_list(5000)
    res_idx = {r["resource_id"]: r for r in
               await db.resources.find({}, {"_id": 0, "resource_id": 1, "name": 1, "type": 1}).to_list(1000)}

    body = _csv_line(["booking_id", "resource_id", "resource_name", "resource_type",
                      "title", "user_id", "booked_for_user_id", "start_at", "end_at",
                      "status", "cost_center", "account", "destination",
                      "mileage_before", "mileage_after", "catering_request_id"])
    for b in items:
        r = res_idx.get(b["resource_id"], {})
        body += _csv_line([
            b.get("booking_id"), b.get("resource_id"), r.get("name"), r.get("type"),
            b.get("title"), b.get("user_id"), b.get("booked_for_user_id"),
            b.get("start_at").isoformat() if isinstance(b.get("start_at"), datetime) else b.get("start_at"),
            b.get("end_at").isoformat() if isinstance(b.get("end_at"), datetime) else b.get("end_at"),
            b.get("status"), b.get("cost_center"), b.get("account"),
            b.get("destination"), b.get("mileage_before"), b.get("mileage_after"),
            b.get("catering_request_id"),
        ])
    return PlainTextResponse(
        content=body, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bookings.csv"'},
    )


@router.get("/catering-requests/export/csv")
async def export_catering_csv(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    status: Optional[CateringStatus] = None,
    user=Depends(get_current_user),
):
    """CSV export of catering requests (cost-centre billing aid)."""
    from fastapi.responses import PlainTextResponse
    await require_cap(user, "bookings.invoice", db)
    q: dict = {}
    if status:
        q["status"] = status
    if from_date:
        q["created_at"] = {"$gte": _parse_iso(from_date)}
    if to_date:
        q.setdefault("created_at", {})["$lte"] = _parse_iso(to_date)
    items = await db.catering_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    items_idx = {i["item_id"]: i for i in
                 await db.catering_items.find({}, {"_id": 0}).to_list(500)}

    body = _csv_line(["request_id", "booking_id", "status", "user_id",
                      "delivery_at", "delivery_target", "cost_center", "account",
                      "item_name", "quantity", "unit_price", "line_total"])
    for cr in items:
        for ln in cr.get("items", []):
            it = items_idx.get(ln.get("item_id"), {})
            qty = int(ln.get("quantity", 0))
            price = float(it.get("price", 0))
            body += _csv_line([
                cr.get("request_id"), cr.get("booking_id"), cr.get("status"), cr.get("user_id"),
                cr.get("delivery_at").isoformat() if isinstance(cr.get("delivery_at"), datetime) else cr.get("delivery_at"),
                cr.get("delivery_target"), cr.get("cost_center"), cr.get("account"),
                it.get("name") or ln.get("item_id"), qty, price, round(qty * price, 2),
            ])
    return PlainTextResponse(
        content=body, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="catering.csv"'},
    )


# ----- P0 #6: ICS export ----------------------------------------------------
@router.get("/resource-bookings/{booking_id}/ical")
async def booking_ical(booking_id: str, user=Depends(get_current_user)):
    """Generate a single VEVENT iCal file for a booking."""
    from fastapi.responses import PlainTextResponse
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    bk = await db.resource_bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Buchung nicht gefunden")
    res = await db.resources.find_one({"resource_id": bk["resource_id"]}, {"_id": 0}) or {}

    def _ics_dt(d):
        if isinstance(d, str):
            d = _parse_iso(d)
        return d.strftime("%Y%m%dT%H%M%SZ")

    summary = bk.get("title", "Buchung").replace("\n", " ")
    location = res.get("name", "")
    description = (bk.get("description") or "").replace("\n", "\\n")
    uid = f"booking-{booking_id}@meetflow"
    ical = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//MeetFlow//Resource Booking//DE\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{_ics_dt(datetime.now(timezone.utc))}\r\n"
        f"DTSTART:{_ics_dt(bk['start_at'])}\r\n"
        f"DTEND:{_ics_dt(bk['end_at'])}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"LOCATION:{location}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"STATUS:{'CONFIRMED' if bk.get('status') == 'confirmed' else 'TENTATIVE'}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return PlainTextResponse(
        content=ical, media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="booking_{booking_id}.ics"'},
    )


# ----- P1 #11: per-resource calendar window --------------------------------
@router.get("/resource-bookings/{booking_id}/invoice.pdf")
async def booking_invoice_pdf(booking_id: str, user=Depends(get_current_user)):
    """Polished A4 PDF version of the single-booking invoice."""
    from fastapi.responses import Response
    await require_cap(user, "bookings.invoice", db)
    # Re-use the JSON invoice endpoint's logic by calling it directly.
    invoice = await booking_invoice(booking_id, user)
    pdf = _build_invoice_pdf(
        title=f"Rechnung {booking_id}",
        subtitle=f"{invoice.get('resource_name', '')} &middot; {invoice.get('title', '')}",
        header_info=[
            ("Buchung", booking_id),
            ("Ressource", invoice.get("resource_name")),
            ("Titel", invoice.get("title")),
            ("Kostenstelle", invoice.get("cost_center")),
            ("Konto", invoice.get("account")),
            ("Datum", invoice.get("generated_at", "")[:10]),
        ],
        lines=invoice.get("lines", []),
        total=float(invoice.get("total", 0)),
        currency=invoice.get("currency", "EUR"),
    )
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice_{booking_id}.pdf"'},
    )


@router.get("/catering-requests/invoices/aggregate")
async def aggregate_catering_invoice(
    cost_center: Optional[str] = None,
    account: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Sammelrechnung: aggregate all catering line items for a cost-centre /
    account in the given window. Returns JSON; use .pdf endpoint for PDF.

    Only includes catering requests in `confirmed`, `delivered` or `completed`
    states (`rejected` and `cancelled` are excluded).
    """
    await require_cap(user, "bookings.invoice", db)

    q: dict = {"status": {"$in": ["confirmed", "delivered", "completed", "in_progress"]}}
    if cost_center:
        q["cost_center"] = cost_center
    if account:
        q["account"] = account
    if from_date:
        q.setdefault("created_at", {})["$gte"] = _parse_iso(from_date)
    if to_date:
        q.setdefault("created_at", {})["$lte"] = _parse_iso(to_date)

    items_idx = {i["item_id"]: i for i in
                 await db.catering_items.find({}, {"_id": 0}).to_list(500)}

    aggregated: dict = {}  # item_id -> {label, unit, unit_price, quantity, subtotal}
    requests_count = 0
    aggregated_request_ids: list = []  # Iter 400 — Back-Link für Catering-Auswertung
    async for cr in db.catering_requests.find(q, {"_id": 0}):
        requests_count += 1
        if cr.get("request_id"):
            aggregated_request_ids.append(cr["request_id"])
        for ln in cr.get("items", []):
            it = items_idx.get(ln.get("item_id"))
            if not it:
                continue
            key = it["item_id"]
            if key not in aggregated:
                aggregated[key] = {
                    "label": it.get("name"),
                    "unit": it.get("unit"),
                    "unit_price": float(it.get("price", 0)),
                    "quantity": 0,
                    "subtotal": 0.0,
                }
            qty = int(ln.get("quantity", 0))
            aggregated[key]["quantity"] += qty
            aggregated[key]["subtotal"] = round(
                aggregated[key]["quantity"] * aggregated[key]["unit_price"], 2
            )

    lines = sorted(aggregated.values(), key=lambda x: -x["subtotal"])
    total = round(sum(ln["subtotal"] for ln in lines), 2)

    return {
        "cost_center": cost_center,
        "account": account,
        "from_date": from_date,
        "to_date": to_date,
        "request_count": requests_count,
        "aggregated_request_ids": aggregated_request_ids,
        "lines": lines,
        "total": total,
        "currency": os.environ.get("BILLING_CURRENCY", "EUR"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/catering-requests/invoices/aggregate.pdf")
async def aggregate_catering_invoice_pdf(
    cost_center: Optional[str] = None,
    account: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Sammelrechnung as a polished A4 PDF."""
    from fastapi.responses import Response
    agg = await aggregate_catering_invoice(cost_center, account, from_date, to_date, user)
    period = "alle Zeitraeume"
    if from_date or to_date:
        period = f"{(from_date or '...')[:10]} &ndash; {(to_date or '...')[:10]}"
    pdf = _build_invoice_pdf(
        title="Sammelrechnung Catering",
        subtitle=f"Kostenstelle: {cost_center or '—'} &middot; Zeitraum: {period}",
        header_info=[
            ("Kostenstelle", cost_center),
            ("Konto", account),
            ("Zeitraum", period),
            ("Anfragen", agg["request_count"]),
        ],
        lines=agg["lines"],
        total=agg["total"],
        currency=agg["currency"],
    )
    filename = f"sammelrechnung_{cost_center or 'alle'}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================================
# Iter 227 — 2D floor-plan / desk-map endpoints
# ============================================================================

@router.get("/resource-bookings/export/xlsx")
async def export_bookings_xlsx(
    from_date: Optional[str] = None, to_date: Optional[str] = None,
    status: Optional[BookingStatus] = None,
    user=Depends(get_current_user),
):
    from fastapi.responses import Response
    if not await has_cap(user, "resources.view_all_bookings", db):
        raise HTTPException(403, "Kein Zugriff")
    q: dict = {}
    if status:
        q["status"] = status
    if from_date:
        q["end_at"] = {"$gte": _parse_iso(from_date)}
    if to_date:
        q.setdefault("start_at", {})["$lte"] = _parse_iso(to_date)
    items = await db.resource_bookings.find(q, {"_id": 0}).sort("start_at", -1).to_list(5000)
    res_idx = {r["resource_id"]: r for r in
               await db.resources.find({}, {"_id": 0, "resource_id": 1, "name": 1, "type": 1}).to_list(1000)}
    rows = []
    for b in items:
        r = res_idx.get(b["resource_id"], {})
        rows.append([
            b.get("booking_id"), r.get("name"), r.get("type"), b.get("title"),
            b.get("user_id"),
            b["start_at"].isoformat() if isinstance(b.get("start_at"), datetime) else b.get("start_at"),
            b["end_at"].isoformat() if isinstance(b.get("end_at"), datetime) else b.get("end_at"),
            b.get("status"), b.get("cost_center"), b.get("account"),
        ])
    data = _build_xlsx(
        rows,
        ["Buchung", "Ressource", "Typ", "Titel", "User", "Von", "Bis", "Status", "Kostenstelle", "Konto"],
        "bookings.xlsx",
    )
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="bookings.xlsx"'})


@router.get("/resource-bookings/invoices/aggregate")
async def aggregate_booking_invoice(
    cost_center: Optional[str] = None,
    account: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    booking_ids: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Iter 284 — Booking-Sammelrechnung: aggregiert ALLE abrechenbaren
    Posten (Catering + Fahrtkilometer) je Kostenstelle/Account in einem
    Zeitraum.

    Im Gegensatz zur reinen Catering-Aggregation (`/catering-requests/
    invoices/aggregate`) deckt diese Variante auch Fahrzeug-km mit ab und
    ist die zentrale Quelle der "Rechnungen"-Seite im Frontend.

    Iter 330 — Per-Buchungs-Positionen werden jetzt ebenfalls geliefert
    (`bookings[i].lines`), damit die UI eine "Buchungen mit Positionen"
    Ansicht rendern kann. Außerdem akzeptiert die Funktion `booking_ids`
    (CSV) als Filter — so kann der User aus mehreren Buchungen eine
    Sammelrechnung aus expliziter Auswahl erzeugen.

    Iter 350 — Body in `services.booking_aggregator` ausgelagert, damit
    der PDF-Endpoint dieselbe Logik aufrufen kann ohne dass `Depends`
    in den Positional-Args verrutscht.
    """
    await require_cap(user, "bookings.invoice", db)
    from services.booking_aggregator import compute_booking_invoice_aggregate
    return await compute_booking_invoice_aggregate(
        cost_center=cost_center, account=account,
        from_date=from_date, to_date=to_date, booking_ids=booking_ids,
    )


@router.get("/resource-bookings/invoices/aggregate.pdf")
async def aggregate_booking_invoice_pdf(
    cost_center: Optional[str] = None,
    account: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Iter 284 — Booking-Sammelrechnung als PDF (Catering + Fahrtkilometer).

    Iter 350 — calls the shared aggregator service so the result is
    identical to /resource-bookings/invoices/aggregate. Previously this
    endpoint called the JSON route function directly which broke under
    FastAPI's Depends() resolution.
    """
    from fastapi.responses import Response
    await require_cap(user, "bookings.invoice", db)
    from services.booking_aggregator import compute_booking_invoice_aggregate
    agg = await compute_booking_invoice_aggregate(
        cost_center=cost_center, account=account,
        from_date=from_date, to_date=to_date,
    )
    period = "alle Zeitraeume"
    if from_date or to_date:
        period = f"{(from_date or '...')[:10]} &ndash; {(to_date or '...')[:10]}"
    pdf = _build_invoice_pdf(
        title="Sammelrechnung Ressourcen",
        subtitle=f"Kostenstelle: {cost_center or 'alle'} &middot; Zeitraum: {period}",
        header_info=[
            ("Kostenstelle", cost_center),
            ("Konto", account),
            ("Zeitraum", period),
            ("Buchungen", agg["booking_count"]),
        ],
        lines=agg["lines"],
        total=agg["total"],
        currency=agg["currency"],
    )
    filename = f"sammelrechnung_buchungen_{cost_center or 'alle'}.pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----- P1 §13 — Invoice approval workflow -----------------------------------
@router.post("/catering-requests/{request_id}/invoice/approve")
async def approve_catering_invoice(request_id: str, payload: Optional[dict] = None, user=Depends(get_current_user)):
    """Freigabe einer Catering-Rechnung vor Versand an Buchhaltung.
    Markiert request mit invoice_approved=true|false + Audit-Eintrag."""
    await require_cap(user, "bookings.invoice", db)
    cr = await db.catering_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not cr:
        raise HTTPException(404, "Anfrage nicht gefunden")
    if cr.get("status") in ("rejected", "cancelled"):
        raise HTTPException(400, "Abgelehnte/stornierte Anfragen können nicht abgerechnet werden")
    decision = (payload or {}).get("decision", "approve")
    update = {
        "invoice_approved": decision == "approve",
        "invoice_approved_by": user["user_id"],
        "invoice_approved_at": datetime.now(timezone.utc),
        "invoice_note": (payload or {}).get("note"),
    }
    await db.catering_requests.update_one({"request_id": request_id}, {"$set": update})
    await _audit_booking(user, cr.get("booking_id", request_id), f"invoice_{decision}", {
        "request_id": request_id, "note": update.get("invoice_note"),
    })
    return {"request_id": request_id, **update,
            "invoice_approved_at": update["invoice_approved_at"].isoformat()}


# ----- P1 §14 — Favorite desks ---------------------------------------------
@router.get("/resource-bookings/export/erp.csv")
async def erp_export_csv(
    days: int = 90,
    format: str = "datev",
    user=Depends(get_current_user),
):
    """Exportiert freigegebene Catering-Rechnungen im DATEV-Buchungsstapel-Format.
    Spalten: Belegdatum;Belegnummer;Konto;Gegenkonto;Betrag;Buchungstext;
             Kostenstelle;USt-Schluessel
    `format=datev` (default) liefert das DATEV-Standardformat (Semikolon getrennt).
    """
    await require_cap(user, "bookings.invoice", db)
    from datetime import timedelta as _td
    import csv as _csv
    import io as _io
    from fastapi.responses import StreamingResponse

    window_start = datetime.now(timezone.utc) - _td(days=days)
    # Items lookup fuer Preise/Namen
    items_idx = {i["item_id"]: i for i in await db.catering_items.find(
        {}, {"_id": 0}).to_list(500)}
    requests = await db.catering_requests.find(
        {"created_at": {"$gte": window_start},
         "invoice_approved": True},
        {"_id": 0},
    ).sort("created_at", 1).to_list(2000)

    buf = _io.StringIO()
    writer = _csv.writer(buf, delimiter=";", quoting=_csv.QUOTE_MINIMAL)
    if format == "datev":
        writer.writerow([
            "Belegdatum", "Belegnummer", "Konto", "Gegenkonto",
            "Betrag", "Buchungstext", "Kostenstelle", "USt-Schlüssel",
        ])
    else:  # generic
        writer.writerow([
            "Datum", "Beleg", "Soll", "Haben", "Betrag (EUR)",
            "Buchungstext", "Kostenstelle", "Steuer",
        ])
    for cr in requests:
        # Summe je Anfrage = sum(item.price * line.quantity)
        amount = 0.0
        for ln in cr.get("items", []):
            it = items_idx.get(ln.get("item_id"))
            if it:
                amount += float(it.get("price") or 0.0) * int(ln.get("quantity") or 0)
        dt = cr.get("invoice_approved_at") or cr.get("created_at")
        if isinstance(dt, datetime):
            dt_str = dt.strftime("%d.%m.%Y")
        else:
            dt_str = str(dt or "")[:10]
        writer.writerow([
            dt_str,
            cr.get("request_id", "")[:12],
            cr.get("account", "8400"),         # Konto (Default: Erloese)
            "1200",                              # Gegenkonto Bank/Verrechnung
            f"{amount:.2f}".replace(".", ","),  # DATEV Komma-Format
            f"Catering {cr.get('request_id', '')[:8]}",
            cr.get("cost_center", ""),
            "19",                                # USt-Schluessel (DATEV: 19% = 9)
        ])
    csv_bytes = "\ufeff" + buf.getvalue()  # BOM fuer Excel
    return StreamingResponse(
        iter([csv_bytes.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename=erp-export-{format}-{days}d.csv"},
    )


# ----- §14 — Lageplan-Metadaten + Hintergrundbild ---------------------------
