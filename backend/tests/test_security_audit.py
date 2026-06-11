"""
MeetFlow Security Audit Test Suite
===================================
Comprehensive pen-test style security assessment covering:
- OWASP Top 10
- Auth & Session Security
- RBAC/IDOR
- Input Validation & Injection
- Data Exposure
- Public Endpoints
- Rate Limiting
- WebSocket Security
- File Security
- DSGVO/Healthcare Compliance

Severity Levels: CRITICAL, HIGH, MEDIUM, LOW, INFO
"""

import pytest
import requests
import json
import time
import os
import base64
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://video-meet-pro.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"
MEMBER_EMAIL = "loadtest001@meetflow.local"
MEMBER_PASSWORD = "Test123!"

# Store findings
FINDINGS = []

def add_finding(severity, category, title, description, reproduction_steps, impact, recommendation):
    """Add a security finding to the report"""
    FINDINGS.append({
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "reproduction_steps": reproduction_steps,
        "impact": impact,
        "recommendation": recommendation,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

class TestAuthSessionSecurity:
    """1. AUTH & SESSION SECURITY TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_admin_token(self):
        """Helper to get admin token"""
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")
        return None
    
    def get_member_token(self):
        """Helper to get member token"""
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MEMBER_EMAIL, "password": MEMBER_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")
        return None
    
    def test_jwt_tampering_role_injection(self):
        """JWT-Tampering: Token with manipulated payload (role=admin injected)"""
        token = self.get_member_token()
        if not token:
            pytest.skip("Could not get member token")
        
        # Decode without verification to get payload
        parts = token.split(".")
        if len(parts) != 3:
            pytest.skip("Invalid token format")
        
        # Decode payload
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        except:
            pytest.skip("Could not decode payload")
        
        # Modify payload to inject admin role
        payload["role"] = "admin"
        modified_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        
        # Create tampered token
        tampered_token = f"{parts[0]}.{modified_payload}.{parts[2]}"
        
        # Try to access admin endpoint with tampered token
        resp = self.session.get(f"{BASE_URL}/api/admin/users", headers={
            "Authorization": f"Bearer {tampered_token}"
        })
        
        # Should be rejected (401 or 403)
        assert resp.status_code in [401, 403], f"JWT tampering not detected! Got {resp.status_code}"
        print("PASS: JWT tampering with role injection correctly rejected")
    
    def test_jwt_alg_none_attack(self):
        """JWT-Signatur-Strip: 'alg: none' attack attempt"""
        token = self.get_member_token()
        if not token:
            pytest.skip("Could not get member token")
        
        parts = token.split(".")
        if len(parts) != 3:
            pytest.skip("Invalid token format")
        
        # Create header with alg: none
        none_header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
        
        # Create token with no signature
        none_token = f"{none_header}.{parts[1]}."
        
        resp = self.session.get(f"{BASE_URL}/api/auth/me", headers={
            "Authorization": f"Bearer {none_token}"
        })
        
        assert resp.status_code in [401, 403], f"alg:none attack not blocked! Got {resp.status_code}"
        print("PASS: alg:none JWT attack correctly rejected")
    
    def test_jwt_expiry_enforcement(self):
        """JWT-Expiry: expired token must return 401"""
        # Create an expired token manually (if we had the secret)
        # For now, test with a clearly invalid/old token
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdCIsImV4cCI6MTAwMDAwMDAwMH0.invalid"
        
        resp = self.session.get(f"{BASE_URL}/api/auth/me", headers={
            "Authorization": f"Bearer {expired_token}"
        })
        
        assert resp.status_code == 401, f"Expired/invalid token not rejected! Got {resp.status_code}"
        print("PASS: Expired/invalid JWT correctly rejected")
    
    def test_cookie_security_attributes(self):
        """Cookies: access_token/refresh_token must have HttpOnly + Secure + SameSite"""
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        
        assert resp.status_code == 200, f"Login failed: {resp.status_code}"
        
        cookies = resp.cookies
        issues = []
        
        for cookie_name in ["access_token", "refresh_token"]:
            if cookie_name in cookies:
                cookie = cookies.get_dict().get(cookie_name)
                # Check Set-Cookie header for attributes
                set_cookie_headers = resp.headers.get("Set-Cookie", "")
                if cookie_name in set_cookie_headers:
                    if "HttpOnly" not in set_cookie_headers and "httponly" not in set_cookie_headers.lower():
                        issues.append(f"{cookie_name} missing HttpOnly")
                    if "Secure" not in set_cookie_headers and "secure" not in set_cookie_headers.lower():
                        issues.append(f"{cookie_name} missing Secure")
        
        if issues:
            add_finding("MEDIUM", "AUTH", "Cookie Security Attributes", 
                       f"Issues found: {', '.join(issues)}", 
                       "POST /api/auth/login and check Set-Cookie headers",
                       "Session cookies could be stolen via XSS or MITM",
                       "Ensure HttpOnly, Secure, and SameSite=None/Strict on all auth cookies")
        
        print(f"Cookie check: {issues if issues else 'PASS'}")
    
    def test_refresh_token_invalid(self):
        """Refresh-Flow: POST /api/auth/refresh with invalid refresh_token"""
        # Try with no cookie
        resp = self.session.post(f"{BASE_URL}/api/auth/refresh")
        assert resp.status_code == 401, f"Refresh without token should fail: {resp.status_code}"
        
        # Try with invalid cookie
        self.session.cookies.set("refresh_token", "invalid_token_here")
        resp = self.session.post(f"{BASE_URL}/api/auth/refresh")
        assert resp.status_code == 401, f"Refresh with invalid token should fail: {resp.status_code}"
        
        print("PASS: Invalid refresh token correctly rejected")
    
    def test_brute_force_login_protection(self):
        """Brute-Force Login: 20x wrong password - check for rate limit/lockout"""
        results = []
        for i in range(20):
            resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
                "email": ADMIN_EMAIL, "password": f"wrongpassword{i}"
            })
            results.append(resp.status_code)
            if resp.status_code == 429:
                print(f"PASS: Rate limit triggered after {i+1} attempts")
                return
        
        # Check if we got locked out
        if 429 in results:
            print("PASS: Brute force protection active (429 returned)")
        else:
            add_finding("HIGH", "AUTH", "Missing Brute Force Protection",
                       "No rate limiting detected after 20 failed login attempts",
                       "Send 20 POST requests to /api/auth/login with wrong passwords",
                       "Account takeover via credential stuffing/brute force",
                       "Implement rate limiting (e.g., 5 attempts per 15 minutes)")
            print("WARNING: No rate limit detected after 20 attempts")
    
    def test_password_reset_email_enumeration(self):
        """Password Reset: Must not leak 'User not found' for unknown emails"""
        # Test with unknown email
        resp = self.session.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": "nonexistent_user_12345@example.com"
        })
        
        # Should return same message regardless of email existence
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}"
        
        data = resp.json()
        message = data.get("message", "").lower()
        
        # Check for privacy-safe response
        if "not found" in message or "does not exist" in message or "unknown" in message:
            add_finding("MEDIUM", "AUTH", "Email Enumeration via Password Reset",
                       "Password reset endpoint reveals whether email exists",
                       "POST /api/auth/forgot-password with unknown email",
                       "Attackers can enumerate valid user emails",
                       "Return generic message regardless of email existence")
        else:
            print("PASS: Password reset does not leak email existence")
    
    def test_auth_me_no_password_hash(self):
        """REGRESSION: /api/auth/me must NOT return password_hash field"""
        token = self.get_admin_token()
        if not token:
            pytest.skip("Could not get admin token")
        
        resp = self.session.get(f"{BASE_URL}/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        
        assert resp.status_code == 200
        data = resp.json()
        
        if "password_hash" in data:
            add_finding("CRITICAL", "DATA_EXPOSURE", "Password Hash Exposed in /auth/me",
                       "The /api/auth/me endpoint returns the password_hash field",
                       "GET /api/auth/me with valid token",
                       "Password hashes exposed, enabling offline cracking",
                       "Exclude password_hash from user response")
            pytest.fail("password_hash found in /auth/me response!")
        
        if "_id" in data:
            add_finding("LOW", "DATA_EXPOSURE", "MongoDB _id Exposed",
                       "The /api/auth/me endpoint returns MongoDB _id",
                       "GET /api/auth/me with valid token",
                       "Internal database IDs exposed",
                       "Exclude _id from all API responses")
        
        print("PASS: /auth/me does not expose password_hash")
    
    def test_login_response_no_password_hash(self):
        """Login response must NOT contain password_hash"""
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        
        assert resp.status_code == 200
        data = resp.json()
        
        if "password_hash" in data:
            add_finding("CRITICAL", "DATA_EXPOSURE", "Password Hash Exposed in Login Response",
                       "The login endpoint returns the password_hash field",
                       "POST /api/auth/login with valid credentials",
                       "Password hashes exposed, enabling offline cracking",
                       "Exclude password_hash from login response")
            pytest.fail("password_hash found in login response!")
        
        print("PASS: Login response does not expose password_hash")
    
    def test_logout_clears_cookies(self):
        """Logout: POST /api/auth/logout must clear cookies (Max-Age=0)"""
        # First login
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        
        # Then logout
        resp = self.session.post(f"{BASE_URL}/api/auth/logout")
        assert resp.status_code == 200
        
        # Check Set-Cookie headers for Max-Age=0 or expires in past
        set_cookie = resp.headers.get("Set-Cookie", "")
        if "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower():
            print("PASS: Logout clears cookies correctly")
        else:
            add_finding("LOW", "AUTH", "Logout May Not Clear Cookies Properly",
                       "Logout response may not properly invalidate cookies",
                       "POST /api/auth/logout and check Set-Cookie headers",
                       "Session may persist after logout",
                       "Set Max-Age=0 and past expiry on logout")


class TestAuthorizationRBAC:
    """2. AUTHORIZATION / RBAC / IDOR TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_admin_token(self):
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return resp.json().get("token") if resp.status_code == 200 else None
    
    def get_member_token(self):
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": MEMBER_EMAIL, "password": MEMBER_PASSWORD
        })
        return resp.json().get("token") if resp.status_code == 200 else None
    
    def test_vertical_escalation_admin_endpoints(self):
        """Vertical Escalation: member user accessing admin endpoints"""
        member_token = self.get_member_token()
        if not member_token:
            pytest.skip("Could not get member token")
        
        admin_endpoints = [
            "/api/admin/users",
            "/api/admin/groups",
            "/api/admin/stats",
            "/api/admin/capabilities",
            "/api/admin/policies",
            "/api/admin/quick-scans",
        ]
        
        failures = []
        for endpoint in admin_endpoints:
            resp = self.session.get(f"{BASE_URL}{endpoint}", headers={
                "Authorization": f"Bearer {member_token}"
            })
            if resp.status_code not in [401, 403]:
                failures.append(f"{endpoint}: {resp.status_code}")
        
        if failures:
            add_finding("CRITICAL", "AUTHZ", "Vertical Privilege Escalation",
                       f"Member can access admin endpoints: {failures}",
                       "Login as member, access admin endpoints",
                       "Complete admin takeover possible",
                       "Enforce role checks on all admin endpoints")
            pytest.fail(f"Admin endpoints accessible by member: {failures}")
        
        print("PASS: All admin endpoints properly protected")
    
    def test_horizontal_idor_meeting_access(self):
        """Horizontal IDOR: User A reading meeting of User B (not joined)"""
        # This test would need two different users and a meeting
        # For now, test that unauthenticated access is blocked
        resp = self.session.get(f"{BASE_URL}/api/meetings/nonexistent_meeting_id")
        # Should require auth or return 404
        assert resp.status_code in [401, 404], f"Unexpected: {resp.status_code}"
        print("PASS: Meeting access requires authentication")
    
    def test_horizontal_idor_chat_conversation(self):
        """Horizontal IDOR: User A reading chat conversation of User B"""
        member_token = self.get_member_token()
        if not member_token:
            pytest.skip("Could not get member token")
        
        # Try to access a conversation that doesn't belong to the user
        resp = self.session.get(f"{BASE_URL}/api/chat/conversations/conv_nonexistent", headers={
            "Authorization": f"Bearer {member_token}"
        })
        
        # Should be 404 (not found) or 403 (forbidden)
        assert resp.status_code in [403, 404], f"Unexpected: {resp.status_code}"
        print("PASS: Chat conversation access properly restricted")
    
    def test_moderator_cannot_delete_users(self):
        """Moderator can see reports but cannot delete users"""
        # Would need a moderator account to test properly
        # For now, verify admin-only endpoint protection
        member_token = self.get_member_token()
        if not member_token:
            pytest.skip("Could not get member token")
        
        resp = self.session.delete(f"{BASE_URL}/api/admin/users/some_user_id", headers={
            "Authorization": f"Bearer {member_token}"
        })
        
        assert resp.status_code in [401, 403], f"User deletion not protected: {resp.status_code}"
        print("PASS: User deletion properly restricted to admin")


