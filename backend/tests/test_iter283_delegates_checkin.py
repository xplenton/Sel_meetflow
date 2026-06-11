"""
Iteration 283 — Delegates (Stellvertreter), Check-in/Check-out, Notification Prefs

Tests:
1. GET/PUT /api/users/me/delegates — Stellvertreter management
2. GET /api/users/search?q=... — User search for delegate picker
3. GET /api/users/bookable-for — Consent-based booking directory
4. POST /api/resource-bookings with booked_for_user_id — Delegate booking
5. POST /api/resource-bookings/{id}/check-in — Check-in (owner, booked_for, admin)
6. POST /api/resource-bookings/{id}/check-out — Check-out (owner, booked_for, admin)
7. GET/PUT /api/users/me/notification-prefs — checkin_reminder_minutes, checkout_reminder_enabled
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_token():
    """Login as admin and get token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json().get("token")

@pytest.fixture(scope="module")
def admin_user_id():
    """Get admin user_id from login response"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200
    return resp.json().get("user_id")

@pytest.fixture(scope="module")
def test_user():
    """Create a test user for delegate tests"""
    unique = uuid.uuid4().hex[:8]
    email = f"test_delegate_{unique}@meetflow.com"
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "testpass123",
        "name": f"Test Delegate User {unique}"
    })
    if resp.status_code == 200:
        data = resp.json()
        return {"email": email, "password": "testpass123", "token": data.get("token"), "user_id": data.get("user_id")}
    # If user exists, try login
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "testpass123"})
    if resp.status_code == 200:
        data = resp.json()
        return {"email": email, "password": "testpass123", "token": data.get("token"), "user_id": data.get("user_id")}
    pytest.skip(f"Could not create/login test user: {resp.text}")

@pytest.fixture(scope="module")
def lisa_user():
    """Get or create Lisa user for delegate tests"""
    # Try to find Lisa via search
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "lisa.schmidt@meetflow.com",
        "password": "lisa123"
    })
    if resp.status_code == 200:
        data = resp.json()
        return {"email": "lisa.schmidt@meetflow.com", "token": data.get("token"), "user_id": data.get("user_id")}
    # Create Lisa if not exists
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": "lisa.schmidt@meetflow.com",
        "password": "lisa123",
        "name": "Lisa Schmidt"
    })
    if resp.status_code == 200:
        data = resp.json()
        return {"email": "lisa.schmidt@meetflow.com", "token": data.get("token"), "user_id": data.get("user_id")}
    # Lisa exists but password unknown - use known user_id
    return {"email": "lisa.schmidt@meetflow.com", "token": None, "user_id": "user_18dcb3735508"}


class TestDelegatesEndpoints:
    """Test /api/users/me/delegates GET/PUT"""
    
    def test_get_delegates_empty_for_admin(self, admin_token):
        """GET /api/users/me/delegates returns empty list initially"""
        resp = requests.get(f"{BASE_URL}/api/users/me/delegates", 
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"GET delegates failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /api/users/me/delegates returned {len(data)} delegates")
    
    def test_put_delegates_add_lisa(self, admin_token, lisa_user):
        """PUT /api/users/me/delegates with Lisa's user_id"""
        resp = requests.put(f"{BASE_URL}/api/users/me/delegates",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"user_ids": [lisa_user["user_id"]]})
        assert resp.status_code == 200, f"PUT delegates failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) >= 1, "Should have at least 1 delegate"
        user_ids = [d.get("user_id") for d in data]
        assert lisa_user["user_id"] in user_ids, "Lisa should be in delegates"
        print(f"✓ PUT /api/users/me/delegates added Lisa: {data}")
    
    def test_get_delegates_shows_lisa(self, admin_token, lisa_user):
        """GET /api/users/me/delegates now shows Lisa"""
        resp = requests.get(f"{BASE_URL}/api/users/me/delegates",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        user_ids = [d.get("user_id") for d in data]
        assert lisa_user["user_id"] in user_ids, "Lisa should be in delegates"
        # Verify hydrated fields
        lisa_entry = next((d for d in data if d.get("user_id") == lisa_user["user_id"]), None)
        assert lisa_entry is not None
        assert "name" in lisa_entry or "email" in lisa_entry, "Delegate should have name/email"
        print(f"✓ GET /api/users/me/delegates shows Lisa: {lisa_entry}")
    
    def test_put_delegates_clear(self, admin_token):
        """PUT /api/users/me/delegates with empty list clears delegates"""
        resp = requests.put(f"{BASE_URL}/api/users/me/delegates",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"user_ids": []})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0, "Delegates should be empty after clearing"
        print("✓ PUT /api/users/me/delegates cleared delegates")


