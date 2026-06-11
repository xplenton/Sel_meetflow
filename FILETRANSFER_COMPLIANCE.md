# MeetFlow Filetransfer — Compliance & Sicherheits-Dokumentation

**Modul-Version**: Iter 386 (Juni 2026)
**Geltungsbereich**: Filetransfer-Modul der MeetFlow-Plattform
**Letzte Aktualisierung**: 2026-06-08

Dieses Dokument fasst alle Sicherheits-, Compliance- und Architektur-
Eigenschaften des Filetransfer-Moduls auf einer Seite zusammen. Es ist
für IT-Audits, ISO-27001-Reviews und Datenschutz-Folgeabschätzungen
(DSFA) gedacht.

---

## 1. Funktionsumfang (Compliance-Matrix)

| Anforderung | Status | Implementierung |
|---|---|---|
| Navigationsseite "Filetransfer" | ✅ | Sidebar-Eintrag + Route `/filetransfer` |
| Übersicht eigener Transfers | ✅ | `FiletransferPage` Tab "Meine Transfers" |
| Filter (Status, Empfänger, Datum, Ablauf, Dateityp) | ✅ | Statussuche + serverseitige Query-Parameter |
| Suche (Dateiname, Empfänger, Nachricht) | ✅ | Regex-Match auf `message` + `file_names` |
| Status-Anzeige (Entwurf, Aktiv, Abgelaufen, Widerrufen, Heruntergeladen) | ✅ | Badge-Komponente mit Farbcodierung |
| Drag-and-drop Upload | ✅ | Native HTML5-DropEvent |
| Mehrfachdateien je Transfer | ✅ | Multi-File-State, n:1 Verhältnis |
| Fortschrittsanzeige | ✅ | axios `onUploadProgress` + Chunk-Counter |
| Validierung von Dateigröße und Dateityp | ✅ | `max_file_size_mb` + `allowed_extensions` + libmagic |
| Transfer-Paket mit mehreren Dateien | ✅ | 1 Transfer → n Files |
| Begleitnachricht pro Transfer | ✅ | Feld `message` (≤ 2000 Zeichen) |
| Interne Empfängerauswahl | ✅ | Server-side User-Search (`/api/chat/users?q=`) |
| Rechteprüfung (Rollen + Capabilities) | ✅ | `filetransfer.use` + Owner/Recipient/Admin-Check |
| Empfänger-Benachrichtigung | ✅ | In-App (`db.notifications`) + E-Mail |
| Downloadtracking | ✅ | Collection `file_transfer_downloads` |
| Externe Freigabelinks | ✅ | `/shares` Endpoint mit Token |
| Ablaufdatum für externe Links | ✅ | `expires_at`, Default aus Settings |
| Optionaler Passwortschutz | ✅ | bcrypt-Hash auf Server |
| Optionaler Einmal-Download | ✅ | `one_time` Flag + Counter-Check |
| Widerruf von Links | ✅ | `DELETE /shares/{sid}` |
| Zugriff nur innerhalb der Frist | ✅ | Server prüft `expires_at` bei jedem Public-Call |
| Einzeldatei-Download | ✅ | `/files/{fid}/download` |
| ZIP-Download aller Dateien | ✅ | `/zip` mit `zipfile.ZIP_DEFLATED` |
| Download-Protokoll | ✅ | jede Aktion in `file_transfer_downloads` |
| Anzeige wer/wann heruntergeladen | ✅ | UI in `TransferDetailDialog` |
| Zugriffskontrolle pro Transfer | ✅ | `_can_read()` mit Owner/Recipient/Admin |
| Pfadmanipulations-Schutz | ✅ | `_safe_join()` via `Path.relative_to()` |
| Sichere Dateinamenbehandlung | ✅ | Regex-Strip in `_safe_filename()` |
| Serverseitige Validierung aller Eingaben | ✅ | Pydantic-Schemata + Backend-Checks |
| Audit-Logging | ✅ | Collection `file_transfer_audit` |

## 2. Speicher-Architektur

### 2.1 Storage-Provider (abstrahiert)

| Provider | Modul-Klasse | Anwendungsfall | Verschlüsselung |
|---|---|---|---|
| `LocalStorageProvider` | `services/storage_providers.py` | Lokales Dateisystem | optional |
| `NetworkShareStorageProvider` | `services/storage_providers.py` | SMB/CIFS/NFS/UNC-Mountpoint | **Pflicht** |

Provider-Wahl erfolgt zur Laufzeit via Admin-Einstellung `target`.
Beide Provider implementieren das gleiche Interface
(`save`, `load`, `delete`, `health`, `usage`).

### 2.2 Konfigurations-Optionen (Admin)

