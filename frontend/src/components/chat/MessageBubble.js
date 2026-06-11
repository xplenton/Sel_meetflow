import {
  AlertTriangle, BellOff, Check, CornerDownRight, Edit2, Hash, Lock,
  Phone, PhoneMissed, Reply, Smile, Trash2, Video, X,
} from 'lucide-react';
import VoicePlayer from './VoicePlayer';
import FilePreview from './FilePreview';
import { renderMarkdown } from '../../lib/chatMarkdown';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🎉', '🔥', '👀'];

/**
 * One chat message bubble (text / file / voice / call / gif / bot / auto-reply).
 *
 * Extracted from ChatPage.js (iter 383) to keep that orchestrator file under
 * the 700-line guideline. All state stays in ChatPage; this component is
 * intentionally presentational + receives callbacks. It does NOT memoise
 * because the parent already keys by `msg.message_id` and React's diff is
 * cheap for these small subtrees.
 */
export default function MessageBubble({
  msg,
  isOwn,
  showSenderName,    // true if previous msg has different sender (group chat)
  activeConv,
  user,
  language,
  editingMsg,
  editContent,
  setEditContent,
  saveEdit,
  cancelEdit,
  beginEdit,
  showEmojiFor,
  toggleShowEmoji,
  toggleReaction,
  deleteMessage,
  onReply,
  onOpenThread,
  onStartCall,
  onJoinMeeting,
  readStatus,
  formatTime,
  t,
}) {
  const isEditing = editingMsg === msg.message_id;
  const rs = readStatus[activeConv?.conversation_id] || {};
  const readPeers = Object.entries(rs).filter(([uid]) => uid !== user?.user_id);
  const readByCount = readPeers.filter(([, ts]) => ts && new Date(ts) >= new Date(msg.created_at)).length;
  const anyRead = readByCount > 0;

  return (
    <div className={`flex ${isOwn ? 'justify-end' : 'justify-start'} group mb-0.5`} data-testid={`msg-${msg.message_id}`}>
      <div className={`relative max-w-[85%] md:max-w-[75%] ${isOwn ? 'order-1' : ''}`}>
        {/* Sender name for group chats */}
        {!isOwn && activeConv?.type === 'group' && showSenderName && (
          <p className="text-[10px] text-[#6B7280] mb-0.5 ml-1">{msg.sender_name}</p>
        )}
        {/* Reply preview */}
        {msg.reply_preview && (
          <div className={`text-[10px] mb-0.5 ml-1 px-2 py-1 rounded-lg border-l-2 ${isOwn ? 'bg-white/10 border-white/30 text-white/70' : 'bg-[#F3F4F1] border-[#4A5D4E]/30 text-[#6B7280]'}`}>
            <span className="font-medium">{msg.reply_preview.sender_name}</span>: {msg.reply_preview.content}
          </div>
        )}
        <div className={`rounded-2xl px-3.5 py-2 ${isOwn ? 'bg-[#4A5D4E] text-white rounded-br-md' : 'bg-white border border-[#E2E4E0] text-[#1C1F1D] rounded-bl-md'} ${msg.priority === 'urgent' ? 'ring-2 ring-[#C87967]' : ''}`}>
          {msg.priority === 'urgent' && <div className="flex items-center gap-1 text-[10px] mb-1 opacity-80"><AlertTriangle className="w-3 h-3" /> Dringend</div>}
          {isEditing ? (
            <div className="flex items-center gap-1">
              <input
                data-testid={`msg-edit-input-${msg.message_id}`}
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && saveEdit()}
                className="bg-transparent text-sm outline-none flex-1 min-w-[100px]"
                autoFocus
              />
              <button data-testid={`msg-edit-save-${msg.message_id}`} onClick={saveEdit}><Check className="w-3.5 h-3.5" /></button>
              <button data-testid={`msg-edit-cancel-${msg.message_id}`} onClick={cancelEdit}><X className="w-3.5 h-3.5" /></button>
            </div>
          ) : msg.type === 'gif' ? (
            /* Iter 385 — Mobile-Fix für GIF-Rendering (no lazy loading on iOS Safari,
               explicit min-height to reserve space, onError fallback to link). */
            <a
              href={msg.gif_url}
              target="_blank"
              rel="noopener noreferrer"
              className="block rounded-lg overflow-hidden bg-black/5 min-h-[120px] w-full max-w-[240px]"
              data-testid={`gif-msg-${msg.message_id}`}
            >
              <img
                src={msg.gif_url}
                alt="GIF"
                className="block w-full h-auto rounded-lg"
                referrerPolicy="no-referrer"
                onError={(e) => {
                  const img = e.currentTarget;
                  img.style.display = 'none';
                  const parent = img.parentElement;
                  if (parent && !parent.querySelector('[data-gif-fallback]')) {
                    const fb = document.createElement('div');
                    fb.setAttribute('data-gif-fallback', '1');
                    fb.className = 'px-3 py-2 text-xs text-[#6B7280] underline';
                    fb.textContent = 'GIF im Browser öffnen';
                    parent.appendChild(fb);
                  }
                }}
              />
            </a>
          ) : msg.type === 'bot' ? (
            <div>
              <div className="flex items-center gap-1 text-[10px] opacity-70 mb-1"><Hash className="w-3 h-3" /> Bot</div>
              <div className="text-sm whitespace-pre-wrap break-words" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
            </div>
          ) : msg.type === 'auto-reply' ? (
            <div>
              <div className="flex items-center gap-1 text-[10px] mb-1" style={{ opacity: 0.7 }}>
                <BellOff className="w-3 h-3" />
                <span>{language === 'de' ? 'Automatische Antwort' : 'Auto-reply'}</span>
              </div>
              <div className="text-sm whitespace-pre-wrap break-words italic opacity-90">{msg.content}</div>
            </div>
          ) : msg.type === 'voice' ? (
            <VoicePlayer src={`${API_URL}${msg.file_url}`} duration={msg.voice_duration} />
          ) : msg.type === 'call' ? (
            msg.missed ? (
              <div
                className={`rounded-xl overflow-hidden ${isOwn ? 'bg-white/10' : 'bg-[#C87967]/8 border border-[#C87967]/30'}`}
                style={{ minWidth: 240 }}
                data-testid={`missed-call-${msg.message_id}`}
              >
                <div className="px-4 py-3 flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${isOwn ? 'bg-white/20' : 'bg-[#C87967]/15'}`}>
                    <PhoneMissed className={`w-5 h-5 ${isOwn ? 'text-white' : 'text-[#C87967]'}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium ${isOwn ? 'text-white' : 'text-[#C87967]'}`}>{msg.content}</p>
                    <p className={`text-[10px] ${isOwn ? 'text-white/60' : 'text-[#9CA3AF]'}`}>
                      {isOwn ? 'Niemand ist beigetreten' : `${msg.sender_name} hat angerufen`}
                    </p>
                  </div>
                  {!isOwn && (
                    <button
                      onClick={onStartCall}
                      className="px-3 py-1.5 rounded-lg bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs font-medium transition-colors"
                      title={t('callBack')}
                      data-testid={`callback-${msg.message_id}`}
                    >
                      <Phone className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className={`rounded-xl overflow-hidden ${isOwn ? 'bg-white/10' : 'bg-gradient-to-r from-[#4A5D4E]/10 to-[#6B8E23]/5 border border-[#4A5D4E]/20'}`} style={{ minWidth: 240 }}>
                <div className="px-4 py-3 flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${isOwn ? 'bg-white/20' : 'bg-[#4A5D4E]/15'}`}>
                    <Video className={`w-5 h-5 ${isOwn ? 'text-white' : 'text-[#4A5D4E]'}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium ${isOwn ? 'text-white' : 'text-[#1C1F1D]'}`}>Videoanruf</p>
                    <p className={`text-[10px] ${isOwn ? 'text-white/60' : 'text-[#9CA3AF]'}`}>
                      {msg.sender_name} hat einen Anruf gestartet
                    </p>
                  </div>
                </div>
                <div className="px-4 pb-3">
                  <button
                    onClick={() => onJoinMeeting(msg.meeting_id)}
                    className={`w-full py-2 rounded-lg text-xs font-medium transition-colors ${isOwn ? 'bg-white/20 hover:bg-white/30 text-white' : 'bg-[#4A5D4E] hover:bg-[#3E4E42] text-white'}`}
                    data-testid={`join-call-${msg.message_id}`}
                  >
                    Jetzt beitreten
                  </button>
                </div>
              </div>
            )
          ) : msg.type === 'file' ? (
            <FilePreview msg={msg} isOwn={isOwn} />
          ) : (
            <div className="text-sm whitespace-pre-wrap break-words" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
          )}
          <div className={`flex items-center gap-1.5 mt-0.5 ${isOwn ? 'justify-end' : ''}`}>
            <span className={`text-[9px] ${isOwn ? 'text-white/50' : 'text-[#9CA3AF]'}`}>{formatTime(msg.created_at)}</span>
            {msg.edited && <span className={`text-[9px] ${isOwn ? 'text-white/40' : 'text-[#9CA3AF]'}`}>(bearbeitet)</span>}
            {msg.e2e_encrypted && <Lock className={`w-2.5 h-2.5 ${isOwn ? 'text-white/40' : 'text-[#6B8E23]/60'}`} />}
            {/* iter 179 — read-receipt indicator on own messages.
                 single check = delivered; double check = read by at least 1 peer */}
            {isOwn && (
              <span
                className={`inline-flex items-center gap-0.5 text-[9px] ${anyRead ? 'text-[#8FC993]' : 'text-white/40'}`}
                title={anyRead ? (activeConv?.type === 'group' ? `Gelesen von ${readByCount}` : 'Gelesen') : 'Zugestellt'}
                data-testid={`msg-${msg.message_id}-read-receipt`}
              >
                <Check className="w-3 h-3" />
                {anyRead && <Check className="w-3 h-3 -ml-1.5" />}
              </span>
            )}
            {(msg.thread_count || 0) > 0 && (
              <button onClick={() => onOpenThread(msg.message_id)} className={`text-[9px] flex items-center gap-0.5 ${isOwn ? 'text-white/60 hover:text-white/80' : 'text-[#4A5D4E] hover:text-[#3E4E42]'}`}>
                <CornerDownRight className="w-3 h-3" /> {msg.thread_count} Antworten
              </button>
            )}
          </div>
        </div>
        {/* Reactions */}
        {msg.reactions?.length > 0 && (
          <div className="flex gap-0.5 mt-0.5 flex-wrap">
            {Object.entries(msg.reactions.reduce((acc, r) => { acc[r.emoji] = (acc[r.emoji] || 0) + 1; return acc; }, {})).map(([emoji, count]) => (
              <button
                key={emoji}
                onClick={() => toggleReaction(msg.message_id, emoji)}
                className="text-[11px] bg-white border border-[#E2E4E0] rounded-full px-1.5 py-0.5 hover:bg-[#F3F4F1]"
              >
                {emoji} {count}
              </button>
            ))}
          </div>
        )}
        {/* Hover actions */}
        <div className={`absolute ${isOwn ? '-left-1' : '-right-1'} -top-3 hidden group-hover:flex items-center gap-0.5 bg-white border border-[#E2E4E0] rounded-lg shadow-sm px-1 py-0.5 z-10`}>
          <button onClick={() => onReply(msg)} className="p-1 rounded hover:bg-[#E8EAE6]" title="Antworten"><Reply className="w-3.5 h-3.5 text-[#6B7280]" /></button>
          <button onClick={() => toggleShowEmoji(msg.message_id)} className="p-1 rounded hover:bg-[#E8EAE6]" title="Reaktion"><Smile className="w-3.5 h-3.5 text-[#6B7280]" /></button>
          {(msg.thread_count || 0) > 0 && <button onClick={() => onOpenThread(msg.message_id)} className="p-1 rounded hover:bg-[#E8EAE6]" title="Thread"><CornerDownRight className="w-3.5 h-3.5 text-[#6B7280]" /></button>}
          {isOwn && <button data-testid={`msg-edit-${msg.message_id}`} onClick={() => beginEdit(msg)} className="p-1 rounded hover:bg-[#E8EAE6]" title="Bearbeiten"><Edit2 className="w-3.5 h-3.5 text-[#6B7280]" /></button>}
          {isOwn && <button data-testid={`msg-delete-${msg.message_id}`} onClick={() => deleteMessage(msg.message_id)} className="p-1 rounded hover:bg-[#C87967]/10" title="Löschen"><Trash2 className="w-3.5 h-3.5 text-[#C87967]" /></button>}
        </div>
        {/* Emoji picker */}
        {showEmojiFor === msg.message_id && (
          <div className={`absolute ${isOwn ? 'right-0' : 'left-0'} -top-12 bg-white border border-[#E2E4E0] rounded-xl shadow-lg p-1.5 flex gap-0.5 z-20`}>
            {EMOJIS.map(e => (
              <button key={e} onClick={() => toggleReaction(msg.message_id, e)} className="text-lg hover:scale-125 transition-transform px-0.5">{e}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
