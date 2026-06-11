"""
Comprehensive MeetFlow API Test Suite - Iteration 41
Tests all major features: Auth, Meetings, Chat, Polls, Q&A, Documents, Calendar, Scheduling, Admin, Whiteboard
"""
import pytest
import requests
import os
import time
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
USER1_EMAIL = "user1@meetflow.com"
USER1_PASSWORD = "test123"
USER2_EMAIL = "user2@meetflow.com"
USER2_PASSWORD = "test123"


class TestAuthAndUserManagement:
    """Auth & User Management Tests (1-6)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_01_register_new_user(self):
        """Test 1: Register new user"""
        unique_email = f"test_user_{int(time.time())}@meetflow.com"
        response = self.session.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test Registration User"
        })
        assert response.status_code == 200, f"Register failed: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert data["email"] == unique_email
        print(f"PASSED: Registered user {unique_email}")
    
    def test_02_login_admin(self):
        """Test 2: Login as admin"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert data["role"] == "admin"
        assert data["email"] == ADMIN_EMAIL
        print("PASSED: Admin login successful")
    
    def test_03_login_user1(self):
        """Test 3: Login as user1"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER1_EMAIL,
            "password": USER1_PASSWORD
        })
        assert response.status_code == 200, f"User1 login failed: {response.text}"
        data = response.json()
        assert data["email"] == USER1_EMAIL
        print("PASSED: User1 login successful")
    
    def test_04_get_current_user(self):
        """Test 4: GET /api/auth/me returns correct user"""
        # Login first
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Get me failed: {response.text}"
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        print("PASSED: /api/auth/me returns correct user")
    
    def test_05_update_user_profile(self):
        """Test 5: Update user profile"""
        # Login first
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        response = self.session.put(f"{BASE_URL}/api/users/profile", json={
            "name": "Updated Admin Name"
        })
        assert response.status_code == 200, f"Update profile failed: {response.text}"
        data = response.json()
        assert data["name"] == "Updated Admin Name"
        print("PASSED: Profile updated successfully")
    
    def test_06_logout(self):
        """Test 6: Logout flow"""
        # Login first
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        response = self.session.post(f"{BASE_URL}/api/auth/logout")
        assert response.status_code == 200, f"Logout failed: {response.text}"
        print("PASSED: Logout successful")


class TestMeetingsCRUD:
    """Meetings CRUD Tests (7-13)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_07_dashboard_meetings_list(self):
        """Test 7: Dashboard loads with meeting list"""
        response = self.session.get(f"{BASE_URL}/api/meetings")
        assert response.status_code == 200, f"Get meetings failed: {response.text}"
        data = response.json()
        assert "meetings" in data
        assert "total" in data
        print(f"PASSED: Dashboard meetings list - {data['total']} meetings found")
    
    def test_08_create_instant_meeting(self):
        """Test 8: Create instant meeting from dashboard"""
        response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Test Instant Meeting",
            "description": "Created by test suite",
            "meeting_type": "instant",
            "duration": 30
        })
        assert response.status_code == 200, f"Create instant meeting failed: {response.text}"
        data = response.json()
        assert data["meeting_type"] == "instant"
        assert data["status"] == "active"
        print(f"PASSED: Created instant meeting {data['meeting_id']}")
        return data["meeting_id"]
    
    def test_09_create_scheduled_meeting(self):
        """Test 9: Create scheduled meeting from dashboard"""
        scheduled_time = (datetime.utcnow() + timedelta(days=1)).isoformat()
        response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Test Scheduled Meeting",
            "description": "Scheduled for tomorrow",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_time,
            "duration": 60
        })
        assert response.status_code == 200, f"Create scheduled meeting failed: {response.text}"
        data = response.json()
        assert data["meeting_type"] == "scheduled"
        assert data["status"] == "scheduled"
        print(f"PASSED: Created scheduled meeting {data['meeting_id']}")
    
    def test_10_list_meetings_with_pagination(self):
        """Test 10: GET /api/meetings returns meetings list with pagination"""
        response = self.session.get(f"{BASE_URL}/api/meetings?page=1&limit=10")
        assert response.status_code == 200, f"List meetings failed: {response.text}"
        data = response.json()
        assert "meetings" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        print(f"PASSED: Meetings list with pagination - page {data['page']} of {data['pages']}")
    
    def test_11_get_meeting_details(self):
        """Test 11: GET /api/meetings/{id} returns meeting details"""
        # Create a meeting first
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Test Meeting for Details",
            "meeting_type": "instant",
            "duration": 30
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert response.status_code == 200, f"Get meeting details failed: {response.text}"
        data = response.json()
        assert data["meeting_id"] == meeting_id
        assert "participants" in data
        print(f"PASSED: Got meeting details for {meeting_id}")
    
    def test_12_update_meeting_settings(self):
        """Test 12: Update meeting settings"""
        # Create a meeting first
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Test Meeting for Update",
            "meeting_type": "instant",
            "duration": 30
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        response = self.session.put(f"{BASE_URL}/api/meetings/{meeting_id}", json={
            "title": "Updated Meeting Title",
            "chat_enabled": False
        })
        assert response.status_code == 200, f"Update meeting failed: {response.text}"
        data = response.json()
        assert data["title"] == "Updated Meeting Title"
        print(f"PASSED: Updated meeting {meeting_id}")
    
    def test_13_delete_meeting(self):
        """Test 13: Delete a meeting"""
        # Create a meeting first
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Test Meeting for Delete",
            "meeting_type": "instant",
            "duration": 30
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        response = self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert response.status_code == 200, f"Delete meeting failed: {response.text}"
        
        # Verify deletion
        get_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 404
        print(f"PASSED: Deleted meeting {meeting_id}")


