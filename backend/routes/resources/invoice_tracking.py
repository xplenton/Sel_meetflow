"""
Iter 285 — Invoice tracking + auto-email + Stripe invoicing
=============================================================

This module persists invoice documents into the `invoices` collection so
that the UI can present a "Erstellte Rechnungen" overview with status
tracking (draft → approved → sent → paid). It also exposes:

* `POST /api/invoices`               – snapshot an aggregate/single invoice
* `GET  /api/invoices`               – list with filters
* `GET  /api/invoices/{id}`          – detail
* `GET  /api/invoices/{id}/pdf`      – stored PDF (re-rendered from snapshot)
* `POST /api/invoices/{id}/approve`  – Freigabe
* `POST /api/invoices/{id}/send-email`  – PDF an Buchhaltung (CC-acct-email)
* `POST /api/invoices/{id}/send-stripe` – externe Rechnung via Stripe
* `POST /api/invoices/{id}/void`     – Storno (nur draft/approved)
* `POST /api/stripe-webhook`         – Stripe → invoice.paid → status=paid

Stripe key is read from `STRIPE_API_KEY` env var; webhook secret from
`STRIPE_WEBHOOK_SECRET` (signature verification is skipped if absent —
acceptable in dev, must be configured in prod).
"""

from __future__ import annotations
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import Response

from database import db
from dependencies import get_current_user
from services.permissions import require_cap

logger = logging.getLogger("server")
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


async def _audit(user, invoice_id, action, extra=None):
    try:
        await db.audit_log.insert_one({
            "audit_id": f"al_{uuid.uuid4().hex[:8]}",
            "ts": _now(),
            "user_id": user["user_id"],
            "user_email": user.get("email"),
            "entity": "invoice",
            "entity_id": invoice_id,
            "action": action,
            "extra": extra or {},
        })
    except Exception as e:
        logger.warning("[INVOICE-AUDIT] %s", e)


def _strip_dates(d: dict) -> dict:
    """Convert datetime → ISO so the response is JSON-serialisable."""
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ---------------------------------------------------------------------------
# Iter 327 — Audit-Verlauf für Rechnungen
# ---------------------------------------------------------------------------
# Persists every meaningful mutation to the `invoice_history` collection so
# the buchhaltung can prove who changed what when. Records {invoice_id, ts,
# action, user_*, diff:[{field, before, after}], extra:{}}.

# Field-Label-Mapping für die UI-Anzeige (Backend liefert beides → Frontend
# zeigt das Label, fällt auf den Pfad zurück).
_FIELD_LABELS = {
    "title": "Titel",
    "recipient_name": "Empfänger",
    "recipient_address": "Anschrift",
    "sender_org_unit": "Absender / Org-Einheit",
    "payment_terms": "Zahlungsbedingungen",
    "notes": "Hinweise",
    "external_customer_email": "Kunden-E-Mail",
    "external_customer_name": "Kundenname",
    "template_id": "Vorlage",
    "issue_date": "Rechnungsdatum",
    "service_period_from": "Leistung von",
    "service_period_to": "Leistung bis",
    "cost_center": "Kostenstelle",
    "account": "Konto",
    "cost_object": "Kostenträger",
    "project_code": "Projekt",
    "currency": "Währung",
    "number_range_id": "Nummernkreis",
    "status": "Status",
    "snapshot.lines": "Positionen",
    "snapshot.subtotal_net": "Zwischensumme netto",
    "snapshot.total_tax": "MwSt",
    "snapshot.total_gross": "Gesamtsumme brutto",
    "total": "Betrag",
}


def _truncate_value(v, limit: int = 280):
    """Lange Werte (z.B. Beschreibungen) kürzen, sonst bläht die History."""
    if v is None:
        return None
    if isinstance(v, list):
        # für Positionen nur Anzahl + Summenlabels speichern
        return f"{len(v)} Position(en)"
    s = str(v)
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def _build_diff(before: dict, updates: dict, ignore_keys=("updated_at",)) -> list:
    """Compare the persisted invoice (`before`) with the `$set` payload
    (`updates`) and return a list of changed fields. Skips no-op writes."""
    diff: list[dict] = []
    for path, new_v in updates.items():
        if path in ignore_keys:
            continue
        # walk nested path (e.g. snapshot.lines)
        ref = before
        for part in path.split("."):
            if isinstance(ref, dict):
                ref = ref.get(part)
            else:
                ref = None
                break
        old_v = ref
        if old_v == new_v:
            continue
        diff.append({
            "field": path,
            "label": _FIELD_LABELS.get(path, path),
            "before": _truncate_value(old_v),
            "after": _truncate_value(new_v),
        })
    return diff


async def _history_log(invoice_id: str, action: str, user, diff: list, extra: dict | None = None):
    """Iter 327 — append entry to `invoice_history`. Best-effort: never
    let history errors block the actual update."""
    try:
        await db.invoice_history.insert_one({
            "entry_id": f"ih_{uuid.uuid4().hex[:10]}",
            "invoice_id": invoice_id,
            "ts": _now(),
            "action": action,
            "user_id": (user or {}).get("user_id"),
            "user_email": (user or {}).get("email"),
            "user_name": (user or {}).get("name") or (user or {}).get("email"),
            "diff": diff or [],
            "extra": extra or {},
        })
    except Exception as e:
        logger.warning("[INVOICE-HISTORY] %s", e)


