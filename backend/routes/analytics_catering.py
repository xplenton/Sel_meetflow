"""
Iter 397 — Analytics: Catering-Verbrauch-Historie.

Aggregiert verbrauchte Catering-Artikel ueber alle Anfragen mit Filtern
(Zeitraum + Status) und gibt eine flache Item-pro-Zeile Liste zurueck.
Pro Zeile: Item, Menge, Lieferzeit, Buchung (Titel/Raum), Anforderer,
Kostenstelle, Status, Rechnungs-ID (falls vorhanden).

Auth: erfordert Capability `analytics.view_catering_history`. Damit
koennen Admins die Sicht via Rollen-/Gruppen-Matrix an z.B. Catering-
Manager, Buchhaltung etc. delegieren.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timezone, timedelta
from database import db
from dependencies import get_current_user
from services.permissions import require_cap

router = APIRouter(tags=["analytics-catering"])


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Accept "YYYY-MM-DD" + full ISO
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


@router.get("/analytics/catering-history")
async def catering_history(
    range: str = Query("all", description="all | week | month | custom"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    status: Optional[str] = Query(None, description="comma-separated list of catering statuses (e.g. delivered,completed)"),
    user=Depends(get_current_user),
):
    """Liefert flache Liste verbrauchter Catering-Items.

    Filter-Logik:
      range=all     → keine Zeitgrenze
      range=week    → letzte 7 Tage ab jetzt
      range=month   → letzte 30 Tage ab jetzt
      range=custom  → date_from/date_to (UTC, inkl. Tagesgrenze)
    """
    await require_cap(user, "analytics.view_catering_history", db)
    # Build date filter on delivery_at
    now = datetime.now(timezone.utc)
    dt_from: Optional[datetime] = None
    dt_to: Optional[datetime] = None
    if range == "week":
        dt_from = now - timedelta(days=7)
    elif range == "month":
        dt_from = now - timedelta(days=30)
    elif range == "custom":
        dt_from = _parse_dt(date_from)
        dt_to = _parse_dt(date_to)
        if dt_to:
            # inkl. ganzer Endtag (23:59:59)
            dt_to = dt_to.replace(hour=23, minute=59, second=59)

    mongo_q: dict = {}
    # Iter 400 — Date-Filter auf `created_at` umgestellt (vorher: delivery_at).
    # Die Sammelrechnung (`aggregate_catering_invoice`) filtert ebenfalls auf
    # `created_at` — damit Catering-Auswertung und Rechnung deckungsgleich sind.
    if dt_from or dt_to:
        df: dict = {}
        if dt_from:
            df["$gte"] = dt_from
        if dt_to:
            df["$lte"] = dt_to
        mongo_q["created_at"] = df
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            mongo_q["status"] = {"$in": statuses}

    requests = await db.catering_requests.find(mongo_q, {"_id": 0}).sort("delivery_at", -1).limit(2000).to_list(2000)

    # Resolve referenced data once (item names, bookings, resources, users, invoices)
    item_ids = {ln.get("item_id") for cr in requests for ln in (cr.get("items") or []) if ln.get("item_id")}
    booking_ids = {cr.get("booking_id") for cr in requests if cr.get("booking_id")}
    user_ids = {cr.get("user_id") for cr in requests if cr.get("user_id")}
    request_ids = {cr.get("request_id") for cr in requests if cr.get("request_id")}

    items_idx = {
        i["item_id"]: i for i in await db.catering_items.find(
            {"item_id": {"$in": list(item_ids)}}, {"_id": 0}
        ).to_list(1000) if item_ids
    } if item_ids else {}
    bookings_idx = {
        b["booking_id"]: b for b in await db.resource_bookings.find(
            {"booking_id": {"$in": list(booking_ids)}}, {"_id": 0}
        ).to_list(2000) if booking_ids
    } if booking_ids else {}
    resource_ids = {b.get("resource_id") for b in bookings_idx.values() if b.get("resource_id")}
    resources_idx = {
        r["resource_id"]: r for r in await db.resources.find(
            {"resource_id": {"$in": list(resource_ids)}}, {"_id": 0}
        ).to_list(2000) if resource_ids
    } if resource_ids else {}
    users_idx = {
        u["user_id"]: u for u in await db.users.find(
            {"user_id": {"$in": list(user_ids)}}, {"_id": 0}
        ).to_list(2000) if user_ids
    } if user_ids else {}
    # Iter 400 — Invoices liegen in `db.invoices` (kind=catering_aggregate),
    # NICHT in `bookings_invoiced` (das war ein veralteter/leerer Collection-
    # Name). Wir bauen einen Back-Index: request_id → invoice.
    # Aggregate-Rechnungen ohne `aggregated_request_ids` (Legacy vor Iter 400)
    # koennen nicht zuverlaessig backgemappt werden — diese Zeilen zeigen „—".
    invoices_idx: dict = {}
    if request_ids:
        async for inv in db.invoices.find(
            {"kind": "catering_aggregate", "snapshot.aggregated_request_ids": {"$in": list(request_ids)}},
            {"_id": 0, "invoice_id": 1, "invoice_number": 1, "status": 1, "snapshot.aggregated_request_ids": 1}
        ):
            for rid in (inv.get("snapshot", {}).get("aggregated_request_ids") or []):
                invoices_idx[rid] = {
                    "invoice_id": inv.get("invoice_id"),
                    "invoice_number": inv.get("invoice_number"),
                    "status": inv.get("status"),
                }

    # Flatten to one row per consumed item
    rows = []
    for cr in requests:
        bk = bookings_idx.get(cr.get("booking_id")) or {}
        res = resources_idx.get(bk.get("resource_id")) or {}
        req_user = users_idx.get(cr.get("user_id")) or {}
        inv = invoices_idx.get(cr.get("request_id"))
        for ln in (cr.get("items") or []):
            meta = items_idx.get(ln.get("item_id")) or {}
            rows.append({
                "request_id": cr.get("request_id"),
                "delivery_at": cr.get("delivery_at").isoformat() if isinstance(cr.get("delivery_at"), datetime) else cr.get("delivery_at"),
                "status": cr.get("status"),
                "item_id": ln.get("item_id"),
                "item_name": meta.get("name") or ln.get("item_id"),
                "item_unit": meta.get("unit") or ln.get("item_unit") or "Stk",
                "quantity": ln.get("quantity", 0),
                "cost_center": cr.get("cost_center"),
                "account": cr.get("account"),
                "booking_id": cr.get("booking_id"),
                "booking_title": bk.get("title"),
                "resource_name": res.get("name"),
                "resource_building": res.get("building"),
                "resource_floor": res.get("floor"),
                "requester_id": cr.get("user_id"),
                "requester_name": req_user.get("name") or req_user.get("email"),
                "requester_email": req_user.get("email"),
                "invoice_id": inv.get("invoice_id") if inv else None,
                "invoice_number": inv.get("number") if inv else None,
                "invoice_status": inv.get("status") if inv else None,
                "rejection_reason": cr.get("rejection_reason"),
                "notes": cr.get("notes"),
            })

    # Aggregate totals for the summary header
    totals = {
        "row_count": len(rows),
        "total_quantity": sum(r.get("quantity", 0) or 0 for r in rows),
        "requests_total": len(requests),
        "by_status": {},
    }
    for cr in requests:
        s = cr.get("status") or "unknown"
        totals["by_status"][s] = totals["by_status"].get(s, 0) + 1

    return {"rows": rows, "totals": totals, "filter": {
        "range": range, "from": date_from, "to": date_to, "status": status,
    }}
