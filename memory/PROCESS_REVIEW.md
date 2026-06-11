# MeetFlow — Prozess-Review & Empfehlungen (Iter 69)

*Stand: Februar 2026 · Basierend auf End-to-End-Tests und Code-Analyse*

Dieses Dokument dokumentiert die Ergebnisse eines ausführlichen logischen Tests
der Anwendung und leitet daraus konkrete Prozess-Verbesserungen ab. Die
Empfehlungen sind nach Impact (🔴 P0 · 🟠 P1 · 🟡 P2) und Aufwand (S/M/L) priorisiert.

---

## 1. Kernflüsse — Befunde aus logischen Tests

### 1.1 Meeting-Lifecycle
| Schritt | Status | Beobachtung |
|---------|--------|-------------|
| POST /meetings (instant) | ✅ | Wird sofort `status=active`, aber `participant_count=0` bis zum ersten Join |
| Custom-Recurring-Generate | ✅ | 2 Slots × 2 Wochen = 4 Meetings korrekt |
| Serie verwalten (Bulk) | ✅ | PATCH /series/{id} + DELETE /series/{id} funktionieren |
| Einzeltermin absagen | ✅ | DELETE /meetings/{id} entfernt saubere Einzelinstanz |
| ICS-Export einzeln | ✅ | RRULE für simple patterns, Attendees, Organizer, URL |
| ICS-Export Serie | ✅ | Multi-VEVENT für Custom-Patterns (4 VEVENTs bei 2×2) |

**📌 Befund:** Der Host sieht nach Meeting-Ende keine automatische „Serie
fortsetzen?"-Abfrage. Bei Kündigung des letzten Termins einer Custom-Series
bleibt der `series_id` als "Geister-Serie" zurück.

### 1.2 News-Workflow
| Schritt | Status | Beobachtung |
|---------|--------|-------------|
| Draft → Review → Publish | ✅ | Approval-Chain funktioniert |
| Kommentare + Anhänge | ✅ | Max 10 Anhänge/Kommentar |
| Sentiment-Analyse | ✅ | Neue Anhang-Text-Extraktion aktiv |
| Read-Receipts | ✅ | CSV-Export vorhanden |
| Audit-Log | ✅ | Zeigt letzte 50 Aktionen |

**📌 Befund:** `news.py` hat 1237 Zeilen — Bulk-Update/Bulk-Publish fehlt.
Redakteure müssen News einzeln durch den Workflow schleusen.

### 1.3 Umfragen
| Schritt | Status | Beobachtung |
|---------|--------|-------------|
| Survey erstellen | ✅ | 4 Fragetypen (Single/Multi/Text/Skala) |
| Response + Anhang | ✅ | Freitext + Attachments OK |
| PDF-Report | ✅ | Matplotlib-Charts generiert |
| Pending-Count | ⚠️ | **22 von 32 Umfragen stehen offen** — Archivierung fehlt |

### 1.4 Scheduling-Polls
| Schritt | Status | Beobachtung |
|---------|--------|-------------|
| Poll + Voting | ✅ | Voter ohne Account via share_token |
| Confirm → Auto-Meeting | ✅ | Alle Voters als Teilnehmer übernommen |
| ICS nach Confirm | ✅ | Terminexport funktioniert |

**📌 Befund:** 25 Polls, davon ~18 mit Prefix `TEST_*` in der DB. **Keine
automatische Cleanup-Policy** für alte Test-/Draft-Daten.

### 1.5 Chat
| Schritt | Status | Beobachtung |
|---------|--------|-------------|
| WebSocket (1:1, Gruppe) | ✅ | Echtzeit, Typing, Reactions |
| File Upload | ✅ | GridFS-Anhänge |
| Search | ✅ | Global Cmd+K durchsucht Chats |

### 1.6 Verwaltung (fix im aktuellen Release)
| Schritt | Status | Beobachtung |
|---------|--------|-------------|
| Desktop-Tabs | ✅ | 12 Tabs funktional |
| Mobile-Tabs | ✅ | Neuer Dropdown-Navigator |
| Nutzer-CRUD, Gruppen, Presets, Regeln | ✅ | Alle Panels laden |

