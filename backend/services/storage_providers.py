"""File-Transfer Storage Providers (iter 386).

Pluggable storage backends for the file-transfer module:

* ``LocalStorageProvider`` writes to a configured directory on the local
  filesystem (default: ``/app/backend/data/filetransfer``).
* ``NetworkShareStorageProvider`` writes to a mounted UNC / NFS / SMB
  path. **All writes are AES-256-GCM encrypted** before they touch the
  share — plaintext never lands on remote media.

Both providers expose the same interface:

    save(rel_path, data, *, force_encrypt=False) -> dict
    load(rel_path)                               -> bytes
    delete(rel_path)                             -> None
    health()                                     -> dict
    usage()                                      -> dict

The dispatcher ``get_active_provider(settings)`` returns the right
instance for the current admin-configured storage settings.

Path safety: every relative path is normalised and must remain under the
provider root, otherwise the operation raises immediately. This blocks
``..`` traversal and absolute-path injection from the caller.
"""
from __future__ import annotations
import os
import shutil
import logging
from pathlib import Path
from typing import Optional

from services.file_encryption import encrypt_bytes, decrypt_bytes, current_key_version

logger = logging.getLogger("server")

_DEFAULT_LOCAL_ROOT = "/app/backend/data/filetransfer"


# ---------- helpers ----------

def _safe_join(root: Path, rel: str) -> Path:
    """Resolve a relative path inside `root` and reject traversal."""
    # Strip any leading slashes; the caller passes "<transfer_id>/<file_id>".
    rel = (rel or "").lstrip("/").lstrip("\\")
    if not rel:
        raise ValueError("empty storage path")
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as e:
        raise ValueError(f"path escapes storage root: {rel}") from e
    return candidate


# ---------- LOCAL ----------

class LocalStorageProvider:
    """Stores files on the local filesystem. Encryption is OPTIONAL for the
    local provider — files are owned by the process user and assumed to be
    in a trusted environment. Set ``force_encrypt=True`` per save to opt in
    (e.g. for very sensitive transfers)."""

    kind = "local"

    def __init__(self, root: str):
        self.root = Path(root or _DEFAULT_LOCAL_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, rel_path: str, data: bytes, *, force_encrypt: bool = False) -> dict:
        path = _safe_join(self.root, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = False
        key_version: Optional[int] = None
        if force_encrypt:
            blob, key_version = encrypt_bytes(data)
            path.write_bytes(blob)
            encrypted = True
            size = len(blob)
        else:
            path.write_bytes(data)
            size = len(data)
        return {
            "provider": self.kind,
            "size_stored": size,
            "size_plain": len(data),
            "encrypted": encrypted,
            "key_version": key_version,
        }

    def load(self, rel_path: str, *, encrypted: bool = False) -> bytes:
        path = _safe_join(self.root, rel_path)
        blob = path.read_bytes()
        return decrypt_bytes(blob) if encrypted else blob

    def delete(self, rel_path: str) -> None:
        path = _safe_join(self.root, rel_path)
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"local storage delete failed for {rel_path}: {e}")

    def health(self) -> dict:
        try:
            usage = shutil.disk_usage(self.root)
            return {
                "ok": self.root.exists() and os.access(self.root, os.W_OK),
                "root": str(self.root),
                "free_bytes": usage.free,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "root": str(self.root)}

    def usage(self) -> dict:
        try:
            total = 0
            for p in self.root.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
            return {"used_by_filetransfer_bytes": total}
        except Exception:
            return {"used_by_filetransfer_bytes": 0}


# ---------- NETWORK SHARE ----------

