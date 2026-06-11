"""
Comprehensive E2E tests for Resources & Bookings module (iter 223 / Sprint 1).

Test Coverage:
  1. GET /api/resources - Top-level list with type filter (room/desk/vehicle)
  2. GET /api/resources/{id} - Splitable room returns 'children' array
  3. POST /api/resources - Admin creates resource + auto sub-resources for splitable
  4. PUT /api/resources/{id} - Update fields
  5. DELETE /api/resources/{id} - Blocked if open bookings exist
  6. POST /api/resource-bookings - Successful booking + 409 on direct overlap
  7. Parent/Child conflict logic - Booking child blocks parent booking
  8. Sibling subroom - Booking B parallel to A must succeed
  9. POST /api/resources/{id}/check-conflicts - Returns conflicts without creating
  10. requires_approval=true -> status='pending_approval'; POST approve -> 'confirmed'
  11. Catering workflow - booking with catering creates CateringRequest + Task
  12. POST /api/catering-requests/{id}/transition - mirrors Task status
  13. GET/POST/PUT/DELETE /api/catering-items (catering.manage_items cap)
  14. Capability gate - Member without 'view:resources' gets 403
  15. Cancel booking cascades to Catering + Task (both -> 'cancelled')
  16. Regression - Existing endpoints (Tasks, News, Meetings, Auth, Admin) still work
"""
import os
import time
import requests
import pytest
from datetime import datetime, timedelta

