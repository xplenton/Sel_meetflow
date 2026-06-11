"""
Iter 292 — Drivers' license module.

- Each user can keep zero or more drivers' licenses on their own profile
  (`users.drivers_licenses` embedded array). Edit/delete is strictly limited
  to the user themselves (DSGVO/privacy by default).
- Front & back photos are uploaded to Object Storage under
  `meetflow/drivers-licenses/{user_id}/{lic_id}_{side}.{ext}` — never on
  local disk so they survive pod restarts and stay outside the public folder.
- An admin OR any user with the new capability `users.view_drivers_license`
  may read another user's licenses (e.g. "Fuhrpark-Manager"); CSV export
  feeds the Admin → Auswertungen → Führerscheine tab.
- The booking endpoint enforces `Resource.required_license_class` for
  vehicles (added separately in routes/resources/_common.py).
"""
import asyncio
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Response, Depends
from pydantic import BaseModel

from database import db
from dependencies import get_current_user
from services.permissions import has_cap
from services.storage import put_object, get_object, APP_STORAGE_PREFIX

router = APIRouter(tags=["drivers-license"])

# Standard German license classes (Iter 292) — UI surfaces them in a select;
# any other value is treated as a free-text custom entry per the user's choice
# at design time.
STANDARD_CLASSES = [
    "AM", "A1", "A2", "A",
    "B", "BE",
    "C1", "C1E", "C", "CE",
    "D1", "D1E", "D", "DE",
    "L", "T",
]

ALLOWED_PHOTO_TYPES = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB


class DriversLicenseIn(BaseModel):
    license_class: str  # standard code or custom_label content
    is_custom: bool = False
    custom_label: Optional[str] = None
    number: Optional[str] = None
    issuing_authority: Optional[str] = None
    issued_at: Optional[str] = None  # ISO date "YYYY-MM-DD"
    expires_at: Optional[str] = None
    notes: Optional[str] = None


def _serialize_license(lic: dict, include_paths: bool = False) -> dict:
    out = {
        "id": lic.get("id"),
        "license_class": lic.get("license_class"),
        "is_custom": lic.get("is_custom", False),
        "custom_label": lic.get("custom_label"),
        "number": lic.get("number"),
        "issuing_authority": lic.get("issuing_authority"),
        "issued_at": lic.get("issued_at"),
        "expires_at": lic.get("expires_at"),
        "notes": lic.get("notes"),
        "has_front_photo": bool(lic.get("front_storage_path")),
        "has_back_photo": bool(lic.get("back_storage_path")),
        # Iter 376 — per-side upload timestamps for the admin monitoring table.
        # Falls auf alten Eintraegen noch nicht gesetzt, fallback zu
        # `updated_at` (das letzte Mal, als die Lizenz irgendwie geaendert
        # wurde) — besser als gar nichts anzuzeigen.
        "front_uploaded_at": lic.get("front_uploaded_at") or (lic.get("updated_at") if lic.get("front_storage_path") else None),
        "back_uploaded_at": lic.get("back_uploaded_at") or (lic.get("updated_at") if lic.get("back_storage_path") else None),
        "created_at": lic.get("created_at"),
        "updated_at": lic.get("updated_at"),
    }
    if include_paths:
        out["front_storage_path"] = lic.get("front_storage_path")
        out["back_storage_path"] = lic.get("back_storage_path")
    return out


async def _can_view_other(viewer: dict) -> bool:
    if viewer.get("role") == "admin":
        return True
    return await has_cap(viewer, "users.view_drivers_license", db)


# ---------------- Self-service ----------------

@router.get("/users/me/drivers-licenses")
async def list_my_licenses(user=Depends(get_current_user)):
    """Caller's own license list — also includes photos URL hint."""
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "drivers_licenses": 1})
    return {"licenses": [_serialize_license(lic) for lic in (u or {}).get("drivers_licenses", [])]}


