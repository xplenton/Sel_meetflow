import { Badge } from '../ui/badge';
import { Label } from '../ui/label';
import { X } from 'lucide-react';

/**
 * Verantwortliche-Auswahl mit Self-Assign-Option.
 * Extrahiert aus TaskDetailDialog (iter 236).
 */
export default function TaskAssigneesBlock({ assigneeIds, usersForAssignment, userMap, currentUser, onPatch }) {
  const ids = assigneeIds || [];
  return (
    <div>
      <Label className="text-[10px] uppercase font-bold text-[#6B7280] block mb-1">
        Verantwortlich (mehrere möglich)
      </Label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {ids.map(uid => (
          <Badge key={uid} className="bg-[#4A5D4E] text-white">
            {userMap[uid]?.name || uid.substring(0, 8)}
            <button
              data-testid={`unassign-${uid}`}
              onClick={() => onPatch({ assignee_ids: ids.filter(x => x !== uid) })}
              className="ml-1.5 hover:bg-white/20 rounded-full"
            >
              <X className="w-3 h-3" />
            </button>
          </Badge>
        ))}
      </div>
      <select
        data-testid="task-add-assignee"
        value=""
        onChange={(e) => {
          if (e.target.value && !ids.includes(e.target.value)) {
            onPatch({ assignee_ids: [...ids, e.target.value] });
          }
        }}
        className="w-full h-9 px-2 text-sm border border-[#E2E4E0] rounded-lg bg-white"
      >
        <option value="">+ Verantwortlichen hinzufügen</option>
        {usersForAssignment.filter(u => !ids.includes(u.user_id)).map(u => (
          <option
            key={u.user_id}
            value={u.user_id}
            data-testid={u.user_id === currentUser?.user_id ? 'assign-self-option' : `assign-${u.user_id}`}
          >
            {u.user_id === currentUser?.user_id ? `Mir zuweisen (${u.name || u.email})` : (u.name || u.email)}
          </option>
        ))}
      </select>
    </div>
  );
}
