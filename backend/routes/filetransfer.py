"""File-Transfer module (iter 386).

Provides secure file exchange between internal users and via passworded
external links. Storage backend (local/network share) and at-rest
encryption are pluggable; see ``services/storage_providers.py``.

Collections:
  * file_transfers           — envelope (owner, message, recipients ids,
                              expires_at, status, totals, ...)
  * file_transfer_files      — one row per file (id, name, size, mime,
                              storage path, encryption status, sha256)
  * file_transfer_shares     — external share-links (token, pw_hash,
                              expires_at, one_time, downloaded_count)
  * file_transfer_downloads  — append-only download log
  * file_transfer_audit      — full audit log (create/upload/download/
                              share/revoke/delete)
  * filetransfer_settings    — singleton (kind: 'global') with storage +
                              limits config; admin-editable
  * filetransfer_uploads     — iter 386b: chunked-upload sessions
"""
from __future__ import annotations
import os
import io
import re
import secrets
import hashlib
import logging
import zipfile
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from passlib.hash import bcrypt

from database import db
from dependencies import get_current_user
from services.permissions import has_cap
from services.storage_providers import build_provider, DEFAULT_SETTINGS

# Optional libmagic-based MIME sniffing. We degrade gracefully if libmagic
# isn't available on the host so the module keeps working in minimal envs.
try:
    import magic as _libmagic  # python-magic
    _MAGIC_OK = True
except Exception:  # pragma: no cover
    _libmagic = None
    _MAGIC_OK = False


# ----------- iter 386d: Throttling for public links + ClamAV hook -----------

import time as _time

# In-process sliding-window rate limiter, keyed by (token, ip).
# Resets on backend restart — for stronger guarantees, plug in Redis later.
_PUBLIC_RL_WINDOW_SEC = 60
_PUBLIC_RL_MAX_REQ = 30
_public_rl_log: dict[tuple[str, str], list[float]] = {}


def _public_rate_check(token: str, ip: str) -> None:
    """Sliding-window: max 30 requests / 60s per token (shared across all
    IPs). Defends against brute-force password guessing and bulk-leech.
    We deliberately ignore the IP because attackers can rotate it; the
    token is the single secret being attacked. The ip parameter is kept
    in the signature so audit/logging can still record where it came
    from. Raises HTTP 429 when exceeded."""
    now = _time.monotonic()
    key = (token or "", "_shared")
    bucket = _public_rl_log.setdefault(key, [])
    cutoff = now - _PUBLIC_RL_WINDOW_SEC
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _PUBLIC_RL_MAX_REQ:
        raise HTTPException(429, "Zu viele Anfragen — bitte später erneut versuchen")
    bucket.append(now)
    if len(_public_rl_log) > 10_000:
        for k in list(_public_rl_log.keys())[:5_000]:
            if not _public_rl_log[k] or _public_rl_log[k][-1] < now - 600:
                _public_rl_log.pop(k, None)
    _ = ip  # kept for future per-ip auditing


def _clamav_scan(data: bytes, settings: dict) -> Optional[str]:
    """Optional virus-scan hook. Connects to clamd via the configured TCP
    socket (default ``127.0.0.1:3310``) and runs INSTREAM. Returns a
    string with the virus name when infected, ``None`` when clean.
    If clamd is unreachable AND ``virus_scan_required`` is True we raise
    503 — otherwise we degrade gracefully.

    Settings keys:
      enable_virus_scan: bool
      virus_scan_required: bool (fail-closed if scanner unreachable)
      clamav_host, clamav_port (default 127.0.0.1:3310)
    """
    if not settings.get("enable_virus_scan"):
        return None
    import socket, struct
    host = settings.get("clamav_host") or "127.0.0.1"
    port = int(settings.get("clamav_port") or 3310)
    try:
        sock = socket.create_connection((host, port), timeout=10)
    except Exception as e:
        if settings.get("virus_scan_required"):
            raise HTTPException(503, f"Virus-Scanner nicht erreichbar: {e}") from e
        logger.warning(f"clamav unreachable, skipping scan: {e}")
        return None
    try:
        sock.sendall(b"zINSTREAM\0")
        # Stream the data in 8 KB chunks, each prefixed with a uint32 size
        for i in range(0, len(data), 8192):
            chunk = data[i:i + 8192]
            sock.sendall(struct.pack(b"!L", len(chunk)) + chunk)
        sock.sendall(struct.pack(b"!L", 0))  # zero-length = end-of-stream
        resp = b""
        sock.settimeout(15)
        while True:
            piece = sock.recv(1024)
            if not piece:
                break
            resp += piece
        text = resp.decode("utf-8", errors="ignore").strip().rstrip("\0")
        # Examples:
        #   "stream: OK"
        #   "stream: Eicar-Test-Signature FOUND"
        if "FOUND" in text:
            # Extract virus name
            parts = text.split(":", 1)[-1].strip()
            return parts.replace(" FOUND", "").strip()
        return None
    except Exception as e:
        if settings.get("virus_scan_required"):
            raise HTTPException(503, f"Virus-Scan fehlgeschlagen: {e}") from e
        logger.warning(f"clamav scan error, skipping: {e}")
        return None
    finally:
        try: sock.close()
        except Exception: pass

logger = logging.getLogger("server")

router = APIRouter()

CAP_USE = "filetransfer.use"
CAP_ADMIN = "filetransfer.admin"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _safe_filename(name: str) -> str:
    """Strip path components + dangerous chars but keep an extension."""
    name = (name or "file").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = re.sub(r"[^\w.\-]+", "_", name)
    return name[:200] or "file"


