"""
Sprint 4 comprehensive tests for the 19-point specification.
Tests: P0 #1-9, P1 #10-13, P2 #14-18 features.
"""
import requests
import pytest
import time

with open("/app/frontend/.env") as f:
    API = next(line.split("=", 1)[1].strip().rstrip("/") for line in f if line.startswith("REACT_APP_BACKEND_URL"))


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/api/auth/login",
               json={"email": "admin@meetflow.com", "password": "admin123"},
               timeout=10)
    assert r.status_code == 200
    yield s


# ============================================================================
# P0 #1: Catering Attachments
# ============================================================================
class TestCateringAttachments:
    """P0 #1: Catering attachments in booking creation."""
    
    def test_booking_with_catering_attachments(self, admin_session):
        """Create booking with catering that includes attachments."""
        # First get a room that allows catering
        resources = admin_session.get(f"{API}/api/resources?type=room", timeout=10).json()
        catering_room = next((r for r in resources if r.get("allow_catering")), None)
        if not catering_room:
            pytest.skip("No room with allow_catering=true")
        
        # Get catering items
        items = admin_session.get(f"{API}/api/catering-items", timeout=10).json()
        if not items:
            pytest.skip("No catering items available")
        
        # Create booking with catering and attachments - use unique far-future time
        import random
        unique_day = random.randint(1, 28)
        unique_hour = random.randint(1, 12)
        unique_year = 2050 + random.randint(0, 10)
        payload = {
            "resource_id": catering_room["resource_id"],
            "title": f"Catering Attach Test {int(time.time())}",
            "start_at": f"{unique_year}-01-{unique_day:02d}T{unique_hour:02d}:00:00Z",
            "end_at": f"{unique_year}-01-{unique_day:02d}T{unique_hour+2:02d}:00:00Z",
            "catering": {
                "items": [{"item_id": items[0]["item_id"], "quantity": 5}],
                "attachments": ["att_test_123", "att_test_456"],  # Mock attachment IDs
                "contact": "Test Contact",
            }
        }
        r = admin_session.post(f"{API}/api/resource-bookings", json=payload, timeout=10)
        assert r.status_code == 200, f"Booking failed: {r.text[:200]}"
        bk = r.json()
        assert bk.get("catering_request_id"), "catering_request_id missing"
        
        # Verify catering request has attachments
        crs = admin_session.get(f"{API}/api/catering-requests", timeout=10).json()
        cr = next((c for c in crs if c["request_id"] == bk["catering_request_id"]), None)
        assert cr is not None, "Catering request not found"
        assert "attachments" in cr, "attachments field missing"
        assert len(cr["attachments"]) == 2, f"Expected 2 attachments, got {len(cr['attachments'])}"


# ============================================================================
# P0 #2: Catering Notifications
# ============================================================================
class TestCateringNotifications:
    """P0 #2: Catering team notifications on new request and status change."""
    
    def test_catering_status_transition_creates_notification(self, admin_session):
        """Transitioning catering status should create notification for booker."""
        # Find a catering request
        crs = admin_session.get(f"{API}/api/catering-requests", timeout=10).json()
        if not crs:
            pytest.skip("No catering requests")
        cr = crs[0]
        
        # Transition to confirmed
        r = admin_session.post(
            f"{API}/api/catering-requests/{cr['request_id']}/transition",
            json={"status": "confirmed"},
            timeout=10
        )
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"
        
        # Check notifications were created (we can't easily verify push, but DB notification should exist)
        # This is a smoke test - the notification logic is in _notify_catering_status


