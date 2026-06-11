import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { useSearchParams, useNavigate } from 'react-router-dom';
import useChatSounds from '../hooks/useChatSounds';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import {
  Search, Send, Plus, Users, MessageSquare, Paperclip, BellOff,
  ChevronDown, X, Check, UserPlus, Phone, PhoneCall, Video, Pin, Lock, Unlock, BellRing,
  CornerDownRight,
} from 'lucide-react';
import api from '../lib/api';
import { resolveLiveRoute } from '../lib/liveRoute';
import usePullToRefresh from '../hooks/usePullToRefresh';

import { copyToClipboard } from '../lib/clipboard';
import useChatWebSocket from '../hooks/useChatWebSocket';
import { useChatUnread } from '../contexts/ChatUnreadContext';
import { toast } from 'sonner';
import StatusDot from '../components/chat/StatusDot';
import VoicePlayer from '../components/chat/VoicePlayer';
import MessageBubble from '../components/chat/MessageBubble';
import MessageInput from '../components/chat/MessageInput';
import ChatSidebar from '../components/chat/ChatSidebar';
import MessageList from '../components/chat/MessageList';
import NewChatDialog from '../components/chat/NewChatDialog';
import AddMembersDialog from '../components/chat/AddMembersDialog';
import { renderMarkdown } from '../lib/chatMarkdown';
import { timeAgo } from '../lib/timeAgo';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function ChatPage() {
  const { user } = useAuth();
  const { t, language } = useLanguage();
  const [searchParams] = useSearchParams();
  const { refresh: refreshChatUnread } = useChatUnread();

  const [conversations, setConversations] = useState([]);
  const [activeConv, setActiveConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // all, unread, mentions
  const [loading, setLoading] = useState(true);
  const [chatUsers, setChatUsers] = useState([]);
  const [userSearchResults, setUserSearchResults] = useState([]);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [newChatType, setNewChatType] = useState('direct');
  const [newChatMembers, setNewChatMembers] = useState([]);
  const [newChatName, setNewChatName] = useState('');
  const [editingMsg, setEditingMsg] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [typingUsers, setTypingUsers] = useState({});
  const [showMembers, setShowMembers] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState(null);
  const [showEmojiFor, setShowEmojiFor] = useState(null);
  const [msgSearch, setMsgSearch] = useState('');
  const [msgSearchResults, setMsgSearchResults] = useState([]);
  const [showMsgSearch, setShowMsgSearch] = useState(false);
  const [mobileShowChat, setMobileShowChat] = useState(false);
  const [replyTo, setReplyTo] = useState(null);
  const [threadOpen, setThreadOpen] = useState(null);
  const [threadReplies, setThreadReplies] = useState([]);
  const [threadParent, setThreadParent] = useState(null);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const navigate = useNavigate();
  const [gifOpen, setGifOpen] = useState(false);
  const [gifQuery, setGifQuery] = useState('');
  const [gifResults, setGifResults] = useState([]);
  const [myStatus, setMyStatus] = useState('online');
  // iter 179 — per-conversation read-status: { [conv_id]: { [user_id]: ISO } }
  const [readStatus, setReadStatus] = useState({});
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const typingTimeout = useRef(null);

  // iter 219 — notification + call sounds extracted into a dedicated hook
  // so this page no longer carries 50+ lines of Web-Audio-API plumbing.
  const { playNotificationSound, playCallSound } = useChatSounds();

  // Fetch conversations
  const fetchConversations = useCallback(async () => {
    try {
      const { data } = await api.get('/chat/conversations');
      setConversations(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  const activeConvRef = useRef(activeConv);
  useEffect(() => { activeConvRef.current = activeConv; }, [activeConv]);

  // Fetch messages
  const fetchMessages = useCallback(async (convId) => {
    try {
      const { data } = await api.get(`/chat/conversations/${convId}/messages?limit=80`);
      setMessages(data);
    } catch { /* ignore */ }
  }, []);

  // WebSocket + auto-resync. The hook owns the lifecycle and dispatches
  // events into the setters below; wsRef.send/.readyState (iter 383) lets
  // us publish typing + read frames from within this page.
  const wsRef = useChatWebSocket({
    userId: user?.user_id,
    activeConvRef,
    setMessages,
    setConversations,
    setTypingUsers,
    setReadStatus,
    fetchMessages,
  });
  // Global hint for the ChatUnreadContext — messages for the currently
  // open conversation shouldn't bump the sidebar badge (iter 123).
  useEffect(() => {
    window.__mfActiveConv = activeConv?.conversation_id || null;
    return () => { window.__mfActiveConv = null; };
  }, [activeConv]);
  const conversationsRef = useRef(conversations);
  useEffect(() => { conversationsRef.current = conversations; }, [conversations]);
  const myStatusRef = useRef(myStatus);
  useEffect(() => { myStatusRef.current = myStatus; }, [myStatus]);

  // Check own status (focus mode)
  useEffect(() => {
    api.get('/chat/my-status').then(({ data }) => setMyStatus(data.status_mode || 'online')).catch(() => {});
    const interval = setInterval(() => {
      api.get('/chat/my-status').then(({ data }) => setMyStatus(data.status_mode || 'online')).catch(() => {});
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => { fetchConversations(); }, [fetchConversations]);

  // Re-sync after a WS reconnect so conversations + active-chat messages
  // reflect anything that arrived while the socket was silently dropped.
  useEffect(() => {
    const onReconnect = () => {
      fetchConversations();
      if (activeConvRef.current?.conversation_id) {
        fetchMessages(activeConvRef.current.conversation_id);
      }
    };
    window.addEventListener('ws:reconnected', onReconnect);
    return () => window.removeEventListener('ws:reconnected', onReconnect);
  }, [fetchConversations, fetchMessages]);

  useEffect(() => {
    if (activeConv) {
      fetchMessages(activeConv.conversation_id);
      setMobileShowChat(true);
      // Persist "read up to now" so unread counts drop — both on server
      // (via WS `read` event) and in the global sidebar badge.
      try {
        if (wsRef.current?.readyState === 1) {
          wsRef.current.send(JSON.stringify({ type: 'read', conversation_id: activeConv.conversation_id }));
        }
      } catch { /* ignore */ }
      refreshChatUnread();
      // iter 179 — hydrate read-status for this conversation so peers'
      // past reads show up instantly (before any WS event arrives).
      api.get(`/chat/conversations/${activeConv.conversation_id}/read-status`)
        .then(({ data }) => {
          setReadStatus(prev => ({
            ...prev,
            [activeConv.conversation_id]: data.read_status || {},
          }));
        })
        .catch(() => { /* non-fatal */ });
    }
    // wsRef.current is a stable ref returned from useChatWebSocket; tracking it
    // would cause unnecessary re-runs of this read-receipt effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConv, fetchMessages, refreshChatUnread]);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // iter 320 — Safety re-fetch: when the active conversation's last_message
  // id in the sidebar changes (e.g. because a new-message WS event updated
  // the conv-list) but isn't yet in the local `messages` array, re-fetch.
  // This catches the case where the WS handler raced ahead of the DB write
  // OR the user navigated to /chat with a stale fetch.
  useEffect(() => {
    if (!activeConv?.conversation_id) return;
    const fresh = conversations.find(c => c.conversation_id === activeConv.conversation_id);
    const latestId = fresh?.last_message?.message_id;
    if (!latestId) return;
    const haveIt = messages.some(m => m.message_id === latestId);
    if (!haveIt) {
      fetchMessages(activeConv.conversation_id);
    }
  }, [conversations, activeConv?.conversation_id, messages, fetchMessages]);

  // Open conv from URL
  useEffect(() => {
    const convId = searchParams.get('conv');
    if (convId && conversations.length > 0) {
      const conv = conversations.find(c => c.conversation_id === convId);
      if (conv) setActiveConv(conv);
    }
  }, [searchParams, conversations]);

  // Fetch users for new chat or add member
  useEffect(() => {
    if (newChatOpen || addMemberOpen) api.get('/chat/users').then(({ data }) => setChatUsers(data)).catch(() => {});
  }, [newChatOpen, addMemberOpen]);

  // Send message
  const sendMessage = async () => {
    if (!input.trim() || !activeConv) return;
    const mentions = [];
    const mentionRegex = /@(\w+)/g;
    let match;
    while ((match = mentionRegex.exec(input)) !== null) {
      const member = activeConv.members?.find(m => m.name?.toLowerCase().includes(match[1].toLowerCase()));
      if (member) mentions.push(member.user_id);
    }
    try {
      const content = input;
      const { data } = await api.post(`/chat/conversations/${activeConv.conversation_id}/messages`, {
        content, mentions, priority: input.includes('!!!') ? 'urgent' : 'normal',
        reply_to: replyTo?.message_id || null,
        e2e_encrypted: false,
      });
      setInput('');
      setReplyTo(null);
      setMessages(prev => prev.find(m => m.message_id === data.message_id) ? prev : [...prev, data]);
      fetchConversations();
    } catch (err) { toast.error('Nachricht konnte nicht gesendet werden'); }
  };

  // Typing indicator
  const handleTyping = () => {
    if (wsRef.current?.readyState === 1 && activeConv) {
      wsRef.current.send(JSON.stringify({ type: 'typing', conversation_id: activeConv.conversation_id, user_name: user?.name }));
    }
  };

  // Create conversation
  const createConversation = async () => {
    if (newChatMembers.length === 0) { toast.error('Mindestens einen Teilnehmer wählen'); return; }
    if (!newChatName.trim()) { toast.error('Gruppenname eingeben'); return; }
    try {
      const { data } = await api.post('/chat/conversations', {
        type: 'group', member_ids: newChatMembers, name: newChatName,
      });
      setActiveConv(data);
      setNewChatOpen(false);
      setNewChatMembers([]);
      setNewChatName('');
      fetchConversations();
    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler'); }
  };

  // Edit message
  const saveEdit = async () => {
    if (!editingMsg || !editContent.trim()) return;
    const msgId = editingMsg;
    try {
      const { data } = await api.put(`/chat/messages/${msgId}`, { content: editContent });
      // Optimistic update: refresh local state immediately from API response
      // so the user sees the new content even if the WS `message-edited`
      // event is delayed, dropped, or arrives after a reconnect.
      if (data?.message_id) {
        setMessages(prev => prev.map(m => m.message_id === data.message_id ? data : m));
      }
      setEditingMsg(null);
      setEditContent('');
    } catch { toast.error('Fehler'); }
  };

  // Delete message
  const deleteMessage = async (msgId) => {
    try {
      await api.delete(`/chat/messages/${msgId}`);
      // Optimistic update: remove locally so the bubble disappears
      // immediately even if the WS `message-deleted` event is delayed.
      setMessages(prev => prev.filter(m => m.message_id !== msgId));
    } catch { toast.error('Fehler'); }
  };

  // Toggle reaction
  const toggleReaction = async (msgId, emoji) => {
    try {
      const { data } = await api.post(`/chat/messages/${msgId}/reactions`, { emoji });
      setShowEmojiFor(null);
      // Optimistic update from API response
      if (data?.reactions) {
        setMessages(prev => prev.map(m => m.message_id === msgId ? { ...m, reactions: data.reactions } : m));
      }
    } catch { /* ignore */ }
  };

  // Pin/Mute
  const togglePin = async () => {
    if (!activeConv) return;
    try { const { data } = await api.put(`/chat/conversations/${activeConv.conversation_id}/pin`); toast.success(data.pinned ? 'Angepinnt' : 'Entpinnt'); setActiveConv(prev => ({ ...prev, pinned_by: data.pinned ? [...(prev.pinned_by || []), user?.user_id] : (prev.pinned_by || []).filter(id => id !== user?.user_id) })); fetchConversations(); } catch { /* ignore */ }
  };
  const toggleMute = async () => {
    if (!activeConv) return;
    try { const { data } = await api.put(`/chat/conversations/${activeConv.conversation_id}/mute`); toast.success(data.muted ? 'Stummgeschaltet' : 'Stummschaltung aufgehoben'); setActiveConv(prev => ({ ...prev, muted_by: data.muted ? [...(prev.muted_by || []), user?.user_id] : (prev.muted_by || []).filter(id => id !== user?.user_id) })); fetchConversations(); } catch { /* ignore */ }
  };

  // Delete conversation
  // iter 308 — Show the real server error so production failures are
  // diagnosable instead of a generic "Fehler beim Löschen".
  const deleteConversation = async (convId) => {
    if (!window.confirm('Chat und alle Nachrichten wirklich löschen?')) return;
    try {
      await api.delete(`/chat/conversations/${convId}`);
      toast.success('Chat gelöscht');
      if (activeConv?.conversation_id === convId) { setActiveConv(null); setMessages([]); setMobileShowChat(false); }
      fetchConversations();
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail || e?.message || 'Unbekannter Fehler';
      const msg = status
        ? `Fehler beim Löschen (HTTP ${status}): ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`
        : `Fehler beim Löschen: ${detail}`;
      toast.error(msg, { duration: 8000 });
      console.error('[chat] delete failed', { convId, status, detail, error: e });
    }
  };


  // File upload
  const uploadFile = async (file) => {
    if (!file || !activeConv) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const { data } = await api.post(`/chat/conversations/${activeConv.conversation_id}/upload`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setMessages(prev => prev.find(m => m.message_id === data.message_id) ? prev : [...prev, data]);
      fetchConversations();
    } catch { toast.error('Upload fehlgeschlagen'); }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    await uploadFile(file);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;
    const files = e.dataTransfer?.files;
    if (files?.length > 0) {
      for (const file of files) {
        await uploadFile(file);
      }
    }
  };

  const handleDragOver = (e) => { e.preventDefault(); e.stopPropagation(); };
  const handleDragEnter = (e) => { e.preventDefault(); e.stopPropagation(); dragCounter.current++; setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); e.stopPropagation(); dragCounter.current--; if (dragCounter.current <= 0) { setIsDragging(false); dragCounter.current = 0; } };

  // Voice recording
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (blob.size < 1000) return;
        const formData = new FormData();
        formData.append('file', blob, `voice_${Date.now()}.webm`);
        try {
          const { data } = await api.post(`/chat/conversations/${activeConv.conversation_id}/voice`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
          setMessages(prev => prev.find(m => m.message_id === data.message_id) ? prev : [...prev, data]);
          fetchConversations();
        } catch { toast.error('Sprachnachricht fehlgeschlagen'); }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch { toast.error('Mikrofon nicht verfügbar'); }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setRecording(false);
  };

  // Start call from chat
  const startCall = async (opts = {}) => {
    if (!activeConv) return;
    // Iter 401 — Bei 1:1-Direkt-Chats prüfen, ob das Gegenüber online ist.
    // Vorher konnte der Anruf gestartet werden auch wenn der andere User
    // offline war → der Caller landete in einem leeren LiveKit-Raum ohne
    // Hinweis. Jetzt: freundliche Toast-Meldung statt „Anruf rumläuft".
    // Gruppen-Calls bleiben unangetastet, da andere Mitglieder online
    // sein könnten.
    if (activeConv.type === 'direct') {
      const isOnline = activeConv.other_online || ['online', 'busy'].includes(activeConv.other_status);
      if (!isOnline) {
        toast.error('Videoanruf nicht möglich — Gegenüber ist gerade offline.');
        return;
      }
    }
    try {
      const { data } = await api.post(
        `/chat/conversations/${activeConv.conversation_id}/call`,
        { urgent: !!opts.urgent }
      );
      // Caller skips the PreJoin screen — they've explicitly started the
      // call, so go straight into the live meeting (iter 122). Choose the
      // right transport (mesh vs. LiveKit SFU) based on conversation
      // headcount — group calls with 3+ members route to the SFU, which
      // scales far better than the mesh for multi-party video (iter 138).
      const headcount = (activeConv.members?.length || 2);
      const route = await resolveLiveRoute(data.meeting_id, headcount);
      navigate(route);
    } catch { toast.error('Anruf konnte nicht gestartet werden'); }
  };

  // Open thread
  const openThread = async (msgId) => {
    setThreadOpen(msgId);
    try {
      const { data } = await api.get(`/chat/messages/${msgId}/replies`);
      setThreadParent(data.parent);
      setThreadReplies(data.replies);
    } catch { /* ignore */ }
  };

  // GIF search
  const searchGifs = async (q) => {
    setGifQuery(q);
    if (q.length < 2) { setGifResults([]); return; }
    try {
      const { data } = await api.get(`/chat/gifs?q=${encodeURIComponent(q)}`);
      setGifResults(data.results || []);
    } catch { /* ignore */ }
  };

  const sendGif = async (url) => {
    if (!activeConv) return;
    try {
      const { data } = await api.post(`/chat/conversations/${activeConv.conversation_id}/gif`, { url });
      setGifOpen(false);
      setGifQuery('');
      setGifResults([]);
      setMessages(prev => prev.find(m => m.message_id === data.message_id) ? prev : [...prev, data]);
      fetchConversations();
    } catch { toast.error('GIF senden fehlgeschlagen'); }
  };

  // Toggle encryption
  const toggleEncryption = async () => {
    if (!activeConv) return;
    try {
      const { data } = await api.put(`/chat/conversations/${activeConv.conversation_id}/encryption`);
      setActiveConv(prev => ({ ...prev, encrypted: data.encrypted }));
      fetchConversations();
      toast.success(data.encrypted ? 'Verschluesselung aktiviert' : 'Verschluesselung deaktiviert');
    } catch { toast.error('Fehler'); }
  };

  // Search messages
  const searchMessages = async () => {
    if (!msgSearch.trim()) { setMsgSearchResults([]); return; }
    try {
      const { data } = await api.get(`/chat/search?q=${encodeURIComponent(msgSearch)}${activeConv ? `&conv_id=${activeConv.conversation_id}` : ''}`);
      setMsgSearchResults(data);
    } catch { /* ignore */ }
  };

  // iter 317 — pull-to-refresh for the conversations list on mobile
  const convPtr = usePullToRefresh({ onRefresh: fetchConversations });

  // Filter conversations + search users
  const filtered = conversations.filter(c => {
    if (filter === 'unread') return (c.unread_count || 0) > 0;
    if (filter === 'pinned') return (c.pinned_by || []).includes(user?.user_id);
    const name = c.display_name || c.name || '';
    return !search || name.toLowerCase().includes(search.toLowerCase());
  });

  // Search users when typing (iter 385 — server-side q-filter so large
  // tenants with >200 users can find anyone, not just the first 200 names)
  useEffect(() => {
    if (search.length >= 2) {
      api.get('/chat/users', { params: { q: search } }).then(({ data }) => {
        setUserSearchResults(data);
      }).catch(() => {});
    } else {
      setUserSearchResults([]);
    }
  }, [search]);

  // Quick start chat with user
  const startChatWithUser = async (targetUser) => {
    try {
      const { data } = await api.post('/chat/conversations', {
        type: 'direct', member_ids: [targetUser.user_id],
      });
      setActiveConv(data);
      setSearch('');
      setUserSearchResults([]);
      fetchConversations();
    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler'); }
  };

  const getConvName = (c) => c.display_name || c.name || c.members?.map(m => m.name).filter(n => n !== user?.name).join(', ') || 'Chat';
  const isPinned = activeConv?.pinned_by?.includes(user?.user_id);
  const isMuted = activeConv?.muted_by?.includes(user?.user_id);
  const typing = activeConv ? typingUsers[activeConv.conversation_id] : null;

  const formatTime = (iso) => { if (!iso) return ''; const d = new Date(iso); return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }); };
  const formatDate = (iso) => { if (!iso) return ''; const d = new Date(iso); const today = new Date(); if (d.toDateString() === today.toDateString()) return 'Heute'; const y = new Date(today); y.setDate(y.getDate() - 1); if (d.toDateString() === y.toDateString()) return 'Gestern'; return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }); };

  const isImage = (type) => type?.startsWith('image/');

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 flex overflow-hidden ml-0 md:ml-[260px]" style={{ height: '100vh' }}>
        {/* Conversation List */}
        <ChatSidebar
          mobileShowChat={mobileShowChat}
          onNewChat={() => setNewChatOpen(true)}
          search={search}
          setSearch={setSearch}
          filter={filter}
          setFilter={setFilter}
          convPtr={convPtr}
          language={language}
          myStatus={myStatus}
          userSearchResults={userSearchResults}
          startChatWithUser={startChatWithUser}
          loading={loading}
          filtered={filtered}
          user={user}
          activeConv={activeConv}
          onPickConversation={(c) => { setActiveConv(c); setMessages([]); }}
          onDeleteConversation={deleteConversation}
          getConvName={getConvName}
          formatTime={formatTime}
          t={t}
        />


        {/* Chat Area */}
        <div className={`flex-1 flex flex-col bg-[#FAFAF9] ${mobileShowChat ? 'flex' : 'hidden md:flex'} relative`}
          data-testid="chat-area"
          onDragOver={handleDragOver}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}>
          {/* Drag overlay */}
          {isDragging && activeConv && (
            <div className="absolute inset-0 z-50 bg-[#4A5D4E]/10 backdrop-blur-[2px] border-2 border-dashed border-[#4A5D4E] rounded-xl flex items-center justify-center pointer-events-none" data-testid="drag-overlay">
              <div className="bg-white rounded-xl px-8 py-6 shadow-lg text-center">
                <Paperclip className="w-8 h-8 text-[#4A5D4E] mx-auto mb-2" />
                <p className="text-sm font-medium text-[#1C1F1D]">{language === 'de' ? 'Datei hier ablegen' : 'Drop file here'}</p>
                <p className="text-[10px] text-[#9CA3AF] mt-0.5">{language === 'de' ? 'Zum Hochladen loslassen' : 'Release to upload'}</p>
              </div>
            </div>
          )}
          {!activeConv ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <MessageSquare className="w-16 h-16 text-[#E2E4E0] mx-auto mb-4" />
                <p className="text-[#9CA3AF] text-sm mb-3">{t('pickConversation')}</p>
                <Button onClick={() => setNewChatOpen(true)} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs">
                  <Plus className="w-3.5 h-3.5 mr-1" /> {t('newChat')}
                </Button>
              </div>
            </div>
          ) : (
            <>
              {/* Chat Header */}
              <div className="px-3 md:px-4 py-2.5 md:py-3 border-b border-[#E2E4E0] bg-white flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 md:gap-3 min-w-0">
                  <button onClick={() => { setMobileShowChat(false); }} className="md:hidden p-1 flex-shrink-0"><ChevronDown className="w-5 h-5 rotate-90" /></button>
                  <div className="relative w-8 h-8 md:w-9 md:h-9 flex-shrink-0">
                    <div className="w-8 h-8 md:w-9 md:h-9 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-sm font-medium text-[#4A5D4E]">
                      {activeConv.type === 'group' ? <Users className="w-4 h-4" /> : (getConvName(activeConv)?.[0]?.toUpperCase() || '?')}
                    </div>
                    {activeConv.type === 'direct' && <StatusDot status={activeConv.other_status || (activeConv.other_online ? 'online' : 'offline')} size="lg" />}
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-sm font-medium text-[#1C1F1D] truncate">{getConvName(activeConv)}</h2>
                    <p className="text-[10px] text-[#9CA3AF] truncate">
                      {activeConv.type === 'direct' && activeConv.other_status === 'dnd'
                        ? (language === 'de' ? 'Nicht stoeren' : 'Do not disturb')
                        : activeConv.type === 'direct' && activeConv.other_status === 'away'
                        ? (language === 'de' ? 'Abwesend' : 'Away')
                        : activeConv.type === 'direct' && !activeConv.other_online && activeConv.other_last_seen
                        ? `${language === 'de' ? 'Zuletzt gesehen' : 'Last seen'} ${timeAgo(activeConv.other_last_seen, language)}`
                        : activeConv.type === 'direct' && activeConv.other_online
                        ? (language === 'de' ? 'Online' : 'Online')
                        : `${activeConv.members?.length} Teilnehmer`}
                      {typing ? ` - ${typing.name} tippt...` : ''}
                      {activeConv.encrypted && <Lock className="w-3 h-3 inline ml-1 text-[#6B8E23]" />}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-0.5 flex-shrink-0">
                  <button onClick={() => startCall()} className="p-1.5 rounded-lg hover:bg-[#4A5D4E]/10 text-[#4A5D4E] hover:text-[#3E4E42] transition-colors" title="Videoanruf starten" data-testid="chat-call-btn"><Video className="w-4 h-4" /></button>
                  <button
                    onClick={() => {
                      if (window.confirm('Dringender Anruf?\n\nDurchbricht den Nicht-Stören-Modus des Empfängers und sendet eine doppelte Benachrichtigung. Bitte nur bei Notfällen einsetzen.')) {
                        startCall({ urgent: true });
                      }
                    }}
                    className="p-1.5 rounded-lg hover:bg-[#C87967]/10 text-[#C87967] hover:text-[#B5624F] transition-colors"
                    title={t('urgentCallHint')}
                    data-testid="chat-urgent-call-btn"
                  ><PhoneCall className="w-4 h-4" /></button>
                  <button onClick={() => setShowMsgSearch(!showMsgSearch)} className="p-1.5 rounded-lg hover:bg-[#F3F4F1] text-[#6B7280]" data-testid="chat-msg-search-btn"><Search className="w-4 h-4" /></button>
                  <button onClick={toggleEncryption} className={`p-1.5 rounded-lg hover:bg-[#F3F4F1] ${activeConv.encrypted ? 'text-[#6B8E23]' : 'text-[#6B7280]'}`} title={activeConv.encrypted ? 'E2E aktiv' : 'E2E aktivieren'} data-testid="chat-encrypt-btn">
                    {activeConv.encrypted ? <Lock className="w-4 h-4" /> : <Unlock className="w-4 h-4" />}
                  </button>
                  <button onClick={togglePin} className={`p-1.5 rounded-lg hover:bg-[#F3F4F1] ${isPinned ? 'text-[#D4A373]' : 'text-[#6B7280]'}`} data-testid="chat-pin-btn"><Pin className="w-4 h-4" /></button>
                  <button onClick={toggleMute} className={`p-1.5 rounded-lg hover:bg-[#F3F4F1] ${isMuted ? 'text-[#C87967] bg-[#C87967]/10' : 'text-[#6B7280]'}`} data-testid="chat-mute-btn" title={isMuted ? 'Stummschaltung aufheben' : 'Stummschalten'}>
                    {isMuted ? <BellOff className="w-4 h-4" /> : <BellRing className="w-4 h-4" />}
                  </button>
                  {activeConv.type === 'group' && (
                    <button onClick={() => setShowMembers(!showMembers)} className="p-1.5 rounded-lg hover:bg-[#F3F4F1] text-[#6B7280]" data-testid="chat-members-btn"><Users className="w-4 h-4" /></button>
                  )}
                </div>
              </div>

              {/* Message Search Bar */}
              {showMsgSearch && (
                <div className="px-4 py-2 bg-white border-b border-[#E2E4E0] flex items-center gap-2">
                  <Search className="w-3.5 h-3.5 text-[#9CA3AF]" />
                  <Input value={msgSearch} onChange={e => setMsgSearch(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && searchMessages()}
                    placeholder="Nachrichten durchsuchen..." className="h-7 text-xs border-none shadow-none" data-testid="chat-msg-search-input" />
                  <button onClick={() => { setShowMsgSearch(false); setMsgSearch(''); setMsgSearchResults([]); }} className="text-[#9CA3AF]"><X className="w-4 h-4" /></button>
                </div>
              )}

              {/* E2E Encryption Banner */}
              {activeConv.encrypted && (
                <div className="px-4 py-1.5 bg-[#6B8E23]/8 border-b border-[#6B8E23]/15 flex items-center gap-2" data-testid="e2e-banner">
                  <Lock className="w-3 h-3 text-[#6B8E23]" />
                  <span className="text-[10px] text-[#6B8E23] font-medium">Ende-zu-Ende-verschluesselt</span>
                </div>
              )}

              {/* Members Panel */}
              {showMembers && (
                <div className="px-4 py-3 bg-white border-b border-[#E2E4E0]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-[#6B7280]">{activeConv.members?.length} Teilnehmer</span>
                    <button onClick={() => setAddMemberOpen(true)} className="text-[10px] text-[#4A5D4E] flex items-center gap-1"><UserPlus className="w-3 h-3" /> Hinzufügen</button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {activeConv.members?.map(m => (
                      <span key={m.user_id} className="text-[11px] px-2 py-1 bg-[#F3F4F1] rounded-full text-[#4B5563]">{m.name}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Messages */}
              <MessageList
                ref={messagesEndRef}
                messages={messages}
                msgSearchResults={msgSearchResults}
                clearMsgSearch={() => { setMsgSearchResults([]); setMsgSearch(''); }}
                activeConv={activeConv}
                user={user}
                language={language}
                editingMsg={editingMsg}
                editContent={editContent}
                setEditContent={setEditContent}
                saveEdit={saveEdit}
                cancelEdit={() => setEditingMsg(null)}
                beginEdit={(m) => { setEditingMsg(m.message_id); setEditContent(m.content); }}
                showEmojiFor={showEmojiFor}
                toggleShowEmoji={(id) => setShowEmojiFor(showEmojiFor === id ? null : id)}
                toggleReaction={toggleReaction}
                deleteMessage={deleteMessage}
                onReply={setReplyTo}
                onOpenThread={openThread}
                onStartCall={startCall}
                onJoinMeeting={(mid) => navigate(`/meetings/${mid}/join`)}
                readStatus={readStatus}
                formatTime={formatTime}
                formatDate={formatDate}
                t={t}
              />

              {/* Input Area */}
              <MessageInput
                input={input}
                setInput={setInput}
                sendMessage={sendMessage}
                handleTyping={handleTyping}
                recording={recording}
                startRecording={startRecording}
                stopRecording={stopRecording}
                replyTo={replyTo}
                clearReplyTo={() => setReplyTo(null)}
                fileInputRef={fileInputRef}
                handleFileUpload={handleFileUpload}
                gifOpen={gifOpen}
                setGifOpen={setGifOpen}
                gifQuery={gifQuery}
                gifResults={gifResults}
                searchGifs={searchGifs}
                sendGif={sendGif}
                t={t}
              />
            </>
          )}
        </div>
      </main>

      {/* New Group Chat Dialog */}
      <NewChatDialog
        open={newChatOpen}
        onOpenChange={setNewChatOpen}
        newChatName={newChatName}
        setNewChatName={setNewChatName}
        newChatMembers={newChatMembers}
        setNewChatMembers={setNewChatMembers}
        chatUsers={chatUsers}
        createConversation={createConversation}
        t={t}
      />

      {/* Add Member Dialog */}
      <AddMembersDialog
        open={addMemberOpen}
        onOpenChange={setAddMemberOpen}
        activeConv={activeConv}
        chatUsers={chatUsers}
        setActiveConv={setActiveConv}
        fetchConversations={fetchConversations}
        t={t}
      />

      {/* Thread Panel */}
      <Dialog open={!!threadOpen} onOpenChange={(open) => { if (!open) { setThreadOpen(null); setThreadReplies([]); setThreadParent(null); } }}>
        <DialogContent className="sm:max-w-[480px] max-h-[80vh] flex flex-col">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><CornerDownRight className="w-4 h-4" /> Thread</DialogTitle></DialogHeader>
          {threadParent && (
            <div className="bg-[#F3F4F1] rounded-xl p-3 mb-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-medium text-[#1C1F1D]">{threadParent.sender_name}</span>
                <span className="text-[10px] text-[#9CA3AF]">{formatTime(threadParent.created_at)}</span>
              </div>
              <div className="text-sm text-[#4B5563]" dangerouslySetInnerHTML={{ __html: renderMarkdown(threadParent.content) }} />
            </div>
          )}
          <div className="flex-1 overflow-y-auto space-y-2 min-h-0">
            {threadReplies.length === 0 ? (
              <p className="text-center text-xs text-[#9CA3AF] py-4">{t('noReplies')}</p>
            ) : threadReplies.map(r => (
              <div key={r.message_id} className={`flex ${r.sender_id === user?.user_id ? 'justify-end' : 'justify-start'}`}>
                <div className={`rounded-xl px-3 py-2 max-w-[85%] ${r.sender_id === user?.user_id ? 'bg-[#4A5D4E] text-white' : 'bg-white border border-[#E2E4E0] text-[#1C1F1D]'}`}>
                  {r.sender_id !== user?.user_id && <p className="text-[10px] font-medium opacity-70 mb-0.5">{r.sender_name}</p>}
                  {r.type === 'voice' ? (
                    <VoicePlayer src={`${API_URL}${r.file_url}`} duration={r.voice_duration} />
                  ) : (
                    <div className="text-sm" dangerouslySetInnerHTML={{ __html: renderMarkdown(r.content) }} />
                  )}
                  <span className={`text-[9px] block mt-0.5 ${r.sender_id === user?.user_id ? 'text-white/50' : 'text-[#9CA3AF]'}`}>{formatTime(r.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 pt-3 border-t border-[#E2E4E0]">
            <Input placeholder="Antworten..." spellCheck="true" lang="de" className="flex-1 border-[#E2E4E0] rounded-xl text-sm" data-testid="thread-input"
              onKeyDown={async (e) => {
                if (e.key === 'Enter' && e.target.value.trim()) {
                  const val = e.target.value.trim();
                  e.target.value = '';
                  try {
                    await api.post(`/chat/conversations/${activeConv?.conversation_id}/messages`, {
                      content: val, reply_to: threadOpen,
                    });
                    const { data } = await api.get(`/chat/messages/${threadOpen}/replies`);
                    setThreadReplies(data.replies);
                    setThreadParent(data.parent);
                  } catch { /* ignore */ }
                }
              }} />
            <Button className="bg-[#4A5D4E] text-white rounded-xl h-9 w-9 p-0" data-testid="thread-send-btn"
              onClick={async () => {
                const inp = document.querySelector('[data-testid="thread-input"]');
                if (!inp?.value?.trim()) return;
                const val = inp.value.trim();
                inp.value = '';
                try {
                  await api.post(`/chat/conversations/${activeConv?.conversation_id}/messages`, {
                    content: val, reply_to: threadOpen,
                  });
                  const { data } = await api.get(`/chat/messages/${threadOpen}/replies`);
                  setThreadReplies(data.replies);
                  setThreadParent(data.parent);
                } catch { /* ignore */ }
              }}><Send className="w-4 h-4" /></Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