# ---------------------------------------------------------------------------
# Create — snapshot an aggregate / single invoice
# ---------------------------------------------------------------------------

@router.post("/invoices")
async def create_invoice_snapshot(payload: dict, user=Depends(get_current_user)):
    """Snapshot an aggregate or single-booking invoice into the `invoices`
    collection so it appears in the "Erstellte Rechnungen" overview.

    Body:
      kind: "aggregate" | "catering_aggregate" | "single" | "external"
      cost_center, account, from_date, to_date  — for aggregates
      booking_id                                — for single
      external_customer_email, external_customer_name — for external/stripe
      title (optional)
    """
    await require_cap(user, "bookings.invoice", db)

    kind = payload.get("kind") or "aggregate"
    if kind not in ("aggregate", "catering_aggregate", "single", "external"):
        raise HTTPException(400, "Unbekannte Rechnungsart")

    # Resolve snapshot data
    snapshot: dict = {}
    # Iter 366 — Cost-Center für Single + Sammel automatisch aus Buchung
    # ableiten, falls der Aufrufer keinen mitsendet. Vorher landete die KS
    # nicht im Invoice-Doc (Tabelle „Erstellte Rechnungen" → Spalte leer).
    derived_cost_center: Optional[str] = None
    if kind == "single":
        booking_id = payload.get("booking_id")
        if not booking_id:
            raise HTTPException(400, "booking_id required")
        # Iter 366 — `single_booking_invoice` war nie definiert; der Endpoint
        # lieferte deshalb 500. Korrekt: `booking_invoice(booking_id, user)`.
        from routes.resources.invoices import booking_invoice
        snap = await booking_invoice(booking_id, user)
        snapshot = {
            "lines": snap.get("lines", []),
            "total": snap.get("total", 0),
            "currency": snap.get("currency", "EUR"),
            "booking_id": booking_id,
            "booking_title": snap.get("title"),
            "cost_center": snap.get("cost_center"),
        }
        derived_cost_center = snap.get("cost_center")
    elif kind == "catering_aggregate":
        from routes.resources.invoices import aggregate_catering_invoice
        snap = await aggregate_catering_invoice(
            payload.get("cost_center"), payload.get("account"),
            payload.get("from_date"), payload.get("to_date"), user,
        )
        snapshot = {
            "lines": snap.get("lines", []),
            "total": snap.get("total", 0),
            "currency": snap.get("currency", "EUR"),
            "request_count": snap.get("request_count", 0),
            # Iter 400 — Back-Link für Catering-Auswertung („Rechnung"-Spalte)
            "aggregated_request_ids": snap.get("aggregated_request_ids", []),
        }
    else:
        # aggregate (default) — also used for "external" (single booking, Stripe-targeted)
        from routes.resources.invoices import aggregate_booking_invoice
        snap = await aggregate_booking_invoice(
            payload.get("cost_center"), payload.get("account"),
            payload.get("from_date"), payload.get("to_date"),
            # Iter 330 — Sammelrechnung aus explizit gewählten Buchungs-IDs
            booking_ids=",".join(payload.get("booking_ids") or []) or None,
            user=user,
        )
        snapshot = {
            "lines": snap.get("lines", []),
            "bookings": snap.get("bookings", []),
            "total": snap.get("total", 0),
            "currency": snap.get("currency", "EUR"),
            "booking_count": snap.get("booking_count", 0),
        }
        # Iter 366 — Wenn der User aus „Buchungen mit Positionen" einzelne
        # Buchungen auswählt, kommt KEIN `cost_center` im Payload. Wir leiten
        # ihn aus den Buchungen ab: gemeinsame KS aller selektierten Bookings.
        # (Gleiche Logik bei „Sammelrechnung über Zeitraum" wenn der User
        # die KS leer gelassen hat — dann zeigt das Aggregat ggf. nur Buchungen
        # einer einzigen KS.)
        bks_in_snap = snap.get("bookings") or []
        ccs = {b.get("cost_center") for b in bks_in_snap if b.get("cost_center")}
        if len(ccs) == 1:
            derived_cost_center = next(iter(ccs))

    invoice_id = f"inv_{uuid.uuid4().hex[:10]}"

    # Iter 326 — Allocate a human-friendly invoice number for every kind
    # (was previously only generated for manual invoices). The default
    # title falls back to "Rechnung_<Nummer>" so the user no longer sees
    # "Sammelrechnung KS123" in the tracking list.
    template_id = (payload.get("template_id") or "").strip() or None
    template_snapshot = {}
    if template_id and template_id != "__none__":
        tpl = await db.invoice_templates.find_one(
            {"template_id": template_id}, {"_id": 0}
        )
        if not tpl:
            raise HTTPException(404, f"Vorlage {template_id} nicht gefunden")
        template_snapshot = {
            "template_id": tpl["template_id"],
            "template_name": tpl.get("name"),
            "header_text": tpl.get("header_text"),
            "header_format": tpl.get("header_format", "text"),
            "footer_text": tpl.get("footer_text"),
            "footer_format": tpl.get("footer_format", "text"),
            "bank_details": tpl.get("bank_details"),
            "payment_terms_default": tpl.get("payment_terms_default"),
            "sender_org_unit_default": tpl.get("sender_org_unit_default"),
            "logo_storage_path": tpl.get("logo_storage_path"),
            "logo_content_type": tpl.get("logo_content_type"),
            "default_tax_rate": tpl.get("default_tax_rate"),
        }
    snapshot.update(template_snapshot)

    # Iter 326 — Allocate an invoice number from the template's default
    # range (or the global default) so all kinds get a "Rechnung_<num>"
    # title and the buchhaltung sees a consistent numbering across
    # aggregate, catering, single, manual.
    invoice_number: Optional[str] = None
    try:
        from routes.resources.invoices_config import _allocate_number
        range_id = None
        if template_snapshot:
            range_id = (await db.invoice_templates.find_one(
                {"template_id": template_snapshot["template_id"]},
                {"_id": 0, "default_number_range_id": 1},
            ) or {}).get("default_number_range_id")
        _, invoice_number = await _allocate_number(range_id)
    except Exception as e:
        logger.warning("[INVOICE] number allocation failed, falling back to invoice_id: %s", e)

    doc = {
        "invoice_id": invoice_id,
        "kind": kind,
        "invoice_number": invoice_number,
        "title": payload.get("title") or _default_title(kind, payload, invoice_number),
        "template_id": template_id if template_id != "__none__" else None,
        "cost_center": payload.get("cost_center") or derived_cost_center,
        "account": payload.get("account"),
        "from_date": payload.get("from_date"),
        "to_date": payload.get("to_date"),
        "external_customer_email": (payload.get("external_customer_email") or "").strip() or None,
        "external_customer_name": (payload.get("external_customer_name") or "").strip() or None,
        "snapshot": snapshot,
        "status": "draft",
        "created_by": user["user_id"],
        "created_by_email": user.get("email"),
        "created_at": _now(),
    }
    await db.invoices.insert_one(doc)
    doc.pop("_id", None)
    await _audit(user, invoice_id, "created", {"kind": kind, "total": snapshot.get("total")})
    # Iter 327 — Initial-Eintrag im Audit-Verlauf.
    await _history_log(invoice_id, "created", user, [], {
        "kind": kind,
        "invoice_number": invoice_number,
        "title": doc["title"],
    })
    return _strip_dates(doc)


