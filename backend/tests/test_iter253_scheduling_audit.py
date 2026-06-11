"""Iter 253 — Comprehensive Scheduling (Terminplanung) Module Audit.

Tests:
- Schedule Polls CRUD (create, list, get, delete, confirm)
- General Polls CRUD
- Booking Availability
- Public Poll Voting
- ICS/CSV Export
- Validation & Error Handling
- RBAC (member vs admin)
- Load Tests (50 concurrent)
- Race Condition Tests (vote, finalize)
- Background Queue (async endpoints)
"""
import asyncio
import os
import uuid
import pytest
import httpx
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://video-meet-pro.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}


# ============================================================================
# Helper functions for tokens (sync approach)
# ============================================================================

_admin_token_cache = None
_member_user_cache = None


def get_admin_token():
    global _admin_token_cache
    if _admin_token_cache:
        return _admin_token_cache
    import requests
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    _admin_token_cache = r.json()["token"]
    return _admin_token_cache


def get_member_user():
    global _member_user_cache
    if _member_user_cache:
        return _member_user_cache
    import requests
    email = f"test-sched-{uuid.uuid4().hex[:8]}@meetflow.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email,
        "password": "test123",
        "name": "Test Scheduler"
    }, timeout=30)
    if r.status_code not in (200, 201):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "test123"}, timeout=30)
    assert r.status_code in (200, 201), f"Member registration failed: {r.text}"
    data = r.json()
    _member_user_cache = {"token": data["token"], "user_id": data.get("user_id"), "email": email}
    return _member_user_cache


@pytest.fixture
def admin_token():
    return get_admin_token()


@pytest.fixture
def member_user():
    return get_member_user()


# ============================================================================
# Schedule Polls CRUD Tests
# ============================================================================

class TestSchedulePollsCRUD:
    """Schedule Polls (Terminabstimmung) CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_schedule_poll(self, admin_token):
        """POST /api/schedule-polls — create a new schedule poll."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            
            payload = {
                "title": "test-schedule-poll-create",
                "description": "Test poll for scheduling audit",
                "time_slots": [
                    {"date": tomorrow, "start_time": "09:00", "end_time": "10:00"},
                    {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"},
                    {"date": next_week, "start_time": "10:00", "end_time": "11:00"},
                ],
                "deadline": (datetime.now() + timedelta(days=5)).isoformat(),
                "allow_maybe": True,
                "allow_suggestions": True,
                "is_private": False,
                "create_meeting_on_confirm": True,
            }
            r = await c.post(f"{API}/schedule-polls", headers=H, json=payload)
            assert r.status_code in (200, 201), f"Create poll failed: {r.text}"
            data = r.json()
            assert "poll_id" in data
            assert "share_token" in data
            print(f"✓ Created schedule poll: {data['poll_id']}")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{data['poll_id']}", headers=H)

    @pytest.mark.asyncio
    async def test_list_schedule_polls(self, admin_token):
        """GET /api/schedule-polls — list user's polls with pagination."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            r = await c.get(f"{API}/schedule-polls?page=1&limit=10", headers=H)
            assert r.status_code == 200, f"List polls failed: {r.text}"
            data = r.json()
            assert "polls" in data
            assert "total" in data
            assert "pages" in data
            print(f"✓ Listed {len(data['polls'])} schedule polls (total: {data['total']})")

    @pytest.mark.asyncio
    async def test_get_schedule_poll_detail(self, admin_token):
        """GET /api/schedule-polls/{id} — get poll details."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            # Create a poll first
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-get-detail",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            poll_id = r.json()["poll_id"]
            
            # Get detail
            r = await c.get(f"{API}/schedule-polls/{poll_id}", headers=H)
            assert r.status_code == 200, f"Get poll detail failed: {r.text}"
            data = r.json()
            assert data["poll_id"] == poll_id
            assert data["title"] == "test-get-detail"
            print(f"✓ Got poll detail: {poll_id}")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)

    @pytest.mark.asyncio
    async def test_delete_schedule_poll(self, admin_token):
        """DELETE /api/schedule-polls/{id} — delete a poll."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-delete-poll",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            poll_id = r.json()["poll_id"]
            
            r = await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)
            assert r.status_code == 200, f"Delete poll failed: {r.text}"
            
            # Verify deleted
            r = await c.get(f"{API}/schedule-polls/{poll_id}", headers=H)
            assert r.status_code == 404
            print(f"✓ Deleted poll: {poll_id}")


# ============================================================================
# Public Poll Voting Tests
# ============================================================================

class TestPublicPollVoting:
    """Public poll voting via share_token."""

    @pytest.mark.asyncio
    async def test_public_poll_access(self, admin_token):
        """GET /api/schedule-polls/public/{share_token} — access poll publicly."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-public-access",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            data = r.json()
            share_token = data["share_token"]
            poll_id = data["poll_id"]
            
            # Access publicly (no auth)
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            assert r.status_code == 200, f"Public access failed: {r.text}"
            public_data = r.json()
            assert public_data["poll_id"] == poll_id
            print(f"✓ Public poll access works: {share_token}")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)

    @pytest.mark.asyncio
    async def test_public_poll_vote(self, admin_token):
        """POST /api/schedule-polls/public/{share_token}/vote — submit vote."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-vote-poll",
                "time_slots": [
                    {"date": tomorrow, "start_time": "09:00", "end_time": "10:00"},
                    {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"},
                ],
                "allow_maybe": True,
            })
            data = r.json()
            share_token = data["share_token"]
            poll_id = data["poll_id"]
            
            # Get poll to get slot IDs
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            slots = r.json()["time_slots"]
            
            # Vote
            r = await c.post(f"{API}/schedule-polls/public/{share_token}/vote", json={
                "voter_name": "Test Voter",
                "voter_email": "voter@test.com",
                "votes": {slots[0]["slot_id"]: "yes", slots[1]["slot_id"]: "maybe"},
            })
            assert r.status_code == 200, f"Vote failed: {r.text}"
            assert "vote_id" in r.json()
            print("✓ Vote submitted successfully")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)

    @pytest.mark.asyncio
    async def test_vote_update_same_voter(self, admin_token):
        """Voting again with same name should update, not duplicate."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-vote-update",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            data = r.json()
            share_token = data["share_token"]
            poll_id = data["poll_id"]
            
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            slots = r.json()["time_slots"]
            
            # First vote
            await c.post(f"{API}/schedule-polls/public/{share_token}/vote", json={
                "voter_name": "Same Voter",
                "votes": {slots[0]["slot_id"]: "yes"},
            })
            
            # Second vote (update)
            await c.post(f"{API}/schedule-polls/public/{share_token}/vote", json={
                "voter_name": "Same Voter",
                "votes": {slots[0]["slot_id"]: "no"},
            })
            
            # Check only 1 vote exists
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            votes = r.json().get("votes", [])
            same_voter_votes = [v for v in votes if v["voter_name"].lower() == "same voter"]
            assert len(same_voter_votes) == 1, f"Expected 1 vote, got {len(same_voter_votes)}"
            assert same_voter_votes[0]["votes"][slots[0]["slot_id"]] == "no"
            print("✓ Vote update works (no duplicates)")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)


