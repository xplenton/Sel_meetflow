"""
Resources/admin · Demo-data seed.

POST /resources-seed-demo — Idempotent: bestehende Demo-Objekte (Praefix
'Demo_') werden vorher geloescht, danach ~10+ rooms, 12 desks, 10 vehicles,
15 catering items, 10 cost centers, 5 accounts und ~30 Beispiel-Buchungen
ueber die naechsten 14 Tage angelegt.

Iter 376 — zusaetzlich werden 5 Demo-Benutzer (`Demo_*` mit Email-Domain
`@demo.meetflow.local`) angelegt, sodass der „Demo-Daten entfernen"-Wipe
auch System-generierte User mit-aufraeumen kann.
"""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
import uuid
import secrets
from passlib.hash import bcrypt

from database import db
from dependencies import get_current_user
from services.permissions import require_cap

router = APIRouter()

# Iter 376 — Erkennungsmuster fuer System-generierte Demo-User. Wird sowohl
# beim Seeden (Cleanup vor Insert) als auch beim Wipe (Identifikation) benutzt.
# Wichtig: nur diese spezifische Domain wird gematcht, damit QA-Tester (z.B.
# `qa_admin@meetflow.com`) NICHT versehentlich geloescht werden.
DEMO_USER_EMAIL_DOMAIN = "@demo.meetflow.local"
DEMO_USER_PASSWORD = "demo_password_2026"


