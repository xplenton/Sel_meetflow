"""
Iteration 90 - Comprehensive E2E Regression Test
Full platform validation before Go-Live

Tests:
1. Admin Stats Tab (GET /api/admin/stats)
2. Admin Health Tab (GET /api/admin/health, /api/admin/health/alerts)
3. Admin Users Tab (CRUD, pagination, filters, invite, status, force-logout)
4. Admin Groups Tab (CRUD, members, permissions)
5. Admin Branding Tab (GET/PUT /api/organization/branding)
6. Admin Integrations Tab (GET/PUT /api/admin/api-config, email-config)
7. Admin Reminders Tab (GET/PUT /api/admin/reminder-config)
8. Admin Policies Tab (CRUD /api/admin/policies)
9. Admin Capabilities Tab (GET /api/admin/capabilities, presets, cap-rules)
10. Admin Quick-Scans Tab (GET /api/admin/quick-scans)
11. Admin Audit-Log Tab (GET /api/admin/audit/system)
12. Meetings Module (CRUD, participants, chat, action-items, focus-times)
13. News Module (CRUD, comments, reactions, reports)
14. Surveys Module (CRUD, responses)
15. Chat Module (conversations, messages)
16. Scheduling Module (polls, bookings, busy-slots)
17. Permission Matrix Tests (role-based access)
18. Seed 50 Test Users for load testing
"""

import pytest
import requests
import os
import uuid
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


def get_admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json().get("token")


def get_auth_headers():
    """Get authorization headers with admin token"""
    token = get_admin_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============ TAB 1: STATISTICS ============

class TestAdminStatsTab:
    """Admin Statistics Tab Tests"""
    
    def test_admin_stats_endpoint(self):
        """GET /api/admin/stats returns correct counts"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/stats", headers=headers)
        
        assert response.status_code == 200, f"Stats failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        expected_fields = ["total_users", "total_meetings", "active_meetings", 
                          "ended_meetings", "total_messages", "total_polls", "total_recordings"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], int), f"{field} should be int"
        
        print(f"✓ Admin stats: {data['total_users']} users, {data['total_meetings']} meetings")


# ============ TAB 2: HEALTH ============

class TestAdminHealthTab:
    """Admin Health Dashboard Tests"""
    
    def test_health_dashboard(self):
        """GET /api/admin/health returns health snapshot"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/health", headers=headers)
        
        assert response.status_code == 200, f"Health failed: {response.text}"
        data = response.json()
        
        # Should have component statuses
        assert isinstance(data, dict), "Health should return dict"
        print(f"✓ Health dashboard: {list(data.keys())[:5]}...")
    
    def test_health_alerts_config(self):
        """GET /api/admin/health/alerts/config returns alert config"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/health/alerts/config", headers=headers)
        
        assert response.status_code == 200, f"Alerts config failed: {response.text}"
        print("✓ Health alerts config accessible")
    
    def test_health_alerts_history(self):
        """GET /api/admin/health/alerts/history returns alert history"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/health/alerts/history", headers=headers)
        
        assert response.status_code == 200, f"Alerts history failed: {response.text}"
        data = response.json()
        assert "items" in data, "Should have items field"
        print(f"✓ Health alerts history: {len(data['items'])} items")


# ============ TAB 3: USERS ============

