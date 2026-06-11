"""
Test Chat Status and DND (Do Not Disturb) Feature
Tests the integration between Focus Time and Chat Status

Features tested:
- GET /api/chat/my-status returns status_mode='dnd' when user has active focus time
- GET /api/chat/users includes status_mode field for each user
- GET /api/chat/conversations returns other_status field for direct conversations
"""

import pytest
import requests
import os
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestChatStatusDND:
    """Test Chat Status and DND integration with Focus Time"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session for all tests"""
        self.session = requests.Session()
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.user = login_response.json()
        yield
        # Cleanup: remove any test focus times created
        try:
            focus_times = self.session.get(f"{BASE_URL}/api/focus-times").json()
            for ft in focus_times:
                if ft.get('label', '').startswith('TEST_'):
                    self.session.delete(f"{BASE_URL}/api/focus-times/{ft['focus_id']}")
        except:
            pass
    
    def test_my_status_endpoint_exists(self):
        """Test that /api/chat/my-status endpoint exists and returns valid response"""
        response = self.session.get(f"{BASE_URL}/api/chat/my-status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert 'status_mode' in data, "Response should contain status_mode field"
        assert data['status_mode'] in ['online', 'dnd', 'busy', 'away', 'offline'], f"Invalid status_mode: {data['status_mode']}"
    
    def test_my_status_returns_dnd_with_active_focus(self):
        """Test that my-status returns 'dnd' when user has active focus time"""
        # First check current focus times
        focus_response = self.session.get(f"{BASE_URL}/api/focus-times")
        assert focus_response.status_code == 200
        focus_times = focus_response.json()
        
        # Check if there's an active focus time
        now = datetime.now(timezone.utc)
        has_active_focus = False
        for ft in focus_times:
            start = datetime.fromisoformat(ft['start_time'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(ft['end_time'].replace('Z', '+00:00'))
            if start <= now <= end:
                has_active_focus = True
                break
        
        # Get my status
        status_response = self.session.get(f"{BASE_URL}/api/chat/my-status")
        assert status_response.status_code == 200
        data = status_response.json()
        
        if has_active_focus:
            assert data['status_mode'] == 'dnd', f"Expected 'dnd' with active focus, got '{data['status_mode']}'"
            assert data.get('focus') is not None, "Should include focus time info when in DND"
        else:
            # If no active focus, status should be online (or whatever default)
            assert data['status_mode'] in ['online', 'offline'], f"Expected 'online' or 'offline' without focus, got '{data['status_mode']}'"
    
    def test_my_status_includes_focus_info(self):
        """Test that my-status includes focus time details when in DND mode"""
        response = self.session.get(f"{BASE_URL}/api/chat/my-status")
        assert response.status_code == 200
        data = response.json()
        
        if data['status_mode'] == 'dnd':
            assert 'focus' in data, "DND status should include focus time info"
            focus = data['focus']
            assert 'focus_id' in focus, "Focus info should have focus_id"
            assert 'label' in focus, "Focus info should have label"
            assert 'start_time' in focus, "Focus info should have start_time"
            assert 'end_time' in focus, "Focus info should have end_time"
    
    def test_chat_users_includes_status_mode(self):
        """Test that /api/chat/users includes status_mode for each user"""
        response = self.session.get(f"{BASE_URL}/api/chat/users")
        assert response.status_code == 200
        users = response.json()
        
        assert len(users) > 0, "Should return at least one user"
        
        for user in users:
            assert 'status_mode' in user, f"User {user.get('user_id')} missing status_mode field"
            assert user['status_mode'] in ['online', 'dnd', 'busy', 'away', 'offline'], f"Invalid status_mode for user: {user['status_mode']}"
            assert 'user_id' in user, "User should have user_id"
            assert 'name' in user, "User should have name"
            assert 'email' in user, "User should have email"
    
    def test_chat_users_excludes_current_user(self):
        """Test that /api/chat/users excludes the current logged-in user"""
        response = self.session.get(f"{BASE_URL}/api/chat/users")
        assert response.status_code == 200
        users = response.json()
        
        user_ids = [u['user_id'] for u in users]
        assert self.user['user_id'] not in user_ids, "Current user should not be in the users list"
    
    def test_conversations_includes_other_status(self):
        """Test that /api/chat/conversations includes other_status for direct chats"""
        response = self.session.get(f"{BASE_URL}/api/chat/conversations")
        assert response.status_code == 200
        conversations = response.json()
        
        direct_convs = [c for c in conversations if c.get('type') == 'direct']
        
        for conv in direct_convs:
            assert 'other_status' in conv, f"Direct conversation {conv.get('conversation_id')} missing other_status field"
            assert conv['other_status'] in ['online', 'dnd', 'busy', 'away', 'offline'], f"Invalid other_status: {conv['other_status']}"
            # Also check other_online field exists
            assert 'other_online' in conv, "Direct conversation should have other_online field"
    
    def test_conversations_direct_has_display_name(self):
        """Test that direct conversations have display_name and display_avatar"""
        response = self.session.get(f"{BASE_URL}/api/chat/conversations")
        assert response.status_code == 200
        conversations = response.json()
        
        direct_convs = [c for c in conversations if c.get('type') == 'direct']
        
        for conv in direct_convs:
            assert 'display_name' in conv, "Direct conversation should have display_name"
            assert 'display_avatar' in conv, "Direct conversation should have display_avatar"
    
    def test_create_focus_time_changes_status(self):
        """Test that creating a focus time changes status to DND"""
        # Create a focus time that starts now and ends in 1 hour
        now = datetime.now(timezone.utc)
        start_time = now.isoformat().replace('+00:00', 'Z')
        end_time = (now + timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
        
        create_response = self.session.post(f"{BASE_URL}/api/focus-times", json={
            "label": "TEST_DND_Focus_Session",
            "start_time": start_time,
            "end_time": end_time
        })
        assert create_response.status_code == 200, f"Failed to create focus time: {create_response.text}"
        focus_data = create_response.json()
        focus_id = focus_data['focus_id']
        
        try:
            # Check status is now DND
            status_response = self.session.get(f"{BASE_URL}/api/chat/my-status")
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data['status_mode'] == 'dnd', f"Expected 'dnd' after creating focus time, got '{status_data['status_mode']}'"
        finally:
            # Cleanup
            self.session.delete(f"{BASE_URL}/api/focus-times/{focus_id}")
    
    def test_my_status_requires_auth(self):
        """Test that /api/chat/my-status requires authentication"""
        # Use a new session without login
        new_session = requests.Session()
        response = new_session.get(f"{BASE_URL}/api/chat/my-status")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
    
    def test_chat_users_requires_auth(self):
        """Test that /api/chat/users requires authentication"""
        new_session = requests.Session()
        response = new_session.get(f"{BASE_URL}/api/chat/users")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
    
    def test_conversations_requires_auth(self):
        """Test that /api/chat/conversations requires authentication"""
        new_session = requests.Session()
        response = new_session.get(f"{BASE_URL}/api/chat/conversations")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"


class TestFocusTimeStatusIntegration:
    """Test Focus Time and Status integration edge cases"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        self.user = login_response.json()
        yield
        # Cleanup test focus times
        try:
            focus_times = self.session.get(f"{BASE_URL}/api/focus-times").json()
            for ft in focus_times:
                if ft.get('label', '').startswith('TEST_'):
                    self.session.delete(f"{BASE_URL}/api/focus-times/{ft['focus_id']}")
        except:
            pass
    
    def test_focus_time_active_endpoint(self):
        """Test /api/focus-times/active endpoint"""
        response = self.session.get(f"{BASE_URL}/api/focus-times/active")
        assert response.status_code == 200
        data = response.json()
        
        # Should return either active focus or null/empty
        if data.get('active'):
            focus = data.get('focus', data)  # Focus data may be nested under 'focus' key
            assert 'focus_id' in focus, "Active focus should have focus_id"
            assert 'label' in focus, "Active focus should have label"
    
    def test_status_mode_values(self):
        """Test that status_mode only contains valid values"""
        valid_statuses = ['online', 'dnd', 'busy', 'away', 'offline']
        
        # Check my-status
        my_status = self.session.get(f"{BASE_URL}/api/chat/my-status").json()
        assert my_status['status_mode'] in valid_statuses
        
        # Check users
        users = self.session.get(f"{BASE_URL}/api/chat/users").json()
        for user in users:
            assert user['status_mode'] in valid_statuses, f"User {user['user_id']} has invalid status: {user['status_mode']}"
        
        # Check conversations
        convs = self.session.get(f"{BASE_URL}/api/chat/conversations").json()
        for conv in convs:
            if conv.get('type') == 'direct' and 'other_status' in conv:
                assert conv['other_status'] in valid_statuses, f"Conv {conv['conversation_id']} has invalid other_status: {conv['other_status']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
