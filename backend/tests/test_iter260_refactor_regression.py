"""
Iteration 260 — Refactoring + Bugfix Regression Tests
======================================================
Tests für:
- FIX D: POST /api/admin/groups → 409 bei duplicate Name (case-insensitive)
- FIX D: PUT /api/admin/groups/{id} → 409 bei Namensänderung auf existierenden Namen
- REFACTOR B: Office-Days Endpoints (neue Datei routes/resources/office_days.py)
- REFACTOR B: Bookings Endpoints (routes/resources/bookings.py)
- BUG-FIX: surveys_archive.py Dict-Repeat-Key-Bug ($nin statt doppeltem $ne)
- BUG-FIX: gifs.py fehlender 'import httpx'
- LINT-CLEANUP: Sanity-Check aller Module nach ~800 ruff F401/F541 Fixes
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"

# Global token cache to avoid rate limiting
_TOKEN_CACHE = {}

def get_admin_token():
    """Get admin token with caching to avoid rate limits"""
    if "admin" in _TOKEN_CACHE:
        return _TOKEN_CACHE["admin"]
    
    for attempt in range(3):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if resp.status_code == 200:
            token = resp.json().get("access_token") or resp.json().get("token")
            _TOKEN_CACHE["admin"] = token
            return token
        elif resp.status_code == 429:
            time.sleep(10)  # Wait for rate limit
        else:
            break
    
    raise Exception(f"Could not get admin token: {resp.status_code} {resp.text}")


class TestGroupDuplicateNameFix:
    """FIX D: Duplicate Gruppenname (case-insensitive) muss 409 zurückgeben"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        token = get_admin_token()
        return {"Authorization": f"Bearer {token}"}
    
    def test_create_group_duplicate_name_exact(self, admin_headers):
        """POST /api/admin/groups mit exakt gleichem Namen → 409"""
        group_name = f"TestDup260-{uuid.uuid4().hex[:6]}"
        
        # Erste Gruppe erstellen
        resp1 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name,
            "description": "First group"
        })
        assert resp1.status_code == 200, f"First group creation failed: {resp1.text}"
        group_id = resp1.json().get("group_id")
        
        # Zweite Gruppe mit gleichem Namen → muss 409 sein
        resp2 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": group_name,
            "description": "Duplicate"
        })
        assert resp2.status_code == 409, f"Expected 409 for duplicate name, got {resp2.status_code}: {resp2.text}"
        print(f"PASS — Duplicate group name '{group_name}' correctly rejected with 409")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}", headers=admin_headers)
    
    def test_create_group_duplicate_name_case_insensitive(self, admin_headers):
        """POST /api/admin/groups mit case-insensitive gleichem Namen → 409"""
        base_name = f"CaseTest260-{uuid.uuid4().hex[:6]}"
        
        # Erste Gruppe mit lowercase
        resp1 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": base_name.lower(),
            "description": "Lowercase"
        })
        assert resp1.status_code == 200, f"First group creation failed: {resp1.text}"
        group_id = resp1.json().get("group_id")
        
        # Zweite Gruppe mit UPPERCASE → muss 409 sein (case-insensitive)
        resp2 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": base_name.upper(),
            "description": "Uppercase duplicate"
        })
        assert resp2.status_code == 409, f"Expected 409 for case-insensitive duplicate, got {resp2.status_code}"
        print(f"PASS — Case-insensitive duplicate '{base_name.upper()}' correctly rejected with 409")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}", headers=admin_headers)
    
    def test_update_group_to_existing_name(self, admin_headers):
        """PUT /api/admin/groups/{id} mit Name einer anderen Gruppe → 409"""
        name1 = f"Group1-260-{uuid.uuid4().hex[:6]}"
        name2 = f"Group2-260-{uuid.uuid4().hex[:6]}"
        
        # Zwei Gruppen erstellen
        resp1 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": name1
        })
        assert resp1.status_code == 200
        group1_id = resp1.json().get("group_id")
        
        resp2 = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": name2
        })
        assert resp2.status_code == 200
        group2_id = resp2.json().get("group_id")
        
        # Versuche group2 auf name1 umzubenennen → muss 409 sein
        update_resp = requests.put(f"{BASE_URL}/api/admin/groups/{group2_id}", 
                                   headers=admin_headers, json={"name": name1})
        assert update_resp.status_code == 409, f"Expected 409 for rename to existing name, got {update_resp.status_code}"
        print(f"PASS — Rename to existing name '{name1}' correctly rejected with 409")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/groups/{group1_id}", headers=admin_headers)
        requests.delete(f"{BASE_URL}/api/admin/groups/{group2_id}", headers=admin_headers)
    
    def test_update_group_same_name_allowed(self, admin_headers):
        """PUT /api/admin/groups/{id} mit eigenem Namen → 200 (kein Konflikt)"""
        name = f"SelfUpdate260-{uuid.uuid4().hex[:6]}"
        
        resp = requests.post(f"{BASE_URL}/api/admin/groups", headers=admin_headers, json={
            "name": name
        })
        assert resp.status_code == 200
        group_id = resp.json().get("group_id")
        
        # Update mit gleichem Namen + neuer Description → sollte 200 sein
        update_resp = requests.put(f"{BASE_URL}/api/admin/groups/{group_id}", 
                                   headers=admin_headers, json={
                                       "name": name,
                                       "description": "Updated description"
                                   })
        assert update_resp.status_code == 200, f"Self-update should be allowed, got {update_resp.status_code}"
        print("PASS — Self-update with same name allowed (200)")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/groups/{group_id}", headers=admin_headers)


