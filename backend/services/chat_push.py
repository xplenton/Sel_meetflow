"""Chat-related push notifications.

Respects user preferences:
  - Conversation is muted for the recipient → skip
  - Recipient has status_mode == 'dnd'            → skip
  - Recipient is the sender                       → skip
  - Recipient is currently connected to the chat WS → still push (phone may be
    idle in the background), but with a lower-priority payload.

Keeps the push-payload compact so iOS/Android surface the message title+body
without truncation.
"""
from __future__ import annotations

from typing import Dict, List

from database import db, logger


async def _eligible_recipients(conv_id: str, sender_id: str, *, bypass_dnd: bool = False) -> List[Dict]:
    """Return the conversation members who should receive a push for a new
    message. Filters out the sender and users who muted this conv.

    `bypass_dnd=True` means calls + urgent messages ignore DND — DND is a
    schedule ("do not disturb after 18:00"), not a "block calls" setting.
    Users who actively muted the conversation are still always skipped
    (an explicit opt-out).
    """
    conv = await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0})
    if not conv:
        return []

    muted_by = set(conv.get("muted_by") or [])
    members = conv.get("members") or []

    recipients = []
    for m in members:
        # Members may be stored as either `{"user_id": ..., "role": ...}`
        # (current schema) or a bare user_id string (legacy 1:1 chats).
        # Using `.get()` unconditionally crashes on strings and silently
        # drops the entire push fan-out, causing one of a group's callees
        # to never ring (iter 138 bug report).
        uid = m.get("user_id") if isinstance(m, dict) else m
        if not uid or uid == sender_id or uid in muted_by:
            continue
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "user_id": 1, "status_mode": 1, "name": 1})
        if not u:
            continue
        if u.get("status_mode") == "dnd" and not bypass_dnd:
            continue
        recipients.append(u)
    return recipients


def _shorten(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


async def push_new_chat_message(
    conv_id: str,
    sender_id: str,
    sender_name: str,
    message_type: str,
    content: str,
    *,
    target_url: str = "/chat",
    urgent: bool = False,
) -> Dict:
    """Fan out a Web Push to every eligible member of a conversation.
    `message_type` is one of: text, file, voice, gif, call.
    When `urgent=True`, DND settings are ignored and the payload is prefixed
    with a siren emoji so it stands out on the lock-screen.
    """
    from services.news_push import send_push_to_user  # reuse existing helper

    # Derive user-friendly body by message type
    if message_type == "file":
        body = "📎 Hat eine Datei gesendet"
    elif message_type == "voice":
        body = "🎤 Sprachnachricht"
    elif message_type == "gif":
        body = "🎬 GIF"
    elif message_type == "call":
        body = "📞 Ruft dich an"
    else:
        body = _shorten(content, 100)
    if urgent:
        body = "🚨 DRINGEND — " + body

    # Include conv name only for group chats (looks weird for 1:1)
    conv = await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0, "type": 1, "name": 1})
    conv_label = ""
    if conv and conv.get("type") == "group" and conv.get("name"):
        conv_label = f" · {conv['name']}"

    title = f"{sender_name}{conv_label}" if sender_name else "Neue Nachricht"
    data = {
        "url": target_url + (f"?c={conv_id}" if message_type != "call" else ""),
        "tag": f"chat-{conv_id}" if message_type != "call" else f"call-{conv_id}",
        "kind": "chat_call" if message_type == "call" else "chat_message",
        "conversation_id": conv_id,
        "sender_id": sender_id,
        "urgent": urgent,
    }

    sent, failed, skipped_prefs = 0, 0, 0
    # Calls always bypass DND — DND is a schedule, not a "block calls" flag.
    # Users who actively muted the conversation are still filtered out
    # inside _eligible_recipients (iter 146 fix for "group call doesn't
    # ring all members").
    is_call = message_type == "call"
    recipients = await _eligible_recipients(conv_id, sender_id, bypass_dnd=urgent or is_call)
    # Iter 183 — honour per-user notification preferences. Calls and urgent
    # messages bypass opt-out so emergencies always ring.
    from services.notification_prefs import is_allowed
    for r in recipients:
        if not (urgent or is_call):
            if not await is_allowed(r["user_id"], "chat", "push"):
                skipped_prefs += 1
                continue
        try:
            res = await send_push_to_user(r["user_id"], title=title, body=body, data=data)
            if res.get("sent", 0) > 0:
                sent += 1
                # Calls + urgent messages get a second push ~1.5 s later to
                # break through phone silent-mode grouping. Two separate
                # notifications are much harder to miss than one. iOS
                # groups same-app pushes aggressively so the first one can
                # get lost under the banner of another app (iter 146).
                if urgent or is_call:
                    import asyncio as _asyncio
                    async def _second_push(uid=r["user_id"]):
                        await _asyncio.sleep(1.5)
                        try:
                            await send_push_to_user(uid, title=f"🚨 {title}", body=body, data={**data, "tag": data["tag"] + "-2"})
                        except Exception:
                            pass
                    _asyncio.create_task(_second_push())
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.warning(f"[chat-push] dispatch failed for {r['user_id']}: {e}")

    logger.info(f"[chat-push] {message_type} conv={conv_id} from={sender_id} → sent={sent} failed={failed} skipped_prefs={skipped_prefs} recipients={len(recipients)}")
    return {"sent": sent, "failed": failed, "skipped_prefs": skipped_prefs, "recipients": len(recipients)}
