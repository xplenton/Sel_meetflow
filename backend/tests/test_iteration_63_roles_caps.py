"""
Iteration 63 - Role+Capability Permission System Tests

Tests for:
1. GET /api/admin/capabilities - List all capabilities with role defaults
2. GET /api/user/permissions - User's effective permissions
3. POST /api/admin/migrate-roles - Idempotent legacy role migration
4. PUT /api/admin/users/{user_id}/capabilities - Per-user overrides
5. News moderation with capability checks
6. Survey creation permissions
7. Export permissions
8. Attachment delete permissions
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestRolesCapabilitiesSystem:
    """Tests for the new capability-based permission system"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin_user = login_resp.json()
        yield
        self.session.close()
    
    # ============ CAPABILITIES ENDPOINT ============
    
    def test_get_capabilities_as_admin(self):
        """GET /api/admin/capabilities returns all 34 capabilities with role defaults"""
        resp = self.session.get(f"{BASE_URL}/api/admin/capabilities")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "capabilities" in data
        assert "role_defaults" in data
        
        # Should have ~34 capabilities
        caps = data["capabilities"]
        assert len(caps) >= 30, f"Expected at least 30 capabilities, got {len(caps)}"
        
        # Each capability should have key, category, label, description
        for cap in caps:
            assert "key" in cap
            assert "category" in cap
            assert "label" in cap
            assert "description" in cap
        
        # Check role defaults
        role_defaults = data["role_defaults"]
        assert "admin" in role_defaults
        assert "moderator" in role_defaults
        assert "member" in role_defaults
        assert "guest" in role_defaults
        
        # Admin should have all capabilities
        admin_caps = role_defaults["admin"]
        assert len(admin_caps) >= 30, f"Admin should have all caps, got {len(admin_caps)}"
        
        # Moderator should have ~28 caps
        mod_caps = role_defaults["moderator"]
        assert len(mod_caps) >= 20, f"Moderator should have ~28 caps, got {len(mod_caps)}"
        
        # Member should have ~10 caps
        member_caps = role_defaults["member"]
        assert len(member_caps) >= 8, f"Member should have ~10 caps, got {len(member_caps)}"
        
        # Guest should have 2 caps
        guest_caps = role_defaults["guest"]
        assert len(guest_caps) == 2, f"Guest should have 2 caps, got {len(guest_caps)}"
        
        print(f"✓ Capabilities endpoint: {len(caps)} capabilities, admin={len(admin_caps)}, moderator={len(mod_caps)}, member={len(member_caps)}, guest={len(guest_caps)}")
    
    # ============ USER PERMISSIONS ENDPOINT ============
    
    def test_get_user_permissions_as_admin(self):
        """GET /api/user/permissions returns effective permissions for admin"""
        resp = self.session.get(f"{BASE_URL}/api/user/permissions")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "permissions" in data  # Legacy module list
        assert "capabilities" in data  # New granular caps
        assert "role" in data
        assert "legacy_role" in data
        assert "groups" in data
        
        # Admin should have role=admin
        assert data["role"] == "admin", f"Expected role=admin, got {data['role']}"
        
        # Admin should have key capabilities
        caps = data["capabilities"]
        assert "admin.manage_users" in caps, "Admin should have admin.manage_users"
        assert "news.moderate" in caps, "Admin should have news.moderate"
        assert "view:analytics" in caps, "Admin should have view:analytics"
        assert "admin.manage_roles" in caps, "Admin should have admin.manage_roles"
        
        print(f"✓ User permissions: role={data['role']}, {len(caps)} capabilities")
    
    # ============ MIGRATION ENDPOINT ============
    
    def test_migrate_roles_idempotent(self):
        """POST /api/admin/migrate-roles is idempotent"""
        # First run
        resp1 = self.session.post(f"{BASE_URL}/api/admin/migrate-roles")
        assert resp1.status_code == 200, f"First migration failed: {resp1.text}"
        
        data1 = resp1.json()
        assert "migrated" in data1
        assert "unchanged" in data1
        assert "details" in data1
        
        # Second run should have migrated=0
        resp2 = self.session.post(f"{BASE_URL}/api/admin/migrate-roles")
        assert resp2.status_code == 200, f"Second migration failed: {resp2.text}"
        
        data2 = resp2.json()
        # After first run, all should be unchanged
        assert data2["migrated"] == 0, f"Second run should migrate 0, got {data2['migrated']}"
        
        print(f"✓ Migration idempotent: first run migrated={data1['migrated']}, unchanged={data1['unchanged']}; second run migrated={data2['migrated']}")
    
    # ============ PER-USER OVERRIDES ============
    
    def test_per_user_capability_overrides(self):
        """PUT /api/admin/users/{user_id}/capabilities sets grants/denies"""
        # First, get a user to modify (not admin)
        users_resp = self.session.get(f"{BASE_URL}/api/admin/users")
        assert users_resp.status_code == 200
        users = users_resp.json()
        
        # Find a non-admin user
        test_user = None
        for u in users:
            if u.get("role") != "admin" and u.get("email") != "admin@meetflow.com":
                test_user = u
                break
        
        if not test_user:
            # Create a test user
            invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
                "email": f"test-caps-{uuid.uuid4().hex[:8]}@meetflow.com",
                "name": "Test Caps User",
                "role": "member"
            })
            assert invite_resp.status_code == 200, f"Failed to create test user: {invite_resp.text}"
            test_user = {"user_id": invite_resp.json()["user_id"]}
        
        user_id = test_user["user_id"]
        
        # Set grants and denies
        caps_resp = self.session.put(f"{BASE_URL}/api/admin/users/{user_id}/capabilities", json={
            "grants": ["news.pin"],
            "denies": ["view:chat"]
        })
        assert caps_resp.status_code == 200, f"Failed to set caps: {caps_resp.text}"
        
        data = caps_resp.json()
        assert data["ok"] == True
        assert "news.pin" in data["grants"]
        assert "view:chat" in data["denies"]
        
        print(f"✓ Per-user overrides set: grants={data['grants']}, denies={data['denies']}")
    
    # ============ NEWS MODERATION PERMISSIONS ============
    
    def test_news_approval_queue_requires_review_cap(self):
        """GET /api/news/approval-queue requires news.review capability"""
        # Admin should have access
        resp = self.session.get(f"{BASE_URL}/api/news/approval-queue")
        assert resp.status_code == 200, f"Admin should access approval queue: {resp.text}"
        
        print("✓ News approval queue accessible by admin")
    
    def test_news_post_creation_requires_cap(self):
        """POST /api/news/posts requires news.create capability"""
        # Admin should be able to create
        resp = self.session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"Test News {uuid.uuid4().hex[:8]}",
            "content": "Test content for capability check",
            "status": "draft"
        })
        assert resp.status_code == 200, f"Admin should create news: {resp.text}"
        
        post_id = resp.json()["post_id"]
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        
        print("✓ News creation works for admin")
    
    # ============ SURVEY PERMISSIONS ============
    
    def test_survey_creation_requires_moderator_or_admin(self):
        """POST /api/surveys requires admin or moderator role"""
        # Admin should be able to create
        resp = self.session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"Test Survey {uuid.uuid4().hex[:8]}",
            "description": "Test survey for capability check",
            "questions": [{"question_id": "q1", "text": "Test?", "type": "free_text"}],
            "status": "draft"
        })
        assert resp.status_code == 200, f"Admin should create survey: {resp.text}"
        
        survey_id = resp.json()["survey_id"]
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/surveys/{survey_id}")
        
        print("✓ Survey creation works for admin")
    
    # ============ EXPORT PERMISSIONS ============
    
    def test_export_permissions_admin_moderator(self):
        """GET /api/exports/* requires admin or moderator"""
        # First create a survey to export
        survey_resp = self.session.post(f"{BASE_URL}/api/surveys", json={
            "title": f"Export Test Survey {uuid.uuid4().hex[:8]}",
            "description": "Test",
            "questions": [{"question_id": "q1", "text": "Test?", "type": "free_text"}],
            "status": "published"
        })
        assert survey_resp.status_code == 200
        survey_id = survey_resp.json()["survey_id"]
        
        # Admin should access PDF export
        pdf_resp = self.session.get(f"{BASE_URL}/api/exports/surveys/{survey_id}/pdf")
        assert pdf_resp.status_code == 200, f"Admin should access PDF export: {pdf_resp.status_code}"
        assert pdf_resp.content[:4] == b'%PDF', "Response should be PDF"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/surveys/{survey_id}")
        
        print("✓ Export permissions work for admin")
    
    # ============ ATTACHMENT DELETE PERMISSIONS ============
    
    def test_attachment_delete_owner_or_moderator(self):
        """DELETE /api/attachments/{id} - owner or moderator can delete"""
        # Upload a test attachment
        files = {'file': ('test.txt', b'Test content for attachment', 'text/plain')}
        upload_resp = self.session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        
        attachment_id = upload_resp.json()["attachment_id"]
        
        # Admin should be able to delete
        delete_resp = self.session.delete(f"{BASE_URL}/api/attachments/{attachment_id}")
        assert delete_resp.status_code == 200, f"Admin should delete attachment: {delete_resp.text}"
        
        print("✓ Attachment delete works for admin")


