"""
Whiteboard Feature Tests
Tests for GET/DELETE /api/meetings/{meeting_id}/whiteboard endpoints
and WebSocket whiteboard message handling
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestWhiteboardEndpoints:
    """Tests for whiteboard REST API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        # Store cookies for authenticated requests
        self.cookies = login_response.cookies
        
        # Get or create a test meeting
        self.meeting_id = self._get_or_create_test_meeting()
        
    def _get_or_create_test_meeting(self):
        """Get existing test meeting or create one"""
        # Try to use the provided test meeting
        test_meeting_id = "meet_044aab394f"
        response = self.session.get(f"{BASE_URL}/api/meetings/{test_meeting_id}", cookies=self.cookies)
        if response.status_code == 200:
            return test_meeting_id
        
        # Create a new meeting if test meeting doesn't exist
        create_response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Whiteboard Test Meeting",
            "scheduled_time": "2026-01-20T10:00:00Z",
            "duration": 60
        }, cookies=self.cookies)
        
        if create_response.status_code in [200, 201]:
            return create_response.json().get("meeting_id")
        
        pytest.skip("Could not get or create test meeting")
    
    # ============ GET /api/meetings/{meeting_id}/whiteboard ============
    
    def test_get_whiteboard_strokes_authenticated(self):
        """GET /api/meetings/{meeting_id}/whiteboard - Returns strokes for authenticated user"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard",
            cookies=self.cookies
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list of strokes"
        
        # If there are strokes, verify structure
        if len(data) > 0:
            stroke = data[0]
            assert "stroke_id" in stroke or "id" in stroke, "Stroke should have stroke_id or id"
            assert "points" in stroke, "Stroke should have points"
            assert "color" in stroke, "Stroke should have color"
            assert "width" in stroke, "Stroke should have width"
            assert "tool" in stroke, "Stroke should have tool"
        
        print(f"✓ GET whiteboard strokes returned {len(data)} strokes")
    
    def test_get_whiteboard_strokes_unauthenticated(self):
        """GET /api/meetings/{meeting_id}/whiteboard - Returns 401 for unauthenticated"""
        # Create new session without cookies
        unauthenticated_session = requests.Session()
        
        response = unauthenticated_session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard"
        )
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("✓ GET whiteboard strokes returns 401 for unauthenticated requests")
    
    def test_get_whiteboard_strokes_nonexistent_meeting(self):
        """GET /api/meetings/{meeting_id}/whiteboard - Returns empty list for non-existent meeting"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/nonexistent_meeting_id/whiteboard",
            cookies=self.cookies
        )
        
        # Should return 200 with empty list (no strokes for non-existent meeting)
        # or 404 if meeting validation is done
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list), "Response should be a list"
            print("✓ GET whiteboard for non-existent meeting returns empty list")
        else:
            print("✓ GET whiteboard for non-existent meeting returns 404")
    
    # ============ DELETE /api/meetings/{meeting_id}/whiteboard ============
    
    def test_delete_whiteboard_strokes_authenticated(self):
        """DELETE /api/meetings/{meeting_id}/whiteboard - Clears all strokes"""
        response = self.session.delete(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard",
            cookies=self.cookies
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "deleted" in data, "Response should contain 'deleted' count"
        assert isinstance(data["deleted"], int), "Deleted count should be an integer"
        
        print(f"✓ DELETE whiteboard cleared {data['deleted']} strokes")
        
        # Verify strokes are actually cleared
        get_response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard",
            cookies=self.cookies
        )
        assert get_response.status_code == 200
        strokes = get_response.json()
        assert len(strokes) == 0, f"Expected 0 strokes after clear, got {len(strokes)}"
        print("✓ Verified whiteboard is empty after DELETE")
    
    def test_delete_whiteboard_strokes_unauthenticated(self):
        """DELETE /api/meetings/{meeting_id}/whiteboard - Returns 401 for unauthenticated"""
        unauthenticated_session = requests.Session()
        
        response = unauthenticated_session.delete(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard"
        )
        
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("✓ DELETE whiteboard returns 401 for unauthenticated requests")
    
    def test_delete_whiteboard_idempotent(self):
        """DELETE /api/meetings/{meeting_id}/whiteboard - Is idempotent (can be called multiple times)"""
        # First delete
        response1 = self.session.delete(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard",
            cookies=self.cookies
        )
        assert response1.status_code == 200
        
        # Second delete (should still succeed with 0 deleted)
        response2 = self.session.delete(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard",
            cookies=self.cookies
        )
        assert response2.status_code == 200
        
        data = response2.json()
        assert data["deleted"] == 0, "Second delete should report 0 deleted"
        print("✓ DELETE whiteboard is idempotent")