def _default_title(kind: str, payload: dict, invoice_number: Optional[str] = None) -> str:
    # Iter 326 — User-requested default: "Rechnung_<Nummer>" instead of
    # "Sammelrechnung <KS>". Falls allocation failed and no number is
    # available, fall back to a descriptive label.
    if invoice_number:
        return f"Rechnung_{invoice_number}"
    cc = payload.get("cost_center") or "alle"
    if kind == "single":
        return f"Einzelrechnung {payload.get('booking_id', '')}"
    if kind == "catering_aggregate":
        return f"Catering-Sammelrechnung {cc}"
    return f"Sammelrechnung {cc}"


# ---------------------------------------------------------------------------
# List + Detail
# ---------------------------------------------------------------------------

@router.get("/invoices")
async def list_invoices(
    status: Optional[str] = None,
    cost_center: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 100,
    user=Depends(get_current_user),
):
    await require_cap(user, "bookings.invoice", db)
    q: dict = {}
    if status:
        q["status"] = status
    if cost_center:
        q["cost_center"] = cost_center
    if from_date:
        q.setdefault("created_at", {})["$gte"] = datetime.fromisoformat(from_date.replace("Z", "+00:00")) if "T" in from_date else datetime.fromisoformat(from_date + "T00:00:00+00:00")
    if to_date:
        q.setdefault("created_at", {})["$lte"] = datetime.fromisoformat(to_date.replace("Z", "+00:00")) if "T" in to_date else datetime.fromisoformat(to_date + "T23:59:59+00:00")
    docs = await db.invoices.find(q, {"_id": 0, "snapshot.bookings": 0}).sort("created_at", -1).limit(max(1, min(limit, 500))).to_list(500)
    for d in docs:
        _strip_dates(d)
    return docs


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user=Depends(get_current_user)):
    await require_cap(user, "bookings.invoice", db)
    doc = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    return _strip_dates(doc)


