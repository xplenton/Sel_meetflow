"""Iter 377 — Admin-Wartungs-Routen.

Stellt zwei vordefinierte Mitarbeitergruppen ("Mitarbeiter Standard" und
"Mitarbeiter Küche") bereit und bietet einen idempotenten Wipe-Endpoint
für alle vom System generierten Demo-Daten.

Alle Endpoints sind admin-only (rolle == "admin").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from database import db
from dependencies import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Pro Standardgruppe Liste der Capabilities. Die View-Module sind
# explizit aufgefuehrt, damit die Gruppe self-contained ist (vgl. iter 375
# Preset-Audit). Roll-overide bleibt "member"-aequivalent.
PRESET_GROUPS = [
    {
        "group_id": "mitarbeiter_standard",
        "name": "Mitarbeiter Standard",
        "description": (
            "Standard-Mitarbeiter ohne Sonderrechte: Dashboard, eigene + "
            "Abteilungs-Aufgaben, Ressourcen mit Buchen-für-Andere, "
            "Terminplanung, Chat (alle Mitarbeiter kontaktieren), Kalender."
        ),
        "color": "#4A5D4E",
        "capabilities": [
            # Dashboard + Profil (Module)
            "view:dashboard",
            # Aufgaben — eigene + Abteilung (kein view_all)
            "view:tasks", "tasks.create", "tasks.view_department",
            # Ressourcen — buchen fuer sich UND fuer andere
            "view:resources", "resources.book", "resources.book_for_others",
            # Terminplanung — alle Rechte
            "view:scheduling", "scheduling.create_poll",
            # Chat — alle Mitarbeiter kontaktieren / Gruppen anlegen
            "view:chat", "chat.create_group",
            # Kalender
            "view:calendar",
        ],
    },
    {
        "group_id": "mitarbeiter_kueche",
        "name": "Mitarbeiter Küche",
        "description": (
            "Kuechen-Mitarbeiter: Dashboard, eigene + Abteilungs-Aufgaben, "
            "Ressourcen mit allen Rechten (Stammdaten, Genehmigung, Catering), "
            "Terminplanung, Chat (alle Mitarbeiter), Kalender."
        ),
        "color": "#C87967",
        "capabilities": [
            # Dashboard + Profil
            "view:dashboard",
            # Aufgaben — eigene + Abteilung
            "view:tasks", "tasks.create", "tasks.view_department",
            # Ressourcen — ALLE Rechte (Stammdaten, Genehmigung, alle Buchungen
            # sehen, Catering verwalten + verarbeiten, Rechnungen)
            "view:resources",
            "resources.book", "resources.book_for_others",
            "resources.manage", "resources.approve", "resources.view_all_bookings",
            "catering.manage_items", "catering.process",
            "bookings.invoice", "bookings.invoice.approve",
            # Terminplanung
            "view:scheduling", "scheduling.create_poll",
            # Chat — alle Mitarbeiter kontaktieren
            "view:chat", "chat.create_group",
            # Kalender
            "view:calendar",
        ],
    },
]


# ---------------------------------------------------------------------------
# /admin/seed-preset-groups
# ---------------------------------------------------------------------------

@router.post("/admin/seed-preset-groups")
async def seed_preset_groups(request: Request):
    """Legt die vordefinierten Mitarbeitergruppen idempotent an.

    Aktualisiert Capabilities/Beschreibung bei jedem Aufruf — der Admin
    kann also "Standard wiederherstellen" jederzeit ausfuehren, falls
    jemand die Rechte versehentlich modifiziert hat. Mitgliedschaften
    bleiben dabei erhalten.
    """
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    created: list[str] = []
    updated: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for defn in PRESET_GROUPS:
        gid = defn["group_id"]
        existing = await db.groups.find_one({"group_id": gid}, {"_id": 0})
        payload: Dict[str, Any] = {
            "group_id": gid,
            "name": defn["name"],
            "description": defn["description"],
            "color": defn["color"],
            "capabilities": list(defn["capabilities"]),
            "permissions": [],  # legacy
            "is_system": True,
            # NICHT module_group — diese Gruppen werden vom Admin manuell
            # zugewiesen, nicht automatisch durch sync_user_module_groups.
            "module_group": False,
            "is_preset_group": True,
            "updated_at": now_iso,
        }
        if existing:
            await db.groups.update_one({"group_id": gid}, {"$set": payload})
            updated.append(gid)
        else:
            payload["members"] = []
            payload["created_at"] = now_iso
            await db.groups.insert_one(payload)
            created.append(gid)

    # Permissions-Cache leeren, damit die Aenderung sofort wirkt
    try:
        from services import permissions_cache as pcache
        await pcache.invalidate_all()
    except Exception:
        pass

    return {
        "created": created,
        "updated": updated,
        "groups": [
            {"group_id": g["group_id"], "name": g["name"],
             "capabilities": g["capabilities"]}
            for g in PRESET_GROUPS
        ],
    }


# ---------------------------------------------------------------------------
# /admin/demo-data/wipe
# ---------------------------------------------------------------------------

@router.post("/admin/demo-data/preview")
async def preview_demo_wipe(request: Request):
    """Zaehlt alle Demo-Datenobjekte, die `wipe` loeschen wuerde.

    Demo-Daten erkennen wir an folgenden Mustern (analog zum Resource-Demo-
    Seeder, der bereits "Demo_" vor jeden Namen setzt):
      - resources.name beginnt mit "Demo_"
      - catering_items.name beginnt mit "Demo_"
      - invoice_master_data.code / cost_centers.code / accounts.code
        beginnt mit "DEMO-"
      - resource_bookings, deren resource_id auf eine Demo-Ressource zeigt
      - catering_requests, deren request_id von einer Demo-Buchung
        referenziert wird
      - **Iter 376** — users mit email-Domain `@demo.meetflow.local`
        (System-generierte Demo-User), inkl. kaskadierter Cleanup ihrer
        Buchungen / Tasks / Messages / Notifications / etc.
    """
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    demo_res = await db.resources.find(
        {"name": {"$regex": "^Demo_"}}, {"_id": 0, "resource_id": 1}
    ).to_list(2000)
    demo_rids = [r["resource_id"] for r in demo_res]
    # Kinder von Demo-Eltern mit einbeziehen
    if demo_rids:
        kids = await db.resources.find(
            {"parent_resource_id": {"$in": demo_rids}}, {"_id": 0, "resource_id": 1}
        ).to_list(1000)
        demo_rids.extend(k["resource_id"] for k in kids)

    bk_count = 0
    cr_count = 0
    if demo_rids:
        bk_count = await db.resource_bookings.count_documents(
            {"resource_id": {"$in": demo_rids}}
        )
        # Catering-Requests pro Demo-Buchung
        bk_with_cr = await db.resource_bookings.find(
            {"resource_id": {"$in": demo_rids},
             "catering_request_id": {"$exists": True, "$ne": None}},
            {"_id": 0, "catering_request_id": 1},
        ).to_list(bk_count or 1)
        cr_ids = [b["catering_request_id"] for b in bk_with_cr if b.get("catering_request_id")]
        if cr_ids:
            cr_count = await db.catering_requests.count_documents(
                {"request_id": {"$in": cr_ids}}
            )

    cat_items = await db.catering_items.count_documents({"name": {"$regex": "^Demo_"}})
    md_count = await db.invoice_master_data.count_documents({"code": {"$regex": "^DEMO-"}})
    legacy_cc = await db.cost_centers.count_documents({"code": {"$regex": "^DEMO-"}})
    legacy_acc = await db.accounts.count_documents({"code": {"$regex": "^DEMO-"}})
    legacy_acc2 = await db.accounting_accounts.count_documents({"code": {"$regex": "^DEMO-"}})

    # Iter 376 — Demo-User + kaskadierte Daten
    demo_user_filter = {"email": {"$regex": r".*@demo\.meetflow\.local$"}}
    demo_users = await db.users.find(demo_user_filter, {"_id": 0, "user_id": 1}).to_list(500)
    demo_uids = [u["user_id"] for u in demo_users]
    user_bk_count = 0
    user_tasks_count = 0
    user_msgs_count = 0
    user_notifs_count = 0
    if demo_uids:
        # Buchungen, die NICHT bereits via demo-resource gezaehlt wurden
        user_bk_count = await db.resource_bookings.count_documents(
            {"user_id": {"$in": demo_uids},
             "resource_id": {"$nin": demo_rids} if demo_rids else {"$exists": True}}
        )
        user_tasks_count = await db.tasks.count_documents({"created_by": {"$in": demo_uids}})
        user_msgs_count = await db.messages.count_documents({"sender_id": {"$in": demo_uids}})
        user_notifs_count = await db.notifications.count_documents({"user_id": {"$in": demo_uids}})

    return {
        "demo_resources": len(demo_rids),
        "demo_bookings": bk_count,
        "demo_catering_requests": cr_count,
        "demo_catering_items": cat_items,
        "demo_master_data_entries": md_count,
        "demo_legacy_cost_centers": legacy_cc,
        "demo_legacy_accounts": legacy_acc + legacy_acc2,
        "demo_users": len(demo_uids),
        "demo_user_bookings": user_bk_count,
        "demo_user_tasks": user_tasks_count,
        "demo_user_messages": user_msgs_count,
        "demo_user_notifications": user_notifs_count,
        "total": (
            len(demo_rids) + bk_count + cr_count + cat_items
            + md_count + legacy_cc + legacy_acc + legacy_acc2
            + len(demo_uids) + user_bk_count + user_tasks_count
            + user_msgs_count + user_notifs_count
        ),
    }


@router.post("/admin/demo-data/wipe")
async def wipe_demo_data(request: Request):
    """Loescht alle Demo-Datenobjekte. Idempotent.

    Greift dieselben Praefixe ab wie `/admin/demo-data/preview`. Wird
    sicherheitshalber nur bei `confirm=true` im Body wirklich ausgefuehrt
    — ein Klick auf die Vorschau alleine darf nichts kaputt machen.
    """
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if not body.get("confirm"):
        raise HTTPException(status_code=400, detail="confirm=true required")

    # 1. Demo-Resourcen + ihre Kinder identifizieren
    demo_res = await db.resources.find(
        {"name": {"$regex": "^Demo_"}}, {"_id": 0, "resource_id": 1}
    ).to_list(2000)
    demo_rids = [r["resource_id"] for r in demo_res]
    if demo_rids:
        kids = await db.resources.find(
            {"parent_resource_id": {"$in": demo_rids}}, {"_id": 0, "resource_id": 1}
        ).to_list(1000)
        demo_rids.extend(k["resource_id"] for k in kids)

    deleted = {"resources": 0, "bookings": 0, "catering_requests": 0,
               "catering_items": 0, "master_data": 0,
               "legacy_cost_centers": 0, "legacy_accounts": 0,
               "users": 0, "user_bookings": 0, "user_tasks": 0,
               "user_messages": 0, "user_notifications": 0,
               "user_conversation_memberships": 0}

    if demo_rids:
        # Catering-Requests aus Demo-Buchungen
        bk_with_cr = await db.resource_bookings.find(
            {"resource_id": {"$in": demo_rids},
             "catering_request_id": {"$exists": True, "$ne": None}},
            {"_id": 0, "catering_request_id": 1},
        ).to_list(5000)
        cr_ids = [b["catering_request_id"] for b in bk_with_cr if b.get("catering_request_id")]
        if cr_ids:
            res = await db.catering_requests.delete_many({"request_id": {"$in": cr_ids}})
            deleted["catering_requests"] = res.deleted_count

        res = await db.resource_bookings.delete_many({"resource_id": {"$in": demo_rids}})
        deleted["bookings"] = res.deleted_count
        res = await db.resources.delete_many({"resource_id": {"$in": demo_rids}})
        deleted["resources"] = res.deleted_count

    res = await db.catering_items.delete_many({"name": {"$regex": "^Demo_"}})
    deleted["catering_items"] = res.deleted_count

    res = await db.invoice_master_data.delete_many({"code": {"$regex": "^DEMO-"}})
    deleted["master_data"] = res.deleted_count
    res = await db.cost_centers.delete_many({"code": {"$regex": "^DEMO-"}})
    deleted["legacy_cost_centers"] = res.deleted_count
    res1 = await db.accounts.delete_many({"code": {"$regex": "^DEMO-"}})
    res2 = await db.accounting_accounts.delete_many({"code": {"$regex": "^DEMO-"}})
    deleted["legacy_accounts"] = res1.deleted_count + res2.deleted_count

    # Iter 376 — Demo-User + kaskadierte Daten loeschen.
    # Wir matchen ausschliesslich die spezifische Domain `@demo.meetflow.local`,
    # damit QA-Accounts (qa_*@meetflow.com) und echte User unangetastet bleiben.
    demo_user_filter = {"email": {"$regex": r".*@demo\.meetflow\.local$"}}
    demo_users = await db.users.find(demo_user_filter, {"_id": 0, "user_id": 1}).to_list(500)
    demo_uids = [u["user_id"] for u in demo_users]
    if demo_uids:
        # Buchungen, die nicht schon ueber Demo-Ressourcen weg sind
        res = await db.resource_bookings.delete_many({"user_id": {"$in": demo_uids}})
        deleted["user_bookings"] = res.deleted_count
        # Tasks vom Demo-User erstellt
        res = await db.tasks.delete_many({"created_by": {"$in": demo_uids}})
        deleted["user_tasks"] = res.deleted_count
        # Chat-Nachrichten von Demo-Usern
        res = await db.messages.delete_many({"sender_id": {"$in": demo_uids}})
        deleted["user_messages"] = res.deleted_count
        # Notifications
        res = await db.notifications.delete_many({"user_id": {"$in": demo_uids}})
        deleted["user_notifications"] = res.deleted_count
        # Aus Conversation-Memberships entfernen (Conversations selbst bleiben
        # erhalten, wenn auch echte User Mitglied sind).
        conv_pull = await db.conversations.update_many(
            {"members.user_id": {"$in": demo_uids}},
            {"$pull": {"members": {"user_id": {"$in": demo_uids}}}}
        )
        deleted["user_conversation_memberships"] = conv_pull.modified_count
        # Diverse Annex-Collections (best-effort, silent on missing collection)
        for coll in ("push_subscriptions", "focus_times", "login_attempts",
                     "user_busy_slots", "notification_prefs",
                     "password_reset_tokens", "email_verification_tokens",
                     "user_keys", "user_favorites", "auth_refresh_log",
                     "meeting_participants"):
            try:
                await db[coll].delete_many({"user_id": {"$in": demo_uids}})
            except Exception:
                pass
        # Schliesslich die User selbst
        res = await db.users.delete_many(demo_user_filter)
        deleted["users"] = res.deleted_count

    deleted["total"] = sum(v for k, v in deleted.items() if k != "total")
    return deleted
