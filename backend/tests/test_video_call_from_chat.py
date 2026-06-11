"""
Test Video Call from Chat Feature
Tests the POST /api/chat/conversations/{conv_id}/call endpoint that:
1. Creates an instant meeting
2. Adds caller as host participant
3. Creates system message + call message in chat
4. Returns meeting_id and join_url
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestVideoCallFromChat:
    """Test video call initiation from chat"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        login_data = login_resp.json()
        # Login returns user fields directly (user_id, email, name, etc.) not nested under "user"
        self.token = login_data.get("token")
        self.user = login_data  # The response IS the user object
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get or create a conversation for testing
        convs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations")
        assert convs_resp.status_code == 200
        convs = convs_resp.json()
        
        if convs:
            self.conv_id = convs[0]["conversation_id"]
        else:
            # Create a new conversation
            users_resp = self.session.get(f"{BASE_URL}/api/chat/users")
            if users_resp.status_code == 200 and users_resp.json():
                other_user = users_resp.json()[0]
                create_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
                    "type": "direct",
                    "member_ids": [other_user["user_id"]]
                })
                assert create_resp.status_code == 200
                self.conv_id = create_resp.json()["conversation_id"]
            else:
                pytest.skip("No users available to create conversation")
        
        yield
        
    def test_start_call_creates_meeting_and_returns_join_url(self):
        """POST /api/chat/conversations/{conv_id}/call creates meeting and returns meeting_id + join_url"""
        resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        
        assert resp.status_code == 200, f"Call endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "meeting_id" in data, "Response should contain meeting_id"
        assert "join_url" in data, "Response should contain join_url"
        
        # Verify meeting_id format
        assert data["meeting_id"].startswith("meet_"), f"meeting_id should start with 'meet_': {data['meeting_id']}"
        
        # Verify join_url contains meeting_id
        assert data["meeting_id"] in data["join_url"], f"join_url should contain meeting_id: {data['join_url']}"
        
        # Store for subsequent tests
        self.meeting_id = data["meeting_id"]
        self.join_url = data["join_url"]
        
        print(f"✓ Call created: meeting_id={self.meeting_id}, join_url={self.join_url}")
        
    def test_created_meeting_exists_with_correct_type_and_status(self):
        """The created meeting exists in GET /api/meetings with status 'active' and meeting_type 'instant'"""
        # First create a call
        call_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        assert call_resp.status_code == 200
        meeting_id = call_resp.json()["meeting_id"]
        
        # Get the meeting
        meeting_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}")
        assert meeting_resp.status_code == 200, f"Meeting not found: {meeting_resp.text}"
        meeting = meeting_resp.json()
        
        # Verify meeting properties
        assert meeting["meeting_id"] == meeting_id
        assert meeting["status"] == "active", f"Meeting status should be 'active': {meeting['status']}"
        assert meeting["meeting_type"] == "instant", f"Meeting type should be 'instant': {meeting['meeting_type']}"
        assert meeting["host_id"] == self.user["user_id"], "Host should be the caller"
        
        print(f"✓ Meeting verified: status={meeting['status']}, type={meeting['meeting_type']}")
        
    def test_system_message_created_in_conversation(self):
        """A system message 'hat einen Anruf gestartet' is created in the conversation"""
        # Create a call
        call_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        assert call_resp.status_code == 200
        
        # Get messages
        msgs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/messages?limit=10")
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        
        # Find system message about call
        system_msgs = [m for m in messages if m.get("type") == "system" and "Anruf gestartet" in m.get("content", "")]
        assert len(system_msgs) > 0, f"System message about call not found. Messages: {[m.get('content') for m in messages if m.get('type') == 'system']}"
        
        print(f"✓ System message found: '{system_msgs[-1]['content']}'")
        
    def test_call_message_created_with_meeting_id(self):
        """A call message (type='call') with meeting_id is created in the conversation messages"""
        # Create a call
        call_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        assert call_resp.status_code == 200
        meeting_id = call_resp.json()["meeting_id"]
        
        # Get messages
        msgs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/messages?limit=10")
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        
        # Find call message
        call_msgs = [m for m in messages if m.get("type") == "call"]
        assert len(call_msgs) > 0, f"Call message not found. Message types: {[m.get('type') for m in messages]}"
        
        call_msg = call_msgs[-1]  # Get the most recent call message
        assert call_msg.get("meeting_id") == meeting_id, f"Call message should have meeting_id: {call_msg}"
        assert "meeting_code" in call_msg, "Call message should have meeting_code"
        
        print(f"✓ Call message found: meeting_id={call_msg['meeting_id']}, meeting_code={call_msg['meeting_code']}")
        
    def test_join_url_contains_correct_meeting_id(self):
        """The join_url in the call response contains the correct meeting_id"""
        call_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        assert call_resp.status_code == 200
        data = call_resp.json()
        
        meeting_id = data["meeting_id"]
        join_url = data["join_url"]
        
        # Verify join_url format
        assert f"/meetings/{meeting_id}/join" in join_url, f"join_url should contain /meetings/{meeting_id}/join: {join_url}"
        
        # Verify it uses FRONTEND_URL
        frontend_url = os.environ.get("FRONTEND_URL", "")
        if frontend_url:
            assert join_url.startswith(frontend_url), f"join_url should start with FRONTEND_URL: {join_url}"
        
        print(f"✓ join_url verified: {join_url}")
        
    def test_meeting_has_caller_as_host_participant(self):
        """The meeting has the caller as host participant"""
        # Create a call
        call_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        assert call_resp.status_code == 200
        meeting_id = call_resp.json()["meeting_id"]
        
        # Get participants
        participants_resp = self.session.get(f"{BASE_URL}/api/meetings/{meeting_id}/participants")
        assert participants_resp.status_code == 200
        participants = participants_resp.json()
        
        # Find host participant
        host_participants = [p for p in participants if p.get("role") == "host"]
        assert len(host_participants) > 0, f"No host participant found: {participants}"
        
        host = host_participants[0]
        assert host["user_id"] == self.user["user_id"], f"Host should be the caller: {host}"
        
        print(f"✓ Host participant verified: {host['name']} ({host['user_id']})")
        
    def test_multiple_calls_in_same_conversation(self):
        """Multiple calls can be started in the same conversation without errors"""
        meeting_ids = []
        
        for i in range(3):
            call_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
            assert call_resp.status_code == 200, f"Call {i+1} failed: {call_resp.text}"
            meeting_ids.append(call_resp.json()["meeting_id"])
        
        # Verify all meeting_ids are unique
        assert len(set(meeting_ids)) == 3, f"Meeting IDs should be unique: {meeting_ids}"
        
        # Verify all meetings exist
        for mid in meeting_ids:
            meeting_resp = self.session.get(f"{BASE_URL}/api/meetings/{mid}")
            assert meeting_resp.status_code == 200, f"Meeting {mid} not found"
        
        print(f"✓ Multiple calls verified: {meeting_ids}")
        
    def test_call_with_invalid_conversation_returns_404(self):
        """POST /api/chat/conversations/invalid_conv/call returns 404"""
        resp = self.session.post(f"{BASE_URL}/api/chat/conversations/invalid_conv_id_12345/call")
        assert resp.status_code == 404, f"Expected 404 for invalid conversation: {resp.status_code}"
        
        print("✓ Invalid conversation returns 404")
        
    def test_call_without_auth_returns_401(self):
        """POST /api/chat/conversations/{conv_id}/call without auth returns 401"""
        # Create new session without auth
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        
        resp = no_auth_session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        assert resp.status_code == 401, f"Expected 401 without auth: {resp.status_code}"
        
        print("✓ Unauthenticated request returns 401")


