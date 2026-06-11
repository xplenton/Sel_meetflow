# Deployment-Guide für den MeetFlow License Server

Drei Optionen vom einfachsten zum professionellsten Setup. Empfehlung: **Variante 2 (Hetzner CX11 + Caddy)** — kostet ~4 €/Monat und reicht für hunderte Kunden.

---

## Variante 1: Lokaler Server / Raspberry Pi (entwicklungs- & test-tauglich)

Geeignet wenn du erstmal nur 1-2 Test-Kunden hast und keine cloud-Hosting-Kosten möchtest.

```bash
# Auf dem Pi / lokalem Linux-Server
git clone https://dein-git-server.de/meetflow-license-server.git /opt/license-server
cd /opt/license-server

# Persistent storage anlegen
sudo mkdir -p /var/lib/license-server
sudo chown $USER /var/lib/license-server

# Token generieren (32 zufällige Zeichen — gut merken!)
echo "ADMIN_TOKEN=$(openssl rand -hex 32)" > .env

# Docker-Build + Start mit Auto-Restart
docker build -t meetflow-license-server .
docker run -d --name license-server --restart=always \
  -p 8080:8080 \
  -v /var/lib/license-server:/app/data \
  --env-file .env \
  meetflow-license-server

# Im Heimnetz: Router → Portforwarding 443 → Pi:8080 + DynDNS-Service (z. B. duckdns.org)
```

**Nachteile:** kein TLS out-of-the-box, Heim-Internet kann unzuverlässig sein.

---

## Variante 2: Hetzner Cloud + Caddy (EMPFOHLEN)

Hetzner CX11 = 4 €/Monat, deutsches Rechenzentrum, IPv4 + IPv6, mehr als genug für tausende Lizenzen.

### 2.1 Server bestellen

1. <https://console.hetzner.cloud> → „Server hinzufügen"
2. **Standort:** Nürnberg (oder Helsinki)
3. **Image:** Ubuntu 24.04
4. **Typ:** CX22 (2 vCPU, 4 GB RAM, ~4 €/Monat) — reicht völlig
5. **SSH-Key** hochladen (oder Passwort generieren lassen)
6. **Name:** `license.meinedomain.de`
7. „Server erstellen"

### 2.2 DNS-Eintrag setzen

Bei deinem Domain-Anbieter (Hetzner, IONOS, Strato …) einen **A-Record** anlegen:
```
license.meinedomain.de  →  <IPv4 vom Hetzner-Server>
```

### 2.3 Server vorbereiten (SSH)

```bash
ssh root@license.meinedomain.de

# System aktualisieren + Docker installieren
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# Firewall: nur 22 (SSH) + 443 (HTTPS) + 80 (Let's-Encrypt-ACME)
apt install -y ufw
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Caddy als Reverse-Proxy mit automatischem TLS
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy

# Caddy-Config
cat > /etc/caddy/Caddyfile <<'EOF'
license.meinedomain.de {
    # Iter 371 — TLS via Let's-Encrypt automatisch.
    # Reverse-Proxy zum License-Server-Container.
    reverse_proxy localhost:8080

    # Rate-Limit: 1 Request/Sekunde pro IP reicht
    # (MeetFlow ruft nur alle 6h auf — mehr ist verdächtig)
    # NOTE: Erfordert caddy-ratelimit Plugin, optional weglassen.

    # Security-Header
    header {
        Strict-Transport-Security "max-age=31536000;"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer"
    }
}
EOF
systemctl reload caddy
```

**Wichtig:** Domain MUSS im DNS auf den Server zeigen, BEVOR Caddy startet — sonst bekommst du das Let's-Encrypt-Zertifikat nicht.

### 2.4 License-Server starten

```bash
# Code holen — Variante a) git clone, Variante b) scp upload
mkdir -p /opt/license-server
cd /opt/license-server
# … server.py, Dockerfile, requirements.txt hochladen …

# Persistent Volume
mkdir -p /var/lib/license-server

# Token generieren (NUR EINMAL — danach gut aufbewahren!)
ADMIN_TOKEN=$(openssl rand -hex 32)
echo "Dein Admin-Token (BEWAHRE GUT AUF!): $ADMIN_TOKEN"

# Build + Start
docker build -t meetflow-license-server .
docker run -d --name license-server --restart=always \
  -p 127.0.0.1:8080:8080 \
  -v /var/lib/license-server:/app/data \
  -e ADMIN_TOKEN="$ADMIN_TOKEN" \
  meetflow-license-server

# Smoketest
curl https://license.meinedomain.de/health
# → {"status":"ok","version":"1.0"}
```

