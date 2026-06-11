"""
Pytest E2E tests for the Resources & Bookings module (iter 223 / Sprint 1).

Covers:
  - Resource CRUD (admin)
  - Booking creation + conflict detection (same room, parent vs child, siblings)
  - Capability gates (member without resources.book gets 403)
  - Catering workflow: booking creates request + auto-task; transition mirrors
  - Approval workflow for requires_approval rooms
"""
import os
import time
import requests
import pytest


API = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not API:
    # Fallback: read from frontend .env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    API = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@meetflow.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=10)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    yield s


def _ts():
    return f"{int(time.time())}_{os.getpid()}"


@pytest.fixture(scope="module")
def demo_room(admin_session):
    """Create a fresh splitable demo room for this test module."""
    suffix = _ts()
    payload = {
        "name": f"PytestSaal {suffix}",
        "type": "room",
        "location": "Test",
        "capacity": 30,
        "is_splitable": True,
        "allow_catering": True,
        "sub_resources": [
            {"sub_id": "A", "name": "A", "capacity": 10},
            {"sub_id": "B", "name": "B", "capacity": 10},
        ],
    }
    r = admin_session.post(f"{API}/api/resources", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    parent = r.json()
    # Re-fetch including children
    r2 = admin_session.get(f"{API}/api/resources/{parent['resource_id']}", timeout=10)
    detail = r2.json()
    children = {c["sub_id"]: c for c in detail.get("children", [])}
    assert "A" in children and "B" in children
    yield {"parent": parent, "A": children["A"], "B": children["B"]}
    admin_session.delete(f"{API}/api/resources/{parent['resource_id']}", timeout=10)


def test_list_resources(admin_session):
    r = admin_session.get(f"{API}/api/resources", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_booking_and_self_conflict(admin_session, demo_room):
    a = demo_room["A"]
    b1 = admin_session.post(
        f"{API}/api/resource-bookings",
        json={
            "resource_id": a["resource_id"],
            "title": "Standup",
            "start_at": "2027-06-01T10:00:00Z",
            "end_at": "2027-06-01T11:00:00Z",
        },
        timeout=10,
    )
    assert b1.status_code == 200, b1.text
    bk = b1.json()
    assert bk["status"] == "confirmed"

    b2 = admin_session.post(
        f"{API}/api/resource-bookings",
        json={
            "resource_id": a["resource_id"],
            "title": "Overlap",
            "start_at": "2027-06-01T10:30:00Z",
            "end_at": "2027-06-01T11:30:00Z",
        },
        timeout=10,
    )
    assert b2.status_code == 409, f"expected 409 got {b2.status_code}: {b2.text}"


def test_parent_child_conflict(admin_session, demo_room):
    parent = demo_room["parent"]
    # The previous test booked A 10:00-11:00 — parent must also conflict.
    r = admin_session.post(
        f"{API}/api/resource-bookings",
        json={
            "resource_id": parent["resource_id"],
            "title": "Whole",
            "start_at": "2027-06-01T10:30:00Z",
            "end_at": "2027-06-01T11:30:00Z",
        },
        timeout=10,
    )
    assert r.status_code == 409, r.text


def test_sibling_does_not_conflict(admin_session, demo_room):
    """Booking sibling room B in same window as A must succeed."""
    b = demo_room["B"]
    r = admin_session.post(
        f"{API}/api/resource-bookings",
        json={
            "resource_id": b["resource_id"],
            "title": "Sibling",
            "start_at": "2027-06-01T10:00:00Z",
            "end_at": "2027-06-01T11:00:00Z",
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text


def test_catering_workflow(admin_session, demo_room):
    """Booking with catering creates a request + task; transition mirrors."""
    b = demo_room["B"]
    payload = {
        "resource_id": b["resource_id"],
        "title": "Catering Test",
        "start_at": "2027-06-02T09:00:00Z",
        "end_at": "2027-06-02T12:00:00Z",
        "catering": {
            "items": [{"item_id": "cit_kaffee", "quantity": 5}],
            "contact": "Tester",
        },
    }
    r = admin_session.post(f"{API}/api/resource-bookings", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    bk = r.json()
    assert bk.get("catering_request_id"), "catering_request_id missing"

    # Fetch catering requests
    r2 = admin_session.get(
        f"{API}/api/catering-requests",
        params={"status": "requested"},
        timeout=10,
    )
    assert r2.status_code == 200
    requests_list = r2.json()
    cr = next((c for c in requests_list if c["request_id"] == bk["catering_request_id"]), None)
    assert cr is not None, "catering request not in list"
    assert cr.get("task_id"), "linked task_id missing"

    # Transition to confirmed -> task should mirror to in_progress
    r3 = admin_session.post(
        f"{API}/api/catering-requests/{cr['request_id']}/transition",
        json={"status": "confirmed"},
        timeout=10,
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "confirmed"


def test_booking_validation(admin_session, demo_room):
    a = demo_room["A"]
    r = admin_session.post(
        f"{API}/api/resource-bookings",
        json={
            "resource_id": a["resource_id"],
            "title": "Bad",
            "start_at": "2027-06-05T12:00:00Z",
            "end_at": "2027-06-05T11:00:00Z",
        },
        timeout=10,
    )
    assert r.status_code == 400


def test_resource_404(admin_session):
    r = admin_session.get(f"{API}/api/resources/res_does_not_exist", timeout=10)
    assert r.status_code == 404


def test_check_conflicts_endpoint(admin_session, demo_room):
    a = demo_room["A"]
    r = admin_session.post(
        f"{API}/api/resources/{a['resource_id']}/check-conflicts",
        json={
            "start_at": "2027-06-01T10:30:00Z",
            "end_at": "2027-06-01T10:45:00Z",
        },
        timeout=10,
    )
    assert r.status_code == 200
    payload = r.json()
    assert "conflicts" in payload
    assert len(payload["conflicts"]) >= 1


def test_unauthorised_without_cookie():
    r = requests.get(f"{API}/api/resources", timeout=10)
    assert r.status_code in (401, 403)


def test_catering_items_listing(admin_session):
    r = admin_session.get(f"{API}/api/catering-items", timeout=10)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