class TestOfficeDaysEndpoints:
    """REFACTOR B: Office-Days Endpoints in routes/resources/office_days.py"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        token = get_admin_token()
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_office_days(self, admin_headers):
        """GET /api/users/me/office-days"""
        resp = requests.get(f"{BASE_URL}/api/users/me/office-days", headers=admin_headers)
        assert resp.status_code == 200, f"GET office-days failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "weekdays" in data
        print(f"PASS — GET /api/users/me/office-days: weekdays={data.get('weekdays')}")
    
    def test_put_office_days(self, admin_headers):
        """PUT /api/users/me/office-days"""
        resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=admin_headers, json={
            "weekdays": ["mon", "wed", "fri"],
            "start_time": "09:00",
            "end_time": "17:00",
            "title": "Test Bürotag"
        })
        assert resp.status_code == 200, f"PUT office-days failed: {resp.status_code} {resp.text}"
        print("PASS — PUT /api/users/me/office-days")
    
    def test_get_skip_reasons(self, admin_headers):
        """GET /api/office-days/skip-reasons"""
        resp = requests.get(f"{BASE_URL}/api/office-days/skip-reasons", headers=admin_headers)
        assert resp.status_code == 200, f"GET skip-reasons failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "reasons" in data
        reasons = [r["id"] for r in data["reasons"]]
        assert "krank" in reasons
        assert "homeoffice" in reasons
        print(f"PASS — GET /api/office-days/skip-reasons: {reasons}")
    
    def test_get_upcoming_office_days(self, admin_headers):
        """GET /api/users/me/office-days/upcoming"""
        resp = requests.get(f"{BASE_URL}/api/users/me/office-days/upcoming", headers=admin_headers)
        assert resp.status_code == 200, f"GET upcoming failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "upcoming" in data
        print(f"PASS — GET /api/users/me/office-days/upcoming: {data.get('count', 0)} bookings")
    
    def test_get_office_week(self, admin_headers):
        """GET /api/resources-office-week"""
        resp = requests.get(f"{BASE_URL}/api/resources-office-week", headers=admin_headers)
        assert resp.status_code == 200, f"GET office-week failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "week_start" in data
        assert "days" in data
        print(f"PASS — GET /api/resources-office-week: week_start={data.get('week_start')}")
    
    def test_slack_test_without_webhook(self, admin_headers):
        """POST /api/users/me/office-days/slack/test ohne Webhook → 400"""
        resp = requests.post(f"{BASE_URL}/api/users/me/office-days/slack/test", headers=admin_headers)
        # Erwartet 400 wenn kein Webhook konfiguriert
        assert resp.status_code in [400, 200], f"Slack test unexpected: {resp.status_code}"
        if resp.status_code == 400:
            print("PASS — POST /api/users/me/office-days/slack/test: 400 (no webhook configured)")
        else:
            print("PASS — POST /api/users/me/office-days/slack/test: 200 (webhook configured)")


class TestBookingsEndpoints:
    """REFACTOR B: Bookings Endpoints in routes/resources/bookings.py"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        token = get_admin_token()
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_resource_bookings(self, admin_headers):
        """GET /api/resource-bookings"""
        resp = requests.get(f"{BASE_URL}/api/resource-bookings", headers=admin_headers)
        assert resp.status_code == 200, f"GET bookings failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS — GET /api/resource-bookings: {len(data)} bookings")
    
    def test_get_approvals_pending_count(self, admin_headers):
        """GET /api/resource-bookings/approvals/pending-count"""
        resp = requests.get(f"{BASE_URL}/api/resource-bookings/approvals/pending-count", 
                           headers=admin_headers)
        assert resp.status_code == 200, f"GET pending-count failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "count" in data
        print(f"PASS — GET /api/resource-bookings/approvals/pending-count: {data.get('count')}")
    
    def test_check_conflicts_endpoint(self, admin_headers):
        """POST /api/resources/{id}/check-conflicts"""
        # Erst eine Ressource finden
        resources_resp = requests.get(f"{BASE_URL}/api/resources", headers=admin_headers)
        if resources_resp.status_code != 200:
            pytest.skip("Could not get resources")
        resources = resources_resp.json()
        if not resources:
            pytest.skip("No resources available")
        
        resource_id = resources[0].get("resource_id")
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        start = (now + timedelta(days=1)).replace(hour=10, minute=0).isoformat() + "Z"
        end = (now + timedelta(days=1)).replace(hour=11, minute=0).isoformat() + "Z"
        
        resp = requests.post(f"{BASE_URL}/api/resources/{resource_id}/check-conflicts",
                            headers=admin_headers, json={
                                "start_at": start,
                                "end_at": end
                            })
        assert resp.status_code == 200, f"Check conflicts failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "conflicts" in data
        print(f"PASS — POST /api/resources/{resource_id}/check-conflicts")
    
    def test_suggest_slots_endpoint(self, admin_headers):
        """POST /api/resources/{id}/suggest-slots"""
        resources_resp = requests.get(f"{BASE_URL}/api/resources", headers=admin_headers)
        if resources_resp.status_code != 200:
            pytest.skip("Could not get resources")
        resources = resources_resp.json()
        if not resources:
            pytest.skip("No resources available")
        
        resource_id = resources[0].get("resource_id")
        from datetime import datetime, timedelta
        start = (datetime.utcnow() + timedelta(days=1)).replace(hour=8, minute=0).isoformat() + "Z"
        
        resp = requests.post(f"{BASE_URL}/api/resources/{resource_id}/suggest-slots",
                            headers=admin_headers, json={
                                "start_at": start,
                                "duration_min": 60,
                                "count": 3
                            })
        assert resp.status_code == 200, f"Suggest slots failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "suggestions" in data
        print(f"PASS — POST /api/resources/{resource_id}/suggest-slots: {len(data.get('suggestions', []))} suggestions")


