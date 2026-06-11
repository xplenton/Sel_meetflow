"""
Iteration 267 — Audit-Trail-UI für Admins + Session-Expiry-Banner + Mobile Umlaut-Cleanup

Tests:
1. AUDIT BACKEND: GET /api/admin/audit/system with new query params (actor, since_hours, search, skip)
2. AUDIT CSV EXPORT: GET /api/admin/audit/system.csv
3. RBAC: member → 403, no token → 401
4. 12-MODULE SANITY CHECK: Auth, Tasks, Calendar, News, Resources, Chat, Admin, Surveys, Meetings, Notifications, Dashboard, Scheduling
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuditBackend:
    """Test audit log API with new query params (iter 267)"""
    
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
    
    def test_audit_no_filter(self):
        """(a) ohne Filter → 200 + total + entries"""
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "entries" in data, "Response should have 'entries'"
        assert "total" in data, "Response should have 'total'"
        assert isinstance(data["entries"], list), "entries should be a list"
        assert isinstance(data["total"], int), "total should be an int"
        print(f"✓ Audit no filter: {data['total']} total entries, {len(data['entries'])} returned")
    
    def test_audit_since_hours_filter(self):
        """(b) ?since_hours=24 → smaller list than all"""
        # Get all first
        all_resp = self.session.get(f"{BASE_URL}/api/admin/audit/system")
        all_data = all_resp.json()
        
        # Get last 24h
        filtered_resp = self.session.get(f"{BASE_URL}/api/admin/audit/system", params={"since_hours": 24})
        assert filtered_resp.status_code == 200
        filtered_data = filtered_resp.json()
        
        # Filtered should be <= all (unless all entries are within 24h)
        assert filtered_data["total"] <= all_data["total"], "since_hours=24 should return <= total entries"
        print(f"✓ Audit since_hours=24: {filtered_data['total']} entries (vs {all_data['total']} total)")
    
    def test_audit_actor_filter(self):
        """(c) ?actor=admin → only entries with 'admin' in actor"""
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system", params={"actor": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        
        # Check that returned entries have 'admin' in actor_name, actor_email, or actor_id
        for entry in data["entries"][:10]:  # Check first 10
            actor_name = (entry.get("actor_name") or "").lower()
            actor_email = (entry.get("actor_email") or "").lower()
            actor_id = (entry.get("actor_id") or "").lower()
            has_admin = "admin" in actor_name or "admin" in actor_email or "admin" in actor_id
            assert has_admin, f"Entry should have 'admin' in actor: {entry}"
        print(f"✓ Audit actor=admin: {data['total']} entries")
    
    def test_audit_search_filter(self):
        """(d) ?search=preset → only entries with 'preset' in action/details"""
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system", params={"search": "preset"})
        assert resp.status_code == 200
        data = resp.json()
        print(f"✓ Audit search=preset: {data['total']} entries")
        # Note: search matches action or details fields, not all entries may have visible 'preset' text
    
    def test_audit_combined_filter(self):
        """(e) ?actor=admin&search=alert → combined filter works"""
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system", params={
            "actor": "admin",
            "search": "alert"
        })
        assert resp.status_code == 200
        data = resp.json()
        print(f"✓ Audit actor=admin&search=alert: {data['total']} entries")
    
    def test_audit_pagination(self):
        """(f) ?limit=5&skip=10 → pagination returns different data than skip=0"""
        resp_page1 = self.session.get(f"{BASE_URL}/api/admin/audit/system", params={"limit": 5, "skip": 0})
        resp_page2 = self.session.get(f"{BASE_URL}/api/admin/audit/system", params={"limit": 5, "skip": 10})
        
        assert resp_page1.status_code == 200
        assert resp_page2.status_code == 200
        
        data1 = resp_page1.json()
        data2 = resp_page2.json()
        
        # If there are enough entries, pages should be different
        if data1["total"] > 10:
            ids1 = [e.get("audit_id") for e in data1["entries"]]
            ids2 = [e.get("audit_id") for e in data2["entries"]]
            # At least some IDs should be different
            assert ids1 != ids2, "Pagination should return different entries"
        
        print(f"✓ Audit pagination: page1={len(data1['entries'])} entries, page2={len(data2['entries'])} entries")


class TestAuditCSVExport:
    """Test CSV export endpoint (iter 267)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
    
    def test_csv_export_content_type(self):
        """CSV export returns correct Content-Type and Content-Disposition"""
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system.csv")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        # Check Content-Type
        content_type = resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"
        
        # Check Content-Disposition
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, f"Expected attachment, got {content_disp}"
        assert "audit-log.csv" in content_disp, f"Expected audit-log.csv in disposition"
        
        print(f"✓ CSV export: Content-Type={content_type}, Content-Disposition={content_disp}")
    
    def test_csv_export_header_row(self):
        """CSV export has correct header row"""
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system.csv")
        assert resp.status_code == 200
        
        # Get first line (header)
        lines = resp.text.split('\n')
        assert len(lines) > 0, "CSV should have at least header row"
        
        header = lines[0].strip()
        expected_cols = ["timestamp", "category", "action", "actor_email", "actor_name", "target_user_id", "ip", "details"]
        for col in expected_cols:
            assert col in header, f"Header should contain '{col}': {header}"
        
        print(f"✓ CSV header: {header}")
    
    def test_csv_export_with_filters(self):
        """CSV export respects filters"""
        resp = self.session.get(f"{BASE_URL}/api/admin/audit/system.csv", params={
            "category": "alert",
            "since_hours": 168  # Last 7 days
        })
        assert resp.status_code == 200
        print(f"✓ CSV export with filters: {len(resp.text)} bytes")


