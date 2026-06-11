# Lizenz-System für On-Prem MeetFlow

## Übersicht

MeetFlow kann gegen einen externen Lizenz-Server validiert werden, damit du
deinen Code geschützt an Kunden ausliefern kannst, ohne dass diese ihn
unbegrenzt laufen lassen können.

**Wie es funktioniert:**

1. Beim Backend-Start ruft MeetFlow den Lizenz-Server unter
   `${LICENSE_SERVER_URL}/verify` mit dem Lizenz-Key + Hardware-Fingerprint
   auf.
2. Der Server antwortet mit `{ "status": "valid", "valid_until": "...", "tenant_id": "..." }`.
3. Alle 6 h wiederholt sich der Check. Bei Fehlschlag → 24 h Offline-Grace,
   danach blockt MeetFlow alle API-Calls mit HTTP 503.
4. Im Frontend erscheint ein roter Banner „Lizenz inaktiv".

## Konfiguration (Kunde-Server)

`backend/.env`:

```env
LICENSE_SERVER_URL=https://license.meetflow.de
LICENSE_KEY=KUNDE-ABC-XYZ-12345-67890
LICENSE_TENANT_ID=klinik-abc        # optional
LICENSE_DOMAIN=meetflow.klinik-abc.de # optional
APP_VERSION=1.0.0                   # optional
```

**Dev/Preview:** Lass `LICENSE_SERVER_URL` leer → Check ist deaktiviert
(`status: disabled`). Die App funktioniert ohne Einschränkungen.

## Lizenz-Server-Schnittstelle

Dein Lizenz-Server muss einen `POST /verify`-Endpoint anbieten:

**Request:**
```json
{
  "license_key": "KUNDE-ABC-XYZ-12345-67890",
  "fingerprint": "a3f9b2c8d1e4f6a7",
  "tenant_id": "klinik-abc",
  "domain": "meetflow.klinik-abc.de",
  "version": "1.0.0"
}
```

**Response (valid):**
```json
{
  "status": "valid",
  "valid_until": "2027-01-01T00:00:00Z",
  "tenant_id": "klinik-abc",
  "message": null
}
```

**Response (invalid):**
```json
{
  "status": "invalid",
  "message": "Lizenz abgelaufen am 01.06.2026"
}
```

Der Fingerprint ist ein SHA256 aus `(hostname, mac_addr, license_key)`. Bei
deinem ersten Verify kannst du den Fingerprint in der DB speichern und
zukünftige Anfragen mit anderem Fingerprint zurückweisen — damit ist eine
Kopie auf einen anderen Server gesperrt.

## API-Endpoints in MeetFlow

| Endpoint | Auth | Beschreibung |
|---|---|---|
| `GET /api/license/status` | public | Aktueller Lizenz-Status (für Banner) |
| `POST /api/admin/license/recheck` | `admin.manage_integrations` | Forciert sofortigen Check |

## Empfohlenes Setup für maximalen Schutz

1. **Docker-Image statt Source-Code** ausliefern
   ```bash
   docker build -t registry.deins.de/meetflow:1.0.0 .
   docker push registry.deins.de/meetflow:1.0.0
   ```
2. **Source obfuskieren** (vor dem Build)
   ```bash
   pip install pyarmor
   pyarmor obfuscate --recursive backend/
   ```
3. **Frontend ohne Source-Maps**
   ```bash
   GENERATE_SOURCEMAP=false yarn build
   ```
4. **Lizenz-Server bei dir hosten** (z. B. einfacher FastAPI-Server mit
   PostgreSQL — kann auch Stripe-Subscription-Status spiegeln).
5. **Lizenzvertrag** mit Reverse-Engineering-Verbot.

## Verhalten bei ungültiger Lizenz

| Pfad | Verhalten |
|---|---|
| `/api/auth/*` (Login, Refresh) | ✅ erreichbar |
| `/api/license/status` | ✅ erreichbar |
| `/api/admin/license/recheck` | ✅ erreichbar |
| `/api/health` | ✅ erreichbar |
| Alle anderen `/api/*` | ❌ HTTP 503 mit `code: LICENSE_INVALID` |
| Frontend (React-App) | ✅ erreichbar (zeigt nur Banner + Login) |

Damit kann der Kunde sich noch einloggen + den Status sehen, aber nichts mehr
tun, bis der Admin die Lizenz erneuert.
