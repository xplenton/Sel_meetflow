"""Iter 250 — Survey double-submit race-condition regression test.

50 concurrent POST /api/surveys/{id}/respond by the SAME user must result in
exactly 1 success + 49 failures (400 'Bereits teilgenommen'). The unique
partial index on (survey_id, _user_dedup) enforces this atomically across
multiple uvicorn workers.
"""
import asyncio
import httpx
import pytest

API = "http://localhost:8001/api"
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.mark.asyncio
async def test_50_concurrent_survey_respond_same_user():
    async with httpx.AsyncClient(timeout=30.0) as c:
        # Login admin to create the survey
        r = await c.post(f"{API}/auth/login", json=ADMIN)
        assert r.status_code == 200
        admin_h = {"Authorization": f"Bearer {r.json()['token']}"}

        # Register + login a member user
        import uuid
        email = f"test-survey-race-{uuid.uuid4().hex[:8]}@meetflow.com"
        r = await c.post(f"{API}/auth/register", json={"email": email, "password": "test123", "name": "Race Tester"})
        assert r.status_code in (200, 201), r.text
        r = await c.post(f"{API}/auth/login", json={"email": email, "password": "test123"})
        assert r.status_code == 200
        user_h = {"Authorization": f"Bearer {r.json()['token']}"}

        # Create + publish a simple survey
        r = await c.post(f"{API}/surveys", headers=admin_h, json={
            "title": "Race-Test Survey", "description": "test",
            "target_all": True,
            "questions": [{"question_id": "q1", "type": "single_choice", "text": "?", "options": ["a", "b"], "required": True}],
        })
        assert r.status_code in (200, 201), r.text
        survey_id = r.json()["survey_id"]
        # publish
        r = await c.post(f"{API}/surveys/{survey_id}/publish", headers=admin_h)
        if r.status_code not in (200, 201):
            # fallback to PUT update
            r = await c.put(f"{API}/surveys/{survey_id}", headers=admin_h, json={"status": "published"})
        assert r.status_code in (200, 201), r.text

        try:
            body = {"answers": {"q1": "a"}}

            async def respond():
                r = await c.post(f"{API}/surveys/{survey_id}/respond", headers=user_h, json=body)
                return r.status_code

            results = await asyncio.gather(*[respond() for _ in range(50)])
            ok = sum(1 for s in results if s in (200, 201))
            already = sum(1 for s in results if s == 400)
            other = 50 - ok - already

            assert ok == 1, f"expected exactly 1 success, got {ok}. distribution: 200/201={ok}, 400={already}, other={other}, results={results}"
            assert other == 0, f"unexpected non-400 errors: {other}"
        finally:
            await c.delete(f"{API}/surveys/{survey_id}", headers=admin_h)
