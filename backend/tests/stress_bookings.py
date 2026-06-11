"""
Iter 232 — Stress-Test fuer Ressourcen-Buchungen (Iter 232 / Sprint 9).

Simuliert 50 nebenlaeufige Anwender, die parallel
  - neue Buchungen anlegen (Raeume / Desks / Fahrzeuge)
  - bestehende Buchungen editieren
  - Buchungen stornieren
  - Catering-Anfragen erzeugen
auf einer Reihe verschieden konfigurierter Ressourcen (normal, teilbar,
freigabepflichtig, mit Catering, Fahrzeug mit Antriebsart).

Misst Latenzen, Erfolgs-/Konflikt-/Fehler-Quote und schreibt einen
JSON-Report nach /tmp/booking_stress_report.json.

Ausfuehrung: python3 /app/backend/tests/stress_bookings.py
"""
import asyncio
import json
import random
import statistics
import time
from datetime import datetime, timedelta, timezone
import httpx


def _read_api():
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                return line.split("=", 1)[1].strip().rstrip("/")
API = _read_api()
ADMIN = {"email": "admin@meetflow.com", "password": "admin123"}
CONCURRENCY = 50
OPS_PER_WORKER = 10
TOTAL_OPS = CONCURRENCY * OPS_PER_WORKER  # 500


# ---------------- Setup-Phase ----------------------------------------------
async def setup_resources(client: httpx.AsyncClient) -> dict:
    """Legt eine bunte Mischung an Ressourcen fuer die Last an."""
    base = int(time.time())
    created = {"rooms": [], "split_rooms": [], "approval_rooms": [],
               "catering_rooms": [], "desks": [], "vehicles": []}

    # 5 normale Raeume
    for i in range(5):
        r = await client.post(f"{API}/api/resources", json={
            "name": f"StressRoom_{base}_{i}", "type": "room",
            "capacity": 10 + i, "location": f"Bau {chr(65+i)}",
        })
        if r.status_code == 200:
            created["rooms"].append(r.json()["resource_id"])

    # 3 teilbare Raeume (mit A/B/C)
    for i in range(3):
        r = await client.post(f"{API}/api/resources", json={
            "name": f"StressSplit_{base}_{i}", "type": "room",
            "capacity": 30, "is_splitable": True,
            "allowed_combinations": [["A"], ["B"], ["C"], ["A","B"], ["B","C"], ["A","B","C"]],
            "sub_resources": [
                {"sub_id": "A", "name": "A", "capacity": 10},
                {"sub_id": "B", "name": "B", "capacity": 10},
                {"sub_id": "C", "name": "C", "capacity": 10},
            ],
        })
        if r.status_code == 200:
            data = r.json()
            full = await client.get(f"{API}/api/resources/{data['resource_id']}")
            kids = full.json().get("children", [])
            created["split_rooms"].append({
                "parent": data["resource_id"],
                "subs": {c["sub_id"]: c["resource_id"] for c in kids},
            })

    # 2 freigabepflichtige Raeume
    for i in range(2):
        r = await client.post(f"{API}/api/resources", json={
            "name": f"StressApproval_{base}_{i}", "type": "room",
            "requires_approval": True, "capacity": 20,
        })
        if r.status_code == 200:
            created["approval_rooms"].append(r.json()["resource_id"])

    # 2 Catering-Raeume
    for i in range(2):
        r = await client.post(f"{API}/api/resources", json={
            "name": f"StressCater_{base}_{i}", "type": "room",
            "allow_catering": True, "capacity": 15,
        })
        if r.status_code == 200:
            created["catering_rooms"].append(r.json()["resource_id"])

    # 5 Desks
    for i in range(5):
        r = await client.post(f"{API}/api/resources", json={
            "name": f"StressDesk_{base}_{i}", "type": "desk",
            "desk_number": f"S-{base}-{i}",
        })
        if r.status_code == 200:
            created["desks"].append(r.json()["resource_id"])

    # 3 Fahrzeuge mit verschiedener Antriebsart
    for i, drive in enumerate(["benzin", "elektro", "hybrid"]):
        r = await client.post(f"{API}/api/resources", json={
            "name": f"StressCar_{base}_{drive}", "type": "vehicle",
            "license_plate": f"B-ST-{base % 1000}{i}",
            "vehicle_type": "Kompakt", "seats": 5,
            "fuel_card": True, "fuel_card_number": f"DKV-{base}-{i}",
            "drive_type": drive,
        })
        if r.status_code == 200:
            created["vehicles"].append(r.json()["resource_id"])

    # 3 Catering-Items
    cater_ids = []
    for i, (name, price) in enumerate([("Kaffee", 1.5), ("Brezel", 2.0), ("Saft", 2.5)]):
        r = await client.post(f"{API}/api/catering-items", json={
            "name": f"Stress_{name}_{base}", "price": price, "unit": "Stueck",
            "category": "beverage" if "Kaffee" in name or "Saft" in name else "snack",
        })
        if r.status_code == 200:
            cater_ids.append(r.json()["item_id"])
    created["catering_items"] = cater_ids
    return created


