"""Missed-call watcher for chat-initiated calls.

A chat call creates a meeting + a chat message of type "call" that contains
the join URL. We schedule a background task that checks 45 seconds later
whether any participant OTHER than the caller ever joined the meeting. If
not, the message is rewritten to "❌ Verpasster Anruf um HH:MM" and a push
+ WS event is fired so the callee sees it immediately when they open the
chat later.

Design decisions:
  - `asyncio.create_task` (fire-and-forget) is enough for 45 s sleeps; no
    need for celery/APS in this scope.
  - Task stays alive if the backend is restarted? No — meetings that were
    pending during the crash never get marked as missed. Acceptable trade-off
    for now; a follow-up could persist a "missed_check_due_at" field and a
    periodic scan job to catch stragglers.
  - We deliberately do NOT flag a call as missed if the backend happens to
    have no record of participants (e.g. race condition) — the whole check
    is best-effort.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from database import db, logger


MISSED_CALL_AFTER_SEC = 45


async def _check_and_mark(meeting_id: str, message_id: str, caller_id: str) -> None:
    try:
        # Has any non-caller actually joined?
        joined_non_caller = await db.meeting_participants.find_one({
            "meeting_id": meeting_id,
            "user_id": {"$ne": caller_id},
            "joined_at": {"$ne": None},
        }, {"_id": 0, "user_id": 1})

        msg = await db.messages.find_one({"message_id": message_id}, {"_id": 0})
        if not msg or msg.get("deleted"):
            return
        # Idempotency: only rewrite once
        if msg.get("missed"):
            return

        if joined_non_caller:
            # Call was answered — nothing to do
            return

        # Mark as missed
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            hhmm = datetime.fromisoformat(msg["created_at"].replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        except Exception:
            hhmm = datetime.now(timezone.utc).strftime("%H:%M")
        new_content = f"Verpasster Anruf um {hhmm}"
        await db.messages.update_one(
            {"message_id": message_id},
            {"$set": {
                "missed": True,
                "content": new_content,
                "missed_at": now_iso,
                "updated_at": now_iso,
            }}
        )
        updated = await db.messages.find_one({"message_id": message_id}, {"_id": 0})

        # Update the conversation's last-message preview if this was the last message
        try:
            conv_id = msg["conversation_id"]
            await db.conversations.update_one(
                {"conversation_id": conv_id, "last_message.message_id": message_id},
                {"$set": {"last_message.content": new_content, "updated_at": now_iso}}
            )
        except Exception:
            pass

        # Broadcast to chat WS so open UIs re-render
        try:
            from routes.chat import chat_ws  # local import to avoid circular at module load
            await chat_ws.send_to_conversation(
                msg["conversation_id"],
                {
                    "type": "message-edited",
                    "message": updated,
                    "conversation_id": msg["conversation_id"],
                },
            )
            # Stop any still-ringing IncomingCallModal on the callees' screens
            conv = await db.conversations.find_one({"conversation_id": msg["conversation_id"]}, {"_id": 0, "members": 1})
            for m in (conv or {}).get("members", []):
                uid = m.get("user_id") if isinstance(m, dict) else m
                if uid and uid != caller_id:
                    await chat_ws.send_to_user(uid, {
                        "type": "call-ended",
                        "reason": "missed",
                        "meeting_id": meeting_id,
                        "message_id": message_id,
                    })
        except Exception as e:
            logger.warning(f"[missed-call] WS broadcast failed: {e}")

        # Also send a second push so an offline callee sees "Verpasster Anruf"
        # as the latest notification next time they wake the phone.
        try:
            from services.chat_push import push_new_chat_message
            caller = await db.users.find_one({"user_id": caller_id}, {"_id": 0, "name": 1}) or {}
            await push_new_chat_message(
                msg["conversation_id"], caller_id, caller.get("name", "") or "Jemand",
                "text", new_content,
                target_url=f"/chat?c={msg['conversation_id']}",
            )
        except Exception as e:
            logger.warning(f"[missed-call] follow-up push failed: {e}")

        logger.info(f"[missed-call] marked msg={message_id} meeting={meeting_id} caller={caller_id}")
    except Exception as e:
        logger.warning(f"[missed-call] watcher crashed for meeting={meeting_id}: {e}")


async def _wait_and_check(meeting_id: str, message_id: str, caller_id: str) -> None:
    await asyncio.sleep(MISSED_CALL_AFTER_SEC)
    await _check_and_mark(meeting_id, message_id, caller_id)


def schedule_missed_call_check(*, meeting_id: str, message_id: str, caller_id: str) -> Optional[asyncio.Task]:
    """Fire-and-forget scheduling. Safe to call during a request handler —
    `asyncio.create_task` returns immediately."""
    try:
        return asyncio.create_task(_wait_and_check(meeting_id, message_id, caller_id))
    except Exception as e:
        logger.warning(f"[missed-call] scheduling failed: {e}")
        return None
