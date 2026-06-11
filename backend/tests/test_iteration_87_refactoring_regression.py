"""
Iteration 87 - Backend Refactoring Regression Tests
====================================================
Tests all endpoints from the refactored meetings and news modules:
- meetings/core.py: CRUD, join/leave, chat, AI summarize, polls, questions, breakout rooms
- meetings/ops.py: recordings, transcripts, invitations, notifications, recurring, templates, branding
- meetings/reports.py: CSV/PDF reports, lobby, host-control, consent
- meetings/live.py: live recording/transcript, breakout live, org, attendance, insights, action items, calendar, dashboard, focus-times
- news/posts.py: categories, feed, posts CRUD, reads, reactions, comments, stats
- news/workflow.py: approval workflow, Q&A, sentiment, translations, reports
- news/push.py: push subscribe/send/status
- Busy slots (from Iter 86) should still work
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://video-meet-pro.preview.emergentagent.com"

ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASSWORD = "admin123"


class TestAuthAndSetup:
    """Authentication and basic setup tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_token(self, session):
        """Login and get auth token"""
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        assert "token" in data, "No token in login response"
        return data["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_auth_me(self, session, auth_headers):
        """Verify auth/me works"""
        resp = session.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("email") == ADMIN_EMAIL


# ============ MEETINGS/CORE.PY TESTS ============

class TestMeetingsCore:
    """Tests for meetings/core.py - CRUD, join/leave, chat, polls, questions, breakout rooms"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_meeting(self, session, auth_headers):
        """Create a test meeting for subsequent tests"""
        resp = session.post(f"{BASE_URL}/api/meetings", headers=auth_headers, json={
            "title": f"TEST_Regression_Meeting_{uuid.uuid4().hex[:6]}",
            "description": "Regression test meeting",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "duration_minutes": 60
        })
        assert resp.status_code == 200, f"Create meeting failed: {resp.text}"
        return resp.json()
    
    def test_create_meeting(self, session, auth_headers):
        """POST /api/meetings - Create meeting"""
        resp = session.post(f"{BASE_URL}/api/meetings", headers=auth_headers, json={
            "title": f"TEST_Create_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "meeting_id" in data
        assert "meeting_code" in data
    
    def test_list_meetings(self, session, auth_headers, test_meeting):
        """GET /api/meetings - List meetings"""
        resp = session.get(f"{BASE_URL}/api/meetings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "meetings" in data
        assert "total" in data
    
    def test_get_meeting(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id} - Get single meeting"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["meeting_id"] == mid
    
    def test_update_meeting(self, session, auth_headers, test_meeting):
        """PUT /api/meetings/{meeting_id} - Update meeting"""
        mid = test_meeting["meeting_id"]
        resp = session.put(f"{BASE_URL}/api/meetings/{mid}", headers=auth_headers, json={
            "title": "TEST_Updated_Title"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "TEST_Updated_Title"
    
    def test_join_meeting(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/join - Join meeting"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/join", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
    
    def test_leave_meeting(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/leave - Leave meeting"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/leave", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_get_participants(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/participants"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/participants", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_send_chat_message(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/chat - Send chat message"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/chat", headers=auth_headers, json={
            "message": "TEST_Chat_Message",
            "message_type": "text"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "TEST_Chat_Message"
    
    def test_get_chat_messages(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/chat - Get chat messages"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/chat", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_create_poll(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/polls - Create poll"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/polls", headers=auth_headers, json={
            "question": "TEST_Poll_Question?",
            "options": ["Option A", "Option B", "Option C"]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "poll_id" in data
        return data
    
    def test_get_polls(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/polls - Get polls"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/polls", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_create_question(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/questions - Create question"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/questions", headers=auth_headers, json={
            "text": "TEST_Question_Text?"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "question_id" in data
    
    def test_get_questions(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/questions - Get questions"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/questions", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_create_breakout_room(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/breakout-rooms - Create breakout room"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/breakout-rooms", headers=auth_headers, json={
            "name": "TEST_Breakout_Room",
            "participant_ids": []
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "room_id" in data
    
    def test_get_breakout_rooms(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/breakout-rooms - Get breakout rooms"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/breakout-rooms", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_delete_meeting(self, session, auth_headers):
        """DELETE /api/meetings/{meeting_id} - Delete meeting"""
        # Create a meeting to delete
        resp = session.post(f"{BASE_URL}/api/meetings", headers=auth_headers, json={
            "title": f"TEST_ToDelete_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        })
        assert resp.status_code == 200
        mid = resp.json()["meeting_id"]
        
        # Delete it
        resp = session.delete(f"{BASE_URL}/api/meetings/{mid}", headers=auth_headers)
        assert resp.status_code == 200
        
        # Verify deleted
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}", headers=auth_headers)
        assert resp.status_code == 404


# ============ MEETINGS/OPS.PY TESTS ============

class TestMeetingsOps:
    """Tests for meetings/ops.py - recordings, transcripts, notifications, recurring, templates, branding"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_meeting(self, session, auth_headers):
        resp = session.post(f"{BASE_URL}/api/meetings", headers=auth_headers, json={
            "title": f"TEST_Ops_Meeting_{uuid.uuid4().hex[:6]}",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "duration_minutes": 30
        })
        assert resp.status_code == 200
        return resp.json()
    
    def test_list_recordings(self, session, auth_headers):
        """GET /api/recordings - List recordings"""
        resp = session.get(f"{BASE_URL}/api/recordings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "recordings" in data
    
    def test_list_transcripts(self, session, auth_headers):
        """GET /api/transcripts - List transcripts"""
        resp = session.get(f"{BASE_URL}/api/transcripts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "transcripts" in data
    
    def test_create_recording(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/recordings - Create recording"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/recordings", headers=auth_headers, json={
            "title": "TEST_Recording",
            "url": "https://example.com/recording.mp4",
            "duration": 30
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "recording_id" in data
    
    def test_create_transcript(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/transcripts - Create transcript"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/transcripts", headers=auth_headers, json={
            "content": "TEST_Transcript_Content"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "transcript_id" in data
    
    def test_invite_to_meeting(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/invite - Invite to meeting"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/invite", headers=auth_headers, json={
            "emails": ["test_invite@example.com"],
            "message": "Please join our meeting"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "invited" in data
    
    def test_get_notifications(self, session, auth_headers):
        """GET /api/notifications - Get notifications"""
        resp = session.get(f"{BASE_URL}/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_get_unread_count(self, session, auth_headers):
        """GET /api/notifications/unread-count - Get unread count"""
        resp = session.get(f"{BASE_URL}/api/notifications/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
    
    def test_mark_all_read(self, session, auth_headers):
        """PUT /api/notifications/read-all - Mark all as read"""
        resp = session.put(f"{BASE_URL}/api/notifications/read-all", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_create_template(self, session, auth_headers):
        """POST /api/templates - Create template"""
        resp = session.post(f"{BASE_URL}/api/templates", headers=auth_headers, json={
            "name": f"TEST_Template_{uuid.uuid4().hex[:6]}",
            "title": "Test Meeting Template",
            "description": "A test template",
            "duration": 60,
            "meeting_mode": "standard"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "template_id" in data
        return data
    
    def test_list_templates(self, session, auth_headers):
        """GET /api/templates - List templates"""
        resp = session.get(f"{BASE_URL}/api/templates", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_get_branding(self, session, auth_headers):
        """GET /api/organization/branding - Get branding"""
        resp = session.get(f"{BASE_URL}/api/organization/branding", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "company_name" in data
    
    def test_update_branding(self, session, auth_headers):
        """PUT /api/organization/branding - Update branding"""
        resp = session.put(f"{BASE_URL}/api/organization/branding", headers=auth_headers, json={
            "company_name": "MeetFlow Test"
        })
        assert resp.status_code == 200
    
    def test_get_mode_config(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/mode-config - Get mode config"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/mode-config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "mode" in data


# ============ MEETINGS/REPORTS.PY TESTS ============

class TestMeetingsReports:
    """Tests for meetings/reports.py - CSV/PDF reports, lobby, host-control, consent"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_meeting(self, session, auth_headers):
        resp = session.post(f"{BASE_URL}/api/meetings", headers=auth_headers, json={
            "title": f"TEST_Reports_Meeting_{uuid.uuid4().hex[:6]}",
            "meeting_type": "scheduled",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
            "duration_minutes": 45,
            "lobby_enabled": True
        })
        assert resp.status_code == 200
        return resp.json()
    
    def test_meeting_report_csv(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/report/csv - Get CSV report"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/report/csv", headers=auth_headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
    
    def test_meeting_report_pdf(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/report/pdf - Get PDF report"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/report/pdf", headers=auth_headers)
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("content-type", "")
    
    def test_get_lobby(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/lobby - Get lobby"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/lobby", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_join_lobby(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/join-lobby - Join lobby"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/join-lobby", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "lobby" in data or "status" in data
    
    def test_lobby_status(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/lobby-status - Check lobby status"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/lobby-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
    
    def test_host_control_mute_all(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/host-control - Host control mute_all"""
        mid = test_meeting["meeting_id"]
        # First join as host
        session.post(f"{BASE_URL}/api/meetings/{mid}/join", headers=auth_headers)
        
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/host-control", headers=auth_headers, json={
            "action": "mute_all"
        })
        assert resp.status_code == 200
    
    def test_recording_request(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/recording/request - Request recording consent"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/recording/request", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
    
    def test_transcript_request(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/transcript/request - Request transcript consent"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/transcript/request", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
    
    def test_get_active_consents(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/consent/active - Get active consents"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/consent/active", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ============ MEETINGS/LIVE.PY TESTS ============

class TestMeetingsLive:
    """Tests for meetings/live.py - live recording/transcript, breakout live, org, attendance, insights, action items, calendar, dashboard, focus-times"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_meeting(self, session, auth_headers):
        resp = session.post(f"{BASE_URL}/api/meetings", headers=auth_headers, json={
            "title": f"TEST_Live_Meeting_{uuid.uuid4().hex[:6]}",
            "meeting_type": "instant"
        })
        assert resp.status_code == 200
        return resp.json()
    
    def test_start_recording(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/recording/start - Start recording"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/recording/start", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_stop_recording(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/recording/stop - Stop recording"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/recording/stop", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "recording_id" in data
    
    def test_start_transcript(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/transcript/start - Start transcript"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/transcript/start", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_stop_transcript(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/transcript/stop - Stop transcript"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/transcript/stop", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "transcript_id" in data
    
    def test_get_organization(self, session, auth_headers):
        """GET /api/organization - Get organization"""
        resp = session.get(f"{BASE_URL}/api/organization", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
    
    def test_update_organization(self, session, auth_headers):
        """PUT /api/organization - Update organization"""
        resp = session.put(f"{BASE_URL}/api/organization", headers=auth_headers, json={
            "name": "MeetFlow Test Org",
            "domain": "meetflow.test",
            "description": "Test organization"
        })
        assert resp.status_code == 200
    
    def test_get_attendance(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/attendance - Get attendance"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/attendance", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
    
    def test_log_attendance(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/attendance - Log attendance event"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/attendance", headers=auth_headers, json={
            "event_type": "join"
        })
        assert resp.status_code == 200
    
    def test_get_insights(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/insights - Get insights"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/insights", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_create_action_item(self, session, auth_headers, test_meeting):
        """POST /api/meetings/{meeting_id}/action-items - Create action item"""
        mid = test_meeting["meeting_id"]
        resp = session.post(f"{BASE_URL}/api/meetings/{mid}/action-items", headers=auth_headers, json={
            "text": "TEST_Action_Item",
            "assignee_id": None,
            "due_date": None
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "item_id" in data
    
    def test_list_action_items(self, session, auth_headers, test_meeting):
        """GET /api/meetings/{meeting_id}/action-items - List action items"""
        mid = test_meeting["meeting_id"]
        resp = session.get(f"{BASE_URL}/api/meetings/{mid}/action-items", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_get_calendar_events(self, session, auth_headers):
        """GET /api/calendar/events - Get calendar events"""
        resp = session.get(f"{BASE_URL}/api/calendar/events", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_get_dashboard_stats(self, session, auth_headers):
        """GET /api/dashboard/stats - Get dashboard stats"""
        resp = session.get(f"{BASE_URL}/api/dashboard/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_meetings" in data
    
    def test_get_dashboard_agenda(self, session, auth_headers):
        """GET /api/dashboard/agenda - Get dashboard agenda"""
        resp = session.get(f"{BASE_URL}/api/dashboard/agenda", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "today" in data
    
    def test_get_focus_times(self, session, auth_headers):
        """GET /api/focus-times - Get focus times"""
        resp = session.get(f"{BASE_URL}/api/focus-times", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_create_focus_time(self, session, auth_headers):
        """POST /api/focus-times - Create focus time"""
        start = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        resp = session.post(f"{BASE_URL}/api/focus-times", headers=auth_headers, json={
            "label": "TEST_Focus_Time",
            "start_time": start,
            "end_time": end
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "focus_id" in data
        return data
    
    def test_get_active_focus(self, session, auth_headers):
        """GET /api/focus-times/active - Get active focus time"""
        resp = session.get(f"{BASE_URL}/api/focus-times/active", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "active" in data


# ============ NEWS/POSTS.PY TESTS ============

class TestNewsPosts:
    """Tests for news/posts.py - categories, feed, posts CRUD, reads, reactions, comments, stats"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_post(self, session, auth_headers):
        """Create a test news post"""
        resp = session.post(f"{BASE_URL}/api/news/posts", headers=auth_headers, json={
            "title": f"TEST_News_Post_{uuid.uuid4().hex[:6]}",
            "content": "Test news content",
            "status": "published",
            "target_all": True
        })
        assert resp.status_code == 200
        return resp.json()
    
    def test_list_categories(self, session, auth_headers):
        """GET /api/news/categories - List categories"""
        resp = session.get(f"{BASE_URL}/api/news/categories", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_create_category(self, session, auth_headers):
        """POST /api/news/categories - Create category"""
        resp = session.post(f"{BASE_URL}/api/news/categories", headers=auth_headers, json={
            "name": f"TEST_Category_{uuid.uuid4().hex[:6]}",
            "color": "#FF5733"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "category_id" in data
    
    def test_get_news_feed(self, session, auth_headers):
        """GET /api/news/feed - Get news feed"""
        resp = session.get(f"{BASE_URL}/api/news/feed", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "posts" in data
        assert "total" in data
    
    def test_create_news_post(self, session, auth_headers):
        """POST /api/news/posts - Create news post"""
        resp = session.post(f"{BASE_URL}/api/news/posts", headers=auth_headers, json={
            "title": f"TEST_Create_Post_{uuid.uuid4().hex[:6]}",
            "content": "Test content",
            "status": "draft"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "post_id" in data
    
    def test_get_news_post(self, session, auth_headers, test_post):
        """GET /api/news/posts/{post_id} - Get news post"""
        pid = test_post["post_id"]
        resp = session.get(f"{BASE_URL}/api/news/posts/{pid}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["post_id"] == pid
    
    def test_update_news_post(self, session, auth_headers, test_post):
        """PUT /api/news/posts/{post_id} - Update news post"""
        pid = test_post["post_id"]
        resp = session.put(f"{BASE_URL}/api/news/posts/{pid}", headers=auth_headers, json={
            "title": "TEST_Updated_Title"
        })
        assert resp.status_code == 200
    
    def test_mark_as_read(self, session, auth_headers, test_post):
        """POST /api/news/posts/{post_id}/read - Mark as read"""
        pid = test_post["post_id"]
        resp = session.post(f"{BASE_URL}/api/news/posts/{pid}/read", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_get_read_receipts(self, session, auth_headers, test_post):
        """GET /api/news/posts/{post_id}/reads - Get read receipts"""
        pid = test_post["post_id"]
        resp = session.get(f"{BASE_URL}/api/news/posts/{pid}/reads", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "reads" in data
    
    def test_toggle_reaction(self, session, auth_headers, test_post):
        """POST /api/news/posts/{post_id}/reactions - Toggle reaction"""
        pid = test_post["post_id"]
        resp = session.post(f"{BASE_URL}/api/news/posts/{pid}/reactions", headers=auth_headers, json={
            "reaction_type": "like"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "action" in data
    
    def test_add_comment(self, session, auth_headers, test_post):
        """POST /api/news/posts/{post_id}/comments - Add comment"""
        pid = test_post["post_id"]
        resp = session.post(f"{BASE_URL}/api/news/posts/{pid}/comments", headers=auth_headers, json={
            "content": "TEST_Comment"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "comment_id" in data
    
    def test_get_comments(self, session, auth_headers, test_post):
        """GET /api/news/posts/{post_id}/comments - Get comments"""
        pid = test_post["post_id"]
        resp = session.get(f"{BASE_URL}/api/news/posts/{pid}/comments", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_get_news_stats(self, session, auth_headers):
        """GET /api/news/stats - Get news stats"""
        resp = session.get(f"{BASE_URL}/api/news/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
    
    def test_get_unread_count(self, session, auth_headers):
        """GET /api/news/unread-count - Get unread count"""
        resp = session.get(f"{BASE_URL}/api/news/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "unread" in data
    
    def test_editorial_calendar(self, session, auth_headers):
        """GET /api/news/editorial-calendar - Get editorial calendar"""
        resp = session.get(f"{BASE_URL}/api/news/editorial-calendar", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
    
    def test_get_governance(self, session, auth_headers, test_post):
        """GET /api/news/posts/{post_id}/governance - Get governance"""
        pid = test_post["post_id"]
        resp = session.get(f"{BASE_URL}/api/news/posts/{pid}/governance", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "post" in data


# ============ NEWS/WORKFLOW.PY TESTS ============

class TestNewsWorkflow:
    """Tests for news/workflow.py - approval workflow, Q&A, sentiment, translations, reports"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def draft_post(self, session, auth_headers):
        """Create a draft post for workflow tests"""
        resp = session.post(f"{BASE_URL}/api/news/posts", headers=auth_headers, json={
            "title": f"TEST_Workflow_Post_{uuid.uuid4().hex[:6]}",
            "content": "Test workflow content",
            "status": "draft"
        })
        assert resp.status_code == 200
        return resp.json()
    
    def test_submit_for_review(self, session, auth_headers, draft_post):
        """POST /api/news/posts/{post_id}/submit-review - Submit for review"""
        pid = draft_post["post_id"]
        resp = session.post(f"{BASE_URL}/api/news/posts/{pid}/submit-review", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "review"
    
    def test_get_approval_queue(self, session, auth_headers):
        """GET /api/news/approval-queue - Get approval queue"""
        resp = session.get(f"{BASE_URL}/api/news/approval-queue", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_approve_review(self, session, auth_headers, draft_post):
        """POST /api/news/posts/{post_id}/approve-review - Approve review"""
        pid = draft_post["post_id"]
        resp = session.post(f"{BASE_URL}/api/news/posts/{pid}/approve-review", headers=auth_headers, json={
            "comment": "Approved for testing"
        })
        assert resp.status_code == 200
    
    def test_get_audit_trail(self, session, auth_headers, draft_post):
        """GET /api/news/audit/{post_id} - Get audit trail"""
        pid = draft_post["post_id"]
        resp = session.get(f"{BASE_URL}/api/news/audit/{pid}", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_list_all_audit(self, session, auth_headers):
        """GET /api/news/audit - List all audit"""
        resp = session.get(f"{BASE_URL}/api/news/audit", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_interaction_stats(self, session, auth_headers):
        """GET /api/news/interaction-stats - Get interaction stats"""
        resp = session.get(f"{BASE_URL}/api/news/interaction-stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "posts" in data
    
    def test_ask_question(self, session, auth_headers, draft_post):
        """POST /api/news/posts/{post_id}/questions - Ask question"""
        pid = draft_post["post_id"]
        resp = session.post(f"{BASE_URL}/api/news/posts/{pid}/questions", headers=auth_headers, json={
            "text": "TEST_Question?"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "question_id" in data
        return data
    
    def test_get_questions(self, session, auth_headers, draft_post):
        """GET /api/news/posts/{post_id}/questions - Get questions"""
        pid = draft_post["post_id"]
        resp = session.get(f"{BASE_URL}/api/news/posts/{pid}/questions", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_set_translations(self, session, auth_headers, draft_post):
        """PUT /api/news/posts/{post_id}/translations - Set translations"""
        pid = draft_post["post_id"]
        resp = session.put(f"{BASE_URL}/api/news/posts/{pid}/translations", headers=auth_headers, json={
            "en": {"title": "English Title", "content": "English content", "excerpt": ""},
            "de": {"title": "German Title", "content": "German content", "excerpt": ""}
        })
        assert resp.status_code == 200
    
    def test_get_localized_post(self, session, auth_headers, draft_post):
        """GET /api/news/posts/{post_id}/localized - Get localized post"""
        pid = draft_post["post_id"]
        resp = session.get(f"{BASE_URL}/api/news/posts/{pid}/localized?lang=en", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_report_content(self, session, auth_headers, draft_post):
        """POST /api/news/report - Report content"""
        pid = draft_post["post_id"]
        resp = session.post(f"{BASE_URL}/api/news/report", headers=auth_headers, json={
            "content_type": "post",
            "content_id": pid,
            "reason": "TEST_Report"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "report_id" in data
    
    def test_list_reports(self, session, auth_headers):
        """GET /api/news/reports - List reports"""
        resp = session.get(f"{BASE_URL}/api/news/reports", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_pending_reports_count(self, session, auth_headers):
        """GET /api/news/reports/pending-count - Get pending reports count"""
        resp = session.get(f"{BASE_URL}/api/news/reports/pending-count", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data


# ============ NEWS/PUSH.PY TESTS ============

class TestNewsPush:
    """Tests for news/push.py - push subscribe/send/status"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    def test_get_vapid_key(self, session, auth_headers):
        """GET /api/news/push/vapid-public-key - Get VAPID key"""
        resp = session.get(f"{BASE_URL}/api/news/push/vapid-public-key", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "public_key" in data
    
    def test_push_subscribe(self, session, auth_headers):
        """POST /api/news/push/subscribe - Subscribe to push"""
        resp = session.post(f"{BASE_URL}/api/news/push/subscribe", headers=auth_headers, json={
            "subscription": {
                "endpoint": f"https://test.example.com/push/{uuid.uuid4().hex}",
                "keys": {"p256dh": "test", "auth": "test"}
            }
        })
        assert resp.status_code == 200
    
    def test_push_status(self, session, auth_headers):
        """GET /api/news/push/status - Get push status"""
        resp = session.get(f"{BASE_URL}/api/news/push/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "subscribed" in data
    
    def test_list_push_notifications(self, session, auth_headers):
        """GET /api/news/push/notifications - List push notifications"""
        resp = session.get(f"{BASE_URL}/api/news/push/notifications", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ============ BUSY SLOTS (FROM ITER 86) ============

class TestBusySlots:
    """Tests for busy slots feature (from Iteration 86) - should still work after refactoring"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    def test_create_busy_slot(self, session, auth_headers):
        """POST /api/users/me/busy-slots - Create busy slot"""
        start = (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=11)).isoformat()
        resp = session.post(f"{BASE_URL}/api/users/me/busy-slots", headers=auth_headers, json={
            "start": start,
            "end": end,
            "label": "TEST_Busy_Slot"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "slot_id" in data
        return data
    
    def test_list_busy_slots(self, session, auth_headers):
        """GET /api/users/me/busy-slots - List busy slots"""
        resp = session.get(f"{BASE_URL}/api/users/me/busy-slots", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_delete_busy_slot(self, session, auth_headers):
        """DELETE /api/users/me/busy-slots/{slot_id} - Delete busy slot"""
        # Create a slot to delete
        start = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=13)).isoformat()
        resp = session.post(f"{BASE_URL}/api/users/me/busy-slots", headers=auth_headers, json={
            "start": start,
            "end": end,
            "label": "TEST_ToDelete"
        })
        assert resp.status_code == 200
        slot_id = resp.json()["slot_id"]
        
        # Delete it
        resp = session.delete(f"{BASE_URL}/api/users/me/busy-slots/{slot_id}", headers=auth_headers)
        assert resp.status_code == 200


# ============ SMOKE REGRESSION TESTS ============

class TestSmokeRegression:
    """Quick smoke tests to verify other core functionality still works"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_headers(self, session):
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        return {"Authorization": f"Bearer {resp.json()['token']}"}
    
    def test_auth_me(self, session, auth_headers):
        """GET /api/auth/me - Auth still works"""
        resp = session.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_schedule_polls(self, session, auth_headers):
        """GET /api/schedule-polls - Schedule polls still works"""
        resp = session.get(f"{BASE_URL}/api/schedule-polls", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_surveys(self, session, auth_headers):
        """GET /api/surveys - Surveys still works"""
        resp = session.get(f"{BASE_URL}/api/surveys", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_conversations(self, session, auth_headers):
        """GET /api/conversations - Chat conversations still works"""
        resp = session.get(f"{BASE_URL}/api/conversations", headers=auth_headers)
        assert resp.status_code == 200
    
    def test_users_list(self, session, auth_headers):
        """GET /api/users - Users list still works"""
        resp = session.get(f"{BASE_URL}/api/users", headers=auth_headers)
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