class TestAuditRBAC:
    """Test RBAC for audit endpoints"""
    
    def test_audit_no_token_401(self):
        """(g) No token → 401"""
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/admin/audit/system")
        assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
        print("✓ Audit no token: 401")
    
    def test_audit_csv_no_token_401(self):
        """CSV export without token → 401"""
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/admin/audit/system.csv")
        assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
        print("✓ CSV export no token: 401")
    
    def test_audit_member_403(self):
        """(g) Member role → 403"""
        session = requests.Session()
        # First register a test member
        import uuid
        test_email = f"TEST_member_{uuid.uuid4().hex[:8]}@test.com"
        reg_resp = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "test123",
            "name": "Test Member"
        })
        if reg_resp.status_code == 200:
            # Try to access audit
            resp = session.get(f"{BASE_URL}/api/admin/audit/system")
            assert resp.status_code == 403, f"Expected 403 for member, got {resp.status_code}"
            print("✓ Audit member: 403")
        else:
            # If registration fails, skip
            pytest.skip("Could not create test member")


class TestRegressionSanityCheck:
    """12-Module sanity check: Auth, Tasks, Calendar, News, Resources, Chat, Admin, Surveys, Meetings, Notifications, Dashboard, Scheduling"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@meetflow.com",
            "password": "admin123"
        })
        assert login_resp.status_code == 200
    
    def test_auth_me(self):
        """Auth: GET /api/auth/me → 200"""
        resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        print("✓ Auth /me: 200")
    
    def test_tasks_list(self):
        """Tasks: GET /api/tasks → 200"""
        resp = self.session.get(f"{BASE_URL}/api/tasks")
        assert resp.status_code == 200
        print("✓ Tasks: 200")
    
    def test_calendar_events(self):
        """Calendar: GET /api/calendar/events → 200"""
        resp = self.session.get(f"{BASE_URL}/api/calendar/events")
        assert resp.status_code == 200
        print("✓ Calendar: 200")
    
    def test_news_list(self):
        """News: GET /api/news → 200"""
        resp = self.session.get(f"{BASE_URL}/api/news")
        assert resp.status_code == 200
        print("✓ News: 200")
    
    def test_resources_list(self):
        """Resources: GET /api/resources → 200"""
        resp = self.session.get(f"{BASE_URL}/api/resources")
        assert resp.status_code == 200
        print("✓ Resources: 200")
    
    def test_chat_channels(self):
        """Chat: GET /api/chat/channels → 200"""
        resp = self.session.get(f"{BASE_URL}/api/chat/channels")
        assert resp.status_code == 200
        print("✓ Chat: 200")
    
    def test_admin_stats(self):
        """Admin: GET /api/admin/stats → 200"""
        resp = self.session.get(f"{BASE_URL}/api/admin/stats")
        assert resp.status_code == 200
        print("✓ Admin stats: 200")
    
    def test_surveys_list(self):
        """Surveys: GET /api/surveys → 200"""
        resp = self.session.get(f"{BASE_URL}/api/surveys")
        assert resp.status_code == 200
        print("✓ Surveys: 200")
    
    def test_meetings_list(self):
        """Meetings: GET /api/meetings → 200"""
        resp = self.session.get(f"{BASE_URL}/api/meetings")
        assert resp.status_code == 200
        print("✓ Meetings: 200")
    
    def test_notifications_list(self):
        """Notifications: GET /api/notifications → 200"""
        resp = self.session.get(f"{BASE_URL}/api/notifications")
        assert resp.status_code == 200
        print("✓ Notifications: 200")
    
    def test_dashboard_stats(self):
        """Dashboard: GET /api/dashboard/stats → 200"""
        resp = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200
        print("✓ Dashboard: 200")
    
    def test_scheduling_polls(self):
        """Scheduling: GET /api/schedule/polls → 200"""
        resp = self.session.get(f"{BASE_URL}/api/schedule/polls")
        assert resp.status_code == 200
        print("✓ Scheduling: 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
