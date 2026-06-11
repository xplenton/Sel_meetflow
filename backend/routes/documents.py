from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
import os
import uuid
import asyncio
import io
import requests as sync_requests
from datetime import datetime, timezone
from database import db, logger
from dependencies import get_current_user
from services.storage import put_object, get_object, init_storage, STORAGE_URL, APP_STORAGE_PREFIX
from services.email import send_email_real
from services.ws_manager import ws_manager

router = APIRouter()


async def _log_doc_audit(doc_id: str, meeting_id: str, action: str, user_id: str = "", user_name: str = "", user_email: str = "", ip: str = "", details: str = ""):
    await db.document_audit_logs.insert_one({
        "log_id": f"audit_{uuid.uuid4().hex[:10]}",
        "doc_id": doc_id, "meeting_id": meeting_id,
        "action": action, "user_id": user_id, "user_name": user_name, "user_email": user_email,
        "ip": ip, "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

@router.get("/meetings/{meeting_id}/documents/{doc_id}/audit-log")
async def get_document_audit_log(meeting_id: str, doc_id: str, request: Request):
    await get_current_user(request)
    logs = await db.document_audit_logs.find(
        {"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(200)
    return logs



@router.post("/meetings/{meeting_id}/documents/{doc_id}/signature-fields")
async def add_signature_field(meeting_id: str, doc_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    field_id = f"sf_{uuid.uuid4().hex[:8]}"
    field = {
        "field_id": field_id,
        "x": body.get("x", 0), "y": body.get("y", 0),
        "page": body.get("page", 1),
        "width": body.get("width", 200), "height": body.get("height", 60),
        "assigned_to": body.get("assigned_to", ""),
        "assigned_name": body.get("assigned_name", ""),
        "label": body.get("label", "Unterschrift"),
        "status": "pending",
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.meeting_documents.update_one(
        {"doc_id": doc_id, "meeting_id": meeting_id},
        {"$push": {"signature_fields": field}}
    )
    return field

@router.get("/meetings/{meeting_id}/documents/{doc_id}/signature-fields")
async def get_signature_fields(meeting_id: str, doc_id: str, request: Request):
    await get_current_user(request)
    doc = await db.meeting_documents.find_one({"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0, "storage_path": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    fields = doc.get("signature_fields", [])
    sigs = doc.get("signatures", [])
    # Enrich fields with signature status
    for f in fields:
        matching_sig = next((s for s in sigs if s.get("field_id") == f["field_id"]), None)
        if matching_sig:
            f["status"] = "signed"
            f["signed_by"] = matching_sig.get("signer_name", "")
            f["signed_at"] = matching_sig.get("signed_at", "")
    total = len(fields)
    signed = len([f for f in fields if f.get("status") == "signed"])
    return {"fields": fields, "total": total, "signed": signed}

@router.put("/meetings/{meeting_id}/documents/{doc_id}/signature-fields/{field_id}")
async def update_signature_field(meeting_id: str, doc_id: str, field_id: str, request: Request):
    await get_current_user(request)
    body = await request.json()
    update = {}
    for key in ["x", "y", "width", "height", "page", "label", "assigned_to", "assigned_name"]:
        if key in body:
            update[f"signature_fields.$.{key}"] = body[key]
    if update:
        await db.meeting_documents.update_one(
            {"doc_id": doc_id, "meeting_id": meeting_id, "signature_fields.field_id": field_id},
            {"$set": update}
        )
    return {"updated": field_id}

@router.delete("/meetings/{meeting_id}/documents/{doc_id}/signature-fields/{field_id}")
async def delete_signature_field(meeting_id: str, doc_id: str, field_id: str, request: Request):
    await get_current_user(request)
    await db.meeting_documents.update_one(
        {"doc_id": doc_id, "meeting_id": meeting_id},
        {"$pull": {"signature_fields": {"field_id": field_id}}}
    )
    return {"deleted": field_id}

@router.get("/meetings/{meeting_id}/documents/{doc_id}/audit-log/pdf")
async def export_audit_log_pdf(meeting_id: str, doc_id: str, request: Request):
    await get_current_user(request)
    doc = await db.meeting_documents.find_one({"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0, "storage_path": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    logs = await db.document_audit_logs.find(
        {"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0}
    ).sort("timestamp", 1).to_list(500)

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("AuditTitle", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#4A5D4E"), spaceAfter=6)
    sub_style = ParagraphStyle("AuditSub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6B7280"), spaceAfter=12)
    label_map = {"uploaded": "Hochgeladen", "viewed": "Angesehen/Heruntergeladen", "presented": "Präsentation gestartet", "presentation_stopped": "Präsentation beendet", "signed": "Unterschrieben (Live)", "signed_async": "Unterschrieben (Async)", "signature_requested": "Unterschrift angefordert", "sent_for_signing": "Zum Unterschreiben versendet"}

    elements = []
    elements.append(Paragraph("Dokumenten-Audit-Trail", title_style))
    meeting_title = meeting.get("title", "") if meeting else ""
    elements.append(Paragraph(f"Dokument: {doc.get('filename', '')} | Meeting: {meeting_title}", sub_style))
    elements.append(Paragraph(f"Erstellt am: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC | Eintraege: {len(logs)}", sub_style))
    elements.append(Spacer(1, 4*mm))

    # Signatures summary
    sigs = doc.get("signatures", [])
    if sigs:
        elements.append(Paragraph(f"Unterschriften ({len(sigs)}):", ParagraphStyle("SigHead", parent=styles["Heading3"], fontSize=11, textColor=colors.HexColor("#4A5D4E"), spaceAfter=4)))
        sig_data = [["Name", "E-Mail", "Typ", "Datum"]]
        for s in sigs:
            sig_data.append([s.get("signer_name", ""), s.get("signer_email", ""), s.get("type", ""), s.get("signed_at", "")[:19].replace("T", " ")])
        sig_table = Table(sig_data, colWidths=[45*mm, 55*mm, 25*mm, 40*mm])
        sig_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5D4E")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E4E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(sig_table)
        elements.append(Spacer(1, 6*mm))

    # Audit log table
    elements.append(Paragraph(f"Aktivitaetsprotokoll ({len(logs)} Eintraege):", ParagraphStyle("LogHead", parent=styles["Heading3"], fontSize=11, textColor=colors.HexColor("#4A5D4E"), spaceAfter=4)))
    if logs:
        log_data = [["Zeitpunkt", "Aktion", "Benutzer", "IP", "Details"]]
        for log in logs:
            ts = log.get("timestamp", "")[:19].replace("T", " ")
            action = label_map.get(log.get("action", ""), log.get("action", ""))
            name = log.get("user_name") or log.get("user_email") or "Anonym"
            ip = log.get("ip", "")
            details = log.get("details", "")[:60]
            log_data.append([ts, action, name, ip, details])
        log_table = Table(log_data, colWidths=[35*mm, 40*mm, 35*mm, 25*mm, 35*mm])
        log_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5D4E")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E4E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(log_table)
    else:
        elements.append(Paragraph("Keine Eintraege vorhanden.", styles["Normal"]))

    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(f"Generiert von MeetFlow | Dokument-ID: {doc_id}", ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#9CA3AF"))))

    pdf.build(elements)
    return Response(content=buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="audit_trail_{doc_id}.pdf"'})



@router.post("/meetings/{meeting_id}/documents")
async def upload_meeting_document(meeting_id: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    allowed = ("pdf", "doc", "docx", "png", "jpg", "jpeg", "webp")
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {', '.join(allowed)}")
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    path = f"{APP_STORAGE_PREFIX}/documents/{meeting_id}/{doc_id}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, data, file.content_type or "application/octet-stream")
        storage_path = result.get("path", path)
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
    sign_token = uuid.uuid4().hex[:16]
    doc_count = await db.meeting_documents.count_documents({"meeting_id": meeting_id})
    doc = {
        "doc_id": doc_id, "meeting_id": meeting_id, "filename": file.filename,
        "file_ext": ext, "file_size": len(data), "storage_path": storage_path,
        "uploaded_by": user["user_id"], "uploader_name": user.get("name", ""),
        "sign_token": sign_token, "signatures": [], "requires_signature": False,
        "presenting": False, "current_page": 1,
        "sort_order": doc_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.meeting_documents.insert_one(doc)
    await _log_doc_audit(doc_id, meeting_id, "uploaded", user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "", f"Datei: {file.filename} ({len(data)} Bytes)")
    return {"doc_id": doc_id, "filename": file.filename, "sign_token": sign_token}

@router.get("/meetings/{meeting_id}/documents")
async def list_meeting_documents(meeting_id: str, request: Request):
    await get_current_user(request)
    docs = await db.meeting_documents.find({"meeting_id": meeting_id}, {"_id": 0, "storage_path": 0}).sort([("sort_order", 1), ("created_at", 1)]).to_list(100)
    return docs

@router.delete("/meetings/{meeting_id}/documents/{doc_id}")
async def delete_meeting_document(meeting_id: str, doc_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.meeting_documents.find_one({"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    is_host = meeting and meeting.get("host_id") == user["user_id"]
    is_uploader = doc.get("uploaded_by") == user["user_id"]
    if not is_host and not is_uploader:
        raise HTTPException(status_code=403, detail="Only host or uploader can delete")
    # Delete from storage
    try:
        storage_path = doc.get("storage_path")
        if storage_path:
            key = init_storage()
            if key:
                sync_requests.delete(
                    f"{STORAGE_URL}/objects/{storage_path}",
                    headers={"X-Storage-Key": key}, timeout=30
                )
    except Exception as e:
        logger.warning(f"Storage delete failed for {doc_id}: {e}")
    # Delete from DB
    await db.meeting_documents.delete_one({"doc_id": doc_id, "meeting_id": meeting_id})
    await db.document_audit_logs.delete_many({"doc_id": doc_id, "meeting_id": meeting_id})
    # Broadcast to participants
    await ws_manager.broadcast(meeting_id, {
        "type": "document-deleted", "doc_id": doc_id, "by": user.get("name", ""),
    })
    return {"message": "Document deleted"}

@router.put("/meetings/{meeting_id}/documents/reorder")
async def reorder_meeting_documents(meeting_id: str, request: Request):
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting or meeting.get("host_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only host can reorder documents")
    body = await request.json()
    doc_ids = body.get("doc_ids", [])
    for i, did in enumerate(doc_ids):
        await db.meeting_documents.update_one(
            {"doc_id": did, "meeting_id": meeting_id},
            {"$set": {"sort_order": i}}
        )
    await ws_manager.broadcast(meeting_id, {
        "type": "documents-reordered", "doc_ids": doc_ids, "by": user.get("name", ""),
    })
    return {"message": "Documents reordered"}



@router.get("/meetings/{meeting_id}/documents/{doc_id}/view")
async def view_document(meeting_id: str, doc_id: str, request: Request):
    doc = await db.meeting_documents.find_one({"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        data, ct = await asyncio.to_thread(get_object, doc["storage_path"])
        ip = request.client.host if request.client else ""
        await _log_doc_audit(doc_id, meeting_id, "viewed", ip=ip, details=doc.get("filename", ""))
        return Response(content=data, media_type=ct)
    except Exception:
        raise HTTPException(status_code=500, detail="Document not available")

@router.post("/meetings/{meeting_id}/documents/{doc_id}/present")
async def toggle_document_presentation(meeting_id: str, doc_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    presenting = body.get("presenting", True)
    page = body.get("page", 1)
    await db.meeting_documents.update_many({"meeting_id": meeting_id}, {"$set": {"presenting": False}})
    doc = await db.meeting_documents.find_one({"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0, "storage_path": 0})
    if presenting:
        await db.meeting_documents.update_one({"doc_id": doc_id}, {"$set": {"presenting": True, "current_page": page}})
    await ws_manager.broadcast(meeting_id, {
        "type": "document-present", "doc_id": doc_id if presenting else None,
        "page": page, "presenting": presenting, "by": user.get("name", ""), "by_id": user["user_id"],
        "filename": doc.get("filename", "") if doc else "",
        "file_ext": doc.get("file_ext", "") if doc else "",
        "uploader_name": doc.get("uploader_name", "") if doc else "",
    })
    action = "presented" if presenting else "presentation_stopped"
    await _log_doc_audit(doc_id, meeting_id, action, user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "", f"Seite {page}")
    return {"presenting": presenting, "doc_id": doc_id, "page": page}

@router.post("/meetings/{meeting_id}/documents/{doc_id}/request-signatures")
async def request_document_signatures(meeting_id: str, doc_id: str, request: Request):
    user = await get_current_user(request)
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting or meeting["host_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only host can request signatures")
    await db.meeting_documents.update_one({"doc_id": doc_id}, {"$set": {"requires_signature": True}})
    await ws_manager.broadcast(meeting_id, {
        "type": "signature-request", "doc_id": doc_id, "by": user.get("name", ""),
    })
    await _log_doc_audit(doc_id, meeting_id, "signature_requested", user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "")
    return {"message": "Signature request sent to all participants"}

@router.post("/meetings/{meeting_id}/documents/{doc_id}/sign")
async def sign_document_live(meeting_id: str, doc_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    sig_type = body.get("type", "drawn")  # "drawn" or "typed"
    sig_data = body.get("signature_data", "")  # base64 image for drawn, text for typed
    if not sig_data:
        raise HTTPException(status_code=400, detail="Signature data required")
    sig = {
        "sig_id": f"sig_{uuid.uuid4().hex[:8]}", "signer_id": user["user_id"],
        "signer_name": user.get("name", ""), "signer_email": user.get("email", ""),
        "type": sig_type, "signature_data": sig_data,
        "pos_x": body.get("pos_x", 0), "pos_y": body.get("pos_y", 0), "page": body.get("page", 1),
        "field_id": body.get("field_id", ""),
        "signed_at": datetime.now(timezone.utc).isoformat(), "ip": request.client.host if request.client else "",
    }
    await db.meeting_documents.update_one({"doc_id": doc_id}, {"$push": {"signatures": sig}})
    await ws_manager.broadcast(meeting_id, {
        "type": "document-signed", "doc_id": doc_id, "signer": user.get("name", ""),
    })
    await _log_doc_audit(doc_id, meeting_id, "signed", user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "", f"Typ: {sig_type}")
    return {"message": "Document signed", "sig_id": sig["sig_id"]}

@router.get("/meetings/{meeting_id}/documents/{doc_id}/download-signed")
async def download_signed_document(meeting_id: str, doc_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.meeting_documents.find_one({"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    sigs = doc.get("signatures", [])
    ext = doc.get("file_ext", "pdf")
    import base64

    # Load original file from storage
    try:
        original_data, content_type = await asyncio.to_thread(get_object, doc["storage_path"])
    except Exception:
        raise HTTPException(status_code=500, detail="Original document not available")

    is_image = ext in ["png", "jpg", "jpeg", "webp"]
    positioned_sigs = [s for s in sigs if s.get("pos_x") is not None or s.get("pos_y") is not None]

    if is_image:
        # Stamp signatures onto the image using Pillow
        from PIL import Image as PILImage, ImageDraw, ImageFont
        img = PILImage.open(io.BytesIO(original_data)).convert("RGBA")
        overlay = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", 24)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
        except Exception:
            font = ImageFont.load_default()
            font_small = font
        for s in positioned_sigs:
            px, py = int(s.get("pos_x", 0)), int(s.get("pos_y", 0))
            if s.get("type") == "drawn" and s.get("signature_data", "").startswith("data:image"):
                try:
                    b64 = s["signature_data"].split(",", 1)[1]
                    sig_img = PILImage.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
                    sig_img = sig_img.resize((200, 60), PILImage.LANCZOS)
                    overlay.paste(sig_img, (px, py), sig_img)
                except Exception:
                    draw.text((px, py), f"[{s.get('signer_name', '')}]", fill=(28, 31, 29, 200), font=font)
            elif s.get("type") == "typed":
                draw.text((px, py), s.get("signature_data", ""), fill=(28, 31, 29, 230), font=font)
            draw.text((px, py + 30 if s.get("type") == "typed" else py + 65), s.get("signer_name", ""), fill=(156, 163, 175, 180), font=font_small)
        result = PILImage.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        fmt = "PNG" if ext == "png" else "JPEG"
        result.save(buf, format=fmt, quality=95)
        ct = "image/png" if ext == "png" else "image/jpeg"
        fname = f"signed_{doc.get('filename', 'image')}"
        await _log_doc_audit(doc_id, meeting_id, "downloaded_signed", user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "")
        return Response(content=buf.getvalue(), media_type=ct, headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    elif ext == "pdf":
        # Stamp signatures onto the original PDF using PyPDF2 + ReportLab overlay
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.units import mm
        from reportlab.lib import colors as rl_colors

        reader = PdfReader(io.BytesIO(original_data))
        writer = PdfWriter()

        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            page_w = float(page.mediabox.width)
            page_h = float(page.mediabox.height)

            # Find signatures for this page
            page_sigs = [s for s in positioned_sigs if (s.get("page", 1) - 1) == page_num]

            if page_sigs:
                # Create overlay with signatures
                overlay_buf = io.BytesIO()
                c = pdf_canvas.Canvas(overlay_buf, pagesize=(page_w, page_h))
                # Scale: canvas renders at 800px width, proportional height
                scale_x = page_w / 800.0
                canvas_height = (page_h / page_w) * 800.0
                scale_y = page_h / canvas_height  # same as scale_x

                for s in page_sigs:
                    px = s.get("pos_x", 0)
                    py = s.get("pos_y", 0)
                    sig_x = px * scale_x
                    sig_y = page_h - (py * scale_y)

                    if s.get("type") == "drawn" and s.get("signature_data", "").startswith("data:image"):
                        try:
                            b64 = s["signature_data"].split(",", 1)[1]
                            img_data = base64.b64decode(b64)
                            from reportlab.lib.utils import ImageReader
                            img_reader = ImageReader(io.BytesIO(img_data))
                            c.drawImage(img_reader, sig_x, sig_y - 15*mm, width=50*mm, height=15*mm, preserveAspectRatio=True, mask='auto')
                        except Exception:
                            c.setFont("Helvetica-Oblique", 12)
                            c.setFillColor(rl_colors.HexColor("#1C1F1D"))
                            c.drawString(sig_x, sig_y - 5*mm, f"[{s.get('signer_name', '')}]")
                    elif s.get("type") == "typed":
                        c.setFont("Times-Italic", 16)
                        c.setFillColor(rl_colors.HexColor("#1C1F1D"))
                        c.drawString(sig_x, sig_y - 5*mm, s.get("signature_data", ""))

                    # Name label
                    c.setFont("Helvetica", 7)
                    c.setFillColor(rl_colors.HexColor("#9CA3AF"))
                    y_offset = sig_y - 10*mm if s.get("type") == "typed" else sig_y - 19*mm
                    c.drawString(sig_x, y_offset, s.get("signer_name", ""))

                c.save()
                overlay_buf.seek(0)
                overlay_reader = PdfReader(overlay_buf)
                page.merge_page(overlay_reader.pages[0])

            writer.add_page(page)

        out_buf = io.BytesIO()
        writer.write(out_buf)
        fname = f"signed_{doc.get('filename', 'document.pdf')}"
        await _log_doc_audit(doc_id, meeting_id, "downloaded_signed", user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "")
        return Response(content=out_buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    else:
        # Non-PDF/image: return original with signature info in filename
        fname = f"signed_{doc.get('filename', 'document')}"
        await _log_doc_audit(doc_id, meeting_id, "downloaded_signed", user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "")
        return Response(content=original_data, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{fname}"'})

# Public async signing (after meeting, via email link)
@router.get("/sign/{sign_token}")
async def get_document_for_signing(sign_token: str):
    doc = await db.meeting_documents.find_one({"sign_token": sign_token}, {"_id": 0, "storage_path": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    meeting = await db.meetings.find_one({"meeting_id": doc["meeting_id"]}, {"_id": 0})
    return {
        "doc_id": doc["doc_id"], "filename": doc["filename"], "meeting_id": doc["meeting_id"],
        "file_ext": doc.get("file_ext", ""), "meeting_title": meeting.get("title", "") if meeting else "",
        "uploader_name": doc.get("uploader_name", ""), "signatures": [{"signer_name": s["signer_name"], "signed_at": s["signed_at"]} for s in doc.get("signatures", [])],
        "view_url": f"/api/meetings/{doc['meeting_id']}/documents/{doc['doc_id']}/view",
    }

@router.post("/sign/{sign_token}")
async def sign_document_async(sign_token: str, request: Request):
    body = await request.json()
    doc = await db.meeting_documents.find_one({"sign_token": sign_token})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    signer_name = body.get("signer_name", "")
    signer_email = body.get("signer_email", "")
    sig_type = body.get("type", "typed")
    sig_data = body.get("signature_data", "")
    if not signer_name or not sig_data:
        raise HTTPException(status_code=400, detail="Name and signature required")
    for existing in doc.get("signatures", []):
        if existing.get("signer_email") == signer_email and signer_email:
            raise HTTPException(status_code=409, detail="Already signed")
    sig = {
        "sig_id": f"sig_{uuid.uuid4().hex[:8]}", "signer_name": signer_name,
        "signer_email": signer_email, "type": sig_type, "signature_data": sig_data,
        "pos_x": body.get("pos_x", 0), "pos_y": body.get("pos_y", 0), "page": body.get("page", 1),
        "signed_at": datetime.now(timezone.utc).isoformat(), "ip": request.client.host if request.client else "",
    }
    await db.meeting_documents.update_one({"sign_token": sign_token}, {"$push": {"signatures": sig}})
    await _log_doc_audit(doc["doc_id"], doc["meeting_id"], "signed_async", "", signer_name, signer_email, request.client.host if request.client else "", f"Typ: {sig_type}")
    return {"message": "Document signed", "sig_id": sig["sig_id"]}

@router.post("/meetings/{meeting_id}/documents/{doc_id}/send-for-signing")
async def send_document_for_signing(meeting_id: str, doc_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    emails = body.get("emails", [])
    doc = await db.meeting_documents.find_one({"doc_id": doc_id, "meeting_id": meeting_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    sign_url = f"{os.environ.get('FRONTEND_URL', 'http://localhost:3000')}/sign/{doc['sign_token']}"
    meeting = await db.meetings.find_one({"meeting_id": meeting_id}, {"_id": 0})
    meeting_title = meeting.get("title", "Meeting") if meeting else "Meeting"
    sent = 0
    for email in emails:
        html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#F9F9F8;">
        <h2 style="color:#4A5D4E;">Dokument zur Unterschrift</h2>
        <p>{user.get('name', '')} bittet dich, folgendes Dokument zu unterschreiben:</p>
        <div style="background:#fff;border:1px solid #E2E4E0;border-radius:12px;padding:16px;margin:16px 0;">
          <p style="font-weight:600;">{doc['filename']}</p>
          <p style="color:#6B7280;font-size:13px;">Meeting: {meeting_title}</p>
        </div>
        <a href="{sign_url}" style="display:inline-block;background:#4A5D4E;color:#fff;padding:12px 24px;border-radius:99px;text-decoration:none;font-weight:600;">Dokument unterschreiben</a>
        </div>"""
        result = await send_email_real(email, f"Unterschrift erforderlich: {doc['filename']}", html)
        if result.get("status") in ("sent", "logged"):
            sent += 1
    await db.meeting_documents.update_one({"doc_id": doc_id}, {"$set": {"requires_signature": True}})
    await _log_doc_audit(doc_id, meeting_id, "sent_for_signing", user["user_id"], user.get("name", ""), user.get("email", ""), request.client.host if request.client else "", f"Empfänger: {', '.join(emails)}")
    return {"message": f"Signing request sent to {sent} recipients", "sign_url": sign_url, "sent": sent}



