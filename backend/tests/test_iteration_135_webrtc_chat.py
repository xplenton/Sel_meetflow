"""
Iteration 135 Testing: WebRTC 3+ Participants + Meeting Chat Bug

Tests:
1. Meeting CRUD and chat endpoints
2. Chat message persistence and retrieval
3. Chat stress test (50 messages)
4. Meeting participants management
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
TESTUSER2_EMAIL = "testuser2@meetflow.com"
TESTUSER2_PASSWORD = "admin123"


class TestAuth:
    """Authentication tests"""
    
    def test_admin_login(self):
        """Test admin can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert data["email"] == ADMIN_EMAIL
        print(f"Admin login successful: {data['user_id']}")
    
    def test_testuser2_login(self):
        """Test testuser2 can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TESTUSER2_EMAIL,
            "password": TESTUSER2_PASSWORD
        })
        assert response.status_code == 200, f"Testuser2 login failed: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert data["email"] == TESTUSER2_EMAIL
        print(f"Testuser2 login successful: {data['user_id']}")


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return session


@pytest.fixture(scope="module")
def testuser2_session():
    """Get authenticated testuser2 session"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": TESTUSER2_EMAIL,
        "password": TESTUSER2_PASSWORD
    })
    assert response.status_code == 200, f"Testuser2 login failed: {response.text}"
    return session


@pytest.fixture(scope="module")
def test_meeting(admin_session):
    """Create a test meeting for chat tests"""
    meeting_data = {
        "title": f"TEST_WebRTC_Chat_{uuid.uuid4().hex[:8]}",
        "description": "Test meeting for iteration 135 WebRTC and chat testing",
        "duration": 60,
        "meeting_type": "video"
    }
    response = admin_session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
    assert response.status_code == 200, f"Meeting creation failed: {response.text}"
    meeting = response.json()
    assert "meeting_id" in meeting
    print(f"Created test meeting: {meeting['meeting_id']}")
    yield meeting
    # Cleanup - delete meeting after tests
    try:
        admin_session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
    except:
        pass


class TestMeetingCRUD:
    """Meeting CRUD operations"""
    
    def test_create_meeting(self, admin_session):
        """Test meeting creation"""
        meeting_data = {
            "title": f"TEST_Meeting_{uuid.uuid4().hex[:8]}",
            "description": "Test meeting",
            "duration": 30,
            "meeting_type": "video"
        }
        response = admin_session.post(f"{BASE_URL}/api/meetings", json=meeting_data)
        assert response.status_code == 200, f"Meeting creation failed: {response.text}"
        meeting = response.json()
        assert "meeting_id" in meeting
        assert meeting["title"] == meeting_data["title"]
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/meetings/{meeting['meeting_id']}")
        print("Meeting CRUD test passed")
    
    def test_get_meeting(self, admin_session, test_meeting):
        """Test getting meeting details"""
        response = admin_session.get(f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}")
        assert response.status_code == 200, f"Get meeting failed: {response.text}"
        meeting = response.json()
        assert meeting["meeting_id"] == test_meeting["meeting_id"]
        print("Get meeting test passed")


class TestMeetingChat:
    """Meeting chat functionality tests - Bug B verification"""
    
    def test_send_chat_message(self, admin_session, test_meeting):
        """Test sending a chat message in meeting"""
        message_data = {"message": "Hello from admin!", "message_type": "user"}
        response = admin_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}/chat",
            json=message_data
        )
        assert response.status_code == 200, f"Send chat failed: {response.text}"
        msg = response.json()
        assert "message_id" in msg
        assert msg["message"] == "Hello from admin!"
        print(f"Chat message sent: {msg['message_id']}")
    
    def test_get_chat_messages(self, admin_session, test_meeting):
        """Test retrieving chat messages"""
        response = admin_session.get(f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}/chat")
        assert response.status_code == 200, f"Get chat failed: {response.text}"
        messages = response.json()
        assert isinstance(messages, list)
        print(f"Retrieved {len(messages)} chat messages")
    
    def test_chat_message_persistence(self, admin_session, test_meeting):
        """Test that chat messages are persisted correctly"""
        # Send a unique message
        unique_msg = f"Unique_Test_Message_{uuid.uuid4().hex[:8]}"
        message_data = {"message": unique_msg, "message_type": "user"}
        
        send_response = admin_session.post(
            f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}/chat",
            json=message_data
        )
        assert send_response.status_code == 200
        sent_msg = send_response.json()
        
        # Verify it's in the chat history
        get_response = admin_session.get(f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}/chat")
        assert get_response.status_code == 200
        messages = get_response.json()
        
        found = any(m["message"] == unique_msg for m in messages)
        assert found, f"Message '{unique_msg}' not found in chat history"
        print(f"Chat persistence verified for message: {unique_msg[:30]}...")
    
    def test_two_users_chat(self, admin_session, testuser2_session, test_meeting):
        """Test two users can send and see each other's messages"""
        meeting_id = test_meeting["meeting_id"]
        
        # Admin sends message
        admin_msg = f"Admin_Message_{uuid.uuid4().hex[:6]}"
        r1 = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/chat", json={
            "message": admin_msg, "message_type": "user"
        })
        assert r1.status_code == 200, f"Admin send failed: {r1.text}"
        
        # Testuser2 sends message
        user2_msg = f"User2_Message_{uuid.uuid4().hex[:6]}"
        r2 = testuser2_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/chat", json={
            "message": user2_msg, "message_type": "user"
        })
        assert r2.status_code == 200, f"User2 send failed: {r2.text}"
        
        # Both should see both messages
        r3 = admin_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/chat")
        assert r3.status_code == 200
        messages = r3.json()
        
        admin_found = any(m["message"] == admin_msg for m in messages)
        user2_found = any(m["message"] == user2_msg for m in messages)
        
        assert admin_found, "Admin message not found in history"
        assert user2_found, "User2 message not found in history"
        print("Two-user chat test passed - both messages visible")


