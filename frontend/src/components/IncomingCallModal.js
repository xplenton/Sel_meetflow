import { useEffect, useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Phone, PhoneOff, Video, Users } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { createChatWebSocket } from '../lib/chatWebSocket';
import { resolveLiveRoute } from '../lib/liveRoute';
import { startCallAlert, stopCallAlert, ensureNotificationPermission } from '../lib/callAlert';

/**
 * Global, full-screen "incoming call" ringing UI.
 *
 * Listens on a dedicated chat WebSocket for `incoming-call` events (sent
 * by the backend whenever someone starts a chat-call or an instant
 * meeting where the current user is invited). When an event arrives it
 * displays a WhatsApp-style full-screen overlay with caller avatar,
 * animated ring pulses, a synthesised ringtone (WebAudio, no asset
 * dependency), and two big buttons: Annehmen / Ablehnen.
 *
 * Iter 115 refactor:
 *   - **No more whole-overlay `animate-pulse`** (previously caused a
 *     "flickering" perception especially on urgent red gradient). The
 *     pulse is now scoped to an inner red border ring + the DRINGEND
 *     label, which reads as "urgent" without strobing the whole screen.
 *   - **Visibility-aware alerting**: when the tab is hidden we also
 *     flash the document title and fire an OS-level Notification so the
 *     user on a different tab / desktop sees the call come in.
 */
const AUTO_DISMISS_MS = 45000;

/** Schedule a 2-tone ring chirp on the supplied AudioContext at time `t`. */
function scheduleRing(ctx, t) {
  for (let i = 0; i < 2; i++) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(1200, t + i * 0.18);
    osc.frequency.setValueAtTime(900, t + i * 0.18 + 0.09);
    gain.gain.setValueAtTime(0.22, t + i * 0.18);
    gain.gain.exponentialRampToValueAtTime(0.01, t + i * 0.18 + 0.18);
    osc.start(t + i * 0.18);
    osc.stop(t + i * 0.18 + 0.2);
  }
}

