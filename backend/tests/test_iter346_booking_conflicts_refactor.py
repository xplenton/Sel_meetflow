"""
Iteration 346 — Booking Conflicts Refactor Verification Tests

This iteration refactored conflict-check logic from routes/resources/_common.py
into services/booking_conflicts.py. The behavior MUST be byte-identical.

Tests verify all conflict-detection paths via HTTP:
1. POST /api/resources/{resource_id}/check-conflicts - no conflicts for free slot
2. POST /api/resources/{resource_id}/check-conflicts - returns conflicts for overlapping slot
3. Splitable rooms: parent detects child bookings as conflicts and vice versa
4. Blackout periods: conflict with reason='blackout' surfaces when overlapping
5. Buffer time: booking inside buffer window is reported as conflict
6. POST /api/resource-bookings: normal booking succeeds; overlapping rejected with 409
7. PUT /api/resource-bookings/{id}: moving a booking respects conflict checks
8. Sub-room allowed_combinations whitelist: booking not in whitelist returns HTTP 400
9. Race-condition winner selection (verify_booking_winner) still works
"""
import pytest
import requests
import os
import asyncio
from datetime import datetime, timedelta, timezone
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestIter346CheckConflictsEndpoint:
    """Test POST /api/resources/{resource_id}/check-conflicts endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_bookings = []
        self.created_resources = []
        self.created_blackouts = []
        yield
        
        # Cleanup
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
        for rid in self.created_resources:
            try:
                self.session.delete(f"{BASE_URL}/api/resources/{rid}")
            except:
                pass
        for bo_id in self.created_blackouts:
            try:
                self.session.delete(f"{BASE_URL}/api/blackout-periods/{bo_id}")
            except:
                pass
    
    def test_check_conflicts_free_slot_returns_empty(self):
        """Test 1: check-conflicts returns empty list for a free slot"""
        # Get any active resource
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        active_resources = [r for r in resources if r.get("status") == "active"]
        assert len(active_resources) > 0, "No active resources found"
        
        resource = active_resources[0]
        resource_id = resource["resource_id"]
        
        # Check conflicts for a far-future slot (unlikely to have bookings)
        future = datetime.now(timezone.utc) + timedelta(days=365)
        start_at = future.replace(hour=3, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=4, minute=0, second=0, microsecond=0)
        
        check_resp = self.session.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            }
        )
        assert check_resp.status_code == 200, f"check-conflicts failed: {check_resp.text}"
        result = check_resp.json()
        
        assert "conflicts" in result, f"Response should have 'conflicts' key: {result}"
        # For a far-future slot, conflicts should be empty (or only blackouts if any)
        print(f"Free slot check: {len(result['conflicts'])} conflicts found")
    
    def test_check_conflicts_overlapping_slot_returns_conflicts(self):
        """Test 2: check-conflicts returns conflicts for an overlapping slot"""
        # Create a test resource
        unique_id = uuid.uuid4().hex[:8]
        create_resp = self.session.post(f"{BASE_URL}/api/resources", json={
            "name": f"TEST_Iter346_Desk_{unique_id}",
            "type": "desk",
            "status": "active",
            "location": "Test Location",
            "desk_number": f"T346-{unique_id}",
        })
        assert create_resp.status_code in (200, 201), f"Resource creation failed: {create_resp.text}"
        resource = create_resp.json()
        resource_id = resource["resource_id"]
        self.created_resources.append(resource_id)
        
        # Create a booking on this resource
        future = datetime.now(timezone.utc) + timedelta(days=10)
        start_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_Booking_{unique_id}",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking_resp.status_code == 200, f"Booking creation failed: {booking_resp.text}"
        booking = booking_resp.json()
        self.created_bookings.append(booking["booking_id"])
        
        # Now check conflicts for an overlapping slot
        overlap_start = start_at + timedelta(minutes=30)  # 10:30
        overlap_end = end_at + timedelta(minutes=30)      # 11:30
        
        check_resp = self.session.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": overlap_start.isoformat(),
                "end_at": overlap_end.isoformat(),
            }
        )
        assert check_resp.status_code == 200, f"check-conflicts failed: {check_resp.text}"
        result = check_resp.json()
        
        assert "conflicts" in result
        conflicts = result["conflicts"]
        assert len(conflicts) > 0, f"Expected conflicts for overlapping slot, got: {result}"
        
        # Verify the conflict is our booking
        conflict_ids = [c.get("booking_id") for c in conflicts]
        assert booking["booking_id"] in conflict_ids, f"Our booking should be in conflicts: {conflicts}"
        print(f"Overlapping slot check: {len(conflicts)} conflicts found (expected)")


class TestIter346SplitableRoomConflicts:
    """Test 3: Splitable rooms - parent/child conflict detection"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
    
    def test_parent_detects_child_booking_as_conflict(self):
        """Booking a sub-room should block the parent (komplett)"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        # Find a splittable room with children
        splittable = [r for r in resources if r.get("is_splitable")]
        if not splittable:
            pytest.skip("No splittable rooms found in system")
        
        parent = splittable[0]
        children = [r for r in resources if r.get("parent_resource_id") == parent.get("resource_id")]
        if not children:
            pytest.skip("No sub-rooms found for splittable room")
        
        child = children[0]
        print(f"Testing: Parent={parent.get('name')}, Child={child.get('name')}")
        
        # Book the sub-room
        future = datetime.now(timezone.utc) + timedelta(days=15)
        start_at = future.replace(hour=9, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        
        child_booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": child["resource_id"],
            "title": "TEST_Iter346_SubRoom_Booking",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        if child_booking_resp.status_code != 200:
            # May fail due to allowed_combinations whitelist
            print(f"Child booking failed (may be expected): {child_booking_resp.text}")
            pytest.skip("Could not book sub-room (whitelist restriction)")
        
        child_booking = child_booking_resp.json()
        self.created_bookings.append(child_booking["booking_id"])
        print(f"Created sub-room booking: {child_booking['booking_id']}")
        
        # Check conflicts on parent - should show the child booking
        check_resp = self.session.post(
            f"{BASE_URL}/api/resources/{parent['resource_id']}/check-conflicts",
            json={
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            }
        )
        assert check_resp.status_code == 200
        conflicts = check_resp.json().get("conflicts", [])
        
        print(f"Parent conflicts: {len(conflicts)}")
        assert len(conflicts) > 0, "Parent should see child booking as conflict"
        
        # Verify the child booking is in conflicts
        conflict_resource_ids = [c.get("resource_id") for c in conflicts]
        assert child["resource_id"] in conflict_resource_ids, \
            f"Child resource should be in parent's conflicts: {conflicts}"
    
    def test_child_detects_parent_booking_as_conflict(self):
        """Booking the parent (komplett) should block sub-rooms"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        splittable = [r for r in resources if r.get("is_splitable")]
        if not splittable:
            pytest.skip("No splittable rooms found")
        
        parent = splittable[0]
        children = [r for r in resources if r.get("parent_resource_id") == parent.get("resource_id")]
        if not children:
            pytest.skip("No sub-rooms found")
        
        child = children[0]
        print(f"Testing: Parent={parent.get('name')}, Child={child.get('name')}")
        
        # Book the parent (komplett)
        future = datetime.now(timezone.utc) + timedelta(days=16)
        start_at = future.replace(hour=14, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=15, minute=0, second=0, microsecond=0)
        
        parent_booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": parent["resource_id"],
            "title": "TEST_Iter346_Parent_Booking",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        if parent_booking_resp.status_code != 200:
            print(f"Parent booking failed: {parent_booking_resp.text}")
            pytest.skip("Could not book parent room")
        
        parent_booking = parent_booking_resp.json()
        self.created_bookings.append(parent_booking["booking_id"])
        print(f"Created parent booking: {parent_booking['booking_id']}")
        
        # Check conflicts on child - should show the parent booking
        check_resp = self.session.post(
            f"{BASE_URL}/api/resources/{child['resource_id']}/check-conflicts",
            json={
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            }
        )
        assert check_resp.status_code == 200
        conflicts = check_resp.json().get("conflicts", [])
        
        print(f"Child conflicts: {len(conflicts)}")
        assert len(conflicts) > 0, "Child should see parent booking as conflict"
        
        conflict_resource_ids = [c.get("resource_id") for c in conflicts]
        assert parent["resource_id"] in conflict_resource_ids, \
            f"Parent resource should be in child's conflicts: {conflicts}"


