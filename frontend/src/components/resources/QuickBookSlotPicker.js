import { useEffect, useState, useMemo } from 'react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { toast } from 'sonner';
import { Loader2, Car } from 'lucide-react';

/**
 * Iter 250 — Quick-Book-Slot-Picker direkt in der ResourceCard.
 * Iter 261 — Vehicle-Variante mit km-Schnellerfassung + Zweck-Input.
 *
 * Zeigt einen klickbaren Tagesbalken (8–20h) mit:
 *   - grauen Segmenten = bestehende Buchungen
 *   - klickbare 1h-Slots = freie Slots
 * Klick auf freien Slot -> bestätigen + 1-Klick-Buchung.
 *
 * Reduziert die Klick-Pfad-Länge von ~5 (Card -> Dialog -> Datum -> Zeit ->
 * Speichern) auf 2 (Slot-Click -> Bestätigen).
 *
 * Bei type='vehicle': zeigt zusätzlich km-Stand (vorausgefüllt mit
 * resource.mileage) + Zweck/Ziel-Feld.
 *
 * Props:
 *   resourceId: string
 *   resourceName: string (für default title)
 *   resourceType?: string  (z.B. 'vehicle' → km-Schnellerfassung)
 *   currentMileage?: number  (vorbelegt im km-Feld)
 *   onBooked: () => void   (refresh-Callback nach erfolgreicher Buchung)
 *   onOpenFullDialog: () => void  (Escape-Hatch zum vollen BookingDialog)
 */
const DAY_START_H = 8;
const DAY_END_H = 20;

