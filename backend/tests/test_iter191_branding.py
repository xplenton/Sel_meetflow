"""Iter 191 — Klinik-Branding: Offizieller Virtual-Background.
Tests the admin-only upload/toggle/delete flow + public status endpoint.
"""
import io
import os
import requests
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


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=10).json()
    if r.get("totp_required"):
        pytest.skip("admin 2FA enabled")
    if "token" not in r:
        pytest.skip(f"login failed: {r}")
    return r


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@meetflow.com", "admin123")["token"]


@pytest.fixture(scope="module")
def member_token(admin_token):
    """Create a non-admin user for the authorization checks."""
    import uuid
    suffix = uuid.uuid4().hex[:6]
    email = f"branding_test_{suffix}@example.com"
    requests.post(f"{API}/auth/register",
                  json={"email": email, "name": f"Branding {suffix}", "password": "Test1234!"},
                  timeout=10)
    return _login(email, "Test1234!")["token"]


def _png_bytes() -> bytes:
    # Minimal valid PNG (1x1 green pixel)
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de00000008494441540878636400000000000000017d0dd7000000004944"
        "41454ae426820000000049454e44ae426082"
    )


def test_branding_full_flow(admin_token, member_token):
    ah = {"Authorization": f"Bearer {admin_token}"}
    mh = {"Authorization": f"Bearer {member_token}"}

    # Clean slate
    requests.delete(f"{API}/admin/branding/background", headers=ah, timeout=10)

    # 1) Initial state → enabled=false
    s = requests.get(f"{API}/branding/official-background", headers=ah, timeout=10).json()
    assert s["enabled"] is False
    assert s["url"] is None

    # 2) Member cannot upload → 403
    files = {"file": ("bg.png", io.BytesIO(_png_bytes()), "image/png")}
    r = requests.post(f"{API}/admin/branding/background", headers=mh, files=files, timeout=10)
    assert r.status_code == 403

    # 3) Admin uploads → 200
    files = {"file": ("bg.png", io.BytesIO(_png_bytes()), "image/png")}
    r = requests.post(
        f"{API}/admin/branding/background",
        headers=ah,
        files=files,
        data={"name": "Klinik XY"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["name"] == "Klinik XY"
    url = body["url"]

    # 4) Member can READ the status (to populate the BG picker)
    s = requests.get(f"{API}/branding/official-background", headers=mh, timeout=10).json()
    assert s["enabled"] is True
    assert s["url"] == url
    assert s["name"] == "Klinik XY"

    # 5) File is publicly servable so the <canvas> + crossOrigin='anonymous' works
    r = requests.get(f"{API}{url.replace('/api', '')}", timeout=10)
    # `url` starts with /api/branding/files/...; rebuild as full URL
    full_url = f"{API.rsplit('/api', 1)[0]}{url}"
    r = requests.get(full_url, timeout=10)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/")

    # 6) Toggle disabled → status reflects it
    requests.put(f"{API}/admin/branding/background", headers=ah, json={"enabled": False}, timeout=10)
    s = requests.get(f"{API}/branding/official-background", headers=mh, timeout=10).json()
    assert s["enabled"] is False
    assert s["url"] is None

    # 7) Member cannot toggle
    r = requests.put(f"{API}/admin/branding/background", headers=mh, json={"enabled": True}, timeout=10)
    assert r.status_code == 403

    # 8) Admin can rename only
    requests.put(f"{API}/admin/branding/background", headers=ah, json={"enabled": True, "name": "Neuer Name"}, timeout=10)
    s = requests.get(f"{API}/branding/official-background", headers=mh, timeout=10).json()
    assert s["name"] == "Neuer Name"

    # 9) Reject invalid mime
    r = requests.post(
        f"{API}/admin/branding/background",
        headers=ah,
        files={"file": ("bg.gif", io.BytesIO(b"GIF89a"), "image/gif")},
        timeout=10,
    )
    assert r.status_code == 400

    # 10) Member cannot delete
    r = requests.delete(f"{API}/admin/branding/background", headers=mh, timeout=10)
    assert r.status_code == 403

    # 11) Admin deletes → status goes back to empty
    r = requests.delete(f"{API}/admin/branding/background", headers=ah, timeout=10)
    assert r.status_code == 200
    s = requests.get(f"{API}/branding/official-background", headers=mh, timeout=10).json()
    assert s["enabled"] is False
    assert s["url"] is None


def test_branding_path_traversal_blocked():
    """Direct file-serve must reject path-traversal attempts."""
    r = requests.get(f"{API}/branding/files/..%2F..%2Fetc%2Fpasswd", timeout=10)
    # URL-decoded server-side → detected by the ".." check
    assert r.status_code in (400, 404)
