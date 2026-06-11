import { Badge } from '../ui/badge';
import { Video as VideoIcon, Disc, Clock, AlertTriangle, Users2, LogOut } from 'lucide-react';
import { toast } from 'sonner';
import { useLanguage } from '../../contexts/LanguageContext';

/**
 * Renders the banners (media error, breakout) and the meeting top bar with
 * title, recording badge, mode badge, timer and participant count.
 *
 * Extracted from LiveMeetingPage during the iter 215 refactor — pure
 * presentational. All decisions still live in the parent.
 */
export default function MeetingTopBar({
  meeting, modeConfig, isRecording, isHost,
  elapsed, participantsCount,
  mediaError, onRetryMedia,
  breakoutContext, onLeaveBreakout,
  formatTime,
}) {
  const { t } = useLanguage();
  return (
    <>
      {/* Media Permission Error Banner (shown on iOS failure with retry) */}
      {mediaError && (
        <div className="bg-[#C87967] text-white px-3 sm:px-4 py-2 flex items-center gap-2 text-[11px] sm:text-xs" data-testid="media-error-banner">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1 truncate"><strong>{mediaError.title}:</strong> {mediaError.message}</span>
          {mediaError.code === 'NotAllowed' ? (
            <button onClick={() => window.location.reload()} className="bg-white/20 hover:bg-white/30 rounded-full px-2 py-0.5 text-[10px] flex-shrink-0" data-testid="reload-media-btn">
              Seite neu laden
            </button>
          ) : (
            <button onClick={onRetryMedia} className="bg-white/20 hover:bg-white/30 rounded-full px-2 py-0.5 text-[10px] flex-shrink-0" data-testid="retry-media-btn">
              Erneut versuchen
            </button>
          )}
        </div>
      )}

      {/* Breakout-Room-Banner: shows current sub-room + allows return to main room. */}
      {breakoutContext && (
        <div className="bg-[#4A5D4E] text-white px-3 sm:px-4 py-2 flex items-center gap-2 text-[11px] sm:text-xs" data-testid="breakout-banner">
          <Users2 className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1 truncate">
            Du bist im Gruppenraum <strong>"{breakoutContext.room_name}"</strong>
          </span>
          {isHost && (
            <button
              onClick={() => { onLeaveBreakout(); toast.info('Zurück zum Hauptraum'); }}
              className="bg-white/20 hover:bg-white/30 rounded-full px-2.5 py-1 text-[10px] flex-shrink-0 flex items-center gap-1"
              data-testid="leave-breakout-btn">
              <LogOut className="w-3 h-3" />Hauptraum
            </button>
          )}
        </div>
      )}

      {/* Top bar */}
      <div className="h-12 sm:h-14 bg-[#1A1D1B] border-b border-white/10 flex items-center justify-between px-2 sm:px-4 flex-shrink-0">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <VideoIcon className="w-4 h-4 sm:w-5 sm:h-5 text-white/60 flex-shrink-0" />
          <span className="text-white text-xs sm:text-sm font-medium truncate max-w-[120px] sm:max-w-none" data-testid="meeting-title">{meeting?.title || 'Meeting'}</span>
          {meeting?.recording_enabled && <Badge className="bg-[#E25C5C]/20 text-[#E25C5C] text-[10px]"><Disc className="w-3 h-3 mr-1 pulse-live" />REC</Badge>}
          {isRecording && <Badge className="bg-[#E25C5C] text-white text-[10px] animate-pulse" data-testid="recording-active-badge"><Disc className="w-3 h-3 mr-1" />{t('recordingActive')}</Badge>}
          {modeConfig && modeConfig.mode !== 'standard' && (
            <Badge className="bg-white/10 text-white/70 text-[10px] capitalize" data-testid="meeting-mode-badge">{modeConfig.mode}</Badge>
          )}
          {modeConfig?.config?.auto_mute && !isHost && (
            <Badge className="bg-[#D4A373]/20 text-[#D4A373] text-[10px]" data-testid="auto-muted-badge">{t('autoMuted')}</Badge>
          )}
        </div>
        <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
          <span className="text-white/50 text-[10px] sm:text-xs flex items-center gap-1" data-testid="meeting-timer"><Clock className="w-3 h-3 sm:w-3.5 sm:h-3.5" />{formatTime(elapsed)}</span>
          <span className="text-white/30 text-[10px] sm:text-xs hidden sm:inline">{participantsCount} {t('participants').toLowerCase()}</span>
        </div>
      </div>
    </>
  );
}
