/**
 * Serien-Buchung — kompakter Toggle mit Häufigkeit + Anzahl ODER explizit
 * gewählten Daten (Multi-Date-Kalender, beliebig über Monate hinweg).
 *
 * Iter 334:
 *  - Neue Häufigkeiten: every_4_weeks, monthly, custom
 *  - Bei "custom": Multi-Select-Kalender (react-day-picker mode="multiple")
 *    erlaubt das Auswählen mehrerer Tage über mehrere Monate
 *
 * Iter 386 — Mobile-Fix:
 *  - Calendar zeigt auf Mobile nur 1 Monat (vorher: 2 Monate nebeneinander
 *    sprengten die Viewport-Breite und das Popup wurde rechts abgeschnitten)
 *  - PopoverContent ist auf Mobile zentriert, mit max-w begrenzt, damit
 *    das Kalender-Popup nicht aus dem Bildschirm rutscht
 *  - Label umbenannt: „Benutzerdefinierte Daten…" → „Benutzerdefinierte Buchung"
 */
import { useEffect, useState } from 'react';
import { Calendar as CalendarIcon, X } from 'lucide-react';
import { Calendar } from '../ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';

function _fmtDate(d) {
  try { return new Date(d).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  catch { return String(d); }
}

// Iter 386 — Lokaler Mobile-Detector. Schwellenwert 640px = Tailwind `sm`.
function useIsMobile() {
  const get = () => (typeof window !== 'undefined' && window.matchMedia)
    ? window.matchMedia('(max-width: 639px)').matches
    : false;
  const [isMobile, setIsMobile] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mql = window.matchMedia('(max-width: 639px)');
    const onChange = () => setIsMobile(mql.matches);
    mql.addEventListener?.('change', onChange);
    return () => mql.removeEventListener?.('change', onChange);
  }, []);
  return isMobile;
}

export default function BookingSeriesSection({
  enabled,
  onToggle,
  recurrence,
  onRecurrenceChange,
  occurrences,
  onOccurrencesChange,
  customDates = [],
  onCustomDatesChange,
}) {
  const isCustom = recurrence === 'custom';
  const isMobile = useIsMobile();

  const handleCalendarSelect = (dates) => {
    // react-day-picker mit mode="multiple" liefert Array<Date>
    const isoList = (dates || []).map(d => {
      const dt = d instanceof Date ? d : new Date(d);
      // YYYY-MM-DD in lokaler TZ (vermeidet UTC-Off-by-One)
      const y = dt.getFullYear();
      const m = String(dt.getMonth() + 1).padStart(2, '0');
      const day = String(dt.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    });
    onCustomDatesChange?.(isoList);
  };
  const selectedDateObjs = (customDates || []).map(s => {
    const [y, m, d] = s.split('-').map(Number);
    return new Date(y, m - 1, d);
  });

  return (
    <div className="space-y-2" data-testid="booking-series-section">
      <label className="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" checked={enabled} onChange={onToggle} data-testid="booking-series-toggle" />
        <span className="text-sm font-medium text-[#1C1F1D]">Serien-Buchung aktiv</span>
      </label>
      {enabled && (
        <div className="ml-6 space-y-3">
          <div className="flex items-end gap-2 flex-wrap">
            <div>
              <label className="text-xs text-[#6B7280] block">Wiederholung</label>
              <select
                value={recurrence}
                onChange={(e) => onRecurrenceChange(e.target.value)}
                data-testid="booking-series-recurrence"
                className="border border-[#E2E4E0] rounded px-2 py-1.5 text-sm"
              >
                <option value="daily">Täglich</option>
                <option value="weekly">Wöchentlich</option>
                <option value="biweekly">Alle 2 Wochen</option>
                <option value="every_4_weeks">Alle 4 Wochen</option>
                <option value="monthly">Monatlich</option>
                <option value="custom">Benutzerdefinierte Buchung</option>
              </select>
            </div>
            {!isCustom && (
              <div>
                <label className="text-xs text-[#6B7280] block">Anzahl</label>
                <input
                  type="number"
                  min="1"
                  max="52"
                  value={occurrences}
                  onChange={(e) => onOccurrencesChange(Number(e.target.value))}
                  data-testid="booking-series-occurrences"
                  className="border border-[#E2E4E0] rounded px-2 py-1.5 text-sm w-20"
                />
              </div>
            )}
          </div>

          {isCustom && (
            <div className="border border-[#E2E4E0] rounded-lg p-3 bg-[#FBFBFA]">
              <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                <div className="text-xs text-[#6B7280]">
                  Wähle beliebige Tage — auch über mehrere Monate hinweg (max. 52).
                </div>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button size="sm" variant="outline" data-testid="booking-series-calendar-open">
                      <CalendarIcon className="w-3.5 h-3.5 mr-1" />
                      Datum wählen ({(customDates || []).length})
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent
                    className="w-auto p-0 max-w-[calc(100vw-1.5rem)] overflow-auto"
                    align={isMobile ? 'center' : 'end'}
                  >
                    <Calendar
                      mode="multiple"
                      selected={selectedDateObjs}
                      onSelect={handleCalendarSelect}
                      numberOfMonths={isMobile ? 1 : 2}
                      data-testid="booking-series-calendar"
                    />
                  </PopoverContent>
                </Popover>
              </div>
              {(customDates || []).length === 0 ? (
                <div className="text-xs text-[#9CA3AF] italic">Noch keine Daten gewählt.</div>
              ) : (
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                  {[...customDates].sort().map((d, i) => (
                    <Badge
                      key={d}
                      variant="outline"
                      className="text-[10px] gap-1 pr-1"
                      data-testid={`booking-series-date-chip-${i}`}
                    >
                      {_fmtDate(d)}
                      <button
                        type="button"
                        onClick={() => onCustomDatesChange?.(customDates.filter(x => x !== d))}
                        className="hover:bg-rose-100 rounded p-0.5"
                        aria-label="Entfernen"
                      >
                        <X className="w-2.5 h-2.5" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="text-xs text-[#9CA3AF]">
            {recurrence === 'daily' && 'Jeden Tag · '}
            {recurrence === 'weekly' && 'Jede Woche · '}
            {recurrence === 'biweekly' && 'Alle 2 Wochen · '}
            {recurrence === 'every_4_weeks' && 'Alle 4 Wochen · '}
            {recurrence === 'monthly' && 'Jeden Monat · '}
            {isCustom
              ? `${(customDates || []).length} Termin(e) ausgewählt`
              : `${occurrences} Buchung${occurrences > 1 ? 'en' : ''}`}
          </div>
        </div>
      )}
    </div>
  );
}
