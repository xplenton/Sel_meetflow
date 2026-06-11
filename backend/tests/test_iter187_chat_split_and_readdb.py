"""Iter 187 — verify the chat package refactor + read_db scaling.

* Chat: previously a single 1462-line `routes/chat.py` monolith was split
  into the package `routes/chat/`. Backward-compat exports must still work.
* DB: `database.read_db` must exist and be a Motor handle with
  ReadPreference.SECONDARY_PREFERRED. Heavy read endpoints must still
  return correct data.
"""
import os
import requests


def _api() -> str:
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/") + "/api"
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/") + "/api"
    except Exception:
        pass
    return "http://localhost:8001/api"


API = _api()


def _login() -> str:
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@meetflow.com", "password": "admin123"},
                      timeout=10)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


# ---------- Chat package re-exports ----------------------------------------

def test_chat_package_reexports_router_and_chat_ws():
    """Legacy import paths used widely in services/routes must still work."""
    from routes.chat import router, chat_ws  # noqa: F401
    from routes.chat import ChatWSManager     # noqa: F401
    # Helpers used by other modules (some are imported lazily, but the names
    # must be accessible from the package root for the existing imports).
    from routes.chat import _send_system_message  # noqa: F401
    assert router is not None
    assert chat_ws is not None


def test_chat_routes_still_register():
    """Hit a representative GET endpoint from each sub-module."""
    token = _login()
    h = {"Authorization": f"Bearer {token}"}
    # one endpoint per sub-module:
    paths = {
        "conversations.py": "/chat/conversations",
        "messages.py": "/chat/search?q=test",
        "presence.py": "/chat/my-status",
        "search.py": "/chat/users",
        "bots.py": "/chat/bots",
        "presence/global": "/chat/presence",
        "unread-summary": "/chat/unread-summary",
    }
    for label, p in paths.items():
        r = requests.get(f"{API}{p}", headers=h, timeout=10)
        assert r.status_code == 200, f"{label} broken after refactor: {r.status_code} {r.text[:200]}"


# ---------- read_db handle --------------------------------------------------

def test_read_db_exposes_secondary_preferred():
    from database import read_db, db
    from pymongo.read_preferences import ReadPreference
    assert read_db.client is db.client, "read_db must share the same client"
    assert read_db.read_preference == ReadPreference.SECONDARY_PREFERRED, \
        f"unexpected pref: {read_db.read_preference}"


def test_news_feed_returns_data_via_read_db():
    """The feed handler now uses read_db. Results must remain correct."""
    token = _login()
    r = requests.get(f"{API}/news/feed?limit=5",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "posts" in body and "total" in body
    assert isinstance(body["posts"], list)


def test_meetings_list_via_read_db():
    token = _login()
    r = requests.get(f"{API}/meetings?limit=3",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "meetings" in body and "total" in body
    assert isinstance(body["meetings"], list)


def test_surveys_list_via_read_db():
    token = _login()
    r = requests.get(f"{API}/surveys",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