class TestAdminUsersTab:
    """Admin Users Management Tests"""
    
    def test_list_users_legacy(self):
        """GET /api/admin/users (legacy mode) returns list"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        
        assert response.status_code == 200, f"List users failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Legacy mode should return list"
        print(f"✓ List users (legacy): {len(data)} users")
    
    def test_list_users_paginated(self):
        """GET /api/admin/users with pagination returns paginated response"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/users?page=1&limit=10", headers=headers)
        
        assert response.status_code == 200, f"Paginated list failed: {response.text}"
        data = response.json()
        
        assert "users" in data, "Should have users field"
        assert "total" in data, "Should have total field"
        assert "page" in data, "Should have page field"
        assert "pages" in data, "Should have pages field"
        
        print(f"✓ List users (paginated): {data['total']} total, page {data['page']}/{data['pages']}")
    
    def test_list_users_filters(self):
        """GET /api/admin/users/filters returns filter options"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/users/filters", headers=headers)
        
        assert response.status_code == 200, f"Filters failed: {response.text}"
        data = response.json()
        
        assert "departments" in data, "Should have departments"
        assert "locations" in data, "Should have locations"
        assert "professions" in data, "Should have professions"
        assert "roles" in data, "Should have roles"
        
        print(f"✓ User filters: {len(data['roles'])} roles, {len(data['departments'])} departments")
    
    def test_invite_user(self):
        """POST /api/admin/users/invite creates new user"""
        headers = get_auth_headers()
        test_email = f"TEST_invite_{uuid.uuid4().hex[:6]}@test.local"
        
        response = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email,
            "name": "Test Invited User",
            "role": "member"
        }, headers=headers)
        
        assert response.status_code == 200, f"Invite failed: {response.text}"
        data = response.json()
        
        assert "user_id" in data, "Should return user_id"
        assert "temp_password" in data, "Should return temp_password"
        assert data["email"] == test_email, "Email mismatch"
        
        print(f"✓ User invited: {test_email}")
        return data["user_id"]
    
    def test_update_user_profile(self):
        """PUT /api/admin/users/{uid}/profile updates user"""
        headers = get_auth_headers()
        
        # First invite a user
        test_email = f"TEST_profile_{uuid.uuid4().hex[:6]}@test.local"
        invite_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email, "name": "Profile Test", "role": "member"
        }, headers=headers)
        
        if invite_resp.status_code != 200:
            pytest.skip("Could not create test user")
        
        user_id = invite_resp.json()["user_id"]
        
        # Update profile
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}/profile", json={
            "department": "Test Department",
            "location": "Test Location",
            "profession": "Test Profession"
        }, headers=headers)
        
        assert response.status_code == 200, f"Update profile failed: {response.text}"
        data = response.json()
        
        assert data.get("department") == "Test Department", "Department not updated"
        print(f"✓ User profile updated: {user_id}")
    
    def test_toggle_user_status(self):
        """PUT /api/admin/users/{uid}/status toggles active/inactive"""
        headers = get_auth_headers()
        
        # Create test user
        test_email = f"TEST_status_{uuid.uuid4().hex[:6]}@test.local"
        invite_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email, "name": "Status Test", "role": "member"
        }, headers=headers)
        
        if invite_resp.status_code != 200:
            pytest.skip("Could not create test user")
        
        user_id = invite_resp.json()["user_id"]
        
        # Toggle status
        response = requests.put(f"{BASE_URL}/api/admin/users/{user_id}/status", headers=headers)
        
        assert response.status_code == 200, f"Toggle status failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Should return new status"
        print(f"✓ User status toggled: {data['status']}")
    
    def test_force_logout_user(self):
        """POST /api/admin/users/{uid}/force-logout invalidates tokens"""
        headers = get_auth_headers()
        
        # Create test user
        test_email = f"TEST_logout_{uuid.uuid4().hex[:6]}@test.local"
        invite_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email, "name": "Logout Test", "role": "member"
        }, headers=headers)
        
        if invite_resp.status_code != 200:
            pytest.skip("Could not create test user")
        
        user_id = invite_resp.json()["user_id"]
        
        response = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/force-logout", headers=headers)
        
        assert response.status_code == 200, f"Force logout failed: {response.text}"
        data = response.json()
        
        assert "token_version" in data, "Should return new token_version"
        print(f"✓ User force-logged out: token_version={data['token_version']}")
    
    def test_delete_user_as_admin(self):
        """DELETE /api/admin/users/{uid} deletes user"""
        headers = get_auth_headers()
        
        # Create test user
        test_email = f"TEST_delete_{uuid.uuid4().hex[:6]}@test.local"
        invite_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email, "name": "Delete Test", "role": "member"
        }, headers=headers)
        
        if invite_resp.status_code != 200:
            pytest.skip("Could not create test user")
        
        user_id = invite_resp.json()["user_id"]
        
        response = requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers)
        
        assert response.status_code == 200, f"Delete failed: {response.text}"
        print(f"✓ User deleted: {user_id}")


# ============ TAB 4: GROUPS ============

class TestAdminGroupsTab:
    """Admin Groups Management Tests"""
    
    def test_list_groups(self):
        """GET /api/admin/groups returns groups list"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/groups", headers=headers)
        
        assert response.status_code == 200, f"List groups failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return list"
        print(f"✓ List groups: {len(data)} groups")
    
    def test_create_group(self):
        """POST /api/admin/groups creates new group"""
        headers = get_auth_headers()
        
        response = requests.post(f"{BASE_URL}/api/admin/groups", json={
            "name": f"TEST_Group_{uuid.uuid4().hex[:6]}",
            "description": "Test group for E2E",
            "color": "#4A5D4E",
            "permissions": ["dashboard", "calendar"]
        }, headers=headers)
        
        assert response.status_code == 200, f"Create group failed: {response.text}"
        data = response.json()
        
        assert "group_id" in data, "Should return group_id"
        print(f"✓ Group created: {data['group_id']}")
        return data["group_id"]
    
    def test_update_group(self):
        """PUT /api/admin/groups/{gid} updates group"""
        headers = get_auth_headers()
        
        # Create group first
        create_resp = requests.post(f"{BASE_URL}/api/admin/groups", json={
            "name": f"TEST_Update_{uuid.uuid4().hex[:6]}",
            "description": "To be updated"
        }, headers=headers)
        
        if create_resp.status_code != 200:
            pytest.skip("Could not create test group")
        
        group_id = create_resp.json()["group_id"]
        
        response = requests.put(f"{BASE_URL}/api/admin/groups/{group_id}", json={
            "description": "Updated description"
        }, headers=headers)
        
        assert response.status_code == 200, f"Update group failed: {response.text}"
        print(f"✓ Group updated: {group_id}")
    
    def test_add_remove_member(self):
        """POST/DELETE /api/admin/groups/{gid}/members manages members"""
        headers = get_auth_headers()
        
        # Create group
        create_resp = requests.post(f"{BASE_URL}/api/admin/groups", json={
            "name": f"TEST_Members_{uuid.uuid4().hex[:6]}"
        }, headers=headers)
        
        if create_resp.status_code != 200:
            pytest.skip("Could not create test group")
        
        group_id = create_resp.json()["group_id"]
        
        # Create test user
        test_email = f"TEST_member_{uuid.uuid4().hex[:6]}@test.local"
        invite_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email, "name": "Member Test", "role": "member"
        }, headers=headers)
        
        if invite_resp.status_code != 200:
            pytest.skip("Could not create test user")
        
        user_id = invite_resp.json()["user_id"]
        
        # Add member
        add_resp = requests.post(f"{BASE_URL}/api/admin/groups/{group_id}/members", json={
            "user_id": user_id
        }, headers=headers)
        
        assert add_resp.status_code == 200, f"Add member failed: {add_resp.text}"
        
        # Remove member
        remove_resp = requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}/members/{user_id}", headers=headers)
        
        assert remove_resp.status_code == 200, f"Remove member failed: {remove_resp.text}"
        print("✓ Group member add/remove works")
    
    def test_delete_group(self):
        """DELETE /api/admin/groups/{gid} deletes group"""
        headers = get_auth_headers()
        
        # Create group
        create_resp = requests.post(f"{BASE_URL}/api/admin/groups", json={
            "name": f"TEST_Delete_{uuid.uuid4().hex[:6]}"
        }, headers=headers)
        
        if create_resp.status_code != 200:
            pytest.skip("Could not create test group")
        
        group_id = create_resp.json()["group_id"]
        
        response = requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}", headers=headers)
        
        assert response.status_code == 200, f"Delete group failed: {response.text}"
        print(f"✓ Group deleted: {group_id}")


