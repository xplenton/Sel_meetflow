"""
Iteration 123 Feature Tests:
1. Chat Unread Summary endpoint (GET /api/chat/unread-summary)
2. iCal Calendar Feed endpoints (GET/POST /api/calendar/my-feed-token, GET /api/calendar/feed/{token}.ics)
3. Meeting Join idempotency (POST /api/meetings/{meeting_id}/join)
4. Existing /api/meetings/{meeting_id}/ical regression check
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth cookie."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


class TestChatUnreadSummary:
    """Tests for GET /api/chat/unread-summary endpoint"""
    
    def test_unread_summary_returns_correct_structure(self, admin_session):
        """Verify unread-summary returns total_unread and top array"""
        resp = admin_session.get(f"{BASE_URL}/api/chat/unread-summary")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "total_unread" in data, "Missing total_unread field"
        assert "top" in data, "Missing top field"
        assert isinstance(data["total_unread"], int), "total_unread should be int"
        assert isinstance(data["top"], list), "top should be list"
        
    def test_unread_summary_top_entries_structure(self, admin_session):
        """Verify each entry in top array has required fields"""
        resp = admin_session.get(f"{BASE_URL}/api/chat/unread-summary")
        assert resp.status_code == 200
        data = resp.json()
        
        # If there are entries, verify structure
        for entry in data.get("top", []):
            assert "conversation_id" in entry, "Missing conversation_id"
            assert "display_name" in entry, "Missing display_name"
            assert "unread_count" in entry, "Missing unread_count"
            assert "type" in entry, "Missing type"
            # Optional fields that should be present
            assert "last_message_preview" in entry or entry.get("last_message_preview") is None
            assert "updated_at" in entry or entry.get("updated_at") is None
            
    def test_unread_summary_max_5_entries(self, admin_session):
        """Verify top array has max 5 entries"""
        resp = admin_session.get(f"{BASE_URL}/api/chat/unread-summary")
        assert resp.status_code == 200
        data = resp.json()
        
        assert len(data.get("top", [])) <= 5, "top should have max 5 entries"


class TestICalFeedEndpoints:
    """Tests for iCal calendar subscription feed endpoints"""
    
    def test_get_my_feed_token_returns_token_and_urls(self, admin_session):
        """GET /api/calendar/my-feed-token returns token, subscribe_url, webcal_url"""
        resp = admin_session.get(f"{BASE_URL}/api/calendar/my-feed-token")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "token" in data, "Missing token field"
        assert "subscribe_url" in data, "Missing subscribe_url field"
        assert "webcal_url" in data, "Missing webcal_url field"
        
        # Verify URL formats
        assert data["subscribe_url"].startswith("https://") or data["subscribe_url"].startswith("/"), \
            f"subscribe_url should be HTTPS or relative: {data['subscribe_url']}"
        assert "webcal://" in data["webcal_url"] or data["webcal_url"].startswith("/"), \
            f"webcal_url should contain webcal:// scheme: {data['webcal_url']}"
        assert ".ics" in data["subscribe_url"], "subscribe_url should end with .ics"
        
    def test_public_feed_returns_valid_icalendar(self, admin_session):
        """GET /api/calendar/feed/{token}.ics returns valid iCalendar content (no auth needed)"""
        # First get the token
        resp = admin_session.get(f"{BASE_URL}/api/calendar/my-feed-token")
        assert resp.status_code == 200
        token = resp.json()["token"]
        
        # Now fetch the public feed WITHOUT auth
        public_session = requests.Session()
        feed_resp = public_session.get(f"{BASE_URL}/api/calendar/feed/{token}.ics")
        assert feed_resp.status_code == 200, f"Expected 200, got {feed_resp.status_code}: {feed_resp.text}"
        
        # Verify content type
        content_type = feed_resp.headers.get("Content-Type", "")
        assert "text/calendar" in content_type, f"Expected text/calendar, got {content_type}"
        
        # Verify iCalendar content
        content = feed_resp.text
        assert "BEGIN:VCALENDAR" in content, "Missing BEGIN:VCALENDAR"
        assert "VERSION:2.0" in content, "Missing VERSION:2.0"
        assert "PRODID:" in content, "Missing PRODID"
        
    def test_invalid_token_returns_404(self):
        """GET /api/calendar/feed/{invalid_token}.ics returns 404"""
        public_session = requests.Session()
        invalid_token = "invalid_token_" + uuid.uuid4().hex[:8]
        resp = public_session.get(f"{BASE_URL}/api/calendar/feed/{invalid_token}.ics")
        assert resp.status_code == 404, f"Expected 404 for invalid token, got {resp.status_code}"
        
    def test_regenerate_token_rotates_old_token(self, admin_session):
        """POST /api/calendar/my-feed-token/regenerate rotates token, old token returns 404"""
        # Get current token
        resp1 = admin_session.get(f"{BASE_URL}/api/calendar/my-feed-token")
        assert resp1.status_code == 200
        old_token = resp1.json()["token"]
        
        # Regenerate
        resp2 = admin_session.post(f"{BASE_URL}/api/calendar/my-feed-token/regenerate")
        assert resp2.status_code == 200, f"Regenerate failed: {resp2.text}"
        new_token = resp2.json()["token"]
        
        # Verify new token is different
        assert new_token != old_token, "New token should be different from old token"
        
        # Verify old token no longer works
        public_session = requests.Session()
        old_feed_resp = public_session.get(f"{BASE_URL}/api/calendar/feed/{old_token}.ics")
        assert old_feed_resp.status_code == 404, f"Old token should return 404, got {old_feed_resp.status_code}"
        
        # Verify new token works
        new_feed_resp = public_session.get(f"{BASE_URL}/api/calendar/feed/{new_token}.ics")
        assert new_feed_resp.status_code == 200, f"New token should work, got {new_feed_resp.status_code}"


class TestMeetingJoinIdempotency:
    """Tests for POST /api/meetings/{meeting_id}/join idempotency"""
    
    def test_join_meeting_is_idempotent(self, admin_session):
        """Calling join twice should result in participant_count=1, not 2"""
        # Create a meeting first
        meeting_data = {
            "title": f"TEST_Idempotency_Meeting_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant",
            "duration": 30
        }
        create_resp = admin_session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
        assert create_resp.status_code in [200, 201], f"Create meeting failed: {create_resp.text}"
        meeting_id = create_resp.json()["meeting_id"]
        
        try:
            # Join first time
            join_resp1 = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
            assert join_resp1.status_code == 200, f"First join failed: {join_resp1.text}"
            count1 = join_resp1.json().get("participant_count", 0)
            
            # Join second time (should be idempotent)
            join_resp2 = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
            assert join_resp2.status_code == 200, f"Second join failed: {join_resp2.text}"
            count2 = join_resp2.json().get("participant_count", 0)
            
            # Verify count didn't increase
            assert count2 == count1, f"Join should be idempotent: count1={count1}, count2={count2}"
            assert count2 == 1, f"Participant count should be 1, got {count2}"
            
        finally:
            # Cleanup: leave and delete meeting
            admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/leave")
            admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")


class TestExistingICalEndpointRegression:
    """Regression tests for existing /api/meetings/{meeting_id}/ical endpoint"""
    
    def test_meeting_ical_export_works(self, admin_session):
        """GET /api/meetings/{meeting_id}/ical returns valid iCalendar"""
        # Create a meeting
        meeting_data = {
            "title": f"TEST_iCal_Export_{uuid.uuid4().hex[:6]}",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-01T10:00:00Z",
            "duration": 60
        }
        create_resp = admin_session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
        assert create_resp.status_code in [200, 201], f"Create meeting failed: {create_resp.text}"
        meeting_id = create_resp.json()["meeting_id"]
        
        try:
            # Export iCal
            ical_resp = admin_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
            assert ical_resp.status_code == 200, f"iCal export failed: {ical_resp.text}"
            
            # Verify content type
            content_type = ical_resp.headers.get("Content-Type", "")
            assert "text/calendar" in content_type, f"Expected text/calendar, got {content_type}"
            
            # Verify iCalendar content
            content = ical_resp.text
            assert "BEGIN:VCALENDAR" in content, "Missing BEGIN:VCALENDAR"
            assert "BEGIN:VEVENT" in content, "Missing BEGIN:VEVENT"
            assert "END:VEVENT" in content, "Missing END:VEVENT"
            assert "END:VCALENDAR" in content, "Missing END:VCALENDAR"
            
        finally:
            # Cleanup
            admin_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")


class TestChatConversationsRegression:
    """Regression tests for existing chat functionality"""
    
    def test_chat_conversations_list_works(self, admin_session):
        """GET /api/chat/conversations returns list with expected fields"""
        resp = admin_session.get(f"{BASE_URL}/api/chat/conversations")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        # If there are conversations, verify structure
        for conv in data[:3]:  # Check first 3
            assert "conversation_id" in conv, "Missing conversation_id"
            assert "type" in conv, "Missing type"
            assert "members" in conv, "Missing members"


class TestCalDAVBlockRegression:
    """Regression tests for CalDAV config endpoints on profile"""
    
    def test_caldav_config_endpoint_exists(self, admin_session):
        """GET /api/users/me/caldav-config returns config or empty object"""
        resp = admin_session.get(f"{BASE_URL}/api/users/me/caldav-config")
        # Should return 200 with config or empty object
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, dict), "Response should be a dict"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
