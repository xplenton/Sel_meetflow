# MeetFlow — Go-Live Checklist

> Stand: Iter 113 (April 2026). Checkbox-Liste für jeden Production-Deploy.
> **Vor dem Klick auf "Deploy" bitte alle P0-Punkte abhaken.**

---

## 🔴 P0 — Must-Do vor jedem Production-Deploy

### Environment Variablen (Backend)
Diese MÜSSEN in der Production-Umgebung gesetzt sein. Fehlt `JWT_SECRET`
weigert sich der Container zu starten (fail-fast in `dependencies.py`).

- [ ] `MONGO_URL` — MongoDB-Verbindungs-String (nicht der lokale)
- [ ] `DB_NAME` — eigener Production-DB-Name (z. B. `meetflow_prod`)
- [ ] `JWT_SECRET` — **≥ 32 Zeichen** random (z. B. `python -c "import secrets;print(secrets.token_hex(32))"`). Bei < 32 Zeichen crasht der Container sofort.
- [ ] `ADMIN_EMAIL` — Production-Admin-Mail (niemals `admin@meetflow.com`)
- [ ] `ADMIN_PASSWORD` — **niemals** `admin123` lassen (Startup-Log warnt laut)
- [ ] `CORS_ORIGINS` — Liste aller erlaubten Origins (z. B. `https://app.meinklinik.de`). `*` nur für Staging.
- [ ] `FRONTEND_URL` — absolute Production-URL (wird in Password-Reset-Mails verwendet)
- [ ] `RESEND_API_KEY` — Production-Resend-Schlüssel (oder `SENDGRID_API_KEY`)
- [ ] `SENDER_EMAIL` — verifizierte Absender-Adresse
- [ ] `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CLAIM_EMAIL` — Web-Push-Keys
- [ ] `EMERGENT_LLM_KEY` — Universal-Key (falls LLM-Features genutzt werden)

### Environment Variablen (Frontend)
- [ ] `REACT_APP_BACKEND_URL` — Production-Backend-URL
- [ ] `REACT_APP_VAPID_PUBLIC_KEY` — matched mit Backend

### Sicherheit
- [ ] CORS: `CORS_ORIGINS` explizit gesetzt (**nicht** `*` in Production)
- [ ] Admin-Account: Passwort aus Environment gelesen, **nicht Default**
- [ ] Rate-Limits aktiv: `/auth/login` 10/min, `/auth/register` 5/min, `/auth/forgot-password` 3/min, `/auth/reset-password` 5/min (slowapi)
- [ ] Security-Headers aktiv (siehe `server.py` `security_headers`-Middleware): CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy
- [ ] Emergent-Ingress liefert HSTS-Header (im Ingress konfiguriert, nicht in der App)

### Datenbank
- [ ] MongoDB-Indizes werden automatisch beim Startup angelegt (siehe `server.py::startup`). Nach dem ersten Deploy einmal `db.collection.getIndexes()` prüfen.
- [ ] Backup-Strategie konfiguriert: tägliches Snapshot + Retention (empfohlen: 30 Tage)
- [ ] TTL-Index auf `password_reset_tokens.expires_at` ist aktiv (abgelaufene Tokens werden automatisch gelöscht)

### Monitoring
- [ ] Health-Endpoint `/api/health` antwortet mit `{"status":"ok"}` (für Load-Balancer)
- [ ] JSON-Logs werden vom Log-Collector eingelesen (strukturiert, mit `request_id`)
- [ ] Error-Tracker (Sentry o. ä.) eingerichtet — **noch offen, siehe Backlog**
- [ ] WS Health Widget im Admin-Dashboard überwachen: Rejection-Rate < 1%

---

## 🟠 P1 — Stark empfohlen

### Performance
- [ ] Compound-Indexes aktiv (iter 113): `messages (conversation_id, sender_id, created_at)`, `focus_times (user_id, start_time, end_time)`, `meetings (status, scheduled_at, reminder_sent)`
- [ ] ETag / Cache-Control aktiv auf `/api/organization/branding`, `/api/news/categories`, `/api/news/tags`
- [ ] Frontend-Bundle: Main-Bundle 460 KB, lazy-loaded Chunks für PDF / Whiteboard / Mediapipe. Kein Quick-Win erforderlich.

### Funktionstests (manuell nach Deploy)
- [ ] Login als Admin funktioniert
- [ ] Registrierung neuer User funktioniert
- [ ] Password-Reset: Mail kommt an, Reset-Link funktioniert, kann sich danach einloggen
- [ ] Meeting erstellen → mit zweitem User beitreten → Video/Audio funktioniert
- [ ] Chat-Nachricht senden → empfangen (beide Browser)
- [ ] Chat-Videoanruf → Incoming-Call-Modal erscheint bei Callee
- [ ] **Dringender Anruf** → roter Modal + Sirene bei Callee
- [ ] Sidebar-Dot: grün = "ERREICHBAR", nach WLAN aus/an wird gelb → wieder grün
- [ ] News erstellen + veröffentlichen → in Feed sichtbar
- [ ] PWA-Install-Prompt erscheint auf Mobile
- [ ] Push-Notification wird auf physischem iPhone empfangen

---

## 🟡 P2 — Nice-to-have / Backlog

- [ ] Sentry / Rollbar für Error-Tracking integrieren (Backend + Frontend)
- [ ] Uptime-Monitoring (StatusCake, Better Uptime o. ä.) auf `/api/health`
- [ ] Bundle-Optimierung: weitere Code-Splits falls `main.js > 500 KB` wird
- [ ] Weitere React-Query-Migrationen (Pattern: siehe `NotificationBell.js`)
- [ ] Log-Retention: 30 Tage für INFO, 90 Tage für ERROR
- [ ] Penetration-Test durch externen Auditor

---

## 🔄 Rollback-Plan

Falls nach Deploy schwere Probleme auftreten:

1. **Sofort**: Emergent → Rollback-Button zum letzten funktionierenden Checkpoint (kostenlos, empfohlen).
2. **Alternative (git)**: Im Emergent-UI "Save to GitHub" → Branch zurücksetzen → neu deployen.
3. **Datenbank**: MongoDB-Schema ist nur additiv (neue Felder/Indexes). Ältere Code-Versionen können mit neuer DB arbeiten — kein Schema-Rollback nötig.

---

## 📋 Smoke-Test-Skript (nach jedem Deploy)

```bash
# Adapt to your production URL
API_URL="https://meetflow.meinklinik.de"

# 1. Health
curl -s "$API_URL/api/health" | jq '.status'  # expect "ok"

# 2. Login works + X-Request-ID returned
curl -s -i -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@meetflow.com","password":"<ADMIN_PW>"}' \
  | grep -iE "^HTTP|x-request-id"

# 3. Rate-limiting kicks in after 10 rapid attempts
for i in {1..12}; do
  curl -s -o /dev/null -w "%{http_code} " -X POST "$API_URL/api/auth/login" \
    -H "Content-Type: application/json" -d '{"email":"x@y","password":"z"}'
done
echo  # expect "401 401 ... 429 429"
```

---

**Verantwortlich**: Entwickler-Team  
**Letztes Review**: Iter 113  
**Nächstes Review**: Bei jedem größeren Release