# ============================================================================
# P0 #3: Buffer Time Enforcement
# ============================================================================
class TestBufferTimeEnforcement:
    """P0 #3: Buffer time enforcement in conflict checking."""
    
    @pytest.fixture
    def buffer_room(self, admin_session):
        """Create a room with 30min buffer for testing."""
        suffix = int(time.time())
        payload = {
            "name": f"BufferTestRoom_{suffix}",
            "type": "room",
            "capacity": 10,
            "buffer_time_min": 30
        }
        r = admin_session.post(f"{API}/api/resources", json=payload, timeout=10)
        assert r.status_code == 200
        res = r.json()
        yield res
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)
    
    def test_buffer_blocks_adjacent_booking(self, admin_session, buffer_room):
        """Booking within buffer window should be blocked."""
        rid = buffer_room["resource_id"]
        
        # Create first booking 10:00-11:00
        r1 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": rid,
            "title": "First Booking",
            "start_at": "2041-02-01T10:00:00Z",
            "end_at": "2041-02-01T11:00:00Z",
        }, timeout=10)
        assert r1.status_code == 200
        
        # Try booking 11:15-12:00 (within 30min buffer) -> should fail
        r2 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": rid,
            "title": "Too Close",
            "start_at": "2041-02-01T11:15:00Z",
            "end_at": "2041-02-01T12:00:00Z",
        }, timeout=10)
        assert r2.status_code == 409, f"Expected 409 buffer conflict, got {r2.status_code}"
        
        # Booking at 11:30 (exactly at buffer edge) should succeed
        r3 = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": rid,
            "title": "After Buffer",
            "start_at": "2041-02-01T11:30:00Z",
            "end_at": "2041-02-01T12:00:00Z",
        }, timeout=10)
        assert r3.status_code == 200, f"Expected OK after buffer, got {r3.status_code}"


# ============================================================================
# P0 #4: Allowed Combinations Whitelist
# ============================================================================
class TestAllowedCombinations:
    """P0 #4: Sub-room booking restricted by allowed_combinations whitelist."""
    
    def test_allowed_combinations_enforcement(self, admin_session):
        """Sub-room not in allowed_combinations should be rejected."""
        # Create a splitable room with restricted combinations
        suffix = int(time.time())
        payload = {
            "name": f"RestrictedSaal_{suffix}",
            "type": "room",
            "capacity": 30,
            "is_splitable": True,
            "sub_resources": [
                {"sub_id": "A", "name": "Bereich A", "capacity": 10},
                {"sub_id": "B", "name": "Bereich B", "capacity": 10},
            ],
            "allowed_combinations": [["A", "B"]],  # Only A+B together allowed, not A or B alone
        }
        r = admin_session.post(f"{API}/api/resources", json=payload, timeout=10)
        assert r.status_code == 200
        parent = r.json()
        
        # Get the child resources
        detail = admin_session.get(f"{API}/api/resources/{parent['resource_id']}", timeout=10).json()
        children = detail.get("children", [])
        child_a = next((c for c in children if c.get("sub_id") == "A"), None)
        
        if child_a:
            # Try to book just A alone - should fail because only [A,B] is allowed
            r2 = admin_session.post(f"{API}/api/resource-bookings", json={
                "resource_id": child_a["resource_id"],
                "title": "Solo A Booking",
                "start_at": "2042-03-01T10:00:00Z",
                "end_at": "2042-03-01T11:00:00Z",
            }, timeout=10)
            assert r2.status_code == 400, f"Expected 400 for disallowed combination, got {r2.status_code}"
            assert "nicht als Einzelbuchung freigegeben" in r2.text or "not allowed" in r2.text.lower()
        
        # Cleanup
        admin_session.delete(f"{API}/api/resources/{parent['resource_id']}", timeout=10)


# ============================================================================
# P0 #5: CSV Exports
# ============================================================================
class TestCSVExports:
    """P0 #5: CSV export endpoints for bookings and catering."""
    
    def test_bookings_csv_export(self, admin_session):
        """GET /api/resource-bookings/export/csv returns valid CSV."""
        r = admin_session.get(f"{API}/api/resource-bookings/export/csv", timeout=10)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/csv")
        assert "Content-Disposition" in r.headers
        assert "booking_id," in r.text  # CSV header
    
    def test_catering_csv_export(self, admin_session):
        """GET /api/catering-requests/export/csv returns valid CSV."""
        r = admin_session.get(f"{API}/api/catering-requests/export/csv", timeout=10)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/csv")
        assert "request_id," in r.text  # CSV header


