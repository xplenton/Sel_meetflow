# MeetFlow — Architektur-Übersicht

> Stand: Iter 348 · Refactor-Reihe iter 345–348 hat die Routes-Pakete von monolithischen Dateien in fokussierte Module mit klaren Service-Boundaries umgebaut.

Diese Seite ist die **Onboarding-Karte** für neue Entwickler:innen. Sie listet die Module-Grenzen, die wichtigsten Service-Layer und wo welche Verantwortung lebt.

---

## Tech-Stack

| Layer       | Technologie |
|-------------|-------------|
| Frontend    | React 19 + Tailwind + Shadcn/UI + Lucide-Icons |
| Backend     | FastAPI (Python 3.11) + Motor (async Mongo) |
| Datenbank   | MongoDB Replica-Set (`rs0`) — Read-Routing über `read_db` |
| Auth        | JWT custom + optional Azure AD (Authlib) + Emergent Google |
| Realtime    | WebSockets (per-meeting + Tasks broadcast) + Redis pub/sub (`ws_broker`) |
| Background  | `arq-worker` (Redis-Queue) für Reminders, Mailings, Backups |
| AI          | GPT-5.2 via Emergent LLM Key (Summaries, Findings) |
| Performance | uvloop + httptools, 8 uvicorn workers (Iter 345) |

---

## Frontend (`/app/frontend/src/`)

```
src/
├── pages/                    # Top-level routes (Dashboard, Tasks, Resources, …)
├── components/               # Re-usable UI building blocks
│   ├── admin/                # Admin-only UI (User CSV import, EditUserDialog, …)
│   ├── meetings/             # Live-meeting controls, breakouts, AV
│   ├── resources/            # Resource bookings (BookingDialog, SplittableRoom, …)
│   └── ui/                   # Shadcn primitives (button, dialog, sonner …)
├── contexts/                 # AuthContext, WebSocketContext
├── hooks/                    # useOptimisticTasks, useResourceBookings, …
└── lib/                      # sanitize.js (DOMPurify), i18n helpers, fetch wrapper
```

**Konventionen:**
- Default-export für Pages, Named-export für Components.
- `data-testid` an *jedem* interaktiven Element (Pflicht für das Test-Subagent).
- Tailwind statt CSS-Modules; Animationen via `motion/react`.

---

## Backend (`/app/backend/`)

### Routes-Layer (HTTP-Wiring)

```
routes/
├── auth.py                   # Login, register, password reset, /me, OAuth callback
├── admin/                    # /api/admin/* — RBAC, users, groups, presets
│   └── users.py              # CSV import + export, extended Stammdaten
├── chat/                     # /api/chat/* — DMs, conversations, websocket
├── meetings/                 # /api/meetings/* — live, lifecycle, calendar/events
│   └── live.py               # /calendar/events (30s TTL cache), /dashboard/stats
├── news/                     # /api/news/* — feed, posts, workflow, push, signage
├── resources/                # /api/resources/* + /api/resource-bookings/* — see below
└── tasks.py, surveys.py, …   # The remaining top-level routers
```

### Routes/Resources — fokussierte Sub-Pakete (Iter 234 → 347)

```
routes/resources/
├── __init__.py               # Kombiniert alle Sub-Router unter einem APIRouter
├── _common.py                # Pydantic-Models, Konstanten, CSV/PDF/XLSX-Builder,
│                             # Audit, Upload-Validation, Shims für Service-Layer
├── bookings/                 # ← Iter 347 — aufgesplittet aus 1117-LoC-Monolith
│   ├── __init__.py           #   Kombiniert die 4 Sub-Router
│   ├── crud.py               #   list / get / create / update / cancel + conflicts
│   ├── approval.py           #   approve, pending-count, check-in/out, no-show
│   ├── series.py             #   Recurring + Combo (multi sub-room) bookings
│   └── reporting.py          #   Damage reports, suggest-slots
├── catering.py               # /api/catering-requests/*, lifecycle status changes
├── office_days.py            # /api/office-days/* — wöchentliche Office-Day-Buchung
├── invoices.py               # /api/resource-invoices/* — Interne Verrechnung
├── invoice_tracking.py       # /api/invoice-tracking/* — Status, Reminder
├── invoices_config.py        # /api/invoice-config/* — Setup-UI
└── admin/                    # /api/resources-admin/* — Demo seed, master-data, analytics
```

### Services-Layer (Business-Logic, ~70 Module)

