import { useState } from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Check, Plus, Trash2 } from 'lucide-react';

/**
 * Checkliste / Unteraufgaben — Toggle + Add + Remove.
 * Extrahiert aus TaskDetailDialog (iter 236).
 */
export default function TaskChecklistBlock({ checklist, onPatch }) {
  const [draft, setDraft] = useState('');
  const items = checklist || [];

  const addItem = () => {
    const text = draft.trim();
    if (!text) return;
    const newItem = { id: `cl_${Date.now()}`, text, done: false, order: items.length };
    onPatch({ checklist: [...items, newItem] });
    setDraft('');
  };
  const toggleItem = (id) => {
    onPatch({ checklist: items.map(c => c.id === id ? { ...c, done: !c.done } : c) });
  };
  const removeItem = (id) => {
    onPatch({ checklist: items.filter(c => c.id !== id) });
  };

  return (
    <div>
      <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Checkliste / Unteraufgaben</Label>
      <div className="space-y-1 mt-1">
        {items.map(c => (
          <div key={c.id} data-testid={`checklist-${c.id}`} className="flex items-center gap-2 p-1.5 bg-[#F9F9F8] rounded-lg">
            <button
              onClick={() => toggleItem(c.id)}
              className={`w-4 h-4 rounded border ${c.done ? 'bg-[#4A5D4E] border-[#4A5D4E]' : 'border-[#9CA3AF]'} flex items-center justify-center`}
            >
              {c.done && <Check className="w-3 h-3 text-white" />}
            </button>
            <span className={`flex-1 text-sm ${c.done ? 'line-through text-[#9CA3AF]' : 'text-[#1C1F1D]'}`}>{c.text}</span>
            <button onClick={() => removeItem(c.id)} className="text-[#9CA3AF] hover:text-[#C87967]">
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
        <div className="flex gap-1.5">
          <Input
            data-testid="task-checklist-input"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addItem(); } }}
            placeholder="Neuer Punkt + Enter"
            className="h-8 border-[#E2E4E0] rounded-lg text-xs"
          />
          <Button
            data-testid="task-add-checklist"
            size="sm"
            variant="outline"
            onClick={addItem}
            className="h-8 text-xs px-2"
          >
            <Plus className="w-3 h-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}