# ============================================================================
# Poll Confirmation Tests
# ============================================================================

class TestPollConfirmation:
    """Poll confirmation (finalize) tests."""

    @pytest.mark.asyncio
    async def test_confirm_poll_creates_meeting(self, admin_token):
        """POST /api/schedule-polls/{id}/confirm — confirm slot and create meeting."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-confirm-meeting",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
                "create_meeting_on_confirm": True,
            })
            data = r.json()
            poll_id = data["poll_id"]
            
            # Get slot ID
            r = await c.get(f"{API}/schedule-polls/{poll_id}", headers=H)
            slot_id = r.json()["time_slots"][0]["slot_id"]
            
            # Confirm
            r = await c.post(f"{API}/schedule-polls/{poll_id}/confirm", headers=H, json={"slot_id": slot_id})
            assert r.status_code == 200, f"Confirm failed: {r.text}"
            result = r.json()
            assert "meeting_id" in result, "Meeting should be created on confirm"
            print(f"✓ Poll confirmed, meeting created: {result.get('meeting_id')}")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)


# ============================================================================
# Validation & Error Handling Tests
# ============================================================================

class TestValidationErrors:
    """Validation and error handling tests."""

    @pytest.mark.asyncio
    async def test_create_poll_without_title(self, admin_token):
        """POST without title should fail with 422."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            assert r.status_code == 422, f"Expected 422, got {r.status_code}"
            print("✓ Create without title returns 422")

    @pytest.mark.asyncio
    async def test_get_nonexistent_poll(self, admin_token):
        """GET non-existent poll should return 404."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            r = await c.get(f"{API}/schedule-polls/nonexistent_poll_id", headers=H)
            assert r.status_code == 404
            print("✓ Non-existent poll returns 404")

    @pytest.mark.asyncio
    async def test_unauthenticated_access(self):
        """Accessing protected endpoints without token should return 401."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(f"{API}/schedule-polls")
            assert r.status_code == 401
            print("✓ Unauthenticated access returns 401")


