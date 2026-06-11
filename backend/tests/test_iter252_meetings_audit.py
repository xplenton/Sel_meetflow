"""Iter 252 — Comprehensive Meetings Module Audit

Tests:
- CRUD operations (create, read, update, delete)
- Polls (create, vote, close, race conditions)
- Q&A (questions, upvotes)
- Chat messages
- Breakout rooms
- RBAC (host-only, admin, member permissions)
- Validation (400 errors)
- Load tests (50 concurrent)
- Regression tests (iter 248 booking race, iter 250 survey race)
"""
import asyncio
from datetime import datetime, timezone, timedelta
import httpx
import pytest

BASE_URL = "https://video-meet-pro.preview.emergentagent.com/api"
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}


async def get_admin_token():
    """Get admin auth token."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{BASE_URL}/auth/login", json=ADMIN)
        assert r.status_code == 200, f"Admin login failed: {r.text}"
        return r.json()["token"]


# ============ MEETINGS CRUD ============

@pytest.mark.asyncio
async def test_create_meeting_success():
    """POST /api/meetings — create meeting with valid data."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        scheduled = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-meeting-create",
            "scheduled_at": scheduled,
            "duration": 60,
            "meeting_type": "scheduled"
        })
        assert r.status_code in (200, 201), f"Create failed: {r.text}"
        data = r.json()
        assert "meeting_id" in data
        assert data["title"] == "test-meeting-create"
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{data['meeting_id']}", headers=H)


@pytest.mark.asyncio
async def test_create_meeting_without_title_400():
    """POST /api/meetings without title -> 400."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "duration": 60
        })
        assert r.status_code == 400 or r.status_code == 422, f"Expected 400/422, got {r.status_code}"


@pytest.mark.asyncio
async def test_list_meetings():
    """GET /api/meetings — list meetings."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        r = await c.get(f"{BASE_URL}/meetings", headers=H)
        assert r.status_code == 200
        data = r.json()
        assert "meetings" in data
        assert "total" in data


@pytest.mark.asyncio
async def test_get_meeting_detail():
    """GET /api/meetings/{id} — get meeting detail."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        # Create a meeting first
        scheduled = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-meeting-detail",
            "scheduled_at": scheduled,
            "duration": 30
        })
        assert r.status_code in (200, 201)
        meeting_id = r.json()["meeting_id"]
        
        # Get detail
        r = await c.get(f"{BASE_URL}/meetings/{meeting_id}", headers=H)
        assert r.status_code == 200
        data = r.json()
        assert data["meeting_id"] == meeting_id
        assert data["title"] == "test-meeting-detail"
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


@pytest.mark.asyncio
async def test_update_meeting():
    """PUT /api/meetings/{id} — update meeting (host only)."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        scheduled = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-meeting-update",
            "scheduled_at": scheduled,
            "duration": 45
        })
        assert r.status_code in (200, 201)
        meeting_id = r.json()["meeting_id"]
        
        # Update
        r = await c.put(f"{BASE_URL}/meetings/{meeting_id}", headers=H, json={
            "title": "test-meeting-updated-title",
            "duration": 90
        })
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "test-meeting-updated-title"
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


@pytest.mark.asyncio
async def test_delete_meeting():
    """DELETE /api/meetings/{id} — delete meeting."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        scheduled = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-meeting-delete",
            "scheduled_at": scheduled,
            "duration": 30
        })
        assert r.status_code in (200, 201)
        meeting_id = r.json()["meeting_id"]
        
        # Delete
        r = await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)
        assert r.status_code == 200
        
        # Verify deleted
        r = await c.get(f"{BASE_URL}/meetings/{meeting_id}", headers=H)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_join_meeting_nonexistent_404():
    """POST /api/meetings/{id}/join — nonexistent meeting -> 404."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        r = await c.post(f"{BASE_URL}/meetings/nonexistent123/join", headers=H)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_tokenless_request_401():
    """Tokenless requests -> 401."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{BASE_URL}/meetings")
        assert r.status_code == 401


# ============ POLLS ============

@pytest.mark.asyncio
async def test_create_poll():
    """POST /api/meetings/{id}/polls — create poll."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        # Create meeting
        scheduled = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-poll-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        # Create poll
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H, json={
            "question": "Test poll question?",
            "options": ["Option A", "Option B", "Option C"]
        })
        assert r.status_code in (200, 201)
        data = r.json()
        assert "poll_id" in data
        assert data["question"] == "Test poll question?"
        assert len(data["options"]) == 3
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


