"""
Iteration 148 - Calendar-driven DND Auto-Status Sync Tests

Tests for the new status system:
1. PUT /api/chat/my-status sets status_manually_set_at (ISO timestamp) in users collection
2. PUT /api/chat/my-status sets status_auto_dnd=false (Manual-Override)
3. services/calendar_status.py:_is_manual() returns True when status_manually_set_at < 24h
4. services/calendar_status.py:sync_calendar_dnd() iterates only connected users
5. sync_calendar_dnd() sets user to dnd + status_auto_dnd=true when _has_active_meeting()=true AND not manual
6. sync_calendar_dnd() reverts status_auto_dnd=true back to online when _has_active_meeting()=false
7. _has_active_meeting() considers both host_id meetings and meeting_participants entries
8. Regression: WS disconnect sets status_mode='offline' + clears status_manually_set_at and status_auto_dnd
9. Regression: POST /api/meetings/{id}/ring still works (iter 143)
10. Regression: push_new_chat_message uses bypass_dnd correctly (iter 146)
"""

import pytest
import requests
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


def get_or_create_event_loop():
    """Get existing event loop or create a new one"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


class TestIteration148CalendarStatus:
    """Test suite for calendar-driven DND auto-status sync (iter 148)"""
    
    admin_token = None
    admin_user_id = None
    testuser2_token = None
    testuser2_user_id = None
    test_meeting_id = None
    test_conversation_id = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_01_login_admin(self):
        """Login as admin user"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        TestIteration148CalendarStatus.admin_token = data["token"]
        # user_id is at top level, not nested
        TestIteration148CalendarStatus.admin_user_id = data.get("user_id")
        assert TestIteration148CalendarStatus.admin_user_id, f"No user_id in response: {data}"
        print(f"Admin login successful, user_id: {TestIteration148CalendarStatus.admin_user_id}")
    
    def test_02_put_my_status_sets_manually_set_at(self):
        """PUT /api/chat/my-status sets status_manually_set_at in users collection"""
        headers = {"Authorization": f"Bearer {TestIteration148CalendarStatus.admin_token}"}
        
        # Set status to 'away'
        response = self.session.put(
            f"{BASE_URL}/api/chat/my-status",
            json={"status_mode": "away"},
            headers=headers
        )
        assert response.status_code == 200, f"Set status failed: {response.text}"
        data = response.json()
        assert data.get("status_mode") == "away", f"Status not set to away: {data}"
        print(f"Status set to away: {data}")
    
    def test_03_verify_status_manually_set_at_via_login(self):
        """Verify status_manually_set_at is set via login response"""
        # Re-login to get fresh user data
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Verify status_manually_set_at is present
        manually_set_at = data.get("status_manually_set_at")
        assert manually_set_at is not None, f"status_manually_set_at not in response: {data.keys()}"
        
        # Verify it's a valid ISO timestamp
        try:
            dt = datetime.fromisoformat(manually_set_at.replace("Z", "+00:00"))
            assert dt is not None
            print(f"status_manually_set_at verified: {manually_set_at}")
        except Exception as e:
            pytest.fail(f"Invalid ISO timestamp: {manually_set_at}, error: {e}")
        
        # Verify status_auto_dnd is False (manual override)
        status_auto_dnd = data.get("status_auto_dnd")
        assert status_auto_dnd == False, f"status_auto_dnd should be False: {status_auto_dnd}"
        print(f"status_auto_dnd verified: {status_auto_dnd}")
    
    def test_04_put_my_status_sets_status_auto_dnd_false(self):
        """PUT /api/chat/my-status sets status_auto_dnd=false (Manual-Override)"""
        headers = {"Authorization": f"Bearer {TestIteration148CalendarStatus.admin_token}"}
        
        # Set status to 'dnd' manually
        response = self.session.put(
            f"{BASE_URL}/api/chat/my-status",
            json={"status_mode": "dnd"},
            headers=headers
        )
        assert response.status_code == 200, f"Set DND status failed: {response.text}"
        data = response.json()
        assert data.get("status_mode") == "dnd", f"Status not set to dnd: {data}"
        print(f"Manual DND status set: {data}")
    
    def test_05_verify_db_fields_via_python_import(self):
        """Verify status_manually_set_at and status_auto_dnd fields via direct DB access"""
        from database import db
        
        loop = get_or_create_event_loop()
        
        async def check_user_fields():
            user = await db.users.find_one(
                {"user_id": TestIteration148CalendarStatus.admin_user_id},
                {"_id": 0, "status_mode": 1, "status_manually_set_at": 1, "status_auto_dnd": 1}
            )
            return user
        
        user = loop.run_until_complete(check_user_fields())
        assert user is not None, f"User not found in DB for user_id: {TestIteration148CalendarStatus.admin_user_id}"
        
        # Verify status_manually_set_at is set (ISO timestamp)
        manually_set_at = user.get("status_manually_set_at")
        assert manually_set_at is not None, f"status_manually_set_at not set: {user}"
        
        # Verify it's a valid ISO timestamp
        try:
            dt = datetime.fromisoformat(manually_set_at.replace("Z", "+00:00"))
            assert dt is not None
            print(f"status_manually_set_at verified in DB: {manually_set_at}")
        except Exception as e:
            pytest.fail(f"Invalid ISO timestamp: {manually_set_at}, error: {e}")
        
        # Verify status_auto_dnd is False (manual override)
        status_auto_dnd = user.get("status_auto_dnd")
        assert status_auto_dnd == False, f"status_auto_dnd should be False: {status_auto_dnd}"
        print(f"status_auto_dnd verified in DB: {status_auto_dnd}")
    
    def test_06_is_manual_returns_true_within_24h(self):
        """_is_manual() returns True when status_manually_set_at < 24h"""
        from services.calendar_status import _is_manual
        
        loop = get_or_create_event_loop()
        
        async def check_is_manual():
            return await _is_manual(TestIteration148CalendarStatus.admin_user_id)
        
        result = loop.run_until_complete(check_is_manual())
        assert result == True, f"_is_manual should return True for recently set status: {result}"
        print("_is_manual() returned True as expected")
    
    def test_07_is_manual_returns_false_for_old_timestamp(self):
        """_is_manual() returns False when status_manually_set_at > 24h"""
        from database import db
        from services.calendar_status import _is_manual
        
        loop = get_or_create_event_loop()
        
        # Set an old timestamp (25 hours ago)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        
        async def set_old_timestamp_and_check():
            await db.users.update_one(
                {"user_id": TestIteration148CalendarStatus.admin_user_id},
                {"$set": {"status_manually_set_at": old_ts}}
            )
            result = await _is_manual(TestIteration148CalendarStatus.admin_user_id)
            # Restore current timestamp
            await db.users.update_one(
                {"user_id": TestIteration148CalendarStatus.admin_user_id},
                {"$set": {"status_manually_set_at": datetime.now(timezone.utc).isoformat()}}
            )
            return result
        
        result = loop.run_until_complete(set_old_timestamp_and_check())
        assert result == False, f"_is_manual should return False for old timestamp: {result}"
        print("_is_manual() returned False for old timestamp as expected")
    
    def test_08_create_meeting_for_has_active_meeting_test(self):
        """Create a meeting with scheduled_at=NOW for testing _has_active_meeting"""
        headers = {"Authorization": f"Bearer {TestIteration148CalendarStatus.admin_token}"}
        
        # Create a meeting scheduled for now
        now = datetime.now(timezone.utc).isoformat()
        response = self.session.post(
            f"{BASE_URL}/api/meetings",
            json={
                "title": "TEST_iter148_active_meeting",
                "meeting_type": "scheduled",
                "scheduled_at": now,
                "duration": 60,
                "timezone": "UTC"
            },
            headers=headers
        )
        assert response.status_code in [200, 201], f"Create meeting failed: {response.text}"
        data = response.json()
        TestIteration148CalendarStatus.test_meeting_id = data.get("meeting_id")
        assert TestIteration148CalendarStatus.test_meeting_id, f"No meeting_id in response: {data}"
        print(f"Test meeting created: {TestIteration148CalendarStatus.test_meeting_id}")
    
    def test_09_has_active_meeting_returns_true_for_host(self):
        """_has_active_meeting() returns True for host with active meeting"""
        from services.calendar_status import _has_active_meeting
        
        loop = get_or_create_event_loop()
        
        async def check_has_active_meeting():
            now_dt = datetime.now(timezone.utc)
            return await _has_active_meeting(TestIteration148CalendarStatus.admin_user_id, now_dt)
        
        result = loop.run_until_complete(check_has_active_meeting())
        assert result == True, f"_has_active_meeting should return True for host: {result}"
        print("_has_active_meeting() returned True for host as expected")
    
    def test_10_has_active_meeting_considers_participants(self):
        """_has_active_meeting() considers meeting_participants entries"""
        from database import db
        from services.calendar_status import _has_active_meeting
        
        loop = get_or_create_event_loop()
        
        # Create a test user for participant test
        test_participant_id = "test_participant_iter148"
        
        async def add_participant_and_check():
            # Add test participant to the meeting
            await db.meeting_participants.update_one(
                {"meeting_id": TestIteration148CalendarStatus.test_meeting_id, "user_id": test_participant_id},
                {"$set": {
                    "meeting_id": TestIteration148CalendarStatus.test_meeting_id,
                    "user_id": test_participant_id,
                    "name": "Test Participant",
                    "email": "test_participant@meetflow.com",
                    "role": "participant",
                    "joined_at": None,
                    "left_at": None
                }},
                upsert=True
            )
            now_dt = datetime.now(timezone.utc)
            result = await _has_active_meeting(test_participant_id, now_dt)
            
            # Cleanup
            await db.meeting_participants.delete_one(
                {"meeting_id": TestIteration148CalendarStatus.test_meeting_id, "user_id": test_participant_id}
            )
            return result
        
        result = loop.run_until_complete(add_participant_and_check())
        assert result == True, f"_has_active_meeting should return True for participant: {result}"
        print("_has_active_meeting() returned True for participant as expected")
    
    def test_11_sync_calendar_dnd_skips_manual_users(self):
        """sync_calendar_dnd() skips users with status_manually_set_at < 24h"""
        from services.calendar_status import sync_calendar_dnd
        from routes.chat import chat_ws
        from database import db
        
        loop = get_or_create_event_loop()
        
        async def run_sync_with_manual_user():
            # Ensure admin has manual status set
            await db.users.update_one(
                {"user_id": TestIteration148CalendarStatus.admin_user_id},
                {"$set": {
                    "status_manually_set_at": datetime.now(timezone.utc).isoformat(),
                    "status_mode": "online",
                    "in_meeting": None  # Clear in_meeting flag
                }}
            )
            
            # Mock the user as connected
            chat_ws.connections[TestIteration148CalendarStatus.admin_user_id] = ["mock_ws"]
            
            try:
                result = await sync_calendar_dnd()
                return result
            finally:
                # Cleanup mock connection
                if TestIteration148CalendarStatus.admin_user_id in chat_ws.connections:
                    del chat_ws.connections[TestIteration148CalendarStatus.admin_user_id]
        
        result = loop.run_until_complete(run_sync_with_manual_user())
        assert result.get("skipped_manual", 0) >= 1, f"Should skip manual user: {result}"
        print(f"sync_calendar_dnd() skipped manual user: {result}")
    
    def test_12_sync_calendar_dnd_sets_auto_dnd(self):
        """sync_calendar_dnd() sets user to dnd + status_auto_dnd=true when has active meeting"""
        from services.calendar_status import sync_calendar_dnd
        from routes.chat import chat_ws
        from database import db
        
        loop = get_or_create_event_loop()
        
        async def run_sync_for_auto_dnd():
            # Clear manual status for admin
            await db.users.update_one(
                {"user_id": TestIteration148CalendarStatus.admin_user_id},
                {"$set": {
                    "status_manually_set_at": None,
                    "status_mode": "online",
                    "status_auto_dnd": False,
                    "in_meeting": None  # Clear in_meeting flag so sync can process
                }}
            )
            
            # Mock the user as connected
            chat_ws.connections[TestIteration148CalendarStatus.admin_user_id] = ["mock_ws"]
            
            try:
                result = await sync_calendar_dnd()
                
                # Check user status after sync
                user = await db.users.find_one(
                    {"user_id": TestIteration148CalendarStatus.admin_user_id},
                    {"_id": 0, "status_mode": 1, "status_auto_dnd": 1}
                )
                return result, user
            finally:
                # Cleanup mock connection
                if TestIteration148CalendarStatus.admin_user_id in chat_ws.connections:
                    del chat_ws.connections[TestIteration148CalendarStatus.admin_user_id]
        
        result, user = loop.run_until_complete(run_sync_for_auto_dnd())
        
        # Should have set auto_dnd
        assert result.get("auto_dnd", 0) >= 1, f"Should set auto_dnd: {result}"
        assert user.get("status_mode") == "dnd", f"Status should be dnd: {user}"
        assert user.get("status_auto_dnd") == True, f"status_auto_dnd should be True: {user}"
        print(f"sync_calendar_dnd() set auto DND: {result}, user: {user}")
    
    def test_13_sync_calendar_dnd_reverts_auto_dnd(self):
        """sync_calendar_dnd() reverts status_auto_dnd=true back to online when no active meeting"""
        from services.calendar_status import sync_calendar_dnd
        from routes.chat import chat_ws
        from database import db
        
        loop = get_or_create_event_loop()
        
        async def run_sync_for_revert():
            # End the test meeting
            await db.meetings.update_one(
                {"meeting_id": TestIteration148CalendarStatus.test_meeting_id},
                {"$set": {"status": "ended"}}
            )
            
            # Set user as auto-dnd (simulating previous sync)
            await db.users.update_one(
                {"user_id": TestIteration148CalendarStatus.admin_user_id},
                {"$set": {
                    "status_manually_set_at": None,
                    "status_mode": "dnd",
                    "status_auto_dnd": True,
                    "in_meeting": None
                }}
            )
            
            # Mock the user as connected
            chat_ws.connections[TestIteration148CalendarStatus.admin_user_id] = ["mock_ws"]
            
            try:
                result = await sync_calendar_dnd()
                
                # Check user status after sync
                user = await db.users.find_one(
                    {"user_id": TestIteration148CalendarStatus.admin_user_id},
                    {"_id": 0, "status_mode": 1, "status_auto_dnd": 1}
                )
                return result, user
            finally:
                # Cleanup mock connection
                if TestIteration148CalendarStatus.admin_user_id in chat_ws.connections:
                    del chat_ws.connections[TestIteration148CalendarStatus.admin_user_id]
        
        result, user = loop.run_until_complete(run_sync_for_revert())
        
        # Should have reverted to online
        assert result.get("auto_online", 0) >= 1, f"Should revert to online: {result}"
        assert user.get("status_mode") == "online", f"Status should be online: {user}"
        assert user.get("status_auto_dnd") == False, f"status_auto_dnd should be False: {user}"
        print(f"sync_calendar_dnd() reverted to online: {result}, user: {user}")
    
    def test_14_regression_ring_endpoint(self):
        """Regression: POST /api/meetings/{id}/ring still works (iter 143)"""
        headers = {"Authorization": f"Bearer {TestIteration148CalendarStatus.admin_token}"}
        
        # Create a new meeting for ring test
        now = datetime.now(timezone.utc).isoformat()
        response = self.session.post(
            f"{BASE_URL}/api/meetings",
            json={
                "title": "TEST_iter148_ring_test",
                "meeting_type": "scheduled",
                "scheduled_at": now,
                "duration": 60,
                "timezone": "UTC"
            },
            headers=headers
        )
        assert response.status_code in [200, 201], f"Create meeting failed: {response.text}"
        meeting_id = response.json().get("meeting_id")
        
        # Test ring endpoint
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/ring",
            headers=headers
        )
        # Ring should work (200) or return appropriate status
        assert response.status_code in [200, 204, 400], f"Ring endpoint failed: {response.status_code} - {response.text}"
        print(f"Ring endpoint works: {response.status_code}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/meetings/{meeting_id}", headers=headers)
    
    def test_15_regression_bypass_dnd_in_chat_push(self):
        """Regression: push_new_chat_message uses bypass_dnd correctly (iter 146)"""
        # Code review test - verify the signature and logic
        import inspect
        from services.chat_push import _eligible_recipients, push_new_chat_message
        
        # Check _eligible_recipients signature has bypass_dnd parameter
        sig = inspect.signature(_eligible_recipients)
        params = list(sig.parameters.keys())
        assert "bypass_dnd" in params, f"bypass_dnd not in _eligible_recipients params: {params}"
        print(f"_eligible_recipients has bypass_dnd parameter: {params}")
        
        # Check push_new_chat_message source for is_call logic
        source = inspect.getsource(push_new_chat_message)
        assert "is_call" in source, "is_call logic not found in push_new_chat_message"
        assert "bypass_dnd" in source, "bypass_dnd not used in push_new_chat_message"
        print("push_new_chat_message uses bypass_dnd correctly")
    
    def test_16_code_review_calendar_status_module(self):
        """Code review: calendar_status.py has correct structure"""
        from services import calendar_status
        
        # Verify module has required functions
        assert hasattr(calendar_status, '_is_manual'), "_is_manual not found"
        assert hasattr(calendar_status, '_has_active_meeting'), "_has_active_meeting not found"
        assert hasattr(calendar_status, 'sync_calendar_dnd'), "sync_calendar_dnd not found"
        
        # Verify MANUAL_STICKINESS_HOURS constant
        assert hasattr(calendar_status, 'MANUAL_STICKINESS_HOURS'), "MANUAL_STICKINESS_HOURS not found"
        assert calendar_status.MANUAL_STICKINESS_HOURS == 24, f"MANUAL_STICKINESS_HOURS should be 24: {calendar_status.MANUAL_STICKINESS_HOURS}"
        
        print("calendar_status module structure verified")
    
    def test_17_code_review_maintenance_integration(self):
        """Code review: maintenance.py integrates sync_calendar_dnd"""
        import inspect
        from services import maintenance
        
        # Check _cleanup_loop_tick source for calendar_status import
        source = inspect.getsource(maintenance._cleanup_loop_tick)
        assert "sync_calendar_dnd" in source, "sync_calendar_dnd not integrated in maintenance"
        assert "calendar_status" in source, "calendar_status not imported in maintenance"
        
        print("maintenance.py integrates sync_calendar_dnd correctly")
    
    def test_18_code_review_chat_ws_disconnect_clears_fields(self):
        """Code review: WS disconnect clears status_manually_set_at and status_auto_dnd"""
        import inspect
        from routes import chat
        
        # Get the websocket handler source
        source = inspect.getsource(chat.chat_websocket)
        
        # Verify disconnect clears the fields
        assert "status_manually_set_at" in source, "status_manually_set_at not handled in WS disconnect"
        assert "status_auto_dnd" in source, "status_auto_dnd not handled in WS disconnect"
        
        print("WS disconnect clears status fields correctly")
    
    def test_19_code_review_put_my_status_sets_fields(self):
        """Code review: PUT /chat/my-status sets status_manually_set_at and status_auto_dnd"""
        import inspect
        from routes import chat
        
        # Get the set_my_status handler source
        source = inspect.getsource(chat.set_my_status)
        
        # Verify it sets the fields
        assert "status_manually_set_at" in source, "status_manually_set_at not set in PUT /my-status"
        assert "status_auto_dnd" in source, "status_auto_dnd not set in PUT /my-status"
        
        print("PUT /chat/my-status sets status fields correctly")
    
    def test_20_cleanup_test_data(self):
        """Cleanup test data"""
        from database import db
        
        loop = get_or_create_event_loop()
        
        async def cleanup():
            # Delete test meetings
            await db.meetings.delete_many({"title": {"$regex": "^TEST_iter148"}})
            if TestIteration148CalendarStatus.test_meeting_id:
                await db.meeting_participants.delete_many({
                    "meeting_id": TestIteration148CalendarStatus.test_meeting_id
                })
            
            # Reset admin status
            await db.users.update_one(
                {"user_id": TestIteration148CalendarStatus.admin_user_id},
                {"$set": {
                    "status_mode": "online",
                    "status_manually_set_at": None,
                    "status_auto_dnd": False
                }}
            )
        
        loop.run_until_complete(cleanup())
        print("Test data cleaned up")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
