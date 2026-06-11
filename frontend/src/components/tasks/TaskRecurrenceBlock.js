import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { History } from 'lucide-react';

/**
 * TaskRecurrenceBlock — UI for setting up a recurring task (pattern +
 * interval + end-date). Extracted from TaskDetailDialog (iter 216).
 */
export default function TaskRecurrenceBlock({ recurrence, onPatch }) {
  const handlePatternChange = (e) => {
    const p = e.target.value || null;
    onPatch({
      recurrence: p
        ? { pattern: p, interval: recurrence?.interval || 1, end_date: recurrence?.end_date || null }
        : null,
    });
  };
  const handleIntervalChange = (e) => {
    onPatch({
      recurrence: { ...recurrence, interval: Math.max(1, parseInt(e.target.value) || 1) },
    });
  };
  const handleEndDateChange = (e) => {
    onPatch({
      recurrence: { ...recurrence, end_date: e.target.value || null },
    });
  };

  const pattern = recurrence?.pattern;
  const unitLabel = pattern === 'daily' ? 'Tag(e)' : pattern === 'weekly' ? 'Woche(n)' : 'Monat(e)';

  return (
    <div className="bg-[#F9F9F8] border border-[#E2E4E0] rounded-lg p-3" data-testid="task-recurrence-block">
      <Label className="text-[10px] uppercase font-bold text-[#6B7280] flex items-center gap-1.5">
        <History className="w-3 h-3" /> Wiederholung
      </Label>
      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
        <select data-testid="task-recurrence-pattern"
          value={pattern || ''}
          onChange={handlePatternChange}
          className="h-8 px-2 text-xs border border-[#E2E4E0] rounded-lg bg-white">
          <option value="">keine Wiederholung</option>
          <option value="daily">täglich</option>
          <option value="weekly">wöchentlich</option>
          <option value="monthly">monatlich</option>
        </select>
        {pattern && (
          <>
            <span className="text-xs text-[#6B7280]">alle</span>
            <Input type="number" min="1" max="52"
              data-testid="task-recurrence-interval"
              value={recurrence.interval || 1}
              onChange={handleIntervalChange}
              className="w-14 h-8 text-xs border-[#E2E4E0] rounded-lg" />
            <span className="text-xs text-[#6B7280]">{unitLabel}</span>
            <span className="text-xs text-[#6B7280]">· Ende:</span>
            <Input type="date"
              data-testid="task-recurrence-end"
              value={recurrence.end_date || ''}
              onChange={handleEndDateChange}
              className="w-36 h-8 text-xs border-[#E2E4E0] rounded-lg" />
          </>
        )}
      </div>
      {pattern && (
        <p className="text-[10px] text-[#9CA3AF] mt-1.5">
          Nach dem Erledigen wird automatisch eine neue Aufgabe mit verschobenem Fälligkeitsdatum erstellt.
        </p>
      )}
    </div>
  );
}
