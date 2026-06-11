import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Clock } from 'lucide-react';
import { toLocal } from './bookingHelpers';
import { toast } from 'sonner';

const QUICK_DATES = [
  { mode: 'today-now',       label: 'Heute +1 Std.',  testid: 'qd-today-now' },
  { mode: 'today-afternoon', label: 'Heute 14:00',    testid: 'qd-today-pm' },
  { mode: 'tomorrow-am',     label: 'Morgen 09:00',   testid: 'qd-tomorrow-am' },
  { mode: 'tomorrow-pm',     label: 'Morgen 14:00',   testid: 'qd-tomorrow-pm' },
  { mode: 'next-week',       label: 'Nächste Woche',  testid: 'qd-next-week' },
];

const QUICK_DURATIONS = [
  { l: '30 Min',  m: 30 },
  { l: '1 Std',   m: 60 },
  { l: '1,5 Std', m: 90 },
  { l: '2 Std',   m: 120 },
  { l: '4 Std',   m: 240 },
  { l: 'Halbtag', m: 240 },
  { l: 'Ganztag', m: 480 },
];

export default function BookingDateTimeFields({ start, end, durationMin, onStart, onEnd, onSetQuickDate, onSetDuration }) {
  return (
    <>
      <div data-testid="booking-quick-date">
        <Label className="text-xs">Schnellauswahl Datum</Label>
        <div className="flex flex-wrap gap-1 mt-1">
          {QUICK_DATES.map(qd => (
            <Button key={qd.mode} type="button" variant="outline" size="sm"
                    onClick={() => onSetQuickDate(qd.mode)} data-testid={qd.testid}>
              {qd.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <Label>Von <span className="text-rose-600">*</span></Label>
          <Input
            data-testid="booking-start-input"
            type="datetime-local"
            value={start}
            onChange={e => {
              const newStart = e.target.value;
              onStart(newStart);
              if (newStart && (!end || new Date(end) <= new Date(newStart))) {
                const d = new Date(newStart);
                d.setHours(d.getHours() + 1);
                onEnd(toLocal(d));
              }
            }}
          />
        </div>
        <div>
          <Label>Bis <span className="text-rose-600">*</span></Label>
          <Input
            data-testid="booking-end-input"
            type="datetime-local"
            value={end}
            min={start || undefined}
            onChange={e => {
              const newEnd = e.target.value;
              if (start && newEnd && new Date(newEnd) <= new Date(start)) {
                toast.error('Endzeit muss nach der Startzeit liegen');
                return;
              }
              onEnd(newEnd);
            }}
          />
        </div>
      </div>

      <div data-testid="booking-quick-duration">
        <Label className="text-xs">Schnellauswahl Dauer</Label>
        <div className="flex flex-wrap gap-1 mt-1">
          {QUICK_DURATIONS.map(b => (
            <Button key={b.l} type="button" variant={durationMin === b.m ? 'default' : 'outline'}
                    size="sm" onClick={() => onSetDuration(b.m)}
                    data-testid={`dur-${b.m}`}>
              {b.l}
            </Button>
          ))}
        </div>
        {durationMin > 0 && (
          <div className="text-[10px] text-[#6B7280] mt-1 inline-flex items-center gap-1">
            <Clock className="w-3 h-3" /> Dauer: {durationMin} Min ({(durationMin / 60).toFixed(1)} Std.)
          </div>
        )}
      </div>
    </>
  );
}