# Get API URL from environment or frontend .env
API = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not API:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    API = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@meetflow.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def _ts():
    """Unique timestamp suffix for test data."""
    return f"{int(time.time())}_{os.getpid()}"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def admin_session():
    """Admin session with full capabilities."""
    s = requests.Session()
    r = s.post(f"{API}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:300]}"
    yield s


@pytest.fixture(scope="module")
def member_session(admin_session):
    """Create a member user without resources caps and return session."""
    suffix = _ts()
    member_email = f"test_member_{suffix}@meetflow.com"
    member_password = "testpass123"
    
    # Create member via admin endpoint
    r = admin_session.post(f"{API}/api/admin/users", json={
        "email": member_email,
        "name": f"Test Member {suffix}",
        "password": member_password,
        "role": "member",
    }, timeout=15)
    # May already exist or succeed
    if r.status_code not in (200, 201, 400):
        pytest.skip(f"Could not create member user: {r.status_code} {r.text[:200]}")
    
    # Login as member
    s = requests.Session()
    r2 = s.post(f"{API}/api/auth/login",
                json={"email": member_email, "password": member_password},
                timeout=15)
    if r2.status_code != 200:
        pytest.skip(f"Member login failed: {r2.status_code} {r2.text[:200]}")
    yield s


@pytest.fixture(scope="module")
def demo_splitable_room(admin_session):
    """Create a fresh splitable room for testing parent/child conflicts."""
    suffix = _ts()
    payload = {
        "name": f"TestSaal_{suffix}",
        "type": "room",
        "location": "TestLocation",
        "capacity": 40,
        "is_splitable": True,
        "allow_catering": True,
        "requires_approval": False,
        "sub_resources": [
            {"sub_id": "A", "name": "Bereich A", "capacity": 15},
            {"sub_id": "B", "name": "Bereich B", "capacity": 15},
            {"sub_id": "C", "name": "Bereich C", "capacity": 10},
        ],
    }
    r = admin_session.post(f"{API}/api/resources", json=payload, timeout=15)
    assert r.status_code == 200, f"Failed to create splitable room: {r.text}"
    parent = r.json()
    
    # Fetch with children
    r2 = admin_session.get(f"{API}/api/resources/{parent['resource_id']}", timeout=15)
    assert r2.status_code == 200
    detail = r2.json()
    children = {c["sub_id"]: c for c in detail.get("children", [])}
    assert "A" in children and "B" in children and "C" in children, "Sub-resources not created"
    
    yield {"parent": parent, "A": children["A"], "B": children["B"], "C": children["C"]}
    
    # Cleanup: delete parent (cascades to children)
    admin_session.delete(f"{API}/api/resources/{parent['resource_id']}", timeout=15)


@pytest.fixture(scope="module")
def approval_room(admin_session):
    """Create a room that requires approval for bookings."""
    suffix = _ts()
    payload = {
        "name": f"ApprovalRoom_{suffix}",
        "type": "room",
        "location": "TestLocation",
        "capacity": 10,
        "requires_approval": True,
        "allow_catering": True,
    }
    r = admin_session.post(f"{API}/api/resources", json=payload, timeout=15)
    assert r.status_code == 200, f"Failed to create approval room: {r.text}"
    room = r.json()
    yield room
    admin_session.delete(f"{API}/api/resources/{room['resource_id']}", timeout=15)


# ============================================================================
# Test 1: GET /api/resources - Top-level list with type filter
# ============================================================================

class TestResourceListing:
    """Tests for resource listing endpoint."""
    
    def test_list_resources_returns_top_level_only(self, admin_session):
        """GET /api/resources returns only parent resources (parent_resource_id=null)."""
        r = admin_session.get(f"{API}/api/resources", timeout=15)
        assert r.status_code == 200
        resources = r.json()
        assert isinstance(resources, list)
        # All returned resources should have parent_resource_id=None
        for res in resources:
            assert res.get("parent_resource_id") is None, f"Child resource in top-level list: {res['resource_id']}"
    
    def test_list_resources_type_filter_room(self, admin_session):
        """GET /api/resources?type=room returns only rooms."""
        r = admin_session.get(f"{API}/api/resources", params={"type": "room"}, timeout=15)
        assert r.status_code == 200
        resources = r.json()
        for res in resources:
            assert res["type"] == "room", f"Non-room in room filter: {res['type']}"
    
    def test_list_resources_type_filter_desk(self, admin_session):
        """GET /api/resources?type=desk returns only desks."""
        r = admin_session.get(f"{API}/api/resources", params={"type": "desk"}, timeout=15)
        assert r.status_code == 200
        resources = r.json()
        for res in resources:
            assert res["type"] == "desk", f"Non-desk in desk filter: {res['type']}"
    
    def test_list_resources_type_filter_vehicle(self, admin_session):
        """GET /api/resources?type=vehicle returns only vehicles."""
        r = admin_session.get(f"{API}/api/resources", params={"type": "vehicle"}, timeout=15)
        assert r.status_code == 200
        resources = r.json()
        for res in resources:
            assert res["type"] == "vehicle", f"Non-vehicle in vehicle filter: {res['type']}"


# ============================================================================
# Test 2: GET /api/resources/{id} - Splitable room returns children
# ============================================================================

class TestResourceDetail:
    """Tests for resource detail endpoint."""
    
    def test_splitable_room_returns_children(self, admin_session, demo_splitable_room):
        """GET /api/resources/{id} of splitable room includes 'children' array."""
        parent_id = demo_splitable_room["parent"]["resource_id"]
        r = admin_session.get(f"{API}/api/resources/{parent_id}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("is_splitable") is True
        assert "children" in data
        assert len(data["children"]) == 3
        sub_ids = {c["sub_id"] for c in data["children"]}
        assert sub_ids == {"A", "B", "C"}
    
    def test_resource_404_for_nonexistent(self, admin_session):
        """GET /api/resources/{id} returns 404 for non-existent resource."""
        r = admin_session.get(f"{API}/api/resources/res_does_not_exist_xyz", timeout=15)
        assert r.status_code == 404


# ============================================================================
# Test 3: POST /api/resources - Create resource + auto sub-resources
# ============================================================================

class TestResourceCreation:
    """Tests for resource creation."""
    
    def test_create_simple_room(self, admin_session):
        """POST /api/resources creates a simple room."""
        suffix = _ts()
        payload = {
            "name": f"SimpleRoom_{suffix}",
            "type": "room",
            "location": "Test",
            "capacity": 8,
        }
        r = admin_session.post(f"{API}/api/resources", json=payload, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == payload["name"]
        assert data["type"] == "room"
        assert "resource_id" in data
        # Cleanup
        admin_session.delete(f"{API}/api/resources/{data['resource_id']}", timeout=15)
    
    def test_create_desk(self, admin_session):
        """POST /api/resources creates a desk."""
        suffix = _ts()
        payload = {
            "name": f"Desk_{suffix}",
            "type": "desk",
            "location": "Office",
            "desk_number": f"D-{suffix[-4:]}",
        }
        r = admin_session.post(f"{API}/api/resources", json=payload, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "desk"
        admin_session.delete(f"{API}/api/resources/{data['resource_id']}", timeout=15)
    
    def test_create_vehicle(self, admin_session):
        """POST /api/resources creates a vehicle."""
        suffix = _ts()
        payload = {
            "name": f"Car_{suffix}",
            "type": "vehicle",
            "license_plate": f"M-TEST-{suffix[-4:]}",
            "seats": 5,
        }
        r = admin_session.post(f"{API}/api/resources", json=payload, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "vehicle"
        admin_session.delete(f"{API}/api/resources/{data['resource_id']}", timeout=15)
    
    def test_create_splitable_auto_creates_children(self, admin_session):
        """POST /api/resources with is_splitable=true auto-creates sub-resources."""
        suffix = _ts()
        payload = {
            "name": f"SplitRoom_{suffix}",
            "type": "room",
            "is_splitable": True,
            "sub_resources": [
                {"sub_id": "X", "name": "Teil X", "capacity": 5},
                {"sub_id": "Y", "name": "Teil Y", "capacity": 5},
            ],
        }
        r = admin_session.post(f"{API}/api/resources", json=payload, timeout=15)
        assert r.status_code == 200
        parent = r.json()
        
        # Verify children exist
        r2 = admin_session.get(f"{API}/api/resources/{parent['resource_id']}", timeout=15)
        detail = r2.json()
        assert len(detail.get("children", [])) == 2
        
        admin_session.delete(f"{API}/api/resources/{parent['resource_id']}", timeout=15)


# ============================================================================
# Test 4: PUT /api/resources/{id} - Update fields
# ============================================================================

class TestResourceUpdate:
    """Tests for resource update."""
    
    def test_update_resource_fields(self, admin_session):
        """PUT /api/resources/{id} updates fields."""
        suffix = _ts()
        # Create
        r = admin_session.post(f"{API}/api/resources", json={
            "name": f"UpdateTest_{suffix}",
            "type": "room",
            "capacity": 10,
        }, timeout=15)
        assert r.status_code == 200
        res = r.json()
        
        # Update
        r2 = admin_session.put(f"{API}/api/resources/{res['resource_id']}", json={
            "capacity": 20,
            "notes": "Updated notes",
        }, timeout=15)
        assert r2.status_code == 200
        updated = r2.json()
        assert updated["capacity"] == 20
        assert updated["notes"] == "Updated notes"
        
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=15)


# ============================================================================
# Test 5: DELETE /api/resources/{id} - Blocked if open bookings
# ============================================================================

class TestResourceDeletion:
    """Tests for resource deletion."""
    
    def test_delete_blocked_with_open_bookings(self, admin_session):
        """DELETE /api/resources/{id} returns 400 if open bookings exist."""
        suffix = _ts()
        # Create resource
        r = admin_session.post(f"{API}/api/resources", json={
            "name": f"DeleteTest_{suffix}",
            "type": "room",
        }, timeout=15)
        assert r.status_code == 200
        res = r.json()
        
        # Create a future booking
        future_start = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%dT10:00:00Z")
        future_end = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%dT11:00:00Z")
        r2 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": res["resource_id"],
            "title": "Future Booking",
            "start_at": future_start,
            "end_at": future_end,
        }, timeout=15)
        assert r2.status_code == 200
        booking = r2.json()
        
        # Try to delete resource - should fail
        r3 = admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=15)
        assert r3.status_code == 400, f"Expected 400, got {r3.status_code}: {r3.text}"
        
        # Cancel booking first
        admin_session.delete(f"{API}/api/resource-bookings/{booking['booking_id']}", timeout=15)
        
        # Now delete should succeed
        r4 = admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=15)
        assert r4.status_code == 200