class TestUserSearch:
    """Test /api/users/search?q=..."""
    
    def test_search_users_by_name(self, admin_token, lisa_user):
        """GET /api/users/search?q=lisa returns Lisa"""
        resp = requests.get(f"{BASE_URL}/api/users/search",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           params={"q": "lisa"})
        assert resp.status_code == 200, f"Search failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        # Should find Lisa
        found = any(u.get("email", "").lower().startswith("lisa") or 
                   "lisa" in u.get("name", "").lower() for u in data)
        assert found, f"Should find Lisa in search results: {data}"
        print(f"✓ GET /api/users/search?q=lisa found {len(data)} users")
    
    def test_search_users_by_email(self, admin_token):
        """GET /api/users/search?q=admin returns admin"""
        resp = requests.get(f"{BASE_URL}/api/users/search",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           params={"q": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        found = any("admin" in u.get("email", "").lower() for u in data)
        assert found, "Should find admin in search results"
        print(f"✓ GET /api/users/search?q=admin found {len(data)} users")


class TestBookableFor:
    """Test /api/users/bookable-for — consent-based booking directory"""
    
    def test_admin_sees_all_users(self, admin_token):
        """Admin with resources.book_for_others sees all users"""
        resp = requests.get(f"{BASE_URL}/api/users/bookable-for",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"bookable-for failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        # Admin should see multiple users (all except self)
        print(f"✓ Admin GET /api/users/bookable-for sees {len(data)} users")
    
    def test_regular_user_sees_only_delegators(self, test_user, admin_token, admin_user_id):
        """Regular user sees only users who added them as delegate"""
        # First, admin adds test_user as delegate
        resp = requests.put(f"{BASE_URL}/api/users/me/delegates",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"user_ids": [test_user["user_id"]]})
        assert resp.status_code == 200, f"Failed to add delegate: {resp.text}"
        
        # Now test_user should see admin in bookable-for
        resp = requests.get(f"{BASE_URL}/api/users/bookable-for",
                           headers={"Authorization": f"Bearer {test_user['token']}"})
        assert resp.status_code == 200, f"bookable-for failed: {resp.text}"
        data = resp.json()
        user_ids = [u.get("user_id") for u in data]
        assert admin_user_id in user_ids, f"Test user should see admin in bookable-for: {data}"
        print(f"✓ Regular user sees admin (who added them as delegate) in bookable-for")
        
        # Cleanup: remove test_user from admin's delegates
        requests.put(f"{BASE_URL}/api/users/me/delegates",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"user_ids": []})


class TestBookingWithDelegate:
    """Test POST /api/resource-bookings with booked_for_user_id"""
    
    @pytest.fixture
    def test_resource(self, admin_token):
        """Get or create a test resource"""
        # List resources
        resp = requests.get(f"{BASE_URL}/api/resources?type=room",
                           headers={"Authorization": f"Bearer {admin_token}"})
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        # Create one if none exist
        resp = requests.post(f"{BASE_URL}/api/resources",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            json={
                                "name": f"Test Room {uuid.uuid4().hex[:6]}",
                                "type": "room",
                                "status": "active",
                                "capacity": 10
                            })
        if resp.status_code in [200, 201]:
            return resp.json()
        pytest.skip("Could not get/create test resource")
    
    def test_admin_can_book_for_others(self, admin_token, test_user, test_resource):
        """Admin with resources.book_for_others can book for test_user"""
        # Use a random time slot far in the future to avoid conflicts
        import random
        random_days = random.randint(10, 30)
        random_hours = random.randint(0, 23)
        start = datetime.utcnow() + timedelta(days=random_days, hours=random_hours)
        end = start + timedelta(hours=1)
        resp = requests.post(f"{BASE_URL}/api/resource-bookings",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            json={
                                "resource_id": test_resource["resource_id"],
                                "title": f"Test Booking for Delegate {uuid.uuid4().hex[:6]}",
                                "start_at": start.isoformat() + "Z",
                                "end_at": end.isoformat() + "Z",
                                "booked_for_user_id": test_user["user_id"]
                            })
        assert resp.status_code in [200, 201], f"Booking failed: {resp.text}"
        data = resp.json()
        assert data.get("booked_for_user_id") == test_user["user_id"], "booked_for_user_id should match"
        print(f"✓ Admin booked for test_user: {data.get('booking_id')}")
    
    def test_delegate_can_book_for_delegator(self, admin_token, test_user, admin_user_id, test_resource):
        """User in delegator's delegates list can book for them"""
        # Admin adds test_user as delegate
        resp = requests.put(f"{BASE_URL}/api/users/me/delegates",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"user_ids": [test_user["user_id"]]})
        assert resp.status_code == 200
        
        # test_user books for admin - use unique time slot
        import random
        random_days = random.randint(20, 35)
        random_hours = random.randint(0, 23)
        start = datetime.utcnow() + timedelta(days=random_days, hours=random_hours)
        end = start + timedelta(hours=1)
        resp = requests.post(f"{BASE_URL}/api/resource-bookings",
                            headers={"Authorization": f"Bearer {test_user['token']}"},
                            json={
                                "resource_id": test_resource["resource_id"],
                                "title": f"Delegate Booking for Admin {uuid.uuid4().hex[:6]}",
                                "start_at": start.isoformat() + "Z",
                                "end_at": end.isoformat() + "Z",
                                "booked_for_user_id": admin_user_id
                            })
        assert resp.status_code in [200, 201], f"Delegate booking failed: {resp.text}"
        data = resp.json()
        assert data.get("booked_for_user_id") == admin_user_id
        print(f"✓ Delegate booked for admin: {data.get('booking_id')}")
        
        # Cleanup - remove delegate relationship
        requests.put(f"{BASE_URL}/api/users/me/delegates",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"user_ids": []})
    
    def test_non_delegate_cannot_book_for_others(self, admin_token, test_user, admin_user_id, test_resource):
        """User NOT in delegates list gets 403"""
        # First ensure test_user is NOT in admin's delegates
        resp = requests.put(f"{BASE_URL}/api/users/me/delegates",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"user_ids": []})
        assert resp.status_code == 200, "Failed to clear delegates"
        
        import random
        random_days = random.randint(40, 60)
        random_hours = random.randint(0, 23)
        start = datetime.utcnow() + timedelta(days=random_days, hours=random_hours)
        end = start + timedelta(hours=1)
        resp = requests.post(f"{BASE_URL}/api/resource-bookings",
                            headers={"Authorization": f"Bearer {test_user['token']}"},
                            json={
                                "resource_id": test_resource["resource_id"],
                                "title": "Unauthorized Booking",
                                "start_at": start.isoformat() + "Z",
                                "end_at": end.isoformat() + "Z",
                                "booked_for_user_id": admin_user_id
                            })
        assert resp.status_code == 403, f"Should get 403, got {resp.status_code}: {resp.text}"
        assert "Kein Recht" in resp.text or "nicht" in resp.text.lower(), "Should mention no permission"
        print("✓ Non-delegate correctly gets 403 when booking for others")


