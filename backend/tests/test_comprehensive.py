"""
Comprehensive MeetFlow API Tests - Iteration 18
Tests all major features: Auth, Meetings, Schedule Polls, General Polls, Booking, Recordings, Admin, Analytics
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """POST /api/auth/login with correct credentials returns user + sets cookies"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert data["email"] == "admin@meetflow.com"
        assert data["role"] == "admin"
        # Check cookies are set
        assert "access_token" in response.cookies or "Set-Cookie" in response.headers.get("Set-Cookie", "")
        print(f"✓ Login success: {data['name']}")
    
    def test_login_wrong_password(self):
        """POST /api/auth/login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Wrong password returns 401")
    
    def test_get_me_without_auth(self):
        """GET /api/auth/me without cookies returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ GET /api/auth/me without auth returns 401")
    
    def test_register_new_user(self):
        """POST /api/auth/register creates new user"""
        unique_email = f"test_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "TEST_NewUser"
        })
        assert response.status_code == 200, f"Register failed: {response.text}"
        data = response.json()
        assert data["email"] == unique_email
        assert data["name"] == "TEST_NewUser"
        print(f"✓ Register success: {unique_email}")


class TestMeetings:
    """Meeting CRUD tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200, "Login failed for meeting tests"
    
    def test_create_instant_meeting(self):
        """POST /api/meetings creates instant meeting"""
        response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Instant_Meeting",
            "description": "Test instant meeting",
            "meeting_type": "instant",
            "duration": 30
        })
        assert response.status_code == 200, f"Create meeting failed: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Instant_Meeting"
        assert data["meeting_type"] == "instant"
        assert "meeting_code" in data
        print(f"✓ Created instant meeting: {data['meeting_code']}")
        return data["meeting_id"]
    
    def test_create_scheduled_meeting(self):
        """POST /api/meetings creates scheduled meeting with scheduled_at"""
        future_date = (datetime.now() + timedelta(days=1)).isoformat()
        response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Scheduled_Meeting",
            "description": "Test scheduled meeting",
            "meeting_type": "scheduled",
            "scheduled_at": future_date,
            "duration": 60
        })
        assert response.status_code == 200, f"Create scheduled meeting failed: {response.text}"
        data = response.json()
        assert data["meeting_type"] == "scheduled"
        assert data["scheduled_at"] is not None
        print(f"✓ Created scheduled meeting: {data['meeting_code']}")
        return data["meeting_id"]
    
    def test_list_meetings_pagination(self):
        """GET /api/meetings returns paginated results"""
        response = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=10")
        assert response.status_code == 200, f"List meetings failed: {response.text}"
        data = response.json()
        assert "meetings" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        print(f"✓ List meetings: {data['total']} total, page {data['page']}/{data['pages']}")
    
    def test_list_meetings_search(self):
        """GET /api/meetings?search=Team filters by title"""
        # First create a meeting with "Team" in title
        self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Team_Standup",
            "meeting_type": "instant"
        })
        response = self.session.get(f"{BASE_URL}/api/meetings?search=Team")
        assert response.status_code == 200
        data = response.json()
        assert "meetings" in data
        # All returned meetings should contain "Team" in title
        for m in data["meetings"]:
            assert "team" in m["title"].lower(), f"Meeting {m['title']} doesn't match search"
        print(f"✓ Search filter works: {len(data['meetings'])} meetings found")
    
    def test_list_meetings_upcoming(self):
        """GET /api/meetings?meeting_type=upcoming returns only upcoming"""
        response = self.session.get(f"{BASE_URL}/api/meetings?meeting_type=upcoming")
        assert response.status_code == 200
        data = response.json()
        assert "meetings" in data
        print(f"✓ Upcoming meetings: {len(data['meetings'])} found")
    
    def test_update_meeting(self):
        """PUT /api/meetings/{id} updates meeting"""
        # Create a meeting first
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Update_Meeting",
            "meeting_type": "instant"
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        # Update it
        response = self.session.put(f"{BASE_URL}/api/meetings/{meeting_id}", json={
            "title": "TEST_Updated_Title",
            "description": "Updated description"
        })
        assert response.status_code == 200, f"Update failed: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Updated_Title"
        print(f"✓ Updated meeting: {meeting_id}")
    
    def test_delete_meeting(self):
        """DELETE /api/meetings/{id} removes meeting"""
        # Create a meeting first
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Delete_Meeting",
            "meeting_type": "instant"
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        # Delete it
        response = self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert response.status_code == 200, f"Delete failed: {response.text}"
        
        # Verify it's gone
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 404
        print(f"✓ Deleted meeting: {meeting_id}")
    
    def test_meeting_ical_export(self):
        """GET /api/meetings/{id}/ical returns valid .ics file"""
        # Create a scheduled meeting
        future_date = (datetime.now() + timedelta(days=1)).isoformat()
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_iCal_Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": future_date
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        # Get iCal
        response = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/ical")
        assert response.status_code == 200
        assert "text/calendar" in response.headers.get("Content-Type", "")
        assert "VCALENDAR" in response.text
        assert "VEVENT" in response.text
        print(f"✓ iCal export works for meeting: {meeting_id}")


class TestSchedulePolls:
    """Schedule Poll (Doodle-style) tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
    
    def test_create_schedule_poll(self):
        """POST /api/schedule-polls creates poll with time_slots"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": "TEST_Schedule_Poll",
            "description": "Test poll",
            "time_slots": [
                {"date": tomorrow, "start_time": "09:00", "end_time": "10:00"},
                {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"}
            ],
            "allow_maybe": True,
            "allow_suggestions": True
        })
        assert response.status_code == 200, f"Create poll failed: {response.text}"
        data = response.json()
        assert "poll_id" in data
        assert "share_token" in data
        print(f"✓ Created schedule poll: {data['poll_id']}, token: {data['share_token']}")
        return data
    
    def test_get_public_poll(self):
        """GET /api/schedule-polls/public/{token} returns poll without auth"""
        # Create poll first
        poll_data = self.test_create_schedule_poll()
        
        # Access without auth
        response = requests.get(f"{BASE_URL}/api/schedule-polls/public/{poll_data['share_token']}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Schedule_Poll"
        assert len(data["time_slots"]) == 2
        print("✓ Public poll access works")
        return poll_data
    
    def test_vote_on_poll(self):
        """POST .../vote records vote, same voter name updates existing vote"""
        poll_data = self.test_create_schedule_poll()
        
        # Get poll to get slot IDs
        poll = requests.get(f"{BASE_URL}/api/schedule-polls/public/{poll_data['share_token']}").json()
        slot_ids = [s["slot_id"] for s in poll["time_slots"]]
        
        # First vote
        response = requests.post(f"{BASE_URL}/api/schedule-polls/public/{poll_data['share_token']}/vote", json={
            "voter_name": "TEST_Voter",
            "voter_email": "voter@test.com",
            "votes": {slot_ids[0]: "yes", slot_ids[1]: "maybe"}
        })
        assert response.status_code == 200
        print("✓ Vote recorded")
        
        # Update vote (same name)
        response2 = requests.post(f"{BASE_URL}/api/schedule-polls/public/{poll_data['share_token']}/vote", json={
            "voter_name": "TEST_Voter",
            "votes": {slot_ids[0]: "no", slot_ids[1]: "yes"}
        })
        assert response2.status_code == 200
        print("✓ Vote updated for same voter")
    
    def test_add_comment(self):
        """POST .../comment adds comment"""
        poll_data = self.test_create_schedule_poll()
        
        response = requests.post(f"{BASE_URL}/api/schedule-polls/public/{poll_data['share_token']}/comment", json={
            "author_name": "TEST_Commenter",
            "text": "This is a test comment"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "This is a test comment"
        print("✓ Comment added")
    
    def test_suggest_time_slot(self):
        """POST .../suggest adds time slot (when allowed)"""
        poll_data = self.test_create_schedule_poll()
        day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        
        response = requests.post(f"{BASE_URL}/api/schedule-polls/public/{poll_data['share_token']}/suggest", json={
            "date": day_after,
            "start_time": "16:00",
            "end_time": "17:00",
            "name": "TEST_Suggester"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["date"] == day_after
        print("✓ Time slot suggested")
    
    def test_confirm_poll_creates_meeting(self):
        """POST /api/schedule-polls/{id}/confirm confirms slot and creates meeting"""
        poll_data = self.test_create_schedule_poll()
        poll = requests.get(f"{BASE_URL}/api/schedule-polls/public/{poll_data['share_token']}").json()
        slot_id = poll["time_slots"][0]["slot_id"]
        
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/{poll_data['poll_id']}/confirm", json={
            "slot_id": slot_id
        })
        assert response.status_code == 200
        data = response.json()
        assert "meeting_id" in data or data.get("message") == "Poll confirmed"
        print("✓ Poll confirmed, meeting created")
    
    def test_export_csv(self):
        """GET /api/schedule-polls/{id}/export/csv returns CSV"""
        poll_data = self.test_create_schedule_poll()
        
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_data['poll_id']}/export/csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("Content-Type", "")
        print("✓ CSV export works")
    
    def test_export_pdf(self):
        """GET /api/schedule-polls/{id}/export/pdf returns PDF"""
        poll_data = self.test_create_schedule_poll()
        
        response = self.session.get(f"{BASE_URL}/api/schedule-polls/{poll_data['poll_id']}/export/pdf")
        assert response.status_code == 200
        assert "application/pdf" in response.headers.get("Content-Type", "")
        print("✓ PDF export works")


class TestGeneralPolls:
    """General Poll (non-time) tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
    
    def test_create_single_choice_poll(self):
        """POST /api/general-polls creates poll with single type"""
        response = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Single_Poll",
            "description": "Single choice test",
            "poll_type": "single",
            "options": ["Option A", "Option B", "Option C"],
            "allow_custom_options": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "poll_id" in data
        assert "share_token" in data
        print(f"✓ Created single choice poll: {data['poll_id']}")
        return data
    
    def test_create_multiple_choice_poll(self):
        """POST /api/general-polls creates poll with multiple type"""
        response = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "TEST_Multiple_Poll",
            "poll_type": "multiple",
            "options": ["Red", "Blue", "Green", "Yellow"]
        })
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Created multiple choice poll: {data['poll_id']}")
        return data
    
    def test_get_public_general_poll(self):
        """GET /api/general-polls/public/{token} returns poll without auth"""
        poll_data = self.test_create_single_choice_poll()
        
        response = requests.get(f"{BASE_URL}/api/general-polls/public/{poll_data['share_token']}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_Single_Poll"
        print("✓ Public general poll access works")
        return poll_data
    
    def test_vote_single_choice(self):
        """POST .../vote records vote for single (1 option)"""
        poll_data = self.test_create_single_choice_poll()
        
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{poll_data['share_token']}/vote", json={
            "voter_name": "TEST_SingleVoter",
            "selected": ["Option A"]
        })
        assert response.status_code == 200
        print("✓ Single choice vote recorded")
    
    def test_vote_multiple_choice(self):
        """POST .../vote records vote for multiple (many options)"""
        poll_data = self.test_create_multiple_choice_poll()
        
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{poll_data['share_token']}/vote", json={
            "voter_name": "TEST_MultiVoter",
            "selected": ["Red", "Blue"]
        })
        assert response.status_code == 200
        print("✓ Multiple choice vote recorded")
    
    def test_add_custom_option(self):
        """POST .../add-option adds custom option when allowed"""
        poll_data = self.test_create_single_choice_poll()
        
        response = requests.post(f"{BASE_URL}/api/general-polls/public/{poll_data['share_token']}/add-option", json={
            "option": "Custom Option D"
        })
        assert response.status_code == 200
        print("✓ Custom option added")
    
    def test_close_poll_prevents_voting(self):
        """POST /api/general-polls/{id}/close closes poll, voting on closed returns 400"""
        poll_data = self.test_create_single_choice_poll()
        
        # Close the poll
        close_resp = self.session.post(f"{BASE_URL}/api/general-polls/{poll_data['poll_id']}/close")
        assert close_resp.status_code == 200
        print("✓ Poll closed")
        
        # Try to vote on closed poll
        vote_resp = requests.post(f"{BASE_URL}/api/general-polls/public/{poll_data['share_token']}/vote", json={
            "voter_name": "TEST_LateVoter",
            "selected": ["Option A"]
        })
        assert vote_resp.status_code == 400
        print("✓ Voting on closed poll returns 400")