Services kapseln **Verhalten ohne HTTP-Konzepte**. Routes rufen Services auf, nie umgekehrt. Wichtigste Module:

| Service-Modul                              | Verantwortung |
|--------------------------------------------|---------------|
| `services/booking_conflicts.py`            | Konflikt-Check, Race-Winner, Sub-Room-Whitelist (Iter 346) |
| `services/booking_notifications.py`        | `notify_approvers`, `notify_catering_team`, `notify_catering_status` (Iter 347) |
| `services/catering_request_factory.py`     | Catering-Pipeline: Request + Auto-Task + Lead-Time-Breach + Short-Notice-Mail (Iter 348) |
| `services/pdf_invoices.py`                 | `build_invoice_pdf` — A4-PDF mit reportlab, gebrandetes Layout (Iter 349) |
| `services/csv_export.py`                   | `csv_line` (RFC-4180), `build_xlsx` (gebrandeter Header) (Iter 349) |
| `services/booking_aggregator.py`           | `compute_booking_invoice_aggregate` — geteilte Logik für `/aggregate` (JSON) + `/aggregate.pdf` (Iter 350) |
| `services/resource_hierarchy.py`           | `expand_blocking_ids`, `child_to_parent_map` — zentrale Sub-Room/Parent-Expansion (Iter 352) |
| `services/permissions.py`                  | RBAC: `has_cap`, `require_cap`, Capability-Presets |
| `services/news_feed.py`                    | Feed-Query + Targeting + Pagination + 15 s TTL-Cache (Iter 345) |
| `services/news_crud.py`, `news_workflow.py`| News CRUD, Approval, Sentiment |
| `services/meetings_dashboard.py`           | Calendar-Events-Aggregation, Dashboard-Stats |
| `services/meetings_av.py`, `meetings_lifecycle.py` | Recording, Transcripts, Reminders |
| `services/email.py` + `email_templates.py` | SMTP-Versand mit retry; HTML-Templates |
| `services/ws_manager.py`, `ws_broker.py`   | WebSocket-Fanout (in-process + Redis pub/sub) |
| `services/background_queue.py`             | arq-job-Wrapper für längere Tasks |

### Daten-Layer

- **`database.py`** — Erzeugt `db` (Primary) und `read_db` (Secondary-preferred). Indizes werden in `server.py @on_startup` deklariert (Iter 345 hat hier 4 Compound-Indexe ergänzt).
- **Collections:** `users`, `groups`, `resources`, `resource_bookings`, `catering_requests`, `tasks`, `meetings`, `meeting_participants`, `news_posts`, `news_reads`, `news_reactions`, `notifications`, `invoice_master_data`, `blackout_periods`, `damage_reports`, `chat_*`, `audit_logs` und ~20 weitere.

### Background-Worker

Separater Supervisor-Prozess `arq-worker`. Worker-Funktionen leben in `services/jobs/*` und werden aus `services/background_queue.py` enqueued. Verwendung typischerweise für: E-Mail-Newsletter, GDPR-Export, Office-Day-Massengenerierung, Reminder-Loops.

---

## Cross-Cutting Concerns

### Caching (Iter 172, 335, 345)

In-Memory TTL-Caches pro Worker (kein Redis-Roundtrip nötig, da Daten klein):

| Endpoint                     | TTL  | Scope            |
|------------------------------|------|------------------|
| `/api/dashboard/stats`       | 60 s | per User         |
| `/api/calendar/events`       | 30 s | per User         |
| `/api/cost-centers`          | 30 s | global           |
| `/api/accounts`              | 30 s | global           |
| `/api/news/feed`             | 15 s | per (User, Filter)|

Invalidierung erfolgt aus den jeweiligen Write-Pfaden (`_invalidate_master_cache`, `invalidate_news_feed_cache`, RSVP-Endpoint).

### Race-Condition-Safety bei Buchungen (Iter 248, 252)

Pattern: `check_conflicts` ist *nicht* atomar mit `insert_one`. Lösung in `services/booking_conflicts.verify_booking_winner`:
1. Insert.
2. 50 ms Settle-Delay (Read-Visibility im Connection-Pool).
3. Re-Query nach Competitors.
4. Deterministischer Winner = kleinste `booking_id` (UUID-Sort).
5. Verlierer löscht sich selbst und gibt 409 zurück.

### Audit & Compliance

- `services/permission_audit.log_caps_change` — strukturierter Audit-Log in `audit_logs` für alle RBAC-Änderungen.
- `_audit_booking` in `_common.py` — Buchungs-Lifecycle (created, updated, checked_in, …).
- Fire-and-forget über `asyncio.create_task`, damit Audit nie den Response-Pfad blockiert.

