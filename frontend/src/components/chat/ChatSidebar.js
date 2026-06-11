import { useState } from 'react';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import {
  BellOff, ChevronDown, Lock, MessageSquare, Pin, Plus, Search, Trash2,
  Users, Volume2, VolumeX,
} from 'lucide-react';
import StatusDot from './StatusDot';
import ChatPushBanner from './ChatPushBanner';
import PullToRefreshIndicator from '../PullToRefreshIndicator';
import {
  isChatSoundMuted, setChatSoundMuted, playNotificationSound,
  getChatSoundVolume, setChatSoundVolume, CHAT_SOUND_PROFILES,
} from '../../lib/notificationSound';
import { notificationPermission, requestNotificationPermission } from '../../lib/browserNotifications';
import { timeAgo } from '../../lib/timeAgo';
import { toast } from 'sonner';

const VOLUME_LABELS = { low: 'Leise', normal: 'Normal', loud: 'Laut' };

/**
 * Sound + volume toggle in the sidebar header (iter 307 / 309).
 * Kept colocated with ChatSidebar because it's only used here.
 */
function ChatSoundToggle() {
  const [muted, setMuted] = useState(isChatSoundMuted());
  const [volume, setVolume] = useState(getChatSoundVolume());
  const [open, setOpen] = useState(false);
  const toggle = async () => {
    const next = !muted;
    setChatSoundMuted(next);
    setMuted(next);
    if (!next) {
      try { playNotificationSound(); } catch { /* ignore */ }
      if (notificationPermission() === 'default') {
        try {
          const res = await requestNotificationPermission();
          if (res === 'granted') toast.success('Benachrichtigungen sind aktiv.');
          else if (res === 'denied') toast.info('Browser-Benachrichtigungen blockiert. Du wirst trotzdem im Tab benachrichtigt.');
        } catch { /* ignore */ }
      }
    }
  };
  const pickVolume = (v) => {
    setChatSoundVolume(v);
    setVolume(v);
    setOpen(false);
    if (!muted) {
      try { playNotificationSound(); } catch { /* ignore */ }
    }
  };
  return (
    <div className="relative flex items-center">
      <button
        onClick={toggle}
        data-testid="chat-sound-toggle"
        title={muted ? 'Benachrichtigungs-Ton einschalten' : 'Benachrichtigungs-Ton stumm schalten'}
        className={`h-8 w-8 flex items-center justify-center rounded-full transition-colors ${
          muted ? 'text-[#C87967] hover:bg-[#C87967]/10' : 'text-[#4A5D4E] hover:bg-[#4A5D4E]/10'
        }`}
      >
        {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
      </button>
      {!muted && (
        <>
          <button
            onClick={() => setOpen(o => !o)}
            className="text-[10px] text-[#6B7280] hover:text-[#4A5D4E] px-1.5 rounded"
            title="Lautstärke"
            data-testid="chat-sound-volume-btn"
          >
            <ChevronDown className="w-3 h-3" />
          </button>
          {open && (
            <div className="absolute top-9 right-0 bg-white border border-[#E2E4E0] rounded-lg shadow-md z-50 min-w-[110px] py-1" data-testid="chat-sound-volume-menu">
              {CHAT_SOUND_PROFILES.map(p => (
                <button
                  key={p}
                  onClick={() => pickVolume(p)}
                  className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-[#F3F4F1] ${volume === p ? 'text-[#4A5D4E] font-medium' : 'text-[#1C1F1D]'}`}
                  data-testid={`chat-sound-volume-${p}`}
                >
                  {VOLUME_LABELS[p]} {volume === p && '✓'}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Left-hand chat sidebar — header (title, new-chat button, sound toggle,
 * search input, filter chips) + scrollable conversation list (with DND
 * banner, push banner, user search results, conversation items, delete
 * action). Extracted from ChatPage.js (iter 384) to keep the orchestrator
 * file under the 700-line guideline.
 */
export default function ChatSidebar({
  // Visibility (mobile)
  mobileShowChat,
  // Header
  onNewChat,
  search, setSearch,
  filter, setFilter,
  // List
  convPtr,
  language,
  myStatus,
  userSearchResults,
  startChatWithUser,
  loading,
  filtered,
  user,
  activeConv,
  onPickConversation,
  onDeleteConversation,
  getConvName,
  formatTime,
  t,
}) {
  return (
    <div
      className={`w-full md:w-64 lg:w-80 border-r border-[#E2E4E0] bg-white flex flex-col flex-shrink-0 ${mobileShowChat ? 'hidden md:flex' : 'flex'}`}
      data-testid="chat-conv-list"
    >
      {/* Iter 379 — On mobile (`< md`), reserve right-padding so the
           in-list "+" button does not collide with the global floating
           UserMenu cluster (NotificationBell + Avatar, ~90px wide). */}
      <div className="p-3 lg:p-4 border-b border-[#E2E4E0] pr-28 md:pr-3 lg:pr-4">
        <div className="flex items-center justify-between mb-2 lg:mb-3">
          <h1 className="text-base lg:text-lg font-semibold text-[#1C1F1D] pl-1" style={{ fontFamily: 'Manrope' }}>Chat</h1>
          <div className="flex items-center gap-1">
            <ChatSoundToggle />
            <Button onClick={onNewChat} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-8 w-8 p-0" data-testid="new-chat-btn">
              <Plus className="w-4 h-4" />
            </Button>
          </div>
        </div>
        <div className="relative mb-2">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
          <Input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t('searchUserOrChat')}
            className="pl-8 h-8 text-xs border-[#E2E4E0] rounded-lg"
            data-testid="chat-search"
          />
        </div>
        <div className="flex gap-1">
          {[['all', t('filterAll')], ['unread', t('filterUnread')], ['pinned', t('filterPinned')]].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`text-[10px] px-2 py-1 rounded-full transition-colors ${filter === key ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280] hover:bg-[#E8EAE6]'}`}
              data-testid={`chat-filter-${key}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* iter 317 — pull-to-refresh on mobile (conversations list) */}
      <PullToRefreshIndicator pullPx={convPtr.pullPx} refreshing={convPtr.refreshing} threshold={convPtr.threshold} />
      <div className="flex-1 overflow-y-auto" {...convPtr.bind} style={{ touchAction: convPtr.isPulling ? 'none' : undefined }}>
        {/* Iter 262 — WebPush für DMs aktivieren */}
        <ChatPushBanner language={language} />
        {/* Own DND status banner */}
        {myStatus === 'dnd' && (
          <div className="mx-3 my-2 px-3 py-2 bg-[#D4A373]/10 border border-[#D4A373]/20 rounded-lg flex items-center gap-2" data-testid="chat-dnd-banner">
            <BellOff className="w-3.5 h-3.5 text-[#D4A373] flex-shrink-0" />
            <span className="text-[10px] text-[#D4A373] font-medium">{language === 'de' ? 'Nicht stoeren aktiv' : 'Do not disturb active'}</span>
          </div>
        )}
        {/* User search results */}
        {userSearchResults.length > 0 && search.length >= 2 && (
          <div className="border-b border-[#E2E4E0]">
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-widest font-bold text-[#9CA3AF] bg-[#F9F9F8]">Nutzer</div>
            {userSearchResults.slice(0, 5).map(u => (
              <button
                key={u.user_id}
                onClick={() => startChatWithUser(u)}
                className={`w-full flex items-center gap-2 lg:gap-3 px-3 lg:px-4 py-2 transition-colors text-left ${u.dm_blocked ? 'opacity-70' : 'hover:bg-[#4A5D4E]/5'}`}
                title={u.dm_blocked ? u.dm_blocked_reason : ''}
                data-testid={`user-result-${u.user_id}`}
              >
                <div className="relative flex-shrink-0">
                  <div className="w-9 h-9 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs font-medium text-[#4A5D4E]">
                    {u.avatar ? <img src={u.avatar} alt="" className="w-9 h-9 rounded-full object-cover" /> : (u.name?.[0]?.toUpperCase() || '?')}
                  </div>
                  <StatusDot status={u.status_mode || (u.online ? 'online' : 'offline')} />
                </div>
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-[#1C1F1D] block truncate flex items-center gap-1.5">
                    {u.name}
                    {u.dm_blocked && <Lock className="w-3 h-3 text-[#C87967]" />}
                  </span>
                  <span className="text-[10px] text-[#9CA3AF] truncate block">
                    {u.dm_blocked
                      ? u.dm_blocked_reason
                      : u.status_mode === 'dnd' ? (language === 'de' ? 'Nicht stoeren' : 'Do not disturb')
                      : u.status_mode === 'away' ? (language === 'de' ? 'Abwesend' : 'Away')
                      : (u.status_mode === 'offline' || (!u.online && !u.status_mode)) && u.last_seen
                        ? `${language === 'de' ? 'Zuletzt gesehen' : 'Last seen'} ${timeAgo(u.last_seen, language)}`
                        : u.email}
                  </span>
                </div>
                <MessageSquare className={`w-4 h-4 flex-shrink-0 ${u.dm_blocked ? 'text-[#D1D5DB]' : 'text-[#4A5D4E]'}`} />
              </button>
            ))}
          </div>
        )}
        {search.length >= 2 && filtered.length > 0 && (
          <div className="px-3 py-1.5 text-[10px] uppercase tracking-widest font-bold text-[#9CA3AF] bg-[#F9F9F8]">Chats</div>
        )}
        {loading ? (
          <div className="p-4 text-center text-[#9CA3AF] text-sm">{t('loading')}</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-[#9CA3AF] text-xs">{t('noConversations')}</div>
        ) : (
          filtered.map(c => {
            const isActive = activeConv?.conversation_id === c.conversation_id;
            const pinned = (c.pinned_by || []).includes(user?.user_id);
            const muted = (c.muted_by || []).includes(user?.user_id);
            return (
              <div
                key={c.conversation_id}
                onClick={() => onPickConversation(c)}
                className={`flex items-center gap-2 lg:gap-3 px-3 lg:px-4 py-2.5 lg:py-3 cursor-pointer border-b border-[#F3F4F1] transition-colors group/conv ${isActive ? 'bg-[#4A5D4E]/5' : 'hover:bg-[#F3F4F1]'}`}
                data-testid={`conv-${c.conversation_id}`}
              >
                <div className="relative flex-shrink-0">
                  <div className="w-9 h-9 lg:w-10 lg:h-10 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs lg:text-sm font-medium text-[#4A5D4E]">
                    {c.type === 'group' ? <Users className="w-5 h-5" /> : (getConvName(c)?.[0]?.toUpperCase() || '?')}
                  </div>
                  <StatusDot status={c.other_status || (c.other_online ? 'online' : 'offline')} size="lg" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-[#1C1F1D] truncate flex items-center gap-1">
                      {pinned && <Pin className="w-3 h-3 text-[#D4A373]" />}
                      {getConvName(c)}
                      {muted && <BellOff className="w-3 h-3 text-[#C87967]" />}
                    </span>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <span className="text-[10px] text-[#9CA3AF]">{formatTime(c.last_message?.created_at)}</span>
                      <button
                        onClick={(e) => { e.stopPropagation(); onDeleteConversation(c.conversation_id); }}
                        className="p-1 rounded hover:bg-[#C87967]/10 text-transparent group-hover/conv:text-[#9CA3AF] hover:!text-[#C87967] transition-colors"
                        title="Chat löschen"
                        data-testid={`delete-conv-${c.conversation_id}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-[#9CA3AF] truncate">
                      {c.type === 'direct' && !c.other_online && c.other_last_seen && !c.last_message
                        ? `${language === 'de' ? 'Zuletzt gesehen' : 'Last seen'} ${timeAgo(c.other_last_seen, language)}`
                        : c.last_message ? `${c.last_message.sender_name}: ${c.last_message.content}` : 'Neue Unterhaltung'}
                    </p>
                    {(c.unread_count || 0) > 0 && (
                      <Badge className="bg-[#4A5D4E] text-white text-[9px] h-4 min-w-4 flex items-center justify-center rounded-full px-1">
                        {c.unread_count}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
