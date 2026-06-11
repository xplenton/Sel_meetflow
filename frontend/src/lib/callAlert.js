/**
 * Visibility-aware "call ringing" helper.
 *
 * While a call is ringing AND the app tab is NOT currently visible (user
 * is on another tab, on their desktop, or the browser is minimised), we
 * do three things:
 *
 *   1. Flash the document title between "(Anruf) …" and the original
 *      title so the tab in the tab-bar catches the eye.
 *   2. Fire a native `Notification` (OS-level toast) — only if the user
 *      has granted permission. No prompt is ever forced here; the PWA
 *      install flow is the only place that asks.
 *   3. Restore the original title when dismissed.
 *
 * When the tab IS visible the fullscreen `IncomingCallModal` + WebAudio
 * ringtone already give the user plenty of signal, so we don't add
 * redundant notifications.
 */

let flashTimer = null;
let originalTitle = null;
let activeNotif = null;

export function startCallAlert({ callerName, urgent, meetingId }) {
  stopCallAlert(); // idempotent

  // --- Title flash
  originalTitle = document.title;
  const prefix = urgent ? '🚨 DRINGEND — ' : '📞 Anruf — ';
  const flashing = `${prefix}${callerName || 'Unbekannt'}`;
  let toggle = false;
  flashTimer = setInterval(() => {
    document.title = toggle ? originalTitle : flashing;
    toggle = !toggle;
  }, 1000);
  document.title = flashing;

  // --- OS-level notification (fire always for calls — desktop users
  // often have the tab in another monitor / hidden behind another app).
  // Even with the tab "visible" per document.hidden semantics, the user
  // may not actually see it. iter 148.
  if ('Notification' in window && Notification.permission === 'granted') {
    try {
      activeNotif = new Notification(
        urgent ? 'Dringender Anruf' : 'Eingehender Anruf',
        {
          body: `${callerName || 'Unbekannt'} ruft an`,
          tag: `call-${meetingId || 'inbound'}`,
          requireInteraction: true,
          icon: '/favicon.ico',
          silent: false,
        },
      );
      activeNotif.onclick = () => {
        window.focus();
        try { activeNotif.close(); } catch { /* ignore */ }
      };
    } catch { /* Notification constructor blocked — WebAudio ring still fires */ }
  }
}

export function stopCallAlert() {
  if (flashTimer) {
    clearInterval(flashTimer);
    flashTimer = null;
  }
  if (originalTitle !== null) {
    document.title = originalTitle;
    originalTitle = null;
  }
  if (activeNotif) {
    try { activeNotif.close(); } catch { /* ignore */ }
    activeNotif = null;
  }
}

/**
 * Ask for OS-notification permission lazily. Called from IncomingCallModal
 * the first time an incoming-call arrives — most browsers deny if the
 * prompt appears without a prior user gesture, so we silently no-op the
 * first request and the second one (on a subsequent call after the user
 * has interacted with the page) will succeed.
 */
export function ensureNotificationPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    try { Notification.requestPermission(); } catch { /* ignore */ }
  }
}
