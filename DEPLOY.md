# MeetFlow — Deployment-Anleitung (Self-Hosted)

Schritt-für-Schritt-Setup fuer einen DSGVO-konformen Produktions-Betrieb auf
**Hetzner Cloud + Caddy + systemd**. Diese Anleitung kann genauso auf jedem
anderen Ubuntu-22.04/24.04-Server (AWS, IONOS, Strato, eigener Bare-Metal)
laufen — die Caddy/systemd-Schritte aendern sich nicht.

> **Ungefaehre Dauer:** 60–90 Minuten fuer einen erfahrenen Admin.
> **Voraussetzung:** Domain (z. B. `meetflow.deine-klinik.de`), Root-Zugang zum Server.

---

## 1. Server bestellen

### Empfehlung: Hetzner Cloud
- **Standort:** Falkenstein (FSN1) oder Nuernberg (NBG1) — Deutschland, DSGVO-konform
- **Typ:** `CX32` (4 vCPU, 8 GB RAM, 80 GB NVMe SSD) — ~12 €/Monat
- **Image:** Ubuntu 24.04 LTS
- **Optionen aktivieren:**
  - [x] SSH-Key hinterlegen
  - [x] Backups (zusaetzlich ~2,40 €/Monat — 7 taegliche Snapshots)
  - [x] IPv4 + IPv6
  - [x] Firewall: nur Port 22 (SSH), 80 (HTTP), 443 (HTTPS) eingehend erlauben

Alternativ: jeder Anbieter mit Ubuntu-22.04/24.04 + Root-SSH + mindestens 4 GB RAM funktioniert.

### Domain einrichten
Im DNS deiner Domain einen **A-Record** auf die Server-IPv4 setzen:
```
meetflow.deine-klinik.de.  A   <SERVER_IP>
meetflow.deine-klinik.de.  AAAA <SERVER_IPv6>
```
DNS-Propagation dauert in der Regel <10 Minuten.

---

## 2. Grund-Setup (Ubuntu)

```bash
ssh root@<SERVER_IP>

# System aktuell
apt update && apt upgrade -y

# Zeitzone + Unattended Security Updates
timedatectl set-timezone Europe/Berlin
apt install -y unattended-upgrades
dpkg-reconfigure --priority=low unattended-upgrades

# Firewall (UFW)
apt install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Non-root-User mit sudo
adduser meetflow --disabled-password --gecos ""
usermod -aG sudo meetflow
mkdir -p /home/meetflow/.ssh
cp ~/.ssh/authorized_keys /home/meetflow/.ssh/
chown -R meetflow:meetflow /home/meetflow/.ssh
chmod 700 /home/meetflow/.ssh
chmod 600 /home/meetflow/.ssh/authorized_keys

# Root-SSH deaktivieren
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd
```

Ab jetzt mit `meetflow`-User weiterarbeiten:
```bash
ssh meetflow@<SERVER_IP>
sudo -i
```

---

## 3. Abhaengigkeiten installieren

```bash
# Python 3.12 (Ubuntu 24.04 hat es schon, sonst PPA)
apt install -y python3 python3-pip python3-venv python3-dev build-essential

# Node.js 20 + Yarn (fuer Frontend-Build)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
npm install -g yarn

# MongoDB 7 (offizielles Repo)
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
  gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] \
  https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
  > /etc/apt/sources.list.d/mongodb-org-7.0.list
apt update
apt install -y mongodb-org
systemctl enable --now mongod

# Redis 7
apt install -y redis-server
sed -i 's/^supervised .*/supervised systemd/' /etc/redis/redis.conf
systemctl enable --now redis-server

# Caddy 2 (Reverse-Proxy mit auto-HTTPS)
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy

# Pillow / reportlab Build-Deps (PDF + QR-Codes)
apt install -y libjpeg-dev zlib1g-dev libpq-dev libffi-dev

# Hilfreich fuer Debugging
apt install -y htop tmux git fail2ban
```

### Fail2ban grob konfigurieren (SSH-Brute-Force-Schutz)
```bash
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
maxretry = 4
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban
```

---

## 4. MongoDB-Auth aktivieren

