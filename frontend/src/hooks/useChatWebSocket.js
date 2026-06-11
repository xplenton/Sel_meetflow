import { useEffect, useRef } from 'react';
import { createChatWebSocket } from '../lib/chatWebSocket';
import api from '../lib/api';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Opens and manages the chat WebSocket for the logged-in user, dispatching
 * incoming events (`new-message`, `message-edited`, `message-deleted`,
 * `reaction-update`, `typing`, `read-receipt`, `conversation-created`) to
 * the parent ChatPage's state setters.
 *
 * Extracted from ChatPage.js (iter 385) to keep that orchestrator file
 * short and focused. The hook returns a ref pointing to the WS handle so
 * the caller can use `wsRef.current.send(...)` to publish typing/read
 * frames.
 *
 * @param {object} opts
 * @param {string|undefined} opts.userId — logged-in user id (re-opens WS when changed)
 * @param {React.MutableRefObject<{conversation_id:string}|null>} opts.activeConvRef
 * @param {(c: any[]) => any} opts.setMessages
 * @param {(c: any[]) => any} opts.setConversations
 * @param {(c: any) => any} opts.setTypingUsers
 * @param {(c: any) => any} opts.setReadStatus
 * @param {(id: string) => Promise<void>} opts.fetchMessages
 */
export default function useChatWebSocket({
  userId,
  activeConvRef,
  setMessages,
  setConversations,
  setTypingUsers,
  setReadStatus,
  fetchMessages,
}) {
  const wsRef = useRef(null);

  useEffect(() => {
    if (!userId) return undefined;
    const wsUrl = API_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    const handle = createChatWebSocket(`${wsUrl}/api/ws/chat/${userId}`, (data) => {
      if (data.type === 'new-message') {
        const isForActive = data.conversation_id === activeConvRef.current?.conversation_id;
        setMessages(prev => {
          if (isForActive) {
            if (prev.find(m => m.message_id === data.message.message_id)) return prev;
            return [...prev, data.message];
          }
          return prev;
        });
        // Defense-in-depth against timing races: WS event may arrive before
        // activeConv is set; re-fetch active-conv messages after a short
        // delay so the list is guaranteed to be consistent with the DB.
        if (isForActive) {
          setTimeout(() => {
            const cur = activeConvRef.current;
            if (cur?.conversation_id === data.conversation_id) {
              fetchMessages(cur.conversation_id);
            }
          }, 300);
        }
        setConversations(prev => prev.map(c =>
          c.conversation_id === data.conversation_id
            ? { ...c, last_message: { message_id: data.message.message_id, content: data.message.content?.substring(0, 100), sender_name: data.message.sender_name, created_at: data.message.created_at }, updated_at: data.message.created_at, unread_count: c.conversation_id === activeConvRef.current?.conversation_id ? 0 : (c.unread_count || 0) + 1 }
            : c
        ).sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')));
      } else if (data.type === 'message-edited') {
        setMessages(prev => prev.map(m => m.message_id === data.message.message_id ? data.message : m));
      } else if (data.type === 'message-deleted') {
        setMessages(prev => prev.filter(m => m.message_id !== data.message_id));
      } else if (data.type === 'reaction-update') {
        setMessages(prev => prev.map(m => m.message_id === data.message_id ? { ...m, reactions: data.reactions } : m));
      } else if (data.type === 'typing') {
        setTypingUsers(prev => ({ ...prev, [data.conversation_id]: { name: data.user_name, ts: Date.now() } }));
        setTimeout(() => setTypingUsers(prev => {
          const n = { ...prev };
          if (n[data.conversation_id]?.ts < Date.now() - 2500) delete n[data.conversation_id];
          return n;
        }), 3000);
      } else if (data.type === 'read-receipt') {
        // iter 179 — peer has just read up to `last_read`. Merge into the
        // per-conversation readStatus map so <MessageBubble /> can render
        // "Gelesen" indicators below own messages.
        setReadStatus(prev => ({
          ...prev,
          [data.conversation_id]: {
            ...(prev[data.conversation_id] || {}),
            [data.user_id]: data.last_read,
          },
        }));
      } else if (data.type === 'conversation-created') {
        setConversations(prev => {
          if (prev.find(c => c.conversation_id === data.conversation.conversation_id)) return prev;
          return [data.conversation, ...prev];
        });
      }
    });
    wsRef.current = handle;
    return () => { try { handle.close(); } catch { /* ignore */ } };
    // The setters and fetchMessages are stable; activeConvRef is a ref.
    // Including them would cause the WS to reconnect on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // Re-sync on WS reconnect + tab focus (iter 150). Resync = re-fetch active
  // conversation's messages + the conversation list, since the WS has no
  // replay buffer for messages delivered during the gap.
  useEffect(() => {
    if (!userId) return undefined;
    const resync = () => {
      try {
        const conv = activeConvRef.current;
        if (conv?.conversation_id) {
          api.get(`/chat/conversations/${conv.conversation_id}/messages?limit=80`)
            .then(({ data }) => setMessages(data))
            .catch(() => {});
        }
        api.get('/chat/conversations').then(({ data }) => setConversations(data)).catch(() => {});
      } catch { /* ignore */ }
    };
    const onVisibility = () => { if (document.visibilityState === 'visible') resync(); };
    window.addEventListener('ws:reconnected', resync);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('ws:reconnected', resync);
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  return wsRef;
}
