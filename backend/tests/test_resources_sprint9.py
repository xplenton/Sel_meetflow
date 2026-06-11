"""
Iter 233 — UI-Coverage backend tests:
  GET /users/{user_id}/driver-license  (new endpoint)
"""
import requests
import pytest


with open("/app/frontend/.env") as f:
    API = next(line.split("=", 1)[1].strip().rstrip("/") for line in f if line.startswith("REACT_APP_BACKEND_URL"))


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/api/auth/login",
                  json={"email": "admin@meetflow.com", "password": "admin123"}, timeout=10)
    assert r.status_code == 200
    yield sess


def test_driver_license_get_returns_defaults(s):
    """Wenn noch nichts gesetzt -> defaults zurueck (statt 404)."""
    me = s.get(f"{API}/api/auth/me", timeout=10).json()
    # Reset auf leeren Wert (PUT mit valid=false + leere classes)
    s.put(f"{API}/api/users/{me['user_id']}/driver-license",
          json={"valid": False, "expires_on": None, "classes": []}, timeout=10)
    r = s.get(f"{API}/api/users/{me['user_id']}/driver-license", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is False
    assert data["classes"] == []


def test_driver_license_get_returns_set_data(s):
    me = s.get(f"{API}/api/auth/me", timeout=10).json()
    s.put(f"{API}/api/users/{me['user_id']}/driver-license",
          json={"valid": True, "expires_on": "2030-12-31", "classes": ["B", "BE"]}, timeout=10)
    r = s.get(f"{API}/api/users/{me['user_id']}/driver-license", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["valid"] is True
    assert data["expires_on"] == "2030-12-31"
    assert "B" in data["classes"] and "BE" in data["classes"]
