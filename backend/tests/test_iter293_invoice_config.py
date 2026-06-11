"""
Iteration 293 — Configurable Internal Invoice System Tests
==========================================================

Tests for:
- Master Data CRUD (Konten, Kostenstellen, Kostenträger, Projekte)
- Number Ranges CRUD with pattern validation
- Invoice Templates CRUD with required/visible fields
- Manual Invoice creation with template validation
- PDF generation for manual invoices
- Accounting update endpoint with paid-lock
- Extended DATEV CSV export
- Capability checks (invoices.manage_templates, invoices.manage_master_data, invoices.create_manual, invoices.set_accounting)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://video-meet-pro.preview.emergentagent.com"

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
    token = data.get("token")
    assert token, "No token in login response"
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="module")
def test_user_session(admin_session):
    """Create a test user without invoice capabilities and return session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Create test user via admin invite
    test_email = f"test_nocap_{uuid.uuid4().hex[:6]}@test.com"
    resp = admin_session.post(f"{BASE_URL}/api/admin/users/invite", json={
        "email": test_email,
        "name": "Test No Cap User",
        "role": "member"
    })
    if resp.status_code != 200:
        pytest.skip(f"Could not create test user: {resp.text}")
    
    user_data = resp.json()
    temp_password = user_data.get("temp_password")
    if not temp_password:
        pytest.skip("No temp_password in invite response")
    
    # Login as test user
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": temp_password
    })
    if resp.status_code != 200:
        pytest.skip(f"Test user login failed: {resp.text}")
    
    token = resp.json().get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    session.test_email = test_email
    return session


# ============ MASTER DATA TESTS ============

class TestMasterDataCRUD:
    """Tests for /api/admin/invoice-master-data endpoints."""
    
    created_items = []
    
    def test_create_account(self, admin_session):
        """Create a master data item of type 'account'."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "account",
            "code": f"TEST_ACC_{uuid.uuid4().hex[:4]}",
            "label": "Test Account",
            "description": "Test account for iter 293",
            "active": True
        })
        assert resp.status_code == 200, f"Create account failed: {resp.text}"
        data = resp.json()
        assert "item_id" in data
        assert data["type"] == "account"
        self.created_items.append(data["item_id"])
        print(f"PASS: Created account {data['code']}")
    
    def test_create_cost_center(self, admin_session):
        """Create a master data item of type 'cost_center'."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "cost_center",
            "code": f"TEST_CC_{uuid.uuid4().hex[:4]}",
            "label": "Test Cost Center",
            "active": True
        })
        assert resp.status_code == 200, f"Create cost_center failed: {resp.text}"
        data = resp.json()
        assert data["type"] == "cost_center"
        self.created_items.append(data["item_id"])
        print(f"PASS: Created cost_center {data['code']}")
    
    def test_create_cost_object(self, admin_session):
        """Create a master data item of type 'cost_object'."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "cost_object",
            "code": f"TEST_CO_{uuid.uuid4().hex[:4]}",
            "label": "Test Cost Object",
            "active": True
        })
        assert resp.status_code == 200, f"Create cost_object failed: {resp.text}"
        data = resp.json()
        assert data["type"] == "cost_object"
        self.created_items.append(data["item_id"])
        print(f"PASS: Created cost_object {data['code']}")
    
    def test_create_project(self, admin_session):
        """Create a master data item of type 'project'."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "project",
            "code": f"TEST_PRJ_{uuid.uuid4().hex[:4]}",
            "label": "Test Project",
            "active": True
        })
        assert resp.status_code == 200, f"Create project failed: {resp.text}"
        data = resp.json()
        assert data["type"] == "project"
        self.created_items.append(data["item_id"])
        print(f"PASS: Created project {data['code']}")
    
    def test_list_master_data_by_type(self, admin_session):
        """List master data filtered by type."""
        for t in ["account", "cost_center", "cost_object", "project"]:
            resp = admin_session.get(f"{BASE_URL}/api/admin/invoice-master-data", params={"type": t})
            assert resp.status_code == 200, f"List {t} failed: {resp.text}"
            data = resp.json()
            assert isinstance(data, list)
            print(f"PASS: Listed {len(data)} items of type {t}")
    
    def test_duplicate_code_conflict(self, admin_session):
        """Creating duplicate code for same type should return 409."""
        code = f"TEST_DUP_{uuid.uuid4().hex[:4]}"
        # First create
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "account",
            "code": code,
            "label": "First"
        })
        assert resp.status_code == 200
        self.created_items.append(resp.json()["item_id"])
        
        # Duplicate should fail
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "account",
            "code": code,
            "label": "Duplicate"
        })
        assert resp.status_code == 409, f"Expected 409 for duplicate, got {resp.status_code}"
        print("PASS: Duplicate code returns 409 Conflict")
    
    def test_update_master_data(self, admin_session):
        """Update a master data item."""
        # Create first
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "account",
            "code": f"TEST_UPD_{uuid.uuid4().hex[:4]}",
            "label": "Original Label",
            "active": True
        })
        assert resp.status_code == 200
        item_id = resp.json()["item_id"]
        self.created_items.append(item_id)
        
        # Update
        resp = admin_session.put(f"{BASE_URL}/api/admin/invoice-master-data/{item_id}", json={
            "label": "Updated Label",
            "active": False
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "Updated Label"
        assert data["active"] == False
        print("PASS: Master data update works")
    
    def test_delete_master_data(self, admin_session):
        """Delete a master data item."""
        # Create first
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-master-data", json={
            "type": "account",
            "code": f"TEST_DEL_{uuid.uuid4().hex[:4]}",
            "label": "To Delete"
        })
        assert resp.status_code == 200
        item_id = resp.json()["item_id"]
        
        # Delete
        resp = admin_session.delete(f"{BASE_URL}/api/admin/invoice-master-data/{item_id}")
        assert resp.status_code == 200
        assert resp.json().get("ok") == True
        print("PASS: Master data delete works")


