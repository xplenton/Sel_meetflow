"""
Breakout Rooms Feature Tests
Tests CRUD operations, auto-assign, start/end session, broadcast, and close-all endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBreakoutRoomsCRUD:
    """Test breakout room CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookie"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        
        # Create a test meeting for breakout room tests
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Breakout_Meeting",
            "meeting_type": "instant"
        })
        assert meeting_resp.status_code == 200, f"Failed to create meeting: {meeting_resp.text}"
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting["meeting_id"]
        print(f"Created test meeting: {self.meeting_id}")
        
        yield
        
        # Cleanup: Delete test meeting's breakout rooms
        try:
            rooms = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms").json()
            for room in rooms:
                self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/{room['room_id']}")
        except:
            pass
    
    def test_create_breakout_room(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms - Create a new breakout room"""
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "TEST_Room_Alpha",
            "participant_ids": []
        })
        assert response.status_code == 200, f"Create room failed: {response.text}"
        
        data = response.json()
        assert "room_id" in data
        assert data["name"] == "TEST_Room_Alpha"
        assert data["status"] == "open"
        assert data["meeting_id"] == self.meeting_id
        assert "created_at" in data
        print(f"Created breakout room: {data['room_id']}")
    
    def test_list_breakout_rooms(self):
        """GET /api/meetings/{meeting_id}/breakout-rooms - List breakout rooms"""
        # Create a room first
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "TEST_Room_Beta",
            "participant_ids": []
        })
        
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms")
        assert response.status_code == 200, f"List rooms failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        room_names = [r["name"] for r in data]
        assert "TEST_Room_Beta" in room_names
        print(f"Listed {len(data)} breakout rooms")
    
    def test_update_breakout_room(self):
        """PUT /api/meetings/{meeting_id}/breakout-rooms/{room_id} - Update room"""
        # Create a room first
        create_resp = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "TEST_Room_Gamma",
            "participant_ids": []
        })
        room_id = create_resp.json()["room_id"]
        
        # Update the room
        update_resp = self.session.put(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/{room_id}", json={
            "name": "TEST_Room_Gamma_Updated",
            "status": "closed"
        })
        assert update_resp.status_code == 200, f"Update room failed: {update_resp.text}"
        
        data = update_resp.json()
        assert data["name"] == "TEST_Room_Gamma_Updated"
        assert data["status"] == "closed"
        print(f"Updated breakout room: {room_id}")
    
    def test_delete_breakout_room(self):
        """DELETE /api/meetings/{meeting_id}/breakout-rooms/{room_id} - Delete a room"""
        # Create a room first
        create_resp = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "TEST_Room_Delta",
            "participant_ids": []
        })
        room_id = create_resp.json()["room_id"]
        
        # Delete the room
        delete_resp = self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/{room_id}")
        assert delete_resp.status_code == 200, f"Delete room failed: {delete_resp.text}"
        
        # Verify deletion
        rooms = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms").json()
        room_ids = [r["room_id"] for r in rooms]
        assert room_id not in room_ids
        print(f"Deleted breakout room: {room_id}")
    
    def test_create_room_requires_auth(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms - Requires authentication"""
        unauth_session = requests.Session()
        response = unauth_session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Unauthorized Room",
            "participant_ids": []
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Create room correctly requires authentication")


class TestBreakoutRoomsAutoAssign:
    """Test auto-assign functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookie"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        # Create a test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_AutoAssign_Meeting",
            "meeting_type": "instant"
        })
        assert meeting_resp.status_code == 200
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting["meeting_id"]
        
        yield
        
        # Cleanup
        try:
            rooms = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms").json()
            for room in rooms:
                self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/{room['room_id']}")
        except:
            pass
    
    def test_auto_assign_creates_rooms(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms/auto-assign - Creates rooms if needed"""
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/auto-assign", json={
            "room_count": 3
        })
        assert response.status_code == 200, f"Auto-assign failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        print(f"Auto-assign created {len(data)} rooms")
    
    def test_auto_assign_uses_existing_rooms(self):
        """Auto-assign uses existing rooms if count is met"""
        # Create 2 rooms manually
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Existing Room 1", "participant_ids": []
        })
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Existing Room 2", "participant_ids": []
        })
        
        # Auto-assign with room_count=2 should not create new rooms
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/auto-assign", json={
            "room_count": 2
        })
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 2
        room_names = [r["name"] for r in data]
        assert "Existing Room 1" in room_names
        assert "Existing Room 2" in room_names
        print("Auto-assign correctly uses existing rooms")


