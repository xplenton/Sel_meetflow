import { copyToClipboard } from '../lib/clipboard';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { ArrowLeft, Plus, Trash2, ListChecks, Copy, MessageCircle, Mail } from 'lucide-react';
import { DateTimeInput, parseDateTime, combineDateTime } from '../components/DateTimeInput';
import ShareMenu from '../components/ShareMenu';
import api from '../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../contexts/LanguageContext';
export default function GeneralPollCreatePage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [pollType, setPollType] = useState('single');
  const [options, setOptions] = useState(['', '']);
  const [allowCustom, setAllowCustom] = useState(false);
  const [isAnonymous, setIsAnonymous] = useState(false);
  const [deadline, setDeadline] = useState('');
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  const addOption = () => setOptions(prev => [...prev, '']);
  const removeOption = (i) => setOptions(prev => prev.filter((_, idx) => idx !== i));
  const updateOption = (i, val) => setOptions(prev => prev.map((o, idx) => idx === i ? val : o));

  const handleSubmit = async () => {
    if (!title.trim()) { setTimeout(() => toast.error('Bitte Titel eingeben'), 50); return; }
    const validOpts = options.filter(o => o.trim());
    if (validOpts.length < 2) { setTimeout(() => toast.error('Mindestens 2 Optionen erforderlich'), 50); return; }
    setSaving(true);
    try {
      const { data } = await api.post('/general-polls', {
        title, description, poll_type: pollType, options: validOpts,
        allow_custom_options: allowCustom, is_anonymous: isAnonymous,
        deadline: deadline || null,
      });
      setResult(data);
      setTimeout(() => toast.success('Umfrage erstellt!'), 50);
    } catch (err) { setTimeout(() => toast.error(err.response?.data?.detail || 'Fehler'), 50); }
    finally { setSaving(false); }
  };

  const shareUrl = result ? `${window.location.origin}/survey/${result.share_token}` : '';

  if (result) {
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in">
          <div className="max-w-lg mx-auto text-center">
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-8">
              <div className="w-16 h-16 rounded-full bg-[#6B8E23]/10 flex items-center justify-center mx-auto mb-4">
                <ListChecks className="w-8 h-8 text-[#6B8E23]" />
              </div>
              <h2 className="text-xl font-medium text-[#1C1F1D] mb-2" style={{ fontFamily: 'Manrope' }}>Umfrage erstellt!</h2>
              <p className="text-sm text-[#9CA3AF] mb-6">{t('shareVoteLink')}</p>
              <div className="flex items-center gap-2 bg-[#F3F4F1] rounded-xl p-3 mb-4">
                <input readOnly value={shareUrl} className="flex-1 bg-transparent text-sm text-[#4B5563] outline-none" data-testid="survey-share-url" />
                <Button size="sm" onClick={() => { copyToClipboard(shareUrl); setTimeout(() => toast.success('Link kopiert'), 50); }}
                  className="bg-[#4A5D4E] text-white rounded-full px-4" data-testid="copy-survey-link">
                  <Copy className="w-3.5 h-3.5 mr-1" /> Kopieren
                </Button>
              </div>
              <div className="flex gap-3 justify-center mb-6">
                <Button variant="outline" onClick={() => {
                  const text = `Umfrage: ${title}\nHier abstimmen: ${shareUrl}`;
                  window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
                }} className="rounded-full border-[#E2E4E0] px-5 text-sm" data-testid="share-whatsapp-survey">
                  <MessageCircle className="w-4 h-4 mr-1.5 text-[#25D366]" /> WhatsApp
                </Button>
                <Button variant="outline" onClick={() => {
                  const subject = `Umfrage: ${title}`;
                  const body = `Hallo,\n\nbitte nimm an folgender Umfrage teil:\n\n${title}\n\nHier abstimmen: ${shareUrl}`;
                  window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
                }} className="rounded-full border-[#E2E4E0] px-5 text-sm" data-testid="share-email-survey">
                  <Mail className="w-4 h-4 mr-1.5 text-[#4A5D4E]" /> E-Mail
                </Button>
              </div>
              <div className="flex gap-3 justify-center">
                <Button variant="outline" onClick={() => navigate('/schedule')} className="rounded-full border-[#E2E4E0] px-5">{t('toOverview')}</Button>
                <Button onClick={() => navigate(`/survey/${result.share_token}`)} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-5" data-testid="view-survey">Ansehen</Button>
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
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="general-poll-create-page">
        <div className="max-w-2xl mx-auto">
          <button onClick={() => navigate('/schedule')} className="flex items-center gap-1.5 text-sm text-[#4B5563] hover:text-[#1C1F1D] mb-6">
            <ArrowLeft className="w-4 h-4" /> Zurück
          </button>
          <h1 className="text-2xl font-medium tracking-tight mb-6" style={{ fontFamily: 'Manrope' }}>{t('newPoll')}</h1>

          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-5">
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Frage / Titel *</Label>
              <Input data-testid="survey-title" value={title} onChange={e => setTitle(e.target.value)}
                placeholder="z.B. Welches Restaurant für das Teamessen?" className="border-[#E2E4E0] rounded-xl" />
            </div>

            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Beschreibung</Label>
              <Textarea data-testid="survey-description" value={description} onChange={e => setDescription(e.target.value)}
                placeholder="Optionale Details..." className="border-[#E2E4E0] rounded-xl min-h-[60px]" />
            </div>

            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Umfrage-Typ</Label>
              <Select value={pollType} onValueChange={setPollType}>
                <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="survey-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">{t('singleChoice')}</SelectItem>
                  <SelectItem value="multiple">Mehrfachauswahl</SelectItem>
                  <SelectItem value="priority">Priorisierung (Reihenfolge)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-2 block">Optionen *</Label>
              <div className="space-y-2">
                {options.map((opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-xs text-[#9CA3AF] w-5">{i + 1}.</span>
                    <Input value={opt} onChange={e => updateOption(i, e.target.value)}
                      placeholder={`Option ${i + 1}`} className="border-[#E2E4E0] rounded-lg flex-1 h-9 text-sm" data-testid={`option-${i}`} />
                    {options.length > 2 && (
                      <button onClick={() => removeOption(i)} className="p-1.5 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <Button variant="outline" size="sm" onClick={addOption} className="mt-2 rounded-full border-[#E2E4E0] text-xs" data-testid="add-option">
                <Plus className="w-3.5 h-3.5 mr-1" /> Option hinzufügen
              </Button>
            </div>

            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('deadlineOptional')}</Label>
              <DateTimeInput
                date={parseDateTime(deadline).date}
                time={parseDateTime(deadline).time}
                onDateChange={v => setDeadline(combineDateTime(v, parseDateTime(deadline).time || '23:59'))}
                onTimeChange={v => setDeadline(combineDateTime(parseDateTime(deadline).date, v))}
              />
            </div>

            <div className="space-y-3 pt-3 border-t border-[#E2E4E0]">
              {[
                ['allowCustom', 'Eigene Optionen erlauben', 'Teilnehmer können neue Optionen hinzufügen', allowCustom, setAllowCustom],
                ['isAnonymous', 'Anonyme Abstimmung', 'Teilnehmernamen werden nicht angezeigt', isAnonymous, setIsAnonymous],
              ].map(([key, label, desc, val, setVal]) => (
                <div key={key} className="flex items-center justify-between py-1">
                  <div><span className="text-sm text-[#1C1F1D]">{label}</span><p className="text-xs text-[#9CA3AF]">{desc}</p></div>
                  <Switch checked={val} onCheckedChange={setVal} data-testid={`toggle-${key}`} />
                </div>
              ))}
            </div>

            <Button onClick={handleSubmit} disabled={saving} data-testid="create-survey-submit"
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11 font-medium active:scale-95 transition-all">
              {saving ? 'Erstelle...' : 'Umfrage erstellen'}
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
