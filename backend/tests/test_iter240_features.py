"""
Iter 240 Backend Tests:
1. Permissions: Member gets view:resources + resources.book + resources.book_with_approval
2. Permissions: Member can GET /api/resources?type=room (200 instead of 403)
3. Floorplan Items: GET /api/floorplans/{id}/items?type=room (new endpoint)
4. Chat: POST /api/chat/conversations (direct DM creation, idempotent)
5. ResourcesPage Cleanup: Verwaltung-Button + Lageplan-Tab removed (frontend test)
6. ResourcesPage Subview: Liste/Lageplan toggle per type tab (frontend test)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth cookies."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@meetflow.com",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    if "token" in data:
        session.headers.update({"Authorization": f"Bearer {data['token']}"})
    return session


@pytest.fixture(scope="module")
def member_user(admin_session):
    """Create a fresh member user for permission testing.

    Iter 371 — Self-registered users land in the `Gast` group, which since
    iter 289 carries `role_override='guest'`. That effectively downgrades
    the user's role to guest and strips all member-level caps for permission
    tests. To test pure member-defaults, we use the admin session to remove
    the new user from the Gast group right after registration.
    """
    unique_id = uuid.uuid4().hex[:8]
    email = f"test_member_{unique_id}@meetflow.com"
    password = "testpass123"

    # Register new member
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": password,
        "name": f"Test Member {unique_id}"
    })

    if resp.status_code not in [200, 201]:
        # User might already exist, try login
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        if resp.status_code != 200:
            pytest.skip(f"Could not create/login test member: {resp.text}")

    data = resp.json()
    user_id = data.get("user_id")

    # Iter 371 — Remove the user from the auto-assigned Gast group so the
    # role_override='guest' doesn't downgrade them below member level.
    try:
        groups_resp = admin_session.get(f"{BASE_URL}/api/admin/groups")
        if groups_resp.status_code == 200:
            for grp in groups_resp.json() or []:
                if grp.get("name") == "Gast" and user_id in (grp.get("members") or []):
                    admin_session.delete(
                        f"{BASE_URL}/api/admin/groups/{grp['group_id']}/members/{user_id}"
                    )
    except Exception:
        pass  # Fall back to whatever default permissions the user has.

    # Create session for member
    member_session = requests.Session()
    member_session.headers.update({"Content-Type": "application/json"})
    if "token" in data:
        member_session.headers.update({"Authorization": f"Bearer {data['token']}"})

    return {
        "session": member_session,
        "email": email,
        "user_id": user_id,
        "token": data.get("token")
    }


class TestMemberPermissions:
    """Test Iter 240 permission defaults for member role."""
    
    def test_member_has_view_resources_cap(self, member_user):
        """Member should have view:resources capability."""
        resp = member_user["session"].get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200, f"Failed to get permissions: {resp.text}"
        data = resp.json()
        
        caps = data.get("capabilities", [])
        assert "view:resources" in caps, f"Member missing view:resources. Got: {caps}"
    
    def test_member_has_resources_book_cap(self, member_user):
        """Member should have resources.book capability."""
        resp = member_user["session"].get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        caps = data.get("capabilities", [])
        assert "resources.book" in caps, f"Member missing resources.book. Got: {caps}"
    
    def test_member_has_resources_book_with_approval_cap(self, member_user):
        """Member should still be allowed to book approval-required rooms.

        Iter 370 — Ghost-Cap `resources.book_with_approval` removed; the
        permission to book approval-required rooms is implicit in
        `resources.book` (backend auto-sets `requires_approval` based on
        the resource). We keep the test to assert the behaviour didn't
        regress — but assert on `resources.book` instead of the dead key.
        """
        resp = member_user["session"].get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()

        caps = data.get("capabilities", [])
        assert "resources.book" in caps, f"Member missing resources.book. Got: {caps}"
    
    def test_member_does_not_have_resources_approve(self, member_user):
        """Member should NOT have resources.approve capability (moderator/admin only)."""
        resp = member_user["session"].get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        caps = data.get("capabilities", [])
        assert "resources.approve" not in caps, f"Member should NOT have resources.approve. Got: {caps}"
    
    def test_member_does_not_have_resources_manage(self, member_user):
        """Member should NOT have resources.manage capability (admin only)."""
        resp = member_user["session"].get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        caps = data.get("capabilities", [])
        assert "resources.manage" not in caps, f"Member should NOT have resources.manage. Got: {caps}"


class TestMemberResourceAccess:
    """Test that member can access resources (200 instead of 403)."""
    
    def test_member_can_get_rooms(self, member_user):
        """GET /api/resources?type=room should return 200 for member."""
        resp = member_user["session"].get(f"{BASE_URL}/api/resources?type=room")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"
    
    def test_member_can_get_desks(self, member_user):
        """GET /api/resources?type=desk should return 200 for member."""
        resp = member_user["session"].get(f"{BASE_URL}/api/resources?type=desk")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    def test_member_can_get_vehicles(self, member_user):
        """GET /api/resources?type=vehicle should return 200 for member."""
        resp = member_user["session"].get(f"{BASE_URL}/api/resources?type=vehicle")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


class TestFloorplanItemsEndpoint:
    """Test GET /api/floorplans/{id}/items endpoint (new in Iter 240)."""
    
    def test_floorplan_items_endpoint_exists(self, admin_session):
        """GET /api/floorplans/{id}/items should return 200."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    def test_floorplan_items_with_type_room(self, admin_session):
        """GET /api/floorplans/{id}/items?type=room should filter to rooms."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items?type=room")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "items" in data, "Response missing 'items' field"
        assert "desks" in data, "Response missing 'desks' field (backwards compat)"
        
        # All items should be rooms (if any)
        for item in data.get("items", []):
            if item.get("type"):
                assert item["type"] == "room", f"Expected room, got {item['type']}"
    
    def test_floorplan_items_with_type_desk(self, admin_session):
        """GET /api/floorplans/{id}/items?type=desk should filter to desks."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items?type=desk")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "items" in data
        
        # All items should be desks (if any)
        for item in data.get("items", []):
            if item.get("type"):
                assert item["type"] == "desk", f"Expected desk, got {item['type']}"
    
    def test_floorplan_items_with_type_vehicle(self, admin_session):
        """GET /api/floorplans/{id}/items?type=vehicle should filter to vehicles."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items?type=vehicle")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "items" in data
    
    def test_floorplan_items_without_type_returns_all(self, admin_session):
        """GET /api/floorplans/{id}/items without type should return all types."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "items" in data
        assert "floor_plan_id" in data
        assert "at" in data  # timestamp
    
    def test_floorplan_items_response_structure(self, admin_session):
        """Response should have floor_plan_id, at, items, desks fields."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/items")
        assert resp.status_code == 200
        
        data = resp.json()
        assert "floor_plan_id" in data, "Missing floor_plan_id"
        assert "at" in data, "Missing 'at' timestamp"
        assert "items" in data, "Missing 'items' array"
        assert "desks" in data, "Missing 'desks' array (backwards compat)"
    
    def test_legacy_floorplan_desks_still_works(self, admin_session):
        """GET /api/floorplans/{id}/desks (legacy) should still work."""
        resp = admin_session.get(f"{BASE_URL}/api/floorplans/default/desks")
        assert resp.status_code == 200, f"Legacy endpoint failed: {resp.text}"
        
        data = resp.json()
        assert "desks" in data, "Legacy endpoint missing 'desks' field"


class TestChatConversations:
    """Test POST /api/chat/conversations for DM creation (Iter 240)."""
    
    def test_create_direct_conversation(self, admin_session):
        """POST /api/chat/conversations with type=direct should create DM."""
        # Get admin user_id
        me_resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        admin_id = me_resp.json().get("user_id")
        
        # Get another user to DM
        users_resp = admin_session.get(f"{BASE_URL}/api/users")
        if users_resp.status_code != 200:
            pytest.skip("Could not get users list")
        
        users = users_resp.json()
        other_user = next((u for u in users if u.get("user_id") != admin_id), None)
        
        if not other_user:
            pytest.skip("No other user available for DM test")
        
        other_id = other_user["user_id"]
        
        # Create DM
        resp = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [admin_id, other_id]
        })
        assert resp.status_code == 200, f"Failed to create DM: {resp.text}"
        
        data = resp.json()
        assert "conversation_id" in data, "Response missing conversation_id"
        assert data.get("type") == "direct", "Conversation type should be 'direct'"
        
        # Store for idempotency test
        return data["conversation_id"], admin_id, other_id
    
    def test_create_direct_conversation_idempotent(self, admin_session):
        """Second POST with same members should return same conversation (idempotent)."""
        # Get admin user_id
        me_resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        admin_id = me_resp.json().get("user_id")
        
        # Get another user
        users_resp = admin_session.get(f"{BASE_URL}/api/users")
        if users_resp.status_code != 200:
            pytest.skip("Could not get users list")
        
        users = users_resp.json()
        other_user = next((u for u in users if u.get("user_id") != admin_id), None)
        
        if not other_user:
            pytest.skip("No other user available for DM test")
        
        other_id = other_user["user_id"]
        
        # First call
        resp1 = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [admin_id, other_id]
        })
        assert resp1.status_code == 200
        conv_id_1 = resp1.json().get("conversation_id")
        
        # Second call with same members
        resp2 = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [admin_id, other_id]
        })
        assert resp2.status_code == 200
        conv_id_2 = resp2.json().get("conversation_id")
        
        # Should be the same conversation
        assert conv_id_1 == conv_id_2, f"Expected same conversation, got {conv_id_1} vs {conv_id_2}"
    
    def test_create_direct_conversation_reversed_members(self, admin_session):
        """POST with reversed member order should return same conversation."""
        me_resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200
        admin_id = me_resp.json().get("user_id")
        
        users_resp = admin_session.get(f"{BASE_URL}/api/users")
        if users_resp.status_code != 200:
            pytest.skip("Could not get users list")
        
        users = users_resp.json()
        other_user = next((u for u in users if u.get("user_id") != admin_id), None)
        
        if not other_user:
            pytest.skip("No other user available for DM test")
        
        other_id = other_user["user_id"]
        
        # First call: [admin, other]
        resp1 = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [admin_id, other_id]
        })
        assert resp1.status_code == 200
        conv_id_1 = resp1.json().get("conversation_id")
        
        # Second call: [other, admin] (reversed)
        resp2 = admin_session.post(f"{BASE_URL}/api/chat/conversations", json={
            "type": "direct",
            "member_ids": [other_id, admin_id]
        })
        assert resp2.status_code == 200
        conv_id_2 = resp2.json().get("conversation_id")
        
        # Should be the same conversation
        assert conv_id_1 == conv_id_2, f"Reversed members should return same conv: {conv_id_1} vs {conv_id_2}"


class TestModeratorPermissions:
    """Test Iter 240 permission defaults for moderator role."""
    
    def test_admin_has_moderator_caps(self, admin_session):
        """Admin should have all moderator caps including new Iter 240 ones."""
        resp = admin_session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200
        data = resp.json()
        
        caps = data.get("capabilities", [])
        
        # Admin should have all caps
        assert "resources.approve" in caps, "Admin missing resources.approve"
        assert "resources.view_all_bookings" in caps, "Admin missing resources.view_all_bookings"


class TestInOfficeWidgetRegression:
    """Regression tests for InOfficeWidget (Iter 238)."""
    
    def test_in_office_endpoint_still_works(self, admin_session):
        """GET /api/resources-in-office should still return 200."""
        resp = admin_session.get(f"{BASE_URL}/api/resources-in-office")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "date" in data
        assert "people" in data
        assert "total" in data
        assert "active_now" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
