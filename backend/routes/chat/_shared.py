from fastapi import APIRouter, HTTPException, WebSocket
from datetime import datetime, timezone
from database import db
from services.ws_broker import ws_broker
import uuid
import os
import asyncio

router = APIRouter()  # noqa: F401 - kept for legacy imports; sub-modules use their own

# ============ CHAT WEBSOCKET MANAGER ============

class ChatWSManager:
    def __init__(self):
        self.connections: dict = {}  # user_id -> [websocket, ...]

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.connections:
            self.connections[user_id] = [w for w in self.connections[user_id] if w != ws]
            if not self.connections[user_id]:
                del self.connections[user_id]

    async def _local_send_to_user(self, user_id: str, msg: dict):
        """Deliver to LOCAL connections only. Does NOT hit Redis."""
        if user_id not in self.connections:
            return
        sockets = list(self.connections[user_id])
        if not sockets:
            return
        results = await asyncio.gather(
            *(ws.send_json(msg) for ws in sockets),
            return_exceptions=True,
        )
        dead = [ws for ws, res in zip(sockets, results) if isinstance(res, Exception)]
        for ws in dead:
            try:
                self.connections[user_id].remove(ws)
            except ValueError:
                pass

    async def send_to_user(self, user_id: str, msg: dict):
        """Send to all of a user's live WS connections.

        iter 157 — previously this ran sequentially, so one slow/dying
        socket could delay delivery to the user's other devices (they may
        have 2-3 tabs + a phone PWA + a laptop open). For incoming-calls
        that 1-2 s delay is the difference between ringing and silent.

        iter 176 — also publishes via Redis pub/sub so the user's
        connections on OTHER pods get the message too (horizontal scaling).
        """
        await self._local_send_to_user(user_id, msg)
        await ws_broker.publish("user", msg, target=user_id)

    async def _local_send_to_conversation(self, conversation_id: str, msg: dict, exclude_user: str = None):
        conv = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0, "members": 1})
        if not conv:
            return
        targets = []
        for member in conv.get("members", []):
            uid = member.get("user_id") if isinstance(member, dict) else member
            if uid and uid != exclude_user:
                targets.append(uid)
        if targets:
            await asyncio.gather(*(self._local_send_to_user(uid, msg) for uid in targets), return_exceptions=True)

    async def send_to_conversation(self, conversation_id: str, msg: dict, exclude_user: str = None):
        """Fan-out to every member of a conversation. Local first, then Redis."""
        await self._local_send_to_conversation(conversation_id, msg, exclude_user)
        await ws_broker.publish(
            "conversation", msg,
            target=f"{conversation_id}|{exclude_user or ''}",
        )

    def is_online(self, user_id: str) -> bool:
        """Local-only online check — used when Redis is unavailable.
        For cross-pod presence use `ws_broker.is_online(user_id)` instead."""
        return user_id in self.connections and len(self.connections[user_id]) > 0

    def is_online_locally(self, user_id: str) -> bool:
        """Alias preserved for clarity at call-sites."""
        return self.is_online(user_id)

    async def _local_broadcast_status(self, user_id: str, status_mode: str, user_name: str = ""):
        msg = {"type": "status-change", "user_id": user_id, "status_mode": status_mode, "user_name": user_name}
        for uid in list(self.connections.keys()):
            await self._local_send_to_user(uid, msg)

    async def broadcast_status(self, user_id: str, status_mode: str, user_name: str = ""):
        """Broadcast status change to all currently connected users (local + cross-pod)."""
        await self._local_broadcast_status(user_id, status_mode, user_name)
        await ws_broker.publish(
            "status",
            {"type": "status-change", "user_id": user_id, "status_mode": status_mode, "user_name": user_name},
            target="",
        )

    # ---- Redis subscriber dispatch ---------------------------------------
    async def dispatch_from_broker(self, envelope: dict):
        """Called by the Redis subscriber for envelopes originating on OTHER
        pods. We only perform LOCAL fan-out here (the originating pod already
        did its own local fan-out before publishing)."""
        kind = envelope.get("kind")
        data = envelope.get("data") or {}
        target = envelope.get("target", "")
        if kind == "user":
            await self._local_send_to_user(target, data)
        elif kind == "conversation":
            conv_id, _, exclude = target.partition("|")
            await self._local_send_to_conversation(conv_id, data, exclude_user=exclude or None)
        elif kind == "status":
            # Re-broadcast to this pod's local connections
            await asyncio.gather(
                *(self._local_send_to_user(uid, data) for uid in list(self.connections.keys())),
                return_exceptions=True,
            )

chat_ws = ChatWSManager()
# Hook up the Redis subscriber → local fan-out once the broker starts.
ws_broker.set_dispatcher(chat_ws.dispatch_from_broker)

# ============ MEMBERSHIP HELPERS (iter 185 — privacy hardening) ============

