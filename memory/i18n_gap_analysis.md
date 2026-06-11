# i18n Gap-Analyse — MeetFlow (Iter 125)

**Stand:** Feb 2026
**Scanner:** `/tmp/i18n_gap.json` (exportiert nach `/app/memory/i18n_gap_report.json`)

## Zusammenfassung

- **64 Dateien** mit hardcoded deutschen Strings erkannt
- **360 Strings** insgesamt (JSX-Text + `placeholder`/`title`/`label`/`aria-label`/`alt` Attribute)
- `i18n.js` enthält aktuell ~160 Keys (DE+EN). Gap ~= **200 neue Keys** benötigt für vollständige 100%-Abdeckung.

## Bestehende i18n-Infrastruktur

- `/app/frontend/src/lib/i18n.js` — `translations = { en: {...}, de: {...} }`
- `/app/frontend/src/contexts/LanguageContext.js` — `useLanguage() → { t, language, setLanguage, toggleLanguage }`
- Sidebar hat bereits einen Sprach-Toggle (Globe-Icon)
- Muster in Komponenten: `const { t, language } = useLanguage();` → `<span>{t('myKey')}</span>` ODER `<span>{language === 'de' ? 'Deutsch' : 'English'}</span>`

## Top-Files mit Gap (nach Priorität, absteigend)

| Strings | Datei | Priorität |
|---:|---|---|
| 29 | `pages/AdminPage.js` | 🔴 P1 (häufig genutzt von Admin-Rolle) |
| 17 | `pages/ChatPage.js` | 🔴 P1 (täglich genutzt, viele User) |
| 16 | `components/NewsModerationPanel.js` | 🟠 P2 (nur Redakteur-Rolle) |
| 15 | `pages/MeetingsPage.js` | 🔴 P1 (Hauptflow) |
| 14 | `components/admin/HealthDashboard.js` | 🟠 P2 (Admin-only) |
| 13 | `components/BulkInviteDialog.js` | 🟠 P2 (einmalig) |
| 11 | `pages/ProfilePage.js` | 🔴 P1 |
| 11 | `components/admin/EmailConfigPanel.js` | 🟠 P2 |
| 10 | `components/admin/RolesCapsPanel.js` | 🟠 P2 |
| 9 | `pages/PreJoinPage.js` | 🔴 P1 (jedes Meeting) |
| 9 | `pages/NewsPage.js` | 🔴 P1 |
| 9 | `pages/PublicPollPage.js` | 🟡 P3 (public, extern) |
| 9 | `components/admin/AutoAssignRulesPanel.js` | 🟠 P2 |

**P1-Summe**: 90 Strings über 6 Haupt-Dateien = kritischster Gap.
**P2-Summe**: 83 Strings über 8 Admin-Panels = wichtig für EN-sprachige Admins.
**P3-Summe**: ~187 Strings über 50 Rest-Dateien = nice-to-have.

## Beobachtungen beim Scan

1. **Inline-Conditionals dominieren**: Viele Stellen nutzen `{language === 'de' ? 'Text DE' : 'Text EN'}` statt `t('key')`. Das ist lauffähig, aber unübersichtlich.
2. **Fehlende `t()`-Keys**: Viele Strings haben keinen EN-Pendant im Code — wenn User auf Englisch umschaltet, bleibt der String deutsch.
3. **Admin-UI fast komplett deutsch**: Alle `/app/frontend/src/components/admin/*` Panels sind noch nicht lokalisiert.
4. **Meeting-Modals** (`ConsentDialog`, `BulkInviteDialog`) noch hardcoded.
5. **ARIA-Labels fehlen** oft auch in englischer Version — Accessibility-Ziel.
6. **Toast-Messages**: `toast.success('Gespeichert')` — viele solche Stellen sind hartkodiert.

## Empfohlener Vorgehensplan

### Phase 1 — P1 Dateien (90 Strings, ~2h Arbeit)
- `pages/AdminPage.js`, `pages/ChatPage.js`, `pages/MeetingsPage.js`, `pages/ProfilePage.js`, `pages/PreJoinPage.js`, `pages/NewsPage.js`
- Für jede Datei: Neue `t()`-Keys in `i18n.js` ergänzen (DE+EN), dann Inline-Strings durch `t('key')` ersetzen.

### Phase 2 — P2 Admin-Panels (83 Strings, ~1.5h)
- Schnelle, repetitive Arbeit. Admin-Panels haben viel Boilerplate-UI.

### Phase 3 — P3 Rest (~3h, nice-to-have)
- 50 Dateien mit je 1–6 Strings. Kann auch inkrementell erfolgen.

## Nächster Schritt

Falls User grünes Licht gibt, starte ich mit **Phase 1** (P1) — das gibt ~25% der User-Interaktionen komplett EN-fähig und dauert ~2h. Kann als separater Iter-Task laufen.

## Data

Komplette Datei-→Strings-Map: `/app/memory/i18n_gap_report.json`
