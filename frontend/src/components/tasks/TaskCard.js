import { Badge } from '../ui/badge';
import { Calendar, MessageSquare, Paperclip, ListChecks } from 'lucide-react';

const PRIORITY_COLORS = {
  urgent: 'bg-[#C87967] text-white',
  high: 'bg-[#D4A373] text-white',
  normal: 'bg-[#E2E4E0] text-[#4A5D4E]',
  low: 'bg-[#F3F4F1] text-[#9CA3AF]',
};

/**
 * Build readable initials from a display name. Falls back to "?".
 * Examples: "Anna Schmidt" → "AS", "anna.schmidt@example.com" → "AS",
 *           "" → "?", "Müller" → "MÜ".
 */
function initialsFromName(name) {
  if (!name) return '?';
  const cleaned = String(name).split('@')[0].replace(/[._-]+/g, ' ').trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function TaskCard({ task, onOpen, userMap = {} }) {
  const due = task.due_date ? new Date(task.due_date) : null;
  const overdue = due && due < new Date() && task.status !== 'done';
  return (
    <button data-testid={`task-card-${task.task_id}`}
      onClick={() => onOpen(task.task_id)}
      className="w-full text-left bg-white border border-[#E2E4E0] rounded-xl p-3 hover:border-[#4A5D4E]/40 hover:shadow-sm transition-all">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-medium text-[#1C1F1D] line-clamp-2">{task.title}</h4>
        <Badge className={`shrink-0 text-[10px] uppercase tracking-wider ${PRIORITY_COLORS[task.priority] || PRIORITY_COLORS.normal}`}>
          {task.priority}
        </Badge>
      </div>
      {task.description && <p className="text-xs text-[#6B7280] mt-1 line-clamp-2">{task.description}</p>}
      <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-[11px] text-[#9CA3AF] mt-2">
        {due && (
          <span className={`flex items-center gap-1 ${overdue ? 'text-[#C87967]' : ''}`}>
            <Calendar className="w-3 h-3" />
            {due.toLocaleDateString('de-DE', { day: '2-digit', month: 'short' })}
          </span>
        )}
        {task.subtask_count > 0 && <span className="flex items-center gap-1"><ListChecks className="w-3 h-3" />{task.subtask_done}/{task.subtask_count}</span>}
        {task.comment_count > 0 && <span className="flex items-center gap-1"><MessageSquare className="w-3 h-3" />{task.comment_count}</span>}
        {task.attachment_count > 0 && <span className="flex items-center gap-1"><Paperclip className="w-3 h-3" />{task.attachment_count}</span>}
      </div>
      {task.assignee_ids?.length > 0 && (
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <div className="flex -space-x-1">
            {task.assignee_ids.slice(0, 3).map(uid => {
              const u = userMap[uid];
              const label = u?.name || u?.email || 'Unbekannt';
              return (
                <div key={uid}
                  className="w-6 h-6 rounded-full bg-[#4A5D4E] text-white text-[9px] font-medium flex items-center justify-center border border-white"
                  title={label}
                  data-testid={`task-assignee-avatar-${uid}`}>
                  {initialsFromName(u?.name || u?.email)}
                </div>
              );
            })}
            {task.assignee_ids.length > 3 && (
              <div className="w-6 h-6 rounded-full bg-[#E2E4E0] text-[#4A5D4E] text-[9px] font-medium flex items-center justify-center border border-white">
                +{task.assignee_ids.length - 3}
              </div>
            )}
          </div>
          <span className="text-[11px] text-[#6B7280] truncate max-w-[180px]" data-testid="task-assignee-name">
            {(() => {
              const first = userMap[task.assignee_ids[0]];
              const firstLabel = first?.name || first?.email || 'Unbekannt';
              return task.assignee_ids.length === 1
                ? firstLabel
                : `${firstLabel} +${task.assignee_ids.length - 1}`;
            })()}
          </span>
        </div>
      )}
    </button>
  );
}
