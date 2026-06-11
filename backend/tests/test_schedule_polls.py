"""
Test Schedule Polls Feature - MeetFlow Doodle-like Scheduling
Tests: Create poll, list polls, get poll, public poll access, voting, comments, suggestions, confirm, delete
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"

# Known test poll from context
KNOWN_SHARE_TOKEN = "02e6f3182db4"


class TestSchedulePollsAuth:
    """Test authentication requirements for schedule poll endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_create_poll_requires_auth(self):
        """POST /api/schedule-polls requires authentication"""
        response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": "Test Poll",
            "time_slots": [{"date": "2026-02-01", "start_time": "09:00", "end_time": "10:00"}]
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Create poll requires auth (401)")
    
    def test_list_polls_requires_auth(self):
        """GET /api/schedule-polls requires authentication"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: List polls requires auth (401)")
    
    def test_get_poll_by_id_requires_auth(self):
        """GET /api/schedule-polls/{poll_id} requires authentication"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/spoll_test123")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Get poll by ID requires auth (401)")
    
    def test_confirm_poll_requires_auth(self):
        """POST /api/schedule-polls/{poll_id}/confirm requires authentication"""
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/spoll_test123/confirm", json={"slot_id": "slot_123"})
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Confirm poll requires auth (401)")
    
    def test_delete_poll_requires_auth(self):
        """DELETE /api/schedule-polls/{poll_id} requires authentication"""
        response = self.session.delete(f"{BASE_URL}/api/schedule-polls/spoll_test123")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Delete poll requires auth (401)")