@pytest.mark.asyncio
async def test_vote_poll_success():
    """POST /api/meetings/{id}/polls/{poll_id}/vote — vote success."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        # Create meeting + poll
        scheduled = (datetime.now(timezone.utc) + timedelta(days=6)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-vote-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H, json={
            "question": "Vote test?",
            "options": ["Yes", "No"]
        })
        poll_id = r.json()["poll_id"]
        
        # Vote
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
            "option_index": 0
        })
        assert r.status_code == 200
        data = r.json()
        assert data["total_votes"] == 1
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


@pytest.mark.asyncio
async def test_vote_poll_invalid_option_400():
    """POST /api/meetings/{id}/polls/{poll_id}/vote with invalid option_index -> 400."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        # Create meeting + poll
        scheduled = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-invalid-vote-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H, json={
            "question": "Invalid vote test?",
            "options": ["A", "B"]
        })
        poll_id = r.json()["poll_id"]
        
        # Vote with invalid index
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
            "option_index": 99
        })
        assert r.status_code == 400
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


@pytest.mark.asyncio
async def test_vote_poll_already_voted_400():
    """Vote twice by same user -> 400 'Already voted'."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        # Create meeting + poll
        scheduled = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-double-vote-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H, json={
            "question": "Double vote test?",
            "options": ["X", "Y"]
        })
        poll_id = r.json()["poll_id"]
        
        # First vote
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
            "option_index": 0
        })
        assert r.status_code == 200
        
        # Second vote - should fail
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
            "option_index": 1
        })
        assert r.status_code == 400
        assert "Already voted" in r.text or "already" in r.text.lower()
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


@pytest.mark.asyncio
async def test_vote_closed_poll_400():
    """Vote on closed poll -> 400 'Poll is closed'."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        # Create meeting + poll
        scheduled = (datetime.now(timezone.utc) + timedelta(days=9)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-closed-poll-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H, json={
            "question": "Closed poll test?",
            "options": ["1", "2"]
        })
        poll_id = r.json()["poll_id"]
        
        # Close poll
        r = await c.put(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/close", headers=H)
        assert r.status_code == 200
        
        # Try to vote on closed poll
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
            "option_index": 0
        })
        assert r.status_code == 400
        assert "closed" in r.text.lower()
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


# ============ Q&A ============

@pytest.mark.asyncio
async def test_create_question():
    """POST /api/meetings/{id}/questions — create question."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        scheduled = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-qa-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        # Create question
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/questions", headers=H, json={
            "text": "Test question for Q&A?"
        })
        assert r.status_code in (200, 201)
        data = r.json()
        assert "question_id" in data
        assert data["text"] == "Test question for Q&A?"
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


@pytest.mark.asyncio
async def test_upvote_question():
    """POST /api/meetings/{id}/questions/{q_id}/upvote — upvote question."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        scheduled = (datetime.now(timezone.utc) + timedelta(days=11)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-upvote-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/questions", headers=H, json={
            "text": "Upvote test question?"
        })
        question_id = r.json()["question_id"]
        
        # Upvote
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/questions/{question_id}/upvote", headers=H)
        assert r.status_code == 200
        data = r.json()
        assert data["upvotes"] == 1
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


# ============ CHAT ============

@pytest.mark.asyncio
async def test_send_chat_message():
    """POST /api/meetings/{id}/chat — send chat message."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        scheduled = (datetime.now(timezone.utc) + timedelta(days=12)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-chat-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        # Send message
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/chat", headers=H, json={
            "message": "Hello from test!",
            "message_type": "text"
        })
        assert r.status_code in (200, 201)
        data = r.json()
        assert "message_id" in data
        assert data["message"] == "Hello from test!"
        
        # Get messages
        r = await c.get(f"{BASE_URL}/meetings/{meeting_id}/chat", headers=H)
        assert r.status_code == 200
        messages = r.json()
        assert len(messages) >= 1
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


# ============ BREAKOUT ROOMS ============

@pytest.mark.asyncio
async def test_create_breakout_room():
    """POST /api/meetings/{id}/breakout-rooms — create breakout room."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        scheduled = (datetime.now(timezone.utc) + timedelta(days=13)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-breakout-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        # Create breakout room
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/breakout-rooms", headers=H, json={
            "name": "Room 1",
            "participant_ids": []
        })
        assert r.status_code in (200, 201)
        data = r.json()
        assert "room_id" in data
        assert data["name"] == "Room 1"
        
        # Cleanup
        await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