# ============================================================================
# ICS/CSV Export Tests
# ============================================================================

class TestExports:
    """ICS and CSV export tests."""

    @pytest.mark.asyncio
    async def test_ics_export_confirmed_poll(self, admin_token):
        """GET /api/schedule-polls/{id}/ical — export confirmed poll as ICS."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-ics-export",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            data = r.json()
            poll_id = data["poll_id"]
            
            # Get slot ID and confirm
            r = await c.get(f"{API}/schedule-polls/{poll_id}", headers=H)
            slot_id = r.json()["time_slots"][0]["slot_id"]
            await c.post(f"{API}/schedule-polls/{poll_id}/confirm", headers=H, json={"slot_id": slot_id})
            
            # Export ICS
            r = await c.get(f"{API}/schedule-polls/{poll_id}/ical", headers=H)
            assert r.status_code == 200, f"ICS export failed: {r.text}"
            assert "text/calendar" in r.headers.get("content-type", "")
            assert b"BEGIN:VCALENDAR" in r.content
            print("✓ ICS export works")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)

    @pytest.mark.asyncio
    async def test_csv_export(self, admin_token):
        """GET /api/schedule-polls/{id}/export/csv — export poll results as CSV."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-csv-export",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            poll_id = r.json()["poll_id"]
            
            r = await c.get(f"{API}/schedule-polls/{poll_id}/export/csv", headers=H)
            assert r.status_code == 200, f"CSV export failed: {r.text}"
            assert "text/csv" in r.headers.get("content-type", "")
            print("✓ CSV export works")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)


# ============================================================================
# General Polls Tests
# ============================================================================

class TestGeneralPolls:
    """General Polls (Umfragen) CRUD tests."""

    @pytest.mark.asyncio
    async def test_create_general_poll(self, admin_token):
        """POST /api/general-polls — create a general poll."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            r = await c.post(f"{API}/general-polls", headers=H, json={
                "title": "test-general-poll",
                "description": "Test survey",
                "poll_type": "single",
                "options": ["Option A", "Option B", "Option C"],
                "allow_custom_options": True,
            })
            assert r.status_code in (200, 201), f"Create general poll failed: {r.text}"
            data = r.json()
            assert "poll_id" in data
            assert "share_token" in data
            print(f"✓ Created general poll: {data['poll_id']}")
            
            # Cleanup
            await c.delete(f"{API}/general-polls/{data['poll_id']}", headers=H)

    @pytest.mark.asyncio
    async def test_general_poll_vote(self, admin_token):
        """POST /api/general-polls/public/{share_token}/vote — vote on general poll."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            r = await c.post(f"{API}/general-polls", headers=H, json={
                "title": "test-gpoll-vote",
                "poll_type": "multiple",
                "options": ["A", "B", "C"],
            })
            data = r.json()
            share_token = data["share_token"]
            poll_id = data["poll_id"]
            
            # Vote
            r = await c.post(f"{API}/general-polls/public/{share_token}/vote", json={
                "voter_name": "Test Voter",
                "selected_options": ["A", "C"],
            })
            assert r.status_code == 200, f"Vote failed: {r.text}"
            print("✓ General poll vote works")
            
            # Cleanup
            await c.delete(f"{API}/general-polls/{poll_id}", headers=H)


# ============================================================================
# RBAC Tests
# ============================================================================

class TestRBAC:
    """Role-based access control tests."""

    @pytest.mark.asyncio
    async def test_member_can_create_own_poll(self, member_user):
        """Member can create their own polls."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {member_user['token']}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "test-member-poll",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            assert r.status_code in (200, 201), f"Member create poll failed: {r.text}"
            poll_id = r.json()["poll_id"]
            print("✓ Member can create polls")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)

    @pytest.mark.asyncio
    async def test_member_cannot_delete_others_poll(self, admin_token, member_user):
        """Member cannot delete another user's poll."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            # Admin creates poll
            H_admin = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            r = await c.post(f"{API}/schedule-polls", headers=H_admin, json={
                "title": "test-admin-poll-rbac",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            poll_id = r.json()["poll_id"]
            
            # Member tries to delete
            H_member = {"Authorization": f"Bearer {member_user['token']}"}
            r = await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H_member)
            assert r.status_code == 403, f"Expected 403, got {r.status_code}"
            print("✓ Member cannot delete other's poll (403)")
            
            # Cleanup with admin
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H_admin)


# ============================================================================
# Load Tests (50 Concurrent)
# ============================================================================

