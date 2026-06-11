import { useLanguage } from '../contexts/LanguageContext';
import { ScrollArea } from '../components/ui/scroll-area';
import { Badge } from '../components/ui/badge';
import { X, Mic, MicOff, Video, VideoOff, Hand, MoreVertical, UserMinus, ShieldCheck, Stethoscope } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../components/ui/dropdown-menu';

export default function ParticipantPanel({ participants, onClose, currentUserId, isHost, onAction }) {
  const { t } = useLanguage();

  const roleColors = {
    host: 'bg-[#4A5D4E]/10 text-[#4A5D4E]',
    'co-host': 'bg-[#D4A373]/10 text-[#D4A373]',
    participant: 'bg-[#9CA3AF]/10 text-[#9CA3AF]',
    guest: 'bg-[#E8EAE6] text-[#6B7280]',
  };

  return (
    <div className="w-full sm:w-80 fixed inset-0 sm:static sm:inset-auto bg-white border-l border-[#E2E4E0] flex flex-col h-full z-40 sm:z-auto" data-testid="participant-panel">
      <div className="flex items-center justify-between p-4 border-b border-[#E2E4E0]">
        <h3 className="text-sm font-medium text-[#1C1F1D]">{t('participants')} ({participants.length})</h3>
        <button onClick={onClose} data-testid="close-participants-button" className="p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF]"><X className="w-4 h-4" /></button>
      </div>

      <ScrollArea className="flex-1 p-2">
        <div className="space-y-1">
          {participants.map(p => (
            <div key={p.user_id} className="flex items-center gap-3 p-3 rounded-lg hover:bg-[#F3F4F1] transition-colors"
              data-testid={`participant-${p.user_id}`}>
              <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs font-medium text-[#4A5D4E] flex-shrink-0">
                {p.avatar ? <img src={p.avatar} alt="" className="w-8 h-8 rounded-full object-cover" /> : (p.name?.[0]?.toUpperCase() || '?')}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-[#1C1F1D] truncate">{p.name}</span>
                  {p.user_id === currentUserId && <span className="text-[10px] text-[#9CA3AF]">(you)</span>}
                </div>
                <Badge className={`text-[9px] px-1.5 py-0 ${roleColors[p.role] || ''}`}>{t(p.role)}</Badge>
                {!p.user_id && <Badge className="text-[8px] bg-[#D4A373]/10 text-[#D4A373] px-1 py-0">{t('guest')}</Badge>}
                {p.lobby_status === 'waiting' && <Badge className="text-[8px] bg-[#9CA3AF]/10 text-[#9CA3AF] px-1 py-0">Lobby</Badge>}
              </div>
              <div className="flex items-center gap-1">
                {p.hand_raised && <Hand className="w-3.5 h-3.5 text-[#D4A373]" />}
                {p.mic_on ? <Mic className="w-3.5 h-3.5 text-[#6B8E23]" /> : <MicOff className="w-3.5 h-3.5 text-[#C87967]" />}
                {p.camera_on ? <Video className="w-3.5 h-3.5 text-[#6B8E23]" /> : <VideoOff className="w-3.5 h-3.5 text-[#C87967]" />}
                <span className="w-2 h-2 rounded-full bg-[#6B8E23]" title="Connected" />
                {isHost && p.user_id !== currentUserId && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button className="p-1 rounded hover:bg-[#E8EAE6]" data-testid={`participant-menu-${p.user_id}`}><MoreVertical className="w-3.5 h-3.5 text-[#9CA3AF]" /></button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="min-w-[160px]">
                      <DropdownMenuItem onClick={() => onAction?.(p.user_id, 'mute')} data-testid={`mute-${p.user_id}`}>
                        <MicOff className="w-3.5 h-3.5 mr-2" /> {t('mute')}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onAction?.(p.user_id, 'quick-scan')} data-testid={`quick-scan-${p.user_id}`}>
                        <Stethoscope className="w-3.5 h-3.5 mr-2" /> Schnell-Diagnose senden
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onAction?.(p.user_id, 'co-host')} data-testid={`cohost-${p.user_id}`}>
                        <ShieldCheck className="w-3.5 h-3.5 mr-2" /> {t('makeCoHost')}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onAction?.(p.user_id, 'remove')} className="text-[#C87967]" data-testid={`remove-${p.user_id}`}>
                        <UserMinus className="w-3.5 h-3.5 mr-2" /> {t('removeParticipant')}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