@router.post("/resources-seed-demo")
async def seed_demo_resources(user=Depends(get_current_user)):
    """Erzeugt eine umfangreiche Demo-Datenbasis: 10+ Raeume (inkl. teilbare,
    freigabepflichtige, mit Catering), 10+ Desks, 10+ Fahrzeuge (verschiedene
    Antriebsarten), 10+ Catering-Items, 10+ Kostenstellen, 5+ Konten, dazu
    ~30 Beispiel-Buchungen ueber die naechsten 14 Tage.
    Idempotent: bestehende Demo-Objekte (Praefix 'Demo_') werden vorher geloescht.
    """
    await require_cap(user, "resources.manage", db)
    # Iter 269 — Use secrets.SystemRandom (CSPRNG) instead of `random` to satisfy
    # security scanners, even though this is just demo seeding (no security
    # impact). Drop-in replacement: same method names (choice/randint/sample).
    rand = secrets.SystemRandom()

    # ---- 1. Cleanup vorheriger Demo-Daten -----------------------------------
    cleanup_pref = {"name": {"$regex": "^Demo_"}}
    demo_res = await db.resources.find(cleanup_pref, {"_id": 0, "resource_id": 1}).to_list(1000)
    demo_rids = [r["resource_id"] for r in demo_res]
    # Kinder von Demo-Eltern
    demo_kids = await db.resources.find({"parent_resource_id": {"$in": demo_rids}}, {"_id": 0, "resource_id": 1}).to_list(500)
    demo_rids.extend(k["resource_id"] for k in demo_kids)
    if demo_rids:
        bk_demo = await db.resource_bookings.find({"resource_id": {"$in": demo_rids}}, {"_id": 0, "catering_request_id": 1}).to_list(2000)
        cr_demo = [b["catering_request_id"] for b in bk_demo if b.get("catering_request_id")]
        await db.resource_bookings.delete_many({"resource_id": {"$in": demo_rids}})
        await db.catering_requests.delete_many({"request_id": {"$in": cr_demo}})
        await db.resources.delete_many({"resource_id": {"$in": demo_rids}})
    await db.catering_items.delete_many({"name": {"$regex": "^Demo_"}})
    # Iter 297 — Stammdaten leben jetzt im unified invoice_master_data
    await db.invoice_master_data.delete_many({"code": {"$regex": "^DEMO-"}})
    # Legacy collections (falls noch Reste): aufräumen damit Migration weiß "leer"
    await db.cost_centers.delete_many({"code": {"$regex": "^DEMO-"}})
    await db.accounts.delete_many({"code": {"$regex": "^DEMO-"}})
    await db.accounting_accounts.delete_many({"code": {"$regex": "^DEMO-"}})
    # Iter 376 — Auch Demo-User aus vorherigen Seed-Laeufen entfernen, damit
    # der Insert weiter unten nicht an unique-email-Konflikten scheitert.
    await db.users.delete_many({"email": {"$regex": f".*{DEMO_USER_EMAIL_DOMAIN}$"}})

    created = {"rooms": [], "desks": [], "vehicles": [],
               "catering_items": [], "cost_centers": [], "accounts": [],
               "users": [], "bookings": 0}

    # ---- 2a. Demo-User (Iter 376) ------------------------------------------
    # 5 Beispiel-User mit unterschiedlichen Rollen, alle email-verified, sodass
    # sie sich sofort einloggen koennen. Die User-IDs werden weiter unten fuer
    # die Beispiel-Buchungen verwendet, statt alles dem aufrufenden Admin
    # zuzuordnen — dadurch wirkt der Demo-Datensatz realistischer.
    demo_users_seed = [
        ("Demo_Anna_Schmidt",   "demo_anna",    "member",    "Innere Medizin"),
        ("Demo_Markus_Becker",  "demo_markus",  "member",    "Chirurgie"),
        ("Demo_Lisa_Krueger",   "demo_lisa",    "moderator", "Verwaltung"),
        ("Demo_Tobias_Wagner",  "demo_tobias",  "member",    "IT-Abteilung"),
        ("Demo_Sandra_Hoffmann","demo_sandra",  "member",    "Paediatrie"),
    ]
    pw_hash = bcrypt.hash(DEMO_USER_PASSWORD)
    for full_name, local, role, dept in demo_users_seed:
        uid = f"usr_demo_{uuid.uuid4().hex[:10]}"
        await db.users.insert_one({
            "user_id": uid,
            "email": f"{local}{DEMO_USER_EMAIL_DOMAIN}",
            "name": full_name,
            "first_name": full_name.split("_")[1],
            "last_name": full_name.split("_", 2)[2] if len(full_name.split("_")) > 2 else "",
            "password_hash": pw_hash,
            "role": role,
            "department": dept,
            "email_verified": True,
            "email_verified_at": datetime.now(timezone.utc),
            "email_verified_by": "demo-seeder",
            "verification_method": "demo-seeder",
            "groups": [],
            "online": False,
            "status_mode": "offline",
            "token_version": 0,
            "created_at": datetime.now(timezone.utc),
        })
        created["users"].append(uid)

    # ---- 2. Cost-Centers + Konten (Iter 297 — unified Stammdaten) ----------
    cc_seed = [
        ("DEMO-100", "Innere Medizin"),
        ("DEMO-200", "Chirurgie"),
        ("DEMO-300", "Kardiologie"),
        ("DEMO-400", "Onkologie"),
        ("DEMO-500", "Paediatrie"),
        ("DEMO-600", "Radiologie"),
        ("DEMO-700", "Anaesthesie"),
        ("DEMO-800", "Notaufnahme"),
        ("DEMO-900", "Verwaltung"),
        ("DEMO-IT", "IT-Abteilung"),
    ]
    for code, name in cc_seed:
        await db.invoice_master_data.insert_one({
            "item_id": f"md_demo_cc_{code.lower().replace('-','_')}",
            "type": "cost_center",
            "code": code, "label": name,
            "active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        created["cost_centers"].append(code)

    acc_seed = [
        ("DEMO-8400", "Catering-Erloese"),
        ("DEMO-8410", "Tagungspauschalen"),
        ("DEMO-6100", "Personalverpflegung"),
        ("DEMO-4920", "Fahrzeugkosten"),
        ("DEMO-4630", "Mietkosten Raeume"),
    ]
    for code, name in acc_seed:
        await db.invoice_master_data.insert_one({
            "item_id": f"md_demo_ac_{code.lower().replace('-','_')}",
            "type": "account",
            "code": code, "label": name,
            "active": True,
            "created_at": datetime.now(timezone.utc),
        })
        created["accounts"].append(code)

    # ---- 3. Raeume (12 Stueck) ----------------------------------------------
    rooms = [
        # (name, capacity, location, building, floor, equipment, splitable, allow_catering, requires_approval)
        ("Demo_Konferenzsaal_Nord",   40, "Hauptgebaeude", "Haus A", "EG",  ["Beamer", "Whiteboard", "Videokonferenz", "Klimaanlage"], True, True, True),
        ("Demo_Besprechung_101",       8, "Hauptgebaeude", "Haus A", "1.OG", ["Beamer", "Whiteboard"], False, False, False),
        ("Demo_Besprechung_102",      10, "Hauptgebaeude", "Haus A", "1.OG", ["TV-Bildschirm", "Konferenztelefon"], False, True, False),
        ("Demo_Schulungsraum",        25, "Bildungszentrum", "Haus C", "EG", ["Beamer", "Flipchart", "Whiteboard", "Mikrofon"], False, True, False),
        ("Demo_Direktorium",          12, "Hauptgebaeude", "Haus A", "3.OG", ["TV-Bildschirm", "Konferenztelefon", "Klimaanlage"], False, True, True),
        ("Demo_Workshop_A",           20, "Bildungszentrum", "Haus C", "1.OG", ["Beamer", "Whiteboard", "Steckdosen"], True, True, False),
        ("Demo_Buero_Klein",           4, "Verwaltung", "Haus B", "2.OG", ["TV-Bildschirm"], False, False, False),
        ("Demo_OP_Vorbesprechung",     6, "Chirurgie", "Haus D", "1.OG", ["Lichttafel", "Whiteboard"], False, False, True),
        ("Demo_Cafeteria_Tagung",     30, "Cafeteria", "Haus E", "EG", ["Buffet-Bereich", "Beamer"], False, True, False),
        ("Demo_Pavillon_Garten",      50, "Garten", "Pavillon", "EG", ["Buffet-Bereich", "Mikrofon", "Klimaanlage"], False, True, True),
        ("Demo_Telemed_1",             3, "Telemedizin", "Haus A", "2.OG", ["Videokonferenz", "Mikrofon", "TV-Bildschirm"], False, False, False),
        ("Demo_Telemed_2",             3, "Telemedizin", "Haus A", "2.OG", ["Videokonferenz", "Mikrofon", "TV-Bildschirm"], False, False, False),
    ]
    for name, cap, loc, bldg, flr, eq, splitable, cater, approve in rooms:
        rid = f"res_demo_{uuid.uuid4().hex[:10]}"
        doc = {
            "resource_id": rid, "name": name, "type": "room",
            "capacity": cap, "location": loc, "building": bldg, "floor": flr,
            "equipment": eq, "is_splitable": splitable,
            "allow_catering": cater, "requires_approval": approve,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        }
        if splitable:
            doc["allowed_combinations"] = [["A"], ["B"], ["C"], ["A","B"], ["B","C"], ["A","B","C"]]
        await db.resources.insert_one(doc)
        created["rooms"].append(rid)
        # Kinder fuer teilbare Raeume
        if splitable:
            for sub_id, sub_cap in [("A", cap // 3), ("B", cap // 3), ("C", cap - 2*(cap // 3))]:
                child_id = f"res_demo_{uuid.uuid4().hex[:10]}"
                await db.resources.insert_one({
                    "resource_id": child_id, "name": f"{name} — Bereich {sub_id}",
                    "type": "room", "parent_resource_id": rid, "sub_id": sub_id,
                    "capacity": sub_cap, "location": loc, "building": bldg, "floor": flr,
                    "equipment": eq, "is_splitable": False, "allow_catering": cater,
                    "requires_approval": approve, "status": "active",
                    "created_at": datetime.now(timezone.utc),
                })

    # ---- 4. Desks (12 Stueck) -----------------------------------------------
    for i in range(12):
        bldg = "Verwaltung Open-Space" if i < 6 else "IT-Abteilung"
        flr = "1.OG" if i < 6 else "2.OG"
        rid = f"res_demo_{uuid.uuid4().hex[:10]}"
        # Mittelpunkt-Position fuer Floorplan: gleichmaessig auf Grid 4x3
        col = i % 4
        row = i // 4
        await db.resources.insert_one({
            "resource_id": rid,
            "name": f"Demo_Desk_{bldg.split()[0]}_{i+1:02d}",
            "type": "desk", "location": bldg, "building": bldg, "floor": flr,
            "desk_number": f"DSK-{i+1:03d}",
            "equipment": (["Dock", "Dual-Monitor", "Webcam"] if i % 2 == 0 else ["Dock", "Single-Monitor"]),
            "status": "active",
            "floor_plan_id": "default",
            "floor_plan_x": 0.15 + col * 0.22,
            "floor_plan_y": 0.20 + row * 0.25,
            "created_at": datetime.now(timezone.utc),
        })
        created["desks"].append(rid)

    # ---- 5. Fahrzeuge (10 Stueck) -------------------------------------------
    vehicles = [
        ("Demo_Tesla_Model_3",       "B-EV 1001", "Limousine",   5, True, "DKV-001", "elektro"),
        ("Demo_VW_eGolf",            "B-EV 1002", "Kompakt",     5, True, "DKV-002", "elektro"),
        ("Demo_Mercedes_Vito",       "B-MD 2001", "Transporter", 9, True, "DKV-003", "diesel"),
        ("Demo_BMW_3er_Hybrid",      "B-HY 3001", "Limousine",   5, True, "DKV-004", "hybrid"),
        ("Demo_Audi_Q5_Hybrid",      "B-HY 3002", "SUV",         5, True, "DKV-005", "hybrid"),
        ("Demo_Skoda_Octavia",       "B-BE 4001", "Kombi",       5, True, "DKV-006", "benzin"),
        ("Demo_Ford_Transit",        "B-DI 5001", "Transporter", 3, True, "DKV-007", "diesel"),
        ("Demo_Toyota_Yaris",        "B-BE 4002", "Kleinwagen",  5, False, None,     "benzin"),
        ("Demo_Renault_Zoe",         "B-EV 1003", "Kleinwagen",  4, True, "DKV-008", "elektro"),
        ("Demo_Notarztwagen_Alpha",  "B-NOT 99",  "Notarzt",     3, True, "DKV-009", "diesel"),
    ]
    for name, plate, vtype, seats, has_card, card_no, drive in vehicles:
        rid = f"res_demo_{uuid.uuid4().hex[:10]}"
        await db.resources.insert_one({
            "resource_id": rid, "name": name, "type": "vehicle",
            "license_plate": plate, "vehicle_type": vtype, "seats": seats,
            "fuel_card": has_card, "fuel_card_number": card_no,
            "drive_type": drive, "status": "active",
            "mileage": rand.randint(5000, 90000),
            "requires_approval": ("Notarzt" in vtype),
            "created_at": datetime.now(timezone.utc),
        })
        created["vehicles"].append(rid)

    # ---- 6. Catering-Items (15 Stueck) --------------------------------------
    catering = [
        ("Demo_Kaffee_Filter",      1.50, "Stueck",  "beverage"),
        ("Demo_Cappuccino",         2.20, "Stueck",  "beverage"),
        ("Demo_Mineralwasser_05",   1.20, "Flasche", "beverage"),
        ("Demo_Orangensaft",        2.50, "Glas",    "beverage"),
        ("Demo_Tee_Sortiment",      1.50, "Tasse",   "beverage"),
        ("Demo_Brezel",             1.80, "Stueck",  "snack"),
        ("Demo_Belegtes_Broetchen", 2.80, "Stueck",  "snack"),
        ("Demo_Obstteller",         4.50, "Person",  "snack"),
        ("Demo_Kuchen_Stueck",      3.20, "Stueck",  "snack"),
        ("Demo_Salat_Schale",       6.50, "Person",  "meal"),
        ("Demo_Mittagsbuffet_Veg",  12.00, "Person", "meal"),
        ("Demo_Mittagsbuffet_Std",  14.50, "Person", "meal"),
        ("Demo_Sandwich_Platte",     9.00, "Platte", "meal"),
        ("Demo_Tagungspauschale_Halbtag", 18.00, "Person", "package"),
        ("Demo_Tagungspauschale_Ganztag", 28.00, "Person", "package"),
    ]
    for name, price, unit, cat in catering:
        iid = f"cat_demo_{uuid.uuid4().hex[:8]}"
        await db.catering_items.insert_one({
            "item_id": iid, "name": name, "price": price, "unit": unit,
            "category": cat, "active": True,
            "created_at": datetime.now(timezone.utc),
        })
        created["catering_items"].append(iid)

    # ---- 7. Beispiel-Buchungen ueber 14 Tage --------------------------------
    now_utc = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    bk_count = 0
    for day_offset in range(14):
        day_start = now_utc.replace(hour=8, minute=0) + timedelta(days=day_offset)
        # Pro Tag 3-5 Buchungen auf zufaelligen Raeumen + 1 Vehicle + 2 Desks
        for _ in range(rand.randint(3, 5)):
            rid = rand.choice(created["rooms"])
            hour_start = rand.choice([8, 9, 10, 13, 14, 15])
            dur = rand.choice([60, 90, 120])
            s = day_start.replace(hour=hour_start)
            e = s + timedelta(minutes=dur)
            res = await db.resources.find_one({"resource_id": rid}, {"_id": 0})
            booking = {
                "booking_id": f"bk_demo_{uuid.uuid4().hex[:10]}",
                "resource_id": rid,
                "title": rand.choice([
                    "Teambesprechung", "OP-Vorbesprechung", "Tumor-Board",
                    "Schulung Hygiene", "Pflege-Fortbildung", "Visite",
                    "Direktorium-Sitzung", "Patienten-Konferenz",
                ]),
                "start_at": s, "end_at": e,
                # Iter 376 — Buchungen den Demo-Usern zuordnen (statt alles dem
                # aufrufenden Admin), damit der Datensatz realistischer wirkt.
                "user_id": rand.choice(created["users"]) if created["users"] else user["user_id"],
                "status": "pending_approval" if res.get("requires_approval") else "confirmed",
                "cost_center": rand.choice([c[0] for c in cc_seed]),
                "created_at": datetime.now(timezone.utc),
            }
            try:
                await db.resource_bookings.insert_one(booking)
                bk_count += 1
            except Exception:
                pass
        # 1 Fahrzeug-Buchung
        v_rid = rand.choice(created["vehicles"])
        s = day_start.replace(hour=rand.choice([9, 11, 14]))
        e = s + timedelta(hours=rand.choice([2, 3, 4]))
        try:
            await db.resource_bookings.insert_one({
                "booking_id": f"bk_demo_{uuid.uuid4().hex[:10]}",
                "resource_id": v_rid, "title": "Dienstfahrt",
                "destination": rand.choice(["Klinikum Mitte", "Aussenstelle Sued", "Tochterklinik Ost"]),
                "mileage_before": rand.randint(10000, 80000),
                "start_at": s, "end_at": e,
                "user_id": rand.choice(created["users"]) if created["users"] else user["user_id"],
                "status": "confirmed",
                "created_at": datetime.now(timezone.utc),
            })
            bk_count += 1
        except Exception:
            pass
        # 2 Desk-Buchungen
        for d_rid in rand.sample(created["desks"], 2):
            try:
                await db.resource_bookings.insert_one({
                    "booking_id": f"bk_demo_{uuid.uuid4().hex[:10]}",
                    "resource_id": d_rid, "title": "Desk-Sharing",
                    "start_at": day_start.replace(hour=8),
                    "end_at": day_start.replace(hour=17),
                    "user_id": rand.choice(created["users"]) if created["users"] else user["user_id"],
                    "status": "confirmed",
                    "created_at": datetime.now(timezone.utc),
                })
                bk_count += 1
            except Exception:
                pass
    created["bookings"] = bk_count

    return {
        "status": "ok",
        "created": {
            "rooms": len(created["rooms"]),
            "desks": len(created["desks"]),
            "vehicles": len(created["vehicles"]),
            "catering_items": len(created["catering_items"]),
            "cost_centers": len(created["cost_centers"]),
            "accounts": len(created["accounts"]),
            "users": len(created["users"]),
            "bookings": created["bookings"],
        },
        "demo_user_credentials": {
            "domain": DEMO_USER_EMAIL_DOMAIN,
            "password": DEMO_USER_PASSWORD,
            "note": "Alle Demo-User teilen dasselbe Passwort. Email = <vorname>@demo.meetflow.local",
        },
        "message": "Demo-Daten erfolgreich angelegt.",
    }
