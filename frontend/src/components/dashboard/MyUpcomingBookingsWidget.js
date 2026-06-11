/**
 * Iter 325 — „Meine nächsten Buchungen" — Dashboard-Widget.
 *
 * Zeigt die nächsten bis zu 5 anstehenden eigenen Ressourcen-Buchungen
 * (oder Stellvertreter-Buchungen) als kompakte Liste mit Klartext-
 * Ressourcen-Label und User-Info ("Gebucht von …" / "Gebucht für …").
 *
 * Datenquelle: GET /api/resource-bookings?mine_only=true&from_date=now
 * Backend hydriert resource_name / license_plate / building / floor /
 * user_name / booked_for_name (siehe routes/resources/bookings.py).
 */
import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, ChevronRight, Building2, Sofa, Car, Clock } from 'lucide-react';
import api from '../../lib/api';
import { describeResource, describeBookingUser } from '../../lib/bookingLabels';

const TYPE_ICON = { room: Building2, desk: Sofa, vehicle: Car };

function _fmtWhen(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(tomorrow.getDate() + 1);
  const dayStart = new Date(d); dayStart.setHours(0, 0, 0, 0);
  const time = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  if (dayStart.getTime() === today.getTime()) return `Heute · ${time}`;
  if (dayStart.getTime() === tomorrow.getTime()) return `Morgen · ${time}`;
  return d.toLocaleString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function MyUpcomingBookingsWidget({ isDE = true }) {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const now = new Date();
      const { data } = await api.get('/resource-bookings', {
        params: {
          mine_only: true,
          from_date: now.toISOString(),
          // Nächste 30 Tage genügen für den Dashboard-Snapshot
          to_date: new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000).toISOString(),
        },
      });
      const list = (Array.isArray(data) ? data : (data.items || []))
        .filter(b => !['cancelled', 'completed', 'no_show'].includes(b.status))
        .sort((a, b) => new Date(a.start_at) - new Date(b.start_at))
        .slice(0, 5);
      setItems(list);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-5 flex flex-col"
         data-testid="my-upcoming-bookings-widget">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5" />
          {isDE ? 'Meine nächsten Buchungen' : 'My next bookings'}
          {items.length > 0 && (
            <span className="text-[10px] text-[#9CA3AF] font-normal normal-case ml-1">({items.length})</span>
          )}
        </h3>
        <button onClick={() => navigate('/resources?tab=mine')}
                className="text-[10px] text-[#4A5D4E] hover:underline flex items-center gap-0.5"
                data-testid="my-upcoming-bookings-all">
          {isDE ? 'Alle' : 'All'} <ChevronRight className="w-3 h-3" />
        </button>
      </div>

      {loading ? (
        <div className="text-xs text-[#9CA3AF] py-2">{isDE ? 'Lade …' : 'Loading …'}</div>
      ) : items.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-4">
          <Calendar className="w-8 h-8 text-[#E2E4E0] mb-1.5" />
          <p className="text-xs text-[#9CA3AF]">{isDE ? 'Keine anstehenden Buchungen' : 'No upcoming bookings'}</p>
          <button onClick={() => navigate('/resources')}
                  className="mt-2 text-[11px] text-[#4A5D4E] hover:underline"
                  data-testid="my-upcoming-bookings-empty-cta">
            + {isDE ? 'Ressource buchen' : 'Book a resource'}
          </button>
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map(b => {
            const Icon = TYPE_ICON[b.resource_type] || Calendar;
            const resLabel = describeResource(b);
            const userLabel = describeBookingUser(b);
            return (
              <li key={b.booking_id}
                  className="flex items-start gap-3 px-2 py-2 rounded-lg hover:bg-[#F3F4F1] cursor-pointer transition-colors"
                  onClick={() => navigate('/resources?tab=mine')}
                  data-testid={`upcoming-booking-${b.booking_id}`}>
                <div className="w-8 h-8 rounded-lg bg-[#F3F4F1] flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-[#4A5D4E]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-[#1C1F1D] truncate">{b.title}</div>
                  {resLabel && (
                    <div className="text-[11px] text-[#4A5D4E] truncate"
                         data-testid={`upcoming-resource-${b.booking_id}`}>
                      {resLabel}
                    </div>
                  )}
                  {userLabel && (
                    <div className="text-[10px] text-[#9CA3AF] truncate"
                         data-testid={`upcoming-user-${b.booking_id}`}>
                      {userLabel}
                    </div>
                  )}
                  <div className="text-[10px] text-[#9CA3AF] flex items-center gap-1 mt-0.5">
                    <Clock className="w-3 h-3" /> {_fmtWhen(b.start_at)}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
