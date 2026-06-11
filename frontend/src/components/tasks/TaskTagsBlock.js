import { useState } from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { X } from 'lucide-react';

/**
 * Tag-Eingabe mit Enter-to-Add + Komma-Trenner. Eigener interner State für
 * das Eingabefeld; Tag-Liste lebt am Parent (Tasks state).
 * Extrahiert aus TaskDetailDialog (iter 236).
 */
export default function TaskTagsBlock({ tags, onPatch }) {
  const [tagInput, setTagInput] = useState('');
  const list = tags || [];

  const commit = () => {
    const tg = tagInput.trim().replace(/^#/, '');
    if (tg && !list.includes(tg)) {
      onPatch({ tags: [...list, tg] });
    }
    setTagInput('');
  };

  return (
    <div>
      <Label className="text-[10px] uppercase font-bold text-[#6B7280] block mb-1">Tags</Label>
      <div className="flex flex-wrap items-center gap-1.5" data-testid="task-tags-row">
        {list.map(tg => (
          <span key={tg} className="text-[11px] px-2 py-0.5 rounded-full bg-[#F3F4F1] text-[#6B7280] flex items-center gap-1">
            #{tg}
            <button
              data-testid={`task-tag-remove-${tg}`}
              onClick={() => onPatch({ tags: list.filter(x => x !== tg) })}
              className="hover:text-[#C87967]"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <Input
          data-testid="task-tag-input"
          value={tagInput}
          onChange={e => setTagInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault();
              commit();
            }
          }}
          placeholder="Tag + Enter"
          className="h-7 w-32 border-[#E2E4E0] rounded-lg text-xs"
        />
      </div>
    </div>
  );
}
