import { useState, useEffect } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import AudiencePicker from '../AudiencePicker';
import AttachmentPicker from '../AttachmentPicker';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Switch } from '../ui/switch';
import {
  ClipboardList, Plus, BarChart3, MessageSquare, Check, CheckCircle, ChevronRight,
  Trash2, Send, X, Lightbulb, AlertCircle, HelpCircle,
  Smile, ThumbsUp, Download, Archive, Search,
} from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

const FEEDBACK_CATS = [
  { id: 'ideas', label: 'Ideen', icon: Lightbulb, color: '#6B8E23' },
  { id: 'complaints', label: 'Beschwerden', icon: AlertCircle, color: '#C87967' },
  { id: 'improvements', label: 'Verbesserungen', icon: ThumbsUp, color: '#4A5D4E' },
  { id: 'questions', label: 'Rueckfragen', icon: HelpCircle, color: '#D4A373' },
];

// ============================================================================
// SurveysPage sub-components, extracted during iter 218 refactor.
// All exports are named so that SurveysPage can import what it needs.
// Behaviour identical to the previous inline implementation.
// ============================================================================

export function StatMini({ label, value, accent = '#4A5D4E' }) {
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-3 flex items-center gap-3">
      <span className="text-xl font-semibold" style={{ color: accent, fontFamily: 'Manrope' }}>{value ?? 0}</span>
      <span className="text-[10px] text-[#9CA3AF]">{label}</span>
    </div>
  );
}

export function EmptyState({ icon: Icon, text }) {
  return (
    <div className="text-center py-12 bg-white border border-[#E2E4E0] rounded-xl">
      <Icon className="w-10 h-10 text-[#E2E4E0] mx-auto mb-2" />
      <p className="text-xs text-[#9CA3AF]">{text}</p>
    </div>
  );
}

