"""
Resources/admin · Cost-centers + Accounts (Stammdaten).

Iter 297 — both live in the unified `invoice_master_data` collection.
Legacy `cost_centers` and `accounting_accounts` are migrated lazily on read
so any pre-Iter-297 deployment keeps working without manual data ops.
Cost-center-specific fields (`accounting_email`, `responsible_user_id`,
`department`) stay on the same row to preserve the auto-send-invoice flow.

Iter 345 — global 30 s TTL cache for the list endpoints; cost centers and
accounts are quasi-static reference data that ALL users with view rights
fetch on every page that has a Kostenstelle/Konto-Dropdown. Soak (iter 344)
showed cost_centers alone at ~8 700 calls / 15 min = same data 100×.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import time as _time
import uuid

from database import db
from dependencies import get_current_user
from services.permissions import require_cap, has_cap

router = APIRouter()

# Iter 345 — see module docstring. Single global slot per list (not per user)
# because the response is identical for everyone with view:resources.
_CC_LIST_CACHE: "dict[str, tuple[float, list]]" = {}
_CC_LIST_TTL_SECONDS = 30


def _invalidate_master_cache() -> None:
    """Wipe cost-center / account list caches after any write."""
    _CC_LIST_CACHE.clear()


# ---------------------------------------------------------------------------
# Legacy migration + shape helpers
# ---------------------------------------------------------------------------

async def _migrate_legacy_master_data():
    """Idempotent one-shot copy from the legacy collections. Runs on every
    request that hits the unified endpoints; the existence-check makes it a
    no-op once migration has happened. Skipped if no legacy rows exist."""
    legacy_cc = db.cost_centers
    legacy_ac = db.accounting_accounts
    # Skip work if there's nothing to copy (cheap count + projection)
    has_legacy_cc = await legacy_cc.find_one({}, {"_id": 1})
    has_legacy_ac = await legacy_ac.find_one({}, {"_id": 1})
    if not has_legacy_cc and not has_legacy_ac:
        return
    async for cc in legacy_cc.find({}, {"_id": 0}):
        if not cc.get("code"):
            continue
        existing = await db.invoice_master_data.find_one(
            {"type": "cost_center", "code": cc["code"]}, {"_id": 1}
        )
        if existing:
            continue
        await db.invoice_master_data.insert_one({
            "item_id": f"md_{uuid.uuid4().hex[:10]}",
            "type": "cost_center",
            "code": cc["code"],
            "label": cc.get("name") or cc["code"],
            "description": cc.get("department"),
            "accounting_email": cc.get("accounting_email"),
            "responsible_user_id": cc.get("responsible_user_id"),
            "active": cc.get("status") != "inactive",
            "created_at": cc.get("created_at") or datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    async for ac in legacy_ac.find({}, {"_id": 0}):
        if not ac.get("code"):
            continue
        existing = await db.invoice_master_data.find_one(
            {"type": "account", "code": ac["code"]}, {"_id": 1}
        )
        if existing:
            continue
        await db.invoice_master_data.insert_one({
            "item_id": f"md_{uuid.uuid4().hex[:10]}",
            "type": "account",
            "code": ac["code"],
            "label": ac.get("name") or ac["code"],
            "active": ac.get("status") != "inactive",
            "created_at": ac.get("created_at") or datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    # Mark legacy collections as drained so the migration is truly one-off
    await legacy_cc.delete_many({})
    await legacy_ac.delete_many({})


def _master_to_cc(doc: dict) -> dict:
    """Reshape a unified master-data row back into the legacy cost-center
    shape used by BillingPanel and other older callers."""
    return {
        "cost_center_id": doc["item_id"],
        "code": doc["code"],
        "name": doc["label"],
        "department": doc.get("description"),
        "responsible_user_id": doc.get("responsible_user_id"),
        "accounting_email": doc.get("accounting_email"),
        "status": "active" if doc.get("active", True) else "inactive",
        "created_at": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at"),
    }


def _master_to_account(doc: dict) -> dict:
    return {
        "account_id": doc["item_id"],
        "code": doc["code"],
        "name": doc["label"],
        "status": "active" if doc.get("active", True) else "inactive",
        "created_at": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Cost centers
# ---------------------------------------------------------------------------

@router.get("/cost-centers")
async def list_cost_centers(user=Depends(get_current_user)):
    """Dropdown source for Kostenstellen. Returns active entries only."""
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    # Iter 345 — 30 s TTL cache: list is identical for all viewers, was
    # the #2 hottest endpoint in the soak test (8 689 calls / 15 min).
    now = _time.monotonic()
    entry = _CC_LIST_CACHE.get("cost_centers")
    if entry and (now - entry[0]) < _CC_LIST_TTL_SECONDS:
        return entry[1]
    await _migrate_legacy_master_data()
    items = await db.invoice_master_data.find(
        {"type": "cost_center", "active": {"$ne": False}}, {"_id": 0}
    ).sort("code", 1).to_list(500)
    result = [_master_to_cc(d) for d in items]
    _CC_LIST_CACHE["cost_centers"] = (now, result)
    return result


@router.post("/cost-centers")
async def create_cost_center(payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    await _migrate_legacy_master_data()
    code = (payload.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Code ist Pflicht")
    existing = await db.invoice_master_data.find_one(
        {"type": "cost_center", "code": code}, {"_id": 1}
    )
    if existing:
        raise HTTPException(409, f"Code {code} existiert bereits")
    doc = {
        "item_id": f"md_{uuid.uuid4().hex[:10]}",
        "type": "cost_center",
        "code": code,
        "label": payload.get("name", code),
        "description": payload.get("department"),
        "responsible_user_id": payload.get("responsible_user_id"),
        "accounting_email": (payload.get("accounting_email") or "").strip() or None,
        "active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.invoice_master_data.insert_one(doc)
    _invalidate_master_cache()
    return _master_to_cc({k: v for k, v in doc.items() if k != "_id"})


@router.put("/cost-centers/{cc_id}")
async def update_cost_center(cc_id: str, payload: dict, user=Depends(get_current_user)):
    """Iter 285 — patch a cost center (used to set accounting_email etc.).
       Iter 297 — now also accepts the new unified item_id (md_…) so the new
       Stammdaten UI in Rechnungen-Setup writes through the same endpoint."""
    await require_cap(user, "resources.manage", db)
    target = await db.invoice_master_data.find_one(
        {"item_id": cc_id, "type": "cost_center"}, {"_id": 0}
    )
    if not target:
        raise HTTPException(404, "Kostenstelle nicht gefunden")
    update: dict = {}
    if "name" in payload:
        update["label"] = payload["name"]
    if "department" in payload:
        update["description"] = payload["department"]
    if "responsible_user_id" in payload:
        update["responsible_user_id"] = payload["responsible_user_id"]
    if "accounting_email" in payload:
        v = (payload["accounting_email"] or "").strip()
        update["accounting_email"] = v or None
    if not update:
        raise HTTPException(400, "Nichts zu aktualisieren")
    update["updated_at"] = datetime.now(timezone.utc)
    await db.invoice_master_data.update_one({"item_id": cc_id}, {"$set": update})
    target.update(update)
    _invalidate_master_cache()
    return _master_to_cc(target)


@router.delete("/cost-centers/{cc_id}")
async def deactivate_cost_center(cc_id: str, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    await db.invoice_master_data.update_one(
        {"item_id": cc_id, "type": "cost_center"},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    _invalidate_master_cache()
    return {"deactivated": True}


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

@router.get("/accounts")
async def list_accounts(user=Depends(get_current_user)):
    if not await has_cap(user, "view:resources", db):
        raise HTTPException(403, "Kein Zugriff")
    now = _time.monotonic()
    entry = _CC_LIST_CACHE.get("accounts")
    if entry and (now - entry[0]) < _CC_LIST_TTL_SECONDS:
        return entry[1]
    await _migrate_legacy_master_data()
    items = await db.invoice_master_data.find(
        {"type": "account", "active": {"$ne": False}}, {"_id": 0}
    ).sort("code", 1).to_list(500)
    result = [_master_to_account(d) for d in items]
    _CC_LIST_CACHE["accounts"] = (now, result)
    return result


@router.post("/accounts")
async def create_account(payload: dict, user=Depends(get_current_user)):
    await require_cap(user, "resources.manage", db)
    code = (payload.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Code ist Pflicht")
    existing = await db.invoice_master_data.find_one(
        {"type": "account", "code": code}, {"_id": 1}
    )
    if existing:
        raise HTTPException(409, f"Code {code} existiert bereits")
    doc = {
        "item_id": f"md_{uuid.uuid4().hex[:10]}",
        "type": "account",
        "code": code,
        "label": payload.get("name", code),
        "active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.invoice_master_data.insert_one(doc)
    _invalidate_master_cache()
    return _master_to_account({k: v for k, v in doc.items() if k != "_id"})