async def teardown(client: httpx.AsyncClient, created: dict):
    """Cleanup — direkt ueber MongoDB damit auch cancelled/orphan bookings weg sind."""
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    mc = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = mc[os.environ.get("DB_NAME", "test_database")]
    all_res = list(created["rooms"]) + list(created["approval_rooms"]) + \
        list(created["catering_rooms"]) + list(created["desks"]) + list(created["vehicles"])
    for sp in created["split_rooms"]:
        all_res.append(sp["parent"])
        all_res.extend(sp["subs"].values())
    # Catering requests linked to those bookings
    bks = await db.resource_bookings.find(
        {"resource_id": {"$in": all_res}},
        {"_id": 0, "booking_id": 1, "catering_request_id": 1},
    ).to_list(5000)
    cr_ids = [b["catering_request_id"] for b in bks if b.get("catering_request_id")]
    await db.resource_bookings.delete_many({"resource_id": {"$in": all_res}})
    await db.catering_requests.delete_many({"request_id": {"$in": cr_ids}})
    await db.resources.delete_many({"resource_id": {"$in": all_res}})
    await db.catering_items.delete_many({"item_id": {"$in": created.get("catering_items", [])}})
    mc.close()


# ---------------- Worker-Logic ---------------------------------------------
class Stats:
    def __init__(self):
        self.results: list = []  # tuples (op, status_code, latency_ms, error)
        self.created_bookings: list = []  # for edit/cancel later
        self.lock = asyncio.Lock()

    async def add(self, op, status, latency_ms, error=None):
        async with self.lock:
            self.results.append((op, status, latency_ms, error))

    async def add_booking(self, booking_id):
        async with self.lock:
            self.created_bookings.append(booking_id)

    async def pop_booking(self):
        async with self.lock:
            if not self.created_bookings:
                return None
            idx = random.randrange(len(self.created_bookings))
            return self.created_bookings.pop(idx)


async def op_create_room(client, resources, stats):
    rid = random.choice(resources["rooms"] + resources["catering_rooms"] + resources["approval_rooms"])
    start = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30), hours=random.randint(7, 17), minutes=random.choice([0, 15, 30, 45]))
    duration = random.choice([30, 60, 90, 120])
    body = {
        "resource_id": rid,
        "title": f"Stress-Buchung {start.strftime('%H:%M')}",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(minutes=duration)).isoformat(),
        "purpose": "Load-Test",
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{API}/api/resource-bookings", json=body, timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("create_room", r.status_code, lat,
                        None if r.status_code in (200, 409) else r.text[:120])
        if r.status_code == 200:
            await stats.add_booking(r.json()["booking_id"])
    except Exception as e:
        await stats.add("create_room", 0, (time.perf_counter() - t0) * 1000, str(e))


async def op_create_split(client, resources, stats):
    sp = random.choice(resources["split_rooms"])
    sub_id = random.choice(list(sp["subs"].keys()))
    target = sp["subs"][sub_id]
    start = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30), hours=random.randint(7, 17))
    duration = random.choice([60, 90, 120])
    body = {
        "resource_id": target,
        "title": f"Bereich {sub_id}",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(minutes=duration)).isoformat(),
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{API}/api/resource-bookings", json=body, timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("create_split_sub", r.status_code, lat,
                        None if r.status_code in (200, 409) else r.text[:120])
        if r.status_code == 200:
            await stats.add_booking(r.json()["booking_id"])
    except Exception as e:
        await stats.add("create_split_sub", 0, (time.perf_counter() - t0) * 1000, str(e))


async def op_create_combo(client, resources, stats):
    sp = random.choice(resources["split_rooms"])
    subs = random.choice([["A", "B"], ["B", "C"], ["A", "B", "C"]])
    start = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30), hours=random.randint(7, 17))
    body = {
        "parent_resource_id": sp["parent"],
        "sub_ids": subs,
        "title": f"Kombi {'+'.join(subs)}",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=2)).isoformat(),
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{API}/api/resource-bookings/combo", json=body, timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("create_combo", r.status_code, lat,
                        None if r.status_code in (200, 409) else r.text[:120])
        if r.status_code == 200 and r.json().get("booking_ids"):
            for bid in r.json()["booking_ids"]:
                await stats.add_booking(bid)
    except Exception as e:
        await stats.add("create_combo", 0, (time.perf_counter() - t0) * 1000, str(e))


