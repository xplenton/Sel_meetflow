"""Booking invoice aggregator.

Extracted from `routes/resources/invoices.py` in iter 350.

Public API:
    `compute_booking_invoice_aggregate(cost_center, account, from_date,
                                      to_date, booking_ids)` -> dict

Returns the same dict shape as the legacy `/resource-bookings/invoices/
aggregate` route handler. Both the JSON and PDF routes now share this
single source of truth — previously the PDF endpoint called the JSON
route handler directly which broke because of the `Depends`-arg shifting
(the 5th positional arg got assigned to `booking_ids` and `user` kept
its `Depends` default).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from database import db
from routes.resources._common import _parse_iso


async def compute_booking_invoice_aggregate(
    cost_center: Optional[str] = None,
    account: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    booking_ids: Optional[str] = None,
) -> dict:
    """Aggregate billable positions (Catering + Vehicle-km) per cost
    center / account in a date range.

    See `aggregate_booking_invoice` route handler for the full docstring;
    behaviour is byte-identical.
    """
    q: dict = {"status": {"$in": ["confirmed", "completed"]}}
    if cost_center:
        q["cost_center"] = cost_center
    if account:
        q["account"] = account
    # Iter 339 — Issue #6: see route docstring for the date-range fix.
    if from_date:
        q.setdefault("start_at", {})["$gte"] = _parse_iso(from_date)
    if to_date:
        to_dt = _parse_iso(to_date)
        if "T" not in to_date:
            to_dt = to_dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        q.setdefault("start_at", {})["$lte"] = to_dt
    if booking_ids:
        ids = [b.strip() for b in booking_ids.split(",") if b.strip()]
        if ids:
            q["booking_id"] = {"$in": ids}

    # Iter 332 — exclude bookings already attached to a non-void invoice.
    if not booking_ids:
        invoiced_ids = await db.invoices.distinct(
            "booking_id",
            {"status": {"$ne": "void"}, "booking_id": {"$ne": None}},
        )
        agg_ids: set = set()
        async for inv in db.invoices.find(
            {"status": {"$ne": "void"}, "snapshot.bookings": {"$exists": True}},
            {"_id": 0, "snapshot.bookings": 1},
        ):
            for b in (inv.get("snapshot") or {}).get("bookings", []) or []:
                if b.get("booking_id"):
                    agg_ids.add(b["booking_id"])
        invoiced_ids = list(set(invoiced_ids) | agg_ids)
        if invoiced_ids:
            q["booking_id"] = {"$nin": invoiced_ids}

    items_idx = {i["item_id"]: i for i in
                 await db.catering_items.find({}, {"_id": 0}).to_list(500)}
    res_idx = {r["resource_id"]: r for r in
               await db.resources.find({}, {"_id": 0, "resource_id": 1, "name": 1, "type": 1}).to_list(2000)}

    catering_agg: dict = {}
    km_total_km = 0
    km_total_eur = 0.0
    km_rate = float(os.environ.get("BILLING_KM_RATE", "0.30"))
    bookings_seen = 0
    booking_summaries = []

    async for bk in db.resource_bookings.find(q, {"_id": 0}):
        bookings_seen += 1
        res = res_idx.get(bk["resource_id"], {})
        booking_total = 0.0
        booking_lines: list = []

        # Vehicle km
        if res.get("type") == "vehicle" and bk.get("mileage_after") and bk.get("mileage_before"):
            km = int(bk["mileage_after"]) - int(bk["mileage_before"])
            if km > 0:
                eur = round(km * km_rate, 2)
                km_total_km += km
                km_total_eur += eur
                booking_total += eur
                booking_lines.append({
                    "kind": "km",
                    "label": f"Fahrtkilometer ({km_rate:.2f} EUR/km)",
                    "unit": "km",
                    "unit_price": km_rate,
                    "quantity": km,
                    "subtotal": eur,
                })

        # Catering
        if bk.get("catering_request_id"):
            cr = await db.catering_requests.find_one({"request_id": bk["catering_request_id"]}, {"_id": 0})
            if cr and cr.get("status") not in ("rejected", "cancelled"):
                for ln in cr.get("items", []):
                    it = items_idx.get(ln.get("item_id"))
                    if not it:
                        continue
                    key = it["item_id"]
                    qty = int(ln.get("quantity", 0))
                    price = float(it.get("price", 0))
                    eur = round(qty * price, 2)
                    booking_total += eur
                    booking_lines.append({
                        "kind": "catering",
                        "label": it.get("name"),
                        "unit": it.get("unit"),
                        "unit_price": price,
                        "quantity": qty,
                        "subtotal": eur,
                    })
                    if key not in catering_agg:
                        catering_agg[key] = {
                            "kind": "catering",
                            "label": it.get("name"),
                            "unit": it.get("unit"),
                            "unit_price": price,
                            "quantity": 0,
                            "subtotal": 0.0,
                        }
                    catering_agg[key]["quantity"] += qty
                    catering_agg[key]["subtotal"] = round(
                        catering_agg[key]["quantity"] * catering_agg[key]["unit_price"], 2
                    )

        if booking_total > 0:
            booking_summaries.append({
                "booking_id": bk["booking_id"],
                "title": bk.get("title"),
                "resource_name": res.get("name"),
                "resource_type": res.get("type"),
                "start_at": bk["start_at"].isoformat() if isinstance(bk.get("start_at"), datetime) else bk.get("start_at"),
                "cost_center": bk.get("cost_center"),
                "subtotal": round(booking_total, 2),
                "lines": booking_lines,
            })

    lines = sorted(catering_agg.values(), key=lambda x: -x["subtotal"])
    if km_total_km > 0:
        lines.append({
            "kind": "km",
            "label": f"Fahrtkilometer ({km_rate:.2f} EUR/km)",
            "unit": "km",
            "unit_price": km_rate,
            "quantity": km_total_km,
            "subtotal": round(km_total_eur, 2),
        })
    total = round(sum(ln["subtotal"] for ln in lines), 2)

    return {
        "cost_center": cost_center,
        "account": account,
        "from_date": from_date,
        "to_date": to_date,
        "booking_count": bookings_seen,
        "lines": lines,
        "bookings": sorted(booking_summaries, key=lambda b: b.get("start_at") or ""),
        "total": total,
        "currency": os.environ.get("BILLING_CURRENCY", "EUR"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
