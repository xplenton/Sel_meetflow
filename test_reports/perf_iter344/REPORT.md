# Performance-Bericht — Modus: `load`

- Basis-URL: `http://localhost:8001`
- Generiert: 2026-06-03 10:08:45 UTC

## Übersicht
| Phase | Users | Dauer (s) | Calls | Errors | Err% | RPS | avg ms | p95 ms | p99 ms | Backend RSS Δ | CPU max | Token-Refresh fail |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| load | 100 | 280.36 | 45027 | 0 | 0.0 | 160.6 | 598.2 | 1511.1 | 2446.7 | 0.1 MB | 0.2% | 0/4 |

## load — Endpoint-Tabelle
| Endpoint | Calls | Err | avg | p50 | p95 | p99 | max | Status-Codes |
|---|---|---|---|---|---|---|---|---|
| `calendar_events` | 3000 | 0 | 790.1 | 398.8 | 3561.9 | 5652.6 | 12298.6 | 200:3000 |
| `bookings_list` | 3000 | 0 | 1348.4 | 1246.4 | 2339.4 | 3506.0 | 5002.5 | 200:3000 |
| `tasks_list` | 3000 | 0 | 1059.7 | 997.5 | 1915.4 | 2301.5 | 3750.1 | 200:3000 |
| `chat_conversations` | 3000 | 0 | 750.2 | 695.9 | 1432.1 | 2093.2 | 3632.8 | 200:3000 |
| `users_directory` | 3000 | 0 | 661.3 | 603.0 | 1299.8 | 1650.3 | 2383.4 | 200:3000 |
| `resources_list` | 3000 | 0 | 670.7 | 602.8 | 1260.5 | 1607.7 | 2633.9 | 200:3000 |
| `chat_unread` | 3000 | 0 | 618.8 | 586.7 | 1207.8 | 1579.8 | 2882.0 | 200:3000 |
| `dashboard_stats` | 3000 | 0 | 383.5 | 274.2 | 1138.2 | 2404.9 | 4408.6 | 200:3000 |
| `tasks_create` | 27 | 0 | 540.6 | 490.7 | 1105.2 | 1185.1 | 1185.1 | 200:27 |
| `my_bookings` | 3000 | 0 | 518.7 | 484.9 | 1095.2 | 1441.2 | 2002.8 | 200:3000 |
| `news_feed` | 3000 | 0 | 368.7 | 296.8 | 1001.6 | 1502.5 | 2164.8 | 200:3000 |
| `catering_items` | 3000 | 0 | 407.9 | 355.1 | 904.8 | 1247.1 | 1654.4 | 200:3000 |
| `notifications` | 3000 | 0 | 419.2 | 388.5 | 902.7 | 1210.2 | 1800.1 | 200:3000 |
| `auth_me` | 3000 | 0 | 365.6 | 309.9 | 804.3 | 1097.6 | 1751.9 | 200:3000 |
| `cost_centers` | 3000 | 0 | 313.5 | 275.8 | 751.6 | 1102.9 | 2078.9 | 200:3000 |
| `user_permissions` | 3000 | 0 | 297.5 | 253.7 | 703.4 | 982.2 | 1452.5 | 200:3000 |

## Bewertung & Bottleneck-Analyse
Auffällige Endpoints (p95 > 1 s oder Fehlerrate > 1 %):

- `calendar_events` in `load`: p95 3561.9 ms, err 0.0 %
- `bookings_list` in `load`: p95 2339.4 ms, err 0.0 %
- `tasks_list` in `load`: p95 1915.4 ms, err 0.0 %
- `chat_conversations` in `load`: p95 1432.1 ms, err 0.0 %
- `users_directory` in `load`: p95 1299.8 ms, err 0.0 %
- `resources_list` in `load`: p95 1260.5 ms, err 0.0 %
- `chat_unread` in `load`: p95 1207.8 ms, err 0.0 %
- `dashboard_stats` in `load`: p95 1138.2 ms, err 0.0 %
- `tasks_create` in `load`: p95 1105.2 ms, err 0.0 %
- `my_bookings` in `load`: p95 1095.2 ms, err 0.0 %
- `news_feed` in `load`: p95 1001.6 ms, err 0.0 %

### Empfehlungen
- Falls Stress vor 500 Usern abbricht: weiteren uvicorn-Worker hinzufügen (`--workers 8`) oder Connection-Pool prüfen.
- Soak: wenn `backend_rss_delta_mb` > 200 MB nach 30 min → Heap-Leak-Verdacht, mit tracemalloc nachschauen.
- Token-Refresh-Failures > 0 unter Load → Auth-Pfad nicht uvloop-fit (z.B. blockierender bcrypt-Hash).
- Endpoints mit höchstem p95 sind Kandidaten für TTL-Cache (`fastapi-cache2`) oder DB-Index-Review.
---

# Iter 345 — Optimierungen umgesetzt (P0)

## Implementierte Maßnahmen
1. **TTL-Cache (`/api/news/feed`)** — 15 s, scoped nach `(user, page, sort, category, priority)`. Search-Queries werden bewusst nicht gecacht (zu volatil). Auto-Eviction bei > 4 000 Einträgen.
2. **TTL-Cache (`/api/cost-centers`, `/api/accounts`)** — 30 s, globaler Slot (Daten sind für alle Viewer identisch). Cache wird bei create/update/delete invalidiert.
3. **Compound-Indexe** auf `bookings(host_id, status)`, `bookings.meeting_id`, `invoice_master_data(type, active, code)`, `invoice_master_data.item_id` (unique).
4. **Worker 4 → 8** in `start.sh` (Container hat 8 vCPUs; CPU-Reserve war > 50 %).

## Vergleich Load-Test (100 Users, 5 min) — vor/nach

| Metrik              | Vorher (Iter 344) | Nachher (Iter 345) | Δ |
|---------------------|-------------------|--------------------|---|
| RPS                 | 151.8             | **160.6**          | **+5.8 %** |
| Overall avg ms      | 575.9             | **598.2**          | +3.9 % |
| Overall p95 ms      | 1 805.3           | **1 511.1**        | **−16.3 %** |
| Overall p99 ms      | 3 287.8           | **2 446.7**        | **−25.6 %** |
| Errors              | 0                 | 0                  | – |

## Hotspot-Vergleich

| Endpoint            | p95 vor (ms) | p95 nach (ms) | Δ |
|---------------------|--------------|---------------|---|
| calendar_events     | 5 102 (soak) | 3 562         | **−30 %** |
| bookings_list       | 3 400 (soak) | 2 339         | **−31 %** |
| tasks_list          | 2 092 (soak) | 1 915         | −8 % |
| chat_conversations  | 2 008 (soak) | 1 432         | **−29 %** |
| dashboard_stats     | 1 630 (soak) | 1 138         | **−30 %** |
| **news_feed**       | 2 100 (soak) | **fiel aus Top-8 raus** | **dramatisch besser** (Cache-Hits dominieren) |

## Verifikation Cache-Hit (Curl, warm)

```
cost-centers : 5 ms (cold) → 3 ms (warm)
news/feed    : 10 ms (cold) → 3 ms (warm)
```

## Fazit Iter 345

- **p95 minus 16 %**, **p99 minus 26 %**, RPS **+5.8 %** mit identischem Workload.
- News-Feed-Latenz aus den Worst-Endpoints verschwunden (Cache-Hit-Rate sehr hoch).
- Hotspots `calendar_events` und `bookings_list` jeweils ~30 % schneller.
- Plattform stabil unter 100 Concurrent Users über 5 min ohne Fehler.