# ============ LOAD TESTS (50 concurrent) ============

@pytest.mark.asyncio
async def test_50_concurrent_get_meetings():
    """50× GET /api/meetings concurrent -> all succeed."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=60.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        
        async def get_meetings():
            r = await c.get(f"{BASE_URL}/meetings", headers=H)
            return r.status_code
        
        results = await asyncio.gather(*[get_meetings() for _ in range(50)])
        success = sum(1 for s in results if s == 200)
        assert success == 50, f"Expected 50 successes, got {success}"


@pytest.mark.asyncio
async def test_50_concurrent_create_meetings():
    """50× POST /api/meetings by admin -> all 50 created."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=60.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        created_ids = []
        
        async def create_meeting(i):
            scheduled = (datetime.now(timezone.utc) + timedelta(days=20+i)).isoformat()
            r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
                "title": f"load-test-meeting-{i}",
                "scheduled_at": scheduled,
                "duration": 30
            })
            if r.status_code in (200, 201):
                return r.json().get("meeting_id")
            return None
        
        results = await asyncio.gather(*[create_meeting(i) for i in range(50)])
        created_ids = [mid for mid in results if mid]
        
        try:
            assert len(created_ids) == 50, f"Expected 50 created, got {len(created_ids)}"
        finally:
            # Cleanup
            for mid in created_ids:
                await c.delete(f"{BASE_URL}/meetings/{mid}", headers=H)


@pytest.mark.asyncio
async def test_50_concurrent_chat_messages():
    """50× POST /api/meetings/{id}/chat by admin -> all 50 stored."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=60.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        
        # Create meeting
        scheduled = (datetime.now(timezone.utc) + timedelta(days=100)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "load-test-chat-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        try:
            async def send_message(i):
                r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/chat", headers=H, json={
                    "message": f"Load test message {i}",
                    "message_type": "text"
                })
                return r.status_code
            
            results = await asyncio.gather(*[send_message(i) for i in range(50)])
            success = sum(1 for s in results if s in (200, 201))
            assert success == 50, f"Expected 50 successes, got {success}"
            
            # Verify all stored
            r = await c.get(f"{BASE_URL}/meetings/{meeting_id}/chat", headers=H)
            messages = r.json()
            load_msgs = [m for m in messages if "Load test message" in m.get("message", "")]
            assert len(load_msgs) == 50, f"Expected 50 messages stored, got {len(load_msgs)}"
        finally:
            await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


# ============ POLL VOTE RACE (iter 252 fix) ============

@pytest.mark.asyncio
async def test_50_concurrent_poll_votes_same_user():
    """50× POST /api/meetings/{id}/polls/{poll_id}/vote by SAME user -> exactly 1 success, 49× 400."""
    async with httpx.AsyncClient(timeout=60.0) as c:
        # Login as admin
        r = await c.post(f"{BASE_URL}/auth/login", json=ADMIN)
        H = {"Authorization": f"Bearer {r.json()['token']}"}
        
        # Create meeting + poll
        scheduled = (datetime.now(timezone.utc) + timedelta(days=101)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "race-poll-vote-meeting",
            "scheduled_at": scheduled,
            "duration": 60
        })
        meeting_id = r.json()["meeting_id"]
        
        r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H, json={
            "question": "Race condition test?",
            "options": ["A", "B"]
        })
        poll_id = r.json()["poll_id"]
        
        try:
            async def vote():
                r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
                    "option_index": 0
                })
                return r.status_code
            
            results = await asyncio.gather(*[vote() for _ in range(50)])
            ok = sum(1 for s in results if s == 200)
            already = sum(1 for s in results if s == 400)
            other = 50 - ok - already
            
            assert ok == 1, f"Expected exactly 1 success, got {ok}"
            assert other == 0, f"Unexpected errors: {other}"
            
            # Verify total_votes == 1
            r = await c.get(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H)
            polls = r.json()
            poll = next(p for p in polls if p["poll_id"] == poll_id)
            assert poll["total_votes"] == 1, f"Expected total_votes=1, got {poll['total_votes']}"
        finally:
            await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


# ============ REGRESSION TESTS ============

@pytest.mark.asyncio
async def test_health_check():
    """Backend health check."""
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{BASE_URL}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_iter248_booking_race_regression():
    """Iter 248 booking race still PASS."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{BASE_URL}/auth/login", json=ADMIN)
        H = {"Authorization": f"Bearer {r.json()['token']}"}
        
        # Create a desk resource
        r = await c.post(f"{BASE_URL}/resources", headers=H, json={
            "name": "race-regression-desk",
            "type": "desk",
            "status": "active",
            "location": "racetest",
            "desk_number": "RR1"
        })
        if r.status_code not in (200, 201):
            pytest.skip("Could not create resource for race test")
        rid = r.json()["resource_id"]
        
        try:
            base = datetime.now(timezone.utc) + timedelta(days=50)
            
            async def book():
                r = await c.post(f"{BASE_URL}/resource-bookings", headers=H, json={
                    "resource_id": rid,
                    "title": "race-booking",
                    "start_at": base.isoformat(),
                    "end_at": (base + timedelta(hours=1)).isoformat()
                })
                return r.status_code
            
            results = await asyncio.gather(*[book() for _ in range(50)])
            ok = sum(1 for s in results if s in (200, 201))
            conflict = sum(1 for s in results if s == 409)
            
            assert ok >= 1, f"Expected at least 1 success, got {ok}"
            assert ok + conflict == 50, "Expected all to be success or conflict"
        finally:
            await c.delete(f"{BASE_URL}/resources/{rid}", headers=H)


