"""
Iteration 65 - Capability System Expansion Tests
Tests for:
1. 46 Capabilities (expanded from 34) in 9 categories
2. 13 Presets (expanded from 7) with 6 new clinic-specific presets
3. Updated ROLE_DEFAULTS (admin=46, moderator~34, member~14, guest=2)
4. Apply nursing_lead preset to user
5. Meeting host check with meetings.manage_others capability
6. Scheduling poll deletion with scheduling.delete_others capability
7. Branding endpoint with admin.manage_branding capability
8. Chat message delete with chat.delete_messages capability
9. Regression tests for existing endpoints
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Module-level variables to persist across tests
_admin_token = None
_member_token = None
_member_user_id = None
_test_meeting_id = None
_test_poll_id = None
_test_message_id = None
_test_conversation_id = None


def get_admin_token():
    """Get or create admin token"""
    global _admin_token
    if _admin_token is None:
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        _admin_token = resp.json().get("token")
    return _admin_token


def admin_headers():
    return {"Authorization": f"Bearer {get_admin_token()}"}


def member_headers():
    global _member_token
    return {"Authorization": f"Bearer {_member_token}"} if _member_token else {}


# ============ TEST 1: Capability Count (46 capabilities) ============
def test_01_capabilities_count_46():
    """GET /api/admin/capabilities should return 46 capabilities"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200, f"Failed: {resp.text}"
    data = resp.json()
    caps = data.get("capabilities", [])
    print(f"Total capabilities: {len(caps)}")
    assert len(caps) == 46, f"Expected 46 capabilities, got {len(caps)}"


def test_02_capabilities_categories():
    """Verify 9 categories exist: module, news, meetings, chat, documents, scheduling, surveys, admin, global"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    caps = resp.json().get("capabilities", [])
    categories = set(c["category"] for c in caps)
    expected_categories = {"module", "news", "meetings", "chat", "documents", "scheduling", "surveys", "admin", "global"}
    print(f"Categories found: {categories}")
    assert categories == expected_categories, f"Expected {expected_categories}, got {categories}"


def test_03_new_chat_capabilities():
    """Verify 3 new chat capabilities: chat.create_group, chat.delete_messages, chat.broadcast"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    caps = resp.json().get("capabilities", [])
    chat_caps = [c["key"] for c in caps if c["category"] == "chat"]
    expected_chat = ["chat.create_group", "chat.delete_messages", "chat.broadcast"]
    print(f"Chat capabilities: {chat_caps}")
    for cap in expected_chat:
        assert cap in chat_caps, f"Missing chat capability: {cap}"


def test_04_new_documents_capabilities():
    """Verify 4 documents capabilities: documents.upload, documents.delete_others, whiteboard.create, whiteboard.delete_others"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    caps = resp.json().get("capabilities", [])
    doc_caps = [c["key"] for c in caps if c["category"] == "documents"]
    expected_docs = ["documents.upload", "documents.delete_others", "whiteboard.create", "whiteboard.delete_others"]
    print(f"Documents capabilities: {doc_caps}")
    for cap in expected_docs:
        assert cap in doc_caps, f"Missing documents capability: {cap}"


def test_05_new_scheduling_capabilities():
    """Verify 2 scheduling capabilities: scheduling.create_poll, scheduling.delete_others"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    caps = resp.json().get("capabilities", [])
    sched_caps = [c["key"] for c in caps if c["category"] == "scheduling"]
    expected_sched = ["scheduling.create_poll", "scheduling.delete_others"]
    print(f"Scheduling capabilities: {sched_caps}")
    for cap in expected_sched:
        assert cap in sched_caps, f"Missing scheduling capability: {cap}"


def test_06_expanded_meetings_capabilities():
    """Verify 6 meetings capabilities including new ones: meetings.manage_others, meetings.delete_recordings, meetings.view_attendance"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    caps = resp.json().get("capabilities", [])
    meeting_caps = [c["key"] for c in caps if c["category"] == "meetings"]
    expected_meetings = ["meetings.create", "meetings.record", "meetings.invite_external",
                         "meetings.manage_others", "meetings.delete_recordings", "meetings.view_attendance"]
    print(f"Meetings capabilities: {meeting_caps}")
    assert len(meeting_caps) == 6, f"Expected 6 meetings caps, got {len(meeting_caps)}"
    for cap in expected_meetings:
        assert cap in meeting_caps, f"Missing meetings capability: {cap}"


# ============ TEST 2: Role Defaults ============
def test_07_admin_has_46_caps():
    """Admin role should have all 46 capabilities"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    admin_caps = data.get("role_defaults", {}).get("admin", [])
    print(f"Admin capabilities count: {len(admin_caps)}")
    assert len(admin_caps) == 46, f"Expected admin to have 46 caps, got {len(admin_caps)}"


