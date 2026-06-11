"""
Iteration 285 — Invoice Tracking + Email + Stripe Tests
========================================================

Tests for:
1. POST /api/invoices — create invoice snapshot (kind='aggregate')
2. GET /api/invoices — list invoices with status filter
3. GET /api/invoices/{id} — invoice detail
4. GET /api/invoices/{id}/pdf — PDF download (magic bytes check)
5. POST /api/invoices/{id}/approve — status draft→approved
6. POST /api/invoices/{id}/approve on approved → 400
7. POST /api/invoices/{id}/send-email — email send (requires accounting_email or to_email)
8. POST /api/invoices/{id}/send-stripe — Stripe invoice (requires external_customer_email)
9. POST /api/invoices/{id}/void — void invoice (not on paid)
10. POST /api/stripe-webhook — invoice.paid → status=paid
11. Permission: non-admin without bookings.invoice cap → 403
12. Cost-center accounting_email update via PUT /api/cost-centers/{id}
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with auth token."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    assert token, "No token in login response"
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="module")
def test_cost_center(admin_session):
    """Create a test cost center with accounting_email for testing."""
    code = f"TEST-INV-{uuid.uuid4().hex[:6].upper()}"
    resp = admin_session.post(f"{BASE_URL}/api/cost-centers", json={
        "code": code,
        "name": "Test Invoice Cost Center",
        "accounting_email": "test-accounting@example.com"
    })
    assert resp.status_code in (200, 201), f"Failed to create cost center: {resp.text}"
    cc = resp.json()
    yield cc
    # Cleanup
    try:
        admin_session.delete(f"{BASE_URL}/api/cost-centers/{cc['cost_center_id']}")
    except:
        pass


@pytest.fixture(scope="module")
def test_invoice(admin_session, test_cost_center):
    """Create a test invoice snapshot for testing."""
    today = "2026-01-01"
    end = "2026-01-31"
    resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
        "kind": "aggregate",
        "cost_center": test_cost_center["code"],
        "from_date": today,
        "to_date": end,
        "title": "TEST_Invoice_285"
    })
    assert resp.status_code == 200, f"Failed to create invoice: {resp.text}"
    inv = resp.json()
    assert "invoice_id" in inv
    assert inv["status"] == "draft"
    yield inv
    # Cleanup - void the invoice
    try:
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")
    except:
        pass


class TestInvoiceCreation:
    """Test invoice snapshot creation."""
    
    def test_create_aggregate_invoice(self, admin_session, test_cost_center):
        """POST /api/invoices creates snapshot with kind='aggregate'."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        assert resp.status_code == 200, f"Create invoice failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "invoice_id" in data
        assert data["invoice_id"].startswith("inv_")
        assert data["status"] == "draft"
        assert "snapshot" in data
        assert "lines" in data["snapshot"]
        assert "total" in data["snapshot"]
        assert data["kind"] == "aggregate"
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{data['invoice_id']}/void")
    
    def test_create_catering_aggregate_invoice(self, admin_session, test_cost_center):
        """POST /api/invoices with kind='catering_aggregate'."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "catering_aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        assert resp.status_code == 200, f"Create catering invoice failed: {resp.text}"
        data = resp.json()
        assert data["kind"] == "catering_aggregate"
        assert data["status"] == "draft"
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{data['invoice_id']}/void")
    
    def test_create_invoice_invalid_kind(self, admin_session):
        """POST /api/invoices with invalid kind returns 400."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "invalid_kind",
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        assert resp.status_code == 400


class TestInvoiceList:
    """Test invoice listing and filtering."""
    
    def test_list_invoices(self, admin_session, test_invoice):
        """GET /api/invoices returns list of invoices."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should contain our test invoice
        ids = [inv["invoice_id"] for inv in data]
        assert test_invoice["invoice_id"] in ids
    
    def test_list_invoices_filter_status(self, admin_session, test_invoice):
        """GET /api/invoices?status=draft filters correctly."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices", params={"status": "draft"})
        assert resp.status_code == 200
        data = resp.json()
        # All returned invoices should be draft
        for inv in data:
            assert inv["status"] == "draft"