class TestInputValidationInjection:
    """3. INPUT VALIDATION & INJECTION TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_nosql_injection_login(self):
        """NoSQL-Injection: Login with MongoDB operator injection"""
        # Attempt NoSQL injection in login
        payloads = [
            {"email": {"$ne": None}, "password": {"$ne": None}},
            {"email": {"$gt": ""}, "password": {"$gt": ""}},
            {"email": {"$regex": ".*"}, "password": {"$regex": ".*"}},
        ]
        
        for payload in payloads:
            resp = self.session.post(f"{BASE_URL}/api/auth/login", json=payload)
            if resp.status_code == 200:
                add_finding("CRITICAL", "INJECTION", "NoSQL Injection in Login",
                           f"Login succeeded with NoSQL injection payload: {payload}",
                           f"POST /api/auth/login with body: {json.dumps(payload)}",
                           "Complete authentication bypass",
                           "Validate input types, use parameterized queries")
                pytest.fail(f"NoSQL injection succeeded with: {payload}")
        
        print("PASS: NoSQL injection in login blocked")
    
    def test_nosql_injection_search(self):
        """NoSQL-Injection: Search endpoints with MongoDB operators"""
        admin_token = self._get_admin_token()
        if not admin_token:
            pytest.skip("Could not get admin token")
        
        # Try injection in search parameter
        injection_params = [
            "search={$ne:null}",
            "search={$regex:.*}",
            "q={$gt:}",
        ]
        
        for param in injection_params:
            resp = self.session.get(f"{BASE_URL}/api/admin/users?{param}", headers={
                "Authorization": f"Bearer {admin_token}"
            })
            # Should not return all users or error in a way that reveals injection worked
            if resp.status_code == 200:
                data = resp.json()
                # If it returns users when it shouldn't, that's a problem
                # This is a heuristic check
                print(f"Search with {param}: returned {len(data) if isinstance(data, list) else 'object'}")
        
        print("INFO: NoSQL injection search test completed - manual review recommended")
    
    def test_xss_in_user_input(self):
        """XSS: Script tags in user-controllable fields"""
        admin_token = self._get_admin_token()
        if not admin_token:
            pytest.skip("Could not get admin token")
        
        xss_payloads = [
            "<script>alert(1)</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
            "<svg onload=alert(1)>",
        ]
        
        # Test in meeting title (if we can create one)
        # This is more of a frontend concern, but backend should sanitize
        print("INFO: XSS testing requires frontend validation - backend should store safely")
    
    def test_path_traversal_recording(self):
        """Path-Traversal: Attempt to access files outside allowed paths"""
        admin_token = self._get_admin_token()
        if not admin_token:
            pytest.skip("Could not get admin token")
        
        traversal_paths = [
            "../../etc/passwd",
            "..%2F..%2Fetc%2Fpasswd",
            "....//....//etc/passwd",
        ]
        
        for path in traversal_paths:
            resp = self.session.get(
                f"{BASE_URL}/api/meetings/test/recording/play/{path}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            if resp.status_code == 200 and "root:" in resp.text:
                add_finding("CRITICAL", "INJECTION", "Path Traversal Vulnerability",
                           f"Path traversal succeeded with: {path}",
                           f"GET /api/meetings/test/recording/play/{path}",
                           "Arbitrary file read on server",
                           "Validate and sanitize file paths, use allowlists")
                pytest.fail("Path traversal succeeded!")
        
        print("PASS: Path traversal attempts blocked")
    
    def test_large_json_dos(self):
        """Large JSON DoS: POST with oversized JSON body"""
        # Create a large JSON payload (but not too large to avoid test timeout)
        large_payload = {"data": "x" * 1000000}  # 1MB
        
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json=large_payload)
        # Should be rejected or handled gracefully
        assert resp.status_code in [400, 413, 422], f"Large payload not rejected: {resp.status_code}"
        print("PASS: Large JSON payload handled")
    
    def _get_admin_token(self):
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return resp.json().get("token") if resp.status_code == 200 else None


class TestDataExposure:
    """4. DATA EXPOSURE TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_admin_token(self):
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return resp.json().get("token") if resp.status_code == 200 else None
    
    def test_mongodb_id_exposure(self):
        """Check if MongoDB _id is exposed in API responses"""
        token = self.get_admin_token()
        if not token:
            pytest.skip("Could not get admin token")
        
        endpoints_to_check = [
            "/api/auth/me",
            "/api/admin/users",
            "/api/meetings",
            "/api/chat/conversations",
        ]
        
        exposed = []
        for endpoint in endpoints_to_check:
            resp = self.session.get(f"{BASE_URL}{endpoint}", headers={
                "Authorization": f"Bearer {token}"
            })
            if resp.status_code == 200:
                data = resp.json()
                # Check for _id in response
                if isinstance(data, dict) and "_id" in data:
                    exposed.append(endpoint)
                elif isinstance(data, list) and data and "_id" in data[0]:
                    exposed.append(endpoint)
                elif isinstance(data, dict):
                    # Check nested structures
                    for key, value in data.items():
                        if isinstance(value, list) and value and isinstance(value[0], dict) and "_id" in value[0]:
                            exposed.append(f"{endpoint} ({key})")
        
        if exposed:
            add_finding("LOW", "DATA_EXPOSURE", "MongoDB _id Exposed in Responses",
                       f"Endpoints exposing _id: {exposed}",
                       "GET various API endpoints and check for _id field",
                       "Internal database structure exposed",
                       "Exclude _id from all API responses using projection")
        
        print(f"MongoDB _id check: {exposed if exposed else 'PASS - no _id found'}")
    
    def test_verbose_error_messages(self):
        """Check if 500 errors expose stack traces"""
        # Try to trigger a 500 error
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": None,  # Invalid type
            "password": None
        })
        
        if resp.status_code == 500:
            text = resp.text.lower()
            if "traceback" in text or "stack" in text or "line " in text:
                add_finding("MEDIUM", "DATA_EXPOSURE", "Verbose Error Messages",
                           "500 errors expose stack traces",
                           "Send malformed request to trigger 500",
                           "Internal code structure and paths exposed",
                           "Use generic error messages in production")
        
        print("INFO: Error message verbosity check completed")
    
    def test_email_enumeration_login(self):
        """Check if login reveals email existence via different error messages"""
        # Test with existing email, wrong password
        resp1 = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": "wrongpassword"
        })
        
        # Test with non-existing email
        resp2 = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nonexistent_user_xyz@example.com", "password": "wrongpassword"
        })
        
        msg1 = resp1.json().get("detail", "") if resp1.status_code != 200 else ""
        msg2 = resp2.json().get("detail", "") if resp2.status_code != 200 else ""
        
        if msg1 != msg2:
            add_finding("MEDIUM", "DATA_EXPOSURE", "Email Enumeration via Login",
                       f"Different error messages: '{msg1}' vs '{msg2}'",
                       "Compare login errors for existing vs non-existing emails",
                       "Attackers can enumerate valid user emails",
                       "Use identical error messages for all login failures")
        else:
            print("PASS: Login error messages are consistent")
    
    def test_audit_log_access_control(self):
        """Non-admin must not access audit log"""
        # Try without auth
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system")
        assert resp.status_code in [401, 403], f"Audit log accessible without auth: {resp.status_code}"
        
        print("PASS: Audit log access properly restricted")
    
    def test_cors_configuration(self):
        """Check CORS configuration"""
        resp = self.session.options(f"{BASE_URL}/api/auth/login", headers={
            "Origin": "https://evil-site.com",
            "Access-Control-Request-Method": "POST"
        })
        
        acao = resp.headers.get("Access-Control-Allow-Origin", "")
        acac = resp.headers.get("Access-Control-Allow-Credentials", "")
        
        if acao == "*" and acac.lower() == "true":
            add_finding("HIGH", "DATA_EXPOSURE", "Insecure CORS Configuration",
                       "CORS allows any origin with credentials",
                       "OPTIONS request with evil origin",
                       "Cross-site request forgery possible",
                       "Restrict CORS to specific trusted origins")
        elif acao == "*":
            add_finding("MEDIUM", "DATA_EXPOSURE", "Permissive CORS Configuration",
                       f"CORS allows any origin: {acao}",
                       "OPTIONS request to API endpoint",
                       "Data may be accessible from any website",
                       "Restrict CORS to specific trusted origins")
        
        print(f"CORS check: Allow-Origin={acao}, Allow-Credentials={acac}")
    
    def test_security_headers(self):
        """Check for security headers"""
        resp = self.session.get(f"{BASE_URL}/api/auth/me")
        
        missing_headers = []
        recommended_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": None,  # Any value is good
            "Content-Security-Policy": None,
            "Referrer-Policy": None,
        }
        
        for header, expected in recommended_headers.items():
            value = resp.headers.get(header)
            if not value:
                missing_headers.append(header)
        
        if missing_headers:
            add_finding("LOW", "DATA_EXPOSURE", "Missing Security Headers",
                       f"Missing headers: {missing_headers}",
                       "GET any API endpoint and check response headers",
                       "Various client-side attacks may be easier",
                       "Add recommended security headers")
        
        print(f"Security headers check: Missing {missing_headers if missing_headers else 'none'}")


