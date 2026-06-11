"""
Sprint 4 consolidation test: verify built-in presets carry the new
resource capabilities so customers can roll-out the booking module without
manual cap-fiddling.
"""
import requests
import pytest


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


def _preset_map(admin_session):
    presets = admin_session.get(f"{API}/api/admin/presets", timeout=10).json()["presets"]
    return {p["preset_id"]: p for p in presets}


def test_new_specialist_presets_exist(admin_session):
    """Three new builtin presets should be available: catering_lead, fleet_manager, facility_manager."""
    presets = _preset_map(admin_session)
    for pid in ("catering_lead", "fleet_manager", "facility_manager"):
        assert pid in presets, f"Built-in preset missing: {pid}"
        assert presets[pid].get("builtin") is True


def test_nursing_lead_can_book(admin_session):
    p = _preset_map(admin_session)["nursing_lead"]
    caps = set(p["capabilities"])
    assert {"view:resources", "resources.book", "resources.book_for_others"}.issubset(caps)


def test_department_head_can_approve_and_invoice(admin_session):
    p = _preset_map(admin_session)["department_head"]
    caps = set(p["capabilities"])
    assert {"view:resources", "resources.approve",
            "resources.view_all_bookings", "bookings.invoice"}.issubset(caps)


def test_catering_lead_processes_catering(admin_session):
    p = _preset_map(admin_session)["catering_lead"]
    caps = set(p["capabilities"])
    assert {"catering.process", "catering.manage_items"}.issubset(caps)


def test_fleet_manager_manages_vehicles(admin_session):
    p = _preset_map(admin_session)["fleet_manager"]
    caps = set(p["capabilities"])
    assert {"resources.manage", "resources.approve",
            "resources.view_all_bookings", "bookings.invoice"}.issubset(caps)


def test_facility_manager_manages_rooms(admin_session):
    p = _preset_map(admin_session)["facility_manager"]
    caps = set(p["capabilities"])
    assert {"resources.manage", "catering.manage_items"}.issubset(caps)


def test_analytics_viewer_sees_resource_analytics(admin_session):
    p = _preset_map(admin_session)["analytics_viewer"]
    caps = set(p["capabilities"])
    assert "view:resources" in caps
    assert "resources.view_all_bookings" in caps


def test_catering_lead_full_cap_set(admin_session):
    """catering_lead must give a one-click solution for the Catering team."""
    p = _preset_map(admin_session)["catering_lead"]
    caps = set(p["capabilities"])
    # Can see the module + book themselves
    assert "view:resources" in caps
    assert "resources.book" in caps
    # Manages items + processes requests
    assert "catering.manage_items" in caps
    assert "catering.process" in caps
    # Sees their assigned tasks
    assert "view:tasks" in caps


def test_fleet_manager_full_cap_set(admin_session):
    p = _preset_map(admin_session)["fleet_manager"]
    caps = set(p["capabilities"])
    expected = {"view:resources", "resources.book", "resources.book_for_others",
                "resources.manage", "resources.approve",
                "resources.view_all_bookings", "bookings.invoice"}
    assert expected.issubset(caps), f"missing: {expected - caps}"