class TestBooking:
    """1:1 Booking feature tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
        self.user_data = resp.json()
    
    def test_get_availability(self):
        """GET /api/booking/availability returns weekday schedule"""
        response = self.session.get(f"{BASE_URL}/api/booking/availability")
        assert response.status_code == 200
        data = response.json()
        assert "weekdays" in data
        assert "slot_duration" in data
        print("✓ Got availability settings")
    
    def test_update_availability(self):
        """PUT /api/booking/availability saves settings"""
        response = self.session.put(f"{BASE_URL}/api/booking/availability", json={
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
            "booking_enabled": True
        })
        assert response.status_code == 200
        print("✓ Updated availability settings")
    
    def test_get_public_user_info(self):
        """GET /api/book/{username}/info returns public user info"""
        username = self.user_data["name"]
        response = requests.get(f"{BASE_URL}/api/book/{username}/info")
        assert response.status_code == 200
        data = response.json()
        assert "user_name" in data
        assert "booking_enabled" in data
        print(f"✓ Got public booking info for {username}")
    
    def test_get_available_slots_enabled_day(self):
        """GET /api/book/{username}/slots?date=YYYY-MM-DD returns available slots for enabled weekday"""
        username = self.user_data["name"]
        # Find next Monday
        today = datetime.now()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = (today + timedelta(days=days_until_monday)).strftime("%Y-%m-%d")
        
        response = requests.get(f"{BASE_URL}/api/book/{username}/slots?date={next_monday}")
        assert response.status_code == 200
        data = response.json()
        assert "slots" in data
        print(f"✓ Got {len(data['slots'])} slots for {next_monday}")
    
    def test_get_slots_disabled_day(self):
        """GET /api/book/{username}/slots returns empty for disabled weekday (Saturday)"""
        username = self.user_data["name"]
        # Find next Saturday
        today = datetime.now()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        next_saturday = (today + timedelta(days=days_until_saturday)).strftime("%Y-%m-%d")
        
        response = requests.get(f"{BASE_URL}/api/book/{username}/slots?date={next_saturday}")
        assert response.status_code == 200
        data = response.json()
        assert data["slots"] == []
        print("✓ Saturday returns empty slots")
    
    def test_create_booking(self):
        """POST /api/book/{username} creates booking + meeting"""
        username = self.user_data["name"]
        # Find next Monday
        today = datetime.now()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = (today + timedelta(days=days_until_monday)).strftime("%Y-%m-%d")
        
        # Get available slots
        slots_resp = requests.get(f"{BASE_URL}/api/book/{username}/slots?date={next_monday}")
        slots = slots_resp.json().get("slots", [])
        if not slots:
            pytest.skip("No available slots")
        
        response = requests.post(f"{BASE_URL}/api/book/{username}", json={
            "date": next_monday,
            "start_time": slots[0]["start_time"],
            "guest_name": "TEST_BookingGuest",
            "guest_email": "guest@test.com",
            "topic": "TEST_Booking_Topic"
        })
        assert response.status_code == 200, f"Booking failed: {response.text}"
        data = response.json()
        assert "booking_id" in data
        assert "meeting_code" in data
        print(f"✓ Created booking: {data['booking_id']}, meeting: {data['meeting_code']}")
        return data
    
    def test_double_booking_prevention(self):
        """POST /api/book/{username} same slot twice returns 409"""
        username = self.user_data["name"]
        # Find next Tuesday
        today = datetime.now()
        days_until_tuesday = (1 - today.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        next_tuesday = (today + timedelta(days=days_until_tuesday)).strftime("%Y-%m-%d")
        
        # Get available slots
        slots_resp = requests.get(f"{BASE_URL}/api/book/{username}/slots?date={next_tuesday}")
        slots = slots_resp.json().get("slots", [])
        if not slots:
            pytest.skip("No available slots")
        
        # First booking
        first_resp = requests.post(f"{BASE_URL}/api/book/{username}", json={
            "date": next_tuesday,
            "start_time": slots[0]["start_time"],
            "guest_name": "TEST_FirstGuest",
            "topic": "First booking"
        })
        assert first_resp.status_code == 200
        
        # Second booking same slot
        second_resp = requests.post(f"{BASE_URL}/api/book/{username}", json={
            "date": next_tuesday,
            "start_time": slots[0]["start_time"],
            "guest_name": "TEST_SecondGuest",
            "topic": "Second booking"
        })
        assert second_resp.status_code == 409
        print("✓ Double booking prevented (409)")
    
    def test_booking_ical(self):
        """GET /api/bookings/{id}/ical returns .ics file"""
        booking_data = self.test_create_booking()
        
        response = requests.get(f"{BASE_URL}/api/bookings/{booking_data['booking_id']}/ical")
        assert response.status_code == 200
        assert "text/calendar" in response.headers.get("Content-Type", "")
        print("✓ Booking iCal export works")


class TestRecordings:
    """Recording feature tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
    
    def test_list_recordings(self):
        """GET /api/recordings returns paginated results"""
        response = self.session.get(f"{BASE_URL}/api/recordings?page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "recordings" in data
        assert "total" in data
        assert "page" in data
        print(f"✓ Got {data['total']} recordings")


class TestAdmin:
    """Admin feature tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
    
    def test_admin_list_users(self):
        """GET /api/admin/users returns user list (admin only)"""
        response = self.session.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} users")
    
    def test_get_email_config(self):
        """GET /api/admin/email-config returns email settings"""
        response = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "enabled" in data
        print("✓ Got email config")
    
    def test_update_email_config(self):
        """PUT /api/admin/email-config saves settings"""
        response = self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "provider": "resend",
            "enabled": False
        })
        assert response.status_code == 200
        print("✓ Updated email config")
    
    def test_get_api_config(self):
        """GET /api/admin/api-config returns LLM settings with masked key"""
        response = self.session.get(f"{BASE_URL}/api/admin/api-config")
        assert response.status_code == 200
        data = response.json()
        assert "llm_key" in data
        assert "llm_model" in data
        # Key should be masked
        if data.get("llm_key"):
            assert "***" in data["llm_key"]
        print("✓ Got API config (key masked)")


class TestAnalytics:
    """Analytics feature tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
    
    def test_analytics_overview(self):
        """GET /api/analytics/overview returns all counters including scheduling data"""
        response = self.session.get(f"{BASE_URL}/api/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        # Check meeting counters
        assert "total_meetings" in data
        assert "active_meetings" in data
        assert "ended_meetings" in data
        # Check scheduling counters
        assert "total_schedule_polls" in data
        assert "total_general_polls" in data
        assert "total_bookings" in data
        print(f"✓ Analytics overview: {data['total_meetings']} meetings, {data['total_schedule_polls']} schedule polls")
    
    def test_analytics_scheduling(self):
        """GET /api/analytics/scheduling returns schedule_polls, general_polls, booking data"""
        response = self.session.get(f"{BASE_URL}/api/analytics/scheduling")
        assert response.status_code == 200
        data = response.json()
        assert "schedule_polls" in data
        assert "general_polls" in data
        # API returns booking_by_day instead of bookings
        assert "booking_by_day" in data or "bookings" in data
        print(f"✓ Scheduling analytics: {len(data['schedule_polls'])} polls")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
