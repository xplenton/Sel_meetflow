"""
Iteration 113 - Production Operations & Performance Tests

Tests for:
1. /api/health endpoint (status=ok, mongo_ok=true)
2. Rate limiting on auth endpoints (login 10/min, register 5/min, forgot-password 3/min)
3. X-Request-ID header in responses
4. ETag/Cache-Control on /api/organization/branding
5. Login functionality after rate-limit decorators
6. /api/chat/conversations N+1 fix (unread_count, display_name, other_online, other_status)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


class TestHealthEndpoint:
    """Test /api/health endpoint for load-balancer readiness"""
    
    def test_health_returns_ok(self):
        """Health endpoint should return status=ok and mongo_ok=true"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data.get('status')}"
        assert data.get("checks", {}).get("mongo", {}).get("ok") is True, "mongo_ok should be true"
        assert "version" in data, "version field should be present"
        assert "ts" in data, "timestamp field should be present"
        print(f"✓ Health endpoint OK: status={data['status']}, version={data.get('version')}")


class TestXRequestID:
    """Test X-Request-ID header in API responses"""
    
    def test_x_request_id_in_response(self):
        """API responses should include X-Request-ID header"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert "X-Request-ID" in resp.headers, "X-Request-ID header should be present"
        rid = resp.headers["X-Request-ID"]
        assert len(rid) >= 8, f"Request ID should be at least 8 chars, got {len(rid)}"
        print(f"✓ X-Request-ID present: {rid}")
    
    def test_x_request_id_on_login(self):
        """Login endpoint should also return X-Request-ID"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=10)
        assert "X-Request-ID" in resp.headers, "X-Request-ID should be in login response"
        print(f"✓ X-Request-ID on login: {resp.headers['X-Request-ID']}")


class TestLoginFunctionality:
    """Test login still works after rate-limit decorators"""
    
    def test_admin_login_success(self):
        """Admin login should work with correct credentials"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=10)
        assert resp.status_code == 200, f"Login failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert "user_id" in data, "user_id should be in response"
        assert data.get("email") == ADMIN_EMAIL, "email should match"
        assert "token" in data, "token should be in response"
        print(f"✓ Admin login successful: user_id={data['user_id']}")
        return data.get("token")
    
    def test_login_invalid_credentials(self):
        """Login with wrong password should return 401"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "wrongpassword"
        }, timeout=10)
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Invalid credentials correctly rejected with 401")


class TestRateLimiting:
    """Test rate limiting on auth endpoints"""
    
    def test_login_rate_limit_10_per_minute(self):
        """Login should be rate-limited to 10 requests per minute"""
        # Use a unique email to avoid lockout interference
        test_email = f"ratelimit_test_{int(time.time())}@test.com"
        
        responses = []
        for i in range(12):
            resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": test_email,
                "password": "wrongpass"
            }, timeout=10)
            responses.append(resp.status_code)
            if resp.status_code == 429:
                print(f"✓ Rate limit hit at attempt {i+1}: 429 Too Many Requests")
                break
        
        # Should get 429 before or at attempt 11
        assert 429 in responses, f"Expected 429 in responses, got: {responses}"
        # First 10 should be 401 (invalid credentials)
        non_429 = [r for r in responses if r != 429]
        assert all(r == 401 for r in non_429), f"Non-429 responses should be 401: {non_429}"
        print(f"✓ Login rate limit working: {len(non_429)} attempts before 429")
    
    def test_register_rate_limit_5_per_minute(self):
        """Register should be rate-limited to 5 requests per minute"""
        responses = []
        for i in range(7):
            test_email = f"regtest_{int(time.time())}_{i}@test.com"
            resp = requests.post(f"{BASE_URL}/api/auth/register", json={
                "email": test_email,
                "password": "Test123!",
                "name": f"Test User {i}"
            }, timeout=10)
            responses.append(resp.status_code)
            if resp.status_code == 429:
                print(f"✓ Register rate limit hit at attempt {i+1}")
                break
        
        assert 429 in responses, f"Expected 429 in responses, got: {responses}"
        print("✓ Register rate limit working")
    
    def test_forgot_password_rate_limit_3_per_minute(self):
        """Forgot password should be rate-limited to 3 requests per minute"""
        test_email = f"forgottest_{int(time.time())}@test.com"
        
        responses = []
        for i in range(5):
            resp = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={
                "email": test_email
            }, timeout=10)
            responses.append(resp.status_code)
            if resp.status_code == 429:
                print(f"✓ Forgot-password rate limit hit at attempt {i+1}")
                break
        
        assert 429 in responses, f"Expected 429 in responses, got: {responses}"
        print("✓ Forgot-password rate limit working")


