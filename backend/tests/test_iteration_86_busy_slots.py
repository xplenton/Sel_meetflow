"""
Iteration 86 - Busy Slots Feature Tests
Tests for:
- POST /api/users/me/busy-slots (create busy slot with validation)
- GET /api/users/me/busy-slots (list user's busy slots)
- DELETE /api/users/me/busy-slots/{slot_id} (delete busy slot)
- Idempotency via source_id (upsert behavior)
- GET /api/book/{username}/slots excludes busy times
- 401 on all busy-slots endpoints without auth
- Smoke regression for existing endpoints
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBusySlotsAuth:
    """Test 401 responses without authentication"""
    
    def test_get_busy_slots_no_auth(self):
        """GET /users/me/busy-slots without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/users/me/busy-slots")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: GET /users/me/busy-slots returns 401 without auth")
    
    def test_post_busy_slots_no_auth(self):
        """POST /users/me/busy-slots without auth returns 401"""
        response = requests.post(f"{BASE_URL}/api/users/me/busy-slots", json={
            "start": "2026-02-01T14:00:00+00:00",
            "end": "2026-02-01T15:00:00+00:00"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: POST /users/me/busy-slots returns 401 without auth")
    
    def test_delete_busy_slots_no_auth(self):
        """DELETE /users/me/busy-slots/{slot_id} without auth returns 401"""
        response = requests.delete(f"{BASE_URL}/api/users/me/busy-slots/busy_test123")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: DELETE /users/me/busy-slots/{slot_id} returns 401 without auth")


class TestBusySlotsAuthenticated:
    """Test busy slots CRUD with authentication"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user_data = login_resp.json()
        self.user_name = self.user_data.get("name", "Admin")
        # Derive username slug for booking endpoint
        self.username_slug = self.user_name.lower().replace(" ", "-")
        print(f"Logged in as: {self.user_name}, slug: {self.username_slug}")
        yield
        # Cleanup: delete any test busy slots
        try:
            slots_resp = self.session.get(f"{BASE_URL}/api/users/me/busy-slots")
            if slots_resp.status_code == 200:
                for slot in slots_resp.json().get("slots", []):
                    if slot.get("title", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/users/me/busy-slots/{slot['slot_id']}")
        except:
            pass
    
    def test_create_busy_slot_success(self):
        """POST /users/me/busy-slots creates a busy slot"""
        # Use a future date
        future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        payload = {
            "start": f"{future_date}T14:00:00+00:00",
            "end": f"{future_date}T15:00:00+00:00",
            "title": "TEST_busy_slot_1",
            "source": "manual"
        }
        response = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "slot_id" in data, "Response should contain slot_id"
        assert data["title"] == "TEST_busy_slot_1"
        assert data["source"] == "manual"
        print(f"PASSED: Created busy slot with slot_id={data['slot_id']}")
        return data["slot_id"]
    
    def test_create_busy_slot_validation_missing_start(self):
        """POST /users/me/busy-slots returns 400 when start is missing"""
        payload = {
            "end": "2026-02-01T15:00:00+00:00",
            "title": "TEST_invalid"
        }
        response = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASSED: POST returns 400 when start is missing")
    
    def test_create_busy_slot_validation_end_before_start(self):
        """POST /users/me/busy-slots returns 400 when end <= start"""
        payload = {
            "start": "2026-02-01T15:00:00+00:00",
            "end": "2026-02-01T14:00:00+00:00",
            "title": "TEST_invalid"
        }
        response = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASSED: POST returns 400 when end <= start")
    
    def test_create_busy_slot_validation_invalid_date(self):
        """POST /users/me/busy-slots returns 400 for invalid date format"""
        payload = {
            "start": "not-a-date",
            "end": "also-not-a-date",
            "title": "TEST_invalid"
        }
        response = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASSED: POST returns 400 for invalid date format")
    
    def test_list_busy_slots(self):
        """GET /users/me/busy-slots lists user's busy slots"""
        # First create a slot
        future_date = (datetime.now() + timedelta(days=8)).strftime("%Y-%m-%d")
        create_resp = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json={
            "start": f"{future_date}T10:00:00+00:00",
            "end": f"{future_date}T11:00:00+00:00",
            "title": "TEST_list_slot"
        })
        assert create_resp.status_code == 200
        
        # Now list
        response = self.session.get(f"{BASE_URL}/api/users/me/busy-slots")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "slots" in data, "Response should contain 'slots' array"
        assert "count" in data, "Response should contain 'count'"
        assert isinstance(data["slots"], list)
        # Find our test slot
        test_slots = [s for s in data["slots"] if s.get("title") == "TEST_list_slot"]
        assert len(test_slots) >= 1, "Should find the created test slot"
        print(f"PASSED: Listed {data['count']} busy slots, found test slot")
    
    def test_idempotent_upsert_with_source_id(self):
        """POST with same source_id updates existing slot (idempotent)"""
        future_date = (datetime.now() + timedelta(days=9)).strftime("%Y-%m-%d")
        source_id = "TEST_caldav_event_hash_123"
        
        # First create
        payload1 = {
            "start": f"{future_date}T09:00:00+00:00",
            "end": f"{future_date}T10:00:00+00:00",
            "title": "TEST_idempotent_v1",
            "source": "caldav",
            "source_id": source_id
        }
        resp1 = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json=payload1)
        assert resp1.status_code == 200
        slot_id_1 = resp1.json()["slot_id"]
        
        # Second create with same source_id - should update, not create new
        payload2 = {
            "start": f"{future_date}T09:30:00+00:00",
            "end": f"{future_date}T10:30:00+00:00",
            "title": "TEST_idempotent_v2",
            "source": "caldav",
            "source_id": source_id
        }
        resp2 = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json=payload2)
        assert resp2.status_code == 200
        slot_id_2 = resp2.json()["slot_id"]
        
        # Should be same slot_id (upsert)
        assert slot_id_1 == slot_id_2, f"Expected same slot_id for upsert, got {slot_id_1} vs {slot_id_2}"
        
        # Verify only one slot with this source_id
        list_resp = self.session.get(f"{BASE_URL}/api/users/me/busy-slots")
        slots = list_resp.json().get("slots", [])
        matching = [s for s in slots if s.get("source_id") == source_id]
        assert len(matching) == 1, f"Expected 1 slot with source_id, found {len(matching)}"
        assert matching[0]["title"] == "TEST_idempotent_v2", "Title should be updated"
        print(f"PASSED: Idempotent upsert works, slot_id={slot_id_1}")
    
    def test_delete_busy_slot(self):
        """DELETE /users/me/busy-slots/{slot_id} removes the slot"""
        future_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        # Create
        create_resp = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json={
            "start": f"{future_date}T16:00:00+00:00",
            "end": f"{future_date}T17:00:00+00:00",
            "title": "TEST_delete_me"
        })
        assert create_resp.status_code == 200
        slot_id = create_resp.json()["slot_id"]
        
        # Delete
        del_resp = self.session.delete(f"{BASE_URL}/api/users/me/busy-slots/{slot_id}")
        assert del_resp.status_code == 200, f"Expected 200, got {del_resp.status_code}"
        assert del_resp.json().get("deleted") == True
        
        # Verify gone
        list_resp = self.session.get(f"{BASE_URL}/api/users/me/busy-slots")
        slots = list_resp.json().get("slots", [])
        matching = [s for s in slots if s.get("slot_id") == slot_id]
        assert len(matching) == 0, "Deleted slot should not appear in list"
        print(f"PASSED: Deleted busy slot {slot_id}")
    
    def test_delete_nonexistent_slot_returns_404(self):
        """DELETE /users/me/busy-slots/{slot_id} returns 404 for unknown ID"""
        response = self.session.delete(f"{BASE_URL}/api/users/me/busy-slots/busy_nonexistent_xyz")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: DELETE returns 404 for nonexistent slot")