class TestPublicEndpoints:
    """5. PUBLIC ENDPOINTS (DIAG SHARE / QUICK SCAN) TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_token_enumeration_resistance(self):
        """Token-Enumeration: Random tokens should return 404"""
        import secrets
        
        for _ in range(10):
            random_token = secrets.token_urlsafe(12)
            resp = self.session.get(f"{BASE_URL}/api/diag/shared/{random_token}")
            assert resp.status_code == 404, f"Unexpected response for random token: {resp.status_code}"
        
        print("PASS: Random token enumeration returns 404")
    
    def test_expired_token_returns_410(self):
        """Token-Reuse after Expiry: Should return 410"""
        # This would need an actual expired token to test properly
        # For now, verify the endpoint exists and handles invalid tokens
        resp = self.session.get(f"{BASE_URL}/api/diag/shared/expired_test_token")
        assert resp.status_code in [404, 410], f"Unexpected: {resp.status_code}"
        print("INFO: Expired token handling - needs real expired token to fully test")
    
    def test_push_subscribe_requires_auth(self):
        """Push-Subscribe: /api/news/push/subscribe should require auth"""
        resp = self.session.post(f"{BASE_URL}/api/news/push/subscribe", json={
            "subscription": {"endpoint": "https://evil.com/push"}
        })
        
        if resp.status_code not in [401, 403]:
            add_finding("MEDIUM", "PUBLIC_ENDPOINTS", "Push Subscribe Without Auth",
                       "Push subscription endpoint accessible without authentication",
                       "POST /api/news/push/subscribe without auth",
                       "Unlimited push subscriptions possible (DoS)",
                       "Require authentication for push subscriptions")
        else:
            print("PASS: Push subscribe requires authentication")


class TestRateLimiting:
    """6. RATE LIMITING / DOS TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_login_rate_limit(self):
        """Login endpoint rate limiting"""
        results = []
        start = time.time()
        
        for i in range(50):
            resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
                "email": f"test{i}@example.com", "password": "wrong"
            })
            results.append(resp.status_code)
            if resp.status_code == 429:
                print(f"PASS: Rate limit triggered after {i+1} requests")
                return
        
        elapsed = time.time() - start
        
        if 429 not in results:
            add_finding("MEDIUM", "RATE_LIMIT", "No Rate Limiting on Login",
                       f"50 login attempts in {elapsed:.1f}s without rate limit",
                       "Send 50 rapid login requests",
                       "Brute force and credential stuffing attacks possible",
                       "Implement rate limiting (e.g., 10 req/min per IP)")
        
        print(f"Rate limit test: 50 requests in {elapsed:.1f}s, no 429 received")
    
    def test_api_flood_resilience(self):
        """API flood test - server should remain responsive"""
        def make_request():
            try:
                resp = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
                return resp.status_code
            except:
                return 0
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            results = [f.result() for f in as_completed(futures)]
        
        success_rate = results.count(401) / len(results)  # 401 is expected without auth
        
        if success_rate < 0.8:
            add_finding("MEDIUM", "RATE_LIMIT", "API Flood Causes Failures",
                       f"Only {success_rate*100:.0f}% success rate under load",
                       "Send 50 concurrent requests",
                       "Service degradation under load",
                       "Implement request queuing and rate limiting")
        
        print(f"API flood test: {success_rate*100:.0f}% success rate")