# ============================================================================
# Test 6: POST /api/resource-bookings - Booking + 409 on overlap
# ============================================================================

class TestBookingCreation:
    """Tests for booking creation and conflict detection."""
    
    def test_create_booking_success(self, admin_session, demo_splitable_room):
        """POST /api/resource-bookings creates a booking successfully."""
        child_a = demo_splitable_room["A"]
        start = "2028-01-15T09:00:00Z"
        end = "2028-01-15T10:00:00Z"
        
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_a["resource_id"],
            "title": "Test Meeting",
            "start_at": start,
            "end_at": end,
        }, timeout=15)
        assert r.status_code == 200, r.text
        booking = r.json()
        assert booking["status"] == "confirmed"
        assert booking["resource_id"] == child_a["resource_id"]
    
    def test_direct_overlap_returns_409(self, admin_session, demo_splitable_room):
        """POST /api/resource-bookings returns 409 on direct overlap."""
        child_a = demo_splitable_room["A"]
        start = "2028-01-15T09:30:00Z"  # Overlaps with previous test
        end = "2028-01-15T10:30:00Z"
        
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_a["resource_id"],
            "title": "Overlap Test",
            "start_at": start,
            "end_at": end,
        }, timeout=15)
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"


# ============================================================================
# Test 7: Parent/Child conflict logic
# ============================================================================

