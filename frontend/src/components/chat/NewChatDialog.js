import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Check, Search, X } from 'lucide-react';

/**
 * "Neuer Chat" Modal — pick name + members and create a group conversation.
 * Extracted from ChatPage.js (iter 385).
 */
export default function NewChatDialog({
  open, onOpenChange,
  newChatName, setNewChatName,
  newChatMembers, setNewChatMembers,
  chatUsers,
  createConversation,
  t,
}) {
  const filterUserList = (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('[data-group-user]').forEach(el => {
      el.style.display = !q || el.dataset.groupUser.toLowerCase().includes(q) ? '' : 'none';
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{t('createGroup')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <Input
            value={newChatName}
            onChange={e => setNewChatName(e.target.value)}
            placeholder={t('groupName')}
            className="border-[#E2E4E0] rounded-xl"
            data-testid="new-chat-name"
          />
          <div>
            <p className="text-xs font-medium text-[#6B7280] mb-2">{t('pickParticipants')}</p>
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
              <Input
                placeholder="Nutzer suchen..."
                className="pl-8 h-8 text-xs border-[#E2E4E0] rounded-lg"
                data-testid="new-group-search"
                onChange={filterUserList}
              />
            </div>
            {newChatMembers.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {newChatMembers.map(id => {
                  const u = chatUsers.find(uu => uu.user_id === id);
                  return u ? (
                    <span key={id} className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#4A5D4E]/10 rounded-full text-[11px] text-[#4A5D4E]">
                      {u.name}
                      <button onClick={() => setNewChatMembers(prev => prev.filter(i => i !== id))}>
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ) : null;
                })}
              </div>
            )}
            <div className="max-h-48 overflow-y-auto space-y-1 border border-[#E2E4E0] rounded-xl p-2">
              {chatUsers.map(u => {
                const selected = newChatMembers.includes(u.user_id);
                return (
                  <button
                    key={u.user_id}
                    data-group-user={`${u.name} ${u.email}`}
                    onClick={() => {
                      setNewChatMembers(prev => selected ? prev.filter(id => id !== u.user_id) : [...prev, u.user_id]);
                    }}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-colors ${selected ? 'bg-[#4A5D4E]/10' : 'hover:bg-[#F3F4F1]'}`}
                  >
                    <div className="w-7 h-7 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-[10px] font-medium text-[#4A5D4E]">
                      {u.name?.[0]?.toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-[#1C1F1D] truncate">{u.name}</p>
                      <p className="text-[10px] text-[#9CA3AF] truncate">{u.email}</p>
                    </div>
                    {selected && <Check className="w-4 h-4 text-[#4A5D4E]" />}
                  </button>
                );
              })}
            </div>
          </div>
          <Button
            onClick={createConversation}
            disabled={!newChatName.trim() || newChatMembers.length === 0}
            className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg"
            data-testid="create-chat-btn"
          >
            Gruppe erstellen
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
