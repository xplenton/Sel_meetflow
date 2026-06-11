"""
Iter 241 Backend Tests:
1. Floorplan Position: PUT /api/resources/{resource_id}/floorplan accepts x,y,width,height,floor_plan_id for ALL types (room, desk, vehicle)
2. Floorplan Items: GET /api/floorplans/{id}/items?type=room returns placed rooms, type=vehicle returns vehicles
3. Office-Days: GET /api/users/me/office-days (initial empty config)
4. Office-Days: PUT /api/users/me/office-days with validation (weekdays, time format, desk existence)
5. Office-Days Generate: POST /api/users/me/office-days/generate creates desk bookings
6. Office-Days Idempotency: Second generate call should skip already booked days
7. Office-Days Validations: generate without weekdays/desk returns 400
"""
import pytest
import requests
import os
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
    if "token" in data:
        session.headers.update({"Authorization": f"Bearer {data['token']}"})
    return session


@pytest.fixture(scope="module")
def member_session():
    """Login as member (reviewmember@test.com) and return session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "reviewmember@test.com",
        "password": "member123!"
    })
    if resp.status_code != 200:
        # Try to register if not exists
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": "reviewmember@test.com",
            "password": "member123!",
            "name": "Review Member"
        })
        if reg_resp.status_code in [200, 201]:
            data = reg_resp.json()
            if "token" in data:
                session.headers.update({"Authorization": f"Bearer {data['token']}"})
            return session
        pytest.skip(f"Could not login/register member: {resp.text}")
    
    data = resp.json()
    if "token" in data:
        session.headers.update({"Authorization": f"Bearer {data['token']}"})
    return session


@pytest.fixture(scope="module")
def test_desk(admin_session):
    """Create or find a test desk for office-days testing."""
    # First try to find existing desk
    resp = admin_session.get(f"{BASE_URL}/api/resources?type=desk")
    if resp.status_code == 200:
        desks = resp.json()
        if desks:
            return desks[0]
    
    # Create a new desk
    desk_id = f"res_test_{uuid.uuid4().hex[:10]}"
    resp = admin_session.post(f"{BASE_URL}/api/resources", json={
        "resource_id": desk_id,
        "name": f"Test_Desk_Iter241_{uuid.uuid4().hex[:6]}",
        "type": "desk",
        "location": "Test Building",
        "status": "active",
        "desk_number": f"DSK-TEST-{uuid.uuid4().hex[:4]}"
    })
    if resp.status_code in [200, 201]:
        return resp.json()
    
    pytest.skip("Could not create test desk")


@pytest.fixture(scope="module")
def test_room(admin_session):
    """Create or find a test room for floorplan testing."""
    resp = admin_session.get(f"{BASE_URL}/api/resources?type=room")
    if resp.status_code == 200:
        rooms = resp.json()
        if rooms:
            return rooms[0]
    
    # Create a new room
    room_id = f"res_test_{uuid.uuid4().hex[:10]}"
    resp = admin_session.post(f"{BASE_URL}/api/resources", json={
        "resource_id": room_id,
        "name": f"Test_Room_Iter241_{uuid.uuid4().hex[:6]}",
        "type": "room",
        "location": "Test Building",
        "status": "active",
        "capacity": 10
    })
    if resp.status_code in [200, 201]:
        return resp.json()
    
    pytest.skip("Could not create test room")


@pytest.fixture(scope="module")
def test_vehicle(admin_session):
    """Create or find a test vehicle for floorplan testing."""
    resp = admin_session.get(f"{BASE_URL}/api/resources?type=vehicle")
    if resp.status_code == 200:
        vehicles = resp.json()
        if vehicles:
            return vehicles[0]
    
    # Create a new vehicle
    vehicle_id = f"res_test_{uuid.uuid4().hex[:10]}"
    resp = admin_session.post(f"{BASE_URL}/api/resources", json={
        "resource_id": vehicle_id,
        "name": f"Test_Vehicle_Iter241_{uuid.uuid4().hex[:6]}",
        "type": "vehicle",
        "license_plate": f"B-TEST-{uuid.uuid4().hex[:4].upper()}",
        "status": "active"
    })
    if resp.status_code in [200, 201]:
        return resp.json()
    
    pytest.skip("Could not create test vehicle")


# ============================================================================
# Test: Floorplan Position for ALL resource types (room, desk, vehicle)
# ============================================================================
class TestFloorplanPositionAllTypes:
    """Test PUT /api/resources/{resource_id}/floorplan for all resource types."""
    
    def test_set_room_floorplan_position(self, admin_session, test_room):
        """PUT /api/resources/{room_id}/floorplan should work for rooms."""
        room_id = test_room["resource_id"]
        
        resp = admin_session.put(f"{BASE_URL}/api/resources/{room_id}/floorplan", json={
            "x": 0.2,
            "y": 0.3,
            "width": 0.1,
            "height": 0.08,
            "floor_plan_id": "default"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("x") == 0.2, f"Expected x=0.2, got {data.get('x')}"
        assert data.get("y") == 0.3, f"Expected y=0.3, got {data.get('y')}"
        assert data.get("floor_plan_id") == "default"
    
    def test_set_vehicle_floorplan_position(self, admin_session, test_vehicle):
        """PUT /api/resources/{vehicle_id}/floorplan should work for vehicles."""
        vehicle_id = test_vehicle["resource_id"]
        
        resp = admin_session.put(f"{BASE_URL}/api/resources/{vehicle_id}/floorplan", json={
            "x": 0.5,
            "y": 0.5,
            "width": 0.08,
            "height": 0.06,
            "floor_plan_id": "default"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("x") == 0.5, f"Expected x=0.5, got {data.get('x')}"
        assert data.get("y") == 0.5, f"Expected y=0.5, got {data.get('y')}"
    
    def test_set_desk_floorplan_position(self, admin_session, test_desk):
        """PUT /api/resources/{desk_id}/floorplan should work for desks."""
        desk_id = test_desk["resource_id"]
        
        resp = admin_session.put(f"{BASE_URL}/api/resources/{desk_id}/floorplan", json={
            "x": 0.7,
            "y": 0.4,
            "width": 0.06,
            "height": 0.06,
            "floor_plan_id": "default"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("x") == 0.7
        assert data.get("y") == 0.4
    
    def test_floorplan_position_validation_out_of_range(self, admin_session, test_desk):
        """Coordinates outside 0..1 should return 400."""
        desk_id = test_desk["resource_id"]
        
        resp = admin_session.put(f"{BASE_URL}/api/resources/{desk_id}/floorplan", json={
            "x": 1.5,  # Invalid: > 1
            "y": 0.3,
            "floor_plan_id": "default"
        })
        assert resp.status_code == 400, f"Expected 400 for x=1.5, got {resp.status_code}"


# ============================================================================
# Test: GET /api/floorplans/{id}/items with type filter
# ============================================================================
class TestFloorplanItemsTypeFilter:
    """Test GET /api/floorplans/{id}/items?type=room|vehicle|desk."""
    
    def test_floorplan_items_type_room(self, admin_session, test_room):
        """GET /api/floorplans/default/items?type=room should return placed rooms."""
        # First ensure room is placed
        room_id = test_room["resource_id"]
        admin_session.put(f"{BASE_URL}/api/resources/{room_id}/floorplan", json={
            "x": 0.2, "y": 0.3, "floor_plan_id": "default"
        })
        
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items?type=room")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "items" in data, "Response missing 'items' field"
        
        # All items should be rooms
        for item in data.get("items", []):
            assert item.get("type") == "room", f"Expected type=room, got {item.get('type')}"
    
    def test_floorplan_items_type_vehicle(self, admin_session, test_vehicle):
        """GET /api/floorplans/default/items?type=vehicle should return placed vehicles."""
        # First ensure vehicle is placed
        vehicle_id = test_vehicle["resource_id"]
        admin_session.put(f"{BASE_URL}/api/resources/{vehicle_id}/floorplan", json={
            "x": 0.5, "y": 0.5, "floor_plan_id": "default"
        })
        
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items?type=vehicle")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "items" in data
        
        # All items should be vehicles
        for item in data.get("items", []):
            assert item.get("type") == "vehicle", f"Expected type=vehicle, got {item.get('type')}"
    
    def test_floorplan_items_no_filter_returns_all(self, admin_session):
        """GET /api/floorplans/default/items without type returns all types."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "items" in data
        assert "floor_plan_id" in data
        assert "at" in data


