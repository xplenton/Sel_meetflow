"""Iter 252 — Race condition regression tests for additional endpoints.

1) update_booking (move) — TOCTOU between _check_conflicts and find_one_and_update.
2) poll vote — TOCTOU between "already voted" check and $push.
"""
import asyncio
from datetime import datetime, timezone, timedelta

import httpx
import pytest

API = "http://localhost:8001/api"
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.mark.asyncio
async def test_move_booking_race_safe():
    """Concurrently move two bookings into the SAME target slot — exactly one wins."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{API}/auth/login", json=ADMIN)
        assert r.status_code == 200, r.text
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        # Seed a desk
        desk = await c.post(f"{API}/resources", headers=H, json={
            "name": "move-race-desk", "type": "desk", "status": "active",
            "location": "moveracetest", "desk_number": "MR1",
        })
        assert desk.status_code in (200, 201), desk.text
        rid = desk.json()["resource_id"]

        try:
            # Two source bookings at well-separated times
            base = datetime.now(timezone.utc) + timedelta(days=45)
            b1 = await c.post(f"{API}/resource-bookings", headers=H, json={
                "resource_id": rid, "title": "src1",
                "start_at": base.isoformat(), "end_at": (base + timedelta(hours=1)).isoformat(),
            })
            b2 = await c.post(f"{API}/resource-bookings", headers=H, json={
                "resource_id": rid, "title": "src2",
                "start_at": (base + timedelta(hours=2)).isoformat(),
                "end_at": (base + timedelta(hours=3)).isoformat(),
            })
            assert b1.status_code in (200, 201), b1.text
            assert b2.status_code in (200, 201), b2.text
            id1, id2 = b1.json()["booking_id"], b2.json()["booking_id"]

            # Now race both to move into the SAME target slot at base+5h
            target_start = (base + timedelta(hours=5)).isoformat()
            target_end = (base + timedelta(hours=6)).isoformat()

            async def move(bid):
                r = await c.put(f"{API}/resource-bookings/{bid}", headers=H, json={
                    "start_at": target_start, "end_at": target_end,
                })
                return r.status_code

            results = await asyncio.gather(*[move(id1) for _ in range(25)],
                                           *[move(id2) for _ in range(25)])
            ok = sum(1 for s in results if s == 200)
            conflict = sum(1 for s in results if s == 409)
            other = 50 - ok - conflict

            # At least one must succeed (the winner) and the rest must be conflicts.
            assert ok >= 1, f"expected at least 1 success, got {ok}"
            assert other == 0, f"unexpected non-conflict errors: {other}, results={results}"

            # Verify final DB state: no two bookings overlap on this resource.
            r = await c.get(f"{API}/resource-bookings", headers=H,
                            params={"resource_id": rid, "from_date": base.isoformat(),
                                    "to_date": (base + timedelta(days=2)).isoformat()})
            assert r.status_code == 200
            bks = [b for b in r.json() if b.get("status") != "cancelled"]
            # Sort by start_at, check no overlaps
            bks.sort(key=lambda b: b["start_at"])
            for i in range(len(bks) - 1):
                e_i = bks[i]["end_at"]
                s_n = bks[i + 1]["start_at"]
                assert e_i <= s_n, f"overlap detected: {bks[i]} vs {bks[i+1]}"

        finally:
            await c.delete(f"{API}/resources/{rid}", headers=H)


@pytest.mark.asyncio
async def test_poll_vote_race_safe():
    """50 concurrent votes by the SAME user — exactly 1 stored."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        # Admin creates meeting + poll and votes (admin sees any meeting)
        r = await c.post(f"{API}/auth/login", json=ADMIN)
        H_admin = {"Authorization": f"Bearer {r.json()['token']}"}

        # Create a meeting
        r = await c.post(f"{API}/meetings", headers=H_admin, json={
            "title": "poll-race-meeting", "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "duration_minutes": 60,
        })
        assert r.status_code in (200, 201), r.text
        meeting_id = r.json()["meeting_id"]

        try:
            # Create a poll
            r = await c.post(f"{API}/meetings/{meeting_id}/polls", headers=H_admin, json={
                "question": "race?", "options": ["a", "b"],
            })
            assert r.status_code in (200, 201), r.text
            poll_id = r.json()["poll_id"]

            async def vote():
                r = await c.post(
                    f"{API}/meetings/{meeting_id}/polls/{poll_id}/vote",
                    headers=H_admin, json={"option_index": 0},
                )
                return r.status_code

            results = await asyncio.gather(*[vote() for _ in range(50)])
            ok = sum(1 for s in results if s == 200)
            already = sum(1 for s in results if s == 400)
            other = 50 - ok - already
            assert ok == 1, f"expected exactly 1 success, got {ok}. results={results}"
            assert other == 0, f"unexpected non-400 errors: {other}, results={results}"

            # Confirm DB state: total_votes is exactly 1
            r = await c.get(f"{API}/meetings/{meeting_id}/polls", headers=H_admin)
            polls = r.json()
            poll = next(p for p in polls if p["poll_id"] == poll_id)
            assert poll["total_votes"] == 1, f"total_votes={poll['total_votes']}, expected 1"

        finally:
            await c.delete(f"{API}/meetings/{meeting_id}", headers=H_admin)
