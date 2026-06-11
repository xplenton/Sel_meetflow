import { useEffect, useMemo, useRef, useState } from 'react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';
import { ChevronLeft, ChevronRight, Loader2, RefreshCcw, ArrowRight, Move, Utensils, Clock, User as UserIcon, Building2 } from 'lucide-react';
import { toast } from 'sonner';

/**
 * Resource Occupancy Timeline (Iter 235) — Gantt-style overview.
 * Zeigt mehrere Ressourcen in einer einzigen Ansicht mit ihren Buchungen
 * als farbige Balken auf einer Tag-/Wochen-Zeitachse.
 *
 * Default: 7 Tage ab heute, alle Räume. Filter über Resource-Type-Select.
 */
const TYPE_LABELS = {
  all: 'Alle Ressourcen',
  room: 'Nur Räume',
  desk: 'Nur Arbeitsplätze',
  vehicle: 'Nur Fahrzeuge',
};

const STATUS_COLORS = {
  confirmed: { bar: 'bg-[#4A5D4E]', text: 'text-white' },
  pending_approval: { bar: 'bg-amber-500', text: 'text-white' },
};

export default function OccupancyOverview({ onBook }) {
  const [type, setType] = useState('room');
  const [days, setDays] = useState(7);
  const [windowStart, setWindowStart] = useState(_todayLocalMidnight());
  const [data, setData] = useState({ resources: [], bookings: [], blackouts: [] });
  const [loading, setLoading] = useState(false);
  const [moving, setMoving] = useState(false);
  const [pendingMove, setPendingMove] = useState(null);  // {booking, target_resource_id, start_at, end_at}
  // Iter 238 — Mobile: Long-Press oeffnet einen Modal zum Verschieben.
  // HTML5 DnD funktioniert auf Touch-Geräten nicht zuverlaessig.
  const [mobileMoveBooking, setMobileMoveBooking] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const from = new Date(windowStart);
      const to = new Date(windowStart);
      to.setDate(to.getDate() + days);
      const params = new URLSearchParams({
        from_date: from.toISOString(),
        to_date: to.toISOString(),
      });
      if (type !== 'all') params.set('type', type);
      const { data: d } = await api.get(`/resource-occupancy?${params}`);
      setData(d);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Belegung konnte nicht geladen werden');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [type, days, windowStart]);

  // Berechne Balken-Positionen
  const windowMs = days * 24 * 60 * 60 * 1000;
  const start0 = new Date(windowStart).getTime();
  const dayLabels = useMemo(() => {
    const out = [];
    for (let i = 0; i < days; i++) {
      const d = new Date(windowStart);
      d.setDate(d.getDate() + i);
      out.push(d);
    }
    return out;
  }, [days, windowStart]);

  // Nur Top-Level-Ressourcen (keine Sub-Bereiche von teilbaren Räumen, vermeidet Duplikate)
  const topResources = useMemo(
    () => (data.resources || []).filter(r => !r.parent_resource_id),
    [data.resources]
  );
  const bookingsByResource = useMemo(() => {
    const map = {};
    for (const b of data.bookings || []) {
      (map[b.resource_id] ||= []).push(b);
    }
    return map;
  }, [data.bookings]);
  const blackoutsByResource = useMemo(() => {
    const map = {};
    for (const b of data.blackouts || []) {
      (map[b.resource_id] ||= []).push(b);
    }
    return map;
  }, [data.blackouts]);

  const shift = (deltaDays) => {
    const d = new Date(windowStart);
    d.setDate(d.getDate() + deltaDays);
    setWindowStart(d.toISOString());
  };

  const goToToday = () => setWindowStart(_todayLocalMidnight());

  // Drop-Handler: berechnet neue Zeit anhand der X-Position auf der Zielzeile
  const onDropBooking = (target_resource_id, evt, isSub) => {
    evt.preventDefault();
    const bid = evt.dataTransfer.getData('booking_id');
    const oldStart = evt.dataTransfer.getData('start_at');
    const oldEnd = evt.dataTransfer.getData('end_at');
    if (!bid || !oldStart || !oldEnd) return;
    // X-Position relativ zur Zeilenbreite → neue Start-Zeit
    const rect = evt.currentTarget.getBoundingClientRect();
    const xFrac = Math.max(0, Math.min(1, (evt.clientX - rect.left) / rect.width));
    const duration = new Date(oldEnd).getTime() - new Date(oldStart).getTime();
    const newStartMs = start0 + xFrac * windowMs;
    // Snap auf 15 Minuten
    const snap = 15 * 60 * 1000;
    const snappedStart = Math.round(newStartMs / snap) * snap;
    const newStart = new Date(snappedStart);
    const newEnd = new Date(snappedStart + duration);
    setPendingMove({
      booking_id: bid,
      target_resource_id,
      target_is_sub: isSub,
      new_start: newStart.toISOString(),
      new_end: newEnd.toISOString(),
      original_resource_id: evt.dataTransfer.getData('resource_id'),
    });
  };

  const confirmMove = async () => {
    if (!pendingMove) return;
    setMoving(true);
    try {
      const body = {
        start_at: pendingMove.new_start,
        end_at: pendingMove.new_end,
      };
      if (pendingMove.target_resource_id !== pendingMove.original_resource_id) {
        body.resource_id = pendingMove.target_resource_id;
      }
      await api.put(`/resource-bookings/${pendingMove.booking_id}`, body);
      toast.success('Buchung verschoben');
      setPendingMove(null);
      load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (e.response?.status === 409) {
        toast.error('Konflikt: Zielzeitfenster bereits belegt');
      } else {
        toast.error(typeof detail === 'string' ? detail : 'Verschieben fehlgeschlagen');
      }
    } finally {
      setMoving(false);
    }
  };

  // Find sub-children for splittable rooms so we render them as nested rows
  const childrenByParent = useMemo(() => {
    const map = {};
    for (const r of data.resources || []) {
      if (r.parent_resource_id) {
        (map[r.parent_resource_id] ||= []).push(r);
      }
    }
    return map;
  }, [data.resources]);

  return (
    <div className="space-y-3" data-testid="occupancy-overview">
      <div className="flex items-center gap-2 flex-wrap">
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="w-[180px]" data-testid="occupancy-type-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            {Object.entries(TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
          <SelectTrigger className="w-[130px]" data-testid="occupancy-days-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="1">1 Tag</SelectItem>
            <SelectItem value="3">3 Tage</SelectItem>
            <SelectItem value="7">7 Tage</SelectItem>
            <SelectItem value="14">14 Tage</SelectItem>
            <SelectItem value="30">30 Tage</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={() => shift(-days)} data-testid="occupancy-prev">
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={goToToday} data-testid="occupancy-today">Heute</Button>
        <Button variant="outline" size="sm" onClick={() => shift(days)} data-testid="occupancy-next">
          <ChevronRight className="w-4 h-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={load} data-testid="occupancy-refresh">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCcw className="w-3 h-3" />}
        </Button>
        <div className="text-xs text-[#6B7280] ml-auto">
          {topResources.length} Ressourcen · {data.bookings.length} Buchungen · {data.blackouts.length} Sperrzeiten
        </div>
      </div>

      <div className="border border-[#E2E4E0] rounded-lg bg-white overflow-x-auto">
        {/* Day Headers */}
        {/* Iter 337 — Mobile: schmalere Ressourcen-Spalte (clamp 120-220px)
            damit auf 390 px Display noch genug Platz für Tag-Spalten bleibt.
            min-w stellt sicher, dass die Tag-Spalten nicht zu schmal zum
            Lesen werden — bei Überlauf scrollt der Container horizontal. */}
        <div className="grid border-b border-[#E2E4E0] bg-[#F3F4F1] text-xs min-w-[480px]"
             style={{ gridTemplateColumns: `clamp(120px, 25vw, 220px) repeat(${days}, minmax(40px, 1fr))` }}>
          <div className="px-2 sm:px-3 py-2 font-medium">Ressource</div>
          {dayLabels.map((d, i) => {
            const isToday = d.toDateString() === new Date().toDateString();
            const isWeekend = d.getDay() === 0 || d.getDay() === 6;
            return (
              <div key={i}
                   className={`px-2 py-2 border-l border-[#E2E4E0] text-center ${
                     isToday ? 'bg-emerald-50 text-emerald-800 font-medium' : isWeekend ? 'bg-[#F8F8F6] text-[#9CA3AF]' : ''
                   }`}>
                <div>{d.toLocaleDateString('de-DE', { weekday: 'short' })}</div>
                <div className="font-medium">{d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}</div>
                {/* Iter 324 — Hour ticks for 1-3 day Zeitstrahl views. */}
                {days <= 3 && (
                  <div className="mt-1 flex justify-between text-[9px] text-[#9CA3AF] px-0.5">
                    <span>0</span><span>6</span><span>12</span><span>18</span><span>24</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Rows */}
        {topResources.length === 0 ? (
          <div className="px-3 py-12 text-center text-sm text-[#9CA3AF]">
            Keine Ressourcen im aktuellen Filter.
          </div>
        ) : (
          topResources.map(r => {
            const subs = childrenByParent[r.resource_id] || [];
            // Render parent + each sub as own row
            const rowsForRes = [r, ...subs];
            return rowsForRes.map((row, idx) => {
              const isSubRow = idx > 0;
              return (
                <ResourceRow
                  key={row.resource_id}
                  resource={row}
                  isSub={isSubRow}
                  parentName={isSubRow ? r.name : null}
                  days={days}
                  start0={start0}
                  windowMs={windowMs}
                  bookings={bookingsByResource[row.resource_id] || []}
                  blackouts={blackoutsByResource[row.resource_id] || []}
                  onBook={onBook}
                  onDropBooking={(e) => onDropBooking(row.resource_id, e, isSubRow)}
                  onLongPressBooking={(b) => setMobileMoveBooking(b)}
                />
              );
            });
          })
        )}
      </div>

      <div className="flex items-center gap-3 text-[10px] text-[#6B7280]">
        <div className="flex items-center gap-1">
          <div className="w-3 h-2 rounded bg-[#4A5D4E]" /> Bestätigt
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-2 rounded bg-amber-500" /> Wartet auf Freigabe
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-2 rounded bg-rose-200 border border-rose-300" /> Sperrzeit
        </div>
        <div className="text-[10px] text-[#9CA3AF] ml-auto">
          <span className="hidden sm:inline">Tipp: Buchungen lassen sich per Drag &amp; Drop verschieben.</span>
          <span className="sm:hidden">Tipp: Lange auf eine Buchung tippen, um sie zu verschieben.</span>
        </div>
      </div>

      {/* Confirm-Dialog für Drag & Drop Verschiebung (Iter 236) */}
      <Dialog open={!!pendingMove} onOpenChange={(open) => !open && !moving && setPendingMove(null)}>
        <DialogContent data-testid="occupancy-move-dialog" className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Buchung verschieben?</DialogTitle>
            <DialogDescription>Die Buchung wird auf den neuen Zeitraum verschoben. Konflikte werden automatisch geprüft.</DialogDescription>
          </DialogHeader>
          {pendingMove && (() => {
            const sourceBk = (data.bookings || []).find(b => b.booking_id === pendingMove.booking_id);
            const targetRes = (data.resources || []).find(r => r.resource_id === pendingMove.target_resource_id);
            const sourceRes = (data.resources || []).find(r => r.resource_id === pendingMove.original_resource_id);
            const newStart = new Date(pendingMove.new_start);
            const newEnd = new Date(pendingMove.new_end);
            return (
              <div className="space-y-3 text-sm">
                <div className="rounded-lg bg-[#F8F8F6] p-3">
                  <div className="text-xs text-[#6B7280] mb-1">Buchung</div>
                  <div className="font-medium">{sourceBk?.title || pendingMove.booking_id}</div>
                </div>
                {sourceRes && targetRes && sourceRes.resource_id !== targetRes.resource_id && (
                  <div className="flex items-center justify-between gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3">
                    <div className="text-xs">
                      <div className="text-[#6B7280]">Quelle</div>
                      <div className="font-medium">{sourceRes.name}</div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-amber-600 flex-shrink-0" />
                    <div className="text-xs text-right">
                      <div className="text-[#6B7280]">Ziel</div>
                      <div className="font-medium">{targetRes.name}</div>
                    </div>
                  </div>
                )}
                <div className="rounded-lg bg-[#F8F8F6] p-3">
                  <div className="text-xs text-[#6B7280] mb-1">Neuer Zeitraum</div>
                  <div className="font-medium">
                    {newStart.toLocaleString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    {' – '}
                    {newEnd.toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              </div>
            );
          })()}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setPendingMove(null)} disabled={moving} data-testid="occupancy-move-cancel">
              Abbrechen
            </Button>
            <Button onClick={confirmMove} disabled={moving} data-testid="occupancy-move-confirm">
              {moving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Verschieben
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Mobile-Move-Dialog (Iter 238) — Long-Press auf Buchung oeffnet diesen Modal. */}
      <MobileMoveDialog
        booking={mobileMoveBooking}
        resources={topResources}
        onClose={() => setMobileMoveBooking(null)}
        onSuccess={() => { setMobileMoveBooking(null); load(); }}
      />
    </div>
  );
}


function ResourceRow({ resource, isSub, parentName, days, start0, windowMs, bookings, blackouts, onBook, onDropBooking, onLongPressBooking }) {
  return (
    <div className="grid border-b border-[#E2E4E0] hover:bg-[#FAFBF9] min-w-[480px]"
         style={{ gridTemplateColumns: `clamp(120px, 25vw, 220px) repeat(${days}, minmax(40px, 1fr))` }}
         data-testid={`occupancy-row-${resource.resource_id}`}>
      <div className={`px-2 sm:px-3 py-2 text-sm ${isSub ? 'pl-5 sm:pl-6 text-[#6B7280]' : ''}`}>
        <div className={`${isSub ? 'text-xs' : 'font-medium'} truncate`}>
          {isSub ? `↳ Bereich ${resource.sub_id || resource.name}` : resource.name}
        </div>
        <div className="text-[10px] text-[#9CA3AF] truncate">
          {[resource.building, resource.floor, resource.license_plate, resource.desk_number].filter(Boolean).join(' · ')}
        </div>
      </div>
      <div className="relative col-span-full"
           style={{ gridColumn: `2 / span ${days}` }}
           onDragOver={(e) => e.preventDefault()}
           onDrop={onDropBooking}
           data-testid={`occupancy-drop-${resource.resource_id}`}>
        {/* Day grid lines */}
        <div className="absolute inset-0 grid pointer-events-none"
             style={{ gridTemplateColumns: `repeat(${days}, 1fr)` }}>
          {Array.from({ length: days }).map((_, i) => (
            <div key={i} className="border-l border-[#F3F4F1] relative">
              {/* Iter 324 — show hour ticks (every 6 h) when zoomed in. */}
              {days <= 3 && (
                <>
                  <div className="absolute top-0 bottom-0 border-l border-[#F3F4F1]/60" style={{ left: '25%' }} />
                  <div className="absolute top-0 bottom-0 border-l border-[#E2E4E0]" style={{ left: '50%' }} />
                  <div className="absolute top-0 bottom-0 border-l border-[#F3F4F1]/60" style={{ left: '75%' }} />
                </>
              )}
            </div>
          ))}
        </div>
        {/* Bars */}
        <div className="relative h-12">
          {/* Click-to-book overlay (Empty area click) — rendered FIRST so booking-bars sit on top and remain draggable */}
          {onBook && !isSub && (
            <div className="absolute inset-0 cursor-pointer"
                 onClick={() => onBook(resource)}
                 data-testid={`occupancy-book-${resource.resource_id}`}
                 title={`Buchen: ${resource.name}`} />
          )}
          {blackouts.map((bo, i) => {
            const left = clamp01((new Date(bo.start_at).getTime() - start0) / windowMs) * 100;
            const right = clamp01((new Date(bo.end_at).getTime() - start0) / windowMs) * 100;
            if (right <= left) return null;
            return (
              <div key={`bo-${i}`}
                   className="absolute top-1 bottom-1 bg-rose-200 border border-rose-300 rounded"
                   style={{ left: `${left}%`, width: `${right - left}%` }}
                   title={bo.reason || 'Sperrzeit'}
                   data-testid={`occupancy-blackout-${resource.resource_id}-${i}`} />
            );
          })}
          {bookings.map((b, i) => {
            const left = clamp01((new Date(b.start_at).getTime() - start0) / windowMs) * 100;
            const right = clamp01((new Date(b.end_at).getTime() - start0) / windowMs) * 100;
            if (right <= left) return null;
            const colors = STATUS_COLORS[b.status] || STATUS_COLORS.confirmed;
            // Iter 237 — Privacy-Filter: Backend setzt user_id=null für
            // fremde Buchungen → nur eigene (oder mit view_all_bookings) sind
            // draggable. Foreign bookings zeigen "Belegt" als Titel.
            const isOwn = !!b.user_id;
            const dragTip = isOwn ? '\n(zum Verschieben: Drag&Drop oder lange tippen)' : '';
            // Iter 324 — surface "active catering" (anything that isn't
            // cancelled/rejected) so users know the booking has a food order.
            const hasActiveCatering = !!b.catering_request_id
              && !['cancelled', 'rejected'].includes(b.catering_status || '');
            const cateringTip = hasActiveCatering
              ? `\nCatering: ${b.catering_item_count || 0} Position(en)${b.catering_status ? ' · ' + b.catering_status : ''}`
              : '';
            const t = `${b.title} · ${new Date(b.start_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })} – ${new Date(b.end_at).toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit' })}${dragTip}${cateringTip}`;
            return (
              <BookingBar
                key={`bk-${i}`}
                b={b}
                isOwn={isOwn}
                colors={colors}
                left={left}
                right={right}
                title={t}
                hasCatering={hasActiveCatering}
                resource={resource}
                onLongPress={onLongPressBooking}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function clamp01(v) { return Math.min(1, Math.max(0, v)); }
function _todayLocalMidnight() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}


/**
 * BookingBar mit Long-Press-Detection für Mobile (iter 238).
 * Touch >= 600ms ohne Bewegung > 8px triggert `onLongPress(booking)`.
 * Desktop nutzt weiterhin HTML5 Drag&Drop über `draggable` + onDragStart.
 */
function BookingBar({ b, isOwn, colors, left, right, title, hasCatering, resource, onLongPress }) {
  const timerRef = useRef(null);
  const startPosRef = useRef({ x: 0, y: 0 });

  const cancelTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const onTouchStart = (e) => {
    if (!isOwn) return;
    const t = e.touches[0];
    startPosRef.current = { x: t.clientX, y: t.clientY };
    cancelTimer();
    timerRef.current = setTimeout(() => {
      // Light haptic feedback if available
      if (navigator.vibrate) {
        try { navigator.vibrate(40); } catch {}
      }
      onLongPress?.(b);
      timerRef.current = null;
    }, 600);
  };

  const onTouchMove = (e) => {
    if (!timerRef.current) return;
    const t = e.touches[0];
    const dx = Math.abs(t.clientX - startPosRef.current.x);
    const dy = Math.abs(t.clientY - startPosRef.current.y);
    if (dx > 8 || dy > 8) {
      cancelTimer();
    }
  };

  const onTouchEnd = () => cancelTimer();

  return (
    <TooltipProvider delayDuration={250}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            draggable={isOwn}
            onDragStart={isOwn ? (e) => {
              e.dataTransfer.setData('booking_id', b.booking_id);
              e.dataTransfer.setData('start_at', b.start_at);
              e.dataTransfer.setData('end_at', b.end_at);
              e.dataTransfer.setData('resource_id', resource.resource_id);
              e.dataTransfer.effectAllowed = 'move';
            } : undefined}
            onTouchStart={onTouchStart}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
            onTouchCancel={onTouchEnd}
            className={`absolute top-2 bottom-2 ${colors.bar} ${colors.text} rounded px-1.5 text-[10px] flex items-center overflow-hidden whitespace-nowrap select-none ${
              isOwn ? 'cursor-move ring-1 ring-white/20 active:opacity-80' : 'cursor-default opacity-75'
            }`}
            style={{ left: `${left}%`, width: `${Math.max(right - left, 0.5)}%`, touchAction: 'pan-y' }}
            data-testid={`occupancy-booking-${b.booking_id}`}
          >
            {hasCatering && (
              <Utensils
                className="w-2.5 h-2.5 mr-1 flex-shrink-0 opacity-90"
                data-testid={`occupancy-catering-icon-${b.booking_id}`}
              />
            )}
            <span className="truncate">{b.title}</span>
          </div>
        </TooltipTrigger>
        {/* Iter 339 — Issue #4: Rich hover-tooltip mit allen Eckdaten der
            Buchung, nicht nur dem Drag&Drop-Hint. Wird sowohl von Maus als
            auch von langer Touch-Press-Geste angezeigt. */}
        <TooltipContent side="top" sideOffset={6} data-testid={`booking-tooltip-${b.booking_id}`}
                        className="max-w-xs space-y-1 text-xs">
          <div className="font-medium text-sm">{b.title || 'Buchung'}</div>
          <div className="flex items-center gap-1 text-[11px] opacity-90">
            <Clock className="w-3 h-3" />
            <span>
              {new Date(b.start_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
              {' – '}
              {new Date(b.end_at).toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
          {b.user_name && (
            <div className="flex items-center gap-1 text-[11px] opacity-90">
              <UserIcon className="w-3 h-3" />
              <span>{b.user_name}</span>
            </div>
          )}
          {resource?.name && (
            <div className="flex items-center gap-1 text-[11px] opacity-90">
              <Building2 className="w-3 h-3" />
              <span>{resource.name}</span>
            </div>
          )}
          <div className="text-[10px] opacity-80">
            Status: {b.status === 'pending_approval' ? 'Wartet auf Freigabe' :
                     b.status === 'cancelled' ? 'Storniert' : 'Bestätigt'}
          </div>
          {hasCatering && (
            <div className="text-[10px] opacity-80">
              Catering: {b.catering_item_count || 0} Position(en)
              {b.catering_status ? ` · ${b.catering_status}` : ''}
            </div>
          )}
          {isOwn && (
            <div className="text-[9px] opacity-60 mt-1 pt-1 border-t border-white/15">
              Drag&Drop oder lange tippen zum Verschieben
            </div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}


/**
 * Mobile-Move-Dialog (iter 238).
 * Long-Press auf eine Buchung oeffnet diesen Modal, in dem der User
 * Ziel-Ressource (gleicher Typ), Datum, Start- und End-Uhrzeit eingeben kann.
 * Submit ruft denselben PUT /resource-bookings/{id} auf.
 */
function MobileMoveDialog({ booking, resources, onClose, onSuccess }) {
  const [targetResourceId, setTargetResourceId] = useState('');
  const [date, setDate] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!booking) return;
    const s = new Date(booking.start_at);
    const e = new Date(booking.end_at);
    const pad = (n) => String(n).padStart(2, '0');
    setTargetResourceId(booking.resource_id);
    setDate(`${s.getFullYear()}-${pad(s.getMonth() + 1)}-${pad(s.getDate())}`);
    setStartTime(`${pad(s.getHours())}:${pad(s.getMinutes())}`);
    setEndTime(`${pad(e.getHours())}:${pad(e.getMinutes())}`);
  }, [booking]);

  if (!booking) return null;

  // Filter target resources by same type as the source booking
  const sourceRes = resources.find(r => r.resource_id === booking.resource_id);
  const sourceType = sourceRes?.type;
  const eligibleTargets = (resources || []).filter(r => r.type === sourceType && r.status === 'active');

  const submit = async () => {
    if (!date || !startTime || !endTime) {
      toast.error('Bitte Datum und Uhrzeiten ausfüllen');
      return;
    }
    const startIso = new Date(`${date}T${startTime}`).toISOString();
    const endIso = new Date(`${date}T${endTime}`).toISOString();
    if (new Date(endIso) <= new Date(startIso)) {
      toast.error('Endzeit muss nach Startzeit liegen');
      return;
    }
    setSaving(true);
    try {
      const body = { start_at: startIso, end_at: endIso };
      if (targetResourceId && targetResourceId !== booking.resource_id) {
        body.resource_id = targetResourceId;
      }
      await api.put(`/resource-bookings/${booking.booking_id}`, body);
      toast.success('Buchung verschoben');
      onSuccess?.();
    } catch (e) {
      if (e.response?.status === 409) {
        toast.error('Konflikt: Zielzeitfenster bereits belegt');
      } else {
        toast.error(e.response?.data?.detail || 'Verschieben fehlgeschlagen');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={!!booking} onOpenChange={(open) => !open && !saving && onClose()}>
      <DialogContent className="w-[calc(100vw-1.5rem)] sm:max-w-md" data-testid="occupancy-mobile-move-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Move className="w-4 h-4 text-[#4A5D4E]" />
            Buchung verschieben
          </DialogTitle>
          <DialogDescription>{booking.title}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280] block mb-1">
              Ressource
            </label>
            <Select value={targetResourceId} onValueChange={setTargetResourceId}>
              <SelectTrigger className="h-10" data-testid="mobile-move-resource-select">
                <SelectValue placeholder="Ressource wählen" />
              </SelectTrigger>
              <SelectContent>
                {eligibleTargets.map(r => (
                  <SelectItem key={r.resource_id} value={r.resource_id}>
                    {r.name}
                    {r.building ? ` · ${r.building}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280] block mb-1">
              Datum
            </label>
            <Input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="h-10"
              data-testid="mobile-move-date"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280] block mb-1">
                Von
              </label>
              <Input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="h-10"
                data-testid="mobile-move-start"
              />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280] block mb-1">
                Bis
              </label>
              <Input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="h-10"
                data-testid="mobile-move-end"
              />
            </div>
          </div>
        </div>
        <DialogFooter className="gap-2 mt-3">
          <Button variant="outline" onClick={onClose} disabled={saving} data-testid="mobile-move-cancel">
            Abbrechen
          </Button>
          <Button onClick={submit} disabled={saving} data-testid="mobile-move-confirm">
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
            Verschieben
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

