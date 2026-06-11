/* Tasks page (iter 192–193) — Aufgabenmanagement.
   Layout an News/Surveys angeglichen: Sidebar + Header-Pattern, vollwertiger
   TaskEditorDialog statt prompt(), Push-Toggle, gemeinsamer Filter-Block. */
import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import usePullToRefresh from '../hooks/usePullToRefresh';
import PullToRefreshIndicator from '../components/PullToRefreshIndicator';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Plus, Search, Loader2, ListChecks, LayoutGrid, Calendar as CalendarIcon,
  Filter as FilterIcon, Bell, BellOff, X, Files, Trash2, Pencil,
} from 'lucide-react';
import { toast } from 'sonner';
import TaskDetailDialog from '../components/tasks/TaskDetailDialog';
import TaskTemplateEditorDialog from '../components/tasks/TaskTemplateEditorDialog';
import TaskBoard from '../components/tasks/TaskBoard';
import TaskList from '../components/tasks/TaskList';
import TaskCalendarView from '../components/tasks/TaskCalendarView';
import { TASK_STATUS_LABELS as STATUS_LABELS, TASK_PRIORITY_LABELS as PRIORITY_LABELS } from '../components/tasks/taskConstants';
import {
  subscribeToPush, unsubscribeFromPush,
  getPushSubscriptionStatus, isPushSupported,
} from '../lib/push';