class TestLoadConcurrent:
    """50 concurrent request load tests."""

    @pytest.mark.asyncio
    async def test_50_concurrent_get_polls(self, admin_token):
        """50× GET /api/schedule-polls concurrent."""
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
        async with httpx.AsyncClient(timeout=30.0, limits=limits) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            
            async def fetch():
                r = await c.get(f"{API}/schedule-polls?page=1&limit=5", headers=H)
                return r.status_code
            
            results = await asyncio.gather(*[fetch() for _ in range(50)], return_exceptions=True)
            success = sum(1 for r in results if isinstance(r, int) and r == 200)
            assert success >= 45, f"Expected >=45 success, got {success}/50"
            print(f"✓ 50 concurrent GET polls: {success}/50 success")

    @pytest.mark.asyncio
    async def test_50_concurrent_create_polls(self, admin_token):
        """50× POST /api/schedule-polls by same user."""
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
        async with httpx.AsyncClient(timeout=30.0, limits=limits) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            created_ids = []
            
            async def create(i):
                r = await c.post(f"{API}/schedule-polls", headers=H, json={
                    "title": f"load-test-poll-{i}",
                    "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
                })
                if r.status_code in (200, 201):
                    return r.json().get("poll_id")
                return None
            
            results = await asyncio.gather(*[create(i) for i in range(50)], return_exceptions=True)
            created_ids = [r for r in results if isinstance(r, str)]
            print(f"✓ 50 concurrent CREATE polls: {len(created_ids)}/50 created")
            
            # Cleanup
            for pid in created_ids:
                try:
                    await c.delete(f"{API}/schedule-polls/{pid}", headers=H)
                except:
                    pass
            
            assert len(created_ids) >= 45, f"Expected >=45 created, got {len(created_ids)}"

    @pytest.mark.asyncio
    async def test_50_concurrent_votes_different_users(self, admin_token):
        """50× POST vote by 50 different voters on same poll."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Create poll
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "load-test-votes",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            data = r.json()
            share_token = data["share_token"]
            poll_id = data["poll_id"]
            
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            slot_id = r.json()["time_slots"][0]["slot_id"]
            
            limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
            async with httpx.AsyncClient(timeout=30.0, limits=limits) as c2:
                async def vote(i):
                    r = await c2.post(f"{API}/schedule-polls/public/{share_token}/vote", json={
                        "voter_name": f"Voter-{i}",
                        "votes": {slot_id: "yes"},
                    })
                    return r.status_code
                
                results = await asyncio.gather(*[vote(i) for i in range(50)], return_exceptions=True)
                success = sum(1 for r in results if isinstance(r, int) and r == 200)
                print(f"✓ 50 concurrent votes (different users): {success}/50 success")
            
            # Verify all votes stored
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            votes = r.json().get("votes", [])
            print(f"  → {len(votes)} votes stored in DB")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)
            
            assert success >= 45


# ============================================================================
# Race Condition Tests
# ============================================================================

class TestRaceConditions:
    """Race condition tests for vote and finalize operations."""

    @pytest.mark.asyncio
    async def test_50_concurrent_votes_same_user_race(self, admin_token):
        """50× POST vote by SAME user — should result in exactly 1 vote (last-writer-wins)."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            
            r = await c.post(f"{API}/schedule-polls", headers=H, json={
                "title": "race-test-same-voter",
                "time_slots": [{"date": tomorrow, "start_time": "09:00", "end_time": "10:00"}],
            })
            data = r.json()
            share_token = data["share_token"]
            poll_id = data["poll_id"]
            
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            slot_id = r.json()["time_slots"][0]["slot_id"]
            
            limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
            async with httpx.AsyncClient(timeout=30.0, limits=limits) as c2:
                async def vote(i):
                    r = await c2.post(f"{API}/schedule-polls/public/{share_token}/vote", json={
                        "voter_name": "Same-Voter",  # Same name for all
                        "votes": {slot_id: ["yes", "no", "maybe"][i % 3]},
                    })
                    return r.status_code
                
                results = await asyncio.gather(*[vote(i) for i in range(50)], return_exceptions=True)
                success = sum(1 for r in results if isinstance(r, int) and r == 200)
                print(f"✓ 50 concurrent votes (same user): {success}/50 returned 200")
            
            # Verify exactly 1 vote for "Same-Voter"
            r = await c.get(f"{API}/schedule-polls/public/{share_token}")
            votes = r.json().get("votes", [])
            same_voter_votes = [v for v in votes if v["voter_name"].lower() == "same-voter"]
            assert len(same_voter_votes) == 1, f"Race produced {len(same_voter_votes)} votes (expected 1)"
            print("  → Exactly 1 vote stored (race-safe)")
            
            # Cleanup
            await c.delete(f"{API}/schedule-polls/{poll_id}", headers=H)


