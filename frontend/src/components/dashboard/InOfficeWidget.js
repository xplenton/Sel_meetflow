import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api';
import { Users, ChevronRight, MapPin, Clock, MessageSquare, CalendarPlus, X as XIcon } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { toast } from 'sonner';
import { useAuth } from '../../contexts/AuthContext';

/**
 * In-Office-Today Widget (iter 238).
 * Zeigt eine Avatar-Reihe aller Kolleg/innen mit aktiver Desk-Buchung heute.
 * Klick auf Avatar/„Alle anzeigen" öffnet einen Modal mit der Vollliste.
 *
 * Privacy: Backend respektiert `users.hide_from_office_widget` (Opt-Out via Profil).
 * Permissions: Benötigt `view:resources` cap — sonst wird Widget ausgeblendet.
 */
export default function InOfficeWidget() {
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();
  const [data, setData] = useState({ people: [], total: 0, active_now: 0 });
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [showAll, setShowAll] = useState(false);
  // Iter 240 — Person-Action-Modal: DM oeffnen oder "Ich komme auch heute"
  const [actionPerson, setActionPerson] = useState(null);

  useEffect(() => {
    api.get('/resources-in-office')
      .then(({ data: d }) => setData(d || { people: [], total: 0, active_now: 0 }))
      .catch((e) => {
        if (e.response?.status === 403) setDenied(true);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading || denied || data.people.length === 0) return null;

  const visible = data.people.slice(0, 6);
  const more = Math.max(0, data.total - visible.length);

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="in-office-widget">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
          <Users className="w-3.5 h-3.5" />
          Heute im Büro
          <span className="text-[10px] text-[#9CA3AF] font-normal normal-case ml-1">
            ({data.active_now} jetzt aktiv · {data.total} heute)
          </span>
        </h3>
        <button onClick={() => navigate('/resources?tab=floorplan')}
          className="text-[10px] text-[#4A5D4E] hover:underline flex items-center gap-0.5"
          data-testid="in-office-floorplan-link">
          Lageplan <ChevronRight className="w-3 h-3" />
        </button>
      </div>

      <div className="flex items-center gap-3 mb-3">
        <div className="flex items-center -space-x-2">
          {visible.map((p) => (
            <Avatar key={p.user_id} person={p} onClick={() => setActionPerson(p)} />
          ))}
          {more > 0 && (
            <button onClick={() => setShowAll(true)}
              data-testid="in-office-more-btn"
              className="w-9 h-9 rounded-full bg-[#F3F4F1] border-2 border-white flex items-center justify-center text-[11px] font-semibold text-[#6B7280] hover:bg-[#E2E4E0] transition-colors"
              title={`+${more} weitere`}>
              +{more}
            </button>
          )}
        </div>
        <button onClick={() => setShowAll(true)}
          className="text-[11px] text-[#4A5D4E] hover:underline"
          data-testid="in-office-show-all-btn">
          Alle anzeigen
        </button>
      </div>

      {/* Inline-Preview der ersten 3 mit Desk-Nr/Stockwerk */}
      <div className="space-y-1 text-[11px] text-[#6B7280]">
        {visible.slice(0, 3).map(p => (
          <div key={`pv-${p.user_id}`} className="flex items-center justify-between gap-2"
               data-testid={`in-office-row-${p.user_id}`}>
            <span className="font-medium text-[#1C1F1D] truncate">{p.name}</span>
            <span className="text-[10px] truncate">
              {p.desk_number || '—'}{p.floor ? ` · ${p.floor}` : ''}
            </span>
          </div>
        ))}
      </div>

      <FullListDialog open={showAll} onClose={() => setShowAll(false)} people={data.people}
        currentUserId={currentUser?.user_id}
        onPersonClick={(p) => { setShowAll(false); setActionPerson(p); }} />
      <PersonActionDialog person={actionPerson} currentUser={currentUser}
        navigate={navigate}
        onClose={() => setActionPerson(null)} />
    </div>
  );
}

function Avatar({ person, onClick }) {
  const initials = (person.name || '?').split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
  const ring = person.is_active_now ? 'ring-2 ring-emerald-400' : 'ring-2 ring-[#E2E4E0]';
  const src = resolveAvatarSrc(person.avatar_url);
  return (
    <button onClick={onClick}
      title={`${person.name}${person.desk_number ? ` · ${person.desk_number}` : ''}${person.floor ? ` · ${person.floor}` : ''}`}
      className={`relative w-9 h-9 rounded-full overflow-hidden border-2 border-white ${ring} hover:z-10 hover:scale-110 transition-transform`}
      data-testid={`in-office-avatar-${person.user_id}`}>
      {src ? (
        <img src={src} alt={person.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full bg-[#4A5D4E] text-white text-[11px] font-semibold flex items-center justify-center">
          {initials || '?'}
        </div>
      )}
      {person.is_active_now && (
        <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 border border-white rounded-full" />
      )}
    </button>
  );
}

function FullListDialog({ open, onClose, people, currentUserId, onPersonClick }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md max-h-[80vh] overflow-y-auto" data-testid="in-office-dialog">
        <DialogHeader>
          <DialogTitle>Heute im Büro ({people.length})</DialogTitle>
          <DialogDescription>
            Kolleg/innen mit aktiver Desk-Buchung für heute. Grüner Punkt = gerade vor Ort.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 mt-2">
          {people.map(p => {
            const initials = (p.name || '?').split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
            const src = resolveAvatarSrc(p.avatar_url);
            const isSelf = p.user_id === currentUserId;
            return (
              <button key={p.user_id}
                onClick={() => !isSelf && onPersonClick?.(p)}
                disabled={isSelf}
                className={`w-full text-left flex items-center gap-3 p-2 rounded-lg transition-colors ${isSelf ? 'opacity-60' : 'hover:bg-[#F9F9F8] cursor-pointer'}`}
                data-testid={`in-office-dialog-row-${p.user_id}`}>
                <div className="relative w-10 h-10 flex-shrink-0">
                  {src ? (
                    <img src={src} alt={p.name} className="w-10 h-10 rounded-full object-cover" />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-[#4A5D4E] text-white text-xs font-semibold flex items-center justify-center">
                      {initials}
                    </div>
                  )}
                  {p.is_active_now && (
                    <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 border-2 border-white rounded-full" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-[#1C1F1D] truncate">{p.name}</div>
                  <div className="text-[11px] text-[#6B7280] flex items-center gap-1.5 flex-wrap">
                    {p.desk_number && <span>{p.desk_number}</span>}
                    {(p.building || p.floor) && (
                      <span className="flex items-center gap-0.5">
                        <MapPin className="w-3 h-3" />
                        {[p.building, p.floor].filter(Boolean).join(' · ')}
                      </span>
                    )}
                    <span className="flex items-center gap-0.5">
                      <Clock className="w-3 h-3" />
                      {fmtTimeRange(p.start_at, p.end_at)}
                    </span>
                  </div>
                  {p.department && (
                    <Badge variant="outline" className="text-[9px] mt-0.5 border-[#E2E4E0] text-[#6B7280]">
                      {p.department}
                    </Badge>
                  )}
                </div>
                {p.is_active_now && (
                  <Badge className="bg-emerald-100 text-emerald-700 text-[10px] border-emerald-200">jetzt</Badge>
                )}
              </button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function fmtTimeRange(start, end) {
  try {
    const s = new Date(start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    const e = new Date(end).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    return `${s}–${e}`;
  } catch { return ''; }
}

// Resolves /api/... avatar paths to absolute URLs (CRA hot-reload-safe).
function resolveAvatarSrc(src) {
  if (!src) return null;
  if (src.startsWith('http://') || src.startsWith('https://') || src.startsWith('data:')) return src;
  if (src.startsWith('/api/')) {
    const base = process.env.REACT_APP_BACKEND_URL || '';
    return `${base}${src}`;
  }
  return src;
}


/**
 * Person-Action-Dialog (iter 240).
 * Wird bei Klick auf einen Avatar im InOfficeWidget geöffnet. Zeigt:
 *   - "Direktnachricht" → erstellt/öffnet DM und navigiert zu /chat?conv=...
 *   - "Ich komme auch heute" → leitet zur Arbeitsplatz-Buchung weiter (User
 *      sucht selbst einen freien Desk).
 */
function PersonActionDialog({ person, currentUser, navigate, onClose }) {
  const [busy, setBusy] = useState(null);  // 'dm' | 'book' | null
  if (!person) return null;

  const initials = (person.name || '?').split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
  const src = resolveAvatarSrc(person.avatar_url);
  const isSelf = person.user_id === currentUser?.user_id;

  const openDM = async () => {
    if (!currentUser) return;
    setBusy('dm');
    try {
      const { data } = await api.post('/chat/conversations', {
        type: 'direct',
        member_ids: [currentUser.user_id, person.user_id],
      });
      onClose();
      navigate(`/chat?conv=${data.conversation_id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Chat konnte nicht geöffnet werden');
    } finally {
      setBusy(null);
    }
  };

  const bookAlongside = () => {
    // Desk vom Kollegen ist bereits belegt — User leitet sich selbst auf
    // den Arbeitsplatz-Tab weiter um einen freien Desk im gleichen Bereich
    // zu finden.
    toast.info('Wähle einen freien Arbeitsplatz im Lageplan oder der Belegungsübersicht.');
    onClose();
    navigate('/resources?tab=desks');
  };

  return (
    <Dialog open={!!person} onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="sm:max-w-sm" data-testid="in-office-action-dialog">
        <DialogHeader>
          <DialogTitle>Mit {person.name} kontaktieren</DialogTitle>
          <DialogDescription>Schnelle Aktionen für Hybrid-Zusammenarbeit.</DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-3 py-2">
          <div className="relative w-12 h-12 flex-shrink-0">
            {src ? (
              <img src={src} alt={person.name} className="w-12 h-12 rounded-full object-cover" />
            ) : (
              <div className="w-12 h-12 rounded-full bg-[#4A5D4E] text-white text-sm font-semibold flex items-center justify-center">
                {initials}
              </div>
            )}
            {person.is_active_now && (
              <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 border-2 border-white rounded-full" />
            )}
          </div>
          <div className="min-w-0">
            <div className="font-medium">{person.name}</div>
            <div className="text-xs text-[#6B7280] truncate">
              {person.desk_number}{person.floor ? ` · ${person.floor}` : ''}
            </div>
          </div>
        </div>

        {isSelf ? (
          <div className="text-xs text-[#9CA3AF] text-center py-3">Das bist du.</div>
        ) : (
          <div className="space-y-2 mt-2">
            <Button onClick={openDM} disabled={busy === 'dm'}
              data-testid="in-office-action-dm"
              className="w-full justify-start bg-[#4A5D4E] hover:bg-[#3E4F40] text-white">
              <MessageSquare className="w-4 h-4 mr-2" />
              {busy === 'dm' ? 'Öffne Chat…' : 'Direktnachricht senden'}
            </Button>
            <Button onClick={bookAlongside} disabled={busy === 'book'}
              variant="outline"
              data-testid="in-office-action-book"
              className="w-full justify-start">
              <CalendarPlus className="w-4 h-4 mr-2" />
              Ich komme auch heute (Platz wählen)
            </Button>
          </div>
        )}

        <div className="flex justify-end pt-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={!!busy}
            data-testid="in-office-action-close">
            <XIcon className="w-3 h-3 mr-1" /> Schließen
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

