"""
Phase 3 Testing: General Polls, CSV/PDF Export, AI Suggestions, Timezone Support
Tests for MeetFlow Phase 3 features:
- General polls (non-time based) with single/multiple/priority voting
- CSV/PDF export for schedule polls
- AI scheduling suggestions via GPT-5.2
- Timezone endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestTimezones:
    """Timezone endpoint tests - no auth required"""
    
    def test_get_timezones(self):
        """GET /api/timezones returns list of common timezones"""
        response = requests.get(f"{BASE_URL}/api/timezones")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "timezones" in data
        assert isinstance(data["timezones"], list)
        assert len(data["timezones"]) > 0
        # Check for common timezones
        assert "Europe/Berlin" in data["timezones"]
        assert "US/Eastern" in data["timezones"]
        assert "UTC" in data["timezones"]
        print(f"✓ Timezones endpoint returns {len(data['timezones'])} timezones")


class TestGeneralPollsAuth:
    """General poll tests requiring authentication"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed - skipping authenticated tests")
        self.user = login_resp.json()
        print(f"✓ Logged in as {self.user.get('email')}")
    
    def test_create_general_poll_single(self):
        """POST /api/general-polls creates single-choice poll"""
        response = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Single Choice Poll",
            "description": "Test single choice poll",
            "poll_type": "single",
            "options": ["Option A", "Option B", "Option C"],
            "allow_custom_options": False,
            "is_anonymous": False
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "poll_id" in data
        assert "share_token" in data
        assert data["poll_id"].startswith("gpoll_")
        print(f"✓ Created single-choice poll: {data['poll_id']}")
        # Store for cleanup
        self.created_poll_id = data["poll_id"]
        self.created_share_token = data["share_token"]
        return data
    
    def test_create_general_poll_multiple(self):
        """POST /api/general-polls creates multiple-choice poll"""
        response = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Multiple Choice Poll",
            "description": "Test multiple choice poll",
            "poll_type": "multiple",
            "options": ["Red", "Blue", "Green", "Yellow"],
            "allow_custom_options": True,
            "is_anonymous": False
        })
        assert response.status_code == 200
        data = response.json()
        assert "poll_id" in data
        print(f"✓ Created multiple-choice poll: {data['poll_id']}")
        return data
    
    def test_create_general_poll_priority(self):
        """POST /api/general-polls creates priority poll"""
        response = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Priority Poll",
            "description": "Test priority ranking poll",
            "poll_type": "priority",
            "options": ["First", "Second", "Third"],
            "allow_custom_options": False,
            "is_anonymous": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "poll_id" in data
        print(f"✓ Created priority poll: {data['poll_id']}")
        return data
    
    def test_list_general_polls(self):
        """GET /api/general-polls lists polls with pagination"""
        response = self.session.get(f"{BASE_URL}/api/general-polls?page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "polls" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert isinstance(data["polls"], list)
        print(f"✓ Listed {len(data['polls'])} general polls (total: {data['total']})")
    
    def test_close_general_poll(self):
        """POST /api/general-polls/{poll_id}/close closes poll"""
        # First create a poll
        create_resp = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Poll to Close",
            "poll_type": "single",
            "options": ["Yes", "No"]
        })
        assert create_resp.status_code == 200
        poll_id = create_resp.json()["poll_id"]
        
        # Close it
        close_resp = self.session.post(f"{BASE_URL}/api/general-polls/{poll_id}/close")
        assert close_resp.status_code == 200
        data = close_resp.json()
        assert data.get("message") == "Poll closed"
        print(f"✓ Closed poll: {poll_id}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/general-polls/{poll_id}")
    
    def test_delete_general_poll(self):
        """DELETE /api/general-polls/{poll_id} deletes poll"""
        # First create a poll
        create_resp = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Poll to Delete",
            "poll_type": "single",
            "options": ["A", "B"]
        })
        assert create_resp.status_code == 200
        poll_id = create_resp.json()["poll_id"]
        
        # Delete it
        delete_resp = self.session.delete(f"{BASE_URL}/api/general-polls/{poll_id}")
        assert delete_resp.status_code == 200
        data = delete_resp.json()
        assert data.get("message") == "Poll deleted"
        print(f"✓ Deleted poll: {poll_id}")


