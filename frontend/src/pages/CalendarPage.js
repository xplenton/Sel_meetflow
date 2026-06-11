import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Calendar } from '../components/ui/calendar';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Video, Clock, Users, ChevronLeft, ChevronRight, ArrowRight, CalendarDays, List, Eye, Pencil, Trash2, Calendar as CalendarIcon, MapPin, ShieldX, CheckCircle2, Loader2, ClipboardList } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import api from '../lib/api';
import { toast } from 'sonner';
import { describeResource } from '../lib/bookingLabels';
import { flushSync } from 'react-dom';
import { format, isSameDay, startOfMonth, endOfMonth, parseISO } from 'date-fns';
import { de } from 'date-fns/locale';

export default function CalendarPage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState([]);
  const [externalEvents, setExternalEvents] = useState([]);
  const [resourceBookings, setResourceBookings] = useState([]);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [month, setMonth] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState('calendar');
  const [editMeeting, setEditMeeting] = useState(null);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDesc, setEditDesc] = useState('');

  const fetchMeetings = useCallback(async () => {
    try {
      const { data } = await api.get('/calendar/events');
      setMeetings(Array.isArray(data) ? data : []);
    } catch {} finally { setLoading(false); }
  }, []);

  // Load synced external calendar events (CalDAV / ICS)
  const fetchExternal = useCallback(async () => {
    try {
      const { data } = await api.get('/users/me/caldav-events', { params: { days: 90 } });
      setExternalEvents(data?.events || []);
    } catch { setExternalEvents([]); }
  }, []);

  // Load my resource bookings (rooms / desks / vehicles).
  const fetchResourceBookings = useCallback(async () => {
    try {
      const { data } = await api.get('/resource-bookings', { params: { mine_only: true } });
      setResourceBookings(Array.isArray(data) ? data : []);
    } catch { setResourceBookings([]); }
  }, []);

  // Track which external events are blocked (user-declared busy) so we can
  // show a badge + toggle between "block" / "unblock" actions.
  const [busyByEventHash, setBusyByEventHash] = useState({}); // event_hash -> slot_id
  const fetchBusy = useCallback(async () => {
    try {
      const { data } = await api.get('/users/me/busy-slots', { params: { start: new Date().toISOString().slice(0, 10) } });
      const map = {};
      (data?.slots || []).forEach(s => { if (s.source_id) map[s.source_id] = s.slot_id; });
      setBusyByEventHash(map);
    } catch { setBusyByEventHash({}); }
  }, []);

  const [eventDialog, setEventDialog] = useState(null); // selected external event or null
  const [blocking, setBlocking] = useState(false);
  const blockEvent = async (ev) => {
    setBlocking(true);
    try {
      // Ensure end > start — all-day events or events with missing end
      // default to a full-day block on the event's day.
      let endIso = ev.end;
      if (!endIso || endIso === ev.start) {
        const startD = new Date(ev.start);
        const endD = new Date(startD);
        endD.setHours(23, 59, 0, 0);
        endIso = endD.toISOString();
      }
      const { data } = await api.post('/users/me/busy-slots', {
        start: ev.start, end: endIso,
        title: ev.summary || 'Extern blockiert',
        source: 'caldav', source_id: ev.event_hash,
      });
      setBusyByEventHash(prev => ({ ...prev, [ev.event_hash]: data.slot_id }));
      toast.success('Zeit als blockiert markiert');
    } catch { toast.error('Blockieren fehlgeschlagen'); }
    finally { setBlocking(false); }
  };
  const unblockEvent = async (ev) => {
    const slotId = busyByEventHash[ev.event_hash];
    if (!slotId) return;
    setBlocking(true);
    try {
      await api.delete(`/users/me/busy-slots/${slotId}`);
      setBusyByEventHash(prev => {
        const c = { ...prev }; delete c[ev.event_hash]; return c;
      });
      toast.success('Blockierung aufgehoben');
    } catch { toast.error('Aufheben fehlgeschlagen'); }
    finally { setBlocking(false); }
  };

  useEffect(() => { fetchMeetings(); fetchExternal(); fetchBusy(); fetchResourceBookings(); }, [fetchMeetings, fetchExternal, fetchBusy, fetchResourceBookings]);

  const meetingDates = useMemo(() => {
    const dates = new Set();
    meetings.forEach(m => {
      const d = m.scheduled_at || m.created_at;
      if (d) dates.add(format(new Date(d), 'yyyy-MM-dd'));
    });
    return dates;
  }, [meetings]);

  const selectedDayMeetings = useMemo(() => {
    return meetings.filter(m => {
      const d = m.scheduled_at || m.created_at;
      return d && isSameDay(new Date(d), selectedDate);
    });
  }, [meetings, selectedDate]);

  const externalDates = useMemo(() => {
    const dates = new Set();
    externalEvents.forEach(e => { if (e.start) dates.add(format(new Date(e.start), 'yyyy-MM-dd')); });
    return dates;
  }, [externalEvents]);

  const selectedDayExternal = useMemo(() => {
    return externalEvents
      .filter(e => e.start && isSameDay(new Date(e.start), selectedDate))
      .sort((a, b) => new Date(a.start) - new Date(b.start));
  }, [externalEvents, selectedDate]);

  const selectedDayBookings = useMemo(() => {
    return resourceBookings
      .filter(b => b.start_at && isSameDay(new Date(b.start_at), selectedDate)
        && ['confirmed', 'pending_approval'].includes(b.status))
      .sort((a, b) => new Date(a.start_at) - new Date(b.start_at));
  }, [resourceBookings, selectedDate]);

  const allMeetingsSorted = useMemo(() => {
    return [...meetings].sort((a, b) => {
      const da = a.scheduled_at || a.created_at;
      const db = b.scheduled_at || b.created_at;
      return new Date(db) - new Date(da);
    });
  }, [meetings]);

  const statusColor = { active: 'bg-[#6B8E23]/10 text-[#6B8E23]', scheduled: 'bg-[#D4A373]/10 text-[#D4A373]', ended: 'bg-[#9CA3AF]/10 text-[#9CA3AF]' };

  const formatTime = (iso) => {
    if (!iso) return '';
    return format(new Date(iso), 'HH:mm');
  };

  const formatDateFull = (iso) => {
    if (!iso) return '';
    return format(new Date(iso), 'dd. MMM yyyy, HH:mm', { locale: de });
  };

  const handleDelete = async (meetingId) => {
    if (!window.confirm('Meeting wirklich löschen?')) return;
    try {
      await api.delete(`/meetings/${meetingId}`);
      toast.success('Meeting gelöscht');
      fetchMeetings();
    } catch {
      toast.error('Löschen fehlgeschlagen');
    }
  };

  const openEdit = (m) => {
    setEditMeeting(m);
    setEditTitle(m.title || '');
    setEditDesc(m.description || '');
    setEditDialogOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!editMeeting) return;
    try {
      await api.put(`/meetings/${editMeeting.meeting_id}`, { title: editTitle, description: editDesc });
      flushSync(() => setEditDialogOpen(false));
      setTimeout(() => { toast.success('Meeting aktualisiert'); setEditMeeting(null); }, 50);
      fetchMeetings();
    } catch {
      toast.error('Fehler beim Aktualisieren');
    }
  };

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="calendar-page">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{t('calendarView')}</h1>
            <div className="flex gap-2">
              <Button size="sm" variant={viewMode === 'calendar' ? 'default' : 'outline'} data-testid="calendar-view-btn"
                onClick={() => setViewMode('calendar')}
                className={viewMode === 'calendar' ? 'bg-[#4A5D4E] text-white rounded-lg' : 'rounded-lg border-[#E2E4E0]'}>
                <CalendarDays className="w-4 h-4 mr-1" /> {t('month')}
              </Button>
              <Button size="sm" variant={viewMode === 'list' ? 'default' : 'outline'} data-testid="list-view-btn"
                onClick={() => setViewMode('list')}
                className={viewMode === 'list' ? 'bg-[#4A5D4E] text-white rounded-lg' : 'rounded-lg border-[#E2E4E0]'}>
                <List className="w-4 h-4 mr-1" /> {t('listView')}
              </Button>
            </div>
          </div>

          {viewMode === 'calendar' ? (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Calendar */}
              <div className="lg:col-span-7 bg-white border border-[#E2E4E0] rounded-xl p-6">
                <Calendar
                  mode="single"
                  selected={selectedDate}
                  onSelect={(d) => d && setSelectedDate(d)}
                  month={month}
                  onMonthChange={setMonth}
                  className="w-full"
                  modifiers={{
                    hasMeeting: (date) => meetingDates.has(format(date, 'yyyy-MM-dd')),
                    hasExternal: (date) => {
                      const key = format(date, 'yyyy-MM-dd');
                      return externalDates.has(key) && !meetingDates.has(key);
                    },
                  }}
                  modifiersClassNames={{
                    hasMeeting: 'bg-[#4A5D4E]/10 font-bold text-[#4A5D4E] rounded-lg',
                    hasExternal: 'bg-[repeating-linear-gradient(45deg,transparent,transparent_3px,rgba(156,163,175,0.25)_3px,rgba(156,163,175,0.25)_5px)] text-[#6B7280] rounded-lg',
                  }}
                  data-testid="meeting-calendar"
                />
                {/* Legend */}
                {(meetingDates.size > 0 || externalDates.size > 0) && (
                  <div className="flex items-center gap-4 mt-3 text-[11px] text-[#9CA3AF]" data-testid="calendar-legend">
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded bg-[#4A5D4E]/20" /> Meeting
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded" style={{ background: 'repeating-linear-gradient(45deg,transparent,transparent 3px,rgba(156,163,175,0.35) 3px,rgba(156,163,175,0.35) 5px)' }} />
                      Externer Termin
                    </span>
                  </div>
                )}
              </div>

              {/* Day detail */}
              <div className="lg:col-span-5">
                <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
                  <h3 className="text-sm font-medium text-[#1C1F1D] mb-4" data-testid="selected-date-heading">
                    {format(selectedDate, 'EEEE, d. MMMM yyyy', { locale: de })}
                  </h3>
                  {selectedDayMeetings.length === 0 ? (
                    <div className="text-center py-8">
                      <CalendarDays className="w-10 h-10 text-[#E2E4E0] mx-auto mb-2" />
                      <p className="text-[#9CA3AF] text-sm">{t('noMeetingsOnDate')}</p>
                    </div>
                  ) : (
                    <div className="space-y-3">                      {selectedDayMeetings.map(m => {
                        // iter 194 — task events render differently: no join/edit
                        // buttons (synthetic id has no /meetings/<id> route),
                        // single "Öffnen" action navigates to /tasks/<id>.
                        if (m.meeting_type === 'task' && m.from_task) {
                          const prio = m.task_priority || 'normal';
                          const prioColor = { urgent: '#C87967', high: '#D4A373', normal: '#4A5D4E', low: '#9CA3AF' }[prio] || '#4A5D4E';
                          const STATUS_DE = { open: 'Offen', in_progress: 'In Bearbeitung', blocked: 'Wartend', done: 'Erledigt' };
                          const cleanTitle = (m.title || '').replace(/^📋\s*/, '');
                          return (
                            <button
                              key={m.meeting_id}
                              type="button"
                              onClick={() => navigate(`/tasks/${m.from_task}`)}
                              data-testid={`cal-task-${m.from_task}`}
                              className="w-full text-left p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/30 transition-colors bg-white">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: prioColor }} />
                                <span className="text-[10px] uppercase tracking-wider text-[#9CA3AF] font-bold">Aufgabe</span>
                                <span className="text-sm font-medium text-[#1C1F1D] truncate flex-1">{cleanTitle}</span>
                                <Badge className="text-[10px] bg-[#F3F4F1] text-[#4B5563]">{STATUS_DE[m.task_status] || m.task_status}</Badge>
                              </div>
                              <div className="flex items-center gap-3 text-xs text-[#9CA3AF]">
                                <span className="flex items-center gap-1"><Clock className="w-3 h-3" />Fällig am {format(new Date(m.scheduled_at), 'dd.MM.yyyy', { locale: de })}</span>
                                <span className="text-[#4A5D4E] hover:underline ml-auto">Öffnen →</span>
                              </div>
                            </button>
                          );
                        }
                        return (
                        <div key={m.meeting_id} className="p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/30 transition-colors"
                          data-testid={`cal-meeting-${m.meeting_id}`}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-[#1C1F1D] truncate">{m.title}</span>
                            <div className="flex gap-1">
                              {m.meeting_type === 'booking' && (
                                <Badge className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E]">Buchung</Badge>
                              )}
                              <Badge className={`text-[10px] ${statusColor[m.status] || ''}`}>{t(m.status)}</Badge>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-[#9CA3AF] mb-2">
                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{formatTime(m.scheduled_at || m.created_at)}</span>
                            <span>{m.duration} min</span>
                            {m.guest_name && <span className="text-[#4A5D4E]">mit {m.guest_name}</span>}
                          </div>
                          {(m.status === 'active' || m.status === 'scheduled') && (
                            <div className="flex gap-1.5">
                              <Button size="sm" onClick={() => navigate(`/meetings/${m.meeting_id}/join`)} data-testid={`cal-join-${m.meeting_id}`}
                                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs h-7 px-3">
                                {t('join')} <ArrowRight className="w-3 h-3 ml-1" />
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => navigate(`/meetings/${m.meeting_id}/live`)}
                                className="text-[#6B7280] h-7 px-2 text-xs" title="Ansehen" data-testid={`cal-view-${m.meeting_id}`}>
                                <Eye className="w-3 h-3" />
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => openEdit(m)}
                                className="text-[#6B7280] h-7 px-2 text-xs" title="Bearbeiten" data-testid={`cal-edit-${m.meeting_id}`}>
                                <Pencil className="w-3 h-3" />
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => handleDelete(m.meeting_id)}
                                className="text-[#C87967] h-7 px-2 text-xs" data-testid={`cal-delete-${m.meeting_id}`}>
                                <Trash2 className="w-3 h-3" />
                              </Button>
                            </div>
                          )}
                          {m.status === 'ended' && (
                            <div className="flex gap-1.5">
                              <Button size="sm" variant="ghost" onClick={() => navigate(`/meetings/${m.meeting_id}/attendance`)}
                                className="text-[#6B7280] h-7 px-2 text-xs" data-testid={`cal-view-${m.meeting_id}`}>
                                <Eye className="w-3 h-3 mr-1" />Ansicht
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => handleDelete(m.meeting_id)}
                                className="text-[#C87967] h-7 px-2 text-xs" data-testid={`cal-delete-${m.meeting_id}`}>
                                <Trash2 className="w-3 h-3" />
                              </Button>
                            </div>
                          )}
                        </div>
                        );
                      })}
                    </div>
                  )}

                  {/* External calendar events (CalDAV/ICS) - dezente Hintergrund-Blöcke */}
                  {selectedDayExternal.length > 0 && (
                    <div className="mt-5 pt-4 border-t border-[#E2E4E0]" data-testid="external-events-block">
                      <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#9CA3AF] mb-2 flex items-center gap-1.5">
                        <CalendarIcon className="w-3 h-3" />
                        Externer Kalender ({selectedDayExternal.length})
                      </p>
                      <div className="space-y-1.5">
                        {selectedDayExternal.map((e, i) => {
                          const isBlocked = !!busyByEventHash[e.event_hash];
                          return (
                            <button
                              type="button"
                              key={e.event_hash || i}
                              onClick={() => setEventDialog(e)}
                              className={`w-full text-left p-2 pl-3 rounded-md text-xs border-l-4 transition-colors ${
                                isBlocked
                                  ? 'border-[#C87967] bg-[#C87967]/5 hover:bg-[#C87967]/10'
                                  : 'border-[#9CA3AF]/40 bg-[repeating-linear-gradient(45deg,transparent,transparent_4px,rgba(156,163,175,0.12)_4px,rgba(156,163,175,0.12)_6px)] hover:bg-[#F3F4F1]'
                              }`}
                              data-testid={`external-event-${i}`}>
                              <div className="flex items-start justify-between gap-2">
                                <span className="text-[#6B7280] font-medium truncate flex items-center gap-1.5">
                                  {isBlocked && <ShieldX className="w-3 h-3 text-[#C87967] shrink-0" />}
                                  {e.summary}
                                </span>
                                <span className="text-[#9CA3AF] shrink-0 font-mono text-[10px]">
                                  {e.all_day ? 'ganztägig' : `${format(new Date(e.start), 'HH:mm')}${e.end ? `–${format(new Date(e.end), 'HH:mm')}` : ''}`}
                                </span>
                              </div>
                              {e.location && (
                                <div className="text-[10px] text-[#9CA3AF] mt-0.5 flex items-center gap-1 truncate">
                                  <MapPin className="w-2.5 h-2.5 shrink-0" /> {e.location}
                                </div>
                              )}
                              {isBlocked && (
                                <div className="text-[10px] text-[#C87967] mt-1 font-medium">{t('blockedForBookings')}</div>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Resource bookings (rooms / desks / vehicles) — Sprint 2 */}
                  {selectedDayBookings.length > 0 && (
                    <div className="mt-5 pt-4 border-t border-[#E2E4E0]" data-testid="resource-bookings-block">
                      <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#9CA3AF] mb-2 flex items-center gap-1.5">
                        Ressourcen-Buchungen ({selectedDayBookings.length})
                      </p>
                      <div className="space-y-1.5">
                        {selectedDayBookings.map((bk, i) => {
                          // Iter 339 — Issue #2: zeige neben dem Buchungstitel
                          // den Klartext der Ressource. Sub-Räume zeigen jetzt
                          // "Großer Saal — Bereich A" statt nur den Parent oder
                          // den bloßen Sub-Namen.
                          const resLabel = describeResource(bk);
                          return (
                          <button
                            type="button"
                            key={bk.booking_id}
                            onClick={() => navigate('/resources?tab=mine')}
                            className="w-full text-left p-2 pl-3 rounded-md text-xs border-l-4 border-[#4A5D4E] bg-[#4A5D4E]/5 hover:bg-[#4A5D4E]/10 transition-colors"
                            data-testid={`calendar-booking-${bk.booking_id}`}>
                            <div className="flex items-start justify-between gap-2">
                              <span className="text-[#1C1F1D] font-medium truncate">{bk.title}</span>
                              <span className="text-[#9CA3AF] shrink-0 font-mono text-[10px]">
                                {format(new Date(bk.start_at), 'HH:mm')}–{format(new Date(bk.end_at), 'HH:mm')}
                              </span>
                            </div>
                            {resLabel && (
                              <div className="text-[10px] text-[#4A5D4E] mt-0.5 truncate" data-testid={`calendar-booking-resource-${bk.booking_id}`}>
                                {resLabel}
                              </div>
                            )}
                            <div className="text-[10px] text-[#6B7280] mt-0.5">
                              {bk.status === 'pending_approval' ? 'Wartet auf Freigabe' : 'Bestätigt'}
                            </div>
                          </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* List View */
            <div className="bg-white border border-[#E2E4E0] rounded-xl divide-y divide-[#E2E4E0]">
              {loading ? (
                <div className="text-center py-12 text-[#9CA3AF]">Loading...</div>
              ) : allMeetingsSorted.length === 0 ? (
                <div className="text-center py-12">
                  <CalendarDays className="w-10 h-10 text-[#E2E4E0] mx-auto mb-2" />
                  <p className="text-[#9CA3AF] text-sm">{t('noMeetings')}</p>
                </div>
              ) : allMeetingsSorted.map(m => {
                if (m.meeting_type === 'task' && m.from_task) {
                  const STATUS_DE = { open: 'Offen', in_progress: 'In Bearbeitung', blocked: 'Wartend', done: 'Erledigt' };
                  const cleanTitle = (m.title || '').replace(/^📋\s*/, '');
                  const prio = m.task_priority || 'normal';
                  const prioColor = { urgent: '#C87967', high: '#D4A373', normal: '#4A5D4E', low: '#9CA3AF' }[prio] || '#4A5D4E';
                  return (
                    <button key={m.meeting_id} type="button"
                      onClick={() => navigate(`/tasks/${m.from_task}`)}
                      data-testid={`list-task-${m.from_task}`}
                      className="w-full text-left flex items-center gap-4 p-4 hover:bg-[#F3F4F1] transition-colors">
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: prioColor + '20' }}>
                        <ClipboardList className="w-5 h-5" style={{ color: prioColor }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-[#1C1F1D] truncate">{cleanTitle}</span>
                          <Badge className="text-[10px] bg-[#F3F4F1] text-[#4B5563]">Aufgabe</Badge>
                          <Badge className="text-[10px] bg-[#E2E4E0] text-[#4B5563]">{STATUS_DE[m.task_status] || m.task_status}</Badge>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-[#9CA3AF]">
                          <span>Fällig {format(new Date(m.scheduled_at), 'dd.MM.yyyy', { locale: de })}</span>
                        </div>
                      </div>
                      <span className="text-xs text-[#4A5D4E]">Öffnen →</span>
                    </button>
                  );
                }
                return (
                <div key={m.meeting_id} className="flex items-center gap-4 p-4 hover:bg-[#F3F4F1] transition-colors"
                  data-testid={`list-meeting-${m.meeting_id}`}>
                  <div className="w-10 h-10 rounded-lg bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                    <Video className="w-5 h-5 text-[#4A5D4E]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-[#1C1F1D] truncate">{m.title}</span>
                      {m.meeting_type === 'booking' && <Badge className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E]">Buchung</Badge>}
                      <Badge className={`text-[10px] ${statusColor[m.status] || ''}`}>{t(m.status)}</Badge>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-[#9CA3AF]">
                      <span>{formatDateFull(m.scheduled_at || m.created_at)}</span>
                      <span>{m.duration} min</span>
                      {m.guest_name && <span className="text-[#4A5D4E]">mit {m.guest_name}</span>}
                    </div>
                  </div>
                  {(m.status === 'active' || m.status === 'scheduled') && (
                    <div className="flex gap-1">
                      <Button size="sm" onClick={() => navigate(`/meetings/${m.meeting_id}/join`)}
                        className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs h-8 px-4">
                        {t('join')}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => navigate(`/meetings/${m.meeting_id}/attendance`)}
                        className="text-[#6B7280] h-8 px-2"><Eye className="w-3.5 h-3.5" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(m.meeting_id)}
                        className="text-[#C87967] h-8 px-2"><Trash2 className="w-3.5 h-3.5" /></Button>
                    </div>
                  )}
                  {m.status === 'ended' && (
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => navigate(`/meetings/${m.meeting_id}/attendance`)}
                        className="text-[#6B7280] h-8 px-2 text-xs"><Eye className="w-3.5 h-3.5 mr-1" />Ansicht</Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(m.meeting_id)}
                        className="text-[#C87967] h-8 px-2"><Trash2 className="w-3.5 h-3.5" /></Button>
                    </div>
                  )}
                </div>
                );
              })}
            </div>
          )}
        </div>
      </main>

      {/* Edit Meeting Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle>{t('editMeeting')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">Titel</Label>
              <Input value={editTitle} onChange={e => setEditTitle(e.target.value)} className="border-[#E2E4E0] rounded-xl" data-testid="edit-meeting-title" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">Beschreibung</Label>
              <Input value={editDesc} onChange={e => setEditDesc(e.target.value)} className="border-[#E2E4E0] rounded-xl" data-testid="edit-meeting-desc" />
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setEditDialogOpen(false)} className="rounded-lg">Abbrechen</Button>
              <Button onClick={handleSaveEdit} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg" data-testid="save-edit-meeting">Speichern</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      {/* External Event Action Dialog: block / unblock for bookings */}
      <Dialog open={!!eventDialog} onOpenChange={(o) => !o && setEventDialog(null)}>
        <DialogContent className="sm:max-w-[460px]" data-testid="external-event-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CalendarIcon className="w-4 h-4 text-[#6B7280]" />
              Externer Termin
            </DialogTitle>
          </DialogHeader>
          {eventDialog && (
            <div className="space-y-4 pt-2">
              <div className="p-3 rounded-lg bg-[#F3F4F1] border border-[#E2E4E0]">
                <div className="text-sm font-medium text-[#1C1F1D]">{eventDialog.summary}</div>
                <div className="text-xs text-[#6B7280] mt-1 font-mono">
                  {eventDialog.start && format(new Date(eventDialog.start), 'EEE, dd.MM.yyyy HH:mm', { locale: de })}
                  {eventDialog.end && ` – ${format(new Date(eventDialog.end), 'HH:mm')}`}
                </div>
                {eventDialog.location && (
                  <div className="text-xs text-[#9CA3AF] mt-1 flex items-center gap-1">
                    <MapPin className="w-3 h-3" /> {eventDialog.location}
                  </div>
                )}
              </div>
              <p className="text-xs text-[#6B7280] leading-relaxed">
                {busyByEventHash[eventDialog.event_hash]
                  ? 'Diese Zeit ist derzeit für öffentliche Buchungen blockiert. Buchungsseiten zeigen diesen Slot nicht an.'
                  : 'Markiere diese Zeit als blockiert, damit sie in deinen öffentlichen Buchungsseiten (MeetFlow /book/…) nicht mehr verfügbar ist.'}
              </p>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => setEventDialog(null)} className="rounded-lg" data-testid="external-event-dialog-cancel">
                  Schließen
                </Button>
                {busyByEventHash[eventDialog.event_hash] ? (
                  <Button
                    disabled={blocking}
                    onClick={async () => { await unblockEvent(eventDialog); setEventDialog(null); }}
                    className="bg-white border border-[#C87967] text-[#C87967] hover:bg-[#C87967]/10 rounded-lg"
                    data-testid="external-event-unblock-btn">
                    {blocking ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-1.5" />}
                    Blockierung aufheben
                  </Button>
                ) : (
                  <Button
                    disabled={blocking}
                    onClick={async () => { await blockEvent(eventDialog); setEventDialog(null); }}
                    className="bg-[#C87967] hover:bg-[#B66957] text-white rounded-lg"
                    data-testid="external-event-block-btn">
                    {blocking ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <ShieldX className="w-4 h-4 mr-1.5" />}
                    Als blockiert markieren
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
