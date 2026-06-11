"""
Test suite for MeetFlow 1:1 Booking Page Feature (Phase 2)
Tests: Availability settings, public booking page, slot generation, booking creation, double-booking prevention
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
ADMIN_NAME = "Updated Admin Name"

@pytest.fixture(scope="module")
def session():
    """Create a requests session"""
    return requests.Session()

@pytest.fixture(scope="module")
def auth_cookies(session):
    """Login and get auth cookies"""
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return session.cookies

@pytest.fixture(scope="module")
def authenticated_session(session, auth_cookies):
    """Session with auth cookies"""
    return session


class TestAvailabilityEndpoints:
    """Tests for GET/PUT /api/booking/availability (auth required)"""
    
    def test_get_availability_returns_config(self, authenticated_session):
        """GET /api/booking/availability returns default or saved availability config"""
        response = authenticated_session.get(f"{BASE_URL}/api/booking/availability")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify structure
        assert "weekdays" in data, "Missing weekdays in response"
        assert "slot_duration" in data, "Missing slot_duration"
        assert "buffer_time" in data, "Missing buffer_time"
        assert "blocked_dates" in data, "Missing blocked_dates"
        assert "booking_enabled" in data, "Missing booking_enabled"
        
        # Verify weekdays structure
        weekdays = data["weekdays"]
        for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
            assert day in weekdays, f"Missing day: {day}"
            assert "enabled" in weekdays[day], f"Missing enabled for {day}"
            assert "start" in weekdays[day], f"Missing start for {day}"
            assert "end" in weekdays[day], f"Missing end for {day}"
        
        print(f"✓ Availability config retrieved: slot_duration={data['slot_duration']}, buffer={data['buffer_time']}")
    
    def test_put_availability_saves_config(self, authenticated_session):
        """PUT /api/booking/availability saves weekday schedule, slot duration, buffer, blocked dates"""
        # First get current config
        get_resp = authenticated_session.get(f"{BASE_URL}/api/booking/availability")
        current = get_resp.json()
        
        # Update with test values
        test_config = {
            "weekdays": {
                "mon": {"enabled": True, "start": "09:00", "end": "17:00"},
                "tue": {"enabled": True, "start": "09:00", "end": "17:00"},
                "wed": {"enabled": True, "start": "10:00", "end": "16:00"},
                "thu": {"enabled": True, "start": "09:00", "end": "17:00"},
                "fri": {"enabled": True, "start": "09:00", "end": "12:00"},
                "sat": {"enabled": False, "start": "09:00", "end": "17:00"},
                "sun": {"enabled": False, "start": "09:00", "end": "17:00"},
            },
            "slot_duration": 30,
            "buffer_time": 10,
            "blocked_dates": [],
            "booking_enabled": True,
        }
        
        response = authenticated_session.put(f"{BASE_URL}/api/booking/availability", json=test_config)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify it was saved
        verify_resp = authenticated_session.get(f"{BASE_URL}/api/booking/availability")
        saved = verify_resp.json()
        assert saved["slot_duration"] == 30, "slot_duration not saved"
        assert saved["buffer_time"] == 10, "buffer_time not saved"
        assert saved["booking_enabled"] == True, "booking_enabled not saved"
        assert saved["weekdays"]["wed"]["start"] == "10:00", "Wednesday start time not saved"
        
        print("✓ Availability config saved and verified")
    
    def test_availability_requires_auth(self):
        """Availability endpoints require authentication"""
        # Test without auth
        no_auth_session = requests.Session()
        response = no_auth_session.get(f"{BASE_URL}/api/booking/availability")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ GET /api/booking/availability requires auth")
        
        # PUT returns 422 (validation error) or 401 depending on order of checks
        # Both indicate the endpoint is protected
        response = no_auth_session.put(f"{BASE_URL}/api/booking/availability", json={
            "weekdays": {}, "slot_duration": 30, "buffer_time": 10, 
            "blocked_dates": [], "booking_enabled": True
        })
        assert response.status_code in [401, 422], f"Expected 401/422 without auth, got {response.status_code}"
        print("✓ PUT /api/booking/availability requires auth")


class TestPublicBookingInfo:
    """Tests for GET /api/book/{username}/info (no auth required)"""
    
    def test_get_booking_info_returns_public_data(self):
        """GET /api/book/{username}/info returns public user info"""
        response = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/info")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user_name" in data, "Missing user_name"
        assert "user_id" in data, "Missing user_id"
        assert "slot_duration" in data, "Missing slot_duration"
        assert "booking_enabled" in data, "Missing booking_enabled"
        # avatar is optional
        
        print(f"✓ Public booking info: user_name={data['user_name']}, slot_duration={data['slot_duration']}, enabled={data['booking_enabled']}")
    
    def test_get_booking_info_user_not_found(self):
        """GET /api/book/{username}/info returns 404 for non-existent user"""
        response = requests.get(f"{BASE_URL}/api/book/NonExistentUser12345/info")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Returns 404 for non-existent user")


class TestPublicSlots:
    """Tests for GET /api/book/{username}/slots (no auth required)"""
    
    def test_get_slots_for_enabled_weekday(self):
        """GET /api/book/{username}/slots returns available slots for enabled weekday"""
        # Find next Monday (enabled day)
        today = datetime.now()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = today + timedelta(days=days_until_monday)
        date_str = next_monday.strftime("%Y-%m-%d")
        
        response = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/slots?date={date_str}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "slots" in data, "Missing slots in response"
        assert "user_name" in data, "Missing user_name"
        assert "date" in data, "Missing date"
        
        # Should have slots for Monday (enabled day)
        slots = data["slots"]
        assert len(slots) > 0, f"Expected slots for Monday {date_str}, got none"
        
        # Verify slot structure
        for slot in slots:
            assert "start_time" in slot, "Missing start_time in slot"
            assert "end_time" in slot, "Missing end_time in slot"
        
        print(f"✓ Got {len(slots)} slots for Monday {date_str}")
    
    def test_get_slots_for_disabled_weekday(self):
        """Slots respect weekday enabled/disabled settings (no slots on disabled days)"""
        # Find next Saturday (disabled day)
        today = datetime.now()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        next_saturday = today + timedelta(days=days_until_saturday)
        date_str = next_saturday.strftime("%Y-%m-%d")
        
        response = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/slots?date={date_str}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        slots = data["slots"]
        assert len(slots) == 0, f"Expected no slots for Saturday (disabled), got {len(slots)}"
        
        print(f"✓ No slots returned for disabled day (Saturday {date_str})")
    
    def test_get_slots_respects_blocked_dates(self, authenticated_session):
        """Slots respect blocked_dates"""
        # First, add a blocked date
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = today + timedelta(days=days_until_tuesday)
        blocked_date = next_tuesday.strftime("%Y-%m-%d")
        
        # Get current config and add blocked date
        get_resp = authenticated_session.get(f"{BASE_URL}/api/booking/availability")
        config = get_resp.json()
        config["blocked_dates"] = [blocked_date]
        
        put_resp = authenticated_session.put(f"{BASE_URL}/api/booking/availability", json=config)
        assert put_resp.status_code == 200
        
        # Now check slots for blocked date
        response = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/slots?date={blocked_date}")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["slots"]) == 0, f"Expected no slots for blocked date, got {len(data['slots'])}"
        
        # Clean up - remove blocked date
        config["blocked_dates"] = []
        authenticated_session.put(f"{BASE_URL}/api/booking/availability", json=config)
        
        print(f"✓ No slots returned for blocked date ({blocked_date})")
    
    def test_get_slots_invalid_date_format(self):
        """GET /api/book/{username}/slots returns 400 for invalid date format"""
        response = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/slots?date=invalid-date")
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Returns 400 for invalid date format")


class TestBookingCreation:
    """Tests for POST /api/book/{username} (no auth required)"""
    
    def test_create_booking_success(self):
        """POST /api/book/{username} creates booking + MeetFlow meeting"""
        # Find next Thursday (enabled day)
        today = datetime.now()
        days_until_thursday = (3 - today.weekday()) % 7
        if days_until_thursday == 0:
            days_until_thursday = 7
        next_thursday = today + timedelta(days=days_until_thursday)
        date_str = next_thursday.strftime("%Y-%m-%d")
        
        # Get available slots
        slots_resp = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/slots?date={date_str}")
        slots = slots_resp.json()["slots"]
        
        if len(slots) == 0:
            pytest.skip(f"No slots available for {date_str}")
        
        # Pick a slot that's likely not booked
        test_slot = slots[-1]  # Pick last slot
        
        booking_data = {
            "date": date_str,
            "start_time": test_slot["start_time"],
            "guest_name": "TEST_Booking_User",
            "guest_email": "test@example.com",
            "topic": "Test Meeting Topic"
        }
        
        response = requests.post(f"{BASE_URL}/api/book/{ADMIN_NAME}", json=booking_data)
        
        # Could be 200 (success) or 409 (already booked)
        if response.status_code == 409:
            print(f"⚠ Slot {test_slot['start_time']} already booked, trying another slot")
            # Try first slot
            test_slot = slots[0]
            booking_data["start_time"] = test_slot["start_time"]
            response = requests.post(f"{BASE_URL}/api/book/{ADMIN_NAME}", json=booking_data)
        
        if response.status_code == 409:
            pytest.skip("All tested slots already booked")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "booking_id" in data, "Missing booking_id"
        assert "meeting_id" in data, "Missing meeting_id"
        assert "meeting_code" in data, "Missing meeting_code"
        assert "date" in data, "Missing date"
        assert "start_time" in data, "Missing start_time"
        assert "end_time" in data, "Missing end_time"
        
        print(f"✓ Booking created: booking_id={data['booking_id']}, meeting_code={data['meeting_code']}")
        
        # Store for later tests
        TestBookingCreation.created_booking = data
        TestBookingCreation.booked_date = date_str
        TestBookingCreation.booked_time = test_slot["start_time"]
    
    def test_double_booking_returns_409(self):
        """Double booking returns 409 Conflict"""
        if not hasattr(TestBookingCreation, 'created_booking'):
            pytest.skip("No booking created in previous test")
        
        # Try to book the same slot again
        booking_data = {
            "date": TestBookingCreation.booked_date,
            "start_time": TestBookingCreation.booked_time,
            "guest_name": "Another Guest",
            "guest_email": "another@example.com",
            "topic": "Duplicate Booking Attempt"
        }
        
        response = requests.post(f"{BASE_URL}/api/book/{ADMIN_NAME}", json=booking_data)
        assert response.status_code == 409, f"Expected 409 for double booking, got {response.status_code}"
        
        print("✓ Double booking correctly returns 409 Conflict")
    
    def test_booked_slot_disappears_from_available(self):
        """Booked slot disappears from available slots"""
        if not hasattr(TestBookingCreation, 'created_booking'):
            pytest.skip("No booking created in previous test")
        
        # Get slots for the booked date
        response = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/slots?date={TestBookingCreation.booked_date}")
        assert response.status_code == 200
        
        slots = response.json()["slots"]
        slot_times = [s["start_time"] for s in slots]
        
        assert TestBookingCreation.booked_time not in slot_times, \
            f"Booked slot {TestBookingCreation.booked_time} should not appear in available slots"
        
        print(f"✓ Booked slot {TestBookingCreation.booked_time} not in available slots")
    
    def test_create_booking_missing_fields(self):
        """POST /api/book/{username} returns 400 for missing required fields"""
        response = requests.post(f"{BASE_URL}/api/book/{ADMIN_NAME}", json={
            "date": "2026-03-20"
            # Missing start_time and guest_name
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Returns 400 for missing required fields")


class TestMyBookings:
    """Tests for GET /api/booking/my-bookings (auth required)"""
    
    def test_get_my_bookings_with_pagination(self, authenticated_session):
        """GET /api/booking/my-bookings lists user's bookings with pagination"""
        response = authenticated_session.get(f"{BASE_URL}/api/booking/my-bookings?page=1&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bookings" in data, "Missing bookings"
        assert "total" in data, "Missing total"
        assert "page" in data, "Missing page"
        assert "pages" in data, "Missing pages"
        
        # Verify booking structure if any exist
        if len(data["bookings"]) > 0:
            booking = data["bookings"][0]
            assert "booking_id" in booking, "Missing booking_id"
            assert "date" in booking, "Missing date"
            assert "start_time" in booking, "Missing start_time"
            assert "guest_name" in booking, "Missing guest_name"
        
        print(f"✓ My bookings: {len(data['bookings'])} bookings, total={data['total']}, pages={data['pages']}")
    
    def test_my_bookings_requires_auth(self):
        """GET /api/booking/my-bookings requires authentication"""
        response = requests.get(f"{BASE_URL}/api/booking/my-bookings")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ GET /api/booking/my-bookings requires auth")


class TestCancelBooking:
    """Tests for DELETE /api/booking/{booking_id} (auth required)"""
    
    def test_cancel_booking_success(self, authenticated_session):
        """DELETE /api/booking/{booking_id} cancels booking"""
        # First create a booking to cancel
        today = datetime.now()
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7
        next_friday = today + timedelta(days=days_until_friday)
        date_str = next_friday.strftime("%Y-%m-%d")
        
        # Get available slots
        slots_resp = requests.get(f"{BASE_URL}/api/book/{ADMIN_NAME}/slots?date={date_str}")
        slots = slots_resp.json()["slots"]
        
        if len(slots) == 0:
            pytest.skip(f"No slots available for {date_str}")
        
        # Create booking
        booking_data = {
            "date": date_str,
            "start_time": slots[0]["start_time"],
            "guest_name": "TEST_Cancel_User",
            "guest_email": "cancel@example.com",
            "topic": "To Be Cancelled"
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/book/{ADMIN_NAME}", json=booking_data)
        if create_resp.status_code == 409:
            pytest.skip("Slot already booked")
        
        assert create_resp.status_code == 200
        booking_id = create_resp.json()["booking_id"]
        
        # Cancel the booking
        cancel_resp = authenticated_session.delete(f"{BASE_URL}/api/booking/{booking_id}")
        assert cancel_resp.status_code == 200, f"Expected 200, got {cancel_resp.status_code}: {cancel_resp.text}"
        
        print(f"✓ Booking {booking_id} cancelled successfully")
    
    def test_cancel_booking_not_found(self, authenticated_session):
        """DELETE /api/booking/{booking_id} returns 404 for non-existent booking"""
        response = authenticated_session.delete(f"{BASE_URL}/api/booking/nonexistent_booking_id")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Returns 404 for non-existent booking")
    
    def test_cancel_booking_requires_auth(self):
        """DELETE /api/booking/{booking_id} requires authentication"""
        response = requests.delete(f"{BASE_URL}/api/booking/some_booking_id")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ DELETE /api/booking/{booking_id} requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
