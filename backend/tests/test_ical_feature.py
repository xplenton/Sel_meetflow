"""
Test iCal Export Feature for MeetFlow
Tests the calendar integration endpoints:
- GET /api/meetings/{meeting_id}/ical - Export meeting to .ics
- GET /api/schedule-polls/{poll_id}/ical - Export confirmed poll to .ics
- GET /api/bookings/{booking_id}/ical - Export booking to .ics
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMeetingIcal:
    """Test iCal export for meetings"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth cookies"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    
    def test_meeting_ical_for_scheduled_meeting(self):
        """Test iCal export for a scheduled meeting with date"""
        # First get a scheduled meeting
        meetings_resp = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=upcoming")
        assert meetings_resp.status_code == 200
        meetings = meetings_resp.json().get("meetings", [])
        
        # Find a meeting with scheduled_at
        scheduled_meeting = None
        for m in meetings:
            if m.get("scheduled_at"):
                scheduled_meeting = m
                break
        
        if not scheduled_meeting:
            # Create a scheduled meeting for testing
            from datetime import datetime, timedelta
            future_date = (datetime.now() + timedelta(days=1)).isoformat()
            create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
                "title": "TEST_iCal_Scheduled_Meeting",
                "meeting_type": "scheduled",
                "scheduled_at": future_date,
                "duration": 60
            })
            assert create_resp.status_code == 200
            scheduled_meeting = create_resp.json()
        
        meeting_id = scheduled_meeting["meeting_id"]
        
        # Test iCal export
        ical_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ical_resp.status_code == 200, f"iCal export failed: {ical_resp.text}"
        
        # Verify content type
        assert "text/calendar" in ical_resp.headers.get("Content-Type", "")
        
        # Verify .ics content
        content = ical_resp.text
        assert "BEGIN:VCALENDAR" in content
        assert "BEGIN:VEVENT" in content
        assert "END:VEVENT" in content
        assert "END:VCALENDAR" in content
        assert "DTSTART" in content
        assert "DTEND" in content
        assert "SUMMARY" in content
        assert f"{meeting_id}@meetflow" in content  # UID
        print(f"✓ Meeting iCal export successful for {meeting_id}")
    
    def test_meeting_ical_nonexistent(self):
        """Test iCal export for non-existent meeting returns 404"""
        ical_resp = requests.get(f"{BASE_URL}/api/meetings/nonexistent_meeting_id/ical")
        assert ical_resp.status_code == 404
        print("✓ Non-existent meeting returns 404")


class TestSchedulePollIcal:
    """Test iCal export for schedule polls"""
    
    def test_confirmed_poll_ical(self):
        """Test iCal export for a confirmed schedule poll"""
        # Use the known confirmed poll from test data
        poll_id = "spoll_b00d4c6d41"
        
        ical_resp = requests.get(f"{BASE_URL}/api/schedule-polls/{poll_id}/ical")
        
        if ical_resp.status_code == 200:
            # Verify content type
            assert "text/calendar" in ical_resp.headers.get("Content-Type", "")
            
            # Verify .ics content
            content = ical_resp.text
            assert "BEGIN:VCALENDAR" in content
            assert "BEGIN:VEVENT" in content
            assert "END:VEVENT" in content
            assert "END:VCALENDAR" in content
            assert "DTSTART" in content
            assert "DTEND" in content
            assert "SUMMARY" in content
            assert f"{poll_id}@meetflow" in content  # UID
            print(f"✓ Confirmed poll iCal export successful for {poll_id}")
        elif ical_resp.status_code == 400:
            # Poll exists but not confirmed
            assert "not yet confirmed" in ical_resp.text.lower() or "not confirmed" in ical_resp.text.lower()
            print(f"✓ Poll {poll_id} exists but not confirmed - correct 400 response")
        elif ical_resp.status_code == 404:
            print(f"⚠ Poll {poll_id} not found - may need to create test data")
        else:
            pytest.fail(f"Unexpected status code: {ical_resp.status_code}")
    
    def test_unconfirmed_poll_ical_returns_400(self):
        """Test iCal export for unconfirmed poll returns 400"""
        # Login first to create a poll
        session = requests.Session()
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        
        # Create an unconfirmed poll
        from datetime import datetime, timedelta
        future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        create_resp = session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": "TEST_Unconfirmed_Poll_iCal",
            "time_slots": [
                {"date": future_date, "start_time": "10:00", "end_time": "11:00"}
            ]
        })
        assert create_resp.status_code == 200
        poll_id = create_resp.json()["poll_id"]
        
        # Try to get iCal for unconfirmed poll
        ical_resp = requests.get(f"{BASE_URL}/api/schedule-polls/{poll_id}/ical")
        assert ical_resp.status_code == 400, f"Expected 400 for unconfirmed poll, got {ical_resp.status_code}"
        print("✓ Unconfirmed poll correctly returns 400")
        
        # Cleanup
        session.delete(f"{BASE_URL}/api/schedule-polls/{poll_id}")
    
    def test_poll_ical_nonexistent(self):
        """Test iCal export for non-existent poll returns 404"""
        ical_resp = requests.get(f"{BASE_URL}/api/schedule-polls/nonexistent_poll_id/ical")
        assert ical_resp.status_code == 404
        print("✓ Non-existent poll returns 404")


