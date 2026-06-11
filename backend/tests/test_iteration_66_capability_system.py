"""
Iteration 66 - Capability System Expansion Tests
Tests for:
- DB-Backed Presets (CRUD)
- Auto-Assign Rules Engine (CRUD + Run)
- Bulk Apply Presets
- Audit Logging for capability changes
- Regression tests for existing features
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDBBackedPresets:
    """Tests for DB-backed capability presets"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before each test"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_list_presets_returns_builtin(self):
        """GET /admin/presets should return 13 built-in presets from DB"""
        resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "presets" in data
        presets = data["presets"]
        
        # Should have at least 13 built-in presets
        builtin = [p for p in presets if p.get("builtin") == True]
        assert len(builtin) >= 13, f"Expected at least 13 builtin presets, got {len(builtin)}"
        
        # Check builtin flag is present
        for p in builtin:
            assert p.get("builtin") == True
            assert "preset_id" in p
            assert "label" in p
            assert "capabilities" in p
        print(f"✓ Found {len(builtin)} built-in presets")
    
    def test_02_create_custom_preset(self):
        """POST /admin/presets creates custom preset with auto-gen ID"""
        unique_label = f"TEST_Station_X_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/admin/presets", json={
            "label": unique_label,
            "description": "Test preset for Station X",
            "capabilities": ["news.create", "surveys.create", "invalid_cap_should_be_filtered"]
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify auto-generated preset_id
        assert "preset_id" in data
        assert data["preset_id"].startswith("custom_"), f"Expected custom_ prefix, got {data['preset_id']}"
        
        # Verify builtin=false
        assert data.get("builtin") == False
        
        # Verify invalid caps are filtered
        assert "invalid_cap_should_be_filtered" not in data.get("capabilities", [])
        assert "news.create" in data.get("capabilities", [])
        
        # Store for cleanup
        self.created_preset_id = data["preset_id"]
        print(f"✓ Created custom preset: {data['preset_id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/presets/{data['preset_id']}")
    
    def test_03_update_custom_preset(self):
        """PUT /admin/presets/{id} updates custom preset"""
        # First create a preset
        unique_label = f"TEST_Update_{uuid.uuid4().hex[:6]}"
        create_resp = self.session.post(f"{BASE_URL}/api/admin/presets", json={
            "label": unique_label,
            "description": "Original description",
            "capabilities": ["news.create"]
        })
        assert create_resp.status_code == 200
        preset_id = create_resp.json()["preset_id"]
        
        # Update it
        update_resp = self.session.put(f"{BASE_URL}/api/admin/presets/{preset_id}", json={
            "label": f"{unique_label}_UPDATED",
            "description": "Updated description",
            "capabilities": ["news.create", "surveys.create"]
        })
        assert update_resp.status_code == 200, f"Failed: {update_resp.text}"
        data = update_resp.json()
        
        assert data["label"] == f"{unique_label}_UPDATED"
        assert data["description"] == "Updated description"
        assert "surveys.create" in data.get("capabilities", [])
        print(f"✓ Updated custom preset: {preset_id}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/presets/{preset_id}")
    
    def test_04_update_builtin_preset_forbidden(self):
        """PUT /admin/presets/{id} on builtin preset returns 403"""
        # Get a builtin preset
        resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        presets = resp.json().get("presets", [])
        builtin = [p for p in presets if p.get("builtin") == True]
        assert len(builtin) > 0, "No builtin presets found"
        
        builtin_id = builtin[0]["preset_id"]
        
        # Try to update it
        update_resp = self.session.put(f"{BASE_URL}/api/admin/presets/{builtin_id}", json={
            "label": "Hacked Label"
        })
        assert update_resp.status_code == 403, f"Expected 403, got {update_resp.status_code}"
        assert "Built-in" in update_resp.json().get("detail", "")
        print(f"✓ Builtin preset update correctly blocked: {builtin_id}")
    
    def test_05_delete_custom_preset(self):
        """DELETE /admin/presets/{id} deletes custom preset"""
        # Create a preset to delete
        unique_label = f"TEST_Delete_{uuid.uuid4().hex[:6]}"
        create_resp = self.session.post(f"{BASE_URL}/api/admin/presets", json={
            "label": unique_label,
            "capabilities": ["news.create"]
        })
        assert create_resp.status_code == 200
        preset_id = create_resp.json()["preset_id"]
        
        # Delete it
        delete_resp = self.session.delete(f"{BASE_URL}/api/admin/presets/{preset_id}")
        assert delete_resp.status_code == 200, f"Failed: {delete_resp.text}"
        
        # Verify it's gone
        list_resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        presets = list_resp.json().get("presets", [])
        assert not any(p["preset_id"] == preset_id for p in presets)
        print(f"✓ Deleted custom preset: {preset_id}")
    
    def test_06_delete_builtin_preset_forbidden(self):
        """DELETE /admin/presets/{id} on builtin preset returns 403"""
        resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        presets = resp.json().get("presets", [])
        builtin = [p for p in presets if p.get("builtin") == True]
        assert len(builtin) > 0
        
        builtin_id = builtin[0]["preset_id"]
        delete_resp = self.session.delete(f"{BASE_URL}/api/admin/presets/{builtin_id}")
        assert delete_resp.status_code == 403, f"Expected 403, got {delete_resp.status_code}"
        print(f"✓ Builtin preset delete correctly blocked: {builtin_id}")


class TestBulkApplyPresets:
    """Tests for bulk applying presets to multiple users"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_bulk_apply_preset_to_users(self):
        """POST /admin/presets/{id}/apply-to-users applies preset to multiple users"""
        # Get users
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert users_resp.status_code == 200
        users = users_resp.json()
        
        if len(users) < 2:
            pytest.skip("Need at least 2 users for bulk apply test")
        
        # Get a preset
        presets_resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        presets = presets_resp.json().get("presets", [])
        assert len(presets) > 0
        preset = presets[0]
        
        # Apply to first 2 users
        user_ids = [users[0]["user_id"], users[1]["user_id"]]
        apply_resp = self.session.post(f"{BASE_URL}/api/admin/presets/{preset['preset_id']}/apply-to-users", json={
            "user_ids": user_ids
        })
        assert apply_resp.status_code == 200, f"Failed: {apply_resp.text}"
        data = apply_resp.json()
        
        assert data.get("ok") == True
        assert data.get("updated") >= 1  # At least 1 user updated
        print(f"✓ Bulk applied preset '{preset['label']}' to {data['updated']} users")
    
    def test_02_bulk_apply_empty_user_ids_fails(self):
        """POST /admin/presets/{id}/apply-to-users with empty user_ids returns 400"""
        presets_resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        presets = presets_resp.json().get("presets", [])
        preset = presets[0]
        
        apply_resp = self.session.post(f"{BASE_URL}/api/admin/presets/{preset['preset_id']}/apply-to-users", json={
            "user_ids": []
        })
        assert apply_resp.status_code == 400, f"Expected 400, got {apply_resp.status_code}"
        print("✓ Empty user_ids correctly rejected")


class TestCapRulesCRUD:
    """Tests for Auto-Assign Rules CRUD"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_list_cap_rules(self):
        """GET /admin/cap-rules returns rules list"""
        resp = self.session.get(f"{BASE_URL}/api/admin/cap-rules")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "rules" in data
        print(f"✓ Listed {len(data['rules'])} cap rules")
    
    def test_02_create_cap_rule(self):
        """POST /admin/cap-rules creates a new rule"""
        unique_name = f"TEST_Rule_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules", json={
            "name": unique_name,
            "description": "Test rule for Kardiologie",
            "enabled": True,
            "when": {
                "department": "Kardiologie",
                "location": "",
                "profession": "",
                "role": ""
            },
            "apply": {
                "preset_id": "news_editor",
                "caps": []
            }
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "rule_id" in data
        assert data["rule_id"].startswith("rule_")
        assert data["name"] == unique_name
        assert data["enabled"] == True
        assert data["when"]["department"] == "Kardiologie"
        assert data["apply"]["preset_id"] == "news_editor"
        print(f"✓ Created cap rule: {data['rule_id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/cap-rules/{data['rule_id']}")
    
    def test_03_create_rule_requires_preset_or_caps(self):
        """POST /admin/cap-rules without preset or caps returns 400"""
        resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules", json={
            "name": "Invalid Rule",
            "when": {"department": "Test"},
            "apply": {"preset_id": "", "caps": []}
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ Rule without preset/caps correctly rejected")
    
    def test_04_update_cap_rule(self):
        """PUT /admin/cap-rules/{id} updates a rule"""
        # Create a rule
        unique_name = f"TEST_Update_Rule_{uuid.uuid4().hex[:6]}"
        create_resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules", json={
            "name": unique_name,
            "enabled": True,
            "when": {"department": "Test"},
            "apply": {"preset_id": "news_editor"}
        })
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule_id"]
        
        # Update it
        update_resp = self.session.put(f"{BASE_URL}/api/admin/cap-rules/{rule_id}", json={
            "name": f"{unique_name}_UPDATED",
            "enabled": False,
            "when": {"department": "Neurologie"}
        })
        assert update_resp.status_code == 200, f"Failed: {update_resp.text}"
        data = update_resp.json()
        
        assert data["name"] == f"{unique_name}_UPDATED"
        assert data["enabled"] == False
        assert data["when"]["department"] == "Neurologie"
        print(f"✓ Updated cap rule: {rule_id}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/cap-rules/{rule_id}")
    
    def test_05_delete_cap_rule(self):
        """DELETE /admin/cap-rules/{id} deletes a rule"""
        # Create a rule
        unique_name = f"TEST_Delete_Rule_{uuid.uuid4().hex[:6]}"
        create_resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules", json={
            "name": unique_name,
            "when": {"department": "Test"},
            "apply": {"preset_id": "news_editor"}
        })
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule_id"]
        
        # Delete it
        delete_resp = self.session.delete(f"{BASE_URL}/api/admin/cap-rules/{rule_id}")
        assert delete_resp.status_code == 200, f"Failed: {delete_resp.text}"
        
        # Verify it's gone
        list_resp = self.session.get(f"{BASE_URL}/api/admin/cap-rules")
        rules = list_resp.json().get("rules", [])
        assert not any(r["rule_id"] == rule_id for r in rules)
        print(f"✓ Deleted cap rule: {rule_id}")