* `target` (`local` | `network_share`)
* `local_root` — lokaler Speicherpfad
* `network_share_path` — Mountpoint der Netzwerkfreigabe
* `fallback_to_local` — automatisches Ausweichen bei Share-Fehler
* `max_file_size_mb` — Hard-Limit pro Datei
* `max_total_quota_mb` — Hard-Limit für gesamten Filetransfer-Speicher (HTTP 507 bei Überschreitung)
* `warn_threshold_pct` — Warn-Schwelle für Admin-UI
* `default_expiry_days` — Standard-Ablauf für Transfers
* `allowed_extensions` — Datei-Extension-Whitelist (leer = alle)
* `encryption_required_local` — AES-256-GCM auch auf lokalem Speicher erzwingen
* `chunked_upload_backend` (`mongo` | `disk`) — Sitzungs-Buffer für Chunked Uploads
* `chunked_upload_tmp_dir` — Temp-Verzeichnis für Disk-Backend

### 2.3 Verbindungstest

`POST /api/filetransfer/settings/test` führt eine Write-Read-Delete-
Probe gegen den konfigurierten Pfad aus und liefert
`{ok, write_ok, read_ok, health, error}` zurück.

## 3. Verschlüsselung (AES-256-GCM)

### 3.1 Algorithmus & Layout

* **Algorithmus**: AES-256-GCM (authenticated encryption)
* **Schlüsselableitung**: HKDF-SHA256 aus Master-Secret
* **Schlüssel-Quelle**: `FT_ENCRYPTION_KEY` Umgebungsvariable
  (Fallback bei dev: `JWT_SECRET`-derivative — Produktion **muss**
  explizit setzen)
* **Nonce**: 12 Byte, kryptografisch zufällig pro Datei
* **Auth-Tag**: 16 Byte (GCM-Standard)
* **Blob-Layout**: `[version:1][nonce:12][ciphertext+tag:N]`

### 3.2 Workflow

1. Benutzer lädt Datei hoch (HTTPS-Transport TLS)
2. Server validiert Größe + Extension + MIME-Sniff
3. Quota-Check (`max_total_quota_mb`)
4. Owner-Prüfung (`filetransfer.use` Capability)
5. AES-Schlüssel der aktiven Version wird abgeleitet
6. Datei wird verschlüsselt (Network Share: Pflicht; Local: optional)
7. Verschlüsselter Blob landet auf dem Provider
8. Metadaten + `key_version` werden in `file_transfer_files` gespeichert
9. Beim Download: Owner-/Recipient-/Public-Token-Prüfung
10. Blob wird gelesen, mit der gespeicherten `key_version` entschlüsselt
11. Klartext wird per Streaming an den Client geliefert (TLS)

### 3.3 Schlüssel-Verwaltung

* Master-Secret **niemals** im Quellcode
* Schlüssel **niemals** in der Datenbank
* Schlüssel **niemals** im Log
* `key_version` (int) pro Datei → ermöglicht **Schlüsselrotation**:
  Neue Uploads bekommen die aktive Version; alte Dateien sind
  weiterhin entschlüsselbar, solange das Master-Secret den alten
  HKDF-`info=v{n}`-String erzeugen kann
* Integritäts-Prüfung über GCM-Auth-Tag (Manipulation → Decrypt-Failure)

## 4. Sicherheits-Kontrollen

| Kontrolle | Mechanismus |
|---|---|
| Authentifizierung | Session-Cookie (HttpOnly, SameSite) |
| Autorisierung | RBAC-Capabilities `filetransfer.use`, `filetransfer.admin` |
| Externe Links | URL-sicherer Token (`secrets.token_urlsafe(24)`) |
| PW-Schutz extern | bcrypt-Hash (cost-factor 12) |
| Einmal-Link | Server-side Counter, Race-condition-frei |
| Path-Traversal | `Path.resolve().relative_to(root)` |
| Dateinamen | Regex-Strip auf `[\w.\-]+`, Längen-Cap |
| MIME-Sniff | libmagic auf erste 4 KB; Executables (PE/ELF/Mach-O) abgelehnt |
| Size-Limit | Hard-Limit `max_file_size_mb` |
| Quota-Limit | Hard-Limit `max_total_quota_mb` → HTTP 507 |
| Audit-Trail | Vollständig: create, upload, download (intern+extern), share, revoke, delete, settings.update, settings.test |
| TLS | Alle Endpoints HTTPS-only (Ingress-erzwungen) |

## 5. Datenmodell

