# MeetFlow — Product Requirements Document (PRD)

## Original Problem Statement
Erweiterte bestehende Software ("MeetFlow") für ein zusätzliches Modul zur Verwaltung und Buchung von Besprechungsräumen, Arbeitsplätzen / Desk Sharing und Fahrzeugen — vollständig integriert mit RBAC, Tasks, Calendar und Billing/Rechnungen.

## User Personas
- **Admin**: Verwaltet Nutzer, Gruppen, Ressourcen, Rechnungen, Self-Registration-Whitelist
- **Manager**: Bestätigt Bookings, sieht Auswertungen, exportiert DATEV
- **Mitarbeiter**: Bucht Räume/Desks/Fahrzeuge, nutzt Check-in/out, Tasks, Calendar
- **Gast**: Eingeschränkter Zugriff via `role_override` auf Gast-Gruppe
- **Catering**: Spezielle Inbox für Catering-Requests mit Push-Benachrichtigungen

## Core Requirements (23 Hauptpunkte umgesetzt)
1. Resource-Management (Räume / Desk Sharing / Fahrzeuge)
2. Vollständige RBAC-Integration mit Gruppen + `role_override`
3. Calendar Integration (intern, Outlook-Stub vorhanden)
4. Tasks Integration
5. Billing / Rechnungen mit Stripe Test-Integration
6. PDF/CSV/DATEV Export
7. Check-in / Check-out mit Reminders & Dashboard-Widget
8. "Buchung für Andere" (Book for others)
9. Delegate (Stellvertreter) Profile
10. Catering-Workflow mit Inbox, Push-Notif, Outside-Click-Schutz
11. PWA, News, Surveys, Chat
12. Self-Registration mit Domain-Whitelist & 24h Auto-Lock
13. Admin UI für Pending-Verifications (Iter 291)
14. XSS-Härtung via DOMPurify (`lib/sanitize.js`)
15. Push-Notifications (Webpush)
16. SSO via Azure AD / Authlib
17. Self-Service Verifikation + Resend-Verification
18. Floorplan Auto-Load
19. Background Reminder Loop für Auto-Lock & Check-out Reminders
20. Audit-Log (`log_caps_change`)
21. User-Cache mit Invalidierung
22. Multi-Tenancy Settings (`org_settings`)
23. Sicherheits-Review (XSS, React Keys, undefined vars) abgeschlossen

## Tech Stack
- **Frontend**: React, Shadcn/UI, DOMPurify, sonner toasts
- **Backend**: FastAPI, Motor (MongoDB), Authlib (SSO), Stripe SDK 15.0.1, WebPush
- **DB**: MongoDB Replica Set
- **Integrations**: OpenAI GPT-5.2 (Emergent LLM Key), Azure AD, Stripe (Test Key)

## Architecture
```
/app/
├── backend/
│   ├── routes/
│   │   ├── resources/   (invoice_tracking, catering, admin)
│   │   ├── admin/       (users.py — resend verification)
│   │   └── auth.py      (Domain-Whitelist)
│   ├── services/        (permissions, background_queue, user_cache)
│   └── server.py        (_reminder_loop für Auto-Lock)
├── frontend/src/
│   ├── components/      (admin/AdminUserRow, resources/BillingPanel)
│   └── lib/sanitize.js  (DOMPurify)
└── memory/              (PRD, CHANGELOG, ROADMAP)
```

## Latest Implemented (Feb 2026)
- **Iter 387** (2026-02-06): Chat-Sound bei jeder Nachricht (auch in geöffneter Konversation)
  - **Symptom (User-Report)**: „nur bei erste chat nachricht kommt ein ton nicht bei weiteren in einem chat".
  - **Root Cause**: In `ChatUnreadContext.js` Z. 117 hat ein einziger Guard (`window.__mfActiveConv === conversation_id`) **gleichzeitig** Toast UND Sound unterdrückt. Die allererste WS-Nachricht spielte einen Ton, weil sie das Race gegen das useEffect gewann, das `__mfActiveConv` setzt — alle folgenden Nachrichten in derselben Konversation waren stumm.
  - **Fix**: Sound und Toast entkoppelt. **Sound** läuft jetzt bei JEDER eingehenden Fremd-Nachricht (außer mute/DND/Call-Type). **Rich-Toast** weiterhin nur für nicht-aktiv-betrachtete Konversationen (um Popup-Spam beim Live-Lesen zu vermeiden). Verhalten entspricht jetzt Slack/Teams-Standard.

- **Iter 386** (2026-02-06): Booking-Series Mobile-Fix + GUI-Umlaut-Sweep
  - **`BookingSeriesSection.js`**: Label „Benutzerdefinierte Daten…" → „Benutzerdefinierte Buchung". Multi-Date-Kalender im Popover zeigt auf Mobile (<640px) jetzt **1 Monat** statt 2 (vorher: Popup ragte aus dem Viewport). `useIsMobile()` Hook via `matchMedia('(max-width: 639px)')`. PopoverContent mit `max-w-[calc(100vw-1.5rem)]`-Cap. Align wechselt auf Mobile von „end" → „center".
  - **Umlaut-Sweep**: 267 Treffer ASCII→Unicode in 84 Dateien automatisch ersetzt (Frontend `.js`/`.jsx` + Backend Python-Strings). Allowlist-Filter mit 70+ deutschen Wortstämmen (zurück, ändern, löschen, für, über, nächst, gültig, prüf, schlüssel, möglich etc.) verhindert False-Positives bei englischen Wörtern. Backend-Replacement war auf String-Literale begrenzt — keine Identifier-Brüche. Script: `/tmp/umlaut_sweep.py` (regenerierbar).

- **Iter 385** (2026-02-06): GIFs werden auf Mobile (iOS Safari) wieder angezeigt
  - **Symptom (User-Report)**: „GIF wird in Chat an mobile Geräte nicht angezeigt".
  - **Root Cause**: `<img loading="lazy">` triggert auf iOS Safari den IntersectionObserver für Bilder in scrollenden Flex-Containern (`flex-1 overflow-y-auto` der ChatMessages-Liste) bekannt unzuverlässig. Resultat: GIF-Element bleibt mit 0 Höhe leer.
  - **Fix** (`pages/ChatPage.js`): GIF-Rendering robuster gemacht — `loading="lazy"` entfernt, `referrerPolicy="no-referrer"` für Tenor-CDN, expliziter `min-h-[120px]`-Platzhalter im Wrapper, `onError`-Fallback öffnet GIF als Link in neuem Tab. Wrapper ist jetzt ein `<a>`-Element (data-testid `gif-msg-{message_id}`).
  - **Verifiziert (Playwright)**: GIF wird per UI gesendet → erscheint im Chat → IMG-Box 240×240px sichtbar.
  - **Begleit-Cleanup**: 10 pre-existing `catch {}` Empty-Block-Lint-Warnungen in `ChatPage.js` mit `/* ignore */` ergänzt (Lint-Block für künftige Edits gesenkt).

- **Iter 384b** (2026-02-06): UI-Hinweis für editierbare System-Modul-Gruppen
  - **`GroupsPanel.js`**: SYSTEM-Badge-Tooltip in der Liste klarstellt, dass Modul-Rechte editierbar sind und auch über Backend-Restart hinweg erhalten bleiben. Im Edit-Dialog ein lila Info-Banner ergänzt (data-testid `system-module-group-info-banner`), das Admins erklärt: (a) Mitgliedschaft wird über die Rolle gepflegt, (b) Modul-Rechte sind voll editierbar, (c) Änderungen sind dauerhaft.
  - **Verifiziert**: Screenshot zeigt Banner korrekt im Edit-Dialog von „Modul: Standard". Tooltip auf SYSTEM-Badge in der Liste enthält den vollen Text.

- **Iter 384** (2026-02-06): System-Modul-Gruppen sind editierbar (Persistenz-Fix)
  - **Symptom (User-Report)**: „in `Modul: Standard` ist news nicht ausgewählt — wenn man User zuordnet, ist News trotzdem sichtbar". Root Cause war ein gemischtes Verhalten: zwar konnte der Admin via UI Capabilities entfernen, aber `_ensure_module_groups()` setzte beim nächsten Backend-Start die Caps-Liste per `$set` zurück auf den Code-Default.
  - **Fix** (`routes/org_onboarding.py`): `capabilities`, `members` und `created_at` von `$set` auf `$setOnInsert` verschoben. Beim ersten Anlegen einer Modul-Gruppe wird der Default befüllt; beim zweiten und allen weiteren Bootups bleibt die Admin-Anpassung erhalten. Metadaten (`name`, `description`, `color`, `is_system`, `module_group`) bleiben in `$set`, damit ein zukünftiges Rename/Recoloring noch propagiert wird.
  - **Trade-off**: Neue Module (z.B. später `view:invoices`) propagieren nicht mehr automatisch in bestehende Modul-Gruppen. Admin muss sie aktiv per UI zuweisen — Admin-Edits sind ab jetzt die Source-of-Truth.
  - **Verifiziert via curl + DB**: PUT entfernt `view:news` aus `Modul: Standard` → Backend-Restart → caps bleiben ohne `view:news`. Delete der `Modul: Gast` Gruppe + Bootstrap-Aufruf → Default-Caps (`view:dashboard`, `view:chat`) werden korrekt befüllt. Members bleiben erhalten.

- **Iter 383** (2026-02-06): Chat-Realtime-Bug Fix — Service Worker servierte stale Messages
  - **Symptom (User-Report)**: Eigene gesendete Nachrichten erscheinen nicht im Chat (erst nach Hard-Reload), empfangene Nachrichten aktualisieren sich nicht, kein Benachrichtigungston.
  - **Root Cause**: `frontend/public/sw-push.js` hatte `/api/chat/conversations` in `API_CACHE_PATHS`. Da der Fetch-Handler `startsWith()` matcht, wurden auch alle Sub-Endpoints inkl. `/api/chat/conversations/{id}/messages` per `stale-while-revalidate` gecached. Bei jedem REST-Refetch (POST-Reload, WS-Reconnect, Visibility-Change) servierte der SW die alte gecachte Liste ohne die neuen Nachrichten.
  - **Fix**: `/api/chat/conversations` aus der `API_CACHE_PATHS`-Whitelist entfernt. `API_CACHE` von `meetflow-api-v3` → `meetflow-api-v4` gebumpt, sodass der `activate`-Handler den alten Cache beim Update löscht.
  - **Hinweis Production**: Wie bei dem analogen Iter-377-Fix (`/api/auth/me`) manifestiert sich der Bug typischerweise nur in Production, wo der SW über Sessions akkumuliert. Redeploy nötig, damit der gefixte SW zu Nutzern rollt — beim nächsten Reload aktiviert er sich via `skipWaiting()` automatisch.

- **Iter 382** (2026-02-06): Admin Reset Password — UI-Upgrade
  - `components/admin/ResetPasswordDialog.js` (NEU): Zweistufiger Shadcn-Dialog ersetzt `window.confirm` + `window.prompt`. Stufe 1: Confirm mit User-Identifikation, Bullet-Liste der Konsequenzen, Warn-Banner. Stufe 2: Temp-PW in einem Code-Block mit prominentem Copy-Button (Clipboard API + execCommand-Fallback) und Erklärungstext. Data-testids für E2E: `reset-password-dialog`, `reset-password-cancel`, `reset-password-confirm`, `reset-password-value`, `reset-password-copy`, `reset-password-close`.
  - `components/admin/AdminUserRow.js`: `resetPw()`-Funktion entfernt, ersetzt durch `<ResetPasswordDialog>`-State (`resetDialogOpen`).
  - **E2E verifiziert (Playwright)**: Reset-Button klickbar → Confirm-Dialog erscheint → Bestätigen → Temp-PW (12 Zeichen, policy-konform `FEfx2@HS&342`) wird im Code-Block sichtbar → Copy-Button + Schliessen funktional.