@router.put("/invoices/{invoice_id}")
async def update_invoice_draft(invoice_id: str, payload: dict, user=Depends(get_current_user)):
    """Iter 326 — Editieren einer Entwurfs-Rechnung.

    - Nur Status 'draft' darf bearbeitet werden (alles andere ist
      buchhaltungs-relevant + ggf. an Stripe übergeben).
    - Bei manuellen Rechnungen sind alle Felder editierbar (Titel,
      Empfänger, Positionen, Konten, Hinweise, Zahlungsbedingungen,
      Vorlage). Totals werden serverseitig neu berechnet.
    - Bei Aggregat-/Catering-Aggregat-/Single-Rechnungen sind nur
      kopf-/anschriftsbezogene Felder editierbar — die Aggregat-
      Posten bleiben der Buchungs-Snapshot.
    """
    await require_cap(user, "bookings.invoice", db)
    target = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if target.get("status") != "draft":
        raise HTTPException(400, "Nur Entwürfe können bearbeitet werden")

    # Common editable fields across all kinds
    common = {"title", "recipient_name", "recipient_address",
              "sender_org_unit", "payment_terms", "notes",
              "external_customer_email", "external_customer_name"}
    updates: dict = {k: v for k, v in payload.items() if k in common}

    # Vorlagen-Wechsel: erneut Template-Snapshot anwenden
    if "template_id" in payload:
        tid = (payload.get("template_id") or "").strip() or None
        if tid and tid != "__none__":
            tpl = await db.invoice_templates.find_one(
                {"template_id": tid}, {"_id": 0},
            )
            if not tpl:
                raise HTTPException(404, f"Vorlage {tid} nicht gefunden")
            updates["template_id"] = tpl["template_id"]
            snap_patch = {
                "template_id": tpl["template_id"],
                "template_name": tpl.get("name"),
                "header_text": tpl.get("header_text"),
                "header_format": tpl.get("header_format", "text"),
                "footer_text": tpl.get("footer_text"),
                "footer_format": tpl.get("footer_format", "text"),
                "bank_details": tpl.get("bank_details"),
                "payment_terms_default": tpl.get("payment_terms_default"),
                "sender_org_unit_default": tpl.get("sender_org_unit_default"),
                "logo_storage_path": tpl.get("logo_storage_path"),
                "logo_content_type": tpl.get("logo_content_type"),
                "default_tax_rate": tpl.get("default_tax_rate"),
            }
            for k, v in snap_patch.items():
                updates[f"snapshot.{k}"] = v
        else:
            updates["template_id"] = None

    # Iter 332 — Positionen & Konten-Felder dürfen jetzt für JEDE Rechnungs-
    # Art bearbeitet werden, solange sie im Status "draft" ist. Vorher war
    # das auf kind=="manual" beschränkt → bei Aggregat-/Catering-/Single-
    # Entwürfen waren die Lines read-only, was die Buchhaltung blockierte.
    editable_fields = {"issue_date", "service_period_from", "service_period_to",
                       "cost_center", "account", "cost_object", "project_code",
                       "currency", "number_range_id"}
    for k in editable_fields:
        if k in payload:
            updates[k] = payload[k]
    if "lines" in payload:
        from routes.resources.invoices_config import _compute_totals
        # Vorlage für default_tax_rate
        tpl_for_tax = None
        tpl_id = updates.get("template_id", target.get("template_id"))
        if tpl_id:
            tpl_for_tax = await db.invoice_templates.find_one(
                {"template_id": tpl_id}, {"_id": 0, "default_tax_rate": 1},
            )
        default_tax = float((tpl_for_tax or {}).get("default_tax_rate") or 0)
        totals = _compute_totals([dict(li) for li in (payload.get("lines") or [])], default_tax)
        updates["snapshot.lines"] = totals["lines"]
        updates["snapshot.subtotal_net"] = totals["subtotal_net"]
        updates["snapshot.total_tax"] = totals["total_tax"]
        updates["snapshot.total_gross"] = totals["total_gross"]
        # Aggregat-Snapshot legacy total field (für Rückwärts-Kompat).
        updates["snapshot.total"] = totals["total_gross"]
        updates["total"] = totals["total_gross"]

    updates["updated_at"] = _now()
    # Iter 327 — Audit-Diff persistieren bevor wir schreiben.
    diff = _build_diff(target, updates)
    await db.invoices.update_one({"invoice_id": invoice_id}, {"$set": updates})
    await _audit(user, invoice_id, "edited", {"changed_keys": list(updates.keys())})
    if diff:
        await _history_log(invoice_id, "edited", user, diff)
    fresh = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    return _strip_dates(fresh)


@router.post("/invoices/{invoice_id}/reload-lines-from-bookings")
async def reload_lines_from_bookings(invoice_id: str, user=Depends(get_current_user)):
    """Iter 333 — Regeneriert die Positions-Lines einer Aggregat-/Single-
    /Catering-Aggregat-Rechnung aus den verknüpften Buchungen.

    Nutzungs-Szenario: Buchhaltung hat in der Rechnung manuell editiert,
    danach wurde in einer Buchung die Catering-Anforderung korrigiert →
    der Button lädt die "frische" Position-Liste neu, ohne die Rechnung
    löschen + neu erstellen zu müssen.

    Nur für Draft-Rechnungen und nicht für `kind=manual` (dort gibt es
    keine Buchungs-Quelle).
    """
    await require_cap(user, "bookings.invoice", db)
    doc = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if doc.get("status") != "draft":
        raise HTTPException(400, "Nur Entwürfe können neu geladen werden")
    if doc.get("kind") == "manual":
        raise HTTPException(400, "Manuelle Rechnungen haben keine Buchungs-Quelle")

    # Re-aggregate from the booking_ids snapshot
    snap = doc.get("snapshot") or {}
    booking_ids: list = []
    if doc.get("booking_id"):
        booking_ids = [doc["booking_id"]]
    elif snap.get("bookings"):
        booking_ids = [b.get("booking_id") for b in snap["bookings"] if b.get("booking_id")]
    if not booking_ids:
        raise HTTPException(400, "Keine Buchungs-IDs im Snapshot — nichts zum Neuladen")

    from routes.resources.invoices import aggregate_booking_invoice
    fresh = await aggregate_booking_invoice(
        cost_center=doc.get("cost_center"),
        account=doc.get("account"),
        from_date=None, to_date=None,
        booking_ids=",".join(booking_ids),
        user=user,
    )

    # Iter 333 — Modern totals (used by the manual-renderer) are recomputed
    # so the PDF/UI shows consistent net/tax/gross after reload. Falls back
    # to legacy `total` for aggregate-only fields.
    from routes.resources.invoices_config import _compute_totals
    tpl_id = doc.get("template_id")
    tpl_for_tax = None
    if tpl_id:
        tpl_for_tax = await db.invoice_templates.find_one(
            {"template_id": tpl_id}, {"_id": 0, "default_tax_rate": 1},
        )
    default_tax = float((tpl_for_tax or {}).get("default_tax_rate") or 0)
    totals = _compute_totals(
        [dict(li) for li in (fresh.get("lines") or [])],
        default_tax,
    )

    new_snapshot = {
        **(snap or {}),
        "lines": totals["lines"],
        "bookings": fresh.get("bookings", []),
        "total": totals["total_gross"],
        "subtotal_net": totals["subtotal_net"],
        "total_tax": totals["total_tax"],
        "total_gross": totals["total_gross"],
    }
    updates = {
        "snapshot": new_snapshot,
        "total": totals["total_gross"],
        "updated_at": _now(),
    }
    await db.invoices.update_one({"invoice_id": invoice_id}, {"$set": updates})
    await _history_log(invoice_id, "edited", user, [{
        "field": "snapshot.lines",
        "label": "Positionen",
        "before": f"{len((snap or {}).get('lines') or [])} Position(en)",
        "after": f"{len(fresh.get('lines') or [])} Position(en) (neu aus Buchungen geladen)",
    }], {"reloaded_booking_count": len(booking_ids)})

    refreshed = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    return _strip_dates(refreshed)


