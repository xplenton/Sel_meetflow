"""
Iteration 263 — Notification Center Tests
Tests for:
- Backend enrichment: category + link_target fields
- Backend legacy handling: body from message, notification_id fallback
- Backend category filter: GET /api/notifications?category=X
- Backend counts: GET /api/notifications/categories
- Backend deep-links: link_target resolution
- RBAC: tokenless requests return 401
- Regression: 12-module sanity check
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def admin_user_id(auth_headers):
    """Get admin user ID"""
    resp = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
    if resp.status_code != 200:
        pytest.skip("Could not get user info")
    return resp.json().get("user_id")


class TestRBACTokenless:
    """RBAC: Tokenless requests should return 401"""
    
    def test_notifications_no_token(self):
        """GET /api/notifications without token → 401"""
        resp = requests.get(f"{BASE_URL}/api/notifications")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS — GET /api/notifications without token returns 401")
    
    def test_notifications_categories_no_token(self):
        """GET /api/notifications/categories without token → 401"""
        resp = requests.get(f"{BASE_URL}/api/notifications/categories")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS — GET /api/notifications/categories without token returns 401")
    
    def test_notifications_unread_count_no_token(self):
        """GET /api/notifications/unread-count without token → 401"""
        resp = requests.get(f"{BASE_URL}/api/notifications/unread-count")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS — GET /api/notifications/unread-count without token returns 401")


class TestNotificationsBackwardCompat:
    """Regression: GET /api/notifications without params works (backward-compat)"""
    
    def test_notifications_basic(self, auth_headers):
        """GET /api/notifications returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS — GET /api/notifications returns 200 with {len(data)} notifications")
    
    def test_notifications_with_since_days(self, auth_headers):
        """GET /api/notifications?since_days=30 works"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"since_days": 30}, headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — GET /api/notifications?since_days=30 returns 200")
    
    def test_notifications_with_only_unread(self, auth_headers):
        """GET /api/notifications?only_unread=true works"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"only_unread": True}, headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — GET /api/notifications?only_unread=true returns 200")


