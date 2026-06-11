# MeetFlow — Funktionen für IT & Administration

**Technische Übersicht für Betrieb, Integration und Skalierung.**

---

## Architektur

**Backend**
- FastAPI (Python 3.11), MongoDB, WebSockets
- Single-Pod-Deployment mit Supervisor (uvicorn auf Port 8001)
- Hot-Reload aktiv für Code-Änderungen
- Refresh-Token-Auto-Rotation, JWT in HttpOnly-Cookies

**Frontend**
- React (Create-React-App) + TanStack Query + Tailwind + Shadcn UI
- Service Worker mit Offline-Shell + API-Cache (stale-while-revalidate)
- PWA-Manifest mit Workflow-Branding
- Build wird automatisch beim Deploy generiert

**Datenbank**
- MongoDB einziger Storage
- Schema-frei, Collections: `users`, `groups`, `meetings`, `resource_bookings`, `catering_requests`, `invoices`, `notifications`, `messages`, `audit_log` usw.
- Indizes auf `user_id`, `email`, `booking_id`, `created_at`

---

## Authentifizierung & SSO

**Verfügbare Login-Methoden**
- E-Mail + Passwort (lokal, bcrypt)
- Personalnummer + Passwort (für E-Mail-lose Konten)
- Azure AD / Microsoft 365 SSO (OIDC)
- Google OAuth (Emergent-Managed)

**Passwort-Policy (Org-Setting)**
- 4-aus-4-Regel, mindestens 8 Zeichen
- 6-Monats-Rotation (`password_rotation_months` in `org_settings`)
- 3-Passwort-Historie (gespeichert als bcrypt-Array)
- Force-Change bei Admin-Reset (token_version-Bump beendet alle Sessions)

**Session-Management**
- JWT-Cookie (HttpOnly + Secure + SameSite)
- Refresh-Endpoint mit Auto-Renewal
- Server-side Session-Invalidation via token_version

---

## Benutzer-, Rollen- & Rechtesystem

**Rollen**: Admin, Moderator, Mitarbeiter, Gast
**Capabilities**: 74 atomare Berechtigungen (siehe `/app/backend/services/permissions.py`)
**Gruppen**: 4 System-Modul-Gruppen (auto-managed) + beliebig viele Custom-Gruppen
**Effective-Caps**: Rollen-Defaults ∪ Group-Caps ∪ User-Cap-Grants − Cap-Denies

**Granulare Cap-Beispiele**
- `analytics.view_catering_history` — nur Catering-Auswertung
- `users.view_drivers_license` — nur Führerschein-Übersicht
- `news.moderate` — nur News-Moderation

**Endpoints (Auswahl)**
- `GET /api/user/permissions` — effektive Caps des aktuellen Users
- `GET /api/admin/groups` — alle Gruppen mit Capabilities
- `PUT /api/admin/groups/{id}` — Gruppen-Caps anpassen
- `POST /api/admin/users/{id}/reset-password` — Temp-Passwort + Force-Change

---

## Integrationen

- **OpenAI GPT-5.2** (Meeting-Zusammenfassungen, Action-Items) — Emergent LLM Key
- **OpenAI Whisper** (Transkription) — Emergent LLM Key
- **Gemini Nano Banana** (Bild-Gen für Branding) — Emergent LLM Key
- **Stripe** (Rechnungs-Bezahlung) — Test-Key konfiguriert
- **Azure AD / M365 SSO** (OIDC) — Tenant + Client-ID nötig
- **Tenor** (GIF-API für Chat)
- **Outlook/M365 Kalender** (geplant — bidirektionale Sync)

---

## Deployment

**Voraussetzungen** (siehe `/app/DEPLOY.md`)
- Linux-VM oder Container mit Python 3.11, Node 20, MongoDB
- Reverse-Proxy (NGINX/Traefik) mit HTTPS, WebSocket-Support
- `/api/*` → Backend (Port 8001), Rest → Frontend (Port 3000)
- Persistent Disk für Recordings + Anhänge

**Skalierung**
- Backend ist stateless → horizontale Skalierung möglich
- WebSocket-Broker für Multi-Worker-Setup integriert
- MongoDB-Replica-Set empfohlen für Produktion
- Service Worker: Cache-Versionierung über `API_CACHE_VERSION` (aktuell v4)

**Environment-Variablen**
- `MONGO_URL`, `DB_NAME` (Backend)
- `REACT_APP_BACKEND_URL` (Frontend, externe URL)
- `JWT_SECRET`, `JWT_REFRESH_SECRET`
- `STRIPE_API_KEY` (Test-/Prod-Key)
- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` (SSO)

---

## Monitoring & Wartung

**Admin-Panel → Verwaltung → Monitoring**
- Health-Check (Backend-Status, Mongo-Connection, Disc-Usage)
- Quick-Scans (Orphaned Records, DB-Integrity)
- Audit-Log (browsable, filterbar, CSV-Export)
- System-Audit (Iter-Tracking + Compliance)

**Logs**
- Backend: `/var/log/supervisor/backend.*.log`
- Strukturierte JSON-Logs (logger=server, request_id pro Request)

**Demo-Daten**
- `POST /api/admin/demo-data/seed` — füllt Demo-User + Beispieldaten
- `POST /api/admin/demo-data/wipe` — kaskadierende Löschung inkl. Demo-User

---

## Bekannte technische Eigenheiten

- **Service Worker** cached nur `/api/tasks`, `/api/news/posts`, `/api/dashboard`, `/api/notifications` (read-only). Chat + Auth bewusst ausgeschlossen, da Realtime.
- **MongoDB-Collections**: `resource_bookings` (echte Buchungen) ≠ `bookings` (legacy Meeting-Storage).
- **Catering-Aggregate-Invoices** speichern `aggregated_request_ids` für Auswertungs-Backlink (ab Iter 400).
- **System-Modul-Gruppen** werden beim Boot nur metadata-refresht; Capabilities bleiben editierbar persistent.

---

*Komplette Code-Referenz: `/app/backend/routes/` (API), `/app/frontend/src/` (UI), `/app/memory/PRD.md` (Iter-Historie).*