@router.get("/invoices/{invoice_id}/history")
async def get_invoice_history(invoice_id: str, user=Depends(get_current_user)):
    """Iter 327 — chronologische Liste aller Änderungen an dieser Rechnung."""
    await require_cap(user, "bookings.invoice", db)
    # Existenz prüfen, sonst 404 (sonst leise leere Liste, was missverstanden würde)
    doc = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0, "invoice_id": 1})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    entries = await db.invoice_history.find(
        {"invoice_id": invoice_id}, {"_id": 0},
    ).sort("ts", -1).to_list(500)
    for e in entries:
        _strip_dates(e)
    return entries


# ---------------------------------------------------------------------------
# PDF re-render from snapshot
# ---------------------------------------------------------------------------

def _render_invoice_pdf(doc: dict) -> bytes:
    """Re-renders the stored snapshot as PDF using existing util.

    Iter 322 — when the invoice was saved with a configured template
    (logo + header + footer + payment terms), render via the richer
    `build_manual_invoice_pdf` so the user gets a templated PDF instead
    of the bare-bones default layout.

    Iter 326 — for `kind=="manual"` invoices the snapshot uses the
    `total_gross/subtotal_net/total_tax` shape and already has the right
    line structure → render via `build_manual_invoice_pdf` directly.
    Previously this endpoint adapted the aggregate-snapshot shape and
    fell back to `snap.get("total") = 0` for manual invoices → PDF
    showed all zeros (user-reported bug).
    """
    snap = doc.get("snapshot") or {}
    if doc.get("kind") == "manual":
        from routes.resources.invoices_config import build_manual_invoice_pdf
        tpl = None  # template snapshot is already inlined into doc["snapshot"]
        return build_manual_invoice_pdf(doc, tpl)
    has_template = snap.get("template_id") or snap.get("logo_storage_path") \
        or snap.get("header_text") or snap.get("footer_text")
    if has_template:
        from routes.resources.invoices_config import build_manual_invoice_pdf
        # Adapt the aggregate-snapshot lines into the manual-invoice line shape.
        # The manual-invoice renderer expects `{label, quantity, unit, unit_price, subtotal}`.
        adapted_lines = []
        adapted_subtotal = 0.0
        default_tax = float(snap.get("default_tax_rate") or 0)
        for ln in snap.get("lines", []):
            qty = float(ln.get("quantity", 1) or 0)
            unit_price = float(ln.get("unit_price") or 0)
            # Iter 329 — aggregate-snapshot lines often only store qty + unit_price
            # (no precomputed `subtotal`); compute it so the PDF doesn't show
            # "0.00 EUR" in every Gesamt cell.
            subtotal_net = float(ln.get("subtotal") or 0) or (qty * unit_price)
            tax_rate = float(ln.get("tax_rate") or default_tax)
            subtotal_gross = subtotal_net + subtotal_net * tax_rate / 100
            adapted_subtotal += subtotal_net
            adapted_lines.append({
                "label": ln.get("label") or ln.get("description") or "Position",
                "quantity": qty,
                "unit": ln.get("unit") or "",
                "unit_price": unit_price,
                # Manual-renderer keys: tax_rate_effective + subtotal_gross
                "tax_rate_effective": tax_rate,
                "subtotal_gross": subtotal_gross,
                # Keep legacy for backwards-compat
                "subtotal": subtotal_net,
                "tax_rate": tax_rate,
            })
        # Compute totals from line subtotals (fall back to legacy snap.total
        # if no lines were produced — keeps backwards compatibility).
        line_net = adapted_subtotal or float(snap.get("total", 0))
        line_tax = sum(li["subtotal"] * (li["tax_rate"] or 0) / 100 for li in adapted_lines)
        line_gross = line_net + line_tax
        invoice_view = {
            # Iter 329 — Echte Rechnungsnummer (z.B. KLS-2026-0002) statt
            # interner invoice_id ("inv_5e1bed0977") im PDF-Header zeigen.
            "invoice_number": doc.get("invoice_number") or doc.get("invoice_id"),
            "title": doc.get("title") or "Rechnung",
            "recipient_name": doc.get("recipient_name")
                              or doc.get("external_customer_name")
                              or f"Kostenstelle {doc.get('cost_center') or '—'}",
            "recipient_address": doc.get("recipient_address")
                                 or doc.get("external_customer_email") or "",
            "sender_org_unit": doc.get("sender_org_unit") or snap.get("sender_org_unit_default"),
            "issue_date": (doc.get("created_at") or "")[:10] if isinstance(doc.get("created_at"), str) else _now().date().isoformat(),
            "service_period_from": doc.get("from_date"),
            "service_period_to": doc.get("to_date"),
            "payment_terms": doc.get("payment_terms") or snap.get("payment_terms_default"),
            "notes": doc.get("notes"),
            "cost_center": doc.get("cost_center"),
            "account": doc.get("account"),
            "currency": snap.get("currency", "EUR"),
            "snapshot": {
                "lines": adapted_lines,
                "subtotal_net": line_net,
                "total_tax": line_tax,
                "total_gross": line_gross,
                "header_text": snap.get("header_text"),
                "header_format": snap.get("header_format", "text"),
                "footer_text": snap.get("footer_text"),
                "footer_format": snap.get("footer_format", "text"),
                "bank_details": snap.get("bank_details"),
                "logo_storage_path": snap.get("logo_storage_path"),
                "logo_content_type": snap.get("logo_content_type"),
            },
        }
        return build_manual_invoice_pdf(invoice_view, template=None)

    # Default / legacy layout (no template attached)
    from routes.resources.invoices import _build_invoice_pdf
    header = [
        ("Rechnungs-Nr.", doc["invoice_id"]),
        ("Kostenstelle", doc.get("cost_center")),
        ("Konto", doc.get("account")),
        ("Zeitraum", f"{doc.get('from_date') or '...'} – {doc.get('to_date') or '...'}"),
        ("Erstellt", (doc.get("created_at") or "")[:10] if isinstance(doc.get("created_at"), str) else _now().date().isoformat()),
        ("Status", doc.get("status", "draft")),
    ]
    if doc.get("external_customer_name") or doc.get("external_customer_email"):
        header.append(("Kunde", f"{doc.get('external_customer_name','')} <{doc.get('external_customer_email','')}>"))
    return _build_invoice_pdf(
        title=doc.get("title") or "Rechnung",
        subtitle=f"Status: {doc.get('status','draft')}",
        header_info=header,
        lines=snap.get("lines", []),
        total=snap.get("total", 0),
        currency=snap.get("currency", "EUR"),
    )


