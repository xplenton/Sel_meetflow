import React, { useEffect, useMemo, useState } from 'react';
import api from '../lib/api';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { ChevronLeft, ChevronRight, CalendarDays, Pin, AlertTriangle, Clock, Send, X } from 'lucide-react';

const STATUS_STYLE = {
  draft:     { label: 'Entwurf',      bg: '#E2E4E0', fg: '#6B7280' },
  review:    { label: 'Prüfung',     bg: '#D4A373', fg: '#fff' },
  approval:  { label: 'Freigabe',     bg: '#D4A373', fg: '#fff' },
  scheduled: { label: 'Geplant',      bg: '#4A5D4E', fg: '#fff' },
  published: { label: 'Live',         bg: '#6B8E23', fg: '#fff' },
  archived:  { label: 'Archiviert',   bg: '#9CA3AF', fg: '#fff' },
};

/**
 * Editorial Calendar — timeline view that lets editors see every planned/published
 * news post across the next ~90 days. Works as a weekly or monthly grid.
 */
export default function EditorialCalendar({ open, onClose, onSelectPost }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dragPostId, setDragPostId] = useState(null);
  const [viewStart, setViewStart] = useState(() => {
    // Start from the Monday of the current week
    const d = new Date();
    const dow = (d.getDay() + 6) % 7;
    d.setDate(d.getDate() - dow);
    d.setHours(0, 0, 0, 0);
    return d;
  });
  const [weeks, setWeeks] = useState(6);

  const fetchItems = () => {
    const start = new Date(viewStart);
    const end = new Date(viewStart);
    end.setDate(end.getDate() + weeks * 7);
    setLoading(true);
    return api.get(`/news/editorial-calendar?start=${start.toISOString()}&end=${end.toISOString()}`)
      .then(({ data }) => setItems(data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!open) return;
    fetchItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, viewStart, weeks]);

  const handleDrop = async (targetDateISO, e) => {
    e.preventDefault();
    const postId = dragPostId || e.dataTransfer.getData('text/plain');
    setDragPostId(null);
    if (!postId) return;
    const post = items.find(p => p.post_id === postId);
    if (!post) return;
    // Preserve time-of-day from the original; only change the date part
    const oldISO = post.calendar_date || '';
    const oldDate = new Date(oldISO);
    const newDate = new Date(targetDateISO);
    if (!isNaN(oldDate.getTime())) {
      newDate.setHours(oldDate.getHours(), oldDate.getMinutes(), 0, 0);
    } else {
      newDate.setHours(9, 0, 0, 0);
    }
    const newISO = newDate.toISOString();
    try {
      // If the post was already published, we set publish_at only (history remains);
      // for draft/scheduled/review we update publish_at and — if still scheduled —
      // keep it as scheduled so the background task promotes at the right moment.
      const payload = { publish_at: newISO };
      if (post.status === 'draft' || post.status === 'scheduled') {
        payload.status = 'scheduled';
      }
      await api.put(`/news/posts/${postId}`, payload);
      await fetchItems();
    } catch (err) {
      console.error('DnD update failed:', err);
    }
  };

  const grid = useMemo(() => {
    // Build stable YYYY-MM-DD keys from LOCAL time (not UTC), otherwise posts
    // scheduled in the evening get bucketed into the wrong day.
    const pad = (n) => n.toString().padStart(2, '0');
    const localKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const days = [];
    for (let i = 0; i < weeks * 7; i++) {
      const d = new Date(viewStart);
      d.setDate(d.getDate() + i);
      days.push(d);
    }
    // Group posts by LOCAL date-key
    const byDay = {};
    items.forEach(p => {
      const raw = p.calendar_date || '';
      if (!raw) return;
      const pd = new Date(raw);
      if (isNaN(pd.getTime())) return;
      const k = localKey(pd);
      if (!byDay[k]) byDay[k] = [];
      byDay[k].push(p);
    });
    return { days, byDay, localKey };
  }, [items, viewStart, weeks]);

  if (!open) return null;

  const monthLabel = viewStart.toLocaleDateString('de-DE', { year: 'numeric', month: 'long' });
  const shiftWeeks = (n) => { const d = new Date(viewStart); d.setDate(d.getDate() + n * 7); setViewStart(d); };
  const today = new Date(); today.setHours(0, 0, 0, 0);

  return (
    <div className="fixed inset-0 z-[90] bg-black/40 flex items-start sm:items-center justify-center p-2 sm:p-6 overflow-y-auto" data-testid="editorial-calendar-dialog">
      <div className="bg-white rounded-xl w-full max-w-6xl shadow-xl overflow-hidden max-h-[95vh] flex flex-col">
        <header className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-[#E2E4E0]">
          <div className="flex items-center gap-2 min-w-0">
            <CalendarDays className="w-4 h-4 text-[#4A5D4E] flex-shrink-0" />
            <h2 className="text-sm sm:text-base font-semibold text-[#1C1F1D] truncate">Redaktions-Kalender</h2>
            <span className="hidden sm:inline text-xs text-[#9CA3AF]">{monthLabel} · {items.length} Posts</span>
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="outline" onClick={() => shiftWeeks(-2)} className="h-7 w-7 p-0 rounded-lg border-[#E2E4E0]" data-testid="cal-prev"><ChevronLeft className="w-3.5 h-3.5" /></Button>
            <Button size="sm" variant="outline" onClick={() => { const d = new Date(); const dow = (d.getDay() + 6) % 7; d.setDate(d.getDate() - dow); d.setHours(0,0,0,0); setViewStart(d); }} className="h-7 px-2 text-[10px] rounded-lg border-[#E2E4E0]" data-testid="cal-today">Heute</Button>
            <Button size="sm" variant="outline" onClick={() => shiftWeeks(2)} className="h-7 w-7 p-0 rounded-lg border-[#E2E4E0]" data-testid="cal-next"><ChevronRight className="w-3.5 h-3.5" /></Button>
            <select value={weeks} onChange={e => setWeeks(parseInt(e.target.value))} className="h-7 px-2 text-xs border border-[#E2E4E0] rounded-lg ml-1" data-testid="cal-weeks-select">
              <option value={4}>4 Wochen</option>
              <option value={6}>6 Wochen</option>
              <option value={12}>Quartal</option>
            </select>
            <Button size="sm" variant="outline" onClick={onClose} className="h-7 w-7 p-0 rounded-lg border-[#E2E4E0] ml-1" data-testid="cal-close"><X className="w-3.5 h-3.5" /></Button>
          </div>
        </header>

        <div className="p-3 sm:p-4 overflow-auto flex-1">
          {/* Weekday header */}
          <div className="hidden sm:grid grid-cols-7 gap-1 mb-1">
            {['Mo','Di','Mi','Do','Fr','Sa','So'].map(d => (
              <div key={d} className="text-[10px] uppercase tracking-wider font-bold text-[#9CA3AF] text-center">{d}</div>
            ))}
          </div>
          {/* Calendar grid — one row per week */}
          <div className="grid grid-cols-1 sm:grid-cols-7 gap-1" data-testid="cal-grid">
            {grid.days.map((d, idx) => {
              const key = grid.localKey(d);
              const dayItems = grid.byDay[key] || [];
              const isToday = d.getTime() === today.getTime();
              const isWeekend = d.getDay() === 0 || d.getDay() === 6;
              return (
                <div
                  key={idx}
                  className={`border rounded-lg p-1.5 min-h-[70px] transition-colors ${isToday ? 'border-[#4A5D4E] bg-[#4A5D4E]/5' : 'border-[#E2E4E0]'} ${isWeekend ? 'bg-[#F9F9F8]' : ''} ${dragPostId ? 'hover:border-[#4A5D4E] hover:bg-[#4A5D4E]/10' : ''}`}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => handleDrop(d.toISOString(), e)}
                  data-testid={`cal-day-${key}`}
                >
                  <div className={`text-[10px] font-bold mb-1 flex items-center justify-between ${isToday ? 'text-[#4A5D4E]' : 'text-[#9CA3AF]'}`}>
                    <span className="sm:hidden">{d.toLocaleDateString('de-DE', { weekday: 'short' })} </span>
                    <span>{d.getDate().toString().padStart(2, '0')}.{(d.getMonth()+1).toString().padStart(2,'0')}.</span>
                    {dayItems.length > 0 && <span className="bg-[#4A5D4E] text-white rounded-full text-[9px] px-1.5">{dayItems.length}</span>}
                  </div>
                  <div className="space-y-1">
                    {dayItems.slice(0, 4).map(p => {
                      const s = STATUS_STYLE[p.status] || STATUS_STYLE.draft;
                      const isPlanable = p.status === 'draft' || p.status === 'scheduled';
                      return (
                        <button
                          key={p.post_id}
                          onClick={() => onSelectPost?.(p)}
                          draggable={isPlanable}
                          onDragStart={(e) => { setDragPostId(p.post_id); e.dataTransfer.setData('text/plain', p.post_id); e.dataTransfer.effectAllowed = 'move'; }}
                          onDragEnd={() => setDragPostId(null)}
                          className={`w-full text-left block text-[10px] px-1.5 py-1 rounded truncate hover:opacity-90 ${isPlanable ? 'cursor-move' : ''}`}
                          style={{ backgroundColor: s.bg + '22', color: s.fg === '#fff' ? s.bg : s.fg, borderLeft: `3px solid ${s.bg}` }}
                          title={`${p.title} — ${s.label}${isPlanable ? ' (ziehen zum Umplanen)' : ''}`}
                          data-testid={`cal-post-${p.post_id}`}
                        >
                          <span className="flex items-center gap-1">
                            {p.pinned && <Pin className="w-2.5 h-2.5 flex-shrink-0" />}
                            {p.is_mandatory && <AlertTriangle className="w-2.5 h-2.5 flex-shrink-0" />}
                            {p.status === 'scheduled' && <Clock className="w-2.5 h-2.5 flex-shrink-0" />}
                            {p.channels?.includes('email') && <Send className="w-2.5 h-2.5 flex-shrink-0" />}
                            <span className="truncate">{p.title}</span>
                          </span>
                        </button>
                      );
                    })}
                    {dayItems.length > 4 && <span className="text-[9px] text-[#9CA3AF]">+{dayItems.length - 4} weitere</span>}
                  </div>
                </div>
              );
            })}
          </div>
          {/* Legend */}
          <div className="mt-4 flex flex-wrap gap-2" data-testid="cal-legend">
            {Object.entries(STATUS_STYLE).map(([k, s]) => (
              <Badge key={k} className="text-[9px]" style={{ backgroundColor: s.bg + '22', color: s.bg }}>{s.label}</Badge>
            ))}
          </div>
          {loading && <p className="text-xs text-[#9CA3AF] text-center mt-3">Lade…</p>}
        </div>
      </div>
    </div>
  );
}
