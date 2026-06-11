import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api';
import { CalendarDays, ChevronRight } from 'lucide-react';

/**
 * OfficeWeekWidget (iter 242).
 * Mini-Kalender Mo–Fr auf dem Dashboard. Pro Tag eine Avatar-Spalte der
 * Kolleg/innen mit confirmed Desk-Buchung.
 *
 * Backend: GET /api/resources-office-week
 * Privacy: Backend respektiert hide_from_office_widget Opt-Out.
 */
export default function OfficeWeekWidget() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    api.get('/resources-office-week')
      .then(({ data: d }) => setData(d))
      .catch((e) => { if (e.response?.status === 403) setDenied(true); })
      .finally(() => setLoading(false));
  }, []);

  if (loading || denied || !data) return null;
  const totalPeople = (data.days || []).reduce((s, d) => s + d.count + (d.absent_count || 0), 0);
  if (totalPeople === 0) return null;

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="office-week-widget">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
          <CalendarDays className="w-3.5 h-3.5" />
          Diese Woche im Büro
          <span className="text-[10px] text-[#9CA3AF] font-normal normal-case ml-1">
            ab {new Date(data.week_start).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}
          </span>
        </h3>
        <button onClick={() => navigate('/profile#office-days')}
          className="text-[10px] text-[#4A5D4E] hover:underline flex items-center gap-0.5"
          data-testid="office-week-config-link">
          Meine Tage <ChevronRight className="w-3 h-3" />
        </button>
      </div>

      <div className="grid grid-cols-5 gap-2">
        {(data.days || []).map((d) => (
          <DayColumn key={d.date} day={d} />
        ))}
      </div>
    </div>
  );
}

function DayColumn({ day }) {
  const today = new Date().toISOString().slice(0, 10);
  const isToday = day.date === today;
  const visible = (day.people || []).slice(0, 4);
  const more = Math.max(0, (day.count || 0) - visible.length);
  const absent = day.absent || [];

  return (
    <div data-testid={`office-week-day-${day.weekday.toLowerCase()}`}
      className={`rounded-lg border p-2 text-center ${
        isToday ? 'border-[#4A5D4E] bg-[#F3F4F1]' : 'border-[#E2E4E0]'
      }`}>
      <div className="text-[10px] font-semibold text-[#6B7280] uppercase tracking-wide">
        {day.weekday}
      </div>
      <div className="text-[10px] text-[#9CA3AF] mb-1.5">
        {new Date(day.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}
      </div>
      <div className="flex items-center justify-center flex-wrap gap-0.5 min-h-[26px]">
        {visible.map(p => <PersonAvatar key={p.user_id} person={p} />)}
        {more > 0 && (
          <span className="text-[9px] font-semibold text-[#6B7280] bg-[#F3F4F1] rounded-full w-5 h-5 flex items-center justify-center"
            title={`+${more} weitere`}>
            +{more}
          </span>
        )}
        {day.count === 0 && absent.length === 0 && (
          <span className="text-[10px] text-[#9CA3AF]">—</span>
        )}
      </div>
      <div className="text-[10px] text-[#6B7280] mt-1">{day.count}</div>
      {/* Iter 243 — Abwesende mit Grund (Krank/Homeoffice/Urlaub/...) */}
      {absent.length > 0 && (
        <div className="mt-1.5 pt-1 border-t border-[#E2E4E0] space-y-0.5"
          data-testid={`office-week-absent-${day.weekday.toLowerCase()}`}>
          {absent.slice(0, 3).map(a => (
            <div key={a.user_id} className="flex items-center justify-center gap-1 text-[9px] text-[#9CA3AF]"
              title={`${a.name} · ${a.reason_label}${a.note ? `: ${a.note}` : ''}`}>
              <span>{a.emoji}</span>
              <span className="truncate max-w-[60px]">{a.name.split(' ')[0]}</span>
            </div>
          ))}
          {absent.length > 3 && (
            <div className="text-[9px] text-[#9CA3AF]">+{absent.length - 3}</div>
          )}
        </div>
      )}
    </div>
  );
}

function PersonAvatar({ person }) {
  const initials = (person.name || '?').split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
  const src = resolveAvatarSrc(person.avatar_url);
  return (
    <span className="inline-block w-5 h-5 rounded-full overflow-hidden border border-white shadow-sm"
      title={`${person.name}${person.desk_number ? ` · ${person.desk_number}` : ''}`}>
      {src ? (
        <img src={src} alt={person.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full bg-[#4A5D4E] text-white text-[8px] font-semibold flex items-center justify-center">
          {initials}
        </div>
      )}
    </span>
  );
}

function resolveAvatarSrc(src) {
  if (!src) return null;
  if (src.startsWith('http://') || src.startsWith('https://') || src.startsWith('data:')) return src;
  if (src.startsWith('/api/')) {
    const base = process.env.REACT_APP_BACKEND_URL || '';
    return `${base}${src}`;
  }
  return src;
}
