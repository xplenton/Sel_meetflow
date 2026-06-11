from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from typing import Optional
from datetime import datetime, timezone
from database import db, logger
from dependencies import get_current_user
import uuid
import os

from ._shared import (
    chat_ws,
)

router = APIRouter()

@router.post("/chat/conversations/{conv_id}/upload")
async def upload_file(conv_id: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden")
    upload_dir = "/app/backend/uploads/chat"
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    file_id = f"chatfile_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(upload_dir, file_id)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    file_url = f"/api/chat/files/{file_id}"
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    message = {
        "message_id": msg_id, "conversation_id": conv_id,
        "sender_id": user["user_id"], "sender_name": user.get("name", ""),
        "sender_avatar": user.get("avatar", ""),
        "content": f"Datei: {file.filename}", "type": "file",
        "file_url": file_url, "file_name": file.filename,
        "file_type": file.content_type or "", "file_size": len(content),
        "mentions": [], "priority": "normal",
        "reactions": [], "edited": False, "deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(message)
    msg_clean = {k: v for k, v in message.items() if k != "_id"}
    last_msg = {"message_id": msg_id, "content": f"Datei: {file.filename}", "sender_name": user.get("name", ""), "created_at": message["created_at"]}
    await db.conversations.update_one({"conversation_id": conv_id}, {"$set": {"last_message": last_msg, "updated_at": message["created_at"]}})
    await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": msg_clean, "conversation_id": conv_id})
    try:
        from services.chat_push import push_new_chat_message
        await push_new_chat_message(conv_id, user["user_id"], user.get("name", ""), "file", file.filename or "Datei")
    except Exception as e:
        logger.warning(f"[chat] file push dispatch failed: {e}")
    return msg_clean
from fastapi.responses import FileResponse

import mimetypes

@router.get("/chat/files/{file_id}")
async def serve_chat_file(file_id: str, download: Optional[str] = None):
    path = f"/app/backend/uploads/chat/{file_id}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if download == "1":
        return FileResponse(path, media_type=media_type, headers={"Content-Disposition": f"attachment; filename=\"{file_id}\""})
    return FileResponse(path, media_type=media_type)

# ============ THREAD REPLIES ============

@router.get("/chat/messages/{msg_id}/replies")
async def get_thread_replies(msg_id: str, request: Request):
    await get_current_user(request)
    replies = await db.messages.find(
        {"reply_to": msg_id, "deleted": {"$ne": True}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    parent = await db.messages.find_one({"message_id": msg_id}, {"_id": 0})
    return {"parent": parent, "replies": replies}

# ============ VOICE MESSAGES ============

@router.post("/chat/conversations/{conv_id}/voice")
async def upload_voice(conv_id: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden")
    upload_dir = "/app/backend/uploads/chat"
    os.makedirs(upload_dir, exist_ok=True)
    file_id = f"voice_{uuid.uuid4().hex[:8]}.webm"
    path = os.path.join(upload_dir, file_id)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    duration = len(content) / 6000  # rough estimate
    file_url = f"/api/chat/files/{file_id}"
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    message = {
        "message_id": msg_id, "conversation_id": conv_id,
        "sender_id": user["user_id"], "sender_name": user.get("name", ""),
        "sender_avatar": user.get("avatar", ""),
        "content": "Sprachnachricht", "type": "voice",
        "file_url": file_url, "file_name": file_id,
        "file_type": "audio/webm", "file_size": len(content),
        "voice_duration": round(duration, 1),
        "mentions": [], "priority": "normal", "reply_to": None, "reply_preview": None,
        "reactions": [], "edited": False, "deleted": False, "thread_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(message)
    msg_clean = {k: v for k, v in message.items() if k != "_id"}
    last_msg = {"message_id": msg_id, "content": "Sprachnachricht", "sender_name": user.get("name", ""), "created_at": message["created_at"]}
    await db.conversations.update_one({"conversation_id": conv_id}, {"$set": {"last_message": last_msg, "updated_at": message["created_at"]}})
    await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": msg_clean, "conversation_id": conv_id})
    try:
        from services.chat_push import push_new_chat_message
        await push_new_chat_message(conv_id, user["user_id"], user.get("name", ""), "voice", "Sprachnachricht")
    except Exception as e:
        logger.warning(f"[chat] voice push dispatch failed: {e}")
    return msg_clean

# ============ CALL FROM CHAT ============