@router.post("/users/me/drivers-licenses")
async def create_my_license(payload: DriversLicenseIn, user=Depends(get_current_user)):
    if payload.is_custom and not (payload.custom_label or "").strip():
        raise HTTPException(400, "Eigene Klasse benötigt eine Bezeichnung")
    if not payload.is_custom and payload.license_class not in STANDARD_CLASSES:
        raise HTTPException(400, f"Unbekannte Führerscheinklasse: {payload.license_class}")
    lic = {
        "id": f"dl_{uuid.uuid4().hex[:12]}",
        "license_class": payload.license_class,
        "is_custom": payload.is_custom,
        "custom_label": (payload.custom_label or "").strip() or None,
        "number": (payload.number or "").strip() or None,
        "issuing_authority": (payload.issuing_authority or "").strip() or None,
        "issued_at": payload.issued_at,
        "expires_at": payload.expires_at,
        "notes": (payload.notes or "").strip() or None,
        "front_storage_path": None,
        "back_storage_path": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$push": {"drivers_licenses": lic}},
    )
    return _serialize_license(lic)


@router.put("/users/me/drivers-licenses/{lic_id}")
async def update_my_license(lic_id: str, payload: DriversLicenseIn, user=Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "drivers_licenses": 1})
    licenses = (u or {}).get("drivers_licenses", [])
    target = next((entry for entry in licenses if entry.get("id") == lic_id), None)
    if not target:
        raise HTTPException(404, "Führerschein nicht gefunden")
    target.update({
        "license_class": payload.license_class,
        "is_custom": payload.is_custom,
        "custom_label": (payload.custom_label or "").strip() or None,
        "number": (payload.number or "").strip() or None,
        "issuing_authority": (payload.issuing_authority or "").strip() or None,
        "issued_at": payload.issued_at,
        "expires_at": payload.expires_at,
        "notes": (payload.notes or "").strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"drivers_licenses": licenses}},
    )
    return _serialize_license(target)


@router.delete("/users/me/drivers-licenses/{lic_id}")
async def delete_my_license(lic_id: str, user=Depends(get_current_user)):
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$pull": {"drivers_licenses": {"id": lic_id}}},
    )
    return {"ok": True}


@router.post("/users/me/drivers-licenses/{lic_id}/photo")
async def upload_my_photo(
    lic_id: str,
    side: Literal["front", "back"] = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    if file.content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(400, f"Bildformat nicht erlaubt: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(400, "Maximal 5 MB pro Bild")
    ext = (file.filename or "img").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "png"
    path = f"{APP_STORAGE_PREFIX}/drivers-licenses/{user['user_id']}/{lic_id}_{side}.{ext}"
    await asyncio.to_thread(put_object, path, data, file.content_type or "image/png")
    field = "front_storage_path" if side == "front" else "back_storage_path"
    # Iter 376 — pro Seite separates Upload-Datum mitschreiben, damit der
    # Admin im Monitoring sehen kann, wann genau das Foto hochgeladen wurde
    # (das gemeinsame `updated_at` aendert sich auch bei reinen Metadaten-
    # Edits, ist also nicht aussagekraeftig).
    ts_field = "front_uploaded_at" if side == "front" else "back_uploaded_at"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"user_id": user["user_id"], "drivers_licenses.id": lic_id},
        {"$set": {f"drivers_licenses.$.{field}": path,
                  f"drivers_licenses.$.{ts_field}": now_iso,
                  "drivers_licenses.$.updated_at": now_iso}},
    )
    return {"ok": True, "side": side, "uploaded_at": now_iso}


async def _get_license_for_view(target_user_id: str, lic_id: str, viewer: dict) -> dict:
    if viewer["user_id"] != target_user_id and not await _can_view_other(viewer):
        raise HTTPException(403, "Kein Zugriff auf fremden Führerschein")
    u = await db.users.find_one(
        {"user_id": target_user_id}, {"_id": 0, "drivers_licenses": 1}
    )
    if not u:
        raise HTTPException(404, "Nutzer nicht gefunden")
    target = next((entry for entry in (u.get("drivers_licenses") or []) if entry.get("id") == lic_id), None)
    if not target:
        raise HTTPException(404, "Führerschein nicht gefunden")
    return target


@router.get("/users/me/drivers-licenses/{lic_id}/photo/{side}")
async def get_my_photo(
    lic_id: str,
    side: Literal["front", "back"],
    user=Depends(get_current_user),
):
    """Self-view of own photo (browser <img src>)."""
    target = await _get_license_for_view(user["user_id"], lic_id, user)
    path = target.get(f"{side}_storage_path")
    if not path:
        raise HTTPException(404, "Kein Foto hochgeladen")
    data, ct = await asyncio.to_thread(get_object, path)
    return Response(content=data, media_type=ct, headers={"Cache-Control": "private, max-age=60"})