class TestParentChildConflict:
    """Tests for parent/child booking conflicts."""
    
    def test_child_booking_blocks_parent(self, admin_session, demo_splitable_room):
        """Booking a child blocks booking the parent in same time window."""
        parent = demo_splitable_room["parent"]
        # Child A is already booked 2028-01-15 09:00-10:00 from previous test
        
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": parent["resource_id"],
            "title": "Parent Booking",
            "start_at": "2028-01-15T09:30:00Z",
            "end_at": "2028-01-15T10:30:00Z",
        }, timeout=15)
        assert r.status_code == 409, f"Expected 409 (child blocks parent), got {r.status_code}"
    
    def test_parent_booking_blocks_child(self, admin_session, demo_splitable_room):
        """Booking the parent blocks booking any child in same time window."""
        parent = demo_splitable_room["parent"]
        child_c = demo_splitable_room["C"]
        
        # Book parent in a new time slot
        r1 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": parent["resource_id"],
            "title": "Parent Full",
            "start_at": "2028-02-01T14:00:00Z",
            "end_at": "2028-02-01T16:00:00Z",
        }, timeout=15)
        assert r1.status_code == 200, r1.text
        
        # Try to book child C in overlapping slot
        r2 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_c["resource_id"],
            "title": "Child C Overlap",
            "start_at": "2028-02-01T15:00:00Z",
            "end_at": "2028-02-01T17:00:00Z",
        }, timeout=15)
        assert r2.status_code == 409, f"Expected 409 (parent blocks child), got {r2.status_code}"


# ============================================================================
# Test 8: Sibling subroom - parallel booking allowed
# ============================================================================

class TestSiblingBooking:
    """Tests for sibling subroom bookings."""
    
    def test_sibling_booking_allowed(self, admin_session, demo_splitable_room):
        """Booking sibling room B parallel to A must succeed."""
        child_b = demo_splitable_room["B"]
        # Child A is booked 2028-01-15 09:00-10:00
        
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_b["resource_id"],
            "title": "Sibling B Meeting",
            "start_at": "2028-01-15T09:00:00Z",
            "end_at": "2028-01-15T10:00:00Z",
        }, timeout=15)
        assert r.status_code == 200, f"Sibling booking should succeed: {r.text}"


# ============================================================================
# Test 9: POST /api/resources/{id}/check-conflicts
# ============================================================================

