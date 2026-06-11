"""
Iteration 284 — Billing/Rechnungen Integration Tests

Tests for:
1. NEW: GET /api/resource-bookings/invoices/aggregate (JSON)
2. NEW: GET /api/resource-bookings/invoices/aggregate.pdf (PDF)
3. REGRESSION: Existing invoice endpoints still work
4. PERMISSION: 403 for users without bookings.invoice capability
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session with bookings.invoice capability"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    assert token, "No token in login response"
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="module")
def non_admin_session():
    """Try to get a non-admin session (may not exist)"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Try to create a test user without bookings.invoice capability
    # First check if we can register
    test_email = "test_no_invoice_cap@meetflow.com"
    test_password = "testpass123"
    
    # Try login first (user might already exist)
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    # Try to register
    resp = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": test_email,
        "password": test_password,
        "name": "Test No Invoice Cap"
    })
    if resp.status_code in [200, 201]:
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
            return session
    
    # If we can't create a non-admin user, skip tests that need it
    pytest.skip("Could not create non-admin user for 403 test")


class TestNewAggregateBookingInvoice:
    """Tests for the new /resource-bookings/invoices/aggregate endpoint"""
    
    def test_aggregate_invoice_json_no_filter(self, admin_session):
        """GET /api/resource-bookings/invoices/aggregate without filters returns all bookings"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        # Verify required fields exist
        assert "cost_center" in data
        assert "account" in data
        assert "from_date" in data
        assert "to_date" in data
        assert "booking_count" in data
        assert "lines" in data
        assert "bookings" in data
        assert "total" in data
        assert "currency" in data
        assert "generated_at" in data
        
        # Verify types
        assert isinstance(data["booking_count"], int)
        assert isinstance(data["lines"], list)
        assert isinstance(data["bookings"], list)
        assert isinstance(data["total"], (int, float))
        assert isinstance(data["currency"], str)
        
        print(f"PASS: Aggregate invoice returned {data['booking_count']} bookings, total: {data['total']} {data['currency']}")
    
    def test_aggregate_invoice_json_with_date_filter(self, admin_session):
        """GET /api/resource-bookings/invoices/aggregate with date filter"""
        # Use wide date range to get data
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data["from_date"] == "2025-01-01"
        assert data["to_date"] == "2026-12-31"
        print(f"PASS: Date-filtered aggregate returned {data['booking_count']} bookings")
    
    def test_aggregate_invoice_json_with_cost_center_filter(self, admin_session):
        """GET /api/resource-bookings/invoices/aggregate?cost_center=XYZ filters correctly"""
        # First get all to find a cost center
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Find a cost center from bookings
        cost_centers = set()
        for bk in data.get("bookings", []):
            if bk.get("cost_center"):
                cost_centers.add(bk["cost_center"])
        
        if cost_centers:
            test_cc = list(cost_centers)[0]
            resp2 = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
                "cost_center": test_cc,
                "from_date": "2025-01-01",
                "to_date": "2026-12-31"
            })
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["cost_center"] == test_cc
            # All bookings should have this cost center
            for bk in data2.get("bookings", []):
                assert bk.get("cost_center") == test_cc, f"Booking {bk['booking_id']} has wrong cost_center"
            print(f"PASS: Cost center filter '{test_cc}' returned {data2['booking_count']} bookings")
        else:
            print("SKIP: No bookings with cost_center found to test filter")
    
    def test_aggregate_invoice_pdf(self, admin_session):
        """GET /api/resource-bookings/invoices/aggregate.pdf returns valid PDF"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate.pdf", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        # Check content type
        content_type = resp.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected PDF content type, got: {content_type}"
        
        # Check PDF magic bytes
        content = resp.content
        assert content[:4] == b'%PDF', f"PDF should start with %PDF, got: {content[:20]}"
        
        print(f"PASS: Aggregate PDF returned {len(content)} bytes, valid PDF magic bytes")


class TestAggregateInvoicePermissions:
    """Test 403 for users without bookings.invoice capability"""
    
    def test_aggregate_invoice_requires_capability(self, non_admin_session):
        """User without bookings.invoice capability gets 403"""
        resp = non_admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}: {resp.text}"
        print("PASS: Non-admin user correctly gets 403 on aggregate invoice")


