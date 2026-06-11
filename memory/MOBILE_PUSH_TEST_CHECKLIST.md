# 📱 Mobile Push & PWA — E2E Test-Checkliste

**Für dich zum Durchgehen auf echten Endgeräten.**
Stand: Februar 2026 · MeetFlow Klinik-Kommunikationsplattform

---

## 🎯 Voraussetzungen

- [ ] Deine Test-URL ist erreichbar: `https://video-meet-pro.preview.emergentagent.com`
- [ ] Du hast einen Admin-Account (admin@meetflow.com / admin123) und einen Member-Account
- [ ] HTTPS läuft (Push Notifications benötigen sicheres Protokoll — auf Preview-URL bereits gegeben)
- [ ] VAPID-Keys sind im Backend gesetzt (`backend/.env`: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`)

---

## 📲 Test 1 — PWA Installation (Android Chrome)

**Gerät**: Android 10+ mit Chrome

1. [ ] Öffne die URL im Chrome
2. [ ] Lade sie **3 Mal** neu (oder besuche die Seite an 3 verschiedenen Tagen)
3. [ ] Der **Install-Prompt** sollte unten rechts erscheinen (Banner „MeetFlow installieren")
4. [ ] Klicke „Installieren" → App wird auf Home-Bildschirm installiert
5. [ ] App-Icon ist auf dem Home-Bildschirm sichtbar
6. [ ] Klick auf Icon öffnet App im Vollbild (ohne Browser-URL-Leiste)
7. [ ] Unter „Einstellungen → Apps" ist „MeetFlow" als eigene App gelistet

**Erwartetes Verhalten**:
- ✅ Banner erscheint erst nach 3 Visits (Anti-Spam)
- ✅ „Später" dismissiert für 14 Tage
- ✅ Im standalone mode startet App nicht mehr mit Banner

---

## 📲 Test 2 — PWA Installation (iOS Safari)

**Gerät**: iPhone iOS 16+ mit Safari

> iOS zeigt KEINEN automatischen Install-Prompt. Die App muss manuell hinzugefügt werden.

1. [ ] Öffne URL in Safari
2. [ ] Nach 3 Visits erscheint der **iOS-Fallback-Banner** mit Anleitung
3. [ ] Banner zeigt: „In Safari: Teilen-Menü öffnen → ,Zum Home-Bildschirm' antippen"
4. [ ] Klicke auf das „Teilen"-Icon (Quadrat mit Pfeil nach oben)
5. [ ] Wähle „Zum Home-Bildschirm"
6. [ ] Bestätige Namen → Icon erscheint am Home-Bildschirm
7. [ ] Öffnen der App → startet im Vollbild ohne Safari-Leiste

---

## 📲 Test 2b — iOS 17.4+ Web-Push (PHYSICAL DEVICE) ⚠️

> iOS 17.4 und höher unterstützt Web-Push **AUSSCHLIESSLICH für installierte
> PWAs** (nicht im normalen Safari-Tab). Der gesamte Flow MUSS auf einem
> echten iPhone getestet werden — Simulator funktioniert NICHT.

**Vorbereitung**:
- [ ] iPhone ist auf **iOS 17.4 oder neuer**
- [ ] Schritt 2.1–2.7 (PWA-Install) erfolgreich abgeschlossen
- [ ] App läuft als **standalone PWA** (nicht im Safari-Tab)
- [ ] In den iPhone-Einstellungen **Mitteilungen → MeetFlow** vorhanden

**Ablauf**:
1. [ ] Öffne installierte MeetFlow-PWA vom Home-Bildschirm
2. [ ] Login → ProfilePage → „Push-Benachrichtigungen aktivieren"
3. [ ] iOS-System-Dialog erscheint → „Erlauben"
4. [ ] In den iPhone-Einstellungen verifizieren: „MeetFlow → Mitteilungen erlauben = An"
5. [ ] **Selbsttest** über `/diag`-Seite: Button „Test-Push senden" → Push muss in 1–3 s ankommen
6. [ ] **Real-Test**: Admin postet kritische News → Push kommt auf Lockscreen + Banner an
7. [ ] **Badge-Test**: Push erscheint mit Anzahl-Badge auf App-Icon
8. [ ] Tap auf Push öffnet die App **direkt zur betroffenen Seite** (kein neues Tab)
9. [ ] **Background-Test**: PWA komplett geschlossen → Push muss trotzdem ankommen

**Häufige Fehlerquellen iOS 17.4+**:
- ❌ Push subscribed im Safari-Tab (statt PWA) → keine Notifications
- ❌ "Bitte nicht stören" / Fokus-Modus aktiv → Push wird unterdrückt
- ❌ Stiller Modus + "Mitteilungen-Vorschau: nie" → Banner unsichtbar
- ❌ App-Refresh-Throttling: iOS verwirft Pushes nach >24 h Inaktivität
- ❌ VAPID-Token aus Safari-Tab vor Install passt nicht zur PWA-Subscription → neu subscriben

**Tipp**: Nutze die **/diag/shared/{token}**-Seite (Verwaltung → Diag-Link erstellen) um
das iPhone des Mitarbeiters remote testen zu lassen — Ergebnisse fliegen automatisch
zurück ins Admin-Panel.

---

## 📲 Test 2c — Quick-Diagnose des iPhones aus der Ferne

> Wenn ein Klinik-Mitarbeiter sagt „Push funktioniert nicht!", brauchst du
> KEINEN physischen Zugriff auf sein iPhone. Nutze stattdessen den
> **Shareable Diagnose-Link**.

1. [ ] Verwaltung → Tab „Quick-Scans" → „Schnell-Diagnose-Link erstellen"
2. [ ] Notiz „iPhone Push-Debug für Maria S." + 7 Tage Gültigkeit → Erstellen
3. [ ] QR-Code wird angezeigt → per E-Mail/WhatsApp/Chat an den Mitarbeiter senden
4. [ ] Mitarbeiter scannt QR auf dem iPhone → öffnet `/diag/shared/{token}`
5. [ ] Mitarbeiter klickt durch alle 6 Tests (Cam, Mic, Screen, WebRTC, Push, secureCtx)
6. [ ] Submission landet automatisch im Admin-Panel mit User-Agent + alle Fehler
7. [ ] Du siehst sofort: VAPID-OK aber `push:fail` → meist weil PWA nicht installiert ist

---

## 🔔 Test 3 — Push-Notifications abonnieren

**Gerät**: Android Chrome (funktioniert am besten) oder Desktop Chrome/Edge

1. [ ] Logge dich als Member ein
2. [ ] Gehe zu **News** → Klick auf Glocken-Icon oben rechts (Push-Subscribe-Button)
3. [ ] Browser-Dialog erscheint: „Erlauben" anklicken
4. [ ] Toast-Bestätigung: „Push-Benachrichtigungen aktiviert"
5. [ ] Backend-Prüfung: `GET /api/news/push/status` → sollte `subscribed: true` zurückgeben

---

## 🔔 Test 4 — Push empfangen

**Setup**: Subscribed Member-Device läuft im Hintergrund (App geschlossen)

1. [ ] Logge dich **auf einem anderen Gerät** als Admin ein (z.B. Desktop)
2. [ ] Gehe zu News → Erstelle einen Beitrag mit:
   - [ ] Zielgruppe: alle (oder deine Abteilung)
   - [ ] ✅ **Als Pflicht-Lesebestätigung markieren**
3. [ ] Veröffentliche den Beitrag
4. [ ] **Innerhalb von ~10 Sekunden** sollte auf dem Mobilgerät eine Push-Benachrichtigung erscheinen

**Erwartetes Verhalten**:
- ✅ Notification zeigt News-Titel + Body-Auszug
- ✅ Klick auf Notification öffnet die App DIREKT beim News-Beitrag
- ✅ Bei kritischen Meldungen: Vibration + bleibt sichtbar bis geklickt

---

## 🔔 Test 5 — Badge-Icon (ungelesene Zahl)

**Gerät**: Android Chrome oder Edge (Windows/Mac)

1. [ ] Empfange mehrere Pushs in Folge (siehe Test 4 mehrfach auslösen)
2. [ ] **Home-Bildschirm bzw. Taskleiste**: App-Icon sollte eine rote Zahl-Badge anzeigen (z.B. „3")
3. [ ] App öffnen → Badge sollte automatisch auf 0 zurückgesetzt werden
4. [ ] Ohne App-Öffnung: Badge bleibt sichtbar

**Hinweis**: iOS Safari und Firefox unterstützen die Badge-API NICHT (nur Chromium-basiert).

---

## 🌐 Test 6 — Offline-Fallback

**Gerät**: Jedes installierte PWA-Gerät

1. [ ] Schalte **Flugmodus** ein (oder deaktiviere WLAN + Mobilfunk)
2. [ ] Öffne die MeetFlow-App vom Home-Bildschirm
3. [ ] Es sollte die **Offline-Seite** erscheinen mit:
   - ⚠ Icon
   - „Keine Verbindung"
   - „Erneut versuchen"-Button
4. [ ] Button „Erneut versuchen" prüft Verbindung → lädt bei Wiederverbindung App neu

---

## 🔇 Test 7 — DND Status respektiert Pushes

1. [ ] Setze deinen Status auf **DND („Bitte nicht stören bis XX:XX")** via Status-Picker
2. [ ] Lass einen Admin einen neuen News-Beitrag senden (nicht Pflicht)
3. [ ] **Keine Push-Notification** sollte erscheinen
4. [ ] Nach Ablauf des DND-Timers: neue Posts kommen wieder durch
5. [ ] Kritische Pflicht-News sollten auch während DND durchkommen

---

## 🧩 Test 8 — Service Worker funktioniert nach App-Update

1. [ ] App auf Home-Bildschirm installiert
2. [ ] Entwickler pushed ein Frontend-Update (Version-Bump im SW-File)
3. [ ] Nächster App-Start → alter SW wird deaktiviert, neuer aktiviert
4. [ ] Push-Subscription sollte erhalten bleiben (kein re-subscribe nötig)

---

## 📊 Test 9 — Multi-Device Consistency

1. [ ] Logge dich auf 2 Geräten als gleicher Member ein (Android + iPhone)
2. [ ] Subscribe auf beiden für Push
3. [ ] Admin sendet Pflicht-News → **beide Geräte** sollten Push erhalten
4. [ ] Auf Gerät 1 Push antippen & lesen
5. [ ] Backend: Lesebestätigung registriert
6. [ ] Auf Gerät 2: Badge sollte trotzdem erst bei App-Öffnung verschwinden (Badge ist lokal)

---

## 🧪 Test 10 — Unsubscribe

1. [ ] Gehe zu News → Glocken-Icon erneut klicken (Toggle)
2. [ ] Browser-Dialog: Blockieren/Erlauben erneut
3. [ ] Backend: `/api/news/push/status` → `subscribed: false`
4. [ ] Neue Pushes kommen NICHT mehr an
5. [ ] Badge-Count wird nicht mehr aktualisiert

---

## ✅ Finale Abnahme-Kriterien

- [ ] Android Chrome: alle 10 Tests bestanden
- [ ] iOS Safari: Tests 2, 3, 4, 5 (Badge nicht unterstützt), 7, 9, 10 bestanden
- [ ] Desktop Chrome: alle 10 Tests bestanden
- [ ] Desktop Firefox: Tests 2, 3, 4, 6, 7, 9, 10 (kein Badge) bestanden
- [ ] Desktop Edge: alle 10 Tests bestanden
- [ ] DSGVO: Push-Subscription-Opt-In muss explizit sein (Test 3 erfüllt)

---

## 🐛 Typische Fallstricke

| Problem | Lösung |
|---|---|
| Kein Install-Prompt | Inkognito-Modus oder <3 Visits. Prüfe `application` → manifest in DevTools |
| Push kommt nicht | Service Worker prüfen (`chrome://serviceworker-internals/`), VAPID-Keys im backend/.env |
| Badge fehlt | Nur Chromium. Firefox/Safari unterstützen es nicht |
| Offline-Page leer | Ist `offline.html` in /public + wird in SW pre-cached? |
| iOS ohne Prompt | Normal — iOS-PWA geht nur manuell via „Zum Home-Bildschirm" |

---

## 📝 Ergebnis-Template zum Ausfüllen

```
Getestet: [Datum]
Device: [Modell + OS + Browser]
Ergebnis:
  Test 1: ✅ / ❌
  Test 2: ✅ / ❌
  ...
Bemerkungen:
```

Bei Bugs bitte Screenshot + Console-Log (Chrome: Menü → Weitere Tools → Entwicklertools → Console) anhängen.