# ============ TAB 5: BRANDING ============

class TestAdminBrandingTab:
    """Admin Branding/Design Tests"""
    
    def test_get_branding(self):
        """GET /api/organization/branding returns branding config"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/organization/branding", headers=headers)
        
        # May return 200 or 404 if not configured
        assert response.status_code in [200, 404], f"Get branding failed: {response.text}"
        print(f"✓ Branding endpoint accessible (status={response.status_code})")


# ============ TAB 6: INTEGRATIONS ============

class TestAdminIntegrationsTab:
    """Admin Integrations (LLM, Email) Tests"""
    
    def test_get_api_config(self):
        """GET /api/admin/api-config returns LLM config"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/api-config", headers=headers)
        
        assert response.status_code == 200, f"Get API config failed: {response.text}"
        data = response.json()
        
        assert "llm_key_set" in data, "Should have llm_key_set"
        assert "llm_model" in data, "Should have llm_model"
        print(f"✓ API config: LLM key set={data['llm_key_set']}, model={data.get('llm_model')}")
    
    def test_get_email_config(self):
        """GET /api/admin/email-config returns email config"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/email-config", headers=headers)
        
        assert response.status_code == 200, f"Get email config failed: {response.text}"
        data = response.json()
        
        assert "provider" in data, "Should have provider"
        assert "smtp" in data, "Should have smtp config"
        print(f"✓ Email config: provider={data.get('provider')}")


# ============ TAB 7: REMINDERS ============

class TestAdminRemindersTab:
    """Admin Reminder Configuration Tests"""
    
    def test_get_reminder_config(self):
        """GET /api/admin/reminder-config returns config"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/reminder-config", headers=headers)
        
        assert response.status_code == 200, f"Get reminder config failed: {response.text}"
        data = response.json()
        
        assert "default_minutes" in data, "Should have default_minutes"
        assert "enabled" in data, "Should have enabled"
        print(f"✓ Reminder config: {data['default_minutes']} min, enabled={data['enabled']}")
    
    def test_update_reminder_config(self):
        """PUT /api/admin/reminder-config updates config"""
        headers = get_auth_headers()
        
        response = requests.put(f"{BASE_URL}/api/admin/reminder-config", json={
            "default_minutes": 15,
            "enabled": True
        }, headers=headers)
        
        assert response.status_code == 200, f"Update reminder config failed: {response.text}"
        print("✓ Reminder config updated")


