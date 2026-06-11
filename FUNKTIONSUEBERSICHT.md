# MeetFlow — Funktionsübersicht

**Stand**: Iter 400 (Juni 2026)
**Positionierung**: Alles für den Arbeitsalltag — Chat, Aufgaben, Meetings und Ressourcen-Buchung in einer Plattform.
**Plattform**: PWA-fähig, Mobile-optimiert, Offline-Cache, Push-Notifications.

---

## 1. Authentifizierung & Sicherheit

### Login-Verfahren
- E-Mail + Passwort
- Personalnummer + Passwort (E-Mail-lose Konten — Admin kann Benutzer ohne E-Mail anlegen, Login über Personalnummer)
- Azure AD / Microsoft 365 SSO
- Google OAuth (Emergent-Managed)
- Bleibt-angemeldet / Refresh-Token-Auto-Renewal

### Passwort-Sicherheit (Strict-Policy)
- Mindestens 8 Zeichen, 4-aus-4-Regeln (Großbuchstaben, Kleinbuchstaben, Ziffern, Sonderzeichen)
- 6-Monats-Rotation (configurable über Org-Settings)
- 3-Passwort-Historie (verhindert Wiederverwendung)
- Force-Change beim ersten Login + nach Admin-Reset
- Self-Service Passwort-ändern-Dialog mit Stärke-Indikator
- Admin-Reset mit Temp-Passwort (Shadcn-Dialog + Clipboard-Copy)

### Session-Management
- JWT mit HttpOnly-Cookie
- Refresh-Token mit Auto-Rotation
- Token-Version-Bump beendet alle aktiven Sessions eines Users (bei Passwort-Reset)
- Logout: vollständiger Cache-Cleanup (sessionStorage + alle `mf_*` localStorage-Keys, außer Geräte-Präferenzen)

---

## 2. Benutzer- & Rechteverwaltung (IAM)

### Benutzer
- CRUD via Admin-UI (Liste, Detail, Bearbeiten, Löschen)
- Bulk-Aktionen (Aktivieren / Deaktivieren / Rolle ändern)
- E-Mail-Einladung mit Magic-Link + Passwort-Reset-Token
- Demo-User-Auto-Seed + kaskadierender Demo-Daten-Wipe
- Letzter Login + letzter Passwort-Wechsel als sortierbare Spalten
- Status-Indikator (Online / DND / Abwesend / Offline)
- Profilbild mit Initials-Fallback

### Rollen-System (4 Rollen)
- **Admin** (volle Capabilities)
- **Moderator** (eingeschränkt)
- **Mitarbeiter** (Standard-Set)
- **Gast** (minimal)
- Rollen-Defaults werden aus `CAPABILITIES`-Set abgeleitet
- Per-User Cap-Grants und Cap-Denies möglich

### Gruppen-System
- **System-Modul-Gruppen** (4): `Modul: Gast`, `Modul: Standard`, `Modul: Verwaltung`, `Modul: Auswertungen`
  - Mitgliedschaft wird automatisch über die Rolle gepflegt
  - Modul-Rechte editierbar und persistent (auch nach Backend-Restart, ab Iter 384)
- **Custom-Gruppen** mit eigenen Capabilities und Role-Override
- Bulk-Member-Management

### Capabilities (74 Stück)
- **Meetings**: create, join, edit, delete, share_recording, transcript_view, view_others
- **Chat**: send_message, create_group, delete_message, moderate
- **Tasks**: create, edit, assign, complete, view_others
- **News**: create, edit, delete, moderate, pin, target_all, mandatory
- **Ressourcen**: book, manage, approve, view_others
- **Catering**: order, process, manage_items
- **Surveys**: create, fill, view_results
- **Fuhrpark**: view_drivers_license, manage_vehicles
- **Auswertungen**: view_meetings, view_scheduling, view_surveys, view_bookings, view_platform_stats, view_catering_history
- **Verwaltung**: admin_panel, manage_users, manage_roles, manage_groups, manage_org_settings, view_audit_log, demo_seed
- + viele weitere granulare Berechtigungen

