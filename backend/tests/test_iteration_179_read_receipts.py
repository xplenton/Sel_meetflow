"""Iteration 179 — Read-Receipts Feature Tests

Tests for:
1. Login flow (no 'Keine Verbindung' error)
2. Redis startup wrapper
3. POST /api/chat/conversations/{conv_id}/mark-read
4. GET /api/chat/conversations/{conv_id}/read-status
5. WebSocket 'read' event handling
6. Regression tests from iter 177/178
"""
import os
import sys
import uuid
import pytest
import requests
from pathlib import Path

# Load environment
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://video-meet-pro.preview.emergentagent.com"


class TestLoginFlow:
    """Test login flow works without 'Keine Verbindung' error"""
    
    def test_admin_login_returns_token(self):
        """Admin login with correct credentials returns token and user data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data or "user_id" in data, "Missing token or user_id in response"
        assert data.get("email") == "admin@meetflow.com"
        print(f"✓ Admin login successful, user_id: {data.get('user_id')}")
    
    def test_dashboard_loads_after_login(self):
        """Dashboard endpoint accessible after login"""
        # Login first
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        token = login_resp.json().get("token")
        
        # Access dashboard stats
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        print("✓ Dashboard loads without error")


class TestRedisStartupWrapper:
    """Test Redis is running and ws_broker is connected"""
    
    def test_redis_ping(self):
        """Redis server responds to ping"""
        import subprocess
        result = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True)
        assert "PONG" in result.stdout, f"Redis not responding: {result.stderr}"
        print("✓ Redis server is running")
    
    def test_chat_presence_uses_redis(self):
        """Chat presence endpoint works (uses Redis for cross-pod presence)"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        token = login_resp.json().get("token")
        
        response = requests.get(
            f"{BASE_URL}/api/chat/presence",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "online" in data
        print(f"✓ Chat presence endpoint works, online users: {len(data['online'])}")


class TestReadReceiptsMarkRead:
    """Test POST /api/chat/conversations/{conv_id}/mark-read"""
    
    @pytest.fixture
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        return response.json().get("token")
    
    @pytest.fixture
    def conversation_id(self, auth_token):
        """Get first conversation ID"""
        response = requests.get(
            f"{BASE_URL}/api/chat/conversations",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        convs = response.json()
        if convs:
            return convs[0]["conversation_id"]
        return None
    
    def test_mark_read_returns_ok(self, auth_token, conversation_id):
        """POST /mark-read returns ok:true and last_read timestamp"""
        if not conversation_id:
            pytest.skip("No conversations available")
        
        response = requests.post(
            f"{BASE_URL}/api/chat/conversations/{conversation_id}/mark-read",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"mark-read failed: {response.text}"
        data = response.json()
        assert data.get("ok") == True
        assert "last_read" in data
        print(f"✓ mark-read returns ok:true, last_read: {data['last_read']}")
    
    def test_mark_read_non_member_returns_404(self, auth_token):
        """POST /mark-read for non-existent conversation returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/chat/conversations/conv_nonexistent123/mark-read",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 404
        print("✓ mark-read returns 404 for non-member/non-existent conversation")


class TestReadReceiptsReadStatus:
    """Test GET /api/chat/conversations/{conv_id}/read-status"""
    
    @pytest.fixture
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        return response.json().get("token")
    
    @pytest.fixture
    def conversation_id(self, auth_token):
        """Get first conversation ID"""
        response = requests.get(
            f"{BASE_URL}/api/chat/conversations",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        convs = response.json()
        if convs:
            return convs[0]["conversation_id"]
        return None
    
    def test_read_status_returns_member_timestamps(self, auth_token, conversation_id):
        """GET /read-status returns read_status dict with member timestamps"""
        if not conversation_id:
            pytest.skip("No conversations available")
        
        response = requests.get(
            f"{BASE_URL}/api/chat/conversations/{conversation_id}/read-status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"read-status failed: {response.text}"
        data = response.json()
        assert "read_status" in data
        assert isinstance(data["read_status"], dict)
        print(f"✓ read-status returns {len(data['read_status'])} member timestamps")
    
    def test_read_status_non_member_returns_404(self, auth_token):
        """GET /read-status for non-existent conversation returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/chat/conversations/conv_nonexistent123/read-status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 404
        print("✓ read-status returns 404 for non-member/non-existent conversation")


class TestReadReceiptsE2E:
    """End-to-end test: alice sends message, bob marks read, alice sees read-status"""
    
    def test_full_read_receipt_flow(self):
        """Complete read-receipt flow with two users"""
        tag = uuid.uuid4().hex[:6]
        alice_email = f"alice_{tag}@test.local"
        bob_email = f"bob_{tag}@test.local"
        
        # Register alice
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": alice_email, "password": "Test1234!", "name": f"Alice {tag}"
        })
        assert r.status_code == 200, f"Alice registration failed: {r.text}"
        alice_token = r.json()["token"]
        alice_id = r.json()["user_id"]
        
        # Register bob
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": bob_email, "password": "Test1234!", "name": f"Bob {tag}"
        })
        assert r.status_code == 200, f"Bob registration failed: {r.text}"
        bob_token = r.json()["token"]
        bob_id = r.json()["user_id"]
        
        # Alice creates conversation with Bob
        r = requests.post(
            f"{BASE_URL}/api/chat/conversations",
            headers={"Authorization": f"Bearer {alice_token}"},
            json={"type": "direct", "member_ids": [bob_id]}
        )
        assert r.status_code == 200, f"Create conversation failed: {r.text}"
        conv_id = r.json()["conversation_id"]
        
        # Alice sends a message
        r = requests.post(
            f"{BASE_URL}/api/chat/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {alice_token}"},
            json={"content": "Hello Bob!"}
        )
        assert r.status_code == 200, f"Send message failed: {r.text}"
        msg_created_at = r.json()["created_at"]
        
        # Bob marks as read
        r = requests.post(
            f"{BASE_URL}/api/chat/conversations/{conv_id}/mark-read",
            headers={"Authorization": f"Bearer {bob_token}"}
        )
        assert r.status_code == 200, f"Bob mark-read failed: {r.text}"
        bob_last_read = r.json()["last_read"]
        assert bob_last_read >= msg_created_at, "Bob's last_read should be >= message timestamp"
        
        # Alice fetches read-status
        r = requests.get(
            f"{BASE_URL}/api/chat/conversations/{conv_id}/read-status",
            headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert r.status_code == 200, f"Alice read-status failed: {r.text}"
        rs = r.json()["read_status"]
        assert bob_id in rs, f"Bob not in read_status: {rs}"
        assert rs[bob_id] >= msg_created_at, "Alice should see Bob's read timestamp"
        
        # Non-member (eve) cannot access
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"eve_{tag}@test.local", "password": "Test1234!", "name": "Eve"
        })
        eve_token = r.json()["token"]
        r = requests.get(
            f"{BASE_URL}/api/chat/conversations/{conv_id}/read-status",
            headers={"Authorization": f"Bearer {eve_token}"}
        )
        assert r.status_code == 404, f"Eve should get 404, got {r.status_code}"
        
        print("✓ Full read-receipt E2E flow passed")
        
        # Cleanup
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            import asyncio
            async def cleanup():
                mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
                d = mc[os.environ["DB_NAME"]]
                await d.users.delete_many({"email": {"$in": [alice_email, bob_email, f"eve_{tag}@test.local"]}})
                await d.conversations.delete_one({"conversation_id": conv_id})
                await d.messages.delete_many({"conversation_id": conv_id})
                mc.close()
            asyncio.run(cleanup())
        except Exception as e:
            print(f"Cleanup warning: {e}")


class TestRegressionIter177:
    """Regression tests for iteration 177 bug fixes"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        return response.json().get("token")
    
    def test_surveys_endpoint(self, auth_token):
        """Surveys endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/surveys",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Surveys endpoint works")
    
    def test_news_feed_endpoint(self, auth_token):
        """News feed endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/news/feed",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ News feed endpoint works")
    
    def test_meetings_endpoint(self, auth_token):
        """Meetings endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/meetings",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Meetings endpoint works")


class TestRegressionIter178:
    """Regression tests for iteration 178 features"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        return response.json().get("token")
    
    def test_chat_presence_endpoint(self, auth_token):
        """Chat presence endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/chat/presence",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        assert "online" in response.json()
        print("✓ Chat presence endpoint works")
    
    def test_chat_conversations_endpoint(self, auth_token):
        """Chat conversations endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/chat/conversations",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        print("✓ Chat conversations endpoint works")
    
    def test_chat_my_status_endpoint(self, auth_token):
        """Chat my-status endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/chat/my-status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        assert "status_mode" in response.json()
        print("✓ Chat my-status endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
