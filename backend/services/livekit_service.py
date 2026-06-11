"""LiveKit SFU integration (iter 136).

Hybrid strategy: mesh WebRTC for ≤ 3 participants, LiveKit SFU for ≥
LIVEKIT_UPGRADE_THRESHOLD. Credentials may either live in `.env` for
bootstrap OR be overridden at runtime via the admin UI (stored in
`system_config` MongoDB collection). Runtime config wins.
"""
from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional

from livekit import api
from motor.motor_asyncio import AsyncIOMotorClient

_MONGO_URL = os.environ.get("MONGO_URL")
_DB_NAME = os.environ.get("DB_NAME")
_client = AsyncIOMotorClient(_MONGO_URL)
_db = _client[_DB_NAME]

_CONFIG_KEY = "livekit"


async def get_config() -> dict:
    """Return effective LiveKit config: DB override takes precedence over .env."""
    doc = await _db.system_config.find_one({"key": _CONFIG_KEY}, {"_id": 0})
    doc = doc or {}
    value = doc.get("value", {}) if isinstance(doc, dict) else {}
    threshold_raw = value.get("upgrade_threshold") or os.environ.get("LIVEKIT_UPGRADE_THRESHOLD", "4")
    try:
        threshold = int(threshold_raw)
    except (ValueError, TypeError):
        threshold = 4
    return {
        "url": (value.get("url") or os.environ.get("LIVEKIT_URL") or "").strip(),
        "api_key": (value.get("api_key") or os.environ.get("LIVEKIT_API_KEY") or "").strip(),
        "api_secret": (value.get("api_secret") or os.environ.get("LIVEKIT_API_SECRET") or "").strip(),
        "upgrade_threshold": threshold,
    }


async def save_config(url: str, api_key: str, api_secret: str, upgrade_threshold: int = 4) -> dict:
    """Persist LiveKit config to the admin-editable store."""
    value = {
        "url": (url or "").strip(),
        "api_key": (api_key or "").strip(),
        "api_secret": (api_secret or "").strip(),
        "upgrade_threshold": max(2, min(20, int(upgrade_threshold or 4))),
    }
    await _db.system_config.update_one(
        {"key": _CONFIG_KEY},
        {"$set": {"key": _CONFIG_KEY, "value": value}},
        upsert=True,
    )
    return value


async def is_configured() -> bool:
    cfg = await get_config()
    return bool(cfg["url"] and cfg["api_key"] and cfg["api_secret"])


async def generate_token(
    room_name: str,
    identity: str,
    display_name: str,
    can_publish: bool = True,
    can_subscribe: bool = True,
    metadata: Optional[str] = None,
    ttl_hours: int = 6,
) -> dict:
    """Mint a LiveKit JWT for `identity` to join `room_name`.

    Returns {url, token} — the client then connects directly to the SFU.
    Tokens are server-minted only; the api_secret NEVER leaves the backend.
    """
    cfg = await get_config()
    if not (cfg["url"] and cfg["api_key"] and cfg["api_secret"]):
        raise ValueError("LiveKit not configured — admin must set URL, API key and secret first.")

    grant = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=can_publish,
        can_subscribe=can_subscribe,
        can_publish_data=True,  # chat / reactions via data channel
    )
    token = (
        api.AccessToken(cfg["api_key"], cfg["api_secret"])
        .with_identity(identity)
        .with_name(display_name)
        .with_grants(grant)
        .with_ttl(timedelta(hours=max(1, min(24, int(ttl_hours or 6)))))
    )
    if metadata:
        token = token.with_metadata(metadata)
    return {"url": cfg["url"], "token": token.to_jwt(), "identity": identity, "room": room_name}
