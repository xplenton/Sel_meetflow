"""Iter 235 — Demo-Seed + Occupancy-Overview backend tests."""
import requests
import pytest
from datetime import datetime, timezone, timedelta


with open("/app/frontend/.env") as f:
    API = next(l.split("=", 1)[1].strip().rstrip("/") for l in f if l.startswith("REACT_APP_BACKEND_URL"))


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/api/auth/login",
                  json={"email": "admin@meetflow.com", "password": "admin123"}, timeout=10)
    assert r.status_code == 200
    yield sess


def test_seed_demo_creates_resources(s):
    r = s.post(f"{API}/api/resources-seed-demo", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    c = data["created"]
    assert c["rooms"] >= 10
    assert c["desks"] >= 10
    assert c["vehicles"] >= 10
    assert c["catering_items"] >= 10
    assert c["cost_centers"] >= 5
    assert c["bookings"] >= 30


def test_seed_demo_idempotent(s):
    """Second call must NOT explode and produce the same counts."""
    r1 = s.post(f"{API}/api/resources-seed-demo", timeout=30)
    r2 = s.post(f"{API}/api/resources-seed-demo", timeout=30)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["created"]["rooms"] == r2.json()["created"]["rooms"]


def test_occupancy_basic(s):
    """After seeding, occupancy returns rooms + bookings inside the window."""
    s.post(f"{API}/api/resources-seed-demo", timeout=30)
    now = datetime.now(timezone.utc)
    params = {
        "from_date": now.isoformat(),
        "to_date": (now + timedelta(days=14)).isoformat(),
        "type": "room",
    }
    r = s.get(f"{API}/api/resource-occupancy", params=params, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert len(data["resources"]) > 0
    # Demo-Buchungen wurden auf Raeumen angelegt
    assert isinstance(data["bookings"], list)
    # alle bookings haben start_at + end_at als string
    for b in data["bookings"][:3]:
        assert isinstance(b["start_at"], str)
        assert b["resource_id"] in [r["resource_id"] for r in data["resources"]]


def test_occupancy_rejects_huge_window(s):
    now = datetime.now(timezone.utc).isoformat()
    far = (datetime.now(timezone.utc) + timedelta(days=200)).isoformat()
    r = s.get(f"{API}/api/resource-occupancy",
              params={"from_date": now, "to_date": far}, timeout=15)
    assert r.status_code == 400


def test_occupancy_filters_by_type(s):
    now = datetime.now(timezone.utc)
    params = {
        "from_date": now.isoformat(),
        "to_date": (now + timedelta(days=7)).isoformat(),
        "type": "vehicle",
    }
    r = s.get(f"{API}/api/resource-occupancy", params=params, timeout=15)
    assert r.status_code == 200
    data = r.json()
    # Alle Top-Level-Ressourcen muessen type=vehicle haben
    for res in data["resources"]:
        if not res.get("parent_resource_id"):
            assert res["type"] == "vehicle"
