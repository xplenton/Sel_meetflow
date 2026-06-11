import { useLanguage } from '../../contexts/LanguageContext';
import { QuickScanRequestCard, QuickScanResultCard } from '../QuickScanOverlay';

const REACTION_EMOJIS = [
  '👍','👏','❤️','😂','🎉','🔥','😮','😢','🤔','💯','👋','🙌',
  '✅','⭐','🚀','😍','👎','💪','🎯','😊','🥳','💡','👀','🤝',
];

/**
 * Floating overlays that sit on top of the main meeting layout:
 *   - Emoji picker for reactions
 *   - Floating reaction emoji animations
 *   - Live subtitle overlay
 *   - Quick-Scan request/result cards
 *
 * Extracted from LiveMeetingPage during the iter 215 refactor.
 */
export default function MeetingOverlays({
  emojiPickerOpen, onCloseEmojiPicker, onPickReaction,
  reactions,
  subtitleText, subtitleSender,
  quickScanRequest, onDismissQuickScanRequest,
  quickScanResult, onDismissQuickScanResult,
}) {
  const { t } = useLanguage();
  return (
    <>
      {/* Quick-Scan overlays — request card for target, result card for host */}
      <QuickScanRequestCard
        request={quickScanRequest}
        onDismiss={onDismissQuickScanRequest}
      />
      <QuickScanResultCard
        result={quickScanResult}
        onDismiss={onDismissQuickScanResult}
      />

      {/* Emoji Picker */}
      {emojiPickerOpen && (
        <div className="fixed inset-0 z-[60]" onClick={onCloseEmojiPicker}>
          <div className="absolute bottom-24 left-1/2 -translate-x-1/2" onClick={e => e.stopPropagation()}>
            <div className="bg-white border border-[#E2E4E0] rounded-xl shadow-lg p-3" data-testid="emoji-picker">
              <p className="text-[10px] text-[#9CA3AF] mb-2 text-center">{t('pickReaction')}</p>
              <div className="grid grid-cols-8 gap-1">
                {REACTION_EMOJIS.map(emoji => (
                  <button key={emoji} onClick={() => { onPickReaction(emoji); onCloseEmojiPicker(); }}
                    className="w-9 h-9 flex items-center justify-center text-xl rounded-lg hover:bg-[#F3F4F1] transition-colors"
                    data-testid={`emoji-${emoji}`}>
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reactions overlay */}
      <div className="fixed bottom-28 left-1/2 -translate-x-1/2 pointer-events-none">
        {reactions.map(r => <span key={r.id} className="reaction-float text-3xl inline-block mx-1">{r.emoji}</span>)}
      </div>

      {/* Subtitle overlay */}
      {subtitleText && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 pointer-events-none z-30 max-w-xl"
          data-testid="subtitle-overlay">
          <div className="bg-black/75 text-white px-5 py-2.5 rounded-lg text-center">
            {subtitleSender && <span className="text-[10px] text-white/50 block mb-0.5">{subtitleSender}</span>}
            <span className="text-sm">{subtitleText}</span>
          </div>
        </div>
      )}
    </>
  );
}
