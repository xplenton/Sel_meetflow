import { useEffect, useRef, useState } from 'react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { toast } from 'sonner';
import { Loader2, Upload, Printer } from 'lucide-react';

/**
 * Live 2D floor-plan view for placed resources (iter 227, iter 240).
 * Normalised coords (0..1) so any backdrop image scales correctly.
 *
 * Props:
 *   - floorPlanId: required
 *   - backdropUrl: optional image URL (CSS background) — if omitted the
 *                  component fetches `/floorplans/{id}` and uses its
 *                  configured `background_url`.
 *   - editMode: if true, allow drag-to-position + save + backdrop-upload
 *   - resourceTypeFilter: 'room'|'desk'|'vehicle'|undefined (iter 240) — filter
 *                  the items shown to a single resource type. Default = desk.
 *   - onBook(resource): callback when a free resource is clicked in view mode
 */
export default function FloorPlanView({ floorPlanId, backdropUrl, editMode = false, resourceTypeFilter, onBook }) {
  const [data, setData] = useState({ desks: [] });
  const [loading, setLoading] = useState(true);
  const [draggingId, setDraggingId] = useState(null);
  // Iter 283 — Auto-select the first available floorplan (sorted ABC) when
  // none is explicitly provided. The list is fetched once on mount; if only
  // one plan exists the dropdown collapses into a static label.
  const [planId, setPlanId] = useState(floorPlanId || '');
  const [allPlans, setAllPlans] = useState([]);
  const [allDesks, setAllDesks] = useState([]);
  const [plan, setPlan] = useState(null);
  const [uploadingBg, setUploadingBg] = useState(false);
  const fileRef = useRef(null);
  const apiBase = process.env.REACT_APP_BACKEND_URL || '';
  const effectiveBackdrop = backdropUrl
    || (plan?.background_url ? `${apiBase}${plan.background_url}` : null);
  // Iter 240 — kompatibel mit altem Endpoint, wenn nur Desks gewuenscht sind.
  const typeFilter = resourceTypeFilter || 'desk';

  // Iter 283 — load list of all floorplans once on mount; auto-select first.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data: list } = await api.get('/floorplans');
        if (cancelled) return;
        const sorted = (list || []).slice().sort((a, b) =>
          (a.name || a.floor_plan_id || '').localeCompare(b.name || b.floor_plan_id || ''),
        );
        setAllPlans(sorted);
        if (!floorPlanId && !planId && sorted.length) {
          setPlanId(sorted[0].floor_plan_id);
        } else if (!floorPlanId && !planId) {
          // No plans configured yet — fall back to 'default' so the empty
          // canvas + create-via-drag flow still works for admins.
          setPlanId('default');
        }
      } catch {
        if (!cancelled && !planId) setPlanId(floorPlanId || 'default');
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const url = typeFilter === 'desk'
        ? `/floorplans/${planId}/desks`
        : `/floorplans/${planId}/items?type=${typeFilter}`;
      const { data: d } = await api.get(url);
      // Normalise so {desks: [...]} works in both modes.
      const list = d.desks?.length ? d.desks : (d.items || []);
      setData({ ...d, desks: list });
    } catch {
      setData({ desks: [] });
    } finally {
      setLoading(false);
    }
  };
  const loadPlan = async () => {
    try {
      const { data: p } = await api.get(`/floorplans/${planId}`);
      setPlan(p);
    } catch { setPlan(null); }
  };
  // For edit-mode we also want resources of the current type that don't
  // have a plan yet. (Iter 240: typeFilter-aware; was hard-coded to 'desk'.)
  const loadAll = async () => {
    if (!editMode) return;
    try {
      const t = typeFilter || 'desk';
      const params = t === 'desk' ? 'type=desk&include_children=true' : `type=${t}`;
      const { data: d } = await api.get(`/resources?${params}`);
      setAllDesks(d || []);
    } catch { /* ignore */ }
  };
  useEffect(() => { if (planId) { load(); loadAll(); loadPlan(); } /* eslint-disable-next-line */ }, [planId, typeFilter]);

  const onBackdropPick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Bitte ein Bild auswählen (PNG/JPG/WebP)');
      return;
    }
    setUploadingBg(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data: att } = await api.post('/attachments/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await api.put(`/floorplans/${planId}`, {
        background_attachment_id: att.attachment_id,
      });
      toast.success('Hintergrund hochgeladen');
      loadPlan();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload fehlgeschlagen');
    } finally {
      setUploadingBg(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const removeBackdrop = async () => {
    if (!window.confirm('Hintergrundbild entfernen?')) return;
    try {
      await api.put(`/floorplans/${planId}`, { background_attachment_id: null });
      toast.success('Hintergrund entfernt');
      loadPlan();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler');
    }
  };

  // Iter 371 — QR-Bulk-Druck für alle auf diesem Plan platzierten Ressourcen.
  const printBulkQr = async () => {
    const ids = (data.desks || []).map(d => d.resource_id).filter(Boolean);
    if (ids.length === 0) {
      toast.error('Keine Ressourcen auf diesem Lageplan platziert');
      return;
    }
    try {
      toast.info(`Erzeuge PDF für ${ids.length} QR-Code(s)…`);
      const res = await api.post('/resources-qr-bulk-pdf',
        { resource_ids: ids },
        { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `qr-${planId}-${new Date().toISOString().slice(0,10)}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success(`PDF mit ${ids.length} QR-Code(s) heruntergeladen`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'PDF-Erzeugung fehlgeschlagen');
    }
  };

  const onDrop = async (e) => {
    e.preventDefault();
    if (!draggingId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    try {
      await api.put(`/resources/${draggingId}/floorplan`, {
        x, y, width: 0.06, height: 0.06, floor_plan_id: planId,
      });
      toast.success('Position gespeichert');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Speichern fehlgeschlagen');
    } finally {
      setDraggingId(null);
    }
  };

  const unplacedDesks = editMode
    ? allDesks.filter(d => !data.desks.find(p => p.resource_id === d.resource_id) && d.floor_plan_id !== planId)
    : [];

  return (
    <div className="space-y-3" data-testid="floorplan-view">
      <div className="flex items-center gap-2 flex-wrap">
        {allPlans.length > 1 ? (
          <Select value={planId} onValueChange={setPlanId}>
            <SelectTrigger className="max-w-xs" data-testid="floorplan-select">
              <SelectValue placeholder="Lageplan wählen" />
            </SelectTrigger>
            <SelectContent>
              {allPlans.map(p => (
                <SelectItem key={p.floor_plan_id} value={p.floor_plan_id}
                            data-testid={`floorplan-option-${p.floor_plan_id}`}>
                  {p.name || p.floor_plan_id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : allPlans.length === 1 ? (
          <Badge variant="outline" className="text-xs" data-testid="floorplan-single-label">
            {allPlans[0].name || allPlans[0].floor_plan_id}
          </Badge>
        ) : (
          <Input value={planId} onChange={e => setPlanId(e.target.value)} placeholder="floor_plan_id"
                 className="max-w-xs" data-testid="floorplan-id-input" />
        )}
        {editMode && (
          <Input
            value={planId}
            onChange={e => setPlanId(e.target.value)}
            placeholder="Neuer Plan-ID"
            className="max-w-[160px] text-xs"
            data-testid="floorplan-id-input-edit"
            title="Plan-ID anpassen / neuen Plan erstellen"
          />
        )}
        <Button size="sm" variant="outline" onClick={() => { load(); loadPlan(); }} data-testid="floorplan-refresh">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Aktualisieren'}
        </Button>
        <Badge variant="outline" className="text-[10px]">{data.desks.length} platziert</Badge>
        {editMode && (
          <Badge variant="outline" className="text-[10px] border-amber-400 text-amber-700">
            {unplacedDesks.length} noch nicht platziert
          </Badge>
        )}
        {editMode && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onBackdropPick}
              data-testid="floorplan-bg-file-input"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => fileRef.current?.click()}
              disabled={uploadingBg}
              data-testid="floorplan-upload-bg"
            >
              {uploadingBg
                ? <Loader2 className="w-3 h-3 animate-spin" />
                : <><Upload className="w-3 h-3 mr-1" />Hintergrund</>}
            </Button>
            {plan?.background_url && (
              <Button size="sm" variant="ghost" onClick={removeBackdrop}
                      data-testid="floorplan-remove-bg" className="text-rose-600">
                Hintergrund entfernen
              </Button>
            )}
            {/* Iter 371 — QR-Bulk-Druck für alle auf diesem Plan platzierten Ressourcen */}
            {data.desks.length > 0 && (
              <Button size="sm" variant="outline" onClick={printBulkQr}
                data-testid="floorplan-print-qr-bulk"
                className="border-[#4A5D4E] text-[#4A5D4E] hover:bg-[#4A5D4E]/5">
                <Printer className="w-3 h-3 mr-1" /> QR-Codes drucken ({data.desks.length})
              </Button>
            )}
          </>
        )}
      </div>

      <div
        className="relative w-full border border-[#E2E4E0] rounded-lg overflow-hidden bg-[#F3F4F1]"
        style={{
          aspectRatio: '16 / 9',
          backgroundImage: effectiveBackdrop ? `url(${effectiveBackdrop})` : 'none',
          backgroundSize: 'contain',
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'center',
        }}
        onDragOver={e => e.preventDefault()}
        onDrop={onDrop}
        data-testid="floorplan-canvas">
        {!loading && data.desks.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-[#9CA3AF] text-center p-6">
            {typeFilter === 'desk'
              ? 'Keine Arbeitsplätze auf diesem Lageplan platziert.'
              : typeFilter === 'room'
                ? 'Noch keine Räume auf dem Lageplan platziert. Ein Admin kann Räume in der Verwaltung positionieren.'
                : 'Noch keine Fahrzeuge auf dem Lageplan platziert. Ein Admin kann Fahrzeuge in der Verwaltung positionieren.'}
          </div>
        )}
        {data.desks.map(d => {
          const x = ((d.x ?? 0) * 100).toFixed(1);
          const y = ((d.y ?? 0) * 100).toFixed(1);
          const w = ((d.width ?? 0.06) * 100).toFixed(1);
          const h = ((d.height ?? 0.06) * 100).toFixed(1);
          const busy = d.is_busy;
          const color = busy ? '#C87967' : '#4A5D4E';
          // Iter 240 — Label je nach Typ: Desk-Nr / Kennzeichen / Raumname
          const label = d.type === 'vehicle'
            ? (d.license_plate || d.name?.slice(0, 8) || 'V')
            : d.type === 'room'
              ? (d.name?.slice(0, 12) || 'R')
              : (d.desk_number || d.name?.slice(0, 8) || 'D');
          return (
            <div
              key={d.resource_id}
              data-testid={`floorplan-desk-${d.resource_id}`}
              draggable={editMode}
              onDragStart={() => setDraggingId(d.resource_id)}
              onClick={() => !editMode && !busy && onBook?.(d)}
              style={{
                position: 'absolute',
                left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%`,
                background: color, color: 'white',
                borderRadius: 4, fontSize: 10, padding: 2,
                cursor: editMode ? 'grab' : busy ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
                opacity: busy ? 0.85 : 1,
              }}
              title={`${d.name} ${busy ? '(belegt)' : '(frei)'}`}
            >
              {label}
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-3 text-xs text-[#6B7280]">
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#4A5D4E' }}></span>Frei</span>
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#C87967' }}></span>Belegt</span>
        {editMode && (
          <span>
            {typeFilter === 'vehicle'
              ? 'Ziehe Fahrzeuge aus der Liste auf den Plan.'
              : typeFilter === 'room'
                ? 'Ziehe Räume aus der Liste auf den Plan.'
                : 'Ziehe Arbeitsplätze aus der Liste auf den Plan.'}
          </span>
        )}
      </div>

      {editMode && unplacedDesks.length > 0 && (
        <div className="border border-[#E2E4E0] rounded-lg p-3">
          <div className="text-xs font-medium text-[#1C1F1D] mb-2">Noch ohne Position:</div>
          <div className="flex flex-wrap gap-2">
            {unplacedDesks.map(d => {
              const label = d.type === 'vehicle'
                ? (d.license_plate || d.name)
                : d.type === 'room'
                  ? d.name
                  : (d.desk_number || d.name);
              return (
                <div key={d.resource_id}
                  draggable
                  onDragStart={() => setDraggingId(d.resource_id)}
                  className="px-2 py-1 rounded border border-[#E2E4E0] bg-white text-xs cursor-grab hover:border-[#4A5D4E]"
                  data-testid={`unplaced-desk-${d.resource_id}`}>
                  {label}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
