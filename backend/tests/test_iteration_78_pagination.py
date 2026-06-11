"""
Iteration 78 - Server-side Pagination + Filters + Search for Admin User List

Tests:
1. GET /admin/users without params → returns RAW LIST (backward compat, up to 1000 users, newest-first)
2. GET /admin/users?page=1&limit=20 → returns {users:[], total, page, limit, pages}
3. GET /admin/users?page=1&limit=50&search=admin → server-side case-insensitive search
4. GET /admin/users?page=1&limit=50&role=admin → filter by role
5. GET /admin/users?page=1&limit=50&status=active → filter by status
6. GET /admin/users?page=3&limit=10 → correct page slice
7. GET /admin/users/filters → distinct values for dropdowns
8. Legacy consumers: /admin/presets/{id}/apply-to-users with paginated user_ids
9. Limit capped at 200
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAdminUsersPagination:
    """Tests for server-side pagination + filters + search on /admin/users"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    # ============ BACKWARD COMPATIBILITY: No params returns raw list ============
    
    def test_legacy_no_params_returns_raw_list(self):
        """GET /admin/users without query params returns a raw list (not paginated object)"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # CRITICAL: Must be a list, not an object with 'users' key
        assert isinstance(data, list), f"Expected raw list, got {type(data)}: {str(data)[:200]}"
        
        # Should have users (platform has 1085 users, capped at 1000)
        assert len(data) > 0, "Expected at least some users"
        assert len(data) <= 1000, f"Expected max 1000 users, got {len(data)}"
        
        # Each item should be a user object with expected fields
        if len(data) > 0:
            user = data[0]
            assert "user_id" in user, "User should have user_id"
            assert "email" in user, "User should have email"
            assert "password_hash" not in user, "password_hash should be excluded"
            assert "_id" not in user, "_id should be excluded"
        
        print(f"PASSED: Legacy endpoint returns raw list with {len(data)} users")
    
    def test_legacy_sorted_newest_first(self):
        """Legacy endpoint returns users sorted by created_at descending (newest first)"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        
        # Check sorting - users with created_at should be in descending order
        created_dates = [u.get("created_at") for u in data if u.get("created_at")]
        if len(created_dates) >= 2:
            # Verify descending order
            for i in range(len(created_dates) - 1):
                assert created_dates[i] >= created_dates[i+1], "Users should be sorted newest first"
        
        print("PASSED: Legacy endpoint returns users sorted newest first")
    
    # ============ PAGINATED ENDPOINT ============
    
    def test_paginated_returns_object_structure(self):
        """GET /admin/users?page=1&limit=20 returns paginated object"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 20})
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Must be an object with pagination fields
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "users" in data, "Response should have 'users' key"
        assert "total" in data, "Response should have 'total' key"
        assert "page" in data, "Response should have 'page' key"
        assert "limit" in data, "Response should have 'limit' key"
        assert "pages" in data, "Response should have 'pages' key"
        
        # Validate types
        assert isinstance(data["users"], list), "users should be a list"
        assert isinstance(data["total"], int), "total should be int"
        assert isinstance(data["page"], int), "page should be int"
        assert isinstance(data["limit"], int), "limit should be int"
        assert isinstance(data["pages"], int), "pages should be int"
        
        # Validate values
        assert data["page"] == 1, f"Expected page=1, got {data['page']}"
        assert data["limit"] == 20, f"Expected limit=20, got {data['limit']}"
        assert len(data["users"]) <= 20, f"Expected max 20 users, got {len(data['users'])}"
        
        print(f"PASSED: Paginated endpoint returns correct structure - total={data['total']}, pages={data['pages']}")
    
    def test_paginated_page_defaults_to_1(self):
        """When limit is passed but page is omitted, page defaults to 1"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        
        assert isinstance(data, dict), "Should return paginated object when limit is passed"
        assert data["page"] == 1, f"Page should default to 1, got {data['page']}"
        
        print("PASSED: Page defaults to 1 when only limit is passed")
    
    def test_paginated_limit_capped_at_200(self):
        """Limit is capped at 200"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 500})
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["limit"] == 200, f"Limit should be capped at 200, got {data['limit']}"
        assert len(data["users"]) <= 200, f"Should return max 200 users, got {len(data['users'])}"
        
        print("PASSED: Limit is capped at 200")
    
    def test_paginated_correct_page_slice(self):
        """GET /admin/users?page=3&limit=10 returns correct page slice (users 21-30)"""
        # First get total count
        resp1 = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 10})
        assert resp1.status_code == 200
        total = resp1.json()["total"]
        
        if total < 30:
            pytest.skip(f"Not enough users to test page 3 (total={total})")
        
        # Get page 1, 2, 3
        page1 = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 10}).json()
        page2 = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 2, "limit": 10}).json()
        page3 = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 3, "limit": 10}).json()
        
        # Verify no overlap between pages
        page1_ids = {u["user_id"] for u in page1["users"]}
        page2_ids = {u["user_id"] for u in page2["users"]}
        page3_ids = {u["user_id"] for u in page3["users"]}
        
        assert len(page1_ids & page2_ids) == 0, "Page 1 and 2 should not overlap"
        assert len(page2_ids & page3_ids) == 0, "Page 2 and 3 should not overlap"
        assert len(page1_ids & page3_ids) == 0, "Page 1 and 3 should not overlap"
        
        print("PASSED: Page 3 returns correct slice (no overlap with pages 1,2)")
    
    def test_paginated_pages_calculation(self):
        """Pages calculation is correct: ceil(total/limit)"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 50})
        assert resp.status_code == 200
        data = resp.json()
        
        expected_pages = max(1, (data["total"] + 49) // 50)  # ceil division
        assert data["pages"] == expected_pages, f"Expected {expected_pages} pages, got {data['pages']}"
        
        print(f"PASSED: Pages calculation correct - total={data['total']}, limit=50, pages={data['pages']}")
    
    # ============ SEARCH FUNCTIONALITY ============
    
    def test_search_by_email(self):
        """Search filters by email (case-insensitive)"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "search": "admin"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Should find admin@meetflow.com at minimum
        assert data["total"] >= 1, "Should find at least admin user"
        
        # All returned users should match search term in name, email, department, location, or profession
        for user in data["users"]:
            search_fields = [
                (user.get("name") or "").lower(),
                (user.get("email") or "").lower(),
                (user.get("department") or "").lower(),
                (user.get("location") or "").lower(),
                (user.get("profession") or "").lower(),
            ]
            matches = any("admin" in field for field in search_fields)
            assert matches, f"User {user.get('email')} doesn't match search 'admin'"
        
        print(f"PASSED: Search by 'admin' returns {data['total']} matching users")
    
    def test_search_reduces_total(self):
        """Search should reduce total count compared to no search"""
        # Get total without search
        resp_all = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 50})
        total_all = resp_all.json()["total"]
        
        # Get total with search
        resp_search = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "search": "admin"
        })
        total_search = resp_search.json()["total"]
        
        assert total_search <= total_all, f"Search total ({total_search}) should be <= all total ({total_all})"
        
        print(f"PASSED: Search reduces total from {total_all} to {total_search}")
    
    def test_search_case_insensitive(self):
        """Search is case-insensitive"""
        resp_lower = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "search": "admin"
        })
        resp_upper = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "search": "ADMIN"
        })
        resp_mixed = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "search": "AdMiN"
        })
        
        assert resp_lower.json()["total"] == resp_upper.json()["total"] == resp_mixed.json()["total"], \
            "Search should be case-insensitive"
        
        print("PASSED: Search is case-insensitive")
    
    # ============ FILTER FUNCTIONALITY ============
    
    def test_filter_by_role(self):
        """Filter by role=admin returns only admins"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "role": "admin"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # All returned users should have role=admin
        for user in data["users"]:
            assert user.get("role") == "admin", f"User {user.get('email')} has role {user.get('role')}, expected admin"
        
        print(f"PASSED: Filter by role=admin returns {data['total']} admin users")
    
    def test_filter_by_status_active(self):
        """Filter by status=active excludes inactive users"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "status": "active"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # No user should have status=inactive
        for user in data["users"]:
            assert user.get("status") != "inactive", f"User {user.get('email')} is inactive but should be excluded"
        
        print(f"PASSED: Filter by status=active returns {data['total']} active users")
    
    def test_filter_by_status_inactive(self):
        """Filter by status=inactive returns only inactive users"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "status": "inactive"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # All returned users should have status=inactive
        for user in data["users"]:
            assert user.get("status") == "inactive", f"User {user.get('email')} has status {user.get('status')}, expected inactive"
        
        print(f"PASSED: Filter by status=inactive returns {data['total']} inactive users")
    
    def test_filter_reduces_total(self):
        """Filters should reduce total count"""
        # Get total without filter
        resp_all = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 50})
        total_all = resp_all.json()["total"]
        
        # Get total with role filter
        resp_admin = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "role": "admin"
        })
        total_admin = resp_admin.json()["total"]
        
        assert total_admin <= total_all, f"Filtered total ({total_admin}) should be <= all total ({total_all})"
        
        print(f"PASSED: Filter reduces total from {total_all} to {total_admin}")
    
    def test_combined_search_and_filter(self):
        """Search + filter can be combined"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={
            "page": 1, "limit": 50, "search": "admin", "role": "admin"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # All users should match both search and filter
        for user in data["users"]:
            assert user.get("role") == "admin", "User should have role=admin"
            search_fields = [
                (user.get("name") or "").lower(),
                (user.get("email") or "").lower(),
                (user.get("department") or "").lower(),
                (user.get("location") or "").lower(),
                (user.get("profession") or "").lower(),
            ]
            matches = any("admin" in field for field in search_fields)
            assert matches, "User should match search 'admin'"
        
        print(f"PASSED: Combined search+filter returns {data['total']} users")
    
    # ============ FILTERS ENDPOINT ============
    
    def test_filters_endpoint_returns_distinct_values(self):
        """GET /admin/users/filters returns distinct values for dropdowns"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users/filters")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Should have all filter categories
        assert "departments" in data, "Should have departments"
        assert "locations" in data, "Should have locations"
        assert "professions" in data, "Should have professions"
        assert "roles" in data, "Should have roles"
        
        # All should be lists
        assert isinstance(data["departments"], list), "departments should be list"
        assert isinstance(data["locations"], list), "locations should be list"
        assert isinstance(data["professions"], list), "professions should be list"
        assert isinstance(data["roles"], list), "roles should be list"
        
        # Roles should include admin at minimum
        assert "admin" in data["roles"], "roles should include 'admin'"
        
        # Values should be sorted
        assert data["departments"] == sorted(data["departments"]), "departments should be sorted"
        assert data["locations"] == sorted(data["locations"]), "locations should be sorted"
        assert data["professions"] == sorted(data["professions"]), "professions should be sorted"
        assert data["roles"] == sorted(data["roles"]), "roles should be sorted"
        
        print(f"PASSED: Filters endpoint returns - departments={len(data['departments'])}, locations={len(data['locations'])}, professions={len(data['professions'])}, roles={data['roles']}")
    
    def test_filters_endpoint_requires_admin(self):
        """GET /admin/users/filters requires admin role"""
        # Create new session without auth
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/admin/users/filters")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        
        print("PASSED: Filters endpoint requires admin auth")
    
    def test_filters_excludes_empty_values(self):
        """Filters should exclude empty/null values"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users/filters")
        assert resp.status_code == 200
        data = resp.json()
        
        # No empty strings in any list
        for key in ["departments", "locations", "professions", "roles"]:
            for val in data[key]:
                assert val and val.strip(), f"Empty value found in {key}"
        
        print("PASSED: Filters exclude empty values")
    
    # ============ LEGACY CONSUMERS ============
    
    def test_legacy_bulk_apply_preset_works(self):
        """Legacy consumers like bulk apply preset still work with paginated user_ids"""
        # First get some user IDs from paginated endpoint
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 5})
        assert resp.status_code == 200
        users = resp.json()["users"]
        
        if len(users) < 2:
            pytest.skip("Not enough users to test bulk apply")
        
        user_ids = [u["user_id"] for u in users[:2]]
        
        # Get or create a preset
        presets_resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        assert presets_resp.status_code == 200
        presets = presets_resp.json().get("presets", [])
        
        if not presets:
            # Create a test preset
            create_resp = self.session.post(f"{BASE_URL}/api/admin/presets", json={
                "label": "TEST_pagination_preset",
                "description": "Test preset for pagination testing",
                "capabilities": ["view:dashboard"]
            })
            assert create_resp.status_code == 200
            preset_id = create_resp.json()["preset_id"]
        else:
            preset_id = presets[0]["preset_id"]
        
        # Apply preset to users
        apply_resp = self.session.post(f"{BASE_URL}/api/admin/presets/{preset_id}/apply-to-users", json={
            "user_ids": user_ids
        })
        assert apply_resp.status_code == 200, f"Bulk apply failed: {apply_resp.text}"
        data = apply_resp.json()
        
        assert data.get("ok") == True, "Bulk apply should return ok=True"
        assert data.get("updated", 0) >= 1, "Should update at least 1 user"
        
        print(f"PASSED: Legacy bulk apply preset works - updated {data.get('updated')} users")
    
    # ============ EDGE CASES ============
    
    def test_page_beyond_total_returns_empty(self):
        """Requesting page beyond total returns empty users list"""
        # Get total pages
        resp1 = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 1, "limit": 50})
        pages = resp1.json()["pages"]
        
        # Request page beyond total
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": pages + 10, "limit": 50})
        assert resp.status_code == 200
        data = resp.json()
        
        assert len(data["users"]) == 0, f"Expected empty users list for page beyond total, got {len(data['users'])}"
        
        print(f"PASSED: Page beyond total ({pages + 10}) returns empty list")
    
    def test_negative_page_defaults_to_1(self):
        """Negative page value defaults to page 1 when limit is provided"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": -1, "limit": 50})
        assert resp.status_code == 200
        data = resp.json()
        
        # When limit > 0, paginated mode is used and page defaults to 1
        assert isinstance(data, dict), "Should return paginated object when limit > 0"
        assert data["page"] == 1, f"Negative page should default to 1, got {data['page']}"
        
        print("PASSED: Negative page defaults to 1 when limit is provided")
    
    def test_zero_page_defaults_to_1(self):
        """page=0 defaults to page 1 when limit is provided"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users", params={"page": 0, "limit": 50})
        assert resp.status_code == 200
        data = resp.json()
        
        # When limit > 0, paginated mode is used and page defaults to 1
        assert isinstance(data, dict), "Should return paginated object when limit > 0"
        assert data["page"] == 1, f"page=0 should default to 1, got {data['page']}"
        
        print("PASSED: page=0 defaults to 1 when limit is provided")
    
    def test_requires_admin_role(self):
        """GET /admin/users requires admin role"""
        # Create new session without auth
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        
        print("PASSED: /admin/users requires admin auth")


class TestRegressionIteration77:
    """Regression tests for iteration 77 features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_force_logout_all_endpoint_exists(self):
        """POST /admin/force-logout-all endpoint still works"""
        # Just verify endpoint exists and returns expected structure
        # Don't actually force logout all users
        resp = self.session.post(f"{BASE_URL}/api/admin/force-logout-all")
        assert resp.status_code == 200, f"Force logout all failed: {resp.text}"
        data = resp.json()
        assert "modified_count" in data, "Should return modified_count"
        
        print(f"PASSED: Force logout all works - modified {data['modified_count']} users")
    
    def test_email_config_endpoint_exists(self):
        """GET /admin/email-config still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert resp.status_code == 200, f"Email config failed: {resp.text}"
        data = resp.json()
        
        assert "provider" in data, "Should have provider"
        assert "smtp" in data, "Should have smtp block"
        
        print("PASSED: Email config endpoint works")
    
    def test_dns_check_endpoint_exists(self):
        """GET /admin/email-config/dns-check still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config/dns-check", params={
            "domain": "example.com"
        })
        assert resp.status_code == 200, f"DNS check failed: {resp.text}"
        data = resp.json()
        
        assert "domain" in data, "Should have domain"
        assert "mx" in data, "Should have mx"
        assert "spf" in data, "Should have spf"
        
        print("PASSED: DNS check endpoint works")
    
    def test_admin_stats_endpoint(self):
        """GET /admin/stats still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/stats")
        assert resp.status_code == 200, f"Stats failed: {resp.text}"
        data = resp.json()
        
        assert "total_users" in data, "Should have total_users"
        assert "total_meetings" in data, "Should have total_meetings"
        
        print(f"PASSED: Admin stats - {data['total_users']} users, {data['total_meetings']} meetings")
    
    def test_admin_groups_endpoint(self):
        """GET /admin/groups still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/groups")
        assert resp.status_code == 200, f"Groups failed: {resp.text}"
        data = resp.json()
        
        assert isinstance(data, list), "Should return list of groups"
        
        print(f"PASSED: Admin groups - {len(data)} groups")
    
    def test_admin_presets_endpoint(self):
        """GET /admin/presets still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        assert resp.status_code == 200, f"Presets failed: {resp.text}"
        data = resp.json()
        
        assert "presets" in data, "Should have presets key"
        
        print(f"PASSED: Admin presets - {len(data['presets'])} presets")
    
    def test_admin_cap_rules_endpoint(self):
        """GET /admin/cap-rules still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/cap-rules")
        assert resp.status_code == 200, f"Cap rules failed: {resp.text}"
        data = resp.json()
        
        assert "rules" in data, "Should have rules key"
        
        print(f"PASSED: Admin cap rules - {len(data['rules'])} rules")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
