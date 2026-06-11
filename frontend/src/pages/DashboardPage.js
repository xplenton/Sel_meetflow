import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import Sidebar from '../components/Sidebar';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import {
  Video, Calendar, Clock, Users, ArrowRight, Disc, Zap, MessageCircle,
  ArrowUpRight, ChevronRight, Shield, X, BellOff, Flag, AlertTriangle, ClipboardList,
  CheckSquare, Square, ListChecks, Building2, Sofa, Car, Inbox
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import TaskDetailDialog from '../components/tasks/TaskDetailDialog';
import InOfficeWidget from '../components/dashboard/InOfficeWidget';
import OfficeWeekWidget from '../components/dashboard/OfficeWeekWidget';
import ActiveBookingWidget from '../components/dashboard/ActiveBookingWidget';
import MyUpcomingBookingsWidget from '../components/dashboard/MyUpcomingBookingsWidget';

export default function DashboardPage() {
  const { user } = useAuth();
  const { t, language } = useLanguage();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [agenda, setAgenda] = useState(null);
  const [focusTimes, setFocusTimes] = useState([]);
  const [activeFocus, setActiveFocus] = useState(null);
  const [focusDialogOpen, setFocusDialogOpen] = useState(false);
  const [focusLabel, setFocusLabel] = useState('');
  const [focusDate, setFocusDate] = useState('');
  const [focusStart, setFocusStart] = useState('');
  const [focusEnd, setFocusEnd] = useState('');
  const [focusRecurrence, setFocusRecurrence] = useState('none'); // 'none' | 'daily' | 'weekly'
  const [focusUntilDate, setFocusUntilDate] = useState('');
  const [pendingReports, setPendingReports] = useState(0);
  const [mandatoryUnread, setMandatoryUnread] = useState(0);
  const [pendingSurveys, setPendingSurveys] = useState(0);
  // iter 194 — eigene Aufgaben + Quick-Create + Detail
  const [myTasks, setMyTasks] = useState([]);
  const [taskUsers, setTaskUsers] = useState([]);
  // iter 195 — single merged TaskDetailDialog handles both create + view
  const [taskDialogId, setTaskDialogId] = useState(null);
  const [taskDialogCreate, setTaskDialogCreate] = useState(false);
  const taskDialogOpen = !!taskDialogId || taskDialogCreate;
  const isDE = language === 'de';
  const isReviewer = ['admin', 'redakteur', 'freigeber'].includes(user?.role);

  const fetchMyTasks = () => {
    if (!user?.user_id) return;
    api.get(`/tasks?assignee_id=${user.user_id}`).then(({ data }) => {
      // Show only non-done, sort by due_date asc with overdue/urgent first
      const today = new Date().toISOString().slice(0, 10);
      const open = (data.tasks || []).filter(t => t.status !== 'done');
      open.sort((a, b) => {
        const ao = a.due_date && a.due_date < today ? 1 : 0;
        const bo = b.due_date && b.due_date < today ? 1 : 0;
        if (ao !== bo) return bo - ao;
        const ap = { urgent: 0, high: 1, normal: 2, low: 3 }[a.priority] ?? 2;
        const bp = { urgent: 0, high: 1, normal: 2, low: 3 }[b.priority] ?? 2;
        if (ap !== bp) return ap - bp;
        return (a.due_date || '9999').localeCompare(b.due_date || '9999');
      });
      setMyTasks(open.slice(0, 8));
    }).catch(() => setMyTasks([]));
  };

  const toggleTaskDone = async (taskId, currentStatus) => {
    const next = currentStatus === 'done' ? 'open' : 'done';
    try {
      await api.put(`/tasks/${taskId}`, { status: next });
      fetchMyTasks();
    } catch { toast.error('Status-Update fehlgeschlagen'); }
  };

  const fetchFocus = () => {
    api.get('/focus-times').then(({ data }) => setFocusTimes(data)).catch(() => {});
    api.get('/focus-times/active').then(({ data }) => setActiveFocus(data.active ? data.focus : null)).catch(() => {});
  };

  useEffect(() => {
    api.get('/dashboard/stats').then(({ data }) => setStats(data)).catch(() => {});
    api.get('/dashboard/agenda').then(({ data }) => setAgenda(data)).catch(() => {});
    fetchFocus();
    fetchMyTasks();
    api.get('/chat/users').then(({ data }) => setTaskUsers(data || [])).catch(() => {});
    if (isReviewer) {
      api.get('/news/reports/pending-count').then(({ data }) => setPendingReports(data?.count || 0)).catch(() => {});
    }
    api.get('/news/unread-count').then(({ data }) => setMandatoryUnread(data?.mandatory_unread || 0)).catch(() => {});
    api.get('/surveys/pending-count').then(({ data }) => setPendingSurveys(data?.count || 0)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReviewer, user?.user_id]);

  // Iter 336 — Realtime: refresh "My open tasks" widget when something
  // happens to any of the user's tasks elsewhere in the system.
  useEffect(() => {
    const onTaskEvent = (e) => {
      const data = e.detail || {};
      if (data.actor_id && data.actor_id === user?.user_id) return;
      fetchMyTasks();
    };
    window.addEventListener('meetflow:task-event', onTaskEvent);
    return () => window.removeEventListener('meetflow:task-event', onTaskEvent);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);

  const createFocus = async () => {
    if (!focusDate || !focusStart || !focusEnd) { toast.error(isDE ? 'Bitte alle Felder ausfüllen' : 'Please fill all fields'); return; }
    if (focusRecurrence !== 'none' && !focusUntilDate) {
      toast.error(isDE ? 'Bitte Enddatum für Wiederholung wählen' : 'Please pick an end date for the recurrence');
      return;
    }
    const start_time = new Date(`${focusDate}T${focusStart}`).toISOString();
    const end_time = new Date(`${focusDate}T${focusEnd}`).toISOString();
    const payload = {
      label: focusLabel || (isDE ? 'Fokus-Zeit' : 'Focus Time'),
      start_time, end_time,
      recurrence: focusRecurrence,
    };
    if (focusRecurrence !== 'none') payload.until_date = focusUntilDate;
    try {
      const { data } = await api.post('/focus-times', payload);
      if (data?.count) {
        toast.success(isDE ? `${data.count} Fokus-Zeiten erstellt` : `${data.count} focus times created`);
      } else {
        toast.success(isDE ? 'Fokus-Zeit erstellt' : 'Focus time created');
      }
      setFocusDialogOpen(false);
      setFocusLabel(''); setFocusDate(''); setFocusStart(''); setFocusEnd('');
      setFocusRecurrence('none'); setFocusUntilDate('');
      fetchFocus();
    } catch (err) {
      toast.error(err?.response?.data?.detail || (isDE ? 'Fehler' : 'Error'));
    }
  };

  const deleteFocus = async (id) => {
    try {
      await api.delete(`/focus-times/${id}`);
      toast.success(isDE ? 'Fokus-Zeit entfernt' : 'Focus time removed');
      fetchFocus();
    } catch {}
  };

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return isDE ? 'Guten Morgen' : 'Good morning';
    if (h < 18) return isDE ? 'Guten Tag' : 'Good afternoon';
    return isDE ? 'Guten Abend' : 'Good evening';
  };

  const formatTime = (iso) => {
    if (!iso) return '';
    return new Date(iso).toLocaleTimeString(isDE ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit' });
  };

  const formatRelative = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000 / 60;
    if (diff < 1) return isDE ? 'gerade eben' : 'just now';
    if (diff < 60) return `${Math.floor(diff)}m`;
    if (diff < 1440) return `${Math.floor(diff / 60)}h`;
    return d.toLocaleDateString(isDE ? 'de-DE' : 'en-US', { day: '2-digit', month: '2-digit' });
  };

  const activityIcon = (type) => {
    if (type === 'meeting_ended') return <Video className="w-3.5 h-3.5 text-[#9CA3AF]" />;
    if (type === 'recording') return <Disc className="w-3.5 h-3.5 text-[#C87967]" />;
    if (type === 'chat') return <MessageCircle className="w-3.5 h-3.5 text-[#4A5D4E]" />;
    return <Calendar className="w-3.5 h-3.5 text-[#9CA3AF]" />;
  };

  const activityLabel = (type) => {
    if (type === 'meeting_ended') return isDE ? 'Meeting beendet' : 'Meeting ended';
    if (type === 'recording') return isDE ? 'Neue Aufnahme' : 'New recording';
    if (type === 'chat') return isDE ? 'Neue Nachricht' : 'New message';
    return '';
  };

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="dashboard-page">
        <div className="max-w-5xl mx-auto">

          {/* Header */}
          <div className="mb-8">
            <p className="text-sm text-[#9CA3AF] mb-1" style={{ fontFamily: 'Work Sans' }}>{greeting()}</p>
            <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }} data-testid="welcome-heading">
              {user?.name || 'User'}
            </h1>
            <p className="text-[#9CA3AF] text-sm mt-1">
              {new Date().toLocaleDateString(isDE ? 'de-DE' : 'en-US', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
          </div>

          {/* Action-Required Widgets Row */}
          {(mandatoryUnread > 0 || pendingSurveys > 0 || (isReviewer && pendingReports > 0)) && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4" data-testid="action-widgets">
              {mandatoryUnread > 0 && (
                <button onClick={() => navigate('/news')}
                  className="flex items-center gap-3 p-3 bg-gradient-to-r from-[#C87967]/10 to-transparent border border-[#C87967]/30 rounded-xl hover:border-[#C87967]/50 transition-colors text-left group"
                  data-testid="mandatory-news-widget">
                  <div className="w-10 h-10 rounded-lg bg-[#C87967]/15 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                    <AlertTriangle className="w-5 h-5 text-[#C87967]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[9px] font-bold text-[#C87967] uppercase tracking-wider">
                      {isDE ? 'Pflicht zu lesen' : 'Mandatory read'}
                    </p>
                    <p className="text-sm font-medium text-[#1C1F1D]">
                      {mandatoryUnread} {isDE ? (mandatoryUnread === 1 ? 'Mitteilung' : 'Mitteilungen') : (mandatoryUnread === 1 ? 'notice' : 'notices')}
                    </p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[#C87967] group-hover:translate-x-1 transition-transform flex-shrink-0" />
                </button>
              )}
              {pendingSurveys > 0 && (
                <button onClick={() => navigate('/surveys')}
                  className="flex items-center gap-3 p-3 bg-gradient-to-r from-[#D4A373]/10 to-transparent border border-[#D4A373]/30 rounded-xl hover:border-[#D4A373]/50 transition-colors text-left group"
                  data-testid="pending-surveys-widget">
                  <div className="w-10 h-10 rounded-lg bg-[#D4A373]/15 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                    <ClipboardList className="w-5 h-5 text-[#D4A373]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[9px] font-bold text-[#D4A373] uppercase tracking-wider">
                      {isDE ? 'Offene Umfragen' : 'Open surveys'}
                    </p>
                    <p className="text-sm font-medium text-[#1C1F1D]">
                      {pendingSurveys} {isDE ? (pendingSurveys === 1 ? 'Umfrage' : 'Umfragen') : (pendingSurveys === 1 ? 'survey' : 'surveys')}
                    </p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[#D4A373] group-hover:translate-x-1 transition-transform flex-shrink-0" />
                </button>
              )}
              {isReviewer && pendingReports > 0 && (
                <button onClick={() => navigate('/admin?tab=news-moderation')}
                  className="flex items-center gap-3 p-3 bg-gradient-to-r from-[#C87967]/10 to-transparent border border-[#C87967]/30 rounded-xl hover:border-[#C87967]/50 transition-colors text-left group"
                  data-testid="pending-reports-widget">
                  <div className="w-10 h-10 rounded-lg bg-[#C87967]/15 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                    <Flag className="w-5 h-5 text-[#C87967]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[9px] font-bold text-[#C87967] uppercase tracking-wider">
                      {isDE ? 'Moderation' : 'Moderation'}
                    </p>
                    <p className="text-sm font-medium text-[#1C1F1D]">
                      {pendingReports} {isDE ? (pendingReports === 1 ? 'Meldung' : 'Meldungen') : (pendingReports === 1 ? 'report' : 'reports')}
                    </p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[#C87967] group-hover:translate-x-1 transition-transform flex-shrink-0" />
                </button>
              )}
            </div>
          )}

          {/* Top Row: Quick Actions + Resource Quick-Book (iter 294) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            {/* Quick Actions */}
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="quick-actions">
              <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider mb-3">
                {isDE ? 'Schnellzugriff' : 'Quick Actions'}
              </h3>
              <div className="grid grid-cols-2 gap-2">
                <button onClick={async () => {
                  try {
                    const { data } = await api.post('/meetings', { title: `${user?.name}'s Meeting`, meeting_type: 'instant' });
                    navigate(`/meetings/${data.meeting_id}/join`);
                  } catch {}
                }} className="flex items-center gap-2.5 p-3 rounded-lg bg-[#4A5D4E] text-white hover:bg-[#3E4E42] transition-colors active:scale-[0.97]"
                  data-testid="quick-instant">
                  <Zap className="w-4 h-4" />
                  <span className="text-xs font-medium">{t('startInstantMeeting')}</span>
                </button>
                <button onClick={() => { setTaskDialogId(null); setTaskDialogCreate(true); }}
                  data-testid="quick-new-task"
                  className="flex items-center gap-2.5 p-3 rounded-lg border border-[#4A5D4E]/30 bg-[#4A5D4E]/5 hover:border-[#4A5D4E]/60 transition-colors active:scale-[0.97]">
                  <ListChecks className="w-4 h-4 text-[#4A5D4E]" />
                  <span className="text-xs font-medium text-[#1C1F1D]">{isDE ? 'Neue Aufgabe' : 'New task'}</span>
                </button>
                <button onClick={() => navigate('/meetings/create')}
                  className="flex items-center gap-2.5 p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/30 transition-colors active:scale-[0.97]"
                  data-testid="quick-schedule">
                  <Calendar className="w-4 h-4 text-[#4A5D4E]" />
                  <span className="text-xs font-medium text-[#1C1F1D]">{t('scheduleMeeting')}</span>
                </button>
                <button onClick={() => navigate('/chat')}
                  className="flex items-center gap-2.5 p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/30 transition-colors active:scale-[0.97]"
                  data-testid="quick-chat">
                  <MessageCircle className="w-4 h-4 text-[#4A5D4E]" />
                  <span className="text-xs font-medium text-[#1C1F1D]">Chat</span>
                </button>
              </div>
            </div>

            {/* Ressourcen buchen — Schnellzugriff (iter 294) */}
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="resource-quick-book">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5" />
                  {isDE ? 'Ressourcen buchen' : 'Book a resource'}
                </h3>
                <button onClick={() => navigate('/resources')} className="text-[10px] text-[#4A5D4E] hover:underline flex items-center gap-0.5"
                  data-testid="dashboard-resources-link">
                  {isDE ? 'Alle' : 'All'} <ChevronRight className="w-3 h-3" />
                </button>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <button onClick={() => navigate('/resources?tab=rooms')}
                  className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/40 hover:bg-[#4A5D4E]/5 transition-colors active:scale-[0.97]"
                  data-testid="quick-book-rooms">
                  <Building2 className="w-5 h-5 text-[#4A5D4E]" />
                  <span className="text-xs font-medium text-[#1C1F1D]">{isDE ? 'Raum' : 'Room'}</span>
                </button>
                <button onClick={() => navigate('/resources?tab=desks')}
                  className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/40 hover:bg-[#4A5D4E]/5 transition-colors active:scale-[0.97]"
                  data-testid="quick-book-desks">
                  <Sofa className="w-5 h-5 text-[#4A5D4E]" />
                  <span className="text-xs font-medium text-[#1C1F1D]">{isDE ? 'Desk' : 'Desk'}</span>
                </button>
                <button onClick={() => navigate('/resources?tab=vehicles')}
                  className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/40 hover:bg-[#4A5D4E]/5 transition-colors active:scale-[0.97]"
                  data-testid="quick-book-vehicles">
                  <Car className="w-5 h-5 text-[#4A5D4E]" />
                  <span className="text-xs font-medium text-[#1C1F1D]">{isDE ? 'Fahrzeug' : 'Vehicle'}</span>
                </button>
              </div>
              <button onClick={() => navigate('/resources?tab=mine')}
                className="mt-2 w-full flex items-center justify-center gap-1.5 p-2 rounded-lg bg-[#F3F4F1] hover:bg-[#E8EAE6] transition-colors text-xs text-[#1C1F1D]"
                data-testid="quick-mine-bookings">
                <Inbox className="w-3.5 h-3.5" />
                {isDE ? 'Meine Buchungen' : 'My bookings'}
              </button>
            </div>
            {/* Iter 325 — Meine nächsten Buchungen (Räume, Desks, Fahrzeuge) */}
            <MyUpcomingBookingsWidget isDE={isDE} />
          </div>

          {/* Row 2: Meine Aufgaben (full width) */}
          <div className="grid grid-cols-1 gap-4 mb-4">
            {/* Meine Aufgaben — moved below in iter 294 */}
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-5 flex flex-col" data-testid="my-tasks-widget">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
                  <ListChecks className="w-3.5 h-3.5" />
                  {isDE ? 'Meine Aufgaben' : 'My Tasks'}
                  {myTasks.length > 0 && (
                    <span className="text-[10px] text-[#9CA3AF] font-normal normal-case ml-1">({myTasks.length})</span>
                  )}
                </h3>
                <button onClick={() => navigate('/tasks')} className="text-[10px] text-[#4A5D4E] hover:underline flex items-center gap-0.5"
                  data-testid="dashboard-tasks-link">
                  {isDE ? 'Alle' : 'All'} <ChevronRight className="w-3 h-3" />
                </button>
              </div>
              {myTasks.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center py-4">
                  <ListChecks className="w-8 h-8 text-[#E2E4E0] mb-1.5" />
                  <p className="text-xs text-[#9CA3AF] mb-2">{isDE ? 'Keine offenen Aufgaben' : 'No open tasks'}</p>
                  <button onClick={() => { setTaskDialogId(null); setTaskDialogCreate(true); }} data-testid="empty-create-task"
                    className="text-[11px] text-[#4A5D4E] hover:underline">
                    + {isDE ? 'Aufgabe erstellen' : 'Create task'}
                  </button>
                </div>
              ) : (
                <div className="space-y-1.5 flex-1">
                  {myTasks.map(t => {
                    const today = new Date().toISOString().slice(0, 10);
                    const overdue = t.due_date && t.due_date < today;
                    const PRIO_DOT = { urgent: '#C87967', high: '#D4A373', normal: '#4A5D4E', low: '#9CA3AF' };
                    return (
                      <div key={t.task_id} data-testid={`dash-task-${t.task_id}`}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[#F3F4F1] transition-colors group">
                        <button onClick={(e) => { e.stopPropagation(); toggleTaskDone(t.task_id, t.status); }}
                          data-testid={`dash-task-toggle-${t.task_id}`}
                          title={isDE ? 'Als erledigt markieren' : 'Mark done'}
                          className="flex-shrink-0">
                          {t.status === 'done'
                            ? <CheckSquare className="w-4 h-4 text-[#6B8E23]" />
                            : <Square className="w-4 h-4 text-[#9CA3AF] hover:text-[#4A5D4E]" />}
                        </button>
                        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: PRIO_DOT[t.priority] || '#4A5D4E' }} />
                        <button onClick={() => setTaskDialogId(t.task_id)} className="flex-1 min-w-0 text-left"
                          data-testid={`dash-task-open-${t.task_id}`}>
                          <p className="text-xs font-medium text-[#1C1F1D] truncate">{t.title}</p>
                          {t.due_date && (
                            <p className={`text-[10px] ${overdue ? 'text-[#C87967] font-medium' : 'text-[#9CA3AF]'}`}>
                              {overdue ? (isDE ? 'überfällig · ' : 'overdue · ') : ''}
                              {new Date(t.due_date).toLocaleDateString(isDE ? 'de-DE' : 'en-US', { day: '2-digit', month: 'short' })}
                            </p>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
          {/* End Row 2 (Meine Aufgaben) */}

          {/* Focus Time + Active Banner */}
          <div className="mb-4">
            {/* Iter 283 — Active-Booking Widget zeigt prominent Check-in/Check-out */}
            <ActiveBookingWidget />
            {/* In-Office-Today Widget (iter 238) — vor Focus-Time */}
            <div className="mb-3">
              <InOfficeWidget />
            </div>
            {/* Office-Week Widget (iter 242) — Team-Übersicht Mo–Fr */}
            <div className="mb-3">
              <OfficeWeekWidget />
            </div>
            {activeFocus && (
              <div className="mb-3 px-4 py-3 bg-[#4A5D4E]/8 border border-[#4A5D4E]/20 rounded-xl flex items-center gap-3" data-testid="focus-active-banner">
                <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/15 flex items-center justify-center flex-shrink-0">
                  <BellOff className="w-4 h-4 text-[#4A5D4E]" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[#4A5D4E]">{activeFocus.label}</p>
                  <p className="text-[10px] text-[#4A5D4E]/70">
                    {isDE ? 'Nicht stoeren aktiv bis' : 'Do not disturb until'} {formatTime(activeFocus.end_time)}
                  </p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => deleteFocus(activeFocus.focus_id)}
                  className="text-[#4A5D4E] hover:text-[#C87967] h-7 text-xs" data-testid="focus-end-btn">
                  {isDE ? 'Beenden' : 'End'}
                </Button>
              </div>
            )}
            <div className="bg-white border border-[#E2E4E0] rounded-xl" data-testid="focus-time-card">
              <div className="px-5 py-3 border-b border-[#E2E4E0]">
                <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
                  <Shield className="w-3.5 h-3.5" />
                  {isDE ? 'Fokus-Zeit' : 'Focus Time'}
                </h3>
              </div>
              <div className="px-5 py-3">
                {focusTimes.length === 0 ? (
                  <div className="flex items-center gap-3 py-1">
                    <BellOff className="w-5 h-5 text-[#E2E4E0] flex-shrink-0" />
                    <p className="text-xs text-[#9CA3AF]">{isDE ? 'Keine Fokus-Zeiten geplant' : 'No focus times planned'}</p>
                    <button onClick={() => setFocusDialogOpen(true)}
                      className="text-xs text-[#4A5D4E] hover:underline ml-auto font-medium" data-testid="focus-create-link">
                      {isDE ? 'Erstellen' : 'Create'}
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2 items-center">
                    {focusTimes.slice(0, 6).map(ft => {
                      const start = new Date(ft.start_time);
                      const end = new Date(ft.end_time);
                      const isActive = new Date() >= start && new Date() <= end;
                      return (
                        <div key={ft.focus_id}
                          className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs ${isActive ? 'bg-[#4A5D4E]/10 border border-[#4A5D4E]/25 text-[#4A5D4E]' : 'bg-[#F3F4F1] text-[#6B7280]'} group`}
                          data-testid={`focus-${ft.focus_id}`}>
                          {isActive && <div className="w-1.5 h-1.5 rounded-full bg-[#4A5D4E] animate-pulse" />}
                          <span className="font-medium">{ft.label}</span>
                          <span className="opacity-60">
                            {start.toLocaleDateString(isDE ? 'de-DE' : 'en-US', { day: '2-digit', month: '2-digit' })} {formatTime(ft.start_time)}-{formatTime(ft.end_time)}
                          </span>
                          <button onClick={() => deleteFocus(ft.focus_id)}
                            className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-[#C87967]"
                            data-testid={`focus-delete-${ft.focus_id}`}>
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      );
                    })}
                    <button onClick={() => setFocusDialogOpen(true)}
                      className="text-xs text-[#4A5D4E] hover:underline ml-auto font-medium"
                      data-testid="focus-create-link-inline">
                      {isDE ? 'Erstellen' : 'Create'}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Main Grid: Today + This Week */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">

            {/* Today Card */}
            <div className="bg-white border border-[#E2E4E0] rounded-xl" data-testid="today-card">
              <div className="px-5 py-4 border-b border-[#E2E4E0] flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
                  {isDE ? 'Heute' : 'Today'}
                </h2>
                <Badge className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E] px-2 py-0.5">
                  {agenda?.meetings_today ?? 0} {isDE ? 'Termine' : 'events'}
                </Badge>
              </div>
              <div className="p-4">
                {!agenda || agenda.today.length === 0 ? (
                  <div className="text-center py-8">
                    <Calendar className="w-10 h-10 text-[#E2E4E0] mx-auto mb-2" />
                    <p className="text-xs text-[#9CA3AF]">{isDE ? 'Keine Termine heute' : 'No events today'}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {agenda.today.map(m => (
                      <button key={m.meeting_id} onClick={() => navigate(`/meetings/${m.meeting_id}/join`)}
                        className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-[#F3F4F1] transition-colors text-left group"
                        data-testid={`today-${m.meeting_id}`}>
                        <div className="flex-shrink-0">
                          {m.status === 'active' ? (
                            <div className="w-9 h-9 rounded-lg bg-[#E25C5C]/10 flex items-center justify-center">
                              <div className="w-2.5 h-2.5 rounded-full bg-[#E25C5C] animate-pulse" />
                            </div>
                          ) : (
                            <div className="w-9 h-9 rounded-lg bg-[#4A5D4E]/8 flex items-center justify-center">
                              <span className="text-xs font-semibold text-[#4A5D4E]">{formatTime(m.scheduled_at)}</span>
                            </div>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-[#1C1F1D] truncate">{m.title}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            {m.status === 'active' && <Badge className="text-[9px] bg-[#E25C5C]/10 text-[#E25C5C] px-1.5 py-0">LIVE</Badge>}
                            {m.duration > 0 && <span className="text-[10px] text-[#9CA3AF]">{m.duration} min</span>}
                            {m.participant_count > 0 && (
                              <span className="text-[10px] text-[#9CA3AF] flex items-center gap-0.5">
                                <Users className="w-2.5 h-2.5" />{m.participant_count}
                              </span>
                            )}
                          </div>
                        </div>
                        <ArrowRight className="w-4 h-4 text-[#9CA3AF] opacity-0 group-hover:opacity-100 transition-opacity" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* This Week Card */}
            <div className="bg-white border border-[#E2E4E0] rounded-xl" data-testid="week-card">
              <div className="px-5 py-4 border-b border-[#E2E4E0] flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
                  {isDE ? 'Diese Woche' : 'This Week'}
                </h2>
                <button onClick={() => navigate('/calendar')} className="text-[10px] text-[#4A5D4E] hover:underline flex items-center gap-0.5">
                  {isDE ? 'Kalender' : 'Calendar'} <ChevronRight className="w-3 h-3" />
                </button>
              </div>
              <div className="p-4">
                {!agenda || agenda.week_days.length === 0 ? (
                  <div className="text-center py-8">
                    <Calendar className="w-10 h-10 text-[#E2E4E0] mx-auto mb-2" />
                    <p className="text-xs text-[#9CA3AF]">{isDE ? 'Keine weiteren Termine diese Woche' : 'No more events this week'}</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {agenda.week_days.map(day => (
                      <div key={day.date}>
                        <p className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider mb-1.5">{day.label}</p>
                        <div className="space-y-1">
                          {day.meetings.map(m => (
                            <button key={m.meeting_id} onClick={() => navigate(`/meetings/${m.meeting_id}/join`)}
                              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-[#F3F4F1] transition-colors text-left group"
                              data-testid={`week-${m.meeting_id}`}>
                              <span className="text-xs text-[#9CA3AF] w-12 flex-shrink-0">{formatTime(m.scheduled_at)}</span>
                              <p className="text-sm text-[#1C1F1D] truncate flex-1">{m.title}</p>
                              <ArrowUpRight className="w-3.5 h-3.5 text-[#9CA3AF] opacity-0 group-hover:opacity-100 transition-opacity" />
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="mt-4">
            <div className="bg-white border border-[#E2E4E0] rounded-xl" data-testid="recent-activity">
              <div className="px-5 py-4 border-b border-[#E2E4E0]">
                <h3 className="text-xs font-bold text-[#6B7280] uppercase tracking-wider">
                  {isDE ? 'Letzte Aktivitaeten' : 'Recent Activity'}
                </h3>
              </div>
              <div className="p-4">
                {!agenda || agenda.recent.length === 0 ? (
                  <p className="text-center text-xs text-[#9CA3AF] py-6">{isDE ? 'Keine Aktivitaeten' : 'No recent activity'}</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
                    {agenda.recent.map((a, i) => (
                      <button key={i} onClick={() => {
                        if (a.type === 'chat') navigate(`/chat?conv=${a.id}`);
                        else if (a.type === 'recording') navigate('/recordings');
                        else navigate(`/meetings/${a.id}/summary`);
                      }} className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#F3F4F1] transition-colors text-left"
                        data-testid={`activity-${i}`}>
                        <div className="w-7 h-7 rounded-full bg-[#F3F4F1] flex items-center justify-center flex-shrink-0">
                          {activityIcon(a.type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-[#1C1F1D] truncate">{a.title}</p>
                          <p className="text-[10px] text-[#9CA3AF] truncate">
                            {activityLabel(a.type)}
                            {a.detail ? ` - ${a.detail}` : ''}
                          </p>
                        </div>
                        <span className="text-[10px] text-[#9CA3AF] flex-shrink-0">{formatRelative(a.time)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Focus Time Dialog */}
      <Dialog open={focusDialogOpen} onOpenChange={setFocusDialogOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle className="text-base font-medium flex items-center gap-2">
              <Shield className="w-4 h-4 text-[#4A5D4E]" />
              {isDE ? 'Fokus-Zeit erstellen' : 'Create Focus Time'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div>
              <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">
                {isDE ? 'Bezeichnung' : 'Label'}
              </label>
              <Input value={focusLabel} onChange={e => setFocusLabel(e.target.value)}
                placeholder={isDE ? 'z.B. Deep Work, Mittagspause...' : 'e.g. Deep Work, Lunch...'}
                className="border-[#E2E4E0] rounded-xl" data-testid="focus-label-input" />
            </div>
            <div>
              <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">
                {isDE ? 'Datum' : 'Date'}
              </label>
              <Input type="date" value={focusDate} onChange={e => setFocusDate(e.target.value)}
                className="border-[#E2E4E0] rounded-xl" data-testid="focus-date-input" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">
                  {isDE ? 'Von' : 'From'}
                </label>
                <Input type="time" value={focusStart} onChange={e => setFocusStart(e.target.value)}
                  className="border-[#E2E4E0] rounded-xl" data-testid="focus-start-input" />
              </div>
              <div>
                <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">
                  {isDE ? 'Bis' : 'Until'}
                </label>
                <Input type="time" value={focusEnd} onChange={e => setFocusEnd(e.target.value)}
                  className="border-[#E2E4E0] rounded-xl" data-testid="focus-end-input" />
              </div>
            </div>

            {/* Iter 279 — Recurrence */}
            <div>
              <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">
                {isDE ? 'Wiederholung' : 'Recurrence'}
              </label>
              <div className="grid grid-cols-3 gap-2" data-testid="focus-recurrence-group">
                {[
                  { v: 'none',   de: 'Einmalig',  en: 'Once' },
                  { v: 'daily',  de: 'Täglich',  en: 'Daily' },
                  { v: 'weekly', de: 'Wöchentlich', en: 'Weekly' },
                ].map(opt => (
                  <button
                    key={opt.v}
                    type="button"
                    data-testid={`focus-rec-${opt.v}`}
                    onClick={() => setFocusRecurrence(opt.v)}
                    className={`h-9 rounded-full text-xs font-medium border transition-all ${
                      focusRecurrence === opt.v
                        ? 'bg-[#4A5D4E] text-white border-[#4A5D4E]'
                        : 'bg-white text-[#1C1F1D] border-[#E2E4E0] hover:bg-[#F3F4F1]'
                    }`}
                  >
                    {isDE ? opt.de : opt.en}
                  </button>
                ))}
              </div>
            </div>

            {focusRecurrence !== 'none' && (
              <div data-testid="focus-until-block">
                <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">
                  {isDE ? 'Wiederholen bis' : 'Repeat until'}
                </label>
                <Input
                  type="date"
                  value={focusUntilDate}
                  min={focusDate || undefined}
                  onChange={e => setFocusUntilDate(e.target.value)}
                  className="border-[#E2E4E0] rounded-xl"
                  data-testid="focus-until-input"
                />
                <p className="text-[10px] text-[#9CA3AF] mt-1">
                  {isDE ? 'Es werden bis zu 365 Termine ab Startdatum angelegt.' : 'Up to 365 occurrences from the start date.'}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFocusDialogOpen(false)} className="rounded-full border-[#E2E4E0]">
              {isDE ? 'Abbrechen' : 'Cancel'}
            </Button>
            <Button onClick={createFocus} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="focus-save-btn">
              {isDE ? 'Erstellen' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Single merged TaskDetailDialog (iter 195) — handles both create + view */}
      <TaskDetailDialog
        taskId={taskDialogId}
        createMode={taskDialogCreate}
        users={taskUsers}
        open={taskDialogOpen}
        onClose={() => { setTaskDialogId(null); setTaskDialogCreate(false); }}
        onChanged={fetchMyTasks}
        onCreated={(t) => { setTaskDialogCreate(false); setTaskDialogId(t.task_id); fetchMyTasks(); }}
      />
    </div>
  );
}

function StatCard({ testId, label, value, icon, accent, sub }) {
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 hover:border-[#4A5D4E]/20 transition-colors" data-testid={testId}>
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${accent}12` }}>
          <span style={{ color: accent }}>{icon}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xl font-semibold text-[#1C1F1D] tracking-tight" style={{ fontFamily: 'Manrope' }}>
            {value}
          </div>
          <p className="text-[10px] text-[#9CA3AF]">{label}</p>
        </div>
        {sub && <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full flex-shrink-0" style={{ backgroundColor: `${accent}12`, color: accent }}>{sub}</span>}
      </div>
    </div>
  );
}