---

## 2. Prozess-Empfehlungen

### 🔴 P0 (Impact: kritisch, Aufwand: S–M)

**2.1 Daten-Hygiene / TEST-Daten-Cleanup (S)**
> **Problem:** ≈ 18 Test-Polls + 22 stale Surveys + 327 Meetings (viele davon Test-Series)
> überladen Dashboards, verfälschen Statistiken, verlängern Such-Zeit.
>
> **Empfehlung:** Cron-Job/Celery-Task, der einmal täglich Items löscht, die
> - mit `TEST_*` beginnen UND älter als 7 Tage sind
> - bzw. unbesuchte Drafts älter als 30 Tage
>
> **Impact:** Dashboards werden 3–5× schneller, Statistiken aussagekräftig.

**2.2 Meeting-Status-Konsistenz (S)**
> **Problem:** `participant_count=0` bei aktivem Instant-Meeting, obwohl der Host schon joined ist.
> `status=active` wird auf dem POST /meetings direkt gesetzt, der Host aber erst auf /join gezählt.
>
> **Empfehlung:** Bei `meeting_type=instant` den Host sofort als `joined_at=now` markieren,
> `participant_count=1` initialisieren. Konsistenz zwischen beiden Feldern erzwingen.

**2.3 Cookie-basierte Auth: Token in localStorage spiegeln für Debugging (S)**
> **Problem:** Während Mobile Push/PWA Tests ist Debugging erschwert, da JWT nur im httpOnly-Cookie
> lebt und in DevTools nicht sichtbar ist. Developer-Tools-Workflow ist umständlich.
>
> **Empfehlung:** In Dev-Mode (NODE_ENV) zusätzlich `window.__MEETFLOW_TOKEN__` für Debugging bereitstellen.
> Production bleibt unberührt (httpOnly-Cookie ist korrekt).

### 🟠 P1 (Impact: hoch, Aufwand: M)

**2.4 Series-Ausnahmen als "Cancelled" statt Hard-Delete (M)**
> **Problem:** Ein abgesagter Einzeltermin wird komplett gelöscht → er verschwindet aus der
> Historie / aus dem Audit-Log. Kein Nachweis, dass der 14.04. abgesagt wurde.
>
> **Empfehlung:** Neuen `status=cancelled` einführen statt DELETE. Cancelled Termine
> bleiben sichtbar im SeriesManagerDialog (grauer Badge), werden nicht im Kalender
> angezeigt und lassen sich per „Wiederherstellen" reaktivieren.

**2.5 Umfragen-Archivierung + Ablaufdatum (M)**
> **Problem:** 22 offene Umfragen → Benutzer klicken sie nicht mehr an (Benachrichtigungs-Müdigkeit).
>
> **Empfehlung:** Feld `expires_at` + automatische Archivierung. Surveys, die 14 Tage nach
> Deadline noch offen sind, landen in „Archiv" und zählen nicht mehr in pending-count.

**2.6 Onboarding-Tour Skip-Persistence (S)**
> **Problem:** Beim E2E-Testing überdeckt der Onboarding-Dialog wiederholt die UI, obwohl
> `onboarding_dismissed` in localStorage steht. Vermutlich wird dismissed nicht pro Nutzer gekoppelt.
>
> **Empfehlung:** Dismiss-Flag serverseitig in `users.onboarding_completed_at` speichern,
> nicht in localStorage. Dann funktioniert es geräte-übergreifend korrekt.

**2.7 ICS-Auto-Send bei Meeting-Erstellung (M)**
> **Problem:** Eingeladene Teilnehmer bekommen keine Kalender-Einladung automatisch. Sie müssen
> manuell aus der UI ICS herunterladen.
>
> **Empfehlung:** Bei POST /meetings und bei Serien-Confirm automatisch ICS per E-Mail
> (Resend/SMTP) an alle `invited_emails` senden. Header `Content-Type: text/calendar; method=REQUEST`.
> Nutzer können in Outlook/Gmail mit einem Klick akzeptieren.