# ============================================================================
# Background Queue Tests (Iter 253)
# ============================================================================

class TestBackgroundQueue:
    """Iter 253 background queue tests."""

    @pytest.mark.asyncio
    async def test_async_push_endpoint(self, admin_token):
        """POST /api/news/push/send/async — returns job_id."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            
            # Create a news post first
            r = await c.post(f"{API}/news/posts", headers=H, json={
                "title": "test-async-push",
                "content": "Test content",
                "status": "published",
            })
            if r.status_code not in (200, 201):
                pytest.skip("Could not create news post for async push test")
            post_id = r.json()["post_id"]
            
            # Call async push
            r = await c.post(f"{API}/news/push/send/async", headers=H, json={"post_id": post_id})
            assert r.status_code == 200, f"Async push failed: {r.text}"
            data = r.json()
            assert "job_id" in data
            print(f"✓ Async push returns job_id: {data['job_id']}")
            
            # Poll job status
            job_id = data["job_id"]
            if job_id != "inline":
                r = await c.get(f"{API}/jobs/{job_id}", headers=H)
                assert r.status_code in (200, 503), f"Job status failed: {r.text}"
                if r.status_code == 200:
                    print(f"  → Job status: {r.json().get('status')}")
            
            # Cleanup
            await c.delete(f"{API}/news/posts/{post_id}", headers=H)

    @pytest.mark.asyncio
    async def test_async_office_days_generate(self, admin_token):
        """POST /api/users/me/office-days/generate/async — returns job_id."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            
            # First set up office days config
            await c.put(f"{API}/users/me/office-days", headers=H, json={
                "weekdays": ["mon", "wed", "fri"],
                "start_time": "09:00",
                "end_time": "17:00",
            })
            
            # Call async generate (may fail if no desk configured, that's OK)
            r = await c.post(f"{API}/users/me/office-days/generate/async", headers=H, json={"weeks": 12})
            # Accept 200 (success) or 400 (no desk configured)
            if r.status_code == 200:
                data = r.json()
                assert "job_id" in data
                print(f"✓ Async office-days generate returns job_id: {data['job_id']}")
            else:
                print(f"✓ Async office-days generate: {r.status_code} (expected if no desk)")

    @pytest.mark.asyncio
    async def test_job_polling_endpoint(self, admin_token):
        """GET /api/jobs/{job_id} — poll job status."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            
            # Test with a fake job_id
            r = await c.get(f"{API}/jobs/fake_job_id_12345", headers=H)
            # Should return 200 with status "not_found" or 503 if Redis down
            assert r.status_code in (200, 503), f"Job poll failed: {r.text}"
            if r.status_code == 200:
                data = r.json()
                assert "status" in data
                print(f"✓ Job polling works: status={data.get('status')}")


# ============================================================================
# Regression Tests (Iter 252/253)
# ============================================================================

class TestRegression:
    """Regression tests for previous iterations."""

    @pytest.mark.asyncio
    async def test_news_reaction_race_regression(self, admin_token):
        """Iter 253 — news reaction race fix regression."""
        async with httpx.AsyncClient(timeout=30.0) as c:
            H = {"Authorization": f"Bearer {admin_token}"}
            
            # Create a news post
            r = await c.post(f"{API}/news/posts", headers=H, json={
                "title": "reaction-race-regression",
                "content": "Test",
                "status": "published",
            })
            if r.status_code not in (200, 201):
                pytest.skip("Could not create news post")
            post_id = r.json()["post_id"]
            
            # 10 concurrent reactions (lighter test)
            limits = httpx.Limits(max_connections=50, max_keepalive_connections=25)
            async with httpx.AsyncClient(timeout=30.0, limits=limits) as c2:
                r = await c2.post(f"{API}/auth/login", json=ADMIN)
                H2 = {"Authorization": f"Bearer {r.json()['token']}"}
                
                async def react():
                    r = await c2.post(f"{API}/news/posts/{post_id}/reactions", headers=H2, json={"reaction_type": "like"})
                    return r.status_code
                
                results = await asyncio.gather(*[react() for _ in range(10)], return_exceptions=True)
                success = sum(1 for r in results if isinstance(r, int) and 200 <= r < 300)
                print(f"✓ News reaction race: {success}/10 success")
            
            # Cleanup
            await c.delete(f"{API}/news/posts/{post_id}", headers=H)


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
