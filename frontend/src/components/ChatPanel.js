import { useState, useRef, useCallback } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { ScrollArea } from '../components/ui/scroll-area';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { Send, X } from 'lucide-react';

export default function ChatPanel({ messages, onSend, onClose, userName }) {
  const { t } = useLanguage();
  const [text, setText] = useState('');
  const scrollRef = useRef(null);

  const handleSend = useCallback(() => {
    if (!text.trim()) return;
    onSend(text.trim());
    setText('');
  }, [text, onSend]);

  const handleKey = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  return (
    <div className="w-full sm:w-80 fixed inset-0 sm:static sm:inset-auto bg-white border-l border-[#E2E4E0] flex flex-col h-full z-40 sm:z-auto" data-testid="chat-panel">
      <div className="flex items-center justify-between p-4 border-b border-[#E2E4E0]">
        <h3 className="text-sm font-medium text-[#1C1F1D]">{t('chat')}</h3>
        <button onClick={onClose} data-testid="close-chat-button" className="p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF]"><X className="w-4 h-4" /></button>
      </div>

      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <div className="space-y-3">
          {messages.map((msg, i) => (
            <div key={msg.message_id || i} className="animate-fade-in" data-testid={`chat-message-${i}`}>
              {msg.message_type === 'host' ? (
                <div className="bg-[#4A5D4E]/10 border border-[#4A5D4E]/20 rounded-lg p-2 my-1">
                  <span className="text-[10px] font-bold text-[#4A5D4E] block mb-0.5">{msg.user_name}</span>
                  <p className="text-xs text-[#1C1F1D]">{msg.message}</p>
                </div>
              ) : msg.message_type === 'system' ? (
                <p className="text-[10px] text-[#9CA3AF] text-center py-1 italic">{msg.message}</p>
              ) : (
                <>
                  <div className="flex items-baseline gap-2 mb-0.5">
                    <span className="text-xs font-medium text-[#1C1F1D]">{msg.user_name || msg.sender}</span>
                    <span className="text-[10px] text-[#9CA3AF]">{new Date(msg.created_at || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  <p className="text-sm text-[#4B5563] leading-relaxed">{msg.message}</p>
                </>
              )}
            </div>
          ))}
          {messages.length === 0 && <p className="text-center text-xs text-[#9CA3AF] py-8">{t('typeMessage')}</p>}
        </div>
      </ScrollArea>

      {/* Bottom padding shifts input above the fixed "Made with Emergent"
          badge (bottom-right, ~56px tall) so the send button is clickable
          on desktop without a z-index workaround. iter 135 UX fix. */}
      <div className="p-3 border-t border-[#E2E4E0] pb-16 sm:pb-20">
        <div className="flex gap-2">
          <Input data-testid="chat-message-input" value={text} onChange={e => setText(e.target.value)} onKeyDown={handleKey}
            placeholder={t('typeMessage')} className="border-[#E2E4E0] rounded-lg text-sm h-9 flex-1" />
          <Button onClick={handleSend} size="sm" data-testid="send-chat-button"
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg h-9 w-9 p-0">
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
