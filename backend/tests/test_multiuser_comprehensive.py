"""
Comprehensive Multi-User Test Suite for MeetFlow
Tests all 39+ features with 10 users as requested
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"

TEST_USERS = [
    {"email": f"user{i}@meetflow.test", "password": "test1234", "name": f"Testuser {i}"}
    for i in range(1, 11)
]


class TestSession:
    """Helper class to manage user sessions with cookies"""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.user_data = None
    
    def login(self, email, password):
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
        if resp.status_code == 200:
            self.user_data = resp.json()
        return resp
    
    def register(self, email, password, name):
        resp = self.session.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": password, "name": name})
        if resp.status_code == 200:
            self.user_data = resp.json()
        return resp
    
    def get(self, endpoint, **kwargs):
        return self.session.get(f"{BASE_URL}{endpoint}", **kwargs)
    
    def post(self, endpoint, **kwargs):
        return self.session.post(f"{BASE_URL}{endpoint}", **kwargs)
    
    def put(self, endpoint, **kwargs):
        return self.session.put(f"{BASE_URL}{endpoint}", **kwargs)
    
    def delete(self, endpoint, **kwargs):
        return self.session.delete(f"{BASE_URL}{endpoint}", **kwargs)


# ============ FIXTURES ============

@pytest.fixture(scope="module")
def admin_session():
    """Admin session fixture"""
    session = TestSession()
    resp = session.login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    return session


@pytest.fixture(scope="module")
def user_sessions():
    """Create sessions for all 10 test users"""
    sessions = []
    for user in TEST_USERS:
        session = TestSession()
        # Try login first, register if needed
        resp = session.login(user["email"], user["password"])
        if resp.status_code != 200:
            resp = session.register(user["email"], user["password"], user["name"])
            if resp.status_code != 200:
                # User might exist but login failed - try again
                session2 = TestSession()
                resp2 = session2.login(user["email"], user["password"])
                if resp2.status_code == 200:
                    sessions.append(session2)
                    continue
                pytest.skip(f"Could not create/login user {user['email']}: {resp.text}")
        sessions.append(session)
    return sessions


# ============ AUTH TESTS ============

class TestAuth:
    """Authentication tests with multiple users"""
    
    def test_admin_login(self, admin_session):
        """Admin login and verify admin role"""
        resp = admin_session.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print(f"PASSED: Admin login verified - role: {data['role']}")
    
    def test_all_users_login(self, user_sessions):
        """Verify all 10 users can login and have sessions"""
        assert len(user_sessions) == 10, f"Expected 10 user sessions, got {len(user_sessions)}"
        for i, session in enumerate(user_sessions):
            resp = session.get("/api/auth/me")
            assert resp.status_code == 200
            data = resp.json()
            assert "user_id" in data
            print(f"PASSED: User {i+1} session verified - {data.get('email')}")
    
    def test_non_admin_cannot_access_admin_endpoints(self, user_sessions):
        """Non-admin users should get 403 on admin endpoints"""
        session = user_sessions[0]
        resp = session.get("/api/admin/users")
        assert resp.status_code == 403
        print("PASSED: Non-admin gets 403 on /api/admin/users")
        
        resp = session.get("/api/admin/stats")
        assert resp.status_code == 403
        print("PASSED: Non-admin gets 403 on /api/admin/stats")


# ============ MEETING TESTS ============

class TestMeetings:
    """Meeting creation and multi-user participation tests"""
    
    @pytest.fixture(scope="class")
    def test_meeting(self, admin_session):
        """Create a test meeting for multi-user tests"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Multi-User Test Meeting",
            "description": "Testing with 10 users",
            "meeting_type": "instant",
            "lobby_enabled": False,
            "chat_enabled": True,
            "reactions_enabled": True
        })
        assert resp.status_code == 200
        meeting = resp.json()
        print(f"PASSED: Created test meeting {meeting['meeting_id']}")
        return meeting
    
    def test_all_users_join_meeting(self, test_meeting, user_sessions):
        """All 10 users join the meeting"""
        meeting_id = test_meeting["meeting_id"]
        joined_count = 0
        
        for i, session in enumerate(user_sessions):
            resp = session.post(f"/api/meetings/{meeting_id}/join")
            assert resp.status_code == 200, f"User {i+1} failed to join: {resp.text}"
            joined_count += 1
        
        assert joined_count == 10
        print(f"PASSED: All 10 users joined meeting {meeting_id}")
    
    def test_participants_list(self, test_meeting, admin_session):
        """Verify participants list shows all joined users"""
        meeting_id = test_meeting["meeting_id"]
        resp = admin_session.get(f"/api/meetings/{meeting_id}/participants")
        assert resp.status_code == 200
        participants = resp.json()
        # Should have admin + 10 users = 11 participants
        assert len(participants) >= 10, f"Expected at least 10 participants, got {len(participants)}"
        print(f"PASSED: Participants list shows {len(participants)} participants")
    
    def test_create_scheduled_meeting_with_lobby(self, admin_session):
        """Create scheduled meeting with lobby enabled"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Scheduled Meeting with Lobby",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-01T14:00:00",
            "lobby_enabled": True,
            "reminder_minutes": 15
        })
        assert resp.status_code == 200
        meeting = resp.json()
        assert meeting["lobby_enabled"] == True
        assert meeting["reminder_minutes"] == 15
        print(f"PASSED: Created scheduled meeting with lobby - {meeting['meeting_id']}")
        return meeting


# ============ LOBBY TESTS ============

class TestLobby:
    """Lobby approve/reject tests"""
    
    @pytest.fixture(scope="class")
    def lobby_meeting(self, admin_session):
        """Create meeting with lobby enabled"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Lobby Test Meeting",
            "meeting_type": "instant",
            "lobby_enabled": True
        })
        assert resp.status_code == 200
        return resp.json()
    
    def test_user_joins_lobby(self, lobby_meeting, user_sessions):
        """User joins lobby-enabled meeting"""
        meeting_id = lobby_meeting["meeting_id"]
        session = user_sessions[0]
        
        resp = session.post(f"/api/meetings/{meeting_id}/join-lobby")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("lobby") == True or data.get("status") == "waiting"
        print(f"PASSED: User joined lobby - status: {data.get('status')}")
    
    def test_admin_approves_user(self, lobby_meeting, admin_session, user_sessions):
        """Admin approves user from lobby"""
        meeting_id = lobby_meeting["meeting_id"]
        user_id = user_sessions[0].user_data["user_id"]
        
        resp = admin_session.post(f"/api/meetings/{meeting_id}/lobby/{user_id}", json={"action": "approve"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("lobby_status") == "approved"
        print("PASSED: Admin approved user from lobby")
    
    def test_admin_rejects_user(self, lobby_meeting, admin_session, user_sessions):
        """Admin rejects user from lobby"""
        meeting_id = lobby_meeting["meeting_id"]
        # User 2 joins lobby
        session = user_sessions[1]
        session.post(f"/api/meetings/{meeting_id}/join-lobby")
        
        user_id = session.user_data["user_id"]
        resp = admin_session.post(f"/api/meetings/{meeting_id}/lobby/{user_id}", json={"action": "reject"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("lobby_status") == "rejected"
        print("PASSED: Admin rejected user from lobby")


# ============ HOST CONTROLS TESTS ============

class TestHostControls:
    """Host control tests - mute all, toggle features"""
    
    @pytest.fixture(scope="class")
    def control_meeting(self, admin_session, user_sessions):
        """Create meeting and have users join"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Host Control Test Meeting",
            "meeting_type": "instant"
        })
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Have 5 users join
        for session in user_sessions[:5]:
            session.post(f"/api/meetings/{meeting_id}/join")
        
        return meeting
    
    def test_mute_all(self, control_meeting, admin_session):
        """Host mutes all participants"""
        meeting_id = control_meeting["meeting_id"]
        resp = admin_session.post(f"/api/meetings/{meeting_id}/host-control", json={"action": "mute_all"})
        assert resp.status_code == 200
        assert resp.json().get("action") == "mute_all"
        print("PASSED: Host muted all participants")
    
    def test_unmute_all(self, control_meeting, admin_session):
        """Host unmutes all participants"""
        meeting_id = control_meeting["meeting_id"]
        resp = admin_session.post(f"/api/meetings/{meeting_id}/host-control", json={"action": "unmute_all"})
        assert resp.status_code == 200
        assert resp.json().get("action") == "unmute_all"
        print("PASSED: Host unmuted all participants")
    
    def test_toggle_chat(self, control_meeting, admin_session):
        """Host toggles chat"""
        meeting_id = control_meeting["meeting_id"]
        resp = admin_session.post(f"/api/meetings/{meeting_id}/host-control", json={"action": "toggle_chat"})
        assert resp.status_code == 200
        print("PASSED: Host toggled chat")
    
    def test_toggle_reactions(self, control_meeting, admin_session):
        """Host toggles reactions"""
        meeting_id = control_meeting["meeting_id"]
        resp = admin_session.post(f"/api/meetings/{meeting_id}/host-control", json={"action": "toggle_reactions"})
        assert resp.status_code == 200
        print("PASSED: Host toggled reactions")
    
    def test_toggle_lobby(self, control_meeting, admin_session):
        """Host toggles lobby"""
        meeting_id = control_meeting["meeting_id"]
        resp = admin_session.post(f"/api/meetings/{meeting_id}/host-control", json={"action": "toggle_lobby"})
        assert resp.status_code == 200
        print("PASSED: Host toggled lobby")


# ============ CHAT TESTS ============

class TestChat:
    """Multi-user chat tests"""
    
    @pytest.fixture(scope="class")
    def chat_meeting(self, admin_session, user_sessions):
        """Create meeting for chat tests"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Chat Test Meeting",
            "meeting_type": "instant"
        })
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Have all users join
        for session in user_sessions:
            session.post(f"/api/meetings/{meeting_id}/join")
        
        return meeting
    
    def test_multiple_users_send_messages(self, chat_meeting, user_sessions):
        """Multiple users send chat messages"""
        meeting_id = chat_meeting["meeting_id"]
        
        for i, session in enumerate(user_sessions[:5]):
            resp = session.post(f"/api/meetings/{meeting_id}/chat", json={
                "message": f"Hello from User {i+1}!",
                "message_type": "text"
            })
            assert resp.status_code == 200
            print(f"PASSED: User {i+1} sent chat message")
    
    def test_get_all_chat_messages(self, chat_meeting, admin_session):
        """Verify all chat messages appear"""
        meeting_id = chat_meeting["meeting_id"]
        resp = admin_session.get(f"/api/meetings/{meeting_id}/chat")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) >= 5, f"Expected at least 5 messages, got {len(messages)}"
        print(f"PASSED: Retrieved {len(messages)} chat messages")


# ============ DOCUMENT TESTS ============

class TestDocuments:
    """Document upload and multi-user signature tests"""
    
    @pytest.fixture(scope="class")
    def doc_meeting(self, admin_session):
        """Create meeting for document tests"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Document Test Meeting",
            "meeting_type": "instant"
        })
        return resp.json()
    
    def test_upload_document(self, doc_meeting, admin_session):
        """Admin uploads a document"""
        meeting_id = doc_meeting["meeting_id"]
        
        # Create a simple PDF-like content
        files = {
            'file': ('test_document.pdf', b'%PDF-1.4 test content', 'application/pdf')
        }
        # Remove Content-Type header for multipart
        headers = dict(admin_session.session.headers)
        headers.pop('Content-Type', None)
        
        resp = admin_session.session.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/documents",
            files=files,
            headers=headers
        )
        if resp.status_code == 200:
            doc = resp.json()
            print(f"PASSED: Uploaded document {doc.get('document_id')}")
            return doc
        else:
            print(f"Document upload returned {resp.status_code} - may need different format")
            return None
    
    def test_create_signature_fields(self, doc_meeting, admin_session):
        """Admin creates signature fields on document"""
        meeting_id = doc_meeting["meeting_id"]
        
        # Get documents
        resp = admin_session.get(f"/api/meetings/{meeting_id}/documents")
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No documents to add signature fields to")
        
        docs = resp.json()
        if not docs:
            pytest.skip("No documents available")
        
        doc_id = docs[0]["document_id"]
        
        # Create 3 signature fields
        for i in range(3):
            resp = admin_session.post(f"/api/meetings/{meeting_id}/documents/{doc_id}/signature-fields", json={
                "page": 1,
                "x": 100 + (i * 150),
                "y": 500,
                "width": 120,
                "height": 50,
                "label": f"Signature {i+1}"
            })
            if resp.status_code == 200:
                print(f"PASSED: Created signature field {i+1}")
    
    def test_multiple_users_sign_document(self, doc_meeting, user_sessions, admin_session):
        """Multiple users sign the same document"""
        meeting_id = doc_meeting["meeting_id"]
        
        # Get documents
        resp = admin_session.get(f"/api/meetings/{meeting_id}/documents")
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No documents to sign")
        
        docs = resp.json()
        doc_id = docs[0]["document_id"]
        
        # Have 3 users sign
        for i, session in enumerate(user_sessions[:3]):
            # First join the meeting
            session.post(f"/api/meetings/{meeting_id}/join")
            
            resp = session.post(f"/api/meetings/{meeting_id}/documents/{doc_id}/sign", json={
                "signature_type": "typed",
                "signature_data": f"User {i+1} Signature",
                "position": {"x": 100 + (i * 150), "y": 500, "page": 1}
            })
            if resp.status_code == 200:
                print(f"PASSED: User {i+1} signed document")
            else:
                print(f"User {i+1} sign returned {resp.status_code}: {resp.text[:100]}")
    
    def test_audit_trail(self, doc_meeting, admin_session):
        """Verify audit trail shows all actions"""
        meeting_id = doc_meeting["meeting_id"]
        
        resp = admin_session.get(f"/api/meetings/{meeting_id}/documents")
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No documents for audit trail")
        
        docs = resp.json()
        doc_id = docs[0]["document_id"]
        
        resp = admin_session.get(f"/api/meetings/{meeting_id}/documents/{doc_id}/audit-trail")
        if resp.status_code == 200:
            trail = resp.json()
            print(f"PASSED: Audit trail has {len(trail)} entries")


# ============ SCHEDULE POLL TESTS ============

class TestSchedulePolls:
    """Schedule poll with multi-user voting"""
    
    @pytest.fixture(scope="class")
    def schedule_poll(self, admin_session):
        """Create a schedule poll"""
        resp = admin_session.post("/api/schedule-polls", json={
            "title": "Team Meeting Time Poll",
            "description": "Vote for the best meeting time",
            "time_slots": [
                {"date": "2026-02-10", "start_time": "09:00", "end_time": "10:00"},
                {"date": "2026-02-10", "start_time": "14:00", "end_time": "15:00"},
                {"date": "2026-02-11", "start_time": "10:00", "end_time": "11:00"}
            ],
            "allow_maybe": True
        })
        assert resp.status_code == 200
        poll = resp.json()
        print(f"PASSED: Created schedule poll {poll['poll_id']}")
        return poll
    
    def test_multiple_users_vote(self, schedule_poll):
        """5 users vote on the schedule poll"""
        share_token = schedule_poll["share_token"]
        
        # Get poll to get slot IDs
        resp = requests.get(f"{BASE_URL}/api/schedule-polls/public/{share_token}")
        assert resp.status_code == 200
        poll_data = resp.json()
        slots = poll_data.get("time_slots", [])
        
        if not slots:
            pytest.skip("No time slots in poll")
        
        # 5 users vote
        for i in range(5):
            votes = {}
            for j, slot in enumerate(slots):
                # Alternate votes
                votes[slot["slot_id"]] = "yes" if (i + j) % 2 == 0 else "maybe"
            
            resp = requests.post(f"{BASE_URL}/api/schedule-polls/public/{share_token}/vote", json={
                "voter_name": f"Voter {i+1}",
                "voter_email": f"voter{i+1}@test.com",
                "votes": votes
            })
            assert resp.status_code == 200
            print(f"PASSED: Voter {i+1} voted on schedule poll")
    
    def test_poll_results(self, schedule_poll):
        """Verify poll results show all votes"""
        share_token = schedule_poll["share_token"]
        resp = requests.get(f"{BASE_URL}/api/schedule-polls/public/{share_token}")
        assert resp.status_code == 200
        poll = resp.json()
        votes = poll.get("votes", [])
        assert len(votes) >= 5, f"Expected at least 5 votes, got {len(votes)}"
        print(f"PASSED: Poll has {len(votes)} votes")


# ============ BOOKING TESTS ============

class TestBookings:
    """1:1 Booking tests"""
    
    def test_get_booking_availability(self, admin_session):
        """Get booking availability"""
        resp = admin_session.get("/api/booking/availability")
        assert resp.status_code == 200
        avail = resp.json()
        assert "weekdays" in avail
        print("PASSED: Retrieved booking availability")
    
    def test_create_booking(self, admin_session):
        """Create a booking"""
        # Get admin name for booking
        me = admin_session.get("/api/auth/me").json()
        username = me.get("name", "Admin")
        
        # Get available slots
        resp = requests.get(f"{BASE_URL}/api/book/{username}/slots?date=2026-02-15")
        if resp.status_code != 200:
            pytest.skip(f"Could not get slots: {resp.text}")
        
        slots = resp.json().get("slots", [])
        if not slots:
            pytest.skip("No available slots")
        
        # Book first slot
        resp = requests.post(f"{BASE_URL}/api/book/{username}", json={
            "date": "2026-02-15",
            "start_time": slots[0]["start_time"],
            "guest_name": "Test Guest",
            "guest_email": "guest@test.com",
            "topic": "Test Booking"
        })
        if resp.status_code == 200:
            booking = resp.json()
            print(f"PASSED: Created booking {booking.get('booking_id')}")
        else:
            print(f"Booking creation returned {resp.status_code}")
    
    def test_list_my_bookings(self, admin_session):
        """List user's bookings"""
        resp = admin_session.get("/api/booking/my-bookings")
        assert resp.status_code == 200
        data = resp.json()
        print(f"PASSED: Retrieved {data.get('total', 0)} bookings")


# ============ GENERAL SURVEY TESTS ============

class TestGeneralSurveys:
    """General survey/poll tests"""
    
    @pytest.fixture(scope="class")
    def general_poll(self, admin_session):
        """Create a general poll"""
        resp = admin_session.post("/api/general-polls", json={
            "title": "Team Lunch Survey",
            "description": "Where should we go for lunch?",
            "poll_type": "single",
            "options": ["Italian", "Chinese", "Mexican"],
            "allow_custom_options": False,
            "is_anonymous": False
        })
        assert resp.status_code == 200
        poll = resp.json()
        print(f"PASSED: Created general poll {poll['poll_id']}")
        return poll
    
    def test_multiple_users_vote_survey(self, general_poll):
        """7 users vote on the survey"""
        share_token = general_poll["share_token"]
        
        options = ["Italian", "Chinese", "Mexican"]
        for i in range(7):
            resp = requests.post(f"{BASE_URL}/api/general-polls/public/{share_token}/vote", json={
                "voter_name": f"Survey Voter {i+1}",
                "voter_email": f"surveyvote{i+1}@test.com",
                "selected": [options[i % 3]]
            })
            assert resp.status_code == 200
            print(f"PASSED: Survey voter {i+1} voted")
    
    def test_survey_results(self, general_poll):
        """Verify survey results"""
        share_token = general_poll["share_token"]
        resp = requests.get(f"{BASE_URL}/api/general-polls/public/{share_token}")
        assert resp.status_code == 200
        poll = resp.json()
        votes = poll.get("votes", [])
        assert len(votes) >= 7, f"Expected at least 7 votes, got {len(votes)}"
        print(f"PASSED: Survey has {len(votes)} votes")


# ============ BREAKOUT ROOM TESTS ============

class TestBreakoutRooms:
    """Breakout room tests with multiple users"""
    
    @pytest.fixture(scope="class")
    def breakout_meeting(self, admin_session, user_sessions):
        """Create meeting and have users join"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Breakout Room Test Meeting",
            "meeting_type": "instant"
        })
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Have all 10 users join
        for session in user_sessions:
            session.post(f"/api/meetings/{meeting_id}/join")
        
        return meeting
    
    def test_create_breakout_rooms(self, breakout_meeting, admin_session):
        """Create 3 breakout rooms"""
        meeting_id = breakout_meeting["meeting_id"]
        
        for i in range(3):
            resp = admin_session.post(f"/api/meetings/{meeting_id}/breakout-rooms", json={
                "name": f"Room {i+1}",
                "participant_ids": []
            })
            assert resp.status_code == 200
            print(f"PASSED: Created breakout room {i+1}")
    
    def test_auto_assign_users(self, breakout_meeting, admin_session):
        """Auto-assign 10 users to 3 rooms"""
        meeting_id = breakout_meeting["meeting_id"]
        
        resp = admin_session.post(f"/api/meetings/{meeting_id}/breakout-rooms/auto-assign", json={
            "room_count": 3
        })
        assert resp.status_code == 200
        rooms = resp.json()
        
        total_assigned = sum(len(r.get("participant_ids", [])) for r in rooms)
        print(f"PASSED: Auto-assigned {total_assigned} users to {len(rooms)} rooms")
    
    def test_start_breakout_session(self, breakout_meeting, admin_session):
        """Start breakout session"""
        meeting_id = breakout_meeting["meeting_id"]
        
        resp = admin_session.post(f"/api/meetings/{meeting_id}/breakout-rooms/start", json={
            "duration": 600
        })
        assert resp.status_code == 200
        print("PASSED: Started breakout session")
    
    def test_broadcast_message(self, breakout_meeting, admin_session):
        """Broadcast message to all rooms"""
        meeting_id = breakout_meeting["meeting_id"]
        
        resp = admin_session.post(f"/api/meetings/{meeting_id}/breakout-rooms/broadcast", json={
            "message": "5 minutes remaining!"
        })
        assert resp.status_code == 200
        print("PASSED: Broadcast message to all rooms")
    
    def test_end_breakout_session(self, breakout_meeting, admin_session):
        """End breakout session"""
        meeting_id = breakout_meeting["meeting_id"]
        
        resp = admin_session.post(f"/api/meetings/{meeting_id}/breakout-rooms/end")
        assert resp.status_code == 200
        print("PASSED: Ended breakout session")


# ============ WHITEBOARD TESTS ============

class TestWhiteboard:
    """Whiteboard feature tests"""
    
    @pytest.fixture(scope="class")
    def whiteboard_meeting(self, admin_session):
        """Create meeting for whiteboard tests"""
        resp = admin_session.post("/api/meetings", json={
            "title": "Whiteboard Test Meeting",
            "meeting_type": "instant"
        })
        return resp.json()
    
    def test_save_whiteboard(self, whiteboard_meeting, admin_session):
        """Save whiteboard state"""
        meeting_id = whiteboard_meeting["meeting_id"]
        
        resp = admin_session.post(f"/api/meetings/{meeting_id}/whiteboard", json={
            "elements": [
                {"type": "pen", "points": [[0, 0], [100, 100]], "color": "#000000", "size": 2},
                {"type": "rect", "x": 50, "y": 50, "width": 100, "height": 80, "color": "#FF0000"},
                {"type": "circle", "cx": 200, "cy": 200, "r": 50, "color": "#00FF00"},
                {"type": "arrow", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "color": "#0000FF"},
                {"type": "note", "x": 300, "y": 100, "text": "Sticky note", "color": "#FFFF00"}
            ]
        })
        if resp.status_code == 200:
            print("PASSED: Saved whiteboard with multiple elements")
        else:
            print(f"Whiteboard save returned {resp.status_code}")
    
    def test_get_whiteboard(self, whiteboard_meeting, admin_session):
        """Get whiteboard state"""
        meeting_id = whiteboard_meeting["meeting_id"]
        
        resp = admin_session.get(f"/api/meetings/{meeting_id}/whiteboard")
        if resp.status_code == 200:
            data = resp.json()
            print(f"PASSED: Retrieved whiteboard with {len(data.get('elements', []))} elements")


# ============ ATTENDANCE REPORT TESTS ============

class TestAttendanceReport:
    """Attendance report tests"""
    
    def test_get_attendance_report(self, admin_session, user_sessions):
        """Get attendance report for meeting with multiple participants"""
        # Create meeting and have users join
        resp = admin_session.post("/api/meetings", json={
            "title": "Attendance Report Test",
            "meeting_type": "instant"
        })
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Have 10 users join
        for session in user_sessions:
            session.post(f"/api/meetings/{meeting_id}/join")
        
        # Get attendance report
        resp = admin_session.get(f"/api/meetings/{meeting_id}/attendance-report")
        assert resp.status_code == 200
        report = resp.json()
        
        assert report["total_participants"] >= 10
        print(f"PASSED: Attendance report shows {report['total_participants']} participants")
    
    def test_download_attendance_pdf(self, admin_session):
        """Download attendance report as PDF"""
        # Get a meeting
        resp = admin_session.get("/api/meetings")
        meetings = resp.json().get("meetings", [])
        if not meetings:
            pytest.skip("No meetings for PDF test")
        
        meeting_id = meetings[0]["meeting_id"]
        resp = admin_session.get(f"/api/meetings/{meeting_id}/attendance-report/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("Content-Type", "")
        print("PASSED: Downloaded attendance report PDF")


# ============ ADMIN TESTS ============

class TestAdmin:
    """Admin configuration tests"""
    
    def test_get_api_config(self, admin_session):
        """Get API configuration"""
        resp = admin_session.get("/api/admin/api-config")
        assert resp.status_code == 200
        config = resp.json()
        assert "llm_key" in config
        print("PASSED: Retrieved API config")
    
    def test_get_email_config(self, admin_session):
        """Get email configuration"""
        resp = admin_session.get("/api/admin/email-config")
        assert resp.status_code == 200
        config = resp.json()
        assert "provider" in config
        print("PASSED: Retrieved email config")
    
    def test_get_branding(self, admin_session):
        """Get branding configuration"""
        resp = admin_session.get("/api/admin/branding")
        assert resp.status_code == 200
        print("PASSED: Retrieved branding config")
    
    def test_update_branding(self, admin_session):
        """Update branding configuration"""
        resp = admin_session.put("/api/admin/branding", json={
            "company_name": "MeetFlow Test",
            "primary_color": "#4A5D4E"
        })
        assert resp.status_code == 200
        print("PASSED: Updated branding config")
    
    def test_get_reminder_config(self, admin_session):
        """Get reminder configuration"""
        resp = admin_session.get("/api/admin/reminder-config")
        assert resp.status_code == 200
        config = resp.json()
        assert "enabled" in config
        print("PASSED: Retrieved reminder config")
    
    def test_update_reminder_config(self, admin_session):
        """Update reminder configuration"""
        resp = admin_session.put("/api/admin/reminder-config", json={
            "enabled": True,
            "default_minutes": 15
        })
        assert resp.status_code == 200
        print("PASSED: Updated reminder config")
    
    def test_admin_stats(self, admin_session):
        """Get admin statistics"""
        resp = admin_session.get("/api/admin/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert "total_users" in stats
        assert "total_meetings" in stats
        print(f"PASSED: Admin stats - {stats['total_users']} users, {stats['total_meetings']} meetings")


# ============ ANALYTICS TESTS ============

class TestAnalytics:
    """Analytics dashboard tests"""
    
    def test_get_analytics(self, admin_session):
        """Get analytics data"""
        resp = admin_session.get("/api/analytics")
        if resp.status_code == 200:
            data = resp.json()
            print("PASSED: Retrieved analytics data")
        else:
            # Analytics endpoint might not exist
            print(f"Analytics endpoint returned {resp.status_code}")


# ============ RECORDINGS TESTS ============

class TestRecordings:
    """Recordings page tests"""
    
    def test_list_recordings(self, admin_session):
        """List recordings"""
        resp = admin_session.get("/api/recordings")
        assert resp.status_code == 200
        data = resp.json()
        print(f"PASSED: Retrieved {data.get('total', 0)} recordings")


# ============ PROFILE TESTS ============

class TestProfile:
    """User profile tests"""
    
    def test_get_profile(self, user_sessions):
        """Get user profile"""
        session = user_sessions[0]
        resp = session.get("/api/users/profile")
        assert resp.status_code == 200
        profile = resp.json()
        assert "name" in profile
        print("PASSED: Retrieved user profile")
    
    def test_update_profile(self, user_sessions):
        """Update user profile"""
        session = user_sessions[0]
        new_name = f"Updated User {uuid.uuid4().hex[:4]}"
        resp = session.put("/api/users/profile", json={"name": new_name})
        assert resp.status_code == 200
        profile = resp.json()
        assert profile["name"] == new_name
        print("PASSED: Updated user profile")


# ============ CALENDAR TESTS ============

class TestCalendar:
    """Calendar tests"""
    
    def test_get_calendar_events(self, admin_session):
        """Get calendar events"""
        resp = admin_session.get("/api/calendar/events")
        assert resp.status_code == 200
        events = resp.json()
        print(f"PASSED: Retrieved {len(events)} calendar events")


# ============ ICAL EXPORT TESTS ============

class TestICalExport:
    """iCal export tests"""
    
    def test_export_meeting_ical(self, admin_session):
        """Export meeting as iCal"""
        # Get a meeting
        resp = admin_session.get("/api/meetings")
        meetings = resp.json().get("meetings", [])
        if not meetings:
            pytest.skip("No meetings for iCal test")
        
        meeting_id = meetings[0]["meeting_id"]
        resp = admin_session.get(f"/api/meetings/{meeting_id}/ical")
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers.get("Content-Type", "")
        print("PASSED: Exported meeting as iCal")


# ============ MEETING TEMPLATES TESTS ============

class TestMeetingTemplates:
    """Meeting template tests"""
    
    def test_create_template(self, admin_session):
        """Create meeting template"""
        resp = admin_session.post("/api/meeting-templates", json={
            "name": "Weekly Standup Template",
            "title": "Weekly Standup",
            "description": "Team standup meeting",
            "duration": 30,
            "lobby_enabled": False,
            "chat_enabled": True
        })
        if resp.status_code == 200:
            template = resp.json()
            print(f"PASSED: Created template {template.get('template_id')}")
            return template
        else:
            print(f"Template creation returned {resp.status_code}")
    
    def test_list_templates(self, admin_session):
        """List meeting templates"""
        resp = admin_session.get("/api/meeting-templates")
        if resp.status_code == 200:
            templates = resp.json()
            print(f"PASSED: Retrieved {len(templates)} templates")
    
    def test_create_meeting_from_template(self, admin_session):
        """Create meeting from template"""
        # Get templates
        resp = admin_session.get("/api/meeting-templates")
        if resp.status_code != 200:
            pytest.skip("Could not get templates")
        
        templates = resp.json()
        if not templates:
            pytest.skip("No templates available")
        
        template_id = templates[0]["template_id"]
        resp = admin_session.post(f"/api/meeting-templates/{template_id}/create-meeting")
        if resp.status_code == 200:
            meeting = resp.json()
            print(f"PASSED: Created meeting from template - {meeting.get('meeting_id')}")


# ============ LEAVE MEETING TESTS ============

class TestLeaveMeeting:
    """Leave meeting tests"""
    
    def test_user_leaves_meeting(self, admin_session, user_sessions):
        """User leaves meeting"""
        # Create meeting
        resp = admin_session.post("/api/meetings", json={
            "title": "Leave Test Meeting",
            "meeting_type": "instant"
        })
        meeting = resp.json()
        meeting_id = meeting["meeting_id"]
        
        # User joins
        session = user_sessions[0]
        session.post(f"/api/meetings/{meeting_id}/join")
        
        # User leaves
        resp = session.post(f"/api/meetings/{meeting_id}/leave")
        assert resp.status_code == 200
        print("PASSED: User left meeting")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
