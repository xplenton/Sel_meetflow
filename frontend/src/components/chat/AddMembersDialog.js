import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Input } from '../ui/input';
import { Search, UserPlus } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

/**
 * "Mitglied hinzufügen"-Modal for group chats. Lists eligible users (excludes
 * already-members), supports client-side search filter, calls
 * POST /chat/conversations/{id}/members and refreshes the parent state.
 *
 * Extracted from ChatPage.js (iter 385).
 */
export default function AddMembersDialog({
  open, onOpenChange,
  activeConv,
  chatUsers,
  setActiveConv,
  fetchConversations,
  t,
}) {
  const filterMemberList = (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('[data-member-item]').forEach(el => {
      el.style.display = !q || el.dataset.memberItem.toLowerCase().includes(q) ? '' : 'none';
    });
  };

  const eligible = chatUsers.filter(u => !activeConv?.members?.find(m => m.user_id === u.user_id));

  const addUser = async (u) => {
    try {
      await api.post(`/chat/conversations/${activeConv.conversation_id}/members`, { user_id: u.user_id });
      toast.success(`${u.name} hinzugefuegt`);
      const { data: conv } = await api.get(`/chat/conversations/${activeConv.conversation_id}`);
      setActiveConv(conv);
      fetchConversations();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>{t('addMember')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
            <Input
              placeholder="Nutzer suchen..."
              className="pl-8 h-8 text-xs border-[#E2E4E0] rounded-lg"
              data-testid="add-member-search"
              onChange={filterMemberList}
            />
          </div>
          <div className="max-h-60 overflow-y-auto space-y-1">
            {eligible.length === 0 ? (
              <p className="text-center text-xs text-[#9CA3AF] py-4">{t('noMoreUsers')}</p>
            ) : eligible.map(u => (
              <button
                key={u.user_id}
                data-member-item={`${u.name} ${u.email}`}
                onClick={() => addUser(u)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#F3F4F1] transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs font-medium text-[#4A5D4E]">
                  {u.avatar ? <img src={u.avatar} alt="" className="w-8 h-8 rounded-full object-cover" /> : (u.name?.[0]?.toUpperCase() || '?')}
                </div>
                <div className="flex-1 min-w-0 text-left">
                  <span className="text-sm font-medium text-[#1C1F1D] block truncate">{u.name}</span>
                  <span className="text-[10px] text-[#9CA3AF] block truncate">{u.email}</span>
                </div>
                <UserPlus className="w-4 h-4 text-[#4A5D4E] flex-shrink-0" />
              </button>
            ))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