async def op_create_desk(client, resources, stats):
    rid = random.choice(resources["desks"])
    start = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=random.randint(1, 30))
    body = {
        "resource_id": rid,
        "title": "Desk-Sharing",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=8)).isoformat(),
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{API}/api/resource-bookings", json=body, timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("create_desk", r.status_code, lat,
                        None if r.status_code in (200, 409) else r.text[:120])
        if r.status_code == 200:
            await stats.add_booking(r.json()["booking_id"])
    except Exception as e:
        await stats.add("create_desk", 0, (time.perf_counter() - t0) * 1000, str(e))


async def op_create_vehicle(client, resources, stats):
    rid = random.choice(resources["vehicles"])
    start = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30), hours=random.randint(7, 16))
    body = {
        "resource_id": rid,
        "title": "Dienstfahrt",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=random.choice([2, 4, 6]))).isoformat(),
        "destination": random.choice(["Berlin Mitte", "Klinikum Nord", "Praxis Sued"]),
        "mileage_before": random.randint(10000, 80000),
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{API}/api/resource-bookings", json=body, timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("create_vehicle", r.status_code, lat,
                        None if r.status_code in (200, 409) else r.text[:120])
        if r.status_code == 200:
            await stats.add_booking(r.json()["booking_id"])
    except Exception as e:
        await stats.add("create_vehicle", 0, (time.perf_counter() - t0) * 1000, str(e))


async def op_create_with_catering(client, resources, stats):
    rid = random.choice(resources["catering_rooms"])
    items = resources.get("catering_items", [])
    if not items:
        return
    start = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30), hours=random.randint(8, 16))
    lines = [{"item_id": random.choice(items), "quantity": random.randint(1, 10)}
             for _ in range(random.randint(1, 3))]
    body = {
        "resource_id": rid,
        "title": "Meeting mit Catering",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=2)).isoformat(),
        "catering": {
            "items": lines,
            "delivery_at": start.isoformat(),
            "delivery_target": "Konferenzraum",
            "cost_center": "KS-100",
        },
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{API}/api/resource-bookings", json=body, timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("create_catering", r.status_code, lat,
                        None if r.status_code in (200, 409) else r.text[:120])
        if r.status_code == 200:
            await stats.add_booking(r.json()["booking_id"])
    except Exception as e:
        await stats.add("create_catering", 0, (time.perf_counter() - t0) * 1000, str(e))


