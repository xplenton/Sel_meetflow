import { useState, useEffect, useRef } from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { CalendarDays, Eye, Trash2, Plus, X, AlertTriangle, Sparkles, Loader2 } from 'lucide-react';
import { DateInput, TimeInput } from '../DateTimeInput';
import api from '../../lib/api';
import { toast } from 'sonner';

const WEEKDAYS = [
  { id: 0, short: 'Mo', long: 'Montag' },
  { id: 1, short: 'Di', long: 'Dienstag' },
  { id: 2, short: 'Mi', long: 'Mittwoch' },
  { id: 3, short: 'Do', long: 'Donnerstag' },
  { id: 4, short: 'Fr', long: 'Freitag' },
  { id: 5, short: 'Sa', long: 'Samstag' },
  { id: 6, short: 'So', long: 'Sonntag' },
];

function calcDuration(start, end) {
  if (!start || !end) return 60;
  const [sh, sm] = start.split(':').map(Number);
  const [eh, em] = end.split(':').map(Number);
  return Math.max(15, (eh * 60 + em) - (sh * 60 + sm));
}

function addMinutes(time, mins) {
  const [h, m] = time.split(':').map(Number);
  const total = h * 60 + m + mins;
  const nh = Math.floor(total / 60) % 24;
  const nm = total % 60;
  return `${String(nh).padStart(2, '0')}:${String(nm).padStart(2, '0')}`;
}

function getISOWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

/**
 * SchedulePreview — sub-widget rendered inside CustomScheduleEditor. Lists
 * every generated occurrence grouped by ISO-week, flags calendar conflicts
 * (via /api/meetings/conflicts/bulk) and offers a popover to shift the
 * whole weekday-slot when a conflict is detected.
 * Extracted from MeetingCreatePage during the iter 218 refactor.
 */
