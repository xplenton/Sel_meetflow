import { Badge } from '../ui/badge';
import { Calendar, MessageSquare, Paperclip, ListChecks } from 'lucide-react';
import { PRIORITY_BADGE as PRIO_COLOR, STATUS_COLOR } from './taskConstants';

export default function TaskList({ tasks, statusLabels, priorityLabels, onOpen, users }) {
  const userMap = users.reduce((a, u) => { a[u.user_id] = u; return a; }, {});

  if (!tasks.length) {
    return <div className="text-center py-12 text-sm text-[#9CA3AF]">Keine Aufgaben gefunden.</div>;
  }
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid="task-list">
      <table className="w-full text-sm">
        <thead className="bg-[#F3F4F1] border-b border-[#E2E4E0]">
          <tr>
            <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-bold text-[#6B7280]">Titel</th>
            <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-bold text-[#6B7280] hidden sm:table-cell">Status</th>
            <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-bold text-[#6B7280] hidden sm:table-cell">Prio</th>
            <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-bold text-[#6B7280] hidden md:table-cell">Faellig</th>
            <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-bold text-[#6B7280] hidden lg:table-cell">Verantw.</th>
            <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-bold text-[#6B7280]"></th>
          </tr>
        </thead>
        <tbody>
          {tasks.map(t => {
            const due = t.due_date ? new Date(t.due_date) : null;
            const overdue = due && due < new Date() && t.status !== 'done';
            return (
              <tr key={t.task_id}
                data-testid={`task-row-${t.task_id}`}
                onClick={() => onOpen(t.task_id)}
                className="border-b border-[#E2E4E0] hover:bg-[#F9F9F8] cursor-pointer">
                <td className="px-3 py-3">
                  <div className="font-medium text-[#1C1F1D]">{t.title}</div>
                  <div className="flex items-center gap-2 mt-1 sm:hidden">
                    <Badge className={`text-[9px] ${STATUS_COLOR[t.status] || ''}`}>{statusLabels[t.status]}</Badge>
                    <Badge className={`text-[9px] ${PRIO_COLOR[t.priority]}`}>{priorityLabels[t.priority]}</Badge>
                  </div>
                </td>
                <td className="px-3 py-3 hidden sm:table-cell"><Badge className={`text-[10px] ${STATUS_COLOR[t.status] || ''}`}>{statusLabels[t.status]}</Badge></td>
                <td className="px-3 py-3 hidden sm:table-cell"><Badge className={`text-[10px] ${PRIO_COLOR[t.priority]}`}>{priorityLabels[t.priority]}</Badge></td>
                <td className={`px-3 py-3 text-xs hidden md:table-cell ${overdue ? 'text-[#C87967]' : 'text-[#6B7280]'}`}>
                  {due ? due.toLocaleDateString('de-DE') : '–'}
                </td>
                <td className="px-3 py-3 hidden lg:table-cell text-xs text-[#6B7280]" data-testid={`task-row-assignees-${t.task_id}`}>
                  {(t.assignee_ids || []).slice(0, 2).map(uid => {
                    const u = userMap[uid];
                    return u?.name || u?.email || 'Unbekannt';
                  }).join(', ')}
                  {t.assignee_ids?.length > 2 && ` +${t.assignee_ids.length - 2}`}
                  {(!t.assignee_ids || t.assignee_ids.length === 0) && <span className="text-[#9CA3AF]">—</span>}
                </td>
                <td className="px-3 py-3 text-[10px] text-[#9CA3AF]">
                  <div className="flex items-center gap-2">
                    {t.subtask_count > 0 && <span className="flex items-center gap-0.5"><ListChecks className="w-3 h-3" />{t.subtask_done}/{t.subtask_count}</span>}
                    {t.comment_count > 0 && <span className="flex items-center gap-0.5"><MessageSquare className="w-3 h-3" />{t.comment_count}</span>}
                    {t.attachment_count > 0 && <span className="flex items-center gap-0.5"><Paperclip className="w-3 h-3" />{t.attachment_count}</span>}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
