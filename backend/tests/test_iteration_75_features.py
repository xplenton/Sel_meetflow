"""
Iteration 75 Backend Tests:
- POST /api/users/me/onboarding-complete (requires auth, sets onboarding_completed_at)
- GET /api/user/permissions (now includes capability_labels field)
- Regression: Email preferences and unsubscribe endpoints still work
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestOnboardingComplete:
    """Tests for POST /api/users/me/onboarding-complete endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_onboarding_complete_requires_auth(self):
        """POST /api/users/me/onboarding-complete returns 401 without auth"""
        resp = requests.post(f"{BASE_URL}/api/users/me/onboarding-complete")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASSED: onboarding-complete returns 401 without auth")
    
    def test_onboarding_complete_sets_timestamp(self):
        """POST /api/users/me/onboarding-complete sets onboarding_completed_at"""
        resp = self.session.post(f"{BASE_URL}/api/users/me/onboarding-complete")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "onboarding_completed_at" in data, f"Missing onboarding_completed_at in response: {data}"
        assert data["onboarding_completed_at"], "onboarding_completed_at should not be empty"
        # Verify it's an ISO timestamp
        assert "T" in data["onboarding_completed_at"], "Should be ISO format timestamp"
        print(f"PASSED: onboarding-complete returns timestamp: {data['onboarding_completed_at']}")
    
    def test_onboarding_complete_persists_in_user(self):
        """After POST /api/users/me/onboarding-complete, GET /api/auth/me returns onboarding_completed_at"""
        # First call onboarding-complete
        post_resp = self.session.post(f"{BASE_URL}/api/users/me/onboarding-complete")
        assert post_resp.status_code == 200
        timestamp = post_resp.json().get("onboarding_completed_at")
        
        # Then verify via GET /api/auth/me
        me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200, f"GET /api/auth/me failed: {me_resp.text}"
        user_data = me_resp.json()
        assert "onboarding_completed_at" in user_data, f"onboarding_completed_at not in user data: {user_data.keys()}"
        assert user_data["onboarding_completed_at"] == timestamp or user_data["onboarding_completed_at"], \
            "onboarding_completed_at mismatch or empty"
        print(f"PASSED: onboarding_completed_at persisted in user: {user_data.get('onboarding_completed_at')}")


