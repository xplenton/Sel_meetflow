from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user

from ._shared import (
    _send_system_message,
)

router = APIRouter()

@router.post("/chat/keys")
async def store_public_key(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    public_key = body.get("public_key", "")
    if not public_key:
        raise HTTPException(status_code=400, detail="public_key erforderlich")
    await db.user_keys.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "public_key": public_key, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"message": "Key gespeichert"}

@router.get("/chat/keys/{target_user_id}")
async def get_public_key(target_user_id: str, request: Request):
    await get_current_user(request)
    key_doc = await db.user_keys.find_one({"user_id": target_user_id}, {"_id": 0})
    if not key_doc:
        raise HTTPException(status_code=404, detail="Kein Schlüssel gefunden")
    return key_doc

@router.put("/chat/conversations/{conv_id}/encryption")
async def toggle_encryption(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    encrypted = not conv.get("encrypted", False)
    await db.conversations.update_one({"conversation_id": conv_id}, {"$set": {"encrypted": encrypted}})
    await _send_system_message(conv_id, f"Ende-zu-Ende-Verschluesselung {'aktiviert' if encrypted else 'deaktiviert'}")
    return {"encrypted": encrypted}

@router.post("/chat/conversations/{conv_id}/group-key")
async def store_group_key(conv_id: str, request: Request):
    """Store encrypted group key for a conversation (shared by key creator)."""
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    body = await request.json()
    group_key = body.get("group_key", "")
    if not group_key:
        raise HTTPException(status_code=400, detail="group_key erforderlich")
    await db.group_keys.update_one(
        {"conversation_id": conv_id},
        {"$set": {"conversation_id": conv_id, "group_key": group_key, "set_by": user["user_id"], "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"message": "Gruppenschluessel gespeichert"}

@router.get("/chat/conversations/{conv_id}/group-key")
async def get_group_key(conv_id: str, request: Request):
    """Retrieve the group key for a conversation."""
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    key_doc = await db.group_keys.find_one({"conversation_id": conv_id}, {"_id": 0})
    if not key_doc:
        return {"group_key": None}
    return {"group_key": key_doc.get("group_key")}