class TestMemberPermissions:
    """Test that member role has restricted permissions"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Create and login as a member user"""
        self.admin_session = requests.Session()
        login_resp = self.admin_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        
        # Create a test member user
        self.test_email = f"test-member-{uuid.uuid4().hex[:8]}@meetflow.com"
        self.test_password = "testpass123"
        
        # Register as member
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": self.test_email,
            "password": self.test_password,
            "name": "Test Member"
        })
        
        if reg_resp.status_code != 200:
            # User might exist, try login
            pass
        
        # Login as member
        self.member_session = requests.Session()
        member_login = self.member_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.test_email,
            "password": self.test_password
        })
        
        if member_login.status_code != 200:
            pytest.skip("Could not create/login member user")
        
        yield
        
        # Cleanup - delete test user
        users_resp = self.admin_session.get(f"{BASE_URL}/api/admin/users")
        if users_resp.status_code == 200:
            for u in users_resp.json():
                if u.get("email") == self.test_email:
                    self.admin_session.delete(f"{BASE_URL}/api/admin/users/{u['user_id']}")
                    break
        
        self.admin_session.close()
        self.member_session.close()
    
    def test_member_cannot_access_capabilities_endpoint(self):
        """Member should get 403 on /api/admin/capabilities"""
        resp = self.member_session.get(f"{BASE_URL}/api/admin/capabilities")
        assert resp.status_code == 403, f"Member should get 403, got {resp.status_code}"
        print("✓ Member cannot access capabilities endpoint (403)")
    
    def test_member_cannot_create_survey(self):
        """Member should get 403 on POST /api/surveys"""
        resp = self.member_session.post(f"{BASE_URL}/api/surveys", json={
            "title": "Member Survey Test",
            "description": "Should fail",
            "questions": [],
            "status": "draft"
        })
        assert resp.status_code == 403, f"Member should get 403, got {resp.status_code}"
        print("✓ Member cannot create survey (403)")
    
    def test_member_cannot_access_approval_queue(self):
        """Member should get 403 on /api/news/approval-queue"""
        resp = self.member_session.get(f"{BASE_URL}/api/news/approval-queue")
        assert resp.status_code == 403, f"Member should get 403, got {resp.status_code}"
        print("✓ Member cannot access approval queue (403)")
    
    def test_member_cannot_export_pdf(self):
        """Member should get 403 on /api/exports/surveys/{id}/pdf"""
        # First get a survey ID from admin
        surveys_resp = self.admin_session.get(f"{BASE_URL}/api/surveys?status=published")
        if surveys_resp.status_code != 200 or not surveys_resp.json():
            pytest.skip("No published surveys to test")
        
        survey_id = surveys_resp.json()[0]["survey_id"]
        
        resp = self.member_session.get(f"{BASE_URL}/api/exports/surveys/{survey_id}/pdf")
        assert resp.status_code == 403, f"Member should get 403, got {resp.status_code}"
        print("✓ Member cannot export PDF (403)")


