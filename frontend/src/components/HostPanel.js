import { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Switch } from '../components/ui/switch';
import { ScrollArea } from '../components/ui/scroll-area';
import { Input } from '../components/ui/input';
import { X, MicOff, Mic, MessageSquare, Hand, Monitor, Disc, FileText, UserCheck, UserX, Megaphone, Loader2, Users2, DoorOpen } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import BreakoutPanel from './BreakoutPanel';

export default function HostPanel({ meetingId, meeting, onClose, onMeetingUpdate, onRecordingStart, onRecordingStop, participants, breakoutContext, onVisitBreakout }) {
  const { t } = useLanguage();
  const [lobby, setLobby] = useState([]);
  const [allMuted, setAllMuted] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const [recordingActive, setRecordingActive] = useState(meeting?.recording_active || false);
  const [transcriptActive, setTranscriptActive] = useState(meeting?.transcript_active || false);
  const [consentPending, setConsentPending] = useState({ recording: false, transcript: false });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRecordingActive(meeting?.recording_active || false);
    setTranscriptActive(meeting?.transcript_active || false);
  }, [meeting?.recording_active, meeting?.transcript_active]);

  const fetchLobby = useCallback(async () => {
    try { const { data } = await api.get(`/meetings/${meetingId}/lobby`); setLobby(data); } catch {}
  }, [meetingId]);

  useEffect(() => { fetchLobby(); const i = setInterval(fetchLobby, 5000); return () => clearInterval(i); }, [fetchLobby]);

  const lobbyAction = async (userId, action) => {
    try {
      await api.post(`/meetings/${meetingId}/lobby/${userId}`, { action });
      fetchLobby();
      setTimeout(() => toast.success(action === 'approve' ? 'Genehmigt' : 'Abgelehnt'), 50);
    } catch {}
  };

  const handleMuteToggle = async () => {
    setBusy(true);
    try {
      await api.post(`/meetings/${meetingId}/host-control`, { action: allMuted ? 'unmute_all' : 'mute_all' });
      setAllMuted(!allMuted);
    } catch { setTimeout(() => toast.error('Fehler'), 50); }
    finally { setBusy(false); }
  };

  const handleToggle = async (action) => {
    setBusy(true);
    try {
      await api.post(`/meetings/${meetingId}/host-control`, { action });
      onMeetingUpdate?.();
    } catch { setTimeout(() => toast.error('Fehler'), 50); }
    finally { setBusy(false); }
  };

  const toggleRecording = async () => {
    setBusy(true);
    try {
      if (recordingActive) {
        await api.post(`/meetings/${meetingId}/recording/stop`);
        setRecordingActive(false);
        onRecordingStop?.();
      } else {
        const { data } = await api.post(`/meetings/${meetingId}/recording/request`);
        if (data.immediate) {
          setRecordingActive(true);
          onRecordingStart?.();
          setTimeout(() => toast.success('Aufnahme gestartet'), 50);
        } else {
          setConsentPending(p => ({ ...p, recording: true }));
          setTimeout(() => toast.info(`Zustimmung von ${data.awaiting} Teilnehmer(n) angefragt`), 50);
        }
      }
    } catch { setTimeout(() => toast.error('Fehler'), 50); }
    finally { setBusy(false); }
  };

  const toggleTranscript = async () => {
    setBusy(true);
    try {
      if (transcriptActive) {
        await api.post(`/meetings/${meetingId}/transcript/stop`);
        setTranscriptActive(false);
      } else {
        const { data } = await api.post(`/meetings/${meetingId}/transcript/request`);
        if (data.immediate) {
          setTranscriptActive(true);
          setTimeout(() => toast.success('Transkript gestartet'), 50);
        } else {
          setConsentPending(p => ({ ...p, transcript: true }));
          setTimeout(() => toast.info(`Zustimmung von ${data.awaiting} Teilnehmer(n) angefragt`), 50);
        }
      }
    } catch { setTimeout(() => toast.error('Fehler'), 50); }
    finally { setBusy(false); }
  };

  const sendAnnouncement = async () => {
    if (!announcement.trim()) return;
    try {
      await api.post(`/meetings/${meetingId}/chat/announcement`, { message: announcement });
      setAnnouncement('');
      setTimeout(() => toast.success('Ankuendigung gesendet'), 50);
    } catch {}
  };

  return (
    <div className="w-full sm:w-80 fixed inset-0 sm:static sm:inset-auto bg-white border-l border-[#E2E4E0] flex flex-col h-full z-40 sm:z-auto" data-testid="host-panel">
      <div className="flex items-center justify-between p-4 border-b border-[#E2E4E0]">
        <h3 className="text-sm font-medium text-[#1C1F1D]">Host-Steuerung</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF]" data-testid="close-host-panel"><X className="w-4 h-4" /></button>
      </div>
      <ScrollArea className="flex-1 p-3 space-y-4">
        {/* Lobby */}
        {lobby.length > 0 && (
          <div className="mb-4">
            <h4 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider mb-2">Lobby ({lobby.length})</h4>
            <div className="space-y-2">
              {lobby.map(p => (
                <div key={p.user_id} className="flex items-center gap-2 p-2 bg-[#F3F4F1] rounded-lg" data-testid={`lobby-${p.user_id}`}>
                  <div className="w-7 h-7 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs font-medium text-[#4A5D4E]">
                    {p.name?.[0]?.toUpperCase()}
                  </div>
                  <span className="text-xs flex-1 truncate">{p.name}</span>
                  <button onClick={() => lobbyAction(p.user_id, 'approve')} className="p-1 rounded bg-[#6B8E23]/10 text-[#6B8E23] hover:bg-[#6B8E23]/20" data-testid={`approve-${p.user_id}`}><UserCheck className="w-3.5 h-3.5" /></button>
                  <button onClick={() => lobbyAction(p.user_id, 'reject')} className="p-1 rounded bg-[#C87967]/10 text-[#C87967] hover:bg-[#C87967]/20" data-testid={`reject-${p.user_id}`}><UserX className="w-3.5 h-3.5" /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Mute / Unmute All */}
        <div className="space-y-3">
          <h4 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider">Steuerung</h4>
          <Button onClick={handleMuteToggle} disabled={busy} size="sm" variant="outline"
            className={`w-full justify-start rounded-lg text-xs ${allMuted ? 'border-[#6B8E23] text-[#6B8E23] hover:bg-[#6B8E23]/10' : 'border-[#E2E4E0] text-[#C87967] hover:bg-[#C87967]/10'}`}
            data-testid="mute-all-button">
            {allMuted ? <><Mic className="w-3.5 h-3.5 mr-2" /> Alle Stummschaltung aufheben</> : <><MicOff className="w-3.5 h-3.5 mr-2" /> Alle stummschalten</>}
          </Button>

          {/* Toggle Controls */}
          <div className="space-y-2">
            {[
              ['toggle_chat', 'Chat', MessageSquare, meeting?.chat_enabled],
              ['toggle_reactions', 'Reaktionen', Hand, meeting?.reactions_enabled],
              ['toggle_screen_share', 'Bildschirm teilen', Monitor, meeting?.screen_share_enabled !== false],
              ['toggle_lobby', 'Warteraum', DoorOpen, meeting?.lobby_enabled],
            ].map(([action, label, Icon, enabled]) => (
              <div key={action} className="flex items-center justify-between py-1">
                <span className="text-xs text-[#4B5563] flex items-center gap-1.5"><Icon className="w-3.5 h-3.5" />{label}</span>
                <Switch checked={enabled !== false} onCheckedChange={() => handleToggle(action)} disabled={busy} data-testid={`host-${action}`} />
              </div>
            ))}
          </div>
        </div>

        {/* Recording & Transcript */}
        <div className="space-y-3 pt-3 border-t border-[#E2E4E0]">
          <h4 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider">Aufnahme & Transkript</h4>
          <div className="flex items-center justify-between">
            <span className="text-xs flex items-center gap-1.5">
              <Disc className={`w-3.5 h-3.5 ${recordingActive ? 'text-[#E25C5C] pulse-live' : 'text-[#9CA3AF]'}`} />
              Aufnahme
            </span>
            <div className="flex items-center gap-1.5">
              {consentPending.recording && <span className="text-[9px] text-[#D4A373] animate-pulse">Warten...</span>}
              <Switch checked={recordingActive} onCheckedChange={toggleRecording} disabled={busy} data-testid="toggle-recording" />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs flex items-center gap-1.5">
              <FileText className={`w-3.5 h-3.5 ${transcriptActive ? 'text-[#6B8E23]' : 'text-[#9CA3AF]'}`} />
              Transkript
            </span>
            <div className="flex items-center gap-1.5">
              {consentPending.transcript && <span className="text-[9px] text-[#D4A373] animate-pulse">Warten...</span>}
              <Switch checked={transcriptActive} onCheckedChange={toggleTranscript} disabled={busy} data-testid="toggle-transcript" />
            </div>
          </div>
        </div>

        {/* Announcement */}
        <div className="space-y-2 pt-3 border-t border-[#E2E4E0]">
          <h4 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1"><Megaphone className="w-3.5 h-3.5" />Ankuendigung</h4>
          <div className="flex gap-1">
            <Input value={announcement} onChange={e => setAnnouncement(e.target.value)} placeholder={t('messageToAll')} className="border-[#E2E4E0] rounded-lg text-xs h-8 flex-1" data-testid="announcement-input" />
            <Button onClick={sendAnnouncement} size="sm" className="bg-[#4A5D4E] text-white rounded-lg h-8 px-3 text-xs" data-testid="send-announcement"><Megaphone className="w-3.5 h-3.5" /></Button>
          </div>
        </div>

        {/* Breakout Rooms */}
        <div className="space-y-2 pt-3 border-t border-[#E2E4E0]">
          <h4 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1">
            <Users2 className="w-3.5 h-3.5" />Breakout Rooms
          </h4>
          <BreakoutPanel meetingId={meetingId} participants={participants || []} onClose={() => {}}
            breakoutContext={breakoutContext} onVisitBreakout={onVisitBreakout} />
        </div>
      </ScrollArea>
    </div>
  );
}
