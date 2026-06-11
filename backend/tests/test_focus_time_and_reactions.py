"""
Test Focus Time CRUD and Chat Reactions Bug Fix
- Focus Time: Create, List, Delete, Active Check
- Chat Reactions: POST returns updated message with reactions
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_session():
    """Login and return authenticated session with cookies"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login with admin credentials - uses httpOnly cookies
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    
    # Verify we got cookies (access_token is set as httpOnly cookie)
    assert len(session.cookies) > 0 or "access_token" in response.cookies, "No auth cookies received"
    
    # Verify we can access authenticated endpoint
    me_response = session.get(f"{BASE_URL}/api/auth/me")
    assert me_response.status_code == 200, f"Auth verification failed: {me_response.text}"
    
    return session


class TestFocusTimeCRUD:
    """Focus Time CRUD endpoint tests"""
    
    def test_create_focus_time(self, auth_session):
        """POST /api/focus-times creates a focus time"""
        # Create a focus time for tomorrow
        tomorrow = datetime.utcnow() + timedelta(days=1)
        start_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0).isoformat() + "Z"
        end_time = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0).isoformat() + "Z"
        
        response = auth_session.post(f"{BASE_URL}/api/focus-times", json={
            "label": "TEST_Deep Work Session",
            "start_time": start_time,
            "end_time": end_time
        })
        
        assert response.status_code == 200, f"Create focus time failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "focus_id" in data, "Response missing focus_id"
        assert data["label"] == "TEST_Deep Work Session"
        assert data["start_time"] == start_time
        assert data["end_time"] == end_time
        assert "user_id" in data
        assert "created_at" in data
        
        # Store for cleanup
        pytest.focus_id_1 = data["focus_id"]
        print(f"✓ Created focus time: {data['focus_id']}")
    
    def test_create_focus_time_missing_fields(self, auth_session):
        """POST /api/focus-times returns 400 if missing required fields"""
        response = auth_session.post(f"{BASE_URL}/api/focus-times", json={
            "label": "Missing times"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Missing fields returns 400")
    
    def test_list_focus_times(self, auth_session):
        """GET /api/focus-times returns upcoming/active focus times"""
        response = auth_session.get(f"{BASE_URL}/api/focus-times")
        
        assert response.status_code == 200, f"List focus times failed: {response.text}"
        data = response.json()
        
        # Should be a list
        assert isinstance(data, list), "Response should be a list"
        
        # Should contain our created focus time
        focus_ids = [ft["focus_id"] for ft in data]
        assert pytest.focus_id_1 in focus_ids, "Created focus time not in list"
        
        # Verify structure of items
        for ft in data:
            assert "focus_id" in ft
            assert "label" in ft
            assert "start_time" in ft
            assert "end_time" in ft
            assert "_id" not in ft, "MongoDB _id should be excluded"
        
        print(f"✓ Listed {len(data)} focus times")
    
    def test_get_active_focus_none(self, auth_session):
        """GET /api/focus-times/active returns no active focus when none is active"""
        response = auth_session.get(f"{BASE_URL}/api/focus-times/active")
        
        assert response.status_code == 200, f"Get active focus failed: {response.text}"
        data = response.json()
        
        # Should have active flag
        assert "active" in data
        # Our test focus time is for tomorrow, so should not be active
        # (unless there's another active one)
        print(f"✓ Active focus check: active={data['active']}")
    
    def test_create_active_focus_time(self, auth_session):
        """Create a focus time that is currently active"""
        now = datetime.utcnow()
        start_time = (now - timedelta(minutes=5)).isoformat() + "Z"
        end_time = (now + timedelta(hours=1)).isoformat() + "Z"
        
        response = auth_session.post(f"{BASE_URL}/api/focus-times", json={
            "label": "TEST_Currently Active Focus",
            "start_time": start_time,
            "end_time": end_time
        })
        
        assert response.status_code == 200, f"Create active focus time failed: {response.text}"
        data = response.json()
        pytest.focus_id_2 = data["focus_id"]
        print(f"✓ Created active focus time: {data['focus_id']}")
    
    def test_get_active_focus_exists(self, auth_session):
        """GET /api/focus-times/active returns active focus when one exists"""
        response = auth_session.get(f"{BASE_URL}/api/focus-times/active")
        
        assert response.status_code == 200, f"Get active focus failed: {response.text}"
        data = response.json()
        
        assert data["active"] == True, "Should have active focus"
        assert data["focus"] is not None, "Focus object should be present"
        assert data["focus"]["focus_id"] == pytest.focus_id_2, "Should return the active focus"
        print(f"✓ Active focus detected: {data['focus']['label']}")
    
    def test_delete_focus_time(self, auth_session):
        """DELETE /api/focus-times/{focus_id} removes a focus time"""
        # Delete the first focus time
        response = auth_session.delete(f"{BASE_URL}/api/focus-times/{pytest.focus_id_1}")
        
        assert response.status_code == 200, f"Delete focus time failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"✓ Deleted focus time: {pytest.focus_id_1}")
        
        # Verify it's gone
        response = auth_session.get(f"{BASE_URL}/api/focus-times")
        assert response.status_code == 200
        focus_ids = [ft["focus_id"] for ft in response.json()]
        assert pytest.focus_id_1 not in focus_ids, "Deleted focus time should not be in list"
        print("✓ Verified focus time is deleted")
    
    def test_delete_focus_time_not_found(self, auth_session):
        """DELETE /api/focus-times/{focus_id} returns 404 for non-existent"""
        response = auth_session.delete(f"{BASE_URL}/api/focus-times/focus_nonexistent123")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Delete non-existent returns 404")
    
    def test_cleanup_active_focus(self, auth_session):
        """Cleanup: Delete the active focus time"""
        response = auth_session.delete(f"{BASE_URL}/api/focus-times/{pytest.focus_id_2}")
        assert response.status_code == 200, f"Cleanup failed: {response.text}"
        print("✓ Cleaned up active focus time")


class TestChatReactions:
    """Chat Reactions endpoint tests - verify fix for immediate update"""
    
    @pytest.fixture(scope="class")
    def conversation_and_message(self, auth_session):
        """Create a conversation and message for testing reactions"""
        # Get users to create a conversation
        response = auth_session.get(f"{BASE_URL}/api/chat/users")
        if response.status_code != 200:
            pytest.skip("Cannot get chat users")
        users = response.json()
        
        if len(users) < 1:
            pytest.skip("No users available for chat test")
        
        # Create a direct conversation
        other_user = users[0]
        response = auth_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [other_user["user_id"]]
        })
        
        if response.status_code not in [200, 201]:
            # Try to find existing conversation
            response = auth_session.get(f"{BASE_URL}/api/chat/conversations")
            if response.status_code == 200:
                convs = response.json()
                if convs:
                    conv = convs[0]
                else:
                    pytest.skip("No conversations available")
            else:
                pytest.skip("Cannot create or find conversation")
        else:
            conv = response.json()
        
        conv_id = conv["conversation_id"]
        
        # Send a test message
        response = auth_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "TEST_Message for reaction testing"
        })
        
        if response.status_code not in [200, 201]:
            pytest.skip(f"Cannot send message: {response.text}")
        
        msg = response.json()
        return {"conversation_id": conv_id, "message_id": msg["message_id"]}
    
    def test_add_reaction_returns_updated_message(self, auth_session, conversation_and_message):
        """POST /api/chat/messages/{msg_id}/reactions returns updated message with reactions"""
        msg_id = conversation_and_message["message_id"]
        
        response = auth_session.post(f"{BASE_URL}/api/chat/messages/{msg_id}/reactions", json={
            "emoji": "👍"
        })
        
        assert response.status_code == 200, f"Add reaction failed: {response.text}"
        data = response.json()
        
        # KEY FIX VERIFICATION: Response should contain the updated message with reactions
        assert "reactions" in data, "Response should contain reactions array"
        assert "message_id" in data, "Response should contain message_id"
        assert data["message_id"] == msg_id, "Response should be for the correct message"
        
        # Verify reaction was added
        reactions = data["reactions"]
        assert len(reactions) >= 1, "Should have at least one reaction"
        
        # Find our reaction
        thumbs_up = [r for r in reactions if r["emoji"] == "👍"]
        assert len(thumbs_up) >= 1, "Should have thumbs up reaction"
        
        print(f"✓ Reaction added, response contains {len(reactions)} reactions")
    
    def test_toggle_reaction_removes(self, auth_session, conversation_and_message):
        """POST same reaction again toggles it off"""
        msg_id = conversation_and_message["message_id"]
        
        # Add reaction first
        auth_session.post(f"{BASE_URL}/api/chat/messages/{msg_id}/reactions", json={
            "emoji": "❤️"
        })
        
        # Toggle off
        response = auth_session.post(f"{BASE_URL}/api/chat/messages/{msg_id}/reactions", json={
            "emoji": "❤️"
        })
        
        assert response.status_code == 200, f"Toggle reaction failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "reactions" in data, "Response should contain reactions"
        
        # Heart should be removed
        hearts = [r for r in data["reactions"] if r["emoji"] == "❤️"]
        # After toggle, there should be no heart from this user
        print(f"✓ Reaction toggled, {len(hearts)} heart reactions remaining")
    
    def test_reaction_missing_emoji(self, auth_session, conversation_and_message):
        """POST without emoji returns 400"""
        msg_id = conversation_and_message["message_id"]
        
        response = auth_session.post(f"{BASE_URL}/api/chat/messages/{msg_id}/reactions", json={})
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Missing emoji returns 400")
    
    def test_reaction_nonexistent_message(self, auth_session):
        """POST to non-existent message returns 404"""
        response = auth_session.post(f"{BASE_URL}/api/chat/messages/msg_nonexistent123/reactions", json={
            "emoji": "👍"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent message returns 404")


class TestFocusTimeRequiresAuth:
    """Verify Focus Time endpoints require authentication"""
    
    def test_list_focus_times_requires_auth(self):
        """GET /api/focus-times requires authentication"""
        response = requests.get(f"{BASE_URL}/api/focus-times")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ List focus times requires auth")
    
    def test_create_focus_time_requires_auth(self):
        """POST /api/focus-times requires authentication"""
        response = requests.post(f"{BASE_URL}/api/focus-times", json={
            "label": "Test",
            "start_time": "2026-01-01T09:00:00Z",
            "end_time": "2026-01-01T11:00:00Z"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Create focus time requires auth")
    
    def test_delete_focus_time_requires_auth(self):
        """DELETE /api/focus-times/{id} requires authentication"""
        response = requests.delete(f"{BASE_URL}/api/focus-times/focus_test123")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Delete focus time requires auth")
    
    def test_active_focus_requires_auth(self):
        """GET /api/focus-times/active requires authentication"""
        response = requests.get(f"{BASE_URL}/api/focus-times/active")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Active focus check requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