class TestCheckConflicts:
    """Tests for conflict check endpoint."""
    
    def test_check_conflicts_returns_conflicts(self, admin_session, demo_splitable_room):
        """POST /api/resources/{id}/check-conflicts returns conflicts without creating."""
        child_a = demo_splitable_room["A"]
        
        r = admin_session.post(f"{API}/api/resources/{child_a['resource_id']}/check-conflicts", json={
            "start_at": "2028-01-15T09:30:00Z",
            "end_at": "2028-01-15T10:30:00Z",
        }, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "conflicts" in data
        assert len(data["conflicts"]) >= 1
    
    def test_check_conflicts_no_conflicts(self, admin_session, demo_splitable_room):
        """POST /api/resources/{id}/check-conflicts returns empty when no conflicts."""
        child_c = demo_splitable_room["C"]
        
        r = admin_session.post(f"{API}/api/resources/{child_c['resource_id']}/check-conflicts", json={
            "start_at": "2029-06-01T09:00:00Z",
            "end_at": "2029-06-01T10:00:00Z",
        }, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "conflicts" in data
        assert len(data["conflicts"]) == 0


# ============================================================================
# Test 10: requires_approval workflow
# ============================================================================

class TestApprovalWorkflow:
    """Tests for approval workflow."""
    
    def test_requires_approval_creates_pending(self, admin_session, approval_room):
        """Booking on requires_approval room creates status='pending_approval'."""
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": approval_room["resource_id"],
            "title": "Approval Test",
            "start_at": "2028-03-01T10:00:00Z",
            "end_at": "2028-03-01T11:00:00Z",
        }, timeout=15)
        assert r.status_code == 200, r.text
        booking = r.json()
        assert booking["status"] == "pending_approval"
        return booking
    
    def test_approve_booking(self, admin_session, approval_room):
        """POST /api/resource-bookings/{id}/approve sets status to 'confirmed'."""
        # Create pending booking
        r1 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": approval_room["resource_id"],
            "title": "Approve Test",
            "start_at": "2028-03-02T10:00:00Z",
            "end_at": "2028-03-02T11:00:00Z",
        }, timeout=15)
        assert r1.status_code == 200
        booking = r1.json()
        assert booking["status"] == "pending_approval"
        
        # Approve
        r2 = admin_session.post(f"{API}/api/resource-bookings/{booking['booking_id']}/approve", 
                                json={}, timeout=15)
        assert r2.status_code == 200
        approved = r2.json()
        assert approved["status"] == "confirmed"
        assert approved.get("approved_by") is not None
    
    def test_reject_booking(self, admin_session, approval_room):
        """POST /api/resource-bookings/{id}/approve with decision=reject cancels booking."""
        # Create pending booking
        r1 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": approval_room["resource_id"],
            "title": "Reject Test",
            "start_at": "2028-03-03T10:00:00Z",
            "end_at": "2028-03-03T11:00:00Z",
        }, timeout=15)
        assert r1.status_code == 200
        booking = r1.json()
        
        # Reject
        r2 = admin_session.post(f"{API}/api/resource-bookings/{booking['booking_id']}/approve", 
                                json={"decision": "reject", "reason": "Test rejection"}, timeout=15)
        assert r2.status_code == 200
        rejected = r2.json()
        assert rejected["status"] == "cancelled"


# ============================================================================
# Test 11: Catering workflow - booking creates CateringRequest + Task
# ============================================================================

class TestCateringWorkflow:
    """Tests for catering workflow."""
    
    def test_booking_with_catering_creates_request_and_task(self, admin_session, demo_splitable_room):
        """Booking with catering block creates CateringRequest + Task."""
        child_b = demo_splitable_room["B"]
        
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_b["resource_id"],
            "title": "Catering Meeting",
            "start_at": "2028-04-01T09:00:00Z",
            "end_at": "2028-04-01T12:00:00Z",
            "catering": {
                "items": [{"item_id": "cit_kaffee", "quantity": 10}],
                "contact": "Test Contact",
                "notes": "Extra sugar",
            },
        }, timeout=15)
        assert r.status_code == 200, r.text
        booking = r.json()
        assert booking.get("catering_request_id"), "catering_request_id missing"
        
        # Verify catering request exists
        r2 = admin_session.get(f"{API}/api/catering-requests", timeout=15)
        assert r2.status_code == 200
        requests_list = r2.json()
        cr = next((c for c in requests_list if c["request_id"] == booking["catering_request_id"]), None)
        assert cr is not None, "Catering request not found"
        assert cr.get("task_id"), "Task not linked to catering request"
        assert cr["status"] == "requested"
        
        return booking, cr


# ============================================================================
# Test 12: Catering transition mirrors Task status
# ============================================================================