class TestPublicBookingSlotsExclusion:
    """Test that busy slots are excluded from public booking slots"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup booking availability"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user_data = login_resp.json()
        self.user_name = self.user_data.get("name", "Admin")
        self.username_slug = self.user_name.lower().replace(" ", "-")
        
        # Ensure booking is enabled with predictable settings
        avail_resp = self.session.put(f"{BASE_URL}/api/booking/availability", json={
            "weekdays": {
                "mon": {"enabled": True, "start": "09:00", "end": "17:00"},
                "tue": {"enabled": True, "start": "09:00", "end": "17:00"},
                "wed": {"enabled": True, "start": "09:00", "end": "17:00"},
                "thu": {"enabled": True, "start": "09:00", "end": "17:00"},
                "fri": {"enabled": True, "start": "09:00", "end": "17:00"},
                "sat": {"enabled": False, "start": "09:00", "end": "17:00"},
                "sun": {"enabled": False, "start": "09:00", "end": "17:00"},
            },
            "slot_duration": 30,
            "buffer_time": 0,  # No buffer for deterministic slots
            "blocked_dates": [],
            "booking_enabled": True
        })
        assert avail_resp.status_code == 200, f"Failed to set availability: {avail_resp.text}"
        print(f"Setup complete: username_slug={self.username_slug}, slot_duration=30, buffer=0")
        yield
        # Cleanup test busy slots
        try:
            slots_resp = self.session.get(f"{BASE_URL}/api/users/me/busy-slots")
            if slots_resp.status_code == 200:
                for slot in slots_resp.json().get("slots", []):
                    if slot.get("title", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/users/me/busy-slots/{slot['slot_id']}")
        except:
            pass
    
    def _find_next_weekday(self, days_ahead=7):
        """Find a future weekday (Mon-Fri) for testing"""
        target = datetime.now() + timedelta(days=days_ahead)
        while target.weekday() >= 5:  # Skip Sat/Sun
            target += timedelta(days=1)
        return target.strftime("%Y-%m-%d")
    
    def test_busy_slot_excludes_overlapping_booking_slots(self):
        """Busy slot 14:00-15:00 should exclude 14:00 and 14:30 from public slots"""
        test_date = self._find_next_weekday(14)
        
        # First get slots without busy block
        slots_before = requests.get(f"{BASE_URL}/api/book/{self.username_slug}/slots", params={"date": test_date})
        assert slots_before.status_code == 200, f"Failed to get slots: {slots_before.text}"
        slots_before_data = slots_before.json().get("slots", [])
        times_before = [s["start_time"] for s in slots_before_data]
        print(f"Slots before busy block on {test_date}: {times_before}")
        
        # Verify 14:00 and 14:30 are available
        assert "14:00" in times_before, "14:00 should be available before busy block"
        assert "14:30" in times_before, "14:30 should be available before busy block"
        
        # Create busy slot 14:00-15:00
        busy_resp = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json={
            "start": f"{test_date}T14:00:00+00:00",
            "end": f"{test_date}T15:00:00+00:00",
            "title": "TEST_booking_exclusion"
        })
        assert busy_resp.status_code == 200, f"Failed to create busy slot: {busy_resp.text}"
        slot_id = busy_resp.json()["slot_id"]
        
        # Get slots after busy block
        slots_after = requests.get(f"{BASE_URL}/api/book/{self.username_slug}/slots", params={"date": test_date})
        assert slots_after.status_code == 200
        slots_after_data = slots_after.json().get("slots", [])
        times_after = [s["start_time"] for s in slots_after_data]
        print(f"Slots after busy block: {times_after}")
        
        # Verify 14:00 and 14:30 are now excluded
        assert "14:00" not in times_after, "14:00 should be excluded after busy block"
        assert "14:30" not in times_after, "14:30 should be excluded after busy block"
        
        # Other slots should still be available
        assert "13:30" in times_after or "13:00" in times_after, "Slots before busy time should still be available"
        assert "15:00" in times_after, "15:00 should be available (after busy block ends)"
        
        print(f"PASSED: Busy slot {slot_id} correctly excludes 14:00 and 14:30 from booking slots")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/users/me/busy-slots/{slot_id}")
    
    def test_slots_available_after_busy_slot_deleted(self):
        """After deleting busy slot, times should be available again"""
        test_date = self._find_next_weekday(15)
        
        # Create busy slot
        busy_resp = self.session.post(f"{BASE_URL}/api/users/me/busy-slots", json={
            "start": f"{test_date}T10:00:00+00:00",
            "end": f"{test_date}T11:00:00+00:00",
            "title": "TEST_delete_restore"
        })
        assert busy_resp.status_code == 200
        slot_id = busy_resp.json()["slot_id"]
        
        # Verify excluded
        slots_blocked = requests.get(f"{BASE_URL}/api/book/{self.username_slug}/slots", params={"date": test_date})
        times_blocked = [s["start_time"] for s in slots_blocked.json().get("slots", [])]
        assert "10:00" not in times_blocked, "10:00 should be excluded while busy"
        assert "10:30" not in times_blocked, "10:30 should be excluded while busy"
        
        # Delete busy slot
        del_resp = self.session.delete(f"{BASE_URL}/api/users/me/busy-slots/{slot_id}")
        assert del_resp.status_code == 200
        
        # Verify restored
        slots_restored = requests.get(f"{BASE_URL}/api/book/{self.username_slug}/slots", params={"date": test_date})
        times_restored = [s["start_time"] for s in slots_restored.json().get("slots", [])]
        assert "10:00" in times_restored, "10:00 should be available after busy slot deleted"
        assert "10:30" in times_restored, "10:30 should be available after busy slot deleted"
        
        print("PASSED: Slots restored after busy slot deletion")


class TestSmokeRegression:
    """Quick smoke tests for existing endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        yield
    
    def test_auth_me(self):
        """GET /auth/me returns user info"""
        resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        assert "email" in resp.json()
        print("PASSED: GET /auth/me works")
    
    def test_meetings_list(self):
        """GET /meetings returns list"""
        resp = self.session.get(f"{BASE_URL}/api/meetings")
        assert resp.status_code == 200
        assert "meetings" in resp.json()
        print("PASSED: GET /meetings works")
    
    def test_schedule_polls_list(self):
        """GET /schedule-polls returns list"""
        resp = self.session.get(f"{BASE_URL}/api/schedule-polls")
        assert resp.status_code == 200
        assert "polls" in resp.json()
        print("PASSED: GET /schedule-polls works")
    
    def test_news_feed(self):
        """GET /news/feed returns list"""
        resp = self.session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200
        print("PASSED: GET /news/feed works")
    
    def test_surveys_list(self):
        """GET /surveys returns list"""
        resp = self.session.get(f"{BASE_URL}/api/surveys")
        assert resp.status_code == 200
        print("PASSED: GET /surveys works")
    
    def test_booking_availability(self):
        """GET /booking/availability returns config"""
        resp = self.session.get(f"{BASE_URL}/api/booking/availability")
        assert resp.status_code == 200
        assert "weekdays" in resp.json()
        print("PASSED: GET /booking/availability works")
    
    def test_caldav_config(self):
        """GET /users/me/caldav-config returns config"""
        resp = self.session.get(f"{BASE_URL}/api/users/me/caldav-config")
        assert resp.status_code == 200
        print("PASSED: GET /users/me/caldav-config works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