- **Iter 381** (2026-02-06): Refactor — zentrale localStorage Cache-Utility
  - **Frontend** (`lib/cache.js` NEU): Single source of truth für alle `mf_*_cache` Keys via `CACHE_KEYS` Registry. Helpers `getCache(key, {ttlMs, userId})`, `setCache(key, value, {userId})`, `removeCache`, `clearAllUserCaches()` (Logout-Cleanup), `invalidateUserScoped(reason)` (Custom-Event-Hook für zukünftige Realtime-Pfade). `KEEP_ON_LOGOUT = ['mf_lang', 'mf_install_', 'mf_theme']`.
  - **Refactored Konsumenten**: `AuthContext.js` (Logout nutzt jetzt `clearAllUserCaches()` statt inline-KEEP-Liste), `LicenseBanner.js`, `NotificationBell.js` (Unread + Categories), `ChatUnreadContext.js`, `Sidebar.js` (Tasks/News-Reports-Counter + Permissions-Cache). `permissions.js` (komplexes Multi-Field-Schema) behält sein eigenes Layout — Key ist aber in der Registry, sodass der Logout-Cleanup ihn mitfegt.
  - **Bonus-Fix**: LicenseBanner pollte vorher auch auf `/login`, was den Logout-Cleanup direkt nach der Navigation wieder mit `mf_license_status_cache` befüllte. Jetzt mit `useAuth()`-Guard: nur loggedIn → Fetch + Cache-Write.
  - **Verifiziert**: 6/6 Backend-Pytest-Tests grün (Admin Reset Password Endpoint). E2E-Logout-Test: 8 `mf_*` Keys vor Logout → **0 Keys** nach Logout (vorher: 1 Leftover). Cache-Hydration nach Re-Login unverändert funktional (Sidebar-Module + Chat-Badge erscheinen ohne Aufblitzen).
- **Iter 380** (2026-02-06): Admin Reset Password — User-Test bestätigt
  - **Backend**: `POST /api/admin/users/{user_id}/reset-password` generiert policy-konformes Temp-PW, setzt `must_change_password=true`, blockiert für Non-Admins (403).
  - **Frontend** (`admin/AdminUserRow.js`): Reset-Button löst `window.confirm` → API-Call → `window.prompt` mit Temp-PW zur Übergabe an User. *Hinweis aus Review*: Browser-Native-Dialogs sind funktional aber nicht test-/UX-freundlich. Backlog-Punkt: ersetzen durch Shadcn-Dialog + Clipboard-API.

- **Iter 333** (2026-02-06): „Positionen aus Buchung neu laden"-Button für Aggregat-Rechnungen
  - **Backend** (`routes/resources/invoice_tracking.py`): Neuer Endpoint `POST /api/invoices/{id}/reload-lines-from-bookings`. Liest die `booking_ids` (single via `doc.booking_id`, aggregate via `snapshot.bookings[].booking_id`), ruft `aggregate_booking_invoice` mit diesen IDs erneut auf, berechnet Totals via `_compute_totals` und überschreibt `snapshot.lines/bookings/total/subtotal_net/total_tax/total_gross`. Nur für Draft-Status; `manual` ist explizit ausgeschlossen (keine Buchungs-Quelle). Schreibt einen History-Eintrag „edited" mit `extra.reloaded_booking_count`.
  - **Frontend** (`ManualInvoiceDialog.js`): Im Aggregat-Hinweis-Banner steckt jetzt ein **„Positionen neu laden"-Button** (RotateCcw-Icon). Confirm-Dialog warnt vor Verlust lokaler Anpassungen, Toast bestätigt die neue Anzahl. Lädt die neue Lines-Liste direkt in den Form-State, sodass die Buchhaltung sofort weiter editieren kann.
  - **Verifiziert via curl**: POST auf Aggregat-Draft mit 1 Buchung lieferte neue Lines (1 Brezel · 14 Stk · 1,80 €) + korrekt berechnete Totals (25,20 netto / 4,79 MwSt / 29,99 brutto). History-Endpoint zeigt den Eintrag mit `reloaded_booking_count: 1`. UI-Screenshot bestätigt sichtbaren Button + Banner.
- **Iter 332** (2026-02-06): 3 User-Reports — Banner-Cleanup, Filter-Buchungen mit Rechnung, Edit-Positionen
  - **#1 „Summe abrechenbar"-Karte entfernt**: Die oberste Status-Card mit Total + Export-Buttons wurde komplett entfernt. Export-Aktionen (Sammelrechnung-PDF, Nur-Catering-PDF/Speichern, DATEV-CSV, Generisch-CSV) sind nun im DropdownMenu „Weitere Aktionen" rechts oben in der Bookings-Tabelle gebündelt — auch sichtbar wenn keine Buchungen vorhanden sind.
  - **#2 Auswahl-Button kontextabhängig**: Bei 1 Buchung „**Rechnung aus Auswahl (1)**" statt verwirrendem „Sammelrechnung". Bei >1 weiterhin „Sammelrechnung aus Auswahl".
  - **#3a Buchungen mit Rechnung ausblenden**: Backend `aggregate_booking_invoice` filtert jetzt Buchungen aus, die in einer **nicht-stornierten** Rechnung enthalten sind (sowohl direkter `invoice.booking_id` für Single-Invoices als auch `snapshot.bookings[].booking_id` für Aggregate). Bei Storno → Rechnung wird zu „void" → Buchungen erscheinen wieder. Hinweis-Text in Empty-State erklärt das Verhalten.
  - **#3b Positionen editierbar für alle Rechnungs-Kinds**: PUT `/invoices/{id}` erlaubt jetzt `lines`-Editing für JEDE Draft-Rechnung (vorher nur `kind=manual`). Frontend `ManualInvoiceDialog` lädt Positionen aus `snapshot.lines` für alle Kinds vor; Aggregat-Hinweis ist jetzt nur noch ein dezenter Hinweis-Banner (nicht mehr blockierend). Buchhaltung kann eine Aggregat-Rechnung freigeben, nachbessern und wieder freigeben.
  - **Verifiziert**: curl-Test bestätigt Aggregat-PUT mit `lines` → total_gross neu berechnet ✅. UI-Screenshot: Summe-Karte weg, „Weitere Aktionen"-Dropdown sichtbar, Edit-Pencil bei allen 21 Entwürfen.
- **Iter 331** (2026-02-06): Chat-Counter-Sync + Toast-Position/Dedup + Bookings-Table-Filter
  - **#1 Sidebar-Chat-Counter mismatch**: Beide Backend-Endpoints (`/chat/conversations` und `/chat/unread-summary`) scannen jetzt 500 statt 100/200 Konversationen — Sidebar-Badge stimmt nun exakt mit der Summe der Conv-Listen-Badges überein. Curl-Verifiziert: total_unread=7, sum aller Conv-Badges=7 ✅
  - **#2 Toast-Position + Duplikat-Fix**: Sonner Toaster in `App.js` von `top-right` auf **`bottom-left`** umgezogen. Toast-Animation auf `slide-in-from-left-5`. Chat-Toasts haben jetzt eine stabile ID `chat-msg-{message_id}` (Fallback: `chat-conv-{conversation_id}`) → WebSocket-Reconnects oder doppelte `new-message`-Events ersetzen das Popup statt mehrfach zu rendern. Auch Gast-Notify dedup via `guest-notify-{guest_id}`.
  - **#3 Filter + Sort in Bookings-Table**: `BillingBookingsTable` hat jetzt: Such-Input (Titel/Ressource/KS), Ressourcen-Typ-Dropdown (Räume/Arbeitsplätze/Fahrzeuge), Kostenstellen-Dropdown (dynamisch aus Daten), klickbare Sort-Header (Datum/Titel/Betrag, asc/desc-Toggle), „Filter zurücksetzen"-Button. Badge zeigt `N / M Buchungen gefiltert`. Multi-Select-Header-Checkbox respektiert jetzt den Filter (wählt nur Sichtbare aus).
  - **Verifiziert**: Curl-Test (beide Endpoints geben 7 zurück), UI-Screenshot bestätigt Filter (33/34) + Sortier-Icons funktional.
- **Iter 330** (2026-02-06): Buchungen-mit-Positionen + Multi-Select-Sammelrechnung + PDF-Vorschau
  - **Backend** (`routes/resources/invoices.py`): `aggregate_booking_invoice` liefert nun per-Buchungs-`lines[]` (Katering + Fahrtkilometer pro Buchung) statt nur globaler Aggregation. Akzeptiert zusätzlich `booking_ids` (CSV) als Filter — Grundlage für Sammelrechnung aus expliziter Auswahl.
  - **Backend** (`routes/resources/invoice_tracking.py`): `POST /api/invoices` mit `kind=aggregate` akzeptiert jetzt `booking_ids: list[str]` — wird intern als CSV an `aggregate_booking_invoice` weitergereicht. Frontend kann damit eine Sammelrechnung aus ausgewählten Buchungen erzeugen.
  - **Backend** (`routes/resources/invoices_config.py`): Neuer Endpoint `POST /api/invoices/preview-pdf` — nimmt das gleiche `ManualInvoiceIn`-Payload wie `POST /invoices/manual`, rendert sofort ein PDF (mit Logo, Header, Footer, korrekte Totals) **ohne in der DB zu speichern**.
  - **Frontend** (`BillingBookingsTable.js` neu): Ersetzt die zwei alten Karten („Summe abrechenbar"-Lines + „Einzel-Buchungen mit Betrag") durch eine einheitliche Tabelle: Buchung klick → klappt Positionen auf; Header-Checkbox + Zeilen-Checkboxen → Multi-Select; Buttons pro Buchung: PDF + „Rechnung" (Einzelrechnung über `SaveInvoiceWithTemplateDialog` mit `kind=single`); globaler Button „Sammelrechnung aus Auswahl ({N}) · Σ".
  - **Frontend** (`SaveInvoiceWithTemplateDialog.js`): Neue Props `bookingId` (single) und `bookingIds` (Aggregat-Selektion) — sendet entsprechend `booking_id` oder `booking_ids` an `POST /invoices`. Dialog-Footer zeigt jetzt kontextabhängig „Buchung: X" / „N Buchungen ausgewählt" statt nur Kostenstelle+Zeitraum.
  - **Frontend** (`ManualInvoiceDialog.js`): Neuer Button **„PDF-Vorschau"** im Footer (sichtbar vor dem Speichern). Sendet die aktuellen Form-Daten an den neuen Preview-Endpoint und öffnet das gerenderte PDF in einem neuen Tab (Blob-URL). Buchhaltung sieht das finale Layout (Logo, Bank-Daten, Totals) bevor der Entwurf gespeichert wird.
  - **Verifiziert via curl**: aggregate-API liefert per-booking lines ✅, preview-pdf liefert 200+2.8KB PDF ✅, POST /invoices mit booking_ids erzeugt korrekt skalierte Sammelrechnung ✅. UI-Screenshot zeigt: klappbare Zeilen mit Positions-Tabelle, Multi-Select mit Live-Σ, Action-Buttons pro Buchung.
- **Iter 329** (2026-02-06): 2 PDF-Bugs in aggregaten Rechnungen behoben
  - **#1 Falsche Rechnungsnummer im PDF-Header**: `_render_invoice_pdf` übergab `doc.get("invoice_id")` ("inv_5e1bed0977") als `invoice_number`. Fix: `doc.get("invoice_number") or doc.get("invoice_id")` — zeigt jetzt die echte „KLS-2026-0002" / „RE-2026-0015". Bonus: `recipient_name/address`, `sender_org_unit`, `payment_terms`, `notes` werden jetzt aus dem Doc bevorzugt (mit Fallback auf Template-Defaults).
  - **#2 Gesamt-Spalte zeigt 0.00 EUR + Totals falsch ausgerichtet**: Aggregat-Lines speichern oft nur `quantity` + `unit_price` ohne `subtotal_gross` → der Manual-Renderer fand 0. Fix: `_render_invoice_pdf` berechnet jetzt pro Zeile `subtotal_net = qty * unit_price`, `subtotal_gross = net * (1 + tax/100)`, mappt `tax_rate_effective` aus `tax_rate`/default_tax. Totals werden aus den Line-Subtotals aggregiert. **Außerdem**: Die Totals-Tabelle (`Zwischensumme/MwSt/Gesamtsumme`) wurde neu strukturiert (fixe Spalten 102/40/28 mm + RIGHTPADDING=14 auf Value-Col) — EUR-Werte stehen jetzt pixelgenau (x=524.6pt) unter der Items-`Gesamt`-Spalte. Verifiziert via pdfplumber.
