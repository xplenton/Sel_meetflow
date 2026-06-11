import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import api from '../../lib/api';

/**
 * Iter 387 — Filetransfer Admin-Übersicht (Nutzungs-Auswertung).
 * Verschoben aus `pages/FiletransferPage.js` in den zentralen Analytics-
 * Bereich, damit alle auswertbaren Daten an einem Ort liegen.
 *
 * Zeigt: Transfer-Zähler nach Status, Speicher-Health, Volumen,
 * Verschlüsselungs-Status sowie die letzten 50 Transfers (read-only).
 */

const STATUS_LABEL = {
  draft: 'Entwurf', active: 'Aktiv', expired: 'Abgelaufen',
  revoked: 'Widerrufen', downloaded: 'Heruntergeladen',
};
const STATUS_COLOR = {
  draft: 'bg-[#D4A373]/15 text-[#D4A373]',
  active: 'bg-[#6B8E23]/15 text-[#6B8E23]',
  expired: 'bg-[#9CA3AF]/15 text-[#6B7280]',
  revoked: 'bg-[#C87967]/15 text-[#C87967]',
  downloaded: 'bg-[#4A5D4E]/15 text-[#4A5D4E]',
};

function fmtBytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB']; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
function fmtDate(iso) { return iso ? new Date(iso).toLocaleString('de-DE') : ''; }

export default function FiletransferAdminOverview() {
  const [data, setData] = useState(null);
  const [transfers, setTransfers] = useState([]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.get('/filetransfer/admin/overview').then(r => r.data),
      api.get('/filetransfer/admin/transfers').then(r => r.data),
    ]).then(([ov, tr]) => { if (alive) { setData(ov); setTransfers(tr); } })
      .catch(err => toast.error(err?.response?.data?.detail || 'Fehler'));
    return () => { alive = false; };
  }, []);

  if (!data) return <div className="text-center py-12 text-[#9CA3AF] text-sm">Lade...</div>;
  const s = data.stats || {};
  const h = data.storage?.health || {};
  return (
    <div className="space-y-4" data-testid="ft-admin-overview">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Stat label="Gesamt" value={s.total_transfers} />
        <Stat label="Aktiv" value={s.active} />
        <Stat label="Entwurf" value={s.draft} />
        <Stat label="Widerrufen" value={s.revoked} />
        <Stat label="Abgelaufen" value={s.expired} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-4">
          <p className="text-xs font-semibold text-[#6B7280] uppercase mb-2">Speicher-Status</p>
          <p className="text-xs"><strong>Provider:</strong> {data.storage?.settings?.target}</p>
          <p className="text-xs"><strong>Pfad:</strong> {h.root}</p>
          <p className="text-xs"><strong>Frei:</strong> {fmtBytes(h.free_bytes)} / {fmtBytes(h.total_bytes)}</p>
          <p className="text-xs"><strong>Status:</strong> {h.ok ? <span className="text-[#6B8E23]">OK</span> : <span className="text-[#C87967]">Fehler: {h.error || '?'}</span>}</p>
          {data.storage?.settings?._degraded && (
            <p className="text-[11px] text-[#C87967] mt-1">⚠ Fallback aktiv: {data.storage.settings._degraded_reason}</p>
          )}
        </div>
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-4">
          <p className="text-xs font-semibold text-[#6B7280] uppercase mb-2">Volumen</p>
          <p className="text-xs"><strong>Gesamt:</strong> {fmtBytes(s.total_size_bytes)}</p>
          <p className="text-xs">
            <strong>Encryption:</strong>{' '}
            {data.storage?.settings?.target === 'network_share'
              ? <span className="text-[#6B8E23]">aktiv (Pflicht)</span>
              : (data.storage?.settings?.encryption_required_local
                ? <span className="text-[#6B8E23]">lokal verschlüsselt</span>
                : <span className="text-[#9CA3AF]">lokal Klartext</span>)}
          </p>
        </div>
      </div>
      <div>
        <h3 className="text-xs font-semibold text-[#6B7280] uppercase mb-2">Alle Transfers</h3>
        <div className="bg-white border border-[#E2E4E0] rounded-xl divide-y divide-[#E2E4E0]">
          {transfers.slice(0, 50).map(t => (
            <div key={t.transfer_id} className="flex items-center gap-2 p-2 text-xs" data-testid={`ft-admin-row-${t.transfer_id}`}>
              <span className={`text-[9px] px-1.5 rounded-full ${STATUS_COLOR[t.status] || STATUS_COLOR.draft}`}>{STATUS_LABEL[t.status]}</span>
              <span className="truncate flex-1">{t.message || '(ohne Nachricht)'}</span>
              <span className="text-[#9CA3AF]">{t.owner_name}</span>
              <span className="text-[#9CA3AF]">{fmtDate(t.created_at)}</span>
              <span className="text-[#9CA3AF]">{fmtBytes(t.total_size_bytes)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-3 text-center">
      <p className="text-[10px] text-[#9CA3AF] uppercase">{label}</p>
      <p className="text-xl font-semibold text-[#1C1F1D]">{value || 0}</p>
    </div>
  );
}