### Capability-Presets
- Vordefinierte Bündel (z.B. „Buchhaltung", „Fuhrpark-Manager")
- Klick-zum-Zuweisen statt Einzelauswahl

### Audit & Compliance
- Audit-Log aller sicherheitsrelevanten Aktionen (Logins, Rollen-Wechsel, Daten-Wipe etc.)
- System-Audit-Tab mit Quick-Scans und Health-Checks

---

## 3. Meetings & Video-Konferenz

### Meeting-Erstellung
- Einmalige + Serien-Meetings
- Privat / Öffentlich / Passwort-geschützt
- Eingeladene Teilnehmer (intern + extern via E-Mail)
- Vorlagen für wiederkehrende Meetings

### Live-Meeting
- WebRTC-basierte Audio/Video-Konferenz
- Bildschirmübertragung (Screen-Share)
- Gruppenräume (Breakout-Rooms)
- Live-Chat während Meeting
- Hand heben + Reaktionen (Emojis)
- Aufzeichnung (mit Disc-basierter Storage)
- Live-Polls
- Whiteboard

### Nachbereitung
- KI-Zusammenfassungen (GPT-5.2)
- Automatische Transkripte (Whisper)
- Action-Items-Extraktion
- Recording-Library mit Zugriffsrechten

### Telefonie / Status
- Status-Sync (Online / DND / Abwesend) mit Kalender-Integration
- Eingehende Anrufe → IncomingCallModal mit Annehmen/Ablehnen
- Auto-DND bei Meeting-Zeiten

---

## 4. Chat & Messaging

### Direktnachrichten + Gruppen
- 1:1, Gruppen-Chat, Channels
- Read-Receipts + Tipp-Indikator
- Dateianhänge (Bilder, Dokumente, GIFs via Tenor)
- Nachrichten zitieren / antworten
- Emoji-Reaktionen
- Markdown + Code-Blöcke
- Nachrichten suchen + Konversation durchsuchen
- Edit + Delete (innerhalb Zeitfenster)

### Erweiterte Features
- Voice-Memos (Sprachnachrichten)
- Bildschirm-Sharing direkt aus Chat
- Audio/Video-Anruf aus Conversation
- Stumm-Schaltung pro Konversation
- @-Mentions mit Notification
- Chat-Bots (System-Nachrichten)

### Echtzeit & Offline
- WebSocket-basierte Echtzeitübermittlung
- Notification-Ton bei jeder eingehenden Nachricht (Slack-Pattern)
- Push-Notifications für Mobile (PWA)
- Sound-Volume-Profile (low/normal/loud)
- DND-Modus unterdrückt Töne + Toasts

---

## 5. Aufgaben (Tasks)