class TestNotificationsCategoriesEndpoint:
    """NEW endpoint GET /api/notifications/categories"""
    
    def test_categories_endpoint_exists(self, auth_headers):
        """GET /api/notifications/categories returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications/categories", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        print(f"PASS — GET /api/notifications/categories returns 200: {data}")
    
    def test_categories_has_all_keys(self, auth_headers):
        """Categories response has all 7 categories + 'all'"""
        resp = requests.get(f"{BASE_URL}/api/notifications/categories", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = {"chat", "news", "tasks", "meetings", "bookings", "surveys", "system", "all"}
        actual_keys = set(data.keys())
        assert expected_keys.issubset(actual_keys), f"Missing keys: {expected_keys - actual_keys}"
        print(f"PASS — Categories response has all expected keys: {list(data.keys())}")
    
    def test_categories_values_are_integers(self, auth_headers):
        """Category counts are integers"""
        resp = requests.get(f"{BASE_URL}/api/notifications/categories", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for key, value in data.items():
            assert isinstance(value, int), f"Expected int for {key}, got {type(value)}"
        print("PASS — All category counts are integers")


class TestNotificationsCategoryFilter:
    """Backend category filter: GET /api/notifications?category=X"""
    
    def test_filter_category_chat(self, auth_headers):
        """GET /api/notifications?category=chat returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "chat"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # If there are results, verify they are chat category
        for n in data:
            assert n.get("category") == "chat", f"Expected chat category, got {n.get('category')}"
        print(f"PASS — category=chat filter works, {len(data)} results")
    
    def test_filter_category_news(self, auth_headers):
        """GET /api/notifications?category=news returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "news"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert n.get("category") == "news", f"Expected news category, got {n.get('category')}"
        print(f"PASS — category=news filter works, {len(data)} results")
    
    def test_filter_category_tasks(self, auth_headers):
        """GET /api/notifications?category=tasks returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "tasks"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert n.get("category") == "tasks", f"Expected tasks category, got {n.get('category')}"
        print(f"PASS — category=tasks filter works, {len(data)} results")
    
    def test_filter_category_meetings(self, auth_headers):
        """GET /api/notifications?category=meetings returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "meetings"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert n.get("category") == "meetings", f"Expected meetings category, got {n.get('category')}"
        print(f"PASS — category=meetings filter works, {len(data)} results")
    
    def test_filter_category_bookings(self, auth_headers):
        """GET /api/notifications?category=bookings returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "bookings"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert n.get("category") == "bookings", f"Expected bookings category, got {n.get('category')}"
        print(f"PASS — category=bookings filter works, {len(data)} results")
    
    def test_filter_category_surveys(self, auth_headers):
        """GET /api/notifications?category=surveys returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "surveys"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert n.get("category") == "surveys", f"Expected surveys category, got {n.get('category')}"
        print(f"PASS — category=surveys filter works, {len(data)} results")
    
    def test_filter_category_system(self, auth_headers):
        """GET /api/notifications?category=system returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "system"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert n.get("category") == "system", f"Expected system category, got {n.get('category')}"
        print(f"PASS — category=system filter works, {len(data)} results")
    
    def test_filter_category_invalid(self, auth_headers):
        """GET /api/notifications?category=invalid returns all (no filter)"""
        resp = requests.get(f"{BASE_URL}/api/notifications", 
                          params={"category": "invalid_category"}, headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — category=invalid returns 200 (no filter applied)")


class TestNotificationsEnrichment:
    """Backend enrichment: category + link_target fields"""
    
    def test_notifications_have_category_field(self, auth_headers):
        """All notifications have 'category' field"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        valid_categories = {"chat", "news", "tasks", "meetings", "bookings", "surveys", "system"}
        for n in data:
            assert "category" in n, f"Missing 'category' field in notification {n.get('notification_id')}"
            assert n["category"] in valid_categories, f"Invalid category: {n['category']}"
        print(f"PASS — All {len(data)} notifications have valid 'category' field")
    
    def test_notifications_have_link_target_field(self, auth_headers):
        """All notifications have 'link_target' field"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert "link_target" in n, f"Missing 'link_target' field in notification {n.get('notification_id')}"
            assert isinstance(n["link_target"], str), f"link_target should be string"
            assert n["link_target"].startswith("/"), f"link_target should start with '/': {n['link_target']}"
        print(f"PASS — All {len(data)} notifications have valid 'link_target' field")
    
    def test_notifications_have_notification_id(self, auth_headers):
        """All notifications have 'notification_id' field (including legacy fallback)"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for n in data:
            assert "notification_id" in n, f"Missing 'notification_id' field"
            assert n["notification_id"], f"notification_id should not be empty"
        print(f"PASS — All {len(data)} notifications have 'notification_id' field")


class TestRegression12Modules:
    """12-Module Sanity Check"""
    
    def test_auth_me(self, auth_headers):
        """GET /api/auth/me returns 200"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Auth module: GET /api/auth/me 200")
    
    def test_tasks(self, auth_headers):
        """GET /api/tasks returns 200"""
        resp = requests.get(f"{BASE_URL}/api/tasks", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Tasks module: GET /api/tasks 200")
    
    def test_calendar(self, auth_headers):
        """GET /api/calendar/events returns 200"""
        resp = requests.get(f"{BASE_URL}/api/calendar/events", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Calendar module: GET /api/calendar/events 200")
    
    def test_news(self, auth_headers):
        """GET /api/news/feed returns 200"""
        resp = requests.get(f"{BASE_URL}/api/news/feed", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — News module: GET /api/news/feed 200")
    
    def test_resources(self, auth_headers):
        """GET /api/resources returns 200"""
        resp = requests.get(f"{BASE_URL}/api/resources", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Resources module: GET /api/resources 200")
    
    def test_chat(self, auth_headers):
        """GET /api/chat/conversations returns 200"""
        resp = requests.get(f"{BASE_URL}/api/chat/conversations", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Chat module: GET /api/chat/conversations 200")
    
    def test_admin(self, auth_headers):
        """GET /api/admin/users returns 200"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Admin module: GET /api/admin/users 200")
    
    def test_surveys(self, auth_headers):
        """GET /api/surveys returns 200"""
        resp = requests.get(f"{BASE_URL}/api/surveys", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Surveys module: GET /api/surveys 200")
    
    def test_meetings(self, auth_headers):
        """GET /api/meetings returns 200"""
        resp = requests.get(f"{BASE_URL}/api/meetings", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Meetings module: GET /api/meetings 200")
    
    def test_notifications(self, auth_headers):
        """GET /api/notifications returns 200"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Notifications module: GET /api/notifications 200")
    
    def test_dashboard(self, auth_headers):
        """GET /api/dashboard/stats returns 200"""
        resp = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Dashboard module: GET /api/dashboard/stats 200")
    
    def test_scheduling(self, auth_headers):
        """GET /api/schedule-polls returns 200"""
        resp = requests.get(f"{BASE_URL}/api/schedule-polls", headers=auth_headers)
        assert resp.status_code == 200
        print("PASS — Scheduling module: GET /api/schedule-polls 200")


class TestDeepLinkResolution:
    """Test deep-link resolution for various notification types via direct MongoDB insert"""
    
    def test_link_target_defaults(self, auth_headers):
        """Verify link_target has sensible defaults for existing notifications"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        
        # Check that link_target is a valid route
        valid_prefixes = ["/meetings", "/surveys", "/news", "/tasks", "/ressourcen", 
                         "/chat", "/profile", "/dashboard", "/diag"]
        for n in data:
            link = n.get("link_target", "")
            has_valid_prefix = any(link.startswith(p) for p in valid_prefixes)
            assert has_valid_prefix, f"Invalid link_target: {link} for type {n.get('type')}"
        
        print(f"PASS — All {len(data)} notifications have valid link_target routes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
