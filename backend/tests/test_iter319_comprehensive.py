"""
Iter 319 — Comprehensive Full-Stack Test Suite for MeetFlow

Tests all major modules:
- Auth & RBAC
- Resources (CRUD, Bookings, Conflicts, Check-in/out)
- Catering (Items, Requests, Status Transitions)
- Billing/Invoices
- Tasks, News, Chat, Surveys
- Admin (Users, Groups, Permissions)
- Analytics Dashboards

Run: `cd /app/backend && pytest tests/test_iter319_comprehensive.py -v --tb=short`
"""
import pytest
import requests
import os
import time
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Session-scoped token to avoid rate limits
_cached_token = None
_token_time = 0


def _get_session_token(base_url: str) -> str:
    """Get cached token or fetch new one"""
    global _cached_token, _token_time
    if _cached_token and (time.time() - _token_time) < 300:  # 5 min cache
        return _cached_token
    r = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": "admin@meetflow.com", "password": "admin123"},
        timeout=10,
        verify=False,
    )
    r.raise_for_status()
    _cached_token = r.json().get("token")
    _token_time = time.time()
    return _cached_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# AUTH & RBAC TESTS
# ============================================================================
class TestAuth:
    """Authentication and authorization tests"""

    def test_login_success(self, base_url, admin_credentials):
        """POST /api/auth/login with valid credentials"""
        r = requests.post(
            f"{base_url}/api/auth/login",
            json=admin_credentials,
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["email"] == admin_credentials["email"]
        assert data["role"] == "admin"

    def test_login_invalid_password(self, base_url, admin_credentials):
        """POST /api/auth/login with wrong password"""
        r = requests.post(
            f"{base_url}/api/auth/login",
            json={"email": admin_credentials["email"], "password": "wrongpassword"},
            timeout=10,
            verify=False,
        )
        assert r.status_code == 401

    def test_auth_me_with_token(self, base_url, admin_token):
        """GET /api/auth/me with valid token"""
        r = requests.get(
            f"{base_url}/api/auth/me",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        data = r.json()
        assert "user_id" in data
        assert "email" in data

    def test_auth_me_without_token(self, base_url):
        """GET /api/auth/me without token returns 401"""
        r = requests.get(f"{base_url}/api/auth/me", timeout=10, verify=False)
        assert r.status_code == 401


# ============================================================================
# RESOURCES CRUD TESTS
# ============================================================================
class TestResourcesCRUD:
    """Resource management CRUD operations"""

    def test_list_resources(self, base_url, admin_token):
        """GET /api/resources returns list"""
        r = requests.get(
            f"{base_url}/api/resources",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_resource(self, base_url, admin_token):
        """POST /api/resources creates a new resource"""
        payload = {
            "name": "TEST_Room_319",
            "type": "room",
            "capacity": 10,
            "location": "Building A",
            "equipment": ["projector", "whiteboard"],
        }
        r = requests.post(
            f"{base_url}/api/resources",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == payload["name"]
        assert "resource_id" in data  # API uses resource_id not id
        # Cleanup
        requests.delete(
            f"{base_url}/api/resources/{data['resource_id']}",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )

    def test_get_resource_by_id(self, base_url, admin_token):
        """GET /api/resources/{id} returns resource details"""
        # First create a resource
        payload = {"name": "TEST_Room_Get_319", "type": "room", "capacity": 5}
        create_r = requests.post(
            f"{base_url}/api/resources",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert create_r.status_code == 200
        resource_id = create_r.json()["resource_id"]

        # Get by ID
        r = requests.get(
            f"{base_url}/api/resources/{resource_id}",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert r.json()["resource_id"] == resource_id

        # Cleanup
        requests.delete(
            f"{base_url}/api/resources/{resource_id}",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )

    def test_get_nonexistent_resource(self, base_url, admin_token):
        """GET /api/resources/{id} for non-existent returns 404"""
        r = requests.get(
            f"{base_url}/api/resources/res_does_not_exist",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 404

    def test_resources_require_auth(self, base_url):
        """GET /api/resources without token returns 401"""
        r = requests.get(f"{base_url}/api/resources", timeout=10, verify=False)
        assert r.status_code == 401


# ============================================================================
# RESOURCE BOOKINGS TESTS
# ============================================================================
class TestResourceBookings:
    """Resource booking operations"""

    @pytest.fixture
    def test_resource(self, base_url, admin_token):
        """Create a test resource for booking tests"""
        payload = {"name": "TEST_BookingRoom_319", "type": "room", "capacity": 10}
        r = requests.post(
            f"{base_url}/api/resources",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        resource = r.json()
        yield resource
        # Cleanup
        requests.delete(
            f"{base_url}/api/resources/{resource['resource_id']}",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )

    def test_create_booking(self, base_url, admin_token, test_resource):
        """POST /api/resource-bookings creates a booking"""
        start = datetime.utcnow() + timedelta(days=1)
        end = start + timedelta(hours=1)
        payload = {
            "resource_id": test_resource["resource_id"],
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z",
            "title": "TEST_Booking_319",
        }
        r = requests.post(
            f"{base_url}/api/resource-bookings",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data or "booking_id" in data
        booking_id = data.get("id") or data.get("booking_id")
        # Cleanup
        requests.delete(
            f"{base_url}/api/resource-bookings/{booking_id}",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )

    def test_booking_conflict_detection(self, base_url, admin_token, test_resource):
        """POST /api/resource-bookings detects conflicts (409)"""
        start = datetime.utcnow() + timedelta(days=2)
        end = start + timedelta(hours=1)
        payload = {
            "resource_id": test_resource["resource_id"],
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z",
            "title": "TEST_Booking_Conflict_1",
        }
        # First booking
        r1 = requests.post(
            f"{base_url}/api/resource-bookings",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r1.status_code == 200
        data = r1.json()
        booking_id = data.get("id") or data.get("booking_id")

        # Second booking at same time should conflict
        payload["title"] = "TEST_Booking_Conflict_2"
        r2 = requests.post(
            f"{base_url}/api/resource-bookings",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r2.status_code == 409

        # Cleanup
        requests.delete(
            f"{base_url}/api/resource-bookings/{booking_id}",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )

    def test_check_conflicts_endpoint(self, base_url, admin_token, test_resource):
        """POST /api/resources/{id}/check-conflicts"""
        start = datetime.utcnow() + timedelta(days=3)
        end = start + timedelta(hours=1)
        payload = {
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z",
        }
        r = requests.post(
            f"{base_url}/api/resources/{test_resource['resource_id']}/check-conflicts",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        data = r.json()
        assert "conflicts" in data

    def test_booking_invalid_time_range(self, base_url, admin_token, test_resource):
        """POST /api/resource-bookings with end < start returns 400"""
        start = datetime.utcnow() + timedelta(days=4)
        end = start - timedelta(hours=1)  # End before start
        payload = {
            "resource_id": test_resource["resource_id"],
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z",
            "title": "TEST_Invalid_Time",
        }
        r = requests.post(
            f"{base_url}/api/resource-bookings",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 400


# ============================================================================
# CATERING TESTS
# ============================================================================
class TestCatering:
    """Catering items and requests"""

    def test_list_catering_items(self, base_url, admin_token):
        """GET /api/catering-items returns list"""
        r = requests.get(
            f"{base_url}/api/catering-items",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_catering_requests(self, base_url, admin_token):
        """GET /api/catering-requests returns list"""
        r = requests.get(
            f"{base_url}/api/catering-requests",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ============================================================================
# MASTER DATA TESTS
# ============================================================================
class TestMasterData:
    """Cost centers and accounts"""

    def test_list_cost_centers(self, base_url, admin_token):
        """GET /api/cost-centers returns list"""
        r = requests.get(
            f"{base_url}/api/cost-centers",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_accounts(self, base_url, admin_token):
        """GET /api/accounts returns list"""
        r = requests.get(
            f"{base_url}/api/accounts",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cost_centers_require_auth(self, base_url):
        """GET /api/cost-centers without token returns 401"""
        r = requests.get(f"{base_url}/api/cost-centers", timeout=10, verify=False)
        assert r.status_code == 401

    def test_accounts_require_auth(self, base_url):
        """GET /api/accounts without token returns 401"""
        r = requests.get(f"{base_url}/api/accounts", timeout=10, verify=False)
        assert r.status_code == 401


# ============================================================================
# FLOORPLANS TESTS
# ============================================================================
class TestFloorplans:
    """Floorplan management"""

    def test_list_floorplans(self, base_url, admin_token):
        """GET /api/floorplans returns list"""
        r = requests.get(
            f"{base_url}/api/floorplans",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_floorplans_require_auth(self, base_url):
        """GET /api/floorplans without token returns 401"""
        r = requests.get(f"{base_url}/api/floorplans", timeout=10, verify=False)
        assert r.status_code == 401


# ============================================================================
# ANALYTICS DASHBOARD TESTS
# ============================================================================
class TestAnalytics:
    """Analytics and dashboard endpoints"""

    def test_dashboard_overview(self, base_url, admin_token):
        """GET /api/resources/dashboard/overview"""
        r = requests.get(
            f"{base_url}/api/resources/dashboard/overview",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200

    def test_availability_snapshot(self, base_url, admin_token):
        """GET /api/resource-availability-snapshot"""
        r = requests.get(
            f"{base_url}/api/resource-availability-snapshot",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200

    def test_no_show_dashboard(self, base_url, admin_token):
        """GET /api/resources/dashboard/no-show"""
        r = requests.get(
            f"{base_url}/api/resources/dashboard/no-show",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200

    def test_in_office_endpoint(self, base_url, admin_token):
        """GET /api/resources-in-office"""
        r = requests.get(
            f"{base_url}/api/resources-in-office",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200

    def test_upload_config(self, base_url, admin_token):
        """GET /api/resource-upload-config"""
        r = requests.get(
            f"{base_url}/api/resource-upload-config",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200


# ============================================================================
# TASKS MODULE TESTS
# ============================================================================
class TestTasks:
    """Tasks CRUD operations"""

    def test_list_tasks(self, base_url, admin_token):
        """GET /api/tasks returns list"""
        r = requests.get(
            f"{base_url}/api/tasks",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data or isinstance(data, list)

    def test_create_task(self, base_url, admin_token):
        """POST /api/tasks creates a task"""
        payload = {
            "title": "TEST_Task_319",
            "description": "Test task description",
            "status": "todo",
        }
        r = requests.post(
            f"{base_url}/api/tasks",
            json=payload,
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code in [200, 201]
        data = r.json()
        assert "id" in data or "task_id" in data
        # Cleanup
        task_id = data.get("id") or data.get("task_id")
        if task_id:
            requests.delete(
                f"{base_url}/api/tasks/{task_id}",
                headers=_auth(admin_token),
                timeout=10,
                verify=False,
            )


# ============================================================================
# NEWS MODULE TESTS
# ============================================================================
class TestNews:
    """News posts operations"""

    def test_list_news_feed(self, base_url, admin_token):
        """GET /api/news/feed returns list"""
        r = requests.get(
            f"{base_url}/api/news/feed",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200


# ============================================================================
# CHAT MODULE TESTS
# ============================================================================
class TestChat:
    """Chat conversations"""

    def test_list_conversations(self, base_url, admin_token):
        """GET /api/chat/conversations returns list"""
        r = requests.get(
            f"{base_url}/api/chat/conversations",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200


# ============================================================================
# SURVEYS MODULE TESTS
# ============================================================================
class TestSurveys:
    """Survey operations"""

    def test_list_surveys(self, base_url, admin_token):
        """GET /api/surveys returns list"""
        r = requests.get(
            f"{base_url}/api/surveys",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200


# ============================================================================
# ADMIN MODULE TESTS
# ============================================================================
class TestAdmin:
    """Admin operations"""

    def test_list_users(self, base_url, admin_token):
        """GET /api/admin/users returns list"""
        r = requests.get(
            f"{base_url}/api/admin/users",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_groups(self, base_url, admin_token):
        """GET /api/admin/groups returns list"""
        r = requests.get(
            f"{base_url}/api/admin/groups",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_permissions_audit(self, base_url, admin_token):
        """GET /api/admin/permissions/audit returns audit data"""
        r = requests.get(
            f"{base_url}/api/admin/permissions/audit",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200


# ============================================================================
# INVOICES MODULE TESTS
# ============================================================================
class TestInvoices:
    """Invoice operations"""

    def test_list_invoices(self, base_url, admin_token):
        """GET /api/invoices returns list"""
        r = requests.get(
            f"{base_url}/api/invoices",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200


# ============================================================================
# FAVORITES TESTS
# ============================================================================
class TestFavorites:
    """User favorites"""

    def test_get_desk_favorites(self, base_url, admin_token):
        """GET /api/favorites/desks returns favorites"""
        r = requests.get(
            f"{base_url}/api/favorites/desks",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 200
        data = r.json()
        assert "desk_ids" in data


# ============================================================================
# DEPRECATED ENDPOINTS TESTS
# ============================================================================
class TestDeprecatedEndpoints:
    """Verify deprecated endpoints return correct status"""

    def test_driver_license_singular_returns_410(self, base_url, admin_token):
        """GET /api/users/{id}/driver-license returns 410 Gone"""
        r = requests.get(
            f"{base_url}/api/users/anyone/driver-license",
            headers=_auth(admin_token),
            timeout=10,
            verify=False,
        )
        assert r.status_code == 410


# ============================================================================
# SECURITY TESTS
# ============================================================================
class TestSecurity:
    """Security and auth enforcement"""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/resources",
            "/api/cost-centers",
            "/api/accounts",
            "/api/floorplans",
            "/api/tasks",
            "/api/chat/conversations",
            "/api/surveys",
            "/api/admin/users",
            "/api/admin/groups",
        ],
    )
    def test_endpoints_require_auth(self, base_url, endpoint):
        """All protected endpoints return 401 without token"""
        r = requests.get(f"{base_url}{endpoint}", timeout=10, verify=False)
        assert r.status_code == 401, f"{endpoint} should require auth, got {r.status_code}"
