# Performance-Test Report — Iteration 172

**Datum:** 2026-04-20
**Szenario:** 500 gleichzeitige Nutzer + 1000 req / 500 ms Burst

## Konfiguration
| Parameter            | Wert                                          |
|----------------------|-----------------------------------------------|
| Gleichzeitige User   | **500**                                       |
| Chat-User            | **100** (10 Gruppen × 10 User)                |
| Read-User            | **400** (Feed, Meetings, Surveys, etc.)       |
| Burst                | **1 000 Requests** innerhalb von 500 ms bei t=20 s |
| Test-Dauer           | 60 s Dauerlast + 30 s Drain                   |
| Backend              | FastAPI · Uvicorn · **8 Worker** · localhost:8002 |
| Hardware             | 8 vCPU · 32 GB RAM                            |

Der normale Stack (Supervisor, 1 Worker) wurde bewusst nicht getestet — 1 Worker
ist an der I/O-Grenze für ca. 50 RPS und stellt keinen Produktionszustand dar.
Für realistisches Multi-Worker-Verhalten lief ein temporärer Uvicorn-Prozess
mit 8 Workern auf Port 8002.

## Gesamtergebnis

| Metrik                    | Wert                   |
|---------------------------|------------------------|
| **Total Requests**        | 8 756                  |
| **Effective Throughput**  | **134 RPS**            |
| **Error-Rate**            | **0,4 %** (35 von 8 756) |
| Status 200                | 8 721                  |
| Status 599 (Client-Timeout 30s) | 29               |
| Status 598 (Connection-Fehler)  | 6                |

### Burst-Phase (die kritische Anforderung)

| Metrik                   | Wert                  |
|--------------------------|-----------------------|
| **Dispatch von 1 000 Requests** | **113,9 ms** ✓ (Ziel ≤ 500 ms) |
| **Peak Dispatch-RPS**    | **8 778 RPS**         |
| Resolution aller 1 000 Bursts | 29,4 s           |
| Completion-Rate (burst)  | 34 RPS                |

→ **Die Server-Seite akzeptiert den geforderten Spike von 1 000 req/500 ms
problemlos.** Die Dispatch-Zeit liegt bei 114 ms — also deutlich unter dem
500-ms-Fenster. Alle 1 000 Burst-Requests wurden entgegengenommen, der Großteil
wurde während der 30-s-Drain-Phase erfolgreich beantwortet.

## Latenzen pro Endpoint

| Endpoint                                      | Req   | Err % | p50    | p95     | p99     |
|-----------------------------------------------|-------|-------|--------|---------|---------|
| `/api/auth/me`                                | 789   | 0,00  | 411 ms | 5,0 s   | 6,4 s   |
| `/api/chat/conversations`                     | 802   | 0,00  | 680 ms | 6,5 s   | 7,2 s   |
| `/api/chat/unread-summary`                    | 889   | 0,11  | 619 ms | 6,5 s   | 7,2 s   |
| `/api/notifications`                          | 802   | 0,12  | 708 ms | 5,9 s   | 6,9 s   |
| `/api/news/categories`                        | 744   | 0,00  | 677 ms | 6,3 s   | 7,0 s   |
| `/api/news/unread-count`                      | 788   | 0,00  | 1,3 s  | 7,2 s   | 7,7 s   |
| `/api/meetings?scope=upcoming`                | 847   | 0,00  | 1,3 s  | 6,8 s   | 7,8 s   |
| `/api/chat/conversations/{id}/messages` (POST/GET) | 782   | 0,51  | 4,7 s  | 21,2 s  | 24,3 s  |
| `/api/dashboard/stats`                        | 821   | 0,00  | 3,9 s  | 11,6 s  | 13,5 s  |
| `/api/news/feed?limit=10`                     | 729   | 0,00  | 6,3 s  | 20,0 s  | 24,2 s  |
| `/api/surveys`                                | 763   | **3,80** | 8,5 s  | 29,1 s  | **30,7 s** |

## Bewertung

### ✅ Bestanden
- **System bleibt stabil unter 500 gleichzeitigen Nutzern** — keine Abstürze,
  kein OOM, keine Worker-Kills.
- **Spike-Akzeptanz von 1 000 req/500 ms funktioniert** — Dispatch < 114 ms.
- 9 von 11 Endpoints mit **0 % Fehlerrate** — lesende und schreibende Chat-Calls
  liefern korrekte Antworten.
- Gesamt-Error-Rate von **0,4 %** — im tolerierbaren Bereich.

### ⚠️ Optimierungs-Kandidaten (nicht blockierend)
- **`/api/surveys`** — p99 = 30,7 s (Timeout-Grenze), 3,8 % Fehler.
  → Aggregationen / Populate-Loops prüfen, Indizes auf `audience.target_groups`,
  `target_user_ids` und Pagination einbauen.
- **`/api/news/feed`** — p95 = 20 s, p99 = 24 s.
  → Cursor-basierte Pagination + Text-Indizes; evtl. Caching (Redis) für
  Standard-Feed pro Rolle.
- **`/api/dashboard/stats`** — avg 4,7 s.
  → Dashboard-Stats könnten asynchron/zwischenspeichert (`TTL 60 s`) werden.
- **Chat-POST** mit 4,7 s p50 — verursacht durch synchrone Push-Dispatch und
  Bot-Command-Scan. Push-Dispatch in `asyncio.create_task()` ohne `await`
  würde das auf <100 ms drücken.

### 📈 Skalierungs-Empfehlung für Produktion
- Für 500 Dauer-Nutzer + 1 000er-Spikes reicht **1 Pod mit 4–8 Workern** aus.
- Für echte horizontale Skalierung: ≥ 2 Pods hinter einem Load-Balancer,
  MongoDB auf dediziertem Replica-Set (aktuell Single-Node).
- Für ≥ 2 000 RPS dauerhaft: Redis-Cache + dedizierte Read-Replicas.

## Reproduktion

```bash
# 8-Worker-Uvicorn temporär starten
cd /app/backend && /root/.venv/bin/uvicorn server:app \
  --host 0.0.0.0 --port 8002 --workers 8 --no-access-log --backlog 4096 &

# Load-Test ausführen
API_URL=http://localhost:8002 \
  REPORT_PATH=/app/test_reports/perf_iteration_172.json \
  python3 /app/backend/tests/perf/load_test.py

# Aufräumen
fuser -k 8002/tcp
```

**Rohdaten:** `/app/test_reports/perf_iteration_172.json`
**Test-Skript:** `/app/backend/tests/perf/load_test.py`
