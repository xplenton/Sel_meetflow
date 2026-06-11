import {
  TASK_STATUS_LABELS as STATUS_LABELS,
  TASK_PRIORITY_LABELS as PRIORITY_LABELS,
} from './taskConstants';

// Translate task_history actions into German labels.
function labelAction(h) {
  const a = h.action || '';
  if (a === 'created') return 'hat die Aufgabe erstellt';
  if (a.startsWith('set:')) {
    const key = a.slice(4);
    const map = {
      title: 'Titel', description: 'Beschreibung',
      status: 'Status', priority: 'Priorität',
      due_date: 'Fälligkeit', assignee_ids: 'Zuständigkeit',
      group_ids: 'Gruppen', checklist: 'Checkliste',
      tags: 'Tags', archived: 'Archivierung',
    };
    const label = map[key] || key;
    if (key === 'status') {
      return `hat Status auf "${STATUS_LABELS[h.new] || h.new}" geändert`;
    }
    if (key === 'priority') {
      return `hat Priorität auf "${PRIORITY_LABELS[h.new] || h.new}" geändert`;
    }
    return `hat ${label} aktualisiert`;
  }
  return a;
}

/**
 * TaskActivityTab — chronological history of the task: who changed what
 * and when. Extracted from TaskDetailDialog (iter 216).
 */
export default function TaskActivityTab({ history }) {
  return (
    <div data-testid="task-activity-section">
      {history.length === 0 ? (
        <p className="text-xs text-[#9CA3AF] text-center py-4">Noch keine Aktivitäten.</p>
      ) : (
        <div className="space-y-1.5">
          {history.map(h => (
            <div key={h.history_id} data-testid={`activity-${h.history_id}`}
              className="flex items-start gap-2 p-2 bg-[#F9F9F8] rounded-lg">
              <div className="w-7 h-7 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-[10px] font-bold text-[#4A5D4E] flex-shrink-0">
                {(h.actor_name || '?').slice(0, 1).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-[#1C1F1D]">
                  <span className="font-medium">{h.actor_name}</span>{' '}
                  <span className="text-[#6B7280]">{labelAction(h)}</span>
                </p>
                <p className="text-[10px] text-[#9CA3AF]">{new Date(h.ts).toLocaleString('de-DE')}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
