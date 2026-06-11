"""
Test Meeting CRUD Operations - Edit/Delete/CopyLink features
Tests PUT /api/meetings/{id} and DELETE /api/meetings/{id} endpoints
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestMeetingCRUD:
    """Test meeting edit and delete operations"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s
    
    @pytest.fixture(scope="class")
    def auth_session(self, session):
        """Login and return authenticated session"""
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        return session
    
    @pytest.fixture
    def test_meeting(self, auth_session):
        """Create a test meeting for CRUD operations"""
        scheduled_time = (datetime.utcnow() + timedelta(days=1)).isoformat()
        create_resp = auth_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_CRUD_Meeting",
            "description": "Test meeting for CRUD operations",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_time,
            "duration": 60
        })
        assert create_resp.status_code == 200, f"Create meeting failed: {create_resp.text}"
        meeting = create_resp.json()
        yield meeting
        # Cleanup - try to delete if still exists
        try:
            auth_session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        except:
            pass
    
    # ============ LOGIN TESTS ============
    
    def test_login_success(self, session):
        """Test login with valid credentials"""
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert data["email"] == "admin@meetflow.com"
        print(f"✓ Login successful: {data['email']}")
    
    def test_get_current_user(self, auth_session):
        """Test GET /api/auth/me returns user"""
        resp = auth_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "email" in data
        print(f"✓ Get current user: {data['email']}")
    
    # ============ CREATE MEETING TESTS ============
    
    def test_create_scheduled_meeting(self, auth_session):
        """Test creating a scheduled meeting with ISO date string"""
        scheduled_time = (datetime.utcnow() + timedelta(days=2)).isoformat()
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Scheduled_Meeting",
            "description": "Test scheduled meeting",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_time,
            "duration": 60
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "TEST_Scheduled_Meeting"
        assert data["meeting_type"] == "scheduled"
        assert data["scheduled_at"] is not None
        assert "meeting_id" in data
        assert "meeting_code" in data
        print(f"✓ Created scheduled meeting: {data['meeting_id']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/meetings/{data['meeting_id']}")
    
    def test_create_instant_meeting(self, auth_session):
        """Test creating an instant meeting"""
        resp = auth_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Instant_Meeting",
            "meeting_type": "instant"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "TEST_Instant_Meeting"
        assert data["meeting_type"] == "instant"
        assert data["status"] == "active"
        print(f"✓ Created instant meeting: {data['meeting_id']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/meetings/{data['meeting_id']}")
    
    # ============ EDIT MEETING TESTS ============
    
    def test_edit_meeting_title(self, auth_session, test_meeting):
        """Test PUT /api/meetings/{id} - update title"""
        meeting_id = test_meeting["meeting_id"]
        new_title = "TEST_Updated_Title"
        
        resp = auth_session.put(f"{BASE_URL}/api/meetings/{meeting_id}", json={
            "title": new_title
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == new_title
        print(f"✓ Updated meeting title: {new_title}")
        
        # Verify with GET
        get_resp = auth_session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == new_title
        print("✓ Verified title persisted via GET")
    
    def test_edit_meeting_description(self, auth_session, test_meeting):
        """Test PUT /api/meetings/{id} - update description"""
        meeting_id = test_meeting["meeting_id"]
        new_desc = "Updated description for testing"
        
        resp = auth_session.put(f"{BASE_URL}/api/meetings/{meeting_id}", json={
            "description": new_desc
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == new_desc
        print("✓ Updated meeting description")
        
        # Verify with GET
        get_resp = auth_session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["description"] == new_desc
        print("✓ Verified description persisted via GET")
    
    def test_edit_meeting_scheduled_at(self, auth_session, test_meeting):
        """Test PUT /api/meetings/{id} - update scheduled_at"""
        meeting_id = test_meeting["meeting_id"]
        new_time = (datetime.utcnow() + timedelta(days=7)).isoformat()
        
        resp = auth_session.put(f"{BASE_URL}/api/meetings/{meeting_id}", json={
            "scheduled_at": new_time
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["scheduled_at"] is not None
        print(f"✓ Updated meeting scheduled_at: {data['scheduled_at']}")
        
        # Verify with GET
        get_resp = auth_session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["scheduled_at"] is not None
        print("✓ Verified scheduled_at persisted via GET")
    
    def test_edit_meeting_multiple_fields(self, auth_session, test_meeting):
        """Test PUT /api/meetings/{id} - update multiple fields at once"""
        meeting_id = test_meeting["meeting_id"]
        new_time = (datetime.utcnow() + timedelta(days=5)).isoformat()
        
        resp = auth_session.put(f"{BASE_URL}/api/meetings/{meeting_id}", json={
            "title": "TEST_Multi_Update",
            "description": "Multi-field update test",
            "scheduled_at": new_time,
            "duration": 90
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "TEST_Multi_Update"
        assert data["description"] == "Multi-field update test"
        assert data["duration"] == 90
        print("✓ Updated multiple fields successfully")
    
    def test_edit_meeting_not_found(self, auth_session):
        """Test PUT /api/meetings/{id} - 404 for non-existent meeting"""
        resp = auth_session.put(f"{BASE_URL}/api/meetings/nonexistent_meeting_id", json={
            "title": "Should fail"
        })
        assert resp.status_code == 404
        print("✓ Correctly returned 404 for non-existent meeting")
    
    # ============ DELETE MEETING TESTS ============
    
    def test_delete_meeting(self, auth_session):
        """Test DELETE /api/meetings/{id} - delete meeting and verify 404"""
        # Create a meeting to delete
        scheduled_time = (datetime.utcnow() + timedelta(days=1)).isoformat()
        create_resp = auth_session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_To_Delete",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_time
        })
        assert create_resp.status_code == 200
        meeting_id = create_resp.json()["meeting_id"]
        print(f"✓ Created meeting to delete: {meeting_id}")
        
        # Delete the meeting
        delete_resp = auth_session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert delete_resp.status_code == 200
        assert "deleted" in delete_resp.json().get("message", "").lower()
        print(f"✓ Deleted meeting: {meeting_id}")
        
        # Verify meeting no longer exists
        get_resp = auth_session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert get_resp.status_code == 404
        print("✓ Verified meeting returns 404 after deletion")
    
    def test_delete_meeting_not_found(self, auth_session):
        """Test DELETE /api/meetings/{id} - 404 for non-existent meeting"""
        resp = auth_session.delete(f"{BASE_URL}/api/meetings/nonexistent_meeting_id")
        assert resp.status_code == 404
        print("✓ Correctly returned 404 for non-existent meeting")
    
    # ============ LIST MEETINGS TESTS ============
    
    def test_list_meetings(self, auth_session):
        """Test GET /api/meetings - list user's meetings (paginated)"""
        resp = auth_session.get(f"{BASE_URL}/api/meetings")
        assert resp.status_code == 200
        data = resp.json()
        # API now returns paginated response
        assert "meetings" in data, "Response should have 'meetings' key"
        assert "total" in data, "Response should have 'total' key"
        assert "page" in data, "Response should have 'page' key"
        assert "pages" in data, "Response should have 'pages' key"
        assert isinstance(data["meetings"], list)
        print(f"✓ Listed {len(data['meetings'])} meetings (total: {data['total']}, pages: {data['pages']})")
    
    def test_get_meeting_by_id(self, auth_session, test_meeting):
        """Test GET /api/meetings/{id} - get single meeting"""
        meeting_id = test_meeting["meeting_id"]
        resp = auth_session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meeting_id"] == meeting_id
        assert "meeting_code" in data
        assert "participants" in data
        print(f"✓ Got meeting by ID: {meeting_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
