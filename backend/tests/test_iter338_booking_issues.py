"""
Iteration 338 — Backend tests for 6 booking-related issues:
1. End-time debounce validation (frontend-only, tested via UI)
2. Booking dialog performance (refdata cache - frontend-only)
3. Splittable room: pending_approval overlap with allow_pending_overlap flag
4. Splittable room: switch-target chips (frontend-only)
5. Billing button labels (frontend-only)
6. Invoice creation auto-refresh (frontend-only)

Backend tests focus on Issue 3: allow_pending_overlap flag behavior.
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestIter338AllowPendingOverlap:
    """Issue 3: POST /api/resource-bookings with allow_pending_overlap flag"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
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
        self.admin_user = login_resp.json().get("user", {})
        
        # Store created booking IDs for cleanup
        self.created_bookings = []
        yield
        
        # Cleanup created bookings
        for bid in self.created_bookings:
            try:
                self.session.delete(f"{BASE_URL}/api/resource-bookings/{bid}")
            except:
                pass
    
    def test_get_resources_list(self):
        """Verify resources endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200, f"Failed to get resources: {resp.text}"
        resources = resp.json()
        assert isinstance(resources, list), "Resources should be a list"
        print(f"Found {len(resources)} resources")
        
        # Find a room that requires approval
        approval_rooms = [r for r in resources if r.get("requires_approval") and r.get("type") == "room"]
        print(f"Found {len(approval_rooms)} rooms requiring approval")
        return resources
    
    def test_create_pending_booking_then_overlap_without_flag(self):
        """
        Issue 3 (backend): Create a pending_approval booking, then try to book
        the same slot WITHOUT allow_pending_overlap flag - should return 409.
        """
        # Get a room that requires approval
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        # Find a room requiring approval
        approval_rooms = [r for r in resources if r.get("requires_approval") and r.get("type") == "room"]
        if not approval_rooms:
            # Create a test room with requires_approval
            pytest.skip("No rooms with requires_approval found - skipping test")
        
        room = approval_rooms[0]
        resource_id = room["resource_id"]
        print(f"Using room: {room.get('name')} ({resource_id})")
        
        # Create a booking in the future (tomorrow 10:00-11:00)
        tomorrow = datetime.now() + timedelta(days=1)
        start_at = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_at = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
        
        # First booking - should be pending_approval
        booking1_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": "TEST_Iter338_Pending_Booking_1",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking1_resp.status_code == 200, f"First booking failed: {booking1_resp.text}"
        booking1 = booking1_resp.json()
        self.created_bookings.append(booking1["booking_id"])
        
        assert booking1.get("status") == "pending_approval", f"Expected pending_approval, got {booking1.get('status')}"
        print(f"Created first booking: {booking1['booking_id']} with status {booking1['status']}")
        
        # Second booking - same slot, WITHOUT allow_pending_overlap - should 409
        booking2_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": "TEST_Iter338_Overlap_Without_Flag",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        assert booking2_resp.status_code == 409, f"Expected 409 conflict, got {booking2_resp.status_code}: {booking2_resp.text}"
        print(f"Second booking correctly rejected with 409: {booking2_resp.json()}")
    
    def test_create_pending_booking_then_overlap_with_flag(self):
        """
        Issue 3 (backend): Create a pending_approval booking, then book the same
        slot WITH allow_pending_overlap=true - should return 200 with new pending booking.
        """
        # Get a room that requires approval
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        approval_rooms = [r for r in resources if r.get("requires_approval") and r.get("type") == "room"]
        if not approval_rooms:
            pytest.skip("No rooms with requires_approval found")
        
        room = approval_rooms[0]
        resource_id = room["resource_id"]
        print(f"Using room: {room.get('name')} ({resource_id})")
        
        # Create a booking in the future (day after tomorrow 14:00-15:00)
        future = datetime.now() + timedelta(days=2)
        start_at = future.replace(hour=14, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=15, minute=0, second=0, microsecond=0)
        
        # First booking - should be pending_approval
        booking1_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": "TEST_Iter338_Pending_Booking_2",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking1_resp.status_code == 200, f"First booking failed: {booking1_resp.text}"
        booking1 = booking1_resp.json()
        self.created_bookings.append(booking1["booking_id"])
        
        assert booking1.get("status") == "pending_approval"
        print(f"Created first booking: {booking1['booking_id']} with status {booking1['status']}")
        
        # Second booking - same slot, WITH allow_pending_overlap=true - should succeed
        booking2_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": "TEST_Iter338_Overlap_With_Flag",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "allow_pending_overlap": True,
        })
        
        assert booking2_resp.status_code == 200, f"Expected 200 with allow_pending_overlap, got {booking2_resp.status_code}: {booking2_resp.text}"
        booking2 = booking2_resp.json()
        self.created_bookings.append(booking2["booking_id"])
        
        # The new booking should also be pending_approval (forced by overlap)
        assert booking2.get("status") == "pending_approval", f"Expected pending_approval, got {booking2.get('status')}"
        print(f"Second booking created successfully: {booking2['booking_id']} with status {booking2['status']}")
    
    def test_confirmed_conflict_still_blocks_with_flag(self):
        """
        Issue 3 (backend): Even with allow_pending_overlap=true, a CONFIRMED
        booking should still block (409). The flag only bypasses pending conflicts.
        """
        # Get a room that does NOT require approval (auto-confirms)
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        auto_confirm_rooms = [r for r in resources if not r.get("requires_approval") and r.get("type") == "room"]
        if not auto_confirm_rooms:
            pytest.skip("No auto-confirm rooms found")
        
        room = auto_confirm_rooms[0]
        resource_id = room["resource_id"]
        print(f"Using auto-confirm room: {room.get('name')} ({resource_id})")
        
        # Create a booking in the future (3 days from now 09:00-10:00)
        future = datetime.now() + timedelta(days=3)
        start_at = future.replace(hour=9, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # First booking - should be confirmed (auto-confirm room)
        booking1_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": "TEST_Iter338_Confirmed_Booking",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking1_resp.status_code == 200, f"First booking failed: {booking1_resp.text}"
        booking1 = booking1_resp.json()
        self.created_bookings.append(booking1["booking_id"])
        
        assert booking1.get("status") == "confirmed", f"Expected confirmed, got {booking1.get('status')}"
        print(f"Created confirmed booking: {booking1['booking_id']} with status {booking1['status']}")
        
        # Second booking - same slot, WITH allow_pending_overlap=true
        # Should STILL 409 because the existing booking is confirmed, not pending
        booking2_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": "TEST_Iter338_Should_Still_Conflict",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "allow_pending_overlap": True,
        })
        
        assert booking2_resp.status_code == 409, f"Expected 409 (confirmed conflict), got {booking2_resp.status_code}: {booking2_resp.text}"
        print(f"Second booking correctly rejected with 409 (confirmed conflict)")


class TestIter338CheckConflicts:
    """Test the check-conflicts endpoint returns pending_approval status"""
    
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
    
    def test_check_conflicts_returns_pending_status(self):
        """Verify check-conflicts returns status field for pending bookings"""
        # Get a room that requires approval
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        approval_rooms = [r for r in resources if r.get("requires_approval") and r.get("type") == "room"]
        if not approval_rooms:
            pytest.skip("No rooms with requires_approval found")
        
        room = approval_rooms[0]
        resource_id = room["resource_id"]
        
        # Create a pending booking
        future = datetime.now() + timedelta(days=4)
        start_at = future.replace(hour=11, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=12, minute=0, second=0, microsecond=0)
        
        booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": resource_id,
            "title": "TEST_Iter338_Check_Conflicts",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert booking_resp.status_code == 200
        booking = booking_resp.json()
        self.created_bookings.append(booking["booking_id"])
        
        # Now check conflicts for the same slot
        check_resp = self.session.post(f"{BASE_URL}/api/resources/{resource_id}/check-conflicts", json={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert check_resp.status_code == 200
        conflicts = check_resp.json().get("conflicts", [])
        
        assert len(conflicts) > 0, "Expected at least one conflict"
        
        # Verify the conflict includes status field
        conflict = conflicts[0]
        assert "status" in conflict, f"Conflict should include status field: {conflict}"
        assert conflict["status"] == "pending_approval", f"Expected pending_approval status: {conflict}"
        print(f"Check-conflicts correctly returns status: {conflict['status']}")


class TestIter338SplittableRoomConflicts:
    """Test splittable room conflict detection for Issue 4"""
    
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
    
    def test_find_splittable_rooms(self):
        """Find splittable rooms in the system"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        splittable = [r for r in resources if r.get("is_splitable")]
        print(f"Found {len(splittable)} splittable rooms")
        
        for room in splittable[:3]:
            print(f"  - {room.get('name')} ({room.get('resource_id')})")
            children = [r for r in resources if r.get("parent_resource_id") == room.get("resource_id")]
            for child in children:
                print(f"    - Sub: {child.get('name')} ({child.get('resource_id')})")
        
        return splittable
    
    def test_subroom_booking_blocks_parent(self):
        """Booking a sub-room should block the parent (komplett)"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        resources = resp.json()
        
        # Find a splittable room with children
        splittable = [r for r in resources if r.get("is_splitable")]
        if not splittable:
            pytest.skip("No splittable rooms found")
        
        parent = splittable[0]
        children = [r for r in resources if r.get("parent_resource_id") == parent.get("resource_id")]
        if not children:
            pytest.skip("No sub-rooms found for splittable room")
        
        child = children[0]
        print(f"Testing: Parent={parent.get('name')}, Child={child.get('name')}")
        
        # Book the sub-room
        future = datetime.now() + timedelta(days=5)
        start_at = future.replace(hour=13, minute=0, second=0, microsecond=0)
        end_at = future.replace(hour=14, minute=0, second=0, microsecond=0)
        
        child_booking_resp = self.session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": child["resource_id"],
            "title": "TEST_Iter338_SubRoom_Booking",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        
        if child_booking_resp.status_code != 200:
            print(f"Child booking failed (may be expected): {child_booking_resp.text}")
            pytest.skip("Could not book sub-room")
        
        child_booking = child_booking_resp.json()
        self.created_bookings.append(child_booking["booking_id"])
        print(f"Created sub-room booking: {child_booking['booking_id']}")
        
        # Check conflicts on parent - should show the child booking
        check_resp = self.session.post(f"{BASE_URL}/api/resources/{parent['resource_id']}/check-conflicts", json={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        })
        assert check_resp.status_code == 200
        conflicts = check_resp.json().get("conflicts", [])
        
        print(f"Parent conflicts: {len(conflicts)}")
        for c in conflicts:
            print(f"  - {c.get('title')} on {c.get('resource_id')}")
        
        # The parent should see the child booking as a conflict
        assert len(conflicts) > 0, "Parent should see child booking as conflict"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
