"""
Test E2E Encryption and Chat Features for MeetFlow
Tests:
1. E2E Key Registration: POST /api/chat/keys, GET /api/chat/keys/{user_id}
2. E2E Message Encryption: POST /api/chat/conversations/{conv_id}/messages with e2e_encrypted flag
3. E2E Group Key Storage: POST/GET /api/chat/conversations/{conv_id}/group-key
4. E2E Toggle: PUT /api/chat/conversations/{conv_id}/encryption
5. Chat conversation CRUD operations
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestE2EEncryption:
    """E2E Encryption endpoint tests"""
    
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
        data = login_resp.json()
        self.token = data.get("token")
        self.user = data.get("user", {})
        self.user_id = self.user.get("user_id")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
    def test_store_public_key(self):
        """Test POST /api/chat/keys - store public key"""
        # Generate a mock public key (JWK format)
        mock_public_key = '{"kty":"EC","crv":"P-256","x":"test_x_value","y":"test_y_value"}'
        
        response = self.session.post(f"{BASE_URL}/api/chat/keys", json={
            "public_key": mock_public_key
        })
        
        assert response.status_code == 200, f"Store key failed: {response.text}"
        data = response.json()
        assert "message" in data
        print("✓ POST /api/chat/keys - Key stored successfully")
        
    def test_store_public_key_requires_key(self):
        """Test POST /api/chat/keys - requires public_key field"""
        response = self.session.post(f"{BASE_URL}/api/chat/keys", json={})
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ POST /api/chat/keys - Correctly rejects empty key")
        
    def test_get_public_key(self):
        """Test GET /api/chat/keys/{user_id} - retrieve public key"""
        # First store a key for the current user
        mock_public_key = '{"kty":"EC","crv":"P-256","x":"get_test_x","y":"get_test_y"}'
        store_resp = self.session.post(f"{BASE_URL}/api/chat/keys", json={
            "public_key": mock_public_key
        })
        assert store_resp.status_code == 200, f"Store key failed: {store_resp.text}"
        
        # Now retrieve it - the key is stored for the authenticated user
        response = self.session.get(f"{BASE_URL}/api/chat/keys/{self.user_id}")
        
        # If 404, the user_id might be different - let's check what we have
        if response.status_code == 404:
            # Try to get the user info to see the actual user_id
            me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
            if me_resp.status_code == 200:
                actual_user_id = me_resp.json().get("user_id")
                response = self.session.get(f"{BASE_URL}/api/chat/keys/{actual_user_id}")
        
        assert response.status_code == 200, f"Get key failed: {response.text}"
        data = response.json()
        assert "public_key" in data
        assert "user_id" in data
        print(f"✓ GET /api/chat/keys/{data['user_id']} - Key retrieved successfully")
        
    def test_get_public_key_not_found(self):
        """Test GET /api/chat/keys/{user_id} - returns 404 for non-existent user"""
        response = self.session.get(f"{BASE_URL}/api/chat/keys/nonexistent_user_12345")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ GET /api/chat/keys/nonexistent - Correctly returns 404")


class TestE2EConversationEncryption:
    """Test E2E encryption toggle and group keys"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and create a test conversation"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        self.token = data.get("token")
        self.user = data.get("user", {})
        self.user_id = self.user.get("user_id")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get list of users to create a conversation with
        users_resp = self.session.get(f"{BASE_URL}/api/chat/users")
        if users_resp.status_code == 200:
            users = users_resp.json()
            if users:
                self.other_user_id = users[0].get("user_id")
            else:
                self.other_user_id = None
        else:
            self.other_user_id = None
            
    def test_toggle_encryption(self):
        """Test PUT /api/chat/conversations/{conv_id}/encryption - toggle E2E"""
        # First create a conversation
        if not self.other_user_id:
            pytest.skip("No other users available for conversation")
            
        conv_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [self.other_user_id]
        })
        assert conv_resp.status_code == 200, f"Create conv failed: {conv_resp.text}"
        conv = conv_resp.json()
        conv_id = conv.get("conversation_id")
        initial_encrypted = conv.get("encrypted", False)
        
        # Toggle encryption
        toggle_resp = self.session.put(f"{BASE_URL}/api/chat/conversations/{conv_id}/encryption")
        
        assert toggle_resp.status_code == 200, f"Toggle failed: {toggle_resp.text}"
        data = toggle_resp.json()
        assert "encrypted" in data
        assert data["encrypted"] != initial_encrypted, "Encryption state should have toggled"
        print(f"✓ PUT /api/chat/conversations/{conv_id}/encryption - Toggled to {data['encrypted']}")
        
    def test_store_group_key(self):
        """Test POST /api/chat/conversations/{conv_id}/group-key - store group key"""
        # Create a group conversation
        conv_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "group",
            "member_ids": [self.other_user_id] if self.other_user_id else [],
            "name": f"TEST_E2E_Group_{uuid.uuid4().hex[:6]}"
        })
        assert conv_resp.status_code == 200, f"Create group failed: {conv_resp.text}"
        conv = conv_resp.json()
        conv_id = conv.get("conversation_id")
        
        # Store a group key
        mock_group_key = '{"kty":"oct","k":"test_group_key_base64","alg":"A256GCM"}'
        response = self.session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/group-key", json={
            "group_key": mock_group_key
        })
        
        assert response.status_code == 200, f"Store group key failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"✓ POST /api/chat/conversations/{conv_id}/group-key - Group key stored")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/chat/conversations/{conv_id}")
        
    def test_get_group_key(self):
        """Test GET /api/chat/conversations/{conv_id}/group-key - retrieve group key"""
        # Create a group conversation
        conv_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "group",
            "member_ids": [self.other_user_id] if self.other_user_id else [],
            "name": f"TEST_E2E_GetKey_{uuid.uuid4().hex[:6]}"
        })
        assert conv_resp.status_code == 200
        conv = conv_resp.json()
        conv_id = conv.get("conversation_id")
        
        # Store a group key first
        mock_group_key = '{"kty":"oct","k":"retrieve_test_key","alg":"A256GCM"}'
        self.session.post(f"{BASE_URL}/api/chat/conversations/{conv_id}/group-key", json={
            "group_key": mock_group_key
        })
        
        # Retrieve the group key
        response = self.session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/group-key")
        
        assert response.status_code == 200, f"Get group key failed: {response.text}"
        data = response.json()
        assert "group_key" in data
        assert data["group_key"] == mock_group_key
        print(f"✓ GET /api/chat/conversations/{conv_id}/group-key - Group key retrieved")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/chat/conversations/{conv_id}")
        
    def test_get_group_key_not_set(self):
        """Test GET /api/chat/conversations/{conv_id}/group-key - returns null when not set"""
        # Create a new conversation without setting a key
        conv_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "group",
            "member_ids": [self.other_user_id] if self.other_user_id else [],
            "name": f"TEST_E2E_NoKey_{uuid.uuid4().hex[:6]}"
        })
        assert conv_resp.status_code == 200
        conv = conv_resp.json()
        conv_id = conv.get("conversation_id")
        
        # Try to get group key (should return null)
        response = self.session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/group-key")
        
        assert response.status_code == 200, f"Get group key failed: {response.text}"
        data = response.json()
        assert "group_key" in data
        assert data["group_key"] is None
        print(f"✓ GET /api/chat/conversations/{conv_id}/group-key - Returns null when not set")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/chat/conversations/{conv_id}")