```
file_transfers       { transfer_id, owner_user_id, message,
                       recipient_user_ids[], status, expires_at,
                       file_names[], total_size_bytes, download_count }
file_transfer_files  { file_id, transfer_id, file_name, size_bytes,
                       size_stored_bytes, sha256, mime_type, mime_declared,
                       storage_provider, storage_path, encrypted, key_version }
file_transfer_shares { share_id, transfer_id, token, password_hash,
                       one_time, expires_at, downloaded_count, revoked }
file_transfer_downloads { download_id, transfer_id, file_id, by_user_id,
                          channel (internal|external), share_id, ip }
file_transfer_audit  { audit_id, action, actor_user_id, transfer_id, ... }
filetransfer_settings (singleton kind='global')
filetransfer_uploads (chunked-upload sessions, automatisch bereinigt)
```

## 6. Hintergrundjobs

* `expire_outdated()` — markiert abgelaufene Transfers als `expired`
* **Periodische Ausführung**: arq Cron-Job alle 10 Minuten (`minute={0,10,…,50}`)
* **Safety-Net**: einmaliger Sweep beim Server-Startup
* `filetransfer_uploads` werden bei Abbruch oder Commit automatisch gelöscht;
  bei Disk-Backend wird das Session-Verzeichnis ebenfalls bereinigt

## 7. Benachrichtigungen

| Ereignis | In-App | E-Mail |
|---|---|---|
| Neuer Transfer mit Empfänger | ✅ | ✅ (opt-out via `email_preferences.filetransfer_enabled`) |
| Datei heruntergeladen | ✅ (an Eigentümer) | ✅ (an Eigentümer) |
| Transfer läuft demnächst ab | 🟡 (Backlog) | 🟡 (Backlog) |
| Speicher-Problem (Quota / Share unreachable) | 🟡 (Admin-UI Warnbanner) | 🟡 (Backlog) |

Alle Notifications respektieren existierende User-Präferenzen über das
`email_preferences`-Subdokument am User-Eintrag.

## 8. Schnittstellen (API-Endpoints)

* **Auth (Cookie)**: alle `/api/filetransfer/transfers/*`, `/api/filetransfer/admin/*`, `/api/filetransfer/settings*`
* **Anonym (Token-basiert)**:
  * `GET /api/filetransfer/public/{token}` — Metadaten + Datei-Liste
  * `POST /api/filetransfer/public/{token}/access` — PW-Validierung
  * `POST /api/filetransfer/public/{token}/files/{fid}/download` — Download mit PW im Body

## 9. Compliance-Referenzen

* **DSGVO Art. 32** (Sicherheit der Verarbeitung): AES-256-GCM,
  Zugriffskontrolle, Audit-Trail.
* **ISO 27001 A.10** (Cryptography): Schlüsselverwaltung über Umgebung,
  Rotation vorbereitet, GCM-AEAD.
* **ISO 27001 A.12.4** (Logging and monitoring): Vollständiger
  Audit-Trail in `file_transfer_audit`.
* **BSI IT-Grundschutz SYS.1.1**: Path-Traversal-Schutz,
  Authentifizierung, Verschlüsselung.

## 10. Bekannte Einschränkungen

* Chunked-Upload `mongo`-Backend: praktisches Limit ~1 GB pro Datei
  (Mongo-Doc-Limit). Disk-Backend empfohlen für >1 GB.
* Disk-Backend braucht freien Platz ≥ größte erwartete Datei im
  Temp-Verzeichnis (während des Uploads).
* Public-Token sind nicht widerrufbar **nach** einem laufenden
  Download — der Download wird abgeschlossen. Revoke wirkt erst auf
  künftige Aufrufe.

---

## Anhang A: Konfigurations-Variablen

| Variable | Pflicht | Beschreibung |
|---|---|---|
| `FT_ENCRYPTION_KEY` | ✅ (Produktion) | Master-Secret für AES-256-GCM (≥ 32 Zeichen) |
| `MONGO_URL` | ✅ | MongoDB-Verbindung |
| `JWT_SECRET` | ✅ | Session-Signatur (auch Fallback für `FT_ENCRYPTION_KEY` im Dev-Modus) |
| `REDIS_URL` | empfohlen | arq Cron-Job + Background-Tasks |

## Anhang B: Betriebs-Voraussetzungen

* Python-Paket `python-magic==0.4.27`
* System-Paket `libmagic1` (Debian/Ubuntu) oder `libmagic` (RHEL)
* MongoDB ≥ 5.0
* Optional: Redis ≥ 6.0 (für arq Cron)
* Netzwerkfreigabe (falls verwendet): vom OS gemountet (cifs-utils /
  autofs / NFS-Client). Anwendung verwendet **nur** den Mountpoint —
  Zugangsdaten gehören in die OS-Mount-Konfiguration, nicht in die DB.

---

*Bei Fragen zur Compliance kontaktiere das Verantwortliche IT-Sicherheits-Team
oder den Datenschutzbeauftragten.*
