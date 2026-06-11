import os
import logging
import requests as sync_requests
from fastapi import HTTPException

logger = logging.getLogger("server")

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_STORAGE_PREFIX = "meetflow"
storage_key = None
_last_init_emergent_key = None  # so we can detect a changed source-key and re-init


def _read_emergent_key() -> str:
    """Resolve the Emergent key. Priority:
       1) Live ENV var (preferred on Emergent-managed deployments)
       2) DB `api_config.llm_key` saved via the Admin → Integrationen panel
    Using a synchronous Mongo client here because put_object/get_object run
    inside `asyncio.to_thread` — calling async Motor from a worker thread
    would mismatch event loops."""
    env_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if env_key:
        return env_key
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL", "")
        db_name = os.environ.get("DB_NAME", "")
        if not mongo_url or not db_name:
            return ""
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        cfg = client[db_name].api_config.find_one({"config_id": "global"}, {"_id": 0, "llm_key": 1})
        client.close()
        return (cfg or {}).get("llm_key", "") or ""
    except Exception as e:
        logger.warning(f"Storage DB-key fallback failed: {e}")
        return ""


def init_storage(force_refresh: bool = False):
    global storage_key, _last_init_emergent_key
    emergent_key = _read_emergent_key()
    if not emergent_key:
        # Invalidate any previous storage_key so a later key-set re-inits cleanly
        storage_key = None
        _last_init_emergent_key = None
        logger.warning("No EMERGENT_LLM_KEY (env or api_config.llm_key) for storage")
        return None
    # Re-init if the source key changed (admin pasted a new key in the GUI)
    if storage_key and not force_refresh and _last_init_emergent_key == emergent_key:
        return storage_key
    try:
        resp = sync_requests.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key}, timeout=30)
        resp.raise_for_status()
        storage_key = resp.json()["storage_key"]
        _last_init_emergent_key = emergent_key
        logger.info("Object storage initialized")
        return storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        storage_key = None
        return None


def reset_storage():
    """Invalidate the cached storage_key so the next operation re-inits.
    Called after the admin saves a new LLM key via the GUI."""
    global storage_key, _last_init_emergent_key
    storage_key = None
    _last_init_emergent_key = None


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage not available")
    resp = sync_requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage not available")
    resp = sync_requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