class TestCallMessageInMessages:
    """Test that call messages appear correctly in GET /api/chat/conversations/{conv_id}/messages"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        self.token = login_data.get("token")
        self.user = login_data  # The response IS the user object
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get a conversation
        convs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations")
        assert convs_resp.status_code == 200
        convs = convs_resp.json()
        if convs:
            self.conv_id = convs[0]["conversation_id"]
        else:
            pytest.skip("No conversations available")
        
        yield
        
    def test_call_message_has_required_fields(self):
        """GET /api/chat/conversations/{conv_id}/messages returns call message with type='call' and meeting_id field"""
        # Create a call
        call_resp = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/call")
        assert call_resp.status_code == 200
        expected_meeting_id = call_resp.json()["meeting_id"]
        
        # Get messages
        msgs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/messages?limit=20")
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        
        # Find the call message
        call_msgs = [m for m in messages if m.get("type") == "call" and m.get("meeting_id") == expected_meeting_id]
        assert len(call_msgs) > 0, f"Call message with meeting_id {expected_meeting_id} not found"
        
        call_msg = call_msgs[0]
        
        # Verify required fields
        required_fields = ["message_id", "conversation_id", "sender_id", "sender_name", "type", "meeting_id", "meeting_code", "content", "created_at"]
        for field in required_fields:
            assert field in call_msg, f"Call message missing field: {field}"
        
        assert call_msg["type"] == "call"
        assert call_msg["meeting_id"] == expected_meeting_id
        assert call_msg["conversation_id"] == self.conv_id
        
        print(f"✓ Call message has all required fields: {list(call_msg.keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