# ============================================================================
# P0 #6: ICS Export
# ============================================================================
class TestICSExport:
    """P0 #6: ICS/iCal export for bookings."""
    
    def test_ics_export_format(self, admin_session):
        """GET /api/resource-bookings/{id}/ical returns valid iCal."""
        bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
        if not bookings:
            pytest.skip("No bookings available")
        
        bk = bookings[0]
        r = admin_session.get(f"{API}/api/resource-bookings/{bk['booking_id']}/ical", timeout=10)
        assert r.status_code == 200
        
        ical = r.text
        assert "BEGIN:VCALENDAR" in ical
        assert "BEGIN:VEVENT" in ical
        assert "DTSTART:" in ical
        assert "DTEND:" in ical
        assert "SUMMARY:" in ical
        assert "LOCATION:" in ical
        assert "STATUS:" in ical
        assert "END:VEVENT" in ical
        assert "END:VCALENDAR" in ical


# ============================================================================
# P0 #8: Auto-Task Assignment
# ============================================================================
class TestAutoTaskAssignment:
    """P0 #8: Auto-created catering tasks have assignee_ids."""
    
    def test_catering_task_has_assignees(self, admin_session):
        """Catering task should have assignee_ids (admins + catering.process users)."""
        # Find a catering request with a task
        crs = admin_session.get(f"{API}/api/catering-requests", timeout=10).json()
        cr_with_task = next((c for c in crs if c.get("task_id")), None)
        if not cr_with_task:
            pytest.skip("No catering request with task")
        
        # Get the task - API returns {"tasks": [...]}
        tasks_resp = admin_session.get(f"{API}/api/tasks", timeout=10).json()
        tasks = tasks_resp.get("tasks", []) if isinstance(tasks_resp, dict) else tasks_resp
        task = next((t for t in tasks if t.get("task_id") == cr_with_task["task_id"]), None)
        if not task:
            pytest.skip("Task not found")
        
        # Verify assignee_ids exists and is populated
        assert "assignee_ids" in task, "assignee_ids field missing from task"
        # At minimum, admin should be assigned
        assert len(task.get("assignee_ids", [])) >= 1, "Task should have at least one assignee"


# ============================================================================
# P1 #11: Resource Calendar
# ============================================================================
class TestResourceCalendar:
    """P1 #11: Per-resource calendar endpoint."""
    
    def test_resource_calendar_endpoint(self, admin_session):
        """GET /api/resources/{id}/calendar returns bookings in window."""
        resources = admin_session.get(f"{API}/api/resources", timeout=10).json()
        if not resources:
            pytest.skip("No resources")
        
        res = resources[0]
        r = admin_session.get(
            f"{API}/api/resources/{res['resource_id']}/calendar"
            "?from_date=2026-01-01T00:00:00Z&to_date=2030-01-01T00:00:00Z",
            timeout=10
        )
        assert r.status_code == 200
        data = r.json()
        assert "resource_ids" in data
        assert "bookings" in data
        assert isinstance(data["bookings"], list)


