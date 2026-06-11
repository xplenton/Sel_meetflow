"""
Seed demo resources & catering items for the new Resources Module (iter 223).

Idempotent: each entity uses a deterministic resource_id/item_id so the script
can be run multiple times without duplicating data.

Demo set:
  - 1 splitable meeting room "Grosser Saal" with 3 sub-rooms (A/B/C)
  - 1 normal meeting room "Besprechung 1.05" (requires_approval)
  - 1 desk "Desk D-12"
  - 1 vehicle "VW Caddy (M-AB 1234)"
  - 5 catering items
"""
import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)

    # 1. Splitable big room "Grosser Saal" (A/B/C)
    saal_id = "res_demo_saal_001"
    await db.resources.update_one(
        {"resource_id": saal_id},
        {"$set": {
            "resource_id": saal_id,
            "name": "Grosser Saal",
            "type": "room",
            "location": "Hauptgebaeude",
            "building": "Haus A",
            "floor": "EG",
            "room": "0.10",
            "capacity": 60,
            "equipment": ["Beamer", "Mikrofon", "Whiteboard", "Videokonferenz"],
            "seating": "U-Form",
            "status": "active",
            "is_splitable": True,
            "allow_catering": True,
            "requires_approval": False,
            "allowed_combinations": [["A"], ["B"], ["C"], ["A", "B"], ["B", "C"], ["A", "B", "C"]],
            "sub_resources": [
                {"sub_id": "A", "name": "Bereich A", "capacity": 20, "equipment": ["Beamer"]},
                {"sub_id": "B", "name": "Bereich B", "capacity": 20, "equipment": ["Whiteboard"]},
                {"sub_id": "C", "name": "Bereich C", "capacity": 20, "equipment": ["Mikrofon"]},
            ],
            "parent_resource_id": None,
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    # Children (independent bookability for each split section)
    for sub in ["A", "B", "C"]:
        child_id = f"res_demo_saal_{sub}"
        await db.resources.update_one(
            {"resource_id": child_id},
            {"$set": {
                "resource_id": child_id,
                "name": f"Grosser Saal — Bereich {sub}",
                "type": "room",
                "location": "Hauptgebaeude",
                "building": "Haus A",
                "floor": "EG",
                "capacity": 20,
                "equipment": [],
                "status": "active",
                "parent_resource_id": saal_id,
                "sub_id": sub,
                "allow_catering": True,
                "created_at": now,
                "updated_at": now,
            }},
            upsert=True,
        )

    # 2. Standard room requiring approval
    await db.resources.update_one(
        {"resource_id": "res_demo_bes_105"},
        {"$set": {
            "resource_id": "res_demo_bes_105",
            "name": "Besprechung 1.05",
            "type": "room",
            "location": "Hauptgebaeude",
            "building": "Haus A",
            "floor": "1. OG",
            "capacity": 8,
            "equipment": ["Bildschirm", "Telefon"],
            "status": "active",
            "requires_approval": True,
            "allow_catering": True,
            "min_duration_min": 15,
            "max_duration_min": 480,
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )

    # 3. Desk
    await db.resources.update_one(
        {"resource_id": "res_demo_desk_12"},
        {"$set": {
            "resource_id": "res_demo_desk_12",
            "name": "Desk D-12",
            "type": "desk",
            "location": "Hauptgebaeude",
            "building": "Haus B",
            "floor": "2. OG",
            "desk_number": "D-12",
            "equipment": ["Monitor x2", "Dockingstation"],
            "accessibility": "barrierefrei",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )

    # 4. Vehicle
    await db.resources.update_one(
        {"resource_id": "res_demo_car_caddy"},
        {"$set": {
            "resource_id": "res_demo_car_caddy",
            "name": "VW Caddy",
            "type": "vehicle",
            "location": "Tiefgarage",
            "license_plate": "M-AB 1234",
            "vehicle_type": "Kombi",
            "seats": 5,
            "fuel_card": True,
            "mileage": 84500,
            "status": "active",
            "requires_approval": False,
            "min_duration_min": 30,
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )

    # 5. Catering items
    items = [
        {"item_id": "cit_kaffee", "name": "Kaffee", "category": "Getränk", "price": 1.5, "unit": "Tasse", "lead_time_min": 30},
        {"item_id": "cit_wasser", "name": "Wasser (still)", "category": "Getränk", "price": 1.0, "unit": "Flasche", "lead_time_min": 15},
        {"item_id": "cit_brezel", "name": "Brezel", "category": "Snack", "price": 1.8, "unit": "Stueck", "lead_time_min": 45},
        {"item_id": "cit_obstplatte", "name": "Obstplatte", "category": "Snack", "price": 12.0, "unit": "Platte", "min_quantity": 1, "lead_time_min": 120},
        {"item_id": "cit_mittagsbuffet", "name": "Mittagsbuffet", "category": "Mahlzeit", "price": 14.5, "unit": "Person", "min_quantity": 5, "lead_time_min": 240},
    ]
    for it in items:
        await db.catering_items.update_one(
            {"item_id": it["item_id"]},
            {"$set": {**it, "available": True, "status": "active", "created_at": now}},
            upsert=True,
        )

    print("Seed done.")
    print(f"  resources:      {await db.resources.count_documents({})}")
    print(f"  catering_items: {await db.catering_items.count_documents({})}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