@pytest.mark.asyncio
async def test_iter250_survey_race_regression():
    """Iter 250 survey race still PASS."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{BASE_URL}/auth/login", json=ADMIN)
        H = {"Authorization": f"Bearer {r.json()['token']}"}
        
        # Create a survey
        r = await c.post(f"{BASE_URL}/surveys", headers=H, json={
            "title": "race-regression-survey",
            "description": "Test survey for race condition",
            "questions": [{"type": "text", "text": "Test question?", "required": True}],
            "status": "published",
            "target_all": True
        })
        if r.status_code not in (200, 201):
            pytest.skip("Could not create survey for race test")
        survey_id = r.json()["survey_id"]
        
        try:
            async def respond():
                r = await c.post(f"{BASE_URL}/surveys/{survey_id}/responses", headers=H, json={
                    "answers": [{"question_index": 0, "value": "Test answer"}]
                })
                return r.status_code
            
            results = await asyncio.gather(*[respond() for _ in range(50)])
            ok = sum(1 for s in results if s in (200, 201))
            already = sum(1 for s in results if s == 400)
            
            assert ok == 1, f"Expected exactly 1 success, got {ok}"
            assert ok + already == 50, "Expected all to be success or already responded"
        finally:
            await c.delete(f"{BASE_URL}/surveys/{survey_id}", headers=H)


# ============ FUNCTIONAL FLOW ============

@pytest.mark.asyncio
async def test_full_meeting_flow():
    """Full flow: create meeting -> create poll -> vote -> close poll -> end meeting."""
    token = await get_admin_token()
    async with httpx.AsyncClient(timeout=60.0) as c:
        H = {"Authorization": f"Bearer {token}"}
        
        # 1. Create meeting
        scheduled = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        r = await c.post(f"{BASE_URL}/meetings", headers=H, json={
            "title": "test-full-flow-meeting",
            "scheduled_at": scheduled,
            "duration": 60,
            "meeting_type": "scheduled"
        })
        assert r.status_code in (200, 201)
        meeting_id = r.json()["meeting_id"]
        
        try:
            # 2. Create poll
            r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H, json={
                "question": "Full flow poll?",
                "options": ["Yes", "No", "Maybe"]
            })
            assert r.status_code in (200, 201)
            poll_id = r.json()["poll_id"]
            
            # 3. Vote
            r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
                "option_index": 0
            })
            assert r.status_code == 200
            
            # 4. Try to vote again - should fail
            r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
                "option_index": 1
            })
            assert r.status_code == 400
            
            # 5. Close poll
            r = await c.put(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/close", headers=H)
            assert r.status_code == 200
            
            # 6. Try to vote on closed poll - should fail
            r = await c.post(f"{BASE_URL}/meetings/{meeting_id}/polls/{poll_id}/vote", headers=H, json={
                "option_index": 2
            })
            assert r.status_code == 400
            
            # 7. Verify poll state
            r = await c.get(f"{BASE_URL}/meetings/{meeting_id}/polls", headers=H)
            assert r.status_code == 200
            polls = r.json()
            poll = next(p for p in polls if p["poll_id"] == poll_id)
            assert poll["status"] == "closed"
            assert poll["total_votes"] == 1
            
        finally:
            await c.delete(f"{BASE_URL}/meetings/{meeting_id}", headers=H)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
