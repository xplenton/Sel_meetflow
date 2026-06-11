import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import AudiencePicker from '../components/AudiencePicker';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import {
  ClipboardList, Plus, BarChart3, MessageSquare, Check, CheckCircle, ChevronRight,
  Trash2, Send, X, Heart, AlertCircle, Lightbulb, HelpCircle,
  Smile, Meh, Frown, ThumbsUp, Eye, Download, Archive, Search
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import AttachmentPicker, { AttachmentChip } from '../components/AttachmentPicker';
import {
  StatMini, EmptyState, SurveyCard, SurveyResponseForm, SurveyEditor,
  AdminReplyInput, TrackFeedbackDialog, FeedbackDialog,
} from '../components/surveys/SurveysComponents';

const FEEDBACK_CATS = [
  { id: 'ideas', label: 'Ideen', icon: Lightbulb, color: '#6B8E23' },
  { id: 'complaints', label: 'Beschwerden', icon: AlertCircle, color: '#C87967' },
  { id: 'improvements', label: 'Verbesserungen', icon: ThumbsUp, color: '#4A5D4E' },
  { id: 'questions', label: 'Rueckfragen', icon: HelpCircle, color: '#D4A373' },
];

export default function SurveysPage() {
  const { user } = useAuth();
  const { language } = useLanguage();
  const isDE = language === 'de';
  const isEditor = ['admin', 'freigeber', 'redakteur'].includes(user?.role);
  const [tab, setTab] = useState('surveys');
  const [surveys, setSurveys] = useState([]);
  const [pulseChecks, setPulseChecks] = useState([]);
  const [feedbackEntries, setFeedbackEntries] = useState([]);
  const [stats, setStats] = useState(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorType, setEditorType] = useState('survey');
  const [selectedSurvey, setSelectedSurvey] = useState(null);
  const [results, setResults] = useState(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [trackOpen, setTrackOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [archivedSurveys, setArchivedSurveys] = useState([]);

  const fetch = useCallback(async () => {
    api.get('/surveys?status=published').then(({ data }) => setSurveys(data.filter(s => s.survey_type === 'survey'))).catch(() => {});
    api.get('/surveys?status=archived').then(({ data }) => setArchivedSurveys((data || []).filter(s => s.survey_type === 'survey'))).catch(() => {});
    api.get('/pulse-checks').then(({ data }) => setPulseChecks(data)).catch(() => {});
    if (isEditor) {
      api.get('/feedback/entries').then(({ data }) => setFeedbackEntries(data)).catch(() => {});
      api.get('/interaction-stats').then(({ data }) => setStats(data)).catch(() => {});
    }
  }, [isEditor]);

  useEffect(() => { fetch(); }, [fetch]);

  const archiveSurvey = async (s) => {
    try { await api.post(`/surveys/${s.survey_id}/archive`); toast.success('Archiviert'); fetch(); }
    catch { toast.error('Fehler beim Archivieren'); }
  };
  const restoreSurvey = async (s) => {
    try { await api.post(`/surveys/${s.survey_id}/restore`); toast.success('Reaktiviert'); fetch(); }
    catch { toast.error('Fehler beim Wiederherstellen'); }
  };

  const openResults = async (survey) => {
    const { data } = await api.get(`/surveys/${survey.survey_id}/results`);
    setResults(data);
    setSelectedSurvey(survey);
  };

  const openSurveyToRespond = async (survey) => {
    const { data } = await api.get(`/surveys/${survey.survey_id}`);
    setSelectedSurvey(data);
    setResults(null);
  };

  // ============ SURVEY RESPONSE VIEW ============
  if (selectedSurvey && !results) {
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-3 pt-14 sm:p-4 md:p-8 animate-fade-in" data-testid="survey-respond">
          <div className="max-w-2xl mx-auto">
            <button onClick={() => setSelectedSurvey(null)} className="flex items-center gap-1 text-sm text-[#4A5D4E] hover:underline mb-4">
              <X className="w-4 h-4" /> {isDE ? 'Zurück' : 'Back'}
            </button>
            <SurveyResponseForm survey={selectedSurvey} isDE={isDE} onDone={() => { setSelectedSurvey(null); fetch(); }} />
          </div>
        </main>
      </div>
    );
  }

  // ============ RESULTS VIEW ============
  if (results) {
    return (
      <div className="flex min-h-screen bg-[#F9F9F8]">
        <Sidebar />
        <main className="flex-1 ml-0 md:ml-[260px] p-3 pt-14 sm:p-4 md:p-8 animate-fade-in" data-testid="survey-results">
          <div className="max-w-3xl mx-auto">
            <button onClick={() => { setResults(null); setSelectedSurvey(null); }} className="flex items-center gap-1 text-sm text-[#4A5D4E] hover:underline mb-4">
              <X className="w-4 h-4" /> {isDE ? 'Zurück' : 'Back'}
            </button>
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 sm:p-6">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-4">
                <div className="min-w-0">
                  <h2 className="text-base sm:text-lg font-semibold text-[#1C1F1D] mb-1 break-words">{results.survey?.title}</h2>
                  <p className="text-xs text-[#9CA3AF]">{results.total_responses} {isDE ? 'Teilnahmen' : 'responses'}</p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 flex-wrap">
                  <a href={`${process.env.REACT_APP_BACKEND_URL}/api/exports/surveys/${results.survey.survey_id}/csv`}
                    target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-[#4A5D4E] border border-[#E2E4E0] rounded-lg px-2.5 py-1.5 hover:bg-[#F3F4F1]"
                    data-testid="export-survey-csv-ext">
                    <Download className="w-3.5 h-3.5" /> CSV
                  </a>
                  <a href={`${process.env.REACT_APP_BACKEND_URL}/api/exports/surveys/${results.survey.survey_id}/pdf`}
                    target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-white bg-[#4A5D4E] hover:bg-[#3E4E42] rounded-lg px-2.5 py-1.5"
                    data-testid="export-survey-pdf">
                    <Download className="w-3.5 h-3.5" /> PDF
                  </a>
                </div>
              </div>
              <div className="space-y-6">
                {Object.values(results.results || {}).map((q, i) => (
                  <div key={q.question_id || q.question || `q-${i}`} className="border-t border-[#E2E4E0] pt-4">
                    <p className="text-sm font-medium text-[#1C1F1D] mb-3">{q.question}</p>
                    {(q.type === 'single_choice' || q.type === 'multiple_choice') && (
                      <div className="space-y-2">
                        {Object.entries(q.answers || {}).map(([opt, count]) => {
                          const pct = q.total > 0 ? Math.round((count / q.total) * 100) : 0;
                          return (
                            <div key={opt}>
                              <div className="flex items-center justify-between text-xs mb-1">
                                <span className="text-[#4B5563]">{opt}</span>
                                <span className="text-[#9CA3AF]">{count} ({pct}%)</span>
                              </div>
                              <div className="h-2 bg-[#F3F4F1] rounded-full overflow-hidden">
                                <div className="h-full bg-[#4A5D4E] rounded-full transition-all" style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {q.type === 'scale' && (
                      <div className="text-center py-3">
                        <span className="text-3xl font-bold text-[#4A5D4E]">{q.average}</span>
                        <p className="text-xs text-[#9CA3AF] mt-1">{isDE ? 'Durchschnitt' : 'Average'} ({q.values?.length} {isDE ? 'Antworten' : 'answers'})</p>
                      </div>
                    )}
                    {q.type === 'free_text' && (
                      <div className="space-y-2 max-h-60 overflow-y-auto">
                        {(q.texts || []).map((t, j) => (
                          <div key={`${t.user || 'anon'}-${j}`} className="text-xs p-2 bg-[#F3F4F1] rounded-lg">
                            <span className="text-[#9CA3AF]">{t.user}:</span> {t.text}
                            {t.attachments && t.attachments.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 mt-1.5">
                                {t.attachments.map(a => <AttachmentChip key={a.attachment_id} att={a} compact />)}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // ============ MAIN LIST VIEW ============
  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-3 pt-14 sm:p-4 md:p-8 animate-fade-in" data-testid="surveys-page">
        <div className="max-w-4xl mx-auto">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 sm:mb-6">
            <div className="min-w-0">
              <h1 className="text-xl sm:text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
                {isDE ? 'Umfragen & Feedback' : 'Surveys & Feedback'}
              </h1>
              <p className="text-xs sm:text-sm text-[#9CA3AF]">{isDE ? 'Beteiligung & Rueckmeldungen' : 'Participation & Feedback'}</p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button onClick={() => setFeedbackOpen(true)} variant="outline" className="rounded-xl border-[#E2E4E0] text-xs sm:text-sm flex-1 sm:flex-none" data-testid="open-feedback-btn">
                <MessageSquare className="w-4 h-4 mr-1" />{isDE ? 'Feedback' : 'Feedback'}
              </Button>
              <Button onClick={() => setTrackOpen(true)} variant="outline" className="rounded-xl border-[#E2E4E0] text-xs sm:text-sm flex-1 sm:flex-none" data-testid="open-track-btn">
                <Search className="w-4 h-4 mr-1" />{isDE ? 'Code prüfen' : 'Track code'}
              </Button>
              {isEditor && (
                <Button onClick={() => { setEditorType('survey'); setEditorOpen(true); }} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl text-xs sm:text-sm flex-1 sm:flex-none" data-testid="create-survey-btn">
                  <Plus className="w-4 h-4 mr-1" />{isDE ? 'Umfrage' : 'Survey'}
                </Button>
              )}
            </div>
          </div>

          {/* Stats (editor only) */}
          {stats && isEditor && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6" data-testid="interaction-stats">
              <StatMini label={isDE ? 'Kommentare' : 'Comments'} value={stats.news?.comments} />
              <StatMini label={isDE ? 'Reaktionen' : 'Reactions'} value={stats.news?.reactions} />
              <StatMini label={isDE ? 'Umfrage-Teilnahmen' : 'Survey Responses'} value={stats.surveys?.responses} />
              <StatMini label={isDE ? 'Neues Feedback' : 'New Feedback'} value={stats.feedback?.new} accent="#C87967" />
            </div>
          )}

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="bg-[#F3F4F1] mb-5 rounded-lg">
              <TabsTrigger value="surveys" className="text-xs rounded-lg" data-testid="tab-surveys">{isDE ? 'Umfragen' : 'Surveys'}</TabsTrigger>
              <TabsTrigger value="pulse" className="text-xs rounded-lg" data-testid="tab-pulse">Pulse-Checks</TabsTrigger>
              {isEditor && <TabsTrigger value="feedback" className="text-xs rounded-lg" data-testid="tab-feedback">Feedback</TabsTrigger>}
            </TabsList>

            <TabsContent value="surveys">
              {surveys.length === 0 ? (
                <EmptyState icon={ClipboardList} text={isDE ? 'Keine aktiven Umfragen' : 'No active surveys'} />
              ) : (
                <div className="space-y-3">
                  {surveys.map(s => (
                    <SurveyCard key={s.survey_id} survey={s} isDE={isDE} isEditor={isEditor}
                      onRespond={() => openSurveyToRespond(s)} onResults={() => openResults(s)}
                      onArchive={isEditor ? () => archiveSurvey(s) : null}
                      onDelete={async () => { await api.delete(`/surveys/${s.survey_id}`); fetch(); }} />
                  ))}
                </div>
              )}

              {isEditor && archivedSurveys.length > 0 && (
                <div className="mt-8 pt-5 border-t border-[#E2E4E0]">
                  <button
                    type="button"
                    onClick={() => setShowArchived(v => !v)}
                    className="flex items-center gap-2 text-xs text-[#9CA3AF] hover:text-[#4A5D4E] mb-3"
                    data-testid="toggle-archived-surveys"
                  >
                    <span>{showArchived ? '▼' : '▶'}</span>
                    <span>Archiv ({archivedSurveys.length})</span>
                  </button>
                  {showArchived && (
                    <div className="space-y-3 opacity-70" data-testid="archived-surveys-list">
                      {archivedSurveys.map(s => (
                        <SurveyCard key={s.survey_id} survey={s} isDE={isDE} isEditor={isEditor}
                          archived
                          onResults={() => openResults(s)}
                          onRestore={() => restoreSurvey(s)}
                          onDelete={async () => { await api.delete(`/surveys/${s.survey_id}`); fetch(); }} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </TabsContent>

            <TabsContent value="pulse">
              {isEditor && (
                <Button onClick={() => { setEditorType('pulse_check'); setEditorOpen(true); }} variant="outline" size="sm" className="mb-4 rounded-xl border-[#E2E4E0] text-xs" data-testid="create-pulse-btn">
                  <Plus className="w-3 h-3 mr-1" />Pulse-Check erstellen
                </Button>
              )}
              {pulseChecks.length === 0 ? (
                <EmptyState icon={Smile} text={isDE ? 'Keine Pulse-Checks' : 'No pulse checks'} />
              ) : (
                <div className="space-y-3">
                  {pulseChecks.map(s => (
                    <SurveyCard key={s.survey_id} survey={s} isDE={isDE} isEditor={isEditor}
                      onRespond={() => openSurveyToRespond(s)} onResults={() => openResults(s)} onDelete={async () => { await api.delete(`/surveys/${s.survey_id}`); fetch(); }} />
                  ))}
                </div>
              )}
            </TabsContent>

            {isEditor && (
              <TabsContent value="feedback">
                <div className="flex justify-end mb-3">
                  <a href={`${process.env.REACT_APP_BACKEND_URL}/api/feedback/export`} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1 text-xs text-[#4A5D4E] hover:underline" data-testid="export-feedback-btn">
                    <Download className="w-3 h-3" />{isDE ? 'CSV Export' : 'Export CSV'}
                  </a>
                </div>
                {feedbackEntries.length === 0 ? (
                  <EmptyState icon={MessageSquare} text={isDE ? 'Kein Feedback eingegangen' : 'No feedback received'} />
                ) : (
                  <div className="space-y-2">
                    {feedbackEntries.map(fb => {
                      const cat = FEEDBACK_CATS.find(c => c.id === fb.category);
                      const CatIcon = cat?.icon || MessageSquare;
                      return (
                        <div key={fb.feedback_id} className="bg-white border border-[#E2E4E0] rounded-xl p-3 sm:p-4" data-testid={`feedback-${fb.feedback_id}`}>
                          <div className="flex flex-col sm:flex-row items-start gap-3">
                            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${cat?.color || '#9CA3AF'}15` }}>
                              <CatIcon className="w-4 h-4" style={{ color: cat?.color || '#9CA3AF' }} />
                            </div>
                            <div className="flex-1 min-w-0 w-full">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <span className="text-xs font-medium text-[#1C1F1D]">{fb.subject || cat?.label || 'Feedback'}</span>
                                <Badge className={`text-[9px] px-1.5 py-0 ${fb.status === 'new' ? 'bg-[#C87967]/10 text-[#C87967]' : fb.status === 'in_progress' ? 'bg-[#D4A373]/10 text-[#D4A373]' : 'bg-[#6B8E23]/10 text-[#6B8E23]'}`}>
                                  {fb.status === 'new' ? 'Neu' : fb.status === 'in_progress' ? 'In Bearbeitung' : 'Erledigt'}
                                </Badge>
                                {fb.anonymous === false && fb.user_name ? (
                                  <Badge className="text-[9px] px-1.5 py-0 bg-[#4A5D4E]/10 text-[#4A5D4E]" data-testid={`feedback-author-${fb.feedback_id}`}>
                                    {fb.user_name}
                                  </Badge>
                                ) : (
                                  <Badge className="text-[9px] px-1.5 py-0 bg-[#9CA3AF]/15 text-[#6B7280]">
                                    {isDE ? 'Anonym' : 'Anonymous'}
                                  </Badge>
                                )}
                                {fb.tracking_code && (
                                  <Badge className="text-[9px] px-1.5 py-0 bg-[#D4A373]/10 text-[#D4A373] font-mono" title={isDE ? 'Tracking-Code — Absender kann Antwort prüfen' : 'Tracking code — submitter can check reply'} data-testid={`feedback-tracking-${fb.feedback_id}`}>
                                    {fb.tracking_code}
                                  </Badge>
                                )}
                                <span className="text-[10px] text-[#9CA3AF]">{new Date(fb.created_at).toLocaleDateString('de-DE')}</span>
                              </div>
                              <p className="text-xs sm:text-sm text-[#4B5563] break-words">{fb.content}</p>
                              {fb.admin_response && (
                                <div className="mt-2 p-2 bg-[#F3F4F1] rounded-lg text-xs text-[#4A5D4E] break-words">
                                  <span className="font-medium">{fb.responded_by}:</span> {fb.admin_response}
                                </div>
                              )}
                              {!fb.admin_response && (
                                <AdminReplyInput feedbackId={fb.feedback_id} isDE={isDE} onSent={fetch} />
                              )}
                            </div>
                            <Select defaultValue={fb.status} onValueChange={async (v) => { await api.put(`/feedback/entries/${fb.feedback_id}`, { status: v }); fetch(); }}>
                              <SelectTrigger className="h-7 w-full sm:w-28 text-[10px] border-[#E2E4E0] rounded-lg"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="new">Neu</SelectItem>
                                <SelectItem value="in_progress">In Bearbeitung</SelectItem>
                                <SelectItem value="resolved">Erledigt</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>
            )}
          </Tabs>
        </div>
      </main>

      <SurveyEditor open={editorOpen} onClose={() => { setEditorOpen(false); fetch(); }} type={editorType} isDE={isDE} />
      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} isDE={isDE} />
      <TrackFeedbackDialog open={trackOpen} onClose={() => setTrackOpen(false)} isDE={isDE} />
    </div>
  );
}

// ============ SUB-COMPONENTS ============

