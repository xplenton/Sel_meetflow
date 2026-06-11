"""
Sprint 3 backend tests: approvals badge, dashboard, billing/invoice.
"""
import requests
import pytest


API = None
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                API = line.split("=", 1)[1].strip().rstrip("/")
                break
except FileNotFoundError:
    pass


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/api/auth/login",
               json={"email": "admin@meetflow.com", "password": "admin123"},
               timeout=10)
    assert r.status_code == 200
    yield s


def test_approvals_pending_count(admin_session):
    r = admin_session.get(f"{API}/api/resource-bookings/approvals/pending-count", timeout=10)
    assert r.status_code == 200
    assert "count" in r.json()


def test_dashboard_overview(admin_session):
    r = admin_session.get(f"{API}/api/resources/dashboard/overview?days=90", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "resources_by_type" in d
    assert "bookings_by_status" in d
    assert "top_resources" in d
    assert "catering" in d
    assert d["window_days"] == 90


def test_invoice_for_catering_booking(admin_session):
    # Find a booking that has a catering_request_id (created in earlier tests)
    bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
    with_cat = [b for b in bookings if b.get("catering_request_id")]
    if not with_cat:
        pytest.skip("no catering booking in this run")
    bk = with_cat[0]
    r = admin_session.get(f"{API}/api/resource-bookings/{bk['booking_id']}/invoice", timeout=10)
    assert r.status_code == 200
    inv = r.json()
    assert inv["booking_id"] == bk["booking_id"]
    assert isinstance(inv["lines"], list)
    assert "total" in inv
    assert inv["currency"] == "EUR"


def test_invoice_404_unknown(admin_session):
    r = admin_session.get(f"{API}/api/resource-bookings/bk_does_not_exist/invoice", timeout=10)
    assert r.status_code == 404
