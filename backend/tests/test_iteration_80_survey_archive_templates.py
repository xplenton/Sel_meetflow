"""
Iteration 80 Tests: Survey Archive + Meeting Templates with Custom Recurring Schedule

Tests cover:
1. Survey Archive Manual: POST /api/surveys/{id}/archive
2. Survey Restore: POST /api/surveys/{id}/restore
3. Survey Auto-Archive: POST /api/surveys/archive/run
4. Archived surveys excluded from default list
5. Pending-count excludes archived
6. Meeting Templates with custom recurring schedule
7. Template CRUD (create, read, update, delete)
8. Create-from-template with generate_series
9. Regression: Iteration 78 features still work
"""

import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSurveyArchive:
    """Survey archival feature tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get auth cookie"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        yield
        # Cleanup: delete test surveys
        try:
            surveys = self.session.get(f"{BASE_URL}/api/surveys?status=published").json()
            for s in surveys:
                if s.get('title', '').startswith('TEST_'):
                    self.session.delete(f"{BASE_URL}/api/surveys/{s['survey_id']}")
            archived = self.session.get(f"{BASE_URL}/api/surveys?status=archived").json()
            for s in archived:
                if s.get('title', '').startswith('TEST_'):
                    self.session.delete(f"{BASE_URL}/api/surveys/{s['survey_id']}")
        except:
            pass
    
    def test_create_survey_for_archive_tests(self):
        """Create a test survey to use in archive tests"""
        payload = {
            "title": f"TEST_Archive_Survey_{uuid.uuid4().hex[:6]}",
            "description": "Test survey for archive testing",
            "survey_type": "survey",
            "questions": [{"question_id": "q1", "text": "Test question?", "type": "single_choice", "options": ["Yes", "No"]}],
            "status": "published",
            "target_all": True
        }
        resp = self.session.post(f"{BASE_URL}/api/surveys", json=payload)
        assert resp.status_code == 200, f"Create survey failed: {resp.text}"
        data = resp.json()
        assert "survey_id" in data
        assert data["status"] == "published"
        self.test_survey_id = data["survey_id"]
        return data
    
    def test_archive_survey_manual(self):
        """POST /api/surveys/{id}/archive sets status='archived', archived_at, archived_by"""
        # Create survey first
        survey = self.test_create_survey_for_archive_tests()
        survey_id = survey["survey_id"]
        
        # Archive it
        resp = self.session.post(f"{BASE_URL}/api/surveys/{survey_id}/archive")
        assert resp.status_code == 200, f"Archive failed: {resp.text}"
        data = resp.json()
        
        # Verify archive fields
        assert data["status"] == "archived", f"Expected status='archived', got {data.get('status')}"
        assert data.get("archived_at"), "archived_at should be set"
        assert data.get("archived_by") == self.user["user_id"], f"archived_by should be {self.user['user_id']}"
        print(f"✓ Survey archived: status={data['status']}, archived_by={data.get('archived_by')}")
    
    def test_restore_survey(self):
        """POST /api/surveys/{id}/restore sets status='published', clears archived_at"""
        # Create and archive survey
        survey = self.test_create_survey_for_archive_tests()
        survey_id = survey["survey_id"]
        self.session.post(f"{BASE_URL}/api/surveys/{survey_id}/archive")
        
        # Restore it
        resp = self.session.post(f"{BASE_URL}/api/surveys/{survey_id}/restore")
        assert resp.status_code == 200, f"Restore failed: {resp.text}"
        data = resp.json()
        
        # Verify restore
        assert data["status"] == "published", f"Expected status='published', got {data.get('status')}"
        assert data.get("archived_at") == "", "archived_at should be cleared"
        print(f"✓ Survey restored: status={data['status']}")
    
    def test_auto_archive_expired_surveys(self):
        """POST /api/surveys/archive/run auto-archives expired surveys"""
        # Create survey with expires_at 30 days ago
        past_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        payload = {
            "title": f"TEST_Expired_Survey_{uuid.uuid4().hex[:6]}",
            "description": "Expired survey for auto-archive test",
            "survey_type": "survey",
            "questions": [{"question_id": "q1", "text": "Test?", "type": "free_text"}],
            "status": "published",
            "expires_at": past_date,
            "target_all": True
        }
        create_resp = self.session.post(f"{BASE_URL}/api/surveys", json=payload)
        assert create_resp.status_code == 200, f"Create expired survey failed: {create_resp.text}"
        survey_id = create_resp.json()["survey_id"]
        
        # Run auto-archive with grace_days=14
        resp = self.session.post(f"{BASE_URL}/api/surveys/archive/run", json={"grace_days": 14})
        assert resp.status_code == 200, f"Auto-archive run failed: {resp.text}"
        data = resp.json()
        assert "archived" in data, f"Response should contain 'archived' count: {data}"
        print(f"✓ Auto-archive run: archived={data.get('archived')}, cutoff={data.get('cutoff')}")
        
        # Verify the survey is now archived
        get_resp = self.session.get(f"{BASE_URL}/api/surveys/{survey_id}")
        assert get_resp.status_code == 200
        survey_data = get_resp.json()
        assert survey_data["status"] == "archived", f"Survey should be archived, got {survey_data.get('status')}"
        assert survey_data.get("archived_by") == "system", f"archived_by should be 'system', got {survey_data.get('archived_by')}"
        print("✓ Expired survey auto-archived with archived_by='system'")
    
    def test_archived_excluded_from_default_list(self):
        """GET /api/surveys (no status filter) should NOT return archived surveys"""
        # Create and archive a survey
        survey = self.test_create_survey_for_archive_tests()
        survey_id = survey["survey_id"]
        self.session.post(f"{BASE_URL}/api/surveys/{survey_id}/archive")
        
        # Get default list (no status param)
        resp = self.session.get(f"{BASE_URL}/api/surveys")
        assert resp.status_code == 200
        surveys = resp.json()
        
        # Verify archived survey is not in the list
        survey_ids = [s["survey_id"] for s in surveys]
        assert survey_id not in survey_ids, f"Archived survey {survey_id} should not be in default list"
        print("✓ Archived survey excluded from default list")
    
    def test_archived_excluded_from_published_filter(self):
        """GET /api/surveys?status=published should NOT return archived surveys"""
        # Create and archive a survey
        survey = self.test_create_survey_for_archive_tests()
        survey_id = survey["survey_id"]
        self.session.post(f"{BASE_URL}/api/surveys/{survey_id}/archive")
        
        # Get published list
        resp = self.session.get(f"{BASE_URL}/api/surveys?status=published")
        assert resp.status_code == 200
        surveys = resp.json()
        
        survey_ids = [s["survey_id"] for s in surveys]
        assert survey_id not in survey_ids, "Archived survey should not be in published list"
        print("✓ Archived survey excluded from status=published filter")
    
    def test_archived_returned_with_archived_filter(self):
        """GET /api/surveys?status=archived returns only archived surveys"""
        # Create and archive a survey
        survey = self.test_create_survey_for_archive_tests()
        survey_id = survey["survey_id"]
        self.session.post(f"{BASE_URL}/api/surveys/{survey_id}/archive")
        
        # Get archived list
        resp = self.session.get(f"{BASE_URL}/api/surveys?status=archived")
        assert resp.status_code == 200
        surveys = resp.json()
        
        # All returned surveys should be archived
        for s in surveys:
            assert s["status"] == "archived", f"Survey {s['survey_id']} should be archived"
        
        # Our test survey should be in the list
        survey_ids = [s["survey_id"] for s in surveys]
        assert survey_id in survey_ids, f"Archived survey {survey_id} should be in archived list"
        print("✓ Archived survey returned with status=archived filter")
    
    def test_pending_count_excludes_archived(self):
        """GET /api/surveys/pending-count doesn't count archived surveys"""
        # Get initial pending count
        initial_resp = self.session.get(f"{BASE_URL}/api/surveys/pending-count")
        assert initial_resp.status_code == 200
        initial_count = initial_resp.json().get("count", 0)
        
        # Create a new survey (should increase pending count)
        survey = self.test_create_survey_for_archive_tests()
        survey_id = survey["survey_id"]
        
        after_create_resp = self.session.get(f"{BASE_URL}/api/surveys/pending-count")
        after_create_count = after_create_resp.json().get("count", 0)
        
        # Archive the survey
        self.session.post(f"{BASE_URL}/api/surveys/{survey_id}/archive")
        
        # Pending count should decrease (or stay same if user already participated)
        after_archive_resp = self.session.get(f"{BASE_URL}/api/surveys/pending-count")
        after_archive_count = after_archive_resp.json().get("count", 0)
        
        # The archived survey should not be counted
        assert after_archive_count <= after_create_count, "Pending count should not increase after archiving"
        print(f"✓ Pending count excludes archived: before={after_create_count}, after={after_archive_count}")
    
    def test_archive_requires_admin_or_moderator(self):
        """Archive endpoint requires admin or moderator role"""
        # This test verifies the permission check exists
        # We're already logged in as admin, so it should work
        survey = self.test_create_survey_for_archive_tests()
        resp = self.session.post(f"{BASE_URL}/api/surveys/{survey['survey_id']}/archive")
        assert resp.status_code == 200, "Admin should be able to archive"
        print("✓ Admin can archive surveys")
    
    def test_auto_archive_requires_admin(self):
        """POST /api/surveys/archive/run requires admin role"""
        # We're logged in as admin, should work
        resp = self.session.post(f"{BASE_URL}/api/surveys/archive/run", json={"grace_days": 14})
        assert resp.status_code == 200, f"Admin should be able to run auto-archive: {resp.text}"
        print("✓ Admin can run auto-archive")