# ============================================================================
# Test: Office-Days GET/PUT endpoints
# ============================================================================
class TestOfficeDaysConfig:
    """Test GET/PUT /api/users/me/office-days."""
    
    def test_get_office_days_initial_empty(self, member_session):
        """GET /api/users/me/office-days should return default config."""
        resp = member_session.get(f"{BASE_URL}/api/users/me/office-days")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # Check default structure
        assert "weekdays" in data, "Missing 'weekdays' field"
        assert "preferred_desk_id" in data, "Missing 'preferred_desk_id' field"
        assert "start_time" in data, "Missing 'start_time' field"
        assert "end_time" in data, "Missing 'end_time' field"
        assert "title" in data, "Missing 'title' field"
        
        # Default values
        assert data.get("start_time") == "08:00", f"Expected start_time=08:00, got {data.get('start_time')}"
        assert data.get("end_time") == "17:00", f"Expected end_time=17:00, got {data.get('end_time')}"
    
    def test_put_office_days_valid(self, member_session, test_desk):
        """PUT /api/users/me/office-days with valid data should return 200."""
        desk_id = test_desk["resource_id"]
        
        resp = member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["tue", "thu"],
            "preferred_desk_id": desk_id,
            "start_time": "09:00",
            "end_time": "17:00",
            "title": "Bürotag"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("weekdays") == ["tue", "thu"]
        assert data.get("preferred_desk_id") == desk_id
        assert data.get("start_time") == "09:00"
    
    def test_put_office_days_invalid_weekday(self, member_session, test_desk):
        """PUT with invalid weekday (e.g., 'xyz') should return 400."""
        desk_id = test_desk["resource_id"]
        
        resp = member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["xyz", "tue"],  # 'xyz' is invalid
            "preferred_desk_id": desk_id,
            "start_time": "09:00",
            "end_time": "17:00"
        })
        assert resp.status_code == 400, f"Expected 400 for invalid weekday, got {resp.status_code}: {resp.text}"
    
    def test_put_office_days_invalid_time_format(self, member_session, test_desk):
        """PUT with invalid time format (e.g., '25:99') should return 400."""
        desk_id = test_desk["resource_id"]
        
        resp = member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["mon"],
            "preferred_desk_id": desk_id,
            "start_time": "25:99",  # Invalid time
            "end_time": "17:00"
        })
        assert resp.status_code == 400, f"Expected 400 for invalid time, got {resp.status_code}: {resp.text}"
    
    def test_put_office_days_end_before_start(self, member_session, test_desk):
        """PUT with end_time <= start_time should return 400."""
        desk_id = test_desk["resource_id"]
        
        resp = member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["mon"],
            "preferred_desk_id": desk_id,
            "start_time": "17:00",
            "end_time": "09:00"  # End before start
        })
        assert resp.status_code == 400, f"Expected 400 for end<=start, got {resp.status_code}: {resp.text}"
    
    def test_put_office_days_nonexistent_desk(self, member_session):
        """PUT with non-existent desk_id should return 404."""
        resp = member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["mon"],
            "preferred_desk_id": "nonexistent_desk_id_12345",
            "start_time": "09:00",
            "end_time": "17:00"
        })
        assert resp.status_code == 404, f"Expected 404 for nonexistent desk, got {resp.status_code}: {resp.text}"


