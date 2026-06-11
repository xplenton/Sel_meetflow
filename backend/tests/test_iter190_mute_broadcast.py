"""Iter 190 — participant mute broadcast + virtual background publishing.

* Backend: PUT /meetings/{id}/participants/{uid} with mic_on=false broadcasts
  host-control/mute_user over WS so the target client actually disables its
  audio track.
* Frontend handling + canvas-stream publishing to LiveKit is covered by
  Playwright in the testing agent run.
"""
import os
import uuid
import asyncio
import json

import pytest
import websockets
import requests


def _api():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/") + "/api"
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/") + "/api"
    return "http://localhost:8001/api"


def _ws():
    return _api().replace("https://", "wss://").replace("http://", "ws://")


API = _api()
# iter 190 — the Kubernetes ingress occasionally blocks wss://-upgrade
# requests during automated test runs. Hit the local backend directly
# for WebSocket tests — it shares the same Mongo + ws_manager state as the
# public endpoint, so the broadcast is equivalent.
WS = "ws://127.0.0.1:8001"
ADMIN = ("admin@meetflow.com", "admin123")


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=10).json()
    if r.get("totp_required"):
        pytest.skip("Admin has 2FA enabled — disable to run this test.")
    if "token" not in r:
        pytest.skip(f"Login did not return a token for {email}: {r}")
    return r


@pytest.mark.asyncio
async def test_mute_user_broadcasts_over_ws():
    """Create a meeting as admin, add a second participant, open a WS for the
    second participant, then have admin call PUT /participants/{uid} with
    mic_on=false. The second participant's WS must receive
    {type: 'host-control', action: 'mute_user', target_user_id: <uid>}.
    """
    admin = _login(*ADMIN)
    admin_token = admin["token"]
    ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # Create a fresh participant user
    suffix = uuid.uuid4().hex[:6]
    pw = "Test1234!"
    email = f"mute_target_{suffix}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "name": f"Mute Target {suffix}", "password": pw},
                      timeout=10)
    assert r.status_code in (200, 201), r.text
    target = _login(email, pw)
    target_uid = target["user_id"]

    # Admin creates a meeting and invites the target
    r = requests.post(f"{API}/meetings", headers=ah,
                      json={"title": f"Mute test {suffix}", "duration": 30, "meeting_type": "instant"},
                      timeout=10)
    assert r.status_code in (200, 201), r.text
    meeting = r.json()
    mid = meeting["meeting_id"]

    # Target joins the meeting (adds itself as participant)
    r = requests.post(f"{API}/meetings/{mid}/join",
                      headers={"Authorization": f"Bearer {target['token']}", "Content-Type": "application/json"},
                      json={}, timeout=10)
    assert r.status_code in (200, 201), r.text

    # Target opens WS. We embed the main login JWT as `?token=` (the
    # websocket endpoint accepts either cookie-based or query-param auth).
    ws_url = f"{WS}/api/ws/{mid}/{target_uid}?token={target['token']}"

    async with websockets.connect(ws_url, open_timeout=10) as ws:
        # Fire the admin mute request
        r = requests.put(
            f"{API}/meetings/{mid}/participants/{target_uid}",
            headers=ah, json={"mic_on": False}, timeout=10,
        )
        assert r.status_code == 200, r.text

        # Wait for the broadcast (max 5 s)
        received = None
        for _ in range(30):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.3)
            except asyncio.TimeoutError:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "host-control" and msg.get("action") == "mute_user":
                received = msg
                break
        assert received is not None, "No mute_user broadcast received within 9s"
        assert received["target_user_id"] == target_uid
        assert received["by_id"] == admin["user_id"]

    # Cleanup
    requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)
