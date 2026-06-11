import { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { ScrollArea } from '../components/ui/scroll-area';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { X, Plus, BarChart3, MessageCircleQuestion, DoorOpen, Send, Trash2, Check, ThumbsUp, Lock } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

// ============ POLLS TAB ============
function PollsTab({ meetingId, userId }) {
  const { t } = useLanguage();
  const [polls, setPolls] = useState([]);
  const [creating, setCreating] = useState(false);
  const [question, setQuestion] = useState('');
  const [options, setOptions] = useState(['', '']);

  const fetchPolls = useCallback(async () => {
    try { const { data } = await api.get(`/meetings/${meetingId}/polls`); setPolls(data); } catch {}
  }, [meetingId]);

  useEffect(() => { fetchPolls(); const i = setInterval(fetchPolls, 5000); return () => clearInterval(i); }, [fetchPolls]);

  const handleCreate = async () => {
    const validOpts = options.filter(o => o.trim());
    if (!question.trim() || validOpts.length < 2) { toast.error('Need question and 2+ options'); return; }
    try {
      await api.post(`/meetings/${meetingId}/polls`, { question, options: validOpts });
      setCreating(false); setQuestion(''); setOptions(['', '']); fetchPolls();
    } catch { toast.error('Failed to create poll'); }
  };

  const handleVote = async (pollId, idx) => {
    try { await api.post(`/meetings/${meetingId}/polls/${pollId}/vote`, { option_index: idx }); fetchPolls(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Vote failed'); }
  };

  const handleClose = async (pollId) => {
    try { await api.put(`/meetings/${meetingId}/polls/${pollId}/close`); fetchPolls(); } catch {}
  };

  return (
    <div className="space-y-3">
      {!creating ? (
        <Button onClick={() => setCreating(true)} size="sm" data-testid="create-poll-btn"
          className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg text-xs h-8">
          <Plus className="w-3.5 h-3.5 mr-1" /> {t('createPoll')}
        </Button>
      ) : (
        <div className="bg-[#F3F4F1] rounded-lg p-3 space-y-2">
          <Input value={question} onChange={e => setQuestion(e.target.value)} placeholder={t('pollQuestion')}
            className="border-[#E2E4E0] rounded-lg text-xs h-8" data-testid="poll-question-input" />
          {options.map((opt, i) => (
            <div key={i} className="flex gap-1">
              <Input value={opt} onChange={e => { const n = [...options]; n[i] = e.target.value; setOptions(n); }}
                placeholder={`Option ${i + 1}`} className="border-[#E2E4E0] rounded-lg text-xs h-8 flex-1" data-testid={`poll-option-${i}`} />
              {options.length > 2 && <button onClick={() => setOptions(options.filter((_, j) => j !== i))} className="text-[#C87967] p-1"><Trash2 className="w-3 h-3" /></button>}
            </div>
          ))}
          <button onClick={() => setOptions([...options, ''])} className="text-xs text-[#4A5D4E] hover:underline" data-testid="add-poll-option">+ {t('addOption')}</button>
          <div className="flex gap-2">
            <Button onClick={handleCreate} size="sm" data-testid="submit-poll-btn" className="bg-[#4A5D4E] text-white rounded-lg text-xs h-7 flex-1">{t('create')}</Button>
            <Button onClick={() => setCreating(false)} size="sm" variant="outline" className="rounded-lg text-xs h-7 border-[#E2E4E0]">{t('cancel')}</Button>
          </div>
        </div>
      )}

      {polls.map(poll => {
        const hasVoted = poll.options.some(o => o.voters?.includes(userId));
        return (
          <div key={poll.poll_id} className="bg-white rounded-lg border border-[#E2E4E0] p-3" data-testid={`poll-${poll.poll_id}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-[#1C1F1D]">{poll.question}</span>
              {poll.status === 'closed' && <Badge className="text-[9px] bg-[#9CA3AF]/10 text-[#9CA3AF]"><Lock className="w-2.5 h-2.5 mr-0.5" />{t('pollClosed')}</Badge>}
            </div>
            <div className="space-y-1.5">
              {poll.options.map((opt, i) => {
                const pct = poll.total_votes > 0 ? Math.round((opt.votes / poll.total_votes) * 100) : 0;
                return (
                  <button key={i} disabled={hasVoted || poll.status === 'closed'}
                    onClick={() => handleVote(poll.poll_id, i)}
                    className="w-full text-left" data-testid={`vote-${poll.poll_id}-${i}`}>
                    <div className="flex justify-between text-[10px] mb-0.5">
                      <span className="text-[#4B5563]">{opt.text}</span>
                      <span className="text-[#9CA3AF]">{opt.votes} {t('votes')} ({pct}%)</span>
                    </div>
                    <Progress value={pct} className="h-1.5" />
                  </button>
                );
              })}
            </div>
            {poll.status === 'active' && (
              <button onClick={() => handleClose(poll.poll_id)} className="text-[10px] text-[#C87967] mt-2 hover:underline" data-testid={`close-poll-${poll.poll_id}`}>{t('closePoll')}</button>
            )}
            <div className="text-[10px] text-[#9CA3AF] mt-1">{poll.total_votes} total {t('votes')} - {poll.created_by_name}</div>
          </div>
        );
      })}
      {polls.length === 0 && !creating && <p className="text-xs text-[#9CA3AF] text-center py-4">{t('polls')}: none yet</p>}
    </div>
  );
}

// ============ Q&A TAB ============
function QATab({ meetingId, userId, isHost }) {
  const { t } = useLanguage();
  const [questions, setQuestions] = useState([]);
  const [text, setText] = useState('');

  const fetchQA = useCallback(async () => {
    try { const { data } = await api.get(`/meetings/${meetingId}/questions`); setQuestions(data); } catch {}
  }, [meetingId]);

  useEffect(() => { fetchQA(); const i = setInterval(fetchQA, 5000); return () => clearInterval(i); }, [fetchQA]);

  const handleAsk = async () => {
    if (!text.trim()) return;
    try { await api.post(`/meetings/${meetingId}/questions`, { text }); setText(''); fetchQA(); } catch {}
  };

  const handleUpdate = async (qId, updates) => {
    try { await api.put(`/meetings/${meetingId}/questions/${qId}`, updates); fetchQA(); } catch {}
  };

  const handleUpvote = async (qId) => {
    try { await api.post(`/meetings/${meetingId}/questions/${qId}/upvote`); fetchQA(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
  };

  const statusColors = { pending: 'bg-[#D4A373]/10 text-[#D4A373]', approved: 'bg-[#6B8E23]/10 text-[#6B8E23]', answered: 'bg-[#4A5D4E]/10 text-[#4A5D4E]', rejected: 'bg-[#C87967]/10 text-[#C87967]' };

  return (
    <div className="space-y-3">
      <div className="flex gap-1">
        <Input value={text} onChange={e => setText(e.target.value)} placeholder={t('questionText')}
          className="border-[#E2E4E0] rounded-lg text-xs h-8 flex-1" data-testid="qa-input"
          onKeyDown={e => e.key === 'Enter' && handleAsk()} />
        <Button onClick={handleAsk} size="sm" data-testid="submit-question-btn"
          className="bg-[#4A5D4E] text-white rounded-lg h-8 w-8 p-0"><Send className="w-3.5 h-3.5" /></Button>
      </div>

      {questions.map(q => (
        <div key={q.question_id} className="bg-white rounded-lg border border-[#E2E4E0] p-3" data-testid={`question-${q.question_id}`}>
          <div className="flex items-start gap-2 mb-1">
            <button onClick={() => handleUpvote(q.question_id)} className="flex flex-col items-center text-[#9CA3AF] hover:text-[#4A5D4E] mt-0.5"
              data-testid={`upvote-${q.question_id}`}>
              <ThumbsUp className="w-3 h-3" /><span className="text-[9px]">{q.upvotes || 0}</span>
            </button>
            <div className="flex-1">
              <p className="text-xs text-[#1C1F1D] leading-relaxed">{q.text}</p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] text-[#9CA3AF]">{q.asked_by_name}</span>
                <Badge className={`text-[8px] px-1 ${statusColors[q.status] || ''}`}>{t(q.status)}</Badge>
              </div>
            </div>
          </div>
          {q.answer && <div className="mt-2 p-2 bg-[#F3F4F1] rounded text-xs text-[#4B5563]"><strong>{t('answer')}:</strong> {q.answer}</div>}
          {isHost && q.status === 'pending' && (
            <div className="flex gap-1 mt-2">
              <button onClick={() => handleUpdate(q.question_id, { status: 'approved' })} className="text-[10px] text-[#6B8E23] hover:underline" data-testid={`approve-${q.question_id}`}>{t('approve')}</button>
              <button onClick={() => handleUpdate(q.question_id, { status: 'rejected' })} className="text-[10px] text-[#C87967] hover:underline" data-testid={`reject-${q.question_id}`}>{t('reject')}</button>
            </div>
          )}
          {isHost && q.status === 'approved' && (
            <button onClick={() => handleUpdate(q.question_id, { status: 'answered' })} className="text-[10px] text-[#4A5D4E] hover:underline mt-1" data-testid={`answer-${q.question_id}`}>{t('markAnswered')}</button>
          )}
        </div>
      ))}
      {questions.length === 0 && <p className="text-xs text-[#9CA3AF] text-center py-4">{t('qa')}: no questions yet</p>}
    </div>
  );
}

// ============ BREAKOUT ROOMS TAB ============
function BreakoutTab({ meetingId, participants }) {
  const { t } = useLanguage();
  const [rooms, setRooms] = useState([]);
  const [name, setName] = useState('');
  const [broadcastMsg, setBroadcastMsg] = useState('');

  const fetchRooms = useCallback(async () => {
    try { const { data } = await api.get(`/meetings/${meetingId}/breakout-rooms`); setRooms(data); } catch {}
  }, [meetingId]);

  useEffect(() => { fetchRooms(); }, [fetchRooms]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    try { await api.post(`/meetings/${meetingId}/breakout-rooms`, { name }); setName(''); fetchRooms(); } catch {}
  };

  const handleDelete = async (roomId) => {
    try { await api.delete(`/meetings/${meetingId}/breakout-rooms/${roomId}`); fetchRooms(); } catch {}
  };

  const handleToggle = async (room) => {
    const newStatus = room.status === 'open' ? 'closed' : 'open';
    try { await api.put(`/meetings/${meetingId}/breakout-rooms/${room.room_id}`, { status: newStatus }); fetchRooms(); } catch {}
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-1">
        <Input value={name} onChange={e => setName(e.target.value)} placeholder={t('roomName')}
          className="border-[#E2E4E0] rounded-lg text-xs h-8 flex-1" data-testid="breakout-room-name" />
        <Button onClick={handleCreate} size="sm" data-testid="create-breakout-btn"
          className="bg-[#4A5D4E] text-white rounded-lg h-8 px-3 text-xs">{t('createRoom')}</Button>
      </div>

      {rooms.map(room => (
        <div key={room.room_id} className="bg-white rounded-lg border border-[#E2E4E0] p-3" data-testid={`breakout-${room.room_id}`}>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <DoorOpen className="w-3.5 h-3.5 text-[#4A5D4E]" />
              <span className="text-xs font-medium text-[#1C1F1D]">{room.name}</span>
            </div>
            <div className="flex items-center gap-1">
              <Badge className={`text-[9px] ${room.status === 'open' ? 'bg-[#6B8E23]/10 text-[#6B8E23]' : 'bg-[#9CA3AF]/10 text-[#9CA3AF]'}`}>{room.status}</Badge>
              <button onClick={() => handleToggle(room)} className="text-[10px] text-[#4A5D4E] hover:underline"
                data-testid={`toggle-room-${room.room_id}`}>{room.status === 'open' ? t('closeRoom') : t('openRoom')}</button>
              <button onClick={() => handleDelete(room.room_id)} className="p-0.5 text-[#C87967]"
                data-testid={`delete-room-${room.room_id}`}><Trash2 className="w-3 h-3" /></button>
            </div>
          </div>
          <div className="text-[10px] text-[#9CA3AF]">{room.participant_ids?.length || 0} {t('participants').toLowerCase()}</div>
        </div>
      ))}
      {rooms.length === 0 && <p className="text-xs text-[#9CA3AF] text-center py-4">{t('breakoutRooms')}: none yet</p>}
    </div>
  );
}

// ============ MAIN PANEL ============
export default function MeetingExtrasPanel({ meetingId, userId, isHost, participants, onClose }) {
  const { t } = useLanguage();

  return (
    <div className="w-full sm:w-80 fixed inset-0 sm:static sm:inset-auto bg-white border-l border-[#E2E4E0] flex flex-col h-full z-40 sm:z-auto" data-testid="meeting-extras-panel">
      <div className="flex items-center justify-between p-3 border-b border-[#E2E4E0]">
        <span className="text-sm font-medium text-[#1C1F1D]">Meeting Tools</span>
        <button onClick={onClose} className="p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF]" data-testid="close-extras-panel"><X className="w-4 h-4" /></button>
      </div>

      <Tabs defaultValue="polls" className="flex-1 flex flex-col">
        <TabsList className="bg-[#F3F4F1] mx-3 mt-2 rounded-lg">
          <TabsTrigger value="polls" className="rounded-lg text-[10px] px-2" data-testid="extras-tab-polls"><BarChart3 className="w-3 h-3 mr-1" />{t('polls')}</TabsTrigger>
          <TabsTrigger value="qa" className="rounded-lg text-[10px] px-2" data-testid="extras-tab-qa"><MessageCircleQuestion className="w-3 h-3 mr-1" />{t('qa')}</TabsTrigger>
          <TabsTrigger value="breakout" className="rounded-lg text-[10px] px-2" data-testid="extras-tab-breakout"><DoorOpen className="w-3 h-3 mr-1" />{t('breakoutRooms')}</TabsTrigger>
        </TabsList>
        <ScrollArea className="flex-1 p-3">
          <TabsContent value="polls" className="mt-0"><PollsTab meetingId={meetingId} userId={userId} /></TabsContent>
          <TabsContent value="qa" className="mt-0"><QATab meetingId={meetingId} userId={userId} isHost={isHost} /></TabsContent>
          <TabsContent value="breakout" className="mt-0"><BreakoutTab meetingId={meetingId} participants={participants} /></TabsContent>
        </ScrollArea>
      </Tabs>
    </div>
  );
}
