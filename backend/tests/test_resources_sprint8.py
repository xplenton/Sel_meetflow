"""
Sprint 8 (iter 231) — Booking UX helper endpoints:
  POST /resources/{id}/suggest-slots  — naechste freie Slots berechnen
  GET  /resource-availability-snapshot — Now-Free / Busy-Until pro Resource
"""
import time
import requests
import pytest
from datetime import datetime, timedelta, timezone


with open("/app/frontend/.env") as f:
    API = next(
        line.split("=", 1)[1].strip().rstrip("/")
        for line in f
        if line.startswith("REACT_APP_BACKEND_URL")
    )


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/api/auth/login",
                  json={"email": "admin@meetflow.com", "password": "admin123"}, timeout=10)
    assert r.status_code == 200
    yield sess


def test_suggest_slots_empty_schedule(s):
    # Frische Ressource ohne Buchungen
    res = s.post(f"{API}/api/resources",
                 json={"name": f"SugRoom_{int(time.time())}", "type": "room"},
                 timeout=10).json()
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0).isoformat()
    r = s.post(f"{API}/api/resources/{res['resource_id']}/suggest-slots",
               json={"start_at": start, "duration_min": 60, "count": 3},
               timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert len(data["suggestions"]) == 3
    assert data["duration_min"] == 60
    # Erste Suggestion muss am gewuenschten Startzeitpunkt liegen
    assert data["suggestions"][0]["start_at"].startswith(start[:13])
    s.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)


def test_suggest_slots_skips_conflicts(s):
    """Nach einer Buchung muss der Vorschlag den belegten Bereich ueberspringen."""
    res = s.post(f"{API}/api/resources",
                 json={"name": f"SugRoom2_{int(time.time())}", "type": "room"},
                 timeout=10).json()
    # Buchung von 10:00–11:00 am morgigen Tag
    base = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0)
    bk = s.post(f"{API}/api/resource-bookings", json={
        "resource_id": res["resource_id"],
        "title": "Bestehende Buchung",
        "start_at": base.isoformat(),
        "end_at": (base + timedelta(hours=1)).isoformat(),
    }, timeout=10)
    assert bk.status_code == 200, bk.text

    # Suche ab 10:00 — der erste Vorschlag darf NICHT 10:00 sein
    r = s.post(f"{API}/api/resources/{res['resource_id']}/suggest-slots",
               json={"start_at": base.isoformat(), "duration_min": 60, "count": 3},
               timeout=10)
    assert r.status_code == 200
    sugs = r.json()["suggestions"]
    assert len(sugs) >= 1
    first = sugs[0]["start_at"]
    # Muss ab 11:00 oder spaeter sein
    assert first >= (base + timedelta(hours=1)).isoformat()

    # Cleanup
    s.delete(f"{API}/api/resource-bookings/{bk.json()['booking_id']}", timeout=10)
    s.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)


def test_suggest_slots_rejects_bad_duration(s):
    r = s.post(f"{API}/api/resources/anything/suggest-slots",
               json={"start_at": "2026-01-01T09:00:00Z", "duration_min": 2},
               timeout=10)
    assert r.status_code == 400


def test_availability_snapshot_basic(s):
    """Snapshot-Endpoint liefert immer ein dict mit 'snapshot'-key."""
    r = s.get(f"{API}/api/resource-availability-snapshot", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "snapshot" in data
    assert isinstance(data["snapshot"], dict)


def test_availability_snapshot_marks_busy(s):
    """Nach einer Buchung jetzt+30min muss next_busy gefuellt sein."""
    res = s.post(f"{API}/api/resources",
                 json={"name": f"SnapRoom_{int(time.time())}", "type": "room"},
                 timeout=10).json()
    in30 = datetime.now(timezone.utc) + timedelta(minutes=30)
    bk = s.post(f"{API}/api/resource-bookings", json={
        "resource_id": res["resource_id"],
        "title": "Soon",
        "start_at": in30.isoformat(),
        "end_at": (in30 + timedelta(hours=1)).isoformat(),
    }, timeout=10)
    assert bk.status_code == 200

    r = s.get(f"{API}/api/resource-availability-snapshot", timeout=10)
    assert r.status_code == 200
    snap = r.json()["snapshot"]
    assert res["resource_id"] in snap
    entry = snap[res["resource_id"]]
    assert entry["next_busy"] is not None or entry["busy_now"]

    s.delete(f"{API}/api/resource-bookings/{bk.json()['booking_id']}", timeout=10)
    s.delete(f"{API}/api/resources/{res['resource_id']}", timeout=10)