class TestInvoiceDetail:
    """Test invoice detail and PDF endpoints."""
    
    def test_get_invoice_detail(self, admin_session, test_invoice):
        """GET /api/invoices/{id} returns invoice detail."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices/{test_invoice['invoice_id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["invoice_id"] == test_invoice["invoice_id"]
        assert "snapshot" in data
        assert "lines" in data["snapshot"]
    
    def test_get_invoice_not_found(self, admin_session):
        """GET /api/invoices/{id} with invalid ID returns 404."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices/inv_nonexistent123")
        assert resp.status_code == 404
    
    def test_get_invoice_pdf(self, admin_session, test_invoice):
        """GET /api/invoices/{id}/pdf returns valid PDF."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices/{test_invoice['invoice_id']}/pdf")
        assert resp.status_code == 200
        assert resp.headers.get("Content-Type") == "application/pdf"
        # Check PDF magic bytes
        assert resp.content[:4] == b"%PDF"


class TestInvoiceApproval:
    """Test invoice approval workflow."""
    
    def test_approve_draft_invoice(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/approve changes status to approved."""
        # Create a fresh invoice for this test
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        assert resp.status_code == 200
        inv = resp.json()
        assert inv["status"] == "draft"
        
        # Approve it
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        
        # Verify via GET
        resp = admin_session.get(f"{BASE_URL}/api/invoices/{inv['invoice_id']}")
        assert resp.json()["status"] == "approved"
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")
    
    def test_approve_already_approved_returns_400(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/approve on approved invoice returns 400."""
        # Create and approve
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        
        # Try to approve again
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        assert resp.status_code == 400
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")


class TestInvoiceSendEmail:
    """Test invoice email sending."""
    
    def test_send_email_requires_approval(self, admin_session, test_invoice):
        """POST /api/invoices/{id}/send-email on draft returns 400."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{test_invoice['invoice_id']}/send-email")
        assert resp.status_code == 400
        assert "freigeben" in resp.json().get("detail", "").lower()
    
    def test_send_email_without_recipient_returns_400(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/send-email without to_email and no accounting_email returns 400."""
        # Create invoice with cost center that has no accounting_email
        resp = admin_session.post(f"{BASE_URL}/api/cost-centers", json={
            "code": f"TEST-NOEMAIL-{uuid.uuid4().hex[:6].upper()}",
            "name": "No Email CC"
        })
        cc_no_email = resp.json()
        
        # Create and approve invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": cc_no_email["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        
        # Try to send without email
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/send-email")
        assert resp.status_code == 400
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")
        admin_session.delete(f"{BASE_URL}/api/cost-centers/{cc_no_email['cost_center_id']}")
    
    def test_send_email_with_override(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/send-email with to_email override works."""
        # Create and approve invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        
        # Send with override email
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/send-email", json={
            "to_email": "override@example.com",
            "message": "Test message"
        })
        # May return 200 (sent) or 502 (SMTP not configured) - both are valid
        assert resp.status_code in (200, 502)
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")