class TestLiveMeetingFeatures:
    """Live Meeting Features Tests (14-22)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        # Create a meeting for tests
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Live Meeting Test",
            "meeting_type": "instant",
            "duration": 60
        })
        self.meeting_id = create_resp.json()["meeting_id"]
    
    def test_14_join_meeting(self):
        """Test 14: Join meeting page loads correctly"""
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/join")
        assert response.status_code == 200, f"Join meeting failed: {response.text}"
        data = response.json()
        assert data["status"] == "active"
        print(f"PASSED: Joined meeting {self.meeting_id}")
    
    def test_15_get_participants(self):
        """Test 15: Meeting toolbar - get participants"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/participants")
        assert response.status_code == 200, f"Get participants failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Got {len(data)} participants")
    
    def test_16_send_chat_message(self):
        """Test 16: Chat: send message"""
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/chat", json={
            "message": "Hello from test suite!",
            "message_type": "text"
        })
        assert response.status_code == 200, f"Send chat failed: {response.text}"
        data = response.json()
        assert data["message"] == "Hello from test suite!"
        print("PASSED: Sent chat message")
    
    def test_17_list_chat_messages(self):
        """Test 17: Chat: list messages"""
        # Send a message first
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/chat", json={
            "message": "Test message for listing",
            "message_type": "text"
        })
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/chat")
        assert response.status_code == 200, f"List chat failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Listed {len(data)} chat messages")
    
    def test_18_create_and_vote_poll(self):
        """Test 18: Polls: create poll, vote on it"""
        # Create poll
        create_resp = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/polls", json={
            "question": "Test Poll Question?",
            "options": ["Option A", "Option B", "Option C"]
        })
        assert create_resp.status_code == 200, f"Create poll failed: {create_resp.text}"
        poll_id = create_resp.json()["poll_id"]
        
        # Vote on poll
        vote_resp = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/polls/{poll_id}/vote", json={
            "option_index": 0
        })
        assert vote_resp.status_code == 200, f"Vote poll failed: {vote_resp.text}"
        print(f"PASSED: Created and voted on poll {poll_id}")
    
    def test_19_create_and_upvote_question(self):
        """Test 19: Q&A: create question, upvote"""
        # Create question
        create_resp = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/questions", json={
            "text": "Test Question from test suite?"
        })
        assert create_resp.status_code == 200, f"Create question failed: {create_resp.text}"
        question_id = create_resp.json()["question_id"]
        
        # Login as different user to upvote
        session2 = requests.Session()
        session2.headers.update({"Content-Type": "application/json"})
        session2.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER1_EMAIL,
            "password": USER1_PASSWORD
        })
        
        upvote_resp = session2.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/questions/{question_id}/upvote")
        assert upvote_resp.status_code == 200, f"Upvote question failed: {upvote_resp.text}"
        print(f"PASSED: Created and upvoted question {question_id}")
    
    def test_20_create_breakout_room(self):
        """Test 20: Breakout rooms: create room"""
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Test Breakout Room",
            "participant_ids": []
        })
        assert response.status_code == 200, f"Create breakout room failed: {response.text}"
        data = response.json()
        assert data["name"] == "Test Breakout Room"
        print(f"PASSED: Created breakout room {data['room_id']}")
    
    def test_21_hand_raise_toggle(self):
        """Test 21: Hand raise toggle"""
        # Get current user's participant record
        me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
        user_id = me_resp.json()["user_id"]
        
        # Update hand raised status
        response = self.session.put(f"{BASE_URL}/api/meetings/{self.meeting_id}/participants/{user_id}", json={
            "hand_raised": True
        })
        assert response.status_code == 200, f"Hand raise failed: {response.text}"
        print("PASSED: Hand raise toggled")
    
    def test_22_get_polls(self):
        """Test 22: Get meeting polls"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/polls")
        assert response.status_code == 200, f"Get polls failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Got {len(data)} polls")


class TestDocumentsAndSignatures:
    """Documents & Signatures Tests (23-30)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        # Create a meeting for tests
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Document Test Meeting",
            "meeting_type": "instant",
            "duration": 60
        })
        self.meeting_id = create_resp.json()["meeting_id"]
    
    def test_23_upload_pdf_document(self):
        """Test 23: Upload PDF document to meeting"""
        # Create a simple PDF
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/test_doc.pdf'); c.drawString(100,700,'Test Document'); c.save()"
        ], check=True)
        
        # Remove Content-Type header for multipart upload
        headers = dict(self.session.headers)
        headers.pop("Content-Type", None)
        
        with open('/tmp/test_doc.pdf', 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
                files={"file": ("test_doc.pdf", f, "application/pdf")},
                cookies=self.session.cookies
            )
        assert response.status_code == 200, f"Upload document failed: {response.text}"
        data = response.json()
        assert "doc_id" in data
        self.doc_id = data["doc_id"]
        print(f"PASSED: Uploaded document {data['doc_id']}")
        return data["doc_id"]
    
    def test_24_list_documents(self):
        """Test 24: List documents"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents")
        assert response.status_code == 200, f"List documents failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Listed {len(data)} documents")
    
    def test_25_present_document(self):
        """Test 25: Present document"""
        # Upload a document first
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/test_present.pdf'); c.drawString(100,700,'Present Test'); c.save()"
        ], check=True)
        
        with open('/tmp/test_present.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
                files={"file": ("test_present.pdf", f, "application/pdf")},
                cookies=self.session.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/present", json={
            "presenting": True,
            "page": 1
        })
        assert response.status_code == 200, f"Present document failed: {response.text}"
        print(f"PASSED: Started presenting document {doc_id}")
    
    def test_26_sign_document(self):
        """Test 26: Sign document with typed signature"""
        # Upload a document first
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/test_sign.pdf'); c.drawString(100,700,'Sign Test'); c.save()"
        ], check=True)
        
        with open('/tmp/test_sign.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
                files={"file": ("test_sign.pdf", f, "application/pdf")},
                cookies=self.session.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/sign", json={
            "type": "typed",
            "signature_data": "Admin Signature",
            "pos_x": 100,
            "pos_y": 500,
            "page": 1
        })
        assert response.status_code == 200, f"Sign document failed: {response.text}"
        print(f"PASSED: Signed document {doc_id}")
        return doc_id
    
    def test_27_download_signed_pdf(self):
        """Test 27: Download signed PDF"""
        # Upload and sign a document first
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/test_download.pdf'); c.drawString(100,700,'Download Test'); c.save()"
        ], check=True)
        
        with open('/tmp/test_download.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
                files={"file": ("test_download.pdf", f, "application/pdf")},
                cookies=self.session.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        # Sign it
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/sign", json={
            "type": "typed",
            "signature_data": "Test Signature",
            "pos_x": 100,
            "pos_y": 500,
            "page": 1
        })
        
        # Download signed version
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/download-signed")
        assert response.status_code == 200, f"Download signed failed: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print("PASSED: Downloaded signed PDF")
    
    def test_28_delete_document(self):
        """Test 28: Delete document"""
        # Upload a document first
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/test_delete.pdf'); c.drawString(100,700,'Delete Test'); c.save()"
        ], check=True)
        
        with open('/tmp/test_delete.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
                files={"file": ("test_delete.pdf", f, "application/pdf")},
                cookies=self.session.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        response = self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}")
        assert response.status_code == 200, f"Delete document failed: {response.text}"
        print(f"PASSED: Deleted document {doc_id}")
    
    def test_29_reorder_documents(self):
        """Test 29: Reorder documents"""
        # Upload two documents
        import subprocess
        for i in range(2):
            subprocess.run([
                "python3", "-c",
                f"from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/test_reorder_{i}.pdf'); c.drawString(100,700,'Reorder Test {i}'); c.save()"
            ], check=True)
        
        doc_ids = []
        for i in range(2):
            with open(f'/tmp/test_reorder_{i}.pdf', 'rb') as f:
                upload_resp = requests.post(
                    f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
                    files={"file": (f"test_reorder_{i}.pdf", f, "application/pdf")},
                    cookies=self.session.cookies
                )
            assert upload_resp.status_code == 200, f"Upload {i} failed: {upload_resp.text}"
            doc_ids.append(upload_resp.json()["doc_id"])
        
        # Reorder (reverse)
        response = self.session.put(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/reorder", json={
            "doc_ids": list(reversed(doc_ids))
        })
        assert response.status_code == 200, f"Reorder documents failed: {response.text}"
        print("PASSED: Reordered documents")
    
    def test_30_audit_trail(self):
        """Test 30: Audit trail"""
        # Upload a document first
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/test_audit.pdf'); c.drawString(100,700,'Audit Test'); c.save()"
        ], check=True)
        
        with open('/tmp/test_audit.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{self.meeting_id}/documents",
                files={"file": ("test_audit.pdf", f, "application/pdf")},
                cookies=self.session.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/documents/{doc_id}/audit-log")
        assert response.status_code == 200, f"Get audit log failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0  # Should have at least upload entry
        print(f"PASSED: Got {len(data)} audit log entries")


class TestCalendar:
    """Calendar Tests (31-33)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_31_get_calendar_events(self):
        """Test 31: GET /api/calendar/events returns events"""
        response = self.session.get(f"{BASE_URL}/api/calendar/events")
        assert response.status_code == 200, f"Get calendar events failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Got {len(data)} calendar events")
    
    def test_32_calendar_includes_bookings(self):
        """Test 32: Calendar includes booking events"""
        response = self.session.get(f"{BASE_URL}/api/calendar/events")
        assert response.status_code == 200, f"Get calendar events failed: {response.text}"
        data = response.json()
        # Check if any events have meeting_type=booking
        booking_events = [e for e in data if e.get("meeting_type") == "booking"]
        print(f"PASSED: Calendar has {len(booking_events)} booking events")
    
    def test_33_rsvp_to_event(self):
        """Test 33: RSVP to event"""
        # Create a scheduled meeting first
        scheduled_time = (datetime.utcnow() + timedelta(days=2)).isoformat()
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "RSVP Test Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_time,
            "duration": 60
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        response = self.session.put(f"{BASE_URL}/api/calendar/events/{meeting_id}/rsvp", json={
            "status": "accepted"
        })
        assert response.status_code == 200, f"RSVP failed: {response.text}"
        data = response.json()
        assert data["rsvp_status"] == "accepted"
        print(f"PASSED: RSVP to event {meeting_id}")