# ============================================================================
# Test: Office-Days Generate endpoint
# ============================================================================
class TestOfficeDaysGenerate:
    """Test POST /api/users/me/office-days/generate."""
    
    def test_generate_without_weekdays_returns_400(self, member_session):
        """Generate without weekdays configured should return 400."""
        # First clear weekdays
        member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": [],
            "preferred_desk_id": None,
            "start_time": "09:00",
            "end_time": "17:00"
        })
        
        resp = member_session.post(f"{BASE_URL}/api/users/me/office-days/generate", json={})
        assert resp.status_code == 400, f"Expected 400 without weekdays, got {resp.status_code}: {resp.text}"
        assert "Keine Standard-Buerotage" in resp.text or "weekdays" in resp.text.lower()
    
    def test_generate_without_desk_returns_400(self, member_session):
        """Generate without preferred_desk_id should return 400."""
        # Set weekdays but no desk
        member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["mon", "wed"],
            "preferred_desk_id": None,
            "start_time": "09:00",
            "end_time": "17:00"
        })
        
        resp = member_session.post(f"{BASE_URL}/api/users/me/office-days/generate", json={})
        assert resp.status_code == 400, f"Expected 400 without desk, got {resp.status_code}: {resp.text}"
        assert "Arbeitsplatz" in resp.text or "desk" in resp.text.lower()
    
    def test_generate_creates_bookings(self, member_session, test_desk):
        """Generate with valid config should create bookings."""
        desk_id = test_desk["resource_id"]
        
        # Configure office days
        put_resp = member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["mon", "wed", "fri"],
            "preferred_desk_id": desk_id,
            "start_time": "09:00",
            "end_time": "17:00",
            "title": "Test Bürotag"
        })
        assert put_resp.status_code == 200, f"Config failed: {put_resp.text}"
        
        # Generate bookings
        resp = member_session.post(f"{BASE_URL}/api/users/me/office-days/generate", json={
            "weeks": 2  # Generate for 2 weeks
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "created" in data, "Response missing 'created' field"
        assert "created_count" in data, "Response missing 'created_count' field"
        assert "skipped_already_booked" in data, "Response missing 'skipped_already_booked' field"
        assert "skipped_desk_conflict" in data, "Response missing 'skipped_desk_conflict' field"
        assert "weeks" in data, "Response missing 'weeks' field"
        
        # Should have created some bookings (depends on current day)
        print(f"Created {data['created_count']} bookings, skipped {len(data.get('skipped_already_booked', []))} already booked")
    
    def test_generate_idempotent(self, member_session, test_desk):
        """Second generate call should skip already booked days."""
        desk_id = test_desk["resource_id"]
        
        # Ensure config is set
        member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["mon", "wed", "fri"],
            "preferred_desk_id": desk_id,
            "start_time": "09:00",
            "end_time": "17:00"
        })
        
        # First generate
        resp1 = member_session.post(f"{BASE_URL}/api/users/me/office-days/generate", json={"weeks": 2})
        assert resp1.status_code == 200
        data1 = resp1.json()
        first_created = data1.get("created_count", 0)
        
        # Second generate (should be idempotent)
        resp2 = member_session.post(f"{BASE_URL}/api/users/me/office-days/generate", json={"weeks": 2})
        assert resp2.status_code == 200
        data2 = resp2.json()
        
        # Second call should create 0 new bookings (all skipped)
        second_created = data2.get("created_count", 0)
        skipped = len(data2.get("skipped_already_booked", []))
        
        print(f"First call created: {first_created}, Second call created: {second_created}, skipped: {skipped}")
        
        # If first call created bookings, second should create 0
        if first_created > 0:
            assert second_created == 0, f"Expected 0 new bookings on second call, got {second_created}"


