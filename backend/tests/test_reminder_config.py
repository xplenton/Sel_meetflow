"""
Test suite for Configurable Meeting Reminders feature
Tests:
- GET /api/admin/reminder-config - Returns global reminder config
- PUT /api/admin/reminder-config - Updates config (requires admin)
- Meeting creation with reminder_minutes field
- Meeting stores reminder_sent: false on creation
- Admin role requirement (403 for non-admin)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestReminderConfig:
    """Tests for reminder configuration endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin login"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        self.admin_session = self.session
        
        # Create a non-admin user session for testing 403
        self.non_admin_session = requests.Session()
        self.non_admin_session.headers.update({"Content-Type": "application/json"})
        
        # Register a test user
        register_response = self.non_admin_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": "TEST_reminder_user@example.com",
            "password": "testpass123",
            "name": "Test Reminder User"
        })
        # If user exists, login instead
        if register_response.status_code != 200:
            login_resp = self.non_admin_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": "TEST_reminder_user@example.com",
                "password": "testpass123"
            })
            if login_resp.status_code != 200:
                pytest.skip("Could not create/login test user")
        
        yield
        
        # Cleanup - delete test user if possible
        try:
            self.admin_session.delete(f"{BASE_URL}/api/admin/users/TEST_reminder_user@example.com")
        except:
            pass

    def test_get_reminder_config_as_admin(self):
        """GET /api/admin/reminder-config returns config for admin"""
        response = self.admin_session.get(f"{BASE_URL}/api/admin/reminder-config")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "default_minutes" in data, "Response should contain default_minutes"
        assert "enabled" in data, "Response should contain enabled"
        assert isinstance(data["default_minutes"], int), "default_minutes should be int"
        assert isinstance(data["enabled"], bool), "enabled should be bool"
        print(f"GET reminder-config: default_minutes={data['default_minutes']}, enabled={data['enabled']}")

    def test_get_reminder_config_as_non_admin_returns_403(self):
        """GET /api/admin/reminder-config returns 403 for non-admin"""
        response = self.non_admin_session.get(f"{BASE_URL}/api/admin/reminder-config")
        
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        print("Non-admin correctly gets 403 on GET reminder-config")

    def test_put_reminder_config_as_admin(self):
        """PUT /api/admin/reminder-config updates config for admin"""
        # First get current config
        get_response = self.admin_session.get(f"{BASE_URL}/api/admin/reminder-config")
        original_config = get_response.json()
        
        # Update config
        new_config = {
            "default_minutes": 30,
            "enabled": True
        }
        response = self.admin_session.put(f"{BASE_URL}/api/admin/reminder-config", json=new_config)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["default_minutes"] == 30, f"Expected default_minutes=30, got {data['default_minutes']}"
        assert data["enabled"] == True, f"Expected enabled=True, got {data['enabled']}"
        
        # Verify persistence with GET
        verify_response = self.admin_session.get(f"{BASE_URL}/api/admin/reminder-config")
        verify_data = verify_response.json()
        assert verify_data["default_minutes"] == 30, "Config not persisted correctly"
        
        # Restore original config
        self.admin_session.put(f"{BASE_URL}/api/admin/reminder-config", json=original_config)
        print("PUT reminder-config: Successfully updated and verified persistence")

    def test_put_reminder_config_as_non_admin_returns_403(self):
        """PUT /api/admin/reminder-config returns 403 for non-admin"""
        response = self.non_admin_session.put(f"{BASE_URL}/api/admin/reminder-config", json={
            "default_minutes": 60,
            "enabled": False
        })
        
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        print("Non-admin correctly gets 403 on PUT reminder-config")

    def test_put_reminder_config_partial_update(self):
        """PUT /api/admin/reminder-config allows partial updates"""
        # Get current config
        get_response = self.admin_session.get(f"{BASE_URL}/api/admin/reminder-config")
        original_config = get_response.json()
        
        # Update only default_minutes
        response = self.admin_session.put(f"{BASE_URL}/api/admin/reminder-config", json={
            "default_minutes": 60
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["default_minutes"] == 60
        
        # Update only enabled
        response2 = self.admin_session.put(f"{BASE_URL}/api/admin/reminder-config", json={
            "enabled": False
        })
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["enabled"] == False
        
        # Restore original
        self.admin_session.put(f"{BASE_URL}/api/admin/reminder-config", json=original_config)
        print("Partial updates work correctly")


class TestMeetingReminderField:
    """Tests for reminder_minutes field in meeting creation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin login"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        self.created_meetings = []
        yield
        
        # Cleanup created meetings
        for meeting_id in self.created_meetings:
            try:
                self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}")
            except:
                pass

    def test_meeting_creation_with_reminder_minutes(self):
        """Meeting creation stores reminder_minutes field"""
        from datetime import datetime, timedelta
        
        # Schedule meeting for tomorrow
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
        
        meeting_data = {
            "title": "TEST_Reminder Meeting",
            "description": "Testing reminder_minutes field",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration": 60,
            "reminder_minutes": 30,
            "lobby_enabled": False,
            "guest_access": True
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
        
        assert response.status_code == 200, f"Meeting creation failed: {response.text}"
        
        data = response.json()
        self.created_meetings.append(data["meeting_id"])
        
        assert "reminder_minutes" in data, "Response should contain reminder_minutes"
        assert data["reminder_minutes"] == 30, f"Expected reminder_minutes=30, got {data['reminder_minutes']}"
        print(f"Meeting created with reminder_minutes={data['reminder_minutes']}")

    def test_meeting_creation_stores_reminder_sent_false(self):
        """Meeting creation stores reminder_sent: false"""
        from datetime import datetime, timedelta
        
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
        
        meeting_data = {
            "title": "TEST_Reminder Sent Check",
            "description": "Testing reminder_sent field",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration": 60,
            "reminder_minutes": 15
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
        
        assert response.status_code == 200, f"Meeting creation failed: {response.text}"
        
        data = response.json()
        self.created_meetings.append(data["meeting_id"])
        
        assert "reminder_sent" in data, "Response should contain reminder_sent"
        assert data["reminder_sent"] == False, f"Expected reminder_sent=False, got {data['reminder_sent']}"
        print(f"Meeting created with reminder_sent={data['reminder_sent']}")

    def test_meeting_creation_with_different_reminder_values(self):
        """Test meeting creation with various reminder_minutes values (0, 5, 10, 15, 30, 60, 1440)"""
        from datetime import datetime, timedelta
        
        reminder_values = [0, 5, 10, 15, 30, 60, 1440]
        
        for reminder_val in reminder_values:
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
            
            meeting_data = {
                "title": f"TEST_Reminder {reminder_val}min",
                "meeting_type": "scheduled",
                "scheduled_at": tomorrow,
                "duration": 60,
                "reminder_minutes": reminder_val
            }
            
            response = self.session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
            
            assert response.status_code == 200, f"Meeting creation failed for reminder_minutes={reminder_val}: {response.text}"
            
            data = response.json()
            self.created_meetings.append(data["meeting_id"])
            
            assert data["reminder_minutes"] == reminder_val, f"Expected {reminder_val}, got {data['reminder_minutes']}"
            print(f"Meeting created with reminder_minutes={reminder_val} - OK")

    def test_meeting_creation_default_reminder_minutes(self):
        """Meeting creation uses default reminder_minutes (15) if not specified"""
        from datetime import datetime, timedelta
        
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
        
        # Create meeting without specifying reminder_minutes
        meeting_data = {
            "title": "TEST_Default Reminder",
            "meeting_type": "scheduled",
            "scheduled_at": tomorrow,
            "duration": 60
        }
        
        response = self.session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
        
        assert response.status_code == 200, f"Meeting creation failed: {response.text}"
        
        data = response.json()
        self.created_meetings.append(data["meeting_id"])
        
        # Default is 15 minutes as per MeetingCreateRequest model
        assert data["reminder_minutes"] == 15, f"Expected default reminder_minutes=15, got {data['reminder_minutes']}"
        print(f"Meeting created with default reminder_minutes={data['reminder_minutes']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
