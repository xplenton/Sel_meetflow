/**
 * Iter 292 — Admin → Auswertungen → Führerscheine.
 *
 * Cross-user table showing who holds which license class, with filters and
 * CSV export. Visible to admins or to anyone with capability
 * `users.view_drivers_license` (e.g. Fuhrpark-Manager).
 */
import { useEffect, useState, useCallback } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Car, Download, ShieldAlert, Eye, X } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

const STANDARD_CLASSES = [
  'AM', 'A1', 'A2', 'A',
  'B', 'BE',
  'C1', 'C1E', 'C', 'CE',
  'D1', 'D1E', 'D', 'DE',
  'L', 'T',
];

const BACKEND = process.env.REACT_APP_BACKEND_URL;

// Iter 376 — kompakte de-DE Datums+Uhrzeit-Anzeige für Upload-Stempel.
// Faellt bei ungültigen Strings sauber auf null zurück, damit das UI
// "—" anzeigen kann.
function formatDate(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return null;
  }
}

export default function DriversLicenseAdminPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterClass, setFilterClass] = useState('all');
  const [filterExpiring, setFilterExpiring] = useState(''); // empty | "30" | "90" | "180"
  const [search, setSearch] = useState('');
  // Iter 299 — Foto-Lightbox: { userId, licId, side }
  const [photoView, setPhotoView] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterClass !== 'all') params.license_class = filterClass;
      if (filterExpiring) params.expiring_within_days = parseInt(filterExpiring, 10);
      const { data } = await api.get('/admin/drivers-licenses', { params });
      setRows(data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Laden fehlgeschlagen');
    } finally {
      setLoading(false);
    }
  }, [filterClass, filterExpiring]);

  useEffect(() => { load(); }, [load]);

  const filtered = rows.filter(r => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return (
      (r.user_name || '').toLowerCase().includes(q) ||
      (r.user_email || '').toLowerCase().includes(q) ||
      (r.department || '').toLowerCase().includes(q) ||
      (r.number || '').toLowerCase().includes(q)
    );
  });

  const downloadCsv = async () => {
    try {
      const params = new URLSearchParams();
      if (filterClass !== 'all') params.set('license_class', filterClass);
      if (filterExpiring) params.set('expiring_within_days', filterExpiring);
      const token = localStorage.getItem('mf_token') || '';
      const resp = await fetch(`${BACKEND}/api/admin/drivers-licenses/export.csv?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error('Export fehlgeschlagen');
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `fuehrerscheine_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e.message || 'Export fehlgeschlagen');
    }
  };

  const isExpired = (d) => d && new Date(d) < new Date();

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-4" data-testid="drivers-license-admin-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Car className="w-5 h-5 text-[#4A5D4E]" />
          <h3 className="text-sm font-medium text-[#1C1F1D]">Führerscheine</h3>
          <Badge variant="outline" className="text-[10px]">{filtered.length}</Badge>
        </div>
        <Button
          size="sm" variant="outline"
          onClick={downloadCsv}
          data-testid="export-csv-button"
          className="rounded-full"
        >
          <Download className="w-3.5 h-3.5 mr-1" />CSV
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <Label className="text-[10px] uppercase tracking-wide text-[#6B7280]">Klasse</Label>
          <Select value={filterClass} onValueChange={setFilterClass}>
            <SelectTrigger data-testid="filter-class"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle</SelectItem>
              {STANDARD_CLASSES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wide text-[#6B7280]">Läuft ab in</Label>
          <Select value={filterExpiring || 'any'} onValueChange={(v) => setFilterExpiring(v === 'any' ? '' : v)}>
            <SelectTrigger data-testid="filter-expiring"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Egal</SelectItem>
              <SelectItem value="30">30 Tagen</SelectItem>
              <SelectItem value="90">90 Tagen</SelectItem>
              <SelectItem value="180">180 Tagen</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wide text-[#6B7280]">Suche</Label>
          <Input
            placeholder="Name, E-Mail, Abteilung, Nummer…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid="filter-search"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-[#E2E4E0] text-left text-[#6B7280]">
              <th className="py-2 pr-3 font-medium">Nutzer</th>
              <th className="py-2 pr-3 font-medium">Klasse</th>
              <th className="py-2 pr-3 font-medium">Nummer</th>
              <th className="py-2 pr-3 font-medium">Behörde</th>
              <th className="py-2 pr-3 font-medium">Ablauf</th>
              <th className="py-2 pr-3 font-medium">Vorderseite</th>
              <th className="py-2 pr-3 font-medium">Rückseite</th>
              <th className="py-2 pr-3 font-medium">Erfasst</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="py-4 text-center text-[#9CA3AF]">Lade…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={8} className="py-4 text-center text-[#9CA3AF]">Keine Einträge</td></tr>
            ) : filtered.map(r => (
              <tr key={`${r.user_id}-${r.id}`} className="border-b border-[#F3F4F1]" data-testid={`row-${r.user_id}-${r.id}`}>
                <td className="py-2 pr-3">
                  <div className="font-medium text-[#1C1F1D]">{r.user_name || r.user_email}</div>
                  <div className="text-[10px] text-[#9CA3AF]">{r.user_email}{r.department ? ` · ${r.department}` : ''}</div>
                </td>
                <td className="py-2 pr-3">
                  <Badge className="bg-[#4A5D4E] text-white text-[10px]">
                    {r.is_custom ? (r.custom_label || 'Sonder') : r.license_class}
                  </Badge>
                </td>
                <td className="py-2 pr-3">{r.number || '—'}</td>
                <td className="py-2 pr-3">{r.issuing_authority || '—'}</td>
                <td className="py-2 pr-3">
                  {r.expires_at ? (
                    <span className={isExpired(r.expires_at) ? 'text-rose-700 font-medium' : ''}>
                      {isExpired(r.expires_at) && <ShieldAlert className="w-3 h-3 inline mr-1" />}
                      {r.expires_at}
                    </span>
                  ) : '—'}
                </td>
                <td className="py-2 pr-3 text-[10px]">
                  {r.has_front_photo ? (
                    <div className="flex items-start gap-1.5">
                      <button
                        type="button"
                        onClick={() => setPhotoView({ userId: r.user_id, licId: r.id, side: 'front', label: 'Vorderseite' })}
                        className="w-12 h-8 border border-[#E2E4E0] rounded overflow-hidden hover:ring-2 hover:ring-[#4A5D4E] transition flex-shrink-0"
                        data-testid={`view-photo-${r.user_id}-${r.id}-front`}
                        title="Vorderseite anzeigen"
                      >
                        <img
                          src={`${BACKEND}/api/users/${r.user_id}/drivers-licenses/${r.id}/photo/front?v=${r.updated_at}`}
                          alt="Vorderseite"
                          className="w-full h-full object-cover"
                        />
                      </button>
                      <span className="text-[9px] text-[#6B7280]" data-testid={`front-uploaded-${r.user_id}-${r.id}`}>
                        {formatDate(r.front_uploaded_at) || '—'}
                      </span>
                    </div>
                  ) : <span className="text-[#9CA3AF]">—</span>}
                </td>
                <td className="py-2 pr-3 text-[10px]">
                  {r.has_back_photo ? (
                    <div className="flex items-start gap-1.5">
                      <button
                        type="button"
                        onClick={() => setPhotoView({ userId: r.user_id, licId: r.id, side: 'back', label: 'Rückseite' })}
                        className="w-12 h-8 border border-[#E2E4E0] rounded overflow-hidden hover:ring-2 hover:ring-[#4A5D4E] transition flex-shrink-0"
                        data-testid={`view-photo-${r.user_id}-${r.id}-back`}
                        title="Rückseite anzeigen"
                      >
                        <img
                          src={`${BACKEND}/api/users/${r.user_id}/drivers-licenses/${r.id}/photo/back?v=${r.updated_at}`}
                          alt="Rückseite"
                          className="w-full h-full object-cover"
                        />
                      </button>
                      <span className="text-[9px] text-[#6B7280]" data-testid={`back-uploaded-${r.user_id}-${r.id}`}>
                        {formatDate(r.back_uploaded_at) || '—'}
                      </span>
                    </div>
                  ) : <span className="text-[#9CA3AF]">—</span>}
                </td>
                <td className="py-2 pr-3 text-[10px] text-[#6B7280]" data-testid={`row-meta-${r.user_id}-${r.id}`}>
                  <div>angelegt: <span className="text-[#1C1F1D]">{formatDate(r.created_at) || '—'}</span></div>
                  <div>aktualisiert: <span className="text-[#1C1F1D]">{formatDate(r.updated_at) || '—'}</span></div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Iter 299 — Foto-Lightbox: Vollbild-Ansicht der Vorder-/Rückseite */}
      <Dialog open={!!photoView} onOpenChange={(v) => { if (!v) setPhotoView(null); }}>
        <DialogContent
          className="max-w-4xl max-h-[90vh] overflow-auto p-0 bg-[#1C1F1D]"
          onInteractOutside={() => setPhotoView(null)}
          data-testid="license-photo-dialog"
        >
          <DialogHeader className="px-4 py-3 bg-[#2A2D2B] border-b border-[#3E4441]">
            <DialogTitle className="text-white text-sm flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Eye className="w-4 h-4" />
                Führerschein — {photoView?.label}
              </span>
            </DialogTitle>
          </DialogHeader>
          {photoView && (
            <div className="flex items-center justify-center p-6 min-h-[300px]">
              <img
                src={`${BACKEND}/api/users/${photoView.userId}/drivers-licenses/${photoView.licId}/photo/${photoView.side}`}
                alt={photoView.label}
                className="max-w-full max-h-[75vh] object-contain rounded shadow-lg"
                data-testid="license-photo-fullsize"
              />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