```bash
mongosh
```
Im Mongo-Shell:
```javascript
use admin
db.createUser({
  user: "meetflow_admin",
  pwd: "<DB-ROOT-PW-HIER>",
  roles: ["root"]
})
use meetflow
db.createUser({
  user: "meetflow_app",
  pwd: "<APP-PW-HIER>",
  roles: [{ role: "readWrite", db: "meetflow" }]
})
exit
```

Auth in der Mongo-Config aktivieren:
```bash
sed -i 's/^#security:/security:\n  authorization: enabled/' /etc/mongod.conf
systemctl restart mongod
```

Verbindung-String fuer spaeter merken:
```
mongodb://meetflow_app:<APP-PW>@127.0.0.1:27017/meetflow?authSource=meetflow
```

---

## 5. App-Code deployen

```bash
# Als meetflow-User
exit  # zurueck zu meetflow
sudo mkdir -p /opt/meetflow
sudo chown meetflow:meetflow /opt/meetflow
cd /opt/meetflow

# Code via Git oder SCP. Beispiel via Git:
git clone https://github.com/<dein-org>/meetflow.git .
# oder als zip-Upload via scp + unzip
```

### Backend-Setup
```bash
cd /opt/meetflow/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
deactivate
```

### Frontend-Build
```bash
cd /opt/meetflow/frontend
yarn install --frozen-lockfile
# Build wird gleich nach .env-Setup gemacht (Build-Time-Variablen)
```

---

## 6. Environment-Variablen setzen

### Backend (`/opt/meetflow/backend/.env`)
```bash
cat > /opt/meetflow/backend/.env <<'EOF'
# Datenbank
MONGO_URL=mongodb://meetflow_app:<APP-PW>@127.0.0.1:27017/meetflow?authSource=meetflow
DB_NAME=meetflow

# JWT / Crypto (KRITISCH — beide mit `openssl rand -hex 32` erzeugen!)
JWT_SECRET=<32-byte-hex-secret>
SECRET_KEY=<32-byte-hex-secret>

# CORS — exakte Produktions-URL (mit https://)
CORS_ORIGINS=https://meetflow.deine-klinik.de
FRONTEND_URL=https://meetflow.deine-klinik.de

# Initial-Admin-Account (wird beim ersten Start angelegt)
ADMIN_EMAIL=admin@deine-klinik.de
ADMIN_PASSWORD=<starkes-Passwort-min-12-Zeichen>

# Redis
REDIS_URL=redis://127.0.0.1:6379/0

# Hintergrund-Job-Queue
ENABLE_BACKGROUND_QUEUE=1

# Optional: E-Mail-Versand (sonst werden Einladungen nur in der Datenbank angelegt)
RESEND_API_KEY=
SENDGRID_API_KEY=
SENDER_EMAIL=noreply@deine-klinik.de

# Optional: AI-Features (Zusammenfassungen, GPT-Antworten)
EMERGENT_LLM_KEY=

# Optional: Skalierende Videoanrufe (>5 Teilnehmer; sonst P2P)
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_UPGRADE_THRESHOLD=5

# Optional: Browser-Push-Notifications (mit `web-push generate-vapid-keys` erzeugen)
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_CLAIM_EMAIL=mailto:admin@deine-klinik.de

# Optional: Error-Monitoring
SENTRY_DSN=
SENTRY_ENV=production
SENTRY_RELEASE=meetflow-v1.0

# Optional: Lizenzpruefung gegen euren License-Server
LICENSE_KEY=
LICENSE_DOMAIN=meetflow.deine-klinik.de
LICENSE_SERVER_URL=
LICENSE_TENANT_ID=

# Optional: Abrechnung
BILLING_CURRENCY=EUR
BILLING_KM_RATE=0.30
EOF
chmod 600 /opt/meetflow/backend/.env
```

> **Sicherheits-Hinweis:** Erzeuge die Secrets mit
> `openssl rand -hex 32` — NIEMALS aus dem Internet kopieren oder erraten.

### Frontend (`/opt/meetflow/frontend/.env`)
```bash
cat > /opt/meetflow/frontend/.env <<'EOF'
REACT_APP_BACKEND_URL=https://meetflow.deine-klinik.de
EOF
```

