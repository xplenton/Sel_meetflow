"""MeetFlow License Server — minimal FastAPI + SQLite.

Run locally:
    pip install -r requirements.txt
    python server.py  # → http://0.0.0.0:8080

Production (Docker):
    docker build -t meetflow-license-server .
    docker run -p 8080:8080 -v $(pwd)/data:/app/data \
        -e ADMIN_TOKEN=ChangeMe! meetflow-license-server

API:
    POST /verify                  → von MeetFlow-Instanzen aufgerufen
    GET  /admin/licenses          → alle Lizenzen (Admin)
    POST /admin/licenses          → neue Lizenz erstellen (Admin)
    PUT  /admin/licenses/{key}    → Lizenz updaten (Admin)
    POST /admin/licenses/{key}/revoke → Lizenz sperren (Admin)
    GET  /admin/licenses/{key}/audit  → Verify-Audit-Log (Admin)

Admin-Auth: Header `X-Admin-Token: <ADMIN_TOKEN>` (env-konfigurierbar).
"""
from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("LICENSE_DB_PATH", "data/licenses.sqlite3")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS licenses (
                license_key   TEXT PRIMARY KEY,
                tenant_id     TEXT NOT NULL,
                customer_name TEXT,
                domain        TEXT,
                valid_until   TEXT NOT NULL,
                fingerprint   TEXT,
                revoked       INTEGER NOT NULL DEFAULT 0,
                notes         TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verify_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key   TEXT NOT NULL,
                fingerprint   TEXT,
                domain        TEXT,
                version       TEXT,
                status        TEXT NOT NULL,
                message       TEXT,
                ip            TEXT,
                at            TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_log_key ON verify_log(license_key);
            CREATE INDEX IF NOT EXISTS idx_log_at ON verify_log(at);
        """)


_init_db()


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class VerifyRequest(BaseModel):
    license_key: str
    fingerprint: str = ""
    tenant_id: Optional[str] = None
    domain: Optional[str] = None
    version: Optional[str] = None


class VerifyResponse(BaseModel):
    status: str
    valid_until: Optional[str] = None
    tenant_id: Optional[str] = None
    message: Optional[str] = None


class LicenseCreate(BaseModel):
    tenant_id: str
    customer_name: Optional[str] = None
    domain: Optional[str] = None
    valid_until: str  # ISO 8601
    notes: Optional[str] = None
    # leer lassen → wird generiert
    license_key: Optional[str] = Field(default=None)


class LicenseUpdate(BaseModel):
    customer_name: Optional[str] = None
    domain: Optional[str] = None
    valid_until: Optional[str] = None
    notes: Optional[str] = None
    fingerprint: Optional[str] = None  # zum Reset bei Hardware-Wechsel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_admin(x_admin_token: str = Header(default="")) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(500, "Server misconfigured: ADMIN_TOKEN missing")
    if not secrets.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(401, "invalid admin token")


def _generate_license_key() -> str:
    """Format: MEETFLOW-XXXX-XXXX-XXXX-XXXX (24 Zeichen)."""
    parts = [secrets.token_hex(2).upper() for _ in range(4)]
    return "MEETFLOW-" + "-".join(parts)


def _log_verify(lic_key: str, req: VerifyRequest, status: str,
                message: Optional[str], ip: Optional[str]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO verify_log "
            "(license_key, fingerprint, domain, version, status, message, ip, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (lic_key, req.fingerprint, req.domain, req.version,
             status, message, ip, _now_iso()),
        )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="MeetFlow License Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest, request: Request):
    """Von MeetFlow aufgerufen — gibt valid/invalid + Ablaufdatum zurück."""
    # Iter 371 — Capture client IP für Audit-Trail. Falls hinter Reverse-Proxy
    # (Caddy/Nginx) → bevorzugt X-Forwarded-For Header.
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM licenses WHERE license_key = ?", (req.license_key,)
        ).fetchone()

    if not row:
        _log_verify(req.license_key, req, "invalid", "unknown license_key", ip)
        return VerifyResponse(status="invalid", message="Lizenz unbekannt")

    if row["revoked"]:
        _log_verify(req.license_key, req, "invalid", "revoked", ip)
        return VerifyResponse(status="invalid", message="Lizenz gesperrt")

    # Hardware-Fingerprint binden: erste Verify schreibt den Fingerprint;
    # spätere Verifies müssen denselben mitsenden.
    if row["fingerprint"]:
        if req.fingerprint and req.fingerprint != row["fingerprint"]:
            _log_verify(req.license_key, req, "invalid",
                        f"fingerprint mismatch (got {req.fingerprint!r})", ip)
            return VerifyResponse(
                status="invalid",
                message="Lizenz an andere Hardware gebunden — bitte Reset im Admin-UI",
            )
    else:
        # First-time bind
        with _conn() as c:
            c.execute(
                "UPDATE licenses SET fingerprint = ?, updated_at = ? WHERE license_key = ?",
                (req.fingerprint or "", _now_iso(), req.license_key),
            )

    # Ablaufdatum
    try:
        valid_until = datetime.fromisoformat(row["valid_until"].replace("Z", "+00:00"))
    except Exception:
        _log_verify(req.license_key, req, "invalid", "invalid valid_until", ip)
        return VerifyResponse(status="invalid", message="Datums-Format invalid")

    if valid_until < datetime.now(timezone.utc):
        _log_verify(req.license_key, req, "invalid",
                    f"expired on {row['valid_until']}", ip)
        return VerifyResponse(
            status="invalid",
            valid_until=row["valid_until"],
            message=f"Lizenz abgelaufen am {valid_until.strftime('%d.%m.%Y')}",
        )

    _log_verify(req.license_key, req, "valid", None, ip)
    return VerifyResponse(
        status="valid",
        valid_until=row["valid_until"],
        tenant_id=row["tenant_id"],
        message=None,
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
@app.get("/admin/licenses", dependencies=[Depends(_require_admin)])
def list_licenses():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM licenses ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/admin/licenses", dependencies=[Depends(_require_admin)])
def create_license(payload: LicenseCreate):
    key = payload.license_key or _generate_license_key()
    now = _now_iso()
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO licenses "
                "(license_key, tenant_id, customer_name, domain, valid_until, "
                " fingerprint, revoked, notes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, '', 0, ?, ?, ?)",
                (key, payload.tenant_id, payload.customer_name, payload.domain,
                 payload.valid_until, payload.notes, now, now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "license_key already exists")
        row = c.execute("SELECT * FROM licenses WHERE license_key = ?", (key,)).fetchone()
    return dict(row)


@app.put("/admin/licenses/{license_key}", dependencies=[Depends(_require_admin)])
def update_license(license_key: str, payload: LicenseUpdate):
    fields = []
    values = []
    for k in ("customer_name", "domain", "valid_until", "notes", "fingerprint"):
        v = getattr(payload, k)
        if v is not None:
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        raise HTTPException(400, "no fields to update")
    fields.append("updated_at = ?")
    values.append(_now_iso())
    values.append(license_key)
    with _conn() as c:
        c.execute(f"UPDATE licenses SET {', '.join(fields)} WHERE license_key = ?", values)
        row = c.execute("SELECT * FROM licenses WHERE license_key = ?", (license_key,)).fetchone()
    if not row:
        raise HTTPException(404, "license not found")
    return dict(row)


@app.post("/admin/licenses/{license_key}/revoke", dependencies=[Depends(_require_admin)])
def revoke_license(license_key: str):
    with _conn() as c:
        c.execute("UPDATE licenses SET revoked = 1, updated_at = ? WHERE license_key = ?",
                  (_now_iso(), license_key))
        row = c.execute("SELECT * FROM licenses WHERE license_key = ?", (license_key,)).fetchone()
    if not row:
        raise HTTPException(404, "license not found")
    return dict(row)


@app.post("/admin/licenses/{license_key}/restore", dependencies=[Depends(_require_admin)])
def restore_license(license_key: str):
    """Stellt eine gesperrte Lizenz wieder her."""
    with _conn() as c:
        c.execute("UPDATE licenses SET revoked = 0, updated_at = ? WHERE license_key = ?",
                  (_now_iso(), license_key))
        row = c.execute("SELECT * FROM licenses WHERE license_key = ?", (license_key,)).fetchone()
    if not row:
        raise HTTPException(404, "license not found")
    return dict(row)


@app.post("/admin/licenses/{license_key}/reset-fingerprint",
          dependencies=[Depends(_require_admin)])
def reset_fingerprint(license_key: str):
    """Setzt Hardware-Fingerprint zurück — Kunde kann sich auf neuem Server bind-en."""
    with _conn() as c:
        c.execute("UPDATE licenses SET fingerprint = '', updated_at = ? WHERE license_key = ?",
                  (_now_iso(), license_key))
        row = c.execute("SELECT * FROM licenses WHERE license_key = ?", (license_key,)).fetchone()
    if not row:
        raise HTTPException(404, "license not found")
    return dict(row)


@app.get("/admin/licenses/{license_key}/audit", dependencies=[Depends(_require_admin)])
def license_audit(license_key: str, limit: int = 100):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM verify_log WHERE license_key = ? "
            "ORDER BY at DESC LIMIT ?",
            (license_key, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0"}


# ---------------------------------------------------------------------------
# Minimal Admin UI (single HTML page, kein React-Bundle nötig)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def admin_ui():
    return HTMLResponse(_ADMIN_HTML)


_ADMIN_HTML = """
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8" />
<title>MeetFlow License Server</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; background: #F0F2EE; color: #1C1F1D; }
  header { background: #2C3E33; color: white; padding: 14px 24px; display: flex; align-items: center; gap: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.1); }
  header h1 { margin: 0; font-size: 17px; font-weight: 600; flex: 1; }
  header .token-input { background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.25); color: white; padding: 6px 10px; border-radius: 6px; font-size: 12px; width: 280px; }
  header .token-input::placeholder { color: rgba(255,255,255,.5); }
  main { padding: 20px 24px; max-width: 1300px; margin: 0 auto; }

  /* Stats grid */
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
  .stat { background: white; border: 1px solid #E2E4E0; border-radius: 8px; padding: 14px 16px; }
  .stat-label { font-size: 11px; color: #6B7280; text-transform: uppercase; font-weight: 600; letter-spacing: .03em; }
  .stat-value { font-size: 26px; font-weight: 700; color: #1C1F1D; margin-top: 4px; }
  .stat.active .stat-value { color: #047857; }
  .stat.warn .stat-value { color: #B45309; }
  .stat.bad .stat-value { color: #B91C1C; }

  .card { background: white; border: 1px solid #E2E4E0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .card h2 { margin: 0 0 12px 0; font-size: 14px; font-weight: 600; color: #1C1F1D; display: flex; align-items: center; gap: 8px; }
  .card h2 .count { background: #F0F2EE; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 500; color: #6B7280; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #F0F2EE; }
  th { background: #FAFBF9; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; color: #4A5D4E; position: sticky; top: 0; }
  tr:hover { background: #FAFBF9; }

  .btn { background: #2C9A6E; color: white; border: 0; padding: 7px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: background .15s; }
  .btn:hover { background: #218252; }
  .btn-sm { padding: 4px 8px; font-size: 11px; }
  .btn-outline { background: white; color: #2C9A6E; border: 1px solid #2C9A6E; }
  .btn-outline:hover { background: #F0FDF4; }
  .btn-danger { background: #DC2626; }
  .btn-danger:hover { background: #B91C1C; }
  .btn-ghost { background: transparent; color: #6B7280; border: 1px solid #D1D5DB; }
  .btn-ghost:hover { background: #F0F2EE; }

  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; letter-spacing: .02em; }
  .badge-ok { background: #D1FAE5; color: #047857; }
  .badge-bad { background: #FEE2E2; color: #B91C1C; }
  .badge-warn { background: #FEF3C7; color: #92400E; }

  input, textarea, select { padding: 7px 10px; border: 1px solid #D1D5DB; border-radius: 6px; font-size: 13px; width: 100%; background: white; font-family: inherit; }
  input:focus { outline: 2px solid #2C9A6E; outline-offset: -1px; border-color: transparent; }
  label { display: block; font-size: 10px; font-weight: 700; color: #6B7280; text-transform: uppercase; letter-spacing: .03em; margin-bottom: 4px; }

  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; align-items: end; }
  .row-actions { display: flex; gap: 4px; flex-wrap: wrap; }
  .key { font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  .key-cell { display: flex; align-items: center; gap: 6px; }
  .copy-btn { background: transparent; border: 0; color: #6B7280; cursor: pointer; padding: 2px 4px; border-radius: 4px; font-size: 11px; }
  .copy-btn:hover { background: #F0F2EE; color: #2C9A6E; }

  /* Toast */
  #toasts { position: fixed; bottom: 20px; right: 20px; display: flex; flex-direction: column; gap: 8px; z-index: 100; }
  .toast { background: white; border-left: 4px solid #2C9A6E; padding: 12px 16px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,.15); animation: slide-in .2s ease-out; font-size: 13px; min-width: 240px; max-width: 380px; }
  .toast.error { border-left-color: #DC2626; }
  .toast.info { border-left-color: #3B82F6; }
  @keyframes slide-in { from { transform: translateX(20px); opacity: 0; } }

  /* Status bar */
  .topbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .topbar input[type="search"] { flex: 1; max-width: 320px; }
  .topbar .right { margin-left: auto; display: flex; align-items: center; gap: 8px; font-size: 12px; color: #6B7280; }

  @media (max-width: 800px) {
    .stats { grid-template-columns: 1fr 1fr; }
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<header>
  <span style="font-size: 22px;">🔐</span>
  <h1>MeetFlow License Server</h1>
  <input id="adminToken" class="token-input" placeholder="X-Admin-Token" autocomplete="off" />
  <button class="btn btn-sm" onclick="loadLicenses()">Laden</button>
</header>
<main>

  <!-- Stats Dashboard -->
  <div class="stats">
    <div class="stat active">
      <div class="stat-label">Aktive Lizenzen</div>
      <div class="stat-value" id="stat-active">—</div>
    </div>
    <div class="stat warn">
      <div class="stat-label">Läuft &lt; 30 Tage ab</div>
      <div class="stat-value" id="stat-expiring">—</div>
    </div>
    <div class="stat bad">
      <div class="stat-label">Abgelaufen</div>
      <div class="stat-value" id="stat-expired">—</div>
    </div>
    <div class="stat bad">
      <div class="stat-label">Gesperrt</div>
      <div class="stat-value" id="stat-revoked">—</div>
    </div>
  </div>

  <!-- Create new license -->
  <div class="card">
    <h2>➕ Neue Lizenz erstellen</h2>
    <div class="grid">
      <div><label>Tenant ID *</label><input id="newTenant" placeholder="klinik-abc" /></div>
      <div><label>Kundenname</label><input id="newCustomer" placeholder="Klinik ABC GmbH" /></div>
      <div><label>Domain</label><input id="newDomain" placeholder="meetflow.klinik-abc.de" /></div>
      <div><label>Gültig bis *</label><input type="date" id="newValidUntil" /></div>
    </div>
    <div style="margin-top: 10px; display: flex; gap: 8px; align-items: end;">
      <div style="flex: 1"><label>Notizen / Vertragsnr.</label><input id="newNotes" placeholder="Vertrag 2026-001 · Standard-Plan" /></div>
      <button class="btn" onclick="createLicense()">Lizenz erstellen</button>
    </div>
  </div>

  <!-- License list -->
  <div class="card">
    <div class="topbar">
      <h2 style="margin: 0;">📋 Lizenzen <span class="count" id="lic-count">0</span></h2>
      <input type="search" id="search" placeholder="Suchen: Key, Tenant, Kunde, Notiz, Fingerprint…" oninput="renderTable()" />
      <div class="right">
        <label style="display: inline-flex; align-items: center; gap: 4px; margin: 0; text-transform: none; font-size: 11px;">
          <input type="checkbox" id="autoRefresh" style="width: auto;" /> Auto-Refresh 30s
        </label>
        <span id="lastUpdate"></span>
      </div>
    </div>
    <div style="overflow-x: auto;">
      <table>
        <thead>
          <tr>
            <th>Lizenz-Key</th>
            <th>Tenant</th>
            <th>Kunde / Notiz</th>
            <th>Gültig bis</th>
            <th>Status</th>
            <th>Fingerprint</th>
            <th>Aktion</th>
          </tr>
        </thead>
        <tbody id="licenseTable"></tbody>
      </table>
    </div>
  </div>
</main>

<div id="toasts"></div>

<script>
const $ = id => document.getElementById(id);
let allLicenses = [];

// Iter 371 — Token in localStorage persistieren, damit Admin sich nicht
// nach jedem Page-Reload neu eintragen muss.
const savedToken = localStorage.getItem('mf_license_admin_token');
if (savedToken) $('adminToken').value = savedToken;
$('adminToken').addEventListener('change', () => {
  localStorage.setItem('mf_license_admin_token', $('adminToken').value);
});

function token() { return $('adminToken').value; }

function toast(message, type = 'success') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = message;
  $('toasts').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      'X-Admin-Token': token(),
      'Content-Type': 'application/json',
    },
  });
  if (!r.ok) {
    const t = await r.text();
    toast('Fehler ' + r.status + ': ' + t, 'error');
    throw new Error(t);
  }
  return r.json();
}

function copy(text, what = 'Lizenz-Key') {
  navigator.clipboard.writeText(text).then(() => toast(what + ' kopiert ✓', 'info'));
}

async function loadLicenses() {
  if (!token()) { toast('Admin-Token eingeben!', 'error'); return; }
  try {
    allLicenses = await api('/admin/licenses');
    updateStats();
    renderTable();
    $('lastUpdate').textContent = 'Stand: ' + new Date().toLocaleTimeString('de-DE');
  } catch { /* error already toasted */ }
}

function updateStats() {
  const today = new Date();
  const in30 = new Date(Date.now() + 30 * 86400000);
  let active = 0, expiring = 0, expired = 0, revoked = 0;
  for (const r of allLicenses) {
    const valid = new Date(r.valid_until);
    if (r.revoked) revoked++;
    else if (valid < today) expired++;
    else if (valid < in30) { active++; expiring++; }
    else active++;
  }
  $('stat-active').textContent = active;
  $('stat-expiring').textContent = expiring;
  $('stat-expired').textContent = expired;
  $('stat-revoked').textContent = revoked;
}

function renderTable() {
  const q = ($('search').value || '').toLowerCase();
  const filtered = !q ? allLicenses : allLicenses.filter(r =>
    [r.license_key, r.tenant_id, r.customer_name, r.domain, r.notes, r.fingerprint]
      .filter(Boolean).some(v => v.toLowerCase().includes(q))
  );
  const today = new Date();
  const in30 = new Date(Date.now() + 30 * 86400000);
  $('lic-count').textContent = filtered.length + (q ? ` / ${allLicenses.length}` : '');
  $('licenseTable').innerHTML = filtered.length === 0
    ? '<tr><td colspan="7" style="padding: 32px; text-align: center; color: #9CA3AF;">Keine Lizenzen gefunden.</td></tr>'
    : filtered.map(r => {
        const valid = new Date(r.valid_until);
        let badge;
        if (r.revoked) badge = '<span class="badge badge-bad">gesperrt</span>';
        else if (valid < today) badge = '<span class="badge badge-bad">abgelaufen</span>';
        else if (valid < in30) badge = '<span class="badge badge-warn">läuft bald ab</span>';
        else badge = '<span class="badge badge-ok">aktiv</span>';
        const notes = r.notes ? `<div style="font-size: 11px; color: #6B7280; margin-top: 2px;">${escapeHtml(r.notes)}</div>` : '';
        return `<tr>
          <td>
            <div class="key-cell">
              <span class="key">${r.license_key}</span>
              <button class="copy-btn" onclick="copy('${r.license_key}')" title="In Zwischenablage kopieren">⎘</button>
            </div>
            ${r.domain ? `<div style="font-size: 11px; color: #6B7280; margin-top: 2px;">${escapeHtml(r.domain)}</div>` : ''}
          </td>
          <td>${escapeHtml(r.tenant_id || '')}</td>
          <td>${escapeHtml(r.customer_name || '—')}${notes}</td>
          <td class="key">${r.valid_until ? r.valid_until.slice(0,10) : '—'}</td>
          <td>${badge}</td>
          <td class="key">${r.fingerprint || '<i style="color:#9CA3AF">noch nicht gebunden</i>'}</td>
          <td class="row-actions">
            <button class="btn btn-sm btn-outline" onclick="extendLicense('${r.license_key}')">+1 Jahr</button>
            ${r.revoked
              ? `<button class="btn btn-sm" onclick="restoreLicense('${r.license_key}')">Reaktivieren</button>`
              : `<button class="btn btn-sm btn-danger" onclick="revokeLicense('${r.license_key}')">Sperren</button>`}
            ${r.fingerprint ? `<button class="btn btn-sm btn-ghost" onclick="resetFp('${r.license_key}')">Reset HW</button>` : ''}
            <button class="btn btn-sm btn-ghost" onclick="showAudit('${r.license_key}')">Audit</button>
          </td>
        </tr>`;
      }).join('');
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

async function createLicense() {
  const validUntil = $('newValidUntil').value;
  if (!$('newTenant').value || !validUntil) {
    toast('Tenant ID und Gültig-bis sind Pflicht.', 'error');
    return;
  }
  const created = await api('/admin/licenses', {
    method: 'POST',
    body: JSON.stringify({
      tenant_id: $('newTenant').value,
      customer_name: $('newCustomer').value || null,
      domain: $('newDomain').value || null,
      notes: $('newNotes').value || null,
      valid_until: validUntil + 'T23:59:59Z',
    }),
  });
  copy(created.license_key, 'Neuer Lizenz-Key');
  toast(`Lizenz ${created.license_key} erstellt und kopiert`);
  ['newTenant','newCustomer','newDomain','newNotes','newValidUntil'].forEach(id => $(id).value = '');
  loadLicenses();
}

async function revokeLicense(key) {
  if (!confirm('Lizenz ' + key + ' sperren?\\n\\nKunde verliert sofort den Zugriff nach dem nächsten Heartbeat (max 6 Stunden).')) return;
  await api('/admin/licenses/' + key + '/revoke', { method: 'POST' });
  toast('Lizenz gesperrt');
  loadLicenses();
}

async function restoreLicense(key) {
  await api('/admin/licenses/' + key + '/restore', { method: 'POST' });
  toast('Lizenz reaktiviert');
  loadLicenses();
}

async function resetFp(key) {
  if (!confirm('Hardware-Fingerprint für ' + key + ' zurücksetzen?\\n\\nKunde kann sich danach auf einem NEUEN Server neu bind-en (z. B. nach Hardware-Tausch).')) return;
  await api('/admin/licenses/' + key + '/reset-fingerprint', { method: 'POST' });
  toast('Hardware-Bindung zurückgesetzt');
  loadLicenses();
}

async function extendLicense(key) {
  const lic = allLicenses.find(r => r.license_key === key);
  if (!lic) return;
  const cur = new Date(lic.valid_until);
  const next = new Date(cur.getFullYear() + 1, cur.getMonth(), cur.getDate(), 23, 59, 59);
  await api('/admin/licenses/' + key, {
    method: 'PUT',
    body: JSON.stringify({ valid_until: next.toISOString() }),
  });
  toast(`+ 1 Jahr: gültig bis ${next.toISOString().slice(0,10)}`);
  loadLicenses();
}

async function showAudit(key) {
  const rows = await api('/admin/licenses/' + key + '/audit?limit=200');
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:9999;padding:24px';
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  const csvHref = 'data:text/csv;charset=utf-8,' + encodeURIComponent(
    'Timestamp,Status,Fingerprint,Domain,Version,IP,Message\\n' +
    rows.map(r => [r.at, r.status, r.fingerprint||'', r.domain||'', r.version||'', r.ip||'', (r.message||'').replace(/,/g,';')].join(',')).join('\\n')
  );
  modal.setAttribute('data-modal', '1');
  modal.innerHTML = `
    <div style="background:white;border-radius:8px;max-width:1100px;width:100%;max-height:90vh;display:flex;flex-direction:column">
      <div style="padding:14px 18px;border-bottom:1px solid #E2E4E0;display:flex;align-items:center;gap:10px">
        <strong style="flex:1;font-size:14px">📜 Audit-Log · <span class="key">${key}</span></strong>
        <input id="auditFilter" placeholder="Filter…" style="width:200px" />
        <a href="${csvHref}" download="audit-${key}.csv" class="btn btn-sm btn-outline" style="text-decoration:none">CSV</a>
        <button class="btn btn-sm btn-ghost" onclick="this.closest('[data-modal]').remove()">Schließen</button>
      </div>
      <div style="overflow:auto;flex:1">
        <table style="width:100%;font-size:12px">
          <thead><tr>
            <th>Zeitpunkt (UTC)</th><th>Status</th><th>Fingerprint</th><th>Domain</th><th>Version</th><th>IP</th><th>Nachricht</th>
          </tr></thead>
          <tbody id="auditBody">
            ${rows.map(r => `<tr>
              <td class="key">${r.at.slice(0,19).replace('T',' ')}</td>
              <td>${r.status === 'valid' ? '<span class="badge badge-ok">valid</span>' : '<span class="badge badge-bad">invalid</span>'}</td>
              <td class="key">${escapeHtml(r.fingerprint || '—')}</td>
              <td>${escapeHtml(r.domain || '')}</td>
              <td>${escapeHtml(r.version || '')}</td>
              <td class="key">${escapeHtml(r.ip || '')}</td>
              <td>${escapeHtml(r.message || '')}</td>
            </tr>`).join('') || '<tr><td colspan="7" style="padding:32px;text-align:center;color:#9CA3AF">Noch keine Verify-Versuche</td></tr>'}
          </tbody>
        </table>
      </div>
      <div style="padding:8px 18px;border-top:1px solid #F0F2EE;font-size:11px;color:#6B7280">
        ${rows.length} Einträge${rows[0] ? ' · letzter Verify ' + rows[0].at.slice(0,19).replace('T',' ') + ' UTC' : ''}
      </div>
    </div>`;
  document.body.appendChild(modal);
  modal.querySelector('#auditFilter').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    modal.querySelectorAll('#auditBody tr').forEach(tr => {
      tr.style.display = !q || tr.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

// Auto-refresh
setInterval(() => {
  if ($('autoRefresh').checked && token()) loadLicenses();
}, 30_000);

// Initial Load wenn Token da
if (token()) loadLicenses();
</script>
</body></html>
"""


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
