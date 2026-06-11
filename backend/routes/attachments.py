"""
Generic attachment storage using MongoDB GridFS.
Used by News comments and Survey free-text answers (and anywhere else
an uploaded file should persist across container restarts).
"""
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
import uuid
import mimetypes
from datetime import datetime, timezone
from typing import List

from dependencies import get_current_user
from database import db

router = APIRouter()

# Single shared GridFS bucket for all generic attachments
bucket = AsyncIOMotorGridFSBucket(db, bucket_name="attachments")

MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB per file

# MIME whitelist — documents, images, audio. No executables.
ALLOWED_MIMES = {
    # Images
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/csv", "text/markdown",
    # Audio
    "audio/mpeg", "audio/wav", "audio/webm", "audio/ogg",
    # Video (short clips)
    "video/mp4", "video/webm",
}


@router.post("/attachments/upload")
async def upload_attachment(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=400, detail="Leere Datei")
    if size > MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"Datei ist zu gross (max {MAX_SIZE_BYTES // (1024*1024)} MB)")

    mime = (file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream").lower()
    if mime not in ALLOWED_MIMES:
        raise HTTPException(status_code=415, detail=f"Dateityp nicht erlaubt: {mime}")

    attachment_id = f"att_{uuid.uuid4().hex[:12]}"
    safe_filename = (file.filename or "file")[:200]

    # Store in GridFS with metadata
    await bucket.upload_from_stream_with_id(
        attachment_id,
        safe_filename,
        content,
        metadata={
            "mime": mime,
            "size": size,
            "owner_id": user["user_id"],
            "owner_name": user.get("name", ""),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "attachment_id": attachment_id,
        "filename": safe_filename,
        "mime": mime,
        "size": size,
        "url": f"/api/attachments/{attachment_id}",
    }


@router.get("/attachments/{attachment_id}")
async def get_attachment(attachment_id: str, download: str = ""):
    """Stream a stored attachment. Returns inline by default."""
    try:
        gridout = await bucket.open_download_stream(attachment_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Anhang nicht gefunden")

    meta = gridout.metadata or {}
    mime = meta.get("mime") or "application/octet-stream"
    filename = gridout.filename or attachment_id
    disposition = "attachment" if download == "1" else "inline"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        "Cache-Control": "private, max-age=3600",
    }

    async def stream():
        while True:
            chunk = await gridout.readchunk()
            if not chunk:
                break
            yield chunk

    return StreamingResponse(stream(), media_type=mime, headers=headers)


@router.get("/attachments/{attachment_id}/meta")
async def get_attachment_meta(attachment_id: str, request: Request):
    await get_current_user(request)
    doc = await db["attachments.files"].find_one({"_id": attachment_id}, {"filename": 1, "length": 1, "metadata": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Anhang nicht gefunden")
    meta = doc.get("metadata", {}) or {}
    return {
        "attachment_id": attachment_id,
        "filename": doc.get("filename"),
        "mime": meta.get("mime", "application/octet-stream"),
        "size": doc.get("length", meta.get("size", 0)),
        "owner_id": meta.get("owner_id"),
        "owner_name": meta.get("owner_name"),
        "uploaded_at": meta.get("uploaded_at"),
        "url": f"/api/attachments/{attachment_id}",
    }


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(attachment_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db["attachments.files"].find_one({"_id": attachment_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Anhang nicht gefunden")
    meta = doc.get("metadata", {}) or {}
    if meta.get("owner_id") != user["user_id"] and user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    try:
        await bucket.delete(attachment_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Anhang nicht gefunden")
    return {"ok": True}


async def fetch_attachments_meta(ids: List[str]) -> List[dict]:
    """Helper used by other routes to enrich responses with attachment details."""
    if not ids:
        return []
    docs = await db["attachments.files"].find(
        {"_id": {"$in": ids}}, {"_id": 1, "filename": 1, "length": 1, "metadata": 1}
    ).to_list(50)
    out = []
    for d in docs:
        meta = d.get("metadata", {}) or {}
        out.append({
            "attachment_id": d["_id"],
            "filename": d.get("filename"),
            "mime": meta.get("mime", "application/octet-stream"),
            "size": d.get("length", meta.get("size", 0)),
            "url": f"/api/attachments/{d['_id']}",
        })
    return out