class TestETagCaching:
    """Test ETag and Cache-Control headers on cacheable endpoints"""
    
    def get_auth_token(self):
        """Helper to get auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("token")
        return None
    
    def test_branding_etag_header(self):
        """GET /api/organization/branding should return ETag header"""
        token = self.get_auth_token()
        if not token:
            pytest.skip("Could not get auth token")
        
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BASE_URL}/api/organization/branding", headers=headers, timeout=10)
        
        if resp.status_code == 404:
            pytest.skip("Branding endpoint not found - may not be configured")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "ETag" in resp.headers, "ETag header should be present"
        assert "Cache-Control" in resp.headers, "Cache-Control header should be present"
        
        etag = resp.headers["ETag"]
        cache_control = resp.headers["Cache-Control"]
        print(f"✓ Branding ETag: {etag}")
        print(f"✓ Cache-Control: {cache_control}")
        return etag, token
    
    def test_branding_304_not_modified(self):
        """GET /api/organization/branding with If-None-Match should return 304"""
        token = self.get_auth_token()
        if not token:
            pytest.skip("Could not get auth token")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # First request to get ETag
        resp1 = requests.get(f"{BASE_URL}/api/organization/branding", headers=headers, timeout=10)
        if resp1.status_code == 404:
            pytest.skip("Branding endpoint not found")
        
        if "ETag" not in resp1.headers:
            pytest.skip("ETag not returned - endpoint may not be cacheable")
        
        etag = resp1.headers["ETag"]
        
        # Second request with If-None-Match
        headers["If-None-Match"] = etag
        resp2 = requests.get(f"{BASE_URL}/api/organization/branding", headers=headers, timeout=10)
        
        assert resp2.status_code == 304, f"Expected 304 Not Modified, got {resp2.status_code}"
        print("✓ 304 Not Modified returned for matching ETag")


class TestConversationsN1Fix:
    """Test /api/chat/conversations after N+1 fix"""
    
    def get_auth_token(self):
        """Helper to get auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("token")
        return None
    
    def test_conversations_returns_expected_fields(self):
        """Conversations should include unread_count, display_name, other_online, other_status for direct chats"""
        token = self.get_auth_token()
        if not token:
            pytest.skip("Could not get auth token")
        
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BASE_URL}/api/chat/conversations", headers=headers, timeout=10)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        
        # Should be a list
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Conversations returned: {len(data)} items")
        
        # Check fields on direct conversations
        direct_convs = [c for c in data if c.get("type") == "direct"]
        if direct_convs:
            conv = direct_convs[0]
            assert "unread_count" in conv, "unread_count should be present"
            assert "display_name" in conv, "display_name should be present for direct chat"
            assert "other_online" in conv, "other_online should be present for direct chat"
            assert "other_status" in conv, "other_status should be present for direct chat"
            print("✓ Direct conversation has all N+1 fix fields:")
            print(f"  - unread_count: {conv.get('unread_count')}")
            print(f"  - display_name: {conv.get('display_name')}")
            print(f"  - other_online: {conv.get('other_online')}")
            print(f"  - other_status: {conv.get('other_status')}")
        else:
            # Even without direct convs, check that unread_count is present
            if data:
                assert "unread_count" in data[0], "unread_count should be present"
                print(f"✓ Conversation has unread_count: {data[0].get('unread_count')}")
            else:
                print("✓ No conversations found (empty list is valid)")


class TestMessagesIndex:
    """Verify messages collection has the new compound index (indirect test via performance)"""
    
    def get_auth_token(self):
        """Helper to get auth token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("token")
        return None
    
    def test_conversations_performance(self):
        """Conversations endpoint should respond quickly (< 2s) thanks to indexes"""
        token = self.get_auth_token()
        if not token:
            pytest.skip("Could not get auth token")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        start = time.time()
        resp = requests.get(f"{BASE_URL}/api/chat/conversations", headers=headers, timeout=10)
        elapsed = time.time() - start
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert elapsed < 2.0, f"Conversations took too long: {elapsed:.2f}s (expected < 2s)"
        print(f"✓ Conversations responded in {elapsed:.3f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