class TestSchedulePollsPublicEndpoints:
    """Test public endpoints that don't require authentication"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_get_public_poll_by_share_token(self):
        """GET /api/schedule-polls/public/{share_token} returns poll without auth"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "poll_id" in data, "Response should contain poll_id"
        assert "title" in data, "Response should contain title"
        assert "time_slots" in data, "Response should contain time_slots"
        assert "votes" in data, "Response should contain votes"
        assert "share_token" in data, "Response should contain share_token"
        assert data["share_token"] == KNOWN_SHARE_TOKEN
        print(f"PASS: Public poll access works - Title: {data['title']}, Votes: {len(data.get('votes', []))}")
    
    def test_get_public_poll_not_found(self):
        """GET /api/schedule-polls/public/{invalid_token} returns 404"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/public/invalid_token_xyz")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Invalid share token returns 404")
    
    def test_vote_on_public_poll(self):
        """POST /api/schedule-polls/public/{share_token}/vote records vote"""
        # First get the poll to get slot IDs
        poll_response = self.session.get(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}")
        assert poll_response.status_code == 200
        poll = poll_response.json()
        
        if poll.get("status") == "confirmed":
            pytest.skip("Poll is already confirmed, cannot vote")
        
        slot_ids = [s["slot_id"] for s in poll.get("time_slots", [])]
        if not slot_ids:
            pytest.skip("No time slots in poll")
        
        # Create unique voter name for this test
        voter_name = f"TEST_Voter_{uuid.uuid4().hex[:6]}"
        votes = {slot_ids[0]: "yes"}
        if len(slot_ids) > 1:
            votes[slot_ids[1]] = "maybe"
        
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}/vote", json={
            "voter_name": voter_name,
            "voter_email": f"{voter_name.lower()}@test.com",
            "votes": votes
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "vote_id" in data, "Response should contain vote_id"
        assert data.get("message") == "Vote recorded"
        print(f"PASS: Vote recorded - vote_id: {data['vote_id']}")
        
        # Verify vote was persisted
        verify_response = self.session.get(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}")
        verify_poll = verify_response.json()
        voter_found = any(v["voter_name"] == voter_name for v in verify_poll.get("votes", []))
        assert voter_found, f"Voter {voter_name} not found in poll votes"
        print(f"PASS: Vote persisted and verified for {voter_name}")
    
    def test_vote_update_overwrites_previous(self):
        """POST /api/schedule-polls/public/{share_token}/vote with same name overwrites"""
        poll_response = self.session.get(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}")
        poll = poll_response.json()
        
        if poll.get("status") == "confirmed":
            pytest.skip("Poll is already confirmed")
        
        slot_ids = [s["slot_id"] for s in poll.get("time_slots", [])]
        if not slot_ids:
            pytest.skip("No time slots")
        
        voter_name = f"TEST_UpdateVoter_{uuid.uuid4().hex[:4]}"
        
        # First vote
        self.session.post(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}/vote", json={
            "voter_name": voter_name,
            "voter_email": "",
            "votes": {slot_ids[0]: "yes"}
        })
        
        # Update vote (same name)
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}/vote", json={
            "voter_name": voter_name,
            "voter_email": "",
            "votes": {slot_ids[0]: "no"}
        })
        assert response.status_code == 200
        
        # Verify only one vote exists for this voter
        verify_response = self.session.get(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}")
        verify_poll = verify_response.json()
        voter_votes = [v for v in verify_poll.get("votes", []) if v["voter_name"].lower() == voter_name.lower()]
        assert len(voter_votes) == 1, f"Expected 1 vote for {voter_name}, found {len(voter_votes)}"
        assert voter_votes[0]["votes"].get(slot_ids[0]) == "no", "Vote should be updated to 'no'"
        print(f"PASS: Vote update overwrites previous vote for {voter_name}")
    
    def test_add_comment_to_public_poll(self):
        """POST /api/schedule-polls/public/{share_token}/comment adds comment"""
        comment_text = f"TEST_Comment_{uuid.uuid4().hex[:6]}"
        author_name = f"TEST_Author_{uuid.uuid4().hex[:4]}"
        
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}/comment", json={
            "author_name": author_name,
            "text": comment_text
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "comment_id" in data, "Response should contain comment_id"
        assert data["author_name"] == author_name
        assert data["text"] == comment_text
        print(f"PASS: Comment added - comment_id: {data['comment_id']}")
        
        # Verify comment persisted
        verify_response = self.session.get(f"{BASE_URL}/api/schedule-polls/public/{KNOWN_SHARE_TOKEN}")
        verify_poll = verify_response.json()
        comment_found = any(c["text"] == comment_text for c in verify_poll.get("comments", []))
        assert comment_found, "Comment not found in poll"
        print("PASS: Comment persisted and verified")


class TestSchedulePollsCRUD:
    """Test authenticated CRUD operations for schedule polls"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.created_poll_ids = []
    
    def teardown_method(self, method):
        """Cleanup created polls"""
        for poll_id in self.created_poll_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/schedule-polls/{poll_id}")
            except:
                pass
    
    def test_create_poll_returns_poll_id_and_share_token(self):
        """POST /api/schedule-polls creates poll and returns poll_id + share_token"""
        poll_title = f"TEST_Poll_{uuid.uuid4().hex[:6]}"
        response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": poll_title,
            "description": "Test description",
            "time_slots": [
                {"date": "2026-02-15", "start_time": "09:00", "end_time": "10:00"},
                {"date": "2026-02-16", "start_time": "14:00", "end_time": "15:00"}
            ],
            "deadline": None,
            "allow_maybe": True,
            "allow_suggestions": True,
            "is_private": False,
            "password": None,
            "create_meeting_on_confirm": True
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "poll_id" in data, "Response should contain poll_id"
        assert "share_token" in data, "Response should contain share_token"
        assert data["poll_id"].startswith("spoll_"), f"poll_id should start with 'spoll_', got {data['poll_id']}"
        assert len(data["share_token"]) == 12, f"share_token should be 12 chars, got {len(data['share_token'])}"
        
        self.created_poll_ids.append(data["poll_id"])
        print(f"PASS: Poll created - poll_id: {data['poll_id']}, share_token: {data['share_token']}")
        
        # Verify poll can be retrieved
        get_response = self.session.get(f"{BASE_URL}/api/schedule-polls/{data['poll_id']}")
        assert get_response.status_code == 200
        poll = get_response.json()
        assert poll["title"] == poll_title
        assert len(poll["time_slots"]) == 2
        print("PASS: Created poll verified via GET")
    
    def test_list_polls_with_pagination(self):
        """GET /api/schedule-polls returns paginated list"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls?page=1&limit=5")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "polls" in data, "Response should contain polls array"
        assert "total" in data, "Response should contain total count"
        assert "page" in data, "Response should contain page number"
        assert "pages" in data, "Response should contain total pages"
        assert isinstance(data["polls"], list)
        print(f"PASS: List polls - total: {data['total']}, page: {data['page']}/{data['pages']}, returned: {len(data['polls'])}")
    
    def test_list_polls_with_search(self):
        """GET /api/schedule-polls?search=... filters by title"""
        # Create a poll with unique title
        unique_title = f"TEST_SearchPoll_{uuid.uuid4().hex[:8]}"
        create_response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": unique_title,
            "time_slots": [{"date": "2026-03-01", "start_time": "10:00", "end_time": "11:00"}]
        })
        assert create_response.status_code == 200
        poll_id = create_response.json()["poll_id"]
        self.created_poll_ids.append(poll_id)
        
        # Search for it
        search_response = self.session.get(f"{BASE_URL}/api/schedule-polls?search={unique_title[:15]}")
        assert search_response.status_code == 200
        data = search_response.json()
        assert data["total"] >= 1, "Should find at least 1 poll"
        found = any(p["title"] == unique_title for p in data["polls"])
        assert found, f"Poll with title {unique_title} not found in search results"
        print(f"PASS: Search filter works - found poll with title containing '{unique_title[:15]}'")
    
    def test_get_poll_by_id(self):
        """GET /api/schedule-polls/{poll_id} returns full poll details"""
        # Create a poll first
        create_response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": f"TEST_GetPoll_{uuid.uuid4().hex[:6]}",
            "description": "Test get by ID",
            "time_slots": [{"date": "2026-04-01", "start_time": "09:00", "end_time": "10:00"}],
            "allow_maybe": True,
            "allow_suggestions": False
        })
        assert create_response.status_code == 200
        poll_id = create_response.json()["poll_id"]
        self.created_poll_ids.append(poll_id)
        
        # Get by ID
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["poll_id"] == poll_id
        assert "title" in data
        assert "description" in data
        assert "time_slots" in data
        assert "votes" in data
        assert "comments" in data
        assert "status" in data
        assert data["status"] == "open"
        print(f"PASS: Get poll by ID - {poll_id}")
    
    def test_get_poll_not_found(self):
        """GET /api/schedule-polls/{invalid_id} returns 404"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/spoll_invalid123")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Invalid poll_id returns 404")
    
    def test_delete_poll(self):
        """DELETE /api/schedule-polls/{poll_id} deletes poll"""
        # Create a poll
        create_response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": f"TEST_DeletePoll_{uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": "2026-05-01", "start_time": "09:00", "end_time": "10:00"}]
        })
        assert create_response.status_code == 200
        poll_id = create_response.json()["poll_id"]
        
        # Delete it
        delete_response = self.session.delete(f"{BASE_URL}/api/schedule-polls/{poll_id}")
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}"
        data = delete_response.json()
        assert data.get("message") == "Poll deleted"
        print(f"PASS: Poll deleted - {poll_id}")
        
        # Verify it's gone
        get_response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_id}")
        assert get_response.status_code == 404, "Deleted poll should return 404"
        print("PASS: Deleted poll verified as 404")