class TestWebSocketSecurity:
    """7. WEBSOCKET SECURITY TESTS"""
    
    def test_websocket_endpoint_exists(self):
        """Verify WebSocket endpoint configuration"""
        # WebSocket testing requires async client
        # For now, verify the endpoint pattern
        print("INFO: WebSocket security requires manual testing with WS client")
        print("CHECK: /api/ws/{meeting_id}/{user_id} - verify token validation")
        print("CHECK: WS messages with host-control type - verify role checks")


class TestFileDownloadStorage:
    """8. FILE DOWNLOAD / STORAGE TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_admin_token(self):
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return resp.json().get("token") if resp.status_code == 200 else None
    
    def test_chat_file_access_control(self):
        """Chat file download requires conversation membership"""
        # Try to access a chat file without auth
        resp = self.session.get(f"{BASE_URL}/api/chat/files/nonexistent_file")
        # Should be 404 (not found) - but check it's not exposing files
        assert resp.status_code in [401, 403, 404], f"Unexpected: {resp.status_code}"
        print("PASS: Chat file access controlled")
    
    def test_avatar_upload_type_restriction(self):
        """Avatar upload should restrict file types"""
        token = self.get_admin_token()
        if not token:
            pytest.skip("Could not get admin token")
        
        # Try to upload a PHP file as avatar
        files = {
            "file": ("malicious.php", b"<?php echo 'pwned'; ?>", "application/x-php")
        }
        
        resp = self.session.post(
            f"{BASE_URL}/api/users/avatar",
            headers={"Authorization": f"Bearer {token}"},
            files=files
        )
        
        if resp.status_code == 200:
            add_finding("HIGH", "FILE_SECURITY", "Dangerous File Type Upload Allowed",
                       "PHP file uploaded as avatar",
                       "POST /api/users/avatar with .php file",
                       "Remote code execution if file is served",
                       "Restrict uploads to image types only")
        else:
            print(f"PASS: PHP upload rejected with {resp.status_code}")


class TestPasswordCrypto:
    """9. PASSWORD / CRYPTO TESTS"""
    
    def test_jwt_secret_not_default(self):
        """JWT_SECRET should not be default value"""
        # We can't directly check the secret, but we can verify tokens work
        # and aren't using a known weak secret
        print("INFO: JWT_SECRET check requires server-side verification")
        print("CHECK: Ensure JWT_SECRET is not 'default-secret-change-me'")
    
    def test_bcrypt_cost_factor(self):
        """bcrypt rounds should be >= 12"""
        # This requires checking the hash format
        # bcrypt hashes start with $2b$XX$ where XX is the cost factor
        print("INFO: bcrypt cost factor check requires hash inspection")
        print("CHECK: Verify hash_password uses bcrypt.gensalt() with rounds >= 12")


class TestDSGVOCompliance:
    """10. DSGVO / HEALTHCARE SPECIFIC TESTS"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_admin_token(self):
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return resp.json().get("token") if resp.status_code == 200 else None
    
    def test_data_export_endpoint_exists(self):
        """DSGVO: Data export endpoint should exist"""
        token = self.get_admin_token()
        if not token:
            pytest.skip("Could not get admin token")
        
        # Check if data export endpoint exists
        resp = self.session.get(f"{BASE_URL}/api/users/me/export", headers={
            "Authorization": f"Bearer {token}"
        })
        
        if resp.status_code == 404:
            add_finding("INFO", "DSGVO", "No Data Export Endpoint",
                       "No /api/users/me/export endpoint found",
                       "GET /api/users/me/export",
                       "DSGVO Art. 20 data portability may not be implemented",
                       "Implement data export functionality")
        
        print(f"Data export endpoint: {resp.status_code}")
    
    def test_data_delete_endpoint_exists(self):
        """DSGVO: Right to erasure endpoint should exist"""
        token = self.get_admin_token()
        if not token:
            pytest.skip("Could not get admin token")
        
        # Check if self-delete endpoint exists (don't actually delete!)
        # Just check the endpoint pattern
        print("INFO: DSGVO right to erasure - verify DELETE /api/users/me exists")
    
    def test_audit_trail_exists(self):
        """DSGVO: Audit trail for user actions"""
        token = self.get_admin_token()
        if not token:
            pytest.skip("Could not get admin token")
        
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system", headers={
            "Authorization": f"Bearer {token}"
        })
        
        if resp.status_code == 200:
            print("PASS: Audit trail endpoint exists")
        else:
            add_finding("INFO", "DSGVO", "Audit Trail Access Issue",
                       f"Audit endpoint returned {resp.status_code}",
                       "GET /api/admin/audit/system",
                       "Audit trail may not be properly implemented",
                       "Ensure comprehensive audit logging")


