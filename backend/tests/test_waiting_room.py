"""
Waiting Room (Warteraum/Lobby) Feature Tests
Tests for:
- POST /api/meetings/{meeting_id}/join-lobby
- GET /api/meetings/{meeting_id}/lobby-status
- GET /api/meetings/{meeting_id}/lobby
- POST /api/meetings/{meeting_id}/lobby/{user_id}
- POST /api/meetings/{meeting_id}/host-control with toggle_lobby
- Meeting creation with lobby_enabled:true
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"

@pytest.fixture(scope="module")
def session():
    """Create a requests session"""
    return requests.Session()

@pytest.fixture(scope="module")
def admin_auth(session):
    """Login as admin and return session with cookies"""
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return session

@pytest.fixture(scope="module")
def test_user_session():
    """Create and login a test user for lobby testing"""
    test_session = requests.Session()
    test_email = f"TEST_lobbyuser_{uuid.uuid4().hex[:6]}@test.com"
    test_password = "testpass123"
    
    # Register test user
    reg_response = test_session.post(f"{BASE_URL}/api/auth/register", json={
        "email": test_email,
        "password": test_password,
        "name": "Test Lobby User"
    })
    if reg_response.status_code != 200:
        # User might exist, try login
        login_response = test_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": test_password
        })
        assert login_response.status_code == 200, f"Test user login failed: {login_response.text}"
    
    return test_session, test_email

@pytest.fixture(scope="module")
def meeting_with_lobby(admin_auth):
    """Create a meeting with lobby_enabled=true"""
    response = admin_auth.post(f"{BASE_URL}/api/meetings", json={
        "title": f"TEST_Lobby_Meeting_{uuid.uuid4().hex[:6]}",
        "description": "Meeting with lobby enabled for testing",
        "meeting_type": "instant",
        "duration": 60,
        "lobby_enabled": True,
        "guest_access": True
    })
    assert response.status_code == 200, f"Meeting creation failed: {response.text}"
    meeting = response.json()
    assert meeting.get("lobby_enabled") == True, "lobby_enabled should be True"
    return meeting

@pytest.fixture(scope="module")
def meeting_without_lobby(admin_auth):
    """Create a meeting with lobby_enabled=false"""
    response = admin_auth.post(f"{BASE_URL}/api/meetings", json={
        "title": f"TEST_NoLobby_Meeting_{uuid.uuid4().hex[:6]}",
        "description": "Meeting without lobby for testing",
        "meeting_type": "instant",
        "duration": 60,
        "lobby_enabled": False,
        "guest_access": True
    })
    assert response.status_code == 200, f"Meeting creation failed: {response.text}"
    meeting = response.json()
    assert meeting.get("lobby_enabled") == False, "lobby_enabled should be False"
    return meeting


class TestMeetingCreationWithLobby:
    """Test meeting creation with lobby_enabled flag"""
    
    def test_create_meeting_with_lobby_enabled(self, admin_auth):
        """Meeting creation with lobby_enabled:true stores the flag"""
        response = admin_auth.post(f"{BASE_URL}/api/meetings", json={
            "title": f"TEST_LobbyCreate_{uuid.uuid4().hex[:6]}",
            "description": "Test lobby creation",
            "meeting_type": "instant",
            "duration": 30,
            "lobby_enabled": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("lobby_enabled") == True
        assert "meeting_id" in data
        print(f"✓ Meeting created with lobby_enabled=True: {data['meeting_id']}")
    
    def test_create_meeting_with_lobby_disabled(self, admin_auth):
        """Meeting creation with lobby_enabled:false stores the flag"""
        response = admin_auth.post(f"{BASE_URL}/api/meetings", json={
            "title": f"TEST_NoLobbyCreate_{uuid.uuid4().hex[:6]}",
            "description": "Test no lobby creation",
            "meeting_type": "instant",
            "duration": 30,
            "lobby_enabled": False
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("lobby_enabled") == False
        print(f"✓ Meeting created with lobby_enabled=False: {data['meeting_id']}")


class TestJoinLobbyEndpoint:
    """Test POST /api/meetings/{meeting_id}/join-lobby"""
    
    def test_join_lobby_when_disabled_returns_direct_join(self, admin_auth, meeting_without_lobby):
        """When lobby is disabled, returns lobby:false + direct_join"""
        meeting_id = meeting_without_lobby["meeting_id"]
        response = admin_auth.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        assert response.status_code == 200
        data = response.json()
        assert data.get("lobby") == False
        assert data.get("status") == "direct_join"
        print("✓ join-lobby returns direct_join when lobby disabled")
    
    def test_join_lobby_host_bypass(self, admin_auth, meeting_with_lobby):
        """Host bypasses lobby even when enabled"""
        meeting_id = meeting_with_lobby["meeting_id"]
        response = admin_auth.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        assert response.status_code == 200
        data = response.json()
        assert data.get("lobby") == False
        assert data.get("status") == "host_bypass"
        print("✓ Host bypasses lobby with status=host_bypass")
    
    def test_join_lobby_participant_waits(self, test_user_session, meeting_with_lobby):
        """Participant lands in waiting room when lobby enabled"""
        test_session, _ = test_user_session
        meeting_id = meeting_with_lobby["meeting_id"]
        response = test_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        assert response.status_code == 200
        data = response.json()
        assert data.get("lobby") == True
        assert data.get("status") == "waiting"
        print("✓ Participant enters waiting room with status=waiting")
    
    def test_join_lobby_requires_auth(self, meeting_with_lobby):
        """join-lobby requires authentication"""
        meeting_id = meeting_with_lobby["meeting_id"]
        response = requests.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        assert response.status_code == 401
        print("✓ join-lobby requires authentication (401)")


class TestLobbyStatusEndpoint:
    """Test GET /api/meetings/{meeting_id}/lobby-status"""
    
    def test_lobby_status_waiting(self, test_user_session, meeting_with_lobby):
        """Returns lobby_status=waiting for participant in lobby"""
        test_session, _ = test_user_session
        meeting_id = meeting_with_lobby["meeting_id"]
        
        # First join lobby
        test_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        
        # Check status
        response = test_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby-status")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "waiting"
        print("✓ lobby-status returns 'waiting' for participant in lobby")
    
    def test_lobby_status_requires_auth(self, meeting_with_lobby):
        """lobby-status requires authentication"""
        meeting_id = meeting_with_lobby["meeting_id"]
        response = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby-status")
        assert response.status_code == 401
        print("✓ lobby-status requires authentication (401)")


class TestGetLobbyEndpoint:
    """Test GET /api/meetings/{meeting_id}/lobby"""
    
    def test_get_lobby_list(self, admin_auth, meeting_with_lobby, test_user_session):
        """List waiting participants in lobby"""
        test_session, test_email = test_user_session
        meeting_id = meeting_with_lobby["meeting_id"]
        
        # Ensure test user is in lobby
        test_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        
        # Host gets lobby list
        response = admin_auth.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least one waiting participant
        waiting_users = [p for p in data if p.get("lobby_status") == "waiting"]
        assert len(waiting_users) >= 1, "Should have at least one waiting participant"
        print(f"✓ GET /lobby returns list of {len(waiting_users)} waiting participants")
    
    def test_get_lobby_requires_auth(self, meeting_with_lobby):
        """GET /lobby requires authentication"""
        meeting_id = meeting_with_lobby["meeting_id"]
        response = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby")
        assert response.status_code == 401
        print("✓ GET /lobby requires authentication (401)")


class TestLobbyActionEndpoint:
    """Test POST /api/meetings/{meeting_id}/lobby/{user_id}"""
    
    def test_approve_participant(self, admin_auth, meeting_with_lobby):
        """Host approves participant - status changes to approved"""
        meeting_id = meeting_with_lobby["meeting_id"]
        
        # Create a new test user for this test
        approve_session = requests.Session()
        approve_email = f"TEST_approve_{uuid.uuid4().hex[:6]}@test.com"
        reg_resp = approve_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": approve_email,
            "password": "testpass123",
            "name": "Approve Test User"
        })
        assert reg_resp.status_code == 200
        approve_user = reg_resp.json()
        
        # User joins lobby
        join_resp = approve_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        assert join_resp.status_code == 200
        assert join_resp.json().get("status") == "waiting"
        
        # Host approves
        approve_resp = admin_auth.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/lobby/{approve_user['user_id']}",
            json={"action": "approve"}
        )
        assert approve_resp.status_code == 200
        data = approve_resp.json()
        assert data.get("lobby_status") == "approved"
        assert data.get("joined_at") is not None
        print("✓ Host approved participant, status=approved, joined_at set")
        
        # Verify via lobby-status
        status_resp = approve_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby-status")
        assert status_resp.status_code == 200
        assert status_resp.json().get("status") == "approved"
        print("✓ Participant's lobby-status now shows 'approved'")
    
    def test_reject_participant(self, admin_auth, meeting_with_lobby):
        """Host rejects participant - status changes to rejected"""
        meeting_id = meeting_with_lobby["meeting_id"]
        
        # Create a new test user for this test
        reject_session = requests.Session()
        reject_email = f"TEST_reject_{uuid.uuid4().hex[:6]}@test.com"
        reg_resp = reject_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": reject_email,
            "password": "testpass123",
            "name": "Reject Test User"
        })
        assert reg_resp.status_code == 200
        reject_user = reg_resp.json()
        
        # User joins lobby
        join_resp = reject_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        assert join_resp.status_code == 200
        
        # Host rejects
        reject_resp = admin_auth.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/lobby/{reject_user['user_id']}",
            json={"action": "reject"}
        )
        assert reject_resp.status_code == 200
        data = reject_resp.json()
        assert data.get("lobby_status") == "rejected"
        print("✓ Host rejected participant, status=rejected")
        
        # Verify via lobby-status
        status_resp = reject_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby-status")
        assert status_resp.status_code == 200
        assert status_resp.json().get("status") == "rejected"
        print("✓ Participant's lobby-status now shows 'rejected'")
    
    def test_lobby_action_requires_host(self, test_user_session, meeting_with_lobby):
        """Only host/co-host can approve/reject"""
        test_session, _ = test_user_session
        meeting_id = meeting_with_lobby["meeting_id"]
        
        # Try to approve as non-host
        response = test_session.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/lobby/some_user_id",
            json={"action": "approve"}
        )
        assert response.status_code == 403
        print("✓ Non-host cannot approve/reject (403)")


class TestToggleLobbyHostControl:
    """Test POST /api/meetings/{meeting_id}/host-control with toggle_lobby"""
    
    def test_toggle_lobby_on(self, admin_auth):
        """Toggle lobby on via host-control"""
        # Create meeting with lobby off
        create_resp = admin_auth.post(f"{BASE_URL}/api/meetings", json={
            "title": f"TEST_ToggleLobby_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant",
            "duration": 30,
            "lobby_enabled": False
        })
        assert create_resp.status_code == 200
        meeting = create_resp.json()
        meeting_id = meeting["meeting_id"]
        assert meeting.get("lobby_enabled") == False
        
        # Toggle lobby on
        toggle_resp = admin_auth.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/host-control",
            json={"action": "toggle_lobby"}
        )
        assert toggle_resp.status_code == 200
        data = toggle_resp.json()
        assert data.get("action") == "toggle_lobby"
        assert data.get("status") == "toggled"
        assert data.get("value") == True
        print("✓ toggle_lobby turned lobby ON")
        
        # Verify meeting has lobby_enabled=True
        get_resp = admin_auth.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 200
        assert get_resp.json().get("lobby_enabled") == True
        print("✓ Meeting now has lobby_enabled=True")
    
    def test_toggle_lobby_off(self, admin_auth, meeting_with_lobby):
        """Toggle lobby off via host-control"""
        meeting_id = meeting_with_lobby["meeting_id"]
        
        # Toggle lobby off
        toggle_resp = admin_auth.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/host-control",
            json={"action": "toggle_lobby"}
        )
        assert toggle_resp.status_code == 200
        data = toggle_resp.json()
        assert data.get("action") == "toggle_lobby"
        assert data.get("status") == "toggled"
        # Value should be False (toggled from True)
        assert data.get("value") == False
        print("✓ toggle_lobby turned lobby OFF")
    
    def test_toggle_lobby_requires_host(self, test_user_session, meeting_with_lobby):
        """Only host can toggle lobby"""
        test_session, _ = test_user_session
        meeting_id = meeting_with_lobby["meeting_id"]
        
        response = test_session.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/host-control",
            json={"action": "toggle_lobby"}
        )
        assert response.status_code == 403
        print("✓ Non-host cannot toggle lobby (403)")


class TestLobbyStatusPolling:
    """Test lobby status polling flow"""
    
    def test_full_lobby_flow(self, admin_auth):
        """Full flow: create meeting -> user joins lobby -> host approves -> user status changes"""
        # Create meeting with lobby
        create_resp = admin_auth.post(f"{BASE_URL}/api/meetings", json={
            "title": f"TEST_FullLobbyFlow_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant",
            "duration": 30,
            "lobby_enabled": True
        })
        assert create_resp.status_code == 200
        meeting = create_resp.json()
        meeting_id = meeting["meeting_id"]
        
        # Create test user
        user_session = requests.Session()
        user_email = f"TEST_fullflow_{uuid.uuid4().hex[:6]}@test.com"
        reg_resp = user_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": user_email,
            "password": "testpass123",
            "name": "Full Flow User"
        })
        assert reg_resp.status_code == 200
        user = reg_resp.json()
        
        # User joins lobby
        join_resp = user_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join-lobby")
        assert join_resp.status_code == 200
        assert join_resp.json().get("lobby") == True
        assert join_resp.json().get("status") == "waiting"
        print("✓ Step 1: User joined lobby, status=waiting")
        
        # User polls status - should be waiting
        status_resp = user_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby-status")
        assert status_resp.status_code == 200
        assert status_resp.json().get("status") == "waiting"
        print("✓ Step 2: User polls status, still waiting")
        
        # Host sees user in lobby
        lobby_resp = admin_auth.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby")
        assert lobby_resp.status_code == 200
        lobby_list = lobby_resp.json()
        user_in_lobby = any(p.get("user_id") == user["user_id"] for p in lobby_list)
        assert user_in_lobby, "User should be in lobby list"
        print("✓ Step 3: Host sees user in lobby list")
        
        # Host approves user
        approve_resp = admin_auth.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/lobby/{user['user_id']}",
            json={"action": "approve"}
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json().get("lobby_status") == "approved"
        print("✓ Step 4: Host approved user")
        
        # User polls status - should be approved
        status_resp2 = user_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/lobby-status")
        assert status_resp2.status_code == 200
        assert status_resp2.json().get("status") == "approved"
        print("✓ Step 5: User polls status, now approved - can join meeting!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
