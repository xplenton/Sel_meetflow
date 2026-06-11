# Performance-Test 200 Nutzer — Iter 184

**Datum:** 2026-04-21
**Ziel:** FastAPI-Backend gegen 200 simultane User belasten (Preview-Env-realistisch).
**Backend-Setup:** Supervisor-managed uvicorn, **1 Worker** (genau wie im Preview),
MongoDB single-node, Redis + ws_broker aktiv.

---

## Szenario A — 200 User STEADY-STATE (45 s, kein Burst)

| Metrik                  | Wert                  |
|-------------------------|-----------------------|
| Total Requests          | **9 346**             |
| Effektive Throughput    | **199,0 RPS** 🟢       |
| **Error-Rate**          | **0,00 %** 🟢          |
| Chat-Users              | 40 (4 Gruppen × 10)   |
| Read-Users              | 160                   |
| Dauer                   | 45 s                  |

### Latenzen

| Endpoint                                         | Req    | p50    | p95    | p99    | avg    |
|--------------------------------------------------|-------:|-------:|-------:|-------:|-------:|
| `/api/chat/conversations/{id}/messages` (POST+GET) | 1 653 | 108 ms | 447 ms | **904 ms** | 153 ms |
| `/api/dashboard/stats`                           |    736 |  45 ms | 329 ms | 868 ms |  90 ms |
| `/api/news/feed?limit=10`                        |    733 |  89 ms | 330 ms | 687 ms | 124 ms |
| `/api/surveys`                                   |    781 |  70 ms | 254 ms | 623 ms |  97 ms |
| `/api/meetings?scope=upcoming`                   |    754 |  61 ms | 217 ms | 576 ms |  88 ms |
| `/api/news/unread-count`                         |    712 |  62 ms | 204 ms | 572 ms |  84 ms |
| `/api/notifications`                             |    748 |  45 ms | 168 ms | 486 ms |  64 ms |
| `/api/chat/conversations`                        |    762 |  46 ms | 164 ms | 485 ms |  64 ms |
| `/api/news/categories`                           |    710 |  46 ms | 169 ms | 484 ms |  64 ms |
| `/api/chat/unread-summary`                       |  1 019 |  47 ms | 174 ms | 463 ms |  64 ms |
| `/api/auth/me`                                   |    738 |  37 ms | 150 ms | 330 ms |  52 ms |

**Alle Endpoints:**
- ✅ **0 Fehler**
- ✅ **p99 < 1 s** bei allen Endpoints
- ✅ **p50 < 110 ms** bei allen Endpoints
- ✅ System komplett stabil

---

## Szenario B — 200 User + Burst 1 000 req/500 ms (60 s)

| Metrik               | Wert                  |
|----------------------|-----------------------|
| Total Requests       | 6 506                 |
| Effektive Throughput | 104,7 RPS             |
| Burst Dispatch       | **4,3 ms** (Ziel ≤ 500 ms) ✓ |
| Error-Rate           | 16,29 % (1 041 Client-Timeouts während Burst) |

**Was passiert im Burst:**
- Alle 1 000 Burst-Requests werden in 4 ms versendet
- Der Single-Worker-Backend verarbeitet sie seriell → Queue-Staustau
- Steady-State-Requests während der Burst-Phase laufen in den 30 s-Client-Timeout

**Status 500:** nur 19 echte Server-Errors (meist MongoDB-Connection-Timeout unter Spitze)
**Status 599:** 1 041 Client-Timeouts (nicht das Backend, sondern „aiohttp: timeout").

Das ist **erwartetes Verhalten** für einen Single-Worker unter extremem Spike — in
Produktion würde man den Burst über Multi-Worker-Uvicorn + Redis-Broker + horizontale
Skalierung abfangen (validiert in iter 173-176 mit 0,05 % Fehlerrate bei 8 Workern).

---

## Fazit

### ✅ Für Klinik-Alltag völlig ausreichend
- **200 simultane User** → 199 RPS durchgehend stabil
- **Alle Endpoints p99 < 1 s**
- **Keine Fehler** unter realistischer Last
- **Phase-A-Optimierungen aus iter 173** zahlen sich sichtbar aus:
  - Surveys p99 = 623 ms (war vor iter 173 bei ~30 s 💥)
  - News-Feed p99 = 687 ms (war > 20 s)
  - Dashboard-Stats p99 = 868 ms (TTL-Cache greift bei wiederholten Abfragen)

### ⚠️ Für echte Burst-Lastspitzen (>500 req/500ms) Multi-Worker nötig
- Siehe `/app/docs/PRODUCTION_DEPLOYMENT.md` für nginx + 8-Worker-Uvicorn + Redis
- Validiert in iter 176 final: **500 User + 1 000-Burst → 0,05 % Fehler**

### Reproduktion

```bash
# Steady-State 200 User (45 s)
CONCURRENT_USERS=200 CHAT_USERS=40 BURST_SPIKE_SIZE=0 BURST_DURATION_SEC=45 \
  API_URL=http://localhost:8001 \
  python3 /app/backend/tests/perf/load_test.py

# Inklusive 1 000 req/500 ms Burst
CONCURRENT_USERS=200 CHAT_USERS=40 BURST_SPIKE_SIZE=1000 BURST_DURATION_SEC=60 \
  API_URL=http://localhost:8001 \
  python3 /app/backend/tests/perf/load_test.py
```

**Artefakte:**
- `/app/test_reports/perf_200u_noburst.json`
- `/app/test_reports/perf_200u.json`
- `/app/backend/tests/perf/load_test.py`
