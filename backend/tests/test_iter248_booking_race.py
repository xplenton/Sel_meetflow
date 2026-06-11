"""Iter 248 — Race-condition regression test for resource_bookings.

Verifies that 50 concurrent POST requests to /api/resource-bookings for the
SAME resource + SAME timeslot result in exactly ONE successful booking and
49 conflict (409) responses.

Tests against localhost (bypasses ingress rate-limiting) so the result is
deterministic and reflects production behaviour with multiple workers.
"""
import asyncio
from datetime import datetime, timezone, timedelta

import httpx
import pytest

API = "http://localhost:8001/api"
ADMIN_CREDS = {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.mark.asyncio
async def test_50_concurrent_same_slot_race_condition():
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{API}/auth/login", json=ADMIN_CREDS)
        assert r.status_code == 200
        token = r.json()["token"]
        H = {"Authorization": f"Bearer {token}"}

        # Seed a desk
        seed = await c.post(f"{API}/resources", json={
            "name": "race-test-desk", "type": "desk", "status": "active",
            "location": "racetest", "desk_number": "RT1",
        }, headers=H)
        assert seed.status_code in (200, 201), seed.text
        desk_id = seed.json()["resource_id"]

        try:
            start = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
            end = start + timedelta(hours=1)
            body = {
                "resource_id": desk_id,
                "title": "race-it248",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            }

            async def book():
                r = await c.post(f"{API}/resource-bookings", headers=H, json=body)
                return r.status_code

            results = await asyncio.gather(*[book() for _ in range(50)])

            success = sum(1 for s in results if s in (200, 201))
            conflict = sum(1 for s in results if s == 409)
            other = 50 - success - conflict

            assert success == 1, (
                f"Race-condition bug: expected exactly 1 success, got {success}. "
                f"Distribution: 200/201={success}, 409={conflict}, other={other}"
            )
            assert conflict == 49, f"expected 49 conflicts, got {conflict}"
            assert other == 0, f"unexpected non-conflict errors: {other}"
        finally:
            await c.delete(f"{API}/resources/{desk_id}", headers=H)