### Authentication

- **JWT-basiert**: `auth.py` issued + `dependencies.get_current_user` validiert.
- **Self-Registration** mit Domain-Allowlist + 24 h Auto-Lock (Iter 290).
- **SSO**: Azure AD via Authlib (`sso_azure.py`), optional Emergent Google Auth.
- Brute-Force-Schutz über `login_attempts`-Collection mit indizierter Rate-Limitierung.

### Performance

- `start.sh` startet uvicorn mit **8 workers** + `uvloop` + `httptools` + `limit-concurrency=1000` + `backlog=2048`.
- Indexe für die heißesten Hotspots stehen in `server.py @on_startup` (siehe Iter-345-Block).
- Load-Test-Harness: `tests/load/loadtest.py` mit Smoke / Load / Stress / Soak-Modi.
- Letzter Bericht: `/app/test_reports/perf_iter344/REPORT.md`.

---

## Module-Boundaries — Goldene Regeln

1. **Routes dürfen Services importieren**, niemals umgekehrt.
2. **Routes-Pakete dürfen `_common.py` ihres eigenen Pakets importieren** (z. B. `routes/resources/bookings/crud.py` → `routes/resources/_common`), aber nicht andere Routes-Pakete (kein `routes/news/...` aus `routes/resources/...`).
3. **Services dürfen andere Services importieren**, aber zirkuläre Imports werden mit lazy-Imports innerhalb von Funktionen aufgelöst.
4. **Models leben in `_common.py`** des jeweiligen Routes-Pakets oder in `models.py` für globale Pydantic-Klassen.
5. **DB-Reads gehen über `read_db`** wo die Latenz wichtig ist und stale-bis-30s OK ist (`news_feed`, Calendar). Writes immer über `db`.
6. **Niemals `_id` in der API-Response**: Immer mit `{"_id": 0}` projizieren oder Pydantic-Response-Model nutzen.
7. **Notifications fire-and-forget**: `asyncio.create_task(...)` damit eMail/Push nie den HTTP-Pfad blockieren.

---

## Refactor-Historie (für Kontext)

| Iter | Refactor |
|------|----------|
| 234  | Routes-Layer `resources.py` → `resources/` Paket (bookings, catering, invoices, admin) |
| 260  | Refactor-Regression-Suite gestützt + Tests dokumentiert |
| 345  | TTL-Caches + Compound-Indexe + Workers 4→8 (Performance) |
| 346  | `_check_conflicts` → `services/booking_conflicts.py` |
| 347  | (a) Notifications → `services/booking_notifications.py`<br>(b) `bookings.py` (1117 LoC) → 4-Datei-Subpaket `bookings/` |
| 348  | Catering-Pipeline (145 LoC) → `services/catering_request_factory.py` |
| 349  | PDF-Builder → `services/pdf_invoices.py`, CSV/XLSX → `services/csv_export.py` |
| 350  | Booking-Aggregator → `services/booking_aggregator.py`; Status-Filter ausgerichtet zwischen `availability_only` und Snapshot |
| 351  | Bugfix: Splitable-Parent zeigte „frei" trotz gebuchter Sub-Rooms — Children-Buchungen in Snapshot + List eingewoben |
| 352  | Resource-Hierarchy-Helper extrahiert (`expand_blocking_ids`, `child_to_parent_map`) — DRY zwischen Conflict-Check, Snapshot, List |

---

## Wichtige Dateien für neue Entwickler:innen

| Frage | Datei |
|-------|-------|
| Wie sehen unsere Models aus? | `routes/resources/_common.py` (Resource, ResourceBooking, CateringRequest, …) |
| Wo läuft die Conflict-Logic? | `services/booking_conflicts.py` |
| Wo werden Notifications gesendet? | `services/booking_notifications.py` |
| Wie sehen DB-Indexe aus? | `server.py @on_startup` (Zeile 90 ff.) |
| Wo definieren wir RBAC-Caps? | `services/permissions.py` + `services/permission_presets.py` |
| Wo läuft das Auth-Routing? | `routes/auth.py` + `dependencies.get_current_user` |
| Wo läuft die Load-Test-Suite? | `tests/load/loadtest.py` |
| Wie testen wir? | `tests/test_iter*.py` + `testing_agent_v3_fork` für E2E |

---

## Test-Credentials

Siehe `/app/memory/test_credentials.md`.
