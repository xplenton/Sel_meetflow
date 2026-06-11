/* TaskTemplateEditorDialog (iter 197)
   Vollständiger Editor für Aufgaben-Vorlagen. Ersetzt die Prompt-basierte
   "leere Vorlage"-Erstellung aus Iter 196. Felder: Name, Titel (Aufgaben-Titel
   bei Anwendung), Beschreibung, Priorität, Tags, Checkliste, Gruppen,
   Verantwortliche, Wiederholung. */
import { useEffect, useMemo, useState } from 'react';
import api from '../../lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { Plus, X, ListChecks, Loader2, Check, Trash2, History, Files } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../contexts/AuthContext';
import {
  TASK_PRIORITIES as PRIORITIES, TASK_PRIORITY_LABELS as PRIORITY_LABELS,
} from './taskConstants';

const EMPTY_DRAFT = {
  name: '', description: '', title: '', priority: 'normal',
  tags: [], checklist: [], group_ids: [], assignee_ids: [], recurrence: null,
};

export default function TaskTemplateEditorDialog({ open, template = null, users = [], onClose, onSaved }) {
  const isEdit = !!template;
  const { user: currentUser } = useAuth();
  // iter 206 — same self-assign rationale as TaskDetailDialog: include the
  // current user in the picker (chat/users excludes self by design).
  const usersForAssignment = (() => {
    if (!currentUser?.user_id) return users;
    if (users.some(u => u.user_id === currentUser.user_id)) return users;
    return [
      { user_id: currentUser.user_id, name: currentUser.name || currentUser.email, email: currentUser.email },
      ...users,
    ];
  })();
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [groups, setGroups] = useState([]);
  const [tagInput, setTagInput] = useState('');
  const [checklistInput, setChecklistInput] = useState('');
  const [userQuery, setUserQuery] = useState('');

  const userMap = useMemo(() => {
    const m = {};
    usersForAssignment.forEach(u => { m[u.user_id] = u; });
    return m;
  }, [usersForAssignment]);

  useEffect(() => {
    if (!open) return;
    if (template) {
      setDraft({
        name: template.name || '',
        description: template.description || '',
        title: template.title || '',
        priority: template.priority || 'normal',
        tags: template.tags || [],
        checklist: template.checklist || [],
        group_ids: template.group_ids || [],
        assignee_ids: template.assignee_ids || [],
        recurrence: template.recurrence || null,
      });
    } else {
      setDraft(EMPTY_DRAFT);
    }
    setTagInput(''); setChecklistInput(''); setUserQuery('');
  }, [open, template]);

  useEffect(() => {
    if (open) {
      api.get('/admin/groups').then(({ data }) => setGroups(data || [])).catch(() => setGroups([]));
    }
  }, [open]);

  const set = (changes) => setDraft(d => ({ ...d, ...changes }));

  const addTag = () => {
    const t = tagInput.trim().replace(/^#/, '');
    if (!t || draft.tags.includes(t)) { setTagInput(''); return; }
    set({ tags: [...draft.tags, t] });
    setTagInput('');
  };
  const addChecklistItem = () => {
    const text = checklistInput.trim();
    if (!text) return;
    set({ checklist: [...draft.checklist, { id: `cl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`, text, done: false, order: draft.checklist.length }] });
    setChecklistInput('');
  };
  const toggleAssignee = (uid) => set({
    assignee_ids: draft.assignee_ids.includes(uid)
      ? draft.assignee_ids.filter(x => x !== uid)
      : [...draft.assignee_ids, uid]
  });
  const toggleGroup = (gid) => set({
    group_ids: draft.group_ids.includes(gid)
      ? draft.group_ids.filter(x => x !== gid)
      : [...draft.group_ids, gid]
  });

  const filteredUsers = useMemo(() => {
    const q = userQuery.trim().toLowerCase();
    const base = usersForAssignment.filter(u => !draft.assignee_ids.includes(u.user_id));
    if (!q) return base.slice(0, 20);
    return base.filter(u =>
      (u.name || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q)
    ).slice(0, 20);
  }, [usersForAssignment, draft.assignee_ids, userQuery]);

  const submit = async () => {
    if (!draft.name.trim()) { toast.error('Name erforderlich'); return; }
    const payload = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      title: (draft.title || draft.name).trim(),
      priority: draft.priority,
      tags: draft.tags,
      checklist: draft.checklist,
      group_ids: draft.group_ids,
      assignee_ids: draft.assignee_ids,
      recurrence: draft.recurrence,
    };
    setBusy(true);
    try {
      let res;
      if (isEdit) {
        res = await api.put(`/task-templates/${template.template_id}`, payload);
        toast.success('Vorlage aktualisiert');
      } else {
        res = await api.post('/task-templates', payload);
        toast.success('Vorlage erstellt');
      }
      onSaved?.(res.data);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Speichern');
    } finally { setBusy(false); }
  };

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-[760px] max-h-[92vh] overflow-y-auto w-[calc(100vw-1rem)] p-4 sm:p-6"
        data-testid="task-template-editor-dialog">
        <DialogHeader>
          <DialogTitle data-testid="task-template-dialog-title" className="flex items-center gap-2">
            <Files className="w-4 h-4 text-[#4A5D4E]" />
            <span>Aufgaben-Vorlage</span>
            <Badge className="text-[10px] bg-[#D4A373]/10 text-[#D4A373] ml-1">{isEdit ? 'Bearbeiten' : 'Neu'}</Badge>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {/* Name (identifier) */}
          <div>
            <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Vorlagen-Name *</Label>
            <Input
              data-testid="tpl-name-input"
              value={draft.name}
              onChange={e => set({ name: e.target.value })}
              placeholder="z. B. Dienstübergabe Pflege"
              autoFocus={!isEdit}
              className="mt-1 border-[#E2E4E0] rounded-lg"
            />
            <p className="text-[10px] text-[#9CA3AF] mt-0.5">Erscheint in der Vorlagen-Auswahl.</p>
          </div>

          {/* Title */}
          <div>
            <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Titel der Aufgabe</Label>
            <Input
              data-testid="tpl-title-input"
              value={draft.title}
              onChange={e => set({ title: e.target.value })}
              placeholder="(Standard: Vorlagen-Name)"
              className="mt-1 border-[#E2E4E0] rounded-lg"
            />
          </div>

          {/* Description */}
          <div>
            <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Beschreibung</Label>
            <Textarea
              data-testid="tpl-description-input"
              value={draft.description}
              onChange={e => set({ description: e.target.value })}
              placeholder="Standard-Beschreibung, die bei jeder Anwendung vorbelegt wird ..."
              rows={3}
              className="mt-1 border-[#E2E4E0] rounded-lg text-sm"
            />
          </div>

          {/* Priority */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Priorität</Label>
              <select data-testid="tpl-priority-select" value={draft.priority}
                onChange={e => set({ priority: e.target.value })}
                className="mt-1 w-full h-9 px-2 text-sm border border-[#E2E4E0] rounded-lg bg-white">
                {PRIORITIES.map(p => <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>)}
              </select>
            </div>
          </div>

          {/* Audience — assignees */}
          <div>
            <Label className="text-[10px] uppercase font-bold text-[#6B7280] block mb-1">Standard-Verantwortliche</Label>
            {draft.assignee_ids.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {draft.assignee_ids.map(uid => (
                  <Badge key={uid} className="bg-[#4A5D4E] text-white pl-2 pr-1">
                    {userMap[uid]?.name || userMap[uid]?.email || uid.substring(0, 8)}
                    <button data-testid={`tpl-unassign-${uid}`}
                      onClick={() => toggleAssignee(uid)}
                      className="ml-1 hover:bg-white/20 rounded-full"><X className="w-3 h-3" /></button>
                  </Badge>
                ))}
              </div>
            )}
            <Input
              data-testid="tpl-user-search"
              value={userQuery} onChange={e => setUserQuery(e.target.value)}
              placeholder="Nutzer suchen ..."
              className="h-9 border-[#E2E4E0] rounded-lg text-sm"
            />
            {filteredUsers.length > 0 && (
              <div className="max-h-32 overflow-y-auto border border-[#E2E4E0] rounded-lg mt-1">
                {filteredUsers.map(u => (
                  <button key={u.user_id} type="button"
                    data-testid={`tpl-add-user-${u.user_id}`}
                    onClick={() => { toggleAssignee(u.user_id); setUserQuery(''); }}
                    className="w-full flex items-center gap-2 px-2 py-1.5 text-left hover:bg-[#F3F4F1]">
                    <div className="w-6 h-6 rounded-full bg-[#4A5D4E]/10 text-[#4A5D4E] flex items-center justify-center text-[9px] font-bold">
                      {(u.name || u.email || '?').slice(0, 1).toUpperCase()}
                    </div>
                    <span className="text-xs font-medium text-[#1C1F1D] truncate">{u.name || u.email}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Groups */}
          {groups.length > 0 && (
            <div>
              <Label className="text-[10px] uppercase font-bold text-[#6B7280] block mb-1">Gruppen</Label>
              <div className="flex flex-wrap gap-1" data-testid="tpl-groups">
                {groups.map(g => {
                  const active = draft.group_ids.includes(g.group_id);
                  return (
                    <button key={g.group_id} type="button"
                      onClick={() => toggleGroup(g.group_id)}
                      data-testid={`tpl-group-toggle-${g.group_id}`}
                      className={`flex items-center gap-1 text-[11px] rounded-full px-2.5 py-0.5 ${active ? 'bg-[#D4A373] text-white' : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#E2E4E0]'}`}>
                      {active && <Check className="w-3 h-3" />}{g.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Tags */}
          <div>
            <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Tags</Label>
            <div className="flex flex-wrap items-center gap-1.5 mt-1">
              {draft.tags.map(t => (
                <span key={t} className="text-[11px] px-2 py-0.5 rounded-full bg-[#F3F4F1] text-[#6B7280] flex items-center gap-1">
                  #{t}
                  <button onClick={() => set({ tags: draft.tags.filter(x => x !== t) })} className="hover:text-[#C87967]"><X className="w-3 h-3" /></button>
                </span>
              ))}
              <Input
                data-testid="tpl-tag-input"
                value={tagInput} onChange={e => setTagInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(); } }}
                placeholder="Tag + Enter"
                className="h-7 w-32 border-[#E2E4E0] rounded-lg text-xs"
              />
            </div>
          </div>

          {/* Checklist */}
          <div>
            <Label className="text-[10px] uppercase font-bold text-[#6B7280] flex items-center gap-1.5">
              <ListChecks className="w-3 h-3" /> Checkliste
            </Label>
            <div className="space-y-1 mt-1">
              {draft.checklist.map(c => (
                <div key={c.id} data-testid={`tpl-checklist-${c.id}`}
                  className="flex items-center gap-2 p-1.5 bg-[#F9F9F8] rounded-lg">
                  <span className="w-4 h-4 rounded border border-[#9CA3AF] flex-shrink-0" />
                  <span className="flex-1 text-sm text-[#1C1F1D]">{c.text}</span>
                  <button onClick={() => set({ checklist: draft.checklist.filter(x => x.id !== c.id) })}
                    className="text-[#9CA3AF] hover:text-[#C87967]"><Trash2 className="w-3 h-3" /></button>
                </div>
              ))}
              <div className="flex gap-1.5">
                <Input
                  data-testid="tpl-checklist-input"
                  value={checklistInput} onChange={e => setChecklistInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addChecklistItem(); } }}
                  placeholder="Neuer Schritt + Enter"
                  className="h-8 border-[#E2E4E0] rounded-lg text-xs"
                />
                <Button size="sm" variant="outline" data-testid="tpl-checklist-add"
                  onClick={addChecklistItem} className="h-8 text-xs px-2">
                  <Plus className="w-3 h-3" />
                </Button>
              </div>
            </div>
          </div>

          {/* Recurrence */}
          <div className="bg-[#F9F9F8] border border-[#E2E4E0] rounded-lg p-3">
            <Label className="text-[10px] uppercase font-bold text-[#6B7280] flex items-center gap-1.5">
              <History className="w-3 h-3" /> Standard-Wiederholung
            </Label>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <select data-testid="tpl-recurrence-pattern"
                value={draft.recurrence?.pattern || ''}
                onChange={e => {
                  const p = e.target.value || null;
                  set({ recurrence: p ? { pattern: p, interval: draft.recurrence?.interval || 1, end_date: draft.recurrence?.end_date || null } : null });
                }}
                className="h-8 px-2 text-xs border border-[#E2E4E0] rounded-lg bg-white">
                <option value="">keine Wiederholung</option>
                <option value="daily">täglich</option>
                <option value="weekly">wöchentlich</option>
                <option value="monthly">monatlich</option>
              </select>
              {draft.recurrence?.pattern && (
                <>
                  <span className="text-xs text-[#6B7280]">alle</span>
                  <Input type="number" min="1" max="52"
                    data-testid="tpl-recurrence-interval"
                    value={draft.recurrence.interval || 1}
                    onChange={e => set({ recurrence: { ...draft.recurrence, interval: Math.max(1, parseInt(e.target.value) || 1) } })}
                    className="w-14 h-8 text-xs border-[#E2E4E0] rounded-lg" />
                  <span className="text-xs text-[#6B7280]">
                    {draft.recurrence.pattern === 'daily' ? 'Tag(e)' : draft.recurrence.pattern === 'weekly' ? 'Woche(n)' : 'Monat(e)'}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex flex-col sm:flex-row gap-2 pt-3 border-t border-[#E2E4E0]">
            <Button variant="outline" size="sm" onClick={onClose}
              disabled={busy} data-testid="tpl-cancel" className="h-9 text-xs">
              Abbrechen
            </Button>
            <div className="flex-1" />
            <Button data-testid="tpl-submit" onClick={submit}
              disabled={busy || !draft.name.trim()}
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-9 text-xs">
              {busy && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
              {isEdit ? 'Speichern' : 'Vorlage anlegen'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