@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, user=Depends(get_current_user)):
    await require_cap(user, "bookings.invoice", db)
    doc = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    pdf = _render_invoice_pdf(_strip_dates(doc))
    # Iter 363 — User-feedback: PDF-Topbar zeigte interne `invoice_id`
    # statt der konfigurierten Rechnungsnummer. Bevorzuge `invoice_number`
    # (z. B. „KLS-2026-0006") und fallback auf `invoice_id` für sehr alte
    # Datensätze, die noch keine Nummer haben.
    number = doc.get("invoice_number") or invoice_id
    fname = f"Rechnung_{number}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/approve")
async def approve_invoice(invoice_id: str, user=Depends(get_current_user)):
    await require_cap(user, "bookings.invoice.approve", db)
    doc = await db.invoices.find_one({"invoice_id": invoice_id})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if doc.get("status") not in ("draft",):
        raise HTTPException(400, f"Status muss 'draft' sein (ist '{doc.get('status')}')")
    await db.invoices.update_one(
        {"invoice_id": invoice_id},
        {"$set": {"status": "approved", "approved_by": user["user_id"],
                  "approved_by_email": user.get("email"), "approved_at": _now()}},
    )
    await _audit(user, invoice_id, "approved")
    await _history_log(invoice_id, "approved", user, [
        {"field": "status", "label": "Status", "before": "draft", "after": "approved"},
    ])
    return {"status": "approved"}


