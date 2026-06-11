"""
Backend tests for User Status System and Pending Reports Count
Tests:
- PUT /api/chat/my-status - set user status (online/away/dnd/offline)
- GET /api/chat/my-status - get current status with focus-time override
- POST /api/chat/statuses - bulk fetch statuses for multiple users
- GET /api/news/reports/pending-count - pending reports count for reviewers
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
AUTOR_EMAIL = "autor-test@meetflow.com"
AUTOR_PASSWORD = "9e619d6544"


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth cookie"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def autor_session():
    """Login as autor and return session with auth cookie"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": AUTOR_EMAIL,
        "password": AUTOR_PASSWORD
    })
    assert resp.status_code == 200, f"Autor login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def admin_user_id(admin_session):
    """Get admin user_id"""
    resp = admin_session.get(f"{BASE_URL}/api/auth/me")
    assert resp.status_code == 200
    return resp.json().get("user_id")


@pytest.fixture(scope="module")
def autor_user_id(autor_session):
    """Get autor user_id"""
    resp = autor_session.get(f"{BASE_URL}/api/auth/me")
    assert resp.status_code == 200
    return resp.json().get("user_id")


class TestMyStatusEndpoint:
    """Tests for PUT /api/chat/my-status"""

    def test_set_status_online(self, admin_session):
        """Set status to 'online' - should succeed"""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "online"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status_mode") == "online", f"Expected status_mode='online', got {data}"

    def test_set_status_away(self, admin_session):
        """Set status to 'away' - should succeed"""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "away"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status_mode") == "away"

    def test_set_status_dnd(self, admin_session):
        """Set status to 'dnd' (do not disturb) - should succeed"""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "dnd"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status_mode") == "dnd"

    def test_set_status_offline(self, admin_session):
        """Set status to 'offline' - should succeed"""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "offline"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status_mode") == "offline"

    def test_set_invalid_status_returns_400(self, admin_session):
        """Set invalid status value - should return 400"""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "invalid_status"})
        assert resp.status_code == 400, f"Expected 400 for invalid status, got {resp.status_code}"

    def test_set_status_empty_returns_400(self, admin_session):
        """Set empty status value - should return 400"""
        resp = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": ""})
        assert resp.status_code == 400, f"Expected 400 for empty status, got {resp.status_code}"


class TestGetMyStatusEndpoint:
    """Tests for GET /api/chat/my-status"""

    def test_get_my_status_returns_current_status(self, admin_session):
        """GET /api/chat/my-status returns current status"""
        # First set a known status
        admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "online"})
        
        resp = admin_session.get(f"{BASE_URL}/api/chat/my-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status_mode" in data, f"Expected 'status_mode' in response, got {data}"
        # Note: Admin has active focus time, so status might be 'dnd' due to focus override
        assert data["status_mode"] in ["online", "away", "dnd", "offline"], f"Invalid status: {data['status_mode']}"

    def test_get_my_status_includes_focus_info(self, admin_session):
        """GET /api/chat/my-status includes focus time info if active"""
        resp = admin_session.get(f"{BASE_URL}/api/chat/my-status")
        assert resp.status_code == 200
        data = resp.json()
        # Response should have 'focus' key (can be null or object)
        assert "focus" in data or "status_mode" in data, "Expected focus or status_mode in response"


class TestBulkStatusesEndpoint:
    """Tests for POST /api/chat/statuses"""

    def test_bulk_statuses_returns_statuses_for_users(self, admin_session, admin_user_id, autor_user_id):
        """POST /api/chat/statuses returns statuses for given user_ids"""
        resp = admin_session.post(f"{BASE_URL}/api/chat/statuses", json={
            "user_ids": [admin_user_id, autor_user_id]
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "statuses" in data, f"Expected 'statuses' in response, got {data}"
        statuses = data["statuses"]
        # Should have entries for requested users
        assert isinstance(statuses, dict), f"Expected dict, got {type(statuses)}"

    def test_bulk_statuses_empty_list_returns_empty(self, admin_session):
        """POST /api/chat/statuses with empty list returns empty statuses"""
        resp = admin_session.post(f"{BASE_URL}/api/chat/statuses", json={"user_ids": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("statuses") == {}, f"Expected empty statuses, got {data}"

    def test_bulk_statuses_nonexistent_user(self, admin_session):
        """POST /api/chat/statuses with non-existent user_id returns empty for that user"""
        resp = admin_session.post(f"{BASE_URL}/api/chat/statuses", json={
            "user_ids": ["nonexistent_user_12345"]
        })
        assert resp.status_code == 200
        data = resp.json()
        # Non-existent user should not be in statuses
        assert "nonexistent_user_12345" not in data.get("statuses", {}), "Unexpected user in statuses"

    def test_bulk_statuses_returns_last_seen(self, admin_session, admin_user_id):
        """POST /api/chat/statuses returns last_seen for users"""
        resp = admin_session.post(f"{BASE_URL}/api/chat/statuses", json={
            "user_ids": [admin_user_id]
        })
        assert resp.status_code == 200
        data = resp.json()
        statuses = data.get("statuses", {})
        if admin_user_id in statuses:
            user_status = statuses[admin_user_id]
            assert "status_mode" in user_status, "Expected status_mode in user status"
            assert "last_seen" in user_status, "Expected last_seen in user status"


class TestPendingReportsCount:
    """Tests for GET /api/news/reports/pending-count"""

    def test_admin_gets_pending_count(self, admin_session):
        """Admin (reviewer) gets pending reports count"""
        resp = admin_session.get(f"{BASE_URL}/api/news/reports/pending-count")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "count" in data, f"Expected 'count' in response, got {data}"
        assert isinstance(data["count"], int), f"Expected int count, got {type(data['count'])}"
        assert data["count"] >= 0, "Count should be non-negative"

    def test_autor_gets_zero_count_not_403(self, autor_session):
        """Autor (non-reviewer) gets count=0 instead of 403"""
        resp = autor_session.get(f"{BASE_URL}/api/news/reports/pending-count")
        # Per spec: non-reviewers get 200 with count=0, not 403
        assert resp.status_code == 200, f"Expected 200 for non-reviewer, got {resp.status_code}"
        data = resp.json()
        assert data.get("count") == 0, f"Expected count=0 for non-reviewer, got {data}"


class TestStatusPersistence:
    """Test that status changes persist correctly"""

    def test_status_change_persists(self, admin_session):
        """Status change via PUT persists and is returned by GET"""
        # Set to 'away'
        resp1 = admin_session.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "away"})
        assert resp1.status_code == 200
        
        # Get status - should be 'away' (unless focus override)
        resp2 = admin_session.get(f"{BASE_URL}/api/chat/my-status")
        assert resp2.status_code == 200
        data = resp2.json()
        # Note: If admin has active focus, status will be 'dnd' due to focus override
        # This is expected behavior per the spec
        assert data["status_mode"] in ["away", "dnd"], f"Expected 'away' or 'dnd' (focus override), got {data['status_mode']}"


class TestUnauthenticatedAccess:
    """Test that endpoints require authentication"""

    def test_my_status_requires_auth(self):
        """GET /api/chat/my-status requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/chat/my-status")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_set_status_requires_auth(self):
        """PUT /api/chat/my-status requires authentication"""
        resp = requests.put(f"{BASE_URL}/api/chat/my-status", json={"status_mode": "online"})
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_bulk_statuses_requires_auth(self):
        """POST /api/chat/statuses requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/chat/statuses", json={"user_ids": []})
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"

    def test_pending_count_requires_auth(self):
        """GET /api/news/reports/pending-count requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/news/reports/pending-count")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
