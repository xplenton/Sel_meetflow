import { useRef, useCallback } from 'react';

/**
 * useChatSounds — bundles the two Web-Audio-API based notification sounds
 * used by the chat (incoming message ping + incoming call ringtone).
 *
 * Extracted from ChatPage during the iter 219 refactor — the sound logic
 * shared no other concerns with the chat state, so isolating it removes
 * ~50 lines of unrelated noise from the page component.
 *
 * Returns:
 *   - playNotificationSound() — short 2-tone ping for new messages
 *   - playCallSound() — 3-pulse ringtone for inbound calls
 *
 * Both are no-ops on browsers without AudioContext support; they reuse a
 * single lazily-created context to avoid the "100 contexts" Safari warning.
 */
export default function useChatSounds() {
  const audioCtxRef = useRef(null);

  const ensureCtx = useCallback(() => {
    if (!audioCtxRef.current) {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return null;
      audioCtxRef.current = new Ctor();
    }
    const ctx = audioCtxRef.current;
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }, []);

  const playNotificationSound = useCallback(() => {
    try {
      const ctx = ensureCtx();
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(1047, ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.25);
    } catch {}
  }, [ensureCtx]);

  const playCallSound = useCallback(() => {
    try {
      const ctx = ensureCtx();
      if (!ctx) return;
      for (let i = 0; i < 3; i++) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        const t = ctx.currentTime + i * 0.3;
        osc.frequency.setValueAtTime(1200, t);
        osc.frequency.setValueAtTime(900, t + 0.1);
        gain.gain.setValueAtTime(0.2, t);
        gain.gain.exponentialRampToValueAtTime(0.01, t + 0.2);
        osc.start(t);
        osc.stop(t + 0.2);
      }
    } catch {}
  }, [ensureCtx]);

  return { playNotificationSound, playCallSound };
}