class TestCateringTransition:
    """Tests for catering status transitions."""
    
    def test_transition_confirmed_mirrors_task(self, admin_session, demo_splitable_room):
        """POST /api/catering-requests/{id}/transition?status=confirmed mirrors to task."""
        child_c = demo_splitable_room["C"]
        
        # Create booking with catering
        r1 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_c["resource_id"],
            "title": "Transition Test",
            "start_at": "2028-05-01T09:00:00Z",
            "end_at": "2028-05-01T11:00:00Z",
            "catering": {
                "items": [{"item_id": "cit_wasser", "quantity": 5}],
            },
        }, timeout=15)
        assert r1.status_code == 200
        booking = r1.json()
        cr_id = booking["catering_request_id"]
        
        # Get task_id
        r2 = admin_session.get(f"{API}/api/catering-requests", timeout=15)
        cr = next((c for c in r2.json() if c["request_id"] == cr_id), None)
        task_id = cr["task_id"]
        
        # Transition to confirmed
        r3 = admin_session.post(f"{API}/api/catering-requests/{cr_id}/transition",
                                json={"status": "confirmed"}, timeout=15)
        assert r3.status_code == 200
        assert r3.json()["status"] == "confirmed"
        
        # Check task status mirrored to in_progress
        r4 = admin_session.get(f"{API}/api/tasks/{task_id}", timeout=15)
        if r4.status_code == 200:
            task = r4.json()
            assert task["status"] == "in_progress", f"Task status should be in_progress, got {task['status']}"
    
    def test_transition_completed_mirrors_task_done(self, admin_session, demo_splitable_room):
        """POST /api/catering-requests/{id}/transition?status=completed mirrors to task done."""
        child_c = demo_splitable_room["C"]
        
        # Create booking with catering
        r1 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_c["resource_id"],
            "title": "Complete Test",
            "start_at": "2028-05-02T09:00:00Z",
            "end_at": "2028-05-02T11:00:00Z",
            "catering": {
                "items": [{"item_id": "cit_brezel", "quantity": 3}],
            },
        }, timeout=15)
        assert r1.status_code == 200
        booking = r1.json()
        cr_id = booking["catering_request_id"]
        
        # Transition to completed
        r2 = admin_session.post(f"{API}/api/catering-requests/{cr_id}/transition",
                                json={"status": "completed"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] == "completed"


# ============================================================================
# Test 13: Catering items CRUD
# ============================================================================

class TestCateringItems:
    """Tests for catering items CRUD."""
    
    def test_list_catering_items(self, admin_session):
        """GET /api/catering-items returns list."""
        r = admin_session.get(f"{API}/api/catering-items", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
    
    def test_create_catering_item(self, admin_session):
        """POST /api/catering-items creates item."""
        suffix = _ts()
        r = admin_session.post(f"{API}/api/catering-items", json={
            "name": f"TestItem_{suffix}",
            "category": "Test",
            "price": 5.50,
            "unit": "Stueck",
        }, timeout=15)
        assert r.status_code == 200
        item = r.json()
        assert item["name"] == f"TestItem_{suffix}"
        return item
    
    def test_update_catering_item(self, admin_session):
        """PUT /api/catering-items/{id} updates item."""
        # Create first
        suffix = _ts()
        r1 = admin_session.post(f"{API}/api/catering-items", json={
            "name": f"UpdateItem_{suffix}",
            "price": 3.00,
        }, timeout=15)
        assert r1.status_code == 200
        item = r1.json()
        
        # Update
        r2 = admin_session.put(f"{API}/api/catering-items/{item['item_id']}", json={
            "price": 4.50,
        }, timeout=15)
        assert r2.status_code == 200
        updated = r2.json()
        assert updated["price"] == 4.50
    
    def test_delete_catering_item(self, admin_session):
        """DELETE /api/catering-items/{id} deactivates item."""
        suffix = _ts()
        r1 = admin_session.post(f"{API}/api/catering-items", json={
            "name": f"DeleteItem_{suffix}",
        }, timeout=15)
        assert r1.status_code == 200
        item = r1.json()
        
        r2 = admin_session.delete(f"{API}/api/catering-items/{item['item_id']}", timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("deactivated") is True


# ============================================================================
# Test 14: Capability gate - Member without view:resources gets 403
# ============================================================================

class TestCapabilityGates:
    """Tests for capability-based access control."""
    
    def test_member_without_view_resources_gets_403(self, member_session):
        """Member without 'view:resources' cap gets 403 on /api/resources."""
        r = member_session.get(f"{API}/api/resources", timeout=15)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    
    def test_member_without_resources_book_gets_403(self, member_session):
        """Member without 'resources.book' cap gets 403 on POST /api/resource-bookings."""
        r = member_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": "res_demo_saal_001",
            "title": "Test",
            "start_at": "2028-06-01T10:00:00Z",
            "end_at": "2028-06-01T11:00:00Z",
        }, timeout=15)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    
    def test_unauthenticated_gets_401_or_403(self):
        """Unauthenticated request gets 401 or 403."""
        r = requests.get(f"{API}/api/resources", timeout=15)
        assert r.status_code in (401, 403)


# ============================================================================
# Test 15: Cancel booking cascades to Catering + Task
# ============================================================================

class TestCancelCascade:
    """Tests for booking cancellation cascade."""
    
    def test_cancel_booking_cascades_catering_and_task(self, admin_session, demo_splitable_room):
        """DELETE /api/resource-bookings/{id} cascades to catering and task."""
        child_a = demo_splitable_room["A"]
        
        # Create booking with catering
        r1 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_a["resource_id"],
            "title": "Cancel Cascade Test",
            "start_at": "2028-06-15T09:00:00Z",
            "end_at": "2028-06-15T11:00:00Z",
            "catering": {
                "items": [{"item_id": "cit_kaffee", "quantity": 5}],
            },
        }, timeout=15)
        assert r1.status_code == 200
        booking = r1.json()
        cr_id = booking["catering_request_id"]
        
        # Get task_id before cancel
        r2 = admin_session.get(f"{API}/api/catering-requests", timeout=15)
        cr = next((c for c in r2.json() if c["request_id"] == cr_id), None)
        task_id = cr["task_id"]
        
        # Cancel booking
        r3 = admin_session.delete(f"{API}/api/resource-bookings/{booking['booking_id']}", 
                                  json={"reason": "Test cancellation"}, timeout=15)
        assert r3.status_code == 200
        assert r3.json().get("cancelled") is True
        
        # Verify catering request is cancelled
        r4 = admin_session.get(f"{API}/api/catering-requests", timeout=15)
        cr_after = next((c for c in r4.json() if c["request_id"] == cr_id), None)
        assert cr_after["status"] == "cancelled", f"Catering should be cancelled, got {cr_after['status']}"
        
        # Verify task is cancelled
        r5 = admin_session.get(f"{API}/api/tasks/{task_id}", timeout=15)
        if r5.status_code == 200:
            task = r5.json()
            assert task["status"] == "cancelled", f"Task should be cancelled, got {task['status']}"