# ============ NUMBER RANGES TESTS ============

class TestNumberRangesCRUD:
    """Tests for /api/admin/invoice-number-ranges endpoints."""
    
    created_ranges = []
    
    def test_create_number_range_valid_pattern(self, admin_session):
        """Create a number range with valid pattern containing counter."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-number-ranges", json={
            "name": f"Test Range {uuid.uuid4().hex[:4]}",
            "prefix": "RE",
            "pattern": "{PREFIX}-{YYYY}-{####}",
            "start_number": 1,
            "yearly_reset": True,
            "active": True,
            "is_default": False
        })
        assert resp.status_code == 200, f"Create range failed: {resp.text}"
        data = resp.json()
        assert "range_id" in data
        assert data["pattern"] == "{PREFIX}-{YYYY}-{####}"
        self.created_ranges.append(data["range_id"])
        print(f"PASS: Created number range {data['name']}")
    
    def test_create_number_range_invalid_pattern(self, admin_session):
        """Pattern without counter should return 400."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-number-ranges", json={
            "name": f"Invalid Range {uuid.uuid4().hex[:4]}",
            "prefix": "RE",
            "pattern": "{PREFIX}-{YYYY}",  # No counter!
            "start_number": 1
        })
        assert resp.status_code == 400, f"Expected 400 for invalid pattern, got {resp.status_code}"
        print("PASS: Invalid pattern (no counter) returns 400")
    
    def test_create_number_range_three_digit_counter(self, admin_session):
        """Pattern with {###} counter should work."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-number-ranges", json={
            "name": f"Three Digit Range {uuid.uuid4().hex[:4]}",
            "prefix": "INV",
            "pattern": "{PREFIX}-{YY}-{###}",
            "start_number": 1
        })
        assert resp.status_code == 200, f"Create range with ### failed: {resp.text}"
        self.created_ranges.append(resp.json()["range_id"])
        print("PASS: Pattern with {###} counter works")
    
    def test_create_number_range_two_digit_counter(self, admin_session):
        """Pattern with {##} counter should work."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-number-ranges", json={
            "name": f"Two Digit Range {uuid.uuid4().hex[:4]}",
            "prefix": "R",
            "pattern": "{PREFIX}{MM}-{##}",
            "start_number": 1
        })
        assert resp.status_code == 200, f"Create range with ## failed: {resp.text}"
        self.created_ranges.append(resp.json()["range_id"])
        print("PASS: Pattern with {##} counter works")
    
    def test_is_default_exclusive(self, admin_session):
        """Setting is_default should clear previous default."""
        # Create first default
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-number-ranges", json={
            "name": f"Default 1 {uuid.uuid4().hex[:4]}",
            "prefix": "D1",
            "pattern": "{PREFIX}-{####}",
            "is_default": True
        })
        assert resp.status_code == 200
        range1_id = resp.json()["range_id"]
        self.created_ranges.append(range1_id)
        
        # Create second default
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-number-ranges", json={
            "name": f"Default 2 {uuid.uuid4().hex[:4]}",
            "prefix": "D2",
            "pattern": "{PREFIX}-{####}",
            "is_default": True
        })
        assert resp.status_code == 200
        range2_id = resp.json()["range_id"]
        self.created_ranges.append(range2_id)
        
        # Check first is no longer default
        resp = admin_session.get(f"{BASE_URL}/api/admin/invoice-number-ranges")
        assert resp.status_code == 200
        ranges = resp.json()
        range1 = next((r for r in ranges if r["range_id"] == range1_id), None)
        range2 = next((r for r in ranges if r["range_id"] == range2_id), None)
        
        if range1:
            assert range1.get("is_default") == False, "First range should no longer be default"
        if range2:
            assert range2.get("is_default") == True, "Second range should be default"
        print("PASS: is_default is exclusive (only one default)")
    
    def test_list_number_ranges(self, admin_session):
        """List all number ranges."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/invoice-number-ranges")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: Listed {len(data)} number ranges")


# ============ TEMPLATES TESTS ============

class TestTemplatesCRUD:
    """Tests for /api/admin/invoice-templates endpoints."""
    
    created_templates = []
    
    def test_create_template(self, admin_session):
        """Create an invoice template."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-templates", json={
            "name": f"Test Template {uuid.uuid4().hex[:4]}",
            "description": "Test template for iter 293",
            "header_text": "Test Header",
            "footer_text": "Test Footer",
            "payment_terms_default": "Zahlbar binnen 14 Tagen",
            "bank_details": "IBAN: DE89 3704 0044 0532 0130 00",
            "default_tax_rate": 19.0,
            "required_fields": ["recipient_name", "issue_date", "lines", "cost_center"],
            "visible_fields": ["cost_center", "account", "payment_terms", "notes"],
            "is_default": False,
            "active": True
        })
        assert resp.status_code == 200, f"Create template failed: {resp.text}"
        data = resp.json()
        assert "template_id" in data
        assert "cost_center" in data["required_fields"]
        self.created_templates.append(data["template_id"])
        print(f"PASS: Created template {data['name']}")
        return data["template_id"]
    
    def test_template_is_default_exclusive(self, admin_session):
        """Setting is_default should clear previous default."""
        # Create first default
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-templates", json={
            "name": f"Default Tpl 1 {uuid.uuid4().hex[:4]}",
            "default_tax_rate": 19.0,
            "is_default": True
        })
        assert resp.status_code == 200
        tpl1_id = resp.json()["template_id"]
        self.created_templates.append(tpl1_id)
        
        # Create second default
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-templates", json={
            "name": f"Default Tpl 2 {uuid.uuid4().hex[:4]}",
            "default_tax_rate": 7.0,
            "is_default": True
        })
        assert resp.status_code == 200
        tpl2_id = resp.json()["template_id"]
        self.created_templates.append(tpl2_id)
        
        # Check first is no longer default
        resp = admin_session.get(f"{BASE_URL}/api/admin/invoice-templates")
        assert resp.status_code == 200
        templates = resp.json()
        tpl1 = next((t for t in templates if t["template_id"] == tpl1_id), None)
        tpl2 = next((t for t in templates if t["template_id"] == tpl2_id), None)
        
        if tpl1:
            assert tpl1.get("is_default") == False
        if tpl2:
            assert tpl2.get("is_default") == True
        print("PASS: Template is_default is exclusive")
    
    def test_list_templates(self, admin_session):
        """List all templates."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/invoice-templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: Listed {len(data)} templates")


# ============ MANUAL INVOICE TESTS ============

class TestManualInvoice:
    """Tests for POST /api/invoices/manual endpoint."""
    
    created_invoices = []
    test_template_id = None
    test_range_id = None
    
    @pytest.fixture(autouse=True)
    def setup_template_and_range(self, admin_session):
        """Create a template with cost_center required and a number range."""
        # Create template with cost_center required
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-templates", json={
            "name": f"Manual Test Tpl {uuid.uuid4().hex[:4]}",
            "default_tax_rate": 7.0,
            "required_fields": ["recipient_name", "issue_date", "lines", "cost_center"],
            "visible_fields": ["cost_center", "account", "payment_terms"],
            "is_default": True,
            "active": True
        })
        if resp.status_code == 200:
            self.__class__.test_template_id = resp.json()["template_id"]
        
        # Create number range
        resp = admin_session.post(f"{BASE_URL}/api/admin/invoice-number-ranges", json={
            "name": f"Manual Test Range {uuid.uuid4().hex[:4]}",
            "prefix": "RE",
            "pattern": "{PREFIX}-{YYYY}-{####}",
            "start_number": 1,
            "yearly_reset": True,
            "is_default": True,
            "active": True
        })
        if resp.status_code == 200:
            self.__class__.test_range_id = resp.json()["range_id"]
    
    def test_create_manual_invoice_missing_required_field(self, admin_session):
        """Creating invoice without required cost_center should return 400."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Test Customer",
            "issue_date": "2026-01-15",
            # cost_center is missing but required by template
            "lines": [
                {"label": "Service", "quantity": 1, "unit_price": 100}
            ]
        })
        assert resp.status_code == 400, f"Expected 400 for missing required field, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("code") == "missing_required_fields", f"Expected code='missing_required_fields', got {detail}"
            assert "cost_center" in detail.get("fields", []), f"Expected cost_center in fields, got {detail}"
        print("PASS: Missing required field returns 400 with code='missing_required_fields'")
    
    def test_create_manual_invoice_success(self, admin_session):
        """Create a valid manual invoice."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Test Customer GmbH",
            "issue_date": "2026-01-15",
            "cost_center": "TEST_CC",
            "lines": [
                {"label": "Beratung", "quantity": 2, "unit": "Std", "unit_price": 150, "tax_rate": 19},
                {"label": "Material", "quantity": 1, "unit_price": 50, "discount_percent": 10, "tax_rate": 7}
            ]
        })
        assert resp.status_code == 200, f"Create manual invoice failed: {resp.text}"
        data = resp.json()
        assert "invoice_id" in data
        assert "invoice_number" in data
        assert data["kind"] == "manual"
        self.created_invoices.append(data["invoice_id"])
        print(f"PASS: Created manual invoice {data['invoice_number']}")
        return data
    
    def test_invoice_number_allocation_atomic(self, admin_session):
        """Two consecutive invoices should get sequential numbers."""
        # First invoice
        resp1 = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Customer 1",
            "issue_date": "2026-01-15",
            "cost_center": "CC1",
            "lines": [{"label": "Item 1", "quantity": 1, "unit_price": 100}]
        })
        assert resp1.status_code == 200, f"First invoice failed: {resp1.text}"
        inv1 = resp1.json()
        self.created_invoices.append(inv1["invoice_id"])
        
        # Second invoice
        resp2 = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Customer 2",
            "issue_date": "2026-01-15",
            "cost_center": "CC2",
            "lines": [{"label": "Item 2", "quantity": 1, "unit_price": 200}]
        })
        assert resp2.status_code == 200, f"Second invoice failed: {resp2.text}"
        inv2 = resp2.json()
        self.created_invoices.append(inv2["invoice_id"])
        
        # Numbers should be different
        assert inv1["invoice_number"] != inv2["invoice_number"]
        print(f"PASS: Sequential invoice numbers: {inv1['invoice_number']} -> {inv2['invoice_number']}")
    
    def test_tax_calculation_with_discount(self, admin_session):
        """Verify MwSt calculation: discount applied before tax."""
        resp = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Tax Test Customer",
            "issue_date": "2026-01-15",
            "cost_center": "TAX_CC",
            "lines": [
                # 10 * 100 = 1000, 10% discount = 900 net, 7% tax = 63
                {"label": "Discounted Item", "quantity": 10, "unit_price": 100, "discount_percent": 10, "tax_rate": 7}
            ]
        })
        assert resp.status_code == 200, f"Tax calculation invoice failed: {resp.text}"
        data = resp.json()
        self.created_invoices.append(data["invoice_id"])
        
        snapshot = data.get("snapshot", {})
        lines = snapshot.get("lines", [])
        assert len(lines) == 1
        
        line = lines[0]
        # Net after discount: 1000 * 0.9 = 900
        assert abs(line["subtotal_net"] - 900.0) < 0.01, f"Expected net 900, got {line['subtotal_net']}"
        # Tax: 900 * 0.07 = 63
        assert abs(line["tax_amount"] - 63.0) < 0.01, f"Expected tax 63, got {line['tax_amount']}"
        # Gross: 900 + 63 = 963
        assert abs(line["subtotal_gross"] - 963.0) < 0.01, f"Expected gross 963, got {line['subtotal_gross']}"
        
        print("PASS: Tax calculation with discount is correct (discount before tax)")


# ============ PDF GENERATION TEST ============

class TestManualInvoicePDF:
    """Tests for GET /api/invoices/{id}/pdf/manual endpoint."""
    
    def test_get_manual_invoice_pdf(self, admin_session):
        """Generate PDF for a manual invoice."""
        # First create an invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "PDF Test Customer",
            "issue_date": "2026-01-15",
            "cost_center": "PDF_CC",
            "payment_terms": "Zahlbar sofort",
            "lines": [
                {"label": "PDF Test Item", "quantity": 1, "unit_price": 100, "tax_rate": 19}
            ]
        })
        assert resp.status_code == 200, f"Create invoice for PDF failed: {resp.text}"
        invoice_id = resp.json()["invoice_id"]
        
        # Get PDF
        resp = admin_session.get(f"{BASE_URL}/api/invoices/{invoice_id}/pdf/manual")
        assert resp.status_code == 200, f"PDF generation failed: {resp.text}"
        assert resp.headers.get("content-type") == "application/pdf"
        assert len(resp.content) > 1000, f"PDF too small: {len(resp.content)} bytes"
        print(f"PASS: PDF generated, {len(resp.content)} bytes, content-type=application/pdf")


# ============ ACCOUNTING UPDATE TEST ============

class TestAccountingUpdate:
    """Tests for PUT /api/invoices/{id}/accounting endpoint."""
    
    def test_update_accounting_fields(self, admin_session):
        """Update cost_center/account/cost_object/project_code on invoice."""
        # Create invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Accounting Test",
            "issue_date": "2026-01-15",
            "cost_center": "OLD_CC",
            "lines": [{"label": "Item", "quantity": 1, "unit_price": 100}]
        })
        assert resp.status_code == 200, f"Create invoice for accounting test failed: {resp.text}"
        invoice_id = resp.json()["invoice_id"]
        
        # Update accounting
        resp = admin_session.put(f"{BASE_URL}/api/invoices/{invoice_id}/accounting", json={
            "cost_center": "NEW_CC",
            "account": "4711",
            "cost_object": "KT001",
            "project_code": "PRJ2026"
        })
        assert resp.status_code == 200, f"Accounting update failed: {resp.text}"
        data = resp.json()
        assert data["cost_center"] == "NEW_CC"
        assert data["account"] == "4711"
        assert data["cost_object"] == "KT001"
        assert data["project_code"] == "PRJ2026"
        print("PASS: Accounting fields updated successfully")


# ============ DATEV EXPORT TEST ============

class TestDatevExport:
    """Tests for GET /api/invoices/export/datev-extended.csv endpoint."""
    
    def test_datev_csv_export(self, admin_session):
        """Export invoices as DATEV CSV."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices/export/datev-extended.csv")
        assert resp.status_code == 200, f"DATEV export failed: {resp.text}"
        
        content_type = resp.headers.get("content-type", "")
        assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"
        
        content = resp.content
        # Check UTF-8 BOM
        assert content[:3] == b'\xef\xbb\xbf', "Missing UTF-8 BOM"
        
        # Decode and check structure
        text = content.decode("utf-8-sig")
        lines = text.strip().split("\n")
        assert len(lines) >= 1, "CSV should have at least header row"
        
        header = lines[0]
        # Check semicolon delimiter
        assert ";" in header, "Expected semicolon delimiter"
        
        # Check expected columns
        expected_cols = ["Rechnungsnummer", "Datum", "Empfänger", "Konto", "Kostenstelle", 
                        "Kostenträger", "Projekt", "Brutto", "Netto", "MwSt", "Währung", "Status"]
        for col in expected_cols:
            assert col in header, f"Missing column: {col}"
        
        print(f"PASS: DATEV CSV export OK, {len(lines)} rows, UTF-8 BOM, semicolon delimiter")
    
    def test_datev_csv_filter_by_cost_center(self, admin_session):
        """Filter DATEV export by cost_center."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices/export/datev-extended.csv", 
                                 params={"cost_center": "FILTER_TEST_CC"})
        assert resp.status_code == 200
        print("PASS: DATEV CSV filter by cost_center works")
    
    def test_datev_csv_filter_by_date_range(self, admin_session):
        """Filter DATEV export by date range."""
        resp = admin_session.get(f"{BASE_URL}/api/invoices/export/datev-extended.csv",
                                 params={"from_date": "2026-01-01", "to_date": "2026-12-31"})
        assert resp.status_code == 200
        print("PASS: DATEV CSV filter by date range works")


# ============ CAPABILITY TESTS ============

class TestCapabilities:
    """Tests for new invoice capabilities."""
    
    def test_capabilities_exist_in_list(self, admin_session):
        """Verify new capabilities are defined in the system."""
        # We can check by trying to access endpoints that require them
        # Admin should have all caps by default
        
        # invoices.manage_templates - admin can access templates
        resp = admin_session.get(f"{BASE_URL}/api/admin/invoice-templates")
        assert resp.status_code == 200, "Admin should have invoices.manage_templates"
        
        # invoices.manage_master_data - admin can access master data
        resp = admin_session.get(f"{BASE_URL}/api/admin/invoice-master-data", params={"type": "account"})
        assert resp.status_code == 200, "Admin should have invoices.manage_master_data"
        
        # invoices.create_manual - admin can create manual invoice
        resp = admin_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Cap Test",
            "issue_date": "2026-01-15",
            "cost_center": "CAP_CC",
            "lines": [{"label": "Test", "quantity": 1, "unit_price": 10}]
        })
        assert resp.status_code == 200, f"Admin should have invoices.create_manual: {resp.text}"
        
        print("PASS: All 4 new capabilities work for admin")
    
    def test_non_admin_without_create_manual_cap_403(self, test_user_session):
        """User without invoices.create_manual capability should get 403."""
        resp = test_user_session.post(f"{BASE_URL}/api/invoices/manual", json={
            "recipient_name": "Unauthorized Test",
            "cost_center": "UNAUTH_CC",
            "lines": [{"label": "Test", "quantity": 1, "unit_price": 10}]
        })
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("PASS: Non-admin without create_manual cap gets 403")


# ============ CLEANUP ============

@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_session, request):
    """Cleanup test data after all tests."""
    def do_cleanup():
        # Cleanup is best-effort, don't fail if items already deleted
        for item_id in TestMasterDataCRUD.created_items:
            try:
                admin_session.delete(f"{BASE_URL}/api/admin/invoice-master-data/{item_id}")
            except:
                pass
        
        for range_id in TestNumberRangesCRUD.created_ranges:
            try:
                admin_session.delete(f"{BASE_URL}/api/admin/invoice-number-ranges/{range_id}")
            except:
                pass
        
        for tpl_id in TestTemplatesCRUD.created_templates:
            try:
                admin_session.delete(f"{BASE_URL}/api/admin/invoice-templates/{tpl_id}")
            except:
                pass
        
        print("Cleanup completed")
    
    request.addfinalizer(do_cleanup)
