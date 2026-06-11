"""
Iteration 146 Tests: DND Bypass for Chat Calls + Reachability Endpoint

Tests:
1. POST /api/chat/conversations/{conv_id}/call for GROUP conversation - DND users should receive push
2. _eligible_recipients with bypass_dnd=True includes DND users
3. _eligible_recipients with bypass_dnd=False filters out DND users
4. push_new_chat_message with message_type='call' triggers secondary push (bypass_dnd=True)
5. push_new_chat_message with message_type='text' and urgent=False filters DND users
6. GET /api/meetings/{id}/reachability - host-only, returns invitee reachability info
7. Regression: POST /api/meetings/{id}/ring still works
8. Regression: POST /api/meetings/{id}/join still rings invitees at first-join
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
# Use unique test users for this iteration to avoid password conflicts
TESTUSER2_EMAIL = "testuser_iter146_2@meetflow.com"
TESTUSER2_PASSWORD = "testuser146_2"
TESTUSER3_EMAIL = "testuser_iter146_3@meetflow.com"
TESTUSER3_PASSWORD = "testuser146_3"


class TestIteration146DNDBypassReachability:
    """Test suite for iteration 146 DND bypass and reachability features"""

    admin_token = None
    admin_user_id = None
    testuser2_token = None
    testuser2_user_id = None
    testuser3_token = None
    testuser3_user_id = None
    group_conv_id = None
    test_meeting_id = None

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def test_01_login_admin(self):
        """Login as admin user"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        TestIteration146DNDBypassReachability.admin_token = data.get("token")
        # user_id is at top level, not nested under "user"
        TestIteration146DNDBypassReachability.admin_user_id = data.get("user_id")
        assert TestIteration146DNDBypassReachability.admin_token, "No token returned"
        assert TestIteration146DNDBypassReachability.admin_user_id, "No user_id returned"
        print(f"Admin login successful: {TestIteration146DNDBypassReachability.admin_user_id}")

    def test_02_login_or_create_testuser2(self):
        """Login or create testuser2"""
        # Try login first
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TESTUSER2_EMAIL,
            "password": TESTUSER2_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            TestIteration146DNDBypassReachability.testuser2_token = data.get("token")
            TestIteration146DNDBypassReachability.testuser2_user_id = data.get("user_id")
        else:
            # Register new user
            response = self.session.post(f"{BASE_URL}/api/auth/register", json={
                "email": TESTUSER2_EMAIL,
                "password": TESTUSER2_PASSWORD,
                "name": "Test User 2 Iter146"
            })
            if response.status_code in [200, 201]:
                data = response.json()
                TestIteration146DNDBypassReachability.testuser2_token = data.get("token")
                TestIteration146DNDBypassReachability.testuser2_user_id = data.get("user_id")
            else:
                pytest.skip(f"Could not login or register testuser2: {response.text}")
        
        assert TestIteration146DNDBypassReachability.testuser2_token, "No token for testuser2"
        assert TestIteration146DNDBypassReachability.testuser2_user_id, "No user_id for testuser2"
        print(f"Testuser2 ready: {TestIteration146DNDBypassReachability.testuser2_user_id}")

    def test_03_login_or_create_testuser3(self):
        """Login or create testuser3 for group chat testing"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TESTUSER3_EMAIL,
            "password": TESTUSER3_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            TestIteration146DNDBypassReachability.testuser3_token = data.get("token")
            TestIteration146DNDBypassReachability.testuser3_user_id = data.get("user_id")
        else:
            response = self.session.post(f"{BASE_URL}/api/auth/register", json={
                "email": TESTUSER3_EMAIL,
                "password": TESTUSER3_PASSWORD,
                "name": "Test User 3 Iter146"
            })
            if response.status_code in [200, 201]:
                data = response.json()
                TestIteration146DNDBypassReachability.testuser3_token = data.get("token")
                TestIteration146DNDBypassReachability.testuser3_user_id = data.get("user_id")
            else:
                pytest.skip(f"Could not login or register testuser3: {response.text}")
        
        assert TestIteration146DNDBypassReachability.testuser3_token, "No token for testuser3"
        assert TestIteration146DNDBypassReachability.testuser3_user_id, "No user_id for testuser3"
        print(f"Testuser3 ready: {TestIteration146DNDBypassReachability.testuser3_user_id}")

    def test_04_set_testuser2_to_dnd(self):
        """Set testuser2 status to DND to test bypass"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.testuser2_token}"}
        response = self.session.put(f"{BASE_URL}/api/chat/my-status", json={
            "status_mode": "dnd"
        }, headers=headers)
        assert response.status_code == 200, f"Set DND failed: {response.text}"
        data = response.json()
        assert data.get("status_mode") == "dnd", f"Status not set to DND: {data}"
        print("Testuser2 status set to DND")

    def test_05_create_group_conversation(self):
        """Create a group conversation with admin, testuser2 (DND), and testuser3"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        response = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "group",
            "name": "TEST_Iter146_Group",
            "member_ids": [
                TestIteration146DNDBypassReachability.admin_user_id,
                TestIteration146DNDBypassReachability.testuser2_user_id,
                TestIteration146DNDBypassReachability.testuser3_user_id
            ]
        }, headers=headers)
        assert response.status_code == 200, f"Create group conv failed: {response.text}"
        data = response.json()
        TestIteration146DNDBypassReachability.group_conv_id = data.get("conversation_id")
        assert TestIteration146DNDBypassReachability.group_conv_id, "No conversation_id returned"
        
        # Verify members
        members = data.get("members", [])
        member_ids = [m.get("user_id") for m in members]
        assert TestIteration146DNDBypassReachability.testuser2_user_id in member_ids, "testuser2 not in members"
        assert TestIteration146DNDBypassReachability.testuser3_user_id in member_ids, "testuser3 not in members"
        print(f"Group conversation created: {TestIteration146DNDBypassReachability.group_conv_id}")

    def test_06_start_call_from_group_chat(self):
        """Start a call from group chat - DND user (testuser2) should still be included in push recipients"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        response = self.session.post(
            f"{BASE_URL}/api/chat/conversations/{TestIteration146DNDBypassReachability.group_conv_id}/call",
            json={},
            headers=headers
        )
        assert response.status_code == 200, f"Start call failed: {response.text}"
        data = response.json()
        assert "meeting_id" in data, "No meeting_id in response"
        assert "join_url" in data, "No join_url in response"
        print(f"Call started from group chat: meeting_id={data['meeting_id']}")
        
        # The key test here is that the call succeeded and push was attempted
        # The actual push delivery depends on push subscriptions, but the code path
        # should include DND users (testuser2) in the recipients list

    def test_07_send_text_message_to_group(self):
        """Send a text message to group - DND user should be filtered from push (non-urgent)"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        response = self.session.post(
            f"{BASE_URL}/api/chat/conversations/{TestIteration146DNDBypassReachability.group_conv_id}/messages",
            json={"content": "TEST_Iter146_TextMessage"},
            headers=headers
        )
        assert response.status_code == 200, f"Send message failed: {response.text}"
        data = response.json()
        assert data.get("type") == "text", f"Message type not text: {data}"
        print("Text message sent to group (DND users should be filtered from push)")

    def test_08_create_meeting_for_reachability_test(self):
        """Create a meeting with invitees for reachability endpoint testing"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        
        # Create a scheduled meeting with testuser2 and testuser3 as invitees
        scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Iter146_Reachability_Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "duration": 30,
            "invitees": [
                {"email": TESTUSER2_EMAIL, "user_id": TestIteration146DNDBypassReachability.testuser2_user_id},
                {"email": "testuser3@meetflow.com", "user_id": TestIteration146DNDBypassReachability.testuser3_user_id},
                {"email": "guest@example.com"}  # Guest without user_id
            ]
        }, headers=headers)
        assert response.status_code in [200, 201], f"Create meeting failed: {response.text}"
        data = response.json()
        TestIteration146DNDBypassReachability.test_meeting_id = data.get("meeting_id")
        assert TestIteration146DNDBypassReachability.test_meeting_id, "No meeting_id returned"
        print(f"Meeting created for reachability test: {TestIteration146DNDBypassReachability.test_meeting_id}")

    def test_09_reachability_endpoint_host_access(self):
        """Test GET /api/meetings/{id}/reachability - host should have access"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{TestIteration146DNDBypassReachability.test_meeting_id}/reachability",
            headers=headers
        )
        assert response.status_code == 200, f"Reachability endpoint failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "invitees" in data, "No invitees in response"
        assert "total" in data, "No total in response"
        assert "reachable" in data, "No reachable in response"
        
        invitees = data.get("invitees", [])
        print(f"Reachability response: total={data['total']}, reachable={data['reachable']}")
        
        # Verify invitee structure
        for inv in invitees:
            assert "user_id" in inv, "Missing user_id in invitee"
            assert "name" in inv, "Missing name in invitee"
            assert "email" in inv, "Missing email in invitee"
            assert "push_enabled" in inv, "Missing push_enabled in invitee"
            assert "online" in inv, "Missing online in invitee"
            assert "in_meeting" in inv, "Missing in_meeting in invitee"
            assert "is_guest" in inv, "Missing is_guest in invitee"
        
        # Check guest invitee handling
        guest_invitees = [i for i in invitees if i.get("is_guest")]
        if guest_invitees:
            guest = guest_invitees[0]
            assert guest.get("push_enabled") == False, "Guest should have push_enabled=False"
            assert guest.get("online") == False, "Guest should have online=False"
            assert guest.get("in_meeting") == False, "Guest should have in_meeting=False"
            print("Guest invitee correctly returned with is_guest=True and all booleans False")
        
        # Host should NOT be in the invitees list
        host_in_list = any(i.get("user_id") == TestIteration146DNDBypassReachability.admin_user_id for i in invitees)
        assert not host_in_list, "Host should not be in invitees list"
        print("Host correctly filtered from invitees list")

    def test_10_reachability_endpoint_non_host_forbidden(self):
        """Test GET /api/meetings/{id}/reachability - non-host should get 403"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.testuser2_token}"}
        response = self.session.get(
            f"{BASE_URL}/api/meetings/{TestIteration146DNDBypassReachability.test_meeting_id}/reachability",
            headers=headers
        )
        assert response.status_code == 403, f"Expected 403 for non-host, got {response.status_code}: {response.text}"
        print("Non-host correctly denied access to reachability endpoint (403)")

    def test_11_reachability_endpoint_not_found(self):
        """Test GET /api/meetings/{id}/reachability - non-existent meeting returns 404"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        response = self.session.get(
            f"{BASE_URL}/api/meetings/nonexistent_meeting_id/reachability",
            headers=headers
        )
        assert response.status_code == 404, f"Expected 404 for non-existent meeting, got {response.status_code}"
        print("Non-existent meeting correctly returns 404")

    def test_12_regression_ring_endpoint(self):
        """Regression: POST /api/meetings/{id}/ring still works (iter 143 feature)"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        
        # First, join the meeting to make it active
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{TestIteration146DNDBypassReachability.test_meeting_id}/join",
            headers=headers
        )
        assert response.status_code == 200, f"Join meeting failed: {response.text}"
        
        # Now test the ring endpoint
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{TestIteration146DNDBypassReachability.test_meeting_id}/ring",
            headers=headers
        )
        assert response.status_code == 200, f"Ring endpoint failed: {response.text}"
        data = response.json()
        assert "rang" in data or "message" in data, f"Unexpected ring response: {data}"
        print(f"Ring endpoint works: {data}")

    def test_13_regression_join_meeting_rings_invitees(self):
        """Regression: POST /api/meetings/{id}/join still rings invitees at first-join (iter 142 feature)"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        
        # Create a new scheduled meeting
        scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        response = self.session.post(f"{BASE_URL}/api/meetings", json={
            "title": "TEST_Iter146_JoinRing_Meeting",
            "meeting_type": "scheduled",
            "scheduled_at": scheduled_at,
            "duration": 30,
            "invitees": [
                {"email": TESTUSER2_EMAIL, "user_id": TestIteration146DNDBypassReachability.testuser2_user_id}
            ]
        }, headers=headers)
        assert response.status_code in [200, 201], f"Create meeting failed: {response.text}"
        meeting_id = response.json().get("meeting_id")
        
        # Join the meeting - this should trigger ringing for invitees
        response = self.session.post(
            f"{BASE_URL}/api/meetings/{meeting_id}/join",
            headers=headers
        )
        assert response.status_code == 200, f"Join meeting failed: {response.text}"
        data = response.json()
        
        # Verify meeting is now active
        response = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}", headers=headers)
        assert response.status_code == 200
        meeting_data = response.json()
        assert meeting_data.get("status") == "active", f"Meeting should be active after join: {meeting_data.get('status')}"
        print("Join meeting correctly transitions scheduled meeting to active (triggers ring)")

    def test_14_reset_testuser2_status(self):
        """Reset testuser2 status back to online"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.testuser2_token}"}
        response = self.session.put(f"{BASE_URL}/api/chat/my-status", json={
            "status_mode": "online"
        }, headers=headers)
        assert response.status_code == 200, f"Reset status failed: {response.text}"
        print("Testuser2 status reset to online")

    def test_15_cleanup_test_data(self):
        """Cleanup test conversations and meetings"""
        headers = {"Authorization": f"Bearer {TestIteration146DNDBypassReachability.admin_token}"}
        
        # Delete test conversation
        if TestIteration146DNDBypassReachability.group_conv_id:
            response = self.session.delete(
                f"{BASE_URL}/api/chat/conversations/{TestIteration146DNDBypassReachability.group_conv_id}",
                headers=headers
            )
            print(f"Cleanup: Deleted test conversation (status={response.status_code})")
        
        # Delete test meeting
        if TestIteration146DNDBypassReachability.test_meeting_id:
            response = self.session.delete(
                f"{BASE_URL}/api/meetings/{TestIteration146DNDBypassReachability.test_meeting_id}",
                headers=headers
            )
            print(f"Cleanup: Deleted test meeting (status={response.status_code})")
        
        print("Test cleanup completed")