### 🟡 P2 (Impact: mittel, Aufwand: M–L)

**2.8 Routen-Refactoring abschließen (L)**
> **Problem:** `meetings.py` = 2165 Zeilen, `news.py` = 1237 Zeilen. Schwer zu warten.
>
> **Empfehlung:** Analog zu `meetings_recurring.py` + `news_sentiment.py` folgende
> Services extrahieren:
> - `services/meetings_modes.py` (MEETING_MODE_CONFIG + mode-specific logic)
> - `services/meeting_summaries.py` (AI-Summary, Transcript-Handling)
> - `services/news_approval.py` (Draft → Review → Publish Workflow)
> - `services/news_targeting.py` (Zielgruppen-Matching)

**2.9 Permissions-Audit-UI für User (S)**
> **Problem:** Nutzer können ihre eigenen effektiven Capabilities nicht einsehen. Führt
> zu Frust, wenn Buttons „einfach nicht da" sind.
>
> **Empfehlung:** Im Profil-Tab eine Sektion „Meine Rechte" mit Liste aller aktiven Caps
> und deren Quelle (Rolle / Gruppe / Preset / Direkt). Simulator-Output für Endnutzer.

**2.10 Meeting-Vorlagen (Templates) als Serien-Presets (M)**
> **Problem:** Templates speichern `recurring=true` aber ohne `recurring_schedule`.
> Das heißt: Custom-Pattern-Serien müssen jedes Mal neu komplett eingegeben werden.
>
> **Empfehlung:** Template-Model um `recurring_schedule` + `recurring_weeks` erweitern.
> „Jour Fixe Pflegedienstleitung" wird zum One-Click-Preset.

**2.11 Kalender-Sync (M)**
> **Problem:** Kalender-Seite zeigt nur MeetFlow-interne Termine. Outlook-/Google-Kalender-
> Termine bleiben außen vor.
>
> **Empfehlung:** CalDAV-Read-Only-Sync. User trägt einmal seine Outlook-URL ein und
> sieht externe Termine als graue Balken im MeetFlow-Kalender — vermeidet Doppelbuchungen.

---

## 3. Technisch-hygienische To-Dos (Low Impact, keep in backlog)

- `dnd_enabled`/`presence`-Defaults vereinheitlichen (nie `None`)
- `routes/__pycache__/*.pyc` aus Git ignorieren (bereits via .gitignore — prüfen)
- `iteration_60_features.py` und Legacy-Tests konsolidieren
- Lint-Warnings in `meetings.py` / `news.py` (F841, E701) bereinigen — 24 Issues
- `requirements.txt`: pypdf **und** PyPDF2 installiert → auf `pypdf` standardisieren

---

## 4. Security / Compliance

- ✅ JWT in httpOnly-Cookie + Refresh-Flow
- ✅ GridFS Upload-Mime-Whitelist (keine Executables)
- ✅ Capability-Gates auf allen Admin-Endpoints
- ⚠️ **Rate-Limit** aktuell nur auf `/auth/*`. Empfehlung: zusätzlich für
  `/news/report`, `/feedback/submit`, `/push/subscribe` — Anti-Spam-Guard.
- ⚠️ Verschlüsselung der Anhänge at rest (GridFS) ist nicht dokumentiert — wichtig
  für DSGVO bei Klinik-Daten.

---

## 5. Zusammenfassung der Top-5-Quick-Wins

| # | Änderung | Aufwand | Impact |
|---|----------|---------|--------|
| 1 | Cleanup-Cron für TEST_* Daten | S | 🔴 Sofort spürbar |
| 2 | Meeting-Participant-Count-Fix | S | 🔴 UX-Polish |
| 3 | Onboarding serverseitig speichern | S | 🟠 Test-Stabilität |
| 4 | Cancelled-Status statt Delete (Serien) | M | 🟠 Audit/DSGVO |
| 5 | ICS-Auto-Email bei Einladung | M | 🟠 Teilnahme +15 % |

**Nächster empfohlener Sprint:** #1 + #2 + #5 (alle klein/mittel, großer sichtbarer Effekt).