### Frontend bauen
```bash
cd /opt/meetflow/frontend
yarn build
```

---

## 7. systemd-Services

### Backend
```bash
sudo tee /etc/systemd/system/meetflow-backend.service > /dev/null <<'EOF'
[Unit]
Description=MeetFlow Backend (FastAPI)
After=network.target mongod.service redis-server.service

[Service]
Type=simple
User=meetflow
Group=meetflow
WorkingDirectory=/opt/meetflow/backend
EnvironmentFile=/opt/meetflow/backend/.env
ExecStart=/opt/meetflow/backend/.venv/bin/uvicorn server:app \
          --host 127.0.0.1 --port 8001 --workers 2 \
          --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=5
LimitNOFILE=65535

# Security-Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/meetflow
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now meetflow-backend
sudo systemctl status meetflow-backend
```

### Frontend (statisches Build serven via Caddy — kein systemd noetig)
Das `frontend/build/`-Verzeichnis wird direkt vom Caddy ausgeliefert.

---

## 8. Caddy konfigurieren

```bash
sudo tee /etc/caddy/Caddyfile > /dev/null <<'EOF'
meetflow.deine-klinik.de {
  encode gzip zstd

  # Logs
  log {
    output file /var/log/caddy/meetflow.log {
      roll_size 100mb
      roll_keep 7
    }
  }

  # Security-Headers
  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Content-Type-Options nosniff
    X-Frame-Options DENY
    Referrer-Policy strict-origin-when-cross-origin
    Permissions-Policy "camera=(self), microphone=(self), geolocation=()"
    -Server
  }

  # Backend-API + WebSocket
  reverse_proxy /api/* 127.0.0.1:8001 {
    transport http {
      keepalive 5m
    }
    flush_interval -1   # Wichtig fuer Server-Sent-Events
  }
  reverse_proxy /api/ws/* 127.0.0.1:8001 {
    transport http { keepalive 5m }
    flush_interval -1
  }

  # Frontend (React-SPA)
  root * /opt/meetflow/frontend/build
  try_files {path} /index.html
  file_server

  # Statische Assets: 1 Jahr cachen
  @assets path /static/*
  header @assets Cache-Control "public, max-age=31536000, immutable"
}
EOF

sudo systemctl reload caddy
```

Caddy holt automatisch ein Let's-Encrypt-Zertifikat. Nach ca. 30 Sekunden
sollte `https://meetflow.deine-klinik.de` erreichbar sein.

---

## 9. Initial-Checks

```bash
# Backend antwortet
curl -s http://127.0.0.1:8001/api/health
# -> {"status":"ok",...}

# Datenbank verbunden
curl -s http://127.0.0.1:8001/api/health/db
# -> {"db":"ok"}

# Frontend lokal
curl -sI https://meetflow.deine-klinik.de | head -5
# -> HTTP/2 200, server: Caddy
```

Browser oeffnen, mit `ADMIN_EMAIL` + `ADMIN_PASSWORD` einloggen.
Direkt nach Login: **Verwaltung → Richtlinien → Passwort-Rotation** + Admin-Passwort aendern.

---

## 10. Backups einrichten

### Tagliches MongoDB-Backup
```bash
sudo mkdir -p /var/backups/meetflow
sudo tee /usr/local/bin/meetflow-backup.sh > /dev/null <<'EOF'
#!/bin/bash
set -e
TS=$(date +%Y%m%d-%H%M%S)
DEST="/var/backups/meetflow/$TS"
mkdir -p "$DEST"
mongodump --uri "mongodb://meetflow_app:<APP-PW>@127.0.0.1:27017/meetflow?authSource=meetflow" \
          --gzip --archive="$DEST/meetflow.gz"
# Lokale Frontend-Build und Backend-Code sind im Git — nur die DB ist wirklich kritisch.
# Ueberreste loeschen: Aelter als 30 Tage
find /var/backups/meetflow -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
EOF
sudo chmod +x /usr/local/bin/meetflow-backup.sh

# Cron um 03:00 Uhr nightly
sudo tee /etc/cron.d/meetflow-backup > /dev/null <<'EOF'
0 3 * * * meetflow /usr/local/bin/meetflow-backup.sh >> /var/log/meetflow-backup.log 2>&1
EOF
```

