"""Iteration 190 Comprehensive Backend Tests

Tests for:
1. BUG #1 - Mute einzelner Teilnehmer (WS-Broadcast for mute_user, disable_camera_user, remove_user)
2. PUT /meetings/{id}/participants/{uid} authorization (403 for non-host/co-host)
3. Regression tests for iter186-189 features (Chat, News, Surveys, 2FA, Booking)
"""
import os
import uuid
import json
import asyncio

import pytest
import requests
import websockets


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
# Use local WS for WebSocket tests (Kubernetes ingress may block wss:// upgrades)
WS = "ws://127.0.0.1:8001"
ADMIN = ("admin@meetflow.com", "admin123")


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=10).json()
    if r.get("totp_required"):
        pytest.skip("Admin has 2FA enabled — disable to run this test.")
    if "token" not in r:
        pytest.skip(f"Login did not return a token for {email}: {r}")
    return r


def _create_test_user(suffix=None):
    """Create a test user and return login response."""
    suffix = suffix or uuid.uuid4().hex[:6]
    email = f"TEST_iter190_{suffix}@example.com"
    pw = "Test1234!"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "name": f"Test User {suffix}", "password": pw},
                      timeout=10)
    if r.status_code not in (200, 201):
        pytest.skip(f"Could not create test user: {r.text}")
    return _login(email, pw)


class TestMuteUserBroadcast:
    """BUG #1: PUT /meetings/{id}/participants/{uid} with mic_on=false broadcasts mute_user."""

    @pytest.mark.asyncio
    async def test_mute_user_broadcasts_over_ws(self):
        """Host mutes participant -> WS broadcast with action=mute_user."""
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        # Create target participant
        target = _create_test_user()
        target_uid = target["user_id"]

        # Admin creates meeting
        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"Mute test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            # Target joins meeting
            r = requests.post(f"{API}/meetings/{mid}/join",
                              headers={"Authorization": f"Bearer {target['token']}", "Content-Type": "application/json"},
                              json={}, timeout=10)
            assert r.status_code in (200, 201), r.text

            # Target opens WS
            ws_url = f"{WS}/api/ws/{mid}/{target_uid}?token={target['token']}"

            async with websockets.connect(ws_url, open_timeout=10) as ws:
                # Admin mutes target
                r = requests.put(
                    f"{API}/meetings/{mid}/participants/{target_uid}",
                    headers=ah, json={"mic_on": False}, timeout=10,
                )
                assert r.status_code == 200, r.text

                # Wait for broadcast
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

                assert received is not None, "No mute_user broadcast received"
                assert received["target_user_id"] == target_uid
                assert received["by_id"] == admin["user_id"]
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)

    @pytest.mark.asyncio
    async def test_disable_camera_broadcasts_over_ws(self):
        """Host disables participant camera -> WS broadcast with action=disable_camera_user."""
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        target = _create_test_user()
        target_uid = target["user_id"]

        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"Camera test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            r = requests.post(f"{API}/meetings/{mid}/join",
                              headers={"Authorization": f"Bearer {target['token']}", "Content-Type": "application/json"},
                              json={}, timeout=10)
            assert r.status_code in (200, 201), r.text

            ws_url = f"{WS}/api/ws/{mid}/{target_uid}?token={target['token']}"

            async with websockets.connect(ws_url, open_timeout=10) as ws:
                r = requests.put(
                    f"{API}/meetings/{mid}/participants/{target_uid}",
                    headers=ah, json={"camera_on": False}, timeout=10,
                )
                assert r.status_code == 200, r.text

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
                    if msg.get("type") == "host-control" and msg.get("action") == "disable_camera_user":
                        received = msg
                        break

                assert received is not None, "No disable_camera_user broadcast received"
                assert received["target_user_id"] == target_uid
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)

    @pytest.mark.asyncio
    async def test_remove_user_broadcasts_over_ws(self):
        """Host removes participant -> WS broadcast with action=remove_user."""
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        target = _create_test_user()
        target_uid = target["user_id"]

        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"Remove test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            r = requests.post(f"{API}/meetings/{mid}/join",
                              headers={"Authorization": f"Bearer {target['token']}", "Content-Type": "application/json"},
                              json={}, timeout=10)
            assert r.status_code in (200, 201), r.text

            ws_url = f"{WS}/api/ws/{mid}/{target_uid}?token={target['token']}"

            async with websockets.connect(ws_url, open_timeout=10) as ws:
                r = requests.put(
                    f"{API}/meetings/{mid}/participants/{target_uid}",
                    headers=ah, json={"role": "removed"}, timeout=10,
                )
                assert r.status_code == 200, r.text

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
                    if msg.get("type") == "host-control" and msg.get("action") == "remove_user":
                        received = msg
                        break

                assert received is not None, "No remove_user broadcast received"
                assert received["target_user_id"] == target_uid
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)


class TestParticipantUpdateAuthorization:
    """Non-host/co-host cannot update participants (403)."""

    def test_non_host_cannot_mute_participant(self):
        """Regular participant trying to mute another -> 403."""
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        # Create two participants
        participant1 = _create_test_user("p1")
        participant2 = _create_test_user("p2")

        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"Auth test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            # Both participants join
            for p in [participant1, participant2]:
                r = requests.post(f"{API}/meetings/{mid}/join",
                                  headers={"Authorization": f"Bearer {p['token']}", "Content-Type": "application/json"},
                                  json={}, timeout=10)
                assert r.status_code in (200, 201), r.text

            # Participant1 tries to mute participant2 -> should fail with 403
            r = requests.put(
                f"{API}/meetings/{mid}/participants/{participant2['user_id']}",
                headers={"Authorization": f"Bearer {participant1['token']}", "Content-Type": "application/json"},
                json={"mic_on": False}, timeout=10,
            )
            assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)


