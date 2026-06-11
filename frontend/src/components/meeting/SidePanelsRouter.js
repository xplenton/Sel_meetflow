import { toast } from 'sonner';
import ChatPanel from '../ChatPanel';
import ParticipantPanel from '../ParticipantPanel';
import MeetingExtrasPanel from '../MeetingExtrasPanel';
import FileSharePanel from '../FileSharePanel';
import DocumentPanel from '../DocumentPanel';
import HostPanel from '../HostPanel';
import api from '../../lib/api';

/**
 * SidePanelsRouter — renders the chat / participants / extras / files /
 * documents / host side panels both for desktop (inline next to the video
 * grid) and mobile (full-screen overlay). Extracted from LiveMeetingPage
 * during the iter 215 refactor to flatten the JSX in the page component.
 *
 * All state for which panel is open and the WS/recording handlers continue
 * to live in the parent — this component just routes them to the right
 * panel and renders both flavors.
 */
export default function SidePanelsRouter({
  meeting, meetingId,
  user, isHost,
  participants,
  chatOpen, onCloseChat, chatMessages, onSendChat,
  participantsOpen, onCloseParticipants, onParticipantAction,
  extrasOpen, onCloseExtras,
  filesOpen, onCloseFiles,
  docsOpen, onCloseDocs, presentedDoc, onPresentDoc, wsRef,
  hostPanelOpen, onCloseHostPanel, onMeetingRefreshed,
  onRecordingStart, onRecordingStop,
  breakoutContext, onVisitBreakout,
}) {
  const activeParticipants = participants.filter(p => p.joined_at && !p.left_at);

  const refreshMeeting = async () => {
    try {
      const { data } = await api.get(`/meetings/${meetingId}`);
      onMeetingRefreshed?.(data);
    } catch {}
  };

  const handleVisitBreakout = (room) => {
    if (!room) {
      onVisitBreakout?.(null);
      toast.info('Zurück zum Hauptraum');
    } else {
      onVisitBreakout?.({ room_id: room.room_id, room_name: room.name });
      toast.info(`Besuche Gruppenraum "${room.name}" …`);
    }
  };

  const chat = chatOpen && (
    <ChatPanel messages={chatMessages} onSend={onSendChat} onClose={onCloseChat} userName={user?.name} />
  );
  const participantsPanel = participantsOpen && (
    <ParticipantPanel participants={activeParticipants} onClose={onCloseParticipants}
      currentUserId={user?.user_id} isHost={isHost} onAction={onParticipantAction} />
  );
  const extras = extrasOpen && (
    <MeetingExtrasPanel meetingId={meetingId} userId={user?.user_id} isHost={isHost}
      participants={activeParticipants} onClose={onCloseExtras} />
  );
  const files = filesOpen && (
    <FileSharePanel meetingId={meetingId} onClose={onCloseFiles} />
  );
  const docs = docsOpen && (
    <DocumentPanel meetingId={meetingId} isHost={isHost} userId={user?.user_id}
      userName={user?.name} onClose={onCloseDocs}
      presentedDoc={presentedDoc} onPresentDoc={onPresentDoc} wsRef={wsRef}
      participants={participants} />
  );
  const host = hostPanelOpen && isHost && (
    <HostPanel meetingId={meetingId} meeting={meeting} onClose={onCloseHostPanel}
      onMeetingUpdate={refreshMeeting}
      onRecordingStart={onRecordingStart} onRecordingStop={onRecordingStop}
      participants={participants}
      breakoutContext={breakoutContext}
      onVisitBreakout={handleVisitBreakout}
    />
  );

  return (
    <>
      {/* Desktop side panels: inline next to the video grid */}
      <div className="hidden sm:contents">
        {chat}
        {participantsPanel}
        {extras}
        {files}
        {docs}
        {host}
      </div>

      {/* Mobile overlay panels: full-screen overlay */}
      <div className="sm:hidden">
        {chat && <div className="fixed inset-0 z-40">{chat}</div>}
        {participantsPanel && <div className="fixed inset-0 z-40">{participantsPanel}</div>}
        {extras && <div className="fixed inset-0 z-40">{extras}</div>}
        {files && <div className="fixed inset-0 z-40">{files}</div>}
        {docs && <div className="fixed inset-0 z-40">{docs}</div>}
        {host && <div className="fixed inset-0 z-40">{host}</div>}
      </div>
    </>
  );
}
