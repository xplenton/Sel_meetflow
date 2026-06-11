/**
 * Iter 397 — Catering-Verbrauchs-Historie (Auswertungen / Datenpflege).
 *
 * Tabelle aller verbrauchten Catering-Artikel mit:
 *  - Item-Name + Menge + Einheit
 *  - Lieferdatum + Uhrzeit
 *  - Buchungstitel + Raum/Gebäude
 *  - Anforderer (Name + E-Mail)
 *  - Kostenstelle + Konto
 *  - Status (requested / confirmed / cancelled / completed / rejected)
 *  - Rechnungs-ID + Status (falls aus Catering eine Rechnung erstellt wurde)
 *
 * Filter:
 *  - Zeitraum: Alle / Letzte Woche / Letzter Monat / Benutzerdefiniert (von – bis)
 *  - Status (Multi-Select)
 *  - Volltextsuche über Item, Buchung, Raum, Anforderer
 *
 * CSV-Export (Browser-side via Blob): semikolon-getrennt, UTF-8 BOM für Excel.
 */
import { useState, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, Download, Filter, Calendar, AlertCircle } from 'lucide-react';
import api from '../../lib/api';

const STATUS_LABELS = {
  requested: 'Angefragt',
  confirmed: 'Bestätigt',
  in_preparation: 'In Vorbereitung',
  in_progress: 'In Bearbeitung',
  delivered: 'Geliefert',
  completed: 'Abgeschlossen',
  cancelled: 'Storniert',
  rejected: 'Abgelehnt',
};
const STATUS_COLORS = {
  requested: 'bg-[#F3F4F6] text-[#4B5563]',
  confirmed: 'bg-[#E0EAFC] text-[#1E40AF]',
  in_preparation: 'bg-[#FEF3C7] text-[#92400E]',
  in_progress: 'bg-[#FEF3C7] text-[#92400E]',
  delivered: 'bg-[#D1FAE5] text-[#065F46]',
  completed: 'bg-[#DCFCE7] text-[#166534]',
  cancelled: 'bg-[#FEE2E2] text-[#991B1B]',
  rejected: 'bg-[#FEE2E2] text-[#991B1B]',
};

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