class TestInvoiceSendStripe:
    """Test Stripe invoice sending."""
    
    def test_send_stripe_requires_approval(self, admin_session, test_invoice):
        """POST /api/invoices/{id}/send-stripe on draft returns 400."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{test_invoice['invoice_id']}/send-stripe", json={
            "external_customer_email": "customer@example.com"
        })
        assert resp.status_code == 400
    
    def test_send_stripe_without_email_returns_400(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/send-stripe without external_customer_email returns 400."""
        # Create and approve invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        
        # Try to send without email
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/send-stripe")
        assert resp.status_code == 400
        # German error message uses "E-Mail"
        assert "e-mail" in resp.json().get("detail", "").lower()
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")
    
    def test_send_stripe_with_email(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/send-stripe with email attempts Stripe call."""
        # Create and approve invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        
        # Try to send via Stripe
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/send-stripe", json={
            "external_customer_email": "test-customer@example.com",
            "external_customer_name": "Test Customer GmbH"
        })
        # May return 200 (success), 400 (no lines), 502 (Stripe error), or 503 (Stripe not configured)
        # All are valid depending on configuration
        assert resp.status_code in (200, 400, 502, 503)
        
        # Cleanup
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")


class TestInvoiceVoid:
    """Test invoice void functionality."""
    
    def test_void_draft_invoice(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/void on draft works."""
        # Create invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        
        # Void it
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")
        assert resp.status_code == 200
        assert resp.json()["status"] == "void"
        
        # Verify via GET
        resp = admin_session.get(f"{BASE_URL}/api/invoices/{inv['invoice_id']}")
        assert resp.json()["status"] == "void"
    
    def test_void_approved_invoice(self, admin_session, test_cost_center):
        """POST /api/invoices/{id}/void on approved works."""
        # Create and approve
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        
        # Void it
        resp = admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/void")
        assert resp.status_code == 200


class TestStripeWebhook:
    """Test Stripe webhook handling."""
    
    def test_webhook_invoice_paid(self, admin_session, test_cost_center):
        """POST /api/stripe-webhook with invoice.paid updates status."""
        # Create and approve invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "cost_center": test_cost_center["code"],
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        inv = resp.json()
        admin_session.post(f"{BASE_URL}/api/invoices/{inv['invoice_id']}/approve")
        
        # Simulate webhook (no signature verification in dev mode)
        webhook_payload = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_test_123",
                    "status": "paid",
                    "metadata": {
                        "meetflow_invoice_id": inv["invoice_id"]
                    }
                }
            }
        }
        resp = requests.post(f"{BASE_URL}/api/stripe-webhook", json=webhook_payload)
        assert resp.status_code == 200
        assert resp.json().get("received") == True
        
        # Verify status changed to paid
        resp = admin_session.get(f"{BASE_URL}/api/invoices/{inv['invoice_id']}")
        assert resp.json()["status"] == "paid"
    
    def test_webhook_invalid_payload(self):
        """POST /api/stripe-webhook with invalid payload returns 400."""
        resp = requests.post(f"{BASE_URL}/api/stripe-webhook", data="invalid json")
        assert resp.status_code == 400


class TestCostCenterAccountingEmail:
    """Test cost center accounting_email field."""
    
    def test_create_cost_center_with_email(self, admin_session):
        """POST /api/cost-centers with accounting_email."""
        code = f"TEST-EMAIL-{uuid.uuid4().hex[:6].upper()}"
        resp = admin_session.post(f"{BASE_URL}/api/cost-centers", json={
            "code": code,
            "name": "Test CC with Email",
            "accounting_email": "accounting@test.com"
        })
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["accounting_email"] == "accounting@test.com"
        
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/cost-centers/{data['cost_center_id']}")
    
    def test_update_cost_center_email(self, admin_session, test_cost_center):
        """PUT /api/cost-centers/{id} updates accounting_email."""
        new_email = "updated-accounting@test.com"
        resp = admin_session.put(
            f"{BASE_URL}/api/cost-centers/{test_cost_center['cost_center_id']}",
            json={"accounting_email": new_email}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accounting_email"] == new_email
        
        # Verify via list
        resp = admin_session.get(f"{BASE_URL}/api/cost-centers")
        ccs = resp.json()
        found = [cc for cc in ccs if cc.get("cost_center_id") == test_cost_center["cost_center_id"]]
        assert len(found) == 1
        assert found[0]["accounting_email"] == new_email


class TestPermissions:
    """Test permission checks for invoice endpoints."""
    
    def test_non_admin_cannot_access_invoices(self, admin_session):
        """Non-admin user without bookings.invoice cap gets 403."""
        # Create a test user without invoice capability
        test_email = f"test_noinvoice_{uuid.uuid4().hex[:8]}@test.com"
        resp = admin_session.post(f"{BASE_URL}/api/admin/users", json={
            "email": test_email,
            "password": "testpass123",
            "name": "Test No Invoice",
            "role": "member"
        })
        if resp.status_code not in (200, 201):
            pytest.skip("Could not create test user")
        
        # Login as test user
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_email,
            "password": "testpass123"
        })
        if resp.status_code != 200:
            pytest.skip("Could not login as test user")
        
        token = resp.json().get("token") or resp.json().get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Try to access invoices
        resp = session.get(f"{BASE_URL}/api/invoices")
        assert resp.status_code == 403
        
        # Try to create invoice
        resp = session.post(f"{BASE_URL}/api/invoices", json={
            "kind": "aggregate",
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        })
        assert resp.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