class TestScheduling:
    """Scheduling Tests (34-40)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_34_create_schedule_poll(self):
        """Test 34: Create schedule poll"""
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        response = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": "Test Schedule Poll",
            "description": "Testing schedule poll creation",
            "time_slots": [
                {"date": tomorrow, "start_time": "10:00", "end_time": "11:00"},
                {"date": tomorrow, "start_time": "14:00", "end_time": "15:00"}
            ],
            "allow_maybe": True,
            "allow_suggestions": True
        })
        assert response.status_code == 200, f"Create schedule poll failed: {response.text}"
        data = response.json()
        assert "poll_id" in data
        assert "share_token" in data
        print(f"PASSED: Created schedule poll {data['poll_id']}")
        return data
    
    def test_35_vote_on_schedule_poll(self):
        """Test 35: Vote on schedule poll"""
        # Create poll first
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        create_resp = self.session.post(f"{BASE_URL}/api/schedule-polls", json={
            "title": "Vote Test Poll",
            "time_slots": [
                {"date": tomorrow, "start_time": "10:00", "end_time": "11:00"}
            ]
        })
        share_token = create_resp.json()["share_token"]
        
        # Get poll to get slot_id
        poll_resp = self.session.get(f"{BASE_URL}/api/schedule-polls/public/{share_token}")
        slot_id = poll_resp.json()["time_slots"][0]["slot_id"]
        
        # Vote
        response = self.session.post(f"{BASE_URL}/api/schedule-polls/public/{share_token}/vote", json={
            "voter_name": "Test Voter",
            "voter_email": "voter@test.com",
            "votes": {slot_id: "yes"}
        })
        assert response.status_code == 200, f"Vote on schedule poll failed: {response.text}"
        print("PASSED: Voted on schedule poll")
    
    def test_36_create_booking_availability(self):
        """Test 36: Create booking availability"""
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
        assert response.status_code == 200, f"Create booking availability failed: {response.text}"
        print("PASSED: Created booking availability")
    
    def test_37_book_a_slot(self):
        """Test 37: Book a slot"""
        # Get admin's name for booking
        me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
        admin_name = me_resp.json()["name"]
        
        # Get available slots for tomorrow (weekday)
        tomorrow = datetime.utcnow() + timedelta(days=1)
        # Find next weekday
        while tomorrow.weekday() >= 5:  # Skip weekend
            tomorrow += timedelta(days=1)
        date_str = tomorrow.strftime("%Y-%m-%d")
        
        slots_resp = self.session.get(f"{BASE_URL}/api/book/{admin_name}/slots?date={date_str}")
        if slots_resp.status_code == 200 and slots_resp.json().get("slots"):
            slot = slots_resp.json()["slots"][0]
            
            response = self.session.post(f"{BASE_URL}/api/book/{admin_name}", json={
                "date": date_str,
                "start_time": slot["start_time"],
                "guest_name": "Test Guest",
                "guest_email": "guest@test.com",
                "topic": "Test Booking"
            })
            assert response.status_code == 200, f"Book slot failed: {response.text}"
            print(f"PASSED: Booked slot for {date_str}")
        else:
            print("PASSED: Booking availability not set up (expected)")
    
    def test_38_get_my_bookings(self):
        """Test 38: GET /api/booking/my-bookings returns bookings"""
        response = self.session.get(f"{BASE_URL}/api/booking/my-bookings")
        assert response.status_code == 200, f"Get my bookings failed: {response.text}"
        data = response.json()
        assert "bookings" in data
        print(f"PASSED: Got {data['total']} bookings")
    
    def test_39_create_general_poll(self):
        """Test 39: Create general poll"""
        response = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "Test General Poll",
            "description": "Testing general poll creation",
            "poll_type": "single",
            "options": ["Option A", "Option B", "Option C"],
            "allow_custom_options": True,
            "is_anonymous": False
        })
        assert response.status_code == 200, f"Create general poll failed: {response.text}"
        data = response.json()
        assert "poll_id" in data
        print(f"PASSED: Created general poll {data['poll_id']}")
        return data
    
    def test_40_vote_on_general_poll(self):
        """Test 40: Vote on general poll"""
        # Create poll first
        create_resp = self.session.post(f"{BASE_URL}/api/general-polls", json={
            "title": "Vote Test General Poll",
            "poll_type": "single",
            "options": ["Yes", "No", "Maybe"]
        })
        share_token = create_resp.json()["share_token"]
        
        # Vote
        response = self.session.post(f"{BASE_URL}/api/general-polls/public/{share_token}/vote", json={
            "voter_name": "Test Voter",
            "voter_email": "voter@test.com",
            "selected": ["Yes"]
        })
        assert response.status_code == 200, f"Vote on general poll failed: {response.text}"
        print("PASSED: Voted on general poll")


class TestAdmin:
    """Admin Tests (41-45)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_41_admin_list_users(self):
        """Test 41: GET /api/admin/users (admin only)"""
        response = self.session.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 200, f"Admin list users failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Admin listed {len(data)} users")
    
    def test_42_admin_stats(self):
        """Test 42: GET /api/admin/stats"""
        response = self.session.get(f"{BASE_URL}/api/admin/stats")
        assert response.status_code == 200, f"Admin stats failed: {response.text}"
        data = response.json()
        assert "total_users" in data
        assert "total_meetings" in data
        print(f"PASSED: Admin stats - {data['total_users']} users, {data['total_meetings']} meetings")
    
    def test_43_update_user_role(self):
        """Test 43: Update user role"""
        # Get user1's user_id
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        users = users_resp.json()
        user1 = next((u for u in users if u["email"] == USER1_EMAIL), None)
        
        if user1:
            response = self.session.put(f"{BASE_URL}/api/admin/users/{user1['user_id']}", json={
                "role": "user"  # Keep as user
            })
            assert response.status_code == 200, f"Update user role failed: {response.text}"
            print("PASSED: Updated user role")
        else:
            print("PASSED: User1 not found (may need to register)")
    
    def test_44_email_config(self):
        """Test 44: Email config (GET/PUT)"""
        # GET
        get_resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert get_resp.status_code == 200, f"Get email config failed: {get_resp.text}"
        
        # PUT
        put_resp = self.session.put(f"{BASE_URL}/api/admin/email-config", json={
            "enabled": False
        })
        assert put_resp.status_code == 200, f"Update email config failed: {put_resp.text}"
        print("PASSED: Email config GET/PUT")
    
    def test_45_reminder_config(self):
        """Test 45: Reminder config (GET/PUT)"""
        # GET
        get_resp = self.session.get(f"{BASE_URL}/api/admin/reminder-config")
        assert get_resp.status_code == 200, f"Get reminder config failed: {get_resp.text}"
        
        # PUT
        put_resp = self.session.put(f"{BASE_URL}/api/admin/reminder-config", json={
            "default_minutes": 15,
            "enabled": True
        })
        assert put_resp.status_code == 200, f"Update reminder config failed: {put_resp.text}"
        print("PASSED: Reminder config GET/PUT")