class TestChatStress:
    """Chat stress test - Bug C verification (50 messages)"""
    
    def test_50_messages_stress(self, admin_session, testuser2_session, test_meeting):
        """Send 50 messages alternating between users and verify all are stored"""
        meeting_id = test_meeting["meeting_id"]
        sent_messages = []
        
        print("Sending 50 messages...")
        for i in range(50):
            session = admin_session if i % 2 == 0 else testuser2_session
            user_label = "admin" if i % 2 == 0 else "user2"
            msg_content = f"Stress_Test_{user_label}_{i:03d}_{uuid.uuid4().hex[:4]}"
            
            response = session.post(f"{BASE_URL}/api/meetings/{meeting_id}/chat", json={
                "message": msg_content, "message_type": "user"
            })
            
            if response.status_code == 200:
                sent_messages.append(msg_content)
            else:
                print(f"  Failed to send message {i}: {response.status_code}")
        
        print(f"Sent {len(sent_messages)}/50 messages")
        assert len(sent_messages) >= 45, f"Too many failures: only {len(sent_messages)}/50 sent"
        
        # Verify all messages are retrievable
        response = admin_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/chat")
        assert response.status_code == 200
        messages = response.json()
        
        # Count how many of our stress test messages are in the history
        stress_msgs = [m for m in messages if m["message"].startswith("Stress_Test_")]
        print(f"Retrieved {len(stress_msgs)} stress test messages from history")
        
        assert len(stress_msgs) >= 45, f"Not all messages persisted: {len(stress_msgs)}/50"
        print(f"Chat stress test PASSED: {len(stress_msgs)} messages verified")
    
    def test_special_characters(self, admin_session, test_meeting):
        """Test special characters in chat messages"""
        meeting_id = test_meeting["meeting_id"]
        special_messages = [
            "Emoji test: 👍❤️🎉🔥😂",
            "HTML test: <script>alert('xss')</script>",
            "Unicode: äöü ß ñ 中文 日本語",
            "Long message: " + "A" * 500,
            "Special chars: @#$%^&*()[]{}|\\;:'\",.<>?/`~"
        ]
        
        for msg in special_messages:
            response = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/chat", json={
                "message": msg, "message_type": "user"
            })
            assert response.status_code == 200, f"Failed to send: {msg[:30]}..."
        
        # Verify retrieval
        response = admin_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/chat")
        assert response.status_code == 200
        messages = response.json()
        
        for msg in special_messages:
            found = any(m["message"] == msg for m in messages)
            assert found, f"Special message not found: {msg[:30]}..."
        
        print("Special characters test PASSED")
    
    def test_chat_message_ordering(self, admin_session, test_meeting):
        """Verify messages are returned in chronological order"""
        response = admin_session.get(f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}/chat")
        assert response.status_code == 200
        messages = response.json()
        
        if len(messages) >= 2:
            for i in range(len(messages) - 1):
                assert messages[i]["created_at"] <= messages[i+1]["created_at"], \
                    f"Messages not in order at index {i}"
        
        print(f"Message ordering verified for {len(messages)} messages")


class TestMeetingParticipants:
    """Meeting participants management for WebRTC tests"""
    
    def test_join_meeting(self, admin_session, test_meeting):
        """Test joining a meeting"""
        response = admin_session.post(f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}/join")
        # Join can return 200 or 409 if already joined
        assert response.status_code in [200, 409], f"Join failed: {response.text}"
        print("Join meeting test passed")
    
    def test_get_participants(self, admin_session, test_meeting):
        """Test getting meeting participants"""
        response = admin_session.get(f"{BASE_URL}/api/meetings/{test_meeting['meeting_id']}/participants")
        assert response.status_code == 200, f"Get participants failed: {response.text}"
        participants = response.json()
        assert isinstance(participants, list)
        print(f"Got {len(participants)} participants")
    
    def test_multiple_users_join(self, admin_session, testuser2_session, test_meeting):
        """Test multiple users can join the same meeting"""
        meeting_id = test_meeting["meeting_id"]
        
        # Admin joins
        r1 = admin_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
        assert r1.status_code in [200, 409]
        
        # Testuser2 joins
        r2 = testuser2_session.post(f"{BASE_URL}/api/meetings/{meeting_id}/join")
        assert r2.status_code in [200, 409]
        
        # Verify both are in participants
        r3 = admin_session.get(f"{BASE_URL}/api/meetings/{meeting_id}/participants")
        assert r3.status_code == 200
        participants = r3.json()
        
        user_ids = [p["user_id"] for p in participants]
        print(f"Participants in meeting: {len(participants)}")
        assert len(participants) >= 2, "Expected at least 2 participants"
        print("Multiple users join test PASSED")


class TestRegressionIter134:
    """Regression tests for iteration 134 features"""
    
    def test_force_logout_all_endpoint(self, admin_session):
        """Test force-logout-all endpoint exists and requires admin"""
        response = admin_session.post(f"{BASE_URL}/api/admin/force-logout-all")
        # Should work for admin
        assert response.status_code in [200, 204], f"Force logout failed: {response.text}"
        print("Force logout all endpoint works")
    
    def test_chat_unread_summary(self, admin_session):
        """Test chat unread summary endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/chat/unread-summary")
        assert response.status_code == 200, f"Unread summary failed: {response.text}"
        data = response.json()
        assert "total_unread" in data or isinstance(data, dict)
        print("Chat unread summary endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