class TestGeneralPollsPublic:
    """Public general poll endpoints - no auth required"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Create a poll for testing public endpoints"""
        self.session = requests.Session()
        # Login to create poll
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed")
        
        # Create test poll with custom options allowed
        create_resp = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Public Poll",
            "description": "Test public voting",
            "poll_type": "single",
            "options": ["Pizza", "Burger", "Sushi"],
            "allow_custom_options": True,
            "is_anonymous": False
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create test poll")
        
        data = create_resp.json()
        self.poll_id = data["poll_id"]
        self.share_token = data["share_token"]
        print(f"✓ Created test poll: {self.poll_id} (token: {self.share_token})")
        
        yield
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/general-polls/{self.poll_id}")
    
    def test_get_public_poll(self):
        """GET /api/general-polls/public/{share_token} returns poll without auth"""
        # Use a fresh session without auth
        response = requests.get(f"{BASE_URL}/api/general-polls/public/{self.share_token}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Public Poll"
        assert data["poll_type"] == "single"
        assert "options" in data
        assert "Pizza" in data["options"]
        print(f"✓ Public poll accessible: {data['title']}")
    
    def test_vote_on_public_poll(self):
        """POST /api/general-polls/public/{share_token}/vote records vote"""
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/vote", json={
            "voter_name": "TEST_Voter1",
            "voter_email": "voter1@test.com",
            "selected": ["Pizza"]
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("message") == "Vote recorded"
        assert "vote_id" in data
        print(f"✓ Vote recorded: {data['vote_id']}")
    
    def test_vote_updates_existing(self):
        """Voting again with same name updates existing vote"""
        # First vote
        requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/vote", json={
            "voter_name": "TEST_UpdateVoter",
            "selected": ["Pizza"]
        })
        
        # Second vote with same name
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/vote", json={
            "voter_name": "TEST_UpdateVoter",
            "selected": ["Burger"]
        })
        assert response.status_code == 200
        
        # Verify only one vote exists for this voter
        poll_resp = requests.get(f"{BASE_URL}/api/general-polls/public/{self.share_token}")
        poll = poll_resp.json()
        voter_votes = [v for v in poll.get("votes", []) if v["voter_name"] == "TEST_UpdateVoter"]
        assert len(voter_votes) == 1
        assert "Burger" in voter_votes[0]["selected"]
        print("✓ Vote update works correctly")
    
    def test_add_comment(self):
        """POST /api/general-polls/public/{share_token}/comment adds comment"""
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/comment", json={
            "author_name": "TEST_Commenter",
            "text": "This is a test comment"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "comment_id" in data
        assert data["author_name"] == "TEST_Commenter"
        assert data["text"] == "This is a test comment"
        print(f"✓ Comment added: {data['comment_id']}")
    
    def test_add_custom_option(self):
        """POST /api/general-polls/public/{share_token}/add-option adds custom option"""
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/add-option", json={
            "option": "Tacos"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("message") == "Option added"
        assert data.get("option") == "Tacos"
        
        # Verify option was added
        poll_resp = requests.get(f"{BASE_URL}/api/general-polls/public/{self.share_token}")
        poll = poll_resp.json()
        assert "Tacos" in poll["options"]
        print("✓ Custom option added successfully")
    
    def test_add_duplicate_option_fails(self):
        """Adding duplicate option returns error"""
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/add-option", json={
            "option": "Pizza"  # Already exists
        })
        assert response.status_code == 400
        print("✓ Duplicate option correctly rejected")
    
    def test_invalid_share_token(self):
        """Invalid share token returns 404"""
        response = requests.get(f"{BASE_URL}/api/general-polls/public/invalid_token_123")
        assert response.status_code == 404
        print("✓ Invalid token returns 404")


class TestExistingGeneralPoll:
    """Test with existing general poll (share_token=4a56cddbf0f0)"""
    
    def test_existing_poll_accessible(self):
        """Known test poll is accessible"""
        response = requests.get(f"{BASE_URL}/api/general-polls/public/4a56cddbf0f0")
        if response.status_code == 404:
            pytest.skip("Test poll 4a56cddbf0f0 not found - may have been deleted")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Existing poll found: {data.get('title')} with {len(data.get('votes', []))} votes")


class TestSchedulePollExport:
    """CSV/PDF export tests for schedule polls"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login for authenticated endpoints"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed")
    
    def test_export_csv(self):
        """GET /api/schedule-polls/{poll_id}/export/csv returns CSV"""
        # First get a schedule poll
        polls_resp = self.session.get(f"{BASE_URL}/api/schedule-polls?page=1&limit=1")
        if polls_resp.status_code != 200:
            pytest.skip("Could not list schedule polls")
        
        polls = polls_resp.json().get("polls", [])
        if not polls:
            pytest.skip("No schedule polls available for export test")
        
        poll_id = polls[0]["poll_id"]
        
        # Export CSV
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_id}/export/csv")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", "")
        assert "attachment" in response.headers.get("Content-Disposition", "")
        
        # Verify CSV content
        content = response.text
        assert "Teilnehmer" in content  # Header
        assert "Score" in content  # Score row
        print(f"✓ CSV export successful for poll {poll_id}")
    
    def test_export_pdf(self):
        """GET /api/schedule-polls/{poll_id}/export/pdf returns PDF"""
        # First get a schedule poll
        polls_resp = self.session.get(f"{BASE_URL}/api/schedule-polls?page=1&limit=1")
        if polls_resp.status_code != 200:
            pytest.skip("Could not list schedule polls")
        
        polls = polls_resp.json().get("polls", [])
        if not polls:
            pytest.skip("No schedule polls available for export test")
        
        poll_id = polls[0]["poll_id"]
        
        # Export PDF
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_id}/export/pdf")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert "application/pdf" in response.headers.get("Content-Type", "")
        assert "attachment" in response.headers.get("Content-Disposition", "")
        
        # Verify PDF content (starts with %PDF)
        assert response.content[:4] == b'%PDF'
        print(f"✓ PDF export successful for poll {poll_id}")
    
    def test_export_nonexistent_poll(self):
        """Export of non-existent poll returns 404"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/nonexistent_poll/export/csv")
        assert response.status_code == 404
        print("✓ Non-existent poll export returns 404")