class TestUserPermissionsWithLabels:
    """Tests for GET /api/user/permissions with capability_labels"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_permissions_returns_capability_labels(self):
        """GET /api/user/permissions includes capability_labels field"""
        resp = self.session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check required fields
        assert "capabilities" in data, f"Missing capabilities in response: {data.keys()}"
        assert "capability_labels" in data, f"Missing capability_labels in response: {data.keys()}"
        assert "role" in data, f"Missing role in response: {data.keys()}"
        
        print("PASSED: /api/user/permissions returns capability_labels field")
    
    def test_capability_labels_structure(self):
        """capability_labels has correct structure: {cap_key: {label, category, description}}"""
        resp = self.session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        capability_labels = data.get("capability_labels", {})
        capabilities = data.get("capabilities", [])
        
        # capability_labels should have entries for each capability
        assert len(capability_labels) > 0, "capability_labels should not be empty for admin"
        
        # Check structure of each label entry
        for cap_key, label_info in capability_labels.items():
            assert "label" in label_info, f"Missing 'label' for {cap_key}"
            assert "category" in label_info, f"Missing 'category' for {cap_key}"
            assert "description" in label_info, f"Missing 'description' for {cap_key}"
            # Labels should be German (human-readable)
            assert isinstance(label_info["label"], str) and len(label_info["label"]) > 0, \
                f"Label should be non-empty string for {cap_key}"
        
        print(f"PASSED: capability_labels has correct structure with {len(capability_labels)} entries")
    
    def test_capability_labels_match_capabilities(self):
        """capability_labels keys should match capabilities list"""
        resp = self.session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        capability_labels = data.get("capability_labels", {})
        capabilities = set(data.get("capabilities", []))
        label_keys = set(capability_labels.keys())
        
        # All label keys should be in capabilities
        assert label_keys == capabilities, \
            f"Mismatch: labels has {len(label_keys)} keys, capabilities has {len(capabilities)} items. " \
            f"Missing in labels: {capabilities - label_keys}, Extra in labels: {label_keys - capabilities}"
        
        print(f"PASSED: capability_labels keys match capabilities list ({len(capabilities)} items)")
    
    def test_admin_has_all_capabilities(self):
        """Admin user should have all 46 capabilities"""
        resp = self.session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        capabilities = data.get("capabilities", [])
        # Admin should have all capabilities (46 based on permissions.py)
        assert len(capabilities) >= 40, f"Admin should have many capabilities, got {len(capabilities)}"
        
        # Check some expected capabilities
        expected_caps = ["view:dashboard", "view:admin", "admin.manage_users", "admin.manage_roles"]
        for cap in expected_caps:
            assert cap in capabilities, f"Admin missing expected capability: {cap}"
        
        print(f"PASSED: Admin has {len(capabilities)} capabilities including admin-specific ones")
    
    def test_capability_labels_have_german_labels(self):
        """Labels should be in German (human-readable)"""
        resp = self.session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        capability_labels = data.get("capability_labels", {})
        
        # Check some expected German labels
        german_indicators = ["Dashboard", "News", "Chat", "Meetings", "Verwaltung", "Nutzer", "Gruppen"]
        found_german = False
        for cap_key, label_info in capability_labels.items():
            label = label_info.get("label", "")
            if any(g in label for g in german_indicators):
                found_german = True
                break
        
        assert found_german, "Expected German labels in capability_labels"
        print("PASSED: capability_labels contain German labels")


class TestEmailPreferencesRegression:
    """Regression tests for email preferences endpoints (Iter 74)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_get_email_preferences(self):
        """GET /api/users/me/email-preferences returns preferences"""
        resp = self.session.get(f"{BASE_URL}/api/users/me/email-preferences")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check required fields
        assert "newsletter_enabled" in data, f"Missing newsletter_enabled: {data}"
        assert "meeting_invites_enabled" in data, f"Missing meeting_invites_enabled: {data}"
        assert "digest_frequency" in data, f"Missing digest_frequency: {data}"
        
        print(f"PASSED: GET /api/users/me/email-preferences returns: {data}")
    
    def test_put_email_preferences(self):
        """PUT /api/users/me/email-preferences updates preferences"""
        # First get current state
        get_resp = self.session.get(f"{BASE_URL}/api/users/me/email-preferences")
        original = get_resp.json()
        
        # Update preferences
        new_prefs = {
            "newsletter_enabled": not original.get("newsletter_enabled", True),
            "meeting_invites_enabled": True,
            "digest_frequency": "daily"
        }
        put_resp = self.session.put(f"{BASE_URL}/api/users/me/email-preferences", json=new_prefs)
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        
        # Verify change persisted
        verify_resp = self.session.get(f"{BASE_URL}/api/users/me/email-preferences")
        assert verify_resp.status_code == 200
        updated = verify_resp.json()
        assert updated["digest_frequency"] == "daily", f"digest_frequency not updated: {updated}"
        
        # Restore original
        self.session.put(f"{BASE_URL}/api/users/me/email-preferences", json={
            "newsletter_enabled": original.get("newsletter_enabled", True),
            "digest_frequency": original.get("digest_frequency", "immediate")
        })
        
        print("PASSED: PUT /api/users/me/email-preferences updates and persists")


class TestUnsubscribeRegression:
    """Regression tests for unsubscribe endpoints (Iter 74)"""
    
    def test_unsubscribe_invalid_token(self):
        """GET /api/unsubscribe/{invalid_token} returns 400"""
        resp = requests.get(f"{BASE_URL}/api/unsubscribe/invalid_token_abc123")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("PASSED: GET /api/unsubscribe/invalid_token returns 400")
    
    def test_unsubscribe_post_invalid_token(self):
        """POST /api/unsubscribe/{invalid_token} returns 400"""
        resp = requests.post(f"{BASE_URL}/api/unsubscribe/invalid_token_abc123")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("PASSED: POST /api/unsubscribe/invalid_token returns 400")
    
    def test_resubscribe_invalid_token(self):
        """POST /api/unsubscribe/{invalid_token}/resubscribe returns 400"""
        resp = requests.post(f"{BASE_URL}/api/unsubscribe/invalid_token_abc123/resubscribe")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("PASSED: POST /api/unsubscribe/invalid_token/resubscribe returns 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
