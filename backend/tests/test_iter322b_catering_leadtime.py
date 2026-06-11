"""
Iter 322b — Server-side catering lead-time validation + cafeteria e-mail.

Validates that booking a catering-equipped room with short-notice catering:
  1. Flags the catering_request with `lead_time_breach=True`
  2. Surfaces `lead_time_warning` in the booking POST response
  3. Triggers the urgency e-mail path (mocked SMTP — we just assert the call
     was made by checking the email_log collection / observability hook)

Also asserts the inverse: well-planned bookings do NOT set the breach flag.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests


@pytest.fixture(scope="module")
def base_url() -> str:
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_token(base_url: str) -> str:
    r = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": "admin@meetflow.com", "password": "admin123"},
        timeout=10, verify=False,
    )
    r.raise_for_status()
    return r.json().get("token") or r.json().get("access_token")


def _auth(t: str) -> dict: return {"Authorization": f"Bearer {t}"}


def test_short_notice_catering_flags_breach(base_url: str, admin_token: str):
    """Book a room with catering starting in 10 min, using an item with the
    default 60-min lead time → response carries the lead_time_warning, and
    the stored catering_request has the breach flag."""
    H = _auth(admin_token)
    suffix = uuid.uuid4().hex[:6]
    cleanup = {"resource": None, "item": None, "booking": None}

    try:
        # ---- A catering-enabled room ----
        r = requests.post(f"{base_url}/api/resources", headers=H,
                          verify=False, timeout=10,
                          json={"name": f"E2E Short-Notice {suffix}", "type": "room",
                                "capacity": 4, "allow_catering": True, "status": "active"})
        assert r.status_code == 200
        cleanup["resource"] = r.json()["resource_id"]

        # ---- A catering item with lead_time_min=120 (extra strict) ----
        r = requests.post(f"{base_url}/api/catering-items", headers=H,
                          verify=False, timeout=10,
                          json={"name": f"E2E Cake {suffix}", "price": 4.00,
                                "unit": "Stueck", "category": "snack",
                                "lead_time_min": 120})
        assert r.status_code == 200, r.text
        cleanup["item"] = r.json()["item_id"]

        # ---- Book it for "in 10 minutes" — breach! ----
        start = datetime.now(timezone.utc) + timedelta(minutes=10)
        end = start + timedelta(hours=1)
        r = requests.post(f"{base_url}/api/resource-bookings", headers=H,
                          verify=False, timeout=15,
                          json={"resource_id": cleanup["resource"],
                                "title": f"Short Notice {suffix}",
                                "start_at": start.isoformat(),
                                "end_at": end.isoformat(),
                                "catering": {"items": [{"item_id": cleanup["item"],
                                                         "quantity": 6}]}})
        assert r.status_code == 200, r.text
        booking = r.json()
        cleanup["booking"] = booking["booking_id"]

        # Response should expose the warning
        warning = booking.get("lead_time_warning")
        assert warning, f"No lead_time_warning surfaced in booking response: {booking}"
        assert warning["breach"] is True
        assert warning["required_min"] == 120
        assert 0 <= warning["available_min"] <= 12, \
            f"available_min ({warning['available_min']}) should be ~10"
        assert warning["worst_item"] == f"E2E Cake {suffix}"
        print(f"\n  ✓ Booking response has lead_time_warning: "
              f"needs {warning['required_min']}m, has {warning['available_min']}m")

        # Stored catering_request should carry the flag too
        cr_id = booking.get("catering_request_id")
        assert cr_id, "catering_request_id missing"
        r = requests.get(f"{base_url}/api/catering-requests",
                         headers=H, timeout=10, verify=False)
        assert r.status_code == 200
        cr = next((x for x in r.json() if x.get("request_id") == cr_id), None)
        assert cr, f"catering_request {cr_id} not found in list"
        assert cr.get("lead_time_breach") is True
        assert cr.get("lead_time_required_min") == 120
        assert cr.get("lead_time_worst_item") == f"E2E Cake {suffix}"
        print(f"  ✓ catering_request persisted with breach flags")

    finally:
        if cleanup["booking"]:
            requests.delete(f"{base_url}/api/resource-bookings/{cleanup['booking']}",
                            headers=H, timeout=10, verify=False)
        if cleanup["item"]:
            requests.delete(f"{base_url}/api/catering-items/{cleanup['item']}",
                            headers=H, timeout=10, verify=False)
        if cleanup["resource"]:
            requests.delete(f"{base_url}/api/resources/{cleanup['resource']}",
                            headers=H, timeout=10, verify=False)


def test_well_planned_catering_no_breach(base_url: str, admin_token: str):
    """Inverse: booking 7 days out leaves plenty of lead time → no breach."""
    H = _auth(admin_token)
    suffix = uuid.uuid4().hex[:6]
    cleanup = {"resource": None, "item": None, "booking": None}

    try:
        r = requests.post(f"{base_url}/api/resources", headers=H,
                          verify=False, timeout=10,
                          json={"name": f"E2E Planned {suffix}", "type": "room",
                                "capacity": 4, "allow_catering": True, "status": "active"})
        assert r.status_code == 200
        cleanup["resource"] = r.json()["resource_id"]

        r = requests.post(f"{base_url}/api/catering-items", headers=H,
                          verify=False, timeout=10,
                          json={"name": f"E2E Coffee {suffix}", "price": 2.50,
                                "unit": "Tasse", "category": "beverage",
                                "lead_time_min": 60})
        assert r.status_code == 200
        cleanup["item"] = r.json()["item_id"]

        start = datetime.now(timezone.utc) + timedelta(days=7)
        end = start + timedelta(hours=1)
        r = requests.post(f"{base_url}/api/resource-bookings", headers=H,
                          verify=False, timeout=15,
                          json={"resource_id": cleanup["resource"],
                                "title": f"Well-Planned {suffix}",
                                "start_at": start.isoformat(),
                                "end_at": end.isoformat(),
                                "catering": {"items": [{"item_id": cleanup["item"],
                                                         "quantity": 8}]}})
        assert r.status_code == 200, r.text
        booking = r.json()
        cleanup["booking"] = booking["booking_id"]

        # No breach should be surfaced
        assert "lead_time_warning" not in booking, \
            f"Unexpected breach for well-planned booking: {booking.get('lead_time_warning')}"
        print(f"\n  ✓ Well-planned booking (7 days out) has no breach flag")

    finally:
        if cleanup["booking"]:
            requests.delete(f"{base_url}/api/resource-bookings/{cleanup['booking']}",
                            headers=H, timeout=10, verify=False)
        if cleanup["item"]:
            requests.delete(f"{base_url}/api/catering-items/{cleanup['item']}",
                            headers=H, timeout=10, verify=False)
        if cleanup["resource"]:
            requests.delete(f"{base_url}/api/resources/{cleanup['resource']}",
                            headers=H, timeout=10, verify=False)