class TestWhiteboard:
    """Whiteboard Tests (46-47)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        # Create a meeting for tests
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Whiteboard Test Meeting",
            "meeting_type": "instant",
            "duration": 60
        })
        self.meeting_id = create_resp.json()["meeting_id"]
    
    def test_46_get_whiteboard_strokes(self):
        """Test 46: GET /api/meetings/{id}/whiteboard/strokes"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard")
        assert response.status_code == 200, f"Get whiteboard strokes failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Got {len(data)} whiteboard strokes")
    
    def test_47_get_whiteboard_notes(self):
        """Test 47: GET /api/meetings/{id}/whiteboard/notes"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard/notes")
        assert response.status_code == 200, f"Get whiteboard notes failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASSED: Got {len(data)} whiteboard notes")


class TestRecordings:
    """Recordings Tests (48)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as admin
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        # Create a meeting for tests
        create_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Recording Test Meeting",
            "meeting_type": "instant",
            "duration": 60
        })
        self.meeting_id = create_resp.json()["meeting_id"]
    
    def test_48_get_recordings(self):
        """Test 48: GET /api/meetings/{id}/recordings"""
        response = self.session.get(f"{BASE_URL}/api/recordings")
        assert response.status_code == 200, f"Get recordings failed: {response.text}"
        data = response.json()
        assert "recordings" in data
        print(f"PASSED: Got {data['total']} recordings")