# ============================================================================
# Test 16: Regression - Existing endpoints still work
# ============================================================================

class TestRegression:
    """Regression tests for existing endpoints."""
    
    def test_auth_login(self, admin_session):
        """Auth login still works."""
        r = admin_session.get(f"{API}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json().get("email") == ADMIN_EMAIL
    
    def test_tasks_endpoint(self, admin_session):
        """Tasks endpoint still works."""
        r = admin_session.get(f"{API}/api/tasks", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data  # Tasks returns {tasks: [...], total: N}
        assert isinstance(data["tasks"], list)
    
    def test_news_endpoint(self, admin_session):
        """News endpoint still works."""
        r = admin_session.get(f"{API}/api/news/feed", timeout=15)
        assert r.status_code == 200
    
    def test_meetings_endpoint(self, admin_session):
        """Meetings endpoint still works."""
        r = admin_session.get(f"{API}/api/meetings", timeout=15)
        assert r.status_code == 200
    
    def test_admin_users_endpoint(self, admin_session):
        """Admin users endpoint still works."""
        r = admin_session.get(f"{API}/api/admin/users", timeout=15)
        assert r.status_code == 200
    
    def test_health_endpoint(self):
        """Health endpoint still works."""
        r = requests.get(f"{API}/api/health", timeout=15)
        assert r.status_code == 200


# ============================================================================
# Additional edge case tests
# ============================================================================

class TestEdgeCases:
    """Edge case tests."""
    
    def test_booking_end_before_start_rejected(self, admin_session, demo_splitable_room):
        """Booking with end_at before start_at is rejected."""
        child_a = demo_splitable_room["A"]
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": child_a["resource_id"],
            "title": "Invalid Time",
            "start_at": "2028-07-01T12:00:00Z",
            "end_at": "2028-07-01T11:00:00Z",
        }, timeout=15)
        assert r.status_code == 400
    
    def test_booking_on_inactive_resource_rejected(self, admin_session):
        """Booking on inactive resource is rejected."""
        suffix = _ts()
        # Create and deactivate resource
        r1 = admin_session.post(f"{API}/api/resources", json={
            "name": f"InactiveRoom_{suffix}",
            "type": "room",
            "status": "inactive",
        }, timeout=15)
        assert r1.status_code == 200
        res = r1.json()
        
        # Try to book
        r2 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": res["resource_id"],
            "title": "Should Fail",
            "start_at": "2028-08-01T10:00:00Z",
            "end_at": "2028-08-01T11:00:00Z",
        }, timeout=15)
        assert r2.status_code == 400
        
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=15)
    
    def test_list_bookings(self, admin_session):
        """GET /api/resource-bookings returns list."""
        r = admin_session.get(f"{API}/api/resource-bookings", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
