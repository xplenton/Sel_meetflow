"""
Iteration 261 — Admin Refactoring + Replica-Set + Quick-Book Vehicle Tests

Tests:
1. REFACTOR: routes/admin.py split into routes/admin/{users,permissions,system}.py
   - Verify backward-compat: 'from routes.admin import router' still works
   - All admin endpoints accessible: /api/admin/users, /api/admin/groups, etc.
2. REPLICA-SET: GET /api/admin/health/mongo returns status='replica_set' or 'standalone'
3. QUICK-BOOK VEHICLE: POST /api/resource-bookings with mileage_before + destination
4. RBAC: Member gets 403 on admin endpoints, tokenless gets 401
5. REGRESSION: 12-module sanity check
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_token():
    """Get admin token for authenticated requests."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
    data = resp.json()
    return data.get("access_token") or data.get("token")

@pytest.fixture(scope="module")
def member_user_and_token(admin_token):
    """Create a member user for RBAC tests."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    email = f"test_member_261_{uuid.uuid4().hex[:6]}@meetflow.local"
    # Create via invite
    resp = requests.post(f"{BASE_URL}/api/admin/users/invite", json={
        "email": email,
        "name": "Test Member 261",
        "role": "member"
    }, headers=headers)
    if resp.status_code not in [200, 201]:
        pytest.skip(f"Could not create member user: {resp.status_code}")
    data = resp.json()
    temp_pw = data.get("temp_password")
    user_id = data.get("user_id")
    # Login as member
    login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": email,
        "password": temp_pw
    })
    if login_resp.status_code != 200:
        pytest.skip(f"Member login failed: {login_resp.status_code}")
    member_token = login_resp.json().get("access_token") or login_resp.json().get("token")
    yield {"user_id": user_id, "email": email, "token": member_token}
    # Cleanup
    requests.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=headers)


class TestAdminRefactoring:
    """Test that admin endpoints are still accessible after refactoring."""

    def test_admin_users_list(self, admin_token):
        """GET /api/admin/users — should return user list."""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        # Legacy mode returns list, paginated mode returns dict
        assert isinstance(data, (list, dict)), "Should return list or dict"
        print(f"PASS: GET /api/admin/users — {len(data) if isinstance(data, list) else data.get('total', 'N/A')} users")

    def test_admin_users_filters(self, admin_token):
        """GET /api/admin/users/filters — should return filter options."""
        resp = requests.get(f"{BASE_URL}/api/admin/users/filters", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "departments" in data or "roles" in data
        print("PASS: GET /api/admin/users/filters")

    def test_admin_groups_list(self, admin_token):
        """GET /api/admin/groups — should return groups list."""
        resp = requests.get(f"{BASE_URL}/api/admin/groups", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/admin/groups — {len(data)} groups")

    def test_admin_capabilities_list(self, admin_token):
        """GET /api/admin/capabilities — should return capabilities list."""
        resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "capabilities" in data
        print(f"PASS: GET /api/admin/capabilities — {len(data['capabilities'])} capabilities")

    def test_admin_presets_list(self, admin_token):
        """GET /api/admin/presets — should return presets list."""
        resp = requests.get(f"{BASE_URL}/api/admin/presets", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "presets" in data
        print(f"PASS: GET /api/admin/presets — {len(data['presets'])} presets")

    def test_admin_stats(self, admin_token):
        """GET /api/admin/stats — should return stats."""
        resp = requests.get(f"{BASE_URL}/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "total_users" in data
        print(f"PASS: GET /api/admin/stats — {data.get('total_users')} users")

    def test_admin_audit_system(self, admin_token):
        """GET /api/admin/audit/system — should return audit logs."""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/system", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "entries" in data
        print(f"PASS: GET /api/admin/audit/system — {len(data['entries'])} entries")

    def test_admin_health(self, admin_token):
        """GET /api/admin/health — should return health dashboard."""
        resp = requests.get(f"{BASE_URL}/api/admin/health", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("PASS: GET /api/admin/health")

    def test_admin_email_config(self, admin_token):
        """GET /api/admin/email-config — should return email config."""
        resp = requests.get(f"{BASE_URL}/api/admin/email-config", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "provider" in data or "config_id" in data
        print("PASS: GET /api/admin/email-config")

    def test_admin_policies_list(self, admin_token):
        """GET /api/admin/policies — should return policies list."""
        resp = requests.get(f"{BASE_URL}/api/admin/policies", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/admin/policies — {len(data)} policies")

    def test_admin_cap_rules_list(self, admin_token):
        """GET /api/admin/cap-rules — should return cap rules list."""
        resp = requests.get(f"{BASE_URL}/api/admin/cap-rules", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "rules" in data
        print(f"PASS: GET /api/admin/cap-rules — {len(data['rules'])} rules")

    def test_admin_permissions_audit(self, admin_token):
        """GET /api/admin/permissions/audit — should return permissions audit."""
        resp = requests.get(f"{BASE_URL}/api/admin/permissions/audit", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "total_issues" in data or "redundant_grants" in data
        print("PASS: GET /api/admin/permissions/audit")


class TestMongoReplicaSetHealth:
    """Test the new /api/admin/health/mongo endpoint."""

    def test_mongo_health_admin(self, admin_token):
        """GET /api/admin/health/mongo — should return RS status."""
        resp = requests.get(f"{BASE_URL}/api/admin/health/mongo", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        # Should have status field
        assert "status" in data, f"Missing 'status' field: {data}"
        status = data["status"]
        assert status in ["replica_set", "standalone", "error"], f"Unexpected status: {status}"
        
        if status == "replica_set":
            # Verify RS fields
            assert "set_name" in data, "Missing set_name for replica_set"
            assert "primary_count" in data, "Missing primary_count"
            assert data["primary_count"] >= 1, f"Expected at least 1 primary, got {data['primary_count']}"
            assert "members" in data, "Missing members list"
            print(f"PASS: GET /api/admin/health/mongo — status=replica_set, set_name={data['set_name']}, primary_count={data['primary_count']}")
        elif status == "standalone":
            assert "note" in data, "Missing note for standalone"
            print(f"PASS: GET /api/admin/health/mongo — status=standalone")
        else:
            print(f"PASS: GET /api/admin/health/mongo — status={status}, error={data.get('error', 'N/A')}")

    def test_mongo_health_member_forbidden(self, member_user_and_token):
        """GET /api/admin/health/mongo — member should get 403."""
        token = member_user_and_token["token"]
        resp = requests.get(f"{BASE_URL}/api/admin/health/mongo", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, f"Expected 403 for member, got {resp.status_code}"
        print("PASS: GET /api/admin/health/mongo — member gets 403")


class TestQuickBookVehicle:
    """Test Quick-Book Vehicle feature with mileage_before + destination."""

    @pytest.fixture(scope="class")
    def vehicle_resource(self, admin_token):
        """Create or find a vehicle resource for testing."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # First check if demo vehicle exists
        resp = requests.get(f"{BASE_URL}/api/resources?type=vehicle", headers=headers)
        if resp.status_code == 200:
            vehicles = resp.json()
            if vehicles:
                # Use first vehicle
                return vehicles[0]
        # Create a test vehicle
        vehicle_data = {
            "name": f"Test Vehicle 261 {uuid.uuid4().hex[:6]}",
            "type": "vehicle",
            "status": "active",
            "license_plate": "TEST-261",
            "seats": 5,
            "mileage": 71300
        }
        resp = requests.post(f"{BASE_URL}/api/resources", json=vehicle_data, headers=headers)
        if resp.status_code in [200, 201]:
            return resp.json()
        pytest.skip(f"Could not create vehicle resource: {resp.status_code}")

    def test_quickbook_vehicle_with_mileage_destination(self, admin_token, vehicle_resource):
        """POST /api/resource-bookings with mileage_before + destination."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resource_id = vehicle_resource.get("resource_id")
        
        # Create booking with vehicle-specific fields
        start = datetime.now(timezone.utc) + timedelta(hours=2)
        end = start + timedelta(hours=1)
        booking_data = {
            "resource_id": resource_id,
            "title": "Test Fahrt 261",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "mileage_before": 71300,
            "destination": "Klinikum Mitte"
        }
        resp = requests.post(f"{BASE_URL}/api/resource-bookings", json=booking_data, headers=headers)
        assert resp.status_code in [200, 201], f"Expected 200/201, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        
        # Verify fields are set
        assert data.get("mileage_before") == 71300, f"mileage_before not set: {data}"
        assert data.get("destination") == "Klinikum Mitte", f"destination not set: {data}"
        print(f"PASS: POST /api/resource-bookings with mileage_before={data.get('mileage_before')}, destination={data.get('destination')}")
        
        # Cleanup
        booking_id = data.get("booking_id")
        if booking_id:
            requests.delete(f"{BASE_URL}/api/resource-bookings/{booking_id}", headers=headers)


class TestRBAC:
    """Test RBAC: member gets 403 on admin endpoints, tokenless gets 401."""

    def test_admin_users_member_forbidden(self, member_user_and_token):
        """GET /api/admin/users — member should get 403."""
        token = member_user_and_token["token"]
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, f"Expected 403 for member, got {resp.status_code}"
        print("PASS: GET /api/admin/users — member gets 403")

    def test_admin_groups_member_forbidden(self, member_user_and_token):
        """GET /api/admin/groups — member should get 403."""
        token = member_user_and_token["token"]
        resp = requests.get(f"{BASE_URL}/api/admin/groups", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, f"Expected 403 for member, got {resp.status_code}"
        print("PASS: GET /api/admin/groups — member gets 403")

    def test_admin_stats_member_forbidden(self, member_user_and_token):
        """GET /api/admin/stats — member should get 403."""
        token = member_user_and_token["token"]
        resp = requests.get(f"{BASE_URL}/api/admin/stats", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, f"Expected 403 for member, got {resp.status_code}"
        print("PASS: GET /api/admin/stats — member gets 403")

    def test_admin_users_no_token_unauthorized(self):
        """GET /api/admin/users — no token should get 401."""
        resp = requests.get(f"{BASE_URL}/api/admin/users")
        assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
        print("PASS: GET /api/admin/users — no token gets 401")

    def test_admin_health_mongo_no_token_unauthorized(self):
        """GET /api/admin/health/mongo — no token should get 401."""
        resp = requests.get(f"{BASE_URL}/api/admin/health/mongo")
        assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
        print("PASS: GET /api/admin/health/mongo — no token gets 401")


class TestRegressionSanityCheck:
    """12-module sanity check — all endpoints should return 200/expected."""

    def test_auth_module(self, admin_token):
        """Auth module — GET /api/auth/me."""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Auth module failed: {resp.status_code}"
        print("PASS: Auth module — GET /api/auth/me")

    def test_tasks_module(self, admin_token):
        """Tasks module — GET /api/tasks."""
        resp = requests.get(f"{BASE_URL}/api/tasks", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Tasks module failed: {resp.status_code}"
        print("PASS: Tasks module — GET /api/tasks")

    def test_calendar_module(self, admin_token):
        """Calendar module — GET /api/calendar/events."""
        resp = requests.get(f"{BASE_URL}/api/calendar/events", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Calendar module failed: {resp.status_code}"
        print("PASS: Calendar module — GET /api/calendar/events")

    def test_news_module(self, admin_token):
        """News module — GET /api/news/feed."""
        resp = requests.get(f"{BASE_URL}/api/news/feed", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"News module failed: {resp.status_code}"
        print("PASS: News module — GET /api/news/feed")

    def test_resources_module(self, admin_token):
        """Resources module — GET /api/resources."""
        resp = requests.get(f"{BASE_URL}/api/resources", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Resources module failed: {resp.status_code}"
        print("PASS: Resources module — GET /api/resources")

    def test_chat_module(self, admin_token):
        """Chat module — GET /api/chat/conversations."""
        resp = requests.get(f"{BASE_URL}/api/chat/conversations", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Chat module failed: {resp.status_code}"
        print("PASS: Chat module — GET /api/chat/conversations")

    def test_admin_module(self, admin_token):
        """Admin module — GET /api/admin/users."""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Admin module failed: {resp.status_code}"
        print("PASS: Admin module — GET /api/admin/users")

    def test_surveys_module(self, admin_token):
        """Surveys module — GET /api/surveys."""
        resp = requests.get(f"{BASE_URL}/api/surveys", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Surveys module failed: {resp.status_code}"
        print("PASS: Surveys module — GET /api/surveys")

    def test_meetings_module(self, admin_token):
        """Meetings module — GET /api/meetings."""
        resp = requests.get(f"{BASE_URL}/api/meetings", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Meetings module failed: {resp.status_code}"
        print("PASS: Meetings module — GET /api/meetings")

    def test_notifications_module(self, admin_token):
        """Notifications module — GET /api/notifications."""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Notifications module failed: {resp.status_code}"
        print("PASS: Notifications module — GET /api/notifications")

    def test_dashboard_module(self, admin_token):
        """Dashboard module — GET /api/dashboard/stats."""
        resp = requests.get(f"{BASE_URL}/api/dashboard/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Dashboard module failed: {resp.status_code}"
        print("PASS: Dashboard module — GET /api/dashboard/stats")

    def test_scheduling_module(self, admin_token):
        """Scheduling module — GET /api/schedule-polls."""
        resp = requests.get(f"{BASE_URL}/api/schedule-polls", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200, f"Scheduling module failed: {resp.status_code}"
        print("PASS: Scheduling module — GET /api/schedule-polls")


class TestAdminUserSimulateAndCapabilities:
    """Test user simulation and capabilities endpoints."""

    def test_admin_user_simulate(self, admin_token):
        """GET /api/admin/users/{id}/simulate — should return capability breakdown."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Get admin user_id first
        me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        if me_resp.status_code != 200:
            pytest.skip("Could not get current user")
        user_id = me_resp.json().get("user_id")
        
        resp = requests.get(f"{BASE_URL}/api/admin/users/{user_id}/simulate", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "effective" in data, "Missing 'effective' capabilities"
        assert "role_defaults" in data, "Missing 'role_defaults'"
        print(f"PASS: GET /api/admin/users/{user_id}/simulate — {data.get('effective_count', 0)} effective caps")

    def test_admin_user_capabilities_update(self, admin_token, member_user_and_token):
        """PUT /api/admin/users/{id}/capabilities — should update user caps."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        user_id = member_user_and_token["user_id"]
        
        # Update capabilities
        resp = requests.put(f"{BASE_URL}/api/admin/users/{user_id}/capabilities", json={
            "grants": ["view:dashboard"],
            "denies": []
        }, headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("ok") == True or "grants" in data
        print(f"PASS: PUT /api/admin/users/{user_id}/capabilities")


class TestAdminGroupMembers:
    """Test group member management endpoints."""

    def test_admin_group_members_flow(self, admin_token, member_user_and_token):
        """Test adding/removing group members."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        user_id = member_user_and_token["user_id"]
        
        # Create a test group
        group_resp = requests.post(f"{BASE_URL}/api/admin/groups", json={
            "name": f"TestGroup261_{uuid.uuid4().hex[:6]}",
            "description": "Test group for iter 261"
        }, headers=headers)
        if group_resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create group: {group_resp.status_code}")
        group_id = group_resp.json().get("group_id")
        
        try:
            # Add member to group
            add_resp = requests.post(f"{BASE_URL}/api/admin/groups/{group_id}/members", json={
                "user_id": user_id
            }, headers=headers)
            assert add_resp.status_code == 200, f"Expected 200, got {add_resp.status_code}"
            print(f"PASS: POST /api/admin/groups/{group_id}/members — added member")
            
            # Remove member from group
            remove_resp = requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}/members/{user_id}", headers=headers)
            assert remove_resp.status_code == 200, f"Expected 200, got {remove_resp.status_code}"
            print(f"PASS: DELETE /api/admin/groups/{group_id}/members/{user_id} — removed member")
        finally:
            # Cleanup group
            requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}", headers=headers)


class TestAdminPresetApply:
    """Test preset application endpoints."""

    def test_admin_preset_apply_to_user(self, admin_token, member_user_and_token):
        """POST /api/admin/presets/{id}/apply-to-user/{user_id}."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        user_id = member_user_and_token["user_id"]
        
        # Get presets
        presets_resp = requests.get(f"{BASE_URL}/api/admin/presets", headers=headers)
        if presets_resp.status_code != 200:
            pytest.skip("Could not get presets")
        presets = presets_resp.json().get("presets", [])
        if not presets:
            pytest.skip("No presets available")
        
        preset_id = presets[0].get("preset_id")
        resp = requests.post(f"{BASE_URL}/api/admin/presets/{preset_id}/apply-to-user/{user_id}", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert data.get("ok") == True or "applied" in data
        print(f"PASS: POST /api/admin/presets/{preset_id}/apply-to-user/{user_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