class NetworkShareStorageProvider:
    """Stores files on a mounted network share (SMB/CIFS via UNC path or a
    mounted NFS export). Always encrypts before writing — the share is
    assumed to be untrusted (other systems / backup tooling may read it).
    Mount/auth is expected to be handled at the OS level; this class only
    handles bytes-in / bytes-out.

    On Linux, UNC paths like ``\\server\share`` must be mounted (e.g. via
    cifs-utils) so the OS sees them as a regular directory. The admin
    enters that mount path; we never spawn a mount call ourselves.
    """

    kind = "network_share"

    def __init__(self, mount_path: str):
        if not mount_path:
            raise ValueError("network share mount path is empty")
        self.root = Path(mount_path)
        # Don't auto-mkdir on shares — if the path is missing the admin
        # made a config mistake we should surface, not paper over.
        if not self.root.exists():
            logger.warning(f"network share path does not exist (yet): {self.root}")

    def save(self, rel_path: str, data: bytes, *, force_encrypt: bool = True) -> dict:
        # Plaintext NEVER lands on a share — `force_encrypt` is effectively
        # mandatory here but the kwarg keeps the interface symmetric.
        path = _safe_join(self.root, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob, key_version = encrypt_bytes(data)
        path.write_bytes(blob)
        return {
            "provider": self.kind,
            "size_stored": len(blob),
            "size_plain": len(data),
            "encrypted": True,
            "key_version": key_version,
        }

    def load(self, rel_path: str, *, encrypted: bool = True) -> bytes:
        path = _safe_join(self.root, rel_path)
        blob = path.read_bytes()
        if not encrypted:
            # Theoretical — current code path always passes encrypted=True
            # because we never write plaintext to a share.
            return blob
        return decrypt_bytes(blob)

    def delete(self, rel_path: str) -> None:
        path = _safe_join(self.root, rel_path)
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"network share delete failed for {rel_path}: {e}")

    def health(self) -> dict:
        try:
            if not self.root.exists():
                return {"ok": False, "error": "mount path missing", "root": str(self.root)}
            usage = shutil.disk_usage(self.root)
            writable = os.access(self.root, os.W_OK)
            return {
                "ok": writable,
                "root": str(self.root),
                "free_bytes": usage.free,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "writable": writable,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "root": str(self.root)}

    def usage(self) -> dict:
        try:
            total = 0
            for p in self.root.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
            return {"used_by_filetransfer_bytes": total}
        except Exception:
            return {"used_by_filetransfer_bytes": 0}


# ---------- DISPATCHER ----------

DEFAULT_SETTINGS = {
    "target": "local",
    "local_root": _DEFAULT_LOCAL_ROOT,
    "network_share_path": "",
    "fallback_to_local": True,
    "max_file_size_mb": 200,
    "max_total_quota_mb": 50000,  # 50 GB soft warning threshold
    "warn_threshold_pct": 80,
    "default_expiry_days": 14,
    "allowed_extensions": [],  # empty = all allowed
    "encryption_required_local": False,  # local stays plaintext by default
    "key_version": current_key_version(),
    # Iter 386c — Chunked-upload backend:
    #   'mongo' — buffer chunks in the DB (default, simple, < 16 MB/chunk)
    #   'disk'  — stream chunks to a temp file (preferred for very large
    #             uploads, no DB-size pressure, no in-memory reassembly)
    "chunked_upload_backend": "mongo",
    "chunked_upload_tmp_dir": "/tmp/meetflow_ft_uploads",
    "enable_virus_scan": False,
    "virus_scan_required": False,
    "clamav_host": "127.0.0.1",
    "clamav_port": 3310,
}


def build_provider(settings: dict):
    """Construct the configured provider. On NetworkShare config errors we
    fall back to LocalStorageProvider if `fallback_to_local` is set, and
    emit a warning so the storage-health page can flag the degraded mode.
    """
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    target = (settings.get("target") or "local").lower()
    if target == "network_share":
        try:
            return NetworkShareStorageProvider(settings.get("network_share_path") or ""), settings
        except Exception as e:
            logger.error(f"network share provider init failed: {e}")
            if settings.get("fallback_to_local"):
                return LocalStorageProvider(settings.get("local_root") or _DEFAULT_LOCAL_ROOT), {**settings, "_degraded": True, "_degraded_reason": str(e)}
            raise
    return LocalStorageProvider(settings.get("local_root") or _DEFAULT_LOCAL_ROOT), settings
