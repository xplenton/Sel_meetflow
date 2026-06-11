"""Chat package — split from former chat.py monolith (iter 187).

Re-exports `router` (aggregated) and `chat_ws` for backward compatibility
with `from routes.chat import router as chat_router` and
`from routes.chat import chat_ws` used widely across the codebase.
"""
from fastapi import APIRouter

from ._shared import (
    chat_ws,
    _require_member,
    _require_admin_or_member,
    _send_system_message,
    _handle_bot_command,
    BUILTIN_BOTS,
    ChatWSManager,
)
from . import _websocket, conversations, messages, files, calls
from . import search, presence, gifs, bots, crypto, push

router = APIRouter()
for mod in (
    _websocket, conversations, messages, files, calls,
    search, presence, gifs, bots, crypto, push,
):
    router.include_router(mod.router)

__all__ = [
    "router", "chat_ws", "ChatWSManager",
    "_require_member", "_require_admin_or_member",
    "_send_system_message", "_handle_bot_command", "BUILTIN_BOTS",
]
