"""License management for self-hosted MeetFlow deployments.

Goals:
 1. Kunde bekommt ein Docker-Image, das beim Start gegen einen externen
    Lizenz-Server (`LICENSE_SERVER_URL`) verifiziert, ob die installierte
    Lizenz für seine Domain/Hardware noch gültig ist.
 2. Heartbeat alle 6 h erneuert den Status. 24 h Offline-Grace gegen
    kurzzeitige Netzwerk-Ausfälle.
 3. Bei `status="invalid"` blockt die Middleware fast alle API-Calls mit 503;
    nur Login + Lizenz-Status bleiben erreichbar, damit der Admin die
    Situation diagnostizieren und ggf. neuen Key eingeben kann.

Dev-Modus: Wenn `LICENSE_SERVER_URL` leer ist, wird der Check vollständig
übersprungen — die Preview/Test-Umgebung läuft ohne externe Abhängigkeit.

Hardware-Fingerprint: SHA256 aus (uname.node, MAC-Adresse, LICENSE_KEY).
Wenn das Image auf einem anderen Host gestartet wird, schlägt die
Lizenz-Validierung fehl, sobald der Lizenz-Server den Fingerprint kennt.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import platform
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from database import db

logger = logging.getLogger("meetflow.license")

_HEARTBEAT_INTERVAL_SEC = 6 * 60 * 60  # 6 h
_OFFLINE_GRACE_SEC = 24 * 60 * 60      # 24 h
_HTTP_TIMEOUT_SEC = 10


def _hardware_fingerprint(license_key: str) -> str:
    """SHA256 über (Hostname, MAC-Adresse, License-Key).

    Nur 16 Hex-Zeichen zurückgegeben — reicht für eindeutige Identifizierung
    und ist kompakt genug für Lizenz-Server-Logs.
    """
    node = platform.node() or "unknown"
    try:
        mac = uuid.getnode()  # int repräsentation der MAC
    except Exception:
        mac = 0
    raw = f"{node}|{mac:012x}|{license_key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _load_cached_status() -> dict:
    """Lädt den letzten bekannten Lizenz-Status aus `app_settings`.

    Schema:
        {
          "status": "valid" | "invalid" | "grace" | "disabled",
          "license_key": str,
          "tenant_id": str | None,
          "valid_until": ISO-string,
          "last_check_at": ISO-string,
          "last_success_at": ISO-string,
          "message": str | None,
          "fingerprint": str,
        }
    """
    doc = await db.app_settings.find_one({"key": "license"}, {"_id": 0}) or {}
    return doc


async def _save_status(status: dict) -> None:
    status["key"] = "license"
    status["updated_at"] = _now().isoformat()
    await db.app_settings.update_one(
        {"key": "license"}, {"$set": status}, upsert=True
    )


async def _verify_with_server(license_key: str, fingerprint: str) -> dict:
    """Ruft den Lizenz-Server auf.

    Erwartet vom Server JSON wie:
        { "status": "valid", "valid_until": "2027-01-01T00:00:00Z",
          "tenant_id": "kunde-abc", "message": null }
    """
    url = os.environ.get("LICENSE_SERVER_URL", "").rstrip("/")
    if not url:
        return {"status": "disabled", "message": "LICENSE_SERVER_URL not configured"}
    payload = {
        "license_key": license_key,
        "fingerprint": fingerprint,
        "tenant_id": os.environ.get("LICENSE_TENANT_ID") or None,
        "domain": os.environ.get("LICENSE_DOMAIN") or None,
        "version": os.environ.get("APP_VERSION") or "unknown",
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as cl:
        r = await cl.post(f"{url}/verify", json=payload)
        r.raise_for_status()
        return r.json()


async def check_license(force: bool = False) -> dict:
    """Eine Verifikation gegen den Lizenz-Server.

    Mit `force=True` ignoriert es den 6-h-Cache-Throttle und fragt sofort
    neu nach. Wird auch vom `/api/admin/license` Force-Recheck verwendet.
    """
    license_key = os.environ.get("LICENSE_KEY", "").strip()
    server_url = os.environ.get("LICENSE_SERVER_URL", "").strip()

    # Dev-/Test-Modus: kein Lizenz-Server konfiguriert → check deaktivieren.
    if not server_url:
        status = {
            "status": "disabled",
            "license_key": "",
            "tenant_id": None,
            "valid_until": None,
            "last_check_at": _now().isoformat(),
            "last_success_at": _now().isoformat(),
            "message": "Lizenzpruefung deaktiviert (LICENSE_SERVER_URL nicht gesetzt)",
            "fingerprint": "",
        }
        await _save_status(status)
        return status

    if not license_key:
        status = {
            "status": "invalid",
            "license_key": "",
            "tenant_id": None,
            "valid_until": None,
            "last_check_at": _now().isoformat(),
            "last_success_at": None,
            "message": "LICENSE_KEY nicht gesetzt",
            "fingerprint": "",
        }
        await _save_status(status)
        return status

    fingerprint = _hardware_fingerprint(license_key)

    cached = await _load_cached_status()

    try:
        result = await _verify_with_server(license_key, fingerprint)
        srv_status = result.get("status") or "invalid"
        status = {
            "status": srv_status,
            "license_key": license_key[:8] + "…" if len(license_key) > 8 else license_key,
            "tenant_id": result.get("tenant_id"),
            "valid_until": result.get("valid_until"),
            "last_check_at": _now().isoformat(),
            "last_success_at": _now().isoformat() if srv_status == "valid" else cached.get("last_success_at"),
            "message": result.get("message"),
            "fingerprint": fingerprint,
        }
        await _save_status(status)
        logger.info("License check: status=%s tenant=%s", srv_status, result.get("tenant_id"))
        return status
    except Exception as e:
        # Server nicht erreichbar — Offline-Grace prüfen.
        last_success = cached.get("last_success_at")
        within_grace = False
        if last_success:
            try:
                ls = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
                within_grace = (_now() - ls).total_seconds() < _OFFLINE_GRACE_SEC
            except Exception:
                within_grace = False
        status = {
            **cached,
            "status": "grace" if within_grace else "invalid",
            "license_key": (license_key[:8] + "…") if len(license_key) > 8 else license_key,
            "last_check_at": _now().isoformat(),
            "message": f"Lizenz-Server nicht erreichbar: {e}",
            "fingerprint": fingerprint,
        }
        await _save_status(status)
        logger.warning("License check failed (grace=%s): %s", within_grace, e)
        return status


async def is_license_active() -> bool:
    """Schneller Cache-Lookup für die Middleware.

    `valid`, `grace` und `disabled` lassen die App durch; `invalid` blockt.
    """
    cached = await _load_cached_status()
    return cached.get("status") in ("valid", "grace", "disabled")


async def get_current_status() -> dict:
    """Public-API-View für den Admin-Endpoint (ohne sensible Felder)."""
    cached = await _load_cached_status()
    return {
        "status": cached.get("status") or "unknown",
        "tenant_id": cached.get("tenant_id"),
        "valid_until": cached.get("valid_until"),
        "last_check_at": cached.get("last_check_at"),
        "last_success_at": cached.get("last_success_at"),
        "message": cached.get("message"),
        "fingerprint": cached.get("fingerprint"),
        "license_key_masked": cached.get("license_key"),
        "server_configured": bool(os.environ.get("LICENSE_SERVER_URL", "").strip()),
    }


_heartbeat_task: Optional[asyncio.Task] = None


async def _heartbeat_loop() -> None:
    """Hintergrund-Task: alle 6 h gegen den Lizenz-Server prüfen."""
    while True:
        try:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SEC)
            await check_license()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("License heartbeat crashed: %s", e)


async def start_heartbeat() -> None:
    """Wird beim FastAPI-Startup einmalig aufgerufen.

    Macht einen sofortigen Check und startet danach den Heartbeat-Loop.
    """
    global _heartbeat_task
    try:
        await check_license()
    except Exception as e:
        logger.warning("Initial license check failed: %s", e)
    if _heartbeat_task is None or _heartbeat_task.done():
        _heartbeat_task = asyncio.create_task(_heartbeat_loop())
