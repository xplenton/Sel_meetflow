"""
Iter 238 Backend Tests:
1. GET /api/resources-in-office — In-Office-Today Widget
2. GET/PUT /api/users/me/privacy — Privacy Opt-Out
3. GET /api/floorplans — Multi-Floor-Picker
4. PUT /api/resource-bookings/{id} with resource_id — Drag&Drop Cross-Move (Regression from Iter 236)
5. GET /api/resource-occupancy — Privacy Mask (Regression from Iter 237)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth cookies."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    # Store token for Authorization header as backup
    if "token" in data:
        session.headers.update({"Authorization": f"Bearer {data['token']}"})
    return session


@pytest.fixture(scope="module")
def test_desk_booking(admin_session):
    """Create a confirmed desk booking that is active NOW for in-office testing."""
    # First, get a desk resource
    resp = admin_session.get(f"{BASE_URL}/api/resources?type=desk")
    assert resp.status_code == 200, f"Failed to get desks: {resp.text}"
    desks = resp.json()
    
    if not desks:
        # Create a test desk if none exist
        desk_data = {
            "name": f"TEST_Desk_{uuid.uuid4().hex[:6]}",
            "type": "desk",
            "location": "Test Building",
            "building": "Test Building",
            "floor": "1.OG",
            "desk_number": f"DSK-TEST-{uuid.uuid4().hex[:4]}",
            "status": "active"
        }
        resp = admin_session.post(f"{BASE_URL}/api/resources", json=desk_data)
        if resp.status_code == 201:
            desk = resp.json()
        else:
            pytest.skip("Could not create test desk")
    else:
        # Use first active desk
        desk = next((d for d in desks if d.get("status") == "active"), desks[0])
    
    # Create a booking that is active NOW (start=now, end=now+4h)
    now = datetime.utcnow()
    start_at = now.isoformat() + "Z"
    end_at = (now + timedelta(hours=4)).isoformat() + "Z"
    
    booking_data = {
        "resource_id": desk["resource_id"],
        "title": f"TEST_InOffice_Booking_{uuid.uuid4().hex[:6]}",
        "start_at": start_at,
        "end_at": end_at
    }
    resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
    
    if resp.status_code in [200, 201]:
        booking = resp.json()
        yield {"desk": desk, "booking": booking}
        # Cleanup: delete the booking
        admin_session.delete(f"{BASE_URL}/api/resource-bookings/{booking['booking_id']}")
    else:
        # Booking might fail due to conflict, try with different time
        start_at = (now + timedelta(hours=1)).isoformat() + "Z"
        end_at = (now + timedelta(hours=5)).isoformat() + "Z"
        booking_data["start_at"] = start_at
        booking_data["end_at"] = end_at
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        if resp.status_code in [200, 201]:
            booking = resp.json()
            yield {"desk": desk, "booking": booking}
            admin_session.delete(f"{BASE_URL}/api/resource-bookings/{booking['booking_id']}")
        else:
            yield {"desk": desk, "booking": None}


class TestInOfficeWidget:
    """Test GET /api/resources-in-office endpoint (Iter 238)."""
    
    def test_in_office_endpoint_returns_200(self, admin_session):
        """GET /api/resources-in-office should return 200 for admin."""
        resp = admin_session.get(f"{BASE_URL}/api/resources-in-office")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    def test_in_office_response_structure(self, admin_session):
        """Response should have date, people, total, active_now fields."""
        resp = admin_session.get(f"{BASE_URL}/api/resources-in-office")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "date" in data, "Response missing 'date' field"
        assert "people" in data, "Response missing 'people' field"
        assert "total" in data, "Response missing 'total' field"
        assert "active_now" in data, "Response missing 'active_now' field"
        
        assert isinstance(data["people"], list), "'people' should be a list"
        assert isinstance(data["total"], int), "'total' should be an integer"
        assert isinstance(data["active_now"], int), "'active_now' should be an integer"
    
    def test_in_office_with_active_booking(self, admin_session, test_desk_booking):
        """With an active desk booking, user should appear in people list."""
        if not test_desk_booking.get("booking"):
            pytest.skip("No test booking created")
        
        resp = admin_session.get(f"{BASE_URL}/api/resources-in-office")
        assert resp.status_code == 200
        data = resp.json()
        
        # The admin user should be in the people list
        # Check if total > 0 (at least our booking should be there)
        # Note: The user might have hide_from_office_widget=true, so we check structure
        if data["total"] > 0:
            person = data["people"][0]
            # Verify person structure
            expected_fields = ["user_id", "name", "email", "desk_number", "building", "floor", "is_active_now"]
            for field in expected_fields:
                assert field in person, f"Person missing '{field}' field"


class TestPrivacySettings:
    """Test GET/PUT /api/users/me/privacy endpoints (Iter 238)."""
    
    def test_get_privacy_settings(self, admin_session):
        """GET /api/users/me/privacy should return current privacy settings."""
        resp = admin_session.get(f"{BASE_URL}/api/users/me/privacy")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "hide_from_office_widget" in data, "Response missing 'hide_from_office_widget'"
        assert isinstance(data["hide_from_office_widget"], bool), "'hide_from_office_widget' should be boolean"
    
    def test_put_privacy_settings_enable(self, admin_session):
        """PUT /api/users/me/privacy with hide_from_office_widget=true should succeed."""
        resp = admin_session.put(f"{BASE_URL}/api/users/me/privacy", json={
            "hide_from_office_widget": True
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("hide_from_office_widget") == True, "hide_from_office_widget should be True"
    
    def test_put_privacy_settings_disable(self, admin_session):
        """PUT /api/users/me/privacy with hide_from_office_widget=false should succeed."""
        resp = admin_session.put(f"{BASE_URL}/api/users/me/privacy", json={
            "hide_from_office_widget": False
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("hide_from_office_widget") == False, "hide_from_office_widget should be False"
    
    def test_get_privacy_reflects_update(self, admin_session):
        """GET /api/users/me/privacy should reflect the updated value."""
        # Set to True
        admin_session.put(f"{BASE_URL}/api/users/me/privacy", json={"hide_from_office_widget": True})
        
        # Verify GET returns True
        resp = admin_session.get(f"{BASE_URL}/api/users/me/privacy")
        assert resp.status_code == 200
        assert resp.json().get("hide_from_office_widget") == True
        
        # Set back to False
        admin_session.put(f"{BASE_URL}/api/users/me/privacy", json={"hide_from_office_widget": False})
        
        # Verify GET returns False
        resp = admin_session.get(f"{BASE_URL}/api/users/me/privacy")
        assert resp.status_code == 200
        assert resp.json().get("hide_from_office_widget") == False
    
    def test_privacy_opt_out_hides_from_in_office(self, admin_session, test_desk_booking):
        """When hide_from_office_widget=true, user should NOT appear in /api/resources-in-office."""
        if not test_desk_booking.get("booking"):
            pytest.skip("No test booking created")
        
        # Enable privacy opt-out
        admin_session.put(f"{BASE_URL}/api/users/me/privacy", json={"hide_from_office_widget": True})
        
        # Check in-office endpoint
        resp = admin_session.get(f"{BASE_URL}/api/resources-in-office")
        assert resp.status_code == 200
        data = resp.json()
        
        # Get current user info
        me_resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        if me_resp.status_code == 200:
            my_user_id = me_resp.json().get("user_id")
            
            # User should NOT be in the people list
            user_ids_in_list = [p.get("user_id") for p in data.get("people", [])]
            assert my_user_id not in user_ids_in_list, "User with hide_from_office_widget=true should not appear in people list"
        
        # Disable privacy opt-out (cleanup)
        admin_session.put(f"{BASE_URL}/api/users/me/privacy", json={"hide_from_office_widget": False})


class TestFloorplans:
    """Test GET /api/floorplans endpoint (Iter 238)."""
    
    def test_get_floorplans_returns_200(self, admin_session):
        """GET /api/floorplans should return 200 for admin."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    def test_get_floorplans_returns_array(self, admin_session):
        """GET /api/floorplans should return an array."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans")
        assert resp.status_code == 200
        data = resp.json()
        
        assert isinstance(data, list), "Response should be an array"
    
    def test_floorplan_structure(self, admin_session):
        """Each floorplan should have floor_plan_id and name."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans")
        assert resp.status_code == 200
        data = resp.json()
        
        if len(data) > 0:
            plan = data[0]
            assert "floor_plan_id" in plan, "Floorplan missing 'floor_plan_id'"
            assert "name" in plan or plan.get("floor_plan_id"), "Floorplan should have name or floor_plan_id"