class TestExistingInvoiceEndpointsRegression:
    """Regression tests for existing invoice endpoints"""
    
    def test_single_booking_invoice_json(self, admin_session):
        """GET /api/resource-bookings/{id}/invoice still works"""
        # First get a booking ID
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings", params={"limit": 1})
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No bookings available for single invoice test")
        
        booking = resp.json()[0]
        booking_id = booking.get("booking_id")
        
        resp2 = admin_session.get(f"{BASE_URL}/api/resource-bookings/{booking_id}/invoice")
        assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
        
        data = resp2.json()
        assert data["booking_id"] == booking_id
        assert "lines" in data
        assert "total" in data
        assert "currency" in data
        print(f"PASS: Single booking invoice for {booking_id} returned total: {data['total']}")
    
    def test_single_booking_invoice_pdf(self, admin_session):
        """GET /api/resource-bookings/{id}/invoice.pdf still works"""
        # First get a booking ID
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings", params={"limit": 1})
        if resp.status_code != 200 or not resp.json():
            pytest.skip("No bookings available for single invoice PDF test")
        
        booking = resp.json()[0]
        booking_id = booking.get("booking_id")
        
        resp2 = admin_session.get(f"{BASE_URL}/api/resource-bookings/{booking_id}/invoice.pdf")
        assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
        
        content_type = resp2.headers.get("Content-Type", "")
        assert "application/pdf" in content_type
        assert resp2.content[:4] == b'%PDF'
        print(f"PASS: Single booking PDF for {booking_id} is valid")
    
    def test_catering_aggregate_invoice_json(self, admin_session):
        """GET /api/catering-requests/invoices/aggregate still works"""
        resp = admin_session.get(f"{BASE_URL}/api/catering-requests/invoices/aggregate", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "request_count" in data
        assert "lines" in data
        assert "total" in data
        print(f"PASS: Catering aggregate returned {data['request_count']} requests, total: {data['total']}")
    
    def test_catering_aggregate_invoice_pdf(self, admin_session):
        """GET /api/catering-requests/invoices/aggregate.pdf still works"""
        resp = admin_session.get(f"{BASE_URL}/api/catering-requests/invoices/aggregate.pdf", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        content_type = resp.headers.get("Content-Type", "")
        assert "application/pdf" in content_type
        assert resp.content[:4] == b'%PDF'
        print("PASS: Catering aggregate PDF is valid")
    
    def test_bookings_export_csv(self, admin_session):
        """GET /api/resource-bookings/export/csv still works"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/export/csv")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        content_type = resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type
        print("PASS: Bookings CSV export works")
    
    def test_erp_export_csv_datev(self, admin_session):
        """GET /api/resource-bookings/export/erp.csv?format=datev still works"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/export/erp.csv", params={
            "format": "datev",
            "days": 365
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        content_type = resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type
        print("PASS: DATEV CSV export works")
    
    def test_erp_export_csv_generic(self, admin_session):
        """GET /api/resource-bookings/export/erp.csv?format=generic still works"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/export/erp.csv", params={
            "format": "generic",
            "days": 365
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        content_type = resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type
        print("PASS: Generic CSV export works")


class TestAggregateInvoiceDataIntegrity:
    """Test data integrity of aggregate invoice response"""
    
    def test_lines_structure(self, admin_session):
        """Verify lines array has correct structure"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        for line in data.get("lines", []):
            assert "kind" in line, "Line missing 'kind' field"
            assert line["kind"] in ["catering", "km"], f"Invalid kind: {line['kind']}"
            assert "label" in line
            assert "quantity" in line
            assert "unit_price" in line
            assert "subtotal" in line
            assert isinstance(line["subtotal"], (int, float))
        
        print(f"PASS: All {len(data.get('lines', []))} lines have correct structure")
    
    def test_bookings_structure(self, admin_session):
        """Verify bookings array has correct structure"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        for bk in data.get("bookings", []):
            assert "booking_id" in bk
            assert "title" in bk
            assert "resource_name" in bk
            assert "start_at" in bk
            assert "subtotal" in bk
            assert isinstance(bk["subtotal"], (int, float))
        
        print(f"PASS: All {len(data.get('bookings', []))} bookings have correct structure")
    
    def test_total_matches_lines_sum(self, admin_session):
        """Verify total equals sum of line subtotals"""
        resp = admin_session.get(f"{BASE_URL}/api/resource-bookings/invoices/aggregate", params={
            "from_date": "2025-01-01",
            "to_date": "2026-12-31"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        lines_sum = sum(line.get("subtotal", 0) for line in data.get("lines", []))
        total = data.get("total", 0)
        
        # Allow small floating point difference
        assert abs(lines_sum - total) < 0.01, f"Total {total} doesn't match lines sum {lines_sum}"
        print(f"PASS: Total {total} matches lines sum {lines_sum}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
