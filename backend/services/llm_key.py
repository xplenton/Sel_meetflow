"""
Shared LLM-key resolver — used by every endpoint that needs to call LLMs.
Resolves from the admin-configured DB override first, then from env.
"""
from __future__ import annotations

import os
from database import db


async def get_llm_key() -> str:
    """Return the effective Emergent LLM key: DB override first, env fallback."""
    try:
        config = await db.api_config.find_one({"config_id": "global"}, {"_id": 0})
        if config and config.get("llm_enabled") and config.get("llm_key"):
            return config["llm_key"]
    except Exception:
        pass
    return os.environ.get("EMERGENT_LLM_KEY", "")