function csvEscape(v) {
  if (v == null) return '';
  const s = String(v);
  if (/[";\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export default function CateringHistoryPanel() {
  // Filter-State
  const [range, setRange] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  // Iter 399 — Default-Status-Filter so gesetzt, dass die Catering-
  // Auswertung mit den erstellten Sammelrechnungen exakt uebereinstimmt:
  // Die Rechnung beruecksichtigt nur Status confirmed/delivered/completed/
  // in_progress (siehe `aggregate_catering_invoice`). Vorher waren alle
  // Status sichtbar inkl. cancelled/rejected → die Summen wichen ab.
  // User kann die ausgeschlossenen Statuses manuell wieder dazuwaehlen.
  const BILLABLE_DEFAULT = ['confirmed', 'delivered', 'completed', 'in_progress'];
  const [statusFilter, setStatusFilter] = useState(new Set(BILLABLE_DEFAULT));
  const [search, setSearch] = useState('');

  const queryParams = useMemo(() => {
    const p = new URLSearchParams();
    p.set('range', range);
    if (range === 'custom') {
      if (dateFrom) p.set('from', dateFrom);
      if (dateTo) p.set('to', dateTo);
    }
    if (statusFilter.size) p.set('status', Array.from(statusFilter).join(','));
    return p.toString();
  }, [range, dateFrom, dateTo, statusFilter]);

  const q = useQuery({
    queryKey: ['analytics', 'catering-history', queryParams],
    queryFn: async () => (await api.get(`/analytics/catering-history?${queryParams}`)).data,
    staleTime: 30_000,
  });

  const rows = q.data?.rows || [];
  const totals = q.data?.totals || {};

  // Client-side text filter on top of server filter
  const filteredRows = useMemo(() => {
    if (!search) return rows;
    const s = search.toLowerCase();
    return rows.filter(r =>
      (r.item_name || '').toLowerCase().includes(s)
      || (r.booking_title || '').toLowerCase().includes(s)
      || (r.resource_name || '').toLowerCase().includes(s)
      || (r.requester_name || '').toLowerCase().includes(s)
      || (r.requester_email || '').toLowerCase().includes(s)
      || (r.cost_center || '').toLowerCase().includes(s)
      || (r.invoice_number || '').toLowerCase().includes(s)
    );
  }, [rows, search]);

  const toggleStatus = (s) => {
    setStatusFilter(prev => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  const exportCsv = useCallback(() => {
    const headers = [
      'Lieferdatum', 'Status', 'Artikel', 'Menge', 'Einheit',
      'Buchung', 'Raum', 'Gebäude', 'Etage',
      'Anforderer', 'E-Mail', 'Kostenstelle', 'Konto',
      'Rechnungs-Nr.', 'Rechnungs-Status', 'Notizen',
    ];
    const lines = [headers.join(';')];
    for (const r of filteredRows) {
      lines.push([
        fmtDate(r.delivery_at),
        STATUS_LABELS[r.status] || r.status,
        r.item_name, r.quantity, r.item_unit,
        r.booking_title, r.resource_name, r.resource_building, r.resource_floor,
        r.requester_name, r.requester_email, r.cost_center, r.account,
        r.invoice_number, r.invoice_status, r.notes,
      ].map(csvEscape).join(';'));
    }
    // BOM für Excel-Encoding
    const blob = new Blob(['\uFEFF' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `catering-historie-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [filteredRows]);

  return (
    <div className="space-y-4" data-testid="catering-history-panel">
      {/* Filter Bar */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#1C1F1D]">
          <Filter className="w-4 h-4" /> Filter
        </div>
        {/* Zeitraum */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-[#6B7280] mr-1">Zeitraum:</span>
          {[
            ['all', 'Alle'],
            ['week', 'Letzte Woche'],
            ['month', 'Letzter Monat'],
            ['custom', 'Benutzerdefiniert'],
          ].map(([k, label]) => (
            <button key={k} onClick={() => setRange(k)}
              className={`px-3 py-1 rounded-full text-xs border transition-colors ${range === k ? 'bg-[#4A5D4E] text-white border-[#4A5D4E]' : 'bg-white text-[#374151] border-[#E2E4E0] hover:bg-[#F3F4F1]'}`}
              data-testid={`cat-range-${k}`}>
              {label}
            </button>
          ))}
          {range === 'custom' && (
            <div className="flex items-center gap-1.5 ml-2">
              <Calendar className="w-3.5 h-3.5 text-[#6B7280]" />
              <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                className="text-xs border border-[#E2E4E0] rounded px-2 py-1" data-testid="cat-date-from" />
              <span className="text-xs text-[#6B7280]">bis</span>
              <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                className="text-xs border border-[#E2E4E0] rounded px-2 py-1" data-testid="cat-date-to" />
            </div>
          )}
        </div>
        {/* Status */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-[#6B7280] mr-1">Status:</span>
          {Object.entries(STATUS_LABELS).map(([k, label]) => (
            <button key={k} onClick={() => toggleStatus(k)}
              className={`px-2.5 py-1 rounded-full text-[11px] border transition-colors ${statusFilter.has(k) ? 'bg-[#4A5D4E] text-white border-[#4A5D4E]' : 'bg-white text-[#374151] border-[#E2E4E0] hover:bg-[#F3F4F1]'}`}
              data-testid={`cat-status-${k}`}>
              {label}{statusFilter.has(k) ? ' ✓' : ''}
            </button>
          ))}
          <button onClick={() => setStatusFilter(new Set(BILLABLE_DEFAULT))} className="text-xs text-[#6B7280] underline hover:text-[#1C1F1D]"
            data-testid="cat-status-reset" title="Auf abrechnungsrelevante Statuses zuruecksetzen (deckungsgleich mit Sammelrechnung)">Standard</button>
          <button onClick={() => setStatusFilter(new Set())} className="text-xs text-[#6B7280] underline hover:text-[#1C1F1D]"
            data-testid="cat-status-clear">Alle</button>
        </div>
        {/* Default-Filter Hinweis */}
        <div className="text-[11px] text-[#6B7280] bg-[#F9F9F8] border border-[#E2E4E0] rounded-md px-2.5 py-1.5 leading-snug">
          <strong>Hinweis:</strong> Standardmäßig sind nur abrechnungsrelevante Statuses (Bestätigt, In Bearbeitung, Geliefert, Abgeschlossen) gewählt — die Zahlen entsprechen damit den erstellten Sammelrechnungen. Klicke „Alle“ um stornierte und abgelehnte Anfragen zusätzlich einzublenden.
        </div>
        {/* Suche + Export */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex-1 min-w-[180px] relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-[#9CA3AF]" />
            <input type="text" placeholder="Suche (Artikel, Buchung, Anforderer …)"
              value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-sm border border-[#E2E4E0] rounded-lg" data-testid="cat-search" />
          </div>
          <button onClick={exportCsv} disabled={filteredRows.length === 0}
            className="px-3 py-1.5 text-xs font-medium bg-[#4A5D4E] hover:bg-[#3a4a3e] text-white rounded-lg flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="cat-export-csv">
            <Download className="w-3.5 h-3.5" /> CSV-Export ({filteredRows.length})
          </button>
        </div>
      </div>

      {/* Totals */}
      {totals.row_count != null && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="cat-totals">
          <div className="bg-white border border-[#E2E4E0] rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-[#6B7280] mb-1">Anfragen</div>
            <div className="text-xl font-light text-[#1C1F1D]">{totals.requests_total}</div>
          </div>
          <div className="bg-white border border-[#E2E4E0] rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-[#6B7280] mb-1">Positionen</div>
            <div className="text-xl font-light text-[#1C1F1D]">{totals.row_count}</div>
          </div>
          <div className="bg-white border border-[#E2E4E0] rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-[#6B7280] mb-1">Gesamtmenge</div>
            <div className="text-xl font-light text-[#1C1F1D]">{totals.total_quantity}</div>
          </div>
          <div className="bg-white border border-[#E2E4E0] rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-[#6B7280] mb-1">Status-Verteilung</div>
            <div className="text-[11px] text-[#374151] leading-tight">
              {Object.entries(totals.by_status || {}).map(([k, v]) => (
                <div key={k}>{STATUS_LABELS[k] || k}: <strong>{v}</strong></div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
        {q.isLoading ? (
          <div className="p-8 text-center text-sm text-[#9CA3AF]">Lade …</div>
        ) : q.isError ? (
          <div className="p-8 text-center text-sm text-[#C87967] flex items-center justify-center gap-2">
            <AlertCircle className="w-4 h-4" /> Fehler beim Laden
          </div>
        ) : filteredRows.length === 0 ? (
          <div className="p-8 text-center text-sm text-[#9CA3AF]">Keine Einträge im gewählten Zeitraum.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-[#F3F4F1] border-b border-[#E2E4E0]">
                <tr className="text-left text-[10px] uppercase tracking-wider text-[#6B7280]">
                  <th className="px-3 py-2">Lieferung</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Artikel</th>
                  <th className="px-3 py-2 text-right">Menge</th>
                  <th className="px-3 py-2">Buchung / Raum</th>
                  <th className="px-3 py-2">Anforderer</th>
                  <th className="px-3 py-2">Kostenstelle</th>
                  <th className="px-3 py-2">Rechnung</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((r, idx) => (
                  <tr key={`${r.request_id}_${r.item_id}_${idx}`} className="border-b border-[#F0F0EE] hover:bg-[#F9FAF7]"
                    data-testid={`cat-row-${idx}`}>
                    <td className="px-3 py-2 text-[#1C1F1D] whitespace-nowrap">{fmtDate(r.delivery_at)}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[r.status] || 'bg-[#F3F4F6] text-[#4B5563]'}`}>
                        {STATUS_LABELS[r.status] || r.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-[#1C1F1D] font-medium">{r.item_name}</td>
                    <td className="px-3 py-2 text-right text-[#1C1F1D]">{r.quantity} {r.item_unit}</td>
                    <td className="px-3 py-2 text-[#374151]">
                      <div className="font-medium">{r.booking_title || '—'}</div>
                      <div className="text-[10px] text-[#6B7280]">
                        {r.resource_name}{r.resource_building ? ` · ${r.resource_building}` : ''}{r.resource_floor ? ` · ${r.resource_floor}` : ''}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-[#374151]">
                      <div>{r.requester_name || '—'}</div>
                      <div className="text-[10px] text-[#6B7280]">{r.requester_email}</div>
                    </td>
                    <td className="px-3 py-2 text-[#374151]">
                      {r.cost_center || '—'}{r.account ? <div className="text-[10px] text-[#6B7280]">{r.account}</div> : null}
                    </td>
                    <td className="px-3 py-2 text-[#374151]">
                      {r.invoice_id ? (
                        <>
                          <div className="font-medium text-[#1E40AF]">{r.invoice_number || r.invoice_id.slice(-8)}</div>
                          <div className="text-[10px] text-[#6B7280]">{r.invoice_status}</div>
                        </>
                      ) : (
                        <span className="text-[10px] text-[#9CA3AF]">keine</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