# ---------------------------------------------------------------------------
# Send email (Buchhaltung)
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/send-email")
async def send_invoice_email(invoice_id: str, payload: Optional[dict] = None, user=Depends(get_current_user)):
    """Send the invoice PDF to the cost-center's accounting_email
    (or override via payload.to_email). Body optional:
      to_email: str — override default recipient
      message: str — additional message
    """
    await require_cap(user, "bookings.invoice", db)
    payload = payload or {}
    doc = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if doc.get("status") not in ("approved", "sent"):
        raise HTTPException(400, f"Bitte zuerst freigeben (Status='{doc.get('status')}').")

    # Determine recipient
    to_email = (payload.get("to_email") or "").strip()
    if not to_email and doc.get("cost_center"):
        cc = await db.cost_centers.find_one({"code": doc["cost_center"]}, {"_id": 0})
        to_email = (cc or {}).get("accounting_email") or ""
    if not to_email:
        raise HTTPException(400, "Keine Empfaenger-E-Mail (Kostenstelle hat keine accounting_email).")

    # Render PDF
    pdf = _render_invoice_pdf(_strip_dates(dict(doc)))

    # Build HTML body
    msg = (payload.get("message") or "").strip()
    extra_block = f'<p style="margin-top:16px;color:#374151;">{_html_escape(msg)}</p>' if msg else ""
    html = f"""
    <div style="font-family: Arial, sans-serif; color: #1C1F1D; line-height: 1.45;">
      <h2 style="margin:0 0 8px;">Rechnung {doc['invoice_id']}</h2>
      <p style="margin:0 0 12px;color:#6B7280;">
        Anbei die {doc.get('title','Rechnung')} (Kostenstelle: <b>{doc.get('cost_center') or '—'}</b>).
        Betrag: <b>{_fmt_eur(doc['snapshot'].get('total',0), doc['snapshot'].get('currency','EUR'))}</b>.
      </p>
      {extra_block}
      <p style="font-size:12px;color:#9CA3AF;margin-top:24px;">Versendet von {user.get('email','MeetFlow')} via MeetFlow Billing.</p>
    </div>
    """

    # Send (SMTP supports attachments — Resend/SendGrid use link fallback)
    result = await _send_with_attachment(
        to_email=to_email,
        subject=f"Rechnung {doc['invoice_id']} — {doc.get('title','')}",
        html=html,
        pdf_bytes=pdf,
        pdf_filename=f"{doc['invoice_id']}.pdf",
    )

    if result.get("status") == "sent":
        await db.invoices.update_one(
            {"invoice_id": invoice_id},
            {"$set": {"status": "sent",
                      "sent_to_email": to_email,
                      "sent_at": _now(),
                      "sent_by": user["user_id"],
                      "email_provider": result.get("provider"),
                      "email_provider_id": str(result.get("id") or result.get("code") or "")}},
        )
        await _audit(user, invoice_id, "sent_email", {"to": to_email, "provider": result.get("provider")})
        await _history_log(invoice_id, "sent_email", user, [], {
            "to": to_email,
            "provider": result.get("provider"),
        })
        return {"status": "sent", "to_email": to_email, "result": result}

    raise HTTPException(502, f"E-Mail-Versand fehlgeschlagen: {result.get('error') or result.get('status')}")


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_eur(n, cur="EUR") -> str:
    try:
        return f"{float(n):,.2f} {cur}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"{n} {cur}"


async def _send_with_attachment(to_email: str, subject: str, html: str, pdf_bytes: bytes, pdf_filename: str) -> dict:
    """Send email with PDF attachment. Prefers SMTP because it supports
    attachments natively; falls back to Resend/SendGrid with a download
    link in the body if SMTP is not configured.
    """
    config = await db.email_config.find_one({"config_id": "global"}, {"_id": 0}) or {}
    smtp_cfg = config.get("smtp") if isinstance(config.get("smtp"), dict) else None
    smtp_ready = bool(smtp_cfg and smtp_cfg.get("host") and smtp_cfg.get("port")
                      and smtp_cfg.get("username") and smtp_cfg.get("password"))
    if smtp_ready:
        from services.email_smtp import send_via_smtp
        return await send_via_smtp(
            smtp_cfg, to_email, subject, html,
            attachments=[{
                "filename": pdf_filename,
                "content": pdf_bytes,
                "content_type": "application/pdf",
            }],
            from_email=config.get("sender_email"),
        )
    # Fallback — no attachment support → simulated log
    from services.email import send_email_real
    res = await send_email_real(to_email, subject,
                                html + '<p>Diese Mail-Konfiguration unterstützt keine Anhänge. PDF bitte aus MeetFlow herunterladen.</p>')
    return res


