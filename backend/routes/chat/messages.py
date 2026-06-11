from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
from database import db, logger
from dependencies import get_current_user
from services.permissions import has_cap
import uuid
import asyncio

from ._shared import (
    chat_ws, _require_member, _handle_bot_command,
)

router = APIRouter()

# ============ MESSAGES ============

@router.get("/chat/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, request: Request, limit: int = 50, before: str = None):
    user = await get_current_user(request)
    # Iter 185 — privacy hardening. Previously this endpoint returned
    # every message of any conv_id regardless of membership, leaking
    # private chat history platform-wide. Now: 404 unless member.
    await _require_member(conv_id, user["user_id"])
    query = {"conversation_id": conv_id, "deleted": {"$ne": True}}
    if before:
        query["created_at"] = {"$lt": before}
    messages = await db.messages.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    messages.reverse()
    await db.conversations.update_one(
        {"conversation_id": conv_id, "members.user_id": user["user_id"]},
        {"$set": {"members.$.last_read": datetime.now(timezone.utc).isoformat()}}
    )
    return messages

@router.post("/chat/conversations/{conv_id}/messages")
async def send_message(conv_id: str, request: Request):
    user = await get_current_user(request)
    conv = await db.conversations.find_one({"conversation_id": conv_id, "members.user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden")
    body = await request.json()
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Nachricht darf nicht leer sein")
    mentions = body.get("mentions", [])
    priority = body.get("priority", "normal")
    e2e_encrypted = body.get("e2e_encrypted", False)
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    message = {
        "message_id": msg_id, "conversation_id": conv_id,
        "sender_id": user["user_id"], "sender_name": user.get("name", ""),
        "sender_avatar": user.get("avatar", ""),
        "content": content, "type": "text",
        "mentions": mentions, "priority": priority,
        "reply_to": body.get("reply_to"),
        "reply_preview": None,
        "reactions": [], "edited": False, "deleted": False,
        "file_url": None, "file_name": None, "file_type": None,
        "thread_count": 0,
        "e2e_encrypted": e2e_encrypted,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if message["reply_to"]:
        parent = await db.messages.find_one({"message_id": message["reply_to"]}, {"_id": 0, "content": 1, "sender_name": 1})
        if parent:
            message["reply_preview"] = {"content": parent["content"][:80], "sender_name": parent["sender_name"]}
        await db.messages.update_one({"message_id": message["reply_to"]}, {"$inc": {"thread_count": 1}})
    await db.messages.insert_one(message)
    msg_clean = {k: v for k, v in message.items() if k != "_id"}
    last_msg = {"message_id": msg_id, "content": content[:100], "sender_name": user.get("name", ""), "created_at": message["created_at"]}
    await db.conversations.update_one({"conversation_id": conv_id}, {"$set": {"last_message": last_msg, "updated_at": message["created_at"]}})
    await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": msg_clean, "conversation_id": conv_id})
    # Iter 172 (perf): fire-and-forget push dispatch — don't block the response
    # on web-push / sendgrid I/O. Errors are logged inside the coroutine.
    async def _async_push():
        try:
            from services.chat_push import push_new_chat_message
            await push_new_chat_message(conv_id, user["user_id"], user.get("name", ""), "text", content)
        except Exception as e:
            logger.warning(f"[chat] push dispatch failed: {e}")
    asyncio.create_task(_async_push())
    if mentions:
        for mention_id in mentions:
            if mention_id != user["user_id"]:
                await db.notifications.insert_one({
                    "notification_id": f"notif_{uuid.uuid4().hex[:8]}",
                    "user_id": mention_id, "type": "mention",
                    "title": f"{user.get('name', '')} hat Sie erwaehnt",
                    "message": content[:100], "read": False,
                    "link": f"/chat?conv={conv_id}",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
    # Bot command handling
    if content.startswith("/"):
        bot_response = await _handle_bot_command(conv_id, user, content)
        if bot_response:
            bot_msg_id = f"msg_{uuid.uuid4().hex[:12]}"
            bot_msg = {
                "message_id": bot_msg_id, "conversation_id": conv_id,
                "sender_id": "meetflow-bot", "sender_name": "MeetFlow Bot",
                "sender_avatar": "", "content": bot_response, "type": "bot",
                "mentions": [], "priority": "normal", "reply_to": msg_id, "reply_preview": {"content": content[:80], "sender_name": user.get("name", "")},
                "reactions": [], "edited": False, "deleted": False,
                "file_url": None, "file_name": None, "file_type": None, "thread_count": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.messages.insert_one(bot_msg)
            bot_clean = {k: v for k, v in bot_msg.items() if k != "_id"}
            await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": bot_clean, "conversation_id": conv_id})

    # Auto-reply for DND users (focus mode)
    if not content.startswith("/"):
        now_iso = datetime.now(timezone.utc).isoformat()
        for member in conv.get("members", []):
            mid = member.get("user_id") if isinstance(member, dict) else member
            if mid == user["user_id"]:
                continue
            # Check if member is in focus mode
            focus = await db.focus_times.find_one(
                {"user_id": mid, "start_time": {"$lte": now_iso}, "end_time": {"$gte": now_iso}},
                {"_id": 0}
            )
            if focus:
                member_user = await db.users.find_one({"user_id": mid}, {"_id": 0})
                if member_user and member_user.get("auto_reply_enabled", False):
                    reply_text = member_user.get("auto_reply_message") or "Ich bin gerade in einer Fokus-Session und antworte spaeter."
                    # Check if we already sent an auto-reply in this conv in the last 30 min
                    thirty_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
                    recent_auto = await db.messages.find_one({
                        "conversation_id": conv_id, "sender_id": mid, "type": "auto-reply",
                        "created_at": {"$gte": thirty_min_ago}
                    })
                    if not recent_auto:
                        ar_id = f"msg_{uuid.uuid4().hex[:12]}"
                        ar_msg = {
                            "message_id": ar_id, "conversation_id": conv_id,
                            "sender_id": mid, "sender_name": member_user.get("name", ""),
                            "sender_avatar": member_user.get("avatar", ""),
                            "content": reply_text, "type": "auto-reply",
                            "mentions": [], "priority": "normal", "reply_to": msg_id,
                            "reply_preview": {"content": content[:80], "sender_name": user.get("name", "")},
                            "reactions": [], "edited": False, "deleted": False,
                            "file_url": None, "file_name": None, "file_type": None, "thread_count": 0,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        await db.messages.insert_one(ar_msg)
                        ar_clean = {k: v for k, v in ar_msg.items() if k != "_id"}
                        await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": ar_clean, "conversation_id": conv_id})

    return msg_clean

@router.put("/chat/messages/{msg_id}")
async def edit_message(msg_id: str, request: Request):
    user = await get_current_user(request)
    msg = await db.messages.find_one({"message_id": msg_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
    if msg["sender_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Nur eigene Nachrichten bearbeiten")
    body = await request.json()
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Nachricht darf nicht leer sein")
    await db.messages.update_one({"message_id": msg_id}, {"$set": {"content": content, "edited": True, "updated_at": datetime.now(timezone.utc).isoformat()}})
    updated = await db.messages.find_one({"message_id": msg_id}, {"_id": 0})
    await chat_ws.send_to_conversation(msg["conversation_id"], {"type": "message-edited", "message": updated, "conversation_id": msg["conversation_id"]})
    return updated

@router.delete("/chat/messages/{msg_id}")
async def delete_message(msg_id: str, request: Request):
    user = await get_current_user(request)
    msg = await db.messages.find_one({"message_id": msg_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
    if msg["sender_id"] != user["user_id"] and not await has_cap(user, "chat.delete_messages", db):
        raise HTTPException(status_code=403, detail="Nur eigene Nachrichten löschen (oder Moderations-Recht)")
    await db.messages.update_one({"message_id": msg_id}, {"$set": {"deleted": True, "content": "", "updated_at": datetime.now(timezone.utc).isoformat()}})
    await chat_ws.send_to_conversation(msg["conversation_id"], {"type": "message-deleted", "message_id": msg_id, "conversation_id": msg["conversation_id"]})
    return {"message": "Gelöscht"}

# ============ REACTIONS ============

@router.post("/chat/messages/{msg_id}/reactions")
async def toggle_reaction(msg_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    emoji = body.get("emoji", "")
    if not emoji:
        raise HTTPException(status_code=400, detail="Emoji erforderlich")
    msg = await db.messages.find_one({"message_id": msg_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
    # Iter 185 — only members of the message's conversation may react.
    # Without this, anyone with the msg_id could spam reactions on private
    # conversations they have no business in.
    await _require_member(msg["conversation_id"], user["user_id"])
    # Iter 254 — race-safe toggle: instead of read-then-write, attempt an
    # atomic $pull first; if nothing was removed (i.e. the reaction wasn't
    # there) atomically $push with a conditional filter that prevents
    # duplicates under concurrent calls.
    pull_res = await db.messages.update_one(
        {"message_id": msg_id},
        {"$pull": {"reactions": {"emoji": emoji, "user_id": user["user_id"]}}}
    )
    if pull_res.modified_count == 0:
        # Push only if no peer call has just added the same (emoji, user)
        # combination. The $not + $elemMatch filter is evaluated atomically
        # together with the update.
        await db.messages.update_one(
            {
                "message_id": msg_id,
                "reactions": {"$not": {"$elemMatch": {
                    "emoji": emoji, "user_id": user["user_id"],
                }}},
            },
            {"$push": {"reactions": {
                "emoji": emoji,
                "user_id": user["user_id"],
                "user_name": user.get("name", ""),
            }}}
        )
    updated = await db.messages.find_one({"message_id": msg_id}, {"_id": 0})
    await chat_ws.send_to_conversation(msg["conversation_id"], {"type": "reaction-update", "message_id": msg_id, "reactions": updated.get("reactions", []), "conversation_id": msg["conversation_id"]})
    return updated

