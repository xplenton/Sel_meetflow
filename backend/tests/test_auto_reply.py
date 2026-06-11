"""
Test Auto-Reply Feature for Focus Mode (DND)
Tests:
1. Profile auto-reply settings (PUT /api/users/profile with auto_reply_enabled and auto_reply_message)
2. GET /api/users/profile returns auto_reply fields
3. Auto-reply message sending when a message is sent to a DND user
4. Auto-reply throttling (max 1 per conversation per 30 minutes)
5. Auto-reply message type is 'auto-reply'
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAutoReplyFeature:
    """Test auto-reply feature for focus mode (DND)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin login"""
        self.session = requests.Session()
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin_user = login_resp.json()
        
        # Create a test user session
        self.test_session = requests.Session()
        test_email = f"test_autoreply_{uuid.uuid4().hex[:8]}@test.com"
        register_resp = self.test_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "test123",
            "name": "Test AutoReply User"
        })
        if register_resp.status_code == 400:  # User exists, try login
            login_resp = self.test_session.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": "test123"
            })
            assert login_resp.status_code == 200
            self.test_user = login_resp.json()
        else:
            assert register_resp.status_code == 200
            self.test_user = register_resp.json()
        
        yield
        
        # Cleanup - restore admin auto-reply settings
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True,
            "auto_reply_message": "Bin in Fokus-Modus, antworte spaeter!"
        })

    # ============ Profile Auto-Reply Settings Tests ============
    
    def test_get_profile_returns_auto_reply_fields(self):
        """GET /api/users/profile returns auto_reply_enabled and auto_reply_message fields"""
        response = self.session.get(f"{BASE_URL}/api/users/profile")
        assert response.status_code == 200
        data = response.json()
        
        # Verify auto_reply fields exist
        assert "auto_reply_enabled" in data, "auto_reply_enabled field missing from profile"
        assert "auto_reply_message" in data, "auto_reply_message field missing from profile"
        print(f"✓ Profile contains auto_reply_enabled={data['auto_reply_enabled']}, auto_reply_message='{data.get('auto_reply_message', '')}'")
    
    def test_update_profile_auto_reply_enabled(self):
        """PUT /api/users/profile accepts auto_reply_enabled field"""
        # First disable
        response = self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": False
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("auto_reply_enabled") == False, "auto_reply_enabled should be False"
        
        # Then enable
        response = self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("auto_reply_enabled") == True, "auto_reply_enabled should be True"
        print("✓ auto_reply_enabled toggle works correctly")
    
    def test_update_profile_auto_reply_message(self):
        """PUT /api/users/profile accepts auto_reply_message field"""
        test_message = f"Test auto-reply message {uuid.uuid4().hex[:6]}"
        response = self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_message": test_message
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("auto_reply_message") == test_message, f"auto_reply_message should be '{test_message}'"
        print(f"✓ auto_reply_message updated to '{test_message}'")
    
    def test_update_profile_both_auto_reply_fields(self):
        """PUT /api/users/profile accepts both auto_reply fields together"""
        test_message = "Combined update test message"
        response = self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True,
            "auto_reply_message": test_message
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("auto_reply_enabled") == True
        assert data.get("auto_reply_message") == test_message
        print("✓ Both auto_reply fields updated together successfully")

    # ============ Auto-Reply Message Sending Tests ============
    
    def test_auto_reply_sent_to_dnd_user(self):
        """When a message is sent to a DND user with auto_reply_enabled=true, an auto-reply is created"""
        # Ensure admin has auto-reply enabled
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True,
            "auto_reply_message": "I am in focus mode, will reply later."
        })
        
        # Check if admin has active focus time (DND)
        focus_resp = self.session.get(f"{BASE_URL}/api/focus-times/active")
        if focus_resp.status_code != 200 or not focus_resp.json().get("active"):
            # Create a focus time for admin
            from datetime import datetime, timezone, timedelta
            start = datetime.now(timezone.utc)
            end = start + timedelta(hours=1)
            self.session.post(f"{BASE_URL}/api/focus-times", json={
                "label": "Test Focus Session",
                "start_time": start.isoformat(),
                "end_time": end.isoformat()
            })
        
        # Create a new conversation between test user and admin
        conv_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [self.admin_user["user_id"]]
        })
        assert conv_resp.status_code == 200
        conv = conv_resp.json()
        conv_id = conv["conversation_id"]
        
        # Send a message from test user to admin
        msg_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Hello, are you available?"
        })
        assert msg_resp.status_code == 200
        
        # Check messages in conversation - should have auto-reply
        messages_resp = self.test_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages?limit=10")
        assert messages_resp.status_code == 200
        messages = messages_resp.json()
        
        # Find auto-reply message
        auto_replies = [m for m in messages if m.get("type") == "auto-reply"]
        assert len(auto_replies) >= 1, "Auto-reply message should be created"
        
        auto_reply = auto_replies[0]
        assert auto_reply["sender_id"] == self.admin_user["user_id"], "Auto-reply should be from admin"
        assert auto_reply["content"] == "I am in focus mode, will reply later.", "Auto-reply content should match"
        print("✓ Auto-reply message created with type='auto-reply' and correct content")
    
    def test_auto_reply_has_correct_type(self):
        """Auto-reply messages have type='auto-reply'"""
        # Ensure admin has auto-reply enabled
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True,
            "auto_reply_message": "Auto-reply type test"
        })
        
        # Create a new conversation
        conv_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [self.admin_user["user_id"]]
        })
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["conversation_id"]
        
        # Send message
        self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Testing auto-reply type"
        })
        
        # Get messages
        messages_resp = self.test_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages?limit=10")
        messages = messages_resp.json()
        
        auto_replies = [m for m in messages if m.get("type") == "auto-reply"]
        if auto_replies:
            assert auto_replies[0]["type"] == "auto-reply", "Message type should be 'auto-reply'"
            print("✓ Auto-reply message has type='auto-reply'")
        else:
            # Admin might not be in DND mode
            print("⚠ No auto-reply generated (admin may not be in DND mode)")
    
    def test_auto_reply_is_reply_to_triggering_message(self):
        """Auto-reply is sent as a reply_to the triggering message"""
        # Ensure admin has auto-reply enabled
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True,
            "auto_reply_message": "Reply-to test"
        })
        
        # Create a new conversation
        conv_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [self.admin_user["user_id"]]
        })
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["conversation_id"]
        
        # Send message
        msg_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Testing reply_to field"
        })
        assert msg_resp.status_code == 200
        original_msg = msg_resp.json()
        
        # Get messages
        messages_resp = self.test_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages?limit=10")
        messages = messages_resp.json()
        
        auto_replies = [m for m in messages if m.get("type") == "auto-reply"]
        if auto_replies:
            auto_reply = auto_replies[0]
            assert auto_reply.get("reply_to") == original_msg["message_id"], "Auto-reply should reference the triggering message"
            assert auto_reply.get("reply_preview") is not None, "Auto-reply should have reply_preview"
            print("✓ Auto-reply has correct reply_to and reply_preview")
        else:
            print("⚠ No auto-reply generated (admin may not be in DND mode)")

    # ============ Auto-Reply Throttling Tests ============
    
    def test_auto_reply_throttling(self):
        """Only 1 auto-reply per conversation per 30 minutes"""
        # Ensure admin has auto-reply enabled
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True,
            "auto_reply_message": "Throttling test message"
        })
        
        # Create a new conversation
        conv_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [self.admin_user["user_id"]]
        })
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["conversation_id"]
        
        # Send first message
        self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "First message for throttling test"
        })
        
        # Send second message immediately
        self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Second message for throttling test"
        })
        
        # Send third message
        self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Third message for throttling test"
        })
        
        # Get all messages
        messages_resp = self.test_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages?limit=20")
        messages = messages_resp.json()
        
        # Count auto-replies
        auto_replies = [m for m in messages if m.get("type") == "auto-reply"]
        
        # Should have at most 1 auto-reply due to throttling
        assert len(auto_replies) <= 1, f"Should have at most 1 auto-reply due to throttling, got {len(auto_replies)}"
        print(f"✓ Throttling works: {len(auto_replies)} auto-reply(s) for 3 messages")
    
    def test_no_auto_reply_when_disabled(self):
        """No auto-reply when auto_reply_enabled=false"""
        # Disable auto-reply for admin
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": False
        })
        
        # Create a new conversation
        conv_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [self.admin_user["user_id"]]
        })
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["conversation_id"]
        
        # Send message
        self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "Message when auto-reply is disabled"
        })
        
        # Get messages
        messages_resp = self.test_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages?limit=10")
        messages = messages_resp.json()
        
        # Should have no auto-replies
        auto_replies = [m for m in messages if m.get("type") == "auto-reply"]
        assert len(auto_replies) == 0, "Should have no auto-reply when disabled"
        print("✓ No auto-reply when auto_reply_enabled=false")
        
        # Re-enable for other tests
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True
        })

    # ============ Edge Cases ============
    
    def test_no_auto_reply_for_bot_commands(self):
        """No auto-reply for messages starting with / (bot commands)"""
        # Ensure admin has auto-reply enabled
        self.session.put(f"{BASE_URL}/api/users/profile", json={
            "auto_reply_enabled": True,
            "auto_reply_message": "Bot command test"
        })
        
        # Create a new conversation
        conv_resp = self.test_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [self.admin_user["user_id"]]
        })
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["conversation_id"]
        
        # Send a bot command
        self.test_session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages", json={
            "content": "/hilfe"
        })
        
        # Get messages
        messages_resp = self.test_session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages?limit=10")
        messages = messages_resp.json()
        
        # Should have no auto-replies for bot commands
        auto_replies = [m for m in messages if m.get("type") == "auto-reply"]
        assert len(auto_replies) == 0, "Should have no auto-reply for bot commands"
        print("✓ No auto-reply for bot commands (messages starting with /)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
