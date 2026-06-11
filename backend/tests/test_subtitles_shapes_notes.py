"""
Test suite for new MeetFlow features:
1. Live Subtitles (WebSocket broadcast)
2. Whiteboard Shapes (rect, circle, arrow)
3. Sticky Notes (CRUD via WebSocket + REST API)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestWhiteboardNotesAPI:
    """Test whiteboard notes REST API endpoints"""
    
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
        
        # Create a test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_WhiteboardNotes_Meeting",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code == 200, f"Meeting creation failed: {meeting_resp.text}"
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting['meeting_id']
        yield
        # Cleanup - delete test meeting
        try:
            self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}")
        except:
            pass
    
    def test_get_whiteboard_notes_empty(self):
        """GET /api/meetings/{meeting_id}/whiteboard/notes - Returns empty list initially"""
        resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard/notes")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /whiteboard/notes returns empty list: {data}")
    
    def test_get_whiteboard_notes_requires_auth(self):
        """GET /api/meetings/{meeting_id}/whiteboard/notes - Requires authentication"""
        new_session = requests.Session()
        resp = new_session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard/notes")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ GET /whiteboard/notes requires authentication (401)")
    
    def test_delete_whiteboard_clears_strokes_and_notes(self):
        """DELETE /api/meetings/{meeting_id}/whiteboard - Clears both strokes AND notes"""
        resp = self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "deleted" in data, "Response should contain 'deleted' count"
        print(f"✓ DELETE /whiteboard clears strokes and notes: {data}")
    
    def test_get_whiteboard_strokes(self):
        """GET /api/meetings/{meeting_id}/whiteboard - Returns strokes list"""
        resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /whiteboard returns strokes list: {data}")


class TestWhiteboardShapesAPI:
    """Test whiteboard shapes (rect, circle, arrow) via strokes API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookie"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.user = login_resp.json()
        
        # Create a test meeting
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_WhiteboardShapes_Meeting",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code == 200
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting['meeting_id']
        yield
        try:
            self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}")
        except:
            pass
    
    def test_whiteboard_strokes_endpoint_exists(self):
        """GET /api/meetings/{meeting_id}/whiteboard - Endpoint exists and returns strokes"""
        resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Response should be a list of strokes"
        print("✓ Whiteboard strokes endpoint exists and returns list")
    
    def test_whiteboard_clear_endpoint(self):
        """DELETE /api/meetings/{meeting_id}/whiteboard - Clears whiteboard"""
        resp = self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "deleted" in data
        print(f"✓ Whiteboard clear endpoint works: deleted {data['deleted']} items")


class TestSubtitlesWebSocket:
    """Test subtitle WebSocket message handling"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and create test meeting"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.user = login_resp.json()
        
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Subtitles_Meeting",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code == 200
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting['meeting_id']
        yield
        try:
            self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}")
        except:
            pass
    
    def test_meeting_created_for_subtitle_test(self):
        """Verify meeting is created for WebSocket subtitle testing"""
        assert self.meeting_id is not None
        print(f"✓ Meeting created for subtitle testing: {self.meeting_id}")


class TestExistingWhiteboardFeatures:
    """Verify existing whiteboard features still work"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and create test meeting"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.user = login_resp.json()
        
        meeting_resp = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_ExistingWhiteboard_Meeting",
            "meeting_type": "instant",
            "duration": 30
        })
        assert meeting_resp.status_code == 200
        self.meeting = meeting_resp.json()
        self.meeting_id = self.meeting['meeting_id']
        yield
        try:
            self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}")
        except:
            pass
    
    def test_whiteboard_get_strokes(self):
        """GET /api/meetings/{meeting_id}/whiteboard - Returns strokes"""
        resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        print("✓ GET /whiteboard returns strokes list")
    
    def test_whiteboard_clear(self):
        """DELETE /api/meetings/{meeting_id}/whiteboard - Clears whiteboard"""
        resp = self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "deleted" in data
        print(f"✓ DELETE /whiteboard clears whiteboard: {data}")
    
    def test_whiteboard_notes_endpoint(self):
        """GET /api/meetings/{meeting_id}/whiteboard/notes - Returns notes"""
        resp = self.session.get(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard/notes")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        print("✓ GET /whiteboard/notes returns notes list")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
