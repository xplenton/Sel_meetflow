import { useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import {
  Wifi, WifiOff, BellRing, BellOff, MessageCircle, Mail, CheckCircle2,
} from 'lucide-react';
import api from '../../lib/api';

/**
 * Reachability Popover (iter 145) — shows the host per-invitee reachability
 * BEFORE they press "Klingeln", so they know who will actually be reached:
 *
 *   🟢 online (chat WS connected)
 *   🔔 push_enabled (web-push subscription registered on at least one device)
 *   ⚪ neither — only reachable out-of-band (WhatsApp / e-mail)
 *   ✅ in_meeting — already inside
 *
 * Fetches lazily on open to avoid hammering the API while the list renders.
 * Extracted from MeetingsPage during the iter 217 refactor.
 */
export default function ReachabilityPopover({ meetingId, meeting }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data: r } = await api.get(`/meetings/${meetingId}/reachability`);
      setData(r);
    } catch { setData({ invitees: [], total: 0, reachable: 0, error: true }); }
    finally { setLoading(false); }
  };

  const handleOpen = (o) => {
    setOpen(o);
    if (o && !data) load();
  };

  const summary = data ? `${data.reachable}/${data.total}` : '…';
  const allReachable = data && data.total > 0 && data.reachable === data.total;

  const joinLink = `${window.location.origin}/meetings/${meetingId}/join`;
  const buildWaText = (inv) =>
    `Hi ${inv.name || ''}, wir warten auf dich im Meeting "${meeting?.title || ''}". Beitreten: ${joinLink}`;
  const buildEmail = (inv) => ({
    subject: `Wir warten auf dich: ${meeting?.title || 'Meeting'}`,
    body: `Hi ${inv.name || ''},\n\nwir warten im Meeting "${meeting?.title || ''}" auf dich.\n\nBeitreten: ${joinLink}${meeting?.meeting_code ? `\nCode: ${meeting.meeting_code}` : ''}\n\nDanke!`,
  });

  return (
    <Popover open={open} onOpenChange={handleOpen}>
      <PopoverTrigger asChild>
        <button
          data-testid={`reach-trigger-${meetingId}`}
          className={`text-[10px] h-8 px-2 rounded-lg flex items-center gap-1 border transition-colors ${
            allReachable
              ? 'border-[#6B8E23]/30 text-[#6B8E23] hover:bg-[#6B8E23]/10'
              : 'border-[#E2E4E0] text-[#9CA3AF] hover:text-[#4A5D4E] hover:bg-[#F3F4F1]'
          }`}
          title="Push- & Online-Status der Teilnehmer"
        >
          <Wifi className="w-3 h-3" />
          <span className="hidden sm:inline">{summary}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0" data-testid={`reach-popover-${meetingId}`}>
        <div className="px-3 py-2 border-b border-[#E2E4E0]">
          <p className="text-xs font-medium text-[#1C1F1D]">Erreichbarkeit</p>
          <p className="text-[10px] text-[#9CA3AF]">Wer wird klingeln, wenn du jetzt anrufst?</p>
        </div>
        <div className="max-h-80 overflow-y-auto">
          {loading && <p className="text-[11px] text-[#9CA3AF] px-3 py-4 text-center">Lade …</p>}
          {!loading && data?.error && <p className="text-[11px] text-[#C87967] px-3 py-4 text-center">Fehler beim Laden</p>}
          {!loading && data && data.invitees.length === 0 && (
            <p className="text-[11px] text-[#9CA3AF] px-3 py-4 text-center">Keine weiteren Teilnehmer eingeladen</p>
          )}
          {!loading && data?.invitees.map((inv, i) => {
            const unreachable = !inv.push_enabled && !inv.online && !inv.in_meeting;
            return (
              <div key={inv.user_id || inv.email || i}
                className="flex items-center gap-2 px-3 py-2 hover:bg-[#F3F4F1] text-xs border-b border-[#E2E4E0] last:border-0"
                data-testid={`reach-row-${inv.user_id || inv.email}`}>
                <div className="w-7 h-7 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                  {inv.avatar ? (
                    <img src={inv.avatar} alt="" className="w-full h-full rounded-full object-cover" />
                  ) : (
                    <span className="text-[10px] font-medium text-[#4A5D4E]">{(inv.name?.[0] || '?').toUpperCase()}</span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-medium text-[#1C1F1D] truncate">{inv.name}</p>
                  <p className="text-[9px] text-[#9CA3AF] truncate">{inv.email}</p>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0" title={
                  inv.in_meeting ? 'Bereits im Meeting'
                  : inv.online ? (inv.push_enabled ? 'Online + Push aktiv' : 'Online (Tab offen)')
                  : inv.push_enabled ? 'Push aktiv (klingelt)'
                  : inv.is_guest ? 'Gast — nur per E-Mail erreichbar'
                  : 'Nicht erreichbar (kein Push, offline)'
                }>
                  {inv.in_meeting ? (
                    <CheckCircle2 className="w-4 h-4 text-[#6B8E23]" />
                  ) : (
                    <>
                      {inv.online
                        ? <Wifi className="w-3.5 h-3.5 text-[#6B8E23]" />
                        : <WifiOff className="w-3.5 h-3.5 text-[#9CA3AF]/60" />}
                      {inv.push_enabled
                        ? <BellRing className="w-3.5 h-3.5 text-[#D4A373]" />
                        : <BellOff className="w-3.5 h-3.5 text-[#9CA3AF]/60" />}
                    </>
                  )}
                </div>
                {unreachable && (
                  <div className="flex items-center gap-0.5 flex-shrink-0 ml-1 pl-1 border-l border-[#E2E4E0]">
                    <button
                      onClick={() => window.open(`https://wa.me/?text=${encodeURIComponent(buildWaText(inv))}`, '_blank')}
                      className="w-6 h-6 rounded hover:bg-[#25D366]/10 text-[#25D366] flex items-center justify-center transition-colors"
                      title="Per WhatsApp nachfragen"
                      data-testid={`reach-wa-${inv.user_id || inv.email}`}>
                      <MessageCircle className="w-3.5 h-3.5" />
                    </button>
                    {inv.email && (
                      <button
                        onClick={() => {
                          const { subject, body } = buildEmail(inv);
                          window.open(`mailto:${inv.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
                        }}
                        className="w-6 h-6 rounded hover:bg-[#4A5D4E]/10 text-[#4A5D4E] flex items-center justify-center transition-colors"
                        title="Per E-Mail nachfragen"
                        data-testid={`reach-mail-${inv.user_id || inv.email}`}>
                        <Mail className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {!loading && data && data.invitees.some(i => !i.push_enabled && !i.online && !i.in_meeting) && (
          <div className="px-3 py-2 border-t border-[#E2E4E0] bg-[#FFF8E7]">
            <p className="text-[10px] text-[#B8875C] leading-snug">
              <BellOff className="w-3 h-3 inline-block mr-1" />
              Nutze WhatsApp oder E-Mail daneben, um unerreichbare Teilnehmer zu informieren.
            </p>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
