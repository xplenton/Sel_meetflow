"""
Sprint 5 backend tests (iter 227): PDF invoices, Sammelrechnung, floor-plan,
e-mail templates.
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


def test_pdf_invoice(admin_session):
    bookings = admin_session.get(f"{API}/api/resource-bookings", timeout=10).json()
    with_cat = [b for b in bookings if b.get("catering_request_id")]
    if not with_cat:
        pytest.skip("no catering booking")
    bk = with_cat[0]
    r = admin_session.get(f"{API}/api/resource-bookings/{bk['booking_id']}/invoice.pdf", timeout=15)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF", "not a valid PDF"
    assert int(r.headers.get("content-length", 0)) > 500
    assert "attachment" in r.headers.get("content-disposition", "")


def test_aggregate_invoice_json(admin_session):
    r = admin_session.get(f"{API}/api/catering-requests/invoices/aggregate", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "lines" in d
    assert "total" in d
    assert "currency" in d
    assert d["currency"] == "EUR"
    # Each line carries the required keys
    for ln in d["lines"]:
        assert "label" in ln
        assert "quantity" in ln
        assert "subtotal" in ln


def test_aggregate_invoice_pdf(admin_session):
    r = admin_session.get(f"{API}/api/catering-requests/invoices/aggregate.pdf", timeout=15)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert "sammelrechnung" in r.headers.get("content-disposition", "").lower()


def test_aggregate_filtered_by_cost_center(admin_session):
    r = admin_session.get(
        f"{API}/api/catering-requests/invoices/aggregate?cost_center=KS-001",
        timeout=10,
    )
    assert r.status_code == 200
    d = r.json()
    assert d["cost_center"] == "KS-001"


def test_floorplan_position(admin_session):
    r = admin_session.put(f"{API}/api/resources/res_demo_desk_12/floorplan",
                          json={"x": 0.42, "y": 0.55, "width": 0.06, "height": 0.06,
                                "floor_plan_id": "test_plan"},
                          timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["x"] == 0.42
    assert d["floor_plan_id"] == "test_plan"


def test_floorplan_position_validation(admin_session):
    r = admin_session.put(f"{API}/api/resources/res_demo_desk_12/floorplan",
                          json={"x": 1.5}, timeout=10)
    assert r.status_code == 400


def test_floorplan_desks_listing(admin_session):
    r = admin_session.get(f"{API}/api/floorplans/test_plan/desks", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["floor_plan_id"] == "test_plan"
    assert "desks" in d
    # Each desk has `is_busy` flag injected
    for desk in d["desks"]:
        assert "is_busy" in desk


def test_email_templates_module_loads():
    from services.email_templates import render_email, render_kv_list
    html = render_email(
        title="Test", body_html="<p>hi</p>",
        cta_label="OK", cta_url="https://example.com",
    )
    assert "<table" in html and "MeetFlow" in html
    assert "OK" in html and "https://example.com" in html
    kv = render_kv_list([("Foo", "Bar"), ("Skip", None)])
    assert "Foo" in kv and "Bar" in kv
    assert "Skip" not in kv  # None values must be filtered out
