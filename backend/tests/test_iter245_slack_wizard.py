"""
Iter 245 — Slack-Webhook Setup-Wizard Tests
Tests for:
1. POST /api/users/me/office-days/slack/test endpoint
   - Without configured URL → 400 'Kein Slack-Webhook konfiguriert'
   - With non-https://hooks.slack.com/ URL → 200 with {success:false, error:'URL beginnt nicht mit https://hooks.slack.com/'}
   - With invalid token URL → 200 with {success:false, error:'HTTP <code>...'}
   - Never 500 (failure-tolerant)
2. Regression: Iter 244 features (Slack-URL Privacy, Catering-Cancel)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestIter245SlackTest:
    """Tests for the new Slack test endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Store original config to restore later
        cfg_resp = requests.get(f"{BASE_URL}/api/users/me/office-days", headers=self.headers)
        self.original_cfg = cfg_resp.json() if cfg_resp.status_code == 200 else {}
        yield
        # Cleanup: restore original config (clear slack if we set it)
        # Note: We can't restore the original slack_webhook_url since it's not returned
        # Just clear it to be safe
        requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": self.original_cfg.get("weekdays", []),
            "preferred_desk_id": self.original_cfg.get("preferred_desk_id"),
            "start_time": self.original_cfg.get("start_time", "08:00"),
            "end_time": self.original_cfg.get("end_time", "17:00"),
            "title": self.original_cfg.get("title", "Bürotag"),
            "slack_webhook_url": "",  # Clear any test webhook
        })
    
    def test_slack_test_without_configured_url_returns_400(self):
        """Test: Without configured URL → 400 'Kein Slack-Webhook konfiguriert'"""
        # First ensure no slack webhook is configured
        requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": [],
            "slack_webhook_url": "",
        })
        
        # Now test the endpoint
        resp = requests.post(f"{BASE_URL}/api/users/me/office-days/slack/test", headers=self.headers)
        
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "Kein Slack-Webhook konfiguriert" in data.get("detail", ""), f"Unexpected error: {data}"
        print("PASS: Without configured URL returns 400 with correct message")
    
    def test_slack_test_with_non_slack_url_returns_success_false(self):
        """Test: With non-https://hooks.slack.com/ URL → 200 with {success:false, error:'URL beginnt nicht mit https://hooks.slack.com/'}"""
        # Configure a non-Slack URL
        put_resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "slack_webhook_url": "https://example.com/webhook",
        })
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        
        # Now test the endpoint
        resp = requests.post(f"{BASE_URL}/api/users/me/office-days/slack/test", headers=self.headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") == False, f"Expected success=false, got: {data}"
        assert "URL beginnt nicht mit https://hooks.slack.com/" in data.get("error", ""), f"Unexpected error: {data}"
        print("PASS: Non-Slack URL returns 200 with success=false and correct error")
    
    def test_slack_test_with_invalid_token_url_returns_success_false_with_http_error(self):
        """Test: With invalid token URL (z.B. T0/B0/INVALID) → 200 with {success:false, error:'HTTP <code>...'}"""
        # Configure an invalid Slack URL (valid format but invalid token)
        put_resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "slack_webhook_url": "https://hooks.slack.com/services/T0/B0/INVALID",
        })
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        
        # Now test the endpoint
        resp = requests.post(f"{BASE_URL}/api/users/me/office-days/slack/test", headers=self.headers)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") == False, f"Expected success=false, got: {data}"
        # Error should contain HTTP status code
        error = data.get("error", "")
        assert "HTTP" in error or "404" in error or "403" in error or "invalid" in error.lower(), \
            f"Expected HTTP error message, got: {error}"
        print(f"PASS: Invalid token URL returns 200 with success=false, error='{error}'")
    
    def test_slack_test_never_returns_500(self):
        """Test: Failure-tolerant — niemals 500"""
        # Test with various edge cases that might cause 500
        test_urls = [
            "https://hooks.slack.com/services/",  # Empty tokens
            "https://hooks.slack.com/services/T0/B0/",  # Missing last token
            "https://hooks.slack.com/services/INVALID",  # Single invalid token
        ]
        
        for url in test_urls:
            put_resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
                "weekdays": ["mon"],
                "slack_webhook_url": url,
            })
            assert put_resp.status_code == 200, f"PUT failed for {url}: {put_resp.text}"
            
            resp = requests.post(f"{BASE_URL}/api/users/me/office-days/slack/test", headers=self.headers)
            
            assert resp.status_code != 500, f"Got 500 for URL '{url}': {resp.text}"
            assert resp.status_code in [200, 400], f"Unexpected status {resp.status_code} for URL '{url}'"
            print(f"PASS: URL '{url}' did not cause 500 (got {resp.status_code})")
        
        print("PASS: Slack test endpoint never returns 500")
    
    def test_slack_test_requires_auth(self):
        """Test: Endpoint requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/users/me/office-days/slack/test")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print("PASS: Slack test endpoint requires authentication")


class TestIter244Regression:
    """Regression tests for Iter 244 features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_slack_webhook_privacy_url_not_returned(self):
        """Regression: GET /api/users/me/office-days returns slack_webhook_configured=true, NOT the URL"""
        # First configure a slack webhook
        put_resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "slack_webhook_url": "https://hooks.slack.com/services/T0/B0/TEST",
        })
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        
        # Now GET and verify privacy
        get_resp = requests.get(f"{BASE_URL}/api/users/me/office-days", headers=self.headers)
        assert get_resp.status_code == 200, f"GET failed: {get_resp.text}"
        
        data = get_resp.json()
        assert data.get("slack_webhook_configured") == True, f"Expected slack_webhook_configured=true, got: {data}"
        assert "slack_webhook_url" not in data, f"URL should NOT be returned for privacy: {data}"
        print("PASS: Slack webhook URL is not returned (privacy preserved)")
    
    def test_slack_webhook_clear_works(self):
        """Regression: PUT with slack_webhook_url='' clears it"""
        # First configure a slack webhook
        put_resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "slack_webhook_url": "https://hooks.slack.com/services/T0/B0/TEST",
        })
        assert put_resp.status_code == 200
        
        # Verify it's configured
        get_resp = requests.get(f"{BASE_URL}/api/users/me/office-days", headers=self.headers)
        assert get_resp.json().get("slack_webhook_configured") == True
        
        # Now clear it
        clear_resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "slack_webhook_url": "",
        })
        assert clear_resp.status_code == 200
        
        # Verify it's cleared
        get_resp2 = requests.get(f"{BASE_URL}/api/users/me/office-days", headers=self.headers)
        assert get_resp2.json().get("slack_webhook_configured") == False, \
            f"Expected slack_webhook_configured=false after clear, got: {get_resp2.json()}"
        print("PASS: Slack webhook can be cleared")
    
    def test_skip_reasons_endpoint_still_works(self):
        """Regression: GET /api/office-days/skip-reasons still returns 4 reasons"""
        resp = requests.get(f"{BASE_URL}/api/office-days/skip-reasons", headers=self.headers)
        assert resp.status_code == 200, f"GET failed: {resp.text}"
        
        data = resp.json()
        reasons = data.get("reasons", [])
        assert len(reasons) == 4, f"Expected 4 skip reasons, got {len(reasons)}: {reasons}"
        
        reason_ids = [r["id"] for r in reasons]
        expected_ids = ["krank", "homeoffice", "urlaub", "sonstiges"]
        for eid in expected_ids:
            assert eid in reason_ids, f"Missing skip reason: {eid}"
        
        print("PASS: Skip reasons endpoint returns all 4 reasons")
    
    def test_office_days_generate_returns_slack_notified_field(self):
        """Regression: POST /api/users/me/office-days/generate returns slack_notified field"""
        # First we need a desk to generate bookings
        desks_resp = requests.get(f"{BASE_URL}/api/resources?type=desk", headers=self.headers)
        if desks_resp.status_code != 200 or not desks_resp.json():
            pytest.skip("No desks available for testing")
        
        desks = desks_resp.json()
        if not desks:
            pytest.skip("No desks available for testing")
        
        desk_id = desks[0].get("resource_id")
        
        # Configure office days
        put_resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "preferred_desk_id": desk_id,
            "start_time": "08:00",
            "end_time": "17:00",
            "slack_webhook_url": "",  # No slack configured
        })
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        
        # Generate bookings
        gen_resp = requests.post(f"{BASE_URL}/api/users/me/office-days/generate", 
                                 headers=self.headers, json={"weeks": 1})
        assert gen_resp.status_code == 200, f"Generate failed: {gen_resp.text}"
        
        data = gen_resp.json()
        assert "slack_notified" in data, f"Missing slack_notified field: {data}"
        # Without slack configured, should be false
        assert data.get("slack_notified") == False, f"Expected slack_notified=false, got: {data}"
        print("PASS: Generate endpoint returns slack_notified field")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