export default function QuickBookSlotPicker({
  resourceId,
  resourceName,
  resourceType,
  currentMileage,
  prefetchedBookings,
  onBooked,
  onOpenFullDialog,
}) {
  const [bookings, setBookings] = useState(prefetchedBookings || []);
  const [loading, setLoading] = useState(!prefetchedBookings);
  const [pickedHour, setPickedHour] = useState(null);
  const [booking, setBooking] = useState(false);
  // Iter 261 — Vehicle-spezifisch
  const isVehicle = resourceType === 'vehicle';
  const [mileage, setMileage] = useState(currentMileage ?? '');
  const [destination, setDestination] = useState('');

  // Always show "today" — heute relevant für Quick-Book.
  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  // Iter 356 — Bookings kommen jetzt IMMER vom Parent (ResourcesPage)
  // über `prefetchedBookings`. Ein eigener Fetch ist nicht mehr nötig und
  // wurde entfernt, weil er die Single-Source-of-Truth-Garantie aushebeln
  // würde (Picker und Snapshot könnten sich kurzzeitig unterscheiden).
  // Wenn `prefetchedBookings === undefined`, wartet die Komponente einfach
  // mit "lädt …" — der scoped Hybrid-Call landet typischerweise in ~50 ms.
  useEffect(() => {
    if (prefetchedBookings !== undefined) {
      setBookings(prefetchedBookings || []);
      setLoading(false);
    } else {
      setLoading(true);
    }
  }, [prefetchedBookings]);

  // Build hour grid 8..19 (12 slots of 1h)
  const slots = useMemo(() => {
    const arr = [];
    const now = new Date();
    for (let h = DAY_START_H; h < DAY_END_H; h += 1) {
      const slotStart = new Date(today);
      slotStart.setHours(h, 0, 0, 0);
      const slotEnd = new Date(today);
      slotEnd.setHours(h + 1, 0, 0, 0);
      // Conflict if any booking (status confirmed/pending) overlaps this hour.
      // Iter 350 — Explicit allow-list so cancelled / no_show / completed
      // bookings don't render as blocked. Aligns the SlotPicker with the
      // `Frei bis HH:MM`-badge on the resource card (backend snapshot uses
      // the same allow-list).
      const blocked = bookings.some(b => {
        if (b.status && b.status !== 'confirmed' && b.status !== 'pending_approval') return false;
        const bs = new Date(b.start_at);
        const be = new Date(b.end_at);
        return bs < slotEnd && be > slotStart;
      });
      const isPast = slotEnd <= now;
      arr.push({ hour: h, start: slotStart, end: slotEnd, blocked, isPast });
    }
    return arr;
  }, [bookings, today]);

  const submit = async () => {
    if (pickedHour === null) return;
    const slot = slots.find(s => s.hour === pickedHour);
    if (!slot) return;
    setBooking(true);
    try {
      const body = {
        resource_id: resourceId,
        title: `Quick-Buchung · ${resourceName}`,
        start_at: slot.start.toISOString(),
        end_at: slot.end.toISOString(),
      };
      // Iter 261 — Vehicle-spezifische Felder mitsenden
      if (isVehicle) {
        if (mileage !== '' && mileage !== null && !Number.isNaN(Number(mileage))) {
          body.mileage_before = Number(mileage);
        }
        if (destination.trim()) {
          body.destination = destination.trim();
          body.title = `Fahrt · ${destination.trim()}`;
        }
      }
      await api.post('/resource-bookings', body);
      const label = slot.start.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
      toast.success(`Buchung um ${label} erstellt`);
      setPickedHour(null);
      setDestination('');
      // Reload day bookings + parent
      const dayEnd = new Date(today);
      dayEnd.setDate(dayEnd.getDate() + 1);
      const r = await api.get('/resource-bookings', {
        params: { resource_id: resourceId, from_date: today.toISOString(), to_date: dayEnd.toISOString() },
      });
      setBookings(r.data || []);
      onBooked?.();
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : (d?.detail || 'Buchung fehlgeschlagen'));
    } finally {
      setBooking(false);
    }
  };

  if (loading) {
    return (
      <div className="mt-2 h-7 flex items-center text-[10px] text-[#9CA3AF]" data-testid={`quickbook-loading-${resourceId}`}>
        <Loader2 className="w-3 h-3 mr-1 animate-spin" /> Lade Slots…
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-1.5" data-testid={`quickbook-${resourceId}`}>
      {/* Iter 355 — Mobile-UX: Stundenslots auf Handy h-8 (≈32px) statt h-5 (20px).
         Touch-Zielfläche jetzt > 30 px (Apple HIG-Empfehlung), Tippen ist
         deutlich präziser. Desktop bleibt kompakt mit sm:h-5. */}
      <div className="grid grid-cols-12 gap-px">
        {slots.map(s => {
          const isPicked = pickedHour === s.hour;
          let cls = 'h-8 sm:h-5 text-[11px] sm:text-[8px] flex items-center justify-center cursor-pointer transition-colors ';
          if (s.blocked) cls += 'bg-zinc-300 text-zinc-500 cursor-not-allowed';
          else if (s.isPast) cls += 'bg-zinc-100 text-zinc-300 cursor-not-allowed';
          else if (isPicked) cls += 'bg-[#4A5D4E] text-white ring-2 ring-[#4A5D4E] ring-offset-1';
          else cls += 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200 active:bg-emerald-300';
          return (
            <button
              key={s.hour}
              type="button"
              disabled={s.blocked || s.isPast || booking}
              onClick={() => setPickedHour(isPicked ? null : s.hour)}
              className={cls}
              title={s.blocked ? 'belegt' : s.isPast ? 'vergangen' : `${s.hour}:00 – ${s.hour + 1}:00`}
              data-testid={`quickbook-slot-${resourceId}-${s.hour}`}
            >
              {s.hour}
            </button>
          );
        })}
      </div>
      <div className="flex items-center justify-between flex-wrap gap-1">
        <span className="text-[9px] text-[#9CA3AF]">Heute · 8–20 Uhr · Stunden-Slots</span>
        {pickedHour !== null ? (
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-medium text-[#1C1F1D]">{pickedHour}:00–{pickedHour + 1}:00</span>
            {/* Iter 355 — größerer Touch-CTA: h-8 statt h-6, sm:h-6 für Desktop */}
            <Button
              size="sm"
              className="h-8 sm:h-6 text-[11px] sm:text-[10px] px-3 sm:px-2 bg-[#4A5D4E] hover:bg-[#3E4F40]"
              onClick={submit}
              disabled={booking}
              data-testid={`quickbook-confirm-${resourceId}`}
            >
              {booking ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Sofort buchen'}
            </Button>
          </div>
        ) : (
          <button
            type="button"
            className="text-[11px] sm:text-[10px] text-[#4A5D4E] hover:underline px-1 py-1 -my-1"
            onClick={onOpenFullDialog}
            data-testid={`quickbook-fulldialog-${resourceId}`}
          >
            Andere Zeit …
          </button>
        )}
      </div>
      {/* Iter 261 — Vehicle-Quick-Book: km-Schnellerfassung + Ziel */}
      {isVehicle && pickedHour !== null && (
        <div className="flex items-center gap-1 pt-1" data-testid={`quickbook-vehicle-fields-${resourceId}`}>
          <Car className="w-3 h-3 text-[#6B7280] shrink-0" />
          <Input
            type="number"
            inputMode="numeric"
            value={mileage}
            onChange={(e) => setMileage(e.target.value)}
            placeholder="km-Stand"
            className="h-6 text-[10px] px-1 w-20"
            data-testid={`quickbook-mileage-${resourceId}`}
            title="km-Stand bei Fahrtbeginn (vorausgefüllt)"
          />
          <Input
            type="text"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="Ziel (optional)"
            className="h-6 text-[10px] px-1 flex-1 min-w-0"
            data-testid={`quickbook-destination-${resourceId}`}
            maxLength={80}
          />
        </div>
      )}
    </div>
  );
}