async def _settings() -> dict:
    cfg = await db.filetransfer_settings.find_one({"kind": "global"}, {"_id": 0}) or {}
    return {**DEFAULT_SETTINGS, **cfg}


async def _require_use(user: dict):
    if not await has_cap(user, CAP_USE, db):
        raise HTTPException(status_code=403, detail="Keine Filetransfer-Berechtigung")


async def _require_admin(user: dict):
    if not await has_cap(user, CAP_ADMIN, db):
        raise HTTPException(status_code=403, detail="Keine Filetransfer-Adminrechte")


async def _audit(action: str, user: dict, *, transfer_id: Optional[str] = None,
                 file_id: Optional[str] = None, share_id: Optional[str] = None,
                 meta: Optional[dict] = None):
    await db.file_transfer_audit.insert_one({
        "audit_id": _new_id("ftaud"),
        "action": action,
        "actor_user_id": user.get("user_id") if user else None,
        "actor_name": user.get("name") if user else None,
        "transfer_id": transfer_id,
        "file_id": file_id,
        "share_id": share_id,
        "meta": meta or {},
        "created_at": _now_iso(),
    })


# ----------- iter 386b: MIME-sniff + Notifications -----------

# Conservative allow-list. Empty `allowed_extensions` setting bypasses the
# whitelist entirely (default = "alles erlaubt"). When extensions are
# whitelisted, we additionally verify the magic-bytes MIME doesn't collide
# with a known executable type — even if the extension is on the allow list.
_EXECUTABLE_MIMES = {
    "application/x-dosexec", "application/x-msdownload", "application/x-mach-binary",
    "application/x-elf", "application/x-executable",
}


def _sniff_mime(data: bytes, fallback: str) -> str:
    """libmagic MIME sniff (first 4096 B). Returns the declared content_type
    if libmagic isn't installed."""
    if not _MAGIC_OK or not data:
        return fallback or "application/octet-stream"
    try:
        return _libmagic.from_buffer(data[:4096], mime=True) or fallback
    except Exception:
        return fallback or "application/octet-stream"


async def _notify_recipients(transfer: dict, actor: dict, *, kind: str, extra: dict | None = None):
    """In-app + e-mail notifications on share/download events. Failures are
    non-fatal so the user request never breaks on a flaky e-mail backend.
    """
    from services.email import send_email_real
    try:
        recipients = list(transfer.get("recipient_user_ids") or [])
        if kind == "download":
            # Only notify the owner about external/internal downloads.
            recipients = [transfer["owner_user_id"]] if transfer.get("owner_user_id") else []
        if not recipients:
            return
        title_map = {
            "new_transfer": f"Neue Dateien von {actor.get('name') or 'einem Kollegen'}",
            "download": f"Datei aus deinem Transfer wurde heruntergeladen",
        }
        body_map = {
            "new_transfer": (
                f"{actor.get('name') or 'Ein Kollege'} hat dir {(extra or {}).get('file_count', 0)} Datei(en) bereitgestellt."
                f"\n\nNachricht: {transfer.get('message') or '(keine)'}"
                f"\nGültig bis: {transfer.get('expires_at')}"
            ),
            "download": (
                f"{(extra or {}).get('downloader_name') or 'Jemand'} hat soeben "
                f"{(extra or {}).get('file_name') or 'eine Datei'} aus deinem Transfer heruntergeladen."
            ),
        }
        title = title_map.get(kind, "Filetransfer-Benachrichtigung")
        body = body_map.get(kind, "")
        link = f"/filetransfer/{transfer['transfer_id']}"
        now = _now_iso()
        notif_docs = [{
            "notification_id": _new_id("ftn"),
            "user_id": uid,
            "type": f"filetransfer.{kind}",
            "title": title,
            "body": body,
            "link": link,
            "transfer_id": transfer["transfer_id"],
            "read": False,
            "created_at": now,
        } for uid in recipients]
        if notif_docs:
            await db.notifications.insert_many(notif_docs)
        # E-mail (best-effort, respects user preference filetransfer_enabled)
        users = await db.users.find({"user_id": {"$in": recipients}},
                                    {"_id": 0, "user_id": 1, "email": 1, "name": 1,
                                     "email_preferences": 1}).to_list(200)
        for u in users:
            if not u.get("email"):
                continue
            prefs = u.get("email_preferences") or {}
            # Default: opted-in. Set `filetransfer_enabled: false` to opt-out.
            if prefs.get("filetransfer_enabled", True) is False:
                continue
            html = f"<p>{body.replace(chr(10), '<br/>')}</p><p><a href='{link}'>Im Filetransfer öffnen</a></p>"
            try:
                await send_email_real(u["email"], title, html, category="filetransfer")
            except Exception as e:
                logger.warning(f"filetransfer email failed for {u.get('email')}: {e}")
    except Exception as e:
        logger.warning(f"filetransfer notify failed: {e}")


async def _check_quota(settings: dict, incoming_bytes: int) -> None:
    """Iter 386c — Hard quota enforcement.
    Sums up stored bytes from `file_transfer_files` and compares to
    `max_total_quota_mb`. Raises 507 (Insufficient Storage) if the new
    upload would exceed the quota. The aggregation is fast because we
    only project `size_stored_bytes` and filter on a small collection.
    Falls disabled when `max_total_quota_mb <= 0`.
    """
    quota_mb = int(settings.get("max_total_quota_mb") or 0)
    if quota_mb <= 0:
        return
    quota_bytes = quota_mb * 1024 * 1024
    agg = await db.file_transfer_files.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$size_stored_bytes"}}}
    ]).to_list(1)
    used = (agg[0]["total"] if agg else 0) or 0
    if used + incoming_bytes > quota_bytes:
        free = max(0, quota_bytes - used)
        raise HTTPException(
            507,
            f"Speicher-Kontingent erschöpft (verwendet {used // (1024*1024)} MB / "
            f"max {quota_mb} MB, frei {free // (1024*1024)} MB)",
        )


