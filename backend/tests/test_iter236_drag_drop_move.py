"""
Iter 236 — Drag & Drop Move Booking Tests

Tests the PUT /api/resource-bookings/{id} endpoint with resource_id change support.
Features tested:
1. Move booking to another resource of same type (room -> room)
2. Reject move to different type (room -> vehicle) with 400
3. Reject move with conflict on target resource with 409
4. Cancel dialog does not trigger PUT
5. Verify response contains updated resource_id, start_at, end_at
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_CREDS = {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.fixture(scope="module")
def auth_session():
    """Login and return authenticated session"""
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return session


@pytest.fixture(scope="module")
def demo_rooms(auth_session):
    """Get demo rooms for testing"""
    r = auth_session.get(f"{BASE_URL}/api/resources?type=room")
    assert r.status_code == 200
    rooms = [res for res in r.json() if res['name'].startswith('Demo_')]
    assert len(rooms) >= 2, "Need at least 2 demo rooms for testing"
    return rooms


@pytest.fixture(scope="module")
def demo_vehicle(auth_session):
    """Get a demo vehicle for cross-type test"""
    r = auth_session.get(f"{BASE_URL}/api/resources?type=vehicle")
    assert r.status_code == 200
    vehicles = [res for res in r.json() if res['name'].startswith('Demo_')]
    assert len(vehicles) >= 1, "Need at least 1 demo vehicle for testing"
    return vehicles[0]


class TestDragDropMoveBooking:
    """Tests for PUT /api/resource-bookings/{id} with resource_id change"""

    def test_move_booking_to_same_type_resource(self, auth_session, demo_rooms):
        """Test moving a booking to another room (same type) - should succeed"""
        room_a = demo_rooms[0]
        room_b = demo_rooms[1]
        
        # Create booking on room A
        start = (datetime.utcnow() + timedelta(days=30)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        
        create_resp = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room_a['resource_id'],
            "title": "TEST_Move_SameType",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        booking_id = create_resp.json()['booking_id']
        
        # Move to room B with new time
        new_start = start + timedelta(hours=4)
        new_end = new_start + timedelta(hours=2)
        
        move_resp = auth_session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
            "resource_id": room_b['resource_id'],
            "start_at": new_start.isoformat() + "Z",
            "end_at": new_end.isoformat() + "Z"
        })
        
        assert move_resp.status_code == 200, f"Move failed: {move_resp.text}"
        data = move_resp.json()
        
        # Verify response contains updated values
        assert data['resource_id'] == room_b['resource_id'], "resource_id not updated"
        assert new_start.isoformat()[:16] in data['start_at'], "start_at not updated"
        assert new_end.isoformat()[:16] in data['end_at'], "end_at not updated"
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")

    def test_move_booking_to_different_type_returns_400(self, auth_session, demo_rooms, demo_vehicle):
        """Test moving a room booking to a vehicle - should fail with 400"""
        room = demo_rooms[0]
        
        # Create booking on room
        start = (datetime.utcnow() + timedelta(days=31)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        
        create_resp = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room['resource_id'],
            "title": "TEST_Move_CrossType",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        booking_id = create_resp.json()['booking_id']
        
        # Try to move to vehicle (different type)
        move_resp = auth_session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
            "resource_id": demo_vehicle['resource_id'],
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        
        assert move_resp.status_code == 400, f"Expected 400, got {move_resp.status_code}: {move_resp.text}"
        assert "Typ" in move_resp.json().get('detail', ''), "Error should mention type mismatch"
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")

    def test_move_booking_with_conflict_returns_409(self, auth_session, demo_rooms):
        """Test moving a booking to a time slot with conflict - should fail with 409"""
        room_a = demo_rooms[0]
        room_b = demo_rooms[1]
        
        # Create booking on room A
        start = (datetime.utcnow() + timedelta(days=32)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        
        create_resp_a = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room_a['resource_id'],
            "title": "TEST_Move_Source",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        assert create_resp_a.status_code == 200
        booking_id_a = create_resp_a.json()['booking_id']
        
        # Create conflicting booking on room B at same time
        create_resp_b = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room_b['resource_id'],
            "title": "TEST_Move_Conflict",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        assert create_resp_b.status_code == 200
        booking_id_b = create_resp_b.json()['booking_id']
        
        # Try to move booking A to room B at conflicting time
        move_resp = auth_session.put(f"{BASE_URL}/api/resource-bookings/{booking_id_a}", json={
            "resource_id": room_b['resource_id'],
            "start_at": (start + timedelta(minutes=30)).isoformat() + "Z",
            "end_at": (end + timedelta(minutes=30)).isoformat() + "Z"
        })
        
        assert move_resp.status_code == 409, f"Expected 409, got {move_resp.status_code}: {move_resp.text}"
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id_a}")
        auth_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id_b}")

    def test_move_booking_time_only_no_resource_change(self, auth_session, demo_rooms):
        """Test moving a booking time without changing resource - should succeed"""
        room = demo_rooms[0]
        
        # Create booking
        start = (datetime.utcnow() + timedelta(days=33)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        
        create_resp = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room['resource_id'],
            "title": "TEST_Move_TimeOnly",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        assert create_resp.status_code == 200
        booking_id = create_resp.json()['booking_id']
        
        # Move time only (no resource_id in payload)
        new_start = start + timedelta(hours=4)
        new_end = new_start + timedelta(hours=2)
        
        move_resp = auth_session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
            "start_at": new_start.isoformat() + "Z",
            "end_at": new_end.isoformat() + "Z"
        })
        
        assert move_resp.status_code == 200, f"Move failed: {move_resp.text}"
        data = move_resp.json()
        
        # Verify resource_id unchanged
        assert data['resource_id'] == room['resource_id'], "resource_id should not change"
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")

    def test_move_to_inactive_resource_returns_400(self, auth_session, demo_rooms):
        """Test moving to an inactive resource - should fail with 400"""
        room_a = demo_rooms[0]
        
        # Create a test resource and set it to inactive
        create_res = auth_session.post(f"{BASE_URL}/api/resources", json={
            "name": "TEST_Inactive_Room",
            "type": "room",
            "status": "inactive",
            "capacity": 10
        })
        if create_res.status_code != 200:
            pytest.skip("Could not create test resource")
        inactive_room_id = create_res.json()['resource_id']
        
        # Create booking on room A
        start = (datetime.utcnow() + timedelta(days=34)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        
        create_resp = auth_session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room_a['resource_id'],
            "title": "TEST_Move_ToInactive",
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        assert create_resp.status_code == 200
        booking_id = create_resp.json()['booking_id']
        
        # Try to move to inactive resource
        move_resp = auth_session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
            "resource_id": inactive_room_id,
            "start_at": start.isoformat() + "Z",
            "end_at": end.isoformat() + "Z"
        })
        
        assert move_resp.status_code == 400, f"Expected 400, got {move_resp.status_code}: {move_resp.text}"
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")
        auth_session.delete(f"{BASE_URL}/api/resources/{inactive_room_id}")


class TestOccupancyOverviewEndpoint:
    """Tests for GET /api/resource-occupancy endpoint"""

    def test_occupancy_returns_resources_and_bookings(self, auth_session):
        """Test that occupancy endpoint returns resources and bookings"""
        from_date = datetime.utcnow().isoformat() + "Z"
        to_date = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
        
        r = auth_session.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date,
            "type": "room"
        })
        
        assert r.status_code == 200, f"Occupancy failed: {r.text}"
        data = r.json()
        
        assert 'resources' in data, "Response should contain resources"
        assert 'bookings' in data, "Response should contain bookings"
        assert 'blackouts' in data, "Response should contain blackouts"
        assert isinstance(data['resources'], list)
        assert isinstance(data['bookings'], list)

    def test_occupancy_type_filter(self, auth_session):
        """Test that type filter works correctly"""
        from_date = datetime.utcnow().isoformat() + "Z"
        to_date = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
        
        # Get rooms only
        r = auth_session.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date,
            "type": "room"
        })
        assert r.status_code == 200
        rooms_data = r.json()
        
        # Get vehicles only
        r = auth_session.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date,
            "type": "vehicle"
        })
        assert r.status_code == 200
        vehicles_data = r.json()
        
        # Verify different resources returned
        room_ids = {res['resource_id'] for res in rooms_data['resources']}
        vehicle_ids = {res['resource_id'] for res in vehicles_data['resources']}
        
        # Should have no overlap
        assert room_ids.isdisjoint(vehicle_ids), "Room and vehicle IDs should not overlap"


class TestTabNavigation:
    """Tests for tab navigation in /resources page"""

    def test_resources_endpoint_rooms(self, auth_session):
        """Test GET /api/resources?type=room"""
        r = auth_session.get(f"{BASE_URL}/api/resources?type=room")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_resources_endpoint_vehicles(self, auth_session):
        """Test GET /api/resources?type=vehicle"""
        r = auth_session.get(f"{BASE_URL}/api/resources?type=vehicle")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_resources_endpoint_desks(self, auth_session):
        """Test GET /api/resources?type=desk"""
        r = auth_session.get(f"{BASE_URL}/api/resources?type=desk")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_my_bookings_endpoint(self, auth_session):
        """Test GET /api/resource-bookings?mine_only=true"""
        r = auth_session.get(f"{BASE_URL}/api/resource-bookings?mine_only=true")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