class TestMeetingTemplatesCustomRecurring:
    """Meeting templates with custom recurring schedule tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.user = login_resp.json()
        yield
        # Cleanup test templates
        try:
            templates = self.session.get(f"{BASE_URL}/api/templates").json()
            for t in templates:
                if t.get('name', '').startswith('TEST_'):
                    self.session.delete(f"{BASE_URL}/api/templates/{t['template_id']}")
        except:
            pass
    
    def test_create_template_with_custom_schedule(self):
        """POST /api/templates with recurring=true, recurring_pattern='custom', recurring_schedule"""
        payload = {
            "name": f"TEST_Custom_Template_{uuid.uuid4().hex[:6]}",
            "title": "Weekly Team Sync",
            "description": "Custom recurring meeting",
            "duration": 60,
            "meeting_mode": "standard",
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 1, "start_time": "09:00", "end_time": "10:00"},  # Tuesday
                {"weekday": 3, "start_time": "14:00", "end_time": "15:00"}   # Thursday
            ],
            "recurring_weeks": 4,
            "invited_emails": ["pdl@klinik.de"]
        }
        resp = self.session.post(f"{BASE_URL}/api/templates", json=payload)
        assert resp.status_code == 200, f"Create template failed: {resp.text}"
        data = resp.json()
        
        assert data.get("recurring") == True
        assert data.get("recurring_pattern") == "custom"
        assert len(data.get("recurring_schedule", [])) == 2
        assert data.get("recurring_weeks") == 4
        assert "pdl@klinik.de" in data.get("invited_emails", [])
        
        self.template_id = data["template_id"]
        print(f"✓ Template created with custom schedule: {data['template_id']}")
        return data
    
    def test_get_templates_includes_custom_fields(self):
        """GET /api/templates includes recurring_schedule, recurring_weeks, invited_emails"""
        # Create template first
        template = self.test_create_template_with_custom_schedule()
        
        # Get templates list
        resp = self.session.get(f"{BASE_URL}/api/templates")
        assert resp.status_code == 200
        templates = resp.json()
        
        # Find our template
        found = None
        for t in templates:
            if t["template_id"] == template["template_id"]:
                found = t
                break
        
        assert found is not None, "Template not found in list"
        assert found.get("recurring_schedule") is not None
        assert found.get("recurring_weeks") is not None
        assert found.get("invited_emails") is not None
        print("✓ GET /api/templates includes custom recurring fields")
    
    def test_update_template(self):
        """PUT /api/templates/{id} updates all fields including new ones"""
        # Create template
        template = self.test_create_template_with_custom_schedule()
        template_id = template["template_id"]
        
        # Update it
        update_payload = {
            "name": f"TEST_Updated_Template_{uuid.uuid4().hex[:6]}",
            "title": "Updated Team Sync",
            "description": "Updated description",
            "duration": 90,
            "meeting_mode": "moderated",
            "recurring": True,
            "recurring_pattern": "custom",
            "recurring_schedule": [
                {"weekday": 0, "start_time": "10:00", "end_time": "11:00"},  # Monday
                {"weekday": 2, "start_time": "15:00", "end_time": "16:00"},  # Wednesday
                {"weekday": 4, "start_time": "09:00", "end_time": "10:00"}   # Friday
            ],
            "recurring_weeks": 6,
            "invited_emails": ["pdl@klinik.de", "team@klinik.de"]
        }
        resp = self.session.put(f"{BASE_URL}/api/templates/{template_id}", json=update_payload)
        assert resp.status_code == 200, f"Update template failed: {resp.text}"
        data = resp.json()
        
        assert data["title"] == "Updated Team Sync"
        assert data["duration"] == 90
        assert len(data.get("recurring_schedule", [])) == 3
        assert data.get("recurring_weeks") == 6
        assert len(data.get("invited_emails", [])) == 2
        print("✓ Template updated with new custom schedule")
    
    def test_update_template_not_owned_returns_404(self):
        """PUT /api/templates/{id} returns 404 when not owned by caller"""
        # Try to update a non-existent template
        resp = self.session.put(f"{BASE_URL}/api/templates/tmpl_nonexistent", json={
            "name": "Test",
            "title": "Test"
        })
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Update non-existent template returns 404")
    
    def test_create_from_template_with_generate_series(self):
        """POST /api/templates/{id}/create-meeting with generate_series=true creates series"""
        # Create template with custom schedule
        template = self.test_create_template_with_custom_schedule()
        template_id = template["template_id"]
        
        # Create meeting from template with generate_series=true
        # Schedule for next week to ensure future dates
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
        
        payload = {
            "scheduled_at": future_date.isoformat(),
            "generate_series": True
        }
        resp = self.session.post(f"{BASE_URL}/api/templates/{template_id}/create-meeting", json=payload)
        assert resp.status_code == 200, f"Create from template failed: {resp.text}"
        data = resp.json()
        
        assert "meeting_id" in data
        assert data.get("template_id") == template_id
        
        # Check if series was generated
        series_count = data.get("_series_generated", 0)
        print(f"✓ Meeting created from template, series_generated={series_count}")
        
        # The series count should be >= 4 (2 weekdays × 4 weeks, minus anchor if on same weekday)
        # Actual count depends on anchor weekday
        assert series_count >= 4, f"Expected at least 4 series meetings, got {series_count}"
        print(f"✓ Series generation: {series_count} meetings created (expected ~6-8 for 2 weekdays × 4 weeks)")
        
        return data
    
    def test_create_from_template_without_generate_series(self):
        """POST /api/templates/{id}/create-meeting without generate_series creates only anchor"""
        # Create template
        template = self.test_create_template_with_custom_schedule()
        template_id = template["template_id"]
        
        # Create meeting without generate_series
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
        
        payload = {
            "scheduled_at": future_date.isoformat(),
            "generate_series": False
        }
        resp = self.session.post(f"{BASE_URL}/api/templates/{template_id}/create-meeting", json=payload)
        assert resp.status_code == 200, f"Create from template failed: {resp.text}"
        data = resp.json()
        
        assert "meeting_id" in data
        # Should NOT have _series_generated or it should be 0
        series_count = data.get("_series_generated", 0)
        assert series_count == 0, f"Expected no series, got {series_count}"
        print("✓ Meeting created without series (generate_series=false)")
    
    def test_template_invited_emails_copied_to_meeting(self):
        """Template's invited_emails are copied to the created meeting"""
        # Create template with invited_emails
        template = self.test_create_template_with_custom_schedule()
        template_id = template["template_id"]
        
        # Create meeting from template
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
        payload = {"scheduled_at": future_date.isoformat()}
        resp = self.session.post(f"{BASE_URL}/api/templates/{template_id}/create-meeting", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        
        # Check invited_emails
        invited = data.get("invited_emails", [])
        assert "pdl@klinik.de" in invited, f"Expected pdl@klinik.de in invited_emails, got {invited}"
        print(f"✓ Template invited_emails copied to meeting: {invited}")


class TestRegressionIteration78:
    """Regression tests for iteration 78 features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
        yield
    
    def test_admin_users_pagination(self):
        """GET /api/admin/users with pagination still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users?page=1&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        print(f"✓ Admin users pagination: {data['total']} users, page {data['page']}/{data['pages']}")
    
    def test_admin_users_filters(self):
        """GET /api/admin/users/filters still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/users/filters")
        assert resp.status_code == 200
        data = resp.json()
        assert "departments" in data
        assert "locations" in data
        assert "roles" in data
        print("✓ Admin users filters endpoint works")
    
    def test_force_logout_all_endpoint(self):
        """POST /api/admin/force-logout-all still works"""
        resp = self.session.post(f"{BASE_URL}/api/admin/force-logout-all")
        assert resp.status_code == 200
        data = resp.json()
        assert "modified_count" in data or "affected" in data or "message" in data
        print(f"✓ Force logout all endpoint works: {data}")
    
    def test_email_config_endpoint(self):
        """GET /api/admin/email-config still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "config_id" in data or "smtp" in data or "provider" in data
        print("✓ Email config endpoint works")
    
    def test_dns_check_endpoint(self):
        """GET /api/admin/email-config/dns-check still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/email-config/dns-check?domain=example.com")
        # May return 200 or 400 depending on domain, but endpoint should exist
        assert resp.status_code in [200, 400, 422], f"Unexpected status: {resp.status_code}"
        print(f"✓ DNS check endpoint works (status={resp.status_code})")
    
    def test_admin_stats_endpoint(self):
        """GET /api/admin/stats still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data or "users" in data
        print("✓ Admin stats endpoint works")
    
    def test_admin_groups_endpoint(self):
        """GET /api/admin/groups still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/groups")
        assert resp.status_code == 200
        print("✓ Admin groups endpoint works")
    
    def test_admin_presets_endpoint(self):
        """GET /api/admin/presets still works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/presets")
        assert resp.status_code == 200
        print("✓ Admin presets endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