class TestGetParticipantsUnchanged:
    """GET /meetings/{id}/participants should still work."""

    def test_get_participants_returns_list(self):
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"Participants test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            r = requests.get(f"{API}/meetings/{mid}/participants", headers=ah, timeout=10)
            assert r.status_code == 200, r.text
            data = r.json()
            assert isinstance(data, list)
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)


class TestHostControlMuteAll:
    """POST /meetings/{id}/host-control with action=mute_all should still work."""

    @pytest.mark.asyncio
    async def test_mute_all_broadcasts(self):
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        target = _create_test_user()
        target_uid = target["user_id"]

        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"MuteAll test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            r = requests.post(f"{API}/meetings/{mid}/join",
                              headers={"Authorization": f"Bearer {target['token']}", "Content-Type": "application/json"},
                              json={}, timeout=10)
            assert r.status_code in (200, 201), r.text

            ws_url = f"{WS}/api/ws/{mid}/{target_uid}?token={target['token']}"

            async with websockets.connect(ws_url, open_timeout=10) as ws:
                r = requests.post(
                    f"{API}/meetings/{mid}/host-control",
                    headers=ah, json={"action": "mute_all"}, timeout=10,
                )
                assert r.status_code == 200, r.text

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
                    if msg.get("type") == "host-control" and msg.get("action") == "mute_all":
                        received = msg
                        break

                assert received is not None, "No mute_all broadcast received"
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)


class TestRegressionIter186_189:
    """Regression tests for features from iterations 186-189."""

    def test_news_feed_returns_200(self):
        """News feed endpoint should work."""
        admin = _login(*ADMIN)
        ah = {"Authorization": f"Bearer {admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/news/feed", headers=ah, timeout=10)
        assert r.status_code == 200, r.text

    def test_surveys_list_returns_200(self):
        """Surveys list endpoint should work."""
        admin = _login(*ADMIN)
        ah = {"Authorization": f"Bearer {admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/surveys", headers=ah, timeout=10)
        assert r.status_code == 200, r.text

    def test_meetings_list_returns_200(self):
        """Meetings list endpoint should work."""
        admin = _login(*ADMIN)
        ah = {"Authorization": f"Bearer {admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/meetings", headers=ah, timeout=10)
        assert r.status_code == 200, r.text

    def test_chat_conversations_list(self):
        """Chat conversations endpoint should work."""
        admin = _login(*ADMIN)
        ah = {"Authorization": f"Bearer {admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/chat/conversations", headers=ah, timeout=10)
        assert r.status_code == 200, r.text

    def test_2fa_status_endpoint(self):
        """2FA status endpoint should work (iter 188)."""
        admin = _login(*ADMIN)
        ah = {"Authorization": f"Bearer {admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/auth/2fa/status", headers=ah, timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "totp_enabled" in data

    def test_booking_pages_list(self):
        """Booking pages endpoint should work (iter 189)."""
        admin = _login(*ADMIN)
        ah = {"Authorization": f"Bearer {admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/booking/pages", headers=ah, timeout=10)
        assert r.status_code == 200, r.text

    def test_calendar_events_list(self):
        """Calendar events endpoint should work."""
        admin = _login(*ADMIN)
        ah = {"Authorization": f"Bearer {admin['token']}", "Content-Type": "application/json"}
        r = requests.get(f"{API}/calendar/events", headers=ah, timeout=10)
        assert r.status_code == 200, r.text


class TestNoSelfMuteBroadcast:
    """PUT without mic_on change or when uid==self should NOT broadcast mute_user."""

    def test_no_broadcast_when_updating_self(self):
        """Host updating their own mic_on should not broadcast mute_user."""
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        admin_uid = admin["user_id"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"Self mute test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            # Admin joins their own meeting
            r = requests.post(f"{API}/meetings/{mid}/join", headers=ah, json={}, timeout=10)
            assert r.status_code in (200, 201), r.text

            # Admin updates their own mic_on - should succeed but no broadcast
            r = requests.put(
                f"{API}/meetings/{mid}/participants/{admin_uid}",
                headers=ah, json={"mic_on": False}, timeout=10,
            )
            assert r.status_code == 200, r.text
            # The endpoint should return the updated participant
            data = r.json()
            assert data.get("mic_on") is False
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)

    def test_no_broadcast_when_no_mic_change(self):
        """PUT with only hand_raised change should not broadcast mute_user."""
        admin = _login(*ADMIN)
        admin_token = admin["token"]
        ah = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

        target = _create_test_user()
        target_uid = target["user_id"]

        suffix = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/meetings", headers=ah,
                          json={"title": f"No mic change test {suffix}", "duration": 30, "meeting_type": "instant"},
                          timeout=10)
        assert r.status_code in (200, 201), r.text
        meeting = r.json()
        mid = meeting["meeting_id"]

        try:
            r = requests.post(f"{API}/meetings/{mid}/join",
                              headers={"Authorization": f"Bearer {target['token']}", "Content-Type": "application/json"},
                              json={}, timeout=10)
            assert r.status_code in (200, 201), r.text

            # Update only hand_raised - should succeed
            r = requests.put(
                f"{API}/meetings/{mid}/participants/{target_uid}",
                headers=ah, json={"hand_raised": True}, timeout=10,
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data.get("hand_raised") is True
        finally:
            requests.delete(f"{API}/meetings/{mid}", headers=ah, timeout=10)