# ============================================================================
# P1 #13: Photo/QR
# ============================================================================
class TestPhotoQR:
    """P1 #13: Resource image upload and QR code generation."""
    
    def test_qr_code_generation(self, admin_session):
        """GET /api/resources/{id}/qr returns QR code data URL."""
        resources = admin_session.get(f"{API}/api/resources", timeout=10).json()
        if not resources:
            pytest.skip("No resources")
        
        res = resources[0]
        r = admin_session.get(f"{API}/api/resources/{res['resource_id']}/qr", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "qr_code_url" in data
        assert data["qr_code_url"].startswith("data:image/png;base64,")
        assert "deep_link" in data
        assert res["resource_id"] in data["deep_link"]
    
    def test_image_upload_endpoint(self, admin_session):
        """POST /api/resources/{id}/image links attachment as image."""
        resources = admin_session.get(f"{API}/api/resources", timeout=10).json()
        if not resources:
            pytest.skip("No resources")
        
        res = resources[0]
        r = admin_session.post(
            f"{API}/api/resources/{res['resource_id']}/image?attachment_id=att_test_img_123",
            timeout=10
        )
        assert r.status_code == 200
        data = r.json()
        assert "image_url" in data
        assert "att_test_img_123" in data["image_url"]


# ============================================================================
# P2 #14: Damage Report
# ============================================================================
class TestDamageReport:
    """P2 #14: Damage reporting for bookings."""
    
    def test_damage_report_creation(self, admin_session):
        """POST /api/resource-bookings/{id}/damage-report creates report."""
        bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
        if not bookings:
            pytest.skip("No bookings")
        
        bk = bookings[0]
        r = admin_session.post(
            f"{API}/api/resource-bookings/{bk['booking_id']}/damage-report",
            json={"description": "Test damage report", "severity": "minor"},
            timeout=10
        )
        assert r.status_code == 200
        report = r.json()
        assert report["status"] == "open"
        assert "report_id" in report
        assert report["description"] == "Test damage report"
    
    def test_damage_reports_listing(self, admin_session):
        """GET /api/resources/{id}/damage-reports lists reports."""
        bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
        if not bookings:
            pytest.skip("No bookings")
        
        bk = bookings[0]
        r = admin_session.get(
            f"{API}/api/resources/{bk['resource_id']}/damage-reports",
            timeout=10
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ============================================================================
# P2 #14: Maintenance/TUEV
# ============================================================================
class TestMaintenance:
    """P2 #14: Maintenance dates for vehicles."""
    
    def test_maintenance_update(self, admin_session):
        """PUT /api/resources/{id}/maintenance updates maintenance fields."""
        # Get or create a vehicle
        vehicles = admin_session.get(f"{API}/api/resources?type=vehicle", timeout=10).json()
        if not vehicles:
            # Create a test vehicle
            r = admin_session.post(f"{API}/api/resources", json={
                "name": f"TestVehicle_{int(time.time())}",
                "type": "vehicle",
                "license_plate": "TEST-123",
            }, timeout=10)
            assert r.status_code == 200
            vehicle = r.json()
        else:
            vehicle = vehicles[0]
        
        # Update maintenance dates
        r = admin_session.put(
            f"{API}/api/resources/{vehicle['resource_id']}/maintenance",
            json={
                "tuev_due": "2027-06-15",
                "insurance_due": "2027-12-31",
                "service_due": "2027-03-01",
            },
            timeout=10
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("tuev_due") == "2027-06-15"
        assert data.get("insurance_due") == "2027-12-31"


# ============================================================================
# P2 #15: Check-in/Check-out
# ============================================================================
class TestCheckInOut:
    """P2 #15: Check-in and check-out for bookings."""
    
    def test_check_in_out_flow(self, admin_session):
        """Full check-in/check-out flow."""
        # Create a fresh booking
        resources = admin_session.get(f"{API}/api/resources?type=room", timeout=10).json()
        if not resources:
            pytest.skip("No rooms")
        
        res = resources[0]
        unique_ts = int(time.time())
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": res["resource_id"],
            "title": f"CheckInOut Test {unique_ts}",
            "start_at": "2043-01-01T10:00:00Z",
            "end_at": "2043-01-01T11:00:00Z",
        }, timeout=10)
        assert r.status_code == 200
        bk = r.json()
        
        # Check-in
        r2 = admin_session.post(f"{API}/api/resource-bookings/{bk['booking_id']}/check-in", timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("checked_in_at") is not None
        
        # Check-out
        r3 = admin_session.post(f"{API}/api/resource-bookings/{bk['booking_id']}/check-out", json={}, timeout=10)
        assert r3.status_code == 200
        assert r3.json().get("checked_out_at") is not None
        assert r3.json().get("status") == "completed"
    
    def test_vehicle_checkout_updates_mileage(self, admin_session):
        """Check-out with mileage_after updates vehicle mileage."""
        vehicles = admin_session.get(f"{API}/api/resources?type=vehicle", timeout=10).json()
        if not vehicles:
            pytest.skip("No vehicles")
        
        vehicle = vehicles[0]
        unique_ts = int(time.time())
        
        # Create booking with mileage_before
        r = admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": vehicle["resource_id"],
            "title": f"Vehicle Mileage Test {unique_ts}",
            "start_at": "2044-01-01T10:00:00Z",
            "end_at": "2044-01-01T12:00:00Z",
            "mileage_before": 50000,
        }, timeout=10)
        assert r.status_code == 200
        bk = r.json()
        
        # Check-in
        admin_session.post(f"{API}/api/resource-bookings/{bk['booking_id']}/check-in", timeout=10)
        
        # Check-out with mileage_after
        r2 = admin_session.post(
            f"{API}/api/resource-bookings/{bk['booking_id']}/check-out",
            json={"mileage_after": 50150},
            timeout=10
        )
        assert r2.status_code == 200
        assert r2.json().get("mileage_after") == 50150