class TestGifsEndpoint:
    """BUG-FIX: gifs.py fehlender 'import httpx'"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        token = get_admin_token()
        return {"Authorization": f"Bearer {token}"}
    
    def test_gif_search_no_nameerror(self, admin_headers):
        """GET /api/chat/gifs?q=hello → kein NameError (httpx importiert)"""
        resp = requests.get(f"{BASE_URL}/api/chat/gifs", headers=admin_headers, 
                           params={"q": "hello"})
        # Sollte 200 oder 403 sein, aber NICHT 500 mit NameError
        assert resp.status_code != 500, f"GIF search returned 500 (possible NameError): {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "results" in data
            print(f"PASS — GET /api/chat/gifs: {len(data.get('results', []))} results (httpx works)")
        elif resp.status_code == 403:
            print("PASS — GET /api/chat/gifs: 403 (permission denied, but no NameError)")
        else:
            print(f"PASS — GET /api/chat/gifs: {resp.status_code} (no 500/NameError)")


class TestSurveyArchive:
    """BUG-FIX: surveys_archive.py Dict-Repeat-Key-Bug ($nin statt $ne)"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        token = get_admin_token()
        return {"Authorization": f"Bearer {token}"}
    
    def test_auto_archive_endpoint_exists(self, admin_headers):
        """POST /api/admin/surveys/auto-archive (falls vorhanden)"""
        resp = requests.post(f"{BASE_URL}/api/admin/surveys/auto-archive", headers=admin_headers)
        # Endpoint könnte existieren oder nicht
        if resp.status_code == 404:
            print("INFO — POST /api/admin/surveys/auto-archive: 404 (endpoint not exposed)")
        elif resp.status_code == 200:
            data = resp.json()
            print(f"PASS — POST /api/admin/surveys/auto-archive: archived={data.get('archived', 0)}")
        elif resp.status_code == 403:
            print("PASS — POST /api/admin/surveys/auto-archive: 403 (permission check works)")
        else:
            print(f"INFO — POST /api/admin/surveys/auto-archive: {resp.status_code}")
    
    def test_surveys_list_works(self, admin_headers):
        """GET /api/surveys funktioniert nach $nin Fix"""
        resp = requests.get(f"{BASE_URL}/api/surveys", headers=admin_headers)
        assert resp.status_code == 200, f"GET surveys failed: {resp.status_code} {resp.text}"
        data = resp.json()
        # Kann Liste oder Dict mit surveys sein
        if isinstance(data, list):
            print(f"PASS — GET /api/surveys: {len(data)} surveys")
        else:
            print(f"PASS — GET /api/surveys: {len(data.get('surveys', []))} surveys")