# ---------------- Admin / Fuhrpark-Manager ----------------

@router.get("/users/{user_id}/drivers-licenses")
async def list_other_licenses(user_id: str, user=Depends(get_current_user)):
    if user_id != user["user_id"] and not await _can_view_other(user):
        raise HTTPException(403, "Kein Zugriff")
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "drivers_licenses": 1, "name": 1, "email": 1})
    if not u:
        raise HTTPException(404, "Nutzer nicht gefunden")
    return {
        "user_id": user_id,
        "name": u.get("name"),
        "email": u.get("email"),
        "licenses": [_serialize_license(entry) for entry in (u.get("drivers_licenses") or [])],
    }


@router.get("/users/{user_id}/drivers-licenses/{lic_id}/photo/{side}")
async def get_other_photo(
    user_id: str,
    lic_id: str,
    side: Literal["front", "back"],
    user=Depends(get_current_user),
):
    target = await _get_license_for_view(user_id, lic_id, user)
    path = target.get(f"{side}_storage_path")
    if not path:
        raise HTTPException(404, "Kein Foto hochgeladen")
    data, ct = await asyncio.to_thread(get_object, path)
    return Response(content=data, media_type=ct, headers={"Cache-Control": "private, max-age=60"})


@router.get("/admin/drivers-licenses")
async def list_all_licenses(
    license_class: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
    user=Depends(get_current_user),
):
    """Cross-user view. Filterable by class and 'expiring within N days'.
    Each row is one license — users with multiple licenses appear multiple times,
    which matches what an Auswertungen-style CSV export expects."""
    if not await _can_view_other(user):
        raise HTTPException(403, "Kein Zugriff")
    cutoff = None
    if expiring_within_days is not None:
        cutoff = (datetime.now(timezone.utc).date()).isoformat()
        from datetime import timedelta
        cutoff_max = (datetime.now(timezone.utc).date() + timedelta(days=expiring_within_days)).isoformat()
    else:
        cutoff_max = None
    rows = []
    cursor = db.users.find(
        {"drivers_licenses": {"$exists": True, "$ne": []}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "department": 1, "drivers_licenses": 1},
    )
    async for u in cursor:
        for lic in u.get("drivers_licenses") or []:
            if license_class and lic.get("license_class") != license_class:
                continue
            if cutoff_max and lic.get("expires_at"):
                if not (cutoff <= lic["expires_at"] <= cutoff_max):
                    continue
            row = _serialize_license(lic)
            row["user_id"] = u["user_id"]
            row["user_name"] = u.get("name")
            row["user_email"] = u.get("email")
            row["department"] = u.get("department")
            rows.append(row)
    return {"rows": rows, "total": len(rows)}


@router.get("/admin/drivers-licenses/export.csv")
async def export_csv(
    license_class: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
    user=Depends(get_current_user),
):
    if not await _can_view_other(user):
        raise HTTPException(403, "Kein Zugriff")
    data = await list_all_licenses(license_class=license_class, expiring_within_days=expiring_within_days, user=user)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "Nutzer-ID", "Name", "E-Mail", "Abteilung",
        "Klasse", "Bezeichnung", "Nummer", "Behörde",
        "Ausgestellt am", "Ablaufdatum", "Notiz",
        "Vorderseite", "Vorderseite hochgeladen am",
        "Rückseite", "Rückseite hochgeladen am",
        "Erstellt am", "Letzte Änderung",
    ])
    for r in data["rows"]:
        writer.writerow([
            r.get("user_id", ""), r.get("user_name", ""), r.get("user_email", ""), r.get("department", "") or "",
            r.get("license_class", ""), r.get("custom_label", "") or "",
            r.get("number", "") or "", r.get("issuing_authority", "") or "",
            r.get("issued_at", "") or "", r.get("expires_at", "") or "",
            (r.get("notes", "") or "").replace("\n", " "),
            "ja" if r.get("has_front_photo") else "nein",
            r.get("front_uploaded_at", "") or "",
            "ja" if r.get("has_back_photo") else "nein",
            r.get("back_uploaded_at", "") or "",
            r.get("created_at", "") or "",
            r.get("updated_at", "") or "",
        ])
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens UTF-8 correctly
    fname = f"fuehrerscheine_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
