# Uptime Monitoring Setup

> Iter 121. Ziel: sofortige Benachrichtigung, wenn Production down geht.

## Warum eine externe Uptime-Überwachung?

Der Emergent-Pod hat eigene Watchdogs, aber eine **unabhängige** externe
Quelle ist wichtig, weil:

- Ein Ausfall des Emergent-Providers nichts mehr selbst-reporten kann
- DNS-/CDN-/Cloud-Probleme oft nur von außen sichtbar sind
- Du willst die Email/SMS bekommen, bevor der erste User sich beschwert

## Empfohlene Anbieter (Free Tier reicht für 1 Domain)

| Anbieter | Free-Tier | Besonderheiten |
|----------|-----------|---------------|
| **UptimeRobot** | 50 Monitore, 5-Min-Intervall | einfachster Einstieg, E-Mail-Alerts |
| **Better Uptime** | 10 Monitore, 3-Min-Intervall | schöne Status-Page gratis |
| **StatusCake** | unbegrenzt, 5-Min | erweiterte Checks (DNS, SSL, …) |

## Setup-Anleitung (am Beispiel UptimeRobot)

### 1. Account anlegen
https://uptimerobot.com → Sign up → Email bestätigen

### 2. Monitor erstellen
- **Monitor Type**: `HTTP(s)`
- **Friendly Name**: `MeetFlow Production Health`
- **URL**: `https://<deine-domain>/api/health`
- **Monitoring Interval**: `5 Minutes`
- **HTTP Status Codes**: akzeptiere `200` (default reicht)
- **Timeout**: `30s`

### 3. Alert Contacts
- **E-Mail**: deine Admin-Mail
- Optional: SMS (kostenpflichtig), Slack-Webhook, Telegram

### 4. Status-Page (optional, öffentlich teilbar)
- Dashboard → My Public Status Pages → `+ Add New`
- Wähle den oben erstellten Monitor aus
- Teile den Link mit deinem Klinik-Team

## Was überwacht wird

Der `/api/health` Endpoint (Iter 113/121) gibt einen 200 OK zurück wenn:
- Die FastAPI-App läuft
- MongoDB per `ping` erreichbar ist

Gibt 503 bei DB-Problemen — UptimeRobot wird dich dann benachrichtigen,
bevor dein erster User merkt, dass der Login nicht mehr funktioniert.

## Zusätzliche Monitore (optional)

```
/api/health                → Liveness (oben beschrieben)
/api/auth/login            → Funktional (POST, Body mit Test-Account)
/                          → Frontend statisch (sollte 200 zurück)
```

## Alarm-Routing bei Incident

1. **UptimeRobot** schickt E-Mail/SMS an Admin (~ 30s Delay)
2. **Sentry** (Iter 121) erfasst gleichzeitig Backend-Exceptions
3. Check `/api/health` für Mongo-Status
4. Falls nötig: Emergent → Rollback zum letzten funktionierenden Checkpoint

## Cost ($0 Setup)

UptimeRobot Free = 50 Monitore, 5-Min-Intervall, E-Mail-Alerts — mehr als
ausreichend für eine Klinik-App. Sentry Free = 5000 Errors/Monat +
10 000 Performance Events. Beide ohne Kreditkarte startbar.

---

**Nächster Schritt:** Account anlegen → Monitor erstellen → bei nächstem
Deploy verifizieren, dass E-Mail-Alert bei manuellem Backend-Stopp
ankommt.
