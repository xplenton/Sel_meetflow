# MeetFlow — Roadmap

> Prioritized backlog. P0=blocker, P1=high, P2=medium, P3=nice-to-have.
> For shipped items see [`CHANGELOG.md`](./CHANGELOG.md).
> For module overview see [`PRD.md`](./PRD.md).

## P1 — High Priority
- **Outlook / Microsoft 365 OAuth & bidirektionale Calendar-Sync**
  - Aktuell: `/api/resources/outlook/oauth` Stub-Endpoint → 503
  - Benötigt: Authorization-Code-Flow, Token-Refresh-Logik, EWS/Graph-Sync für Bookings ↔ Outlook-Kalender
  - Spec: bidirektional, Konflikte 2-Wege-Merge
- **Billing / Rechnungen-Integration für Ressourcen-Management** (originale PRD-Anforderung, vom User explizit als nächste Priorität bestätigt am 28. Feb 2026)
  - ✅ DONE (Iter 284): Booking-Level-Aggregat-Endpoint + UI-Tab "Rechnungen" in Ressourcen mit Filter, Summe-Card, 4 Export-Buttons (Sammelrechnung PDF, Nur Catering PDF, DATEV-CSV, Generisch CSV), Einzel-Buchungs-Tabelle mit Direkt-PDF
  - Cost-Center + Account-Felder existieren bereits auf Bookings
  - **Verbleibend (Backlog)**:
    - ✅ DONE (Iter 285): Auto-E-Mail-Versand der Rechnung an Buchhaltung/Cost-Center-Empfänger
    - ✅ DONE (Iter 285): Status-Übersicht "Erstellte Rechnungen" mit Workflow (Entwurf/Freigegeben/Versendet/Bezahlt/Storniert)
    - ✅ DONE (Iter 285): Stripe-Invoicing für externe Buchungen (mit Webhook für invoice.paid)

## P2 — Medium Priority
- *(no items currently — alle Race-Schutz + Queue-Migrationen sind durch)*

## P3 — Nice-to-Have
- *(no items currently — alle P3-Roadmap-Items abgeschlossen)*
- **Replica-Set MongoDB** **DONE iter 261** (Single-Node rs0 aktiv, `/api/admin/health/mongo` zeigt Status, `/app/docs/MONGO_REPLICA_SET.md` für Multi-Node-Migration)
- **Quick-Book für Fahrzeuge** **DONE iter 261** (km-Stand + Ziel inline in QuickBookSlotPicker)

## Refactoring / Tech-Debt
- Lint cleanup: noch ~430 stylistische ruff-Warnings (E712/E722/E402/E701/E741/F841) — keine Bug-Risiken, nur Style
- `bookings.py` Refactoring **DONE iter 260** (1257 → 728 Zeilen; `office_days.py` neu ausgelagert)
- `BookingDialog.js` Refactoring **DONE iter 260** (658 → 589 Zeilen; CateringSection + SeriesSection ausgelagert)
- `admin.py` Refactoring **DONE iter 261** (1855 Z. → routes/admin/ Package mit users.py + permissions.py + system.py)

## Future / Backlog (un-prioritisiert)
- Mehrsprachiges Catering-Item-Catalog (i18n)
- AI-Vorschläge im News-Editor (Titel-Generator, Zusammenfassung)
- **WebPush für In-App-Direktnachrichten** **DONE iter 262** (ChatPushBanner + POST /api/chat/push/test, App-Badge in ChatUnreadContext)
- **Audit-Trail-UI für Admins** **DONE iter 267** (SystemAuditPanel mit Filtern, CSV-Export, Pagination, JSON-Expand)
- **Notification Center** **DONE iter 263** (Category-Tabs, server-side Deep-Link Resolution, Per-Kategorie Unread-Counts)
- **Session-Expiry-Banner** **DONE iter 267** (mf:session-expired Event + Return-to nach Login)
- **Mobile Umlaut-Cleanup** **DONE iter 267** (293 Replacements in 79 Files)
- API-Rate-Limiting konfigurierbar
- **Single-Sign-On via SAML / OIDC** (jenseits Google) — geplant: braucht IdP-Wahl (Azure AD/Okta/Keycloak/SAML 2.0/Google Workspace SAML) + Client-Credentials vom User
- **Mobile-Native-App** — Optionen: (a) PWA-Polish + A2HS *(teilweise DONE iter 262 — App-Badge + Meta-Tags)*, (b) TWA via Bubblewrap für Google Play, (c) React Native Wrapper (mehrwöchig)

---

## How to add items
1. Identify priority (P0/P1/P2/P3)
2. Add bullet with title + 1-2 sentence description
3. Reference relevant test report / issue if applicable
4. When shipped, move to `CHANGELOG.md` under the iteration that delivered it
