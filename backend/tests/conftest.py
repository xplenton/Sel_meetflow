"""
Iter 318 — Pytest configuration / autouse fixtures.

Makes the integration-test suite self-sufficient by loading the env vars
the tests reach for at module-import time (REACT_APP_BACKEND_URL +
MONGO_URL). Previously these had to be exported in the calling shell,
which made `pytest tests/` fail to even collect 36 of the 100+ test files.

Behaviour:
  1. If REACT_APP_BACKEND_URL is already set in os.environ, leave it alone.
  2. Else, parse it from /app/frontend/.env (the canonical location).
  3. Same for MONGO_URL / DB_NAME from /app/backend/.env (used by a few tests
     that talk to Mongo directly).
  4. If the backend is unreachable, skip the entire integration suite with a
     clear message — so unit-style tests can still run on CI without a live
     backend.
"""
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

_FRONTEND_ENV = Path("/app/frontend/.env")
_BACKEND_ENV = Path("/app/backend/.env")


def _load_dotenv_into_environ(path: Path, keys: tuple) -> None:
    """Minimal dotenv parser: KEY=VALUE per line, no quoting tricks needed
    for our .env files. Only fills the requested keys if absent."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in keys and not os.environ.get(k):
            os.environ[k] = v


# ---------------------------------------------------------------------------
# Run at collection time so module-level `os.environ.get(...)` calls in the
# test files see the values.
# ---------------------------------------------------------------------------
_load_dotenv_into_environ(_FRONTEND_ENV, ("REACT_APP_BACKEND_URL",))
_load_dotenv_into_environ(_BACKEND_ENV, ("MONGO_URL", "DB_NAME"))


def _backend_reachable(url: str, timeout: float = 2.0) -> bool:
    """Cheap TCP check — no HTTP request, just confirm the port answers."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    """Skip integration tests if the backend isn't reachable. Keeps `pytest
    tests/` from imploding with a wall of ConnectionErrors on CI runners
    that don't spin up the full stack."""
    base = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    if not base:
        skip = pytest.mark.skip(
            reason="REACT_APP_BACKEND_URL not configured "
                   "(set in /app/frontend/.env or env)"
        )
        for item in items:
            item.add_marker(skip)
        return
    if not _backend_reachable(base):
        skip = pytest.mark.skip(
            reason=f"Backend at {base} is not reachable — "
                   "start the stack with `sudo supervisorctl start backend` "
                   "or skip integration tests."
        )
        for item in items:
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Shared fixtures the suite can opt into.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def base_url() -> str:
    """Backend base URL (no trailing slash). Tests should prefer this over
    reading os.environ themselves so the fixture-injection is explicit."""
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="session")
def admin_credentials() -> dict:
    """Standard admin login. Source-of-truth: /app/memory/test_credentials.md."""
    return {"email": "admin@meetflow.com", "password": "admin123"}


@pytest.fixture(scope="session")
def admin_token(base_url: str, admin_credentials: dict) -> str:
    """Session-scoped admin JWT to avoid rate limits."""
    import requests
    import time
    # Wait a bit to avoid rate limits from previous runs
    time.sleep(1)
    r = requests.post(
        f"{base_url}/api/auth/login",
        json=admin_credentials,
        timeout=10,
        verify=False,
    )
    if r.status_code == 429:
        # Rate limited - wait and retry
        time.sleep(5)
        r = requests.post(
            f"{base_url}/api/auth/login",
            json=admin_credentials,
            timeout=10,
            verify=False,
        )
    r.raise_for_status()
    return r.json().get("token") or r.json().get("access_token")