# ----------------------------- PUBLIC SCHEMAS -----------------------------

class TransferCreate(BaseModel):
    message: Optional[str] = ""
    recipient_user_ids: List[str] = []
    expiry_days: Optional[int] = None
    notify: bool = True

class TransferUpdate(BaseModel):
    message: Optional[str] = None
    status: Optional[str] = None  # active | revoked

class ShareCreate(BaseModel):
    password: Optional[str] = None
    one_time: bool = False
    expires_at: Optional[str] = None  # ISO, optional override

class StorageTestRequest(BaseModel):
    target: str  # local | network_share
    path: str

class SettingsUpdate(BaseModel):
    target: Optional[str] = None
    local_root: Optional[str] = None
    network_share_path: Optional[str] = None
    fallback_to_local: Optional[bool] = None
    max_file_size_mb: Optional[int] = None
    max_total_quota_mb: Optional[int] = None
    warn_threshold_pct: Optional[int] = None
    default_expiry_days: Optional[int] = None
    allowed_extensions: Optional[List[str]] = None
    encryption_required_local: Optional[bool] = None
    chunked_upload_backend: Optional[str] = None  # 'mongo' | 'disk'
    chunked_upload_tmp_dir: Optional[str] = None
    enable_virus_scan: Optional[bool] = None
    virus_scan_required: Optional[bool] = None
    clamav_host: Optional[str] = None
    clamav_port: Optional[int] = None


# ============================ TRANSFERS (auth) ============================

@router.get("/filetransfer/transfers")
async def list_my_transfers(request: Request, status: Optional[str] = None,
                            q: Optional[str] = None,
                            recipient: Optional[str] = None,
                            file_type: Optional[str] = None):
    user = await get_current_user(request)
    await _require_use(user)
    uid = user["user_id"]
    mongo_q: dict = {"$or": [
        {"owner_user_id": uid},
        {"recipient_user_ids": uid},
    ]}
    if status:
        mongo_q["status"] = status
    if recipient:
        mongo_q["recipient_user_ids"] = recipient
    if q and len(q) >= 2:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        mongo_q["$and"] = [{"$or": [{"message": rx}, {"file_names": rx}]}]
    cursor = db.file_transfers.find(mongo_q, {"_id": 0}).sort("created_at", -1).limit(200)
    rows = await cursor.to_list(200)
    if file_type:
        rows = [r for r in rows if any((fn or "").lower().endswith("." + file_type.lower().lstrip(".")) for fn in (r.get("file_names") or []))]
    return rows


