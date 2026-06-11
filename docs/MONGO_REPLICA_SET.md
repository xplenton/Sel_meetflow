# MongoDB Replica-Set — Setup & Operations

## Aktueller Status

Diese MeetFlow-Instanz läuft seit **Iter 261** mit einem **Single-Node Replica-Set** namens `rs0`. Der Code (`backend/database.py`) verwendet zwei Handles:

- `db` — Standard-Handle, alle Schreibvorgänge laufen über die PRIMARY.
- `read_db` — `read_preference=SECONDARY_PREFERRED`. Bei einem mehrgliedrigen RS leiten heavy Read-Endpunkte (Listen, Dashboards, Reports) automatisch auf eine SECONDARY um.

Bei Single-Node-RS bleibt die PRIMARY für Reads und Writes zuständig — der Code ist aber bereits "RS-fähig" und skaliert ohne Code-Änderung, sobald weitere Member hinzugefügt werden.

## RS-Status prüfen

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" $REACT_APP_BACKEND_URL/api/admin/health/mongo
```

Antwort enthält `set_name`, `primary_count`, `secondary_count` und eine `members`-Liste.

Oder direkt via `mongosh`:

```bash
mongosh --eval "rs.status()"
```

## Standalone → Replica-Set umstellen (Production)

### 1. mongod mit `--replSet rs0` starten

Das `command:`-Feld im Supervisor (oder systemd-Unit / `mongod.conf`) ergänzen:

```yaml
# /etc/mongod.conf
replication:
  replSetName: rs0
```

oder als CLI-Flag in `/etc/supervisor/conf.d/supervisord.conf` (so machen wir es hier):

```ini
[program:mongodb]
command=/usr/bin/mongod --bind_ip_all --replSet rs0
```

Anschließend `sudo supervisorctl restart mongodb`.

### 2. Replica-Set initiieren (einmalig)

```bash
mongosh --eval 'rs.initiate({_id:"rs0", members:[{_id:0, host:"localhost:27017"}]})'
```

Oder via Python:

```python
import pymongo
client = pymongo.MongoClient("mongodb://localhost:27017", directConnection=True)
client.admin.command({"replSetInitiate": {
    "_id": "rs0",
    "members": [{"_id": 0, "host": "localhost:27017"}]
}})
```

### 3. (Optional) Sekundärknoten hinzufügen

Sobald die App produktiv läuft, weitere Nodes auf separater Hardware aufsetzen, gleiches `--replSet rs0`, dann auf der PRIMARY:

```javascript
rs.add("mongo2.intern:27017")
rs.add("mongo3.intern:27017")
```

Ab dem dritten Member (ungerade Anzahl für Quorum) ist Auto-Failover aktiv.

### 4. MONGO_URL aktualisieren

Für Multi-Node-Setup ergänzen:

```
MONGO_URL="mongodb://mongo1.intern:27017,mongo2.intern:27017,mongo3.intern:27017/?replicaSet=rs0"
```

Bei Single-Node bleibt `mongodb://localhost:27017` ausreichend; der Treiber erkennt das RS automatisch.

## Code-Konventionen

- **NIE** `db` und `read_db` in derselben Funktion mischen, wenn Read-after-Write-Konsistenz benötigt wird.
- `read_db` ist für eventually-consistent Endpoints gedacht:
  - List/Search-Endpoints (Resources, Users, Tasks, Bookings)
  - Reports, Statistiken, Dashboards
  - Audit-Logs, Health-Metriken
- Für transaktionale Operationen, "read your own write" oder Counter-Increments **immer** `db` verwenden.

## Troubleshooting

| Symptom | Ursache | Fix |
|---------|---------|-----|
| `NotPrimaryNoSecondaryOk` bei `read_db.find()` | RS gerade Election-Phase | Retry-Logic im Driver greift automatisch; sonst auf `db` zurückfallen. |
| `replSetGetStatus` wirft `NoReplicationEnabled` | mongod ohne `--replSet` gestartet | Supervisor-Config prüfen, restart. |
| `OplogTooSmall` Warnings im Log | Replica-Set hat zu kleines Oplog | `db.adminCommand({replSetResizeOplog: 1, size: 16384})` (16 GB). |

## Atlas / Managed-MongoDB

Wenn die Produktionsumgebung Atlas/CosmosDB/DocumentDB verwendet, ist Replica-Set bereits Standard. Einfach die Connection-String im `MONGO_URL` setzen — kein weiteres Setup nötig. `read_db` wird transparent SECONDARY-Reads nutzen.