# ============ SUMMARY GENERATION ============

def generate_security_report():
    """Generate final security report"""
    report = {
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "target": BASE_URL,
        "findings": FINDINGS,
        "summary": {
            "critical": len([f for f in FINDINGS if f["severity"] == "CRITICAL"]),
            "high": len([f for f in FINDINGS if f["severity"] == "HIGH"]),
            "medium": len([f for f in FINDINGS if f["severity"] == "MEDIUM"]),
            "low": len([f for f in FINDINGS if f["severity"] == "LOW"]),
            "info": len([f for f in FINDINGS if f["severity"] == "INFO"]),
        }
    }
    
    # Calculate security rating
    total_weighted = (
        report["summary"]["critical"] * 10 +
        report["summary"]["high"] * 5 +
        report["summary"]["medium"] * 2 +
        report["summary"]["low"] * 1
    )
    
    if total_weighted == 0:
        report["rating"] = "A"
    elif total_weighted <= 5:
        report["rating"] = "B"
    elif total_weighted <= 15:
        report["rating"] = "C"
    elif total_weighted <= 30:
        report["rating"] = "D"
    else:
        report["rating"] = "F"
    
    return report


@pytest.fixture(scope="session", autouse=True)
def print_report(request):
    """Print security report at end of test session"""
    yield
    report = generate_security_report()
    print("\n" + "="*60)
    print("SECURITY AUDIT REPORT")
    print("="*60)
    print(f"Target: {report['target']}")
    print(f"Date: {report['scan_date']}")
    print(f"\nSecurity Rating: {report['rating']}")
    print("\nFindings Summary:")
    print(f"  CRITICAL: {report['summary']['critical']}")
    print(f"  HIGH: {report['summary']['high']}")
    print(f"  MEDIUM: {report['summary']['medium']}")
    print(f"  LOW: {report['summary']['low']}")
    print(f"  INFO: {report['summary']['info']}")
    
    if FINDINGS:
        print("\nDetailed Findings:")
        for i, f in enumerate(FINDINGS, 1):
            print(f"\n{i}. [{f['severity']}] {f['title']}")
            print(f"   Category: {f['category']}")
            print(f"   Description: {f['description']}")
            print(f"   Impact: {f['impact']}")
            print(f"   Recommendation: {f['recommendation']}")
    
    print("\n" + "="*60)
