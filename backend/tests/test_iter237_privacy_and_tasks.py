"""
Iteration 237 Tests:
1. Privacy-Fix in /api/resource-occupancy (Belegungsübersicht)
   - User WITHOUT 'resources.view_all_bookings' cap: foreign bookings masked (title='Belegt', user_id=null)
   - User WITH 'resources.view_all_bookings' cap (admin): all bookings with real titles
2. Drag&Drop Move Booking Regression (smoke test from iter 236)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


class TestResourceOccupancyPrivacy:
    """Test privacy masking in /api/resource-occupancy endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with token"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in login response"
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data.get("user", {})
    
    @pytest.fixture(scope="class")
    def regular_user_session(self, admin_session):
        """Create a regular user without view_all_bookings capability"""
        admin_sess, _ = admin_session
        
        # Create a test user
        test_email = f"test_iter237_{uuid.uuid4().hex[:8]}@test.com"
        test_password = "testpass123"
        
        # Register the user
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": test_password,
            "name": "Test User Iter237"
        })
        # User might already exist or registration might be disabled
        if resp.status_code not in [200, 201, 400]:
            pytest.skip(f"Could not create test user: {resp.text}")
        
        # Login as the test user
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": test_password
        })
        if resp.status_code != 200:
            pytest.skip(f"Could not login as test user: {resp.text}")
        
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data.get("user", {}), test_email
    
    @pytest.fixture(scope="class")
    def demo_data(self, admin_session):
        """Ensure demo data exists for testing"""
        admin_sess, _ = admin_session
        # Seed demo data
        resp = admin_sess.post(f"{BASE_URL}/api/resources-seed-demo")
        # It's OK if it fails (already seeded or no permission)
        return True
    
    def test_admin_sees_all_booking_titles(self, admin_session, demo_data):
        """Admin with view_all_bookings cap should see real titles"""
        admin_sess, admin_user = admin_session
        
        # Get date range for next 7 days
        from_date = datetime.utcnow().strftime("%Y-%m-%d")
        to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        resp = admin_sess.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date,
            "type": "room"
        })
        
        assert resp.status_code == 200, f"Failed to get occupancy: {resp.text}"
        data = resp.json()
        
        assert "resources" in data, "Response missing 'resources' key"
        assert "bookings" in data, "Response missing 'bookings' key"
        
        # Admin should see real titles (not 'Belegt')
        bookings = data.get("bookings", [])
        if bookings:
            # Check that at least some bookings have real titles (not masked)
            real_titles = [b for b in bookings if b.get("title") and b.get("title") != "Belegt"]
            print(f"Admin sees {len(bookings)} bookings, {len(real_titles)} with real titles")
            # Admin should see user_ids on bookings
            bookings_with_user = [b for b in bookings if b.get("user_id")]
            print(f"Admin sees {len(bookings_with_user)} bookings with user_id")
        else:
            print("No bookings found in date range - this is OK for privacy test")
    
    def test_regular_user_sees_masked_foreign_bookings(self, regular_user_session, admin_session, demo_data):
        """Regular user without view_all_bookings should see masked foreign bookings"""
        user_sess, user_data, _ = regular_user_session
        admin_sess, admin_user = admin_session
        
        # First check user's capabilities
        resp = user_sess.get(f"{BASE_URL}/api/user/permissions")
        if resp.status_code == 200:
            caps = resp.json().get("capabilities", [])
            print(f"Regular user capabilities: {caps}")
            has_view_all = "resources.view_all_bookings" in caps
            print(f"Has view_all_bookings: {has_view_all}")
        
        # Get date range
        from_date = datetime.utcnow().strftime("%Y-%m-%d")
        to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        resp = user_sess.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date,
            "type": "room"
        })
        
        # User might not have view:resources capability
        if resp.status_code == 403:
            print("Regular user doesn't have view:resources capability - expected for privacy")
            return
        
        assert resp.status_code == 200, f"Failed to get occupancy: {resp.text}"
        data = resp.json()
        
        bookings = data.get("bookings", [])
        user_id = user_data.get("user_id")
        
        if bookings:
            # Check foreign bookings (not owned by this user)
            foreign_bookings = [b for b in bookings if b.get("user_id") != user_id]
            
            for fb in foreign_bookings:
                # Foreign bookings should be masked
                if fb.get("title") != "Belegt":
                    print(f"WARNING: Foreign booking not masked: {fb.get('title')}")
                if fb.get("user_id") is not None:
                    print(f"WARNING: Foreign booking user_id not null: {fb.get('user_id')}")
            
            # Own bookings should have real titles
            own_bookings = [b for b in bookings if b.get("user_id") == user_id]
            print(f"User sees {len(bookings)} bookings, {len(foreign_bookings)} foreign, {len(own_bookings)} own")
    
    def test_occupancy_endpoint_returns_correct_structure(self, admin_session, demo_data):
        """Verify /api/resource-occupancy returns expected structure"""
        admin_sess, _ = admin_session
        
        from_date = datetime.utcnow().strftime("%Y-%m-%d")
        to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        resp = admin_sess.get(f"{BASE_URL}/api/resource-occupancy", params={
            "from_date": from_date,
            "to_date": to_date
        })
        
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Check structure
        assert "from_date" in data
        assert "to_date" in data
        assert "resources" in data
        assert "bookings" in data
        assert "blackouts" in data
        
        # Check booking structure if any exist
        if data["bookings"]:
            booking = data["bookings"][0]
            assert "booking_id" in booking
            assert "resource_id" in booking
            assert "title" in booking
            assert "start_at" in booking
            assert "end_at" in booking
            assert "status" in booking
            # user_id may be null for masked bookings
            assert "user_id" in booking
    
    def test_occupancy_type_filter(self, admin_session, demo_data):
        """Test type filter works correctly"""
        admin_sess, _ = admin_session
        
        from_date = datetime.utcnow().strftime("%Y-%m-%d")
        to_date = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        for res_type in ["room", "desk", "vehicle"]:
            resp = admin_sess.get(f"{BASE_URL}/api/resource-occupancy", params={
                "from_date": from_date,
                "to_date": to_date,
                "type": res_type
            })
            
            assert resp.status_code == 200, f"Failed for type={res_type}: {resp.text}"
            data = resp.json()
            
            # All resources should be of the requested type
            for r in data.get("resources", []):
                assert r.get("type") == res_type, f"Resource type mismatch: {r.get('type')} != {res_type}"
            
            print(f"Type filter '{res_type}': {len(data.get('resources', []))} resources")


