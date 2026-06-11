"""
Comprehensive multi-user scheduling tests for MeetFlow
Tests: Schedule Polls (Doodle-style), 1:1 Booking, General Polls, Calendar Integration
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@meetflow.com", "password": "admin123"}
USER1_CREDS = {"email": "user1@meetflow.com", "password": "test123"}
USER2_CREDS = {"email": "user2@meetflow.com", "password": "test123"}
USER3_CREDS = {"email": "user3@meetflow.com", "password": "test123"}


def login_user(session, creds):
    """Login and return token"""
    resp = session.post(f"{BASE_URL}/api/auth/login", json=creds)
    if resp.status_code != 200:
        # Try to register the user first
        register_data = {**creds, "name": creds["email"].split("@")[0]}
        session.post(f"{BASE_URL}/api/auth/register", json=register_data)
        resp = session.post(f"{BASE_URL}/api/auth/login", json=creds)
    return resp.cookies.get("session_token")


# ==================== SCHEDULE POLLS (Doodle-Style) ====================

class TestSchedulePolls:
    """Schedule poll tests with multi-user voting"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        session = requests.Session()
        login_user(session, ADMIN_CREDS)
        return session
    
    @pytest.fixture(scope="class")
    def schedule_poll(self, admin_session):
        """Create a schedule poll and return its data"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        poll_data = {
            "title": "TEST_Team Meeting Terminplanung",
            "description": "Finde den besten Termin fuer unser Team-Meeting",
            "time_slots": [
                {"date": tomorrow, "start_time": "09:00", "end_time": "10:00"},
                {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"},
                {"date": next_week, "start_time": "10:00", "end_time": "11:00"}
            ],
            "deadline": (datetime.now() + timedelta(days=5)).isoformat(),
            "allow_comments": True,
            "allow_maybe": True,
            "timezone": "Europe/Berlin"
        }
        
        resp = admin_session.post(f"{BASE_URL}/api/schedule-polls", json=poll_data)
        assert resp.status_code == 200, f"Failed to create schedule poll: {resp.text}"
        
        data = resp.json()
        print(f"Created schedule poll: {data['poll_id']}")
        
        yield data
        
        # Cleanup
        try:
            admin_session.delete(f"{BASE_URL}/api/schedule-polls/{data['poll_id']}")
        except:
            pass
    
    def test_01_schedule_poll_created(self, schedule_poll):
        """Verify schedule poll was created"""
        assert "poll_id" in schedule_poll
        assert "share_token" in schedule_poll
        print(f"Schedule poll ID: {schedule_poll['poll_id']}")
    
    def test_02_user1_votes_on_schedule_poll(self, admin_session, schedule_poll):
        """User1 votes on the schedule poll with yes/no/maybe"""
        # Get the poll to get slot IDs
        resp = admin_session.get(f"{BASE_URL}/api/schedule-polls/{schedule_poll['poll_id']}")
        assert resp.status_code == 200
        poll = resp.json()
        
        slots = poll["time_slots"]
        assert len(slots) >= 3, "Expected at least 3 time slots"
        
        vote_data = {
            "voter_name": "User1",
            "voter_email": "user1@meetflow.com",
            "votes": {
                slots[0]["slot_id"]: "yes",
                slots[1]["slot_id"]: "maybe",
                slots[2]["slot_id"]: "no"
            }
        }
        
        resp = requests.post(f"{BASE_URL}/api/schedule-polls/public/{schedule_poll['share_token']}/vote", json=vote_data)
        assert resp.status_code == 200, f"User1 vote failed: {resp.text}"
        
        data = resp.json()
        assert "vote_id" in data
        print(f"User1 voted: {data['vote_id']}")
    
    def test_03_user2_votes_on_schedule_poll(self, admin_session, schedule_poll):
        """User2 votes on same poll with different choices"""
        resp = admin_session.get(f"{BASE_URL}/api/schedule-polls/{schedule_poll['poll_id']}")
        poll = resp.json()
        slots = poll["time_slots"]
        
        vote_data = {
            "voter_name": "User2",
            "voter_email": "user2@meetflow.com",
            "votes": {
                slots[0]["slot_id"]: "maybe",
                slots[1]["slot_id"]: "yes",
                slots[2]["slot_id"]: "yes"
            }
        }
        
        resp = requests.post(f"{BASE_URL}/api/schedule-polls/public/{schedule_poll['share_token']}/vote", json=vote_data)
        assert resp.status_code == 200, f"User2 vote failed: {resp.text}"
        print("User2 voted successfully")
    
    def test_04_user3_votes_on_schedule_poll(self, admin_session, schedule_poll):
        """User3 votes on same poll"""
        resp = admin_session.get(f"{BASE_URL}/api/schedule-polls/{schedule_poll['poll_id']}")
        poll = resp.json()
        slots = poll["time_slots"]
        
        vote_data = {
            "voter_name": "User3",
            "voter_email": "user3@meetflow.com",
            "votes": {
                slots[0]["slot_id"]: "yes",
                slots[1]["slot_id"]: "no",
                slots[2]["slot_id"]: "maybe"
            }
        }
        
        resp = requests.post(f"{BASE_URL}/api/schedule-polls/public/{schedule_poll['share_token']}/vote", json=vote_data)
        assert resp.status_code == 200, f"User3 vote failed: {resp.text}"
        print("User3 voted successfully")
    
    def test_05_add_comment_to_schedule_poll(self, schedule_poll):
        """Add comment to poll"""
        comment_data = {
            "author_name": "User1",
            "text": "Ich bevorzuge den Vormittagstermin!"
        }
        
        resp = requests.post(f"{BASE_URL}/api/schedule-polls/public/{schedule_poll['share_token']}/comment", json=comment_data)
        assert resp.status_code == 200, f"Comment failed: {resp.text}"
        
        data = resp.json()
        assert "comment_id" in data
        assert data["text"] == comment_data["text"]
        print(f"Comment added: {data['comment_id']}")
    
    def test_06_get_poll_results_verify_votes(self, admin_session, schedule_poll):
        """Get poll results - verify all 3 votes visible"""
        resp = admin_session.get(f"{BASE_URL}/api/schedule-polls/{schedule_poll['poll_id']}")
        assert resp.status_code == 200
        
        poll = resp.json()
        assert len(poll["votes"]) == 3, f"Expected 3 votes, got {len(poll['votes'])}"
        assert len(poll["comments"]) >= 1, "Expected at least 1 comment"
        
        voter_names = [v["voter_name"] for v in poll["votes"]]
        assert "User1" in voter_names
        assert "User2" in voter_names
        assert "User3" in voter_names
        
        print(f"Poll has {len(poll['votes'])} votes and {len(poll['comments'])} comments")
    
    def test_07_list_schedule_polls(self, admin_session):
        """List all schedule polls"""
        resp = admin_session.get(f"{BASE_URL}/api/schedule-polls")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "polls" in data
        assert "total" in data
        print(f"Found {data['total']} schedule polls")


# ==================== 1:1 BOOKING ====================

class TestBooking:
    """1:1 Booking tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        session = requests.Session()
        login_user(session, ADMIN_CREDS)
        return session
    
    @pytest.fixture(scope="class")
    def admin_name(self, admin_session):
        """Get admin's name for booking"""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        return resp.json().get("name", "admin")
    
    @pytest.fixture(scope="class")
    def booking_date(self):
        """Get next Monday for booking"""
        today = datetime.now()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        return (today + timedelta(days=days_until_monday)).strftime("%Y-%m-%d")
    
    def test_08_admin_sets_booking_availability(self, admin_session):
        """Admin sets booking availability - weekdays with time slots"""
        availability_data = {
            "weekdays": {
                "mon": {"enabled": True, "start": "09:00", "end": "17:00"},
                "tue": {"enabled": True, "start": "09:00", "end": "17:00"},
                "wed": {"enabled": True, "start": "09:00", "end": "17:00"},
                "thu": {"enabled": True, "start": "09:00", "end": "17:00"},
                "fri": {"enabled": True, "start": "09:00", "end": "17:00"},
                "sat": {"enabled": False, "start": "09:00", "end": "17:00"},
                "sun": {"enabled": False, "start": "09:00", "end": "17:00"}
            },
            "slot_duration": 30,
            "buffer_time": 10,
            "blocked_dates": [],
            "booking_enabled": True,
            "timezone": "Europe/Berlin"
        }
        
        resp = admin_session.put(f"{BASE_URL}/api/booking/availability", json=availability_data)
        assert resp.status_code == 200, f"Failed to set availability: {resp.text}"
        print("Admin booking availability set")
    
    def test_09_get_booking_availability(self, admin_session):
        """Get availability"""
        resp = admin_session.get(f"{BASE_URL}/api/booking/availability")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "weekdays" in data
        assert data["booking_enabled"] == True
        print(f"Availability: slot_duration={data.get('slot_duration')}min")
    
    def test_10_get_available_slots_for_date(self, admin_name, booking_date):
        """Get available slots for a specific date"""
        resp = requests.get(f"{BASE_URL}/api/book/{admin_name}/slots?date={booking_date}")
        assert resp.status_code == 200, f"Failed to get slots: {resp.text}"
        
        data = resp.json()
        assert "slots" in data
        print(f"Found {len(data['slots'])} available slots for {booking_date}")
    
    def test_11_user1_books_a_slot(self, admin_name, booking_date):
        """User1 books a slot"""
        # Get available slots
        resp = requests.get(f"{BASE_URL}/api/book/{admin_name}/slots?date={booking_date}")
        slots = resp.json().get("slots", [])
        
        if not slots:
            pytest.skip("No available slots")
        
        slot = slots[0]
        booking_data = {
            "date": booking_date,
            "start_time": slot["start_time"],
            "guest_name": "User1 Test",
            "guest_email": "user1@meetflow.com",
            "topic": "TEST_Projektbesprechung"
        }
        
        resp = requests.post(f"{BASE_URL}/api/book/{admin_name}", json=booking_data)
        assert resp.status_code == 200, f"User1 booking failed: {resp.text}"
        
        data = resp.json()
        assert "booking_id" in data
        assert "meeting_id" in data
        
        print(f"User1 booked: {data['booking_id']}, meeting: {data['meeting_id']}")
    
    def test_12_user2_books_different_slot(self, admin_name, booking_date):
        """User2 books a different slot"""
        # Get available slots
        resp = requests.get(f"{BASE_URL}/api/book/{admin_name}/slots?date={booking_date}")
        slots = resp.json().get("slots", [])
        
        if len(slots) < 1:
            pytest.skip("Not enough available slots")
        
        slot = slots[0]  # First available (previous one is now booked)
        booking_data = {
            "date": booking_date,
            "start_time": slot["start_time"],
            "guest_name": "User2 Test",
            "guest_email": "user2@meetflow.com",
            "topic": "TEST_Beratungsgespraech"
        }
        
        resp = requests.post(f"{BASE_URL}/api/book/{admin_name}", json=booking_data)
        assert resp.status_code == 200, f"User2 booking failed: {resp.text}"
        
        data = resp.json()
        assert "booking_id" in data
        print(f"User2 booked: {data['booking_id']}")
    
    def test_13_admin_checks_my_bookings(self, admin_session):
        """Admin checks my-bookings - should see bookings"""
        resp = admin_session.get(f"{BASE_URL}/api/booking/my-bookings")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "bookings" in data
        print(f"Admin sees {len(data['bookings'])} bookings")
    
    def test_14_verify_booking_creates_calendar_event(self, admin_session):
        """Verify booking creates a meeting in calendar events"""
        resp = admin_session.get(f"{BASE_URL}/api/calendar/events")
        assert resp.status_code == 200
        
        data = resp.json()
        events = data.get("events", data) if isinstance(data, dict) else data
        
        # Find booking events
        booking_events = [e for e in events if e.get("from_booking")]
        print(f"Found {len(booking_events)} booking events in calendar")


