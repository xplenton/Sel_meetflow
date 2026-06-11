import { copyToClipboard } from '../lib/clipboard';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Textarea } from '../components/ui/textarea';
import { ArrowLeft, Plus, Trash2, CalendarClock, Copy, MessageCircle, Mail } from 'lucide-react';
import { DateInput, TimeInput, DateTimeInput, TimeRangeInput, parseDateTime, combineDateTime } from '../components/DateTimeInput';
import ShareMenu from '../components/ShareMenu';
import api from '../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../contexts/LanguageContext';
export default function ScheduleCreatePage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [slots, setSlots] = useState([{ date: '', start_time: '09:00', end_time: '10:00' }]);
  const [deadline, setDeadline] = useState('');
  const [allowMaybe, setAllowMaybe] = useState(true);
  const [allowSuggestions, setAllowSuggestions] = useState(false);
  const [isPrivate, setIsPrivate] = useState(false);
  const [password, setPassword] = useState('');
  const [createMeeting, setCreateMeeting] = useState(true);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  const addSlot = () => setSlots(prev => [...prev, { date: '', start_time: '09:00', end_time: '10:00' }]);
  const removeSlot = (i) => setSlots(prev => prev.filter((_, idx) => idx !== i));
  const updateSlot = (i, field, value) => setSlots(prev => prev.map((s, idx) => idx === i ? { ...s, [field]: value } : s));

  const handleSubmit = async () => {
    if (!title.trim()) { setTimeout(() => toast.error('Bitte Titel eingeben'), 50); return; }
    const validSlots = slots.filter(s => s.date && s.start_time && s.end_time);
    if (validSlots.length === 0) { setTimeout(() => toast.error('Mindestens ein Zeitfenster erforderlich'), 50); return; }
    setSaving(true);
    try {
      const { data } = await api.post('/schedule-polls', {
        title, description, time_slots: validSlots, deadline: deadline || null,
        allow_maybe: allowMaybe, allow_suggestions: allowSuggestions,
        is_private: isPrivate, password: password || null,
        create_meeting_on_confirm: createMeeting,
      });
      setResult(data);
      setTimeout(() => toast.success('Terminplanung erstellt!'), 50);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = Array.isArray(detail) ? detail.map(e => e.msg || JSON.stringify(e)).join(', ') : (typeof detail === 'string' ? detail : 'Fehler');
      setTimeout(() => toast.error(msg), 50);
    } finally { setSaving(false); }
  };

  const shareUrl = result ? `${window.location.origin}/poll/${result.share_token}` : '';

  if (result) {
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in">
          <div className="max-w-lg mx-auto text-center">
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-8">
              <div className="w-16 h-16 rounded-full bg-[#6B8E23]/10 flex items-center justify-center mx-auto mb-4">
                <CalendarClock className="w-8 h-8 text-[#6B8E23]" />
              </div>
              <h2 className="text-xl font-medium text-[#1C1F1D] mb-2" style={{ fontFamily: 'Manrope' }}>Terminplanung erstellt!</h2>
              <p className="text-sm text-[#9CA3AF] mb-6">{t('shareLinkWithParticipantsToVote')}</p>
              <div className="flex items-center gap-2 bg-[#F3F4F1] rounded-xl p-3 mb-4">
                <input readOnly value={shareUrl} className="flex-1 bg-transparent text-sm text-[#4B5563] outline-none" data-testid="share-url-input" />
                <Button size="sm" onClick={() => { copyToClipboard(shareUrl); setTimeout(() => toast.success('Link kopiert'), 50); }}
                  className="bg-[#4A5D4E] text-white rounded-full px-4" data-testid="copy-share-link">
                  <Copy className="w-3.5 h-3.5 mr-1" /> Kopieren
                </Button>
              </div>
              <div className="flex gap-3 justify-center mb-6">
                <Button variant="outline" onClick={() => {
                  const text = `Terminabstimmung: ${title}\nHier abstimmen: ${shareUrl}`;
                  window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
                }} className="rounded-full border-[#E2E4E0] px-5 text-sm" data-testid="share-whatsapp-create">
                  <MessageCircle className="w-4 h-4 mr-1.5 text-[#25D366]" /> WhatsApp
                </Button>
                <Button variant="outline" onClick={() => {
                  const subject = `Terminabstimmung: ${title}`;
                  const body = `Hallo,\n\nich lade dich zur Terminabstimmung ein:\n\n${title}\n\nHier abstimmen: ${shareUrl}`;
                  window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
                }} className="rounded-full border-[#E2E4E0] px-5 text-sm" data-testid="share-email-create">
                  <Mail className="w-4 h-4 mr-1.5 text-[#4A5D4E]" /> E-Mail
                </Button>
              </div>
              <div className="flex gap-3 justify-center">
                <Button variant="outline" onClick={() => navigate('/schedule')} className="rounded-full border-[#E2E4E0] px-5">{t('toOverview')}</Button>
                <Button onClick={() => navigate(`/schedule/${result.poll_id}`)} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-5" data-testid="view-poll-button">{t('viewResults')}</Button>
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="schedule-create-page">
        <div className="max-w-2xl mx-auto">
          <button onClick={() => navigate('/schedule')} className="flex items-center gap-1.5 text-sm text-[#4B5563] hover:text-[#1C1F1D] mb-6">
            <ArrowLeft className="w-4 h-4" /> Zurück
          </button>
          <h1 className="text-2xl font-medium tracking-tight mb-6" style={{ fontFamily: 'Manrope' }}>{t('newScheduling')}</h1>

          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-5">
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Titel *</Label>
              <Input data-testid="poll-title" value={title} onChange={e => setTitle(e.target.value)}
                placeholder="z.B. Team-Meeting Terminabstimmung" className="border-[#E2E4E0] rounded-xl" />
            </div>

            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Beschreibung</Label>
              <Textarea data-testid="poll-description" value={description} onChange={e => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung..." className="border-[#E2E4E0] rounded-xl min-h-[80px]" />
            </div>

            {/* Time Slots */}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-2 block">Zeitfenster *</Label>
              <div className="space-y-2">
                {slots.map((slot, i) => (
                  <div key={i} className="flex flex-col sm:flex-row sm:items-center gap-2 p-3 bg-[#F3F4F1] rounded-lg" data-testid={`slot-${i}`}>
                    <DateInput value={slot.date} onChange={v => updateSlot(i, 'date', v)} className="w-full sm:flex-1" data-testid={`slot-date-${i}`} />
                    <div className="flex items-center gap-2 w-full sm:w-auto sm:flex-1 min-w-0">
                      <TimeRangeInput
                        startTime={slot.start_time} endTime={slot.end_time}
                        onStartChange={v => updateSlot(i, 'start_time', v)}
                        onEndChange={v => updateSlot(i, 'end_time', v)}
                        className="flex-1"
                      />
                      {slots.length > 1 && (
                        <button onClick={() => removeSlot(i)} className="p-1.5 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967] flex-shrink-0">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <Button variant="outline" size="sm" onClick={addSlot} className="mt-2 rounded-full border-[#E2E4E0] text-xs" data-testid="add-slot-button">
                <Plus className="w-3.5 h-3.5 mr-1" /> Zeitfenster hinzufügen
              </Button>
            </div>

            {/* Deadline */}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('votingDeadlineOptional')}</Label>
              <DateTimeInput
                date={parseDateTime(deadline).date}
                time={parseDateTime(deadline).time}
                onDateChange={v => setDeadline(combineDateTime(v, parseDateTime(deadline).time || '23:59'))}
                onTimeChange={v => setDeadline(combineDateTime(parseDateTime(deadline).date, v))}
              />
            </div>

            {/* Options */}
            <div className="space-y-3 pt-3 border-t border-[#E2E4E0]">
              <h3 className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">Optionen</h3>
              {[
                ['allowMaybe', '"Vielleicht" erlauben', 'Teilnehmer können auch "Vielleicht" antworten', allowMaybe, setAllowMaybe],
                ['allowSuggestions', 'Vorschlaege erlauben', 'Teilnehmer können eigene Zeitfenster vorschlagen', allowSuggestions, setAllowSuggestions],
                ['createMeeting', 'Meeting automatisch erstellen', 'Bei Bestätigung wird ein MeetFlow-Meeting erstellt', createMeeting, setCreateMeeting],
                ['isPrivate', 'Passwortschutz', 'Umfrage nur mit Passwort zugänglich', isPrivate, setIsPrivate],
              ].map(([key, label, desc, val, setVal]) => (
                <div key={key} className="flex items-center justify-between py-1">
                  <div>
                    <span className="text-sm text-[#1C1F1D]">{label}</span>
                    <p className="text-xs text-[#9CA3AF]">{desc}</p>
                  </div>
                  <Switch checked={val} onCheckedChange={setVal} data-testid={`option-${key}`} />
                </div>
              ))}
              {isPrivate && (
                <Input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="Passwort eingeben" className="border-[#E2E4E0] rounded-xl max-w-xs" data-testid="poll-password" />
              )}
            </div>

            <Button onClick={handleSubmit} disabled={saving} data-testid="create-poll-submit"
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11 font-medium active:scale-95 transition-all">
              {saving ? 'Erstelle...' : 'Terminplanung erstellen'}
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