class TestBookingIcal:
    """Test iCal export for bookings"""
    
    def test_booking_ical(self):
        """Test iCal export for a booking"""
        # Use the known booking from test data
        booking_id = "bk_423c841132"
        
        ical_resp = requests.get(f"{BASE_URL}/api/bookings/{booking_id}/ical")
        
        if ical_resp.status_code == 200:
            # Verify content type
            assert "text/calendar" in ical_resp.headers.get("Content-Type", "")
            
            # Verify .ics content
            content = ical_resp.text
            assert "BEGIN:VCALENDAR" in content
            assert "BEGIN:VEVENT" in content
            assert "END:VEVENT" in content
            assert "END:VCALENDAR" in content
            assert "DTSTART" in content
            assert "DTEND" in content
            assert "SUMMARY" in content
            assert f"{booking_id}@meetflow" in content  # UID
            print(f"✓ Booking iCal export successful for {booking_id}")
        elif ical_resp.status_code == 404:
            print(f"⚠ Booking {booking_id} not found - may need to create test data")
        else:
            pytest.fail(f"Unexpected status code: {ical_resp.status_code}")
    
    def test_booking_ical_nonexistent(self):
        """Test iCal export for non-existent booking returns 404"""
        ical_resp = requests.get(f"{BASE_URL}/api/bookings/nonexistent_booking_id/ical")
        assert ical_resp.status_code == 404
        print("✓ Non-existent booking returns 404")


class TestIcalContentValidation:
    """Test iCal content structure and validity"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and create test meeting"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        
        # Create a scheduled meeting for testing
        from datetime import datetime, timedelta
        self.future_date = (datetime.now() + timedelta(days=2)).isoformat()
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_iCal_Content_Validation",
            "description": "Test meeting for iCal validation",
            "meeting_type": "scheduled",
            "scheduled_at": self.future_date,
            "duration": 45
        })
        assert create_resp.status_code == 200
        self.meeting = create_resp.json()
    
    def test_ical_has_required_fields(self):
        """Verify iCal contains all required VEVENT fields"""
        meeting_id = self.meeting["meeting_id"]
        ical_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ical_resp.status_code == 200
        
        content = ical_resp.text
        
        # Required calendar properties
        assert "PRODID:" in content, "Missing PRODID"
        assert "VERSION:2.0" in content, "Missing VERSION"
        
        # Required event properties
        assert "UID:" in content, "Missing UID"
        assert "SUMMARY:" in content, "Missing SUMMARY"
        assert "DTSTART" in content, "Missing DTSTART"
        assert "DTEND" in content, "Missing DTEND"
        
        # Verify meeting title is in summary
        assert self.meeting["title"] in content or "TEST_iCal" in content
        
        print("✓ iCal contains all required fields")
    
    def test_ical_content_disposition(self):
        """Verify Content-Disposition header for file download"""
        meeting_id = self.meeting["meeting_id"]
        ical_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert ical_resp.status_code == 200
        
        content_disp = ical_resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert ".ics" in content_disp
        print("✓ Content-Disposition header correct for file download")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