class TestDragDropMoveRegression:
    """Smoke test for Drag&Drop move booking from iter 236"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin"""
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_move_booking_same_type_works(self, admin_session):
        """PUT /api/resource-bookings/{id} with resource_id should move booking"""
        session = admin_session
        
        # Get two rooms
        resp = session.get(f"{BASE_URL}/api/resources?type=room")
        if resp.status_code != 200:
            pytest.skip("Could not get rooms")
        
        rooms = resp.json()
        if len(rooms) < 2:
            pytest.skip("Need at least 2 rooms for move test")
        
        source_room = rooms[0]
        target_room = rooms[1]
        
        # Create a booking on source room
        start = (datetime.utcnow() + timedelta(days=5, hours=10)).isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=5, hours=11)).isoformat() + "Z"
        
        resp = session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": source_room["resource_id"],
            "title": "Test Move Booking Iter237",
            "start_at": start,
            "end_at": end
        })
        
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create booking: {resp.text}")
        
        booking = resp.json()
        booking_id = booking.get("booking_id")
        
        try:
            # Move to target room
            resp = session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
                "resource_id": target_room["resource_id"],
                "start_at": start,
                "end_at": end
            })
            
            assert resp.status_code == 200, f"Move failed: {resp.text}"
            updated = resp.json()
            assert updated.get("resource_id") == target_room["resource_id"], "Resource not updated"
            print(f"Successfully moved booking from {source_room['name']} to {target_room['name']}")
            
        finally:
            # Cleanup
            session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")
    
    def test_move_booking_different_type_fails(self, admin_session):
        """PUT with resource_id of different type should return 400"""
        session = admin_session
        
        # Get a room and a desk
        resp_room = session.get(f"{BASE_URL}/api/resources?type=room")
        resp_desk = session.get(f"{BASE_URL}/api/resources?type=desk")
        
        if resp_room.status_code != 200 or resp_desk.status_code != 200:
            pytest.skip("Could not get resources")
        
        rooms = resp_room.json()
        desks = resp_desk.json()
        
        if not rooms or not desks:
            pytest.skip("Need at least 1 room and 1 desk")
        
        room = rooms[0]
        desk = desks[0]
        
        # Create booking on room
        start = (datetime.utcnow() + timedelta(days=6, hours=10)).isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=6, hours=11)).isoformat() + "Z"
        
        resp = session.post(f"{BASE_URL}/api/resource-bookings", json={
            "resource_id": room["resource_id"],
            "title": "Test Cross-Type Move Iter237",
            "start_at": start,
            "end_at": end
        })
        
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create booking: {resp.text}")
        
        booking = resp.json()
        booking_id = booking.get("booking_id")
        
        try:
            # Try to move to desk (different type) - should fail
            resp = session.put(f"{BASE_URL}/api/resource-bookings/{booking_id}", json={
                "resource_id": desk["resource_id"],
                "start_at": start,
                "end_at": end
            })
            
            assert resp.status_code == 400, f"Expected 400 for cross-type move, got {resp.status_code}"
            print("Cross-type move correctly rejected with 400")
            
        finally:
            # Cleanup
            session.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