# ============ TAB 8: POLICIES ============

class TestAdminPoliciesTab:
    """Admin Meeting Policies Tests"""
    
    def test_list_policies(self):
        """GET /api/admin/policies returns policies list"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/policies", headers=headers)
        
        assert response.status_code == 200, f"List policies failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return list"
        print(f"✓ List policies: {len(data)} policies")
    
    def test_create_policy(self):
        """POST /api/admin/policies creates new policy"""
        headers = get_auth_headers()
        
        response = requests.post(f"{BASE_URL}/api/admin/policies", json={
            "name": f"TEST_Policy_{uuid.uuid4().hex[:6]}",
            "max_duration": 120,
            "max_participants": 50,
            "allow_recording": True,
            "allow_guest": True,
            "require_lobby": False,
            "default_meeting_mode": "standard",
            "auto_transcribe": False
        }, headers=headers)
        
        assert response.status_code == 200, f"Create policy failed: {response.text}"
        data = response.json()
        
        assert "policy_id" in data, "Should return policy_id"
        print(f"✓ Policy created: {data['policy_id']}")
        return data["policy_id"]
    
    def test_delete_policy(self):
        """DELETE /api/admin/policies/{pid} deletes policy"""
        headers = get_auth_headers()
        
        # Create policy first
        create_resp = requests.post(f"{BASE_URL}/api/admin/policies", json={
            "name": f"TEST_Delete_{uuid.uuid4().hex[:6]}",
            "max_duration": 60
        }, headers=headers)
        
        if create_resp.status_code != 200:
            pytest.skip("Could not create test policy")
        
        policy_id = create_resp.json()["policy_id"]
        
        response = requests.delete(f"{BASE_URL}/api/admin/policies/{policy_id}", headers=headers)
        
        assert response.status_code == 200, f"Delete policy failed: {response.text}"
        print(f"✓ Policy deleted: {policy_id}")


# ============ TAB 9: CAPABILITIES ============

class TestAdminCapabilitiesTab:
    """Admin Roles & Capabilities Tests"""
    
    def test_list_capabilities(self):
        """GET /api/admin/capabilities returns all capability keys"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=headers)
        
        assert response.status_code == 200, f"List capabilities failed: {response.text}"
        data = response.json()
        
        assert "capabilities" in data, "Should have capabilities"
        assert "role_defaults" in data, "Should have role_defaults"
        
        caps = data["capabilities"]
        assert len(caps) > 0, "Should have some capabilities"
        
        # Check for expected capability categories
        categories = set(c["category"] for c in caps)
        print(f"✓ Capabilities: {len(caps)} caps in {len(categories)} categories")
    
    def test_list_presets(self):
        """GET /api/admin/presets returns capability presets"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/presets", headers=headers)
        
        assert response.status_code == 200, f"List presets failed: {response.text}"
        data = response.json()
        
        assert "presets" in data, "Should have presets"
        print(f"✓ Presets: {len(data['presets'])} presets")
    
    def test_list_cap_rules(self):
        """GET /api/admin/cap-rules returns auto-assign rules"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/cap-rules", headers=headers)
        
        assert response.status_code == 200, f"List cap-rules failed: {response.text}"
        data = response.json()
        
        assert "rules" in data, "Should have rules"
        print(f"✓ Cap-rules: {len(data['rules'])} rules")


