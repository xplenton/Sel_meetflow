import { Input } from './ui/input';
import { Calendar, Clock } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

/**
 * Einheitliche Datum/Uhrzeit-Eingabe für die gesamte App.
 * - Datum: type="date" (manuell editierbar)
 * - Uhrzeit: type="time" (manuell editierbar)
 * Beide Felder sind immer manuell veränderbar.
 */

export function DateInput({ value, onChange, className = '', ...props }) {
  return (
    <div className={`relative ${className}`}>
      <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF] pointer-events-none" />
      <Input type="date" value={value || ''} onChange={e => onChange(e.target.value)}
        className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl h-10 text-sm" {...props} />
    </div>
  );
}

export function TimeInput({ value, onChange, className = '', ...props }) {
  return (
    <div className={`relative min-w-0 ${className}`}>
      <Clock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF] pointer-events-none" />
      <Input type="time" value={value || ''} onChange={e => onChange(e.target.value)}
        className="pl-10 pr-2 border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl h-10 text-sm w-full min-w-[110px]" {...props} />
    </div>
  );
}

export function DateTimeInput({ date, time, onDateChange, onTimeChange, className = '' }) {
  return (
    <div className={`flex flex-col sm:flex-row sm:items-center gap-2 ${className}`}>
      <DateInput value={date} onChange={onDateChange} className="w-full sm:flex-1" />
      <TimeInput value={time} onChange={onTimeChange} className="w-full sm:w-[140px]" />
    </div>
  );
}

/**
 * Start- und Endzeit mit Validierung.
 * Endzeit darf nicht vor Startzeit liegen.
 */
export function TimeRangeInput({ startTime, endTime, onStartChange, onEndChange, className = '' }) {
  const { t } = useLanguage();
  const invalid = startTime && endTime && endTime <= startTime;

  const handleStartChange = (v) => {
    onStartChange(v);
    if (endTime && v >= endTime) {
      const [h, m] = v.split(':').map(Number);
      const newEnd = `${String(Math.min(h + 1, 23)).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      onEndChange(newEnd);
    }
  };

  const handleEndChange = (v) => {
    if (startTime && v <= startTime) return;
    onEndChange(v);
  };

  return (
    <div className={`flex items-center gap-2 min-w-0 ${className}`}>
      <TimeInput value={startTime} onChange={handleStartChange} className="flex-1 min-w-0" />
      <span className="text-xs text-[#9CA3AF] flex-shrink-0">bis</span>
      <div className="relative flex-1 min-w-0">
        <TimeInput value={endTime} onChange={handleEndChange}
          className={invalid ? '[&_input]:border-[#C87967] [&_input]:text-[#C87967]' : ''} />
        {invalid && <span className="absolute -bottom-4 left-0 text-[10px] text-[#C87967]">{t('mustBeAfterStart')}</span>}
      </div>
    </div>
  );
}

/** Parse ISO string into { date, time } */
export function parseDateTime(iso) {
  if (!iso) return { date: '', time: '' };
  const parts = iso.split('T');
  return { date: parts[0] || '', time: (parts[1] || '').slice(0, 5) || '' };
}

/** Combine date + time into ISO string */
export function combineDateTime(date, time) {
  if (!date) return '';
  return time ? `${date}T${time}` : date;
}