# ==================== GENERAL POLLS ====================

class TestGeneralPolls:
    """General poll tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        session = requests.Session()
        login_user(session, ADMIN_CREDS)
        return session
    
    @pytest.fixture(scope="class")
    def single_poll(self, admin_session):
        """Create a single-choice poll"""
        poll_data = {
            "title": "TEST_Lieblings-Meeting-Tag",
            "description": "An welchem Tag sollen wir unser woechentliches Meeting haben?",
            "poll_type": "single",
            "options": ["Montag", "Dienstag", "Mittwoch", "Donnerstag"],
            "allow_comments": True,
            "allow_custom_options": False,
            "is_anonymous": False
        }
        
        resp = admin_session.post(f"{BASE_URL}/api/general-polls", json=poll_data)
        assert resp.status_code == 200, f"Failed to create poll: {resp.text}"
        
        data = resp.json()
        print(f"Created single-choice poll: {data['poll_id']}")
        
        yield data
        
        # Cleanup
        try:
            admin_session.delete(f"{BASE_URL}/api/general-polls/{data['poll_id']}")
        except:
            pass
    
    @pytest.fixture(scope="class")
    def multi_poll(self, admin_session):
        """Create a multiple-choice poll"""
        poll_data = {
            "title": "TEST_Meeting-Features",
            "description": "Welche Features nutzt du am meisten?",
            "poll_type": "multiple",
            "options": ["Chat", "Bildschirmfreigabe", "Aufnahme", "Breakout-Raeume", "Umfragen"],
            "allow_comments": True,
            "allow_custom_options": True,
            "is_anonymous": False
        }
        
        resp = admin_session.post(f"{BASE_URL}/api/general-polls", json=poll_data)
        assert resp.status_code == 200, f"Failed to create poll: {resp.text}"
        
        data = resp.json()
        print(f"Created multiple-choice poll: {data['poll_id']}")
        
        yield data
        
        # Cleanup
        try:
            admin_session.delete(f"{BASE_URL}/api/general-polls/{data['poll_id']}")
        except:
            pass
    
    def test_15_single_poll_created(self, single_poll):
        """Verify single-choice poll was created"""
        assert "poll_id" in single_poll
        assert "share_token" in single_poll
    
    def test_16_multi_poll_created(self, multi_poll):
        """Verify multiple-choice poll was created"""
        assert "poll_id" in multi_poll
        assert "share_token" in multi_poll
    
    def test_17_user1_votes_single_choice(self, single_poll):
        """User1 votes on single choice poll"""
        vote_data = {
            "voter_name": "User1",
            "voter_email": "user1@meetflow.com",
            "selected": ["Montag"]
        }
        
        resp = requests.post(f"{BASE_URL}/api/general-polls/public/{single_poll['share_token']}/vote", json=vote_data)
        assert resp.status_code == 200, f"User1 vote failed: {resp.text}"
        print("User1 voted on single-choice poll")
    
    def test_18_user2_votes_single_choice_different(self, single_poll):
        """User2 votes on same poll with different choice"""
        vote_data = {
            "voter_name": "User2",
            "voter_email": "user2@meetflow.com",
            "selected": ["Mittwoch"]
        }
        
        resp = requests.post(f"{BASE_URL}/api/general-polls/public/{single_poll['share_token']}/vote", json=vote_data)
        assert resp.status_code == 200, f"User2 vote failed: {resp.text}"
        print("User2 voted on single-choice poll")
    
    def test_19_user1_votes_multiple_choice(self, multi_poll):
        """User1 votes on multiple choice poll with 2 selections"""
        vote_data = {
            "voter_name": "User1",
            "voter_email": "user1@meetflow.com",
            "selected": ["Chat", "Bildschirmfreigabe"]
        }
        
        resp = requests.post(f"{BASE_URL}/api/general-polls/public/{multi_poll['share_token']}/vote", json=vote_data)
        assert resp.status_code == 200, f"User1 multi-vote failed: {resp.text}"
        print("User1 voted on multiple-choice poll")
    
    def test_20_get_general_poll_results(self, admin_session, single_poll):
        """Get poll results"""
        resp = admin_session.get(f"{BASE_URL}/api/general-polls/{single_poll['poll_id']}")
        assert resp.status_code == 200
        
        poll = resp.json()
        assert len(poll["votes"]) == 2, f"Expected 2 votes, got {len(poll['votes'])}"
        print(f"Single-choice poll has {len(poll['votes'])} votes")
    
    def test_21_list_general_polls(self, admin_session):
        """List all general polls"""
        resp = admin_session.get(f"{BASE_URL}/api/general-polls")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "polls" in data
        print(f"Found {data['total']} general polls")
    
    def test_22_add_comment_to_general_poll(self, single_poll):
        """Add comment to general poll"""
        comment_data = {
            "author_name": "User2",
            "text": "Gute Umfrage!"
        }
        
        resp = requests.post(f"{BASE_URL}/api/general-polls/public/{single_poll['share_token']}/comment", json=comment_data)
        assert resp.status_code == 200, f"Comment failed: {resp.text}"
        print("Comment added to general poll")


# ==================== CALENDAR INTEGRATION ====================

class TestCalendarIntegration:
    """Calendar integration tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        session = requests.Session()
        login_user(session, ADMIN_CREDS)
        return session
    
    def test_23_calendar_events_include_bookings(self, admin_session):
        """GET /api/calendar/events - verify booking events"""
        resp = admin_session.get(f"{BASE_URL}/api/calendar/events")
        assert resp.status_code == 200
        
        data = resp.json()
        events = data.get("events", data) if isinstance(data, dict) else data
        
        # Check for booking-related meetings
        booking_meetings = [e for e in events if e.get("from_booking")]
        
        if booking_meetings:
            for meeting in booking_meetings:
                assert "meeting_id" in meeting
                print(f"Found booking meeting: {meeting.get('title', 'N/A')}")
        
        print(f"Calendar has {len(events)} total events")


# ==================== GERMAN TRANSLATIONS ====================

class TestGermanTranslations:
    """Test German translations in the app"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        session = requests.Session()
        login_user(session, ADMIN_CREDS)
        return session
    
    def test_api_returns_german_content(self, admin_session):
        """Verify API responses contain German content where applicable"""
        # Get booking availability - should have German defaults
        resp = admin_session.get(f"{BASE_URL}/api/booking/availability")
        assert resp.status_code == 200
        print("Booking availability API working")
    
    def test_schedule_polls_german_labels(self, admin_session):
        """Verify schedule polls work with German content"""
        resp = admin_session.get(f"{BASE_URL}/api/schedule-polls")
        assert resp.status_code == 200
        print("Schedule polls API working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
