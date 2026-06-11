"""Iter 254 — Chat reaction race-condition regression test.

The endpoint /chat/messages/{id}/reactions previously used a read-then-write
pattern. Iter 254 makes it race-safe via:
  1. Atomic $pull (idempotent)
  2. If pull modified nothing, atomic $push with $not/$elemMatch filter

50 concurrent toggles by the SAME user → final reactions array contains AT
MOST 1 entry for that (emoji, user_id) pair.
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
import httpx
import pytest
import uuid

API = "http://localhost:8001/api"
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.mark.asyncio
async def test_chat_reaction_race_safe():
    async with httpx.AsyncClient(timeout=30.0) as c:
        # Login two users so we can create a direct conversation
        r = await c.post(f"{API}/auth/login", json=ADMIN)
        H_admin = {"Authorization": f"Bearer {r.json()['token']}"}
        admin_id = r.json()["user_id"]

        # Register + login a peer user
        email = f"test-chat-react-{uuid.uuid4().hex[:8]}@meetflow.com"
        r = await c.post(f"{API}/auth/register", json={
            "email": email, "password": "test123", "name": "Reactor",
        })
        assert r.status_code in (200, 201), r.text
        peer_id = r.json()["user_id"]
        r = await c.post(f"{API}/auth/login", json={"email": email, "password": "test123"})
        H_peer = {"Authorization": f"Bearer {r.json()['token']}"}

        # Create direct conversation between admin and peer
        r = await c.post(f"{API}/chat/conversations", headers=H_admin, json={
            "type": "direct", "member_ids": [peer_id],
        })
        assert r.status_code in (200, 201), r.text
        conv_id = r.json()["conversation_id"]

        try:
            # Admin sends a message
            r = await c.post(f"{API}/chat/conversations/{conv_id}/messages",
                              headers=H_admin, json={"content": "react to me"})
            assert r.status_code in (200, 201), r.text
            msg_id = r.json()["message_id"]

            limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
            async with httpx.AsyncClient(timeout=30.0, limits=limits) as c2:
                r = await c2.post(f"{API}/auth/login", json=ADMIN)
                H2 = {"Authorization": f"Bearer {r.json()['token']}"}

                async def react():
                    r = await c2.post(
                        f"{API}/chat/messages/{msg_id}/reactions",
                        headers=H2,
                        json={"emoji": "👍"},
                    )
                    return r.status_code

                results = await asyncio.gather(
                    *[react() for _ in range(50)], return_exceptions=True)
                ok = sum(1 for s in results if isinstance(s, int) and 200 <= s < 300)
                assert ok >= 40, f"most toggles should 2xx (got {ok}/50)"

                # Verify DB invariant: at most 1 reaction matching (emoji, user_id)
                cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
                db = cli[os.environ["DB_NAME"]]
                msg = await db.messages.find_one({"message_id": msg_id}, {"_id": 0})
                matching = [r for r in (msg.get("reactions") or [])
                            if r["emoji"] == "👍" and r["user_id"] == admin_id]
                assert len(matching) <= 1, (
                    f"race produced {len(matching)} reaction entries (expected 0 or 1). "
                    f"All reactions: {msg.get('reactions')}"
                )
        finally:
            await c.delete(f"{API}/chat/conversations/{conv_id}", headers=H_admin)
