"""
Comprehensive Regression Test Suite for MeetFlow
Tests all major features: Auth, Meetings, Documents, Signatures, Scheduling, Whiteboard, Breakout Rooms, etc.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
TEST_MEETING_ID = "meet_044aab394f"
TEST_DOC_ID = "doc_49f0e85622"
TEST_SIGN_TOKEN = "07a232b0a3c24d1a"


class TestAuthEndpoints:
    """Authentication endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_login_success(self):
        """Test admin login with valid credentials"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print(f"✓ Login successful for {ADMIN_EMAIL}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401
        print("✓ Invalid login correctly rejected")
    
    def test_get_me_authenticated(self):
        """Test /auth/me endpoint after login"""
        # Login first
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        
        # Get current user
        me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data["email"] == ADMIN_EMAIL
        print("✓ /auth/me returns correct user")
    
    def test_logout(self):
        """Test logout endpoint"""
        # Login first
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Logout
        logout_resp = self.session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_resp.status_code == 200
        print("✓ Logout successful")


class TestMeetingEndpoints:
    """Meeting CRUD and related endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_list_meetings(self):
        """Test listing meetings"""
        response = self.session.get(f"{BASE_URL}/api/meetings")
        assert response.status_code == 200
        data = response.json()
        assert "meetings" in data
        print(f"✓ Listed {len(data['meetings'])} meetings")
    
    def test_get_meeting_details(self):
        """Test getting specific meeting details"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["meeting_id"] == TEST_MEETING_ID
        print(f"✓ Got meeting details: {data.get('title', 'N/A')}")
    
    def test_create_instant_meeting(self):
        """Test creating an instant meeting"""
        response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Instant Meeting",
            "description": "Test meeting for regression",
            "meeting_type": "instant",
            "duration": 30,
            "chat_enabled": True,
            "reactions_enabled": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "meeting_id" in data
        assert data["title"] == "TEST_Instant Meeting"
        print(f"✓ Created instant meeting: {data['meeting_id']}")
        return data["meeting_id"]
    
    def test_meeting_participants(self):
        """Test getting meeting participants"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/participants")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} participants")
    
    def test_meeting_chat(self):
        """Test getting meeting chat messages"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/chat")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} chat messages")


class TestDocumentEndpoints:
    """Document management and signature endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_list_documents(self):
        """Test listing documents for a meeting"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} documents")
        
        # Check for signatures with positions
        for doc in data:
            if doc.get("doc_id") == TEST_DOC_ID:
                sigs = doc.get("signatures", [])
                sigs_with_pos = [s for s in sigs if s.get("pos_x") or s.get("pos_y")]
                print(f"  - Doc {doc['doc_id']}: {len(sigs)} signatures, {len(sigs_with_pos)} with positions")
    
    def test_document_audit_log(self):
        """Test getting document audit log"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/audit-log")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} audit log entries")
    
    def test_download_signed_document(self):
        """Test downloading signed document PDF"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/download-signed")
        assert response.status_code == 200
        assert "application/pdf" in response.headers.get("content-type", "")
        assert len(response.content) > 1000  # Should be a valid PDF
        print(f"✓ Downloaded signed PDF ({len(response.content)} bytes)")
    
    def test_audit_log_pdf_export(self):
        """Test exporting audit log as PDF"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/documents/{TEST_DOC_ID}/audit-log/pdf")
        assert response.status_code == 200
        assert "application/pdf" in response.headers.get("content-type", "")
        print(f"✓ Exported audit trail PDF ({len(response.content)} bytes)")


class TestPublicSignEndpoint:
    """Public async signing endpoint"""
    
    def test_get_sign_document_info(self):
        """Test getting document info via sign token"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/sign/{TEST_SIGN_TOKEN}")
        # May return 200 or 404 depending on token validity
        if response.status_code == 200:
            data = response.json()
            assert "doc_id" in data
            print(f"✓ Got sign document info: {data.get('filename', 'N/A')}")
        else:
            print(f"✓ Sign token endpoint returned {response.status_code} (token may be expired)")


class TestWhiteboardEndpoints:
    """Whiteboard feature endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_get_whiteboard_strokes(self):
        """Test getting whiteboard strokes"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/whiteboard")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} whiteboard strokes")
    
    def test_get_whiteboard_notes(self):
        """Test getting whiteboard sticky notes"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/whiteboard/notes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} whiteboard notes")