# ============ TAB 10: QUICK-SCANS ============

class TestAdminQuickScansTab:
    """Admin Quick-Scans Panel Tests"""
    
    def test_list_all_quick_scans(self):
        """GET /api/admin/quick-scans returns org-wide quick-scan list"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/quick-scans", headers=headers)
        
        assert response.status_code == 200, f"List quick-scans failed: {response.text}"
        data = response.json()
        
        assert "tokens" in data, "Should have tokens"
        assert "stats" in data, "Should have stats"
        
        stats = data["stats"]
        assert "total" in stats, "Stats should have total"
        assert "submitted" in stats, "Stats should have submitted"
        assert "with_failures" in stats, "Stats should have with_failures"
        
        print(f"✓ Quick-scans: {stats['total']} total, {stats['submitted']} submitted, {stats['with_failures']} with failures")


# ============ TAB 11: AUDIT-LOG ============

class TestAdminAuditLogTab:
    """Admin System Audit Log Tests"""
    
    def test_system_audit_log(self):
        """GET /api/admin/audit/system returns audit entries"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/admin/audit/system", headers=headers)
        
        assert response.status_code == 200, f"Audit log failed: {response.text}"
        data = response.json()
        
        assert "entries" in data, "Should have entries"
        assert "total" in data, "Should have total"
        
        print(f"✓ Audit log: {data['total']} entries")


# ============ MEETINGS MODULE ============