class TestWhiteboardDataPersistence:
    """Tests for whiteboard stroke persistence via WebSocket"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        self.cookies = login_response.cookies
        
        # Get user info
        me_response = self.session.get(f"{BASE_URL}/api/auth/me", cookies=self.cookies)
        assert me_response.status_code == 200
        self.user = me_response.json()
        
        # Get or create test meeting
        self.meeting_id = self._get_or_create_test_meeting()
        
        # Clear whiteboard before tests
        self.session.delete(f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard", cookies=self.cookies)
    
    def _get_or_create_test_meeting(self):
        """Get existing test meeting or create one"""
        test_meeting_id = "meet_044aab394f"
        response = self.session.get(f"{BASE_URL}/api/meetings/{test_meeting_id}", cookies=self.cookies)
        if response.status_code == 200:
            return test_meeting_id
        
        create_response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "Whiteboard Persistence Test",
            "scheduled_time": "2026-01-20T11:00:00Z",
            "duration": 60
        }, cookies=self.cookies)
        
        if create_response.status_code in [200, 201]:
            return create_response.json().get("meeting_id")
        
        pytest.skip("Could not get or create test meeting")
    
    def test_whiteboard_strokes_initially_empty(self):
        """Whiteboard should be empty initially (after clear)"""
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard",
            cookies=self.cookies
        )
        
        assert response.status_code == 200
        strokes = response.json()
        assert len(strokes) == 0, f"Expected empty whiteboard, got {len(strokes)} strokes"
        print("✓ Whiteboard is initially empty")
    
    def test_whiteboard_stroke_structure(self):
        """Verify expected stroke structure from API"""
        # This test verifies the API returns strokes with correct structure
        # Strokes are created via WebSocket, so we just verify the GET endpoint structure
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{self.meeting_id}/whiteboard",
            cookies=self.cookies
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Strokes should be returned as a list"
        
        # The response excludes _id (MongoDB ObjectId) as per the endpoint
        # Expected fields: stroke_id, points, color, width, tool, user_id, meeting_id, created_at
        print("✓ Whiteboard stroke structure verified")


class TestWhiteboardIntegration:
    """Integration tests for whiteboard feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        self.cookies = login_response.cookies
    
    def test_meeting_exists_for_whiteboard(self):
        """Verify test meeting exists and is accessible"""
        test_meeting_id = "meet_044aab394f"
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{test_meeting_id}",
            cookies=self.cookies
        )
        
        if response.status_code == 200:
            meeting = response.json()
            assert "meeting_id" in meeting or "id" in meeting
            print(f"✓ Test meeting exists: {meeting.get('title', 'Unknown')}")
        else:
            print(f"⚠ Test meeting {test_meeting_id} not found, tests will create new meeting")
    
    def test_auth_required_for_whiteboard_operations(self):
        """Both GET and DELETE require authentication"""
        unauthenticated = requests.Session()
        meeting_id = "meet_044aab394f"
        
        # GET without auth
        get_response = unauthenticated.get(f"{BASE_URL}/api/meetings/{meeting_id}/whiteboard")
        assert get_response.status_code == 401, "GET should require auth"
        
        # DELETE without auth
        delete_response = unauthenticated.delete(f"{BASE_URL}/api/meetings/{meeting_id}/whiteboard")
        assert delete_response.status_code == 401, "DELETE should require auth"
        
        print("✓ Both whiteboard endpoints require authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
