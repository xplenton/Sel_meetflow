"""Iter 189 — backend pytest for the 5-bug-fix sweep:
  * Schedule-poll wrong-password surfaces `wrong_password` flag
  * Booking page accepts + persists `booking_until` and `max_advance_days`
  * /book/<u>/<slug>/info exposes those limits
  * Booking-slot endpoint blocks dates outside the horizon
  * Booking POST rejects out-of-horizon dates server-side
  * Calendar /events includes confirmed schedule-polls without auto-meeting
"""
import os
import requests
import uuid
import pytest


def _api():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/") + "/api"
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/") + "/api"
    return "http://localhost:8001/api"


API = _api()
ADMIN = ("admin@meetflow.com", "admin123")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=10)
    body = r.json()
    if body.get("totp_required"):
        pytest.skip("Admin has 2FA enabled — please disable for this test run.")
    return body["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


# ============ #3 Wrong password ============

def test_schedule_poll_wrong_password_surfaces_flag(admin_token):
    poll = requests.post(
        f"{API}/schedule-polls", headers=_h(admin_token),
        json={
            "title": f"PW Test {uuid.uuid4().hex[:6]}",
            "time_slots": [{"date": "2026-12-30", "start_time": "10:00", "end_time": "11:00"}],
            "is_private": True, "password": "secret123",
        },
        timeout=10,
    ).json()
    share = poll["share_token"]
    pid = poll["poll_id"]

    # 1) No password supplied → requires_password=true, wrong_password=false
    r = requests.get(f"{API}/schedule-polls/public/{share}", timeout=10).json()
    assert r["requires_password"] is True
    assert r["wrong_password"] is False

    # 2) Wrong password → requires_password=true, wrong_password=TRUE
    r = requests.get(f"{API}/schedule-polls/public/{share}?pwd=nope", timeout=10).json()
    assert r["requires_password"] is True
    assert r["wrong_password"] is True

    # 3) Correct password → poll details
    r = requests.get(f"{API}/schedule-polls/public/{share}?pwd=secret123", timeout=10).json()
    assert "time_slots" in r
    assert "password_hash" not in r

    # cleanup
    requests.delete(f"{API}/schedule-polls/{pid}", headers=_h(admin_token), timeout=10)


# ============ #4 Booking horizon ============

def test_booking_page_persists_horizon_limits(admin_token):
    me = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=10).json()
    uid = me["user_id"]
    slug = f"horiz-{uuid.uuid4().hex[:6]}"
    page = requests.post(
        f"{API}/booking/pages", headers=_h(admin_token),
        json={"slug": slug, "title": "Horizon", "booking_until": "2027-06-30", "max_advance_days": 14},
        timeout=10,
    ).json()
    assert page["booking_until"] == "2027-06-30"
    assert page["max_advance_days"] == 14

    # /book/<user>/<slug>/info must expose them (uses user_id as identifier)
    info = requests.get(f"{API}/book/{uid}/{slug}/info", timeout=10).json()
    assert info["booking_until"] == "2027-06-30"
    assert info["max_advance_days"] == 14

    # /book/<user>/<slug>/slots far in future → blocked_reason
    far = requests.get(f"{API}/book/{uid}/{slug}/slots?date=2030-01-01", timeout=10).json()
    assert far["blocked_reason"] in ("booking_window_ended", "too_far_ahead")

    # POST a far-future booking → 400
    r = requests.post(
        f"{API}/book/{uid}/{slug}",
        json={"date": "2030-01-01", "start_time": "10:00", "guest_name": "Test"},
        timeout=10,
    )
    assert r.status_code == 400, f"Got {r.status_code}: {r.text}"

    # cleanup
    requests.delete(f"{API}/booking/pages/{page['page_id']}", headers=_h(admin_token), timeout=10)


# ============ #5 Calendar shows schedule-polls ============

def test_calendar_includes_confirmed_schedule_poll_without_meeting(admin_token):
    title = f"CalPoll iter189 {uuid.uuid4().hex[:6]}"
    poll = requests.post(
        f"{API}/schedule-polls", headers=_h(admin_token),
        json={
            "title": title,
            "time_slots": [{"date": "2026-11-15", "start_time": "10:00", "end_time": "11:30"}],
            "create_meeting_on_confirm": False,
            "is_private": False,
        }, timeout=10,
    ).json()
    pid = poll["poll_id"]

    detail = requests.get(f"{API}/schedule-polls/{pid}", headers=_h(admin_token), timeout=10).json()
    slot_id = detail["time_slots"][0]["slot_id"]

    confirm = requests.post(
        f"{API}/schedule-polls/{pid}/confirm", headers=_h(admin_token),
        json={"slot_id": slot_id}, timeout=10,
    ).json()
    # No auto-meeting created
    assert "meeting_id" not in confirm or confirm.get("meeting_id") is None

    # /calendar/events must surface this poll
    events = requests.get(f"{API}/calendar/events", headers=_h(admin_token), timeout=10).json()
    found = [e for e in events if e.get("title") == title]
    assert len(found) == 1, f"Confirmed schedule-poll missing from calendar (got {len(found)})"
    e = found[0]
    assert e["meeting_type"] == "schedule_poll"
    assert e["no_room"] is True
    assert e["my_role"] == "host"
    assert e["scheduled_at"].startswith("2026-11-15")

    requests.delete(f"{API}/schedule-polls/{pid}", headers=_h(admin_token), timeout=10)


def test_calendar_with_auto_meeting_does_not_duplicate(admin_token):
    """When create_meeting_on_confirm=true, we get a real meeting → calendar
    shows the meeting but NOT a duplicate schedule_poll entry."""
    title = f"CalPollAuto iter189 {uuid.uuid4().hex[:6]}"
    poll = requests.post(
        f"{API}/schedule-polls", headers=_h(admin_token),
        json={
            "title": title,
            "time_slots": [{"date": "2026-11-16", "start_time": "12:00", "end_time": "13:00"}],
            "create_meeting_on_confirm": True,
            "is_private": False,
        }, timeout=10,
    ).json()
    pid = poll["poll_id"]
    detail = requests.get(f"{API}/schedule-polls/{pid}", headers=_h(admin_token), timeout=10).json()
    slot_id = detail["time_slots"][0]["slot_id"]
    confirm = requests.post(
        f"{API}/schedule-polls/{pid}/confirm", headers=_h(admin_token),
        json={"slot_id": slot_id}, timeout=10,
    ).json()
    assert confirm.get("meeting_id"), "auto-meeting expected"

    events = requests.get(f"{API}/calendar/events", headers=_h(admin_token), timeout=10).json()
    matches = [e for e in events if e.get("title") == title]
    # Exactly ONE entry — not duplicated
    assert len(matches) == 1, f"Expected 1 match, got {len(matches)}"
    assert matches[0]["meeting_type"] != "schedule_poll", "should be the meeting, not the poll"

    # cleanup
    requests.delete(f"{API}/schedule-polls/{pid}", headers=_h(admin_token), timeout=10)
    requests.delete(f"{API}/meetings/{confirm['meeting_id']}", headers=_h(admin_token), timeout=10)
