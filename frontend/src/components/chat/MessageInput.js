import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Mic, MicOff, Paperclip, Reply, Send, X } from 'lucide-react';

/**
 * Composer at the bottom of the chat area — text input + reply preview +
 * file upload + voice recording + GIF picker. Pure presentational, all
 * state lives in ChatPage.
 *
 * Extracted from ChatPage.js (iter 384) to keep the orchestrator file
 * under the 700-line guideline.
 */
export default function MessageInput({
  input, setInput,
  sendMessage,
  handleTyping,
  recording, startRecording, stopRecording,
  replyTo, clearReplyTo,
  fileInputRef, handleFileUpload,
  gifOpen, setGifOpen,
  gifQuery, gifResults,
  searchGifs, sendGif,
  t,
}) {
  return (
    <div className="px-3 md:px-4 py-2 md:py-3 bg-white border-t border-[#E2E4E0] relative z-50">
      {/* Reply preview bar */}
      {replyTo && (
        <div className="flex items-center gap-2 mb-2 px-3 py-2 bg-[#F3F4F1] rounded-lg border-l-3 border-[#4A5D4E]">
          <Reply className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="text-[10px] font-medium text-[#4A5D4E]">{replyTo.sender_name}</span>
            <p className="text-xs text-[#6B7280] truncate">{replyTo.content}</p>
          </div>
          <button onClick={clearReplyTo} className="text-[#9CA3AF] hover:text-[#6B7280]" data-testid="reply-cancel-btn">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      <div className="flex items-center gap-2">
        <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="p-2 rounded-lg hover:bg-[#F3F4F1] text-[#6B7280] flex-shrink-0"
          data-testid="chat-upload-btn"
        >
          <Paperclip className="w-4 h-4" />
        </button>
        <button
          onClick={recording ? stopRecording : startRecording}
          className={`p-2 rounded-lg hover:bg-[#F3F4F1] flex-shrink-0 ${recording ? 'text-[#C87967] animate-pulse' : 'text-[#6B7280]'}`}
          title={recording ? 'Aufnahme stoppen' : 'Sprachnachricht'}
          data-testid="chat-voice-btn"
        >
          {recording ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
        </button>
        <div className="relative">
          <button
            onClick={() => setGifOpen(!gifOpen)}
            className="p-2 rounded-lg hover:bg-[#F3F4F1] text-[#6B7280]"
            title="GIF"
            data-testid="chat-gif-btn"
          >
            <span className="text-xs font-bold">GIF</span>
          </button>
          {gifOpen && (
            <div className="absolute bottom-12 left-0 bg-white border border-[#E2E4E0] rounded-xl shadow-xl w-72 z-20" data-testid="gif-picker">
              <div className="p-2 border-b border-[#E2E4E0]">
                <Input
                  value={gifQuery}
                  onChange={e => searchGifs(e.target.value)}
                  placeholder="GIF suchen..."
                  className="h-7 text-xs border-[#E2E4E0] rounded-lg"
                  autoFocus
                  data-testid="gif-search-input"
                />
              </div>
              <div className="grid grid-cols-2 gap-1 p-2 max-h-56 overflow-y-auto">
                {gifResults.map(g => (
                  <button key={g.id} onClick={() => sendGif(g.url)} className="rounded-lg overflow-hidden hover:opacity-80 transition-opacity">
                    <img src={g.preview || g.url} alt={g.title} className="w-full h-20 object-cover" loading="lazy" />
                  </button>
                ))}
                {gifQuery.length >= 2 && gifResults.length === 0 && (
                  <p className="col-span-2 text-center text-xs text-[#9CA3AF] py-4">{t('noGifsFound')}</p>
                )}
                {gifQuery.length < 2 && (
                  <p className="col-span-2 text-center text-xs text-[#9CA3AF] py-4">{t('enterSearchTerm')}</p>
                )}
              </div>
            </div>
          )}
        </div>
        <Input
          value={input}
          onChange={e => { setInput(e.target.value); handleTyping(); }}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), sendMessage())}
          placeholder={recording ? 'Aufnahme...' : 'Nachricht...'}
          spellCheck="true"
          lang="de"
          className="flex-1 border-[#E2E4E0] rounded-xl text-sm h-9"
          data-testid="chat-input"
          disabled={recording}
        />
        <Button
          onClick={sendMessage}
          disabled={!input.trim() || recording}
          className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl h-9 w-9 p-0 relative z-[10001] flex-shrink-0"
          data-testid="chat-send-btn"
        >
          <Send className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
