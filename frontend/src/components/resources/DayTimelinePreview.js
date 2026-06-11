import { useEffect, useState, useMemo } from 'react';
import api from '../../lib/api';

/**
 * Iter 248 — Visuelle Echtzeit-Buchungs-Konflikt-Vorschau.
 *
 * Zeigt einen schmalen 24h-Tagesbalken (8:00–20:00 fokussiert) mit:
 *  - Grauen Segmenten: alle existierenden Buchungen auf dieser Ressource
 *  - Grün/Rot-Segment: das aktuell vom User ausgewählte Slot
 *      grün = frei, rot = überlappt mit bestehender Buchung
 *  - Stundenticks unten
 *
 * Props:
 *   resourceId: string
 *   startISO:   string (vom User gewählter Start)
 *   endISO:     string (vom User gewählter Ende)
 *   hasConflict: boolean (gibt der Parent BookingDialog mit basierend auf check-conflicts)
 */
export default function DayTimelinePreview({ resourceId, startISO, endISO, hasConflict }) {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(false);

  // Stunden-Fenster der Anzeige: 6h-22h (16h Total)
  const DAY_START_H = 6;
  const DAY_END_H = 22;
  const SPAN_H = DAY_END_H - DAY_START_H;

  const focusDay = useMemo(() => {
    if (!startISO) return null;
    const d = new Date(startISO);
    if (isNaN(d.getTime())) return null;
    const dayStart = new Date(d);
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(dayStart);
    dayEnd.setDate(dayEnd.getDate() + 1);
    return { dayStart, dayEnd, label: dayStart.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' }) };
  }, [startISO]);

  useEffect(() => {
    if (!resourceId || !focusDay) { setBookings([]); return; }
    setLoading(true);
    const ctrl = new AbortController();
    api.get('/resource-bookings', {
      params: {
        resource_id: resourceId,
        from_date: focusDay.dayStart.toISOString(),
        to_date: focusDay.dayEnd.toISOString(),
      },
      signal: ctrl.signal,
    })
      .then(r => setBookings(Array.isArray(r.data) ? r.data : []))
      .catch(() => setBookings([]))
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [resourceId, focusDay?.dayStart?.toISOString()]);

  if (!focusDay || !startISO || !endISO) return null;

  const startD = new Date(startISO);
  const endD = new Date(endISO);
  if (isNaN(startD.getTime()) || isNaN(endD.getTime())) return null;

  // Helper: convert any Date to fractional hour-offset from DAY_START_H clamped to [0, SPAN_H]
  const toPct = (date) => {
    if (date < focusDay.dayStart) return 0;
    if (date >= focusDay.dayEnd) return 100;
    const h = date.getHours() + date.getMinutes() / 60;
    const offset = Math.max(0, Math.min(SPAN_H, h - DAY_START_H));
    return (offset / SPAN_H) * 100;
  };

  // Existing bookings (skip cancelled, skip ourselves if id matches - none here since we are pre-create)
  const blockSegs = bookings
    .filter(b => b.status !== 'cancelled')
    .map(b => {
      const s = new Date(b.start_at);
      const e = new Date(b.end_at);
      return { left: toPct(s), right: toPct(e), title: b.title, user: b.user_id };
    })
    .filter(seg => seg.right > seg.left);

  const userSeg = {
    left: toPct(startD),
    right: toPct(endD),
  };
  const userInRange = userSeg.right > userSeg.left;

  // Hour ticks every 2h
  const ticks = [];
  for (let h = DAY_START_H; h <= DAY_END_H; h += 2) {
    ticks.push({ h, left: ((h - DAY_START_H) / SPAN_H) * 100 });
  }

  return (
    <div className="rounded-lg border border-[#E2E4E0] bg-[#FAFBF9] p-3 space-y-2"
         data-testid="booking-day-timeline">
      <div className="flex items-center justify-between text-[10px] text-[#6B7280]">
        <span className="font-medium">{focusDay.label} · {blockSegs.length} bestehende Buchung{blockSegs.length === 1 ? '' : 'en'}</span>
        {loading && <span className="italic">Lade …</span>}
      </div>
      <div className="relative h-7 bg-white border border-[#E2E4E0] rounded overflow-hidden">
        {/* existing bookings (grey) */}
        {blockSegs.map((seg, i) => (
          <div
            key={i}
            className="absolute top-0 bottom-0 bg-zinc-300/70 border-x border-zinc-400/40"
            style={{ left: `${seg.left}%`, width: `${Math.max(0.5, seg.right - seg.left)}%` }}
            title={`${seg.title}`}
            data-testid={`timeline-block-${i}`}
          />
        ))}
        {/* user-selected slot overlay */}
        {userInRange && (
          <div
            className={`absolute top-0 bottom-0 border-2 ${
              hasConflict
                ? 'bg-rose-400/50 border-rose-600'
                : 'bg-emerald-400/60 border-emerald-700'
            }`}
            style={{ left: `${userSeg.left}%`, width: `${Math.max(0.8, userSeg.right - userSeg.left)}%` }}
            data-testid="timeline-user-slot"
          />
        )}
      </div>
      {/* Hour ticks */}
      <div className="relative h-3">
        {ticks.map(t => (
          <div key={t.h}
               className="absolute top-0 -translate-x-1/2 text-[9px] text-[#9CA3AF] tabular-nums"
               style={{ left: `${t.left}%` }}>
            {String(t.h).padStart(2, '0')}
          </div>
        ))}
      </div>
    </div>
  );
}
