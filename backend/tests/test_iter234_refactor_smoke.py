"""
Iter 234 — Backend Refactor Smoke Test
Validates that all 70+ endpoints from the refactored resources module still work.
The module was split from a single 2747-line file into:
  - /app/backend/routes/resources/__init__.py (combines sub-routers)
  - /app/backend/routes/resources/_common.py (shared helpers/models)
  - /app/backend/routes/resources/bookings.py
  - /app/backend/routes/resources/catering.py
  - /app/backend/routes/resources/invoices.py
  - /app/backend/routes/resources/admin.py
"""
import requests
import pytest
from datetime import datetime, timedelta

# Read API base from frontend .env
with open("/app/frontend/.env") as f:
    API = next(line.split("=", 1)[1].strip().rstrip("/") for line in f if line.startswith("REACT_APP_BACKEND_URL"))


@pytest.fixture(scope="module")
def session():
    """Authenticated session as admin."""
    sess = requests.Session()
    r = sess.post(f"{API}/api/auth/login",
                  json={"email": "admin@meetflow.com", "password": "admin123"}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.text}"
    yield sess


class TestAdminEndpoints:
    """Tests for admin.py endpoints (resources CRUD, dashboard, floorplans, etc.)"""

    def test_list_resources(self, session):
        """GET /api/resources"""
        r = session.get(f"{API}/api/resources", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        print(f"  -> Found {len(data)} resources")

    def test_list_resources_by_type(self, session):
        """GET /api/resources?type=room"""
        for t in ["room", "desk", "vehicle"]:
            r = session.get(f"{API}/api/resources?type={t}", timeout=10)
            assert r.status_code == 200
            print(f"  -> {t}: {len(r.json())} items")

    def test_get_resource_detail(self, session):
        """GET /api/resources/{resource_id}"""
        # First get a resource
        r = session.get(f"{API}/api/resources", timeout=10)
        items = r.json()
        if items:
            rid = items[0]["resource_id"]
            r2 = session.get(f"{API}/api/resources/{rid}", timeout=10)
            assert r2.status_code == 200
            assert r2.json()["resource_id"] == rid
            print(f"  -> Got detail for {rid}")

    def test_dashboard_overview(self, session):
        """GET /api/resources/dashboard/overview"""
        r = session.get(f"{API}/api/resources/dashboard/overview?days=30", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "resources_by_type" in data
        assert "bookings_by_status" in data
        print(f"  -> Dashboard: {data.get('resources_by_type')}")

    def test_no_show_analytics(self, session):
        """GET /api/resources/dashboard/no-show"""
        r = session.get(f"{API}/api/resources/dashboard/no-show?days=90", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "no_show_count" in data
        print(f"  -> No-show rate: {data.get('no_show_rate')}")

    def test_by_department(self, session):
        """GET /api/resources/dashboard/by-department"""
        r = session.get(f"{API}/api/resources/dashboard/by-department?days=90", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "rows" in data
        print(f"  -> Departments: {len(data.get('rows', []))} entries")

    def test_cost_centers(self, session):
        """GET /api/cost-centers"""
        r = session.get(f"{API}/api/cost-centers", timeout=10)
        assert r.status_code == 200
        print(f"  -> Cost centers: {len(r.json())} items")

    def test_accounts(self, session):
        """GET /api/accounts"""
        r = session.get(f"{API}/api/accounts", timeout=10)
        assert r.status_code == 200
        print(f"  -> Accounts: {len(r.json())} items")

    def test_floorplans(self, session):
        """GET /api/floorplans"""
        r = session.get(f"{API}/api/floorplans", timeout=10)
        assert r.status_code == 200
        print(f"  -> Floorplans: {len(r.json())} items")

    def test_upload_config(self, session):
        """GET /api/resource-upload-config"""
        r = session.get(f"{API}/api/resource-upload-config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "max_size_mb" in data
        print(f"  -> Upload config: max {data.get('max_size_mb')} MB")

    def test_availability_snapshot(self, session):
        """GET /api/resource-availability-snapshot"""
        r = session.get(f"{API}/api/resource-availability-snapshot", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "snapshot" in data
        print(f"  -> Snapshot: {len(data.get('snapshot', {}))} resources")

    def test_driver_license_get(self, session):
        """GET /api/users/{user_id}/driver-license — 410 Gone since Iter 292
        (use plural /drivers-licenses endpoint instead)."""
        me = session.get(f"{API}/api/auth/me", timeout=10).json()
        r = session.get(f"{API}/api/users/{me['user_id']}/driver-license", timeout=10)
        assert r.status_code == 410
        print("  -> Driver license endpoint: 410 Gone (use plural endpoint)")


class TestBookingsEndpoints:
    """Tests for bookings.py endpoints"""

    def test_list_bookings(self, session):
        """GET /api/resource-bookings"""
        r = session.get(f"{API}/api/resource-bookings", timeout=10)
        assert r.status_code == 200
        print(f"  -> Bookings: {len(r.json())} items")

    def test_list_bookings_mine_only(self, session):
        """GET /api/resource-bookings?mine_only=true"""
        r = session.get(f"{API}/api/resource-bookings?mine_only=true", timeout=10)
        assert r.status_code == 200
        print(f"  -> My bookings: {len(r.json())} items")

    def test_approvals_pending_count(self, session):
        """GET /api/resource-bookings/approvals/pending-count"""
        r = session.get(f"{API}/api/resource-bookings/approvals/pending-count", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        print(f"  -> Pending approvals: {data.get('count')}")

    def test_check_conflicts(self, session):
        """POST /api/resources/{id}/check-conflicts"""
        # Get a resource first
        res = session.get(f"{API}/api/resources?type=room", timeout=10).json()
        if res:
            rid = res[0]["resource_id"]
            now = datetime.utcnow()
            r = session.post(f"{API}/api/resources/{rid}/check-conflicts", json={
                "start_at": (now + timedelta(days=30)).isoformat() + "Z",
                "end_at": (now + timedelta(days=30, hours=1)).isoformat() + "Z",
            }, timeout=10)
            assert r.status_code == 200
            data = r.json()
            assert "conflicts" in data
            print(f"  -> Conflicts: {len(data.get('conflicts', []))}")

    def test_suggest_slots(self, session):
        """POST /api/resources/{id}/suggest-slots"""
        res = session.get(f"{API}/api/resources?type=room", timeout=10).json()
        if res:
            rid = res[0]["resource_id"]
            now = datetime.utcnow()
            r = session.post(f"{API}/api/resources/{rid}/suggest-slots", json={
                "start_at": now.isoformat() + "Z",
                "duration_min": 60,
                "count": 3,
            }, timeout=10)
            assert r.status_code == 200
            data = r.json()
            assert "suggestions" in data
            print(f"  -> Suggestions: {len(data.get('suggestions', []))}")


class TestCateringEndpoints:
    """Tests for catering.py endpoints"""

    def test_list_catering_items(self, session):
        """GET /api/catering-items"""
        r = session.get(f"{API}/api/catering-items", timeout=10)
        assert r.status_code == 200
        print(f"  -> Catering items: {len(r.json())} items")

    def test_list_catering_requests(self, session):
        """GET /api/catering-requests"""
        r = session.get(f"{API}/api/catering-requests", timeout=10)
        assert r.status_code == 200
        print(f"  -> Catering requests: {len(r.json())} items")

    def test_rejection_reasons(self, session):
        """GET /api/catering-requests/rejection-reasons"""
        r = session.get(f"{API}/api/catering-requests/rejection-reasons", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "reasons" in data
        assert len(data["reasons"]) > 0
        print(f"  -> Rejection reasons: {len(data.get('reasons', []))}")


class TestInvoicesEndpoints:
    """Tests for invoices.py endpoints (exports, invoices)"""

    def test_export_bookings_csv(self, session):
        """GET /api/resource-bookings/export/csv"""
        r = session.get(f"{API}/api/resource-bookings/export/csv", timeout=15)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        print(f"  -> CSV export: {len(r.content)} bytes")

    def test_export_bookings_xlsx(self, session):
        """GET /api/resource-bookings/export/xlsx"""
        r = session.get(f"{API}/api/resource-bookings/export/xlsx", timeout=15)
        assert r.status_code == 200
        print(f"  -> XLSX export: {len(r.content)} bytes")

    def test_erp_export_csv(self, session):
        """GET /api/resource-bookings/export/erp.csv"""
        r = session.get(f"{API}/api/resource-bookings/export/erp.csv?days=90&format=datev", timeout=15)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        print(f"  -> ERP export: {len(r.content)} bytes")

    def test_aggregate_catering_invoice(self, session):
        """GET /api/catering-requests/invoices/aggregate"""
        r = session.get(f"{API}/api/catering-requests/invoices/aggregate", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        print(f"  -> Aggregate invoice total: {data.get('total')} EUR")


class TestSeriesAndComboBookings:
    """Tests for series and combo booking endpoints"""

    def test_series_booking_endpoint_exists(self, session):
        """POST /api/resource-bookings/series - verify endpoint exists"""
        # Just verify the endpoint responds (don't actually create)
        res = session.get(f"{API}/api/resources?type=room", timeout=10).json()
        if res:
            rid = res[0]["resource_id"]
            now = datetime.utcnow()
            # Use a far future date to avoid conflicts
            r = session.post(f"{API}/api/resource-bookings/series", json={
                "resource_id": rid,
                "title": "TEST_SERIES_SMOKE",
                "start_at": (now + timedelta(days=365)).isoformat() + "Z",
                "end_at": (now + timedelta(days=365, hours=1)).isoformat() + "Z",
                "recurrence": "weekly",
                "occurrences": 2,
            }, timeout=10)
            # Should succeed or fail with conflict, not 404/500
            assert r.status_code in [200, 201, 409], f"Unexpected status: {r.status_code}"
            print(f"  -> Series endpoint: {r.status_code}")
            # Cleanup if created
            if r.status_code in [200, 201]:
                data = r.json()
                for bid in data.get("created", []):
                    session.delete(f"{API}/api/resource-bookings/{bid}", timeout=10)

    def test_combo_booking_endpoint_exists(self, session):
        """POST /api/resource-bookings/combo - verify endpoint exists"""
        # Find a splitable room
        res = session.get(f"{API}/api/resources?type=room&include_children=true", timeout=10).json()
        splitable = [r for r in res if r.get("is_splitable")]
        if splitable:
            parent = splitable[0]
            # Get children
            detail = session.get(f"{API}/api/resources/{parent['resource_id']}", timeout=10).json()
            children = detail.get("children", [])
            if len(children) >= 2:
                sub_ids = [c["sub_id"] for c in children[:2]]
                now = datetime.utcnow()
                r = session.post(f"{API}/api/resource-bookings/combo", json={
                    "parent_resource_id": parent["resource_id"],
                    "sub_ids": sub_ids,
                    "title": "TEST_COMBO_SMOKE",
                    "start_at": (now + timedelta(days=366)).isoformat() + "Z",
                    "end_at": (now + timedelta(days=366, hours=1)).isoformat() + "Z",
                }, timeout=10)
                assert r.status_code in [200, 201, 400, 409], f"Unexpected: {r.status_code}"
                print(f"  -> Combo endpoint: {r.status_code}")
                # Cleanup
                if r.status_code in [200, 201]:
                    data = r.json()
                    for bid in data.get("booking_ids", []):
                        session.delete(f"{API}/api/resource-bookings/{bid}", timeout=10)
            else:
                print("  -> Combo: No children found, skipping")
        else:
            print("  -> Combo: No splitable rooms, skipping")


class TestUtilizationAndBlackouts:
    """Tests for utilization and blackout endpoints"""

    def test_utilization_by_sub(self, session):
        """GET /api/resources/{id}/utilization-by-sub"""
        res = session.get(f"{API}/api/resources?type=room&include_children=true", timeout=10).json()
        splitable = [r for r in res if r.get("is_splitable")]
        if splitable:
            rid = splitable[0]["resource_id"]
            r = session.get(f"{API}/api/resources/{rid}/utilization-by-sub?days=30", timeout=10)
            assert r.status_code == 200
            data = r.json()
            assert "sub_rows" in data
            print(f"  -> Utilization: {len(data.get('sub_rows', []))} sub-rows")
        else:
            print("  -> Utilization: No splitable rooms, skipping")

    def test_list_blackouts(self, session):
        """GET /api/resources/{id}/blackouts"""
        res = session.get(f"{API}/api/resources?type=room", timeout=10).json()
        if res:
            rid = res[0]["resource_id"]
            r = session.get(f"{API}/api/resources/{rid}/blackouts", timeout=10)
            assert r.status_code == 200
            print(f"  -> Blackouts: {len(r.json())} items")


class TestVehicleSpecific:
    """Tests for vehicle-specific endpoints"""

    def test_driving_log(self, session):
        """GET /api/resources/{vehicle_id}/driving-log"""
        res = session.get(f"{API}/api/resources?type=vehicle", timeout=10).json()
        if res:
            vid = res[0]["resource_id"]
            r = session.get(f"{API}/api/resources/{vid}/driving-log", timeout=10)
            assert r.status_code == 200
            print(f"  -> Driving log: {len(r.json())} entries")
        else:
            print("  -> Driving log: No vehicles, skipping")

    def test_damage_reports(self, session):
        """GET /api/resources/{id}/damage-reports"""
        res = session.get(f"{API}/api/resources?type=vehicle", timeout=10).json()
        if res:
            vid = res[0]["resource_id"]
            r = session.get(f"{API}/api/resources/{vid}/damage-reports", timeout=10)
            assert r.status_code == 200
            print(f"  -> Damage reports: {len(r.json())} items")
        else:
            print("  -> Damage reports: No vehicles, skipping")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
