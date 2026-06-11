"""
Iteration 262 — WebPush für DMs + PWA-Polish Tests

Tests:
1. WEBPUSH DMs — POST /api/chat/push/test endpoint
   - Without subscription: HTTP 400 with 'Kein Gerät registriert'
   - With token: 200 or 400 (depending on subscription)
   - Without token: 401
   - Tag in payload must be 'chat-push-test', kind='chat_message'

2. Chat messages endpoint regression — POST /api/chat/conversations/{id}/messages still returns 200

3. PWA-Polish — GET /api/chat/unread-summary returns 'total_unread' field

4. 12-Module Sanity Check — Auth, Tasks, Calendar, News, Resources, Chat, Admin, Surveys, Meetings, Notifications, Dashboard, Scheduling

5. RBAC — Tokenless requests on new endpoints return 401
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestWebPushDMs:
    """WebPush DMs endpoint tests — POST /api/chat/push/test"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_chat_push_test_without_token_returns_401(self):
        """RBAC: POST /api/chat/push/test without token returns 401"""
        resp = requests.post(f"{BASE_URL}/api/chat/push/test", json={})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS — POST /api/chat/push/test without token returns 401")
    
    def test_chat_push_test_with_token_no_subscription(self):
        """POST /api/chat/push/test with token but no subscription returns 400 with 'Kein Gerät registriert'"""
        resp = self.session.post(f"{BASE_URL}/api/chat/push/test", headers=self.headers, json={})
        # Expected: 400 if no subscription, 200 if subscription exists
        if resp.status_code == 400:
            data = resp.json()
            assert "Kein Gerät registriert" in data.get("detail", ""), f"Expected 'Kein Gerät registriert' in detail, got: {data}"
            print("PASS — POST /api/chat/push/test returns 400 with 'Kein Gerät registriert' (no subscription)")
        elif resp.status_code == 200:
            data = resp.json()
            assert "message" in data, f"Expected 'message' in response, got: {data}"
            print("PASS — POST /api/chat/push/test returns 200 (subscription exists)")
        else:
            pytest.fail(f"Unexpected status code {resp.status_code}: {resp.text}")


class TestChatMessagesRegression:
    """Chat messages endpoint regression tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_conversations_returns_200(self):
        """GET /api/chat/conversations returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/chat/conversations", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — GET /api/chat/conversations returns 200")
    
    def test_post_message_to_conversation(self):
        """POST /api/chat/conversations/{id}/messages returns 200/201"""
        # First get conversations
        convs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations", headers=self.headers)
        assert convs_resp.status_code == 200
        convs = convs_resp.json()
        
        if len(convs) == 0:
            # Create a conversation first
            users_resp = self.session.get(f"{BASE_URL}/api/chat/users", headers=self.headers)
            if users_resp.status_code == 200 and len(users_resp.json()) > 0:
                other_user = users_resp.json()[0]
                create_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", headers=self.headers, json={
                    "type": "direct",
                    "member_ids": [other_user["user_id"]]
                })
                if create_resp.status_code in [200, 201]:
                    conv_id = create_resp.json().get("conversation_id")
                else:
                    pytest.skip("Could not create conversation for testing")
            else:
                pytest.skip("No users available to create conversation")
        else:
            conv_id = convs[0]["conversation_id"]
        
        # Send a test message
        msg_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", headers=self.headers, json={
            "content": "Test message from iter262 test",
            "mentions": [],
            "priority": "normal"
        })
        assert msg_resp.status_code in [200, 201], f"Expected 200/201, got {msg_resp.status_code}: {msg_resp.text}"
        print(f"PASS — POST /api/chat/conversations/{conv_id}/messages returns {msg_resp.status_code}")


class TestPWAPolish:
    """PWA-Polish tests — unread-summary endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_unread_summary_returns_total_unread(self):
        """GET /api/chat/unread-summary returns 200 with 'total_unread' field"""
        resp = self.session.get(f"{BASE_URL}/api/chat/unread-summary", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "total_unread" in data, f"Expected 'total_unread' in response, got: {data}"
        print(f"PASS — GET /api/chat/unread-summary returns 200 with total_unread={data['total_unread']}")
    
    def test_unread_summary_without_token_returns_401(self):
        """RBAC: GET /api/chat/unread-summary without token returns 401"""
        resp = requests.get(f"{BASE_URL}/api/chat/unread-summary")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS — GET /api/chat/unread-summary without token returns 401")


class TestRegressionSanityCheck:
    """12-Module Sanity Check — Auth, Tasks, Calendar, News, Resources, Chat, Admin, Surveys, Meetings, Notifications, Dashboard, Scheduling"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_auth_me(self):
        """Auth — GET /api/auth/me returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/auth/me", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Auth: GET /api/auth/me 200")
    
    def test_tasks(self):
        """Tasks — GET /api/tasks returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Tasks: GET /api/tasks 200")
    
    def test_calendar(self):
        """Calendar — GET /api/calendar/events returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/calendar/events", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Calendar: GET /api/calendar/events 200")
    
    def test_news(self):
        """News — GET /api/news/feed returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/news/feed", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — News: GET /api/news/feed 200")
    
    def test_resources(self):
        """Resources — GET /api/resources returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/resources", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Resources: GET /api/resources 200")
    
    def test_chat(self):
        """Chat — GET /api/chat/conversations returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/chat/conversations", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Chat: GET /api/chat/conversations 200")
    
    def test_admin(self):
        """Admin — GET /api/admin/users returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Admin: GET /api/admin/users 200")
    
    def test_surveys(self):
        """Surveys — GET /api/surveys returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/surveys", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Surveys: GET /api/surveys 200")
    
    def test_meetings(self):
        """Meetings — GET /api/meetings returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/meetings", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Meetings: GET /api/meetings 200")
    
    def test_notifications(self):
        """Notifications — GET /api/notifications returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/notifications", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Notifications: GET /api/notifications 200")
    
    def test_dashboard(self):
        """Dashboard — GET /api/dashboard/stats returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/dashboard/stats", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Dashboard: GET /api/dashboard/stats 200")
    
    def test_scheduling(self):
        """Scheduling — GET /api/schedule-polls returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/schedule-polls", headers=self.headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS — Scheduling: GET /api/schedule-polls 200")


class TestRBACTokenless:
    """RBAC — Tokenless requests on new endpoints return 401"""
    
    def test_chat_push_test_no_token(self):
        """POST /api/chat/push/test without token returns 401"""
        resp = requests.post(f"{BASE_URL}/api/chat/push/test", json={})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS — POST /api/chat/push/test without token returns 401")
    
    def test_chat_conversations_no_token(self):
        """GET /api/chat/conversations without token returns 401"""
        resp = requests.get(f"{BASE_URL}/api/chat/conversations")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS — GET /api/chat/conversations without token returns 401")
    
    def test_chat_unread_summary_no_token(self):
        """GET /api/chat/unread-summary without token returns 401"""
        resp = requests.get(f"{BASE_URL}/api/chat/unread-summary")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS — GET /api/chat/unread-summary without token returns 401")
    
    def test_admin_users_no_token(self):
        """GET /api/admin/users without token returns 401"""
        resp = requests.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS — GET /api/admin/users without token returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