### Task-Verwaltung
- Eigene + zugewiesene Aufgaben
- Status: Offen / In Bearbeitung / Erledigt
- Priorität (Low/Med/High/Critical)
- Fälligkeitsdatum mit Erinnerung
- Subtasks (Checklisten)
- Anhänge + Kommentare
- Aus Meetings/Chat erstellbar (Right-click „als Aufgabe")
- Wiederkehrende Aufgaben

### Übersichten
- Meine Aufgaben (Dashboard-Widget)
- Team-Aufgaben (für Manager/Admins)
- Überfällige Aufgaben mit visueller Hervorhebung
- Sidebar-Counter (offen + überfällig)

---

## 6. Kalender & Terminplanung

### Kalender
- Persönlicher Kalender mit Meetings + Buchungen integriert
- Team-Kalender (Kollegen-Ansicht)
- Tag / Woche / Monat-Ansichten
- iCal-Export
- Microsoft 365 / Outlook-Sync (geplant — P1)

### Terminplanung
- Doodle-ähnliche Slot-Abstimmung
- Externe Teilnehmer-Einladung per Link
- Verfügbarkeits-Heatmap
- Auto-Buchung beim finalen Slot

---

## 7. News & Beiträge

### News-Feed
- Hierarchische Beiträge (Org → Abteilung → Team)
- Reichweite konfigurierbar (alle / einzelne Gruppen)
- Pflicht-News (mandatory) mit Lesebestätigung
- Pinned-News (oben fixiert)
- Bilder / Videos / Anhänge
- Reaktionen + Kommentare
- Reichweiten-Statistik

### Moderation
- News-Reports (User können Beiträge melden)
- Moderations-Tab in Auswertungen
- Soft-Delete + Wiederherstellung

---

## 8. Ressourcen & Buchung

### Buchbare Ressourcen
- Besprechungsräume (mit Kapazität, Ausstattung)
- Arbeitsplätze (Desk-Sharing)
- Fahrzeuge (mit Führerschein-Check)
- Catering-Anfragen (an Buchung gekoppelt)

### Buchungs-Workflow
- Einfache Buchung + Serien-Buchung (täglich/wöchentlich/monatlich/benutzerdefiniert)
- Multi-Date-Kalender für „Benutzerdefinierte Buchung"
- Mobile-optimiert (1-Monat-Ansicht auf <640px)
- Konflikt-Erkennung mit Vorschlägen
- Freigabe-Workflow (für Räume mit Genehmigungspflicht)
- Stornierung mit Begründung
- No-Show-Tracking
- Wiederholbare Buchungs-Templates

### Catering-Modul
- Catering-Items-Verwaltung (Name, Preis, Einheit)
- Anfrage an Buchung anhängen
- Status-Workflow: Angefragt → Bestätigt → In Bearbeitung → Geliefert → Abgeschlossen
- Stornierung + Ablehnung mit Grund
- Catering-Inbox für Caterer (separater Tab)
- Mindestvorlauf-Check + „Kurzfristig"-Warnung

### Fuhrpark
- Fahrzeug-Buchung (Klasse-Check gegen Führerschein)
- Führerscheine-Verwaltung pro Mitarbeiter
- Foto-Upload + Verfallsdatum-Check
- Schaden-Reports + No-Show-Tracking

### Rechnungen / Belege
- Sammelrechnung-Generierung (Buchungen + Catering)
- DATEV-konformer CSV-Export
- Rechnungs-Templates mit Logo + Footer
- Nummernkreise pro Geschäftsjahr
- Stripe-Integration für Online-Zahlung (Test)
- PDF-Generierung serverseitig

---

## 9. Umfragen (Polls / Surveys)

- Live-Polls während Meetings
- Standalone-Umfragen mit Multi-Question
- Multiple-Choice + Single-Choice + Freitext + Bewertungsskala
- Anonyme + namentliche Stimmen
- Reichweiten-Steuerung (alle / Gruppen / Einzelne)
- Ergebnis-Live-View mit Charts
- Export als CSV

---

## 10. Auswertungen (Analytics)

### Gruppe „Nutzungs-Auswertung"
- **Meetings-Analyse**: Anwesenheit, Modi, Daily-Counts, Top-User
- **Terminplanung-Analyse**: Slot-Auslastung, Verfügbarkeits-Statistik
- **Umfragen-Analyse**: Teilnahmequoten, Ergebnis-Aggregation
- **Buchungs-Analyse**: Ressourcen-Auslastung, No-Show-Quote
- **Plattform-Statistiken**: Nutzer, Meetings, Nachrichten, Aufrufe etc.

### Gruppe „Datenpflege"
- **Catering-Artikel-Historie**: Verbrauchte Items mit Buchung, Raum, Anforderer, Kostenstelle, Status, Rechnungs-Backlink. CSV-Export (UTF-8 BOM für Excel). Filter: Zeitraum (Alle / Letzte Woche / Letzter Monat / Benutzerdefiniert) + Status-Multi-Select + Volltextsuche. Zahlen 100% deckungsgleich mit Sammelrechnungen.
- **Führerscheine**: Alle eingetragenen Führerscheine mit Klassen, Behörde, Verfallsdatum, Foto-Verifikation
- **News-Moderation**: gemeldete Beiträge + Workflow für Soft-Delete / Restore

### Granulare Capabilities
- Jeder Tab ist einzeln per Capability zuteilbar (z.B. Buchhaltung sieht nur Catering-Historie, Fuhrpark-Manager nur Führerscheine)

---

## 11. Verwaltung (Admin-Panel)

### Identität
- Benutzer-CRUD (oben Modul 2)
- Gruppen-Editor
- Presets-Editor
- Rollen-Rechte-Matrix
- Berechtigungs-Hub (Überblick aller Caps + Zuordnungen)

### Konfiguration
- Org-Settings (Name, Logo, Branding-Farben, Domain)
- Lizenz-Status + Limits
- Catering-Items-Master-Data
- Ressourcen-Verwaltung (Räume, Plätze, Fahrzeuge anlegen)
- Rechnungs-Templates + Nummernkreise
- Push-Notification-Server-Key (VAPID)
- Storage-Backend (Disc + Cloud)
- Branding (Logo + Primärfarbe für Sidebar / Login)

### Monitoring (technisch)
- Health-Check + Backend-Status
- Quick-Scans (DB-Integrity, Orphaned-Records)
- Audit-Log (Browsable, Filterable, Export)
- System-Audit (Iter-Tracking + Compliance-Reports)

### Maintenance
- Demo-Daten-Seed + kaskadierender Wipe
- Mass-Import (CSV-User)
- Backup / Restore (manuell)

---

## 12. Dashboard

- **Heute im Büro / Diese Woche**: Anwesenheits-Übersicht
- **Meine nächsten Buchungen**: Räume + Plätze + Fahrzeuge
- **Offene Aufgaben** mit Quick-Complete
- **Anstehende Meetings** mit Join-Button
- **News-Feed-Preview**
- **Quick-Actions**: Neues Meeting / Neuer Chat / Neue Buchung
- **Wetter-Widget** (optional, je Standort)

---

## 13. Mobile / PWA

- Vollwertige PWA-Installation (Manifest mit Apple-Touch-Icon)
- Service-Worker mit Offline-Shell + API-Cache (stale-while-revalidate für read-only-Daten wie Tasks, News, Dashboard)
- Push-Notifications (Web-Push mit VAPID)
- Mobile-optimierte Layouts (Sidebar als Off-Canvas, responsive Tabellen)
- Touch-Gesten in Chat + Buchungs-Kalender
- Mobile-Cache-Hydration für sofortige UI-Anzeige nach Reload

---

## 14. Integrationen (3rd Party)

- **OpenAI GPT-5.2** (Meeting-Zusammenfassungen, Action-Items) — Emergent LLM Key
- **OpenAI Whisper** (Transkription) — Emergent LLM Key
- **Gemini Nano Banana** (Bild-Generation für Branding) — Emergent LLM Key
- **Stripe** (Rechnungs-Bezahlung) — Test-Key
- **Azure AD / Microsoft 365** (SSO)
- **Tenor** (GIF-Suche im Chat)
- **Outlook / M365 Kalender** (geplant — P1)

---

## 15. Technische Eigenschaften

- **Backend**: FastAPI (Python 3.11), MongoDB, WebSockets
- **Frontend**: React + TanStack Query + Tailwind + Shadcn UI + Lucide Icons
- **Realtime**: WS-Broker für Chat, Status, Notifications
- **Auth**: JWT + Refresh-Token-Rotation
- **Build**: PWA mit Service Worker
- **Internationalisierung**: i18n-System (DE/EN, easy expandable)
- **Sprache**: Komplette deutsche UI mit korrekten Umlauten

---

*Generiert für Dokumentationszwecke. Bei Fragen zu einzelnen Funktionen: API-Routen unter `/app/backend/routes/`, UI-Komponenten unter `/app/frontend/src/components/`.*
