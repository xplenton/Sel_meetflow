"""
Shared helpers, models and constants for the resources package.
Imported by bookings.py, catering.py, invoices.py, admin.py.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid
from database import db

# Type aliases
ResourceType = Literal["room", "desk", "vehicle"]
ResourceStatus = Literal["active", "inactive", "blocked", "maintenance"]
BookingStatus = Literal["confirmed", "pending_approval", "cancelled", "completed", "no_show"]
CateringStatus = Literal["requested", "confirmed", "rejected", "in_progress", "delivered", "completed", "cancelled"]

# Catering rejection reasons (master list) — P2 §11
CATERING_REJECTION_REASONS = [
    "Artikel nicht verfügbar",
    "Vorlaufzeit zu kurz",
    "Personalkapazitaet nicht ausreichend",
    "Budget / Kostenstelle nicht freigegeben",
    "Raumaenderung erforderlich",
    "Sonstiger Grund",
]

# Upload-Limits — defaults (overridable via /resource-upload-config)
DEFAULT_UPLOAD_MAX_MB = 10
DEFAULT_UPLOAD_MIMES = [
    # Dokumente
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Bilder
    "image/jpeg", "image/png", "image/gif", "image/webp",
    # Text
    "text/plain", "text/csv",
]

# Internal dummy router; sub-modules build their own.
router = APIRouter()


class SubResourceConfig(BaseModel):
    """Sub-room definition for splitable meeting rooms."""
    sub_id: str  # e.g. "A", "B", "C"
    name: str
    capacity: Optional[int] = None
    equipment: List[str] = []


class Resource(BaseModel):
    resource_id: str = Field(default_factory=lambda: f"res_{uuid.uuid4().hex[:12]}")
    name: str
    type: ResourceType
    location: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    capacity: Optional[int] = None
    equipment: List[str] = []  # ["Beamer", "Whiteboard", ...]
    seating: Optional[str] = None  # for rooms
    status: ResourceStatus = "active"
    notes: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_group_id: Optional[str] = None
    image_url: Optional[str] = None
    qr_code_url: Optional[str] = None
    # Booking constraints
    min_duration_min: Optional[int] = None
    max_duration_min: Optional[int] = None
    lead_time_min: Optional[int] = 0
    buffer_time_min: Optional[int] = 0
    requires_approval: bool = False
    allow_catering: bool = False
    # Vehicle specifics
    license_plate: Optional[str] = None
    vehicle_type: Optional[str] = None
    seats: Optional[int] = None
    fuel_card: bool = False
    fuel_card_number: Optional[str] = None  # Iter 229 §15 — Tankkartennummer
    drive_type: Optional[Literal["benzin", "diesel", "elektro", "hybrid", "gas"]] = None  # Iter 229 §15 — Antriebsart
    required_license_class: Optional[str] = None  # Iter 292 — z.B. "B", "BE", "CE" — Buchung wird blockiert wenn Nutzer diese Klasse nicht hat
    mileage: Optional[int] = None
    # ----- Iter 299 — Fuhrpark-Stammblatt -----
    # Identität & Technik
    first_registration: Optional[str] = None       # ISO date — Erstzulassung
    vin: Optional[str] = None                       # Fahrgestellnummer
    engine_ccm: Optional[int] = None                # Hubraum
    engine_kw: Optional[int] = None                 # Leistung (kW)
    # Prüfungen
    tuev_next: Optional[str] = None                 # nächste Hauptuntersuchung
    au_next: Optional[str] = None                   # nächste Abgasuntersuchung
    next_service_due: Optional[str] = None          # nächster Service / Inspektion
    last_oil_change: Optional[str] = None
    # Reifen
    has_summer_tires: bool = False
    summer_tire_depth_mm: Optional[float] = None
    has_winter_tires: bool = False
    winter_tire_depth_mm: Optional[float] = None
    current_tires: Optional[Literal["summer", "winter", "allseason"]] = None
    # Versicherung & Verträge
    insurance_policy_no: Optional[str] = None
    insurance_expires: Optional[str] = None
    ownership: Optional[Literal["owned", "leased"]] = None
    leasing_company: Optional[str] = None
    leasing_end: Optional[str] = None
    # Sonstiges
    parking_location: Optional[str] = None
    fleet_status: Optional[Literal["in_service", "service_pending", "out_of_service", "sold"]] = None
    # Desk specifics
    desk_number: Optional[str] = None
    accessibility: Optional[str] = None
    # Splitable room
    is_splitable: bool = False
    sub_resources: List[SubResourceConfig] = []  # max 3
    allowed_combinations: List[List[str]] = []
    parent_resource_id: Optional[str] = None
    sub_id: Optional[str] = None
    # Visibility
    allowed_group_ids: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResourceBooking(BaseModel):
    booking_id: str = Field(default_factory=lambda: f"bk_{uuid.uuid4().hex[:12]}")
    resource_id: str
    user_id: str
    booked_for_user_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    start_at: datetime
    end_at: datetime
    status: BookingStatus = "confirmed"
    purpose: Optional[str] = None
    destination: Optional[str] = None
    passengers: List[str] = []
    mileage_before: Optional[int] = None
    mileage_after: Optional[int] = None
    cost_center: Optional[str] = None
    account: Optional[str] = None
    catering_request_id: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[str] = None
    cancellation_reason: Optional[str] = None
    checked_in_at: Optional[datetime] = None
    checked_out_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CateringItem(BaseModel):
    item_id: str = Field(default_factory=lambda: f"cit_{uuid.uuid4().hex[:10]}")
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: float = 0.0
    unit: str = "Stueck"
    available: bool = True
    min_quantity: int = 1
    lead_time_min: int = 60
    status: Literal["active", "inactive"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CateringLine(BaseModel):
    item_id: str
    quantity: int
    notes: Optional[str] = None


class CateringRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"cat_{uuid.uuid4().hex[:12]}")
    booking_id: str
    user_id: str
    items: List[CateringLine] = []
    delivery_at: Optional[datetime] = None
    delivery_target: Optional[str] = None  # "main"/"A"/"B"/"C"
    contact: Optional[str] = None
    notes: Optional[str] = None
    cost_center: Optional[str] = None
    account: Optional[str] = None
    attachments: List[str] = []
    status: CateringStatus = "requested"
    rejection_reason: Optional[str] = None
    processed_by: Optional[str] = None
    processed_at: Optional[datetime] = None
    task_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Resources CRUD
# ============================================================================

# Iter 346 — Conflict-check logic moved to services.booking_conflicts so the
# routes package no longer owns the bookings business rules. The underscore-
# prefixed names are kept as thin shims for backwards compatibility with the
# many call sites + tests that import them from `_common`.
from services.booking_conflicts import (  # noqa: E402  (top-level shim)
    check_conflicts as _check_conflicts,
    verify_booking_winner as _verify_booking_winner,
    validate_allowed_combination as _validate_allowed_combination,
)


async def _audit_booking(actor: dict, booking_id: str, action: str, details: dict) -> None:
    """Light-weight audit log for booking lifecycle (Sec 19 — Revisionssicher)."""
    try:
        from services.permission_audit import log_caps_change
        await log_caps_change(actor, booking_id, action, details, category="bookings")
    except Exception:
        pass


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _notify_approvers(resource: dict, booking: ResourceBooking) -> None:
    """Shim — see services.booking_notifications."""
    from services.booking_notifications import notify_approvers
    await notify_approvers(resource, booking)


async def _notify_catering_team(catering, resource: dict, booking) -> None:
    """Shim — see services.booking_notifications."""
    from services.booking_notifications import notify_catering_team
    await notify_catering_team(catering, resource, booking)


async def _notify_catering_status(cr: dict, new_status: str) -> None:
    """Shim — see services.booking_notifications."""
    from services.booking_notifications import notify_catering_status
    await notify_catering_status(cr, new_status)


# ----- P0 #5: CSV exports ---------------------------------------------------
# ----- P0 #5: CSV / XLSX / PDF exports --------------------------------------
# Iter 349 — bodies moved to services.csv_export + services.pdf_invoices so
# `_common.py` stays focused on models/constants. The underscore-prefixed
# names below are kept as thin shims for backwards compat with existing
# call sites in `invoices.py` and `invoice_tracking.py`.
def _csv_line(values: List) -> str:
    from services.csv_export import csv_line
    return csv_line(values)


def _build_invoice_pdf(*, title: str, subtitle: str, header_info: List, lines: List, total: float, currency: str = "EUR") -> bytes:
    from services.pdf_invoices import build_invoice_pdf
    return build_invoice_pdf(
        title=title, subtitle=subtitle, header_info=header_info,
        lines=lines, total=total, currency=currency,
    )


def _build_xlsx(rows: list, headers: list, filename: str) -> bytes:
    from services.csv_export import build_xlsx
    return build_xlsx(rows, headers, filename)


async def _get_upload_config() -> dict:
    """Aktive Upload-Konfiguration fuer Ressourcen-/Catering-Anhaenge.
    Persistiert in `db.app_settings.resource_uploads`. Faellt auf Defaults zurueck."""
    cfg = await db.app_settings.find_one(
        {"key": "resource_uploads"}, {"_id": 0}) or {}
    return {
        "max_size_mb": int(cfg.get("max_size_mb") or DEFAULT_UPLOAD_MAX_MB),
        "allowed_mimes": cfg.get("allowed_mimes") or DEFAULT_UPLOAD_MIMES,
    }


async def _validate_attachment(attachment_id: str) -> None:
    """Prueft groesse + mime eines GridFS-Anhangs gegen die aktive Config.
    Wirft 413/415, wenn die Datei das Limit/Whitelist verletzt."""
    cfg = await _get_upload_config()
    meta = await db.attachments.files.find_one(
        {"_id": attachment_id}, {"length": 1, "metadata": 1})
    if not meta:
        raise HTTPException(404, f"Anhang {attachment_id} nicht gefunden")
    size = int(meta.get("length") or 0)
    max_bytes = int(cfg["max_size_mb"]) * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(
            413,
            f"Datei zu gross: {size // (1024*1024)} MB > {cfg['max_size_mb']} MB Limit",
        )
    mime = ((meta.get("metadata") or {}).get("mime") or "").lower()
    if cfg["allowed_mimes"] and mime not in [m.lower() for m in cfg["allowed_mimes"]]:
        raise HTTPException(
            415,
            f"Dateityp nicht erlaubt: {mime or 'unbekannt'}",
        )


