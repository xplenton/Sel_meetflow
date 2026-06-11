import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { ChevronDown, ChevronUp, MapPin, Loader2 } from 'lucide-react';

/**
 * Iter 264 — Mini-Lageplan im BookingDialog.
 *
 * Zeigt EINEN spezifischen Lageplan und markiert die aktuell gebuchte
 * Ressource klar. Findet automatisch den richtigen Plan über die
 * floor_plan_id der Ressource oder default-Plan.
 *
 * Kollapsbar — startet zugeklappt, damit der Dialog nicht überfrachtet wird.
 */
export default function BookingFloorplanView({ resource }) {
  const [expanded, setExpanded] = useState(false);
  const [plan, setPlan] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const apiBase = process.env.REACT_APP_BACKEND_URL || '';

  useEffect(() => {
    // Only fetch when expanded and not already loaded/loading
    if (!expanded) return;
    // Skip if already have items or already loading
    if (items.length > 0 || loading) return;
    
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // 1. Welcher Plan? Bevorzugt resource.floor_plan_id, sonst erster Plan, sonst 'default'
        let planId = resource.floor_plan_id;
        if (!planId) {
          try {
            const { data: plans } = await api.get('/floorplans');
            planId = (Array.isArray(plans) && plans[0]?.floor_plan_id) || 'default';
          } catch { planId = 'default'; }
        }
        // 2. Plan + Items laden parallel
        const [pRes, itemsRes] = await Promise.all([
          api.get(`/floorplans/${planId}`).catch(() => ({ data: null })),
          api.get(`/floorplans/${planId}/items?type=${resource.type || 'desk'}`).catch(() => ({ data: { items: [] } })),
        ]);
        if (cancelled) return;
        setPlan(pRes.data);
        const list = itemsRes.data?.items?.length ? itemsRes.data.items : (itemsRes.data?.desks || []);
        setItems(list);
        if (list.length === 0) {
          setError('Diese Ressource ist (noch) nicht auf einem Lageplan positioniert.');
        }
      } catch (e) {
        if (!cancelled) setError('Lageplan konnte nicht geladen werden.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, resource.resource_id, resource.floor_plan_id, resource.type]);

  const backdrop = plan?.background_url ? `${apiBase}${plan.background_url}` : null;
  // Finde "unsere" Ressource im Item-Array (matched by resource_id)
  const ownItem = items.find(it => it.resource_id === resource.resource_id);

  return (
    <div className="border border-[#E2E4E0] rounded-lg" data-testid="booking-floorplan">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-[#1C1F1D] hover:bg-[#F3F4F1] rounded-lg transition-colors"
        data-testid="booking-floorplan-toggle"
      >
        <span className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-[#4A5D4E]" />
          Lageplan anzeigen
          {plan?.name && <span className="text-xs font-normal text-[#9CA3AF] ml-1">· {plan.name}</span>}
        </span>
        {expanded ? <ChevronUp className="w-4 h-4 text-[#9CA3AF]" /> : <ChevronDown className="w-4 h-4 text-[#9CA3AF]" />}
      </button>

      {expanded && (
        <div className="p-3 pt-0">
          {loading && (
            <div className="flex items-center justify-center py-8 text-[#9CA3AF] gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> <span className="text-xs">Lade Lageplan …</span>
            </div>
          )}
          {!loading && error && (
            <div className="text-xs text-[#9CA3AF] py-6 text-center" data-testid="booking-floorplan-error">{error}</div>
          )}
          {!loading && !error && items.length > 0 && (
            <>
              <div
                className="relative w-full border border-[#E2E4E0] rounded-lg overflow-hidden bg-[#F3F4F1]"
                style={{
                  aspectRatio: '16 / 9',
                  backgroundImage: backdrop ? `url(${backdrop})` : 'none',
                  backgroundSize: 'contain',
                  backgroundRepeat: 'no-repeat',
                  backgroundPosition: 'center',
                }}
                data-testid="booking-floorplan-canvas"
              >
                {items.map(d => {
                  const x = ((d.x ?? 0) * 100).toFixed(1);
                  const y = ((d.y ?? 0) * 100).toFixed(1);
                  const w = ((d.width ?? 0.06) * 100).toFixed(1);
                  const h = ((d.height ?? 0.06) * 100).toFixed(1);
                  const isMe = d.resource_id === resource.resource_id;
                  const busy = d.is_busy;
                  // Aktuelle Ressource hervorheben (gelber Ring + größer); Rest dezent
                  const color = isMe ? '#F59E0B' : busy ? '#C87967' : '#4A5D4E';
                  const label = d.type === 'vehicle'
                    ? (d.license_plate || d.name?.slice(0, 8) || 'V')
                    : d.type === 'room'
                      ? (d.name?.slice(0, 12) || 'R')
                      : (d.desk_number || d.name?.slice(0, 8) || 'D');
                  return (
                    <div
                      key={d.resource_id}
                      data-testid={`booking-floorplan-item-${d.resource_id}${isMe ? '-self' : ''}`}
                      style={{
                        position: 'absolute',
                        left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%`,
                        background: color, color: 'white',
                        borderRadius: 4, fontSize: 10, padding: 2,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: isMe ? '0 0 0 3px rgba(245, 158, 11, 0.4)' : '0 1px 2px rgba(0,0,0,0.2)',
                        zIndex: isMe ? 20 : 1,
                        opacity: isMe ? 1 : busy ? 0.6 : 0.85,
                      }}
                      title={`${d.name}${isMe ? ' (diese Ressource)' : busy ? ' (belegt)' : ' (frei)'}`}
                    >
                      {label}
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center gap-3 text-[10px] text-[#6B7280] mt-2 flex-wrap">
                <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#F59E0B' }}></span>Diese Ressource</span>
                <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#4A5D4E' }}></span>Frei</span>
                <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#C87967' }}></span>Belegt</span>
                {!ownItem && (
                  <span className="text-amber-600">⚠ Diese Ressource ist auf dem Lageplan noch nicht positioniert.</span>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
