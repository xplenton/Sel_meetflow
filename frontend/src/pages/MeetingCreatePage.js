import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { ArrowLeft, Users, UserPlus, Shield, BookmarkPlus, BookOpen, Trash2, Plus, X, CalendarDays, Eye, AlertTriangle, Sparkles, Loader2 } from 'lucide-react';
import { DateInput, TimeInput, parseDateTime, combineDateTime } from '../components/DateTimeInput';
import { CustomScheduleEditor, CustomDatesEditor } from '../components/meetings/CustomScheduleEditors';
import api from '../lib/api';
import { toast } from 'sonner';

function calcDuration(start, end) {
  if (!start || !end) return 60;
  const [sh, sm] = start.split(':').map(Number);
  const [eh, em] = end.split(':').map(Number);
  return Math.max(15, (eh * 60 + em) - (sh * 60 + sm));
}

function addMinutes(time, mins) {
  const [h, m] = time.split(':').map(Number);
  const total = h * 60 + m + mins;
  const nh = Math.floor(total / 60) % 24;
  const nm = total % 60;
  return `${String(nh).padStart(2, '0')}:${String(nm).padStart(2, '0')}`;
}

export default function MeetingCreatePage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [showSaveTemplate, setShowSaveTemplate] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [showTemplates, setShowTemplates] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', meeting_type: 'scheduled',
    scheduled_at: '', start_time: '09:00', end_time: '10:00',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    recurring: false, recurring_pattern: null,
    recurring_schedule: [], recurring_weeks: 8,
    recurring_dates: [],
    lobby_enabled: false, guest_access: true,
    meeting_mode: 'standard', chat_enabled: true,
    reactions_enabled: true, recording_enabled: false,
    transcript_enabled: false,
    invited_emails: '', optional_emails: '',
    reminder_minutes: 15,
  });

  const fetchTemplates = useCallback(async () => {
    try { const { data } = await api.get('/templates'); setTemplates(data); } catch {}
  }, []);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const loadTemplate = (tmpl) => {
    setForm(prev => ({
      ...prev, title: tmpl.title, description: tmpl.description || '',
      meeting_mode: tmpl.meeting_mode,
      lobby_enabled: tmpl.lobby_enabled, guest_access: tmpl.guest_access,
      chat_enabled: tmpl.chat_enabled, reactions_enabled: tmpl.reactions_enabled,
      recording_enabled: tmpl.recording_enabled, transcript_enabled: tmpl.transcript_enabled,
      recurring: tmpl.recurring, recurring_pattern: tmpl.recurring_pattern,
      recurring_schedule: tmpl.recurring_schedule || [],
      recurring_weeks: tmpl.recurring_weeks || prev.recurring_weeks,
      invited_emails: (tmpl.invited_emails || []).join(', '),
    }));
    setShowTemplates(false);
    toast.success(t('useTemplate') + ': ' + tmpl.name);
  };

  const saveAsTemplate = async () => {
    if (!templateName.trim()) return;
    try {
      await api.post('/templates', {
        name: templateName, title: form.title || templateName, description: form.description,
        duration: calcDuration(form.start_time, form.end_time), meeting_mode: form.meeting_mode,
        lobby_enabled: form.lobby_enabled, guest_access: form.guest_access,
        chat_enabled: form.chat_enabled, reactions_enabled: form.reactions_enabled,
        recording_enabled: form.recording_enabled, transcript_enabled: form.transcript_enabled,
        recurring: form.recurring, recurring_pattern: form.recurring_pattern,
        recurring_schedule: form.recurring_schedule || [],
        recurring_weeks: form.recurring_weeks,
        invited_emails: (form.invited_emails || '')
          .split(',').map(s => s.trim()).filter(Boolean),
      });
      toast.success(t('templateSaved'));
      setShowSaveTemplate(false); setTemplateName(''); fetchTemplates();
    } catch { toast.error('Vorlage konnte nicht gespeichert werden'); }
  };

  const deleteTemplate = async (id) => {
    try { await api.delete(`/templates/${id}`); toast.success(t('templateDeleted')); fetchTemplates(); } catch {}
  };

  const update = (key, val) => setForm(prev => ({ ...prev, [key]: val }));

  // Live conflict-check against the user's external calendar (CalDAV/ICS)
  const [conflicts, setConflicts] = useState([]);
  useEffect(() => {
    if (form.meeting_type !== 'scheduled' || !form.scheduled_at) { setConflicts([]); return; }
    const dur = calcDuration(form.start_time, form.end_time);
    const handle = setTimeout(() => {
      api.get('/meetings/conflicts', { params: { scheduled_at: form.scheduled_at, duration: dur } })
        .then(({ data }) => setConflicts(data.conflicts || []))
        .catch(() => setConflicts([]));
    }, 400);
    return () => clearTimeout(handle);
  }, [form.scheduled_at, form.start_time, form.end_time, form.meeting_type]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) { toast.error('Titel erforderlich'); return; }
    if (form.meeting_type === 'scheduled' && !form.scheduled_at) { toast.error('Datum & Uhrzeit erforderlich'); return; }
    setLoading(true);
    try {
      const duration = calcDuration(form.start_time, form.end_time);
      const invited = form.invited_emails ? form.invited_emails.split(',').map(e => e.trim()).filter(Boolean) : [];
      const optional = form.optional_emails ? form.optional_emails.split(',').map(e => e.trim()).filter(Boolean) : [];
      const payload = {
        title: form.title, description: form.description, meeting_type: form.meeting_type,
        scheduled_at: form.scheduled_at || null, duration_minutes: duration,
        timezone: form.timezone,
        recurring: form.recurring, recurring_pattern: form.recurring ? (form.recurring_pattern || 'weekly') : null,
        recurring_schedule: form.recurring && form.recurring_pattern === 'custom' ? form.recurring_schedule.filter(s => s.start_time && s.end_time) : [],
        recurring_weeks: form.recurring_weeks,
        recurring_dates: form.recurring && form.recurring_pattern === 'custom_dates' ? form.recurring_dates.filter(s => s.date && s.start_time && s.end_time) : [],
        lobby_enabled: form.lobby_enabled, guest_access: form.guest_access,
        meeting_mode: form.meeting_mode, chat_enabled: form.chat_enabled,
        reactions_enabled: form.reactions_enabled, recording_enabled: form.recording_enabled,
        transcript_enabled: form.transcript_enabled,
        invited_emails: invited, optional_emails: optional,
        reminder_minutes: form.reminder_minutes,
      };
      const { data } = await api.post('/meetings', payload);
      toast.success(t('meetingCreated'));
      setTimeout(() => {
        if (data.meeting_type === 'instant') {
          navigate(`/meetings/${data.meeting_id}/join`);
        } else {
          navigate('/schedule');
        }
      }, 100);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => d?.msg || JSON.stringify(d)).join(', ') : 'Fehler';
      toast.error(msg);
    } finally { setLoading(false); }
  };

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-3 pt-14 sm:p-4 md:p-8 animate-fade-in" data-testid="meeting-create-page">
        <div className="max-w-2xl mx-auto">
          <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-[#4B5563] hover:text-[#1C1F1D] mb-4 sm:mb-6" data-testid="back-to-dashboard">
            <ArrowLeft className="w-4 h-4" /> Zurück
          </button>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-5">
            <h1 className="text-xl sm:text-2xl font-medium tracking-tight" style={{ fontFamily: 'Manrope' }}>{t('scheduleMeeting')}</h1>
            <div className="flex gap-1.5">
              <Button variant="outline" size="sm" onClick={() => setShowTemplates(true)} data-testid="load-template-button"
                className="rounded-full border-[#E2E4E0] text-[10px] sm:text-xs h-8">
                <BookOpen className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">{t('templates')} ({templates.length})</span>
              </Button>
              <Button variant="outline" size="sm" onClick={() => setShowSaveTemplate(true)} data-testid="save-template-button"
                className="rounded-full border-[#E2E4E0] text-[10px] sm:text-xs h-8">
                <BookmarkPlus className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">{t('createTemplate')}</span>
              </Button>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-6">
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 sm:p-6 space-y-4 sm:space-y-5">
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('meetingTitle')}</Label>
                <Input data-testid="meeting-title-input" value={form.title} onChange={e => update('title', e.target.value)}
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" required />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('description')}</Label>
                <Textarea data-testid="meeting-description-input" value={form.description} onChange={e => update('description', e.target.value)}
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl min-h-[70px]" />
              </div>

              {/* Date + Time Von-Bis */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Datum</Label>
                  <DateInput data-testid="meeting-date-input"
                    value={parseDateTime(form.scheduled_at).date}
                    onChange={v => update('scheduled_at', combineDateTime(v, form.start_time || '09:00'))} />
                </div>
                <div>
                  <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Von</Label>
                  <TimeInput data-testid="meeting-start-time"
                    value={form.start_time}
                    onChange={v => {
                      update('start_time', v);
                      update('end_time', addMinutes(v, calcDuration(form.start_time, form.end_time)));
                      const d = parseDateTime(form.scheduled_at).date;
                      if (d) update('scheduled_at', combineDateTime(d, v));
                    }} />
                </div>
                <div>
                  <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Bis</Label>
                  <TimeInput data-testid="meeting-end-time"
                    value={form.end_time}
                    onChange={v => update('end_time', v)} />
                </div>
              </div>

              {conflicts.length > 0 && (
                <div className="bg-[#D4A373]/10 border border-[#D4A373]/40 rounded-xl p-3 flex items-start gap-2"
                  data-testid="meeting-conflict-warning">
                  <span className="text-[#D4A373] mt-0.5">⚠</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-[#D4A373]">
                      {conflicts.length === 1
                        ? 'Terminkonflikt mit externem Kalender'
                        : `${conflicts.length} Konflikte mit externem Kalender`}
                    </p>
                    <ul className="mt-1 space-y-0.5">
                      {conflicts.slice(0, 3).map((c, i) => (
                        <li key={`${c.start || ''}-${c.summary || ''}-${i}`} className="text-[11px] text-[#6B7280] truncate">
                          {c.summary} · {new Date(c.start).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                          {c.end && ` – ${new Date(c.end).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}`}
                          {c.location ? ` · ${c.location}` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('meetingMode')}</Label>
                <Select value={form.meeting_mode} onValueChange={v => update('meeting_mode', v)}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="meeting-mode-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="standard">{t('standard')}</SelectItem>
                    <SelectItem value="moderated">{t('moderated')}</SelectItem>
                    <SelectItem value="webinar">{t('webinar')}</SelectItem>
                    <SelectItem value="training">{t('training')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Participants */}
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                  <Users className="w-3.5 h-3.5 inline mr-1" />Erforderliche Teilnehmer
                </Label>
                <Input data-testid="meeting-invite-input" value={form.invited_emails} onChange={e => update('invited_emails', e.target.value)}
                  placeholder="email1@beispiel.de, email2@beispiel.de"
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                  <UserPlus className="w-3.5 h-3.5 inline mr-1" />Optionale Teilnehmer
                </Label>
                <Input data-testid="meeting-optional-input" value={form.optional_emails} onChange={e => update('optional_emails', e.target.value)}
                  placeholder="optional1@beispiel.de, optional2@beispiel.de"
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
                <p className="text-[10px] text-[#9CA3AF] mt-1">{t('optionalParticipantsHint')}</p>
              </div>
            </div>

            {/* Settings */}
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 sm:p-6 space-y-3 sm:space-y-4">
              <h3 className="text-sm font-medium text-[#1C1F1D] flex items-center gap-2"><Shield className="w-4 h-4 text-[#4A5D4E]" /> {t('settings')}</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                {[
                  ['lobby_enabled', t('lobbyEnabled')],
                  ['guest_access', t('guestAccess')],
                  ['chat_enabled', t('chatEnabled')],
                  ['reactions_enabled', t('reactionsEnabled')],
                  ['recording_enabled', t('recordingEnabled')],
                  ['transcript_enabled', t('transcriptEnabled')],
                  ['recurring', t('recurring')],
                ].map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between py-1.5">
                    <span className="text-xs sm:text-sm text-[#4B5563]">{label}</span>
                    <Switch data-testid={`toggle-${key}`} checked={form[key]} onCheckedChange={v => update(key, v)} />
                  </div>
                ))}
              </div>
              {form.recurring && (
                <div className="pt-2 border-t border-[#E2E4E0]">
                  <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('recurringPattern')}</Label>
                  <Select value={form.recurring_pattern || 'weekly'} onValueChange={v => update('recurring_pattern', v)}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="recurring-pattern-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="daily">{t('daily')}</SelectItem>
                      <SelectItem value="weekly">{t('weekly')}</SelectItem>
                      <SelectItem value="biweekly">{t('biweekly')}</SelectItem>
                      <SelectItem value="monthly">{t('monthly')}</SelectItem>
                      <SelectItem value="custom">Individuell (pro Wochentag)</SelectItem>
                      <SelectItem value="custom_dates">Individuell (spezifische Daten)</SelectItem>
                    </SelectContent>
                  </Select>

                  {form.recurring_pattern === 'custom' && (
                    <CustomScheduleEditor
                      schedule={form.recurring_schedule}
                      onChange={v => update('recurring_schedule', v)}
                      weeks={form.recurring_weeks}
                      onWeeksChange={v => update('recurring_weeks', v)}
                      scheduledDate={parseDateTime(form.scheduled_at).date}
                      startTime={form.start_time}
                    />
                  )}
                  {form.recurring_pattern === 'custom_dates' && (
                    <CustomDatesEditor
                      dates={form.recurring_dates}
                      onChange={v => update('recurring_dates', v)}
                      scheduledDate={parseDateTime(form.scheduled_at).date}
                      startTime={form.start_time}
                      endTime={form.end_time}
                    />
                  )}
                </div>
              )}
              <div className="pt-2 border-t border-[#E2E4E0]">
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Erinnerung</Label>
                <Select value={String(form.reminder_minutes)} onValueChange={v => update('reminder_minutes', parseInt(v))}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="reminder-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">{t('noReminder')}</SelectItem>
                    <SelectItem value="5">5 Minuten vorher</SelectItem>
                    <SelectItem value="10">10 Minuten vorher</SelectItem>
                    <SelectItem value="15">15 Minuten vorher</SelectItem>
                    <SelectItem value="30">30 Minuten vorher</SelectItem>
                    <SelectItem value="60">1 Stunde vorher</SelectItem>
                    <SelectItem value="1440">1 Tag vorher</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex gap-2 sm:gap-3 justify-end">
              <Button type="button" variant="outline" onClick={() => navigate(-1)} data-testid="cancel-meeting-button"
                className="rounded-full px-4 sm:px-6 border-[#E2E4E0] text-xs sm:text-sm">{t('cancel')}</Button>
              <Button type="submit" disabled={loading} data-testid="create-meeting-button"
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-4 sm:px-6 text-xs sm:text-sm">{loading ? '...' : t('create')}</Button>
            </div>
          </form>
        </div>
      </main>

      {/* Save Template Dialog */}
      <Dialog open={showSaveTemplate} onOpenChange={setShowSaveTemplate}>
        <DialogContent className="sm:max-w-[360px]">
          <DialogHeader><DialogTitle className="text-base font-medium">{t('createTemplate')}</DialogTitle></DialogHeader>
          <Input data-testid="template-name-input" value={templateName} onChange={e => setTemplateName(e.target.value)}
            placeholder={t('templateName')} className="border-[#E2E4E0] rounded-xl" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSaveTemplate(false)} className="rounded-full border-[#E2E4E0]">{t('cancel')}</Button>
            <Button onClick={saveAsTemplate} data-testid="confirm-save-template"
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full">
              <BookmarkPlus className="w-4 h-4 mr-1" /> Speichern
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Load Template Dialog */}
      <Dialog open={showTemplates} onOpenChange={setShowTemplates}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader><DialogTitle className="text-base font-medium">{t('templates')}</DialogTitle></DialogHeader>
          {templates.length === 0 ? (
            <div className="text-center py-6">
              <BookOpen className="w-8 h-8 text-[#E2E4E0] mx-auto mb-2" />
              <p className="text-sm text-[#9CA3AF]">{t('noTemplates')}</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {templates.map(tmpl => {
                const sched = tmpl.recurring_schedule || [];
                const weekdayShort = ['Mo','Di','Mi','Do','Fr','Sa','So'];
                const seriesLabel = sched.length
                  ? sched.map(s => `${weekdayShort[s.weekday] || '?'} ${s.start_time}`).join(', ')
                  : null;
                return (
                <div key={tmpl.template_id} className="flex items-center gap-3 p-3 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/30 transition-colors"
                  data-testid={`template-${tmpl.template_id}`}>
                  <div className="flex-1 min-w-0 cursor-pointer" onClick={() => loadTemplate(tmpl)}>
                    <span className="text-sm font-medium text-[#1C1F1D] block truncate">{tmpl.name}</span>
                    <span className="text-xs text-[#9CA3AF]">{tmpl.meeting_mode} - {tmpl.duration}min</span>
                    {seriesLabel && (
                      <span className="block text-[10px] text-[#4A5D4E] mt-0.5 truncate" data-testid={`template-series-${tmpl.template_id}`}>
                        Serie ({tmpl.recurring_weeks || 8} Wochen): {seriesLabel}
                      </span>
                    )}
                  </div>
                  <Button size="sm" onClick={() => loadTemplate(tmpl)} data-testid={`use-template-${tmpl.template_id}`}
                    className="bg-[#4A5D4E] text-white rounded-full text-xs h-7 px-3">{t('useTemplate')}</Button>
                  <button onClick={() => deleteTemplate(tmpl.template_id)} className="p-1 text-[#C87967] hover:bg-[#C87967]/10 rounded"
                    data-testid={`delete-template-${tmpl.template_id}`}><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
                );
              })}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

