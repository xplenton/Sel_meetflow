/**
 * Browser-native notification helper (iter 309 / Thema 2b).
 *
 * Wraps `Notification` so the chat unread-context can fire a system-level
 * popup when a new message arrives while the tab is in the background.
 * On the FOREGROUND tab we keep using the sonner toast (much nicer UX
 * and avoids double-pinging the user).
 *
 * Permission flow:
 *   • `notificationPermission()` is a one-liner read.
 *   • `requestNotificationPermission()` must be called from inside a real
 *     user gesture. The chat sound toggle pipes through here on its first
 *     "enable"-click so users get a single, predictable consent prompt.
 *   • If permission was previously DENIED, we never re-prompt (browsers
 *     would silently ignore us anyway).
 */

export function isNotificationsSupported() {
  return typeof window !== 'undefined' && 'Notification' in window;
}

export function notificationPermission() {
  if (!isNotificationsSupported()) return 'unsupported';
  return Notification.permission; // "granted" | "denied" | "default"
}

export async function requestNotificationPermission() {
  if (!isNotificationsSupported()) return 'unsupported';
  if (Notification.permission !== 'default') return Notification.permission;
  try {
    const res = await Notification.requestPermission();
    return res;
  } catch {
    return Notification.permission;
  }
}

/**
 * Show a system notification IF the tab is hidden and permission was granted.
 * Returns the Notification handle (or null) so the caller can attach
 * click-handlers. Auto-dismisses after `ttlMs` to avoid OS notification
 * pile-up when many messages arrive in a burst.
 */
export function showChatNotification({ title, body, tag, onClick, ttlMs = 8000 }) {
  if (!isNotificationsSupported()) return null;
  if (Notification.permission !== 'granted') return null;
  // Only when the user is actually NOT looking at the tab — otherwise the
  // in-page toast already covers the case.
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') return null;
  try {
    const n = new Notification(title, {
      body: body || undefined,
      tag: tag || undefined,
      // Replace any earlier notification with the same tag — e.g. when 5
      // messages from the same conversation arrive while you're away.
      renotify: false,
      silent: true, // sound is owned by notificationSound.js
      icon: '/favicon.ico',
    });
    if (onClick) {
      n.onclick = (e) => {
        e.preventDefault();
        try { window.focus(); } catch { /* ignore */ }
        onClick();
        n.close();
      };
    }
    if (ttlMs > 0) setTimeout(() => { try { n.close(); } catch { /* ignore */ } }, ttlMs);
    return n;
  } catch {
    return null;
  }
}
