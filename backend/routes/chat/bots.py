from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user
from services.permissions import has_cap
import uuid

from ._shared import (
    BUILTIN_BOTS,
)

router = APIRouter()

@router.get("/chat/bots")
async def list_bots(request: Request):
    await get_current_user(request)
    custom_bots = await db.chat_bots.find({}, {"_id": 0}).to_list(50)
    return {"builtin": list(BUILTIN_BOTS.values()), "custom": custom_bots}

@router.post("/chat/bots")
async def create_bot(request: Request):
    user = await get_current_user(request)
    if not await has_cap(user, "admin.manage_integrations", db):
        raise HTTPException(status_code=403, detail="Admin erforderlich")
    body = await request.json()
    bot_id = f"bot_{uuid.uuid4().hex[:8]}"
    bot = {
        "bot_id": bot_id, "name": body.get("name", "Custom Bot"),
        "description": body.get("description", ""),
        "webhook_url": body.get("webhook_url", ""),
        "trigger_prefix": body.get("trigger_prefix", "/custom"),
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_bots.insert_one(bot)
    return {k: v for k, v in bot.items() if k != "_id"}

