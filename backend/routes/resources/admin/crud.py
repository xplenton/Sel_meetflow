"""
Resources/admin · CRUD module.

Core Resource lifecycle endpoints plus small "owns the resource itself"
extras (image upload, QR code, maintenance dates, floorplan-position write,
favorites, desk-listing-within-room, driving-log readout). Anything that
stays on the `/resources/...` URL family and doesn't justify its own file.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone
import os

from database import db
from dependencies import get_current_user
from services.permissions import require_cap, has_cap

from .._common import ResourceType, ResourceStatus, Resource, _parse_iso

router = APIRouter()


# ---------------------------------------------------------------------------
# Resource CRUD
# ---------------------------------------------------------------------------

@router.get("/resources")
async def list_resources(
    type: Optional[ResourceType] = None,
    location: Optional[str] = None,
    status: Optional[ResourceStatus] = None,
    include_children: bool = False,
    user=Depends(get_current_user),
):
    """List resources visible to the user. Top-level only by default."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff auf Ressourcen-Modul")
    q: dict = {}
    if not include_children:
        q["parent_resource_id"] = None
    if type:
        q["type"] = type
    if location:
        q["location"] = location
    if status:
        q["status"] = status
    items = await db.resources.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    return items


@router.get("/resources/{resource_id}")
async def get_resource(resource_id: str, user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    res = await db.resources.find_one({"resource_id": resource_id}, {"_id": 0})
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    if res.get("is_splitable"):
        children = await db.resources.find(
            {"parent_resource_id": resource_id}, {"_id": 0}
        ).sort("sub_id", 1).to_list(10)
        res["children"] = children
    return res


@router.post("/resources")
async def create_resource(payload: Resource, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    payload.created_at = datetime.now(timezone.utc)
    payload.updated_at = payload.created_at
    doc = payload.model_dump()
    await db.resources.insert_one(doc)
    # If splitable: create one child resource per sub-resource for independent
    # bookability. The parent represents the "whole room"; allowed_combinations
    # is a UI hint indicating which child-combinations behave as the parent.
    if payload.is_splitable and payload.sub_resources:
        if len(payload.sub_resources) > 3:
            raise HTTPException(400, "Maximal 3 Teilbereiche erlaubt")
        for sub in payload.sub_resources:
            child = Resource(
                name=f"{payload.name} — {sub.name}",
                type="room",
                location=payload.location,
                building=payload.building,
                floor=payload.floor,
                capacity=sub.capacity,
                equipment=sub.equipment,
                parent_resource_id=payload.resource_id,
                sub_id=sub.sub_id,
                allow_catering=payload.allow_catering,
                owner_user_id=payload.owner_user_id,
                owner_group_id=payload.owner_group_id,
            )
            await db.resources.insert_one(child.model_dump())
    doc.pop("_id", None)
    return doc


@router.put("/resources/{resource_id}")
async def update_resource(resource_id: str, payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    payload["updated_at"] = datetime.now(timezone.utc)
    payload.pop("_id", None)
    payload.pop("resource_id", None)
    res = await db.resources.find_one_and_update(
        {"resource_id": resource_id},
        {"$set": payload},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    return res


@router.delete("/resources/{resource_id}")
async def delete_resource(resource_id: str, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    open_bk = await db.resource_bookings.count_documents({
        "resource_id": resource_id,
        "status": {"$in": ["confirmed", "pending_approval"]},
        "end_at": {"$gte": datetime.now(timezone.utc)},
    })
    if open_bk:
        raise HTTPException(400, f"{open_bk} offene Buchungen — bitte zuerst stornieren")
    await db.resources.delete_many({
        "$or": [{"resource_id": resource_id}, {"parent_resource_id": resource_id}]
    })
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Calendar (per-resource view) — used by the booking dialog
# ---------------------------------------------------------------------------

@router.get("/resources/{resource_id}/calendar")
async def resource_calendar(
    resource_id: str,
    from_date: str,
    to_date: str,
    user=Depends(get_current_user),
):
    """Return all bookings for a resource (and its parent/children) in the window."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    res = await db.resources.find_one({"resource_id": resource_id}, {"_id": 0})
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    ids = [resource_id]
    if res.get("parent_resource_id"):
        ids.append(res["parent_resource_id"])
    if res.get("is_splitable"):
        ids += [c["resource_id"] for c in await db.resources.find(
            {"parent_resource_id": resource_id}, {"_id": 0, "resource_id": 1}).to_list(10)]
    start = _parse_iso(from_date)
    end = _parse_iso(to_date)
    bookings = await db.resource_bookings.find({
        "resource_id": {"$in": ids},
        "status": {"$in": ["confirmed", "pending_approval"]},
        "start_at": {"$lt": end},
        "end_at": {"$gt": start},
    }, {"_id": 0}).sort("start_at", 1).to_list(500)
    for b in bookings:
        for k in ("start_at", "end_at"):
            if isinstance(b.get(k), datetime):
                b[k] = b[k].isoformat()
    return {"resource_ids": ids, "bookings": bookings}


# ---------------------------------------------------------------------------
# Image / QR / Maintenance / Floorplan-position write
# ---------------------------------------------------------------------------

@router.post("/resources/{resource_id}/image")
async def upload_resource_image(resource_id: str, attachment_id: str, user=Depends(get_current_user)):
    """Link an already-uploaded attachment (via /api/attachments/upload) as resource image."""
    await require_cap(user, "resources.manage", db)
    res = await db.resources.find_one({"resource_id": resource_id}, {"_id": 0})
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    image_url = f"/api/attachments/{attachment_id}"
    await db.resources.update_one(
        {"resource_id": resource_id},
        {"$set": {"image_url": image_url, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"image_url": image_url}


@router.get("/resources/{resource_id}/qr")
async def resource_qr(resource_id: str, user=Depends(get_current_user)):
    """Generate a QR-code PNG (base64 data-URL) deep-linking to the booking dialog."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    res = await db.resources.find_one({"resource_id": resource_id}, {"_id": 0})
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    frontend_url = os.environ.get("FRONTEND_URL", "")
    deep_link = f"{frontend_url}/resources?book={resource_id}"
    try:
        import qrcode
        import io
        import base64
        img = qrcode.make(deep_link)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_b64 = base64.b64encode(buf.getvalue()).decode()
        data_url = f"data:image/png;base64,{png_b64}"
        # cache on the resource so it's served instantly next time
        await db.resources.update_one({"resource_id": resource_id}, {"$set": {"qr_code_url": data_url}})
        return {"qr_code_url": data_url, "deep_link": deep_link}
    except Exception as e:
        raise HTTPException(500, f"QR-Code-Erzeugung fehlgeschlagen: {e}")


# ---------------------------------------------------------------------------
# Iter 371 — QR-Code-Bulk-Druckblatt (A4, 12 QR-Codes pro Seite mit Schnittmarken)
# ---------------------------------------------------------------------------

@router.post("/resources-qr-bulk-pdf")
async def resource_qr_bulk_pdf(payload: dict, user=Depends(get_current_user)):
    """Generate an A4 PDF with up to 12 QR-codes per page for the given resource IDs.

    Body:
        { "resource_ids": ["res_abc", "res_def", ...] }

    Layout:
      - 3 columns × 4 rows = 12 codes per A4 page
      - Each cell: QR code (~55mm), resource name (bold), location/details
      - Light dashed cut-marks between cells so the print shop can guillotine them
      - Centered footer with deep-link domain so users know where they're scanning to

    Returns: streaming PDF response (application/pdf).
    """
    from fastapi.responses import StreamingResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import qrcode
    import io

    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")

    resource_ids = payload.get("resource_ids") or []
    if not isinstance(resource_ids, list) or not resource_ids:
        raise HTTPException(400, "resource_ids muss eine nicht-leere Liste sein")
    if len(resource_ids) > 500:
        raise HTTPException(400, "Maximal 500 Ressourcen pro Druck")

    # Preserve caller-provided order; only fetch the requested IDs.
    resources = await db.resources.find(
        {"resource_id": {"$in": resource_ids}}, {"_id": 0}
    ).to_list(len(resource_ids))
    by_id = {r["resource_id"]: r for r in resources}
    ordered = [by_id[rid] for rid in resource_ids if rid in by_id]
    if not ordered:
        raise HTTPException(404, "Keine Ressourcen gefunden")

    frontend_url = os.environ.get("FRONTEND_URL", "").rstrip("/")

    # Page geometry: A4 = 210×297mm. 12 codes/page in a 3×4 grid.
    page_w, page_h = A4
    cols, rows = 3, 4
    margin_x = 8 * mm
    margin_y = 10 * mm
    cell_w = (page_w - 2 * margin_x) / cols
    cell_h = (page_h - 2 * margin_y) / rows
    qr_size = min(cell_w, cell_h) - 22 * mm  # ~55mm for the QR, rest for labels

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("MeetFlow — QR-Codes")

    per_page = cols * rows
    for idx, res in enumerate(ordered):
        slot = idx % per_page
        if slot == 0 and idx > 0:
            c.showPage()
        col = slot % cols
        row = slot // cols
        # top-left corner of this cell (PDF origin is bottom-left)
        x0 = margin_x + col * cell_w
        y0 = page_h - margin_y - (row + 1) * cell_h

        # Dashed cut marks around the cell — only inner edges to save toner.
        c.setDash(1, 2)
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.setLineWidth(0.3)
        if col < cols - 1:
            c.line(x0 + cell_w, y0, x0 + cell_w, y0 + cell_h)
        if row < rows - 1:
            c.line(x0, y0, x0 + cell_w, y0)
        c.setDash()  # reset

        # Generate QR
        deep_link = f"{frontend_url}/resources?book={res['resource_id']}"
        qr_img = qrcode.make(deep_link)
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)

        qr_x = x0 + (cell_w - qr_size) / 2
        qr_y = y0 + cell_h - qr_size - 6 * mm
        c.drawImage(ImageReader(qr_buf), qr_x, qr_y, qr_size, qr_size,
                    preserveAspectRatio=True, mask='auto')

        # Name (bold, centered)
        name = (res.get("name") or res["resource_id"])[:40]
        c.setFillColorRGB(0.11, 0.12, 0.11)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x0 + cell_w / 2, qr_y - 5 * mm, name)

        # Sub-line: location · building · floor · plate · desk_number
        sub_parts = [res.get(k) for k in ("location", "building", "floor",
                                          "license_plate", "desk_number")]
        sub = " · ".join([s for s in sub_parts if s])[:60]
        if sub:
            c.setFillColorRGB(0.42, 0.45, 0.50)
            c.setFont("Helvetica", 8)
            c.drawCentredString(x0 + cell_w / 2, qr_y - 9 * mm, sub)

        # Resource ID (small, gray) — useful for asset-tag reconciliation.
        c.setFillColorRGB(0.6, 0.6, 0.6)
        c.setFont("Helvetica", 6)
        c.drawCentredString(x0 + cell_w / 2, qr_y - 12.5 * mm, res["resource_id"])

    # Footer on each page: tenant domain so people know what they scan.
    # We add it AFTER the loop by walking the saved pages — simplest: redraw
    # by saving the canvas and re-opening would be overkill. Skip footer for
    # now; QR-code itself contains the URL.

    c.save()
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=qr-codes.pdf"},
    )


@router.put("/resources/{resource_id}/maintenance")
async def set_maintenance(resource_id: str, payload: dict, user=Depends(get_current_user)):
    """payload: {tuev_due: 'YYYY-MM-DD', insurance_due: 'YYYY-MM-DD', service_due: 'YYYY-MM-DD'}"""
    await require_cap(user, "resources.manage", db)
    fields = {k: payload.get(k) for k in ("tuev_due", "insurance_due", "service_due") if k in payload}
    if not fields:
        raise HTTPException(400, "Keine Wartungs-Felder")
    fields["updated_at"] = datetime.now(timezone.utc)
    res = await db.resources.find_one_and_update(
        {"resource_id": resource_id}, {"$set": fields},
        return_document=True, projection={"_id": 0},
    )
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    return res


@router.put("/resources/{resource_id}/floorplan")
async def set_floorplan_position(resource_id: str, payload: dict, user=Depends(get_current_user)):
    """Place a desk/room on its parent floorplan.
    payload: {x: 0..1, y: 0..1, width: 0..1, height: 0..1, floor_plan_id: str}
    All coords are normalised 0..1 so the same plan scales across screens."""
    await require_cap(user, "resources.manage", db)
    fields = {}
    for k in ("x", "y", "width", "height"):
        if k in payload:
            v = float(payload[k])
            if not 0 <= v <= 1:
                raise HTTPException(400, f"{k} muss zwischen 0 und 1 liegen")
            fields[k] = v
    if "floor_plan_id" in payload:
        fields["floor_plan_id"] = payload["floor_plan_id"]
    if not fields:
        raise HTTPException(400, "Keine Lageplan-Felder")
    fields["updated_at"] = datetime.now(timezone.utc)
    res = await db.resources.find_one_and_update(
        {"resource_id": resource_id}, {"$set": fields},
        return_document=True, projection={"_id": 0},
    )
    if not res:
        raise HTTPException(404, "Ressource nicht gefunden")
    return res


# ---------------------------------------------------------------------------
# Desks: list-in-room + favorites
# ---------------------------------------------------------------------------

@router.get("/desk-rooms/{room_id}/desks")
async def list_desks_in_room(room_id: str, user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    items = await db.resources.find({"parent_resource_id": room_id, "type": "desk"}, {"_id": 0}).to_list(200)
    return items


@router.get("/favorites/desks")
async def list_favorite_desks(user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    fav = await db.user_favorites.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    return {"desk_ids": fav.get("desk_ids", [])}


@router.post("/favorites/desks/{desk_id}")
async def add_favorite_desk(desk_id: str, user=Depends(get_current_user)):
    await db.user_favorites.update_one(
        {"user_id": user["user_id"]},
        {"$addToSet": {"desk_ids": desk_id},
         "$set": {"updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"added": desk_id}


@router.delete("/favorites/desks/{desk_id}")
async def remove_favorite_desk(desk_id: str, user=Depends(get_current_user)):
    await db.user_favorites.update_one(
        {"user_id": user["user_id"]},
        {"$pull": {"desk_ids": desk_id}},
    )
    return {"removed": desk_id}
