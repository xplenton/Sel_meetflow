/**
 * Resilient chat-WebSocket helper — shared by `StatusContext` and the global
 * `IncomingCallModal`. Wraps `window.WebSocket` with:
 *
 *   - Auto-reconnect with exponential backoff (1s, 2s, 4s, ... capped at 30s)
 *   - Keep-alive `ping` every 25 s (Kubernetes ingress proxies drop idle
 *     WebSockets after ~60 s; without keep-alive, the callee silently goes
 *     offline and misses `incoming-call` events).
 *   - Visibility-change detection: if the tab becomes visible and the socket
 *     is dead, force an immediate reconnect instead of waiting for backoff.
 *   - A `.close()` method that fully stops all timers and marks the handle
 *     "closed for good" so the backoff loop doesn't resurrect it.
 *   - Reports its lifecycle to `wsConnectionState` so the Sidebar dot can
 *     render green/yellow/red, and a `ws:reconnected` window-event is fired
 *     after every non-initial reconnect for consumers to refetch state.
 *
 * The handle is intentionally tiny — callers just provide an `onMessage`
 * callback and the URL and receive a `{ close }` object back. No external
 * deps; only uses browser APIs.
 */

import {
  _markOpen,
  _markClosed,
  _markReconnecting,
  _markReconnectDone,
} from './wsConnectionState';

const PING_INTERVAL_MS = 25_000;
const MAX_BACKOFF_MS = 30_000;

/**
 * @param {string} url - wss:// URL
 * @param {(data: object) => void} onMessage - fires for every parsed JSON
 *        frame EXCEPT pong (pongs are swallowed internally).
 * @returns {{ close: () => void }}
 */
export function createChatWebSocket(url, onMessage) {
  let ws = null;
  let pingTimer = null;
  let reconnectTimer = null;
  let attempt = 0;
  let stopped = false;
  let reportedOpen = false;      // has THIS handle reported _markOpen yet (for pairing with _markClosed)
  let reportedReconnecting = false; // is this handle currently counted as "reconnecting"

  const clearTimers = () => {
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };

  const scheduleReconnect = () => {
    if (stopped) return;
    if (!reportedReconnecting) {
      reportedReconnecting = true;
      _markReconnecting();
    }
    attempt += 1;
    const delay = Math.min(1000 * Math.pow(2, attempt - 1), MAX_BACKOFF_MS);
    reconnectTimer = setTimeout(() => {
      if (stopped) return;
      open();
    }, delay);
  };

  const open = () => {
    if (stopped) return;
    clearTimers();
    try {
      ws = new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }
    ws.onopen = () => {
      const wasReconnecting = reportedReconnecting;
      attempt = 0;
      if (reportedReconnecting) { reportedReconnecting = false; _markReconnectDone(); }
      reportedOpen = true;
      _markOpen();
      // Iter 280 — fire a window event after a *reconnect* (not the first
      // open) so listeners like StatusContext can refetch their state.
      // Without this, the user can stay shown as "offline" until the next
      // 60-second poll, even though the WS is already live again.
      if (wasReconnecting) {
        try { window.dispatchEvent(new CustomEvent('ws:reconnected')); } catch { /* ignore */ }
      }
      // Start keep-alive pings
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          try { ws.send(JSON.stringify({ type: 'ping' })); } catch { /* ignore */ }
        }
      }, PING_INTERVAL_MS);
    };
    ws.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch { return; }
      if (data && data.type === 'pong') return; // swallow keep-alive
      try { onMessage(data); } catch { /* consumer errors shouldn't kill WS */ }
    };
    ws.onerror = () => { /* onclose fires right after; reconnect there */ };
    ws.onclose = () => {
      clearTimers();
      if (reportedOpen) { reportedOpen = false; _markClosed(); }
      if (!stopped) scheduleReconnect();
    };
  };

  const onVisibility = () => {
    if (document.visibilityState !== 'visible') return;
    // If the socket is dead/absent, try to reconnect immediately
    if (stopped) return;
    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      attempt = 0;
      open();
    }
  };

  const onOnline = () => {
    if (stopped) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      attempt = 0;
      open();
    }
  };

  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('online', onOnline);

  open();

  return {
    /** Whether the underlying socket is OPEN (1). Mirrors `WebSocket.readyState`. */
    get readyState() {
      return ws ? ws.readyState : 3; // CLOSED if no socket yet
    },
    /**
     * Send a JSON-stringified frame on the active socket. Returns true if
     * the frame was queued; false if the socket isn't OPEN (caller decides
     * whether to retry on `ws:reconnected`). Never throws.
     */
    send: (payload) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      try { ws.send(typeof payload === 'string' ? payload : JSON.stringify(payload)); return true; }
      catch { return false; }
    },
    close: () => {
      stopped = true;
      clearTimers();
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('online', onOnline);
      try { ws && ws.close(); } catch { /* ignore */ }
      ws = null;
      // Balance any outstanding status counters so the Sidebar dot settles.
      if (reportedOpen) { reportedOpen = false; _markClosed(); }
      if (reportedReconnecting) { reportedReconnecting = false; _markReconnectDone(); }
    },
  };
}
