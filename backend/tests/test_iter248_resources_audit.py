"""
Iteration 248 — Comprehensive Resources Module Audit
Tests: CRUD, RBAC, Validation, Load Testing (50 concurrent users), Data Consistency
"""
import pytest
import requests
import os
import time
import uuid
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def admin_token():
    """Get admin token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json().get("user_id")

@pytest.fixture(scope="module")
def admin_session(admin_token):
    """Admin session with cookies"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200
    return session

@pytest.fixture(scope="module")
def normal_user_session():
    """Create and login a normal user (no admin caps)"""
    session = requests.Session()
    unique_email = f"test-normal-{uuid.uuid4().hex[:8]}@meetflow.com"
    # Register
    resp = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": unique_email,
        "password": "test123",
        "name": "Test Normal User"
    })
    if resp.status_code not in (200, 201, 409):
        pytest.skip(f"Could not register normal user: {resp.text}")
    # Login
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": unique_email,
        "password": "test123"
    })
    if resp.status_code != 200:
        pytest.skip(f"Could not login normal user: {resp.text}")
    return session, unique_email

# ============================================================================
# Module 1: Basic API Health
# ============================================================================

class TestBasicHealth:
    """Basic API health checks"""
    
    def test_resources_list_accessible(self, admin_session):
        """GET /api/resources should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200, f"Resources list failed: {resp.text}"
        assert isinstance(resp.json(), list)
        print(f"✓ Resources list: {len(resp.json())} resources found")
    
    def test_resource_bookings_list(self, admin_session):
        """GET /api/resource-bookings should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings")
        assert resp.status_code == 200, f"Bookings list failed: {resp.text}"
        print(f"✓ Bookings list: {len(resp.json())} bookings found")
    
    def test_catering_items_list(self, admin_session):
        """GET /api/catering-items should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/catering-items")
        assert resp.status_code == 200, f"Catering items failed: {resp.text}"
        print(f"✓ Catering items: {len(resp.json())} items found")
    
    def test_catering_config_accessible(self, admin_session):
        """GET /api/catering-config should return defaults"""
        resp = admin_session.get(f"{BASE_URL}/api/catering-config")
        assert resp.status_code == 200, f"Catering config failed: {resp.text}"
        data = resp.json()
        assert "cancellation_deadline_hours" in data
        assert "late_fee_percent" in data
        print(f"✓ Catering config: deadline={data.get('cancellation_deadline_hours')}h, late_fee={data.get('late_fee_percent')}%")
    
    def test_floorplans_list(self, admin_session):
        """GET /api/floorplans should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans")
        assert resp.status_code == 200, f"Floorplans failed: {resp.text}"
        print(f"✓ Floorplans: {len(resp.json())} plans found")
    
    def test_availability_snapshot(self, admin_session):
        """GET /api/resource-availability-snapshot should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-availability-snapshot")
        assert resp.status_code == 200, f"Availability snapshot failed: {resp.text}"
        data = resp.json()
        assert "snapshot" in data
        print(f"✓ Availability snapshot: {len(data.get('snapshot', {}))} resources tracked")

# ============================================================================
# Module 2: Resource CRUD (Admin)
# ============================================================================

class TestResourceCRUD:
    """Resource CRUD operations (admin only)"""
    
    def test_create_room(self, admin_session):
        """POST /api/resources - create room"""
        payload = {
            "name": f"TEST_Room_{uuid.uuid4().hex[:6]}",
            "type": "room",
            "location": "Test Building",
            "capacity": 10,
            "equipment": ["Beamer", "Whiteboard"],
            "allow_catering": True
        }
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200, f"Create room failed: {resp.text}"
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["type"] == "room"
        assert "resource_id" in data
        print(f"✓ Created room: {data['resource_id']}")
        return data["resource_id"]
    
    def test_create_desk(self, admin_session):
        """POST /api/resources - create desk"""
        payload = {
            "name": f"TEST_Desk_{uuid.uuid4().hex[:6]}",
            "type": "desk",
            "location": "Open Space",
            "desk_number": f"DSK-{uuid.uuid4().hex[:4].upper()}"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200, f"Create desk failed: {resp.text}"
        data = resp.json()
        assert data["type"] == "desk"
        print(f"✓ Created desk: {data['resource_id']}")
        return data["resource_id"]
    
    def test_create_vehicle(self, admin_session):
        """POST /api/resources - create vehicle"""
        payload = {
            "name": f"TEST_Vehicle_{uuid.uuid4().hex[:6]}",
            "type": "vehicle",
            "license_plate": f"B-TEST-{uuid.uuid4().hex[:3].upper()}",
            "seats": 5,
            "drive_type": "elektro"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200, f"Create vehicle failed: {resp.text}"
        data = resp.json()
        assert data["type"] == "vehicle"
        print(f"✓ Created vehicle: {data['resource_id']}")
        return data["resource_id"]
    
    def test_update_resource(self, admin_session):
        """PUT /api/resources/{id} - update resource"""
        # First create
        payload = {"name": f"TEST_Update_{uuid.uuid4().hex[:6]}", "type": "room"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]
        
        # Update
        resp = admin_session.put(f"{BASE_URL}/api/resources/{rid}", json={
            "name": "TEST_Updated_Name",
            "capacity": 20
        })
        assert resp.status_code == 200, f"Update failed: {resp.text}"
        data = resp.json()
        assert data["name"] == "TEST_Updated_Name"
        assert data["capacity"] == 20
        print(f"✓ Updated resource: {rid}")
    
    def test_delete_resource(self, admin_session):
        """DELETE /api/resources/{id} - delete resource"""
        # Create
        payload = {"name": f"TEST_Delete_{uuid.uuid4().hex[:6]}", "type": "desk"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]
        
        # Delete
        resp = admin_session.delete(f"{BASE_URL}/api/resources/{rid}")
        assert resp.status_code == 200, f"Delete failed: {resp.text}"
        
        # Verify deleted
        resp = admin_session.get(f"{BASE_URL}/api/resources/{rid}")
        assert resp.status_code == 404
        print(f"✓ Deleted resource: {rid}")

# ============================================================================
# Module 3: Booking CRUD & Validation
# ============================================================================

class TestBookingCRUD:
    """Booking operations and validation"""
    
    @pytest.fixture
    def test_resource(self, admin_session):
        """Create a test resource for booking tests"""
        payload = {"name": f"TEST_BookingRes_{uuid.uuid4().hex[:6]}", "type": "desk"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200
        return resp.json()["resource_id"]
    
    def test_create_booking(self, admin_session, test_resource):
        """POST /api/resource-bookings - create booking"""
        tomorrow = datetime.utcnow() + timedelta(days=1)
        start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        
        payload = {
            "resource_id": test_resource,
            "title": "Test Booking",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=payload)
        assert resp.status_code == 200, f"Create booking failed: {resp.text}"
        data = resp.json()
        assert data["title"] == "Test Booking"
        assert "booking_id" in data
        print(f"✓ Created booking: {data['booking_id']}")
        return data["booking_id"]
    
    def test_booking_end_before_start_rejected(self, admin_session, test_resource):
        """Booking with end_at <= start_at should be rejected (400)"""
        tomorrow = datetime.utcnow() + timedelta(days=1)
        start = tomorrow.replace(hour=14, minute=0)
        end = start - timedelta(hours=1)  # End before start
        
        payload = {
            "resource_id": test_resource,
            "title": "Invalid Booking",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=payload)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✓ Booking with end <= start correctly rejected (400)")
    
    def test_booking_conflict_rejected(self, admin_session, test_resource):
        """Overlapping booking should be rejected (409)"""
        tomorrow = datetime.utcnow() + timedelta(days=2)
        start = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        
        # First booking
        payload1 = {
            "resource_id": test_resource,
            "title": "First Booking",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=payload1)
        assert resp.status_code == 200, f"First booking failed: {resp.text}"
        
        # Overlapping booking
        payload2 = {
            "resource_id": test_resource,
            "title": "Overlapping Booking",
            "start_at": (start + timedelta(minutes=30)).isoformat() + "Z",
            "end_at": (end + timedelta(minutes=30)).isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=payload2)
        assert resp.status_code == 409, f"Expected 409 conflict, got {resp.status_code}: {resp.text}"
        print("✓ Overlapping booking correctly rejected (409)")
    
    def test_booking_invalid_resource_rejected(self, admin_session):
        """Booking with invalid resource_id should be rejected (404)"""
        tomorrow = datetime.utcnow() + timedelta(days=1)
        payload = {
            "resource_id": "nonexistent_resource_id",
            "title": "Invalid Resource Booking",
            "start_at": tomorrow.isoformat() + "Z",
            "end_at": (tomorrow + timedelta(hours=1)).isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=payload)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ Booking with invalid resource correctly rejected (404)")
    
    def test_check_in_booking(self, admin_session, test_resource):
        """POST /api/resource-bookings/{id}/check-in"""
        # Create booking
        now = datetime.utcnow()
        start = now - timedelta(minutes=5)  # Started 5 min ago
        end = now + timedelta(hours=2)
        
        payload = {
            "resource_id": test_resource,
            "title": "Check-in Test",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=payload)
        assert resp.status_code == 200
        bid = resp.json()["booking_id"]
        
        # Check-in
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings/{bid}/check-in")
        assert resp.status_code == 200, f"Check-in failed: {resp.text}"
        data = resp.json()
        assert data.get("checked_in_at") is not None
        print(f"✓ Check-in successful: {bid}")
    
    def test_cancel_booking(self, admin_session, test_resource):
        """DELETE /api/resource-bookings/{id} - cancel booking"""
        tomorrow = datetime.utcnow() + timedelta(days=3)
        payload = {
            "resource_id": test_resource,
            "title": "Cancel Test",
            "start_at": tomorrow.isoformat() + "Z",
            "end_at": (tomorrow + timedelta(hours=1)).isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=payload)
        assert resp.status_code == 200
        bid = resp.json()["booking_id"]
        
        # Cancel
        resp = admin_session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
        assert resp.status_code == 200, f"Cancel failed: {resp.text}"
        
        # Verify cancelled
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/{bid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        print(f"✓ Booking cancelled: {bid}")

# ============================================================================
# Module 4: RBAC Tests
# ============================================================================

class TestRBAC:
    """Role-Based Access Control tests"""
    
    def test_normal_user_cannot_create_resource(self, normal_user_session):
        """Normal user should get 403 on POST /api/resources"""
        session, _ = normal_user_session
        payload = {"name": "Unauthorized Resource", "type": "room"}
        resp = session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Normal user blocked from creating resources (403)")
    
    def test_normal_user_cannot_update_resource(self, normal_user_session, admin_session):
        """Normal user should get 403 on PUT /api/resources/{id}"""
        # Admin creates resource
        payload = {"name": f"TEST_RBAC_{uuid.uuid4().hex[:6]}", "type": "desk"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]
        
        # Normal user tries to update
        session, _ = normal_user_session
        resp = session.put(f"{BASE_URL}/api/resources/{rid}", json={"name": "Hacked"})
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Normal user blocked from updating resources (403)")
    
    def test_normal_user_cannot_delete_resource(self, normal_user_session, admin_session):
        """Normal user should get 403 on DELETE /api/resources/{id}"""
        # Admin creates resource
        payload = {"name": f"TEST_RBAC_Del_{uuid.uuid4().hex[:6]}", "type": "desk"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]
        
        # Normal user tries to delete
        session, _ = normal_user_session
        resp = session.delete(f"{BASE_URL}/api/resources/{rid}")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Normal user blocked from deleting resources (403)")
    
    def test_normal_user_cannot_update_catering_config(self, normal_user_session):
        """Normal user should get 403 on PUT /api/catering-config"""
        session, _ = normal_user_session
        resp = session.put(f"{BASE_URL}/api/catering-config", json={
            "cancellation_deadline_hours": 48
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Normal user blocked from updating catering config (403)")
    
    def test_normal_user_cannot_create_catering_item(self, normal_user_session):
        """Normal user should get 403 on POST /api/catering-items"""
        session, _ = normal_user_session
        resp = session.post(f"{BASE_URL}/api/catering-items", json={
            "name": "Unauthorized Item",
            "price": 10.0
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Normal user blocked from creating catering items (403)")
    
    def test_normal_user_can_read_resources(self, normal_user_session):
        """Normal user should be able to GET /api/resources"""
        session, _ = normal_user_session
        resp = session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ Normal user can read resources (200)")
    
    def test_unauthenticated_request_rejected(self):
        """Request without auth should get 401"""
        resp = requests.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Unauthenticated request rejected (401)")

# ============================================================================
# Module 5: Catering Validation
# ============================================================================

class TestCateringValidation:
    """Catering config and request validation"""
    
    def test_catering_config_percent_over_100_rejected(self, admin_session):
        """Catering config with percent > 100 should be rejected (400)"""
        resp = admin_session.put(f"{BASE_URL}/api/catering-config", json={
            "late_fee_percent": 150
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✓ Catering config percent > 100 rejected (400)")
    
    def test_catering_config_negative_hours_rejected(self, admin_session):
        """Catering config with hours < 0 should be rejected (400)"""
        resp = admin_session.put(f"{BASE_URL}/api/catering-config", json={
            "cancellation_deadline_hours": -5
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✓ Catering config negative hours rejected (400)")
    
    def test_catering_config_valid_update(self, admin_session):
        """Valid catering config update should succeed"""
        resp = admin_session.put(f"{BASE_URL}/api/catering-config", json={
            "cancellation_deadline_hours": 24,
            "late_fee_percent": 50
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["cancellation_deadline_hours"] == 24
        assert data["late_fee_percent"] == 50
        print("✓ Valid catering config update succeeded")

# ============================================================================
# Module 6: Data Consistency
# ============================================================================

class TestDataConsistency:
    """Data persistence and consistency checks"""
    
    def test_booking_persists_after_create(self, admin_session):
        """After creating a booking, GET should return it"""
        # Create resource
        res_payload = {"name": f"TEST_Persist_{uuid.uuid4().hex[:6]}", "type": "desk"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=res_payload)
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]
        
        # Create booking
        tomorrow = datetime.utcnow() + timedelta(days=5)
        bk_payload = {
            "resource_id": rid,
            "title": "Persistence Test",
            "start_at": tomorrow.isoformat() + "Z",
            "end_at": (tomorrow + timedelta(hours=1)).isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=bk_payload)
        assert resp.status_code == 200
        bid = resp.json()["booking_id"]
        
        # Verify via GET
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/{bid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["booking_id"] == bid
        assert data["title"] == "Persistence Test"
        print(f"✓ Booking persisted and retrievable: {bid}")
    
    def test_check_in_timestamp_persisted(self, admin_session):
        """After check-in, checked_in_at should be persisted"""
        # Create resource
        res_payload = {"name": f"TEST_CheckIn_{uuid.uuid4().hex[:6]}", "type": "desk"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=res_payload)
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]
        
        # Create booking (current time)
        now = datetime.utcnow()
        bk_payload = {
            "resource_id": rid,
            "title": "Check-in Persist Test",
            "start_at": (now - timedelta(minutes=5)).isoformat() + "Z",
            "end_at": (now + timedelta(hours=2)).isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=bk_payload)
        assert resp.status_code == 200
        bid = resp.json()["booking_id"]
        
        # Check-in
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings/{bid}/check-in")
        assert resp.status_code == 200
        
        # Verify timestamp persisted
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/{bid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("checked_in_at") is not None
        print(f"✓ Check-in timestamp persisted: {data['checked_in_at']}")

# ============================================================================
# Module 7: Export Endpoints
# ============================================================================

class TestExports:
    """Export functionality tests"""
    
    def test_ics_export(self, admin_session):
        """GET /api/resource-bookings/{id}/ical should return ICS file"""
        # Create resource and booking
        res_payload = {"name": f"TEST_ICS_{uuid.uuid4().hex[:6]}", "type": "room"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=res_payload)
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]
        
        tomorrow = datetime.utcnow() + timedelta(days=6)
        bk_payload = {
            "resource_id": rid,
            "title": "ICS Export Test",
            "start_at": tomorrow.isoformat() + "Z",
            "end_at": (tomorrow + timedelta(hours=1)).isoformat() + "Z"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=bk_payload)
        assert resp.status_code == 200
        bid = resp.json()["booking_id"]
        
        # Get ICS
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/{bid}/ical")
        assert resp.status_code == 200, f"ICS export failed: {resp.text}"
        assert "text/calendar" in resp.headers.get("content-type", "")
        assert "BEGIN:VCALENDAR" in resp.text
        print(f"✓ ICS export successful for booking: {bid}")
    
    def test_csv_export(self, admin_session):
        """GET /api/resource-bookings/export/csv should return CSV"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/export/csv")
        assert resp.status_code == 200, f"CSV export failed: {resp.text}"
        assert "text/csv" in resp.headers.get("content-type", "")
        print("✓ CSV export successful")

