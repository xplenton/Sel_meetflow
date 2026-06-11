from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import db, logger
from dependencies import get_current_user
import uuid
import httpx

from ._shared import (
    chat_ws,
)

router = APIRouter()

@router.get("/chat/gifs")
async def search_gifs(request: Request, q: str = ""):
    if not q or len(q) < 2:
        return {"results": []}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://tenor.googleapis.com/v2/search", params={
                "q": q, "key": "AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ",  # Tenor public key
                "limit": 20, "media_filter": "tinygif,gif"
            })
            data = resp.json()
            gifs = []
            for r in data.get("results", []):
                media = r.get("media_formats", {})
                tiny = media.get("tinygif", {})
                full = media.get("gif", {})
                if tiny.get("url") or full.get("url"):
                    gifs.append({"id": r.get("id"), "preview": tiny.get("url", ""), "url": full.get("url", tiny.get("url", "")), "title": r.get("content_description", "")})
            return {"results": gifs}
    except Exception as e:
        logger.error(f"GIF search error: {e}")
        return {"results": []}

@router.post("/chat/conversations/{conv_id}/gif")
async def send_gif(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    body = await request.json()
    gif_url = body.get("url", "")
    if not gif_url:
        raise HTTPException(status_code=400, detail="GIF URL erforderlich")
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    message = {
        "message_id": msg_id, "conversation_id": conv_id,
        "sender_id": user["user_id"], "sender_name": user.get("name", ""),
        "sender_avatar": user.get("avatar", ""),
        "content": "GIF", "type": "gif",
        "gif_url": gif_url,
        "file_url": None, "file_name": None, "file_type": None,
        "mentions": [], "priority": "normal", "reply_to": None, "reply_preview": None,
        "reactions": [], "edited": False, "deleted": False, "thread_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(message)
    msg_clean = {k: v for k, v in message.items() if k != "_id"}
    last_msg = {"message_id": msg_id, "content": "GIF", "sender_name": user.get("name", ""), "created_at": message["created_at"]}
    await db.conversations.update_one({"conversation_id": conv_id}, {"$set": {"last_message": last_msg, "updated_at": message["created_at"]}})
    await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": msg_clean, "conversation_id": conv_id})
    return msg_clean

