import { useEffect, useState, useCallback, useRef } from 'react';
import api from '../../lib/api';
import { Dialog, DialogContent } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import {
  Loader2, MessageSquare, Paperclip, History,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../contexts/AuthContext';
import {
  TASK_STATUSES as STATUSES, TASK_STATUS_LABELS as STATUS_LABELS,
  TASK_PRIORITIES as PRIORITIES, TASK_PRIORITY_LABELS as PRIORITY_LABELS,
} from './taskConstants';
import TaskDialogHeader from './TaskDialogHeader';
import TaskFooter from './TaskFooter';
import TaskRecurrenceBlock from './TaskRecurrenceBlock';
import TaskCommentsTab from './TaskCommentsTab';
import TaskFilesTab from './TaskFilesTab';
import TaskActivityTab from './TaskActivityTab';
import TaskAssigneesBlock from './TaskAssigneesBlock';
import TaskGroupsBlock from './TaskGroupsBlock';
import TaskTagsBlock from './TaskTagsBlock';
import TaskChecklistBlock from './TaskChecklistBlock';

export default function TaskDetailDialog({ taskId, users, open, onClose, onChanged, onEdit, createMode = false, defaults = null, onCreated }) {
  const { user: currentUser } = useAuth();
  // iter 206 — assignee picker must include the current user (self-assign).
  // /api/chat/users excludes self by design (used for chat-DM picker), so we
  // merge the current user into the local list just for this picker.
  const usersForAssignment = (() => {
    const base = users || [];
    if (!currentUser?.user_id) return base;
    if (base.some(u => u.user_id === currentUser.user_id)) return base;
    return [
      { user_id: currentUser.user_id, name: currentUser.name || currentUser.email, email: currentUser.email },
      ...base,
    ];
  })();
  const [task, setTask] = useState(null);
  const [comments, setComments] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('details');
  const [draftCmt, setDraftCmt] = useState('');
  const [replyTo, setReplyTo] = useState(null);
  const [linkUrl, setLinkUrl] = useState('');
  const [linkName, setLinkName] = useState('');
  const [showLinkForm, setShowLinkForm] = useState(false);
  // iter 214 — Templates-Picker inside the dialog (createMode only) so users
  // on mobile/tablet can apply a template without first closing the dialog
  // to reach the Vorlagen-button on the page header (which is covered by
  // the dialog overlay).
  const [templates, setTemplates] = useState([]);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  // iter 214 — kebab menu state moved to TaskFooter component (iter 216).
  // iter 195 — merged dialog: when createMode=true and no taskId, the dialog
  // shows an empty draft form. After submit, parent transitions taskId to the
  // newly-created task (same window — no close/reopen).
  const [groups, setGroups] = useState([]);
  const [creating, setCreating] = useState(false);
  // iter 198 — auto-save on title blur eliminates the explicit "Aufgabe
  // anlegen" button. The ref guards against double-POST when blur fires
  // multiple times during the prop transition (createMode → taskId).
  const autoCreatedRef = useRef(false);
  // iter 200 — track whether the task was just auto-created in this session.
  // If yes, "Abbrechen" rolls it back (DELETE). Otherwise it just closes.
  const justCreatedRef = useRef(false);
  // iter 205 — race-fix: clicking "Abbrechen" while the title input still
  // has focus fires the input's blur *before* the button click. That blur
  // would otherwise auto-create the task we're trying to discard. We set
  // this flag on mouse-down (fires before blur) so handleTitleBlur bails
  // out when the user's actual intent is to cancel.
  // iter 205 — race-fix: clicking either footer button while the title input
  // still has focus fires the input's blur *before* the button click. We set
  // this flag synchronously on the button's mouse-down (which runs before
  // blur) so handleTitleBlur bails out and the button handler decides what
  // to do (save explicitly OR roll back). Reset on every blur so the flag
  // doesn't leak across interactions.
  const skipBlurAutosaveRef = useRef(false);
  // iter 205 — track an in-flight auto-create POST. Kept for symmetry with
  // skipBlurAutosaveRef in case any path still triggers blur first.
  const pendingCreateRef = useRef(null);
  // Original title at first load — used by handleCloseAndSave to detect dirt.
  const originalTitleRef = useRef('');
  // iter 199 — after auto-save we already have the fresh task data; skip
  // the next fetchAll() so the dialog never flashes a loading spinner.
  const skipNextFetchRef = useRef(false);
  const isCreate = createMode && !taskId;

  const userMap = usersForAssignment.reduce((a, u) => { a[u.user_id] = u; return a; }, {});

  const fetchAll = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const [t, c, a] = await Promise.all([
        api.get(`/tasks/${taskId}`),
        api.get(`/tasks/${taskId}/comments`),
        api.get(`/tasks/${taskId}/attachments`),
      ]);
      setTask(t.data); setComments(c.data); setAttachments(a.data);
      originalTitleRef.current = t.data?.title || '';
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Aufgabe nicht ladbar');
      onClose();
    } finally { setLoading(false); }
  }, [taskId]);  // eslint-disable-line

  useEffect(() => {
    if (!open) return;
    // iter 199 — when auto-save just completed, we already have the fresh
    // task in local state; skip the loading flash.
    if (skipNextFetchRef.current) {
      skipNextFetchRef.current = false;
      setTab('details');
      return;
    }
    if (taskId) {
      fetchAll();
    } else if (isCreate) {
      // Empty draft for create mode
      setTask({
        title: '', description: '', status: 'open', priority: 'normal',
        due_date: null, assignee_ids: [], group_ids: [], tags: [], checklist: [],
        ...(defaults || {}),
      });
      setComments([]); setAttachments([]); setHistory([]);
    }
    setTab('details');
  }, [taskId, open, fetchAll, isCreate, defaults]);

  // Lazy-load groups for audience picker (graceful failure for non-admins)
  useEffect(() => {
    if (open) {
      api.get('/admin/groups').then(({ data }) => setGroups(data || [])).catch(() => setGroups([]));
    }
  }, [open]);

  // Lazy-load history when activity tab is opened
  useEffect(() => {
    if (tab === 'activity' && taskId) {
      api.get(`/tasks/${taskId}/history`).then(({ data }) => setHistory(data || []))
        .catch(() => setHistory([]));
    }
  }, [tab, taskId]);

  // Reset transient state on close
  useEffect(() => {
    if (!open) {
      setLinkUrl(''); setLinkName('');
      setShowLinkForm(false); setDraftCmt(''); setReplyTo(null); setCreating(false);
      autoCreatedRef.current = false;
      skipNextFetchRef.current = false;
      justCreatedRef.current = false;
      skipBlurAutosaveRef.current = false;
      pendingCreateRef.current = null;
      setShowTemplatePicker(false);
    }
  }, [open]);

  // iter 214 — Load templates lazily when the picker is opened (createMode only).
  useEffect(() => {
    if (!showTemplatePicker || !isCreate) return;
    if (templates.length > 0) return;
    api.get('/task-templates')
      .then(({ data }) => setTemplates(data || []))
      .catch(() => {});
  }, [showTemplatePicker, isCreate, templates.length]);

  const applyTemplate = async (template_id) => {
    setShowTemplatePicker(false);
    try {
      const { data } = await api.post(`/tasks/from-template/${template_id}`, {});
      // Behave exactly like the auto-create path: seed local state, hand
      // ownership over to the parent so it flips taskId and the dialog
      // continues seamlessly in edit mode.
      setTask(data);
      autoCreatedRef.current = true;
      justCreatedRef.current = true;
      skipNextFetchRef.current = true;
      onChanged?.();
      onCreated?.(data);
      toast.success('Vorlage angewendet');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Vorlage konnte nicht angewendet werden');
    }
  };

  const patch = async (changes) => {
    if (isCreate) {
      // Buffer changes locally — no API call until "Aufgabe anlegen"
      setTask(prev => ({ ...prev, ...changes }));
      return;
    }
    // Iter 335 — Optimistic update: reflect change immediately in UI and
    // in the parent list/board so the user sees the new status without
    // waiting for the server roundtrip. Server response then reconciles.
    const previous = task;
    setTask(prev => ({ ...prev, ...changes }));
    onChanged?.(changes);
    try {
      const { data } = await api.put(`/tasks/${taskId}`, changes);
      setTask(data);
      onChanged?.();
    } catch (e) {
      // Roll back on error
      setTask(previous);
      onChanged?.();
      toast.error(e.response?.data?.detail || 'Update fehlgeschlagen');
    }
  };

  const handleCreate = async () => {
    // Legacy explicit-button path kept for safety. Most flows now go through
    // handleTitleBlur (auto-save) below.
    if (!task?.title?.trim()) { toast.error('Titel erforderlich'); return; }
    setCreating(true);
    try {
      const { data } = await api.post('/tasks', {
        title: task.title.trim(),
        description: (task.description || '').trim(),
        status: task.status || 'open',
        priority: task.priority || 'normal',
        due_date: task.due_date || null,
        assignee_ids: task.assignee_ids || [],
        group_ids: task.group_ids || [],
        tags: task.tags || [],
        checklist: task.checklist || [],
        recurrence: task.recurrence || null,
      });
      toast.success('Aufgabe erstellt');
      onChanged?.();
      onCreated?.(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Erstellen');
    } finally { setCreating(false); }
  };

  /* iter 198 — Auto-create on title blur. The user no longer needs to click
     a separate "Aufgabe anlegen" button. As soon as the title is non-empty
     and the field loses focus, we POST /tasks in the background and seamlessly
     transition the dialog to edit mode. The ref guards against duplicate
     creation if blur fires twice (e.g. on close). */
  const performAutoCreate = async () => {
    // Single source of truth for the POST. Returns the new task on success.
    // Sets autoCreatedRef synchronously so concurrent callers don't double-POST.
    if (autoCreatedRef.current || creating) return null;
    const title = (task?.title || '').trim();
    if (!title) return null;
    autoCreatedRef.current = true;
    setCreating(true);
    try {
      const { data } = await api.post('/tasks', {
        title,
        description: (task.description || '').trim(),
        status: task.status || 'open',
        priority: task.priority || 'normal',
        due_date: task.due_date || null,
        assignee_ids: task.assignee_ids || [],
        group_ids: task.group_ids || [],
        tags: task.tags || [],
        checklist: task.checklist || [],
        recurrence: task.recurrence || null,
      });
      // iter 199 — seed local state with the fresh task BEFORE flipping
      // parent props, and tell the next useEffect run to skip refetching.
      // This eliminates the brief loading-spinner flash that used to make
      // the dialog feel like two windows.
      setTask(data);
      setComments([]); setAttachments([]); setHistory([]);
      skipNextFetchRef.current = true;
      justCreatedRef.current = true;
      onChanged?.();
      onCreated?.(data);  // parent flips createMode→false, sets taskId
      return data;
    } catch (e) {
      autoCreatedRef.current = false;
      toast.error(e.response?.data?.detail || 'Fehler beim Anlegen');
      return null;
    } finally {
      setCreating(false);
    }
  };

  const handleTitleBlur = async () => {
    // iter 205 — if the blur was caused by a mouse-down on a footer button
    // (Abbrechen or Schließen-und-speichern), skip the auto-create. The
    // button's own handler will decide what to do (save explicitly or
    // discard). Reset the flag immediately so subsequent blurs work.
    if (skipBlurAutosaveRef.current) {
      skipBlurAutosaveRef.current = false;
      return;
    }
    const title = (task?.title || '').trim();
    if (!title) return;  // empty title → don't auto-save
    if (isCreate && !autoCreatedRef.current && !creating) {
      pendingCreateRef.current = performAutoCreate();
      try { await pendingCreateRef.current; }
      finally { pendingCreateRef.current = null; }
    } else if (taskId) {
      // Edit mode — just patch the title
      patch({ title });
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Aufgabe wirklich löschen?')) return;
    try {
      await api.delete(`/tasks/${taskId}`);
      toast.success('Gelöscht'); onChanged?.(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  /* iter 200 — "Schließen und speichern": ensure pending title is saved
     (auto-save fires on blur, but if user clicks button without blurring
     first, we explicitly save the current title here too). */
  const handleCloseAndSave = async () => {
    const title = (task?.title || '').trim();
    if (isCreate && !title) {
      // Empty draft: nothing to save — just close.
      onClose();
      return;
    }
    // iter 205 — if a blur-triggered auto-create somehow slipped through
    // (e.g. user tabbed before clicking), wait for it before closing.
    if (pendingCreateRef.current) {
      try { await pendingCreateRef.current; } catch {}
    } else if (isCreate && title && !autoCreatedRef.current && !creating) {
      // Create mode + clean state: save explicitly here. The blur autosave
      // was suppressed by skipBlurAutosaveRef on this button's mouse-down.
      await performAutoCreate();
    } else if (taskId && task?.title?.trim() && task.title !== originalTitleRef.current) {
      // View mode: save any pending title change (other fields auto-save on blur).
      try { await api.put(`/tasks/${taskId}`, { title: task.title }); } catch {}
    }
    onClose();
  };

  /* iter 200 — "Abbrechen": if the task was just auto-created in THIS dialog
     session, roll it back via DELETE. Otherwise just close. */
  const handleCancel = async () => {
    if (justCreatedRef.current && taskId) {
      if (!window.confirm('Diese gerade erstellte Aufgabe verwerfen und löschen?')) return;
      try {
        await api.delete(`/tasks/${taskId}`);
        toast.success('Aufgabe verworfen');
        onChanged?.();
      } catch (e) {
        toast.error(e.response?.data?.detail || 'Konnte nicht verworfen werden');
      }
    }
    onClose();
  };

  const handleDuplicate = async () => {
    try {
      await api.post(`/tasks/${taskId}/duplicate`);
      toast.success('Dupliziert'); onChanged?.();
    } catch (e) { toast.error('Fehler beim Duplizieren'); }
  };

  // Comments
  const submitComment = async () => {
    if (!draftCmt.trim()) return;
    try {
      await api.post(`/tasks/${taskId}/comments`, { content: draftCmt, parent_id: replyTo });
      setDraftCmt(''); setReplyTo(null);
      const { data } = await api.get(`/tasks/${taskId}/comments`);
      setComments(data);
    } catch (e) { toast.error('Kommentar fehlgeschlagen'); }
  };
  const deleteComment = async (cid) => {
    if (!window.confirm('Kommentar löschen?')) return;
    await api.delete(`/tasks/${taskId}/comments/${cid}`);
    setComments(comments.filter(c => c.comment_id !== cid));
  };

  // Mention insertion
  const insertMention = (u) => {
    setDraftCmt(d => `${d}@[${u.name || u.email}](${u.user_id}) `);
  };

  // Attachments
  const handleFile = async (file) => {
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append('file', file);
      await api.post(`/tasks/${taskId}/attachments/file`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const { data } = await api.get(`/tasks/${taskId}/attachments`);
      setAttachments(data);
      toast.success('Datei hochgeladen');
    } catch (e) { toast.error(e.response?.data?.detail || 'Upload fehlgeschlagen'); }
  };
  const addLink = async () => {
    if (!linkUrl.trim()) { toast.error('URL erforderlich'); return; }
    try {
      await api.post(`/tasks/${taskId}/attachments/link`, { url: linkUrl.trim(), name: linkName.trim() || '' });
      const { data } = await api.get(`/tasks/${taskId}/attachments`);
      setAttachments(data);
      setLinkUrl(''); setLinkName(''); setShowLinkForm(false);
      toast.success('Link hinzugefügt');
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };
  const removeAttachment = async (id) => {
    await api.delete(`/tasks/${taskId}/attachments/${id}`);
    setAttachments(attachments.filter(a => a.attachment_id !== id));
  };

  // Threaded comments
  if (!open) return null;
  if (!taskId && !isCreate) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-[760px] max-h-[92vh] overflow-y-auto w-[calc(100vw-1rem)] p-4 sm:p-6" data-testid="task-detail-dialog">
        <TaskDialogHeader
          isCreate={isCreate}
          taskStatus={task?.status}
          showTemplatePicker={showTemplatePicker}
          onToggleTemplatePicker={() => setShowTemplatePicker(v => !v)}
          templates={templates}
          onApplyTemplate={applyTemplate}
        />

        {loading || !task ? <Loader2 className="w-5 h-5 animate-spin" /> : (
          <div className="space-y-4 mt-2">
            <Input
              data-testid="task-title-input"
              value={task.title}
              onChange={e => setTask({ ...task, title: e.target.value })}
              onBlur={handleTitleBlur}
              autoFocus={isCreate}
              placeholder={isCreate ? 'Titel der Aufgabe (Pflicht — speichert automatisch) ...' : ''}
              disabled={creating}
              className="text-lg font-medium border-[#E2E4E0] rounded-lg disabled:opacity-90"
            />
            <Textarea
              data-testid="task-description-input"
              value={task.description || ''}
              onChange={e => setTask({ ...task, description: e.target.value })}
              onBlur={() => !isCreate && patch({ description: task.description })}
              placeholder="Beschreibung ..."
              rows={3}
              className="border-[#E2E4E0] rounded-lg text-sm"
            />

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div>
                <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Status</Label>
                <select data-testid="task-status-select" value={task.status}
                  onChange={(e) => patch({ status: e.target.value })}
                  className="w-full h-9 px-2 text-sm border border-[#E2E4E0] rounded-lg bg-white">
                  {STATUSES.map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Prioritaet</Label>
                <select data-testid="task-priority-select" value={task.priority}
                  onChange={(e) => patch({ priority: e.target.value })}
                  className="w-full h-9 px-2 text-sm border border-[#E2E4E0] rounded-lg bg-white">
                  {PRIORITIES.map(p => <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>)}
                </select>
              </div>
              <div className="col-span-2">
                <Label className="text-[10px] uppercase font-bold text-[#6B7280]">Faellig</Label>
                <Input data-testid="task-due-date" type="date" value={task.due_date || ''}
                  onChange={e => patch({ due_date: e.target.value || null })}
                  className="h-9 border-[#E2E4E0] rounded-lg text-sm" />
              </div>
            </div>

            {/* Recurrence (iter 196) — extracted into TaskRecurrenceBlock (iter 216) */}
            <TaskRecurrenceBlock recurrence={task.recurrence} onPatch={patch} />

            {/* Assignees — extracted into TaskAssigneesBlock (iter 236) */}
            <TaskAssigneesBlock
              assigneeIds={task.assignee_ids}
              usersForAssignment={usersForAssignment}
              userMap={userMap}
              currentUser={currentUser}
              onPatch={patch}
            />

            {/* Groups — extracted into TaskGroupsBlock (iter 236) */}
            <TaskGroupsBlock
              groups={groups}
              groupIds={task.group_ids}
              onPatch={patch}
            />

            {/* Tags — extracted into TaskTagsBlock (iter 236) */}
            <TaskTagsBlock tags={task.tags} onPatch={patch} />

            {/* Checklist — extracted into TaskChecklistBlock (iter 236) */}
            <TaskChecklistBlock checklist={task.checklist} onPatch={patch} />

            {/* Tabs: immer sichtbar — in Create-Mode sind erweiterte Tabs disabled */}
            <div className="border-t border-[#E2E4E0] pt-3">
              <div className="flex gap-2 mb-3 flex-wrap">
                <Button size="sm" variant={tab === 'details' ? 'default' : 'outline'} onClick={() => setTab('details')} className="h-7 text-xs">Details</Button>
                <Button size="sm" variant={tab === 'comments' ? 'default' : 'outline'}
                  disabled={isCreate}
                  title={isCreate ? 'Nach dem Anlegen verfügbar' : ''}
                  onClick={() => !isCreate && setTab('comments')}
                  className="h-7 text-xs disabled:opacity-50"
                  data-testid="task-tab-comments">
                  <MessageSquare className="w-3 h-3 mr-1" />Kommentare {!isCreate && `(${comments.length})`}
                </Button>
                <Button size="sm" variant={tab === 'files' ? 'default' : 'outline'}
                  disabled={isCreate}
                  title={isCreate ? 'Nach dem Anlegen verfügbar' : ''}
                  onClick={() => !isCreate && setTab('files')}
                  className="h-7 text-xs disabled:opacity-50"
                  data-testid="task-tab-files">
                  <Paperclip className="w-3 h-3 mr-1" />Anhänge {!isCreate && `(${attachments.length})`}
                </Button>
                <Button size="sm" variant={tab === 'activity' ? 'default' : 'outline'}
                  disabled={isCreate}
                  title={isCreate ? 'Nach dem Anlegen verfügbar' : ''}
                  onClick={() => !isCreate && setTab('activity')}
                  className="h-7 text-xs disabled:opacity-50"
                  data-testid="task-tab-activity">
                  <History className="w-3 h-3 mr-1" />Verlauf
                </Button>
              </div>

              {tab === 'comments' && (
                <TaskCommentsTab
                  comments={comments} users={users} userMap={userMap}
                  draftCmt={draftCmt} onDraftChange={setDraftCmt}
                  replyTo={replyTo} onSetReplyTo={setReplyTo}
                  onDeleteComment={deleteComment}
                  onSubmitComment={submitComment}
                  onInsertMention={insertMention}
                />
              )}

              {tab === 'files' && (
                <TaskFilesTab
                  attachments={attachments}
                  showLinkForm={showLinkForm}
                  onToggleLinkForm={() => setShowLinkForm(s => !s)}
                  linkUrl={linkUrl} onLinkUrlChange={setLinkUrl}
                  linkName={linkName} onLinkNameChange={setLinkName}
                  onFile={handleFile}
                  onAddLink={addLink}
                  onRemoveAttachment={removeAttachment}
                />
              )}

              {tab === 'activity' && (
                <TaskActivityTab history={history} />
              )}

              {tab === 'details' && task.subtasks?.length > 0 && (
                <div>
                  <Label className="text-[10px] uppercase font-bold text-[#6B7280] block mb-1.5">Unteraufgaben</Label>
                  <div className="space-y-1">
                    {task.subtasks.map(st => (
                      <div key={st.task_id} className="flex items-center justify-between p-2 bg-[#F9F9F8] rounded-lg text-sm">
                        <span>{st.title}</span>
                        <Badge className="text-[9px]">{STATUS_LABELS[st.status]}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Footer (iter 216): extracted into TaskFooter component */}
            <TaskFooter
              isCreate={isCreate}
              creating={creating}
              canDelete={task?.can_delete !== false}
              hasTitle={!!task?.title?.trim()}
              onCancel={handleCancel}
              onSave={handleCloseAndSave}
              onDuplicate={handleDuplicate}
              onDelete={handleDelete}
              onBlockBlurAutosave={() => { skipBlurAutosaveRef.current = true; }}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