class TestE2EEncryptedMessages:
    """Test sending encrypted messages with e2e_encrypted flag"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and create a test conversation"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        self.token = data.get("token")
        self.user = data.get("user", {})
        self.user_id = self.user.get("user_id")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get or create a conversation
        convs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations")
        if convs_resp.status_code == 200:
            convs = convs_resp.json()
            if convs:
                self.conv_id = convs[0].get("conversation_id")
            else:
                # Create one
                users_resp = self.session.get(f"{BASE_URL}/api/chat/users")
                if users_resp.status_code == 200 and users_resp.json():
                    other_user = users_resp.json()[0]
                    conv_resp = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
                        "type": "direct",
                        "member_ids": [other_user.get("user_id")]
                    })
                    if conv_resp.status_code == 200:
                        self.conv_id = conv_resp.json().get("conversation_id")
                    else:
                        self.conv_id = None
                else:
                    self.conv_id = None
        else:
            self.conv_id = None
            
    def test_send_encrypted_message(self):
        """Test POST /api/chat/conversations/{conv_id}/messages with e2e_encrypted=true"""
        if not self.conv_id:
            pytest.skip("No conversation available")
            
        # Send an encrypted message (content would be ciphertext in real scenario)
        mock_ciphertext = "SGVsbG8gV29ybGQh"  # Base64 encoded mock ciphertext
        
        response = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/messages", json={
            "content": mock_ciphertext,
            "e2e_encrypted": True
        })
        
        assert response.status_code == 200, f"Send message failed: {response.text}"
        data = response.json()
        assert data.get("e2e_encrypted") == True, "Message should be marked as e2e_encrypted"
        assert data.get("content") == mock_ciphertext
        print(f"✓ POST /api/chat/conversations/{self.conv_id}/messages - Encrypted message sent")
        
    def test_send_unencrypted_message(self):
        """Test POST /api/chat/conversations/{conv_id}/messages with e2e_encrypted=false (default)"""
        if not self.conv_id:
            pytest.skip("No conversation available")
            
        plaintext = f"Test unencrypted message {uuid.uuid4().hex[:6]}"
        
        response = self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/messages", json={
            "content": plaintext
        })
        
        assert response.status_code == 200, f"Send message failed: {response.text}"
        data = response.json()
        assert data.get("e2e_encrypted") == False, "Message should not be marked as e2e_encrypted"
        assert data.get("content") == plaintext
        print(f"✓ POST /api/chat/conversations/{self.conv_id}/messages - Unencrypted message sent")
        
    def test_encrypted_message_last_message_preview(self):
        """Test that encrypted messages show 'Verschluesselte Nachricht' in last_message"""
        if not self.conv_id:
            pytest.skip("No conversation available")
            
        # Send an encrypted message
        mock_ciphertext = "RW5jcnlwdGVkQ29udGVudA=="
        
        self.session.post(f"{BASE_URL}/api/chat/conversations/{self.conv_id}/messages", json={
            "content": mock_ciphertext,
            "e2e_encrypted": True
        })
        
        # Get conversation to check last_message
        conv_resp = self.session.get(f"{BASE_URL}/api/chat/conversations/{self.conv_id}")
        
        assert conv_resp.status_code == 200, f"Get conv failed: {conv_resp.text}"
        conv = conv_resp.json()
        last_msg = conv.get("last_message", {})
        
        # The last_message content should show "Verschluesselte Nachricht" for encrypted messages
        assert last_msg.get("content") == "Verschluesselte Nachricht", \
            f"Expected 'Verschluesselte Nachricht', got '{last_msg.get('content')}'"
        print("✓ Encrypted message shows 'Verschluesselte Nachricht' in last_message preview")


class TestChatConversations:
    """Test basic chat conversation operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        self.token = data.get("token")
        self.user = data.get("user", {})
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
    def test_list_conversations(self):
        """Test GET /api/chat/conversations"""
        response = self.session.get(f"{BASE_URL}/api/chat/conversations")
        
        assert response.status_code == 200, f"List convs failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/chat/conversations - Listed {len(data)} conversations")
        
    def test_list_chat_users(self):
        """Test GET /api/chat/users"""
        response = self.session.get(f"{BASE_URL}/api/chat/users")
        
        assert response.status_code == 200, f"List users failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/chat/users - Listed {len(data)} users")
        
    def test_create_group_conversation(self):
        """Test POST /api/chat/conversations - create group"""
        # Get users first
        users_resp = self.session.get(f"{BASE_URL}/api/chat/users")
        if users_resp.status_code != 200 or not users_resp.json():
            pytest.skip("No users available")
            
        users = users_resp.json()
        member_ids = [u.get("user_id") for u in users[:2]]
        
        group_name = f"TEST_Group_{uuid.uuid4().hex[:6]}"
        response = self.session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "group",
            "member_ids": member_ids,
            "name": group_name
        })
        
        assert response.status_code == 200, f"Create group failed: {response.text}"
        data = response.json()
        assert data.get("type") == "group"
        assert data.get("name") == group_name
        assert "conversation_id" in data
        assert "encrypted" in data  # Should have encrypted field
        print(f"✓ POST /api/chat/conversations - Created group '{group_name}'")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/chat/conversations/{data.get('conversation_id')}")
        
    def test_get_messages(self):
        """Test GET /api/chat/conversations/{conv_id}/messages"""
        # Get a conversation first
        convs_resp = self.session.get(f"{BASE_URL}/api/chat/conversations")
        if convs_resp.status_code != 200 or not convs_resp.json():
            pytest.skip("No conversations available")
            
        conv_id = convs_resp.json()[0].get("conversation_id")
        
        response = self.session.get(f"{BASE_URL}/api/chat/conversations/{conv_id}/messages")
        
        assert response.status_code == 200, f"Get messages failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        
        # Check message structure if there are messages
        if data:
            msg = data[0]
            assert "message_id" in msg
            assert "content" in msg
            assert "sender_id" in msg
            # Check for e2e_encrypted field
            if "e2e_encrypted" in msg:
                assert isinstance(msg["e2e_encrypted"], bool)
                
        print(f"✓ GET /api/chat/conversations/{conv_id}/messages - Retrieved {len(data)} messages")


class TestChatRequiresAuth:
    """Test that chat endpoints require authentication"""
    
    def test_conversations_requires_auth(self):
        """Test GET /api/chat/conversations requires auth"""
        response = requests.get(f"{BASE_URL}/api/chat/conversations")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ GET /api/chat/conversations requires authentication")
        
    def test_keys_requires_auth(self):
        """Test POST /api/chat/keys requires auth"""
        response = requests.post(f"{BASE_URL}/api/chat/keys", json={"public_key": "test"})
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ POST /api/chat/keys requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