export function SurveyCard({ survey, isDE, isEditor, onRespond, onResults, onDelete, onArchive, onRestore, archived }) {
  const s = survey;
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4" data-testid={`survey-${s.survey_id}`}>
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${s.survey_type === 'pulse_check' ? 'bg-[#D4A373]/10' : 'bg-[#4A5D4E]/10'}`}>
          {s.survey_type === 'pulse_check' ? <Smile className="w-5 h-5 text-[#D4A373]" /> : <ClipboardList className="w-5 h-5 text-[#4A5D4E]" />}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium text-[#1C1F1D] truncate">{s.title}</h3>
          <div className="flex items-center gap-2 text-[10px] text-[#9CA3AF] mt-0.5 flex-wrap">
            <span>{s.questions?.length || 0} {isDE ? 'Fragen' : 'questions'}</span>
            <span>{s.response_count} {isDE ? 'Teilnahmen' : 'responses'}</span>
            {s.anonymous && <Badge className="text-[9px] bg-[#9CA3AF]/10 text-[#9CA3AF] px-1 py-0">Anonym</Badge>}
            {s.participated && <Badge className="text-[9px] bg-[#6B8E23]/10 text-[#6B8E23] px-1 py-0"><Check className="w-2.5 h-2.5 mr-0.5" />Teilgenommen</Badge>}
            {archived && <Badge className="text-[9px] bg-[#9CA3AF]/10 text-[#9CA3AF] px-1 py-0">Archiviert</Badge>}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1.5 flex-wrap sm:flex-nowrap justify-end">
        {!archived && !s.participated && (
          <Button size="sm" onClick={onRespond} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs h-8 px-3" data-testid={`respond-${s.survey_id}`}>
            {isDE ? 'Teilnehmen' : 'Respond'}
          </Button>
        )}
        {(isEditor || s.participated) && (
          <Button size="sm" variant="outline" onClick={onResults} className="rounded-full text-xs h-8 px-3 border-[#E2E4E0]" data-testid={`results-${s.survey_id}`}>
            <BarChart3 className="w-3 h-3 mr-1" />{isDE ? 'Ergebnisse' : 'Results'}
          </Button>
        )}
        {isEditor && archived && onRestore && (
          <Button size="sm" variant="outline" onClick={onRestore} className="rounded-full text-xs h-8 px-3 border-[#6B8E23]/40 text-[#6B8E23] hover:bg-[#6B8E23]/10" data-testid={`restore-${s.survey_id}`}>
            {isDE ? 'Reaktivieren' : 'Restore'}
          </Button>
        )}
        {isEditor && !archived && onArchive && (
          <button onClick={onArchive} title={isDE ? 'Archivieren' : 'Archive'}
            className="p-1.5 rounded-lg hover:bg-[#D4A373]/10 text-[#9CA3AF] hover:text-[#D4A373]"
            data-testid={`archive-${s.survey_id}`}>
            <Archive className="w-3.5 h-3.5" />
          </button>
        )}
        {isEditor && (
          <>
            <a href={`${process.env.REACT_APP_BACKEND_URL}/api/surveys/${s.survey_id}/export`} target="_blank" rel="noreferrer"
              className="p-1.5 rounded-lg hover:bg-[#4A5D4E]/10 text-[#9CA3AF] hover:text-[#4A5D4E]" title="CSV Export"><Download className="w-3.5 h-3.5" /></a>
            <button onClick={onDelete} className="p-1.5 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]"><Trash2 className="w-3.5 h-3.5" /></button>
          </>
        )}
      </div>
    </div>
  );
}

// ============ SURVEY RESPONSE FORM ============
export function SurveyResponseForm({ survey, isDE, onDone }) {
  const [answers, setAnswers] = useState({});
  const [attachmentMap, setAttachmentMap] = useState({}); // {question_id: [att objects]}
  const [submitting, setSubmitting] = useState(false);

  if (survey.participated) {
    return (
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 text-center">
        <Check className="w-10 h-10 text-[#6B8E23] mx-auto mb-2" />
        <p className="text-sm text-[#4B5563]">{isDE ? 'Du hast bereits teilgenommen' : 'You already participated'}</p>
      </div>
    );
  }

  const submit = async () => {
    setSubmitting(true);
    try {
      const attMapIds = {};
      Object.entries(attachmentMap).forEach(([qid, arr]) => {
        if (arr && arr.length) attMapIds[qid] = arr.map(a => a.attachment_id);
      });
      await api.post(`/surveys/${survey.survey_id}/respond`, { answers, attachment_map: attMapIds });
      toast.success(isDE ? 'Antwort gespeichert' : 'Response saved');
      onDone();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 sm:p-6">
      <h2 className="text-base sm:text-lg font-semibold text-[#1C1F1D] mb-1">{survey.title}</h2>
      {survey.description && <p className="text-sm text-[#9CA3AF] mb-4">{survey.description}</p>}
      {survey.anonymous && <Badge className="text-[9px] bg-[#9CA3AF]/10 text-[#9CA3AF] mb-4">Anonym</Badge>}
      <div className="space-y-6">
        {(survey.questions || []).map((q, i) => (
          <div key={q.question_id} className="border-t border-[#E2E4E0] pt-4">
            <p className="text-sm font-medium text-[#1C1F1D] mb-2">{i + 1}. {q.text} {q.required && <span className="text-[#C87967]">*</span>}</p>
            {q.type === 'single_choice' && (
              <div className="space-y-1.5">
                {(q.options || []).map(opt => (
                  <button key={opt} onClick={() => setAnswers(prev => ({ ...prev, [q.question_id]: opt }))}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${answers[q.question_id] === opt ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#E2E4E0]'}`}>
                    {opt}
                  </button>
                ))}
              </div>
            )}
            {q.type === 'multiple_choice' && (
              <div className="space-y-1.5">
                {(q.options || []).map(opt => {
                  const sel = (answers[q.question_id] || []).includes(opt);
                  return (
                    <button key={opt} onClick={() => {
                      const prev = answers[q.question_id] || [];
                      setAnswers(a => ({ ...a, [q.question_id]: sel ? prev.filter(x => x !== opt) : [...prev, opt] }));
                    }} className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${sel ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#E2E4E0]'}`}>
                      {sel ? <Check className="w-3 h-3 inline mr-1" /> : null}{opt}
                    </button>
                  );
                })}
              </div>
            )}
            {q.type === 'free_text' && (
              <>
                <textarea value={answers[q.question_id] || ''} onChange={e => setAnswers(prev => ({ ...prev, [q.question_id]: e.target.value }))}
                  className="w-full p-2 border border-[#E2E4E0] rounded-lg text-sm min-h-[60px] focus:outline-none focus:border-[#4A5D4E]"
                  placeholder={isDE ? 'Deine Antwort...' : 'Your answer...'} />
                <div className="mt-2">
                  <AttachmentPicker
                    attachments={attachmentMap[q.question_id] || []}
                    onChange={(arr) => setAttachmentMap(m => ({ ...m, [q.question_id]: arr }))}
                    max={3}
                    buttonLabel={isDE ? 'Anhang hinzufügen' : 'Add attachment'}
                    testId={`survey-attach-${q.question_id}`}
                  />
                </div>
              </>
            )}
            {q.type === 'scale' && (
              <div className="flex items-center gap-1 justify-center py-2 flex-wrap">
                {Array.from({ length: (q.scale_max || 10) - (q.scale_min || 1) + 1 }, (_, i) => i + (q.scale_min || 1)).map(n => (
                  <button key={n} onClick={() => setAnswers(prev => ({ ...prev, [q.question_id]: n }))}
                    className={`w-8 h-8 sm:w-9 sm:h-9 rounded-lg text-xs sm:text-sm font-medium transition-colors ${answers[q.question_id] === n ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280] hover:bg-[#E2E4E0]'}`}>
                    {n}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-6 flex justify-end">
        <Button onClick={submit} disabled={submitting} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="submit-survey-btn">
          <Send className="w-4 h-4 mr-1" />{submitting ? '...' : (isDE ? 'Absenden' : 'Submit')}
        </Button>
      </div>
    </div>
  );
}

// ============ SURVEY EDITOR ============
export function SurveyEditor({ open, onClose, type, isDE }) {
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [expiresAt, setExpiresAt] = useState('');
  const [questions, setQuestions] = useState([]);
  const [saving, setSaving] = useState(false);
  // iter 169 — targeting
  const [targetAll, setTargetAll] = useState(true);
  const [targetGroups, setTargetGroups] = useState([]);
  const [targetUserIds, setTargetUserIds] = useState([]);
  const [groups, setGroups] = useState([]);

  useEffect(() => {
    if (open) {
      setTitle(''); setDesc(''); setAnonymous(false); setExpiresAt(''); setQuestions([]);
      setTargetAll(true); setTargetGroups([]); setTargetUserIds([]);
      api.get('/news/groups').then(({ data }) => setGroups(data || [])).catch(() => setGroups([]));
    }
  }, [open]);

  const addQuestion = (qtype) => {
    setQuestions(prev => [...prev, {
      question_id: `q_${Date.now()}`, text: '', type: qtype,
      // Start with 2 empty options for choice questions so the layout makes it
      // visually obvious that multiple answers are expected.
      options: qtype === 'single_choice' || qtype === 'multiple_choice' ? ['', ''] : [],
      scale_min: 1, scale_max: 10, required: false,
    }]);
  };

  const moveQuestion = (idx, delta) => {
    setQuestions(prev => {
      const next = [...prev];
      const target = idx + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const updateQ = (idx, field, value) => {
    setQuestions(prev => prev.map((q, i) => i === idx ? { ...q, [field]: value } : q));
  };

  const save = async (status) => {
    if (!title.trim()) { toast.error('Titel erforderlich'); return; }
    if (questions.length === 0) { toast.error('Mindestens eine Frage'); return; }
    setSaving(true);
    try {
      const payload = {
        title, description: desc, anonymous, survey_type: type,
        questions, status,
        target_all: targetAll,
        target_groups: targetGroups,
        target_user_ids: targetUserIds,
      };
      if (expiresAt) {
        // Convert local datetime-local input → UTC ISO
        payload.expires_at = new Date(expiresAt).toISOString();
      }
      await api.post('/surveys', payload);
      toast.success(status === 'published' ? 'Veroeffentlicht' : 'Gespeichert');
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto w-[calc(100vw-1.5rem)]">
        <DialogHeader>
          <DialogTitle className="text-base font-medium">
            {type === 'pulse_check' ? 'Pulse-Check erstellen' : type === 'feedback_form' ? 'Feedback-Formular erstellen' : 'Umfrage erstellen'}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="Titel *" className="border-[#E2E4E0] rounded-xl" data-testid="survey-title-input" />
          <Input value={desc} onChange={e => setDesc(e.target.value)} placeholder={isDE ? 'Beschreibung (optional)' : 'Description'} className="border-[#E2E4E0] rounded-xl text-sm" />
          <div className="flex items-center gap-2">
            <Switch checked={anonymous} onCheckedChange={setAnonymous} />
            <label className="text-xs text-[#6B7280]">{isDE ? 'Anonyme Teilnahme' : 'Anonymous'}</label>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
              {isDE ? 'Zielgruppe' : 'Audience'}
            </label>
            <AudiencePicker
              targetAll={targetAll}
              onTargetAllChange={setTargetAll}
              targetGroups={targetGroups}
              onTargetGroupsChange={setTargetGroups}
              targetUserIds={targetUserIds}
              onTargetUserIdsChange={setTargetUserIds}
              groups={groups}
              isDE={isDE}
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1 block">
              {isDE ? 'Ablaufdatum (optional)' : 'Expires at (optional)'}
            </label>
            <Input type="datetime-local" value={expiresAt} onChange={e => setExpiresAt(e.target.value)}
              className="border-[#E2E4E0] rounded-xl text-sm" data-testid="survey-expires-input" />
            <p className="text-[10px] text-[#9CA3AF] mt-1">
              {isDE ? 'Wird 14 Tage nach Ablauf automatisch archiviert.' : 'Auto-archived 14 days after expiry.'}
            </p>
          </div>

          {/* Questions */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280]">
                {isDE ? `Fragen (${questions.length})` : `Questions (${questions.length})`}
              </label>
              {questions.length > 0 && (
                <span className="text-[10px] text-[#9CA3AF]">
                  {isDE ? 'Du kannst beliebig viele Fragen hinzufügen' : 'Add as many as you like'}
                </span>
              )}
            </div>
            {questions.length === 0 && (
              <div className="border-2 border-dashed border-[#E2E4E0] rounded-xl p-6 text-center bg-[#F9F9F8]">
                <HelpCircle className="w-8 h-8 text-[#9CA3AF] mx-auto mb-2" />
                <p className="text-sm font-medium text-[#1C1F1D]">
                  {isDE ? 'Noch keine Frage' : 'No question yet'}
                </p>
                <p className="text-[11px] text-[#6B7280] mt-0.5 max-w-xs mx-auto">
                  {isDE
                    ? 'Füge unten deine erste Frage hinzu. Du kannst mehrere Fragen-Typen kombinieren.'
                    : 'Add your first question below. You can mix question types.'}
                </p>
              </div>
            )}
            {questions.map((q, i) => {
              const typeLabel = {
                single_choice: isDE ? 'Single Choice' : 'Single choice',
                multiple_choice: isDE ? 'Multiple Choice' : 'Multiple choice',
                free_text: isDE ? 'Freitext' : 'Free text',
                scale: isDE ? 'Skala' : 'Scale',
              }[q.type] || q.type;
              return (
                <div key={q.question_id} className="border border-[#E2E4E0] rounded-xl p-3 sm:p-4 space-y-3 bg-white" data-testid={`survey-question-${i}`}>
                  <div className="flex items-start gap-2">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <span className="text-[10px] font-bold text-white bg-[#4A5D4E] rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">
                        {i + 1}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider font-bold text-[#4A5D4E]">{typeLabel}</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <button type="button" onClick={() => moveQuestion(i, -1)} disabled={i === 0}
                        className="p-1 text-[#9CA3AF] hover:text-[#4A5D4E] disabled:opacity-30 disabled:cursor-not-allowed" title={isDE ? 'Nach oben' : 'Move up'}>
                        <ChevronRight className="w-3.5 h-3.5 -rotate-90" />
                      </button>
                      <button type="button" onClick={() => moveQuestion(i, 1)} disabled={i === questions.length - 1}
                        className="p-1 text-[#9CA3AF] hover:text-[#4A5D4E] disabled:opacity-30 disabled:cursor-not-allowed" title={isDE ? 'Nach unten' : 'Move down'}>
                        <ChevronRight className="w-3.5 h-3.5 rotate-90" />
                      </button>
                      <button type="button" onClick={() => setQuestions(prev => prev.filter((_, j) => j !== i))}
                        className="p-1 text-[#C87967] hover:bg-[#C87967]/10 rounded" data-testid={`remove-question-${i}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <Input value={q.text} onChange={e => updateQ(i, 'text', e.target.value)}
                    placeholder={isDE ? 'Deine Frage hier eingeben... *' : 'Enter your question... *'}
                    className="border-[#E2E4E0] rounded-lg text-sm font-medium" data-testid={`question-text-${i}`} />
                  {(q.type === 'single_choice' || q.type === 'multiple_choice') && (
                    <div className="space-y-1.5 pl-1 border-l-2 border-[#4A5D4E]/20 ml-1">
                      <p className="text-[10px] text-[#6B7280] pl-2">
                        {isDE
                          ? (q.type === 'single_choice' ? 'Antwortmöglichkeiten (Teilnehmer wählt eine)' : 'Antwortmöglichkeiten (Teilnehmer kann mehrere wählen)')
                          : (q.type === 'single_choice' ? 'Answer options (pick one)' : 'Answer options (pick multiple)')}
                      </p>
                      {q.options.map((opt, j) => (
                        <div key={j} className="flex gap-1.5 items-center pl-2" data-testid={`question-${i}-option-${j}`}>
                          <span className="text-[10px] text-[#9CA3AF] w-5 flex-shrink-0">
                            {q.type === 'single_choice' ? '○' : '☐'}
                          </span>
                          <Input value={opt} onChange={e => {
                            const opts = [...q.options]; opts[j] = e.target.value; updateQ(i, 'options', opts);
                          }} placeholder={isDE ? `Antwort ${j + 1}` : `Answer ${j + 1}`}
                            className="border-[#E2E4E0] rounded-lg text-xs h-8 flex-1" />
                          <button type="button" onClick={() => updateQ(i, 'options', q.options.filter((_, k) => k !== j))}
                            className="p-1 text-[#9CA3AF] hover:text-[#C87967] disabled:opacity-30" disabled={q.options.length <= 1}
                            title={isDE ? 'Antwort entfernen' : 'Remove answer'}>
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                      <button type="button" onClick={() => updateQ(i, 'options', [...q.options, ''])}
                        className="ml-2 mt-1 flex items-center gap-1 text-[11px] text-[#4A5D4E] hover:text-[#3E4E42] font-medium"
                        data-testid={`add-option-${i}`}>
                        <Plus className="w-3 h-3" />{isDE ? 'Antwort hinzufügen' : 'Add answer'}
                      </button>
                    </div>
                  )}
                  {q.type === 'scale' && (
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-[10px] text-[#6B7280]">{isDE ? 'Von' : 'From'}:</span>
                      <Input type="number" value={q.scale_min} onChange={e => updateQ(i, 'scale_min', parseInt(e.target.value))} className="w-16 h-7 text-xs border-[#E2E4E0] rounded-lg" />
                      <span className="text-[10px] text-[#6B7280]">{isDE ? 'bis' : 'to'}:</span>
                      <Input type="number" value={q.scale_max} onChange={e => updateQ(i, 'scale_max', parseInt(e.target.value))} className="w-16 h-7 text-xs border-[#E2E4E0] rounded-lg" />
                    </div>
                  )}
                  <label className="flex items-center gap-2 text-[11px] text-[#6B7280] cursor-pointer select-none">
                    <input type="checkbox" checked={q.required} onChange={e => updateQ(i, 'required', e.target.checked)}
                      className="w-3.5 h-3.5 rounded border-[#E2E4E0] text-[#4A5D4E]" data-testid={`question-required-${i}`} />
                    {isDE ? 'Antwort ist Pflicht' : 'Required'}
                  </label>
                </div>
              );
            })}
          </div>

          {/* Add Question Buttons */}
          <div className="space-y-1.5">
            <label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280]">
              {isDE ? 'Frage hinzufügen' : 'Add a question'}
            </label>
            <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-1.5">
              <button type="button" onClick={() => addQuestion('single_choice')}
                className="text-[11px] px-2.5 py-1.5 bg-[#F3F4F1] rounded-full text-[#4A5D4E] hover:bg-[#4A5D4E] hover:text-white font-medium transition-colors flex items-center justify-center gap-1" data-testid="add-single-choice">
                <Plus className="w-3 h-3" />{isDE ? 'Single Choice' : 'Single choice'}
              </button>
              <button type="button" onClick={() => addQuestion('multiple_choice')}
                className="text-[11px] px-2.5 py-1.5 bg-[#F3F4F1] rounded-full text-[#4A5D4E] hover:bg-[#4A5D4E] hover:text-white font-medium transition-colors flex items-center justify-center gap-1" data-testid="add-multiple-choice">
                <Plus className="w-3 h-3" />{isDE ? 'Multiple Choice' : 'Multiple choice'}
              </button>
              <button type="button" onClick={() => addQuestion('free_text')}
                className="text-[11px] px-2.5 py-1.5 bg-[#F3F4F1] rounded-full text-[#4A5D4E] hover:bg-[#4A5D4E] hover:text-white font-medium transition-colors flex items-center justify-center gap-1" data-testid="add-free-text">
                <Plus className="w-3 h-3" />{isDE ? 'Freitext' : 'Free text'}
              </button>
              <button type="button" onClick={() => addQuestion('scale')}
                className="text-[11px] px-2.5 py-1.5 bg-[#F3F4F1] rounded-full text-[#4A5D4E] hover:bg-[#4A5D4E] hover:text-white font-medium transition-colors flex items-center justify-center gap-1" data-testid="add-scale">
                <Plus className="w-3 h-3" />{isDE ? 'Skala' : 'Scale'}
              </button>
            </div>
          </div>
        </div>
        <DialogFooter className="gap-2 flex-col sm:flex-row">
          <Button variant="outline" onClick={onClose} className="rounded-full border-[#E2E4E0] w-full sm:w-auto">{isDE ? 'Abbrechen' : 'Cancel'}</Button>
          <Button onClick={() => save('draft')} disabled={saving} variant="outline" className="rounded-full border-[#E2E4E0] w-full sm:w-auto" data-testid="save-survey-draft">{isDE ? 'Entwurf' : 'Draft'}</Button>
          <Button onClick={() => save('published')} disabled={saving} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full w-full sm:w-auto" data-testid="publish-survey-btn">
            {saving ? '...' : (isDE ? 'Veroeffentlichen' : 'Publish')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============ FEEDBACK DIALOG ============
export function AdminReplyInput({ feedbackId, isDE, onSent }) {
  const [open, setOpen] = useState(false);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);
  const send = async () => {
    if (!reply.trim()) return;
    setSending(true);
    try {
      await api.put(`/feedback/entries/${feedbackId}`, { response: reply.trim(), status: 'resolved' });
      toast.success(isDE ? 'Antwort gesendet' : 'Reply sent');
      setReply(''); setOpen(false);
      onSent && onSent();
    } catch { toast.error(isDE ? 'Fehler' : 'Error'); }
    finally { setSending(false); }
  };
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}
        className="mt-2 text-[11px] text-[#4A5D4E] hover:underline flex items-center gap-1"
        data-testid={`reply-trigger-${feedbackId}`}>
        <Send className="w-3 h-3" />{isDE ? 'Antworten' : 'Reply'}
      </button>
    );
  }
  return (
    <div className="mt-2 space-y-2" data-testid={`reply-box-${feedbackId}`}>
      <textarea value={reply} onChange={e => setReply(e.target.value)}
        placeholder={isDE ? 'Antwort an Absender...' : 'Reply to sender...'}
        className="w-full min-h-[60px] p-2 border border-[#E2E4E0] rounded-lg text-xs resize-y focus:outline-none focus:border-[#4A5D4E]"
        data-testid={`reply-input-${feedbackId}`} />
      <div className="flex gap-1.5 justify-end">
        <button type="button" onClick={() => { setOpen(false); setReply(''); }}
          className="text-[10px] px-2 py-1 rounded-lg text-[#6B7280] hover:bg-[#F3F4F1]">
          {isDE ? 'Abbrechen' : 'Cancel'}
        </button>
        <button type="button" onClick={send} disabled={sending || !reply.trim()}
          className="text-[10px] px-2.5 py-1 rounded-lg bg-[#4A5D4E] text-white hover:bg-[#3E4E42] disabled:opacity-50"
          data-testid={`reply-send-${feedbackId}`}>
          {sending ? '...' : (isDE ? 'Senden + Als erledigt markieren' : 'Send + Mark as resolved')}
        </button>
      </div>
    </div>
  );
}

export function TrackFeedbackDialog({ open, onClose, isDE }) {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleClose = () => { setCode(''); setResult(null); setError(''); onClose(); };

  const track = async () => {
    const c = code.trim().toUpperCase();
    if (!c) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const { data } = await api.post('/feedback/track', { tracking_code: c });
      setResult(data);
    } catch (e) {
      setError(e?.response?.data?.detail || (isDE ? 'Code nicht gefunden' : 'Code not found'));
    } finally {
      setLoading(false);
    }
  };

  const statusLabel = (s) => {
    if (s === 'new') return isDE ? 'Neu' : 'New';
    if (s === 'in_progress') return isDE ? 'In Bearbeitung' : 'In progress';
    if (s === 'resolved') return isDE ? 'Erledigt' : 'Resolved';
    return s || '-';
  };
  const statusColor = (s) => s === 'new' ? '#C87967' : s === 'in_progress' ? '#D4A373' : '#6B8E23';

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px] w-[calc(100vw-1.5rem)]" data-testid="track-feedback-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-medium flex items-center gap-2">
            <Search className="w-4 h-4 text-[#4A5D4E]" />
            {isDE ? 'Anonymes Feedback prüfen' : 'Track anonymous feedback'}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 pt-1">
          <p className="text-xs text-[#6B7280] leading-relaxed">
            {isDE
              ? 'Gib den Tracking-Code ein, den du beim Absenden deines anonymen Feedbacks erhalten hast, um Status und Admin-Antwort zu sehen.'
              : 'Enter the tracking code you received when submitting anonymous feedback to see status and admin reply.'}
          </p>
          <div className="flex items-stretch gap-2">
            <Input
              value={code}
              onChange={e => setCode(e.target.value)}
              placeholder="FB-XXXXXXXXXXX"
              className="font-mono tracking-wider border-[#E2E4E0] rounded-xl text-sm uppercase"
              data-testid="track-code-input"
              onKeyDown={(e) => { if (e.key === 'Enter') track(); }}
            />
            <Button onClick={track} disabled={loading || !code.trim()}
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl px-4" data-testid="track-code-submit">
              {loading ? '...' : (isDE ? 'Prüfen' : 'Check')}
            </Button>
          </div>
          {error && (
            <div className="p-2.5 bg-[#C87967]/10 border border-[#C87967]/30 rounded-lg text-xs text-[#C87967]" data-testid="track-error">
              {error}
            </div>
          )}
          {result && (
            <div className="border border-[#E2E4E0] rounded-xl p-3 space-y-2" data-testid="track-result">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-[#1C1F1D]">{result.subject || (isDE ? 'Feedback' : 'Feedback')}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  style={{ backgroundColor: `${statusColor(result.status)}15`, color: statusColor(result.status) }}>
                  {statusLabel(result.status)}
                </span>
                <span className="text-[10px] text-[#9CA3AF] ml-auto">
                  {result.created_at ? new Date(result.created_at).toLocaleDateString(isDE ? 'de-DE' : 'en-US') : ''}
                </span>
              </div>
              {result.admin_response ? (
                <div className="p-2.5 bg-[#F3F4F1] rounded-lg border-l-2 border-[#4A5D4E]">
                  <div className="flex items-center gap-1.5 mb-1">
                    <CheckCircle className="w-3 h-3 text-[#4A5D4E]" />
                    <span className="text-[10px] font-medium text-[#4A5D4E]">
                      {result.responded_by || (isDE ? 'Admin' : 'Admin')}
                      {isDE ? ' hat geantwortet:' : ' replied:'}
                    </span>
                  </div>
                  <p className="text-xs text-[#4B5563] whitespace-pre-wrap">{result.admin_response}</p>
                </div>
              ) : (
                <p className="text-xs text-[#9CA3AF] italic">
                  {isDE ? 'Noch keine Antwort – Status: ' : 'No reply yet – status: '}
                  <strong>{statusLabel(result.status)}</strong>
                </p>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={handleClose} variant="outline" className="rounded-full border-[#E2E4E0]">
            {isDE ? 'Schließen' : 'Close'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function FeedbackDialog({ open, onClose, isDE }) {
  const { user } = useAuth();
  const [category, setCategory] = useState('ideas');
  const [subject, setSubject] = useState('');
  const [content, setContent] = useState('');
  const [anonymous, setAnonymous] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [sentResult, setSentResult] = useState(null); // {anonymous: bool} when submitted

  const reset = () => {
    setSubject(''); setContent(''); setCategory('ideas'); setAnonymous(true); setSentResult(null);
  };
  const handleClose = () => { reset(); onClose(); };

  const submit = async () => {
    if (!content.trim()) { toast.error(isDE ? 'Bitte Feedback eingeben' : 'Please enter feedback'); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post('/feedback/submit', { category, subject, content, anonymous });
      setSentResult({ anonymous, tracking_code: data?.tracking_code || null });
    } catch { toast.error('Fehler'); }
    finally { setSubmitting(false); }
  };

  // Post-submission confirmation screen (replaces toast for clearer UX)
  if (sentResult) {
    const copyCode = async () => {
      try {
        await navigator.clipboard.writeText(sentResult.tracking_code);
        toast.success(isDE ? 'Code kopiert' : 'Code copied');
      } catch {
        toast.error(isDE ? 'Kopieren fehlgeschlagen' : 'Copy failed');
      }
    };
    return (
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-[440px] w-[calc(100vw-1.5rem)]" data-testid="feedback-sent-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-medium flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-[#6B8E23]" />
              {isDE ? 'Feedback gesendet' : 'Feedback sent'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 pt-1">
            <div className={`p-3 rounded-xl border ${sentResult.anonymous ? 'bg-[#F3F4F1] border-[#E2E4E0]' : 'bg-[#6B8E23]/5 border-[#6B8E23]/30'}`}>
              {sentResult.anonymous ? (
                <>
                  <p className="text-sm font-medium text-[#1C1F1D] mb-1">
                    {isDE ? 'Anonym an Admin übermittelt' : 'Anonymously delivered to admin'}
                  </p>
                  <p className="text-xs text-[#6B7280] leading-relaxed">
                    {isDE
                      ? 'Dein Name ist NICHT gespeichert. Damit du trotzdem die Admin-Antwort prüfen kannst, bewahre den Code unten auf. Ohne den Code ist das Feedback nicht mehr zuordenbar.'
                      : 'Your name is NOT stored. To still check the admin reply, keep the code below. Without it the feedback cannot be linked back to you.'}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm font-medium text-[#1C1F1D] mb-1">
                    {isDE ? 'Mit deinem Namen gesendet' : 'Sent under your name'}
                  </p>
                  <p className="text-xs text-[#6B7280] leading-relaxed">
                    {isDE
                      ? 'Du findest dein Feedback jetzt unter Profil → Mein Feedback, inklusive Status und Admin-Antwort sobald sie eintrifft.'
                      : 'You will find your feedback under Profile → My Feedback, including status and any admin reply.'}
                  </p>
                </>
              )}
            </div>
            {sentResult.anonymous && sentResult.tracking_code && (
              <div className="border border-dashed border-[#4A5D4E]/40 bg-[#4A5D4E]/5 rounded-xl p-3" data-testid="tracking-code-box">
                <p className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280] mb-1.5">
                  {isDE ? 'Dein Tracking-Code' : 'Your tracking code'}
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 font-mono text-sm font-semibold text-[#1C1F1D] bg-white border border-[#E2E4E0] rounded-lg px-2.5 py-2 tracking-wider select-all" data-testid="tracking-code-value">
                    {sentResult.tracking_code}
                  </code>
                  <Button size="sm" type="button" onClick={copyCode}
                    className="rounded-lg bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-9 px-3" data-testid="copy-tracking-code">
                    {isDE ? 'Kopieren' : 'Copy'}
                  </Button>
                </div>
                <p className="text-[10px] text-[#6B7280] mt-2 leading-snug">
                  {isDE
                    ? 'Prüfe die Antwort später über „Anonymes Feedback prüfen".'
                    : 'Check the reply later under "Track anonymous feedback".'}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button onClick={handleClose} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="feedback-sent-close">
              {isDE ? 'Schließen' : 'Close'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px] w-[calc(100vw-1.5rem)]">
        <DialogHeader>
          <DialogTitle className="text-base font-medium">{isDE ? 'Feedback senden' : 'Send Feedback'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          {/* Anonymous / Signed toggle */}
          <div className={`p-3 rounded-xl border transition-colors ${anonymous ? 'bg-[#F3F4F1] border-[#E2E4E0]' : 'bg-[#6B8E23]/5 border-[#6B8E23]/30'}`}>
            <div className="flex items-center justify-between gap-3 mb-1">
              <div className="flex items-center gap-2 min-w-0">
                <MessageSquare className="w-4 h-4 text-[#4A5D4E] flex-shrink-0" />
                <span className="text-sm font-medium text-[#1C1F1D]">
                  {anonymous
                    ? (isDE ? 'Anonym senden' : 'Send anonymously')
                    : (isDE ? 'Mit Namen senden' : 'Send with your name')}
                </span>
              </div>
              <Switch checked={!anonymous} onCheckedChange={v => setAnonymous(!v)} data-testid="feedback-anonymous-toggle" />
            </div>
            <p className="text-[11px] text-[#6B7280] leading-relaxed">
              {anonymous
                ? (isDE
                  ? 'Dein Name wird NICHT gespeichert. Admins sehen nur den Inhalt. Du wirst das Feedback nicht wiederfinden – ideal für ehrliches Feedback.'
                  : 'Your name is NOT stored. Admins only see the content. You will not be able to retrieve it – ideal for honest feedback.')
                : (isDE
                  ? `Gesendet als "${user?.name || 'Du'}". Du siehst dein Feedback + Admin-Antwort unter Profil → Mein Feedback.`
                  : `Sent as "${user?.name || 'You'}". You will see your feedback + admin reply under Profile → My Feedback.`)}
            </p>
          </div>

          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1.5">{isDE ? 'Kategorie' : 'Category'}</label>
            <div className="flex flex-wrap gap-1.5">
              {FEEDBACK_CATS.map(c => (
                <button key={c.id} onClick={() => setCategory(c.id)}
                  className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full transition-colors ${category === c.id ? 'text-white' : 'hover:bg-[#E2E4E0]'}`}
                  style={category === c.id ? { backgroundColor: c.color } : { backgroundColor: `${c.color}15`, color: c.color }}>
                  <c.icon className="w-3 h-3" />{c.label}
                </button>
              ))}
            </div>
          </div>
          <Input value={subject} onChange={e => setSubject(e.target.value)} placeholder={isDE ? 'Betreff (optional)' : 'Subject (optional)'} className="border-[#E2E4E0] rounded-xl text-sm" data-testid="feedback-subject" />
          <textarea value={content} onChange={e => setContent(e.target.value)} placeholder={isDE ? 'Dein Feedback...' : 'Your feedback...'}
            className="w-full min-h-[100px] p-3 border border-[#E2E4E0] rounded-xl text-sm resize-y focus:outline-none focus:border-[#4A5D4E]" data-testid="feedback-content" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleClose} className="rounded-full border-[#E2E4E0]">{isDE ? 'Abbrechen' : 'Cancel'}</Button>
          <Button onClick={submit} disabled={submitting} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="submit-feedback-btn">
            <Send className="w-4 h-4 mr-1" />
            {submitting
              ? '...'
              : (anonymous
                ? (isDE ? 'Anonym senden' : 'Send anonymously')
                : (isDE ? 'Mit Namen senden' : 'Send with name'))}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