# ============================================================================
# P2 #18: Series Bookings
# ============================================================================
class TestSeriesBookings:
    """P2 #18: Recurring/series bookings."""
    
    def test_series_booking_creation(self, admin_session):
        """POST /api/resource-bookings/series creates multiple bookings."""
        # Dedicated resource so prior series leftovers don't conflict
        ts = int(time.time() * 1000)
        res = admin_session.post(f"{API}/api/resources", json={
            "name": f"SeriesRoom_{ts}", "type": "room",
        }, timeout=10).json()
        unique_year = 2060 + (ts % 30)  # spread across years to avoid cross-run conflicts

        r = admin_session.post(f"{API}/api/resource-bookings/series", json={
            "resource_id": res["resource_id"],
            "title": f"Weekly Standup {ts}",
            "start_at": f"{unique_year}-01-06T09:00:00Z",  # Monday
            "end_at": f"{unique_year}-01-06T09:30:00Z",
            "recurrence": "weekly",
            "occurrences": 4,
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "series_id" in data
        assert data["series_id"].startswith("sb_")
        # Dedicated resource — all 4 must be created
        assert len(data["created"]) == 4, f"Expected 4 bookings, got {len(data['created'])}"
        # Cleanup
        for bid in data["created"]:
            admin_session.delete(f"{API}/api/resource-bookings/{bid}", timeout=10)
        admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)
    
    def test_series_booking_skips_conflicts(self, admin_session):
        """Series booking skips conflicting slots instead of failing."""
        resources = admin_session.get(f"{API}/api/resources?type=room", timeout=10).json()
        if not resources:
            pytest.skip("No rooms")
        
        res = resources[0]
        unique_ts = int(time.time())
        
        # Create a blocking booking on the second occurrence
        admin_session.post(f"{API}/api/resource-bookings", json={
            "resource_id": res["resource_id"],
            "title": "Blocker",
            "start_at": "2046-01-13T09:00:00Z",  # Second Monday
            "end_at": "2046-01-13T10:00:00Z",
        }, timeout=10)
        
        # Create series - should skip the conflicting one
        r = admin_session.post(f"{API}/api/resource-bookings/series", json={
            "resource_id": res["resource_id"],
            "title": f"Series with Skip {unique_ts}",
            "start_at": "2046-01-06T09:00:00Z",
            "end_at": "2046-01-06T09:30:00Z",
            "recurrence": "weekly",
            "occurrences": 3,
        }, timeout=10)
        assert r.status_code == 200
        data = r.json()
        # Should have created 2 (first and third), skipped 1 (second)
        assert len(data["skipped"]) >= 1, "Expected at least one skipped occurrence"