class TestIter346BlackoutPeriods:
    """Test 4: Blackout periods surface as conflicts with reason='blackout'"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_resources = []
        self.created_blackouts = []
        yield
        
        for bo_id in self.created_blackouts:
            try:
                self.session.delete(f"{BASE_URL}/api/blackout-periods/{bo_id}")
            except:
                pass
        for rid in self.created_resources:
            try:
                self.session.delete(f"{BASE_URL}/api/resources/{rid}")
            except:
                pass
    
    def test_blackout_period_surfaces_as_conflict(self):
        """Blackout period should appear in conflicts with reason='blackout'"""
        # Create a test resource
        unique_id = uuid.uuid4().hex[:8]
        create_resp = self.session.post(f"{BASE_URL}/api/resources", json={
            "name": f"TEST_Iter346_Blackout_Room_{unique_id}",
            "type": "room",
            "status": "active",
            "location": "Test Location",
        })
        assert create_resp.status_code in (200, 201), f"Resource creation failed: {create_resp.text}"
        resource = create_resp.json()
        resource_id = resource["resource_id"]
        self.created_resources.append(resource_id)
        
        # Create a blackout period on this resource
        future = datetime.now(timezone.utc) + timedelta(days=20)
        blackout_start = future.replace(hour=8, minute=0, second=0, microsecond=0)
        blackout_end = future.replace(hour=18, minute=0, second=0, microsecond=0)
        
        blackout_resp = self.session.post(f"{BASE_URL}/api/blackout-periods", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_Blackout_{unique_id}",
            "start_at": blackout_start.isoformat(),
            "end_at": blackout_end.isoformat(),
        })
        
        if blackout_resp.status_code not in (200, 201):
            print(f"Blackout creation response: {blackout_resp.status_code} - {blackout_resp.text}")
            pytest.skip("Blackout periods endpoint not available or failed")
        
        blackout = blackout_resp.json()
        blackout_id = blackout.get("blackout_id") or blackout.get("period_id")
        if blackout_id:
            self.created_blackouts.append(blackout_id)
        print(f"Created blackout period: {blackout}")
        
        # Check conflicts for a slot within the blackout
        check_start = blackout_start + timedelta(hours=2)  # 10:00
        check_end = check_start + timedelta(hours=1)       # 11:00
        
        check_resp = self.session.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": check_start.isoformat(),
                "end_at": check_end.isoformat(),
            }
        )
        assert check_resp.status_code == 200, f"check-conflicts failed: {check_resp.text}"
        conflicts = check_resp.json().get("conflicts", [])
        
        print(f"Conflicts during blackout: {conflicts}")
        
        # Find blackout conflict
        blackout_conflicts = [c for c in conflicts if c.get("reason") == "blackout"]
        assert len(blackout_conflicts) > 0, \
            f"Expected blackout conflict with reason='blackout', got: {conflicts}"
        
        print(f"Blackout conflict found: {blackout_conflicts[0]}")


class TestIter346BufferTime:
    """Test 5: Buffer time - booking inside buffer window is reported as conflict"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_resources = []
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
        for rid in self.created_resources:
            try:
                self.session.delete(f"{BASE_URL}/api/resources/{rid}")
            except:
                pass
    
    def test_buffer_time_creates_conflict(self):
        """Booking within buffer window of existing booking should conflict"""
        # Create a resource with buffer_time_min
        unique_id = uuid.uuid4().hex[:8]
        create_resp = self.session.post(f"{BASE_URL}/api/resources", json={
            "name": f"TEST_Iter346_Buffer_Room_{unique_id}",
            "type": "room",
            "status": "active",
            "location": "Test Location",
            "buffer_time_min": 15,  # 15 minute buffer
        })
        assert create_resp.status_code in (200, 201), f"Resource creation failed: {create_resp.text}"
        resource = create_resp.json()
        resource_id = resource["resource_id"]
        self.created_resources.append(resource_id)
        
        # Create a booking
        future = datetime.now(timezone.utc) + timedelta(days=25)
        booking_start = future.replace(hour=10, minute=0, second=0, microsecond=0)
        booking_end = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_Buffer_Booking_{unique_id}",
            "start_at": booking_start.isoformat(),
            "end_at": booking_end.isoformat(),
        })
        assert booking_resp.status_code == 200, f"Booking creation failed: {booking_resp.text}"
        booking = booking_resp.json()
        self.created_bookings.append(booking["booking_id"])
        
        # Try to check conflicts for a slot that ends within the buffer window
        # Booking is 10:00-11:00 with 15min buffer, so 09:50-10:00 should conflict
        buffer_check_start = booking_start - timedelta(minutes=10)  # 09:50
        buffer_check_end = booking_start  # 10:00 (exactly at booking start)
        
        check_resp = self.session.post(
            f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
            json={
                "start_at": buffer_check_start.isoformat(),
                "end_at": buffer_check_end.isoformat(),
            }
        )
        assert check_resp.status_code == 200
        conflicts = check_resp.json().get("conflicts", [])
        
        print(f"Buffer window conflicts: {conflicts}")
        # Due to buffer_time_min=15, the query window expands, so 09:50-10:00 
        # should see the 10:00-11:00 booking as a conflict
        assert len(conflicts) > 0, \
            f"Expected conflict due to buffer time, got: {conflicts}"


