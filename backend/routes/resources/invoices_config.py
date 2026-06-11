"""
Iter 293 — Configurable manual invoice module.
================================================

Extends the existing invoice flow with:

* `invoice_master_data`  — Konten / Kostenstellen / Kostenträger / Projekte
                           als pflegbare Stammdaten (admin pflegt, Nutzer wählt).
* `invoice_number_ranges` — frei konfigurierbare Nummernkreise mit
                           Pattern `{PREFIX}-{YYYY}-{####}` und atomic counter.
* `invoice_templates`     — Vorlage mit Header/Footer/Zahlungsbedingungen/
                           Pflichtfeldern, sichtbaren Feldern und Standard-MwSt.
* `POST /api/invoices/manual`  — manuelle Rechnung mit freien Positionen,
                                  Validierung gegen Template, Number aus Range.
* `GET /api/invoices/{id}/pdf` (override)  — nutzt Template-Layout falls vorhanden.

Berechtigungen (alle neu, Default-grant an admin):
* `invoices.manage_templates`    — Vorlagen CRUD
* `invoices.manage_master_data`  — Stammdaten CRUD + Nummernkreise
* `invoices.create_manual`       — manuelle Rechnung erstellen
* `invoices.set_accounting`      — Konto/Kostenstelle pro Rechnung ändern

Alle Änderungen schreiben in `audit_log` (Entity-Type je nach Objekt).
"""
from __future__ import annotations

import asyncio
import io
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from database import db
from dependencies import get_current_user
from services.permissions import has_cap, require_cap
from services.storage import put_object, get_object, APP_STORAGE_PREFIX

logger = logging.getLogger("server")
router = APIRouter(tags=["invoices-config"])


# ===========================================================================
# Helpers
# ===========================================================================

def _now():
    return datetime.now(timezone.utc)


async def _audit(user, entity: str, entity_id: str, action: str, extra: Optional[dict] = None):
    """Append-only audit row; never breaks the calling endpoint."""
    try:
        await db.audit_log.insert_one({
            "audit_id": f"al_{uuid.uuid4().hex[:8]}",
            "ts": _now(),
            "user_id": user["user_id"],
            "user_email": user.get("email"),
            "entity": entity,
            "entity_id": entity_id,
            "action": action,
            "extra": extra or {},
        })
    except Exception as e:
        logger.warning("[INVOICE-CFG-AUDIT] %s", e)


def _strip(d: dict) -> dict:
    d.pop("_id", None)
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ===========================================================================
# Master data: Konten / Kostenstellen / Kostenträger / Projekte
# ===========================================================================

MASTER_TYPES = ("account", "cost_center", "cost_object", "project")


class MasterDataItem(BaseModel):
    code: str
    label: str
    description: Optional[str] = None
    active: bool = True


@router.get("/admin/invoice-master-data")
async def list_master_data(type: str, user=Depends(get_current_user)):
    if not await has_cap(user, "invoices.manage_master_data", db) and user.get("role") != "admin":
        # everyone with `bookings.invoice` may *read* (so the create-invoice
        # dropdown works), but only managers/admins can write.
        if not await has_cap(user, "bookings.invoice", db):
            raise HTTPException(403, "Kein Zugriff")
    if type not in MASTER_TYPES:
        raise HTTPException(400, f"Unbekannter Typ: {type}")
    docs = await db.invoice_master_data.find(
        {"type": type}, {"_id": 0}
    ).sort("code", 1).to_list(2000)
    return docs