export default function TasksPage() {
  const { user } = useAuth();
  const { language } = useLanguage();
  const isDE = language === 'de';
  const { taskId } = useParams();
  const navigate = useNavigate();
  const [view, setView] = useState('board');
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState([]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [filterAssignee, setFilterAssignee] = useState('');
  // iter 194 — default to "only mine". Filter "Alle Verantwortlichen" requires
  // the `tasks.view_all` capability (admins always; moderators per default).
  const [showOnlyMine, setShowOnlyMine] = useState(true);
  const [users, setUsers] = useState([]);
  const [openTaskId, setOpenTaskId] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  // iter 195 — single merged dialog. createMode=true means "show empty
  // create form"; once user submits, we transition by setting openTaskId
  // so the SAME dialog re-renders in view mode.
  const [createMode, setCreateMode] = useState(false);
  const [pushStatus, setPushStatus] = useState({ supported: false, permission: 'default', subscribed: false });
  const [capabilities, setCapabilities] = useState([]);
  // iter 196 — task templates
  const [templates, setTemplates] = useState([]);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  // iter 197 — full template editor
  const [templateEditorOpen, setTemplateEditorOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);

  const dialogOpen = !!openTaskId || createMode;
  const canViewAll = user?.role === 'admin' || capabilities.includes('tasks.view_all');
  const canManageTemplates = user?.role === 'admin' || user?.role === 'moderator';

  const fetchTemplates = useCallback(() => {
    api.get('/task-templates').then(({ data }) => setTemplates(data || [])).catch(() => setTemplates([]));
  }, []);
  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const applyTemplate = async (templateId) => {
    try {
      const { data } = await api.post(`/tasks/from-template/${templateId}`, {});
      toast.success('Aufgabe aus Vorlage erstellt');
      setShowTemplatePicker(false);
      fetchTasks();
      // Open the newly created task for review/edit in the SAME merged dialog.
      setCreateMode(false);
      setOpenTaskId(data.task_id);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Vorlage konnte nicht angewandt werden');
    }
  };

  const saveAsTemplate = () => {
    // iter 197 — open full editor instead of prompt()
    setEditingTemplate(null);
    setTemplateEditorOpen(true);
    setShowTemplatePicker(false);
  };

  const editTemplate = (tpl) => {
    setEditingTemplate(tpl);
    setTemplateEditorOpen(true);
    setShowTemplatePicker(false);
  };

  const deleteTemplate = async (templateId) => {
    if (!window.confirm('Vorlage wirklich löschen?')) return;
    try {
      await api.delete(`/task-templates/${templateId}`);
      fetchTemplates();
      toast.success('Vorlage gelöscht');
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  // Push status (parity with NewsPage)
  useEffect(() => {
    if (isPushSupported()) {
      getPushSubscriptionStatus().then(setPushStatus).catch(() => {});
    }
  }, []);

  const handleEnablePush = async () => {
    try {
      await subscribeToPush();
      setPushStatus(await getPushSubscriptionStatus());
      toast.success('Push aktiviert');
    } catch (e) {
      toast.error(e.message || 'Aktivierung fehlgeschlagen', {
        description: 'Klick „Zur Diagnose" unten, um den Fehler einzugrenzen.',
        action: { label: 'Zur Diagnose', onClick: () => navigate('/diag') },
        duration: 10000,
      });
    }
  };
  const handleDisablePush = async () => {
    try {
      await unsubscribeFromPush();
      setPushStatus(await getPushSubscriptionStatus());
      toast.success('Push deaktiviert');
    } catch (e) { toast.error(e.message || 'Fehler'); }
  };

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterStatus) params.append('status', filterStatus);
      if (filterPriority) params.append('priority', filterPriority);
      if (showOnlyMine && user?.user_id) params.append('assignee_id', user.user_id);
      else if (filterAssignee) params.append('assignee_id', filterAssignee);
      if (debouncedSearch) params.append('search', debouncedSearch);
      const { data } = await api.get(`/tasks?${params.toString()}`);
      setTasks(data.tasks || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Aufgaben konnten nicht geladen werden');
    } finally { setLoading(false); }
  }, [filterStatus, filterPriority, filterAssignee, showOnlyMine, debouncedSearch, user]);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  useEffect(() => {
    api.get('/chat/users').then(({ data }) => setUsers(data || [])).catch(() => {});
    api.get('/user/permissions').then(({ data }) => setCapabilities(data?.capabilities || []))
      .catch(() => setCapabilities([]));
  }, []);

  // iter 304 — Always include the current user in the directory map so their
  // own avatar/name renders correctly on tasks they are assigned to (the
  // `/chat/users` endpoint deliberately excludes the caller).
  const usersWithSelf = useMemo(() => {
    if (!user?.user_id) return users;
    if (users.some(u => u.user_id === user.user_id)) return users;
    return [...users, { user_id: user.user_id, name: user.name, email: user.email, avatar: user.avatar }];
  }, [users, user]);

  // If user lacks `tasks.view_all`, force only-mine view at all times so
  // they can never see other users' work via the assignee filter.
  useEffect(() => {
    if (!canViewAll) {
      setShowOnlyMine(true);
      setFilterAssignee('');
    }
  }, [canViewAll]);

  // Open detail when /tasks/:taskId
  useEffect(() => { if (taskId) setOpenTaskId(taskId); }, [taskId]);

  // Iter 336 — Realtime: listen for `task-*` events fan-out from the
  // global chat WebSocket (re-dispatched by StatusContext as a window
  // event). Update local state in-place so other users' status moves
  // appear instantly without polling.
  useEffect(() => {
    const onTaskEvent = (e) => {
      const data = e.detail || {};
      const t = data.task;
      const tid = data.task_id || (t && t.task_id);
      if (!tid) return;
      // Suppress echo of changes the current user just made — they
      // already see the optimistic update.
      if (data.actor_id && data.actor_id === user?.user_id) return;
      if (data.type === 'task-created') {
        setTasks(prev => prev.some(x => x.task_id === tid) ? prev : (t ? [t, ...prev] : prev));
        toast.success(`Neue Aufgabe: ${t?.title || ''}`, { id: `task-evt-${tid}` });
      } else if (data.type === 'task-updated' && t) {
        setTasks(prev => {
          const exists = prev.some(x => x.task_id === tid);
          return exists
            ? prev.map(x => x.task_id === tid ? { ...x, ...t } : x)
            : [t, ...prev];
        });
      } else if (data.type === 'task-deleted') {
        setTasks(prev => prev.filter(x => x.task_id !== tid));
      }
    };
    window.addEventListener('meetflow:task-event', onTaskEvent);
    return () => window.removeEventListener('meetflow:task-event', onTaskEvent);
  }, [user]);

  const handleStatusChange = async (id, newStatus) => {
    try {
      await api.put(`/tasks/${id}`, { status: newStatus });
      setTasks(ts => ts.map(t => t.task_id === id ? { ...t, status: newStatus } : t));
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Status-Update fehlgeschlagen');
    }
  };

  const myCounts = useMemo(() => {
    if (!user?.user_id) return { mine: 0, overdue: 0 };
    const today = new Date().toISOString().slice(0, 10);
    let mine = 0, overdue = 0;
    tasks.forEach(t => {
      if ((t.assignee_ids || []).includes(user.user_id) && t.status !== 'done') {
        mine += 1;
        if (t.due_date && t.due_date < today) overdue += 1;
      }
    });
    return { mine, overdue };
  }, [tasks, user]);

  const filtered = tasks;

  // iter 317 — pull-to-refresh on mobile
  const ptr = usePullToRefresh({ onRefresh: fetchTasks });

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in"
            data-testid="tasks-page"
            {...ptr.bind}
            style={{ touchAction: ptr.isPulling ? 'none' : undefined }}>
        <PullToRefreshIndicator pullPx={ptr.pullPx} refreshing={ptr.refreshing} threshold={ptr.threshold} />
        <div className="max-w-7xl mx-auto">

          {/* Header — News/Surveys parity */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
            <div className="min-w-0">
              <h1 className="text-xl sm:text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
                {isDE ? 'Aufgaben' : 'Tasks'}
              </h1>
              <p className="text-xs sm:text-sm text-[#9CA3AF]">
                {isDE
                  ? `${myCounts.mine} mir zugewiesen${myCounts.overdue ? ` · ${myCounts.overdue} überfällig` : ''} · ${filtered.length} sichtbar`
                  : `${myCounts.mine} assigned to me · ${filtered.length} visible`}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap sm:justify-end">
              {pushStatus.supported && (
                pushStatus.subscribed && pushStatus.permission === 'granted' ? (
                  <Button variant="outline" size="sm" onClick={handleDisablePush}
                    className="rounded-full border-[#E2E4E0] text-xs h-9 gap-1.5"
                    data-testid="tasks-push-disable">
                    <Bell className="w-3.5 h-3.5 text-[#6B8E23]" />
                    <span className="hidden sm:inline">{isDE ? 'Push aktiv' : 'Push on'}</span>
                  </Button>
                ) : pushStatus.permission === 'denied' ? (
                  <span className="text-[10px] text-[#C87967] flex items-center gap-1">
                    <BellOff className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">{isDE ? 'Push blockiert' : 'Push blocked'}</span>
                  </span>
                ) : (
                  <Button variant="outline" size="sm" onClick={handleEnablePush}
                    className="rounded-full border-[#E2E4E0] text-xs h-9 gap-1.5"
                    data-testid="tasks-push-enable">
                    <BellOff className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">{isDE ? 'Push aktivieren' : 'Enable push'}</span>
                  </Button>
                )
              )}
              <Button data-testid="task-create-button"
                onClick={() => { setOpenTaskId(null); setCreateMode(true); }}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl h-9 px-4 text-xs gap-1.5">
                <Plus className="w-4 h-4" />
                <span className="hidden sm:inline">{isDE ? 'Neue Aufgabe' : 'New task'}</span>
                <span className="sm:hidden">{isDE ? 'Neu' : 'New'}</span>
              </Button>
              <div className="relative">
                <Button data-testid="task-templates-btn" variant="outline"
                  onClick={() => setShowTemplatePicker(s => !s)}
                  className="rounded-xl border-[#E2E4E0] h-9 px-3 text-xs gap-1.5">
                  <Files className="w-4 h-4" />
                  <span className="hidden sm:inline">{isDE ? 'Vorlagen' : 'Templates'}</span>
                  {templates.length > 0 && <span className="text-[10px] text-[#9CA3AF]">({templates.length})</span>}
                </Button>
                {showTemplatePicker && (
                  <div data-testid="task-templates-popover"
                    className="absolute right-0 top-full mt-1 z-50 w-80 bg-white border border-[#E2E4E0] rounded-xl shadow-lg p-2">
                    <div className="flex items-center justify-between px-2 py-1.5 border-b border-[#E2E4E0] mb-1.5">
                      <span className="text-[10px] uppercase font-bold text-[#6B7280]">Vorlagen</span>
                      {canManageTemplates && (
                        <button onClick={saveAsTemplate}
                          data-testid="task-template-create"
                          className="text-[11px] text-[#4A5D4E] hover:underline">
                          + neu
                        </button>
                      )}
                    </div>
                    {templates.length === 0 ? (
                      <p className="text-xs text-[#9CA3AF] text-center py-3">
                        Noch keine Vorlagen. {canManageTemplates && 'Klicke "+ neu".'}
                      </p>
                    ) : (
                      <div className="space-y-0.5 max-h-80 overflow-y-auto">
                        {templates.map(t => (
                          <div key={t.template_id} data-testid={`task-template-${t.template_id}`}
                            className="flex items-center gap-2 px-2 py-1.5 hover:bg-[#F3F4F1] rounded-lg group">
                            <button onClick={() => applyTemplate(t.template_id)}
                              data-testid={`task-template-apply-${t.template_id}`}
                              className="flex-1 text-left min-w-0">
                              <p className="text-sm font-medium text-[#1C1F1D] truncate">{t.name}</p>
                              <p className="text-[10px] text-[#9CA3AF] truncate">
                                {t.priority && PRIORITY_LABELS[t.priority]}{t.checklist?.length > 0 ? ` · ${t.checklist.length} Schritt(e)` : ''}{t.recurrence?.pattern ? ' · wiederkehrend' : ''}
                              </p>
                            </button>
                            {canManageTemplates && (
                              <>
                                <button onClick={() => editTemplate(t)}
                                  data-testid={`task-template-edit-${t.template_id}`}
                                  title="Bearbeiten"
                                  className="text-[#9CA3AF] hover:text-[#4A5D4E] opacity-0 group-hover:opacity-100 transition-opacity">
                                  <Pencil className="w-3 h-3" />
                                </button>
                                <button onClick={() => deleteTemplate(t.template_id)}
                                  data-testid={`task-template-delete-${t.template_id}`}
                                  title="Löschen"
                                  className="text-[#9CA3AF] hover:text-[#C87967] opacity-0 group-hover:opacity-100 transition-opacity">
                                  <Trash2 className="w-3 h-3" />
                                </button>
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Toolbar: search + quick toggle + filters */}
          {/* Iter 357 — Mobile-UX: Search nimmt eine volle Zeile, danach
             "Nur meine" + "Filter" nebeneinander in einer zweiten Zeile
             (statt jeweils volle Breite). Spart vertikalen Platz auf Handy. */}
          <div className="flex flex-col sm:flex-row gap-2 sm:items-center mb-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
              <Input
                data-testid="task-search-input"
                value={search} onChange={e => setSearch(e.target.value)}
                placeholder={isDE ? 'Suche in Titel, Beschreibung, Tags ...' : 'Search title, description, tags ...'}
                className="pl-9 h-10 sm:h-9 border-[#E2E4E0] rounded-xl bg-white text-sm"
              />
            </div>
            <div className="flex gap-2 sm:contents">
              <button
                data-testid="tasks-only-mine"
                onClick={() => canViewAll && setShowOnlyMine(s => !s)}
                disabled={!canViewAll}
                title={!canViewAll ? 'Du siehst nur deine eigenen Aufgaben (Recht „tasks.view_all" fehlt).' : ''}
                className={`flex-1 sm:flex-none text-xs h-10 sm:h-9 px-3 rounded-xl border transition-colors ${showOnlyMine ? 'bg-[#4A5D4E] text-white border-[#4A5D4E]' : 'bg-white text-[#4B5563] border-[#E2E4E0] hover:border-[#4A5D4E]/40'} ${!canViewAll ? 'opacity-90 cursor-not-allowed' : ''}`}>
                {isDE ? 'Nur meine' : 'Only mine'}
              </button>
              <Button variant="outline" data-testid="task-toggle-filters"
                onClick={() => setShowFilters(s => !s)}
                className="flex-1 sm:flex-none border-[#E2E4E0] rounded-xl h-10 sm:h-9 text-xs">
                <FilterIcon className="w-4 h-4 mr-1.5" /> Filter
                {(filterStatus || filterPriority || filterAssignee) && (
                  <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-[#C87967]" />
                )}
              </Button>
            </div>
          </div>

          {showFilters && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4 p-3 bg-white border border-[#E2E4E0] rounded-xl">
              <select data-testid="task-filter-status" value={filterStatus}
                onChange={e => setFilterStatus(e.target.value)}
                className="h-9 px-3 text-sm border border-[#E2E4E0] rounded-lg bg-white">
                <option value="">{isDE ? 'Alle Status' : 'All statuses'}</option>
                {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <select data-testid="task-filter-priority" value={filterPriority}
                onChange={e => setFilterPriority(e.target.value)}
                className="h-9 px-3 text-sm border border-[#E2E4E0] rounded-lg bg-white">
                <option value="">{isDE ? 'Alle Prioritäten' : 'All priorities'}</option>
                {Object.entries(PRIORITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <select data-testid="task-filter-assignee" value={filterAssignee}
                onChange={e => setFilterAssignee(e.target.value)}
                disabled={showOnlyMine || !canViewAll}
                title={!canViewAll ? 'Recht „tasks.view_all" fehlt' : ''}
                className="h-9 px-3 text-sm border border-[#E2E4E0] rounded-lg bg-white disabled:opacity-50">
                <option value="">{canViewAll ? (isDE ? 'Alle Verantwortlichen' : 'All assignees') : (isDE ? 'Nur eigene (Recht fehlt)' : 'Only mine (perm missing)')}</option>
                {canViewAll && users.map(u => <option key={u.user_id} value={u.user_id}>{u.name || u.email}</option>)}
              </select>
              {(filterStatus || filterPriority || filterAssignee) && (
                <button
                  data-testid="task-filter-clear"
                  onClick={() => { setFilterStatus(''); setFilterPriority(''); setFilterAssignee(''); }}
                  className="col-span-1 sm:col-span-3 text-[11px] text-[#6B7280] hover:text-[#C87967] flex items-center justify-center gap-1 py-1">
                  <X className="w-3 h-3" /> {isDE ? 'Filter zurücksetzen' : 'Clear filters'}
                </button>
              )}
            </div>
          )}

          {/* Tabs */}
          <Tabs value={view} onValueChange={setView}>
            <TabsList className="bg-white border border-[#E2E4E0]">
              <TabsTrigger value="board" data-testid="tab-board"><LayoutGrid className="w-3.5 h-3.5 mr-1.5" />Board</TabsTrigger>
              <TabsTrigger value="list" data-testid="tab-list"><ListChecks className="w-3.5 h-3.5 mr-1.5" />Liste</TabsTrigger>
              <TabsTrigger value="calendar" data-testid="tab-calendar"><CalendarIcon className="w-3.5 h-3.5 mr-1.5" />Kalender</TabsTrigger>
            </TabsList>

            <TabsContent value="board" className="mt-4">
              {loading ? <Loader2 className="w-5 h-5 animate-spin text-[#9CA3AF]" /> : (
                filtered.length === 0 ? <EmptyState onCreate={() => { setOpenTaskId(null); setCreateMode(true); }} isDE={isDE} /> :
                <TaskBoard tasks={filtered} statusLabels={STATUS_LABELS}
                  onOpen={setOpenTaskId} onStatusChange={handleStatusChange}
                  users={usersWithSelf} />
              )}
            </TabsContent>
            <TabsContent value="list" className="mt-4">
              {loading ? <Loader2 className="w-5 h-5 animate-spin text-[#9CA3AF]" /> : (
                filtered.length === 0 ? <EmptyState onCreate={() => { setOpenTaskId(null); setCreateMode(true); }} isDE={isDE} /> :
                <TaskList tasks={filtered} statusLabels={STATUS_LABELS}
                  priorityLabels={PRIORITY_LABELS} onOpen={setOpenTaskId} users={usersWithSelf} />
              )}
            </TabsContent>
            <TabsContent value="calendar" className="mt-4">
              <TaskCalendarView tasks={filtered} onOpen={setOpenTaskId} />
            </TabsContent>
          </Tabs>
        </div>

        {/* Single merged dialog: handles create + view + edit */}
        <TaskDetailDialog
          taskId={openTaskId}
          createMode={createMode}
          users={users}
          open={dialogOpen}
          onClose={() => {
            setOpenTaskId(null); setCreateMode(false);
            if (taskId) navigate('/tasks', { replace: true });
            // Iter 335 — Safety net: refresh list on close so any background
            // changes are picked up even if onChanged wasn't fired.
            fetchTasks();
          }}
          onChanged={(optimistic) => {
            // Iter 335 — Optimistic patch from dialog: update the local list
            // immediately for snappier UX, then refetch in background to
            // reconcile with server (e.g. updated_at, computed fields).
            if (optimistic && openTaskId) {
              setTasks(ts => ts.map(t => t.task_id === openTaskId ? { ...t, ...optimistic } : t));
            }
            fetchTasks();
          }}
          onCreated={(t) => { setCreateMode(false); setOpenTaskId(t.task_id); fetchTasks(); }}
        />

        {/* Template Editor (iter 197) */}
        <TaskTemplateEditorDialog
          open={templateEditorOpen}
          template={editingTemplate}
          users={users}
          onClose={() => setTemplateEditorOpen(false)}
          onSaved={() => fetchTemplates()}
        />
      </main>
    </div>
  );
}

function EmptyState({ onCreate, isDE }) {
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-10 text-center" data-testid="tasks-empty-state">
      <ListChecks className="w-10 h-10 text-[#9CA3AF] mx-auto mb-3" />
      <h3 className="text-base font-medium text-[#1C1F1D] mb-1">
        {isDE ? 'Keine Aufgaben' : 'No tasks'}
      </h3>
      <p className="text-xs text-[#6B7280] mb-4">
        {isDE ? 'Lege die erste Aufgabe für dein Team an.' : 'Create the first task for your team.'}
      </p>
      <Button onClick={onCreate} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl text-xs h-9">
        <Plus className="w-4 h-4 mr-1.5" />{isDE ? 'Neue Aufgabe' : 'New task'}
      </Button>
    </div>
  );
}

export { STATUS_LABELS, PRIORITY_LABELS };