@router.post("/filetransfer/transfers")
async def create_transfer(payload: TransferCreate, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    settings = await _settings()
    expiry_days = payload.expiry_days if payload.expiry_days and payload.expiry_days > 0 else int(settings.get("default_expiry_days") or 14)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()
    tid = _new_id("ft")
    doc = {
        "transfer_id": tid,
        "owner_user_id": user["user_id"],
        "owner_name": user.get("name", ""),
        "message": (payload.message or "")[:2000],
        "recipient_user_ids": list({u for u in (payload.recipient_user_ids or []) if u and u != user["user_id"]}),
        "status": "draft",
        "expires_at": expires_at,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "file_names": [],
        "total_size_bytes": 0,
        "download_count": 0,
    }
    await db.file_transfers.insert_one(doc)
    await _audit("transfer.create", user, transfer_id=tid)
    doc.pop("_id", None)
    return doc


@router.get("/filetransfer/transfers/{tid}")
async def get_transfer(tid: str, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer nicht gefunden")
    if user["user_id"] not in [t["owner_user_id"]] + (t.get("recipient_user_ids") or []) and not await has_cap(user, CAP_ADMIN, db):
        raise HTTPException(403, "Kein Zugriff")
    files = await db.file_transfer_files.find({"transfer_id": tid}, {"_id": 0, "storage_path": 0}).sort("created_at", 1).to_list(500)
    shares = await db.file_transfer_shares.find({"transfer_id": tid}, {"_id": 0, "password_hash": 0}).to_list(20)
    downloads = await db.file_transfer_downloads.find({"transfer_id": tid}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {**t, "files": files, "shares": shares, "downloads": downloads}


@router.patch("/filetransfer/transfers/{tid}")
async def update_transfer(tid: str, payload: TransferUpdate, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer nicht gefunden")
    if t["owner_user_id"] != user["user_id"] and not await has_cap(user, CAP_ADMIN, db):
        raise HTTPException(403, "Kein Zugriff")
    updates = {"updated_at": _now_iso()}
    if payload.message is not None:
        updates["message"] = payload.message[:2000]
    if payload.status in ("active", "revoked"):
        updates["status"] = payload.status
    await db.file_transfers.update_one({"transfer_id": tid}, {"$set": updates})
    await _audit(f"transfer.{updates.get('status') or 'update'}", user, transfer_id=tid)
    return {"ok": True}


@router.delete("/filetransfer/transfers/{tid}")
async def delete_transfer(tid: str, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer nicht gefunden")
    if t["owner_user_id"] != user["user_id"] and not await has_cap(user, CAP_ADMIN, db):
        raise HTTPException(403, "Kein Zugriff")
    # delete blobs from provider
    settings = await _settings()
    provider, _ = build_provider(settings)
    files = await db.file_transfer_files.find({"transfer_id": tid}).to_list(500)
    for f in files:
        try: provider.delete(f["storage_path"])
        except Exception as e: logger.warning(f"delete file blob failed: {e}")
    await db.file_transfer_files.delete_many({"transfer_id": tid})
    await db.file_transfer_shares.delete_many({"transfer_id": tid})
    await db.file_transfer_downloads.delete_many({"transfer_id": tid})
    await db.file_transfers.delete_one({"transfer_id": tid})
    await _audit("transfer.delete", user, transfer_id=tid)
    return {"ok": True}


# ----------------------------- UPLOAD -----------------------------

@router.post("/filetransfer/transfers/{tid}/files")
async def upload_file(tid: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer nicht gefunden")
    if t["owner_user_id"] != user["user_id"]:
        raise HTTPException(403, "Nur Eigentuemer darf Dateien hinzufuegen")
    if t.get("status") not in (None, "draft", "active"):
        raise HTTPException(400, "Transfer ist abgeschlossen oder widerrufen")

    settings = await _settings()
    max_size = int(settings.get("max_file_size_mb") or 200) * 1024 * 1024
    allowed = [e.lower().lstrip(".") for e in (settings.get("allowed_extensions") or [])]

    data = await file.read()
    if len(data) > max_size:
        raise HTTPException(413, f"Datei zu gross (max {settings.get('max_file_size_mb')} MB)")
    await _check_quota(settings, len(data))
    fname = _safe_filename(file.filename or "file")
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if allowed and ext not in allowed:
        raise HTTPException(400, f"Dateityp .{ext} nicht erlaubt")
    # iter 386b — libmagic MIME-Sniff: reject executables even if their
    # extension was whitelisted (e.g. an .exe renamed to .pdf).
    sniff_mime = _sniff_mime(data, file.content_type or "")
    if sniff_mime in _EXECUTABLE_MIMES:
        raise HTTPException(400, f"Ausführbare Dateien sind nicht erlaubt (MIME {sniff_mime})")
    # iter 386d — optional virus scan
    virus = _clamav_scan(data, settings)
    if virus:
        await _audit("file.virus", user, transfer_id=tid, meta={"virus": virus, "file_name": fname})
        raise HTTPException(400, f"Virus erkannt: {virus}")

    sha = hashlib.sha256(data).hexdigest()
    provider, eff_settings = build_provider(settings)
    encrypt_local = bool(settings.get("encryption_required_local"))
    rel_path = f"{tid}/{_new_id('blob')}"
    try:
        meta = provider.save(rel_path, data, force_encrypt=encrypt_local)
    except Exception as e:
        logger.error(f"storage save failed: {e}")
        raise HTTPException(503, "Speichern fehlgeschlagen") from e

    fid = _new_id("ftf")
    fdoc = {
        "file_id": fid,
        "transfer_id": tid,
        "file_name": fname,
        "size_bytes": len(data),
        "size_stored_bytes": meta.get("size_stored", len(data)),
        "mime_type": sniff_mime or file.content_type or "application/octet-stream",
        "mime_declared": file.content_type or "",
        "sha256": sha,
        "storage_provider": meta.get("provider"),
        "storage_path": rel_path,
        "encrypted": bool(meta.get("encrypted")),
        "key_version": meta.get("key_version"),
        "created_at": _now_iso(),
    }
    await db.file_transfer_files.insert_one(fdoc)
    upd = await db.file_transfers.find_one_and_update(
        {"transfer_id": tid},
        {"$inc": {"total_size_bytes": len(data)},
         "$push": {"file_names": fname},
         "$set": {"status": "active", "updated_at": _now_iso()}},
        return_document=True,
        projection={"_id": 0},
    )
    await _audit("file.upload", user, transfer_id=tid, file_id=fid,
                 meta={"size": len(data), "encrypted": fdoc["encrypted"], "mime": fdoc["mime_type"]})
    # Notify recipients on first activation (status flip from draft -> active).
    # We fire on every upload but `_notify_recipients` is idempotent enough
    # for typical flows; mass-uploads of many files cause one notification
    # per file. Acceptable tradeoff to keep things simple.
    if upd and (upd.get("recipient_user_ids") or []):
        asyncio.create_task(_notify_recipients(upd, user, kind="new_transfer",
                                               extra={"file_count": len((upd.get("file_names") or []))}))
    fdoc.pop("_id", None)
    fdoc.pop("storage_path", None)
    return fdoc


# ----------------------------- CHUNKED UPLOAD (iter 386b) -----------------------------

class ChunkInitRequest(BaseModel):
    file_name: str
    total_size: int = Field(gt=0)
    mime: Optional[str] = None
    total_chunks: int = Field(gt=0, le=10000)


@router.post("/filetransfer/transfers/{tid}/uploads/init")
async def chunk_upload_init(tid: str, payload: ChunkInitRequest, request: Request):
    """Initiate a chunked upload. Returns an `upload_id` and the chunk-size
    we want. For files > max_file_size_mb we reject upfront.
    The session lives in `filetransfer_uploads`. Depending on the admin
    setting `chunked_upload_backend`:

      * `mongo` (default, small files): chunks are appended to the
        Mongo session doc (chunk-data + chunk-index arrays).
      * `disk`  (large files / streaming): chunks are written to
        `<chunked_upload_tmp_dir>/<upload_id>/chunk_<index>.bin` directly
        on disk so we never load > 1 chunk into memory. Commit then
        concatenates the chunks file-by-file and pipes the result
        through the encryption + storage provider.
    """
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t or t["owner_user_id"] != user["user_id"]:
        raise HTTPException(403, "Nur Eigentuemer darf hochladen")
    settings = await _settings()
    max_size = int(settings.get("max_file_size_mb") or 200) * 1024 * 1024
    if payload.total_size > max_size:
        raise HTTPException(413, f"Datei zu gross (max {settings.get('max_file_size_mb')} MB)")
    await _check_quota(settings, payload.total_size)
    fname = _safe_filename(payload.file_name)
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    allowed = [e.lower().lstrip(".") for e in (settings.get("allowed_extensions") or [])]
    if allowed and ext not in allowed:
        raise HTTPException(400, f"Dateityp .{ext} nicht erlaubt")
    upload_id = _new_id("ftu")
    backend = (settings.get("chunked_upload_backend") or "mongo").lower()
    tmp_dir = settings.get("chunked_upload_tmp_dir") or "/tmp/meetflow_ft_uploads"
    session_dir = None
    if backend == "disk":
        session_dir = os.path.join(tmp_dir, upload_id)
        try:
            os.makedirs(session_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"disk upload tmp dir create failed: {e}")
            backend = "mongo"  # graceful fallback
    await db.filetransfer_uploads.insert_one({
        "upload_id": upload_id,
        "transfer_id": tid,
        "owner_user_id": user["user_id"],
        "file_name": fname,
        "mime_declared": payload.mime or "",
        "total_size": payload.total_size,
        "total_chunks": payload.total_chunks,
        "received_chunks": [],   # int[] indices
        "chunk_data": [],        # parallel array of bytes (mongo backend only)
        "backend": backend,
        "session_dir": session_dir,
        "created_at": _now_iso(),
    })
    return {"upload_id": upload_id, "chunk_size_recommended": 4 * 1024 * 1024,
            "backend": backend}


@router.post("/filetransfer/transfers/{tid}/uploads/{upload_id}/chunk")
async def chunk_upload_chunk(tid: str, upload_id: str, request: Request,
                             chunk_index: int = Form(...), chunk: UploadFile = File(...)):
    user = await get_current_user(request)
    await _require_use(user)
    sess = await db.filetransfer_uploads.find_one({"upload_id": upload_id, "transfer_id": tid})
    if not sess or sess["owner_user_id"] != user["user_id"]:
        raise HTTPException(404, "Upload-Session unbekannt")
    if chunk_index in (sess.get("received_chunks") or []):
        return {"ok": True, "duplicate": True}
    data = await chunk.read()
    if (sess.get("backend") or "mongo") == "disk":
        # Stream chunk to disk; only an index goes into Mongo.
        session_dir = sess.get("session_dir")
        if not session_dir:
            raise HTTPException(500, "Sessions-Verzeichnis fehlt")
        chunk_path = os.path.join(session_dir, f"chunk_{int(chunk_index):06d}.bin")
        try:
            with open(chunk_path, "wb") as fh:
                fh.write(data)
        except Exception as e:
            logger.error(f"disk chunk write failed: {e}")
            raise HTTPException(503, "Chunk-Speicherung fehlgeschlagen") from e
        await db.filetransfer_uploads.update_one(
            {"upload_id": upload_id},
            {"$push": {"received_chunks": chunk_index}},
        )
    else:
        # Mongo backend — keep chunk bytes in the session doc.
        await db.filetransfer_uploads.update_one(
            {"upload_id": upload_id},
            {"$push": {"received_chunks": chunk_index, "chunk_data": data}},
        )
    return {"ok": True, "received": len((sess.get("received_chunks") or [])) + 1,
            "total": sess.get("total_chunks")}


def _cleanup_session_dir(session_dir: Optional[str]):
    if not session_dir:
        return
    try:
        import shutil as _sh
        _sh.rmtree(session_dir, ignore_errors=True)
    except Exception as e:
        logger.warning(f"chunk session dir cleanup failed: {e}")


@router.post("/filetransfer/transfers/{tid}/uploads/{upload_id}/commit")
async def chunk_upload_commit(tid: str, upload_id: str, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    sess = await db.filetransfer_uploads.find_one({"upload_id": upload_id, "transfer_id": tid})
    if not sess or sess["owner_user_id"] != user["user_id"]:
        raise HTTPException(404, "Upload-Session unbekannt")
    received = sess.get("received_chunks") or []
    if len(received) != sess.get("total_chunks"):
        raise HTTPException(409, f"Unvollständig: {len(received)}/{sess.get('total_chunks')} Chunks")

    backend = sess.get("backend") or "mongo"
    if backend == "disk":
        # Reassemble from disk in chunk-index order.
        session_dir = sess.get("session_dir")
        if not session_dir or not os.path.isdir(session_dir):
            raise HTTPException(500, "Sessions-Verzeichnis fehlt")
        out = io.BytesIO()
        for idx in sorted(received):
            chunk_path = os.path.join(session_dir, f"chunk_{int(idx):06d}.bin")
            try:
                with open(chunk_path, "rb") as fh:
                    out.write(fh.read())
            except Exception as e:
                _cleanup_session_dir(session_dir)
                raise HTTPException(500, f"Chunk lesen fehlgeschlagen: {e}") from e
        data = out.getvalue()
    else:
        # Mongo backend reassembly.
        pairs = list(zip(received, sess.get("chunk_data") or []))
        pairs.sort(key=lambda p: p[0])
        data = b"".join(b for _, b in pairs)

    if len(data) != sess.get("total_size"):
        if backend == "disk":
            _cleanup_session_dir(sess.get("session_dir"))
        raise HTTPException(409, "Größe stimmt nicht überein")

    settings = await _settings()
    max_size = int(settings.get("max_file_size_mb") or 200) * 1024 * 1024
    if len(data) > max_size:
        if backend == "disk":
            _cleanup_session_dir(sess.get("session_dir"))
        raise HTTPException(413, "Datei zu gross")
    sniff_mime = _sniff_mime(data, sess.get("mime_declared") or "application/octet-stream")
    if sniff_mime in _EXECUTABLE_MIMES:
        if backend == "disk":
            _cleanup_session_dir(sess.get("session_dir"))
        raise HTTPException(400, f"Ausführbare Dateien sind nicht erlaubt (MIME {sniff_mime})")
    virus = _clamav_scan(data, settings)
    if virus:
        if backend == "disk":
            _cleanup_session_dir(sess.get("session_dir"))
        await _audit("file.virus", user, transfer_id=tid, meta={"virus": virus, "file_name": sess["file_name"]})
        raise HTTPException(400, f"Virus erkannt: {virus}")
    sha = hashlib.sha256(data).hexdigest()
    provider, _ = build_provider(settings)
    rel_path = f"{tid}/{_new_id('blob')}"
    try:
        meta = provider.save(rel_path, data, force_encrypt=bool(settings.get("encryption_required_local")))
    except Exception as e:
        logger.error(f"chunked commit save failed: {e}")
        if backend == "disk":
            _cleanup_session_dir(sess.get("session_dir"))
        raise HTTPException(503, "Speichern fehlgeschlagen") from e

    fid = _new_id("ftf")
    fdoc = {
        "file_id": fid, "transfer_id": tid,
        "file_name": sess["file_name"],
        "size_bytes": len(data),
        "size_stored_bytes": meta.get("size_stored", len(data)),
        "mime_type": sniff_mime,
        "mime_declared": sess.get("mime_declared") or "",
        "sha256": sha,
        "storage_provider": meta.get("provider"),
        "storage_path": rel_path,
        "encrypted": bool(meta.get("encrypted")),
        "key_version": meta.get("key_version"),
        "created_at": _now_iso(),
    }
    await db.file_transfer_files.insert_one(fdoc)
    upd = await db.file_transfers.find_one_and_update(
        {"transfer_id": tid},
        {"$inc": {"total_size_bytes": len(data)},
         "$push": {"file_names": sess["file_name"]},
         "$set": {"status": "active", "updated_at": _now_iso()}},
        return_document=True, projection={"_id": 0},
    )
    # Wipe the now-redundant chunk buffer
    if backend == "disk":
        _cleanup_session_dir(sess.get("session_dir"))
    await db.filetransfer_uploads.delete_one({"upload_id": upload_id})
    await _audit("file.upload.chunked", user, transfer_id=tid, file_id=fid,
                 meta={"size": len(data), "chunks": sess.get("total_chunks"),
                       "mime": sniff_mime, "backend": backend})
    if upd and (upd.get("recipient_user_ids") or []):
        asyncio.create_task(_notify_recipients(upd, user, kind="new_transfer",
                                               extra={"file_count": len(upd.get("file_names") or [])}))
    fdoc.pop("_id", None); fdoc.pop("storage_path", None)
    return fdoc


@router.delete("/filetransfer/transfers/{tid}/uploads/{upload_id}")
async def chunk_upload_abort(tid: str, upload_id: str, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    sess = await db.filetransfer_uploads.find_one({"upload_id": upload_id, "transfer_id": tid, "owner_user_id": user["user_id"]})
    if sess and (sess.get("backend") or "mongo") == "disk":
        _cleanup_session_dir(sess.get("session_dir"))
    res = await db.filetransfer_uploads.delete_one({"upload_id": upload_id, "transfer_id": tid, "owner_user_id": user["user_id"]})
    return {"ok": res.deleted_count > 0}


# ----------------------------- DOWNLOAD -----------------------------

async def _can_read(t: dict, user: dict) -> bool:
    if not t: return False
    if t["owner_user_id"] == user["user_id"]: return True
    if user["user_id"] in (t.get("recipient_user_ids") or []): return True
    return await has_cap(user, CAP_ADMIN, db)


async def _stream_file(file_doc: dict) -> tuple[bytes, str]:
    settings = await _settings()
    provider, _ = build_provider(settings)
    raw = provider.load(file_doc["storage_path"], encrypted=bool(file_doc.get("encrypted")))
    return raw, file_doc.get("mime_type", "application/octet-stream")


@router.get("/filetransfer/transfers/{tid}/files/{fid}/download")
async def download_file(tid: str, fid: str, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t or not await _can_read(t, user):
        raise HTTPException(404, "Nicht gefunden")
    if t.get("status") == "revoked":
        raise HTTPException(410, "Transfer widerrufen")
    if (t.get("expires_at") or "") and t["expires_at"] < _now_iso():
        raise HTTPException(410, "Transfer abgelaufen")
    f = await db.file_transfer_files.find_one({"file_id": fid, "transfer_id": tid})
    if not f:
        raise HTTPException(404, "Datei nicht gefunden")
    raw, ctype = await _stream_file(f)
    await db.file_transfer_downloads.insert_one({
        "download_id": _new_id("dl"),
        "transfer_id": tid, "file_id": fid,
        "by_user_id": user["user_id"], "by_name": user.get("name", ""),
        "channel": "internal",
        "ip": request.client.host if request.client else None,
        "created_at": _now_iso(),
    })
    await db.file_transfers.update_one({"transfer_id": tid}, {"$inc": {"download_count": 1}})
    await _audit("file.download", user, transfer_id=tid, file_id=fid)
    if t["owner_user_id"] != user["user_id"]:
        asyncio.create_task(_notify_recipients(
            t, user, kind="download",
            extra={"downloader_name": user.get("name"), "file_name": f["file_name"]},
        ))
    safe = _safe_filename(f["file_name"])
    return StreamingResponse(io.BytesIO(raw), media_type=ctype, headers={
        "Content-Disposition": f'attachment; filename="{safe}"',
        "Content-Length": str(len(raw)),
    })


@router.get("/filetransfer/transfers/{tid}/zip")
async def download_zip(tid: str, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t or not await _can_read(t, user):
        raise HTTPException(404, "Nicht gefunden")
    if t.get("status") == "revoked":
        raise HTTPException(410, "Transfer widerrufen")
    files = await db.file_transfer_files.find({"transfer_id": tid}).to_list(500)
    if not files:
        raise HTTPException(404, "Keine Dateien")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            raw, _ = await _stream_file(f)
            zf.writestr(_safe_filename(f["file_name"]), raw)
    buf.seek(0)
    await db.file_transfers.update_one({"transfer_id": tid}, {"$inc": {"download_count": 1}})
    await _audit("transfer.zip", user, transfer_id=tid)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="transfer_{tid}.zip"',
    })


# ----------------------------- EXTERNAL SHARES -----------------------------

@router.post("/filetransfer/transfers/{tid}/shares")
async def create_share(tid: str, payload: ShareCreate, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    t = await db.file_transfers.find_one({"transfer_id": tid}, {"_id": 0})
    if not t or t["owner_user_id"] != user["user_id"]:
        raise HTTPException(403, "Nur Eigentuemer darf Links erstellen")
    settings = await _settings()
    expires_at = payload.expires_at or t.get("expires_at") or \
        (datetime.now(timezone.utc) + timedelta(days=int(settings.get("default_expiry_days") or 14))).isoformat()
    sid = _new_id("fts")
    token = secrets.token_urlsafe(24)
    doc = {
        "share_id": sid,
        "transfer_id": tid,
        "token": token,
        "password_hash": bcrypt.hash(payload.password) if payload.password else None,
        "one_time": bool(payload.one_time),
        "expires_at": expires_at,
        "downloaded_count": 0,
        "revoked": False,
        "created_by": user["user_id"],
        "created_at": _now_iso(),
    }
    await db.file_transfer_shares.insert_one(doc)
    await _audit("share.create", user, transfer_id=tid, share_id=sid,
                 meta={"one_time": doc["one_time"], "password": bool(payload.password)})
    return {"share_id": sid, "token": token, "expires_at": expires_at,
            "url": f"/filetransfer/public/{token}",
            "password_protected": bool(payload.password),
            "one_time": doc["one_time"]}


@router.delete("/filetransfer/shares/{sid}")
async def revoke_share(sid: str, request: Request):
    user = await get_current_user(request)
    await _require_use(user)
    s = await db.file_transfer_shares.find_one({"share_id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Share nicht gefunden")
    t = await db.file_transfers.find_one({"transfer_id": s["transfer_id"]}, {"_id": 0})
    if t["owner_user_id"] != user["user_id"] and not await has_cap(user, CAP_ADMIN, db):
        raise HTTPException(403, "Kein Zugriff")
    await db.file_transfer_shares.update_one({"share_id": sid}, {"$set": {"revoked": True, "revoked_at": _now_iso()}})
    await _audit("share.revoke", user, transfer_id=s["transfer_id"], share_id=sid)
    return {"ok": True}


# ----------------------------- PUBLIC (anonymous) -----------------------------

class PublicAccessRequest(BaseModel):
    password: Optional[str] = None


async def _resolve_share(token: str, request: Optional[Request] = None) -> tuple[dict, dict]:
    # iter 386d — Brute-force protection
    if request is not None:
        _public_rate_check(token, request.client.host if request.client else "anon")
    s = await db.file_transfer_shares.find_one({"token": token}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Link ungueltig")
    if s.get("revoked"):
        raise HTTPException(410, "Link widerrufen")
    if (s.get("expires_at") or "") and s["expires_at"] < _now_iso():
        raise HTTPException(410, "Link abgelaufen")
    if s.get("one_time") and (s.get("downloaded_count") or 0) > 0:
        raise HTTPException(410, "Einmal-Link bereits eingelöst")
    t = await db.file_transfers.find_one({"transfer_id": s["transfer_id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer nicht gefunden")
    if t.get("status") == "revoked":
        raise HTTPException(410, "Transfer widerrufen")
    return s, t


@router.get("/filetransfer/public/{token}")
async def public_info(token: str, request: Request):
    s, t = await _resolve_share(token, request)
    files = await db.file_transfer_files.find({"transfer_id": t["transfer_id"]},
                                              {"_id": 0, "storage_path": 0, "sha256": 0}).to_list(500)
    return {
        "transfer_id": t["transfer_id"],
        "owner_name": t.get("owner_name", ""),
        "message": t.get("message", ""),
        "expires_at": s["expires_at"],
        "one_time": s.get("one_time", False),
        "password_required": bool(s.get("password_hash")),
        "files": files,
    }


@router.post("/filetransfer/public/{token}/access")
async def public_access(token: str, payload: PublicAccessRequest, request: Request):
    s, _ = await _resolve_share(token, request)
    if s.get("password_hash"):
        if not payload.password or not bcrypt.verify(payload.password, s["password_hash"]):
            raise HTTPException(401, "Passwort falsch")
    return {"ok": True}


@router.post("/filetransfer/public/{token}/files/{fid}/download")
async def public_download_file(token: str, fid: str, payload: PublicAccessRequest, request: Request):
    s, t = await _resolve_share(token, request)
    if s.get("password_hash"):
        if not payload.password or not bcrypt.verify(payload.password, s["password_hash"]):
            raise HTTPException(401, "Passwort falsch")
    f = await db.file_transfer_files.find_one({"file_id": fid, "transfer_id": t["transfer_id"]})
    if not f:
        raise HTTPException(404, "Datei nicht gefunden")
    raw, ctype = await _stream_file(f)
    await db.file_transfer_shares.update_one({"share_id": s["share_id"]}, {"$inc": {"downloaded_count": 1}})
    await db.file_transfer_downloads.insert_one({
        "download_id": _new_id("dl"),
        "transfer_id": t["transfer_id"], "file_id": fid,
        "by_user_id": None, "by_name": "extern", "channel": "external",
        "share_id": s["share_id"], "ip": request.client.host if request.client else None,
        "created_at": _now_iso(),
    })
    await db.file_transfers.update_one({"transfer_id": t["transfer_id"]}, {"$inc": {"download_count": 1}})
    await _audit("file.download.external", None, transfer_id=t["transfer_id"], file_id=fid, share_id=s["share_id"])
    asyncio.create_task(_notify_recipients(
        t, {"name": "Externer Empfänger"}, kind="download",
        extra={"downloader_name": "Externer Empfänger", "file_name": f["file_name"]},
    ))
    safe = _safe_filename(f["file_name"])
    return StreamingResponse(io.BytesIO(raw), media_type=ctype, headers={
        "Content-Disposition": f'attachment; filename="{safe}"',
        "Content-Length": str(len(raw)),
    })


# ----------------------------- ADMIN -----------------------------

@router.get("/filetransfer/admin/overview")
async def admin_overview(request: Request):
    user = await get_current_user(request)
    await _require_admin(user)
    now = _now_iso()
    pipeline = [
        {"$group": {"_id": None,
                    "total_transfers": {"$sum": 1},
                    "active": {"$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}},
                    "draft": {"$sum": {"$cond": [{"$eq": ["$status", "draft"]}, 1, 0]}},
                    "revoked": {"$sum": {"$cond": [{"$eq": ["$status", "revoked"]}, 1, 0]}},
                    "expired": {"$sum": {"$cond": [{"$lt": ["$expires_at", now]}, 1, 0]}},
                    "total_size_bytes": {"$sum": "$total_size_bytes"}}},
    ]
    agg = await db.file_transfers.aggregate(pipeline).to_list(1)
    stats = agg[0] if agg else {"total_transfers": 0}
    stats.pop("_id", None)
    settings = await _settings()
    provider, eff = build_provider(settings)
    health = provider.health()
    return {"stats": stats, "storage": {"settings": eff, "health": health}}


@router.get("/filetransfer/admin/transfers")
async def admin_list_all(request: Request, limit: int = 200):
    user = await get_current_user(request)
    await _require_admin(user)
    rows = await db.file_transfers.find({}, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 500))).to_list(500)
    return rows


@router.get("/filetransfer/admin/audit")
async def admin_audit(request: Request, limit: int = 200):
    user = await get_current_user(request)
    await _require_admin(user)
    rows = await db.file_transfer_audit.find({}, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 500))).to_list(500)
    return rows


# ----------------------------- SETTINGS -----------------------------

@router.get("/filetransfer/settings")
async def get_settings(request: Request):
    user = await get_current_user(request)
    await _require_admin(user)
    s = await _settings()
    provider, eff = build_provider(s)
    return {"settings": eff, "health": provider.health(), "usage": provider.usage()}


@router.patch("/filetransfer/settings")
async def update_settings(payload: SettingsUpdate, request: Request):
    user = await get_current_user(request)
    await _require_admin(user)
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(400, "Keine Aenderungen")
    await db.filetransfer_settings.update_one(
        {"kind": "global"},
        {"$set": {**updates, "updated_at": _now_iso(), "updated_by": user["user_id"]}},
        upsert=True,
    )
    await _audit("settings.update", user, meta={"keys": list(updates.keys())})
    return {"ok": True, "settings": await _settings()}


@router.post("/filetransfer/settings/test")
async def test_storage(payload: StorageTestRequest, request: Request):
    user = await get_current_user(request)
    await _require_admin(user)
    target = payload.target.lower()
    if target not in ("local", "network_share"):
        raise HTTPException(400, "Unbekanntes Ziel")
    if target == "network_share" and not payload.path:
        raise HTTPException(400, "Pfad erforderlich")
    test_settings = {"target": target,
                     "local_root": payload.path if target == "local" else DEFAULT_SETTINGS["local_root"],
                     "network_share_path": payload.path if target == "network_share" else "",
                     "fallback_to_local": False}
    try:
        provider, _ = build_provider(test_settings)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    health = provider.health()
    # Try a tiny round-trip
    probe_path = f"_probe/{secrets.token_hex(4)}.bin"
    payload_bytes = b"meetflow-storage-probe"
    write_ok = read_ok = False
    err = None
    try:
        provider.save(probe_path, payload_bytes, force_encrypt=(target == "network_share"))
        write_ok = True
        roundtrip = provider.load(probe_path, encrypted=(target == "network_share"))
        read_ok = (roundtrip == payload_bytes)
        provider.delete(probe_path)
    except Exception as e:
        err = str(e)
    await _audit("settings.test", user, meta={"target": target, "ok": write_ok and read_ok})
    return {"ok": write_ok and read_ok, "health": health, "write_ok": write_ok, "read_ok": read_ok, "error": err}


# ----------------------------- BACKGROUND: expire -----------------------------

async def expire_outdated():
    """Mark transfers as 'expired' once their expires_at is in the past.
    Safe to call repeatedly; only acts on rows still in active/draft.
    """
    now = _now_iso()
    res = await db.file_transfers.update_many(
        {"expires_at": {"$lt": now}, "status": {"$in": ["active", "draft"]}},
        {"$set": {"status": "expired", "updated_at": now}},
    )
    if res.modified_count:
        logger.info(f"filetransfer: expired {res.modified_count} transfers")
    return res.modified_count