function SchedulePreview({ schedule, onScheduleChange, weeks, scheduledDate, startTime }) {
  const [showAll, setShowAll] = useState(false);
  const [conflictMap, setConflictMap] = useState({});
  const [openShiftKey, setOpenShiftKey] = useState(null);
  const [autoFindingSlot, setAutoFindingSlot] = useState(null);
  const lastRequestRef = useRef(0);

  const safeSchedule = schedule || [];
  const isValid = (s) => {
    if (!s || typeof s.weekday !== 'number' || !s.start_time || !s.end_time) return false;
    const [sh, sm] = s.start_time.split(':').map(Number);
    const [eh, em] = s.end_time.split(':').map(Number);
    return (eh * 60 + em) > (sh * 60 + sm);
  };
  const validSlots = safeSchedule.filter(isValid);

  let baseDt;
  if (scheduledDate) {
    const [y, m, d] = scheduledDate.split('-').map(Number);
    const [sh, sm] = (startTime || '09:00').split(':').map(Number);
    baseDt = new Date(y, m - 1, d, sh, sm, 0, 0);
  } else {
    baseDt = new Date();
  }

  const jsDow = baseDt.getDay();
  const mondayOffset = (jsDow + 6) % 7;
  const startMonday = new Date(baseDt);
  startMonday.setDate(baseDt.getDate() - mondayOffset);
  startMonday.setHours(0, 0, 0, 0);

  const occurrences = [];
  safeSchedule.forEach((slot, scheduleIdx) => {
    if (!isValid(slot)) return;
    const [sh, sm] = slot.start_time.split(':').map(Number);
    const [eh, em] = slot.end_time.split(':').map(Number);
    for (let w = 0; w < weeks; w++) {
      const occ = new Date(startMonday);
      occ.setDate(startMonday.getDate() + w * 7 + slot.weekday);
      occ.setHours(sh, sm, 0, 0);
      if (occ < baseDt) continue;
      occurrences.push({
        date: occ,
        startTime: slot.start_time,
        endTime: slot.end_time,
        duration: (eh * 60 + em) - (sh * 60 + sm),
        weekIdx: w,
        slotIdx: scheduleIdx,
        key: `${scheduleIdx}:${occ.toISOString()}`,
        isoKey: occ.toISOString(),
      });
    }
  });

  occurrences.sort((a, b) => a.date - b.date);

  const slotSignature = occurrences.map(o => `${o.isoKey}:${o.duration}`).join('|');
  useEffect(() => {
    if (!validSlots.length || occurrences.length === 0) {
      setConflictMap({});
      return;
    }
    const handle = setTimeout(async () => {
      const reqId = ++lastRequestRef.current;
      try {
        const { data } = await api.post('/meetings/conflicts/bulk', {
          slots: occurrences.map(o => ({
            scheduled_at: o.date.toISOString(),
            duration: o.duration,
          })),
        });
        if (reqId !== lastRequestRef.current) return;
        const map = {};
        (data.results || []).forEach((r, idx) => {
          const k = occurrences[idx]?.isoKey;
          if (k && r.count > 0) map[k] = { count: r.count, titles: r.titles || [] };
        });
        setConflictMap(map);
      } catch {
        setConflictMap({});
      }
    }, 500);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slotSignature]);

  if (validSlots.length === 0) return null;

  if (occurrences.length === 0) {
    return (
      <div className="p-3 bg-[#D4A373]/10 border border-[#D4A373]/40 rounded-xl">
        <p className="text-[11px] text-[#8B6F47]">
          Keine zukünftigen Termine gefunden. Bitte setze Datum + Startzeit (oben) oder erhöhe die Wochenanzahl.
        </p>
      </div>
    );
  }

  const weekGroups = new Map();
  for (const o of occurrences) {
    if (!weekGroups.has(o.weekIdx)) weekGroups.set(o.weekIdx, []);
    weekGroups.get(o.weekIdx).push(o);
  }
  const weekKeys = Array.from(weekGroups.keys()).sort((a, b) => a - b);

  const MAX_WEEKS = 4;
  const visibleKeys = showAll ? weekKeys : weekKeys.slice(0, MAX_WEEKS);
  const hiddenCount = showAll ? 0 : weekKeys.slice(MAX_WEEKS).reduce((acc, k) => acc + weekGroups.get(k).length, 0);
  const conflictCount = Object.keys(conflictMap).length;

  const shiftSlot = (slotIdx, minutes) => {
    const slot = safeSchedule[slotIdx];
    if (!slot) return;
    const [sh, sm] = slot.start_time.split(':').map(Number);
    const [eh, em] = slot.end_time.split(':').map(Number);
    const newStartMins = sh * 60 + sm + minutes;
    const newEndMins = eh * 60 + em + minutes;
    if (newEndMins > 23 * 60 + 59 || newStartMins < 0) {
      toast.error('Verschiebung würde den Tag überschreiten');
      return;
    }
    const fmt = (mins) => `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`;
    const next = [...safeSchedule];
    next[slotIdx] = { ...slot, start_time: fmt(newStartMins), end_time: fmt(newEndMins) };
    onScheduleChange(next);
    setOpenShiftKey(null);
    const weekdayLabel = WEEKDAYS[slot.weekday]?.long || 'Slot';
    toast.success(`${weekdayLabel}-Serie um ${minutes} Min verschoben`);
  };

  const autoFindShift = async (slotIdx) => {
    const slot = safeSchedule[slotIdx];
    if (!slot) return;
    const slotOccurrences = occurrences.filter(o => o.slotIdx === slotIdx);
    if (slotOccurrences.length === 0) return;
    setAutoFindingSlot(slotIdx);
    try {
      const { data } = await api.post('/meetings/conflicts/suggest-shift', {
        occurrences: slotOccurrences.map(o => o.date.toISOString()),
        duration: slotOccurrences[0].duration,
      });
      if (typeof data.shift_minutes === 'number') {
        shiftSlot(slotIdx, data.shift_minutes);
      } else {
        toast.error('Keine konfliktfreie Zeit in der Nähe gefunden');
        setOpenShiftKey(null);
      }
    } catch {
      toast.error('Suche fehlgeschlagen');
    } finally {
      setAutoFindingSlot(null);
    }
  };

  const renderShiftOptions = (occ) => {
    const [sh, sm] = occ.startTime.split(':').map(Number);
    const [eh, em] = occ.endTime.split(':').map(Number);
    const startMins = sh * 60 + sm;
    const endMins = eh * 60 + em;
    const opts = [
      { label: '+ 30 Min', delta: 30 },
      { label: '+ 1 Stunde', delta: 60 },
      { label: '+ 2 Stunden', delta: 120 },
      { label: '- 1 Stunde', delta: -60 },
    ].filter(o => {
      const ns = startMins + o.delta;
      const ne = endMins + o.delta;
      return ns >= 0 && ne <= 23 * 60 + 59;
    });
    const fmt = (mins) => `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`;
    return opts.map(o => (
      <button key={o.label} type="button" onClick={() => shiftSlot(occ.slotIdx, o.delta)}
        className="w-full text-left px-2.5 py-1.5 rounded-md hover:bg-[#4A5D4E]/10 text-[11px] flex items-center justify-between gap-2 transition-colors"
        data-testid={`shift-${occ.slotIdx}-${o.delta}`}>
        <span className="font-medium text-[#1C1F1D]">{o.label}</span>
        <span className="text-[10px] text-[#9CA3AF] tabular-nums">{fmt(startMins + o.delta)} – {fmt(endMins + o.delta)}</span>
      </button>
    ));
  };

  return (
    <div className="p-3 bg-white border border-[#4A5D4E]/30 rounded-xl" data-testid="schedule-preview">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-xs font-medium text-[#4A5D4E] flex items-center gap-1.5">
          <Eye className="w-3.5 h-3.5" />
          Vorschau · {occurrences.length} {occurrences.length === 1 ? 'Termin' : 'Termine'}
        </span>
        <div className="flex items-center gap-2">
          {conflictCount > 0 && (
            <span className="text-[10px] font-medium text-[#C87967] flex items-center gap-1" data-testid="preview-conflict-count">
              <AlertTriangle className="w-3 h-3" />
              {conflictCount} Konflikt{conflictCount === 1 ? '' : 'e'}
            </span>
          )}
          <span className="text-[10px] text-[#9CA3AF]">{validSlots.length} Slot{validSlots.length === 1 ? '' : 's'} × {weeks} Wo.</span>
        </div>
      </div>
      <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1">
        {visibleKeys.map(wKey => {
          const grp = weekGroups.get(wKey);
          const weekStart = grp[0].date;
          return (
            <div key={wKey} data-testid={`preview-week-${wKey}`}>
              <div className="text-[10px] uppercase tracking-wider font-bold text-[#9CA3AF] mb-1">
                KW {getISOWeek(weekStart)} · ab {weekStart.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}
              </div>
              <div className="space-y-1">
                {grp.map((o) => {
                  const conflict = conflictMap[o.isoKey];
                  if (conflict) {
                    const titles = (conflict.titles || []).filter(Boolean).join(', ') || 'externer Termin';
                    return (
                      <Popover key={o.key} open={openShiftKey === o.key} onOpenChange={(open) => setOpenShiftKey(open ? o.key : null)}>
                        <PopoverTrigger asChild>
                          <button type="button"
                            className="w-full flex items-center justify-between gap-2 text-[11px] rounded-md px-2.5 py-1.5 bg-[#C87967]/10 border border-[#C87967]/30 hover:bg-[#C87967]/15 transition-colors text-left"
                            data-testid={`preview-occ-${o.isoKey}`} title={`Konflikt: ${titles}`}>
                            <span className="font-medium text-[#1C1F1D] flex items-center gap-1.5">
                              <AlertTriangle className="w-3 h-3 text-[#C87967] flex-shrink-0" />
                              {o.date.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })}
                            </span>
                            <span className="tabular-nums text-[#C87967]">{o.startTime} – {o.endTime}</span>
                          </button>
                        </PopoverTrigger>
                        <PopoverContent align="end" className="w-64 p-0 border-[#E2E4E0] rounded-xl shadow-lg" data-testid={`shift-popover-${o.isoKey}`}>
                          <div className="p-3 border-b border-[#E2E4E0]">
                            <div className="flex items-start gap-1.5 mb-1">
                              <AlertTriangle className="w-3.5 h-3.5 text-[#C87967] flex-shrink-0 mt-0.5" />
                              <div className="min-w-0">
                                <p className="text-[11px] font-medium text-[#1C1F1D] leading-tight">Kalender-Konflikt</p>
                                <p className="text-[10px] text-[#9CA3AF] truncate">{titles}</p>
                              </div>
                            </div>
                          </div>
                          <div className="p-2">
                            <p className="text-[10px] uppercase tracking-wider font-bold text-[#9CA3AF] px-2 py-1">
                              {WEEKDAYS[safeSchedule[o.slotIdx]?.weekday]?.long || 'Slot'}-Serie verschieben
                            </p>
                            <div className="space-y-0.5">{renderShiftOptions(o)}</div>
                            <div className="border-t border-[#E2E4E0] my-2" />
                            <button type="button" disabled={autoFindingSlot === o.slotIdx} onClick={() => autoFindShift(o.slotIdx)}
                              className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-[11px] font-medium transition-colors disabled:opacity-60 disabled:cursor-wait"
                              data-testid={`auto-find-${o.slotIdx}`}>
                              {autoFindingSlot === o.slotIdx ? (
                                <><Loader2 className="w-3 h-3 animate-spin" />Suche läuft...</>
                              ) : (
                                <><Sparkles className="w-3 h-3" />Konfliktfreie Zeit finden</>
                              )}
                            </button>
                            <p className="text-[9px] text-[#9CA3AF] px-2 pt-2 leading-snug">
                              Wendet die Zeitverschiebung auf alle {WEEKDAYS[safeSchedule[o.slotIdx]?.weekday]?.long || 'Slot'}-Termine der Serie an.
                            </p>
                          </div>
                        </PopoverContent>
                      </Popover>
                    );
                  }
                  return (
                    <div key={o.key} className="flex items-center justify-between gap-2 text-[11px] rounded-md px-2.5 py-1.5 bg-[#F3F4F1]" data-testid={`preview-occ-${o.isoKey}`}>
                      <span className="font-medium text-[#1C1F1D]">
                        {o.date.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })}
                      </span>
                      <span className="text-[#4B5563] tabular-nums">{o.startTime} – {o.endTime}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {hiddenCount > 0 && (
        <button type="button" onClick={() => setShowAll(true)}
          className="mt-2.5 w-full text-[11px] text-[#4A5D4E] hover:bg-[#4A5D4E]/5 rounded-md py-1.5 transition-colors"
          data-testid="preview-show-all">
          + {hiddenCount} weitere Termine ({weekKeys.length - MAX_WEEKS} Wochen) anzeigen
        </button>
      )}
      {showAll && weekKeys.length > MAX_WEEKS && (
        <button type="button" onClick={() => setShowAll(false)}
          className="mt-2.5 w-full text-[11px] text-[#9CA3AF] hover:text-[#4A5D4E] rounded-md py-1.5 transition-colors"
          data-testid="preview-collapse">
          Weniger anzeigen
        </button>
      )}
    </div>
  );
}

/**
 * CustomScheduleEditor — UI to define a weekly pattern of meeting slots
 * (weekday + start/end time) repeated for N weeks. Extracted from
 * MeetingCreatePage during the iter 218 refactor.
 */
export function CustomScheduleEditor({ schedule, onChange, weeks, onWeeksChange, scheduledDate, startTime }) {
  const addSlot = () => {
    onChange([...(schedule || []), { weekday: 0, start_time: '09:00', end_time: '10:00' }]);
  };
  const updateSlot = (idx, field, value) => {
    const next = [...schedule];
    const prev = next[idx];
    if (field === 'start_time') {
      const dur = calcDuration(prev.start_time, prev.end_time);
      next[idx] = { ...prev, start_time: value, end_time: addMinutes(value, dur) };
    } else {
      next[idx] = { ...prev, [field]: value };
    }
    onChange(next);
  };
  const removeSlot = (idx) => {
    onChange(schedule.filter((_, i) => i !== idx));
  };
  return (
    <div className="mt-3 p-3 bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl space-y-3" data-testid="custom-schedule-editor">
      <div className="flex items-start gap-2 text-[10px] sm:text-[11px] text-[#4B5563]">
        <CalendarDays className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0 mt-0.5" />
        <p>Lege pro Wochentag unterschiedliche Zeiten fest. Je Slot wird eine Meeting-Serie erzeugt.</p>
      </div>

      {(schedule || []).length === 0 && (
        <p className="text-[11px] text-[#9CA3AF] py-2 text-center">Noch keine Zeitfenster</p>
      )}

      {(schedule || []).map((slot, idx) => (
        <div key={idx} className="bg-white border border-[#E2E4E0] rounded-lg p-2.5 sm:p-3" data-testid={`schedule-slot-${idx}`}>
          <div className="flex flex-wrap items-center gap-1 mb-2">
            {WEEKDAYS.map(wd => (
              <button key={wd.id} type="button" onClick={() => updateSlot(idx, 'weekday', wd.id)}
                className={`text-[10px] sm:text-xs rounded-full px-2.5 py-1 transition-colors ${slot.weekday === wd.id ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#E2E4E0]'}`}
                data-testid={`slot-${idx}-wd-${wd.id}`}>
                <span>{wd.short}</span>
              </button>
            ))}
            <button type="button" onClick={() => removeSlot(idx)} className="ml-auto p-1 text-[#C87967] hover:bg-[#C87967]/10 rounded" data-testid={`slot-${idx}-remove`}>
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-[9px] uppercase tracking-wider font-bold text-[#9CA3AF] mb-1 block">Von</Label>
              <TimeInput value={slot.start_time} onChange={v => updateSlot(idx, 'start_time', v)} data-testid={`slot-${idx}-start`} />
            </div>
            <div>
              <Label className="text-[9px] uppercase tracking-wider font-bold text-[#9CA3AF] mb-1 block">Bis</Label>
              <TimeInput value={slot.end_time} onChange={v => updateSlot(idx, 'end_time', v)} data-testid={`slot-${idx}-end`} />
            </div>
          </div>
        </div>
      ))}

      <div className="flex flex-col sm:flex-row sm:items-center gap-2">
        <button type="button" onClick={addSlot}
          className="flex items-center justify-center gap-1 text-xs text-[#4A5D4E] border border-dashed border-[#4A5D4E]/40 rounded-lg px-3 py-2 hover:bg-[#4A5D4E]/5 transition-colors"
          data-testid="add-schedule-slot">
          <Plus className="w-3.5 h-3.5" /> Slot hinzufügen
        </button>
        <div className="flex items-center gap-2 sm:ml-auto">
          <Label className="text-[10px] text-[#6B7280] whitespace-nowrap">Wochen:</Label>
          <Input type="number" min="1" max="52" value={weeks}
            onChange={e => onWeeksChange(Math.max(1, Math.min(52, parseInt(e.target.value || '8'))))}
            className="w-16 h-8 text-xs border-[#E2E4E0] rounded-lg" data-testid="schedule-weeks-input" />
        </div>
      </div>

      <SchedulePreview schedule={schedule} onScheduleChange={onChange} weeks={weeks}
        scheduledDate={scheduledDate} startTime={startTime} />
    </div>
  );
}

/**
 * CustomDatesEditor — explicit list of YYYY-MM-DD dates with start/end
 * times instead of a weekly pattern. Useful for irregular shift schedules,
 * board meetings, ad-hoc series. Extracted from MeetingCreatePage during
 * the iter 218 refactor.
 */
export function CustomDatesEditor({ dates, onChange, scheduledDate, startTime, endTime }) {
  const addDate = () => {
    const today = new Date();
    const nextDate = scheduledDate || today.toISOString().slice(0, 10);
    onChange([...(dates || []), {
      date: nextDate,
      start_time: startTime || '09:00',
      end_time: endTime || '10:00',
    }]);
  };
  const updateEntry = (idx, field, value) => {
    const next = [...dates];
    const prev = next[idx];
    if (field === 'start_time') {
      const dur = calcDuration(prev.start_time, prev.end_time);
      next[idx] = { ...prev, start_time: value, end_time: addMinutes(value, dur) };
    } else {
      next[idx] = { ...prev, [field]: value };
    }
    onChange(next);
  };
  const removeEntry = (idx) => onChange(dates.filter((_, i) => i !== idx));

  const sorted = [...(dates || [])].sort((a, b) =>
    `${a.date || ''}T${a.start_time || ''}`.localeCompare(`${b.date || ''}T${b.start_time || ''}`)
  );
  const validCount = sorted.filter(s => {
    if (!s.date || !s.start_time || !s.end_time) return false;
    const [sh, sm] = s.start_time.split(':').map(Number);
    const [eh, em] = s.end_time.split(':').map(Number);
    return (eh * 60 + em) > (sh * 60 + sm);
  }).length;

  return (
    <div className="mt-3 p-3 bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl space-y-3" data-testid="custom-dates-editor">
      <div className="flex items-start gap-2 text-[10px] sm:text-[11px] text-[#4B5563]">
        <CalendarDays className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0 mt-0.5" />
        <p>Wähle konkrete Termine per Datum. Für jeden Termin wird ein Meeting angelegt.</p>
      </div>

      {(dates || []).length === 0 && (
        <p className="text-[11px] text-[#9CA3AF] py-2 text-center">Noch keine Termine</p>
      )}

      {(dates || []).map((entry, idx) => (
        <div key={idx} className="bg-white border border-[#E2E4E0] rounded-lg p-2.5 sm:p-3 space-y-2" data-testid={`date-entry-${idx}`}>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div>
              <Label className="text-[9px] uppercase tracking-wider font-bold text-[#9CA3AF] mb-1 block">Datum</Label>
              <DateInput value={entry.date} onChange={v => updateEntry(idx, 'date', v)} className="w-full" data-testid={`date-entry-${idx}-date`} />
            </div>
            <div>
              <Label className="text-[9px] uppercase tracking-wider font-bold text-[#9CA3AF] mb-1 block">Von</Label>
              <TimeInput value={entry.start_time} onChange={v => updateEntry(idx, 'start_time', v)} className="w-full" data-testid={`date-entry-${idx}-start`} />
            </div>
            <div>
              <Label className="text-[9px] uppercase tracking-wider font-bold text-[#9CA3AF] mb-1 block">Bis</Label>
              <TimeInput value={entry.end_time} onChange={v => updateEntry(idx, 'end_time', v)} className="w-full" data-testid={`date-entry-${idx}-end`} />
            </div>
          </div>
          <div className="flex justify-end">
            <button type="button" onClick={() => removeEntry(idx)}
              className="inline-flex items-center gap-1 text-[10px] text-[#9CA3AF] hover:text-[#C87967] px-2 py-1 rounded-lg hover:bg-[#C87967]/10"
              data-testid={`date-entry-${idx}-remove`}>
              <Trash2 className="w-3.5 h-3.5" /> Entfernen
            </button>
          </div>
        </div>
      ))}

      <button type="button" onClick={addDate}
        className="w-full flex items-center justify-center gap-1 text-xs text-[#4A5D4E] border border-dashed border-[#4A5D4E]/40 rounded-lg px-3 py-2 hover:bg-[#4A5D4E]/5 transition-colors"
        data-testid="add-custom-date">
        <Plus className="w-3.5 h-3.5" /> Datum hinzufügen
      </button>

      {validCount > 0 && (
        <div className="p-3 bg-white border border-[#4A5D4E]/30 rounded-xl" data-testid="custom-dates-preview">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-[#4A5D4E] flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5" />
              Vorschau · {validCount} {validCount === 1 ? 'Termin' : 'Termine'}
            </span>
          </div>
          <div className="space-y-1 max-h-[180px] overflow-y-auto pr-1">
            {sorted.map((entry, i) => {
              const valid = entry.date && entry.start_time && entry.end_time;
              if (!valid) return null;
              const d = new Date(`${entry.date}T${entry.start_time}:00`);
              return (
                <div key={i} className="flex items-center justify-between gap-2 text-[11px] rounded-md px-2.5 py-1.5 bg-[#F3F4F1]">
                  <span className="font-medium text-[#1C1F1D]">
                    {d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: '2-digit' })}
                  </span>
                  <span className="text-[#4B5563] tabular-nums">{entry.start_time} – {entry.end_time}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
