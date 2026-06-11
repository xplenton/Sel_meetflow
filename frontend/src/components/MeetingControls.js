import { createPortal } from 'react-dom';
import { useLanguage } from '../contexts/LanguageContext';
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '../components/ui/tooltip';
import { Mic, MicOff, Video, VideoOff, Monitor, Hand, MessageSquare, Users, PhoneOff, Smile, LayoutGrid, Paperclip, ImageIcon, ShieldCheck, MonitorUp, FileSignature, PenLine, Captions, Settings, UserPlus } from 'lucide-react';

export default function MeetingControls({ micOn, cameraOn, onToggleMic, onToggleCamera, onShareScreen, onToggleChat,
  onToggleParticipants, onRaiseHand, onLeave, handRaised, chatOpen, participantsOpen, onReaction,
  onToggleExtras, extrasOpen, onToggleFiles, filesOpen, onToggleBg, bgPanelOpen,
  isHost, onToggleHostPanel, hostPanelOpen, isScreenSharing,
  onToggleDocs, docsOpen, onToggleWhiteboard, whiteboardOpen,
  onToggleSubtitles, subtitlesOn, onToggleDeviceSettings, deviceSettingsOpen,
  onToggleInvite }) {
  const { t } = useLanguage();

  // iter 158 — Radix Tooltip's asChild wrapper can swallow touch events on
  // mobile (user reported "Mikrofon ausschalten funktioniert nicht auf Handy").
  // We now:
  //   1. Also wire `onTouchEnd` → fires onClick regardless of Tooltip focus
  //   2. preventDefault on touchend so the synthetic click doesn't double-fire
  const ControlBtn = ({ icon: Icon, label, active, danger, onClick, testId, badge }) => {
    const handleTouchEnd = (e) => {
      e.preventDefault();
      try { onClick?.(); } catch { /* noop */ }
    };
    return (
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onClick}
              onTouchEnd={handleTouchEnd}
              data-testid={testId}
              className={`relative p-3 rounded-full flex items-center justify-center transition-all
                ${danger ? 'bg-[#C87967] text-white hover:bg-[#B56555]' :
                active === false ? 'bg-[#C87967] text-white' :
                active === true ? 'bg-[#4A5D4E] text-white' :
                'bg-[#E8EAE6] text-[#1F2937] hover:bg-[#DCE0D9]'}`}>
              <Icon className="w-5 h-5" />
              {badge && <span className="absolute -top-1 -right-1 w-4 h-4 bg-[#E25C5C] text-white text-[9px] rounded-full flex items-center justify-center">{badge}</span>}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs">{label}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  // Mobile-only leave button — rendered via a portal so it escapes the
  // `.control-bar` wrapper which uses `transform: translateX(-50%)`. A
  // transformed ancestor creates a new containing block for every fixed
  // descendant, which was anchoring the button near the bottom of the
  // screen instead of the viewport top-right (iter 115 regression).
  const mobileLeaveBtn = typeof document !== 'undefined' ? createPortal(
    <button
      onClick={onLeave}
      data-testid="mobile-leave-meeting-button"
      aria-label={t('leave') || 'Beenden'}
      className="sm:hidden fixed z-[100] flex flex-col items-center gap-1 group"
      style={{
        top: 'calc(env(safe-area-inset-top, 0px) + 12px)',
        right: 'calc(env(safe-area-inset-right, 0px) + 12px)',
      }}
    >
      <span className="w-14 h-14 rounded-full bg-[#D93A3A] group-active:bg-[#B02A2A] text-white shadow-[0_4px_16px_rgba(0,0,0,0.45)] flex items-center justify-center transition-transform group-active:scale-95 ring-2 ring-white/40">
        <PhoneOff className="w-7 h-7" />
      </span>
      <span className="text-[10px] font-bold uppercase tracking-wider text-white [text-shadow:_0_1px_3px_rgba(0,0,0,0.8)]">
        {t('leave') || 'Beenden'}
      </span>
    </button>,
    document.body,
  ) : null;

  return (
    <>
      {mobileLeaveBtn}
      <div className="control-bar" data-testid="meeting-controls">
      <ControlBtn icon={micOn ? Mic : MicOff} label={micOn ? t('mute') : t('unmute')} active={micOn} onClick={onToggleMic} testId="toggle-mic-button" />
      <ControlBtn icon={cameraOn ? Video : VideoOff} label={t('camera')} active={cameraOn} onClick={onToggleCamera} testId="toggle-camera-button" />
      <ControlBtn icon={Settings} label="Geräte" active={deviceSettingsOpen || undefined} onClick={onToggleDeviceSettings} testId="toggle-device-settings" />
      <ControlBtn icon={isScreenSharing ? MonitorUp : Monitor} label={t('shareScreen')} active={isScreenSharing || undefined} onClick={onShareScreen} testId="share-screen-button" />
      <div className="w-px h-6 bg-[#E2E4E0]" />
      <ControlBtn icon={Hand} label={t('raiseHand')} active={handRaised || undefined} onClick={onRaiseHand} testId="raise-hand-button" />
      <ControlBtn icon={UserPlus} label="Einladen" onClick={onToggleInvite} testId="toggle-invite-button" />
      <ControlBtn icon={Smile} label={t('reactions')} onClick={onReaction} testId="reactions-button" />
      <ControlBtn icon={MessageSquare} label={t('chat')} active={chatOpen || undefined} onClick={onToggleChat} testId="toggle-chat-button" />
      <ControlBtn icon={Users} label={t('participants')} active={participantsOpen || undefined} onClick={onToggleParticipants} testId="toggle-participants-button" />
      <ControlBtn icon={LayoutGrid} label="Tools" active={extrasOpen || undefined} onClick={onToggleExtras} testId="toggle-extras-button" />
      <ControlBtn icon={Paperclip} label="Files" active={filesOpen || undefined} onClick={onToggleFiles} testId="toggle-files-button" />
      <ControlBtn icon={FileSignature} label="Dokumente" active={docsOpen || undefined} onClick={onToggleDocs} testId="toggle-docs-button" />
      <ControlBtn icon={PenLine} label="Whiteboard" active={whiteboardOpen || undefined} onClick={onToggleWhiteboard} testId="toggle-whiteboard-button" />
      <ControlBtn icon={Captions} label="Untertitel" active={subtitlesOn || undefined} onClick={onToggleSubtitles} testId="toggle-subtitles-button" />
      <ControlBtn icon={ImageIcon} label="Background" active={bgPanelOpen || undefined} onClick={onToggleBg} testId="toggle-bg-button" />
      {isHost && <ControlBtn icon={ShieldCheck} label="Host" active={hostPanelOpen || undefined} onClick={onToggleHostPanel} testId="toggle-host-panel" />}
      <div className="w-px h-6 bg-[#E2E4E0]" />
      <ControlBtn icon={PhoneOff} label={t('leave')} danger onClick={onLeave} testId="leave-meeting-button" />
    </div>
    </>
  );
}