class TestBreakoutRoomsSession:
    """Test start/end breakout session"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookie"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        
        # Create a test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Session_Meeting",
            "meeting_type": "instant"
        })
        assert meeting_resp.status_code == 200
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting["meeting_id"]
        
        yield
        
        # Cleanup
        try:
            self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/end")
            rooms = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms").json()
            for room in rooms:
                self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/{room['room_id']}")
        except:
            pass
    
    def test_start_returns_400_if_no_open_rooms(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms/start - Returns 400 if no open rooms"""
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/start", json={
            "duration": 600
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data
        assert "no open" in data["detail"].lower()
        print("Start correctly returns 400 when no open rooms exist")
    
    def test_start_breakout_session(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms/start - Start breakout session"""
        # Create a room first
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Session Test Room", "participant_ids": []
        })
        
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/start", json={
            "duration": 300
        })
        assert response.status_code == 200, f"Start session failed: {response.text}"
        
        data = response.json()
        assert data["started"] == True
        assert data["rooms"] >= 1
        assert data["duration"] == 300
        print(f"Started breakout session with {data['rooms']} rooms, duration {data['duration']}s")
    
    def test_end_breakout_session(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms/end - End breakout session"""
        # Create and start a session
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "End Test Room", "participant_ids": []
        })
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/start", json={
            "duration": 600
        })
        
        # End the session
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/end")
        assert response.status_code == 200, f"End session failed: {response.text}"
        
        data = response.json()
        assert data["ended"] == True
        
        # Verify rooms are closed
        rooms = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms").json()
        for room in rooms:
            assert room["status"] == "closed"
        print("Ended breakout session, all rooms closed")


class TestBreakoutRoomsBroadcast:
    """Test broadcast and close-all functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookie"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        
        # Create a test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Broadcast_Meeting",
            "meeting_type": "instant"
        })
        assert meeting_resp.status_code == 200
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting["meeting_id"]
        
        yield
        
        # Cleanup
        try:
            rooms = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms").json()
            for room in rooms:
                self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/{room['room_id']}")
        except:
            pass
    
    def test_broadcast_message(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms/broadcast - Send message to all rooms"""
        # Create open rooms
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Broadcast Room 1", "participant_ids": []
        })
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Broadcast Room 2", "participant_ids": []
        })
        
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/broadcast", json={
            "message": "TEST_Broadcast: Please return to main room in 5 minutes"
        })
        assert response.status_code == 200, f"Broadcast failed: {response.text}"
        
        data = response.json()
        assert data["broadcast"] == True
        assert data["rooms"] == 2
        print(f"Broadcast sent to {data['rooms']} rooms")
    
    def test_close_all_rooms(self):
        """POST /api/meetings/{meeting_id}/breakout-rooms/close-all - Close all rooms"""
        # Create open rooms
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Close All Room 1", "participant_ids": []
        })
        self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms", json={
            "name": "Close All Room 2", "participant_ids": []
        })
        
        response = self.session.post(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms/close-all")
        assert response.status_code == 200, f"Close-all failed: {response.text}"
        
        data = response.json()
        assert data["status"] == "all_closed"
        
        # Verify all rooms are closed
        rooms = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms").json()
        for room in rooms:
            assert room["status"] == "closed"
        print("All rooms closed successfully")


class TestBreakoutRoomsExistingMeeting:
    """Test with existing meeting from previous tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and use existing meeting"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.meeting_id = "meet_044aab394f"  # Existing test meeting
        
        yield
    
    def test_list_existing_meeting_rooms(self):
        """List breakout rooms for existing test meeting"""
        response = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/breakout-rooms")
        assert response.status_code == 200, f"List rooms failed: {response.text}"
        
        data = response.json()
        print(f"Existing meeting has {len(data)} breakout rooms")
        for room in data:
            print(f"  - {room['name']} (status: {room['status']}, participants: {len(room.get('participant_ids', []))})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
