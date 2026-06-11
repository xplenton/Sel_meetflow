# MeetFlow — Funktionen für Compliance & Datenschutz

**Übersicht für DSGVO, Audit und Sicherheits-Compliance.**

---

## Datenschutz (DSGVO/GDPR)

**Datenerhebung**
- Personenbezogene Daten: Name, E-Mail oder Personalnummer, ggf. Profilbild, Telefon, Abteilung
- Optional: Führerschein-Foto + Klassen (für Fuhrpark)
- Authentifizierungs-Metadaten: Letzter Login, Login-IP, Geräte-Token

**Speicherort**
- Self-hosted (Kunden-VM/Cloud, MongoDB)
- Keine Drittanbieter-Datenweitergabe außer aktiv konfigurierter Integrationen (OpenAI, Stripe, Azure SSO, Tenor)

**Rechte der Betroffenen**
- Selbst-Service Profilbearbeitung (Auskunftsrecht über eigene Daten)
- Datenexport via Admin (auf Anfrage)
- Lösch-/Anonymisierungs-Funktion via Admin („User löschen" entfernt PII, behält pseudonymisierte Audit-Logs)
- Recht auf Korrektur (Profil-Editor)

**Datenminimierung**
- E-Mail-lose Konten möglich (Login via Personalnummer)
- Optionale Felder (Telefon, Bild) frei wählbar
- Catering/Buchungen referenzieren `user_id` (interne ID), nicht direkt PII

---

## Zugriffskontrolle

**Authentifizierung**
- Multi-Faktor optional über Azure AD/M365 SSO
- Starke Passwort-Policy (4-aus-4, mindestens 8 Zeichen, 6-Monats-Rotation, 3-Passwort-Historie)
- Bcrypt-Hashing (Cost-Faktor 12)
- Server-side Session-Revocation via Token-Version-Bump

**Autorisierung (RBAC + ABAC)**
- 4 Rollen (Admin, Moderator, Mitarbeiter, Gast)
- 74 atomare Capabilities (granulare Funktions-Berechtigungen)
- Custom-Gruppen mit eigenen Capability-Sets
- Per-User Cap-Grants und Cap-Denies (Whitelist/Blacklist)
- Capability-Presets (z.B. „Buchhaltung", „Fuhrpark-Manager") für DRY-Zuweisung

**Trennung von Funktionen (SoD)**
- Beispiel: Buchhaltung kann nur `analytics.view_catering_history` sehen, nicht User verwalten
- Fuhrpark-Manager: `users.view_drivers_license` + Fahrzeug-Buchungen, kein Admin-Zugriff
- News-Moderatoren: `news.moderate` ohne weitere Privilegien

---

## Audit & Nachvollziehbarkeit

**Audit-Log**
- Alle sicherheitsrelevanten Aktionen werden geloggt:
  - Logins (erfolgreich + fehlgeschlagen)
  - Rollen-/Gruppen-Änderungen
  - Passwort-Resets
  - Daten-Wipes (Demo-Daten)
  - Capability-Anpassungen
  - User-Anlage/-Löschung
  - Rechnungs-Erstellung
- Browsable + filterbar im Admin-Panel
- CSV-Export
- Unveränderlich (Append-Only)

**Audit-Sealing** (P1 — geplant)
- Hash + Signatur + Timestamp für regulierte Compliance-Reports
- Beweismittelfähigkeit nach §147 AO / GoBD

**Nachweise**
- Pflicht-News mit Lesebestätigung (Wer hat wann gelesen?)
- Lese-/Schreibstatus auf Catering-Anfragen, Buchungen, Rechnungen
- Versionierte Rechnungen (nicht editierbar nach Erstellung)
- Account-Login-Historie

---

## Sicherheitsfeatures

**Transport-Sicherheit**
- HTTPS-only (HSTS-Header)
- WebSocket über WSS
- CORS auf eigene Domain beschränkt

**Anwendungs-Sicherheit**
- Content-Security-Policy (img-src auf self/data/blob/https)
- HttpOnly-Cookies (XSS-Schutz)
- CSRF-Schutz über SameSite-Cookies
- Rate-Limiting auf Auth-Endpoints

**Mandanten-Trennung**
- Single-Tenant pro Installation (keine Cross-Tenant-Datenmischung)
- Eigene MongoDB pro Kunde

**Backup & Recovery**
- Manuelle MongoDB-Dumps + automatisierte Snapshots (Hosting-Provider)
- Recordings + Anhänge auf persistenter Disc, separat backupbar

---

## Drittanbieter-Datenflüsse

| Dienst | Daten | Zweck | Region | DPA verfügbar |
|---|---|---|---|---|
| OpenAI (GPT-5.2) | Meeting-Transkript-Texte | KI-Zusammenfassung | USA | Ja (Enterprise) |
| OpenAI Whisper | Audio-Dateien (Meeting-Recordings) | Transkription | USA | Ja (Enterprise) |
| Stripe | Rechnungs-Beträge, Zahler-Email | Bezahlung | EU/USA | Ja |
| Azure AD | E-Mail, Name (SSO) | Authentifizierung | Kunden-Tenant | Microsoft DPA |
| Tenor | Suchanfragen für GIFs | GIF-Suche | USA | Ja |

**Hinweis**: Alle Drittanbieter-Integrationen sind im Admin-Panel deaktivierbar.

---

## Compliance-Standards (relevant)

- **DSGVO/GDPR**: User-Rechte, Datenminimierung, Audit-Trail erfüllt
- **GoBD** (Deutschland, Buchhaltung): Rechnungen unveränderlich + nummeriert. Audit-Sealing P1 in Roadmap
- **§147 AO** (Aufbewahrungspflicht): Rechnungen 10 Jahre archivierbar via Export
- **TR-RESISCAN/TR-ESOR** (DE Compliance): nach Audit-Sealing-Iter erfüllbar

---

## Datenexport & -löschung

**Export auf Anfrage**
- Admin kann pro User komplette Datenexport-JSON generieren
- Rechnungen, Buchungen, Aufgaben, Chat-Verläufe einzeln exportierbar

**Löschung**
- Soft-Delete (Status `deleted`) für Tasks, News, Nachrichten — wiederherstellbar
- Hard-Delete bei User-Account → PII entfernt, Pseudonym in Audit-Logs erhalten
- Demo-Daten-Wipe kaskadierend (alle Demo-User + deren Daten in einer Aktion)

---

*Für eine vollständige Datenschutz-Folgenabschätzung (DPIA) kontaktiere den Hersteller-Support oder konsultiere `/app/DEPLOY.md` für Hosting-spezifische Compliance-Hinweise.*