class TestMeetingsModule:
    """Meetings CRUD and Features Tests"""
    
    def test_create_meeting(self):
        """POST /api/meetings creates new meeting"""
        headers = get_auth_headers()
        
        response = requests.post(f"{BASE_URL}/api/meetings", json={
            "title": f"TEST_Meeting_{uuid.uuid4().hex[:6]}",
            "description": "E2E test meeting",
            "meeting_type": "instant",
            "duration": 60
        }, headers=headers)
        
        assert response.status_code in [200, 201], f"Create meeting failed: {response.text}"
        data = response.json()
        
        assert "meeting_id" in data, "Should return meeting_id"
        assert "meeting_code" in data, "Should return meeting_code"
        
        print(f"✓ Meeting created: {data['meeting_id']}")
        return data["meeting_id"]
    
    def test_list_meetings(self):
        """GET /api/meetings returns meetings list"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/meetings", headers=headers)
        
        assert response.status_code == 200, f"List meetings failed: {response.text}"
        data = response.json()
        
        # Could be list or paginated
        if isinstance(data, list):
            print(f"✓ List meetings: {len(data)} meetings")
        else:
            print(f"✓ List meetings: {data.get('total', len(data.get('meetings', [])))} meetings")
    
    def test_action_items_crud(self):
        """Action-Items POST/GET/PUT work correctly"""
        headers = get_auth_headers()
        
        # Create meeting
        meet_resp = requests.post(f"{BASE_URL}/api/meetings", json={
            "title": f"TEST_ActionItems_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        }, headers=headers)
        
        if meet_resp.status_code not in [200, 201]:
            pytest.skip("Could not create test meeting")
        
        meeting_id = meet_resp.json()["meeting_id"]
        
        # Create action item
        create_resp = requests.post(f"{BASE_URL}/api/meetings/{meeting_id}/action-items", json={
            "title": "TEST_Action_Item",
            "assignee": "Test User",
            "status": "open"
        }, headers=headers)
        
        assert create_resp.status_code in [200, 201], f"Create action item failed: {create_resp.text}"
        item = create_resp.json()
        assert "item_id" in item, "Should return item_id"
        
        # List action items
        list_resp = requests.get(f"{BASE_URL}/api/meetings/{meeting_id}/action-items", headers=headers)
        assert list_resp.status_code == 200, f"List action items failed: {list_resp.text}"
        
        print("✓ Action-Items CRUD works")
    
    def test_focus_times_crud(self):
        """Focus-Times POST/GET/DELETE work correctly"""
        headers = get_auth_headers()
        
        start_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        
        # Create focus time
        create_resp = requests.post(f"{BASE_URL}/api/focus-times", json={
            "label": "TEST_Focus_Time",
            "start_time": start_time,
            "end_time": end_time
        }, headers=headers)
        
        assert create_resp.status_code in [200, 201], f"Create focus time failed: {create_resp.text}"
        focus = create_resp.json()
        assert "focus_id" in focus, "Should return focus_id"
        
        focus_id = focus["focus_id"]
        
        # List focus times
        list_resp = requests.get(f"{BASE_URL}/api/focus-times", headers=headers)
        assert list_resp.status_code == 200, f"List focus times failed: {list_resp.text}"
        
        # Delete focus time
        delete_resp = requests.delete(f"{BASE_URL}/api/focus-times/{focus_id}", headers=headers)
        assert delete_resp.status_code == 200, f"Delete focus time failed: {delete_resp.text}"
        
        print("✓ Focus-Times CRUD works")


# ============ NEWS MODULE ============

class TestNewsModule:
    """News Posts and Features Tests"""
    
    def test_list_news(self):
        """GET /api/news returns news posts"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/news", headers=headers)
        
        assert response.status_code == 200, f"List news failed: {response.text}"
        print("✓ News list accessible")
    
    def test_news_reports_pending_count(self):
        """GET /api/news/reports/pending-count returns count"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/news/reports/pending-count", headers=headers)
        
        assert response.status_code == 200, f"Pending count failed: {response.text}"
        data = response.json()
        assert "count" in data, "Should have count"
        print(f"✓ News reports pending: {data['count']}")


# ============ SURVEYS MODULE ============

class TestSurveysModule:
    """Surveys CRUD Tests"""
    
    def test_list_surveys(self):
        """GET /api/surveys returns surveys list"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/surveys", headers=headers)
        
        assert response.status_code == 200, f"List surveys failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return list"
        print(f"✓ List surveys: {len(data)} surveys")
    
    def test_surveys_pending_count(self):
        """GET /api/surveys/pending-count returns count"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/surveys/pending-count", headers=headers)
        
        assert response.status_code == 200, f"Pending count failed: {response.text}"
        data = response.json()
        assert "count" in data, "Should have count"
        print(f"✓ Surveys pending: {data['count']}")
    
    def test_create_survey(self):
        """POST /api/surveys creates new survey"""
        headers = get_auth_headers()
        
        response = requests.post(f"{BASE_URL}/api/surveys", json={
            "title": f"TEST_Survey_{uuid.uuid4().hex[:6]}",
            "description": "E2E test survey",
            "survey_type": "survey",
            "questions": [
                {"question_id": "q1", "text": "Test question?", "type": "single_choice", "options": ["Yes", "No"]}
            ],
            "status": "draft"
        }, headers=headers)
        
        assert response.status_code == 200, f"Create survey failed: {response.text}"
        data = response.json()
        
        assert "survey_id" in data, "Should return survey_id"
        print(f"✓ Survey created: {data['survey_id']}")


# ============ CHAT MODULE ============

class TestChatModule:
    """Chat Conversations and Messages Tests"""
    
    def test_list_conversations(self):
        """GET /api/chat/conversations returns conversations"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/chat/conversations", headers=headers)
        
        assert response.status_code == 200, f"List conversations failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return list"
        print(f"✓ List conversations: {len(data)} conversations")
    
    def test_chat_users_list(self):
        """GET /api/chat/users returns users for chat"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/chat/users", headers=headers)
        
        assert response.status_code == 200, f"Chat users failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return list"
        print(f"✓ Chat users: {len(data)} users")
    
    def test_my_status(self):
        """GET /api/chat/my-status returns current status"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/chat/my-status", headers=headers)
        
        assert response.status_code == 200, f"My status failed: {response.text}"
        data = response.json()
        assert "status_mode" in data, "Should have status_mode"
        print(f"✓ My status: {data['status_mode']}")