# ============================================================================
# Test: Office-Days with inactive/deleted desk
# ============================================================================
class TestOfficeDaysInactiveDesk:
    """Test generate with inactive desk returns 404."""
    
    def test_generate_with_inactive_desk(self, admin_session, member_session):
        """Generate with inactive desk should return 404."""
        # Create an inactive desk
        inactive_desk_id = f"res_inactive_{uuid.uuid4().hex[:10]}"
        create_resp = admin_session.post(f"{BASE_URL}/api/resources", json={
            "resource_id": inactive_desk_id,
            "name": f"Inactive_Desk_{uuid.uuid4().hex[:6]}",
            "type": "desk",
            "status": "inactive"  # Inactive!
        })
        
        if create_resp.status_code not in [200, 201]:
            pytest.skip("Could not create inactive desk")
        
        # Configure with inactive desk
        put_resp = member_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["mon"],
            "preferred_desk_id": inactive_desk_id,
            "start_time": "09:00",
            "end_time": "17:00"
        })
        
        # PUT might succeed (desk exists) but generate should fail
        if put_resp.status_code == 200:
            gen_resp = member_session.post(f"{BASE_URL}/api/users/me/office-days/generate", json={})
            assert gen_resp.status_code == 404, f"Expected 404 for inactive desk, got {gen_resp.status_code}: {gen_resp.text}"


# ============================================================================
# Test: Admin can access office-days endpoints
# ============================================================================
class TestOfficeDaysAdminAccess:
    """Test that admin can also use office-days endpoints."""
    
    def test_admin_get_office_days(self, admin_session):
        """Admin should be able to GET their office-days config."""
        resp = admin_session.get(f"{BASE_URL}/api/users/me/office-days")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    def test_admin_put_office_days(self, admin_session, test_desk):
        """Admin should be able to PUT their office-days config."""
        desk_id = test_desk["resource_id"]
        
        resp = admin_session.put(f"{BASE_URL}/api/users/me/office-days", json={
            "weekdays": ["tue", "thu"],
            "preferred_desk_id": desk_id,
            "start_time": "08:00",
            "end_time": "16:00"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