class TestSchedulePollsConfirm:
    """Test poll confirmation and meeting creation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        self.created_poll_ids = []
    
    def teardown_method(self, method):
        for poll_id in self.created_poll_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/schedule-polls/{poll_id}")
            except:
                pass
    
    def test_confirm_poll_creates_meeting(self):
        """POST /api/schedule-polls/{poll_id}/confirm confirms slot and creates meeting"""
        # Create poll with create_meeting_on_confirm=True
        create_response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": f"TEST_ConfirmPoll_{uuid.uuid4().hex[:6]}",
            "time_slots": [
                {"date": "2026-06-15", "start_time": "10:00", "end_time": "11:00"},
                {"date": "2026-06-16", "start_time": "14:00", "end_time": "15:00"}
            ],
            "create_meeting_on_confirm": True
        })
        assert create_response.status_code == 200
        poll_id = create_response.json()["poll_id"]
        self.created_poll_ids.append(poll_id)
        
        # Get poll to get slot_id
        poll_response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_id}")
        poll = poll_response.json()
        slot_id = poll["time_slots"][0]["slot_id"]
        
        # Add a vote first (optional but realistic)
        pub_session = requests.Session()
        pub_session.post(f"{BASE_URL}/api/schedule-polls/public/{poll['share_token']}/vote", json={
            "voter_name": "TEST_ConfirmVoter",
            "voter_email": "",
            "votes": {slot_id: "yes"}
        })
        
        # Confirm the slot
        confirm_response = self.session.post(f"{BASE_URL}/api/schedule-polls/{poll_id}/confirm", json={
            "slot_id": slot_id
        })
        assert confirm_response.status_code == 200, f"Expected 200, got {confirm_response.status_code}: {confirm_response.text}"
        data = confirm_response.json()
        assert data.get("message") == "Poll confirmed"
        assert "slot" in data
        assert "meeting_id" in data, "Should create meeting when create_meeting_on_confirm=True"
        assert "meeting_code" in data
        assert data["meeting_id"].startswith("meet_")
        print(f"PASS: Poll confirmed - meeting_id: {data['meeting_id']}, meeting_code: {data['meeting_code']}")
        
        # Verify poll status changed
        verify_response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_id}")
        verify_poll = verify_response.json()
        assert verify_poll["status"] == "confirmed"
        assert verify_poll["confirmed_slot_id"] == slot_id
        print("PASS: Poll status updated to 'confirmed'")
    
    def test_confirm_invalid_slot_returns_400(self):
        """POST /api/schedule-polls/{poll_id}/confirm with invalid slot_id returns 400"""
        create_response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": f"TEST_InvalidSlot_{uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": "2026-07-01", "start_time": "09:00", "end_time": "10:00"}]
        })
        poll_id = create_response.json()["poll_id"]
        self.created_poll_ids.append(poll_id)
        
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/{poll_id}/confirm", json={
            "slot_id": "slot_invalid123"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Invalid slot_id returns 400")


class TestSchedulePollsSuggestions:
    """Test time slot suggestion feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        self.created_poll_ids = []
    
    def teardown_method(self, method):
        for poll_id in self.created_poll_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/schedule-polls/{poll_id}")
            except:
                pass
    
    def test_suggest_time_slot_when_allowed(self):
        """POST /api/schedule-polls/public/{share_token}/suggest adds new slot"""
        # Create poll with allow_suggestions=True
        create_response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": f"TEST_SuggestPoll_{uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": "2026-08-01", "start_time": "09:00", "end_time": "10:00"}],
            "allow_suggestions": True
        })
        assert create_response.status_code == 200
        poll_data = create_response.json()
        poll_id = poll_data["poll_id"]
        share_token = poll_data["share_token"]
        self.created_poll_ids.append(poll_id)
        
        # Suggest a new slot (public endpoint)
        pub_session = requests.Session()
        pub_session.headers.update({"Content-Type": "application/json"})
        response = pub_session.post(f"{BASE_URL}/api/schedule-polls/public/{share_token}/suggest", json={
            "date": "2026-08-05",
            "start_time": "15:00",
            "end_time": "16:00",
            "name": "TEST_Suggester"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "slot_id" in data
        assert data["date"] == "2026-08-05"
        assert data["suggested_by"] == "TEST_Suggester"
        print(f"PASS: Time slot suggested - slot_id: {data['slot_id']}")
        
        # Verify slot added to poll
        verify_response = pub_session.get(f"{BASE_URL}/api/schedule-polls/public/{share_token}")
        verify_poll = verify_response.json()
        assert len(verify_poll["time_slots"]) == 2, "Should have 2 slots now"
        suggested_slot = next((s for s in verify_poll["time_slots"] if s.get("suggested_by") == "TEST_Suggester"), None)
        assert suggested_slot is not None, "Suggested slot not found"
        print("PASS: Suggested slot verified in poll")
    
    def test_suggest_time_slot_when_not_allowed(self):
        """POST /api/schedule-polls/public/{share_token}/suggest returns 400 when not allowed"""
        # Create poll with allow_suggestions=False
        create_response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": f"TEST_NoSuggestPoll_{uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": "2026-09-01", "start_time": "09:00", "end_time": "10:00"}],
            "allow_suggestions": False
        })
        poll_data = create_response.json()
        poll_id = poll_data["poll_id"]
        share_token = poll_data["share_token"]
        self.created_poll_ids.append(poll_id)
        
        pub_session = requests.Session()
        pub_session.headers.update({"Content-Type": "application/json"})
        response = pub_session.post(f"{BASE_URL}/api/schedule-polls/public/{share_token}/suggest", json={
            "date": "2026-09-05",
            "start_time": "15:00",
            "end_time": "16:00"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Suggestion rejected when not allowed (400)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