# ---------------------------------------------------------------------------
# Stripe — external invoicing
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/send-stripe")
async def send_invoice_via_stripe(invoice_id: str, payload: Optional[dict] = None, user=Depends(get_current_user)):
    """Iter 285 — Push the invoice into Stripe as a finalized invoice and
    let Stripe email it to the external customer.

    Requires:
      * invoice.external_customer_email (or override in payload)
      * STRIPE_API_KEY env var
      * snapshot.lines  (each {label, quantity, unit_price, subtotal})
    """
    await require_cap(user, "bookings.invoice", db)
    payload = payload or {}
    doc = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if doc.get("status") not in ("approved", "sent"):
        raise HTTPException(400, f"Bitte zuerst freigeben (Status='{doc.get('status')}').")

    customer_email = (payload.get("external_customer_email") or doc.get("external_customer_email") or "").strip()
    customer_name = (payload.get("external_customer_name") or doc.get("external_customer_name") or "").strip()
    if not customer_email:
        raise HTTPException(400, "Externe Kunden-E-Mail erforderlich für Stripe-Versand.")

    api_key = os.environ.get("STRIPE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "Stripe nicht konfiguriert (STRIPE_API_KEY fehlt).")

    try:
        import stripe
        stripe.api_key = api_key
    except Exception as e:
        raise HTTPException(503, f"Stripe SDK nicht verfügbar: {e}")

    snap = doc.get("snapshot") or {}
    if not snap.get("lines"):
        raise HTTPException(400, "Rechnung ohne Positionen kann nicht via Stripe verschickt werden.")
    currency = (snap.get("currency") or "EUR").lower()

    try:
        # 1. Idempotent customer creation via search-by-email
        customer_id = None
        try:
            search = stripe.Customer.search(query=f"email:'{customer_email}'", limit=1)
            if search.data:
                customer_id = search.data[0].id
        except Exception as e:
            logger.warning("[STRIPE] customer search failed: %s — falling back to create", e)
        if not customer_id:
            cust = stripe.Customer.create(
                email=customer_email,
                name=customer_name or customer_email,
                metadata={"meetflow_invoice_id": invoice_id},
                idempotency_key=f"cust_{invoice_id}",
            )
            customer_id = cust.id

        # 2. Create draft invoice
        s_inv = stripe.Invoice.create(
            customer=customer_id,
            collection_method="send_invoice",
            days_until_due=int(payload.get("days_until_due", 14)),
            auto_advance=False,
            description=doc.get("title") or f"Rechnung {invoice_id}",
            metadata={"meetflow_invoice_id": invoice_id,
                      "cost_center": doc.get("cost_center") or ""},
            idempotency_key=f"inv_{invoice_id}",
        )

        # 3. Line items
        for i, ln in enumerate(snap["lines"]):
            try:
                # Stripe expects amount in smallest currency unit (cents)
                amount_cents = int(round(float(ln.get("subtotal", 0)) * 100))
                if amount_cents <= 0:
                    continue
                stripe.InvoiceItem.create(
                    customer=customer_id,
                    invoice=s_inv.id,
                    amount=amount_cents,
                    currency=currency,
                    description=ln.get("label") or "Position",
                    metadata={"line_kind": ln.get("kind", "")},
                    idempotency_key=f"line_{invoice_id}_{i}",
                )
            except Exception as e:
                logger.warning("[STRIPE] line item %s failed: %s", i, e)

        # 4. Finalize + send
        s_inv = stripe.Invoice.finalize_invoice(s_inv.id, auto_advance=True)
        stripe.Invoice.send_invoice(s_inv.id)

        await db.invoices.update_one(
            {"invoice_id": invoice_id},
            {"$set": {"status": "sent",
                      "stripe_customer_id": customer_id,
                      "stripe_invoice_id": s_inv.id,
                      "stripe_invoice_status": s_inv.status,
                      "stripe_hosted_url": getattr(s_inv, "hosted_invoice_url", None),
                      "stripe_invoice_pdf": getattr(s_inv, "invoice_pdf", None),
                      "sent_to_email": customer_email,
                      "sent_at": _now(),
                      "sent_by": user["user_id"],
                      "email_provider": "stripe"}},
        )
        await _audit(user, invoice_id, "sent_stripe",
                     {"customer_id": customer_id, "stripe_invoice_id": s_inv.id})
        await _history_log(invoice_id, "sent_stripe", user, [], {
            "stripe_invoice_id": s_inv.id,
            "customer_id": customer_id,
        })
        return {
            "status": "sent",
            "stripe_invoice_id": s_inv.id,
            "stripe_invoice_status": s_inv.status,
            "hosted_invoice_url": getattr(s_inv, "hosted_invoice_url", None),
        }
    except Exception as e:
        logger.error("[STRIPE] failed: %s", e, exc_info=True)
        raise HTTPException(502, f"Stripe-Versand fehlgeschlagen: {e}")


# ---------------------------------------------------------------------------
# Void
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/void")
async def void_invoice(invoice_id: str, payload: dict | None = None, user=Depends(get_current_user)):
    await require_cap(user, "bookings.invoice.approve", db)
    doc = await db.invoices.find_one({"invoice_id": invoice_id})
    if not doc:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if doc.get("status") == "paid":
        raise HTTPException(400, "Bezahlte Rechnung kann nicht storniert werden.")
    # Iter 328 — Storno-Grund ist Pflicht; ohne Grund 400 mit klarer Meldung.
    reason = ((payload or {}).get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Stornogrund ist Pflicht.")
    await db.invoices.update_one(
        {"invoice_id": invoice_id},
        {"$set": {
            "status": "void",
            "voided_by": user["user_id"],
            "voided_by_email": user.get("email"),
            "voided_by_name": user.get("name") or user.get("email"),
            "voided_at": _now(),
            "void_reason": reason,
        }},
    )
    # Best-effort void on Stripe side, too
    if doc.get("stripe_invoice_id"):
        try:
            import stripe
            stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
            stripe.Invoice.void_invoice(doc["stripe_invoice_id"])
        except Exception as e:
            logger.warning("[STRIPE] void failed: %s", e)
    await _audit(user, invoice_id, "voided", {"reason": reason})
    await _history_log(invoice_id, "voided", user, [
        {"field": "status", "label": "Status", "before": doc.get("status"), "after": "void"},
    ], {"reason": reason})
    return {"status": "void", "void_reason": reason}


# ---------------------------------------------------------------------------
# Stripe webhook — invoice.paid → status=paid
# ---------------------------------------------------------------------------

@router.post("/stripe-webhook")
async def stripe_webhook(request: Request,
                         stripe_signature: Optional[str] = Header(None, alias="stripe-signature")):
    body = await request.body()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    event = None
    if secret and stripe_signature:
        try:
            import stripe
            event = stripe.Webhook.construct_event(payload=body, sig_header=stripe_signature, secret=secret)
        except Exception as e:
            logger.warning("[STRIPE-WEBHOOK] signature verification failed: %s", e)
            raise HTTPException(400, "Invalid signature")
    else:
        # Dev mode — accept without verification
        try:
            import json as _j
            event = _j.loads(body or b"{}")
        except Exception:
            raise HTTPException(400, "Invalid payload")

    ev_type = (event or {}).get("type")
    obj = ((event or {}).get("data") or {}).get("object") or {}
    if ev_type == "invoice.paid":
        meetflow_id = ((obj.get("metadata") or {}).get("meetflow_invoice_id")) or None
        if meetflow_id:
            await db.invoices.update_one(
                {"invoice_id": meetflow_id},
                {"$set": {"status": "paid", "stripe_invoice_status": obj.get("status"), "paid_at": _now()}},
            )
            logger.info("[STRIPE-WEBHOOK] marked %s as paid", meetflow_id)
    return {"received": True, "type": ev_type}
