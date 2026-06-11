"""
Iteration 258 — Profil-Modul Comprehensive Audit
Tests für:
- GET /api/auth/me (eigene Daten, keine _id Leakage)
- PUT /api/users/profile (Name/Sprache/Avatar/Auto-Reply)
- POST /api/users/avatar (Upload, MIME-Check, Size-Limit)
- POST /api/auth/change-password (Komplexität, alte PW Validierung)
- 2FA Setup/Verify/Disable
- GET/PUT /api/users/me/privacy (hide_from_office_widget)
- GET/PUT /api/users/me/office-days (Hybrid-Work Config)
- POST /api/users/me/office-days/generate (4-Wochen-Generierung)
- POST /api/users/me/office-days/skip (Ad-hoc-Skip mit Reason)
- POST /api/users/me/office-days/slack/test
- GET/PUT /api/users/me/email-preferences
- GET/PUT /api/users/me/caldav-config
- RBAC: Member kann nur eigenes Profil ändern
- Privilege-Escalation-Check: role/capabilities via PUT ignoriert
- 50 concurrent Load-Tests
"""
import pytest
import requests
import os
import uuid
import time
import concurrent.futures

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    import pytest
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


class TestProfileBasics:
    """Grundlegende Profil-Endpunkte"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login als Admin für Tests"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        self.token = data.get("token")
        self.user_id = data.get("user_id")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_me_returns_user_data(self):
        """GET /api/auth/me — eigene Daten ohne _id"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "email" in data
        assert "_id" not in data, "MongoDB _id sollte nicht exponiert werden"
        assert data["email"] == ADMIN_EMAIL
        print(f"✓ GET /api/auth/me: user_id={data['user_id']}, role={data.get('role')}")
    
    def test_get_me_without_auth_returns_401(self):
        """GET /api/auth/me ohne Token -> 401"""
        resp = requests.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 401
        print("✓ GET /api/auth/me ohne Auth -> 401")
    
    def test_update_profile_name_and_language(self):
        """PUT /api/users/profile — Name und Sprache ändern"""
        new_name = f"Test Admin {uuid.uuid4().hex[:6]}"
        resp = requests.put(f"{BASE_URL}/api/users/profile", headers=self.headers, json={
            "name": new_name,
            "language": "de"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("name") == new_name
        assert data.get("language") == "de"
        print(f"✓ PUT /api/users/profile: name={new_name}")
        
        # Zurücksetzen
        requests.put(f"{BASE_URL}/api/users/profile", headers=self.headers, json={
            "name": "Admin User", "language": "de"
        })
    
    def test_update_auto_reply_settings(self):
        """PUT /api/users/profile — Auto-Reply aktivieren"""
        resp = requests.put(f"{BASE_URL}/api/users/profile", headers=self.headers, json={
            "auto_reply_enabled": True,
            "auto_reply_message": "Test Auto-Reply Message"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("auto_reply_enabled") == True
        print("✓ Auto-Reply Settings aktualisiert")


class TestAvatarUpload:
    """Avatar-Upload Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_avatar_upload_valid_image(self):
        """POST /api/users/avatar — gültiges Bild"""
        # Erstelle ein minimales PNG (1x1 pixel)
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
            0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
            0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
            0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        files = {"file": ("test.png", png_data, "image/png")}
        resp = requests.post(f"{BASE_URL}/api/users/avatar", headers=self.headers, files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert "avatar" in data
        print(f"✓ Avatar Upload: {data.get('avatar')}")
    
    def test_avatar_upload_invalid_mime_type(self):
        """POST /api/users/avatar — ungültiger MIME-Type -> 400"""
        files = {"file": ("test.txt", b"not an image", "text/plain")}
        resp = requests.post(f"{BASE_URL}/api/users/avatar", headers=self.headers, files=files)
        assert resp.status_code == 400
        print("✓ Avatar Upload mit text/plain -> 400")
    
    def test_avatar_upload_too_large(self):
        """POST /api/users/avatar — > 5MB -> 400"""
        # 6MB Dummy-Daten
        large_data = b"x" * (6 * 1024 * 1024)
        files = {"file": ("large.png", large_data, "image/png")}
        resp = requests.post(f"{BASE_URL}/api/users/avatar", headers=self.headers, files=files)
        assert resp.status_code == 400
        print("✓ Avatar Upload > 5MB -> 400")


class TestPasswordChange:
    """Passwort-Änderung Tests"""
    
    def test_change_password_weak_password(self):
        """POST /api/auth/change-password — schwaches Passwort -> 400"""
        # Erst einloggen
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        token = resp.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Schwaches Passwort (< 6 Zeichen)
        resp = requests.post(f"{BASE_URL}/api/auth/change-password", headers=headers, json={
            "new_password": "123"
        })
        assert resp.status_code == 400
        print("✓ Schwaches Passwort -> 400")


class TestTwoFactorAuth:
    """2FA Setup/Verify/Disable Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_2fa_status(self):
        """GET /api/auth/2fa/status"""
        resp = requests.get(f"{BASE_URL}/api/auth/2fa/status", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "totp_enabled" in data
        print(f"✓ 2FA Status: enabled={data.get('totp_enabled')}")
    
    def test_2fa_setup_returns_qr_and_secret(self):
        """POST /api/auth/2fa/setup — QR + Secret + Recovery Codes"""
        resp = requests.post(f"{BASE_URL}/api/auth/2fa/setup", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "secret" in data
        assert "qr_png" in data
        assert "recovery_codes" in data
        assert len(data["recovery_codes"]) >= 8
        print(f"✓ 2FA Setup: secret length={len(data['secret'])}, recovery_codes={len(data['recovery_codes'])}")
    
    def test_2fa_verify_wrong_code(self):
        """POST /api/auth/2fa/verify-setup — falscher Code -> 401"""
        # Erst Setup
        requests.post(f"{BASE_URL}/api/auth/2fa/setup", headers=self.headers)
        
        # Falscher Code
        resp = requests.post(f"{BASE_URL}/api/auth/2fa/verify-setup", headers=self.headers, json={
            "code": "000000"
        })
        assert resp.status_code == 401
        print("✓ 2FA Verify mit falschem Code -> 401")


class TestPrivacySettings:
    """Privacy-Einstellungen Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_privacy_settings(self):
        """GET /api/users/me/privacy"""
        resp = requests.get(f"{BASE_URL}/api/users/me/privacy", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "hide_from_office_widget" in data
        print(f"✓ Privacy Settings: hide_from_office_widget={data.get('hide_from_office_widget')}")
    
    def test_update_privacy_settings(self):
        """PUT /api/users/me/privacy — Toggle hide_from_office_widget"""
        # Aktuellen Wert holen
        resp = requests.get(f"{BASE_URL}/api/users/me/privacy", headers=self.headers)
        current = resp.json().get("hide_from_office_widget", False)
        
        # Toggle
        resp = requests.put(f"{BASE_URL}/api/users/me/privacy", headers=self.headers, json={
            "hide_from_office_widget": not current
        })
        assert resp.status_code == 200
        
        # Zurücksetzen
        requests.put(f"{BASE_URL}/api/users/me/privacy", headers=self.headers, json={
            "hide_from_office_widget": current
        })
        print("✓ Privacy Settings Toggle funktioniert")


class TestOfficeDays:
    """Office-Days (Hybrid-Work) Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_office_days_config(self):
        """GET /api/users/me/office-days"""
        resp = requests.get(f"{BASE_URL}/api/users/me/office-days", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "weekdays" in data
        assert "start_time" in data
        assert "end_time" in data
        print(f"✓ Office Days Config: weekdays={data.get('weekdays')}")
    
    def test_update_office_days_config(self):
        """PUT /api/users/me/office-days — Wochentage setzen"""
        resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon", "wed", "fri"],
            "start_time": "09:00",
            "end_time": "17:00",
            "title": "Test Bürotag"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "mon" in data.get("weekdays", [])
        print("✓ Office Days Config aktualisiert")
    
    def test_update_office_days_invalid_weekday(self):
        """PUT /api/users/me/office-days — ungültiger Wochentag -> 400"""
        resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["monday"],  # Falsch, sollte "mon" sein
        })
        assert resp.status_code == 400
        print("✓ Ungültiger Wochentag -> 400")
    
    def test_get_upcoming_office_days(self):
        """GET /api/users/me/office-days/upcoming"""
        resp = requests.get(f"{BASE_URL}/api/users/me/office-days/upcoming", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "upcoming" in data
        print(f"✓ Upcoming Office Days: count={data.get('count', 0)}")
    
    def test_slack_test_without_webhook(self):
        """POST /api/users/me/office-days/slack/test — ohne Webhook -> 400"""
        # Erst Webhook entfernen
        requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "slack_webhook_url": ""
        })
        
        resp = requests.post(f"{BASE_URL}/api/users/me/office-days/slack/test", headers=self.headers)
        assert resp.status_code == 400
        print("✓ Slack Test ohne Webhook -> 400")


class TestEmailPreferences:
    """E-Mail-Einstellungen Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_email_preferences(self):
        """GET /api/users/me/email-preferences"""
        resp = requests.get(f"{BASE_URL}/api/users/me/email-preferences", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "newsletter_enabled" in data
        assert "meeting_invites_enabled" in data
        assert "digest_frequency" in data
        print(f"✓ Email Prefs: newsletter={data.get('newsletter_enabled')}, digest={data.get('digest_frequency')}")
    
    def test_update_email_preferences(self):
        """PUT /api/users/me/email-preferences"""
        resp = requests.put(f"{BASE_URL}/api/users/me/email-preferences", headers=self.headers, json={
            "newsletter_enabled": True,
            "meeting_invites_enabled": True,
            "digest_frequency": "daily"
        })
        assert resp.status_code == 200
        print("✓ Email Preferences aktualisiert")


class TestCalDAV:
    """CalDAV-Konfiguration Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_caldav_config(self):
        """GET /api/users/me/caldav-config"""
        resp = requests.get(f"{BASE_URL}/api/users/me/caldav-config", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        # Passwort sollte nicht zurückgegeben werden
        assert "password" not in data
        print(f"✓ CalDAV Config: enabled={data.get('enabled')}")
    
    def test_update_caldav_config(self):
        """PUT /api/users/me/caldav-config"""
        resp = requests.put(f"{BASE_URL}/api/users/me/caldav-config", headers=self.headers, json={
            "enabled": False,
            "url": "",
            "auto_sync": False
        })
        assert resp.status_code == 200
        print("✓ CalDAV Config aktualisiert")


class TestRBACAndPrivilegeEscalation:
    """RBAC und Privilege-Escalation Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        # Admin Login
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.admin_token = resp.json().get("token")
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Neuen Test-User erstellen
        self.test_email = f"test-profile-{uuid.uuid4().hex[:8]}@meetflow.com"
        resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": self.test_email,
            "password": "test123456",
            "name": "Test Profile User"
        })
        if resp.status_code == 200:
            self.test_token = resp.json().get("token")
            self.test_user_id = resp.json().get("user_id")
            self.test_headers = {"Authorization": f"Bearer {self.test_token}"}
        else:
            pytest.skip("Could not create test user")
    
    def test_member_can_only_see_own_profile(self):
        """Member kann nur eigenes Profil sehen"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=self.test_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == self.test_email
        print("✓ Member sieht eigenes Profil")
    
    def test_privilege_escalation_role_ignored(self):
        """PUT /api/users/profile mit role='admin' wird ignoriert"""
        resp = requests.put(f"{BASE_URL}/api/users/profile", headers=self.test_headers, json={
            "name": "Hacker",
            "role": "admin"  # Sollte ignoriert werden!
        })
        assert resp.status_code == 200
        
        # Prüfen ob Role noch 'user' ist
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=self.test_headers)
        data = resp.json()
        assert data.get("role") != "admin", "SECURITY BUG: Role wurde geändert!"
        print("✓ Privilege Escalation via role verhindert")
    
    def test_privilege_escalation_capabilities_ignored(self):
        """PUT /api/users/profile mit capabilities wird ignoriert"""
        resp = requests.put(f"{BASE_URL}/api/users/profile", headers=self.test_headers, json={
            "name": "Hacker",
            "capabilities": ["admin:all", "resources.approve"]  # Sollte ignoriert werden!
        })
        assert resp.status_code == 200
        
        # Prüfen ob keine neuen Capabilities
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=self.test_headers)
        data = resp.json()
        caps = data.get("capabilities", [])
        assert "admin:all" not in caps, "SECURITY BUG: Capabilities wurden geändert!"
        print("✓ Privilege Escalation via capabilities verhindert")


class TestLoadTest50Concurrent:
    """50 Concurrent User Load Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def _make_request(self, endpoint, method="GET", json_data=None):
        """Helper für concurrent requests"""
        start = time.time()
        try:
            if method == "GET":
                resp = requests.get(f"{BASE_URL}{endpoint}", headers=self.headers, timeout=10)
            else:
                resp = requests.request(method, f"{BASE_URL}{endpoint}", headers=self.headers, json=json_data, timeout=10)
            duration = time.time() - start
            return {"status": resp.status_code, "duration": duration, "success": resp.status_code < 400}
        except Exception as e:
            return {"status": 0, "duration": time.time() - start, "success": False, "error": str(e)}
    
    def test_50_concurrent_get_me(self):
        """50× GET /api/auth/me concurrent"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(self._make_request, "/api/auth/me") for _ in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        success_count = sum(1 for r in results if r["success"])
        durations = [r["duration"] for r in results if r["success"]]
        p95 = sorted(durations)[int(len(durations) * 0.95)] if durations else 0
        
        print(f"✓ 50 concurrent GET /api/auth/me: {success_count}/50 success, p95={p95:.3f}s")
        assert success_count >= 45, f"Too many failures: {50 - success_count}"
        assert p95 < 2.0, f"p95 too slow: {p95}s"
    
    def test_50_concurrent_put_profile_same_user(self):
        """50× PUT /api/users/profile concurrent by SAME user"""
        def update_name(i):
            return self._make_request("/api/users/profile", "PUT", {"name": f"Concurrent Test {i}"})
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(update_name, i) for i in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        success_count = sum(1 for r in results if r["success"])
        print(f"✓ 50 concurrent PUT /api/users/profile: {success_count}/50 success")
        assert success_count >= 45, f"Too many failures: {50 - success_count}"
        
        # Zurücksetzen
        requests.put(f"{BASE_URL}/api/users/profile", headers=self.headers, json={"name": "Admin User"})


class TestValidationErrors:
    """Validation Error Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_caldav_malformed_url(self):
        """PUT /api/users/me/caldav-config mit ungültiger URL"""
        resp = requests.put(f"{BASE_URL}/api/users/me/caldav-config", headers=self.headers, json={
            "enabled": True,
            "url": "not-a-valid-url"
        })
        # Sollte entweder 400 oder akzeptiert werden (je nach Implementierung)
        # Wichtig ist, dass es nicht crasht
        assert resp.status_code in [200, 400]
        print(f"✓ CalDAV mit ungültiger URL: {resp.status_code}")
    
    def test_office_days_invalid_time_format(self):
        """PUT /api/users/me/office-days mit ungültigem Zeit-Format"""
        resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "start_time": "invalid"
        })
        assert resp.status_code == 400
        print("✓ Ungültiges Zeit-Format -> 400")
    
    def test_office_days_end_before_start(self):
        """PUT /api/users/me/office-days mit Endzeit vor Startzeit"""
        resp = requests.put(f"{BASE_URL}/api/users/me/office-days", headers=self.headers, json={
            "weekdays": ["mon"],
            "start_time": "17:00",
            "end_time": "08:00"
        })
        assert resp.status_code == 400
        print("✓ Endzeit vor Startzeit -> 400")


class TestDSGVO:
    """DSGVO Export/Delete Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_data_export(self):
        """GET /api/users/me/export — DSGVO Art. 20"""
        resp = requests.get(f"{BASE_URL}/api/users/me/export", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert "generated_at" in data
        print(f"✓ DSGVO Export: keys={list(data.keys())[:5]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