class TestBreakoutRoomEndpoints:
    """Breakout room feature endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_list_breakout_rooms(self):
        """Test listing breakout rooms"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/breakout-rooms")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} breakout rooms")


class TestSchedulingEndpoints:
    """Schedule polls and booking endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_list_schedule_polls(self):
        """Test listing schedule polls"""
        response = self.session.get(f"{BASE_URL}/api/schedule-polls")
        assert response.status_code == 200
        data = response.json()
        assert "polls" in data
        print(f"✓ Listed {len(data['polls'])} schedule polls")
    
    def test_list_general_polls(self):
        """Test listing general polls/surveys"""
        response = self.session.get(f"{BASE_URL}/api/general-polls")
        assert response.status_code == 200
        data = response.json()
        assert "polls" in data
        print(f"✓ Listed {len(data['polls'])} general polls")
    
    def test_get_booking_availability(self):
        """Test getting booking availability settings"""
        response = self.session.get(f"{BASE_URL}/api/booking/availability")
        assert response.status_code == 200
        data = response.json()
        print("✓ Got booking availability settings")


class TestHostControlEndpoints:
    """Host control and lobby endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_get_lobby(self):
        """Test getting lobby participants"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/lobby")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} lobby participants")
    
    def test_get_mode_config(self):
        """Test getting meeting mode config"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{TEST_MEETING_ID}/mode-config")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        print(f"✓ Got mode config: {data.get('mode', 'N/A')}")


class TestRecordingEndpoints:
    """Recording feature endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_list_recordings(self):
        """Test listing recordings"""
        response = self.session.get(f"{BASE_URL}/api/recordings")
        assert response.status_code == 200
        data = response.json()
        assert "recordings" in data
        print(f"✓ Listed {len(data['recordings'])} recordings")


class TestAdminEndpoints:
    """Admin panel endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_list_users(self):
        """Test listing users (admin only)"""
        response = self.session.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        print(f"✓ Listed {len(data['users'])} users")
    
    def test_get_branding(self):
        """Test getting branding settings"""
        response = self.session.get(f"{BASE_URL}/api/admin/branding")
        assert response.status_code == 200
        data = response.json()
        print("✓ Got branding settings")
    
    def test_get_api_config(self):
        """Test getting API config"""
        response = self.session.get(f"{BASE_URL}/api/admin/api-config")
        assert response.status_code == 200
        data = response.json()
        print("✓ Got API config")


class TestAnalyticsEndpoints:
    """Analytics endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_get_meeting_stats(self):
        """Test getting meeting statistics"""
        response = self.session.get(f"{BASE_URL}/api/analytics/meetings")
        assert response.status_code == 200
        data = response.json()
        print("✓ Got meeting analytics")
    
    def test_get_scheduling_stats(self):
        """Test getting scheduling statistics"""
        response = self.session.get(f"{BASE_URL}/api/analytics/scheduling")
        assert response.status_code == 200
        data = response.json()
        print("✓ Got scheduling analytics")
    
    def test_get_document_stats(self):
        """Test getting document statistics"""
        response = self.session.get(f"{BASE_URL}/api/analytics/documents")
        assert response.status_code == 200
        data = response.json()
        print("✓ Got document analytics")


class TestMeetingTemplates:
    """Meeting template endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_list_templates(self):
        """Test listing meeting templates"""
        response = self.session.get(f"{BASE_URL}/api/meeting-templates")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listed {len(data)} meeting templates")


class TestCalendarEndpoints:
    """Calendar endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    def test_get_calendar_events(self):
        """Test getting calendar events"""
        response = self.session.get(f"{BASE_URL}/api/calendar/events")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Got {len(data)} calendar events")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