export default function IncomingCallModal() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [call, setCall] = useState(null);
  const audioCtxRef = useRef(null);
  const ringIntervalRef = useRef(null);
  const wsRef = useRef(null);
  const timerRef = useRef(null);

  const stopRing = useCallback(() => {
    if (ringIntervalRef.current) {
      clearInterval(ringIntervalRef.current);
      ringIntervalRef.current = null;
    }
    try { navigator.vibrate && navigator.vibrate(0); } catch { /* ignore */ }
  }, []);

  const startRing = useCallback(async (urgent = false) => {
    // Haptic feedback on Android/mobile browsers that expose the Vibration
    // API — an urgent call gets an SOS-like pattern that repeats, a normal
    // call gets a single gentle buzz so the user feels their phone ring
    // even in silent-mode. iPhone Safari doesn't support Vibration API so
    // this is a best-effort no-op there (iter 121).
    try {
      if (navigator.vibrate) {
        if (urgent) {
          // SOS morse: short-short-short long long long short-short-short
          navigator.vibrate([200, 100, 200, 100, 200, 400, 600, 100, 600, 100, 600, 400, 200, 100, 200, 100, 200]);
        } else {
          navigator.vibrate([400, 200, 400]);
        }
      }
    } catch { /* best-effort */ }
    try {
      if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
        audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }
      const ctx = audioCtxRef.current;
      // iter 157 — AWAIT resume(). Without this the 2nd+ call arrives while
      // the AudioContext is still suspended and the oscillator plays silently
      // (identical bug to iter 150's notificationSound.js). iOS/Android
      // background their AudioContexts aggressively.
      if (ctx.state === 'suspended') {
        try { await ctx.resume(); } catch { /* ignore */ }
      }
      if (ctx.state !== 'running') return;
      // Urgent: louder, faster cadence, with a siren sweep
      const fire = () => {
        scheduleRing(ctx, ctx.currentTime);
        if (urgent) {
          const osc = ctx.createOscillator();
          const g = ctx.createGain();
          osc.connect(g); g.connect(ctx.destination);
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(400, ctx.currentTime);
          osc.frequency.exponentialRampToValueAtTime(1600, ctx.currentTime + 0.25);
          osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.5);
          g.gain.setValueAtTime(0.35, ctx.currentTime);
          g.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
          osc.start(); osc.stop(ctx.currentTime + 0.52);
        }
      };
      fire();
      ringIntervalRef.current = setInterval(fire, urgent ? 1000 : 1600);
    } catch { /* audio blocked — modal still renders silently */ }
  }, []);

  const dismiss = useCallback(() => {
    stopRing();
    stopCallAlert();
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    setCall(null);
  }, [stopRing]);

  const accept = useCallback(async () => {
    if (!call) return;
    const mid = call.meeting_id;
    dismiss();
    // Callee has explicitly tapped "Annehmen" — skip the PreJoin screen
    // and drop them straight into the live meeting so a single tap is
    // enough to take the call (iter 122). Route to LiveKit SFU if the
    // group is ≥ threshold, else the mesh page (iter 138).
    const route = await resolveLiveRoute(mid);
    navigate(route);
  }, [call, dismiss, navigate]);

  // Ask for OS-notification permission once, after mount + user settled
  useEffect(() => {
    if (user?.user_id) ensureNotificationPermission();
  }, [user?.user_id]);

  // Global WS listener — resilient against idle-proxy drops and tab
  // backgrounding via the shared `createChatWebSocket` helper (keep-alive
  // pings + auto-reconnect). Without this, an idle callee would silently
  // miss incoming-call events after ~60 s.
  //
  // Iter 375 — handle both inbound paths:
  //   1. Dedicated WS connection (this hook)
  //   2. Window event `meetflow:call-event` re-dispatched by StatusContext
  // so the modal always fires even when one of the two channels is
  // temporarily disconnected (eg. while the dedicated WS is mid-reconnect).
  useEffect(() => {
    if (!user?.user_id) return;
    const handleCallData = (data) => {
      if (data.type === 'incoming-call') {
        if (data.caller_id === user.user_id) return;
        // eslint-disable-next-line no-console
        console.debug('[IncomingCallModal] incoming-call received', { meeting_id: data.meeting_id, caller: data.caller_name });
        setCall(data);
      } else if (data.type === 'call-ended' || data.type === 'call-cancelled') {
        // iter 153 — backend sends `call-cancelled` when the caller hangs
        // up before the callee picks up (last-participant-leaves auto-end).
        // We also still accept the legacy `call-ended` event name.
        setCall(prev => (prev && (prev.meeting_id === data.meeting_id || prev.message_id === data.message_id)) ? null : prev);
      }
    };
    const backendUrl = process.env.REACT_APP_BACKEND_URL;
    let handle = null;
    if (backendUrl) {
      const wsUrl = backendUrl.replace(/^http/, 'ws') + `/api/ws/chat/${user.user_id}`;
      handle = createChatWebSocket(wsUrl, handleCallData);
      wsRef.current = handle;
    }
    const onWindowEvent = (e) => {
      if (e && e.detail) handleCallData(e.detail);
    };
    window.addEventListener('meetflow:call-event', onWindowEvent);
    return () => {
      try { handle && handle.close(); } catch { /* ignore */ }
      wsRef.current = null;
      window.removeEventListener('meetflow:call-event', onWindowEvent);
    };
  }, [user]);

  // Start/stop ringtone + title-flash + OS-notification + auto-dismiss
  useEffect(() => {
    if (!call) { stopRing(); stopCallAlert(); return; }
    // Force the app to pop into foreground on desktop browsers so the
    // fullscreen modal is actually visible when the call arrives. On iOS
    // PWAs window.focus() is a no-op (by design) — the Web Push with
    // requireInteraction + the inner ringtone covers that case.
    try { window.focus(); } catch { /* ignore */ }
    // On desktop: exit any active document Picture-in-Picture so the
    // IncomingCallModal overlay isn't hidden behind a floating window.
    if (document.pictureInPictureElement) {
      try { document.exitPictureInPicture(); } catch { /* ignore */ }
    }
    // Also fire an OS notification on desktop regardless of tab visibility
    // — the default `startCallAlert` only fires it when the tab is hidden,
    // but users reported calls arriving silently when the tab was in a
    // different monitor / minimized (iter 148).
    startRing(!!call.urgent);
    startCallAlert({
      callerName: call.caller_name,
      urgent: !!call.urgent,
      meetingId: call.meeting_id,
    });
    timerRef.current = setTimeout(() => dismiss(), AUTO_DISMISS_MS);
    return () => {
      stopRing();
      stopCallAlert();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [call, startRing, stopRing, dismiss]);

  if (!call) return null;

  const isGroup = call.conversation_type === 'group' || call.conversation_type === 'meeting';
  const isUrgent = !!call.urgent;
  const subtitle = isUrgent
    ? 'DRINGEND'
    : (isGroup ? (call.conversation_name || 'Gruppenanruf') : 'Eingehender Anruf');

  const initial = (call.caller_name || '?').trim().charAt(0).toUpperCase();

  // Iter 375 — render to <body> via Portal so the modal escapes any
  // stacking context created by ancestor providers/routers. Combined with
  // a higher z-index (z-[200]) this guarantees the ringing UI sits on top
  // of every other floating element (toasts, banners, lightboxes, ...).
  const overlay = (
    <div
      className={`fixed inset-0 z-[200] flex flex-col items-center justify-between py-14 px-6 ${
        isUrgent
          ? 'bg-gradient-to-b from-[#7A2620] via-[#C87967] to-[#7A2620]'
          : 'bg-gradient-to-b from-[#1C1F1D] via-[#2A3430] to-[#1C1F1D]'
      }`}
      style={{ animation: 'incoming-call-fade-in 180ms ease-out both' }}
      data-testid="incoming-call-modal"
      data-urgent={isUrgent ? 'true' : 'false'}
    >
      {/* Urgent: inner red border ring — pulses WITHOUT strobing the whole
          screen (which is what made the previous version look like flicker) */}
      {isUrgent && (
        <div
          aria-hidden
          className="absolute inset-2 rounded-lg border-4 border-[#FFD1C2]/60"
          style={{ animation: 'incoming-call-urgent-ring 1.4s ease-in-out infinite' }}
        />
      )}

      {/* Top label */}
      <div
        className={`relative text-sm uppercase tracking-[0.25em] font-bold ${
          isUrgent ? 'text-white' : 'text-white/70'
        }`}
        data-testid="incoming-call-subtitle"
        style={isUrgent ? { animation: 'incoming-call-label-blink 1.4s ease-in-out infinite' } : undefined}
      >
        {subtitle}
      </div>

      {/* Avatar + name (centered) */}
      <div className="relative flex-1 flex flex-col items-center justify-center">
        <div className="relative mb-8">
          <div className="absolute inset-0 rounded-full bg-[#4A5D4E]/30 animate-ping" style={{ animationDuration: '1.6s' }} />
          <div className="absolute inset-0 rounded-full bg-[#4A5D4E]/20 animate-ping" style={{ animationDuration: '1.6s', animationDelay: '0.8s' }} />
          <div className="relative w-36 h-36 rounded-full bg-gradient-to-br from-[#4A5D4E] to-[#3E4E42] flex items-center justify-center overflow-hidden border-4 border-white/10 shadow-2xl">
            {call.caller_avatar ? (
              <img src={call.caller_avatar} alt="" className="w-full h-full object-cover" />
            ) : (
              <span className="text-white text-5xl font-medium" style={{ fontFamily: 'Manrope' }}>{initial}</span>
            )}
          </div>
        </div>

        <h2 className="text-white text-3xl font-medium mb-1 text-center" style={{ fontFamily: 'Manrope' }} data-testid="incoming-call-name">
          {call.caller_name || 'Unbekannter Anrufer'}
        </h2>
        <p className="text-white/60 text-sm text-center flex items-center gap-1.5 justify-center">
          {isGroup ? <Users className="w-3.5 h-3.5" /> : <Video className="w-3.5 h-3.5" />}
          {isGroup
            ? `In ${call.conversation_name || 'einer Gruppe'}`
            : 'Videoanruf'}
        </p>
      </div>

      {/* Bottom action buttons */}
      <div className="relative flex items-center justify-center gap-16 w-full max-w-md">
        <div className="flex flex-col items-center gap-2">
          <button
            onClick={dismiss}
            aria-label="Ablehnen"
            data-testid="incoming-call-decline"
            className="w-16 h-16 rounded-full bg-[#C87967] hover:bg-[#B5624F] text-white flex items-center justify-center shadow-2xl transition-transform active:scale-90"
          >
            <PhoneOff className="w-7 h-7" />
          </button>
          <span className="text-white/70 text-xs font-medium">Ablehnen</span>
        </div>
        <div className="flex flex-col items-center gap-2">
          <button
            onClick={accept}
            aria-label="Annehmen"
            data-testid="incoming-call-accept"
            className="w-16 h-16 rounded-full bg-[#6B8E23] hover:bg-[#5a7a1f] text-white flex items-center justify-center shadow-2xl transition-transform active:scale-90"
            style={{ animation: 'incoming-call-accept-pulse 1.6s ease-in-out infinite' }}
          >
            <Phone className="w-7 h-7" />
          </button>
          <span className="text-white/70 text-xs font-medium">Annehmen</span>
        </div>
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
}
