import { useEffect, useState } from 'react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { FileDown, Settings, Activity } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { openAuthedFile, downloadAuthedFile } from '../../lib/authedDownload';

/**
 * Auslastungs-Dashboard + ERP-Export + Sammelrechnung + Upload-Limits +
 * Sub-Utilization. Komplett admin-only — eingebettet in Verwaltung -> Ressourcen.
 */
export default function ResourceReportsPanel() {
  const [data, setData] = useState(null);

  const load = async () => {
    try {
      const { data: d } = await api.get('/resources/dashboard/overview?days=90');
      setData(d);
    } catch { setData(null); }
  };
  useEffect(() => { load(); }, []);

  if (!data) return <div className="text-sm text-[#9CA3AF] text-center py-12">Lade Statistiken …</div>;

  // Iter 324 — All downloads must go through the JWT-aware blob helper.
  // The previous `window.open` opened a new tab without the Authorization
  // header → backend returned 401 and the tab stayed blank.
  const downloadAggregate = (costCenter) => {
    const params = {};
    if (costCenter) params.cost_center = costCenter;
    return openAuthedFile('/catering-requests/invoices/aggregate.pdf', params);
  };
  const downloadErp = (format) => {
    return downloadAuthedFile(
      '/resource-bookings/export/erp.csv',
      { days: 90, format },
      `resource-bookings-${format}-90d.csv`,
    );
  };

  return (
    <div className="space-y-4" data-testid="resource-reports-panel">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-4"><div className="text-xs text-[#6B7280]">Räume</div><div className="text-2xl font-semibold">{data.resources_by_type.room || 0}</div></Card>
        <Card className="p-4"><div className="text-xs text-[#6B7280]">Arbeitsplätze</div><div className="text-2xl font-semibold">{data.resources_by_type.desk || 0}</div></Card>
        <Card className="p-4"><div className="text-xs text-[#6B7280]">Fahrzeuge</div><div className="text-2xl font-semibold">{data.resources_by_type.vehicle || 0}</div></Card>
        <Card className="p-4">
          <div className="text-xs text-[#6B7280]">Catering-Umsatz</div>
          <div className="text-2xl font-semibold">{data.catering.estimated_revenue.toFixed(2)} EUR</div>
          <div className="text-[10px] text-[#9CA3AF]">{data.catering.request_count} Anfragen · letzte {data.window_days} Tage</div>
        </Card>
      </div>

      <Card className="p-4">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <div className="text-sm font-medium">Sammelrechnung &amp; ERP-Export</div>
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" variant="outline" onClick={() => downloadAggregate(null)} data-testid="aggregate-pdf-all">
              PDF (alle Kostenstellen)
            </Button>
            <Button size="sm" variant="outline" onClick={() => downloadErp('datev')} data-testid="erp-export-datev">
              <FileDown className="w-3 h-3 mr-1" />DATEV-CSV
            </Button>
            <Button size="sm" variant="outline" onClick={() => downloadErp('generic')} data-testid="erp-export-generic">
              <FileDown className="w-3 h-3 mr-1" />ERP-CSV (generisch)
            </Button>
          </div>
        </div>
        <div className="text-xs text-[#6B7280]">Itemisiert nach Artikel, Mengen aggregiert. DATEV-Export enthaelt nur Catering-Rechnungen mit Freigabe.</div>
      </Card>

      <UploadLimitsPanel />
      <SubUtilizationPanel />
      <NoShowDepartmentPanel />

      <Card className="p-4">
        <div className="text-sm font-medium mb-2">Buchungen nach Status (letzte {data.window_days} Tage)</div>
        <div className="flex gap-3 flex-wrap">
          {Object.entries(data.bookings_by_status || {}).map(([k, v]) => (
            <div key={k} className="text-xs"><BookingStatus status={k} /> <span className="ml-1 font-medium">{v}</span></div>
          ))}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-sm font-medium mb-2">Top 5 ausgelastete Ressourcen</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[400px]">
            <thead><tr className="text-xs text-[#6B7280] text-left"><th className="py-1">Name</th><th>Typ</th><th>Stunden</th><th>Buchungen</th></tr></thead>
            <tbody>
              {data.top_resources.map(r => (
                <tr key={r.resource_id} className="border-t border-[#E2E4E0]">
                  <td className="py-1">{r.name}</td>
                  <td>{r.type}</td>
                  <td>{r.hours}</td>
                  <td>{r.bookings}</td>
                </tr>
              ))}
              {!data.top_resources.length && <tr><td colSpan={4} className="py-4 text-center text-[#9CA3AF]">Keine Daten.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}


function BookingStatus({ status }) {
  const map = {
    confirmed: { label: 'Bestätigt', cls: 'border-emerald-300 bg-emerald-50 text-emerald-700' },
    pending_approval: { label: 'Wartet auf Freigabe', cls: 'border-amber-300 bg-amber-50 text-amber-700' },
    cancelled: { label: 'Storniert', cls: 'border-zinc-300 bg-zinc-50 text-zinc-500' },
    completed: { label: 'Abgeschlossen', cls: 'border-blue-300 bg-blue-50 text-blue-700' },
    no_show: { label: 'No-Show', cls: 'border-rose-300 bg-rose-50 text-rose-700' },
  };
  const m = map[status] || map.confirmed;
  return <Badge variant="outline" className={`${m.cls} text-[10px]`}>{m.label}</Badge>;
}


function UploadLimitsPanel() {
  const [cfg, setCfg] = useState(null);
  const [maxMb, setMaxMb] = useState(10);
  const [mimes, setMimes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/resource-upload-config');
        setCfg(data);
        setMaxMb(data.max_size_mb);
        setMimes((data.allowed_mimes || []).join(', '));
      } catch { /* ignore */ }
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const list = mimes.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
      const { data } = await api.put('/resource-upload-config', {
        max_size_mb: Number(maxMb),
        allowed_mimes: list.length ? list : null,
      });
      setCfg(data);
      toast.success('Upload-Limits gespeichert');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    } finally {
      setSaving(false);
    }
  };

  if (!cfg) return null;
  return (
    <Card className="p-4" data-testid="upload-limits-panel">
      <div className="flex items-center gap-2 mb-2">
        <Settings className="w-4 h-4 text-[#4A5D4E]" />
        <div className="text-sm font-medium">Upload-Limits für Catering-Anhänge</div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-[180px_1fr_auto] gap-3 items-end">
        <div>
          <Label className="text-xs">Max. Größe (MB)</Label>
          <Input type="number" min={1} max={100} value={maxMb}
                 onChange={e => setMaxMb(e.target.value)}
                 data-testid="upload-max-mb-input" />
        </div>
        <div>
          <Label className="text-xs">Erlaubte MIME-Typen (komma-getrennt)</Label>
          <Input value={mimes} onChange={e => setMimes(e.target.value)}
                 placeholder="application/pdf, image/png, image/jpeg, …"
                 data-testid="upload-mimes-input" />
        </div>
        <Button size="sm" onClick={save} disabled={saving} data-testid="upload-limits-save">
          Speichern
        </Button>
      </div>
      <div className="text-[10px] text-[#9CA3AF] mt-2">
        Aktiv: max {cfg.max_size_mb} MB · {cfg.allowed_mimes?.length || 0} Typen erlaubt
      </div>
    </Card>
  );
}


function SubUtilizationPanel() {  const [splitRooms, setSplitRooms] = useState([]);
  const [selected, setSelected] = useState('');
  const [data, setData] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data: list } = await api.get('/resources?type=room');
        const rs = (list || []).filter(r => r.is_splitable);
        setSplitRooms(rs);
        if (rs.length && !selected) setSelected(rs[0].resource_id);
      } catch { /* ignore */ }
    })();
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    if (!selected) { setData(null); return; }
    (async () => {
      try {
        const { data: d } = await api.get(`/resources/${selected}/utilization-by-sub?days=30`);
        setData(d);
      } catch { setData(null); }
    })();
  }, [selected]);

  if (!splitRooms.length) return null;
  return (
    <Card className="p-4" data-testid="sub-utilization-panel">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <Activity className="w-4 h-4 text-[#4A5D4E]" />
        <div className="text-sm font-medium">Auslastung pro Teilbereich (30 Tage)</div>
        <select
          value={selected}
          onChange={e => setSelected(e.target.value)}
          className="ml-auto text-xs border border-[#E2E4E0] rounded px-2 py-1"
          data-testid="sub-util-select"
        >
          {splitRooms.map(r => (
            <option key={r.resource_id} value={r.resource_id}>{r.name}</option>
          ))}
        </select>
      </div>
      {data?.sub_rows?.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[400px]">
            <thead>
              <tr className="text-xs text-[#6B7280] text-left">
                <th className="py-1">Teilbereich</th>
                <th>Buchungen</th>
                <th>Stunden</th>
                <th>Auslastung</th>
              </tr>
            </thead>
            <tbody>
              {data.sub_rows.map(r => (
                <tr key={r.sub_id} className="border-t border-[#E2E4E0]" data-testid={`sub-util-row-${r.sub_id}`}>
                  <td className="py-1">{r.name}</td>
                  <td>{r.bookings}</td>
                  <td>{(r.total_minutes / 60).toFixed(1)}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 bg-[#F3F4F1] rounded overflow-hidden">
                        <div className="h-full bg-[#4A5D4E]" style={{ width: `${Math.min(100, r.utilization_pct)}%` }} />
                      </div>
                      <span className="text-xs">{r.utilization_pct}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-xs text-[#9CA3AF] py-4 text-center">Keine Daten in den letzten 30 Tagen.</div>
      )}
      {data && data.combo_or_full_room_bookings > 0 && (
        <div className="text-[10px] text-[#9CA3AF] mt-2">
          Davon Kombi-/Gesamtraum-Buchungen: {data.combo_or_full_room_bookings} ({(data.combo_or_full_room_minutes/60).toFixed(1)} Std.) — wirken auf alle Teilbereiche.
        </div>
      )}
    </Card>
  );
}


function NoShowDepartmentPanel() {
  const [noShow, setNoShow] = useState(null);
  const [byDept, setByDept] = useState([]);

  useEffect(() => {
    api.get('/resources/dashboard/no-show?days=90').then(r => setNoShow(r.data)).catch(() => {});
    api.get('/resources/dashboard/by-department?days=90').then(r => setByDept(r.data?.rows || [])).catch(() => {});
  }, []);

  if (!noShow && !byDept.length) return null;
  return (
    <Card className="p-4" data-testid="no-show-department-panel">
      <div className="text-sm font-medium mb-2">No-Show &amp; Buchungen nach Kostenstelle</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {noShow && (
          <div data-testid="no-show-stats" className="space-y-1">
            <div className="text-xs text-[#6B7280]">No-Show / Cancel-Quote ({noShow.window_days} Tage)</div>
            <div className="flex items-end gap-3">
              <div>
                <div className="text-2xl font-semibold text-rose-700">{(noShow.no_show_rate * 100).toFixed(1)}%</div>
                <div className="text-[10px] text-[#9CA3AF]">{noShow.no_show_count} von {noShow.total_bookings} Buchungen</div>
              </div>
              <div>
                <div className="text-2xl font-semibold text-amber-700">{(noShow.cancellation_rate * 100).toFixed(1)}%</div>
                <div className="text-[10px] text-[#9CA3AF]">{noShow.cancelled_count} storniert</div>
              </div>
            </div>
          </div>
        )}
        <div data-testid="by-department-stats">
          <div className="text-xs text-[#6B7280] mb-1">Top Kostenstellen</div>
          {byDept.length === 0 && <div className="text-xs text-[#9CA3AF]">Keine Daten.</div>}
          <div className="space-y-1">
            {byDept.slice(0, 5).map(row => (
              <div key={row.cost_center} className="flex items-center justify-between text-xs"
                   data-testid={`dept-row-${row.cost_center}`}>
                <span>{row.cost_center}</span>
                <span className="font-medium">{row.count} Buchungen</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