- **Iter 328** (2026-02-06): 3 User-Reports gefixed (Form-Reset, Approval-Klartext, Storno-Pflichtgrund)
  - **#1 ManualInvoiceDialog State-Leak**: useEffect fügt jetzt einen Form-Reset hinzu, wenn der Dialog ohne `editInvoice`/`prefill` geöffnet wird — verhindert, dass alte Empfänger/Positionen/Notizen vom vorherigen Aufruf erhalten bleiben. Auch der Catering-Picker wird auf `__pick__` zurückgesetzt.
  - **#2 Approval-Inbox ohne Klartext**: Pending-Cards in `ResourcesPage.js` zeigen jetzt `describeResource(b)` (Raum + Gebäude + Etage / Desk + Gebäude + Etage / Fahrzeug + Kennzeichen) und `describeBookingUser(b)` („Gebucht von …" bzw. „Gebucht für … von …"). Backend war bereits ab Iter 325 hydratisiert.
  - **#3 Storno mit Pflicht-Grund**: Backend `POST /invoices/{id}/void` akzeptiert jetzt `payload.reason` und validiert non-empty (400 sonst). Speichert `voided_by`, `voided_by_email`, `voided_by_name`, `voided_at`, `void_reason`. Frontend ersetzt das `window.confirm` durch einen vollwertigen Dialog mit Pflicht-Textarea. In der Tabellenzeile sichtbar: Storno-Datum, Wer, „Grund". Audit-Verlauf-Eintrag enthält den Grund als `extra.reason`.
  - **Verifiziert via curl**: void ohne reason → 400 „Stornogrund ist Pflicht."; void mit reason → 200 + voided_by_name/email/at + void_reason persistiert. Approval-API liefert 83 hydratisierte Pending-Items mit resource_name/user_name. UI-Screenshot bestätigt alle drei Anzeigen.
- **Iter 327** (2026-02-06): Audit-Verlauf für Rechnungen (buchhaltungs-konform)
  - **Backend** (`routes/resources/invoice_tracking.py` + `invoices_config.py`): Neue Collection `invoice_history` mit `{entry_id, invoice_id, ts, action, user_*, diff:[{field,label,before,after}], extra}`. Helpers: `_build_diff(before, updates)` (vergleicht $set-Patch mit DB), `_history_log(invoice_id, action, user, diff, extra)` (best-effort, blockiert nie). Eingehakt in: `POST /invoices` (aggregate/single/catering — "created"), `POST /invoices/manual` (manual — "created"), `PUT /invoices/{id}` (Edit — "edited"), `POST /invoices/{id}/approve` (Status-Diff), `POST /invoices/{id}/send-email`, `POST /invoices/{id}/send-stripe`, `POST /invoices/{id}/void`, `PUT /invoices/{id}/accounting`. Neuer Endpoint: `GET /invoices/{id}/history` (chronologisch desc, 500 Einträge max).
  - **Frontend** (`components/resources/InvoiceHistoryDialog.js` + `InvoicesTrackingPanel.js`): Clock-Icon-Button neben PDF in jeder Zeile öffnet einen Verlaufs-Dialog. Pro Eintrag: farbiges Action-Badge (Angelegt/Bearbeitet/Freigegeben/E-Mail/Stripe/Storniert), User-Name + Timestamp, und je Feld-Änderung ein Diff im Format `Label: ~~alt~~ → **neu**` (Tailwind line-through + emerald-700).
  - **Verifiziert via curl**: 3-Stufen-Lebenszyklus (created → edited → approved) liefert 3 chronologische History-Einträge mit korrekten Diffs (Status: draft→approved, Titel-Change, Initial-Snapshot).
- **Iter 326** (2026-02-06): 4 weitere Rechnungs-Modul-Fixes nach User-Test in Production
  - **#1 Entwurfsrechnungen editieren**: Neuer `PUT /api/invoices/{id}` (nur draft), Edit-Button (Pencil) in `InvoicesTrackingPanel`, `ManualInvoiceDialog` mit `editInvoice`-Prop. Manual = alle Felder + Positionen editierbar; Aggregat/Catering-Aggregat/Single = nur Titel/Empfänger/Vorlage/Zahlungsziel/Hinweise (Positionen sind Buchungs-Snapshot). Bei Template-Wechsel wird der Template-Snapshot in `invoice.snapshot.*` neu eingebrannt; bei manuell mit neuen Lines werden Totals serverseitig via `_compute_totals` neu berechnet.
  - **#2 PDF aus Liste zeigt Nullen**: `GET /api/invoices/{id}/pdf` erkennt jetzt `kind=="manual"` und routet auf `build_manual_invoice_pdf` (vorher: Aggregat-Adapter mit `snap.get("total")=0` → leere/Null-Werte). Frontend nutzt `openAuthedFile` (Blob, JWT) statt `window.open` — kein leerer Tab mehr. Liste zeigt `snapshot.total_gross ?? snapshot.total`.
  - **#3 Titel „Sammelrechnung" → „Rechnung_<Nummer>"**: Beim `POST /invoices` wird jetzt für jeden `kind` eine Rechnungsnummer aus dem (vorlagen-spezifischen) Nummernkreis allokiert. Default-Titel = `Rechnung_<Nummer>`. UI-Placeholder im Save-Dialog: „Leer lassen → automatisch „Rechnung_<Nummer>"". `defaultTitle`-Prop in `BillingPanel` auf `""` zurückgesetzt.
  - **#4 PDF Totals rechtsbündig**: `totals_table` in `build_manual_invoice_pdf` auf 3 Spalten umstrukturiert (Spacer / Label 72 mm / Wert 28 mm) mit `ALIGN RIGHT` auf beiden Wert-Spalten — Netto/MwSt/Brutto stehen jetzt vertikal exakt unter der „Gesamt"-Spalte der Positionen-Tabelle.
  - **Verifiziert via curl**: Aggregat-Create gibt `title="Rechnung_RE-2026-0013"`, Manual-PDF zeigt korrekt 50/9.50/59.50 €, PUT auf draft erfolgreich (title + lines geändert), PUT auf approved → 400 „Nur Entwürfe können bearbeitet werden". Smoke-Test im UI bestätigt Edit-Dialog + Rechtsbündigkeit visuell.