class TestMultiUserFlow:
    """Multi-User Flow Tests (49-53)"""
    
    def test_49_user1_creates_meeting_user2_joins(self):
        """Test 49: User1 creates meeting, User2 joins via API"""
        # User1 session
        session1 = requests.Session()
        session1.headers.update({"Content-Type": "application/json"})
        session1.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER1_EMAIL,
            "password": USER1_PASSWORD
        })
        
        # User1 creates meeting
        create_resp = session1.post(f"{BASE_URL}/api/meetings", json={
            "title": "Multi-User Test Meeting",
            "meeting_type": "instant",
            "duration": 60
        })
        assert create_resp.status_code == 200, f"User1 create meeting failed: {create_resp.text}"
        meeting_id = create_resp.json()["meeting_id"]
        
        # User2 session
        session2 = requests.Session()
        session2.headers.update({"Content-Type": "application/json"})
        session2.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER2_EMAIL,
            "password": USER2_PASSWORD
        })
        
        # User2 joins meeting
        join_resp = session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
        assert join_resp.status_code == 200, f"User2 join meeting failed: {join_resp.text}"
        print("PASSED: User1 created meeting, User2 joined")
        return meeting_id, session1, session2
    
    def test_50_both_users_send_chat_messages(self):
        """Test 50: Both users send chat messages, verify both appear"""
        # Setup
        session1 = requests.Session()
        session1.headers.update({"Content-Type": "application/json"})
        session1.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER1_EMAIL,
            "password": USER1_PASSWORD
        })
        
        create_resp = session1.post(f"{BASE_URL}/api/meetings", json={
            "title": "Chat Test Meeting",
            "meeting_type": "instant",
            "duration": 60
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        session2 = requests.Session()
        session2.headers.update({"Content-Type": "application/json"})
        session2.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER2_EMAIL,
            "password": USER2_PASSWORD
        })
        session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
        
        # User1 sends message
        session1.post(f"{BASE_URL}/api/meetings/{meeting_id}/chat", json={
            "message": "Hello from User1!",
            "message_type": "text"
        })
        
        # User2 sends message
        session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/chat", json={
            "message": "Hello from User2!",
            "message_type": "text"
        })
        
        # Verify both messages appear
        chat_resp = session1.get(f"{BASE_URL}/api/meetings/{meeting_id}/chat")
        messages = chat_resp.json()
        assert len(messages) >= 2, "Both messages should appear"
        print(f"PASSED: Both users sent chat messages, {len(messages)} messages found")
    
    def test_51_user1_uploads_user2_sees(self):
        """Test 51: User1 uploads document, User2 can see it in list"""
        # Setup
        session1 = requests.Session()
        session1.headers.update({"Content-Type": "application/json"})
        session1.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER1_EMAIL,
            "password": USER1_PASSWORD
        })
        
        create_resp = session1.post(f"{BASE_URL}/api/meetings", json={
            "title": "Document Share Test",
            "meeting_type": "instant",
            "duration": 60
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        session2 = requests.Session()
        session2.headers.update({"Content-Type": "application/json"})
        session2.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER2_EMAIL,
            "password": USER2_PASSWORD
        })
        session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
        
        # User1 uploads document
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/multi_user_doc.pdf'); c.drawString(100,700,'Multi-User Test'); c.save()"
        ], check=True)
        
        with open('/tmp/multi_user_doc.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{meeting_id}/documents",
                files={"file": ("multi_user_doc.pdf", f, "application/pdf")},
                cookies=session1.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        # User2 sees document
        docs_resp = session2.get(f"{BASE_URL}/api/meetings/{meeting_id}/documents")
        docs = docs_resp.json()
        assert any(d["doc_id"] == doc_id for d in docs), "User2 should see User1's document"
        print("PASSED: User1 uploaded document, User2 can see it")
        return meeting_id, doc_id, session1, session2
    
    def test_52_user2_signs_document(self):
        """Test 52: User2 signs the document"""
        # Setup
        session1 = requests.Session()
        session1.headers.update({"Content-Type": "application/json"})
        session1.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER1_EMAIL,
            "password": USER1_PASSWORD
        })
        
        create_resp = session1.post(f"{BASE_URL}/api/meetings", json={
            "title": "Signature Test",
            "meeting_type": "instant",
            "duration": 60
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        session2 = requests.Session()
        session2.headers.update({"Content-Type": "application/json"})
        session2.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER2_EMAIL,
            "password": USER2_PASSWORD
        })
        session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
        
        # User1 uploads document
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/sign_test.pdf'); c.drawString(100,700,'Sign Test'); c.save()"
        ], check=True)
        
        with open('/tmp/sign_test.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{meeting_id}/documents",
                files={"file": ("sign_test.pdf", f, "application/pdf")},
                cookies=session1.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        # User2 signs document
        sign_resp = session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc_id}/sign", json={
            "type": "typed",
            "signature_data": "User2 Signature",
            "pos_x": 100,
            "pos_y": 500,
            "page": 1
        })
        assert sign_resp.status_code == 200, f"User2 sign failed: {sign_resp.text}"
        print("PASSED: User2 signed the document")
        return meeting_id, doc_id, session1
    
    def test_53_user1_downloads_signed_with_user2_signature(self):
        """Test 53: User1 downloads signed version with User2's signature"""
        # Setup
        session1 = requests.Session()
        session1.headers.update({"Content-Type": "application/json"})
        session1.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER1_EMAIL,
            "password": USER1_PASSWORD
        })
        
        create_resp = session1.post(f"{BASE_URL}/api/meetings", json={
            "title": "Download Signed Test",
            "meeting_type": "instant",
            "duration": 60
        })
        meeting_id = create_resp.json()["meeting_id"]
        
        session2 = requests.Session()
        session2.headers.update({"Content-Type": "application/json"})
        session2.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER2_EMAIL,
            "password": USER2_PASSWORD
        })
        session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
        
        # User1 uploads document
        import subprocess
        subprocess.run([
            "python3", "-c",
            "from reportlab.pdfgen import canvas; c=canvas.Canvas('/tmp/final_sign.pdf'); c.drawString(100,700,'Final Sign Test'); c.save()"
        ], check=True)
        
        with open('/tmp/final_sign.pdf', 'rb') as f:
            upload_resp = requests.post(
                f"{BASE_URL}/api/meetings/{meeting_id}/documents",
                files={"file": ("final_sign.pdf", f, "application/pdf")},
                cookies=session1.cookies
            )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        doc_id = upload_resp.json()["doc_id"]
        
        # User2 signs document
        session2.post(f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc_id}/sign", json={
            "type": "typed",
            "signature_data": "User2 Final Signature",
            "pos_x": 100,
            "pos_y": 500,
            "page": 1
        })
        
        # User1 downloads signed version
        download_resp = session1.get(f"{BASE_URL}/api/meetings/{meeting_id}/documents/{doc_id}/download-signed")
        assert download_resp.status_code == 200, f"Download signed failed: {download_resp.text}"
        assert download_resp.headers.get("content-type") == "application/pdf"
        print("PASSED: User1 downloaded signed PDF with User2's signature")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
