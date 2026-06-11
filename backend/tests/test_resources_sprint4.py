"""
Sprint 4 backend tests: buffer time, allowed_combinations, ICS, CSV exports,
QR code, check-in/out, series booking, damage report.
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


@pytest.fixture(scope="module")
def buffer_room(admin_session):
    """Create a room with 30min buffer for buffer-conflict testing."""
    suffix = int(time.time())
    payload = {"name": f"BufRoom_{suffix}", "type": "room", "capacity": 10,
               "buffer_time_min": 30}
    r = admin_session.post(f"{API}/api/resources", json=payload, timeout=10)
    assert r.status_code == 200
    res = r.json()
    yield res
    admin_session.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)


def test_buffer_time_enforces_conflict(admin_session, buffer_room):
    rid = buffer_room["resource_id"]
    # Initial booking 10-11
    r1 = admin_session.post(f"{API}/api/resource-bookings", json={
        "resource_id": rid, "title": "First",
        "start_at": "2028-01-15T10:00:00Z", "end_at": "2028-01-15T11:00:00Z",
    }, timeout=10)
    assert r1.status_code == 200
    # Try 11:10–12:00 — within 30-min buffer of first booking -> 409
    r2 = admin_session.post(f"{API}/api/resource-bookings", json={
        "resource_id": rid, "title": "TooClose",
        "start_at": "2028-01-15T11:10:00Z", "end_at": "2028-01-15T12:00:00Z",
    }, timeout=10)
    assert r2.status_code == 409, f"expected buffer conflict, got {r2.status_code}"
    # 11:30 onward -> OK (exactly at the buffer edge)
    r3 = admin_session.post(f"{API}/api/resource-bookings", json={
        "resource_id": rid, "title": "AfterBuffer",
        "start_at": "2028-01-15T11:30:00Z", "end_at": "2028-01-15T12:00:00Z",
    }, timeout=10)
    assert r3.status_code == 200, f"expected OK after buffer, got {r3.status_code}"


def test_ics_export(admin_session):
    bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
    if not bookings:
        pytest.skip("no bookings")
    bk = bookings[0]
    r = admin_session.get(f"{API}/api/resource-bookings/{bk['booking_id']}/ical", timeout=10)
    assert r.status_code == 200
    text = r.text
    assert "BEGIN:VCALENDAR" in text
    assert "BEGIN:VEVENT" in text
    assert "DTSTART:" in text
    assert "DTEND:" in text


def test_csv_export(admin_session):
    r = admin_session.get(f"{API}/api/resource-bookings/export/csv", timeout=10)
    assert r.status_code == 200
    assert "booking_id," in r.text
    assert r.headers.get("content-type", "").startswith("text/csv")


def test_catering_csv_export(admin_session):
    r = admin_session.get(f"{API}/api/catering-requests/export/csv", timeout=10)
    assert r.status_code == 200
    assert "request_id," in r.text


def test_qr_code(admin_session):
    r = admin_session.get(f"{API}/api/resources/res_demo_saal_001/qr", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["qr_code_url"].startswith("data:image/png;base64,")
    assert "res_demo_saal_001" in d["deep_link"]


def test_resource_calendar(admin_session):
    r = admin_session.get(
        f"{API}/api/resources/res_demo_saal_001/calendar"
        "?from_date=2026-01-01T00:00:00Z&to_date=2027-01-01T00:00:00Z",
        timeout=10,
    )
    assert r.status_code == 200
    d = r.json()
    assert "bookings" in d
    assert "resource_ids" in d


def test_check_in_out_flow(admin_session, buffer_room):
    rid = buffer_room["resource_id"]
    r = admin_session.post(f"{API}/api/resource-bookings", json={
        "resource_id": rid, "title": "CheckTest",
        "start_at": "2028-02-01T10:00:00Z", "end_at": "2028-02-01T11:00:00Z",
    }, timeout=10)
    assert r.status_code == 200
    bk = r.json()
    r2 = admin_session.post(f"{API}/api/resource-bookings/{bk['booking_id']}/check-in", timeout=10)
    assert r2.status_code == 200
    assert r2.json().get("checked_in_at")
    r3 = admin_session.post(f"{API}/api/resource-bookings/{bk['booking_id']}/check-out", json={}, timeout=10)
    assert r3.status_code == 200
    assert r3.json().get("status") == "completed"


def test_series_booking(admin_session, buffer_room):
    rid = buffer_room["resource_id"]
    r = admin_session.post(f"{API}/api/resource-bookings/series", json={
        "resource_id": rid, "title": "Standup",
        "start_at": "2028-03-01T10:00:00Z", "end_at": "2028-03-01T10:30:00Z",
        "recurrence": "weekly", "occurrences": 3,
    }, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert len(d["created"]) == 3
    assert d["series_id"].startswith("sb_")


def test_damage_report(admin_session):
    bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
    if not bookings:
        pytest.skip("no bookings")
    bk = bookings[0]
    r = admin_session.post(f"{API}/api/resource-bookings/{bk['booking_id']}/damage-report",
                          json={"description": "Kleiner Kratzer", "severity": "minor"},
                          timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "open"


def test_catering_re_request_on_time_change(admin_session):
    """Sec 17: changing booking time should reset catering to 'requested'."""
    # Find a booking with catering that has a valid resource
    bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
    resources = admin_session.get(f"{API}/api/resources", timeout=10).json()
    valid_resource_ids = {r["resource_id"] for r in resources}
    
    with_cat = [b for b in bookings if b.get("catering_request_id") and b.get("resource_id") in valid_resource_ids]
    if not with_cat:
        pytest.skip("no catering booking with valid resource")
    bk = with_cat[0]
    cr_id = bk["catering_request_id"]
    # Confirm catering first
    admin_session.post(f"{API}/api/catering-requests/{cr_id}/transition",
                       json={"status": "confirmed"}, timeout=10)
    # Update booking time - use a unique far-future time to avoid conflicts
    import random
    unique_year = 2070 + random.randint(0, 10)
    unique_day = random.randint(1, 28)
    unique_hour = random.randint(1, 12)
    new_start = f"{unique_year}-07-{unique_day:02d}T{unique_hour:02d}:00:00Z"
    new_end = f"{unique_year}-07-{unique_day:02d}T{unique_hour+2:02d}:00:00Z"
    r = admin_session.put(f"{API}/api/resource-bookings/{bk['booking_id']}",
                          json={"start_at": new_start, "end_at": new_end}, timeout=10)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    # Catering must be back to "requested"
    crs = admin_session.get(f"{API}/api/catering-requests", timeout=10).json()
    cr = next(c for c in crs if c["request_id"] == cr_id)
    assert cr["status"] == "requested", f"expected reset, got {cr['status']}"