- **Iter 325** (2026-02-06): Klartext-Anzeige für Ressourcen + User in Buchungen (Dashboard-Widget + Tab „Meine Buchungen")
- **Iter 324** (2026-02-06): 7 User-priorisierte Bug-/UX-Fixes im Ressourcen-Modul (alle 7 mit Testing-Agent verifiziert, 100 % Pass)
  - **Issue 1 — Dialog-Titel** (`SaveInvoiceWithTemplateDialog.js`): Hardcoded „Sammelrechnung speichern" entfernt; Dialog liest nun `dialogTitle`-Prop oder fällt auf den passenden Trigger-Button-Text zurück („Als Rechnung speichern" / „Nur Catering speichern").
  - **Issue 2 — PDF „alle Kostenstellen"** (`admin/ResourceReportsPanel.js`): Drei `window.open()`-Calls (Aggregat-PDF + DATEV/Generisch-CSV) auf `openAuthedFile`/`downloadAuthedFile` umgestellt — neuer Tab bleibt nicht mehr wegen 401 leer. Schließt den noch offenen Teil der Iter-322-Audit-Liste.
  - **Issue 3 — Race-Condition Freigeben/Ablehnen** (`pages/ResourcesPage.js` + `components/resources/CateringInbox.js`): `decidingIds`/`transitioningIds` Sets + `disabled`-Flag schützen vor Doppel-POST. Schnelles Mehrfach-Klicken erzeugt nun nur noch eine API-Anfrage.
  - **Issue 4 — Catering in „Belegung" + Auto-Cancel** (`routes/resources/admin/analytics.py` + `OccupancyOverview.js`): `/resource-occupancy` liefert nun `catering_request_id` + `catering_status` + `catering_item_count` für eigene Buchungen (Privacy-Filter unverändert: bei fremden Buchungen werden Catering-Daten gestrippt). Frontend rendert ein `Utensils`-Icon im Booking-Bar. Cascade-Cancel war bereits in `bookings.py` vorhanden, neu verifiziert.
  - **Issue 5 — Zeitstrahl-Layout** (`OccupancyOverview.js`): Neue Option „1 Tag" im Days-Dropdown, Stunden-Ticks (0/6/12/18/24) im Header bei `days ≤ 3`, zusätzliche subtile Grid-Linien (alle 6 h) in den Bar-Rows. „Heute"-Button war bereits vorhanden.
  - **Issue 6 — Layout „Sehr-spaet-Gebuehr"** (`CateringCancelConfigPanel.js`): Bei `lg:grid-cols-5` brachen die langen deutschen Labels die Spalten. Fix: `min-w-0` auf Cells + `min-h-[2.2em]`/`leading-tight` auf Labels — sauberes 2-Zeilen-Wrapping.
  - **Issue 7c — Catering-Artikel im manuellen Rechnungs-Dialog** (`ManualInvoiceDialog.js`): Neuer Select-Picker im Positionen-Header lädt aktive `catering_items` und fügt bei Auswahl eine Zeile (Name/Einheit/Preis) hinzu. Picker resettet sich (kontrollierter `__pick__`-Placeholder), Mehrfachauswahl möglich. Bonus: `openPdf` nutzt jetzt `openAuthedFile` statt JWT-im-Query-String-Hack.
  - **Verifikation**: `test_reports/iteration_324.json` — 7/7 PASS (Frontend + Backend). Lint clean (Ruff + ESLint).
- **Iter 323**: DM Opt-In Policy — User entscheidet, wer ihn:sie im Chat anschreiben darf
  - **Backend** — Single Source of Truth in `services/dm_policy.py:may_dm(sender, recipient) -> (bool, reason)`. Vier Stufen:
    - `everyone` (Standard) — alle aktiven User mit Chat-Zugriff
    - `same_department` — nur Kolleg:innen mit identischem `users.department`-Feld
    - `managers_plus` — nur Moderator oder Admin als Absender
    - `nobody` — keine neuen DMs starten
  - **Admin-Override**: Admins können *immer* schreiben (User können sich nicht selbst gegen Leitung abschotten)
  - **Gruppen-Chats unbeeinflusst**: Existierende DMs + Gruppen-Aktivität laufen weiter
  - **3 Touchpoints integriert**:
    1. `GET/PUT /api/users/me/privacy` — User setzt `dm_policy` (enum-validiert, 400 bei Tippfehler)
    2. `POST /api/chat/conversations` — Gate vor Direktnachricht-Anlage, 403 mit deutschem Grund
    3. `GET /api/chat/users` — Antwort um `dm_blocked` + `dm_blocked_reason` angereichert (kein Leak von `role`/`dm_policy`)
  - **Frontend**:
    - **Profil → Privatsphäre**: 4-Wege-Dropdown mit Erklärtext + Live-Hilfetext pro Auswahl
    - **Chat-Picker**: Lock-Icon (rotbraun) + Tooltip + abgedimmter Style bei blockierten Usern
  - **Tests** (`test_iter323_dm_optin.py`, 6/6 grün):
    - Privacy-Endpoint Enum-Validierung · Nobody+Admin-Override · same_department-Matching · managers_plus-Rollencheck · Existing-DM-Bypass + Group-Bypass · /chat/users-Augmentation ohne Daten-Leak
- **Iter 322c**: Admin-UI für globale Catering-Vorlaufzeit (User-gewünschtes Follow-up)
  - **Backend** (`routes/resources/catering.py`): `DEFAULT_CANCEL_CFG` um `default_lead_time_min` erweitert. Bestehendes `GET/PUT /api/catering-config` liefert/akzeptiert das Feld jetzt mit Bounds-Check (0..20160 = 14 Tage). Persistiert in `catering_config`-Collection (statt vorher `app_settings`).
  - **Backend** (`routes/resources/bookings.py`): Lead-Time-Lookup im Booking-POST liest jetzt aus `catering_config.default_lead_time_min` (vorher `app_settings`). Per-Item-Override bleibt erhalten (Item-Lead > Global-Default).
  - **Frontend** (`CateringCancelConfigPanel.js`): 5. Eingabefeld "Standard-Vorlaufzeit (Min.)" + erklärender Hinweistext im Header ("Wird beim Buchen geprueft und loest bei Unterschreitung Warnung + E-Mail an die Cafeteria aus"). Sichtbar unter **Verwaltung → System → Ressourcen → Catering-Artikel** ohne Entwickler-Eingriff.
  - **Tests** (`test_iter322c_global_leadtime_admin.py`, 3/3 grün): GET enthält Feld · PUT validiert Bounds + Round-Trip · Global-Default-Fallback bei Item ohne explizite Lead-Time wird in der Booking-Logik korrekt angewandt.
- **Iter 322b**: Server-seitige Catering-Vorlaufzeit-Validierung + Cafeteria-Notification
  - **Backend** (`routes/resources/bookings.py`): Beim Anlegen einer Buchung mit Catering wird `max(item.lead_time_min)` aller gewählten Items mit `(delivery_at - now)` verglichen. Bei Unterschreitung:
    1. `catering_request` bekommt persistente Flags: `lead_time_breach`, `lead_time_required_min`, `lead_time_available_min`, `lead_time_worst_item`
    2. Antwort des `POST /resource-bookings` enthält `lead_time_warning`-Objekt für sofortiges UX-Feedback
    3. **E-Mail-Alarm**: Alle Catering-Team-Mitglieder (`catering.process`-Cap + Admins) bekommen automatisch eine HTML-E-Mail mit gelbem Warning-Banner ("Vorlaufzeit unterschritten — bitte prüfen"), Bestelldetails, Raum, Bereitstellungszeit, Bestelliste. Best-effort (Fail-Silent).
    4. Optional konfigurierbarer **globaler Default** via `app_settings.catering_default_lead_time_min` (sonst 60 Min.)
  - **Frontend** (`CateringInbox.js`): Neues gelbes **"⚠ Kurzfristig"-Badge** neben jedem Eintrag mit `lead_time_breach=true`. Tooltip zeigt: "X benötigt N Min., verfügbar M Min."
  - **Tests**: `test_iter322b_catering_leadtime.py` (2/2 grün):
    - Short-Notice (10 Min. bis Start, Item benötigt 120 Min.) → Breach flag + warning im Response + persistierte Felder
    - Well-Planned (7 Tage Vorlauf) → kein Breach
- **Iter 322**: Billing-Buttons + Template-Picker + Client-side Catering-Lead-Time-Warnung
  - **Bug-Fix Billing-Buttons** (`components/resources/BillingPanel.js`): "Sammelrechnung PDF", "Nur Catering PDF" und "DATEV-CSV"/"Generisch CSV" nutzten `window.open(URL)` → Request ohne JWT → 401, neuer Tab blieb leer. **Fix**: Neuer Helper `lib/authedDownload.js` mit `openAuthedFile(path, params)` lädt die Datei via authentifizierten `api`-Call als Blob und öffnet sie via `URL.createObjectURL` im neuen Tab. Auto-revoke nach 60 s.
  - **Feature: Template-Picker bei "Als Rechnung speichern"** (NEU `SaveInvoiceWithTemplateDialog.js`): Dialog mit Titel-Override + Vorlagen-Dropdown (zeigt "mit Logo" / "Standard"-Markierung). Default-Vorlage wird vorausgewählt. Backend (`routes/resources/invoice_tracking.py`): `POST /invoices` akzeptiert jetzt `template_id` und schreibt Logo, Header, Footer, Bank-Info, Payment-Terms als **Snapshot** auf die Rechnung. `_render_invoice_pdf` nutzt das templated `build_manual_invoice_pdf`-Layout, wenn Template-Daten im Snapshot sind — sonst das bisherige Plain-Layout.
  - **Feature: Catering-Vorlaufzeit-Warnung** (Thema 2, Option c — Default 60 Min. + pro-Artikel-Override): `lead_time_min` (existiert seit Iter 282 in DB & Admin-Editor) wird jetzt im BookingDialog gegen die Startzeit geprüft. Bei Unterschreitung: gelbes Warnungs-Banner im Catering-Bereich mit konkretem Hinweis ("X benötigt mindestens 45 Min. Vorlauf, Besprechung startet in 10 Min."). Non-blocking — User kann trotzdem buchen und mit Cafeteria abklären.
  - **Verifikation**: `test_iter322_billing_buttons.py` 4/4 grün (Auth-Enforcement-Repro + Templated-PDF-Größenvergleich), Frontend-Screenshots bestätigen alle 3 Buttons + Save-Dialog + Lead-Time-Warning.
- **Iter 321**: Rechnungs-Konfiguration · Logo-Upload-Bug + Catering→Rechnung E2E-Test
  - **Bug-Fix** (`components/admin/InvoiceConfigPanel.js`): Beim Anlegen einer NEUEN Vorlage war der Logo-"Hochladen"-Button via `disabled={!editing}` blockiert — User musste erst speichern, Dialog schließen, neu öffnen. **Fix**: Logo kann jetzt sofort gewählt werden, wird in `pendingLogo` + `pendingLogoUrl` zwischengespeichert, beim `save()` nach erfolgreichem POST automatisch hochgeladen. Sofort-Vorschau + Hinweistext.
  - **E2E-Test** (`tests/test_iter321_catering_invoice_e2e.py`, 2/2 grün): Validiert kompletten Catering→Rechnung-Flow: Vorlage + Logo → Catering-Buchung → Prefill → manuelle Rechnung mit Template → PDF (Logo + Header + Footer im Snapshot) → Listing. Plus Logo-CRUD-Roundtrip.
- **Iter 320**: 3 User-Requested Fixes
  - **Bug-Fix Chat-Real-Time**: Beim WS-`new-message`-Event für die aktive Konversation jetzt zusätzlicher 300 ms verzögerter `fetchMessages`-Aufruf (defense-in-depth gegen Timing-Race zwischen WS-Push und DB-Write). Zweites Safety-Net: neuer `useEffect` in `ChatPage.js` beobachtet die `conversations`-Liste und triggert `fetchMessages`, wenn die aktuelle Konversation eine `last_message.message_id` hat, die noch nicht im lokalen `messages`-Array vorhanden ist.
  - **Erweiterter Chat-Toast** (ChatUnreadContext.js): Größerer Popup (360 px Breite), 11×11 Avatar, pulsierender roter Dot, "NEUE CHAT-NACHRICHT"-Label, 3-zeilige Preview, animierter "Antworten →"-Button, 10 s Anzeigedauer. Stärkerer Schatten + Slide-in-Animation.
  - **Branding Crop-Dialog** (NEU `components/admin/BrandingCropDialog.js`, 174 Zeilen): Flexible Crop-Komponente via `react-easy-crop@5.5.7` mit konfigurierbaren `aspect`/`targetWidth`/`targetHeight`/`title`/`description`-Props. Zoom-Slider (1×–5×), Drag-to-Pan, Reset-Button, Output als JPEG-Blob (92 % Qualität).
  - **Integration in BrandingPanel** (Klinik-Hintergrund, 16:9 → 1920×1080) + **BrandingSettings** (Logo, 1:1 → 256×256). Beide haben jetzt: Upload→Crop-Dialog→Save, plus "Zuschneiden"-Icon-Button neben Upload-Button (sichtbar wenn Bild gesetzt). Vorschau-Container von `object-cover` auf `object-contain` umgestellt, damit das vollständige Bild sichtbar bleibt.
  - **Verifikation**: Testing-Agent berichtet 100 % Erfolg für alle 3 Features. ESLint clean (mit dokumentiertem `eslint-disable` für stabilen Callback in WS-useEffect).
- **Iter 319 / 319b**: Vollständige System-Tests + Load-Test (≥ 50 parallele User)
  - **Functional (via testing_agent_v3_fork)**: **46/46 Backend-Tests grün (100 %)** — Auth, Resources-CRUD, Bookings (Race-Safety, Conflict-Detection, Time-Validation), Catering, Master-Data (CC/Accounts), Floorplans, Analytics-Dashboards, Tasks, News, Chat, Surveys, Admin, Invoices, Favorites, Deprecated-Endpoints (410), Security (9× 401-Enforcement). **Frontend**: alle Module verifiziert (Login → Dashboard → Resources/169 Items, Tasks/197 Items mit Kanban, Chat, Admin, Mobile-Bottom-Nav bei 390×844).
  - **Load-Test (iter 319b, NEU `tests/test_iter319b_load.py`)**: 5 Szenarien, alle ≥ 50 parallele User, **alle grün**:
    - READ-STORM (50× GET /api/resources): p95=653 ms, 0 Errors
    - CREATE-STORM (50 verschiedene Slots): p95=381 ms, 50/50 success
    - RACE-STORM (50× POST gleicher Slot): exact 1 Winner + 49× HTTP 409 (deterministic-winner-selection via `_verify_booking_winner` validiert)
    - MIXED-WORKLOAD (50 User × 12 Endpoints parallel): p95=191 ms, 0 Errors
    - UPDATE-RACE (20× PUT gleiche Buchung): alle 20/20 succeeded, finaler State kohärent
  - **Performance-Erkenntnis**: Kubernetes-Ingress (Preview-URL) addiert ~3 s p95-Overhead. Backend selbst ist sehr schnell (p95<700 ms unter 50× Last). Production-Path direct localhost: p50=538 ms, p95=653 ms.
  - **Updated**: `tests/conftest.py` mit session-scoped Token (rate-limit-safe), `tests/test_iter319_comprehensive.py` (NEU, 46 Tests).
- **Iter 318b**: Refactoring — `routes/resources/admin.py` Split + Pytest-Suite Production-Ready
  - **Package-Split**: Der 1477-Zeilen-Monolith `routes/resources/admin.py` wurde in ein Package `routes/resources/admin/` mit 5 fokussierten Modulen aufgeteilt:
    - `__init__.py` (32 Zeilen) — kombiniert Sub-Router, exportiert `router`
    - `crud.py` (296 Zeilen) — Resource-CRUD, Calendar, Image-Upload, QR-Code, Maintenance-Dates, Floorplan-Position-Write, Desks-in-Room, Favoriten
    - `floorplans.py` (290 Zeilen) — Floorplan-CRUD, Floorplan-Items-Reader, Blackouts, Utilization-by-Sub
    - `master_data.py` (222 Zeilen) — Kostenstellen, Konten, Legacy-Migration (`_migrate_legacy_master_data`)
    - `analytics.py` (464 Zeilen) — Dashboard-Overview, Availability-Snapshot, Resource-Occupancy (Gantt), In-Office-Widget, No-Show-Analytics, By-Department, Driving-Log, Outlook-Stub, Upload-Config, deprecated Driver-License-Stubs
    - `demo_seed.py` (296 Zeilen) — POST /resources-seed-demo (idempotent)
  - **Backward-Compat**: `from routes.resources.admin import router` funktioniert unverändert; Importe in `routes/resources/__init__.py` wurden nicht angefasst. Alle 43 Endpoints sind im Package präsent, das Gesamt-Resources-Router hat weiterhin 120 Routes.
  - **Pytest-Suite**: Neue `tests/conftest.py` (~120 Zeilen) lädt `REACT_APP_BACKEND_URL` / `MONGO_URL` / `DB_NAME` automatisch aus den .env-Dateien beim Collect, prüft Backend-Reachability per TCP, skippt sauber wenn unerreichbar. Session-Fixtures `base_url`, `admin_credentials`, `admin_token` zur einfachen Test-Erstellung.
  - **2 Test-Files gefixt**: `raise ValueError` → `pytest.skip(allow_module_level=True)` in `test_iter258_profile_audit.py` + `load_iter258_profile.py`, sodass `pytest tests/` nicht mehr mit ImportError nach dem 1. File crasht.
  - **Stale-Test gefixt**: `test_iter234_refactor_smoke.py::test_driver_license_get` erwartet jetzt korrekt 410 (Endpoint deprecated seit Iter 292, Test war veraltet).
  - **Smoke-Test neu**: `tests/test_iter318_admin_split.py` validiert Package-Struktur, alle 5 Sub-Module + Auth-Regression-Guard (kein-Token = 401 auf den F841-bereinigten Endpoints).
  - **Verifikation**: 3097 Tests werden sauber gesammelt (vorher: Crash nach 1 File). Smoke-Suite (47 Tests aus admin_split + refactor_smoke + resources_module): **alle grün**.
- **Iter 318**: Code Quality Pass (P0 + Lint Cleanup)
  - **Backend Ruff** (50 → 25 errors, alle verbleibenden sind rein stilistische `E701/E702` "one-line if"):
    - **F841** (19×): Ungenutzte `user = await get_current_user(request)` Zuweisungen entfernt — `await get_current_user(request)` bleibt für Auth-Side-Effect (401-Enforcement verifiziert)
    - **F401** (19×): Ungenutzte Imports entfernt
    - **E741** (5×): Mehrdeutige `l`-Variablennamen umbenannt (→ `lbl`/`lic`/`log`/`line`/`lf`) in `exports.py`, `documents.py`, `resources/bookings.py`, `services/health_alerts.py`, `services/meeting_attendance.py`
  - **False-Positives im ursprünglichen "Code Quality Report"** dokumentiert:
    - "Circular Import `background_queue.py` ↔ `exports.py`" — **kein echtes Problem**: Beide Seiten nutzen Lazy-Imports innerhalb von Funktionen (Standard-Python-Pattern). Verifiziert: `python -c "import services.background_queue; import routes.exports"` läuft sauber.
    - "Hardcoded Secrets in `routes/resources/admin.py`" — **kein echtes Problem**: Es handelt sich um Demo-Seed-Daten (deutsche Meeting-Titel, Kennzeichen-Strings, random Mileage-Ranges), nicht um Credentials.
    - "31 undefined variables" — **kein echtes Problem**: `ruff --select F821` meldet 0 Treffer.
    - "React Hook Dependencies / Insecure localStorage" — **kein echtes Problem**: ESLint läuft sauber durch (`✅ No issues found`). JWT-Tokens in localStorage sind SPA-Standard und durch DOMPurify-XSS-Schutz abgesichert.
  - **Verifikation**: Backend-Restart erfolgreich, `GET /api/resources` (244), `GET /api/resource-bookings` (500), `GET /api/admin/users` (1000), Auth-401-Enforcement auf modifizierten Endpoints.
- **Iter 317**: Pull-to-Refresh auf den 3 meistgenutzten Listen
  - **Neuer Hook** `hooks/usePullToRefresh.js`: Pointer-Events-basiert (iOS + Android + Desktop kompatibel), Resistance-Curve (linear bis Threshold, 0.6× decay darüber), Maxpull 130 px, Threshold 70 px.
  - **Anti-Trigger-Schutz**: Aktiv nur bei `innerWidth < 768`, nur wenn der Scroll-Container am `scrollTop=0` ist, nur bei dominant vertikalen Gesten (>1.5× horizontale Komponente).
  - **Neue Komponente** `components/PullToRefreshIndicator.js`: Pfeil-Icon (rotiert bei Threshold) → Spinner während Refresh, Klartext-Hint („Ziehen zum Aktualisieren" / „Loslassen zum Aktualisieren" / „Aktualisiere…"). `md:hidden` versteckt es automatisch auf Desktop.
  - **Integration**: TasksPage, NewsPage, ChatPage (Konversationsliste).
  - **E2E-Verifikation auf 390 × 700 Viewport**: Indikator im DOM, Pull-Geste zeigt „Loslassen zum Aktualisieren" mid-pull, Release triggert `fetchTasks/Posts/Conversations`.
- **Iter 343 (2026-06-03)**: Sub-Raum-Klartext + Single-Source Bereichs-Auswahl + Sammelrechnung Multi-Select
  - **Issue 1 — Sub-Raum-Infos in Freigaben + Catering-Inbox**: Backend `GET /catering-requests` enriched die Booking-Sub-Info jetzt mit `resource_parent_id/name`, `resource_sub_id`. Frontend `CateringInbox.js` nutzt `describeResource()` für „Großer Saal — Bereich A · Gebäude X". Freigaben-Tab nutzt schon das gleiche enriched `/resource-bookings` Output (Iter 339).
  - **Issue 2 — Bereich-Auswahl nur noch in Kombi-Buchung**: `BookingTargetPicker` aus dem BookingDialog entfernt. `BookingComboSection.js` komplett überarbeitet → einziger Single-Source-of-Truth für Sub-Raum-Auswahl. Chips zeigen Verfügbarkeit (✅ frei / ⏳ pending / ⛔ belegt) direkt pro Bereich. Logik: 0 Sub-Räume ausgewählt → Parent gebucht; 1 ausgewählt → Single-Sub; ≥2 → Kombi-Buchung. `target` wird automatisch von `comboSubs` abgeleitet (useEffect in `useBookingDialog`).
  - **Issue 3 — Sammelrechnung Multi-Select**: Button „Alle als Sammelrechnung" umbenannt zu **„Sammelrechnung erstellen"** und Verhalten geändert: Klick selektiert ALLE Buchungen vor (Checkboxen), scrollt zur Tabelle. User kann dann einzeln ab-/auswählen und mit dem grünen „Sammelrechnung erstellen (N)"-Button erstellen.
  - **Test**: Catering-Requests-Endpoint liefert `resource_parent_name=TestSaal..., sub=B` für Sub-Raum-Buchungen ✓.

- **Iter 342 (2026-06-03)**: Verfügbarkeits-Konsistenz + Booking-Speed + CSV-Export
  - **Issue 1 — „Belegt bis HH:MM" widersprach Slot-Anzeige**: `GET /resource-bookings` filterte für nicht-privilegierte Nutzer fremde Buchungen raus, also zeigte der Slot-Picker frei während das Snapshot-Badge (das alle Buchungen sieht) belegt sagte. Neuer Query-Param `availability_only=true` liefert ALLE Buchungen auf der Ressource als **privacy-safe stubs** (title=„Belegt", user_id=None) für den Slot-Picker. Außerdem: Snapshot-Endpoint wird jetzt alle 60 s + bei Window-Focus nachgeladen.
  - **Issue 2 — Buchungs-POST war langsam**: 3 await-Aufrufe (`_audit_booking`, `_notify_catering_team`, `_send_short_notice_email`) blockierten die Response → in `asyncio.create_task` umgewandelt. **Ergebnis: 69 ms POST-Zeit** (vorher 200-500 ms).
  - **Issue 3 — CSV-Export aller User**: Neuer `GET /admin/users/export.csv` (Admin only). Spalten exakt wie der Bulk-Import: email, first_name, last_name, display_name, phone, department, role, group_ids. UTF-8 BOM → Excel öffnet korrekt. Legacy-`name` wird sinnvoll auf first/last gesplittet wenn first/last leer. AdminPage hat neuen „CSV-Export"-Button neben „CSV-Import".
  - **Test**: 2274 User exportiert, availability_only liefert 253 Buchungen ohne PII, Booking-POST 69ms ✓.

- **Iter 341 (2026-06-03)**: CSV-Bulk-Import für User
  - **Backend** `POST /admin/users/bulk-import`: nimmt `{rows: [...], send_email: bool}` mit voller Stammdaten-Erweiterung (email, first_name, last_name, display_name, phone, department, role, group_ids). Pre-loaded groups → `group_ids` werden sowohl als IDs als auch als **Klartext-Namen** akzeptiert (case-insensitive). Bulk-insert (1 DB-Roundtrip) + parallele Group-Membership-Updates + parallele Mail-Batches (10er Chunks). Per-Row-Result (created/skipped_existing/skipped_duplicate/invalid_email) + Summary.
  - **Frontend** `BulkUserImportDialog.js`: CSV-Paste oder File-Upload, Auto-Delimiter-Detection (, oder ;), Quoted-Value-Parsing inkl. doppelter Quotes. Vorlage-Download. Live-Vorschau mit per-Row-Validation (ungültige Email rosa markiert). Submit-Button zeigt Anzahl gültiger Zeilen. Ergebnisansicht mit Summary-Counters (Angelegt/Existieren/Ungültig/Mails OK) und Detail-Tabelle inkl. temporären Passwörtern.
  - **Integration**: AdminPage hat jetzt 3 Buttons in einer Reihe: „Mehrere einladen" (Legacy), **„CSV-Import"** (neu), „Einladen" (Single). React-Query Cache wird nach Import invalidiert (users + filters + stats).
  - **Test**: 4 Zeilen (2 valide mit group-by-id und group-by-name, 1 duplicate, 1 invalid) → Summary `{created:2, skipped_duplicate:1, invalid_email:1}`, group resolution korrekt ✓.

- **Iter 340 (2026-06-03)**: Stammdaten-Erweiterung + Einladung mit Gruppen/Abteilung
  - **1. Invite-Dialog**: `POST /admin/users/invite` nimmt jetzt `first_name`, `last_name`, `display_name`, `phone`, `department`, `group_ids` (Array — bw-compat mit altem `group_id`). Frontend zeigt im Dialog: Vorname, Nachname, Anzeigename, Telefon, Abteilung (datalist mit existierenden), Rolle, Multi-Select Gruppen (Chips mit X). Erfolgsansicht zeigt BenutzerID + Zugangsdaten kopieren.
  - **2. Stammdaten überall**: 
    * Model `UpdateProfileRequest` erweitert um first_name/last_name/display_name/phone/department.
    * `PUT /users/profile` und `PUT /admin/users/{id}` + `PUT /admin/users/{id}/profile` akzeptieren die neuen Felder; `name` wird automatisch aus `first_name + last_name` zusammengesetzt wenn leer (Backwards-Compat). `groups`-Field bei Admin-PUT synct die `groups.members`-Tabelle im Diff (add/remove).
    * `EditUserDialog` (Admin) komplett überarbeitet: BenutzerID read-only oben, Vor-/Nachname, Anzeigename, Telefon, Rolle, Abteilung, Standort, Beruf, Org-Einheit + Multi-Select Gruppen.
    * `ProfilePage` (Self): zusätzlicher Stammdaten-Block oben mit BenutzerID, Vor-/Nachname, Anzeigename, Telefon, Abteilung. Legacy-`Name`-Feld als Fallback bleibt.
    * `AdminUserRow`: Anzeige nutzt jetzt `display_name || (first+last) || name`; Telefon als Sub-Zeile.
    * `useProfileForm` Hook erweitert um neue Felder, Save sendet sie alle mit.
  - **Test (curl integration)**: Invite mit Marketing-Abteilung + Gruppe → user angelegt mit allen Feldern, group_members sync ✓. Self-Profile PUT first_name="Admin"+last_name="Boss" → `name` automatisch zu "Admin Boss" ✓.

- **Iter 339 (2026-06-03)**: 6 weitere Booking-/Billing-Fixes
  - **Issue 1 — Rechnungsnummer**: `InvoicesTrackingPanel.js` zeigt `invoice_number` (z.B. `RE-2026-0023`) prominent in Mono-Font statt der internen `invoice_id`. Fallback auf ID nur bei Altdaten ohne Nummer.
  - **Issue 2 — Calendar Sub-Raum-Klartext**: Backend `_enrich_bookings` liefert jetzt `resource_parent_id/name` + `resource_sub_id`. `describeResource()` baut daraus „Großer Saal — Bereich A · Gebäude IT · 2. Etage". `CalendarPage` zeigt das unter jedem Booking-Eintrag.
  - **Issue 3 — Verfügbarkeit in Ziel-Dropdown**: Neuer `targetAvailability`-State in `useBookingDialog`; parallel `check-conflicts` per Sub-Raum (debounced 750ms); `BookingTargetPicker` rendert „✅ frei" / „⏳ belegt HH:MM–HH:MM" (pending) / „⛔ belegt HH:MM–HH:MM" (confirmed) direkt in der Auswahl + farbig.
  - **Issue 4 — Rich Hover-Tooltip Belegung**: `OccupancyOverview.BookingBar` umgewickelt mit shadcn `Tooltip`. Inhalt: Titel, Zeit, Nutzer, Ressource, Status, Catering-Info, dezenter Drag&Drop-Hint. Backend `/resource-occupancy` liefert jetzt `user_name`.
  - **Issue 5 — Catering Menge überschreibbar**: `BookingCateringSection.js` qty-Input akzeptiert während Tippen rohe/leere Werte; klemmt erst onBlur auf ≥1. Vorher überschrieb `Math.max(1, Number(""))` jeden leeren Zustand sofort mit 1.
  - **Issue 6 — Aggregate Date-Filter**: `aggregate_booking_invoice` filtert jetzt `start_at >= from_date && start_at <= to_date` (statt `end_at <= to_date`); to_date wird auf Tagesende erweitert wenn date-only. Confirmed-Catering taucht jetzt auch in „Buchungen mit Positionen" auf wenn die Buchung am to_date endet.
  - **Tests**: testing-agent E2E PASS für alle 6 Punkte. Backend pytest `test_iter339_booking_billing_issues.py` 5/7 PASS (2 skipped wg. fehlender Sub-Räume in Test-Seed).

- **Iter 338 (2026-06-03)**: 6 Buchungs-bezogene Fixes
  - **Issue 1 — Endzeit-Eingabe**: Konflikt-Check inkl. `invalid_window`-Validierung jetzt komplett im 700 ms Debounce. User kann frei tippen ohne Sofort-Fehler.
  - **Issue 2 — Dialog-Performance**: Neue `bookingRefdataCache.js` (10 min TTL, sessionStorage) für catering-items/cost-centers/accounts/bookable-users. Backend: `_notify_approvers` bulk-insert + `asyncio.gather` + `fire_and_forget`; redundante Query in `_verify_booking_winner` entfernt.
  - **Issue 3 — Pending-Overlap**: Backend POST nimmt Flag `allow_pending_overlap`. Frontend Konflikt-Panel rendert bernsteinfarben mit „Trotzdem Buchung beantragen" Button wenn alle Konflikte pending sind. Override-Buchung → Status `pending_approval` + Approver-Notification.
  - **Issue 4 — Teilbare Räume**: Konflikt-Panel zeigt „Freie Bereiche / Alternativen" Chips für freie Sub-Räume → 1-Click `setTarget` Wechsel.
  - **Issue 5 — Button-Label**: „Rechnung aus Auswahl" → „Rechnung erstellen" / „Sammelrechnung erstellen (N)".
  - **Issue 6 — Auto-Refresh**: `BillingPanel.onSaved/onCreated` ruft `load()` → invoiced Buchungen verschwinden sofort.
  - **Tests**: backend pytest PASS, curl 200/409, testing-agent Code-Review PASS.

- **Iter 336 (2026-06-02)**: Realtime Tasks via WebSocket
  - **Backend** (`/app/backend/routes/tasks.py`): `_broadcast_task_event(event, task, actor_id, extra_uids)` Helper. POST/PUT/DELETE auf `/api/tasks*` fan-out `task-created` / `task-updated` / `task-deleted` Payload an alle Stakeholder (assignees + creator + ex-assignees) via existierende `chat_ws.send_to_user()` (Redis-pub/sub-fähig für Multi-Pod).
  - **Frontend**: `StatusContext` re-emittiert alle `task-*` WS-Frames als `window.dispatchEvent('meetflow:task-event', detail)`. So bleibt der globale Chat-WS Single-Source-of-Truth und keine zweite Verbindung wird geöffnet.
    * `TasksPage` listened auf das Event und patcht `setTasks` in-place — kein Reload für Status-Wechsel von Kollegen.
    * `DashboardPage` "Meine offenen Aufgaben"-Widget refresht analog.
    * `Sidebar`-Badge-Counter (`/tasks/pending-count`) refresht bei Realtime-Event.
  - **Echo-Suppression**: `actor_id === current_user.user_id` → Event ignoriert (eigene Änderungen sind schon optimistisch im UI).
  - **Test**: `/app/backend/tests/test_iter336_task_ws_broadcast.py` (zwei Users, WS-Connection, CRUD durch User A → User B empfängt alle 3 Events). PASS ✓.

- **Iter 335 (2026-06-02)**: Custom Recurring Bookings + Task Status UX + Backend Performance Pass (100-user Load Test)
  - **Serien-Buchung**: Neue Häufigkeiten `every_4_weeks`, `monthly`, `custom` (Multi-Date-Kalender über 2 Monate via `react-day-picker` mode=multiple). Backend (`bookings.py`) erzeugt Termine aus `custom_dates: ['YYYY-MM-DD',...]`-Liste; UI mit Chip-Badges + Entfernen-X.
  - **Task-Status-Update**: Status-/Priority-/Due-Date-Änderungen im `TaskDetailDialog` sind jetzt **optimistisch** — UI + Eltern-Liste (Board/Kanban) aktualisieren sofort beim Speichern, Server-Response rekonsiliert. Rollback bei Fehler. `fetchTasks` zusätzlich als Safety-Net beim Schließen.
  - **Performance-/Load-Test**: Neues Script `/app/backend/tests/load/load_iter335_100users.py` (100 Nutzer × 5 Runden × 15 Endpunkte = 7500 Calls). Report: `/app/test_reports/load_iter335_100users.json`.
  - **Performance-Fixes**: 
    * `uvloop` + `httptools` installiert + uvicorn auf `--loop uvloop --http httptools --limit-concurrency 1000 --backlog 2048` umgestellt.
    * Motor-Pool: `maxPoolSize=200, minPoolSize=10, maxIdleTimeMS=30000`.
    * `/calendar/events`: N+1-Bugfix (Batch-Fetch der eigenen Participant-Rows) **+ 30s TTL-Cache** per User. → p50 von ~1.5s auf **90ms**.
    * `/chat/unread-summary`: Aggregation rechnet Unread jetzt direkt in MongoDB via `$switch`/`$sum` (vorher: alle `created_at` per `$push` nach Python streamen + dort zählen).
  - **Ergebnis (intern, localhost:8001 — bypass des K8s-Ingress)**: 
    * Errors **0%** (vorher 18%), Throughput **151 RPS** (vorher 61), Overall p95 **2.3s** (vorher 7.2s).
    * Extern (Preview-URL) zeigt ~17 % Timeouts ab 30s — das ist **Ingress-Rate-Limiting / TLS-Throttling der Preview-Umgebung**, nicht das Backend. Production-Deployment hat dieses Limit nicht.

- **Iter 316**: Drei Mobile-Layout-Bugs gefixt (AdminUserRow, InvoiceConfigTabs, Vehicle-Editor)
- **Iter 315**: PWA-Install-Prompt — Schwelle 2 + Pro-Tag-Counter
- **Iter 314**: Mobile-Nav rechte-gefiltert
- **Iter 313**: „Mehr"-Sheet + Hamburger raus
- **Iter 312**: Mobile-Bottom-Nav
- **Iter 304**: Tasks — Verantwortliche-Anzeige
- **Iter 303**: Cleanup & Tests
- **Iter 302**: Refactorings
- **Iter 301**: Token-Version-Bump bei Rollenwechsel
- **Iter 299**: Foto-Lightbox + Fuhrpark-Stammblatt
  - Admin → Auswertungen → Führerscheine: Foto-Spalte zeigt jetzt klickbare Thumbnails (Vorder-/Rückseite); Klick öffnet Vollbild-Lightbox-Dialog mit dunklem Hintergrund
  - Resource-Editor (Fahrzeug bearbeiten) erweitert um **23 neue Fuhrpark-Felder**:
    - Identität: Erstzulassung, VIN, Hubraum, kW, Kilometerstand, Stellplatz
    - Prüfungen: TÜV nächste, AU nächste, nächster Service, letzter Ölwechsel
    - Reifen: Sommer/Winter vorhanden + Profil-Tiefe (mm), aktuell montiert (Sommer/Winter/Ganzjahres)
    - Versicherung: Police-Nr., Ablauf, Eigentum/Leasing + Leasinggesellschaft + Leasingende
    - Status: in_service / service_pending / out_of_service / sold
  - Backend Pydantic-Modell mit Validierung (Literals für ownership/current_tires/fleet_status)
- **Iter 298**: Duplikate aufgeräumt (Legacy Driver-License, CostCenterAccountsPanel)
- **Iter 297**: Stammdaten-Konsolidierung
- **Iter 296**: Live-Vorschau für Markdown/HTML
- **Iter 295**: Logo-Upload + Markdown/HTML-Editor
- **Iter 294**: Dashboard-Layout + Catering→Rechnung
- **Iter 293**: Configurable internal invoicing
- **Iter 292**: Object Storage + Führerschein-Modul
- **Iter 344**: Performance & Load Test Suite (smoke/load/stress/soak; Bericht unter `/app/test_reports/perf_iter344/REPORT.md`)
- **Iter 345**: P0 Performance-Optimierungen — TTL-Cache (news/feed 15s, cost-centers/accounts 30s), neue Compound-Indexe (bookings, invoice_master_data), uvicorn workers 4→8. Resultat: p95 −16 %, p99 −26 %, RPS +5.8 %. 26/26 Backend-Tests grün.
- **Iter 346**: Refactor — Booking-Conflict-Logic ausgelagert nach `services/booking_conflicts.py` (`check_conflicts`, `verify_booking_winner`, `validate_allowed_combination`). `_common.py` enthält nur noch Shim-Re-Exports. `_common.py` von 685 → 556 LoC. 15/15 Regressionstests grün, Verhalten identisch.
- **Iter 347**: Refactor — (a) Notifications nach `services/booking_notifications.py` ausgelagert (`notify_approvers`, `notify_catering_team`, `notify_catering_status`); (b) `bookings.py` (1117 LoC) in 5-Datei-Subpackage `bookings/` aufgeteilt: `_helpers` (95), `crud` (633), `approval` (122), `series` (190), `reporting` (134). `_common.py` von 556 → 419 LoC. Shim-Re-Exports unter den alten Namen — keine Call-Site angefasst. 72/72 Pytest + 27/27 E2E grün, Verhalten byte-identisch.
- **Iter 348**: Refactor — Catering-Pipeline (145 LoC) aus `crud.py::create_booking` nach `services/catering_request_factory.py` ausgelagert (`attach_catering_to_booking`, `_send_short_notice_email`). `crud.py` von 633 → 503 LoC (−21 %). `_helpers.py` entfernt (Inhalt nach Factory verschoben). + Neue Datei `/app/memory/ARCHITECTURE.md` mit vollständiger Modul-Übersicht für Onboarding. 14/14 E2E + 72/72 Pytest grün.
- **Iter 349**: Refactor — PDF/CSV/XLSX-Builder aus `_common.py` extrahiert nach `services/pdf_invoices.py` (`build_invoice_pdf`) + `services/csv_export.py` (`csv_line`, `build_xlsx`). `_common.py` von 420 → 305 LoC (−27 %). Shim-Re-Exports für `_csv_line` / `_build_invoice_pdf` / `_build_xlsx` — alle Call-Sites unverändert. 13/13 E2E + 72/72 Pytest grün.
- **Iter 350**: Bugfixes (2): (a) "Frei bis HH:MM"-Badge stimmte nicht mit dem Slot-Grid überein — Backend `availability_only=true` filtert jetzt explizit auf `status ∈ {confirmed, pending_approval}` (gleicher Filter wie `availability_snapshot`). Defensiv im Frontend (`QuickBookSlotPicker.js`) ebenfalls eingeschränkt. (b) `/api/resource-bookings/invoices/aggregate.pdf` 500-Fehler (TOCTOU `Depends`-Shift) behoben durch Auslagerung der Aggregator-Logik nach `services/booking_aggregator.py` — beide Endpoints (JSON + PDF) rufen jetzt denselben Service. `invoices.py` schlanker, kein Code mehr dupliziert. 16/16 E2E + 77/77 Pytest grün.
- **Iter 351**: Bugfix — Splitable Parent-Räume zeigten „frei" obwohl Sub-Räume voll gebucht waren. Snapshot + `availability_only=true` falten Children-Buchungen jetzt in den Parent-Eintrag ein (mit MAX(end_at) für korrekte `next_free`-Anzeige). Symmetrisch: Sub-Room-Queries inkludieren Parent-Buchungen. 14/14 E2E + 77/77 Pytest grün.
- **Iter 352**: DRY-Refactor — Resource-Hierarchy-Logik (Parent/Children-Expansion) aus 3 Call-Sites extrahiert nach `services/resource_hierarchy.py` mit `expand_blocking_ids(resource_id)` und `child_to_parent_map()`. `booking_conflicts.check_conflicts`, `availability_snapshot` und `availability_only`-List teilen jetzt eine Single Source of Truth — der Sub-Room-Bug aus Iter 351 kann nicht mehr an einer 4. Stelle wieder auftauchen. 26/26 E2E (12 neu + 14 Regression) + 77/77 Pytest grün.
- **Iter 353**: Mobile-Layout — Catering-Zeilen im BookingDialog stapeln jetzt auf Handy-Breiten (`< sm`) vertikal: Zeile 1 voll-breit Item-Dropdown, Zeile 2 Menge + Subtotal + Löschen mit `justify-between`. Desktop unverändert. Verifiziert mit Mobile-Screenshot (390×844).
- **Iter 354**: Touch-Stepper — Catering-Mengen-Eingabe mit `−` / `+` Buttons links/rechts des Inputs. Schnellere Bedienung auf Touch-Geräten, Tastatur-Eingabe weiterhin möglich. `−` deaktiviert sich bei Menge ≤ 1. Browser-Spin-Buttons via Tailwind ausgeblendet für saubere Optik.
- **Iter 355**: Touch-Targets in Resource-Karten — Stundenslots in `QuickBookSlotPicker` auf Mobile ≈32 px hoch (statt 20 px), „Buchen"-Button voll-breit + 40 px hoch, „Sofort buchen" CTA + „Andere Zeit …" Link mit größeren Padding/h-8. Apple HIG-konforme > 30 px Touch-Targets. Desktop-Layout unverändert via `sm:`-Breakpoints.
- **Iter 356**: Hybrid-Endpoint — neuer `GET /api/resource-availability?resource_ids=...` liefert Snapshot + Bookings für Slot-Picker in EINEM Request (statt 1 Snapshot + N Picker-Calls). Single Mongo-Query → Status-Drift physikalisch unmöglich. Legacy `/resource-availability-snapshot` als Backward-Compat-Alias erhalten. Frontend: ResourcesPage prefetcht alle Bookings auf einmal, QuickBookSlotPicker macht keinen eigenen Fetch mehr. **2 statt 165 Calls** auf der Resource-Seite. 42/42 E2E + 77/77 Pytest grün.
- **Iter 357**: Mobile-UX-Polish — Tasks-Toolbar (Search voll-breit, „Nur meine"+„Filter" mit `flex-1` in 2. Zeile, Touch-Höhe h-10). News-Filter-Pills mit `snap-x` für Touch-Scroll, py-1.5 statt py-1 für bessere Tap-Targets.
- **Iter 358**: Pull-to-Refresh auf der ResourcesPage ergänzt (gleicher `usePullToRefresh`-Hook + `PullToRefreshIndicator` wie News/Tasks/Chat). Refresh lädt sowohl die Resource-Liste als auch das Hybrid-Snapshot neu. Mobile-only via `md:hidden`.
- **Iter 360** (2026-02): Mobile-Layout für Tab „Rechnungen" — `BillingBookingsTable.js` und `InvoicesTrackingPanel.js` rendern auf `< md` jetzt einen **Card-Stack** statt der klassischen Tabelle (kein horizontales Scrollen mehr). Jede Karte zeigt Datum + Betrag in derselben Zeile, Titel/Ressource/Kostenstelle darunter, Aktionen (PDF + Rechnung erstellen / Bearbeiten / Freigeben / Stornieren) als voll-breite Touch-Buttons. Aufklappen pro Karte zeigt Einzel-Positionen (Catering / Fahrtkilometer). Auf `≥ md` unverändert klassische Tabelle. Lint ✅ + Desktop-/Mobile-Screenshots verifiziert.
- **Iter 361** (2026-02): Bugfix — PDF öffnete sich auf Handy nicht. Ursache: `window.open()` nach `await api.get()` verliert die User-Gesture und wird von iOS Safari / Android Chrome blockiert. Fix in `lib/authedDownload.js`: Mobile (`pointer: coarse`) löst jetzt einen erzwungenen Download via `<a download>` aus (öffnet Share-Sheet / Quick-Look auf iOS, Download-Manager auf Android). Desktop unverändert (Sync-Tab + Blob-URL-Navigation). Dateiname aus `Content-Disposition` extrahiert; Fehler-Blob-Body wird als JSON geparst, um `detail`-Toasts zu erhalten. Mobile-Download verifiziert (2560-Byte echtes PDF, korrekter Dateiname `invoice_bk_...pdf`).
- **Iter 362** (2026-02): In-App-PDF-Viewer für Mobile — statt OS-Download öffnen Rechnungs-PDFs auf Handys jetzt einen Vollbild-Viewer (`react-pdf` + lokal gehostetes pdfjs-worker `pdf.worker.min.mjs`, ~1 MB lazy-loaded). Features: Page-Navigation (←/→), Zoom −/+ (50–200 %), Speichern-Button, ESC-Schließen, Body-Scroll-Lock. Komponenten: `PdfViewerDialog.js` + `PdfViewerHost.js` (Listener auf `mf:open-pdf` CustomEvent, einmal in `App.js` gemountet). `lib/authedDownload.js` dispatcht das Event auf Mobile + PDF-MIME; CSV/XLSX laden weiterhin als Download. Desktop unverändert (Inline-Tab). React.lazy → Viewer-Chunk landet nicht im Initial-Bundle. End-to-End auf Mobile-Viewport getestet: Page-Render, Zoom 75/100/125 %, Speichern (Download `invoice_bk_eb69bf725f1b.pdf`), Schließen, sowie Invoice-Tracking-PDF — alle ✓.
- **Iter 363** (2026-02): 2 Bugfixes aus User-Report. (a) **„Eine Buchung auswählen → alle verschwinden"**: `BillingPanel.js` reichte `bookingId` / `bookingIds` NICHT an `SaveInvoiceWithTemplateDialog` weiter → POST `/invoices` kam ohne `booking_ids` raus → Backend erstellte „Sammelrechnung über gesamten Zeitraum" und excludierte ALLE Buchungen. Fix: Props explizit durchgereicht. Reproduziert und verifiziert via Playwright (5 → 4 Buchungen nach Single-Select-Invoice, POST-Body enthält jetzt `"booking_ids":["bk_..."]`). (b) **PDF-Dateiname zeigte interne ID**: `invoice_tracking.py` und `invoices_config.py` Content-Disposition nutzten `invoice_id` (`inv_8215dfec9d.pdf`) statt der Rechnungsnummer. Fix: Format jetzt `Rechnung_<invoice_number>.pdf` (z. B. `Rechnung_KLS-2026-0006.pdf`). Verifiziert via curl + In-App-PDF-Viewer-Topbar.
- **Iter 364** (2026-02): Undo-Funktion nach Rechnung-Erstellung — Toast zeigt 10 s lang den Button „Rückgängig" (Sonner `action`-API). Klick storniert den Entwurf direkt via `POST /invoices/{id}/void` mit Grund „Versehentlich erstellt — vom User rückgängig gemacht" und lädt das Aggregat neu, sodass die Buchung sofort wieder erscheint. Verifiziert E2E: 5 → 4 → 5 Buchungen, Storno-Reason im Audit-Verlauf.
- **Iter 365** (2026-02): Pro-Teilbereich-Status auf Resource-Karte — bei `is_splitable=true` zeigt die Karte jetzt für JEDEN Sub-Bereich eine farbcodierte Zeile mit Reservierungs-Zeitfenster: ● `Bereich A: belegt 07:37–08:37` (rot, aktuell laufend) / ● `Bereich B: reserviert 13:00–14:00` (amber, zukünftig) / ● `Bereich C: frei` (grün). Datenquelle: bestehender Hybrid-Endpoint `/api/resource-availability` (snapshot + bookings_by_resource pro Kind). Namen aus „Saal — Bereich A" → „Bereich A" gekürzt. Verifiziert visuell auf Mobile-Viewport (alle 3 States gleichzeitig sichtbar).
- **Iter 366** (2026-02): 7-Punkte-Paket aus User-Anforderung.
  1. **Personalnummer Stammdaten** — neues Feld `personnel_number` in User-Schema, im `EditUserDialog` (unter Org.-Einheit) editierbar, in der Admin-Search durchsuchbar.
  2. **Outline-Button „Sammelrechnung erstellen" entfernt** — der grüne Button benennt sich kontextabhängig (1 Selektion: „Rechnung erstellen", >1: „Sammelrechnung erstellen (N) · €").
  3. **Cost-Center-Propagation** — beim Erstellen einer Rechnung (Single & Sammel mit `booking_ids`) wird die KS aus der/den Buchung(en) übernommen, wenn alle ausgewählten Buchungen dieselbe KS haben. Zusätzlich: `single_booking_invoice`-Import-Bug (500) auf `booking_invoice` gefixt.
  4. **Catering-Freigabe-Gating** — Backend gibt 409 zurück, wenn der Raum freigabepflichtig ist und die Buchung noch nicht `confirmed`. Frontend zeigt amber Banner „Buchung freigabepflichtig — Catering kann erst nach Buchungs-Freigabe bestätigt werden" + deaktivierten Button mit Tooltip.
  5. **Booking-Storno-Kaskade** — beim Storno einer Buchung wird das verknüpfte Catering automatisch storniert mit Grund „Buchung wurde storniert: <Titel> — Grund: <Reason>", inkl. korrekt berechneter Stornogebühr-Stufe.
  6. **Catering-Storno-Notification** — `_notify_catering_status('cancelled')` pushed Notification an Buchungs-Owner mit Titel „Catering storniert" + Stornogrund (war im Helper schon implementiert, wird jetzt nach Kaskade aufgerufen).
  7. **Zeitraum-Spalte „Meine Buchungen"** — neue `renderBookingRange()`-Helper rendert 2-zeilig: Datum oben, `HH:MM–HH:MM` darunter (gleicher Tag) bzw. „Start → Ende" (mehrtägig). `whitespace-nowrap` verhindert Umbruch am Trennstrich.

  Verifiziert via curl + Playwright-Screenshots, alle 7 Punkte ✓.
- **Iter 367** (2026-02): Erweiterung Punkt 4 — beim **Genehmigen der Buchung** wird das verknüpfte Catering automatisch in den „bereit zur Bestätigung"-Zustand überführt: `booking_approved_at`-Marker auf dem Catering-Doc + Push-Notification an alle User mit `catering.process`-Cap ("Catering kann jetzt bestätigt werden · <Titel> freigegeben · <Raum> · <Datum>"). UI: amber Sperr-Banner verschwindet, grünes Banner „Buchung freigegeben — Catering kann jetzt bestätigt werden" erscheint, Bestätigen-Button wird aktiv. Backend-Helper `notify_catering_team_booking_approved` parallelisiert Push + DB-Notification mit identischem Schema wie `notify_catering_team`. Verifiziert E2E mit Buchung anlegen → vor Approve amber → approve → nach Approve grün ✓.
- **Iter 368** (2026-02): Reject-Path Cascade — wenn eine freigabepflichtige Buchung **abgelehnt** wird (`decision=reject`), wird das verknüpfte Catering ebenfalls automatisch storniert (genau wie beim normalen Storno aus Iter 366). Cascade-Logik in `services.booking_notifications.cancel_catering_for_booking()` extrahiert, wird jetzt von beiden Pfaden (Storno + Reject) gemeinsam genutzt — DRY. Stornogrund unterscheidet die Pfade: „Buchung wurde storniert: …" vs. „Buchung wurde abgelehnt: …". Notification an Buchungs-Owner mit korrektem Body. Regression-Test: Storno-Pfad funktioniert weiterhin ✓.
- **Iter 369** (2026-02): Lizenz-System für On-Prem-Auslieferung. (a) `services/license.py` — Heartbeat-Loop alle 6 h gegen `LICENSE_SERVER_URL/verify`, SHA256-Hardware-Fingerprint aus (Hostname, MAC, License-Key), 24 h Offline-Grace, Status persistiert in `app_settings.license`. (b) `routes/admin/license.py` — `GET /api/license/status` (public, für Banner), `POST /api/admin/license/recheck` (admin.manage_integrations). (c) `LicenseGuardMiddleware` blockt alle `/api/*` mit 503 wenn Status=invalid; Bypass für `/api/auth/*`, `/api/license/*`, `/api/admin/license/*`, `/api/health`. (d) Frontend `LicenseBanner` pollt 5 min, zeigt roten (invalid) / amber (grace) Top-Banner. Dev-Modus: `LICENSE_SERVER_URL` leer → `status: disabled`, kein Banner, kein Blocking. Doku unter `/app/memory/LICENSE_SETUP.md`. Verifiziert E2E: 7 Szenarien (Dev, Login-Bypass, 503-Blocking, Recheck-Reset, Banner sichtbar/versteckt) ✓.
- **Iter 370** (2026-02): Mini-Lizenz-Server unter `/app/license_server/` als eigenständiges Projekt (FastAPI + SQLite, single file). Features: Hardware-Fingerprint-Bindung, Auto-generierte Keys `MEETFLOW-XXXX-XXXX-XXXX-XXXX`, eingebautes single-page Admin-UI, vollständiges Audit-Log mit IP-Capture, 11 E2E-Szenarien getestet ✓.
- **Iter 371** (2026-02): Admin-UI Polish + Deployment-Guide. Stats-Dashboard (Aktiv/Läuft bald ab/Abgelaufen/Gesperrt), Live-Suchfeld, Auto-Refresh 30 s, Token in localStorage, Toast-Notifications, Copy-to-Clipboard. Audit-Log als Modal mit IP/Domain/Version/Message-Spalten, Live-Filter, CSV-Export. Deployment-Guide `DEPLOY.md` mit 3 Varianten (Lokal/Hetzner CX22+Caddy/AWS) inkl. tägliches Backup-Cron. Verifiziert mit Demo-Lizenzen + Verify-Versuchen — Audit zeigt fingerprint mismatch ✓.
- **Iter 375** (2026-02): **Bugfix — Eingehender Video-Anruf-Popup**. User-Report: Chat-Anrufe zeigten nur den „Jetzt beitreten"-Button im Chat-Stream, das `IncomingCallModal` (Vollbild-Klingel-UI) kam nicht in den Vordergrund. Drei-Punkte-Fix: (a) `IncomingCallModal` rendert jetzt via `createPortal(overlay, document.body)` — entkommt damit jedem Stacking-Context der Provider-Hierarchie. (b) z-index `z-[90]` → `z-[200]`, damit das Modal über Toasts (z-[100]), SessionExpiryBanner, ConsentDialog usw. liegt. (c) Redundanter Liefer-Kanal: `StatusContext.js` re-dispatcht eingehende `incoming-call`/`call-cancelled`/`call-ended` WS-Events als window-Event `meetflow:call-event`; `IncomingCallModal` hört zusätzlich zum eigenen WS-Listener auf dieses Window-Event. Selbst wenn der eigene WS gerade mid-reconnect ist, feuert das Modal zuverlässig. Testing-Agent 10/10 Tests grün (Modal erscheint auf /dashboard, /meetings, /chat; Annehmen/Ablehnen funktionieren).
- **Iter 376** (2026-02): **Demo-Daten-Wipe erfasst jetzt auch System-Demo-User**. User-Report: „alle demo user entfernen und auch alle demo daten die durch system angelegt werden sollten über Demo-Daten entfernen entfernt werden". Umsetzung: (a) `seed_demo_resources` legt jetzt zusätzlich 5 Demo-User mit Email-Domain `@demo.meetflow.local` an (Anna, Markus, Lisa, Tobias, Sandra — Rollen mixed member/moderator, alle `email_verified=True`, gemeinsames Passwort `demo_password_2026`). Beispiel-Buchungen werden den Demo-Usern zugeordnet statt dem aufrufenden Admin (realistischer Datensatz). (b) `/admin/demo-data/preview` + `/admin/demo-data/wipe` matchen jetzt zusätzlich diese spezifische Email-Domain und kaskadieren beim Löschen: bookings, tasks, messages, notifications, conversation-memberships, push_subscriptions, focus_times, login_attempts, user_busy_slots, notification_prefs, password_reset_tokens, email_verification_tokens, user_keys, user_favorites, auth_refresh_log, meeting_participants. (c) Sicherheit: ausschließlich `@demo.meetflow.local` wird gematcht — QA-Tester (`qa_admin@meetflow.com` etc.) und alle echten User bleiben unangetastet. (d) Frontend-UI zeigt eigene Zeile für Demo-User-Counter inkl. ihrer kaskadierten Daten. E2E-curl-Test: Seed → 5 User + 99 Buchungen → Preview zeigt 180 Objekte → Wipe löscht 174 → Post-Wipe-Preview = 0 → QA-User unverändert ✓.
- **Iter 377** (2026-02): **Bugfix — „Abmelden funktioniert nicht" (nur Production)**. User-Report (Edge auf Laptop, Admin-Account): Klick auf „Abmelden" lädt die Seite neu, der User bleibt aber eingeloggt. **Root Cause:** Der Service Worker `sw-push.js` cachte `/api/auth/me` mit stale-while-revalidate. Nach dem Logout (Cookies cleared) lieferte der SW beim Page-Reload die ALTE 200-Antwort mit User-Daten aus dem Cache → React-State zeigte den User weiterhin als eingeloggt. Auf Preview trat der Bug nicht auf, weil dort der SW zu oft frisch registriert wird, um das stale `/auth/me`-Snapshot anzusammeln. **Fix:** (a) `/api/auth/me` aus `API_CACHE_PATHS` entfernt — Auth-State darf NIE aus dem Cache kommen. (b) Cache-Versionen gebumpt (`meetflow-shell-v6`, `meetflow-api-v3`) damit alte Caches beim nächsten SW-`activate` automatisch gelöscht werden. (c) Neuer SW-Message-Handler `clear-api-cache`; `logoutFn` in `AuthContext.js` sendet diese Message direkt nach POST `/auth/logout` UND ruft als Defense-in-depth `caches.keys()` + `caches.delete(k)` auf jeden vorhandenen Cache. E2E-verifiziert: Pre-Logout `/auth/me`=200 → Klick Abmelden → Cookies weg → URL=/login → Post-Logout `/auth/me`=401 ✓.
- **Iter 378** (2026-02): **Bugfix — Modul-Flimmern in der Sidebar + komplette Cache-Hydration UX-Layer**. User-Report: „wenn man über Benutzer gruppen weniger in der Menü leiste module ausgewählt hat … wenn man dann auf die module klickt sieht man für einen Bruchteil alle module und dann nicht mehr". **Root Cause:** `Sidebar.js` `hasPerm()` gab `true` zurück, solange Permissions noch nicht geladen waren → ALLE 10 Module rendern, dann filtern → Flicker. **Fix:** (a) `hasPerm()` invertiert: `permissions === null` → AUSGEBLENDET. (b) localStorage-Cache `mf_user_perms_cache` (user_id-keyed) hydratet synchron beim Mount. (c) Logout-Sweep räumt Cache automatisch auf. **Erweitert auf 7 weitere Komponenten:** (d) `PermissionsProvider` cached in `mf_perms_provider_cache` → `RoleDowngradeBanner` sofort korrekt. (e) `LicenseBanner` cached in `mf_license_status_cache` (1h TTL) → `invalid`/`grace` Banner erscheint sofort bei Reload. (f) `ChatUnreadProvider` cached in `mf_chat_unread_cache` (10min TTL) → Sidebar-Chat-Badge erscheint ab erstem Render. (g) `OnboardingTour` skippt Setup-Logik synchron via localStorage-Flag — kein 1.5s-Delay-Flash mehr. (h) Sidebar Tasks-Pending-Counter (`mf_tasks_pending_cache`) und News-Reports-Pending-Counter (`mf_news_reports_pending_cache`) per `useState(() => loadCachedCounter(...))`. (i) NotificationBell unread-count + categories per TanStack-Query `initialData: loadNotifCache(...)` (`mf_notif_unread_cache`, `mf_notif_categories_cache`). E2E-verifiziert: Hard-Reload zeigt konstant „Chat 5", „Verwaltung 14" ab erstem Sample. Kein „0 → N"-Wackeln mehr im UI.
- **Iter 379** (2026-02): **Bugfix Sweep + Password-Policy + No-Email-User-Konten + Lokalisierungs-Sweep + Mitarbeiter-Standard-Sync + Letzter-PW-Wechsel-Spalte**. Mehrere User-Reports und Compliance-Features in einer Iteration. **Bugfixes:** Chat-„+"-Button-Overlap auf iPhone 17 → `pr-28`; Module-Gruppen-Badges (`Modul: Standard`) als nicht entfernbare Chips → gefiltert via `module_group: true`; Rollen englisch → `lib/roleLabel.js` Mapping. **Mobile-Sweep:** `/app/scripts/mobile_layout_sweep.py`, 6/6 Seiten clean. **Password-Policy:** `services/password_policy.py` (8 Zeichen + 4-aus-4, Historie letzte 3, Rotation 0..36 Monate konfigurierbar), `ChangePasswordDialog` mit Live-Indikatoren, `MustChangePasswordBanner`, Admin → Richtlinien-Tab → Rotation-Input, Legacy-User-Schutz vor Mass-Lockout. **Mitarbeiter-Standard-Sync:** `member` Role-Defaults bekommen `tasks.view_department` + `resources.book_for_others`. **Letzter-PW-Wechsel-Spalte:** AdminUserRow zeigt relatives Datum (rot ⚠ wenn >180 Tage); AdminPage Sort-Dropdown mit „PW-Wechsel: aelteste/neueste zuerst" für Compliance-Audits. **No-Email-User-Konten:** Admin kann Mitarbeitende ohne dienstliche E-Mail anlegen (Pflege, Reinigung etc.). **Implementation:** (a) InviteUserDialog Toggle „Kein E-Mail-Konto" → email-Field deaktiviert, `initial_password`-Field eingeblendet (Policy-validiert), Personalnummer + alle Stammdaten weiter Pflicht. (b) Backend `/admin/users/invite` mit Flag `no_email: True` generiert synthetische `<personnel_number>@no-email.local` und setzt `email_verified=True`, `no_email_account=True`, `must_change_password=True`. (c) `/auth/login` akzeptiert E-Mail ODER Personalnummer (case-insensitive Regex-Lookup). (d) LoginPage Input von `type="email"` → `type="text"` mit `inputMode="email"`, Label „E-Mail oder Personalnummer", Placeholder „name@firma.de oder P-12345". (e) Forgot-Password ist für `no_email_account` blockiert (Wiederherstellung nur via Admin). (f) Neuer Endpoint `POST /admin/users/{user_id}/reset-password` setzt Passwort zurück, bumpt `token_version` → invalidiert alle Sessions, gibt neues PW als Response zurück. E2E-verifiziert: Admin invitiert no_email-User → Login per `PN1780694553` + `StartPw1!` erfolgreich, `must_change_password: true` korrekt gesetzt.

## Pending / Backlog (siehe ROADMAP.md)
- **P1**: Outlook/Microsoft 365 OAuth + bidirektionale Kalender-Sync (aktuell 503-Stub)
- **P2**: Production-Deployment Cache-Issues (User muss redeployen)

## Test Credentials
Siehe `/app/memory/test_credentials.md`