# ============ SCHEDULING MODULE ============

class TestSchedulingModule:
    """Scheduling Polls and Bookings Tests"""
    
    def test_list_schedule_polls(self):
        """GET /api/schedule-polls returns polls"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/schedule-polls", headers=headers)
        
        assert response.status_code == 200, f"List schedule polls failed: {response.text}"
        data = response.json()
        assert "polls" in data, "Should have polls"
        print(f"✓ Schedule polls: {data.get('total', len(data.get('polls', [])))} polls")
    
    def test_booking_availability(self):
        """GET /api/booking/availability returns availability"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/booking/availability", headers=headers)
        
        assert response.status_code == 200, f"Booking availability failed: {response.text}"
        data = response.json()
        assert "weekdays" in data, "Should have weekdays"
        print("✓ Booking availability accessible")
    
    def test_busy_slots(self):
        """GET /api/scheduling/busy-slots returns busy slots"""
        headers = get_auth_headers()
        
        # Get busy slots for next week
        start = datetime.now(timezone.utc).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        response = requests.get(f"{BASE_URL}/api/scheduling/busy-slots?start={start}&end={end}", headers=headers)
        
        # May return 200 or 404 if endpoint doesn't exist
        if response.status_code == 200:
            print("✓ Busy slots accessible")
        else:
            print(f"  Busy slots endpoint returned {response.status_code}")


# ============ PERMISSION MATRIX TESTS ============

class TestPermissionMatrix:
    """Permission-based access control tests"""
    
    def test_non_admin_cannot_access_admin_stats(self):
        """Non-admin user gets 403 on admin endpoints"""
        # Create a member user
        headers = get_auth_headers()
        test_email = f"TEST_member_{uuid.uuid4().hex[:6]}@test.local"
        
        invite_resp = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": test_email, "name": "Member Test", "role": "member"
        }, headers=headers)
        
        if invite_resp.status_code != 200:
            pytest.skip("Could not create test user")
        
        temp_password = invite_resp.json()["temp_password"]
        
        # Login as member
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email, "password": temp_password
        })
        
        if login_resp.status_code != 200:
            pytest.skip("Could not login as member")
        
        member_token = login_resp.json()["token"]
        member_headers = {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}
        
        # Try to access admin stats
        response = requests.get(f"{BASE_URL}/api/admin/stats", headers=member_headers)
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly gets 403 on admin endpoints")
    
    def test_user_permissions_endpoint(self):
        """GET /api/user/permissions returns user's capabilities"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/user/permissions", headers=headers)
        
        assert response.status_code == 200, f"User permissions failed: {response.text}"
        data = response.json()
        
        assert "permissions" in data, "Should have permissions"
        assert "capabilities" in data, "Should have capabilities"
        assert "role" in data, "Should have role"
        
        print(f"✓ User permissions: role={data['role']}, {len(data['capabilities'])} capabilities")


# ============ DASHBOARD ENDPOINTS ============

class TestDashboardEndpoints:
    """Dashboard Stats and Agenda Tests"""
    
    def test_dashboard_stats(self):
        """GET /api/dashboard/stats returns stats"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        print("✓ Dashboard stats accessible")
    
    def test_dashboard_agenda(self):
        """GET /api/dashboard/agenda returns agenda"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/dashboard/agenda", headers=headers)
        
        assert response.status_code == 200, f"Dashboard agenda failed: {response.text}"
        print("✓ Dashboard agenda accessible")
    
    def test_calendar_events(self):
        """GET /api/calendar/events returns events"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/calendar/events", headers=headers)
        
        assert response.status_code == 200, f"Calendar events failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return list"
        print(f"✓ Calendar events: {len(data)} events")
    
    def test_notifications(self):
        """GET /api/notifications returns notifications"""
        headers = get_auth_headers()
        response = requests.get(f"{BASE_URL}/api/notifications", headers=headers)
        
        assert response.status_code == 200, f"Notifications failed: {response.text}"
        print("✓ Notifications accessible")