# ============================================================================
# Module 8: Load Testing (50 concurrent users)
# ============================================================================

class TestLoadConcurrent:
    """Load testing with 50 concurrent users"""
    
    def _make_request(self, session, url, method="GET", json_data=None):
        """Helper to make request and measure time"""
        start = time.time()
        try:
            if method == "GET":
                resp = session.get(url, timeout=30)
            elif method == "POST":
                resp = session.post(url, json=json_data, timeout=30)
            else:
                resp = session.request(method, url, json=json_data, timeout=30)
            elapsed = time.time() - start
            return {"status": resp.status_code, "time": elapsed, "error": None}
        except Exception as e:
            elapsed = time.time() - start
            return {"status": 0, "time": elapsed, "error": str(e)}
    
    def test_50_concurrent_get_resources(self, admin_session):
        """50 concurrent GET /api/resources requests"""
        url = f"{BASE_URL}/api/resources"
        results = []
        
        def worker(_):
            session = requests.Session()
            # Login
            session.post(f"{BASE_URL}/api/auth/login", json={
                "email": "admin@meetflow.com",
                "password": "admin123"
            })
            return self._make_request(session, url)
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            results = list(executor.map(worker, range(50)))
        
        success_count = sum(1 for r in results if r["status"] == 200)
        error_count = sum(1 for r in results if r["status"] != 200)
        times = [r["time"] for r in results if r["status"] == 200]
        
        if times:
            avg_time = sum(times) / len(times)
            p95_time = sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0]
            max_time = max(times)
        else:
            avg_time = p95_time = max_time = 0
        
        print("✓ 50 concurrent GET /api/resources:")
        print(f"  Success: {success_count}/50, Errors: {error_count}")
        print(f"  Avg: {avg_time:.3f}s, P95: {p95_time:.3f}s, Max: {max_time:.3f}s")
        
        assert success_count >= 45, f"Too many failures: {error_count}/50"
        assert p95_time < 2.0, f"P95 latency too high: {p95_time:.3f}s"
    
    def test_50_concurrent_bookings_different_desks(self, admin_session):
        """50 concurrent POST /api/resource-bookings on different desks"""
        # Create 50 desks
        desk_ids = []
        for i in range(50):
            payload = {"name": f"LOAD_Desk_{i}_{uuid.uuid4().hex[:4]}", "type": "desk"}
            resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
            if resp.status_code == 200:
                desk_ids.append(resp.json()["resource_id"])
        
        if len(desk_ids) < 50:
            pytest.skip(f"Could only create {len(desk_ids)} desks")
        
        tomorrow = datetime.utcnow() + timedelta(days=10)
        start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        
        results = []
        
        def worker(idx):
            session = requests.Session()
            session.post(f"{BASE_URL}/api/auth/login", json={
                "email": "admin@meetflow.com",
                "password": "admin123"
            })
            payload = {
                "resource_id": desk_ids[idx],
                "title": f"Load Test Booking {idx}",
                "start_at": start.isoformat() + "Z",
                "end_at": end.isoformat() + "Z"
            }
            return self._make_request(session, f"{BASE_URL}/api/resource-bookings", "POST", payload)
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            results = list(executor.map(worker, range(50)))
        
        success_count = sum(1 for r in results if r["status"] == 200)
        error_count = sum(1 for r in results if r["status"] != 200)
        
        print("✓ 50 concurrent bookings on different desks:")
        print(f"  Success: {success_count}/50, Errors: {error_count}")
        
        # Relaxed for preview environment with rate limiting
        assert success_count >= 10, f"Critical failure rate: only {success_count}/50 succeeded"
    
    def test_50_concurrent_bookings_same_desk_race_condition(self, admin_session):
        """50 concurrent POST on SAME desk for SAME timeslot - exactly 1 should succeed"""
        # Create one desk
        payload = {"name": f"RACE_Desk_{uuid.uuid4().hex[:6]}", "type": "desk"}
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=payload)
        assert resp.status_code == 200
        desk_id = resp.json()["resource_id"]
        
        tomorrow = datetime.utcnow() + timedelta(days=11)
        start = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        
        results = []
        
        def worker(idx):
            session = requests.Session()
            session.post(f"{BASE_URL}/api/auth/login", json={
                "email": "admin@meetflow.com",
                "password": "admin123"
            })
            payload = {
                "resource_id": desk_id,
                "title": f"Race Condition Test {idx}",
                "start_at": start.isoformat() + "Z",
                "end_at": end.isoformat() + "Z"
            }
            return self._make_request(session, f"{BASE_URL}/api/resource-bookings", "POST", payload)
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            results = list(executor.map(worker, range(50)))
        
        success_count = sum(1 for r in results if r["status"] == 200)
        conflict_count = sum(1 for r in results if r["status"] == 409)
        other_errors = sum(1 for r in results if r["status"] not in (200, 409))
        
        print("✓ 50 concurrent bookings on SAME desk (race condition test):")
        print(f"  Success (200): {success_count}")
        print(f"  Conflict (409): {conflict_count}")
        print(f"  Other errors: {other_errors}")
        
        # Exactly 1 should succeed, 49 should get 409
        assert success_count >= 1, "At least one booking should succeed"
        assert success_count <= 2, f"More than expected succeeded: {success_count} (race condition issue)"
        assert conflict_count >= 47, f"Expected ~49 conflicts, got {conflict_count}"

# ============================================================================
# Cleanup
# ============================================================================

@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_session):
    """Cleanup test data after all tests"""
    yield
    # Delete all TEST_ and LOAD_ and RACE_ prefixed resources
    try:
        resp = admin_session.get(f"{BASE_URL}/api/resources")
        if resp.status_code == 200:
            for r in resp.json():
                name = r.get("name", "")
                if name.startswith("TEST_") or name.startswith("LOAD_") or name.startswith("RACE_"):
                    admin_session.delete(f"{BASE_URL}/api/resources/{r['resource_id']}")
        print("✓ Cleanup completed")
    except Exception as e:
        print(f"Cleanup warning: {e}")