async def _require_member(conv_id: str, user_id: str) -> dict:
    """Return the conversation IF the user is a member, else 404.

    Security: every route that operates on a single conversation MUST go
    through this helper. Returning 404 (not 403) prevents leaking the
    existence of conversations the user can't see — they're indistinguishable
    from "doesn't exist".
    """
    conv = await db.conversations.find_one(
        {"conversation_id": conv_id, "members.user_id": user_id},
        {"_id": 0},
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden")
    return conv


async def _require_admin_or_member(conv_id: str, user: dict) -> dict:
    """Like `_require_member` but also lets platform-admins through.

    Used by destructive ops (delete conversation, remove other members)
    where a global admin should be able to step in.
    """
    is_admin = user.get("role") == "admin"
    query = {"conversation_id": conv_id}
    if not is_admin:
        query["members.user_id"] = user["user_id"]
    conv = await db.conversations.find_one(query, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Unterhaltung nicht gefunden")
    return conv

# ============ BOT FRAMEWORK ============

BUILTIN_BOTS = {
    "meetflow-bot": {
        "bot_id": "meetflow-bot", "name": "MeetFlow Bot", "description": "Integrierter Assistent",
        "commands": {
            "/hilfe": "Zeigt alle verfügbaren Befehle",
            "/umfrage": "Erstellt eine Schnellumfrage: /umfrage Frage? Option1, Option2, Option3",
            "/aufgabe": "Erstellt eine Aufgabe: /aufgabe Beschreibung @Verantwortlicher",
            "/meeting": "Plant ein Meeting: /meeting Titel in 30min",
            "/status": "Zeigt Chat-Statistiken",
        }
    }
}

async def _handle_bot_command(conv_id: str, user: dict, content: str):
    parts = content.strip().split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "/hilfe":
        help_text = "**Verfügbare Befehle:**\n"
        for c, d in BUILTIN_BOTS["meetflow-bot"]["commands"].items():
            help_text += f"- `{c}` - {d}\n"
        return help_text

    elif cmd == "/umfrage":
        if "?" not in args:
            return "Bitte Format beachten: `/umfrage Frage? Option1, Option2, Option3`"
        question, options_str = args.split("?", 1)
        options = [o.strip() for o in options_str.split(",") if o.strip()]
        if len(options) < 2:
            return "Mindestens 2 Optionen noetig"
        poll_text = f"**Umfrage:** {question.strip()}?\n"
        for i, o in enumerate(options):
            poll_text += f"\n{['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣'][min(i,5)]} {o}"
        poll_text += "\n\n*Reagiere mit dem entsprechenden Emoji!*"
        return poll_text

    elif cmd == "/aufgabe":
        if not args:
            return "Bitte Beschreibung angeben: `/aufgabe Beschreibung @Verantwortlicher`"
        return f"**Neue Aufgabe erstellt:**\n- {args}\n- Erstellt von: {user.get('name', '')}\n- Status: Offen"

    elif cmd == "/meeting":
        if not args:
            return "Bitte Titel angeben: `/meeting Titel`"
        meeting_id = f"meet_{uuid.uuid4().hex[:10]}"
        meeting_code = f"{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:3]}"
        await db.meetings.insert_one({
            "meeting_id": meeting_id, "meeting_code": meeting_code,
            "title": args, "description": f"Erstellt via Bot von {user.get('name', '')}",
            "meeting_type": "instant", "scheduled_at": None,
            "duration": 60, "timezone": "Europe/Berlin",
            "recurring": False, "lobby_enabled": False, "guest_access": True,
            "meeting_mode": "standard", "chat_enabled": True,
            "reactions_enabled": True, "recording_enabled": False,
            "transcript_enabled": False, "reminder_minutes": 0, "reminder_sent": False,
            "host_id": user["user_id"], "host_name": user.get("name", ""),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(), "ended_at": None,
            "participant_count": 0,
        })
        frontend_url = os.environ.get("FRONTEND_URL", "")
        return f"**Meeting erstellt:** {args}\n[Jetzt beitreten]({frontend_url}/meetings/{meeting_id}/join)"

    elif cmd == "/status":
        msg_count = await db.messages.count_documents({"conversation_id": conv_id})
        conv = await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0})
        members = len(conv.get("members", [])) if conv else 0
        return f"**Chat-Statistiken:**\n- Nachrichten: {msg_count}\n- Teilnehmer: {members}\n- Erstellt: {conv.get('created_at', '')[:10] if conv else '?'}"

    return None

# ============ SYSTEM-MESSAGE HELPER ============

async def _send_system_message(conv_id: str, content: str):
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    message = {
        "message_id": msg_id, "conversation_id": conv_id,
        "sender_id": "system", "sender_name": "System",
        "sender_avatar": "", "content": content, "type": "system",
        "mentions": [], "priority": "normal",
        "reactions": [], "edited": False, "deleted": False,
        "file_url": None, "file_name": None, "file_type": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(message)
    msg_clean = {k: v for k, v in message.items() if k != "_id"}
    await chat_ws.send_to_conversation(conv_id, {"type": "new-message", "message": msg_clean, "conversation_id": conv_id})
    return msg_clean