async def op_edit(client, _resources, stats):
    bid = await stats.pop_booking()
    if not bid:
        await stats.add("edit", 0, 0, "no_booking_available")
        return
    # Verschiebe Buchung um zufaellige Minuten in die Zukunft
    new_start = datetime.now(timezone.utc) + timedelta(days=random.randint(31, 60), hours=random.randint(7, 17))
    body = {
        "title": f"Editiert {new_start.strftime('%d.%m')}",
        "start_at": new_start.isoformat(),
        "end_at": (new_start + timedelta(hours=1)).isoformat(),
    }
    t0 = time.perf_counter()
    try:
        r = await client.put(f"{API}/api/resource-bookings/{bid}", json=body, timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("edit", r.status_code, lat,
                        None if r.status_code in (200, 409) else r.text[:120])
        if r.status_code == 200:
            # zurueck in den Pool
            await stats.add_booking(bid)
    except Exception as e:
        await stats.add("edit", 0, (time.perf_counter() - t0) * 1000, str(e))


async def op_cancel(client, _resources, stats):
    bid = await stats.pop_booking()
    if not bid:
        await stats.add("cancel", 0, 0, "no_booking_available")
        return
    t0 = time.perf_counter()
    try:
        r = await client.delete(f"{API}/api/resource-bookings/{bid}", timeout=15)
        lat = (time.perf_counter() - t0) * 1000
        await stats.add("cancel", r.status_code, lat,
                        None if r.status_code in (200, 400, 404) else r.text[:120])
    except Exception as e:
        await stats.add("cancel", 0, (time.perf_counter() - t0) * 1000, str(e))


OP_WEIGHTS = [
    (op_create_room, 25),
    (op_create_desk, 10),
    (op_create_vehicle, 10),
    (op_create_split, 10),
    (op_create_combo, 5),
    (op_create_with_catering, 10),
    (op_edit, 15),
    (op_cancel, 15),
]


async def worker(worker_id: int, client: httpx.AsyncClient, resources, stats):
    """Simuliert einen Anwender mit OPS_PER_WORKER Mixed-Operationen."""
    ops_list, weights = zip(*OP_WEIGHTS)
    for _ in range(OPS_PER_WORKER):
        op = random.choices(ops_list, weights=weights, k=1)[0]
        try:
            await op(client, resources, stats)
        except Exception as e:
            await stats.add(op.__name__, 0, 0, f"unhandled:{e}")
        await asyncio.sleep(random.uniform(0.01, 0.05))  # leichtes Jitter


# ---------------- Hauptlauf -------------------------------------------------
async def main():
    print(f"==> Stress-Test gegen {API}  ({CONCURRENCY} User x {OPS_PER_WORKER} Ops = {TOTAL_OPS} Operationen)")
    # Login (admin token via cookie)
    async with httpx.AsyncClient(timeout=30) as login_client:
        r = await login_client.post(f"{API}/api/auth/login", json=ADMIN)
        assert r.status_code == 200, r.text
        cookies = login_client.cookies

    # 50 unabhaengige Clients, alle mit dem gleichen Admin-Cookie
    clients = [httpx.AsyncClient(cookies=cookies, timeout=30) for _ in range(CONCURRENCY + 1)]
    setup_client = clients[0]

    print("==> Lege Test-Ressourcen an…")
    resources = await setup_resources(setup_client)
    print(f"    Rooms={len(resources['rooms'])} Split={len(resources['split_rooms'])} "
          f"Approval={len(resources['approval_rooms'])} Catering={len(resources['catering_rooms'])} "
          f"Desks={len(resources['desks'])} Vehicles={len(resources['vehicles'])} "
          f"Items={len(resources.get('catering_items', []))}")

    stats = Stats()
    print(f"==> Starte {CONCURRENCY} parallele Worker…")
    t_start = time.perf_counter()
    await asyncio.gather(*(worker(i, clients[i+1], resources, stats) for i in range(CONCURRENCY)))
    elapsed = time.perf_counter() - t_start
    print(f"==> Fertig in {elapsed:.2f}s")

    # Cleanup
    print("==> Cleanup…")
    await teardown(setup_client, resources)
    for c in clients:
        await c.aclose()

    # Auswertung
    by_op: dict = {}
    for op, status, lat, err in stats.results:
        by_op.setdefault(op, []).append((status, lat, err))

    rows = []
    for op, lst in sorted(by_op.items()):
        oks = [lat for s, lat, _ in lst if 200 <= s < 300]
        confl = [lat for s, lat, _ in lst if s == 409]
        errs = [(s, e) for s, _, e in lst if (s < 200 or s >= 300) and s != 409]
        lats = [lat for _, lat, _ in lst if lat > 0]
        rows.append({
            "op": op,
            "total": len(lst),
            "ok": len(oks),
            "conflict_409": len(confl),
            "error": len(errs),
            "error_examples": [f"{s}:{e[:80]}" for s, e in errs[:3]],
            "lat_p50_ms": round(statistics.median(lats), 1) if lats else 0,
            "lat_p95_ms": round(_pct(lats, 95), 1) if lats else 0,
            "lat_p99_ms": round(_pct(lats, 99), 1) if lats else 0,
            "lat_max_ms": round(max(lats), 1) if lats else 0,
        })

    total = len(stats.results)
    total_ok = sum(r["ok"] for r in rows)
    total_409 = sum(r["conflict_409"] for r in rows)
    total_err = sum(r["error"] for r in rows)

    report = {
        "api": API,
        "concurrency": CONCURRENCY,
        "ops_per_worker": OPS_PER_WORKER,
        "total_ops": total,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_ops_per_sec": round(total / elapsed, 1) if elapsed else 0,
        "summary": {
            "ok_pct": round(total_ok / total * 100, 1) if total else 0,
            "conflict_pct": round(total_409 / total * 100, 1) if total else 0,
            "error_pct": round(total_err / total * 100, 1) if total else 0,
        },
        "by_op": rows,
    }
    out = "/tmp/booking_stress_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"==> Report: {out}")
    print(json.dumps(report["summary"], indent=2))
    print("\nPer-Op breakdown:")
    for r in rows:
        print(f"  {r['op']:22s} total={r['total']:3d}  ok={r['ok']:3d}  409={r['conflict_409']:3d}  "
              f"err={r['error']:3d}  p50={r['lat_p50_ms']:6.1f}ms  p95={r['lat_p95_ms']:6.1f}ms")
        if r["error_examples"]:
            for ex in r["error_examples"]:
                print(f"     ! {ex}")
    return report


def _pct(values, p):
    if not values:
        return 0
    values = sorted(values)
    k = (len(values) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(values) - 1)
    return values[f] + (values[c] - values[f]) * (k - f)


if __name__ == "__main__":
    asyncio.run(main())
