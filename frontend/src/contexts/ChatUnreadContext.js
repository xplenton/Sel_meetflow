import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { createChatWebSocket } from '../lib/chatWebSocket';
import { playNotificationSound } from '../lib/notificationSound';
import { showChatNotification } from '../lib/browserNotifications';
import { toast } from 'sonner';
import api from '../lib/api';
import { CACHE_KEYS, getCache, setCache } from '../lib/cache';

/**
 * Global unread-chat counter — feeds the Sidebar badge + the
 * quick-access popover. Strategy (iter 123, extended iter 134):
 *   • Initial + fallback: poll `/chat/unread-summary` every 30 s (cheap).
 *   • Realtime: listen on the user's chat WS for `new-message` events and
 *     re-poll immediately — avoids 30 s lag on a just-arrived message.
 *   • **Global toast + sound (iter 134)**: when a chat message arrives while
 *     the user is on ANY page (not just /chat), show a toast with a
 *     "Öffnen"-action and play the notification sound. Skipped for own
 *     messages, DND status, muted conversations and call-typed messages.
 *   • Active tab hint: when a chat page is open and sets `window.__mfActiveConv`,
 *     messages for that conversation don't contribute to the badge or trigger
 *     the toast (to avoid double-feedback with the in-page sound).
 */
const ChatUnreadContext = createContext(null);

// Iter 378/380 — localStorage-Cache für das Unread-Summary, damit die Sidebar
// das Chat-Badge sofort beim Mount in der korrekten Hoehe rendert. Vorher
// startete `summary` bei `{ total_unread: 0, top: [] }` → kein Badge
// sichtbar bis der initiale `/chat/unread-summary`-Request (ca. 300-800ms)
// zurückkam → kurzes Aufploppen des Badges. Mit dem Cache wird der letzte
// bekannte Wert beim Reload sofort wieder angezeigt, der Refresh im Hinter-
// grund haelt ihn frisch (max. 30 s Drift im Worst-Case).
// (Iter 380: zentralisiert über lib/cache.js)
const SUMMARY_CACHE_TTL_MS = 10 * 60 * 1000;

function loadCachedSummary(userId) {
  return getCache(CACHE_KEYS.CHAT_UNREAD_SUMMARY, { ttlMs: SUMMARY_CACHE_TTL_MS, userId });
}