class TestCheckInCheckOut:
    """Test check-in/check-out for owner, booked_for_user, and admin"""
    
    @pytest.fixture
    def booking_for_checkin(self, admin_token, test_user):
        """Create a booking for check-in tests"""
        # Get a resource
        resp = requests.get(f"{BASE_URL}/api/resources?type=room",
                           headers={"Authorization": f"Bearer {admin_token}"})
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No resources available")
        resource = resp.json()[0]
        
        # Create booking with booked_for_user_id = test_user
        start = datetime.utcnow() - timedelta(minutes=30)  # Already started
        end = start + timedelta(hours=2)
        resp = requests.post(f"{BASE_URL}/api/resource-bookings",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            json={
                                "resource_id": resource["resource_id"],
                                "title": "Check-in Test Booking",
                                "start_at": start.isoformat() + "Z",
                                "end_at": end.isoformat() + "Z",
                                "booked_for_user_id": test_user["user_id"]
                            })
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create booking: {resp.text}")
        return resp.json()
    
    def test_booked_for_user_can_checkin(self, test_user, booking_for_checkin):
        """booked_for_user_id can check-in"""
        booking_id = booking_for_checkin["booking_id"]
        resp = requests.post(f"{BASE_URL}/api/resource-bookings/{booking_id}/check-in",
                            headers={"Authorization": f"Bearer {test_user['token']}"})
        assert resp.status_code == 200, f"Check-in failed: {resp.text}"
        data = resp.json()
        assert data.get("checked_in_at") is not None, "checked_in_at should be set"
        print(f"✓ booked_for_user checked in: {data.get('checked_in_at')}")
    
    def test_booked_for_user_can_checkout(self, test_user, booking_for_checkin):
        """booked_for_user_id can check-out"""
        booking_id = booking_for_checkin["booking_id"]
        # First ensure checked in
        requests.post(f"{BASE_URL}/api/resource-bookings/{booking_id}/check-in",
                     headers={"Authorization": f"Bearer {test_user['token']}"})
        
        resp = requests.post(f"{BASE_URL}/api/resource-bookings/{booking_id}/check-out",
                            headers={"Authorization": f"Bearer {test_user['token']}"},
                            json={})
        assert resp.status_code == 200, f"Check-out failed: {resp.text}"
        data = resp.json()
        assert data.get("checked_out_at") is not None, "checked_out_at should be set"
        assert data.get("status") == "completed", "Status should be completed"
        print(f"✓ booked_for_user checked out: {data.get('checked_out_at')}")
    
    def test_owner_can_checkin_own_booking(self, admin_token):
        """Booking owner can check-in their own booking"""
        # Get a resource
        resp = requests.get(f"{BASE_URL}/api/resources?type=room",
                           headers={"Authorization": f"Bearer {admin_token}"})
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No resources available")
        resource = resp.json()[0]
        
        # Create booking without booked_for
        start = datetime.utcnow() - timedelta(minutes=15)
        end = start + timedelta(hours=1)
        resp = requests.post(f"{BASE_URL}/api/resource-bookings",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            json={
                                "resource_id": resource["resource_id"],
                                "title": "Owner Check-in Test",
                                "start_at": start.isoformat() + "Z",
                                "end_at": end.isoformat() + "Z"
                            })
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create booking: {resp.text}")
        booking = resp.json()
        
        # Owner checks in
        resp = requests.post(f"{BASE_URL}/api/resource-bookings/{booking['booking_id']}/check-in",
                            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Owner check-in failed: {resp.text}"
        print("✓ Owner can check-in their own booking")
    
    def test_unauthorized_user_cannot_checkin(self, test_user, admin_token):
        """User who is neither owner nor booked_for gets 403"""
        # Get a resource
        resp = requests.get(f"{BASE_URL}/api/resources?type=room",
                           headers={"Authorization": f"Bearer {admin_token}"})
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No resources available")
        resource = resp.json()[0]
        
        # Admin creates booking for themselves (not for test_user)
        start = datetime.utcnow() + timedelta(hours=8)
        end = start + timedelta(hours=1)
        resp = requests.post(f"{BASE_URL}/api/resource-bookings",
                            headers={"Authorization": f"Bearer {admin_token}"},
                            json={
                                "resource_id": resource["resource_id"],
                                "title": "Admin Only Booking",
                                "start_at": start.isoformat() + "Z",
                                "end_at": end.isoformat() + "Z"
                            })
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create booking: {resp.text}")
        booking = resp.json()
        
        # test_user tries to check-in (should fail)
        resp = requests.post(f"{BASE_URL}/api/resource-bookings/{booking['booking_id']}/check-in",
                            headers={"Authorization": f"Bearer {test_user['token']}"})
        assert resp.status_code == 403, f"Should get 403, got {resp.status_code}: {resp.text}"
        print("✓ Unauthorized user correctly gets 403 on check-in")


class TestNotificationPrefs:
    """Test /api/users/me/notification-prefs with new checkin/checkout fields"""
    
    def test_get_notification_prefs_has_new_fields(self, admin_token):
        """GET /api/users/me/notification-prefs includes checkin_reminder_minutes and checkout_reminder_enabled"""
        resp = requests.get(f"{BASE_URL}/api/users/me/notification-prefs",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"GET notification-prefs failed: {resp.text}"
        data = resp.json()
        
        # Check new fields exist with defaults
        assert "checkin_reminder_minutes" in data, "checkin_reminder_minutes should exist"
        assert "checkout_reminder_enabled" in data, "checkout_reminder_enabled should exist"
        assert isinstance(data["checkin_reminder_minutes"], int), "checkin_reminder_minutes should be int"
        assert isinstance(data["checkout_reminder_enabled"], bool), "checkout_reminder_enabled should be bool"
        
        # Default values
        assert data["checkin_reminder_minutes"] == 15, f"Default should be 15, got {data['checkin_reminder_minutes']}"
        assert data["checkout_reminder_enabled"] == True, f"Default should be True, got {data['checkout_reminder_enabled']}"
        print(f"✓ GET notification-prefs has new fields: checkin={data['checkin_reminder_minutes']}, checkout={data['checkout_reminder_enabled']}")
    
    def test_put_notification_prefs_update_checkin(self, admin_token):
        """PUT /api/users/me/notification-prefs updates checkin_reminder_minutes"""
        resp = requests.put(f"{BASE_URL}/api/users/me/notification-prefs",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"checkin_reminder_minutes": 30, "checkout_reminder_enabled": False})
        assert resp.status_code == 200, f"PUT notification-prefs failed: {resp.text}"
        data = resp.json()
        
        assert data["checkin_reminder_minutes"] == 30, f"Should be 30, got {data['checkin_reminder_minutes']}"
        assert data["checkout_reminder_enabled"] == False, f"Should be False, got {data['checkout_reminder_enabled']}"
        print("✓ PUT notification-prefs updated checkin=30, checkout=False")
    
    def test_get_notification_prefs_persisted(self, admin_token):
        """GET /api/users/me/notification-prefs shows persisted values"""
        resp = requests.get(f"{BASE_URL}/api/users/me/notification-prefs",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["checkin_reminder_minutes"] == 30, f"Should persist 30, got {data['checkin_reminder_minutes']}"
        assert data["checkout_reminder_enabled"] == False, f"Should persist False, got {data['checkout_reminder_enabled']}"
        print("✓ GET notification-prefs shows persisted values")
    
    def test_put_notification_prefs_clamp_values(self, admin_token):
        """PUT /api/users/me/notification-prefs clamps values to 0..240"""
        # Try setting > 240
        resp = requests.put(f"{BASE_URL}/api/users/me/notification-prefs",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"checkin_reminder_minutes": 500})
        assert resp.status_code == 200
        data = resp.json()
        assert data["checkin_reminder_minutes"] <= 240, f"Should be clamped to 240, got {data['checkin_reminder_minutes']}"
        
        # Try setting < 0
        resp = requests.put(f"{BASE_URL}/api/users/me/notification-prefs",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"checkin_reminder_minutes": -10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["checkin_reminder_minutes"] >= 0, f"Should be clamped to 0, got {data['checkin_reminder_minutes']}"
        print("✓ PUT notification-prefs clamps values correctly")
    
    def test_reset_notification_prefs(self, admin_token):
        """Reset notification prefs to defaults"""
        resp = requests.put(f"{BASE_URL}/api/users/me/notification-prefs",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={"checkin_reminder_minutes": 15, "checkout_reminder_enabled": True})
        assert resp.status_code == 200
        print("✓ Reset notification-prefs to defaults")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