def test_08_moderator_caps():
    """Moderator role should have ~34 capabilities"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    mod_caps = data.get("role_defaults", {}).get("moderator", [])
    print(f"Moderator capabilities count: {len(mod_caps)}")
    # Moderator should have around 34 caps (not exact, but substantial)
    assert len(mod_caps) >= 30, f"Expected moderator to have ~34 caps, got {len(mod_caps)}"


def test_09_member_caps_include_new_defaults():
    """Member role should have ~14 caps including chat.create_group, documents.upload, whiteboard.create, scheduling.create_poll"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    member_caps = data.get("role_defaults", {}).get("member", [])
    print(f"Member capabilities count: {len(member_caps)}")
    print(f"Member capabilities: {member_caps}")
    # Check new member defaults
    expected_member_new = ["chat.create_group", "documents.upload", "whiteboard.create", "scheduling.create_poll"]
    for cap in expected_member_new:
        assert cap in member_caps, f"Member missing new default cap: {cap}"


def test_10_guest_has_2_caps():
    """Guest role should have exactly 2 capabilities: view:dashboard, view:chat"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    guest_caps = data.get("role_defaults", {}).get("guest", [])
    print(f"Guest capabilities: {guest_caps}")
    assert len(guest_caps) == 2, f"Expected guest to have 2 caps, got {len(guest_caps)}"
    assert "view:dashboard" in guest_caps
    assert "view:chat" in guest_caps


# ============ TEST 3: 13 Presets ============
def test_11_presets_count_13():
    """GET /api/admin/presets should return 13 presets"""
    resp = requests.get(f"{BASE_URL}/api/admin/presets", headers=admin_headers())
    assert resp.status_code == 200, f"Failed: {resp.text}"
    data = resp.json()
    presets = data.get("presets", [])
    print(f"Total presets: {len(presets)}")
    preset_ids = [p["preset_id"] for p in presets]
    print(f"Preset IDs: {preset_ids}")
    assert len(presets) == 13, f"Expected 13 presets, got {len(presets)}"


def test_12_new_presets_exist():
    """Verify 6 new presets: nursing_lead, department_head, it_support, data_protection, intern, broadcast_admin"""
    resp = requests.get(f"{BASE_URL}/api/admin/presets", headers=admin_headers())
    assert resp.status_code == 200
    presets = resp.json().get("presets", [])
    preset_ids = [p["preset_id"] for p in presets]
    new_presets = ["nursing_lead", "department_head", "it_support", "data_protection", "intern", "broadcast_admin"]
    for preset_id in new_presets:
        assert preset_id in preset_ids, f"Missing new preset: {preset_id}"


def test_13_nursing_lead_preset_has_9_caps():
    """nursing_lead preset should have 9 capabilities"""
    resp = requests.get(f"{BASE_URL}/api/admin/presets", headers=admin_headers())
    assert resp.status_code == 200
    presets = resp.json().get("presets", [])
    nursing_lead = next((p for p in presets if p["preset_id"] == "nursing_lead"), None)
    assert nursing_lead is not None, "nursing_lead preset not found"
    caps = nursing_lead.get("capabilities", [])
    print(f"nursing_lead capabilities: {caps}")
    assert len(caps) == 9, f"Expected nursing_lead to have 9 caps, got {len(caps)}"


# ============ TEST 4: Apply nursing_lead preset to user ============
def test_14_create_test_member():
    """Create a test member user for preset application"""
    global _member_user_id, _member_token
    unique_email = f"test_member_{uuid.uuid4().hex[:8]}@meetflow.com"
    resp = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": unique_email,
        "password": "testpass123",
        "name": "Test Member Iter65"
    })
    assert resp.status_code in [200, 201], f"Failed to create member: {resp.text}"
    data = resp.json()
    _member_user_id = data.get("user_id")
    _member_token = data.get("token")
    print(f"Created test member: {unique_email}, user_id: {_member_user_id}")


def test_15_apply_nursing_lead_preset_as_admin():
    """Admin can apply nursing_lead preset to member user"""
    global _member_user_id
    if not _member_user_id:
        pytest.skip("No member user created")
    resp = requests.post(
        f"{BASE_URL}/api/admin/presets/nursing_lead/apply-to-user/{_member_user_id}",
        headers=admin_headers()
    )
    assert resp.status_code == 200, f"Failed to apply preset: {resp.text}"
    data = resp.json()
    print(f"Apply preset response: {data}")
    assert data.get("ok") == True or "added" in data or "message" in data or "applied" in data


def test_16_simulate_member_after_preset():
    """Simulator should show ~20 effective caps (14 base + 9 grants with overlap)"""
    global _member_user_id
    if not _member_user_id:
        pytest.skip("No member user created")
    resp = requests.get(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/simulate",
        headers=admin_headers()
    )
    assert resp.status_code == 200, f"Failed to simulate: {resp.text}"
    data = resp.json()
    effective_count = data.get("effective_count", 0)
    effective = data.get("effective", [])
    print(f"Effective count after nursing_lead preset: {effective_count}")
    print(f"Effective caps: {effective}")
    # Should have more than base member caps (14) due to preset grants
    assert effective_count >= 14, f"Expected at least 14 effective caps, got {effective_count}"


def test_17_member_cannot_apply_preset():
    """Member without admin rights cannot apply preset"""
    global _member_token, _member_user_id
    if not _member_token or not _member_user_id:
        pytest.skip("No member user created")
    resp = requests.post(
        f"{BASE_URL}/api/admin/presets/nursing_lead/apply-to-user/{_member_user_id}",
        headers=member_headers()
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ============ TEST 5: Meeting Host Check with meetings.manage_others ============
def test_18_create_meeting_as_admin():
    """Create a meeting as admin for testing"""
    global _test_meeting_id
    resp = requests.post(f"{BASE_URL}/api/meetings", headers=admin_headers(), json={
        "title": "Test Meeting Iter65",
        "meeting_type": "scheduled",
        "duration": 60
    })
    assert resp.status_code == 200, f"Failed to create meeting: {resp.text}"
    data = resp.json()
    _test_meeting_id = data.get("meeting_id")
    print(f"Created meeting: {_test_meeting_id}")


def test_19_member_cannot_update_others_meeting_without_cap():
    """Member without meetings.manage_others cannot update another user's meeting"""
    global _test_meeting_id, _member_token, _member_user_id
    if not _test_meeting_id or not _member_token:
        pytest.skip("No meeting or member created")
    # First remove the cap if it was granted
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={"grants": [], "denies": ["meetings.manage_others"], "expires": {}}
    )
    # Now try to update as member
    resp = requests.put(
        f"{BASE_URL}/api/meetings/{_test_meeting_id}",
        headers=member_headers(),
        json={"title": "Hacked Title"}
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


def test_20_member_with_manage_others_can_update():
    """Member with meetings.manage_others can update another user's meeting"""
    global _test_meeting_id, _member_user_id
    if not _test_meeting_id or not _member_user_id:
        pytest.skip("No meeting or member created")
    # Grant the capability
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={"grants": ["meetings.manage_others"], "denies": [], "expires": {}}
    )
    assert resp.status_code == 200, f"Failed to grant cap: {resp.text}"
    # Now try to update as member
    resp = requests.put(
        f"{BASE_URL}/api/meetings/{_test_meeting_id}",
        headers=member_headers(),
        json={"title": "Updated by Member with Cap"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ============ TEST 6: Scheduling Poll Deletion ============
def test_21_create_schedule_poll_as_admin():
    """Create a schedule poll as admin"""
    global _test_poll_id
    resp = requests.post(f"{BASE_URL}/api/schedule-polls", headers=admin_headers(), json={
        "title": "Test Poll Iter65",
        "description": "Test poll for deletion",
        "time_slots": [{"date": "2026-02-15", "start_time": "10:00", "end_time": "11:00"}]
    })
    assert resp.status_code == 200, f"Failed to create poll: {resp.text}"
    data = resp.json()
    _test_poll_id = data.get("poll_id")
    print(f"Created poll: {_test_poll_id}")


def test_22_member_cannot_delete_others_poll_without_cap():
    """Member without scheduling.delete_others cannot delete another user's poll"""
    global _test_poll_id, _member_token, _member_user_id
    if not _test_poll_id or not _member_token:
        pytest.skip("No poll or member created")
    # Remove the cap
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={"grants": [], "denies": ["scheduling.delete_others"], "expires": {}}
    )
    # Try to delete
    resp = requests.delete(
        f"{BASE_URL}/api/schedule-polls/{_test_poll_id}",
        headers=member_headers()
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


def test_23_member_with_delete_others_can_delete_poll():
    """Member with scheduling.delete_others can delete another user's poll"""
    global _test_poll_id, _member_user_id
    if not _test_poll_id or not _member_user_id:
        pytest.skip("No poll or member created")
    # Grant the capability
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={"grants": ["scheduling.delete_others"], "denies": [], "expires": {}}
    )
    assert resp.status_code == 200
    # Now delete
    resp = requests.delete(
        f"{BASE_URL}/api/schedule-polls/{_test_poll_id}",
        headers=member_headers()
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ============ TEST 7: Branding Endpoint ============
def test_24_admin_can_update_branding():
    """Admin with admin.manage_branding can update branding"""
    resp = requests.put(f"{BASE_URL}/api/organization/branding", headers=admin_headers(), json={
        "company_name": "MeetFlow Test Iter65"
    })
    assert resp.status_code == 200, f"Failed to update branding: {resp.text}"


def test_25_member_cannot_update_branding_without_cap():
    """Member without admin.manage_branding cannot update branding"""
    global _member_token, _member_user_id
    if not _member_token:
        pytest.skip("No member created")
    # Remove the cap
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={"grants": [], "denies": ["admin.manage_branding"], "expires": {}}
    )
    # Try to update
    resp = requests.put(
        f"{BASE_URL}/api/organization/branding",
        headers=member_headers(),
        json={"company_name": "Hacked Name"}
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ============ TEST 8: Chat Message Delete ============
def test_26_create_conversation_and_message():
    """Create a conversation and message for testing"""
    global _test_conversation_id, _test_message_id, _member_user_id
    # Create conversation
    resp = requests.post(f"{BASE_URL}/api/chat/conversations", headers=admin_headers(), json={
        "type": "group",
        "name": "Test Chat Iter65",
        "member_ids": [_member_user_id] if _member_user_id else []
    })
    if resp.status_code == 200:
        data = resp.json()
        _test_conversation_id = data.get("conversation_id")
        print(f"Created conversation: {_test_conversation_id}")

        # Send a message
        resp = requests.post(
            f"{BASE_URL}/api/chat/conversations/{_test_conversation_id}/messages",
            headers=admin_headers(),
            json={"content": "Test message for deletion"}
        )
        if resp.status_code == 200:
            data = resp.json()
            _test_message_id = data.get("message_id")
            print(f"Created message: {_test_message_id}")


def test_27_member_cannot_delete_others_message_without_cap():
    """Member without chat.delete_messages cannot delete another user's message"""
    global _test_message_id, _member_token, _member_user_id
    if not _test_message_id or not _member_token:
        pytest.skip("No message or member created")
    # Remove the cap
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={"grants": [], "denies": ["chat.delete_messages"], "expires": {}}
    )
    # Try to delete
    resp = requests.delete(
        f"{BASE_URL}/api/chat/messages/{_test_message_id}",
        headers=member_headers()
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


def test_28_member_with_delete_messages_can_delete():
    """Member with chat.delete_messages can delete another user's message"""
    global _test_message_id, _member_user_id
    if not _test_message_id or not _member_user_id:
        pytest.skip("No message or member created")
    # Grant the capability
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={"grants": ["chat.delete_messages"], "denies": [], "expires": {}}
    )
    assert resp.status_code == 200
    # Now delete
    resp = requests.delete(
        f"{BASE_URL}/api/chat/messages/{_test_message_id}",
        headers=member_headers()
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ============ REGRESSION TESTS ============
def test_29_regression_capabilities_endpoint():
    """Regression: GET /api/admin/capabilities still works"""
    resp = requests.get(f"{BASE_URL}/api/admin/capabilities", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "capabilities" in data
    assert "role_defaults" in data


def test_30_regression_presets_endpoint():
    """Regression: GET /api/admin/presets returns 13 presets (was 7)"""
    resp = requests.get(f"{BASE_URL}/api/admin/presets", headers=admin_headers())
    assert resp.status_code == 200
    presets = resp.json().get("presets", [])
    assert len(presets) == 13


def test_31_regression_migrate_roles():
    """Regression: POST /api/admin/migrate-roles still works"""
    resp = requests.post(f"{BASE_URL}/api/admin/migrate-roles", headers=admin_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "migrated" in data or "unchanged" in data


def test_32_regression_user_capabilities_with_expires():
    """Regression: PUT /api/admin/users/{id}/capabilities with expires support"""
    global _member_user_id
    if not _member_user_id:
        pytest.skip("No member created")
    resp = requests.put(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/capabilities",
        headers=admin_headers(),
        json={
            "grants": ["news.create"],
            "denies": [],
            "expires": {"news.create": "2026-12-31T23:59:59Z"}
        }
    )
    assert resp.status_code == 200, f"Failed: {resp.text}"


def test_33_regression_simulate_endpoint():
    """Regression: GET /api/admin/users/{id}/simulate still works"""
    global _member_user_id
    if not _member_user_id:
        pytest.skip("No member created")
    resp = requests.get(
        f"{BASE_URL}/api/admin/users/{_member_user_id}/simulate",
        headers=admin_headers()
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "effective" in data
    assert "effective_count" in data


# ============ CLEANUP ============
def test_99_cleanup():
    """Cleanup test data"""
    global _test_meeting_id, _test_conversation_id
    # Delete test meeting
    if _test_meeting_id:
        requests.delete(f"{BASE_URL}/api/meetings/{_test_meeting_id}", headers=admin_headers())
    # Delete test conversation
    if _test_conversation_id:
        requests.delete(f"{BASE_URL}/api/chat/conversations/{_test_conversation_id}", headers=admin_headers())
    print("Cleanup completed")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
