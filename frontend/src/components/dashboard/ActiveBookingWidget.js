import { useEffect, useState, useCallback } from 'react';
import { CheckCircle2, LogIn, LogOut, MapPin, Clock, Loader2, User } from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import api from '../../lib/api';
import { toast } from 'sonner';
import { describeResource, describeBookingUser } from '../../lib/bookingLabels';

/**
 * Iter 283 — Aktive-Buchung-Widget.
 *
 * Zeigt im Dashboard eine prominente Aktions-Karte für DIE Buchung, die
 * gerade läuft (oder in <= 30 Min beginnt) und noch keinen Check-out hat.
 *  - Vor Beginn (`pre-start`): "Termin in X Min — bitte beim Eintreffen einchecken"
 *  - Läuft, ohne Check-in: rotes Banner + "Jetzt einchecken"-Button
 *  - Läuft, eingecheckt: grünes Banner + "Auschecken"-Button
 *  - Auch sichtbar für `booked_for_user_id` (Begünstigter), nicht nur `user_id`.
 */
export default function ActiveBookingWidget() {
  const [booking, setBooking] = useState(null);
  const [acting, setActing] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const now = new Date();
      const horizonEnd = new Date(now.getTime() + 30 * 60 * 1000); // next 30 min
      const { data } = await api.get('/resource-bookings', {
        params: {
          mine: 1,
          from_date: new Date(now.getTime() - 12 * 60 * 60 * 1000).toISOString(),
          to_date: horizonEnd.toISOString(),
        },
      });
      const list = Array.isArray(data) ? data : (data.items || []);
      // Filter to relevant ones: not cancelled/completed, end_at >= now-2h
      const candidates = list
        .filter(b => !['cancelled', 'completed', 'no_show'].includes(b.status))
        .filter(b => {
          const start = new Date(b.start_at);
          const end = new Date(b.end_at);
          if (b.checked_out_at) return false;
          // Within active window OR starting within 30 min
          return (end > now && start <= horizonEnd);
        })
        .sort((a, b) => new Date(a.start_at) - new Date(b.start_at));
      setBooking(candidates[0] || null);
    } catch {
      setBooking(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 60 * 1000);
    return () => clearInterval(t);
  }, [refresh]);

  const checkIn = async () => {
    if (!booking) return;
    setActing(true);
    try {
      await api.post(`/resource-bookings/${booking.booking_id}/check-in`);
      toast.success('Eingecheckt');
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Check-in fehlgeschlagen');
    } finally {
      setActing(false);
    }
  };

  const checkOut = async () => {
    if (!booking) return;
    setActing(true);
    try {
      await api.post(`/resource-bookings/${booking.booking_id}/check-out`, {});
      toast.success('Ausgecheckt');
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Check-out fehlgeschlagen');
    } finally {
      setActing(false);
    }
  };

  if (loading || !booking) return null;

  const now = new Date();
  const start = new Date(booking.start_at);
  const end = new Date(booking.end_at);
  const minsToStart = Math.round((start - now) / 60000);
  const minsAfterEnd = Math.round((now - end) / 60000);
  const checkedIn = !!booking.checked_in_at;
  const isPreStart = now < start;
  const isOverdueCheckout = !checkedIn ? false : (now > end);

  // Visual state
  let state = 'idle';
  if (isPreStart) state = 'pre-start';
  else if (!checkedIn) state = 'awaiting-checkin';
  else if (isOverdueCheckout) state = 'awaiting-checkout';
  else state = 'active';

  const palette = {
    'pre-start':         { bg: 'bg-amber-50',  border: 'border-amber-300',  text: 'text-amber-900',  Icon: Clock,         label: `Beginnt in ${Math.max(0, minsToStart)} Min` },
    'awaiting-checkin':  { bg: 'bg-rose-50',   border: 'border-rose-300',   text: 'text-rose-900',   Icon: LogIn,         label: 'Bitte einchecken' },
    'awaiting-checkout': { bg: 'bg-orange-50', border: 'border-orange-300', text: 'text-orange-900', Icon: LogOut,        label: `Beendet vor ${minsAfterEnd} Min — bitte auschecken` },
    'active':            { bg: 'bg-emerald-50',border: 'border-emerald-300',text: 'text-emerald-900',Icon: CheckCircle2,  label: 'Aktiv — eingecheckt' },
  }[state];

  return (
    <div className={`mb-3 px-4 py-3 ${palette.bg} ${palette.border} border rounded-xl flex items-center gap-3 flex-wrap`}
         data-testid="active-booking-widget">
      <div className={`w-9 h-9 rounded-full bg-white/70 flex items-center justify-center flex-shrink-0 ${palette.text}`}>
        <palette.Icon className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-[180px]">
        <div className="flex items-center gap-2 flex-wrap">
          <p className={`text-sm font-semibold ${palette.text}`} data-testid="active-booking-title">{booking.title}</p>
          <Badge variant="outline" className={`text-[10px] ${palette.text} ${palette.border}`}>
            {palette.label}
          </Badge>
          {booking.booked_for_user_id && (
            <Badge variant="outline" className="text-[10px]">Stellvertretung</Badge>
          )}
        </div>
        <div className="text-[11px] text-[#6B7280] mt-0.5 flex items-center gap-2 flex-wrap">
          <Clock className="w-3 h-3" />
          {start.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} – {end.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
          {/* Iter 325 — Klartext-Anzeige (Ressourcen-Name + Kennzeichen
              bzw. Gebäude/Etage) statt nackter resource_id */}
          {describeResource(booking) && (
            <span className="inline-flex items-center gap-1" data-testid="active-booking-resource">
              <MapPin className="w-3 h-3" /> {describeResource(booking)}
            </span>
          )}
          {describeBookingUser(booking) && (
            <span className="inline-flex items-center gap-1" data-testid="active-booking-user">
              <User className="w-3 h-3" /> {describeBookingUser(booking)}
            </span>
          )}
        </div>
      </div>
      {state === 'awaiting-checkin' || state === 'pre-start' ? (
        <Button size="sm" disabled={acting || isPreStart && minsToStart > 5} onClick={checkIn}
                data-testid="active-booking-checkin-btn"
                className="bg-[#4A5D4E] text-white hover:bg-[#3a4a3e]">
          {acting ? <Loader2 className="w-3 h-3 animate-spin" /> : <><LogIn className="w-3 h-3 mr-1" /> Einchecken</>}
        </Button>
      ) : null}
      {state === 'awaiting-checkout' || state === 'active' ? (
        <Button size="sm" variant="outline" disabled={acting} onClick={checkOut}
                data-testid="active-booking-checkout-btn">
          {acting ? <Loader2 className="w-3 h-3 animate-spin" /> : <><LogOut className="w-3 h-3 mr-1" /> Auschecken</>}
        </Button>
      ) : null}
    </div>
  );
}
