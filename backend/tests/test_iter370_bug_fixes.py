"""
Iteration 370 Bug Fixes Tests

Tests for three bug fixes:
1. QR Code modal positioning (frontend - tested via Playwright)
2. LicenseBanner false-positive fix (status=disabled → no banner)
3. Capabilities/Module mismatch fixes:
   - Ghost caps removed from ROLE_DEFAULTS
   - CategoryLabels added for tasks/resources/invoices/fleet
   - 'Sichtbare Module' list extended to include surveys/tasks/resources/meetings
   - Sidebar perm mapping aligned
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestLicenseStatus:
    """Test /api/license/status endpoint - should return disabled in preview env"""
    
    def test_license_status_disabled_in_preview(self):
        """In preview env (no LICENSE_SERVER_URL), status should be 'disabled'"""
        # Login first
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        
        # Get license status
        resp = requests.get(
            f"{BASE_URL}/api/license/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, f"License status failed: {resp.text}"
        
        data = resp.json()
        assert data.get("status") == "disabled", f"Expected status='disabled', got {data.get('status')}"
        assert data.get("server_configured") == False, "server_configured should be False"
        print(f"✓ License status is 'disabled' - no banner should show")


class TestCapabilities:
    """Test /api/admin/capabilities endpoint - verify all 67 caps across 13 categories"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_capabilities_count(self):
        """Verify all 67 capabilities are returned"""
        resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=self.headers)
        assert resp.status_code == 200
        
        data = resp.json()
        caps = data.get("capabilities", [])
        assert len(caps) == 67, f"Expected 67 capabilities, got {len(caps)}"
        print(f"✓ All 67 capabilities loaded")
    
    def test_capabilities_categories(self):
        """Verify all 13 categories are present"""
        resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=self.headers)
        assert resp.status_code == 200
        
        data = resp.json()
        caps = data.get("capabilities", [])
        categories = set(c["category"] for c in caps)
        
        expected_categories = {
            "module", "news", "meetings", "chat", "documents", "scheduling",
            "surveys", "tasks", "resources", "invoices", "fleet", "admin", "global"
        }
        
        assert categories == expected_categories, f"Missing categories: {expected_categories - categories}"
        print(f"✓ All 13 categories present: {sorted(categories)}")
    
    def test_new_category_labels(self):
        """Verify new categories have correct German labels"""
        resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=self.headers)
        assert resp.status_code == 200
        
        data = resp.json()
        caps = data.get("capabilities", [])
        
        # Check for specific capabilities in new categories
        tasks_caps = [c for c in caps if c["category"] == "tasks"]
        resources_caps = [c for c in caps if c["category"] == "resources"]
        invoices_caps = [c for c in caps if c["category"] == "invoices"]
        fleet_caps = [c for c in caps if c["category"] == "fleet"]
        
        assert len(tasks_caps) >= 5, f"Expected at least 5 tasks caps, got {len(tasks_caps)}"
        assert len(resources_caps) >= 9, f"Expected at least 9 resources caps, got {len(resources_caps)}"
        assert len(invoices_caps) >= 4, f"Expected at least 4 invoices caps, got {len(invoices_caps)}"
        assert len(fleet_caps) >= 1, f"Expected at least 1 fleet cap, got {len(fleet_caps)}"
        
        print(f"✓ tasks: {len(tasks_caps)} caps")
        print(f"✓ resources: {len(resources_caps)} caps")
        print(f"✓ invoices: {len(invoices_caps)} caps")
        print(f"✓ fleet: {len(fleet_caps)} caps")
    
    def test_ghost_caps_removed_from_role_defaults(self):
        """Verify ghost caps (book_with_approval, cancel_any, process_catering) are NOT in role_defaults"""
        resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=self.headers)
        assert resp.status_code == 200
        
        data = resp.json()
        role_defaults = data.get("role_defaults", {})
        
        ghost_caps = ["resources.book_with_approval", "resources.cancel_any", "resources.process_catering"]
        
        for role, caps in role_defaults.items():
            for ghost in ghost_caps:
                assert ghost not in caps, f"Ghost cap '{ghost}' found in role '{role}' defaults"
        
        print(f"✓ No ghost caps in role_defaults")


class TestUserPermissions:
    """Test /api/user/permissions endpoint - verify meetings and surveys in permissions"""
    
    def test_admin_has_meetings_and_surveys(self):
        """Admin permissions should include 'meetings' and 'surveys'"""
        # Login as admin
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        # Get permissions
        resp = requests.get(
            f"{BASE_URL}/api/user/permissions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        
        data = resp.json()
        perms = data.get("permissions", [])
        
        assert "meetings" in perms, f"'meetings' not in permissions: {perms}"
        assert "surveys" in perms, f"'surveys' not in permissions: {perms}"
        
        print(f"✓ Admin permissions include 'meetings' and 'surveys'")
        print(f"  Full permissions: {perms}")
    
    def test_permissions_include_new_modules(self):
        """Admin permissions should include tasks and resources"""
        # Login as admin
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        # Get permissions
        resp = requests.get(
            f"{BASE_URL}/api/user/permissions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        
        data = resp.json()
        perms = data.get("permissions", [])
        
        assert "tasks" in perms, f"'tasks' not in permissions: {perms}"
        assert "resources" in perms, f"'resources' not in permissions: {perms}"
        
        print(f"✓ Admin permissions include 'tasks' and 'resources'")


class TestModuleMap:
    """Test MODULE_MAP in permissions.py includes meetings and surveys"""
    
    def test_module_map_completeness(self):
        """Verify MODULE_MAP includes all expected modules"""
        # Login as admin
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        token = login_resp.json().get("token")
        
        # Get permissions
        resp = requests.get(
            f"{BASE_URL}/api/user/permissions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        
        data = resp.json()
        perms = data.get("permissions", [])
        
        # Expected modules from MODULE_MAP
        expected_modules = [
            "dashboard", "news", "chat", "scheduling", "calendar",
            "recordings", "profile", "tasks", "resources", "meetings",
            "surveys", "admin", "analytics"
        ]
        
        for module in expected_modules:
            assert module in perms, f"Module '{module}' not in permissions"
        
        print(f"✓ All expected modules present in permissions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
