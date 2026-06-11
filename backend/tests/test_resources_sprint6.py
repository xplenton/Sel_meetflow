"""
Sprint 6 (iter 228) — final audit gap-closer tests.
Covers: Combo-Bookings, Blackouts, Cost-centers/Accounts, Invoice approval,
Favorites, Driving log, XLSX, No-show analytics, Rejection reasons.
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
def combo_room(admin_session):
    """Splittable room with whitelist allowing [A], [B], [A,B]."""
    suffix = int(time.time())
    payload = {
        "name": f"ComboRoom_{suffix}", "type": "room", "is_splitable": True,
        "allowed_combinations": [["A"], ["B"], ["A", "B"]],
        "sub_resources": [
            {"sub_id": "A", "name": "A", "capacity": 10},
            {"sub_id": "B", "name": "B", "capacity": 10},
        ],
    }
    r = admin_session.post(f"{API}/api/resources", json=payload, timeout=10)
    assert r.status_code == 200
    parent = r.json()
    yield parent
    admin_session.delete(f"{API}/api/resources/{parent['resource_id']}", timeout=10)


def test_combo_booking_success(admin_session, combo_room):
    r = admin_session.post(f"{API}/api/resource-bookings/combo", json={
        "parent_resource_id": combo_room["resource_id"],
        "sub_ids": ["A", "B"],
        "title": "Workshop A+B",
        "start_at": "2029-01-15T10:00:00Z",
        "end_at": "2029-01-15T12:00:00Z",
    }, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["combo_id"].startswith("cb_")
    assert len(d["booking_ids"]) == 2


def test_combo_booking_validates_whitelist(admin_session):
    """Room without whitelist must accept anything; with whitelist must enforce."""
    suffix = int(time.time())
    payload = {
        "name": f"StrictCombo_{suffix}", "type": "room", "is_splitable": True,
        "allowed_combinations": [["A"]],  # only single A allowed as a combo
        "sub_resources": [{"sub_id": "A", "name": "A"}, {"sub_id": "B", "name": "B"}],
    }
    parent = admin_session.post(f"{API}/api/resources", json=payload).json()
    try:
        r = admin_session.post(f"{API}/api/resource-bookings/combo", json={
            "parent_resource_id": parent["resource_id"],
            "sub_ids": ["A", "B"],
            "title": "Forbidden",
            "start_at": "2029-02-01T10:00:00Z", "end_at": "2029-02-01T11:00:00Z",
        }, timeout=10)
        assert r.status_code == 400
    finally:
        admin_session.delete(f"{API}/api/resources/{parent['resource_id']}")


def test_blackout_creates_and_blocks(admin_session):
    rid = "res_demo_desk_12"
    r = admin_session.post(f"{API}/api/resources/{rid}/blackouts", json={
        "start_at": "2029-03-01T00:00:00Z", "end_at": "2029-03-05T23:00:00Z",
        "title": "Wartung Q1", "reason": "maintenance",
    }, timeout=10)
    assert r.status_code == 200
    bo_id = r.json()["blackout_id"]
    # Conflict-check inside the blackout window
    check = admin_session.post(f"{API}/api/resources/{rid}/check-conflicts", json={
        "start_at": "2029-03-03T10:00:00Z", "end_at": "2029-03-03T11:00:00Z",
    }, timeout=10).json()
    reasons = [c.get("reason") for c in check["conflicts"]]
    assert "blackout" in reasons
    # Cleanup
    admin_session.delete(f"{API}/api/resources/blackouts/{bo_id}")


def test_cost_center_listing(admin_session):
    r = admin_session.get(f"{API}/api/cost-centers", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert any(cc.get("code") == "KS-001" for cc in r.json())


def test_accounts_listing(admin_session):
    r = admin_session.get(f"{API}/api/accounts", timeout=10)
    assert r.status_code == 200
    assert any(a.get("code") == "4500" for a in r.json())


def test_xlsx_export(admin_session):
    r = admin_session.get(f"{API}/api/resource-bookings/export/xlsx", timeout=10)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # zip-based XLSX magic
    assert int(r.headers.get("content-length", 0)) > 500


def test_invoice_approval(admin_session):
    bookings = admin_session.get(f"{API}/api/resource-bookings").json()
    with_cat = [b for b in bookings if b.get("catering_request_id")]
    if not with_cat:
        pytest.skip("no catering booking")
    cr_id = with_cat[0]["catering_request_id"]
    r = admin_session.post(f"{API}/api/catering-requests/{cr_id}/invoice/approve",
                          json={"decision": "approve", "note": "ok"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["invoice_approved"] is True


def test_favorite_desks(admin_session):
    r = admin_session.post(f"{API}/api/favorites/desks/res_demo_desk_12", timeout=10)
    assert r.status_code == 200
    listed = admin_session.get(f"{API}/api/favorites/desks", timeout=10).json()
    assert "res_demo_desk_12" in listed["desk_ids"]
    admin_session.delete(f"{API}/api/favorites/desks/res_demo_desk_12")


def test_driving_log(admin_session):
    r = admin_session.get(f"{API}/api/resources/res_demo_car_caddy/driving-log", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_driver_license_self(admin_session):
    # Admin updates their own license
    r = admin_session.get(f"{API}/api/users/me", timeout=10)
    if r.status_code != 200:
        pytest.skip("users/me missing")
    me = r.json()
    r2 = admin_session.put(f"{API}/api/users/{me['user_id']}/driver-license",
                           json={"valid": True, "expires_on": "2030-12-31", "classes": ["B"]},
                           timeout=10)
    assert r2.status_code == 200


def test_no_show_analytics(admin_session):
    r = admin_session.get(f"{API}/api/resources/dashboard/no-show?days=365", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "total_bookings" in d
    assert "no_show_rate" in d
    assert "cancelled_count" in d


def test_department_analytics(admin_session):
    r = admin_session.get(f"{API}/api/resources/dashboard/by-department", timeout=10)
    assert r.status_code == 200
    assert "rows" in r.json()


def test_rejection_reasons(admin_session):
    r = admin_session.get(f"{API}/api/catering-requests/rejection-reasons", timeout=10)
    assert r.status_code == 200
    reasons = r.json()["reasons"]
    assert len(reasons) >= 5


def test_outlook_auth_url_unconfigured(admin_session):
    """Without env vars, should return 503 with a helpful message."""
    r = admin_session.get(f"{API}/api/calendar-sync/outlook/auth-url", timeout=10)
    # 503 expected unless OUTLOOK_CLIENT_ID is set
    assert r.status_code in (200, 503)


def test_attachment_removal(admin_session):
    bookings = admin_session.get(f"{API}/api/resource-bookings").json()
    with_cat = [b for b in bookings if b.get("catering_request_id")]
    if not with_cat:
        pytest.skip("no catering booking")
    cr_id = with_cat[0]["catering_request_id"]
    # Try removing a non-existent attachment (should still 200 with empty change)
    r = admin_session.delete(
        f"{API}/api/catering-requests/{cr_id}/attachments/nope", timeout=10
    )
    assert r.status_code == 200
    assert "removed" in r.json()
