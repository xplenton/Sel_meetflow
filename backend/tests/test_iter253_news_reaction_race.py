"""Iter 253 — news_reactions race-condition regression test.

50 concurrent toggle_reaction calls by the SAME user on the SAME post must
result in at most 1 reaction document. Without the unique index + atomic
upsert, TOCTOU would let multiple inserts succeed.
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
import httpx
import pytest

API = "http://localhost:8001/api"
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.mark.asyncio
async def test_news_reaction_race_safe():
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{API}/auth/login", json=ADMIN)
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        # Create a news post the admin owns
        r = await c.post(f"{API}/news/posts", headers=H, json={
            "title": "reaction-race-test",
            "content": "race test post",
            "status": "published",
        })
        assert r.status_code in (200, 201), r.text
        post_id = r.json()["post_id"]

        try:
            limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
            async with httpx.AsyncClient(timeout=30.0, limits=limits) as c2:
                # need a login on the new client
                r = await c2.post(f"{API}/auth/login", json=ADMIN)
                H2 = {"Authorization": f"Bearer {r.json()['token']}"}

                async def react():
                    r = await c2.post(
                        f"{API}/news/posts/{post_id}/reactions",
                        headers=H2,
                        json={"reaction_type": "like"},
                    )
                    return r.status_code

                results = await asyncio.gather(*[react() for _ in range(50)],
                                                return_exceptions=True)
                ok = sum(1 for s in results if isinstance(s, int) and 200 <= s < 300)
                assert ok >= 40, f"expected most toggles to return 2xx (got {ok}/50). results={results[:5]}"

                # Verify DB invariant: at most 1 reaction document for this (post, admin)
                cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
                db = cli[os.environ["DB_NAME"]]
                r = await c2.get(f"{API}/auth/me", headers=H2)
                admin_id = r.json()["user_id"]
                count = await db.news_reactions.count_documents(
                    {"post_id": post_id, "user_id": admin_id}
                )
                assert count <= 1, f"race produced {count} reaction docs (expected 0 or 1)"
        finally:
            await c.delete(f"{API}/news/posts/{post_id}", headers=H)
