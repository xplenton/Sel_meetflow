"""
Test suite for MeetFlow Iteration 10 features:
- Server-side pagination for GET /api/meetings
- Server-side pagination for GET /api/recordings  
- Server-side pagination for GET /api/transcripts
- Search filtering for meetings, recordings, transcripts
- Meeting type filtering (upcoming/past)
- Admin email config CRUD (GET/PUT /api/admin/email-config)
- Admin email test endpoint (POST /api/admin/email-config/test)
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')

class TestPaginationAndEmailConfig:
    """Tests for pagination, search, and email config features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as admin and get session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        yield
    
    # ============ MEETINGS PAGINATION TESTS ============
    
    def test_meetings_returns_paginated_response(self):
        """GET /api/meetings returns {meetings, total, page, pages} structure"""
        resp = self.session.get(f"{BASE_URL}/api/meetings")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify response structure
        assert "meetings" in data, "Response should have 'meetings' key"
        assert "total" in data, "Response should have 'total' key"
        assert "page" in data, "Response should have 'page' key"
        assert "pages" in data, "Response should have 'pages' key"
        assert isinstance(data["meetings"], list), "meetings should be a list"
        assert isinstance(data["total"], int), "total should be an integer"
        assert isinstance(data["page"], int), "page should be an integer"
        assert isinstance(data["pages"], int), "pages should be an integer"
        print(f"✓ Meetings pagination structure correct: total={data['total']}, pages={data['pages']}")
    
    def test_meetings_pagination_limit(self):
        """GET /api/meetings?page=1&limit=3 returns max 3 meetings"""
        resp = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=3")
        assert resp.status_code == 200
        data = resp.json()
        
        assert len(data["meetings"]) <= 3, f"Expected max 3 meetings, got {len(data['meetings'])}"
        assert data["page"] == 1, "Page should be 1"
        if data["total"] > 3:
            assert data["pages"] > 1, "Should have multiple pages when total > limit"
        print(f"✓ Pagination limit works: returned {len(data['meetings'])} meetings, total={data['total']}")
    
    def test_meetings_pagination_page_navigation(self):
        """GET /api/meetings with different pages returns different results"""
        # Get page 1
        resp1 = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=5")
        assert resp1.status_code == 200
        data1 = resp1.json()
        
        if data1["pages"] > 1:
            # Get page 2
            resp2 = self.session.get(f"{BASE_URL}/api/meetings?page=2&limit=5")
            assert resp2.status_code == 200
            data2 = resp2.json()
            
            # Verify different meetings on different pages
            ids1 = {m["meeting_id"] for m in data1["meetings"]}
            ids2 = {m["meeting_id"] for m in data2["meetings"]}
            assert ids1.isdisjoint(ids2), "Page 1 and Page 2 should have different meetings"
            print(f"✓ Page navigation works: page 1 has {len(ids1)} meetings, page 2 has {len(ids2)} meetings")
        else:
            print(f"✓ Only 1 page of meetings (total={data1['total']}), skipping page navigation test")
    
    def test_meetings_search_filter(self):
        """GET /api/meetings?search=Team filters meetings by title"""
        # First create a meeting with specific title
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_SearchableTeamMeeting",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.utcnow() + timedelta(days=1)).isoformat()
        })
        assert create_resp.status_code == 200
        created = create_resp.json()
        meeting_id = created["meeting_id"]
        
        try:
            # Search for it
            resp = self.session.get(f"{BASE_URL}/api/meetings?search=SearchableTeam")
            assert resp.status_code == 200
            data = resp.json()
            
            # Verify search results contain our meeting
            found = any(m["meeting_id"] == meeting_id for m in data["meetings"])
            assert found, "Search should find the created meeting"
            
            # Verify all results match search term
            for m in data["meetings"]:
                assert "searchableteam" in m["title"].lower(), f"Meeting '{m['title']}' doesn't match search"
            print(f"✓ Search filter works: found {len(data['meetings'])} meetings matching 'SearchableTeam'")
        finally:
            # Cleanup
            self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
    
    def test_meetings_type_upcoming(self):
        """GET /api/meetings?meeting_type=upcoming returns only scheduled/active meetings"""
        resp = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=upcoming")
        assert resp.status_code == 200
        data = resp.json()
        
        for m in data["meetings"]:
            assert m["status"] in ["scheduled", "active"], f"Upcoming should not include status={m['status']}"
        print(f"✓ meeting_type=upcoming filter works: {len(data['meetings'])} upcoming meetings")
    
    def test_meetings_type_past(self):
        """GET /api/meetings?meeting_type=past returns only ended meetings"""
        resp = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=past")
        assert resp.status_code == 200
        data = resp.json()
        
        # Past meetings include ended OR scheduled meetings with past scheduled_at
        for m in data["meetings"]:
            is_ended = m["status"] == "ended"
            is_past_scheduled = m["status"] == "scheduled" and m.get("scheduled_at") and m["scheduled_at"] < datetime.utcnow().isoformat()
            assert is_ended or is_past_scheduled, f"Past should not include future scheduled meeting: {m['title']}"
        print(f"✓ meeting_type=past filter works: {len(data['meetings'])} past meetings")
    
    # ============ RECORDINGS PAGINATION TESTS ============
    
    def test_recordings_returns_paginated_response(self):
        """GET /api/recordings returns {recordings, total, page, pages} structure"""
        resp = self.session.get(f"{BASE_URL}/api/recordings")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "recordings" in data, "Response should have 'recordings' key"
        assert "total" in data, "Response should have 'total' key"
        assert "page" in data, "Response should have 'page' key"
        assert "pages" in data, "Response should have 'pages' key"
        assert isinstance(data["recordings"], list), "recordings should be a list"
        print(f"✓ Recordings pagination structure correct: total={data['total']}, pages={data['pages']}")
    
    def test_recordings_pagination_limit(self):
        """GET /api/recordings?page=1&limit=5 respects limit"""
        resp = self.session.get(f"{BASE_URL}/api/recordings?page=1&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        
        assert len(data["recordings"]) <= 5, f"Expected max 5 recordings, got {len(data['recordings'])}"
        print(f"✓ Recordings pagination limit works: returned {len(data['recordings'])} recordings")
    
    # ============ TRANSCRIPTS PAGINATION TESTS ============
    
    def test_transcripts_returns_paginated_response(self):
        """GET /api/transcripts returns {transcripts, total, page, pages} structure"""
        resp = self.session.get(f"{BASE_URL}/api/transcripts")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "transcripts" in data, "Response should have 'transcripts' key"
        assert "total" in data, "Response should have 'total' key"
        assert "page" in data, "Response should have 'page' key"
        assert "pages" in data, "Response should have 'pages' key"
        assert isinstance(data["transcripts"], list), "transcripts should be a list"
        print(f"✓ Transcripts pagination structure correct: total={data['total']}, pages={data['pages']}")
    
    def test_transcripts_pagination_limit(self):
        """GET /api/transcripts?page=1&limit=5 respects limit"""
        resp = self.session.get(f"{BASE_URL}/api/transcripts?page=1&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        
        assert len(data["transcripts"]) <= 5, f"Expected max 5 transcripts, got {len(data['transcripts'])}"
        print(f"✓ Transcripts pagination limit works: returned {len(data['transcripts'])} transcripts")
    
    # ============ EMAIL CONFIG TESTS ============
    
    def test_email_config_get(self):
        """GET /api/admin/email-config returns config with masked API key"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify structure
        assert "provider" in data, "Response should have 'provider' key"
        assert "api_key" in data, "Response should have 'api_key' key"
        assert "sender_email" in data, "Response should have 'sender_email' key"
        assert "enabled" in data, "Response should have 'enabled' key"
        
        # API key should be masked (starts with ***)
        if data["api_key"]:
            assert data["api_key"].startswith("***"), "API key should be masked"
        print(f"✓ Email config GET works: provider={data['provider']}, enabled={data['enabled']}")
    
    def test_email_config_update(self):
        """PUT /api/admin/email-config saves provider/api_key/sender_email/enabled"""
        # Get current config
        get_resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        original = get_resp.json()
        
        # Update config
        update_resp = self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "provider": "resend",
            "api_key": "re_test_key_12345",
            "sender_email": "test@meetflow.app",
            "enabled": True
        })
        assert update_resp.status_code == 200
        
        # Verify update
        verify_resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        updated = verify_resp.json()
        
        assert updated["provider"] == "resend", "Provider should be updated"
        assert updated["sender_email"] == "test@meetflow.app", "Sender email should be updated"
        assert updated["enabled"] == True, "Enabled should be updated"
        assert updated["api_key"].startswith("***"), "API key should be masked"
        print(f"✓ Email config PUT works: provider={updated['provider']}, enabled={updated['enabled']}")
        
        # Restore original config
        restore_data = {
            "provider": original.get("provider", "none"),
            "sender_email": original.get("sender_email", "noreply@meetflow.app"),
            "enabled": original.get("enabled", False)
        }
        self.session.put(f"{BASE_URL}/api/admin/email-config", json=restore_data)
    
    def test_email_config_test_endpoint(self):
        """POST /api/admin/email-config/test sends a test email (simulated)"""
        resp = self.session.post(f"{BASE_URL}/api/admin/email-config/test", json={
            "to_email": "admin@meetflow.com"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Should return status (sent, logged, or error)
        assert "status" in data or "provider" in data, "Response should indicate email status"
        print(f"✓ Email test endpoint works: {data}")
    
    def test_email_config_requires_admin(self):
        """Email config endpoints require admin role"""
        # Create a new session without auth
        unauth_session = requests.Session()
        unauth_session.headers.update({"Content-Type": "application/json"})
        
        resp = unauth_session.get(f"{BASE_URL}/api/admin/email-config")
        assert resp.status_code == 401, "Should require authentication"
        print("✓ Email config requires authentication")
    
    # ============ COMBINED PAGINATION + SEARCH TESTS ============
    
    def test_meetings_pagination_with_search(self):
        """GET /api/meetings with both pagination and search params"""
        resp = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=5&search=Meeting")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "meetings" in data
        assert "total" in data
        assert len(data["meetings"]) <= 5
        print(f"✓ Combined pagination+search works: {len(data['meetings'])} meetings found")
    
    def test_meetings_pagination_with_type_and_search(self):
        """GET /api/meetings with pagination, type filter, and search"""
        resp = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=5&meeting_type=upcoming&search=Meeting")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "meetings" in data
        for m in data["meetings"]:
            assert m["status"] in ["scheduled", "active"]
        print(f"✓ Combined pagination+type+search works: {len(data['meetings'])} upcoming meetings found")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
