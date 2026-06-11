# MeetFlow License Server

Eigenständiger FastAPI-Server zum Verwalten von MeetFlow-Lizenzen. Läuft auf
deinem eigenen Hosting (Hetzner, AWS, lokaler Server) und wird vom
MeetFlow-Backend bei deinen Kunden alle 6 h aufgerufen.

## Quick Start (Lokal)

```bash
cd license_server
pip install -r requirements.txt
export ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
echo "Admin Token: $ADMIN_TOKEN"
python server.py
```

→ Admin-UI öffnen: <http://localhost:8080>
→ Token oben einfügen, „Laden" klicken.

## Production (Docker)

```bash
docker build -t meetflow-license-server .
docker run -d --restart=always \
  -p 443:8080 \
  -v /var/lib/meetflow-license:/app/data \
  -e ADMIN_TOKEN="dein-langes-geheimes-token" \
  --name license-server \
  meetflow-license-server
```

Stelle einen Reverse-Proxy (Caddy/Nginx) davor mit gültigem TLS-Zertifikat.
Endgültige URL z. B. `https://license.deins.de`.

## Workflow: Neuen Kunden ausliefern

1. **Lizenz erstellen** im Admin-UI:
   - Tenant ID: `klinik-abc`
   - Kundenname: `Klinik ABC GmbH`
   - Gültig bis: `31.12.2027`
   - → System generiert `MEETFLOW-A1B2-C3D4-E5F6-7890`

2. **Kunde konfiguriert seinen MeetFlow-Server** (`backend/.env`):
   ```env
   LICENSE_SERVER_URL=https://license.deins.de
   LICENSE_KEY=MEETFLOW-A1B2-C3D4-E5F6-7890
   ```

3. **Beim ersten Start** bindet sich MeetFlow automatisch an die Hardware
   (MAC + Hostname → SHA256). Im Admin-UI siehst du den Fingerprint
   erscheinen.

4. **Wenn Kunde die Hardware wechselt**: Klick auf „Reset HW" → der
   Fingerprint wird gelöscht und beim nächsten Verify neu gebunden.

## API-Endpoints

### Public

| Endpoint | Beschreibung |
|---|---|
| `POST /verify` | Von MeetFlow aufgerufen — Body: `{ license_key, fingerprint, tenant_id?, domain?, version? }` |
| `GET /health` | Liveness Check |
| `GET /` | Admin-UI (HTML) |

### Admin (Header `X-Admin-Token: ...`)

| Endpoint | Beschreibung |
|---|---|
| `GET /admin/licenses` | Alle Lizenzen |
| `POST /admin/licenses` | Neue Lizenz erstellen |
| `PUT /admin/licenses/{key}` | Updaten (valid_until, notes, …) |
| `POST /admin/licenses/{key}/revoke` | Sperren |
| `POST /admin/licenses/{key}/restore` | Wieder aktivieren |
| `POST /admin/licenses/{key}/reset-fingerprint` | Hardware-Bindung löschen |
| `GET /admin/licenses/{key}/audit?limit=100` | Verify-Logs einer Lizenz |

## Sicherheits-Tipps

- **ADMIN_TOKEN** muss lang + zufällig sein. Mit `python -c "import secrets; print(secrets.token_urlsafe(32))"` generieren.
- **TLS**: Den Server NIE unverschlüsselt erreichbar machen — `LICENSE_KEY` würde sonst über die Leitung gesnifft.
- **Backup**: `/app/data/licenses.sqlite3` regelmäßig sichern. Bei Verlust musst du alle Kunden neue Keys verteilen.
- **IP-Whitelist**: Falls du nur eine Handvoll Kunden hast, ergänze den Caddy/Nginx-Proxy um eine Allow-List der Kunden-IPs.
- **Rate-Limiting**: Z. B. via Caddy `rate_limit` Plugin — 1 Request/Sekunde pro IP reicht (MeetFlow ruft nur alle 6 h auf).
- **Stripe-Webhook** anbauen: Nach erfolgreicher Zahlung automatisch `valid_until` verlängern. Code-Snippet kann ich auf Anfrage ergänzen.

## Skalierung

Aktuell SQLite → reicht für tausende Lizenzen, läuft auf einem kleinen
Hetzner-Server problemlos. Wenn du Richtung Enterprise gehst:
- SQLite → PostgreSQL (psycopg + SQLAlchemy)
- Audit-Log nach 90 Tagen archivieren
- Replica + Daily-Backup

Aber bis dahin: SQLite + dieser Single-File-Server reichen vollkommen.