class TestRoleSelectOptions:
    """Test that only 4 roles are available in admin UI endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        yield
        self.session.close()
    
    def test_invite_with_new_roles(self):
        """Invite endpoint accepts only new 4 roles"""
        for role in ["admin", "moderator", "member", "guest"]:
            resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
                "email": f"test-role-{role}-{uuid.uuid4().hex[:6]}@meetflow.com",
                "name": f"Test {role}",
                "role": role
            })
            assert resp.status_code == 200, f"Should accept role={role}: {resp.text}"
            
            # Cleanup
            user_id = resp.json()["user_id"]
            self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
        
        print("✓ All 4 new roles accepted in invite endpoint")
    
    def test_update_user_role(self):
        """Update user endpoint accepts new roles"""
        # Create test user
        invite_resp = self.session.post(f"{BASE_URL}/api/admin/users/invite", json={
            "email": f"test-update-role-{uuid.uuid4().hex[:6]}@meetflow.com",
            "name": "Test Update Role",
            "role": "member"
        })
        assert invite_resp.status_code == 200
        user_id = invite_resp.json()["user_id"]
        
        # Update to moderator
        update_resp = self.session.put(f"{BASE_URL}/api/admin/users/{user_id}", json={
            "role": "moderator"
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["role"] == "moderator"
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
        
        print("✓ User role update works with new roles")


class TestRegressionExistingFeatures:
    """Regression tests for existing features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        yield
        self.session.close()
    
    def test_news_crud_still_works(self):
        """News CRUD operations still work"""
        # Create
        create_resp = self.session.post(f"{BASE_URL}/api/news/posts", json={
            "title": f"Regression Test {uuid.uuid4().hex[:8]}",
            "content": "Test content",
            "status": "draft"
        })
        assert create_resp.status_code == 200
        post_id = create_resp.json()["post_id"]
        
        # Read
        read_resp = self.session.get(f"{BASE_URL}/api/news/posts/{post_id}")
        assert read_resp.status_code == 200
        
        # Update
        update_resp = self.session.put(f"{BASE_URL}/api/news/posts/{post_id}", json={
            "title": "Updated Title"
        })
        assert update_resp.status_code == 200
        
        # Delete
        delete_resp = self.session.delete(f"{BASE_URL}/api/news/posts/{post_id}")
        assert delete_resp.status_code == 200
        
        print("✓ News CRUD regression passed")
    
    def test_news_feed_works(self):
        """News feed endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/news/feed")
        assert resp.status_code == 200
        assert "posts" in resp.json()
        print("✓ News feed regression passed")
    
    def test_surveys_list_works(self):
        """Surveys list endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/surveys")
        assert resp.status_code == 200
        print("✓ Surveys list regression passed")
    
    def test_attachments_upload_works(self):
        """Attachments upload still works"""
        files = {'file': ('test.txt', b'Test content', 'text/plain')}
        resp = self.session.post(f"{BASE_URL}/api/attachments/upload", files=files)
        assert resp.status_code == 200
        
        # Cleanup
        att_id = resp.json()["attachment_id"]
        self.session.delete(f"{BASE_URL}/api/attachments/{att_id}")
        
        print("✓ Attachments upload regression passed")
    
    def test_cmd_k_search_works(self):
        """Cmd+K search endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/search/global?q=test")
        assert resp.status_code == 200
        print("✓ Search regression passed")
    
    def test_audit_log_works(self):
        """Audit log endpoint works"""
        resp = self.session.get(f"{BASE_URL}/api/news/audit")
        assert resp.status_code == 200
        print("✓ Audit log regression passed")