@router.post("/admin/invoice-master-data")
async def create_master_data(payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_master_data", db)
    t = payload.get("type")
    if t not in MASTER_TYPES:
        raise HTTPException(400, f"Unbekannter Typ: {t}")
    code = (payload.get("code") or "").strip()
    label = (payload.get("label") or "").strip()
    if not code or not label:
        raise HTTPException(400, "Code und Bezeichnung sind Pflichtfelder")
    existing = await db.invoice_master_data.find_one(
        {"type": t, "code": code}, {"_id": 1}
    )
    if existing:
        raise HTTPException(409, f"Code {code} existiert bereits für Typ {t}")
    doc = {
        "item_id": f"md_{uuid.uuid4().hex[:10]}",
        "type": t,
        "code": code,
        "label": label,
        "description": (payload.get("description") or "").strip() or None,
        "active": payload.get("active", True),
        "created_at": _now(),
        "updated_at": _now(),
    }
    # Cost-center-specific fields preserved through the unified store
    # (used by auto-send-invoice flow + RACI lookups).
    if t == "cost_center":
        doc["accounting_email"] = (payload.get("accounting_email") or "").strip() or None
        doc["responsible_user_id"] = payload.get("responsible_user_id")
    await db.invoice_master_data.insert_one(doc)
    await _audit(user, "invoice_master_data", doc["item_id"], "created", {"type": t, "code": code})
    return _strip(doc)


@router.put("/admin/invoice-master-data/{item_id}")
async def update_master_data(item_id: str, payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_master_data", db)
    target = await db.invoice_master_data.find_one({"item_id": item_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Eintrag nicht gefunden")
    updates: dict = {}
    for k in ("label", "description", "active"):
        if k in payload:
            updates[k] = payload[k]
    # Cost-center-only fields
    if target.get("type") == "cost_center":
        for k in ("accounting_email", "responsible_user_id"):
            if k in payload:
                v = payload[k]
                if isinstance(v, str):
                    v = v.strip() or None
                updates[k] = v
    if not updates:
        return target
    updates["updated_at"] = _now()
    await db.invoice_master_data.update_one({"item_id": item_id}, {"$set": updates})
    await _audit(user, "invoice_master_data", item_id, "updated", {"diff_keys": list(updates.keys())})
    target.update(updates)
    return _strip(target)


@router.delete("/admin/invoice-master-data/{item_id}")
async def delete_master_data(item_id: str, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_master_data", db)
    res = await db.invoice_master_data.delete_one({"item_id": item_id})
    if not res.deleted_count:
        raise HTTPException(404, "Eintrag nicht gefunden")
    await _audit(user, "invoice_master_data", item_id, "deleted")
    return {"ok": True}


# ===========================================================================
# Number ranges
# ===========================================================================

class NumberRangeIn(BaseModel):
    name: str
    prefix: str = "RE"
    pattern: str = "{PREFIX}-{YYYY}-{####}"   # {PREFIX} {YYYY} {YY} {MM} {####} {###} {##}
    start_number: int = 1
    yearly_reset: bool = True
    active: bool = True
    is_default: bool = False


@router.get("/admin/invoice-number-ranges")
async def list_number_ranges(user=Depends(get_current_user)):
    if not await has_cap(user, "bookings.invoice", db):
        raise HTTPException(403, "Kein Zugriff")
    docs = await db.invoice_number_ranges.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return docs


@router.post("/admin/invoice-number-ranges")
async def create_number_range(payload: NumberRangeIn, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_master_data", db)
    if "{####}" not in payload.pattern and "{###}" not in payload.pattern and "{##}" not in payload.pattern:
        raise HTTPException(400, "Pattern muss einen Zähler enthalten ({####}, {###} oder {##})")
    doc = payload.model_dump()
    doc["range_id"] = f"rng_{uuid.uuid4().hex[:10]}"
    doc["current_number"] = doc["start_number"] - 1   # next-issue = current+1
    doc["current_year"] = _now().year if doc["yearly_reset"] else None
    doc["created_at"] = _now()
    doc["updated_at"] = _now()
    # Only one is_default per organisation: clear the previous one
    if doc["is_default"]:
        await db.invoice_number_ranges.update_many({}, {"$set": {"is_default": False}})
    await db.invoice_number_ranges.insert_one(doc)
    await _audit(user, "invoice_number_range", doc["range_id"], "created",
                 {"name": doc["name"], "pattern": doc["pattern"]})
    return _strip(doc)


@router.put("/admin/invoice-number-ranges/{range_id}")
async def update_number_range(range_id: str, payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_master_data", db)
    target = await db.invoice_number_ranges.find_one({"range_id": range_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Kreis nicht gefunden")
    updates = {k: v for k, v in payload.items() if k in
               {"name", "prefix", "pattern", "start_number",
                "yearly_reset", "active", "is_default"}}
    if updates.get("is_default"):
        await db.invoice_number_ranges.update_many({}, {"$set": {"is_default": False}})
    if updates:
        updates["updated_at"] = _now()
        await db.invoice_number_ranges.update_one({"range_id": range_id}, {"$set": updates})
        await _audit(user, "invoice_number_range", range_id, "updated", {"diff_keys": list(updates.keys())})
        target.update(updates)
    return _strip(target)


@router.delete("/admin/invoice-number-ranges/{range_id}")
async def delete_number_range(range_id: str, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_master_data", db)
    used = await db.invoices.find_one({"number_range_id": range_id}, {"_id": 1})
    if used:
        raise HTTPException(409, "Kreis bereits in Rechnungen verwendet — bitte deaktivieren statt löschen")
    res = await db.invoice_number_ranges.delete_one({"range_id": range_id})
    if not res.deleted_count:
        raise HTTPException(404, "Kreis nicht gefunden")
    await _audit(user, "invoice_number_range", range_id, "deleted")
    return {"ok": True}


def _format_number(pattern: str, prefix: str, year: int, month: int, n: int) -> str:
    out = pattern.replace("{PREFIX}", prefix)
    out = out.replace("{YYYY}", f"{year:04d}").replace("{YY}", f"{year % 100:02d}")
    out = out.replace("{MM}", f"{month:02d}")
    out = out.replace("{####}", f"{n:04d}").replace("{###}", f"{n:03d}").replace("{##}", f"{n:02d}")
    return out


async def _allocate_number(range_id: Optional[str]) -> tuple[str, str]:
    """Atomically pull the next number from the configured range. Falls back
    to a synthetic `RE-YYYY-uuid` if no range is configured at all (keeps
    legacy callers working). Returns (range_id, formatted_number).
    """
    if not range_id:
        rng = await db.invoice_number_ranges.find_one({"is_default": True, "active": True}, {"_id": 0})
        if not rng:
            # No range configured anywhere → synthetic fallback
            return ("", f"RE-{_now().year}-{uuid.uuid4().hex[:6].upper()}")
        range_id = rng["range_id"]
    now = _now()
    # Atomic increment + optional year-reset
    rng = await db.invoice_number_ranges.find_one({"range_id": range_id}, {"_id": 0})
    if not rng or not rng.get("active", True):
        raise HTTPException(400, "Nummernkreis nicht aktiv")
    reset_to = rng.get("start_number", 1) - 1
    if rng.get("yearly_reset") and rng.get("current_year") != now.year:
        await db.invoice_number_ranges.update_one(
            {"range_id": range_id},
            {"$set": {"current_year": now.year, "current_number": reset_to}},
        )
    upd = await db.invoice_number_ranges.find_one_and_update(
        {"range_id": range_id},
        {"$inc": {"current_number": 1}, "$set": {"updated_at": now}},
        return_document=True,
        projection={"_id": 0},
    )
    n = upd["current_number"]
    return (range_id, _format_number(upd["pattern"], upd.get("prefix", "RE"),
                                     now.year, now.month, n))


# ===========================================================================
# Templates
# ===========================================================================

DEFAULT_REQUIRED_FIELDS = ["recipient_name", "issue_date", "lines"]
ALL_OPTIONAL_FIELDS = [
    "service_period_from", "service_period_to",
    "sender_org_unit", "recipient_address",
    "payment_terms", "notes",
    "cost_center", "account", "cost_object", "project_code",
    "tax_rate",
]


class InvoiceTemplateIn(BaseModel):
    name: str
    description: Optional[str] = None
    header_text: Optional[str] = None
    header_format: Literal["text", "markdown", "html"] = "text"
    footer_text: Optional[str] = None
    footer_format: Literal["text", "markdown", "html"] = "text"
    payment_terms_default: Optional[str] = None
    bank_details: Optional[str] = None
    sender_org_unit_default: Optional[str] = None
    default_tax_rate: float = 0.0
    default_number_range_id: Optional[str] = None
    required_fields: List[str] = Field(default_factory=lambda: list(DEFAULT_REQUIRED_FIELDS))
    visible_fields: List[str] = Field(default_factory=lambda: list(ALL_OPTIONAL_FIELDS))
    is_default: bool = False
    active: bool = True


@router.get("/admin/invoice-templates")
async def list_templates(user=Depends(get_current_user)):
    if not await has_cap(user, "bookings.invoice", db):
        raise HTTPException(403, "Kein Zugriff")
    docs = await db.invoice_templates.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    return docs


@router.post("/admin/invoice-templates")
async def create_template(payload: InvoiceTemplateIn, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_templates", db)
    doc = payload.model_dump()
    doc["template_id"] = f"tpl_{uuid.uuid4().hex[:10]}"
    doc["created_at"] = _now()
    doc["updated_at"] = _now()
    if doc["is_default"]:
        await db.invoice_templates.update_many({}, {"$set": {"is_default": False}})
    await db.invoice_templates.insert_one(doc)
    await _audit(user, "invoice_template", doc["template_id"], "created", {"name": doc["name"]})
    return _strip(doc)


@router.put("/admin/invoice-templates/{template_id}")
async def update_template(template_id: str, payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_templates", db)
    target = await db.invoice_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Vorlage nicht gefunden")
    allowed = {"name", "description", "header_text", "header_format",
               "footer_text", "footer_format",
               "payment_terms_default", "bank_details", "sender_org_unit_default",
               "default_tax_rate", "default_number_range_id",
               "required_fields", "visible_fields", "is_default", "active"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if updates.get("is_default"):
        await db.invoice_templates.update_many({}, {"$set": {"is_default": False}})
    if updates:
        updates["updated_at"] = _now()
        await db.invoice_templates.update_one({"template_id": template_id}, {"$set": updates})
        await _audit(user, "invoice_template", template_id, "updated", {"diff_keys": list(updates.keys())})
        target.update(updates)
    return _strip(target)


@router.delete("/admin/invoice-templates/{template_id}")
async def delete_template(template_id: str, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_templates", db)
    used = await db.invoices.find_one({"template_id": template_id}, {"_id": 1})
    if used:
        raise HTTPException(409, "Vorlage bereits in Rechnungen verwendet — bitte deaktivieren statt löschen")
    res = await db.invoice_templates.delete_one({"template_id": template_id})
    if not res.deleted_count:
        raise HTTPException(404, "Vorlage nicht gefunden")
    await _audit(user, "invoice_template", template_id, "deleted")
    return {"ok": True}


# --- Logo upload/get/delete (iter 295) ---

ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


@router.post("/admin/invoice-templates/{template_id}/logo")
async def upload_template_logo(template_id: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload (or replace) the template's logo in Object Storage. Used at the
    top of generated PDFs. Kept per-template so different invoice types can
    show different sender logos (e.g. clinic main + research arm)."""
    await require_cap(user, "invoices.manage_templates", db)
    target = await db.invoice_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Vorlage nicht gefunden")
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(400, f"Bildformat nicht erlaubt: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(400, "Maximal 2 MB pro Logo")
    ext = (file.filename or "img").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "png"
    path = f"{APP_STORAGE_PREFIX}/invoice-templates/{template_id}/logo.{ext}"
    await asyncio.to_thread(put_object, path, data, file.content_type or "image/png")
    await db.invoice_templates.update_one(
        {"template_id": template_id},
        {"$set": {"logo_storage_path": path, "logo_content_type": file.content_type, "updated_at": _now()}},
    )
    await _audit(user, "invoice_template", template_id, "logo_uploaded", {"size": len(data), "type": file.content_type})
    return {"ok": True, "path": path}


@router.get("/admin/invoice-templates/{template_id}/logo")
async def get_template_logo(template_id: str, user=Depends(get_current_user)):
    if not await has_cap(user, "bookings.invoice", db):
        raise HTTPException(403, "Kein Zugriff")
    target = await db.invoice_templates.find_one({"template_id": template_id}, {"_id": 0, "logo_storage_path": 1, "logo_content_type": 1})
    if not target or not target.get("logo_storage_path"):
        raise HTTPException(404, "Kein Logo")
    data, ct = await asyncio.to_thread(get_object, target["logo_storage_path"])
    return Response(content=data, media_type=target.get("logo_content_type") or ct,
                    headers={"Cache-Control": "private, max-age=120"})


@router.delete("/admin/invoice-templates/{template_id}/logo")
async def delete_template_logo(template_id: str, user=Depends(get_current_user)):
    await require_cap(user, "invoices.manage_templates", db)
    await db.invoice_templates.update_one(
        {"template_id": template_id},
        {"$unset": {"logo_storage_path": "", "logo_content_type": ""}, "$set": {"updated_at": _now()}},
    )
    await _audit(user, "invoice_template", template_id, "logo_deleted")
    return {"ok": True}


# ===========================================================================
# Manual invoice — free-form line items, template-validated
# ===========================================================================

class InvoiceLineIn(BaseModel):
    label: str
    description: Optional[str] = None
    quantity: float = 1
    unit: Optional[str] = None
    unit_price: float = 0
    tax_rate: Optional[float] = None      # % — None → fallback to template default
    discount_percent: Optional[float] = None   # negative for surcharge
    cost_center: Optional[str] = None
    account: Optional[str] = None
    cost_object: Optional[str] = None
    project_code: Optional[str] = None


class ManualInvoiceIn(BaseModel):
    template_id: Optional[str] = None
    number_range_id: Optional[str] = None
    title: Optional[str] = None
    recipient_name: str
    recipient_address: Optional[str] = None
    sender_org_unit: Optional[str] = None
    issue_date: Optional[str] = None        # ISO date
    service_period_from: Optional[str] = None
    service_period_to: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    cost_center: Optional[str] = None
    account: Optional[str] = None
    cost_object: Optional[str] = None
    project_code: Optional[str] = None
    currency: str = "EUR"
    lines: List[InvoiceLineIn]


def _validate_against_template(payload: ManualInvoiceIn, tpl: Optional[dict]) -> List[str]:
    """Return list of missing-required-field labels (empty == OK)."""
    required = (tpl or {}).get("required_fields") or DEFAULT_REQUIRED_FIELDS
    data = payload.model_dump()
    missing = []
    for f in required:
        if f == "lines":
            if not data.get("lines"):
                missing.append("Positionen")
            continue
        if not data.get(f):
            missing.append(f)
    return missing


def _compute_totals(lines: List[dict], default_tax_rate: float) -> dict:
    """Compute per-line subtotal/tax + invoice totals.
    discount_percent applies BEFORE tax. Negative discount = surcharge."""
    rows: list = []
    subtotal_net = 0.0
    total_tax = 0.0
    for li in lines:
        qty = float(li.get("quantity") or 0)
        unit_price = float(li.get("unit_price") or 0)
        gross_line = qty * unit_price
        disc = li.get("discount_percent")
        if disc is not None:
            gross_line = gross_line * (1 - float(disc) / 100.0)
        net = round(gross_line, 2)
        tax_rate = li.get("tax_rate")
        if tax_rate is None:
            tax_rate = default_tax_rate
        tax = round(net * (float(tax_rate) / 100.0), 2)
        rows.append({**li,
                     "subtotal_net": net,
                     "tax_rate_effective": tax_rate,
                     "tax_amount": tax,
                     "subtotal_gross": round(net + tax, 2)})
        subtotal_net += net
        total_tax += tax
    return {
        "lines": rows,
        "subtotal_net": round(subtotal_net, 2),
        "total_tax": round(total_tax, 2),
        "total_gross": round(subtotal_net + total_tax, 2),
    }


@router.post("/invoices/manual")
async def create_manual_invoice(payload: ManualInvoiceIn, user=Depends(get_current_user)):
    await require_cap(user, "invoices.create_manual", db)
    # Resolve template (explicit > default > none)
    tpl = None
    if payload.template_id:
        tpl = await db.invoice_templates.find_one({"template_id": payload.template_id}, {"_id": 0})
        if not tpl:
            raise HTTPException(404, "Vorlage nicht gefunden")
    else:
        tpl = await db.invoice_templates.find_one({"is_default": True, "active": True}, {"_id": 0})

    missing = _validate_against_template(payload, tpl)
    if missing:
        raise HTTPException(400, {"code": "missing_required_fields", "fields": missing,
                                  "message": f"Pflichtfelder fehlen: {', '.join(missing)}"})

    # Allocate invoice number
    range_id = payload.number_range_id or (tpl or {}).get("default_number_range_id")
    rng_id, invoice_number = await _allocate_number(range_id)

    # Compute totals
    default_tax = float((tpl or {}).get("default_tax_rate") or 0)
    totals = _compute_totals([li.model_dump() for li in payload.lines], default_tax)

    invoice_id = f"inv_{uuid.uuid4().hex[:10]}"
    doc = {
        "invoice_id": invoice_id,
        "kind": "manual",
        "invoice_number": invoice_number,
        "number_range_id": rng_id or None,
        "template_id": (tpl or {}).get("template_id"),
        "title": payload.title or f"Rechnung {invoice_number}",
        "recipient_name": payload.recipient_name,
        "recipient_address": payload.recipient_address,
        "sender_org_unit": payload.sender_org_unit or (tpl or {}).get("sender_org_unit_default"),
        "issue_date": payload.issue_date or _now().date().isoformat(),
        "service_period_from": payload.service_period_from,
        "service_period_to": payload.service_period_to,
        "payment_terms": payload.payment_terms or (tpl or {}).get("payment_terms_default"),
        "notes": payload.notes,
        "cost_center": payload.cost_center,
        "account": payload.account,
        "cost_object": payload.cost_object,
        "project_code": payload.project_code,
        "currency": payload.currency,
        "snapshot": {
            "lines": totals["lines"],
            "subtotal_net": totals["subtotal_net"],
            "total_tax": totals["total_tax"],
            "total_gross": totals["total_gross"],
            "header_text": (tpl or {}).get("header_text"),
            "header_format": (tpl or {}).get("header_format", "text"),
            "footer_text": (tpl or {}).get("footer_text"),
            "footer_format": (tpl or {}).get("footer_format", "text"),
            "bank_details": (tpl or {}).get("bank_details"),
            "logo_storage_path": (tpl or {}).get("logo_storage_path"),
            "logo_content_type": (tpl or {}).get("logo_content_type"),
        },
        "total": totals["total_gross"],          # for legacy list views
        "status": "draft",
        "created_by": user["user_id"],
        "created_by_email": user.get("email"),
        "created_at": _now(),
    }
    await db.invoices.insert_one(doc)
    await _audit(user, "invoice", invoice_id, "created_manual",
                 {"invoice_number": invoice_number, "total": totals["total_gross"]})
    # Iter 327 — Verlauf für manuelle Rechnungen: initialer Eintrag.
    try:
        from routes.resources.invoice_tracking import _history_log
        await _history_log(invoice_id, "created", user, [], {
            "kind": "manual",
            "invoice_number": invoice_number,
            "title": doc["title"],
            "total": totals["total_gross"],
        })
    except Exception:
        pass
    return _strip(doc)


@router.post("/invoices/preview-pdf")
async def preview_manual_invoice_pdf(payload: ManualInvoiceIn, user=Depends(get_current_user)):
    """Iter 330 — PDF-Vorschau ohne zu speichern.

    Nimmt das gleiche `ManualInvoiceIn`-Payload wie `POST /invoices/manual`
    entgegen, berechnet Totals + rendert das PDF — speichert die Rechnung
    aber NICHT. Verwendet im `ManualInvoiceDialog` als „PDF-Vorschau"-
    Button: Buchhaltung sieht das finale Layout (inkl. Logo, Header, Footer)
    bevor sie auf "Speichern" klickt.
    """
    await require_cap(user, "invoices.create_manual", db)

    tpl = None
    if payload.template_id:
        tpl = await db.invoice_templates.find_one({"template_id": payload.template_id}, {"_id": 0})
    else:
        tpl = await db.invoice_templates.find_one({"is_default": True, "active": True}, {"_id": 0})

    default_tax = float((tpl or {}).get("default_tax_rate") or 0)
    totals = _compute_totals([li.model_dump() for li in payload.lines], default_tax)

    preview_doc = {
        "invoice_id": "preview",
        "kind": "manual",
        "invoice_number": "VORSCHAU",
        "title": payload.title or "Rechnung (Vorschau)",
        "recipient_name": payload.recipient_name,
        "recipient_address": payload.recipient_address,
        "sender_org_unit": payload.sender_org_unit or (tpl or {}).get("sender_org_unit_default"),
        "issue_date": payload.issue_date or _now().date().isoformat(),
        "service_period_from": payload.service_period_from,
        "service_period_to": payload.service_period_to,
        "payment_terms": payload.payment_terms or (tpl or {}).get("payment_terms_default"),
        "notes": payload.notes,
        "cost_center": payload.cost_center,
        "account": payload.account,
        "currency": payload.currency,
        "snapshot": {
            "lines": totals["lines"],
            "subtotal_net": totals["subtotal_net"],
            "total_tax": totals["total_tax"],
            "total_gross": totals["total_gross"],
            "header_text": (tpl or {}).get("header_text"),
            "header_format": (tpl or {}).get("header_format", "text"),
            "footer_text": (tpl or {}).get("footer_text"),
            "footer_format": (tpl or {}).get("footer_format", "text"),
            "bank_details": (tpl or {}).get("bank_details"),
            "logo_storage_path": (tpl or {}).get("logo_storage_path"),
            "logo_content_type": (tpl or {}).get("logo_content_type"),
        },
    }
    pdf_bytes = build_manual_invoice_pdf(preview_doc, tpl)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="Rechnung-Vorschau.pdf"'})


@router.put("/invoices/{invoice_id}/accounting")
async def update_invoice_accounting(invoice_id: str, payload: dict, user=Depends(get_current_user)):
    """Allow Buchhaltung to retro-edit the accounting allocation on an existing
    invoice (cost_center, account, cost_object, project_code) without touching
    line items. Audit-logged. Locked once status is 'paid'."""
    await require_cap(user, "invoices.set_accounting", db)
    target = await db.invoices.find_one({"invoice_id": invoice_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if target.get("status") == "paid":
        raise HTTPException(400, "Bezahlte Rechnungen dürfen nicht mehr geändert werden")
    allowed = {"cost_center", "account", "cost_object", "project_code"}
    updates = {k: payload.get(k) for k in allowed if k in payload}
    if not updates:
        return _strip(target)
    updates["updated_at"] = _now()
    await db.invoices.update_one({"invoice_id": invoice_id}, {"$set": updates})
    await _audit(user, "invoice", invoice_id, "accounting_updated",
                 {"before": {k: target.get(k) for k in allowed if k in updates},
                  "after": {k: updates[k] for k in updates if k in allowed}})
    # Iter 327 — auch Konten-Änderungen in den Verlauf.
    try:
        from routes.resources.invoice_tracking import _build_diff, _history_log
        diff = _build_diff(target, updates)
        if diff:
            await _history_log(invoice_id, "edited", user, diff)
    except Exception:
        pass
    target.update(updates)
    return _strip(target)


# ===========================================================================
# Template-aware PDF (used by /invoices/{id}/pdf)
# ===========================================================================

def _render_rich_text(text: str, fmt: str) -> str:
    """Convert markdown/html/plain → reportlab Paragraph-safe HTML.
    Paragraph supports a subset of HTML tags only, so we run sanitisation
    after markdown rendering to drop anything unsupported (scripts, divs)."""
    if not text:
        return ""
    if fmt == "markdown":
        from markdown_it import MarkdownIt
        text = MarkdownIt().render(text)
    elif fmt == "text":
        # Plain text: preserve newlines, escape angle brackets
        text = (text.replace("&", "&amp;")
                    .replace("<", "&lt;").replace(">", "&gt;"))
        return text.replace("\n", "<br/>")
    # `html` and the post-markdown HTML path: keep a safe subset
    # ReportLab Paragraph honours <b>, <i>, <u>, <font>, <br/>, <a href>, <strong>, <em>.
    # Drop <p> wrappers (they break flow) and convert to <br/><br/>.
    text = re.sub(r"</p>\s*<p[^>]*>", "<br/><br/>", text)
    text = re.sub(r"</?p[^>]*>", "", text)
    # Drop block tags we cannot render
    text = re.sub(r"</?(div|ul|ol|li|h[1-6]|table|tr|td|th|tbody|thead|pre|code|blockquote)[^>]*>", "", text)
    # Strip script/style entirely
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    # Strip attributes except for <a href> + <font color/size>
    def _scrub(m):
        tag = m.group(1).lower()
        if tag in ("a",):
            href = re.search(r'href\s*=\s*"([^"]*)"', m.group(0))
            return f'<a href="{href.group(1)}">' if href else "<a>"
        if tag in ("font",):
            color = re.search(r'color\s*=\s*"([^"]*)"', m.group(0))
            size = re.search(r'size\s*=\s*"([^"]*)"', m.group(0))
            attrs = ""
            if color:
                attrs += f' color="{color.group(1)}"'
            if size:
                attrs += f' size="{size.group(1)}"'
            return f"<font{attrs}>"
        return f"<{tag}>"
    text = re.sub(r"<([A-Za-z][A-Za-z0-9]*)[^>]*>", _scrub, text)
    return text.strip()


def build_manual_invoice_pdf(invoice: dict, template: Optional[dict] = None) -> bytes:
    """Render a manual invoice into a polished A4 PDF respecting the template's
    header/footer/payment-terms/bank_details. Falls back to sensible defaults
    when no template is attached. Iter 295: optional logo + markdown/html
    formatting for header & footer."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    )

    BRAND = colors.HexColor("#4A5D4E")
    MUTED = colors.HexColor("#6B7280")
    BORDER = colors.HexColor("#E2E4E0")

    snap = invoice.get("snapshot") or {}
    lines = snap.get("lines") or []
    currency = invoice.get("currency", "EUR")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=22 * mm)
    styles = getSampleStyleSheet()
    p_title = ParagraphStyle("title", parent=styles["Title"], fontSize=20, textColor=BRAND,
                             spaceAfter=4, leading=24)
    p_sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10, textColor=MUTED,
                           spaceAfter=12)
    p_h = ParagraphStyle("h", parent=styles["Heading4"], textColor=BRAND, spaceBefore=8, spaceAfter=4)
    p_n = ParagraphStyle("n", parent=styles["Normal"], fontSize=10, leading=14)
    p_small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=MUTED, leading=11)

    flow = []

    # Logo (iter 295) — fetched synchronously since build_manual_invoice_pdf
    # always runs inside `asyncio.to_thread` (see PDF endpoint).
    logo_path = snap.get("logo_storage_path") or (template or {}).get("logo_storage_path")
    if logo_path:
        try:
            data, _ct = get_object(logo_path)
            img_buf = io.BytesIO(data)
            from PIL import Image as PILImage
            with PILImage.open(io.BytesIO(data)) as im:
                w, h = im.size
            # Constrain to ≤ 50mm wide / 25mm tall keeping aspect ratio
            max_w_mm, max_h_mm = 50, 25
            ratio = min(max_w_mm * mm / w, max_h_mm * mm / h)
            flow.append(Image(img_buf, width=w * ratio, height=h * ratio, hAlign="LEFT"))
            flow.append(Spacer(1, 8))
        except Exception as e:
            logger.warning("Could not embed template logo: %s", e)

    # Header (markdown / html / text)
    header_html = _render_rich_text(
        snap.get("header_text") or (template or {}).get("header_text", ""),
        snap.get("header_format") or (template or {}).get("header_format", "text"),
    )
    if header_html:
        flow.append(Paragraph(header_html, p_small))
        flow.append(Spacer(1, 6))

    flow.append(Paragraph(invoice.get("title") or "Rechnung", p_title))
    flow.append(Paragraph(f"Rechnungsnummer: <b>{invoice.get('invoice_number','-')}</b> &middot; "
                          f"Datum: {invoice.get('issue_date','-')}", p_sub))

    # Meta table (2 cols)
    meta = []
    for label, key in [
        ("Empfänger", "recipient_name"),
        ("Anschrift", "recipient_address"),
        ("Absender", "sender_org_unit"),
        ("Leistungszeitraum von", "service_period_from"),
        ("Leistungszeitraum bis", "service_period_to"),
        ("Konto", "account"),
        ("Kostenstelle", "cost_center"),
        ("Kostenträger", "cost_object"),
        ("Projekt", "project_code"),
    ]:
        v = invoice.get(key)
        if v:
            meta.append([Paragraph(f"<b>{label}</b>", p_n), Paragraph(str(v).replace("\n", "<br/>"), p_n)])
    if meta:
        t = Table(meta, colWidths=[45 * mm, None])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow.append(t)
        flow.append(Spacer(1, 12))

    # Line items
    flow.append(Paragraph("Positionen", p_h))
    head = [["Bezeichnung", "Menge", "Einheit", "Einzelpreis", "MwSt", "Gesamt"]]
    body = []
    for ln in lines:
        body.append([
            Paragraph((ln.get("label") or "") + ("<br/><font size='7' color='#6B7280'>"
                      + (ln.get("description") or "") + "</font>" if ln.get("description") else ""), p_n),
            f"{ln.get('quantity', 0)}",
            ln.get("unit", "") or "",
            f"{float(ln.get('unit_price', 0)):.2f} {currency}",
            f"{float(ln.get('tax_rate_effective') or 0):.0f}%",
            f"{float(ln.get('subtotal_gross', 0)):.2f} {currency}",
        ])
    if not body:
        body = [["(keine Posten)", "", "", "", "", ""]]

    table = Table(head + body, colWidths=[None, 16 * mm, 16 * mm, 26 * mm, 14 * mm, 28 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBF9")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flow.append(table)
    flow.append(Spacer(1, 8))

    # Iter 326 / 329 — Totals are right-aligned UNDER the line-items
    # "Gesamt" column so the user can read net/tax/gross in one vertical
    # visual flow. Column widths and paddings must match the line-items
    # table above exactly: [None=70mm, 16, 16, 26, 14, 28] mm.
    # NOTE Iter 329: using `None` for the spacer made the column collapse
    # because all cells were empty → totals drifted ~30mm to the left of
    # the items' Gesamt column. Hardcoding the spacer to 70mm (= 170mm
    # content – 100mm fixed cols on the items table) keeps alignment.
    totals_table = Table([
        ["", "Zwischensumme netto",
         f"{float(snap.get('subtotal_net', 0)):.2f} {currency}"],
        ["", "MwSt",
         f"{float(snap.get('total_tax', 0)):.2f} {currency}"],
        ["", "Gesamtsumme brutto",
         f"{float(snap.get('total_gross', 0)):.2f} {currency}"],
    ], colWidths=[70 * mm + 16 * mm + 16 * mm, 26 * mm + 14 * mm, 28 * mm])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),    # labels right-aligned next to value
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),    # values right-aligned under "Gesamt"
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (1, -1), (-1, -1), BRAND),
        ("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (1, -1), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        # Iter 329 — ReportLab inserts ~6pt extra space between the right
        # padding and number text in the items table; bump the totals
        # value cell padding to keep the EUR right-edge in sync.
        ("RIGHTPADDING", (2, 0), (2, -1), 14),
    ]))
    flow.append(totals_table)

    # Payment terms / notes / bank_details / footer
    if invoice.get("payment_terms"):
        flow.append(Spacer(1, 14))
        flow.append(Paragraph("<b>Zahlungsbedingungen</b>", p_h))
        flow.append(Paragraph(invoice["payment_terms"].replace("\n", "<br/>"), p_n))
    if invoice.get("notes"):
        flow.append(Spacer(1, 8))
        flow.append(Paragraph("<b>Hinweise</b>", p_h))
        flow.append(Paragraph(invoice["notes"].replace("\n", "<br/>"), p_n))
    if snap.get("bank_details"):
        flow.append(Spacer(1, 10))
        flow.append(Paragraph("<b>Bankverbindung</b>", p_h))
        flow.append(Paragraph(snap["bank_details"].replace("\n", "<br/>"), p_n))

    footer_html = _render_rich_text(
        snap.get("footer_text") or (template or {}).get("footer_text", ""),
        snap.get("footer_format") or (template or {}).get("footer_format", "text"),
    )
    if footer_html:
        flow.append(Spacer(1, 16))
        flow.append(Paragraph(footer_html, p_small))

    flow.append(Spacer(1, 12))
    flow.append(Paragraph(
        f"<font color='#6B7280' size='8'>Erzeugt {_now().strftime('%d.%m.%Y %H:%M')} UTC &middot; MeetFlow</font>",
        p_n
    ))

    doc.build(flow)
    return buf.getvalue()


@router.get("/invoices/{invoice_id}/pdf/manual")
async def get_manual_invoice_pdf(invoice_id: str, user=Depends(get_current_user)):
    """Re-render a stored manual invoice's PDF on demand."""
    if not await has_cap(user, "bookings.invoice", db):
        raise HTTPException(403, "Kein Zugriff")
    inv = await db.invoices.find_one({"invoice_id": invoice_id, "kind": "manual"}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Manuelle Rechnung nicht gefunden")
    tpl = None
    if inv.get("template_id"):
        tpl = await db.invoice_templates.find_one({"template_id": inv["template_id"]}, {"_id": 0})
    # Logo download and PIL inside build_manual_invoice_pdf are blocking; run
    # in a worker thread so the event loop stays responsive.
    pdf = await asyncio.to_thread(build_manual_invoice_pdf, inv, tpl)
    # Iter 363 — Einheitlicher Dateiname „Rechnung_<Nummer>.pdf"
    number = inv.get("invoice_number") or inv.get("invoice_id") or "rechnung"
    fname = f"Rechnung_{number}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="{fname}"'})


# ===========================================================================
# Erweiterter DATEV-CSV-Export inkl. Stammdaten-Zuordnung
# ===========================================================================

@router.get("/invoices/export/datev-extended.csv")
async def datev_extended_export(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    cost_center: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Datev-style export with all configurable accounting fields. Includes
    manual invoices created via the new flow. Designed to be parseable by
    standard DATEV "Buchungsstapel" tools."""
    if not await has_cap(user, "bookings.invoice", db):
        raise HTTPException(403, "Kein Zugriff")
    import csv as _csv
    q: dict = {}
    if cost_center:
        q["cost_center"] = cost_center
    if from_date or to_date:
        q["created_at"] = {}
        if from_date:
            q["created_at"]["$gte"] = datetime.fromisoformat(from_date + "T00:00:00+00:00")
        if to_date:
            q["created_at"]["$lte"] = datetime.fromisoformat(to_date + "T23:59:59+00:00")
    cursor = db.invoices.find(q, {"_id": 0}).sort("created_at", -1)
    buf = io.StringIO()
    w = _csv.writer(buf, delimiter=";")
    w.writerow([
        "Rechnungsnummer", "Datum", "Empfänger",
        "Konto", "Kostenstelle", "Kostenträger", "Projekt",
        "Brutto", "Netto", "MwSt", "Währung", "Status",
    ])
    async for d in cursor:
        snap = d.get("snapshot") or {}
        w.writerow([
            d.get("invoice_number") or d.get("invoice_id"),
            d.get("issue_date") or (d.get("created_at").isoformat()[:10] if isinstance(d.get("created_at"), datetime) else d.get("created_at")),
            d.get("recipient_name") or d.get("external_customer_name") or "",
            d.get("account") or "",
            d.get("cost_center") or "",
            d.get("cost_object") or "",
            d.get("project_code") or "",
            f"{snap.get('total_gross') or d.get('total') or 0:.2f}".replace(".", ","),
            f"{snap.get('subtotal_net') or d.get('total') or 0:.2f}".replace(".", ","),
            f"{snap.get('total_tax') or 0:.2f}".replace(".", ","),
            d.get("currency") or "EUR",
            d.get("status") or "",
        ])
    data = buf.getvalue().encode("utf-8-sig")
    fname = f"datev_extended_{_now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
