"""
Test meeting creation with duration_minutes and optional_emails fields.
Tests the recent backend changes for Von-Bis time and optional participants.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMeetingDurationAndOptionalParticipants:
    """Tests for meeting creation with duration_minutes and optional_emails fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookies"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.user = login_response.json()
        yield
        # Cleanup is handled by individual tests
    
    def test_create_meeting_with_duration_minutes(self):
        """Test POST /api/meetings with duration_minutes field - verify duration is stored correctly"""
        payload = {
            "title": "TEST_Duration_Minutes_Meeting",
            "description": "Testing duration_minutes field",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-15T14:00:00Z",
            "duration_minutes": 90,  # 90 minutes (1.5 hours)
            "timezone": "Europe/Berlin"
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert response.status_code == 200, f"Create meeting failed: {response.text}"
        
        data = response.json()
        assert "meeting_id" in data, "Response should contain meeting_id"
        assert data["duration"] == 90, f"Duration should be 90, got {data['duration']}"
        assert data["title"] == "TEST_Duration_Minutes_Meeting"
        
        # Cleanup
        meeting_id = data["meeting_id"]
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print(f"PASS: Meeting created with duration_minutes=90, stored duration={data['duration']}")
    
    def test_create_meeting_without_duration_minutes_fallback(self):
        """Test POST /api/meetings without duration_minutes - should fallback to duration field default (60)"""
        payload = {
            "title": "TEST_Duration_Fallback_Meeting",
            "description": "Testing duration fallback",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-16T10:00:00Z",
            "timezone": "Europe/Berlin"
            # No duration_minutes provided - should use default duration=60
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert response.status_code == 200, f"Create meeting failed: {response.text}"
        
        data = response.json()
        assert data["duration"] == 60, f"Duration should fallback to 60, got {data['duration']}"
        
        # Cleanup
        meeting_id = data["meeting_id"]
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print(f"PASS: Meeting created without duration_minutes, fallback duration={data['duration']}")
    
    def test_create_meeting_with_optional_emails(self):
        """Test POST /api/meetings with optional_emails - verify optional participants have is_optional: true"""
        payload = {
            "title": "TEST_Optional_Participants_Meeting",
            "description": "Testing optional_emails field",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-17T09:00:00Z",
            "duration_minutes": 45,
            "timezone": "Europe/Berlin",
            "optional_emails": ["user1@meetflow.com", "user2@meetflow.com"]
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert response.status_code == 200, f"Create meeting failed: {response.text}"
        
        data = response.json()
        meeting_id = data["meeting_id"]
        
        # Get participants to verify is_optional flag
        participants_response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/participants")
        assert participants_response.status_code == 200, f"Get participants failed: {participants_response.text}"
        
        participants = participants_response.json()
        optional_participants = [p for p in participants if p.get("is_optional") == True]
        
        assert len(optional_participants) == 2, f"Expected 2 optional participants, got {len(optional_participants)}"
        
        optional_emails = [p["email"] for p in optional_participants]
        assert "user1@meetflow.com" in optional_emails, "user1@meetflow.com should be optional"
        assert "user2@meetflow.com" in optional_emails, "user2@meetflow.com should be optional"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print(f"PASS: Optional participants created with is_optional=True: {optional_emails}")
    
    def test_create_meeting_with_invited_emails(self):
        """Test POST /api/meetings with invited_emails - verify required participants have is_optional: false"""
        payload = {
            "title": "TEST_Required_Participants_Meeting",
            "description": "Testing invited_emails field",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-18T11:00:00Z",
            "duration_minutes": 60,
            "timezone": "Europe/Berlin",
            "invited_emails": ["user1@meetflow.com", "user3@meetflow.com"]
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert response.status_code == 200, f"Create meeting failed: {response.text}"
        
        data = response.json()
        meeting_id = data["meeting_id"]
        
        # Get participants to verify is_optional flag
        participants_response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/participants")
        assert participants_response.status_code == 200, f"Get participants failed: {participants_response.text}"
        
        participants = participants_response.json()
        
        # Filter out host (admin) and check invited participants
        invited_participants = [p for p in participants if p.get("role") == "participant"]
        
        for p in invited_participants:
            assert p.get("is_optional") == False, f"Invited participant {p['email']} should have is_optional=False, got {p.get('is_optional')}"
        
        assert len(invited_participants) == 2, f"Expected 2 invited participants, got {len(invited_participants)}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print("PASS: Required participants created with is_optional=False")
    
    def test_create_meeting_with_both_required_and_optional(self):
        """Test POST /api/meetings with both invited_emails and optional_emails"""
        payload = {
            "title": "TEST_Mixed_Participants_Meeting",
            "description": "Testing both required and optional participants",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-19T14:30:00Z",
            "duration_minutes": 75,
            "timezone": "Europe/Berlin",
            "invited_emails": ["user1@meetflow.com"],
            "optional_emails": ["user2@meetflow.com", "user3@meetflow.com"]
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert response.status_code == 200, f"Create meeting failed: {response.text}"
        
        data = response.json()
        meeting_id = data["meeting_id"]
        
        # Verify duration
        assert data["duration"] == 75, f"Duration should be 75, got {data['duration']}"
        
        # Get participants
        participants_response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/participants")
        assert participants_response.status_code == 200
        
        participants = participants_response.json()
        
        # Check required participant
        user1 = next((p for p in participants if p["email"] == "user1@meetflow.com"), None)
        assert user1 is not None, "user1@meetflow.com should be in participants"
        assert user1.get("is_optional") == False, f"user1 should be required (is_optional=False), got {user1.get('is_optional')}"
        
        # Check optional participants
        user2 = next((p for p in participants if p["email"] == "user2@meetflow.com"), None)
        user3 = next((p for p in participants if p["email"] == "user3@meetflow.com"), None)
        
        assert user2 is not None, "user2@meetflow.com should be in participants"
        assert user3 is not None, "user3@meetflow.com should be in participants"
        assert user2.get("is_optional") == True, f"user2 should be optional (is_optional=True), got {user2.get('is_optional')}"
        assert user3.get("is_optional") == True, f"user3 should be optional (is_optional=True), got {user3.get('is_optional')}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print("PASS: Mixed participants - 1 required, 2 optional - all with correct is_optional flags")
    
    def test_get_participants_endpoint(self):
        """Test GET /api/meetings/{meeting_id}/participants - verify both required and optional with correct is_optional flag"""
        # Create meeting with mixed participants
        payload = {
            "title": "TEST_Participants_Endpoint_Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": "2026-02-20T16:00:00Z",
            "duration_minutes": 30,
            "invited_emails": ["user1@meetflow.com"],
            "optional_emails": ["user2@meetflow.com"]
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/meetings", json=payload)
        assert create_response.status_code == 200
        meeting_id = create_response.json()["meeting_id"]
        
        # Test GET participants endpoint
        response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/participants")
        assert response.status_code == 200, f"Get participants failed: {response.text}"
        
        participants = response.json()
        assert isinstance(participants, list), "Response should be a list"
        
        # Should have host + 1 required + 1 optional = 3 participants
        assert len(participants) == 3, f"Expected 3 participants (host + 1 required + 1 optional), got {len(participants)}"
        
        # Verify structure
        for p in participants:
            assert "email" in p, "Participant should have email"
            assert "name" in p, "Participant should have name"
            assert "role" in p, "Participant should have role"
        
        # Verify is_optional flags
        required = [p for p in participants if p.get("is_optional") == False and p.get("role") == "participant"]
        optional = [p for p in participants if p.get("is_optional") == True]
        
        assert len(required) == 1, f"Expected 1 required participant, got {len(required)}"
        assert len(optional) == 1, f"Expected 1 optional participant, got {len(optional)}"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        print(f"PASS: GET /api/meetings/{meeting_id}/participants returns correct is_optional flags")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