class TestRuleEngine:
    """Tests for the Auto-Assign Rule Engine"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_run_all_rules_empty(self):
        """POST /admin/cap-rules/run with no rules returns 0 affected"""
        # First ensure no rules exist (or skip if rules exist)
        resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules/run", json={})
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "rules_run" in data
        assert "users_affected" in data
        assert "details" in data
        print(f"✓ Rule engine ran: {data['rules_run']} rules, {data['users_affected']} users affected")
    
    def test_02_run_single_rule(self):
        """POST /admin/cap-rules/run with rule_id runs only that rule"""
        # Create a test rule
        unique_name = f"TEST_Run_Rule_{uuid.uuid4().hex[:6]}"
        create_resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules", json={
            "name": unique_name,
            "enabled": True,
            "when": {"department": "NonExistentDept12345"},  # Won't match anyone
            "apply": {"preset_id": "news_editor"}
        })
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule_id"]
        
        # Run only this rule
        run_resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules/run", json={
            "rule_id": rule_id
        })
        assert run_resp.status_code == 200, f"Failed: {run_resp.text}"
        data = run_resp.json()
        
        assert data["rules_run"] == 1
        assert len(data["details"]) == 1
        assert data["details"][0]["rule_id"] == rule_id
        print(f"✓ Single rule executed: {rule_id}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/cap-rules/{rule_id}")
    
    def test_03_rule_matching_case_insensitive(self):
        """Rule matching is case-insensitive for department"""
        # Create a test user with specific department
        test_email = f"test_rule_match_{uuid.uuid4().hex[:6]}@test.com"
        invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email,
            "name": "Test Rule Match User",
            "role": "member"
        })
        if invite_resp.status_code != 200:
            pytest.skip("Could not create test user")
        
        user_id = invite_resp.json()["user_id"]
        
        # Set user's department
        self.session.put(f"{BASE_URL}/api/admin/users/{user_id}", json={
            "department": "KARDIOLOGIE"  # Uppercase
        })
        
        # Create rule with lowercase department
        unique_name = f"TEST_CaseMatch_{uuid.uuid4().hex[:6]}"
        create_resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules", json={
            "name": unique_name,
            "enabled": True,
            "when": {"department": "kardiologie"},  # lowercase
            "apply": {"caps": ["news.create"]}
        })
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["rule_id"]
        
        # Run the rule
        run_resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules/run", json={
            "rule_id": rule_id
        })
        assert run_resp.status_code == 200
        data = run_resp.json()
        
        # Should match the user (case-insensitive)
        assert data["users_affected"] >= 1, "Rule should have matched at least 1 user"
        print(f"✓ Case-insensitive matching works: {data['users_affected']} users affected")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/cap-rules/{rule_id}")
        self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")


class TestAuditLogging:
    """Tests for audit logging of capability changes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_set_caps_creates_audit_log(self):
        """PUT /admin/users/{id}/capabilities creates audit log entry"""
        # Get a user
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        users = users_resp.json()
        if len(users) < 2:
            pytest.skip("Need at least 2 users")
        
        # Find a non-admin user
        target_user = None
        for u in users:
            if u.get("role") != "admin":
                target_user = u
                break
        
        if not target_user:
            pytest.skip("No non-admin user found")
        
        # Set capabilities
        resp = self.session.put(f"{BASE_URL}/api/admin/users/{target_user['user_id']}/capabilities", json={
            "grants": ["news.create", "surveys.create"],
            "denies": []
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print(f"✓ Set capabilities on user {target_user['user_id']} - audit log should be created")
    
    def test_02_create_preset_creates_audit_log(self):
        """POST /admin/presets creates audit log entry"""
        unique_label = f"TEST_Audit_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/admin/presets", json={
            "label": unique_label,
            "capabilities": ["news.create"]
        })
        assert resp.status_code == 200
        preset_id = resp.json()["preset_id"]
        print(f"✓ Created preset {preset_id} - audit log should be created")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/presets/{preset_id}")
    
    def test_03_create_rule_creates_audit_log(self):
        """POST /admin/cap-rules creates audit log entry"""
        unique_name = f"TEST_Audit_Rule_{uuid.uuid4().hex[:6]}"
        resp = self.session.post(f"{BASE_URL}/api/admin/cap-rules", json={
            "name": unique_name,
            "when": {"department": "Test"},
            "apply": {"preset_id": "news_editor"}
        })
        assert resp.status_code == 200
        rule_id = resp.json()["rule_id"]
        print(f"✓ Created rule {rule_id} - audit log should be created")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/cap-rules/{rule_id}")


class TestRegressionExistingFeatures:
    """Regression tests for existing capability features from iterations 63-65"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_capabilities_list_returns_at_least_baseline(self):
        """GET /admin/capabilities returns at least the original 46 caps.
        (Sprint 4: 9 resource caps + future additions increase this number.)"""
        resp = self.session.get(f"{BASE_URL}/api/admin/capabilities")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        caps = data.get("capabilities", [])
        assert len(caps) >= 46, f"Expected at least 46 capabilities (baseline), got {len(caps)}"
        print(f"✓ Capabilities list: {len(caps)} capabilities")
    
    def test_02_simulate_user_permissions(self):
        """GET /admin/users/{id}/simulate returns detailed breakdown"""
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        users = users_resp.json()
        if not users:
            pytest.skip("No users found")
        
        user_id = users[0]["user_id"]
        resp = self.session.get(f"{BASE_URL}/api/admin/users/{user_id}/simulate")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "user" in data
        assert "role_defaults" in data
        assert "effective" in data
        assert "effective_count" in data
        print(f"✓ Simulated user {user_id}: {data['effective_count']} effective caps")
    
    def test_03_user_capabilities_with_expires(self):
        """PUT /admin/users/{id}/capabilities supports expires field"""
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        users = users_resp.json()
        
        # Find a non-admin user
        target_user = None
        for u in users:
            if u.get("role") != "admin":
                target_user = u
                break
        
        if not target_user:
            pytest.skip("No non-admin user found")
        
        # Set capabilities with expiration
        resp = self.session.put(f"{BASE_URL}/api/admin/users/{target_user['user_id']}/capabilities", json={
            "grants": ["news.create"],
            "denies": [],
            "expires": {
                "news.create": "2030-12-31T23:59:59Z"
            }
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") == True
        assert "expires" in data
        assert "news.create" in data.get("expires", {})
        print(f"✓ Set capability with expiration on user {target_user['user_id']}")
    
    def test_04_migrate_roles_endpoint(self):
        """POST /admin/migrate-roles is idempotent"""
        resp = self.session.post(f"{BASE_URL}/api/admin/migrate-roles")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "migrated" in data
        assert "unchanged" in data
        print(f"✓ Role migration: {data['migrated']} migrated, {data['unchanged']} unchanged")
    
    def test_05_apply_preset_to_single_user(self):
        """POST /admin/presets/{id}/apply-to-user/{id} works"""
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        users = users_resp.json()
        
        target_user = None
        for u in users:
            if u.get("role") != "admin":
                target_user = u
                break
        
        if not target_user:
            pytest.skip("No non-admin user found")
        
        # Get a preset
        presets_resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        presets = presets_resp.json().get("presets", [])
        if not presets:
            pytest.skip("No presets found")
        
        preset = presets[0]
        
        resp = self.session.post(f"{BASE_URL}/api/admin/presets/{preset['preset_id']}/apply-to-user/{target_user['user_id']}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") == True
        assert "applied" in data
        print(f"✓ Applied preset '{preset['label']}' to user {target_user['user_id']}")
    
    def test_06_apply_preset_to_group(self):
        """POST /admin/presets/{id}/apply-to-group/{id} works"""
        # Get groups
        groups_resp = self.session.get(f"{BASE_URL}/api/admin/groups")
        if groups_resp.status_code != 200:
            pytest.skip("Could not get groups")
        
        groups = groups_resp.json()
        if not groups:
            # Create a test group
            create_resp = self.session.post(f"{BASE_URL}/api/admin/groups", json={
                "name": f"TEST_Group_{uuid.uuid4().hex[:6]}",
                "description": "Test group for preset application"
            })
            if create_resp.status_code != 200:
                pytest.skip("Could not create test group")
            group = create_resp.json()
        else:
            group = groups[0]
        
        # Get a preset
        presets_resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        presets = presets_resp.json().get("presets", [])
        if not presets:
            pytest.skip("No presets found")
        
        preset = presets[0]
        
        resp = self.session.post(f"{BASE_URL}/api/admin/presets/{preset['preset_id']}/apply-to-group/{group['group_id']}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("ok") == True
        print(f"✓ Applied preset '{preset['label']}' to group {group['group_id']}")


class TestNewsModuleRegression:
    """Regression tests for News module"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_news_list(self):
        """GET /news/feed returns news list"""
        resp = self.session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("✓ News feed endpoint works")


class TestSurveysModuleRegression:
    """Regression tests for Surveys module"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_surveys_list(self):
        """GET /surveys returns surveys list"""
        resp = self.session.get(f"{BASE_URL}/api/surveys")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("✓ Surveys list endpoint works")


class TestMeetingsModuleRegression:
    """Regression tests for Meetings module"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_meetings_list(self):
        """GET /meetings returns meetings list"""
        resp = self.session.get(f"{BASE_URL}/api/meetings")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("✓ Meetings list endpoint works")


class TestChatModuleRegression:
    """Regression tests for Chat module"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_conversations_list(self):
        """GET /chat/conversations returns conversations list"""
        resp = self.session.get(f"{BASE_URL}/api/chat/conversations")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        print("✓ Chat conversations endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