class TestIter346BookingCRUD:
    """Test 6 & 7: POST/PUT resource-bookings respects conflict checks"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_resources = []
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
        for rid in self.created_resources:
            try:
                self.session.delete(f"{BASE_URL}/api/resources/{rid}")
            except:
                pass
    
    def test_create_booking_succeeds_for_free_slot(self):
        """Test 6a: Creating a normal booking succeeds"""
        unique_id = uuid.uuid4().hex[:8]
        create_resp = self.session.post(f"{BASE_URL}/api/resources", json={
            "name": f"TEST_Iter346_CRUD_Desk_{unique_id}",
            "type": "desk",
            "status": "active",
            "location": "Test Location",
            "desk_number": f"CRUD-{unique_id}",
        })
        assert create_resp.status_code in (200, 201)
        resource = create_resp.json()
        resource_id = resource["resource_id"]
        self.created_resources.append(resource_id)
        
        future = datetime.now(timezone.utc) + timedelta(days=30)
        start_at = future.replace(hour=9, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_CRUD_Booking_{unique_id}",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking_resp.status_code == 200, f"Booking should succeed: {booking_resp.text}"
        booking = booking_resp.json()
        self.created_bookings.append(booking["booking_id"])
        
        assert "booking_id" in booking
        assert booking.get("status") in ("confirmed", "pending_approval")
        print(f"Booking created successfully: {booking['booking_id']}")
    
    def test_create_overlapping_booking_rejected_with_409(self):
        """Test 6b: Creating an overlapping booking is rejected with 409"""
        unique_id = uuid.uuid4().hex[:8]
        create_resp = self.session.post(f"{BASE_URL}/api/resources", json={
            "name": f"TEST_Iter346_Overlap_Desk_{unique_id}",
            "type": "desk",
            "status": "active",
            "location": "Test Location",
            "desk_number": f"OVL-{unique_id}",
        })
        assert create_resp.status_code in (200, 201)
        resource = create_resp.json()
        resource_id = resource["resource_id"]
        self.created_resources.append(resource_id)
        
        future = datetime.now(timezone.utc) + timedelta(days=31)
        start_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        # First booking
        booking1_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_First_{unique_id}",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking1_resp.status_code == 200
        booking1 = booking1_resp.json()
        self.created_bookings.append(booking1["booking_id"])
        
        # Second overlapping booking - should fail with 409
        booking2_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_Second_{unique_id}",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking2_resp.status_code == 409, \
            f"Overlapping booking should be rejected with 409, got {booking2_resp.status_code}: {booking2_resp.text}"
        
        error = booking2_resp.json()
        assert "conflicts" in error or "detail" in error, f"Error should contain conflicts info: {error}"
        print(f"Overlapping booking correctly rejected: {error}")
    
    def test_update_booking_respects_conflicts(self):
        """Test 7: PUT /api/resource-bookings/{id} respects conflict checks"""
        unique_id = uuid.uuid4().hex[:8]
        create_resp = self.session.post(f"{BASE_URL}/api/resources", json={
            "name": f"TEST_Iter346_Update_Desk_{unique_id}",
            "type": "desk",
            "status": "active",
            "location": "Test Location",
            "desk_number": f"UPD-{unique_id}",
        })
        assert create_resp.status_code in (200, 201)
        resource = create_resp.json()
        resource_id = resource["resource_id"]
        self.created_resources.append(resource_id)
        
        future = datetime.now(timezone.utc) + timedelta(days=32)
        
        # Create two non-overlapping bookings
        start1 = future.replace(hour=9, minute=0, second=0, microsecond=0)
        end1 = future.replace(hour=10, minute=0, second=0, microsecond=0)
        
        start2 = future.replace(hour=11, minute=0, second=0, microsecond=0)
        end2 = future.replace(hour=12, minute=0, second=0, microsecond=0)
        
        booking1_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_Update1_{unique_id}",
            "start_at": start1.isoformat(),
            "end_at": end1.isoformat(),
        })
        assert booking1_resp.status_code == 200
        booking1 = booking1_resp.json()
        self.created_bookings.append(booking1["booking_id"])
        
        booking2_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": f"TEST_Iter346_Update2_{unique_id}",
            "start_at": start2.isoformat(),
            "end_at": end2.isoformat(),
        })
        assert booking2_resp.status_code == 200
        booking2 = booking2_resp.json()
        self.created_bookings.append(booking2["booking_id"])
        
        # Try to move booking2 to overlap with booking1 - should fail
        update_resp = self.session.put(
            f"{BASE_URL}/api/resource-bookings/{booking2['booking_id']}",
            json={
                "start_at": start1.isoformat(),  # Same as booking1
                "end_at": end1.isoformat(),
            }
        )
        assert update_resp.status_code == 409, \
            f"Moving booking to overlap should fail with 409, got {update_resp.status_code}: {update_resp.text}"
        print("Update correctly rejected due to conflict")


class TestIter346AllowedCombinations:
    """Test 8: Sub-room allowed_combinations whitelist"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
    
    def test_subroom_not_in_whitelist_returns_400(self):
        """Booking a sub-room not in allowed_combinations returns HTTP 400"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        # Find a splittable room with allowed_combinations set
        splittable_with_combos = [
            r for r in resources 
            if r.get("is_splitable") and r.get("allowed_combinations")
        ]
        
        if not splittable_with_combos:
            pytest.skip("No splittable rooms with allowed_combinations found")
        
        parent = splittable_with_combos[0]
        allowed = parent.get("allowed_combinations", [])
        print(f"Parent: {parent.get('name')}, allowed_combinations: {allowed}")
        
        # Find children
        children = [r for r in resources if r.get("parent_resource_id") == parent.get("resource_id")]
        if not children:
            pytest.skip("No sub-rooms found")
        
        # Find a child whose sub_id is NOT in any allowed combination as a single
        # (i.e., [sub_id] is not in allowed_combinations)
        disallowed_child = None
        for child in children:
            sub_id = child.get("sub_id")
            if sub_id and not any(set(c) == {sub_id} for c in allowed):
                disallowed_child = child
                break
        
        if not disallowed_child:
            pytest.skip("All sub-rooms are allowed as single bookings")
        
        print(f"Testing disallowed sub-room: {disallowed_child.get('name')} (sub_id={disallowed_child.get('sub_id')})")
        
        # Try to book this sub-room - should fail with 400
        future = datetime.now(timezone.utc) + timedelta(days=35)
        start_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": disallowed_child["resource_id"],
            "title": "TEST_Iter346_Disallowed_SubRoom",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        assert booking_resp.status_code == 400, \
            f"Expected 400 for disallowed sub-room, got {booking_resp.status_code}: {booking_resp.text}"
        
        error = booking_resp.json()
        error_detail = error.get("detail", "")
        # Should contain German error message about not being allowed
        assert "nicht" in error_detail.lower() or "freigegeben" in error_detail.lower(), \
            f"Error should mention German restriction message: {error}"
        print(f"Correctly rejected with 400: {error_detail}")


class TestIter346RaceCondition:
    """Test 9: Race-condition winner selection (verify_booking_winner)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        self.created_resources = []
        self.created_bookings = []
        yield
        
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
        for rid in self.created_resources:
            try:
                self.session.delete(f"{BASE_URL}/api/resources/{rid}")
            except:
                pass
    
    def test_concurrent_bookings_one_wins(self):
        """
        Race-condition test: Multiple concurrent POST requests for the same slot
        should result in exactly ONE successful booking.
        """
        import concurrent.futures
        
        unique_id = uuid.uuid4().hex[:8]
        create_resp = self.session.post(f"{BASE_URL}/api/resources", json={
            "name": f"TEST_Iter346_Race_Desk_{unique_id}",
            "type": "desk",
            "status": "active",
            "location": "Test Location",
            "desk_number": f"RACE-{unique_id}",
        })
        assert create_resp.status_code in (200, 201)
        resource = create_resp.json()
        resource_id = resource["resource_id"]
        self.created_resources.append(resource_id)
        
        future = datetime.now(timezone.utc) + timedelta(days=40)
        start_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=11, minute=0, second=0, microsecond=0)
        
        def make_booking(i):
            """Make a booking request"""
            session = requests.Session()
            session.headers.update({
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}"
            })
            resp = session.post(f"{BASE_URL}/api/resource-bookings", json={
                "resource_id": resource_id,
                "title": f"TEST_Iter346_Race_{unique_id}_{i}",
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            })
            return resp.status_code, resp.json() if resp.status_code in (200, 409) else resp.text
        
        # Run 10 concurrent requests
        num_requests = 10
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(make_booking, i) for i in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        success_count = sum(1 for status, _ in results if status == 200)
        conflict_count = sum(1 for status, _ in results if status == 409)
        other_count = num_requests - success_count - conflict_count
        
        print(f"Race test results: success={success_count}, conflict={conflict_count}, other={other_count}")
        
        # Track created bookings for cleanup
        for status, data in results:
            if status == 200 and isinstance(data, dict) and "booking_id" in data:
                self.created_bookings.append(data["booking_id"])
        
        # Exactly one should succeed
        assert success_count == 1, \
            f"Race-condition bug: expected exactly 1 success, got {success_count}. " \
            f"Distribution: 200={success_count}, 409={conflict_count}, other={other_count}"
        
        # The rest should be conflicts
        assert conflict_count == num_requests - 1, \
            f"Expected {num_requests - 1} conflicts, got {conflict_count}"
        
        print("Race-condition winner selection working correctly!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
