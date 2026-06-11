/**
 * Singleton tracker for chat-WebSocket health.
 *
 * Every `createChatWebSocket` handle reports its lifecycle here (created,
 * opened, closed, reconnecting) so the Sidebar can render a live dot —
 * green (alle verbunden), gelb (reconnect läuft), rot (keine Verbindung).
 *
 * Also broadcasts a `ws:reconnected` CustomEvent on window whenever a
 * previously-closed handle re-opens, so consumers (ChatPage, StatusContext,
 * ...) can refetch state to stay in sync after a silent idle-drop.
 */

let openCount = 0;
let reconnectingCount = 0;
let hasEverOpened = false;
const listeners = new Set();

export const CONN_STATE = {
  CONNECTING: 'connecting', // initial, never opened yet
  OPEN: 'open',             // at least one WS currently open
  RECONNECTING: 'reconnecting', // no WS open, but a reconnect is scheduled
  OFFLINE: 'offline',       // no WS open, nothing scheduled (pre-login / post-logout)
};

export function getConnectionState() {
  if (openCount > 0) return CONN_STATE.OPEN;
  if (reconnectingCount > 0) return CONN_STATE.RECONNECTING;
  if (!hasEverOpened) return CONN_STATE.CONNECTING;
  return CONN_STATE.OFFLINE;
}

function notify() {
  const s = getConnectionState();
  for (const l of listeners) {
    try { l(s); } catch { /* ignore */ }
  }
}

export function subscribeConnectionState(fn) {
  listeners.add(fn);
  try { fn(getConnectionState()); } catch { /* ignore */ }
  return () => listeners.delete(fn);
}

// ----- Called by chatWebSocket.js -----
export function _markOpen() {
  openCount += 1;
  const wasFirstOpen = !hasEverOpened;
  hasEverOpened = true;
  notify();
  // Only fire reconnect event AFTER the first-ever open — the first open is
  // not a "reconnect", it's the initial connect.
  if (!wasFirstOpen) {
    try {
      window.dispatchEvent(new CustomEvent('ws:reconnected'));
    } catch { /* SSR */ }
  }
}

export function _markClosed() {
  openCount = Math.max(0, openCount - 1);
  notify();
}

export function _markReconnecting() {
  reconnectingCount += 1;
  notify();
}

export function _markReconnectDone() {
  reconnectingCount = Math.max(0, reconnectingCount - 1);
  notify();
}

export function _reset() {
  openCount = 0;
  reconnectingCount = 0;
  hasEverOpened = false;
  notify();
}