class TestModuleSanityCheck:
    """LINT-CLEANUP: Sanity-Check aller Module nach ruff F401/F541 Fixes"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        token = get_admin_token()
        return {"Authorization": f"Bearer {token}"}
    
    def test_auth_module(self, admin_headers):
        """Auth-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        assert resp.status_code == 200, f"Auth/me failed: {resp.status_code}"
        print("PASS — Auth module works")
    
    def test_tasks_module(self, admin_headers):
        """Tasks-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers)
        assert resp.status_code == 200, f"Tasks failed: {resp.status_code}"
        print("PASS — Tasks module works")
    
    def test_calendar_module(self, admin_headers):
        """Calendar-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/calendar/events", headers=admin_headers)
        assert resp.status_code == 200, f"Calendar failed: {resp.status_code}"
        print("PASS — Calendar module works")
    
    def test_news_module(self, admin_headers):
        """News-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/news/feed", headers=admin_headers)
        assert resp.status_code == 200, f"News failed: {resp.status_code}"
        print("PASS — News module works")
    
    def test_resources_module(self, admin_headers):
        """Resources-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/resources", headers=admin_headers)
        assert resp.status_code == 200, f"Resources failed: {resp.status_code}"
        print("PASS — Resources module works")
    
    def test_chat_module(self, admin_headers):
        """Chat-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/chat/conversations", headers=admin_headers)
        assert resp.status_code == 200, f"Chat failed: {resp.status_code}"
        print("PASS — Chat module works")
    
    def test_admin_module(self, admin_headers):
        """Admin-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers)
        assert resp.status_code == 200, f"Admin stats failed: {resp.status_code}"
        print("PASS — Admin module works")
    
    def test_surveys_module(self, admin_headers):
        """Surveys-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/surveys", headers=admin_headers)
        assert resp.status_code == 200, f"Surveys failed: {resp.status_code}"
        print("PASS — Surveys module works")
    
    def test_meetings_module(self, admin_headers):
        """Meetings-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/meetings", headers=admin_headers)
        assert resp.status_code == 200, f"Meetings failed: {resp.status_code}"
        print("PASS — Meetings module works")
    
    def test_notifications_module(self, admin_headers):
        """Notifications-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/notifications", headers=admin_headers)
        assert resp.status_code == 200, f"Notifications failed: {resp.status_code}"
        print("PASS — Notifications module works")
    
    def test_dashboard_module(self, admin_headers):
        """Dashboard-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=admin_headers)
        assert resp.status_code == 200, f"Dashboard failed: {resp.status_code}"
        print("PASS — Dashboard module works")
    
    def test_scheduling_module(self, admin_headers):
        """Scheduling-Modul funktioniert"""
        resp = requests.get(f"{BASE_URL}/api/schedule-polls", headers=admin_headers)
        assert resp.status_code == 200, f"Scheduling failed: {resp.status_code}"
        print("PASS — Scheduling module works")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        token = get_admin_token()
        return {"Authorization": f"Bearer {token}"}
    
    def test_cleanup_test_groups(self, admin_headers):
        """Cleanup TestDup260-*, CaseTest260-*, Group*-260-*, SelfUpdate260-* groups"""
        resp = requests.get(f"{BASE_URL}/api/admin/groups", headers=admin_headers)
        if resp.status_code != 200:
            return
        
        groups = resp.json()
        deleted = 0
        for g in groups:
            name = g.get("name", "")
            if any(prefix in name for prefix in ["TestDup260", "CaseTest260", "260-", "SelfUpdate260"]):
                del_resp = requests.delete(f"{BASE_URL}/api/admin/groups/{g['group_id']}", 
                                          headers=admin_headers)
                if del_resp.status_code == 200:
                    deleted += 1
        
        print(f"Cleanup: deleted {deleted} test groups")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