export function ChatUnreadProvider({ children }) {
  const { user } = useAuth();
  const [summary, setSummary] = useState(() => {
    const cached = loadCachedSummary(user?.user_id);
    return cached || { total_unread: 0, top: [] };
  });
  const wsRef = useRef(null);
  const lastFetchRef = useRef(0);
  const myStatusRef = useRef('online');
  const mutedConvsRef = useRef(new Set());

  const refresh = useCallback(async () => {
    if (!user?.user_id) return;
    // Simple in-memory debounce — don't refetch more than every 1.5 s
    const now = Date.now();
    if (now - lastFetchRef.current < 1500) return;
    lastFetchRef.current = now;
    try {
      const { data } = await api.get('/chat/unread-summary');
      const next = data || { total_unread: 0, top: [] };
      setSummary(next);
      // Cache persistieren — Folge-Reloads sehen sofort den korrekten Wert.
      setCache(CACHE_KEYS.CHAT_UNREAD_SUMMARY, next, { userId: user.user_id });
      // Iter 262 (PWA-Polish) — App-Badge auf installierten PWAs aktualisieren.
      // Auf iOS Safari sichtbar im Homescreen-Icon, auf Chrome/Android im Launcher.
      try {
        const total = Number(data?.total_unread || 0);
        if (total > 0 && 'setAppBadge' in navigator) {
          navigator.setAppBadge(total).catch(() => undefined);
        } else if ('clearAppBadge' in navigator) {
          navigator.clearAppBadge().catch(() => undefined);
        }
      } catch { /* ignore — badging not supported */ }
      // Remember which conversations are muted for this user — used to
      // decide whether a new-message toast/sound should fire.
      const muted = new Set();
      (data?.top || []).forEach(c => {
        if (Array.isArray(c.muted_by) && c.muted_by.includes(user.user_id)) {
          muted.add(c.conversation_id);
        }
      });
      mutedConvsRef.current = muted;
    } catch { /* best-effort */ }
  }, [user?.user_id]);

  // Poll my chat status (online/dnd/away) so DND suppresses toasts/sounds.
  useEffect(() => {
    if (!user?.user_id) return;
    let cancelled = false;
    const fetchStatus = () => {
      api.get('/chat/my-status')
        .then(({ data }) => { if (!cancelled) myStatusRef.current = data?.status_mode || 'online'; })
        .catch(() => {});
    };
    fetchStatus();
    const iv = setInterval(fetchStatus, 60000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [user?.user_id]);

  // Poll + WebSocket listener
  useEffect(() => {
    if (!user?.user_id) {
      setSummary({ total_unread: 0, top: [] });
      return;
    }
    refresh();
    const iv = setInterval(refresh, 30000);
    // Realtime WS — createChatWebSocket handles keep-alive + reconnect
    const backendUrl = process.env.REACT_APP_BACKEND_URL;
    if (backendUrl) {
      const wsUrl = backendUrl.replace(/^http/, 'ws') + `/api/ws/chat/${user.user_id}`;
      const handle = createChatWebSocket(wsUrl, (data) => {
        if (!data) return;
        if (data.type === 'new-message') {
          const m = data.message || {};
          // Skip if it's my own message
          if (m.sender_id === user.user_id) return;
          // Iter 387 — Sound + Toast entkoppeln. Vorher hat ein einziger
          // Guard (`__mfActiveConv === conv`) beides unterdrückt, was dazu
          // führte, dass beim Lesen einer offenen Konversation gar kein
          // akustischer Hinweis mehr kam (nur die allererste WS-Nachricht
          // gewann das Timing-Race gegen das useEffect, das `__mfActiveConv`
          // setzt). Slack-/Teams-Verhalten: Pip bei JEDER Nachricht, Popup-
          // Toast nur für inaktive Konversationen.
          const isViewingThisConv = window.__mfActiveConv === data.conversation_id;
          const isMuted = mutedConvsRef.current.has(data.conversation_id);
          const isDnd = myStatusRef.current === 'dnd';
          const isCall = m.type === 'call';
          const canPlay = !isMuted && !isDnd && !isCall;
          if (canPlay) {
            try { playNotificationSound(); } catch { /* ignore */ }
          }
          // Rich popup-Toast nur, wenn die Konversation NICHT gerade
          // angezeigt wird — sonst lenkt der Toast vom aktiven Lesen ab.
          if (canPlay && !isViewingThisConv) {
            const senderName = m.sender_name || 'Neue Nachricht';
            const preview = typeof m.content === 'string'
              ? (m.content.length > 80 ? `${m.content.slice(0, 80)}…` : m.content)
              : '';
            const openConv = () => {
              window.location.href = `/chat?conv=${data.conversation_id}`;
            };
            // iter 309 (2a) — rich popup toast with avatar-initials + action
            const initials = (() => {
              const cleaned = String(senderName || '?').split('@')[0].replace(/[._-]+/g, ' ').trim();
              const parts = cleaned.split(/\s+/).filter(Boolean);
              if (!parts.length) return '?';
              if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
              return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
            })();
            toast.custom((tId) => (
              <div
                className="flex items-start gap-3 p-4 rounded-2xl border-2 border-[#4A5D4E]/30 bg-white shadow-2xl w-[360px] animate-in slide-in-from-left-5 duration-300"
                data-testid="chat-toast-popup"
                style={{ boxShadow: '0 10px 40px -10px rgba(74, 93, 78, 0.35), 0 4px 12px rgba(0,0,0,0.08)' }}
              >
                <div className="relative shrink-0">
                  <div className="w-11 h-11 rounded-full bg-[#4A5D4E] text-white text-sm font-semibold flex items-center justify-center">
                    {initials}
                  </div>
                  <span className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-[#C87967] rounded-full ring-2 ring-white animate-pulse" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-[#1C1F1D] truncate">{senderName}</div>
                    <button
                      onClick={() => toast.dismiss(tId)}
                      className="text-[#9CA3AF] hover:text-[#6B7280] text-lg leading-none px-1"
                      data-testid="chat-toast-dismiss"
                      aria-label="Schließen"
                    >×</button>
                  </div>
                  <div className="text-[10px] uppercase tracking-wide text-[#4A5D4E]/70 font-medium mt-0.5">
                    Neue Chat-Nachricht
                  </div>
                  {preview && (
                    <div className="text-sm text-[#1C1F1D] line-clamp-3 mt-1.5 leading-snug">{preview}</div>
                  )}
                  <button
                    onClick={() => { toast.dismiss(tId); openConv(); }}
                    className="mt-2.5 px-3 py-1.5 rounded-full bg-[#4A5D4E] text-white text-xs font-medium hover:bg-[#3E4E42] transition-colors"
                    data-testid="chat-toast-open"
                  >
                    Antworten →
                  </button>
                </div>
              </div>
            ), {
              duration: 10000,
              // Iter 331 — Dedup via stable id: WebSocket-Reconnects oder
              // doppelte `new-message` Events ersetzen das vorhandene Toast,
              // statt ein zweites Popup zu rendern.
              id: m.message_id ? `chat-msg-${m.message_id}` : `chat-conv-${data.conversation_id}`,
            });
            // iter 309 (2b) — system-level notification when tab is in the background
            showChatNotification({
              title: senderName,
              body: preview,
              tag: `chat-${data.conversation_id}`,
              onClick: openConv,
            });
          }
          refresh();
        } else if (data.type === 'conversation-read' || data.type === 'messages-read') {
          refresh();
        } else if (data.type === 'guest-notify') {
          // iter 156 — a guest pinged their host ("Ich bin online"). Show
          // a toast with a 1-click "Antworten"-button that opens the chat.
          toast.info(data.title || 'Gast online', {
            description: data.body || '',
            action: {
              label: 'Öffnen',
              onClick: () => { window.location.href = '/chat'; },
            },
            duration: 12000,
            // Iter 331 — Dedup ping events for the same guest.
            id: data.guest_id ? `guest-notify-${data.guest_id}` : undefined,
          });
          try { playNotificationSound(); } catch { /* ignore */ }
        }
      });
      wsRef.current = handle;
    }
    return () => {
      clearInterval(iv);
      try { wsRef.current?.close(); } catch { /* ignore */ }
      wsRef.current = null;
    };
  }, [user?.user_id, refresh]);

  return (
    <ChatUnreadContext.Provider value={{ ...summary, refresh }}>
      {children}
    </ChatUnreadContext.Provider>
  );
}

export function useChatUnread() {
  const ctx = useContext(ChatUnreadContext);
  return ctx || { total_unread: 0, top: [], refresh: () => {} };
}
