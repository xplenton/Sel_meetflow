import { Label } from '../ui/label';
import { Check } from 'lucide-react';

/**
 * Gruppen-Audience-Selector (Pill-Toggle).
 * Extrahiert aus TaskDetailDialog (iter 236).
 */
export default function TaskGroupsBlock({ groups, groupIds, onPatch }) {
  if (!groups?.length) return null;
  const ids = groupIds || [];
  return (
    <div>
      <Label className="text-[10px] uppercase font-bold text-[#6B7280] block mb-1">Gruppen</Label>
      <div className="flex flex-wrap gap-1" data-testid="task-groups">
        {groups.map(g => {
          const active = ids.includes(g.group_id);
          return (
            <button
              key={g.group_id}
              type="button"
              onClick={() => onPatch({
                group_ids: active
                  ? ids.filter(x => x !== g.group_id)
                  : [...ids, g.group_id]
              })}
              data-testid={`task-group-toggle-${g.group_id}`}
              className={`flex items-center gap-1 text-[11px] rounded-full px-2.5 py-0.5 transition-colors ${
                active
                  ? 'bg-[#D4A373] text-white'
                  : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#E2E4E0]'
              }`}
            >
              {active && <Check className="w-3 h-3" />}
              {g.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