### Off-Site-Backup (DRINGEND EMPFOHLEN)
Hetzner **Storage-Box** ab 4 €/Monat einbinden:
```bash
# In /etc/fstab eintragen, dann mount.
# Im meetflow-backup.sh am Ende ergaenzen:
# rsync -a --delete /var/backups/meetflow/ /mnt/storagebox/meetflow-backups/
```

---

## 11. Update-Prozedur

```bash
sudo -u meetflow bash <<'EOF'
cd /opt/meetflow
git fetch && git pull --ff-only
cd backend && source .venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..
cd frontend && yarn install --frozen-lockfile && yarn build && cd ..
EOF
sudo systemctl restart meetflow-backend
sudo systemctl reload caddy
```

---

## 12. Monitoring + Logs

```bash
# Backend-Logs in Echtzeit
sudo journalctl -u meetflow-backend -f

# Caddy-Logs
sudo tail -f /var/log/caddy/meetflow.log

# Generelle System-Last
htop

# MongoDB-Stats
mongosh --eval 'db.adminCommand("serverStatus").connections'
```

Optional: **Sentry** im `.env` setzen — bekommst dann automatisch alle Fehler
samt Stack-Trace per E-Mail.

---

## 13. Sicherheits-Checkliste vor Live-Gang

- [ ] `ADMIN_PASSWORD` aus `.env` direkt nach Erstanmeldung im UI geaendert
- [ ] `JWT_SECRET` und `SECRET_KEY` mit `openssl rand -hex 32` erzeugt (nicht "secret123")
- [ ] MongoDB lauscht nur auf 127.0.0.1 (nicht 0.0.0.0)
- [ ] Redis lauscht nur auf 127.0.0.1 (Default)
- [ ] UFW ist aktiv mit nur 22/80/443 offen
- [ ] Root-SSH ist deaktiviert
- [ ] Fail2ban laeuft fuer SSH
- [ ] DSGVO-AVV vom Hoster unterschrieben
- [ ] Tagliches Backup laeuft + erste Wiederherstellung getestet
- [ ] Passwort-Policy aktiv (Iter 379) — `password_rotation_months` z.B. auf 6 gesetzt
- [ ] Impressum + Datenschutz unter `/impressum` + `/datenschutz` (App-intern verlinkt)

---

## 14. Troubleshooting

| Problem | Loesung |
|---|---|
| `502 Bad Gateway` | `sudo systemctl status meetflow-backend` — Logs pruefen |
| Login funktioniert nicht | Cookies blockiert? Browser-Konsole pruefen, CORS_ORIGINS pruefen |
| Service-Worker liefert stale `/auth/me` | Browser-Cache + Service-Worker entwerten (Iter 377 Fix sollte das verhindern — pruefen ob Frontend-Build aktuell) |
| TLS-Zertifikat-Fehler | DNS-A-Record pruefen, Port 80 erreichbar? `sudo journalctl -u caddy -f` |
| Hohe RAM-Last | Backend-Worker reduzieren: `--workers 1` in systemd-Unit, oder Server-Upgrade |
| Video-Calls brechen ab | LiveKit aktivieren (siehe `.env`), oder Teilnehmer-Limit reduzieren |

---

## 15. Skalierung bei Wachstum

| Nutzer | Hardware | Anmerkung |
|---|---|---|
| < 50 aktiv | CX22 (2/4) | reicht meistens |
| 50–200 aktiv | CX32 (4/8) | empfohlen — diese Anleitung |
| 200–500 aktiv | CX42 (8/16) + LiveKit | LiveKit unbedingt aktivieren |
| > 500 aktiv | MongoDB Atlas + dedizierter App-Server + LiveKit-Cluster | Architektur-Review noetig |

---

**Fertig.** Bei Fragen die Kommentare in den `.env`-Dateien lesen — alle Variablen sind dort erklaert. Letzte Verifikation:

```bash
sudo systemctl status meetflow-backend caddy mongod redis-server
# Alle 4 sollten "active (running)" zeigen.
```

Viel Erfolg beim Live-Gang!
