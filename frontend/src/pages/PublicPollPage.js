import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { CalendarClock, Check, X, HelpCircle, Users, MessageSquare, Send, Lock, Plus, CalendarPlus } from 'lucide-react';
import { DateInput, TimeRangeInput } from '../components/DateTimeInput';
import axios from 'axios';
import { toast, Toaster } from 'sonner';
import { useLanguage } from '../contexts/LanguageContext';

const API = process.env.REACT_APP_BACKEND_URL;
const pubApi = axios.create({ baseURL: `${API}/api` });

export default function PublicPollPage() {
  const { t } = useLanguage();
  const { shareToken } = useParams();
  const [poll, setPoll] = useState(null);
  const [loading, setLoading] = useState(true);
  const [voterName, setVoterName] = useState('');
  const [voterEmail, setVoterEmail] = useState('');
  const [votes, setVotes] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [comment, setComment] = useState('');
  const [commentName, setCommentName] = useState('');
  const [password, setPassword] = useState('');
  const [needsPassword, setNeedsPassword] = useState(false);
  const [suggestDate, setSuggestDate] = useState('');
  const [suggestStart, setSuggestStart] = useState('09:00');
  const [suggestEnd, setSuggestEnd] = useState('10:00');

  const fetchPoll = useCallback(async (pwd) => {
    try {
      const params = pwd ? `?pwd=${encodeURIComponent(pwd)}` : '';
      const { data } = await pubApi.get(`/schedule-polls/public/${shareToken}${params}`);
      if (data.requires_password) {
        setNeedsPassword(true);
        if (data.wrong_password) {
          // iter 189 — surface bad-password feedback so the user knows
          // the entry was rejected (instead of silently re-rendering the prompt).
          toast.error('Falsches Passwort');
          setPassword('');
        }
        setLoading(false);
        return;
      }
      setPoll(data);
      setNeedsPassword(false);
    } catch { toast.error('Terminplanung nicht gefunden'); }
    finally { setLoading(false); }
  }, [shareToken]);

  useEffect(() => { fetchPoll(); }, [fetchPoll]);

  const handleVote = (slotId) => {
    setVotes(prev => {
      const current = prev[slotId] || 'none';
      const cycle = poll?.allow_maybe ? ['none', 'yes', 'maybe', 'no'] : ['none', 'yes', 'no'];
      const next = cycle[(cycle.indexOf(current) + 1) % cycle.length];
      return { ...prev, [slotId]: next };
    });
  };

  const submitVote = async () => {
    if (!voterName.trim()) { toast.error('Bitte Name eingeben'); return; }
    const validVotes = Object.fromEntries(Object.entries(votes).filter(([, v]) => v !== 'none'));
    if (Object.keys(validVotes).length === 0) { toast.error('Bitte mindestens ein Zeitfenster bewerten'); return; }
    setSubmitting(true);
    try {
      await pubApi.post(`/schedule-polls/public/${shareToken}/vote`, {
        voter_name: voterName, voter_email: voterEmail, votes: validVotes,
      });
      setSubmitted(true);
      fetchPoll(password);
      toast.success('Abstimmung gespeichert!');
    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler'); }
    finally { setSubmitting(false); }
  };

  const submitComment = async () => {
    if (!commentName.trim() || !comment.trim()) return;
    try {
      await pubApi.post(`/schedule-polls/public/${shareToken}/comment`, { author_name: commentName, text: comment });
      setComment('');
      fetchPoll(password);
    } catch (e) { console.warn("silent error:", e); }
  };

  const submitSuggestion = async () => {
    if (!suggestDate) return;
    try {
      await pubApi.post(`/schedule-polls/public/${shareToken}/suggest`, {
        date: suggestDate, start_time: suggestStart, end_time: suggestEnd, name: voterName || 'Anonym',
      });
      setSuggestDate('');
      fetchPoll(password);
      toast.success('Vorschlag hinzugefuegt');
    } catch (e) { console.warn("silent error:", e); }
  };

  const voteIcon = (v) => {
    if (v === 'yes') return <Check className="w-4 h-4 text-white" />;
    if (v === 'no') return <X className="w-4 h-4 text-white" />;
    if (v === 'maybe') return <HelpCircle className="w-4 h-4 text-white" />;
    return null;
  };

  const voteBg = (v) => {
    if (v === 'yes') return 'bg-[#6B8E23]';
    if (v === 'no') return 'bg-[#C87967]';
    if (v === 'maybe') return 'bg-[#D4A373]';
    return 'bg-[#E2E4E0]';
  };

  const slotScore = (slotId) => {
    if (!poll) return 0;
    return poll.votes.reduce((acc, v) => {
      if (v.votes[slotId] === 'yes') return acc + 2;
      if (v.votes[slotId] === 'maybe') return acc + 1;
      return acc;
    }, 0);
  };

  const bestSlotId = poll?.time_slots?.reduce((best, s) => {
    const score = slotScore(s.slot_id);
    return score > (best.score || 0) ? { id: s.slot_id, score } : best;
  }, { id: null, score: 0 })?.id;

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8] text-[#9CA3AF]">Loading...</div>;

  if (needsPassword) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
        <Toaster position="top-right" richColors />
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 max-w-sm w-full text-center">
          <Lock className="w-10 h-10 text-[#4A5D4E] mx-auto mb-3" />
          <h2 className="text-lg font-medium mb-4">{t('passwordRequired')}</h2>
          <Input type="password" value={password} onChange={e => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && password) fetchPoll(password); }}
            placeholder="Passwort" className="border-[#E2E4E0] rounded-xl mb-3"
            data-testid="poll-password-input" autoFocus />
          <Button data-testid="poll-password-submit" onClick={() => fetchPoll(password)} disabled={!password}
            className="w-full bg-[#4A5D4E] text-white rounded-full">Zugriff</Button>
        </div>
      </div>
    );
  }

  if (!poll) return <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8] text-[#9CA3AF]">{t('notFound')}</div>;

  const isConfirmed = poll.status === 'confirmed';
  const confirmedSlot = poll.time_slots?.find(s => s.slot_id === poll.confirmed_slot_id);

  return (
    <div className="min-h-screen bg-[#F9F9F8]">
      <Toaster position="top-right" richColors />
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center gap-2.5 mb-6">
          <CalendarClock className="w-6 h-6 text-[#4A5D4E]" />
          <span className="text-lg font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
        </div>

        <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6">
          <h1 className="text-xl font-medium text-[#1C1F1D] mb-1" style={{ fontFamily: 'Manrope' }} data-testid="poll-title">{poll.title}</h1>
          {poll.description && <p className="text-sm text-[#6B7280] mb-3">{poll.description}</p>}
          <div className="flex items-center gap-3 text-xs text-[#9CA3AF]">
            <span>Erstellt von {poll.creator_name}</span>
            <span className="flex items-center gap-1"><Users className="w-3 h-3" />{poll.votes?.length || 0} Antworten</span>
          </div>
          {isConfirmed && confirmedSlot && (
            <div className="mt-4 p-4 bg-[#6B8E23]/10 rounded-xl" data-testid="confirmed-slot">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 text-[#6B8E23] font-medium text-sm mb-1">
                    <Check className="w-4 h-4" /> Bestätigt
                  </div>
                  <p className="text-sm text-[#1C1F1D]">
                    {new Date(confirmedSlot.date).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}, {confirmedSlot.start_time} - {confirmedSlot.end_time}
                  </p>
                </div>
                <Button size="sm" onClick={() => window.open(`${API}/api/schedule-polls/${poll.poll_id}/ical`, '_blank')}
                  className="rounded-full bg-[#6B8E23] hover:bg-[#5A7C1E] text-white text-xs px-4" data-testid="public-add-to-calendar">
                  <CalendarPlus className="w-3.5 h-3.5 mr-1" /> Zum Kalender
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Voting Matrix */}
        {!isConfirmed && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6 overflow-x-auto" data-testid="voting-matrix">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left text-xs text-[#6B7280] font-medium pb-3 pr-4 min-w-[120px]">{t('participants')}</th>
                  {poll.time_slots.map(slot => (
                    <th key={slot.slot_id} className={`text-center pb-3 px-2 min-w-[90px] ${slot.slot_id === bestSlotId && poll.votes.length > 0 ? 'bg-[#6B8E23]/5 rounded-t-lg' : ''}`}>
                      <div className="text-xs font-medium text-[#1C1F1D]">{new Date(slot.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })}</div>
                      <div className="text-[10px] text-[#9CA3AF]">{slot.start_time}-{slot.end_time}</div>
                      {slot.slot_id === bestSlotId && poll.votes.length > 0 && <div className="text-[9px] text-[#6B8E23] font-bold mt-0.5">BESTE</div>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {poll.votes.map(vote => (
                  <tr key={vote.vote_id} className="border-t border-[#E2E4E0]">
                    <td className="py-2 pr-4 text-xs text-[#4B5563] font-medium">{vote.voter_name}</td>
                    {poll.time_slots.map(slot => (
                      <td key={slot.slot_id} className={`py-2 px-2 text-center ${slot.slot_id === bestSlotId && poll.votes.length > 0 ? 'bg-[#6B8E23]/5' : ''}`}>
                        <div className={`w-7 h-7 rounded-full ${voteBg(vote.votes[slot.slot_id] || 'none')} flex items-center justify-center mx-auto`}>
                          {voteIcon(vote.votes[slot.slot_id])}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
                {/* Score row */}
                {poll.votes.length > 0 && (
                  <tr className="border-t-2 border-[#E2E4E0]">
                    <td className="py-2 pr-4 text-xs text-[#6B7280] font-bold">Score</td>
                    {poll.time_slots.map(slot => (
                      <td key={slot.slot_id} className={`py-2 px-2 text-center ${slot.slot_id === bestSlotId ? 'bg-[#6B8E23]/5 rounded-b-lg' : ''}`}>
                        <span className={`text-xs font-bold ${slot.slot_id === bestSlotId ? 'text-[#6B8E23]' : 'text-[#6B7280]'}`}>{slotScore(slot.slot_id)}</span>
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Vote Form */}
        {!isConfirmed && !submitted && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6" data-testid="vote-form">
            <h3 className="text-sm font-medium text-[#1C1F1D] mb-4">{t('yourVote')}</h3>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <Input data-testid="voter-name" value={voterName} onChange={e => setVoterName(e.target.value)} placeholder={t('yourName')} className="border-[#E2E4E0] rounded-xl" />
              <Input data-testid="voter-email" value={voterEmail} onChange={e => setVoterEmail(e.target.value)} placeholder="E-Mail (optional)" className="border-[#E2E4E0] rounded-xl" />
            </div>
            <div className="space-y-2 mb-4">
              {poll.time_slots.map(slot => (
                <div key={slot.slot_id} className="flex items-center justify-between p-3 bg-[#F3F4F1] rounded-lg">
                  <div className="text-sm">
                    <span className="font-medium text-[#1C1F1D]">{new Date(slot.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })}</span>
                    <span className="text-[#9CA3AF] ml-2">{slot.start_time} - {slot.end_time}</span>
                  </div>
                  <button onClick={() => handleVote(slot.slot_id)} data-testid={`vote-btn-${slot.slot_id}`}
                    className={`w-9 h-9 rounded-full ${voteBg(votes[slot.slot_id] || 'none')} flex items-center justify-center transition-all hover:scale-110`}>
                    {voteIcon(votes[slot.slot_id] || 'none')}
                  </button>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-4 text-xs text-[#9CA3AF] mb-4">
              <span className="flex items-center gap-1"><div className="w-4 h-4 rounded-full bg-[#6B8E23]" /> Ja</span>
              <span className="flex items-center gap-1"><div className="w-4 h-4 rounded-full bg-[#C87967]" /> Nein</span>
              {poll.allow_maybe && <span className="flex items-center gap-1"><div className="w-4 h-4 rounded-full bg-[#D4A373]" /> Vielleicht</span>}
              <span className="flex items-center gap-1"><div className="w-4 h-4 rounded-full bg-[#E2E4E0]" /> {t('noAnswer')}</span>
            </div>
            <Button onClick={submitVote} disabled={submitting} data-testid="submit-vote"
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11">
              {submitting ? 'Speichere...' : 'Abstimmung abgeben'}
            </Button>
          </div>
        )}

        {submitted && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6 text-center">
            <Check className="w-10 h-10 text-[#6B8E23] mx-auto mb-2" />
            <p className="text-sm text-[#4B5563] font-medium">{t('votingSaved')}</p>
            <Button variant="outline" onClick={() => setSubmitted(false)} className="mt-3 rounded-full border-[#E2E4E0] text-xs">{t('changeAnswer')}</Button>
          </div>
        )}

        {/* Suggest Time Slot */}
        {poll.allow_suggestions && !isConfirmed && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6">
            <h3 className="text-sm font-medium text-[#1C1F1D] mb-3 flex items-center gap-1.5"><Plus className="w-4 h-4" />{t('proposeOwnTime')}</h3>
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <DateInput value={suggestDate} onChange={v => setSuggestDate(v)} className="w-full sm:flex-1" />
              <div className="flex items-center gap-2 w-full sm:w-auto sm:flex-1 min-w-0">
                <TimeRangeInput
                  startTime={suggestStart} endTime={suggestEnd}
                  onStartChange={v => setSuggestStart(v)}
                  onEndChange={v => setSuggestEnd(v)}
                  className="flex-1"
                />
                <Button size="sm" onClick={submitSuggestion} className="bg-[#4A5D4E] text-white rounded-lg h-10 px-3 flex-shrink-0"><Plus className="w-4 h-4" /></Button>
              </div>
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
                    <span className="font-medium text-[#1C1F1D]">{c.author_name}</span>
                    <span className="text-[#9CA3AF]">{new Date(c.created_at).toLocaleString('de-DE')}</span>
                  </div>
                  <p className="text-sm text-[#4B5563]">{c.text}</p>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <Input value={commentName} onChange={e => setCommentName(e.target.value)} placeholder="Name" className="border-[#E2E4E0] rounded-lg w-[120px] h-9 text-sm" data-testid="comment-name" />
            <Input value={comment} onChange={e => setComment(e.target.value)} placeholder="Kommentar schreiben..." className="border-[#E2E4E0] rounded-lg flex-1 h-9 text-sm" data-testid="comment-text"
              onKeyDown={e => e.key === 'Enter' && submitComment()} />
            <Button size="sm" onClick={submitComment} className="bg-[#4A5D4E] text-white rounded-lg h-9 px-3" data-testid="submit-comment"><Send className="w-4 h-4" /></Button>
          </div>
        </div>
      </div>
    </div>
  );
}