class TestAISuggestion:
    """AI scheduling suggestion tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login for authenticated endpoints"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed")
    
    def test_ai_suggestion_with_votes(self):
        """POST /api/schedule-polls/{poll_id}/ai-suggest returns AI analysis"""
        # Find a poll with votes
        polls_resp = self.session.get(f"{BASE_URL}/api/schedule-polls?page=1&limit=20")
        if polls_resp.status_code != 200:
            pytest.skip("Could not list schedule polls")
        
        polls = polls_resp.json().get("polls", [])
        poll_with_votes = None
        for poll in polls:
            if len(poll.get("votes", [])) >= 1:
                poll_with_votes = poll
                break
        
        if not poll_with_votes:
            pytest.skip("No schedule poll with votes found for AI test")
        
        poll_id = poll_with_votes["poll_id"]
        print(f"Testing AI suggestion on poll {poll_id} with {len(poll_with_votes['votes'])} votes")
        
        # Request AI suggestion
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/{poll_id}/ai-suggest")
        
        # AI might fail if no LLM key configured
        if response.status_code == 400 and "LLM key" in response.text:
            pytest.skip("No LLM key configured")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "suggestion" in data
        assert "total_voters" in data
        assert "slots_analyzed" in data
        assert len(data["suggestion"]) > 0
        print(f"✓ AI suggestion received ({len(data['suggestion'])} chars)")
    
    def test_ai_suggestion_no_votes_fails(self):
        """AI suggestion fails if poll has no votes"""
        # Create a new poll without votes
        create_resp = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": "TEST_AI No Votes Poll",
            "time_slots": [
                {"date": "2026-02-01", "start_time": "10:00", "end_time": "11:00"}
            ]
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create test poll")
        
        poll_id = create_resp.json()["poll_id"]
        
        # Try AI suggestion
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/{poll_id}/ai-suggest")
        assert response.status_code == 400
        assert "vote" in response.text.lower()
        print("✓ AI suggestion correctly requires votes")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/schedule-polls/{poll_id}")


class TestPriorityVoting:
    """Test priority voting for general polls"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Create priority poll for testing"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed")
        
        # Create priority poll
        create_resp = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Priority Ranking",
            "poll_type": "priority",
            "options": ["First", "Second", "Third", "Fourth"]
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create priority poll")
        
        data = create_resp.json()
        self.poll_id = data["poll_id"]
        self.share_token = data["share_token"]
        
        yield
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/general-polls/{self.poll_id}")
    
    def test_priority_vote(self):
        """Priority vote with priority_order field"""
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/vote", json={
            "voter_name": "TEST_PriorityVoter",
            "selected": ["Third", "First", "Fourth", "Second"],
            "priority_order": ["Third", "First", "Fourth", "Second"]
        })
        assert response.status_code == 200
        
        # Verify vote was recorded with priority order
        poll_resp = requests.get(f"{BASE_URL}/api/general-polls/public/{self.share_token}")
        poll = poll_resp.json()
        voter = next((v for v in poll.get("votes", []) if v["voter_name"] == "TEST_PriorityVoter"), None)
        assert voter is not None
        assert voter.get("priority_order") == ["Third", "First", "Fourth", "Second"]
        print("✓ Priority vote recorded correctly")


class TestVotingOnClosedPoll:
    """Test that voting on closed poll fails"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Create and close a poll"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Login failed")
        
        # Create poll
        create_resp = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Closed Poll",
            "poll_type": "single",
            "options": ["A", "B"]
        })
        if create_resp.status_code != 200:
            pytest.skip("Could not create poll")
        
        data = create_resp.json()
        self.poll_id = data["poll_id"]
        self.share_token = data["share_token"]
        
        # Close it
        self.session.post(f"{BASE_URL}/api/general-polls/{self.poll_id}/close")
        
        yield
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/general-polls/{self.poll_id}")
    
    def test_vote_on_closed_poll_fails(self):
        """Voting on closed poll returns 400"""
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{self.share_token}/vote", json={
            "voter_name": "TEST_LateVoter",
            "selected": ["A"]
        })
        assert response.status_code == 400
        assert "closed" in response.text.lower()
        print("✓ Voting on closed poll correctly rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