**Achtung:** `-p 127.0.0.1:8080:8080` bindet den Container nur an localhost — Caddy ist der einzige Weg von außen. So kann man auch nicht versehentlich über die IP+Port direkt zugreifen.

### 2.5 Admin-UI öffnen

→ <https://license.meinedomain.de>
→ Token oben einfügen, „Laden" klicken
→ Lizenzen erstellen / verwalten

### 2.6 Automatisches Backup

```bash
# Crontab anlegen
cat > /etc/cron.daily/license-backup <<'EOF'
#!/bin/bash
DEST=/root/license-backups
mkdir -p $DEST
sqlite3 /var/lib/license-server/licenses.sqlite3 ".backup $DEST/licenses-$(date +%Y%m%d).sqlite3"
# Älter als 30 Tage löschen
find $DEST -name "licenses-*.sqlite3" -mtime +30 -delete
EOF
chmod +x /etc/cron.daily/license-backup
```

**Bonus:** Backup automatisch zu deinem privaten S3/Backblaze hochladen mit `rclone`.

---

## Variante 3: AWS / Azure (Enterprise)

Wenn du eh schon AWS-Account hast und volle Cloud-Integration willst.

**Minimal-Setup:**
- **EC2 t4g.nano** (ARM64, ~3 $/Monat) mit Ubuntu 24.04
- **EBS-Volume 10 GB** für `/var/lib/license-server`
- **Route 53** für DNS
- **Security Group:** nur 80/443/22 offen
- Rest wie Variante 2

Oder noch schicker:
- **ECS Fargate** mit dem Docker-Image
- **RDS PostgreSQL** statt SQLite (multi-AZ für HA)
- **CloudWatch Logs** für zentrale Verify-Audit-Logs
- **API Gateway + Lambda** statt eigenem Container (höchste Skalierung)

Für deine Größenordnung (B2B-MeetFlow) ist das aber massiv überdimensioniert. Bleib bei Variante 2.

---

## Nach dem Deployment: MeetFlow konfigurieren

Bei jedem Kunden in `backend/.env`:
```env
LICENSE_SERVER_URL=https://license.meinedomain.de
LICENSE_KEY=MEETFLOW-XXXX-XXXX-XXXX-XXXX
LICENSE_TENANT_ID=klinik-abc   # optional
LICENSE_DOMAIN=meetflow.klinik-abc.de  # optional
```

→ Backend restart → erster Verify → Hardware-Fingerprint wird beim License-Server registriert → ab jetzt 6 h Heartbeat.

## Monitoring (optional)

Im License-Server-Container regelmäßig die Logs prüfen:
```bash
docker logs license-server | tail -50
```

Oder mit Loki/Grafana zentralisieren, falls du mehrere Kunden parallel betreibst.

## FAQ

**Was wenn der License-Server kurz offline ist?**
→ MeetFlow-Instanzen laufen 24h Offline-Grace weiter (siehe `services/license.py`). Erst danach kommt der 503-Block.

**Was wenn ich den Server umziehen muss?**
→ `/var/lib/license-server/licenses.sqlite3` auf neuen Server kopieren, DNS umziehen, fertig. Bestehende Lizenzen funktionieren weiter.

**Kann ich mehrere License-Server für HA betreiben?**
→ Nein, SQLite ist single-writer. Für HA: SQLite → PostgreSQL migrieren + Load-Balancer davor. Aber: 99,9 % Uptime auf einem Hetzner-CX22 reicht für 99 % aller B2B-Anwendungen.

**Wer hat Zugriff auf den Admin-Token?**
→ Nur du. Verteil ihn NIE an Kunden. Der Token ist deine Master-Berechtigung zum Erstellen/Sperren aller Lizenzen.
