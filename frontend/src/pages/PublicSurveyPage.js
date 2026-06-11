import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { ListChecks, Check, Users, MessageSquare, Send, Plus, GripVertical, BarChart3 } from 'lucide-react';
import axios from 'axios';
import { toast, Toaster } from 'sonner';
import { useLanguage } from '../contexts/LanguageContext';

const API = process.env.REACT_APP_BACKEND_URL;
const pubApi = axios.create({ baseURL: `${API}/api` });

export default function PublicSurveyPage() {
  const { t } = useLanguage();
  const { shareToken } = useParams();
  const [poll, setPoll] = useState(null);
  const [loading, setLoading] = useState(true);
  const [voterName, setVoterName] = useState('');
  const [selected, setSelected] = useState([]);
  const [priorityOrder, setPriorityOrder] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [comment, setComment] = useState('');
  const [commentName, setCommentName] = useState('');
  const [newOption, setNewOption] = useState('');

  const fetchPoll = useCallback(async () => {
    try { const { data } = await pubApi.get(`/general-polls/public/${shareToken}`); setPoll(data); setPriorityOrder(data.options || []); }
    catch { toast.error('Umfrage nicht gefunden'); }
    finally { setLoading(false); }
  }, [shareToken]);

  useEffect(() => { fetchPoll(); }, [fetchPoll]);

  const toggleOption = (opt) => {
    if (poll.poll_type === 'single') { setSelected([opt]); return; }
    setSelected(prev => prev.includes(opt) ? prev.filter(o => o !== opt) : [...prev, opt]);
  };

  const movePriority = (from, to) => {
    if (to < 0 || to >= priorityOrder.length) return;
    const arr = [...priorityOrder];
    const item = arr.splice(from, 1)[0];
    arr.splice(to, 0, item);
    setPriorityOrder(arr);
  };

  const submitVote = async () => {
    if (!voterName.trim()) { toast.error('Bitte Name eingeben'); return; }
    if (poll.poll_type !== 'priority' && selected.length === 0) { toast.error('Bitte mindestens eine Option wählen'); return; }
    setSubmitting(true);
    try {
      await pubApi.post(`/general-polls/public/${shareToken}/vote`, {
        voter_name: voterName, selected_options: poll.poll_type === 'priority' ? [] : selected,
        selected: poll.poll_type === 'priority' ? priorityOrder : selected,
        priority_order: poll.poll_type === 'priority' ? priorityOrder : null,
      });
      setSubmitted(true);
      fetchPoll();
      toast.success('Abstimmung gespeichert!');
    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler'); }
    finally { setSubmitting(false); }
  };

  const submitComment = async () => {
    if (!commentName.trim() || !comment.trim()) return;
    try {
      await pubApi.post(`/general-polls/public/${shareToken}/comment`, { author_name: commentName, text: comment });
      setComment('');
      fetchPoll();
    } catch (e) { console.warn("silent error:", e); }
  };

  const addOption = async () => {
    if (!newOption.trim()) return;
    try {
      await pubApi.post(`/general-polls/public/${shareToken}/add-option`, { option: newOption });
      setNewOption('');
      fetchPoll();
      toast.success('Option hinzugefuegt');
    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler'); }
  };

  const resolveOption = (o) => {
    if (typeof o === 'number' && poll?.options?.[o]) return poll.options[o];
    return o;
  };

  const getResults = () => {
    if (!poll || !poll.votes?.length) return {};
    const counts = {};
    poll.options.forEach(o => { counts[o] = 0; });
    poll.votes.forEach(v => {
      if (poll.poll_type === 'priority') {
        (v.priority_order || v.selected_options || v.selected || []).forEach((o, i) => {
          const opt = resolveOption(o);
          counts[opt] = (counts[opt] || 0) + (poll.options.length - i);
        });
      } else {
        (v.selected_options || v.selected || []).forEach(o => {
          const opt = resolveOption(o);
          counts[opt] = (counts[opt] || 0) + 1;
        });
      }
    });
    return counts;
  };

  const results = getResults();
  const maxScore = Math.max(1, ...Object.values(results));
  const totalVotes = poll?.votes?.length || 0;

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8] text-[#9CA3AF]">Loading...</div>;
  if (!poll) return <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8] text-[#9CA3AF]">{t('notFound')}</div>;

  const isClosed = poll.status === 'closed';

  return (
    <div className="min-h-screen bg-[#F9F9F8]">
      <Toaster position="top-right" richColors />
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center gap-2.5 mb-6">
          <ListChecks className="w-6 h-6 text-[#4A5D4E]" />
          <span className="text-lg font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
        </div>

        {/* Header */}
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6">
          <h1 className="text-xl font-medium text-[#1C1F1D] mb-1" style={{ fontFamily: 'Manrope' }} data-testid="survey-title">{poll.title}</h1>
          {poll.description && <p className="text-sm text-[#6B7280] mb-2">{poll.description}</p>}
          <div className="flex items-center gap-3 text-xs text-[#9CA3AF]">
            <span>von {poll.creator_name}</span>
            <span className="flex items-center gap-1"><Users className="w-3 h-3" />{totalVotes} Antworten</span>
            <span className="capitalize px-2 py-0.5 bg-[#F3F4F1] rounded-full">{
              poll.poll_type === 'single' ? 'Einzelauswahl' : poll.poll_type === 'multiple' ? 'Mehrfachauswahl' : 'Priorisierung'
            }</span>
            {isClosed && <span className="text-[#C87967] font-medium">Geschlossen</span>}
          </div>
        </div>

        {/* Results */}
        {totalVotes > 0 && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6" data-testid="survey-results">
            <h3 className="text-sm font-medium text-[#1C1F1D] mb-4 flex items-center gap-1.5"><BarChart3 className="w-4 h-4 text-[#4A5D4E]" />Ergebnisse</h3>
            <div className="space-y-3">
              {[...poll.options].sort((a, b) => (results[b] || 0) - (results[a] || 0)).map((opt, i) => {
                const score = results[opt] || 0;
                const pct = poll.poll_type === 'priority' ? Math.round((score / maxScore) * 100) : totalVotes > 0 ? Math.round((score / totalVotes) * 100) : 0;
                const isLeader = i === 0 && score > 0;
                return (
                  <div key={opt} data-testid={`result-${opt}`}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className={`${isLeader ? 'font-bold text-[#1C1F1D]' : 'text-[#4B5563]'}`}>{opt}</span>
                      <span className="text-xs text-[#6B7280]">{poll.poll_type === 'priority' ? `${score} Punkte` : `${score} Stimmen (${pct}%)`}</span>
                    </div>
                    <div className="w-full bg-[#F3F4F1] rounded-full h-2.5 overflow-hidden">
                      <div className={`h-full rounded-full transition-all ${isLeader ? 'bg-[#6B8E23]' : 'bg-[#4A5D4E]/40'}`}
                        style={{ width: `${Math.max(2, pct)}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Vote Form */}
        {!isClosed && !submitted && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6" data-testid="survey-vote-form">
            <h3 className="text-sm font-medium text-[#1C1F1D] mb-4">{t('yourVote')}</h3>
            <Input data-testid="survey-voter-name" value={voterName} onChange={e => setVoterName(e.target.value)}
              placeholder={t('yourName')} className="border-[#E2E4E0] rounded-xl mb-4" />

            {poll.poll_type === 'priority' ? (
              <div className="space-y-2 mb-4">
                <p className="text-xs text-[#9CA3AF] mb-2">Ziehe die Optionen in deine bevorzugte Reihenfolge (1 = beste)</p>
                {priorityOrder.map((opt, i) => (
                  <div key={opt} className="flex items-center gap-2 p-3 bg-[#F3F4F1] rounded-lg" data-testid={`priority-${i}`}>
                    <span className="text-xs font-bold text-[#4A5D4E] w-5">{i + 1}.</span>
                    <GripVertical className="w-4 h-4 text-[#9CA3AF]" />
                    <span className="text-sm flex-1">{opt}</span>
                    <div className="flex gap-1">
                      <button onClick={() => movePriority(i, i - 1)} disabled={i === 0}
                        className="px-2 py-1 rounded text-xs bg-white border border-[#E2E4E0] hover:bg-[#F3F4F1] disabled:opacity-30">▲</button>
                      <button onClick={() => movePriority(i, i + 1)} disabled={i === priorityOrder.length - 1}
                        className="px-2 py-1 rounded text-xs bg-white border border-[#E2E4E0] hover:bg-[#F3F4F1] disabled:opacity-30">▼</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-2 mb-4">
                {poll.options.map(opt => (
                  <button key={opt} onClick={() => toggleOption(opt)} data-testid={`option-btn-${opt}`}
                    className={`w-full text-left p-3 rounded-lg text-sm transition-all flex items-center gap-3 ${
                      selected.includes(opt) ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#4A5D4E]/10'
                    }`}>
                    <div className={`w-5 h-5 rounded-${poll.poll_type === 'single' ? 'full' : 'md'} border-2 flex items-center justify-center flex-shrink-0 ${
                      selected.includes(opt) ? 'border-white bg-white/20' : 'border-[#D1D5DB]'
                    }`}>
                      {selected.includes(opt) && <Check className="w-3 h-3" />}
                    </div>
                    {opt}
                  </button>
                ))}
              </div>
            )}

            <Button onClick={submitVote} disabled={submitting} data-testid="submit-survey-vote"
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11">
              {submitting ? 'Speichere...' : 'Abstimmung abgeben'}
            </Button>
          </div>
        )}

        {submitted && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6 text-center">
            <Check className="w-10 h-10 text-[#6B8E23] mx-auto mb-2" />
            <p className="text-sm text-[#4B5563] font-medium">Danke für deine Abstimmung!</p>
            <Button variant="outline" onClick={() => setSubmitted(false)} className="mt-3 rounded-full border-[#E2E4E0] text-xs">{t('changeAnswer')}</Button>
          </div>
        )}

        {/* Add custom option */}
        {poll.allow_custom_options && !isClosed && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6">
            <h3 className="text-sm font-medium text-[#1C1F1D] mb-3 flex items-center gap-1.5"><Plus className="w-4 h-4" />{t('addOptionShort')}</h3>
            <div className="flex gap-2">
              <Input value={newOption} onChange={e => setNewOption(e.target.value)} placeholder="Neue Option..." className="border-[#E2E4E0] rounded-lg flex-1 h-9 text-sm" data-testid="custom-option-input" />
              <Button size="sm" onClick={addOption} className="bg-[#4A5D4E] text-white rounded-lg h-9 px-3" data-testid="add-custom-option"><Plus className="w-4 h-4" /></Button>
            </div>
          </div>
        )}

        {/* Comments */}
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
          <h3 className="text-sm font-medium text-[#1C1F1D] mb-3 flex items-center gap-1.5"><MessageSquare className="w-4 h-4" />Kommentare ({poll.comments?.length || 0})</h3>
          {poll.comments?.length > 0 && (
            <div className="space-y-2 mb-4 max-h-60 overflow-y-auto">
              {poll.comments.map(c => (
                <div key={c.comment_id} className="p-3 bg-[#F3F4F1] rounded-lg">
                  <div className="flex items-center gap-2 text-xs mb-1">
                    <span className="font-medium text-[#1C1F1D]">{poll.is_anonymous ? 'Anonym' : c.author_name}</span>
                    <span className="text-[#9CA3AF]">{new Date(c.created_at).toLocaleString('de-DE')}</span>
                  </div>
                  <p className="text-sm text-[#4B5563]">{c.text}</p>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <Input value={commentName} onChange={e => setCommentName(e.target.value)} placeholder="Name" className="border-[#E2E4E0] rounded-lg w-[120px] h-9 text-sm" />
            <Input value={comment} onChange={e => setComment(e.target.value)} placeholder="Kommentar..." className="border-[#E2E4E0] rounded-lg flex-1 h-9 text-sm"
              onKeyDown={e => e.key === 'Enter' && submitComment()} />
            <Button size="sm" onClick={submitComment} className="bg-[#4A5D4E] text-white rounded-lg h-9 px-3"><Send className="w-4 h-4" /></Button>
          </div>
        </div>
      </div>
    </div>
  );
}