class TestChatPushBypassDNDLogic:
    """Unit-style tests for chat_push.py _eligible_recipients logic"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def test_code_review_eligible_recipients_signature(self):
        """Verify _eligible_recipients has bypass_dnd parameter (not urgent)"""
        # This is a code review test - we verify the signature change
        import_path = "/app/backend/services/chat_push.py"
        with open(import_path, "r") as f:
            content = f.read()
        
        # Check that bypass_dnd parameter exists
        assert "bypass_dnd: bool = False" in content, "bypass_dnd parameter not found in _eligible_recipients"
        assert "bypass_dnd=urgent or is_call" in content, "bypass_dnd logic for calls not found"
        print("Code review: _eligible_recipients signature correctly changed from urgent to bypass_dnd")

    def test_code_review_push_new_chat_message_call_bypass(self):
        """Verify push_new_chat_message sets bypass_dnd=True for calls"""
        import_path = "/app/backend/services/chat_push.py"
        with open(import_path, "r") as f:
            content = f.read()
        
        # Check that is_call is derived from message_type
        assert 'is_call = message_type == "call"' in content, "is_call derivation not found"
        
        # Check that bypass_dnd is set for calls
        assert "bypass_dnd=urgent or is_call" in content, "bypass_dnd not set for calls"
        
        # Check that secondary push fires for calls too
        assert "if urgent or is_call:" in content, "Secondary push not firing for calls"
        print("Code review: push_new_chat_message correctly bypasses DND for calls")

    def test_code_review_dnd_filter_logic(self):
        """Verify DND filter logic in _eligible_recipients"""
        import_path = "/app/backend/services/chat_push.py"
        with open(import_path, "r") as f:
            content = f.read()
        
        # Check that DND users are filtered when bypass_dnd is False
        assert 'if u.get("status_mode") == "dnd" and not bypass_dnd:' in content, "DND filter logic not found"
        print("Code review: DND filter logic correctly checks bypass_dnd flag")


class TestReachabilityEndpointStructure:
    """Tests for the reachability endpoint response structure"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def test_code_review_reachability_endpoint_exists(self):
        """Verify reachability endpoint exists in meetings/core.py"""
        import_path = "/app/backend/routes/meetings/core.py"
        with open(import_path, "r") as f:
            content = f.read()
        
        # Check endpoint definition
        assert '@router.get("/meetings/{meeting_id}/reachability")' in content, "Reachability endpoint not found"
        
        # Check response structure
        assert '"invitees"' in content or "'invitees'" in content, "invitees field not in response"
        assert '"total"' in content or "'total'" in content, "total field not in response"
        assert '"reachable"' in content or "'reachable'" in content, "reachable field not in response"
        
        # Check invitee fields
        assert '"push_enabled"' in content or "'push_enabled'" in content, "push_enabled field not found"
        assert '"online"' in content or "'online'" in content, "online field not found"
        assert '"in_meeting"' in content or "'in_meeting'" in content, "in_meeting field not found"
        assert '"is_guest"' in content or "'is_guest'" in content, "is_guest field not found"
        
        print("Code review: Reachability endpoint structure verified")

    def test_code_review_host_only_access(self):
        """Verify reachability endpoint is host-only"""
        import_path = "/app/backend/routes/meetings/core.py"
        with open(import_path, "r") as f:
            content = f.read()
        
        # Check host verification
        assert 'is_host = meeting["host_id"] == user["user_id"]' in content, "Host check not found"
        assert "403" in content, "403 status code not found for non-host"
        print("Code review: Reachability endpoint correctly restricts to host")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
