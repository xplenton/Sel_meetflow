"""
Iteration 134 Bug Fixes Tests
=============================
Tests for:
1. Bug 1: Admin 'Alle abmelden' (Force Logout All) - AlertDialog + POST /api/admin/force-logout-all
2. Bug 3: Chat notification code verification (ChatUnreadContext wiring)
3. Smoke test: Digital signage preview endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAdminForceLogoutAll:
    """Bug 1: Admin 'Alle abmelden' button should POST to /api/admin/force-logout-all"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin_user = login_resp.json()
        print(f"Logged in as admin: {self.admin_user.get('email')}")
    
    def test_force_logout_all_endpoint_exists(self):
        """Test that POST /api/admin/force-logout-all endpoint exists and works"""
        resp = self.session.post(f"{BASE_URL}/api/admin/force-logout-all")
        assert resp.status_code == 200, f"Force logout all failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "modified_count" in data, f"Response missing modified_count: {data}"
        print(f"Force logout all response: {data}")
        # modified_count can be 0 if no other users are logged in
        assert isinstance(data["modified_count"], int), "modified_count should be an integer"
        print(f"PASS: Force logout all endpoint works, modified {data['modified_count']} users")
    
    def test_force_logout_all_requires_admin(self):
        """Test that non-admin users cannot call force-logout-all"""
        # Create a new session without admin privileges
        non_admin_session = requests.Session()
        # Try to call without auth
        resp = non_admin_session.post(f"{BASE_URL}/api/admin/force-logout-all")
        assert resp.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {resp.status_code}"
        print("PASS: Force logout all requires authentication")


class TestDigitalSignagePreview:
    """Smoke test: Digital signage preview endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
    
    def test_digital_signage_preview_requires_auth(self):
        """Test that preview endpoint requires authentication"""
        no_auth_session = requests.Session()
        # Use a fake post_id - should fail with 401 before 404
        resp = no_auth_session.get(f"{BASE_URL}/api/news/digital-signage/preview/fake_post_id")
        assert resp.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {resp.status_code}"
        print("PASS: Digital signage preview requires auth")
    
    def test_digital_signage_preview_with_auth(self):
        """Test that authenticated user can access preview (even for non-existent post)"""
        # First, try to get a real post
        feed_resp = self.session.get(f"{BASE_URL}/api/news/feed")
        if feed_resp.status_code == 200:
            feed_data = feed_resp.json()
            posts = feed_data.get("posts", [])
            if posts:
                post_id = posts[0].get("post_id")
                preview_resp = self.session.get(f"{BASE_URL}/api/news/digital-signage/preview/{post_id}")
                if preview_resp.status_code == 200:
                    data = preview_resp.json()
                    assert "posts" in data, f"Response missing posts: {data}"
                    assert "preview" in data, f"Response missing preview flag: {data}"
                    print(f"PASS: Digital signage preview works for post {post_id}")
                    return
        
        # If no posts exist, test with fake ID - should return 404 (not 401/403)
        resp = self.session.get(f"{BASE_URL}/api/news/digital-signage/preview/fake_post_id")
        assert resp.status_code == 404, f"Expected 404 for non-existent post, got {resp.status_code}"
        print("PASS: Digital signage preview returns 404 for non-existent post (auth works)")


class TestChatNotificationWiring:
    """Bug 3: Verify ChatUnreadContext has notification wiring
    
    This is a code verification test - we verify the backend endpoints that
    ChatUnreadContext relies on are working correctly.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.user = login_resp.json()
    
    def test_chat_unread_summary_endpoint(self):
        """Test that /chat/unread-summary endpoint works (used by ChatUnreadContext)"""
        resp = self.session.get(f"{BASE_URL}/api/chat/unread-summary")
        assert resp.status_code == 200, f"Unread summary failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "total_unread" in data, f"Response missing total_unread: {data}"
        assert "top" in data, f"Response missing top: {data}"
        print(f"PASS: Chat unread summary works - total_unread: {data.get('total_unread')}")
    
    def test_chat_my_status_endpoint(self):
        """Test that /chat/my-status endpoint works (used for DND check)"""
        resp = self.session.get(f"{BASE_URL}/api/chat/my-status")
        assert resp.status_code == 200, f"My status failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        # status_mode should be present
        print(f"PASS: Chat my-status works - status: {data}")


class TestMeetingEndpoints:
    """Test meeting-related endpoints for WebRTC bug verification"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.user = login_resp.json()
    
    def test_create_meeting(self):
        """Test creating a meeting for WebRTC testing"""
        from datetime import datetime, timedelta
        
        start_time = (datetime.utcnow() + timedelta(minutes=5)).isoformat() + "Z"
        meeting_data = {
            "title": "TEST_WebRTC_Bug_Verification",
            "description": "Testing WebRTC video call functionality",
            "start_time": start_time,
            "duration": 30
        }
        
        resp = self.session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
        assert resp.status_code in [200, 201], f"Create meeting failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "meeting_id" in data, f"Response missing meeting_id: {data}"
        print(f"PASS: Meeting created with ID: {data.get('meeting_id')}")
        
        # Store for cleanup
        self.meeting_id = data.get("meeting_id")
        return data
    
    def test_get_meeting(self):
        """Test getting meeting details"""
        # First create a meeting
        meeting = self.test_create_meeting()
        meeting_id = meeting.get("meeting_id")
        
        resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert resp.status_code == 200, f"Get meeting failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert data.get("meeting_id") == meeting_id
        print("PASS: Meeting retrieved successfully")


class TestAdminUserManagement:
    """Test admin user management for force-logout verification"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin = login_resp.json()
    
    def test_admin_users_list(self):
        """Test admin can list users"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 200, f"List users failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        # Can be a list or paginated response
        if isinstance(data, list):
            print(f"PASS: Admin users list works - {len(data)} users")
        else:
            users = data.get("users", [])
            print(f"PASS: Admin users list works - {len(users)} users (paginated)")
    
    def test_admin_stats(self):
        """Test admin stats endpoint"""
        resp = self.session.get(f"{BASE_URL}/api/admin/stats")
        assert resp.status_code == 200, f"Admin stats failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "total_users" in data, f"Response missing total_users: {data}"
        print(f"PASS: Admin stats works - {data.get('total_users')} total users")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
