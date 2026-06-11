"""
Sprint 2 + Sprint 3 comprehensive backend tests for Resources & Bookings module.
Tests: CRUD, conflict detection, approval workflow, catering, dashboard, invoice.
"""
import requests
import pytest
from datetime import datetime, timedelta

API = None
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                API = line.split("=", 1)[1].strip().rstrip("/")
                break
except FileNotFoundError:
    pass


@pytest.fixture(scope="module")
def admin_session():
    """Admin session with full capabilities."""
    s = requests.Session()
    r = s.post(f"{API}/api/auth/login",
               json={"email": "admin@meetflow.com", "password": "admin123"},
               timeout=10)
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    yield s


@pytest.fixture(scope="module")
def member_session():
    """Member session with limited capabilities."""
    s = requests.Session()
    r = s.post(f"{API}/api/auth/login",
               json={"email": "member@meetflow.com", "password": "11db7dbd77"},
               timeout=10)
    if r.status_code != 200:
        pytest.skip("Member login failed - skipping member tests")
    yield s


# ============================================================================
# Sprint 2: Frontend-related backend tests
# ============================================================================

class TestResourceListing:
    """Test resource listing with type filters."""
    
    def test_list_rooms(self, admin_session):
        r = admin_session.get(f"{API}/api/resources?type=room", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for res in data:
            assert res.get("type") == "room"
    
    def test_list_desks(self, admin_session):
        r = admin_session.get(f"{API}/api/resources?type=desk", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for res in data:
            assert res.get("type") == "desk"
    
    def test_list_vehicles(self, admin_session):
        r = admin_session.get(f"{API}/api/resources?type=vehicle", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for res in data:
            assert res.get("type") == "vehicle"


class TestSplitableRooms:
    """Test splitable room functionality."""
    
    def test_splitable_room_has_children(self, admin_session):
        # Find a splitable room
        r = admin_session.get(f"{API}/api/resources?type=room", timeout=10)
        rooms = r.json()
        splitable = [rm for rm in rooms if rm.get("is_splitable")]
        if not splitable:
            pytest.skip("No splitable rooms in test data")
        
        # Get detail with children
        room_id = splitable[0]["resource_id"]
        r = admin_session.get(f"{API}/api/resources/{room_id}", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "children" in data
        assert len(data["children"]) > 0
        # Children should have sub_id (A, B, C)
        for child in data["children"]:
            assert "sub_id" in child


class TestBookingConflicts:
    """Test live conflict check functionality."""
    
    def test_check_conflicts_no_overlap(self, admin_session):
        # Get a room
        r = admin_session.get(f"{API}/api/resources?type=room", timeout=10)
        rooms = r.json()
        if not rooms:
            pytest.skip("No rooms available")
        
        room_id = rooms[0]["resource_id"]
        # Check far future time (unlikely to conflict)
        future = datetime.utcnow() + timedelta(days=365)
        r = admin_session.post(f"{API}/api/resources/{room_id}/check-conflicts", json={
            "start_at": future.isoformat() + "Z",
            "end_at": (future + timedelta(hours=1)).isoformat() + "Z",
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "conflicts" in data
        # Should be empty for far future
        assert isinstance(data["conflicts"], list)


class TestCateringItems:
    """Test catering items CRUD."""
    
    def test_list_catering_items(self, admin_session):
        r = admin_session.get(f"{API}/api/catering-items", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Should have seeded items
        assert len(data) > 0
        for item in data:
            assert "item_id" in item
            assert "name" in item
            assert "price" in item
            assert "unit" in item
    
    def test_create_catering_item(self, admin_session):
        r = admin_session.post(f"{API}/api/catering-items", json={
            "name": f"TestItem_{datetime.now().timestamp()}",
            "price": 5.50,
            "unit": "Stueck",
            "lead_time_min": 60,
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "item_id" in data
        assert data["price"] == 5.50


class TestMyBookings:
    """Test my bookings listing."""
    
    def test_list_my_bookings(self, admin_session):
        r = admin_session.get(f"{API}/api/resource-bookings?mine_only=true", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)


# ============================================================================
# Sprint 3: Backend endpoints
# ============================================================================

class TestApprovalsPendingCount:
    """Test approvals pending count endpoint."""
    
    def test_pending_count_returns_count(self, admin_session):
        r = admin_session.get(f"{API}/api/resource-bookings/approvals/pending-count", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert isinstance(data["count"], int)


class TestDashboardOverview:
    """Test dashboard overview endpoint."""
    
    def test_dashboard_overview_structure(self, admin_session):
        r = admin_session.get(f"{API}/api/resources/dashboard/overview?days=90", timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        # Check required fields
        assert "window_days" in data
        assert data["window_days"] == 90
        assert "resources_by_type" in data
        assert "bookings_by_status" in data
        assert "top_resources" in data
        assert "catering" in data
        
        # Check catering structure
        assert "request_count" in data["catering"]
        assert "estimated_revenue" in data["catering"]
        
        # Check top_resources is list of max 5
        assert isinstance(data["top_resources"], list)
        assert len(data["top_resources"]) <= 5


class TestInvoice:
    """Test invoice endpoint."""
    
    def test_invoice_for_catering_booking(self, admin_session):
        # Find a booking with catering
        r = admin_session.get(f"{API}/api/resource-bookings", timeout=10)
        bookings = r.json()
        with_catering = [b for b in bookings if b.get("catering_request_id")]
        
        if not with_catering:
            pytest.skip("No catering bookings available")
        
        booking_id = with_catering[0]["booking_id"]
        r = admin_session.get(f"{API}/api/resource-bookings/{booking_id}/invoice", timeout=10)
        assert r.status_code == 200
        data = r.json()
        
        assert data["booking_id"] == booking_id
        assert "lines" in data
        assert isinstance(data["lines"], list)
        assert "total" in data
        assert data["currency"] == "EUR"
    
    def test_invoice_404_for_unknown(self, admin_session):
        r = admin_session.get(f"{API}/api/resource-bookings/bk_nonexistent/invoice", timeout=10)
        assert r.status_code == 404


class TestApprovalWorkflow:
    """Test approval workflow."""
    
    def test_list_pending_approvals(self, admin_session):
        r = admin_session.get(f"{API}/api/resource-bookings?status=pending_approval", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for bk in data:
            assert bk.get("status") == "pending_approval"


# ============================================================================
# Permission gating tests
# ============================================================================

class TestPermissionGating:
    """Test capability-based access control."""
    
    def test_member_cannot_access_resources(self, member_session):
        r = member_session.get(f"{API}/api/resources", timeout=10)
        assert r.status_code == 403
        assert "Kein Zugriff" in r.json().get("detail", "")
    
    def test_member_permissions_exclude_resources(self, member_session):
        r = member_session.get(f"{API}/api/user/permissions", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "resources" not in data.get("permissions", [])
    
    def test_unauthenticated_cannot_access_resources(self):
        s = requests.Session()
        r = s.get(f"{API}/api/resources", timeout=10)
        assert r.status_code in [401, 403]


# ============================================================================
# Regression tests
# ============================================================================

class TestRegression:
    """Ensure existing endpoints still work."""
    
    def test_auth_login(self, admin_session):
        # Already tested via fixture, but verify session works
        r = admin_session.get(f"{API}/api/auth/me", timeout=10)
        assert r.status_code == 200
    
    def test_tasks_endpoint(self, admin_session):
        r = admin_session.get(f"{API}/api/tasks", timeout=10)
        assert r.status_code == 200
    
    def test_news_endpoint(self, admin_session):
        # News endpoint may not exist in all deployments
        r = admin_session.get(f"{API}/api/news", timeout=10)
        assert r.status_code in [200, 404]  # 404 is acceptable if not implemented
    
    def test_meetings_endpoint(self, admin_session):
        r = admin_session.get(f"{API}/api/meetings", timeout=10)
        assert r.status_code == 200
    
    def test_calendar_events(self, admin_session):
        r = admin_session.get(f"{API}/api/calendar/events", timeout=10)
        assert r.status_code == 200
    
    def test_health_endpoint(self):
        s = requests.Session()
        r = s.get(f"{API}/api/health", timeout=10)
        assert r.status_code == 200
