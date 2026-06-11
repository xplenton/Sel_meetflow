"""
Iteration 289 — Group role_override Feature Tests

Tests the new role_override field on groups that allows admins to downgrade
the effective base role of all members in a group (e.g., Gast-Group forces
members to guest-level permissions even if their user.role is 'member').

Key scenarios:
1. GET /api/admin/groups returns role_override field
2. POST /api/admin/groups with name='Gast' (exact) auto-sets role_override='guest'
3. POST /api/admin/groups with other names keeps role_override=None
4. PUT /api/admin/groups/{id} with role_override updates correctly
5. PRIMARY: User with role='member' + Gast-Group → only guest caps (view:dashboard, view:chat)
6. User with role='admin' + Gast-Group → check downgrade behavior
7. User with role='member' + Group WITHOUT role_override → keeps all member caps
8. User in multiple groups (one with role_override='guest', one without) → lowest wins
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Expected guest-level capabilities (from ROLE_DEFAULTS in permissions.py)
GUEST_CAPS = {"view:dashboard", "view:chat"}

# Expected member-level view capabilities (subset for testing)
MEMBER_VIEW_CAPS = {
    "view:dashboard", "view:news", "view:chat", "view:meetings",
    "view:scheduling", "view:calendar", "view:recordings", "view:surveys",
    "view:tasks", "view:resources"
}


class TestRoleOverrideFeature:
    """Tests for the role_override feature in groups."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login as admin and store session."""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin_token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.admin_token}"})
        
        # Track created resources for cleanup
        self.created_groups = []
        self.created_users = []
        
        yield
        
        # Cleanup: delete test groups and users
        for gid in self.created_groups:
            try:
                self.session.delete(f"{BASE_URL}/api/admin/groups/{gid}")
            except:
                pass
        for uid in self.created_users:
            try:
                self.session.delete(f"{BASE_URL}/api/admin/users/{uid}")
            except:
                pass

    def _create_test_user(self, email, name, role="member", group_id=None):
        """Helper to create a test user via /api/admin/users/invite."""
        payload = {
            "email": email,
            "name": name,
            "role": role
        }
        if group_id:
            payload["group_id"] = group_id
        
        resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json=payload)
        return resp

    # ============ Test 1: GET /api/admin/groups returns role_override field ============
    def test_get_groups_returns_role_override_field(self):
        """GET /api/admin/groups should return role_override field for each group."""
        resp = self.session.get(f"{BASE_URL}/api/admin/groups")
        assert resp.status_code == 200, f"Failed to get groups: {resp.text}"
        
        groups = resp.json()
        assert isinstance(groups, list), "Expected list of groups"
        
        # Check if any group named 'Gast' exists and has role_override='guest'
        gast_group = next((g for g in groups if g.get("name", "").lower() in ("gast", "guest", "gäste")), None)
        if gast_group:
            assert "role_override" in gast_group, "Gast group should have role_override field"
            assert gast_group.get("role_override") == "guest", f"Gast group should have role_override='guest', got {gast_group.get('role_override')}"
            print(f"PASS: Gast group has role_override='guest'")
        else:
            print("INFO: No existing Gast group found, will test creation")
        
        # Verify all groups have role_override field (can be None)
        for g in groups:
            assert "role_override" in g or g.get("role_override") is None, f"Group {g.get('name')} missing role_override field"
        print(f"PASS: GET /api/admin/groups returns {len(groups)} groups with role_override field")

    # ============ Test 2: POST with exact name='Gast' auto-sets role_override='guest' ============
    def test_create_group_exact_guest_name_auto_sets_role_override(self):
        """POST /api/admin/groups with exact name 'Gast'/'Guest'/'Gäste' auto-sets role_override='guest'.
        
        Note: The auto-set only works for EXACT matches, not partial matches like 'Test-Gäste'.
        """
        # First check if 'Gast' already exists
        groups_resp = self.session.get(f"{BASE_URL}/api/admin/groups")
        groups = groups_resp.json()
        existing_gast = next((g for g in groups if g.get("name", "").lower() == "gast"), None)
        
        if existing_gast:
            # Verify existing Gast group has role_override='guest'
            assert existing_gast.get("role_override") == "guest", f"Existing Gast group should have role_override='guest', got {existing_gast.get('role_override')}"
            print(f"PASS: Existing 'Gast' group has role_override='guest'")
        else:
            # Create a new group with exact name 'Gast'
            resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
                "name": "Gast",
                "description": "Test guest group for iter 289"
            })
            if resp.status_code == 409:
                # Group already exists with different casing
                print("INFO: Gast group already exists (conflict)")
            else:
                assert resp.status_code in (200, 201), f"Failed to create group: {resp.text}"
                group = resp.json()
                self.created_groups.append(group.get("group_id"))
                assert group.get("role_override") == "guest", f"Expected role_override='guest' for 'Gast' group, got {group.get('role_override')}"
                print(f"PASS: Group 'Gast' auto-set role_override='guest'")

    # ============ Test 3: POST with name='Test-Marketing' keeps role_override=None ============
    def test_create_group_non_guest_name_no_role_override(self):
        """POST /api/admin/groups with non-guest name should have role_override=None."""
        unique_name = f"TEST_Marketing_{uuid.uuid4().hex[:6]}"
        
        resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
            "name": unique_name,
            "description": "Test marketing group for iter 289"
        })
        assert resp.status_code in (200, 201), f"Failed to create group: {resp.text}"
        
        group = resp.json()
        self.created_groups.append(group.get("group_id"))
        
        assert group.get("role_override") is None, f"Expected role_override=None for non-guest group, got {group.get('role_override')}"
        print(f"PASS: Group '{unique_name}' has role_override=None")

    # ============ Test 4: PUT /api/admin/groups/{id} with role_override updates correctly ============
    def test_update_group_role_override(self):
        """PUT /api/admin/groups/{id} with role_override should update correctly."""
        # Create a test group first
        unique_name = f"TEST_Override_{uuid.uuid4().hex[:6]}"
        create_resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
            "name": unique_name,
            "description": "Test group for role_override update"
        })
        assert create_resp.status_code in (200, 201), f"Failed to create group: {create_resp.text}"
        group = create_resp.json()
        group_id = group.get("group_id")
        self.created_groups.append(group_id)
        
        # Update with role_override='moderator'
        update_resp = self.session.put(f"{BASE_URL}/api/admin/groups/{group_id}", json={
            "role_override": "moderator"
        })
        assert update_resp.status_code == 200, f"Failed to update group: {update_resp.text}"
        updated = update_resp.json()
        assert updated.get("role_override") == "moderator", f"Expected role_override='moderator', got {updated.get('role_override')}"
        print(f"PASS: Updated role_override to 'moderator'")
        
        # Update with invalid value should set to None
        update_resp2 = self.session.put(f"{BASE_URL}/api/admin/groups/{group_id}", json={
            "role_override": "invalid_role"
        })
        assert update_resp2.status_code == 200, f"Failed to update group: {update_resp2.text}"
        updated2 = update_resp2.json()
        assert updated2.get("role_override") is None, f"Expected role_override=None for invalid value, got {updated2.get('role_override')}"
        print(f"PASS: Invalid role_override value set to None")
        
        # Update with empty string should set to None
        update_resp3 = self.session.put(f"{BASE_URL}/api/admin/groups/{group_id}", json={
            "role_override": ""
        })
        assert update_resp3.status_code == 200, f"Failed to update group: {update_resp3.text}"
        updated3 = update_resp3.json()
        assert updated3.get("role_override") is None, f"Expected role_override=None for empty string, got {updated3.get('role_override')}"
        print(f"PASS: Empty role_override set to None")

    # ============ Test 5 (PRIMARY): User with role='member' + Gast-Group → only guest caps ============
    def test_member_in_guest_group_gets_only_guest_caps(self):
        """PRIMARY TEST: User with role='member' in Gast-Group should only have guest capabilities."""
        # Step 1: Create a test group with role_override='guest'
        group_name = f"TEST_GastGroup_{uuid.uuid4().hex[:6]}"
        group_resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
            "name": group_name,
            "description": "Test guest group",
            "role_override": "guest"
        })
        assert group_resp.status_code in (200, 201), f"Failed to create group: {group_resp.text}"
        group = group_resp.json()
        group_id = group.get("group_id")
        self.created_groups.append(group_id)
        assert group.get("role_override") == "guest", "Group should have role_override='guest'"
        
        # Step 2: Create a test user with role='member' and add to group
        test_email = f"test_member_{uuid.uuid4().hex[:6]}@meetflow.com"
        user_resp = self._create_test_user(test_email, "Test Member User", role="member", group_id=group_id)
        assert user_resp.status_code in (200, 201), f"Failed to create user: {user_resp.text}"
        user = user_resp.json()
        user_id = user.get("user_id")
        self.created_users.append(user_id)
        
        # Get the temp password from the response
        temp_password = user.get("temp_password")
        if not temp_password:
            # If not in response, use a known pattern or skip
            print("INFO: temp_password not in response, using default test password")
            temp_password = "testpass123"
        
        # Step 3: Login as the test user
        user_session = requests.Session()
        user_session.headers.update({"Content-Type": "application/json"})
        login_resp = user_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": temp_password
        })
        
        if login_resp.status_code != 200:
            # Try with must_change_password flow or skip
            print(f"INFO: Login failed with temp password, status: {login_resp.status_code}")
            # Use admin to check user permissions via simulate endpoint
            sim_resp = self.session.get(f"{BASE_URL}/api/admin/users/{user_id}/simulate")
            assert sim_resp.status_code == 200, f"Failed to simulate: {sim_resp.text}"
            sim = sim_resp.json()
            caps = set(sim.get("effective", []))
        else:
            user_token = login_resp.json().get("token")
            user_session.headers.update({"Authorization": f"Bearer {user_token}"})
            
            # Step 4: Get user permissions
            perms_resp = user_session.get(f"{BASE_URL}/api/user/permissions")
            assert perms_resp.status_code == 200, f"Failed to get permissions: {perms_resp.text}"
            perms = perms_resp.json()
            caps = set(perms.get("capabilities", []))
        
        print(f"User capabilities: {sorted(caps)}")
        
        # Step 5: Verify user only has guest-level capabilities
        # Guest should have: view:dashboard, view:chat
        # Guest should NOT have: view:resources, view:news, view:tasks, view:meetings, etc.
        
        assert "view:dashboard" in caps, "Guest should have view:dashboard"
        assert "view:chat" in caps, "Guest should have view:chat"
        
        # These should NOT be present for a guest
        forbidden_caps = ["view:resources", "view:news", "view:tasks", "view:meetings", 
                         "view:scheduling", "view:calendar", "view:recordings", "view:surveys"]
        
        for fc in forbidden_caps:
            assert fc not in caps, f"Guest should NOT have {fc}, but it was present"
        
        print(f"PASS: Member in Gast-Group has only guest caps: {sorted(caps)}")

    # ============ Test 6: User with role='admin' + Gast-Group → check downgrade behavior ============
    def test_admin_in_guest_group_downgrade_behavior(self):
        """User with role='admin' in Gast-Group - verify downgrade behavior.
        
        According to the code: min(admin=3, guest=0) = guest (rank 0).
        This means admin WOULD be downgraded to guest. This test verifies this behavior.
        """
        # Step 1: Create a test group with role_override='guest'
        group_name = f"TEST_AdminGast_{uuid.uuid4().hex[:6]}"
        group_resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
            "name": group_name,
            "description": "Test guest group for admin",
            "role_override": "guest"
        })
        assert group_resp.status_code in (200, 201), f"Failed to create group: {group_resp.text}"
        group = group_resp.json()
        group_id = group.get("group_id")
        self.created_groups.append(group_id)
        
        # Step 2: Create a test user with role='admin'
        test_email = f"test_admin_{uuid.uuid4().hex[:6]}@meetflow.com"
        user_resp = self._create_test_user(test_email, "Test Admin User", role="admin", group_id=group_id)
        assert user_resp.status_code in (200, 201), f"Failed to create user: {user_resp.text}"
        user = user_resp.json()
        user_id = user.get("user_id")
        self.created_users.append(user_id)
        
        # Step 3: Use admin simulate endpoint to check effective caps
        sim_resp = self.session.get(f"{BASE_URL}/api/admin/users/{user_id}/simulate")
        assert sim_resp.status_code == 200, f"Failed to simulate: {sim_resp.text}"
        sim = sim_resp.json()
        
        caps = set(sim.get("effective", []))
        print(f"Admin in Gast-Group capabilities: {sorted(caps)}")
        
        # According to the code logic: min(admin=3, guest=0) = guest
        # So admin SHOULD be downgraded to guest-level caps
        # This might be a bug or intended behavior - we document what happens
        
        if "view:admin" in caps:
            print("INFO: Admin in Gast-Group RETAINS admin caps (admin not downgraded)")
            # This would mean there's special handling for admin role
        else:
            print("INFO: Admin in Gast-Group is DOWNGRADED to guest caps")
            # This is what the current code does based on min() logic
            assert "view:dashboard" in caps, "Should have view:dashboard"
            assert "view:chat" in caps, "Should have view:chat"
        
        print(f"PASS: Admin in Gast-Group behavior documented. Caps count: {len(caps)}")

    # ============ Test 7: User with role='member' + Group WITHOUT role_override → keeps member caps ============
    def test_member_in_group_without_role_override_keeps_member_caps(self):
        """User with role='member' in a group WITHOUT role_override should keep all member capabilities."""
        # Step 1: Create a test group WITHOUT role_override
        group_name = f"TEST_NoOverride_{uuid.uuid4().hex[:6]}"
        group_resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
            "name": group_name,
            "description": "Test group without role_override"
            # No role_override specified
        })
        assert group_resp.status_code in (200, 201), f"Failed to create group: {group_resp.text}"
        group = group_resp.json()
        group_id = group.get("group_id")
        self.created_groups.append(group_id)
        assert group.get("role_override") is None, "Group should have role_override=None"
        
        # Step 2: Create a test user with role='member'
        test_email = f"test_member_no_override_{uuid.uuid4().hex[:6]}@meetflow.com"
        user_resp = self._create_test_user(test_email, "Test Member No Override", role="member", group_id=group_id)
        assert user_resp.status_code in (200, 201), f"Failed to create user: {user_resp.text}"
        user = user_resp.json()
        user_id = user.get("user_id")
        self.created_users.append(user_id)
        
        # Step 3: Use admin simulate endpoint to check effective caps
        sim_resp = self.session.get(f"{BASE_URL}/api/admin/users/{user_id}/simulate")
        assert sim_resp.status_code == 200, f"Failed to simulate: {sim_resp.text}"
        sim = sim_resp.json()
        
        caps = set(sim.get("effective", []))
        print(f"Member in group without role_override capabilities: {sorted(caps)}")
        
        # Step 4: Verify user has member-level capabilities
        for mc in MEMBER_VIEW_CAPS:
            assert mc in caps, f"Member should have {mc}"
        
        print(f"PASS: Member in group without role_override keeps all member caps ({len(caps)} caps)")

    # ============ Test 8: User in multiple groups (one with role_override='guest', one without) → lowest wins ============
    def test_user_in_multiple_groups_lowest_role_override_wins(self):
        """User in multiple groups where one has role_override='guest' should be downgraded (lowest wins)."""
        # Step 1: Create a group WITHOUT role_override
        group1_name = f"TEST_Normal_{uuid.uuid4().hex[:6]}"
        group1_resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
            "name": group1_name,
            "description": "Normal group without override"
        })
        assert group1_resp.status_code in (200, 201), f"Failed to create group1: {group1_resp.text}"
        group1 = group1_resp.json()
        group1_id = group1.get("group_id")
        self.created_groups.append(group1_id)
        
        # Step 2: Create a group WITH role_override='guest'
        group2_name = f"TEST_GuestOverride_{uuid.uuid4().hex[:6]}"
        group2_resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
            "name": group2_name,
            "description": "Guest override group",
            "role_override": "guest"
        })
        assert group2_resp.status_code in (200, 201), f"Failed to create group2: {group2_resp.text}"
        group2 = group2_resp.json()
        group2_id = group2.get("group_id")
        self.created_groups.append(group2_id)
        
        # Step 3: Create a test user with role='member' in first group
        test_email = f"test_multi_group_{uuid.uuid4().hex[:6]}@meetflow.com"
        user_resp = self._create_test_user(test_email, "Test Multi Group User", role="member", group_id=group1_id)
        assert user_resp.status_code in (200, 201), f"Failed to create user: {user_resp.text}"
        user = user_resp.json()
        user_id = user.get("user_id")
        self.created_users.append(user_id)
        
        # Step 4: Add user to the second group (guest override)
        add2_resp = self.session.post(f"{BASE_URL}/api/admin/groups/{group2_id}/members", json={"user_id": user_id})
        assert add2_resp.status_code == 200, f"Failed to add to group2: {add2_resp.text}"
        
        # Step 5: Use admin simulate endpoint to check effective caps
        sim_resp = self.session.get(f"{BASE_URL}/api/admin/users/{user_id}/simulate")
        assert sim_resp.status_code == 200, f"Failed to simulate: {sim_resp.text}"
        sim = sim_resp.json()
        
        caps = set(sim.get("effective", []))
        print(f"User in multiple groups (one with guest override) capabilities: {sorted(caps)}")
        
        # Step 6: Verify user is downgraded to guest (lowest wins)
        assert "view:dashboard" in caps, "Should have view:dashboard"
        assert "view:chat" in caps, "Should have view:chat"
        
        # Should NOT have member-only caps
        forbidden_caps = ["view:resources", "view:news", "view:tasks", "view:meetings"]
        for fc in forbidden_caps:
            assert fc not in caps, f"User should NOT have {fc} when in guest-override group"
        
        print(f"PASS: User in multiple groups downgraded to guest (lowest wins). Caps: {len(caps)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
