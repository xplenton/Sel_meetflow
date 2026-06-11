import { forwardRef } from 'react';
import MessageBubble from './MessageBubble';

/**
 * Scrollable container for messages + date separators + system events +
 * message-search results. Wraps the MessageBubble component for each
 * non-system message. The end-ref is forwarded so the parent can do
 * scrollIntoView on new messages.
 *
 * Extracted from ChatPage.js (iter 384) to keep the orchestrator under
 * the 700-line guideline.
 */
const MessageList = forwardRef(function MessageList({
  messages,
  msgSearchResults,
  clearMsgSearch,
  // shared bubble props
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
  formatDate,
  t,
}, endRef) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 pb-16 space-y-1" data-testid="chat-messages">
      {msgSearchResults.length > 0 ? (
        <div className="space-y-2 mb-4">
          <p className="text-xs text-[#6B7280] font-medium">{msgSearchResults.length} Ergebnisse</p>
          {msgSearchResults.map(m => (
            <div key={m.message_id} className="bg-white rounded-lg p-3 border border-[#E2E4E0]">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-medium text-[#1C1F1D]">{m.sender_name}</span>
                <span className="text-[10px] text-[#9CA3AF]">{formatDate(m.created_at)} {formatTime(m.created_at)}</span>
              </div>
              <p className="text-sm text-[#4B5563]">{m.content}</p>
            </div>
          ))}
          <button onClick={clearMsgSearch} className="text-xs text-[#4A5D4E]">{t('closeResults')}</button>
        </div>
      ) : null}
      {messages.map((msg, i) => {
        const isOwn = msg.sender_id === user?.user_id;
        const isSystem = msg.type === 'system';
        const prev = messages[i - 1];
        const showDate = i === 0 || formatDate(prev?.created_at) !== formatDate(msg.created_at);
        const showSenderName = i === 0 || prev?.sender_id !== msg.sender_id;
        return (
          <div key={msg.message_id}>
            {showDate && (
              <div className="text-center my-3">
                <span className="text-[10px] bg-[#E8EAE6] text-[#6B7280] px-3 py-1 rounded-full">{formatDate(msg.created_at)}</span>
              </div>
            )}
            {isSystem ? (
              <div className="text-center my-2">
                <span className="text-[10px] text-[#9CA3AF]">{msg.content}</span>
              </div>
            ) : (
              <MessageBubble
                msg={msg}
                isOwn={isOwn}
                showSenderName={showSenderName}
                activeConv={activeConv}
                user={user}
                language={language}
                editingMsg={editingMsg}
                editContent={editContent}
                setEditContent={setEditContent}
                saveEdit={saveEdit}
                cancelEdit={cancelEdit}
                beginEdit={beginEdit}
                showEmojiFor={showEmojiFor}
                toggleShowEmoji={toggleShowEmoji}
                toggleReaction={toggleReaction}
                deleteMessage={deleteMessage}
                onReply={onReply}
                onOpenThread={onOpenThread}
                onStartCall={onStartCall}
                onJoinMeeting={onJoinMeeting}
                readStatus={readStatus}
                formatTime={formatTime}
                t={t}
              />
            )}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
});

export default MessageList;