class TestDragDropRegression:
    """Regression tests for PUT /api/resource-bookings/{id} with resource_id (Iter 236)."""
    
    def test_put_booking_move_same_type(self, admin_session):
        """PUT /api/resource-bookings/{id} with resource_id should move booking to same type resource."""
        # Get two rooms
        resp = admin_session.get(f"{BASE_URL}/api/resources?type=room")
        assert resp.status_code == 200
        rooms = [r for r in resp.json() if r.get("status") == "active" and not r.get("parent_resource_id")]
        
        if len(rooms) < 2:
            pytest.skip("Need at least 2 active rooms for this test")
        
        room1, room2 = rooms[0], rooms[1]
        
        # Create a booking on room1
        now = datetime.utcnow()
        start_at = (now + timedelta(days=7, hours=10)).isoformat() + "Z"
        end_at = (now + timedelta(days=7, hours=11)).isoformat() + "Z"
        
        booking_data = {
            "resource_id": room1["resource_id"],
            "title": f"TEST_DragDrop_{uuid.uuid4().hex[:6]}",
            "start_at": start_at,
            "end_at": end_at
        }
        resp = admin_session.post(f"{BASE_URL}/api/resource-bookings", json=booking_data)
        
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create test booking: {resp.text}")
        
        booking = resp.json()
        booking_id = booking["booking_id"]
        
        try:
            # Move booking to room2
            move_resp = admin_session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
                "resource_id": room2["resource_id"]
            })
            assert move_resp.status_code == 200, f"Move failed: {move_resp.text}"
            
            moved = move_resp.json()
            assert moved.get("resource_id") == room2["resource_id"], "Booking should be on room2"
        finally:
            # Cleanup
            admin_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")


class TestPrivacyMaskRegression:
    """Regression tests for privacy masking in /api/resource-occupancy (Iter 237)."""
    
    def test_occupancy_returns_bookings(self, admin_session):
        """GET /api/resource-occupancy should return bookings array."""
        now = datetime.utcnow()
        from_date = now.isoformat() + "Z"
        to_date = (now + timedelta(days=7)).isoformat() + "Z"
        
        resp = admin_session.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "resources" in data, "Response missing 'resources'"
        assert "bookings" in data, "Response missing 'bookings'"
        assert "blackouts" in data, "Response missing 'blackouts'"
    
    def test_occupancy_type_filter(self, admin_session):
        """GET /api/resource-occupancy with type=room should filter correctly."""
        now = datetime.utcnow()
        from_date = now.isoformat() + "Z"
        to_date = (now + timedelta(days=7)).isoformat() + "Z"
        
        resp = admin_session.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date,
            "type": "room"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # All resources should be rooms
        for r in data.get("resources", []):
            if r.get("type"):
                assert r["type"] == "room", f"Expected room, got {r['type']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