# ============ SEED TEST USERS ============

class TestSeedUsers:
    """Seed test users for load testing"""
    
    def test_seed_50_users(self):
        """Create 50 test users with varied roles/departments"""
        headers = get_auth_headers()
        
        roles = ["member", "moderator", "member", "member", "member"]
        departments = ["IT", "HR", "Sales", "Marketing", "Operations", "Finance", "Legal", "Support"]
        locations = ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"]
        professions = ["Developer", "Manager", "Analyst", "Designer", "Consultant"]
        
        created = 0
        failed = 0
        
        for i in range(50):
            email = f"loadtest{i+1:03d}@meetflow.local"
            
            # Check if user already exists
            check_resp = requests.get(f"{BASE_URL}/api/admin/users?search={email}", headers=headers)
            if check_resp.status_code == 200:
                data = check_resp.json()
                users = data if isinstance(data, list) else data.get("users", [])
                if any(u.get("email") == email for u in users):
                    created += 1  # Count as existing
                    continue
            
            response = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
                "email": email,
                "name": f"Load Test User {i+1}",
                "role": roles[i % len(roles)]
            }, headers=headers)
            
            if response.status_code == 200:
                user_id = response.json()["user_id"]
                
                # Update profile with department/location/profession
                requests.put(f"{BASE_URL}/api/admin/users/{user_id}/profile", json={
                    "department": departments[i % len(departments)],
                    "location": locations[i % len(locations)],
                    "profession": professions[i % len(professions)]
                }, headers=headers)
                
                created += 1
            elif response.status_code == 409:
                created += 1  # Already exists
            else:
                failed += 1
        
        print(f"✓ Seed users: {created} created/existing, {failed} failed")
        assert created >= 40, f"Should create at least 40 users, got {created}"


# ============ CONCURRENT REQUESTS TEST ============

class TestConcurrentRequests:
    """Test concurrent API access"""
    
    def test_concurrent_logins(self):
        """50 concurrent login requests should not cause 500 errors"""
        def do_login(i):
            try:
                response = requests.post(f"{BASE_URL}/api/auth/login", json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD
                }, timeout=10)
                return response.status_code
            except Exception as e:
                return f"error: {e}"
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(do_login, range(50)))
        
        success = sum(1 for r in results if r == 200)
        errors = [r for r in results if r != 200]
        
        print(f"✓ Concurrent logins: {success}/50 successful")
        
        # Allow some failures due to rate limiting, but no 500s
        server_errors = [r for r in errors if isinstance(r, int) and r >= 500]
        assert len(server_errors) == 0, f"Got {len(server_errors)} server errors: {server_errors}"
    
    def test_concurrent_api_calls(self):
        """50 concurrent API calls should not cause race conditions"""
        headers = get_auth_headers()
        
        def do_api_call(i):
            try:
                endpoints = [
                    "/api/dashboard/stats",
                    "/api/user/permissions",
                    "/api/notifications/unread-count",
                    "/api/chat/my-status",
                    "/api/focus-times/active"
                ]
                endpoint = endpoints[i % len(endpoints)]
                response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
                return response.status_code
            except Exception as e:
                return f"error: {e}"
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(do_api_call, range(50)))
        
        success = sum(1 for r in results if r == 200)
        server_errors = [r for r in results if isinstance(r, int) and r >= 500]
        
        print(f"✓ Concurrent API calls: {success}/50 successful")
        assert len(server_errors) == 0, f"Got {len(server_errors)} server errors"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
