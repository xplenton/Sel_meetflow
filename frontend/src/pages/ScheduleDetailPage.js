import { copyToClipboard } from '../lib/clipboard';
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ArrowLeft, Check, X, HelpCircle, Users, Copy, ExternalLink, CalendarClock, CheckCircle, Video, FileDown, FileText, Sparkles, Loader2, CalendarPlus } from 'lucide-react';
import ShareMenu from '../components/ShareMenu';
import api from '../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../contexts/LanguageContext';
export default function ScheduleDetailPage() {
  const { t } = useLanguage();
  const { pollId } = useParams();
  const navigate = useNavigate();
  const [poll, setPoll] = useState(null);
  const [loading, setLoading] = useState(true);
  const [aiSuggestion, setAiSuggestion] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);

  const fetchPoll = useCallback(async () => {
    try { const { data } = await api.get(`/schedule-polls/${pollId}`); setPoll(data); }
    catch { setTimeout(() => toast.error('Nicht gefunden'), 50); }
    finally { setLoading(false); }
  }, [pollId]);

  useEffect(() => { fetchPoll(); }, [fetchPoll]);

  const confirmSlot = async (slotId) => {
    if (!window.confirm('Diesen Termin bestätigen? Bei Aktivierung wird automatisch ein Meeting erstellt.')) return;
    try {
      const { data } = await api.post(`/schedule-polls/${pollId}/confirm`, { slot_id: slotId });
      setTimeout(() => toast.success(data.meeting_id ? `Bestätigt! Meeting ${data.meeting_code} erstellt.` : 'Bestätigt!'), 50);
      fetchPoll();
    } catch (err) { setTimeout(() => toast.error(err.response?.data?.detail || 'Fehler'), 50); }
  };

  const copyLink = () => {
    const url = `${window.location.origin}/poll/${poll.share_token}`;
    copyToClipboard(url);
    setTimeout(() => toast.success('Link kopiert'), 50);
  };

  const exportCSV = () => { window.open(`${process.env.REACT_APP_BACKEND_URL}/api/schedule-polls/${pollId}/export/csv`, '_blank'); };
  const exportPDF = () => { window.open(`${process.env.REACT_APP_BACKEND_URL}/api/schedule-polls/${pollId}/export/pdf`, '_blank'); };

  // iOS-safe download for .ics — a plain anchor with download attribute fires
  // the "Add to Calendar" action reliably, unlike window.open which can get
  // swallowed by Safari's popup blocker or crash on inline rendering.
  const downloadIcal = () => {
    const a = document.createElement('a');
    a.href = `${process.env.REACT_APP_BACKEND_URL}/api/schedule-polls/${pollId}/ical`;
    a.download = `termin_${pollId}.ics`;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => document.body.removeChild(a), 0);
  };

  const getAiSuggestion = async () => {
    setAiLoading(true);
    try {
      const { data } = await api.post(`/schedule-polls/${pollId}/ai-suggest`);
      setAiSuggestion(data.suggestion);
    } catch (err) { setTimeout(() => toast.error(err.response?.data?.detail || 'KI-Vorschlag fehlgeschlagen'), 50); }
    finally { setAiLoading(false); }
  };

  const slotScore = (slotId) => {
    if (!poll) return { yes: 0, maybe: 0, no: 0, total: 0 };
    let yes = 0, maybe = 0, no = 0;
    poll.votes.forEach(v => {
      if (v.votes[slotId] === 'yes') yes++;
      else if (v.votes[slotId] === 'maybe') maybe++;
      else if (v.votes[slotId] === 'no') no++;
    });
    return { yes, maybe, no, total: yes * 2 + maybe };
  };

  const bestSlotId = poll?.time_slots?.reduce((best, s) => {
    const score = slotScore(s.slot_id).total;
    return score > (best.score || 0) ? { id: s.slot_id, score } : best;
  }, { id: null, score: 0 })?.id;

  const voteIcon = (v) => {
    if (v === 'yes') return <div className="w-6 h-6 rounded-full bg-[#6B8E23] flex items-center justify-center"><Check className="w-3.5 h-3.5 text-white" /></div>;
    if (v === 'no') return <div className="w-6 h-6 rounded-full bg-[#C87967] flex items-center justify-center"><X className="w-3.5 h-3.5 text-white" /></div>;
    if (v === 'maybe') return <div className="w-6 h-6 rounded-full bg-[#D4A373] flex items-center justify-center"><HelpCircle className="w-3.5 h-3.5 text-white" /></div>;
    return <div className="w-6 h-6 rounded-full bg-[#E2E4E0]" />;
  };

  if (loading) return <div className="flex min-h-screen bg-[#F9F9F8]"><Sidebar /><main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 text-center pt-24 text-[#9CA3AF]">Loading...</main></div>;
  if (!poll) return <div className="flex min-h-screen bg-[#F9F9F8]"><Sidebar /><main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 text-center pt-24 text-[#9CA3AF]">{t('notFound')}</main></div>;

  const isConfirmed = poll.status === 'confirmed';
  const confirmedSlot = poll.time_slots?.find(s => s.slot_id === poll.confirmed_slot_id);

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="schedule-detail-page">
        <div className="max-w-4xl mx-auto">
          <button onClick={() => navigate('/schedule')} className="flex items-center gap-1.5 text-sm text-[#4B5563] hover:text-[#1C1F1D] mb-6 ml-12 sm:ml-0">
            <ArrowLeft className="w-4 h-4" /> Zurück
          </button>

          {/* Header */}
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 sm:p-6 mb-6">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <h1 className="text-lg sm:text-xl font-medium text-[#1C1F1D] break-words" style={{ fontFamily: 'Manrope', wordBreak: 'break-word', overflowWrap: 'anywhere' }}>{poll.title}</h1>
                  {isConfirmed ? <Badge className="bg-[#6B8E23]/10 text-[#6B8E23] text-[10px] flex-shrink-0"><CheckCircle className="w-3 h-3 mr-1" />Bestätigt</Badge>
                    : <Badge className="bg-[#4A5D4E]/10 text-[#4A5D4E] text-[10px] flex-shrink-0">Offen</Badge>}
                </div>
                {poll.description && <p className="text-sm text-[#6B7280] mb-2 break-words">{poll.description}</p>}
                <span className="text-xs text-[#9CA3AF] flex items-center gap-1"><Users className="w-3 h-3" />{poll.votes?.length || 0} Antworten</span>
              </div>
              <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-2 sm:shrink-0">
                <ShareMenu url={`${window.location.origin}/poll/${poll.share_token}`} title={poll.title} description={poll.description} type="terminplanung" />
                <Button size="sm" variant="outline" onClick={copyLink} className="rounded-full border-[#E2E4E0] text-xs" data-testid="copy-poll-link">
                  <Copy className="w-3.5 h-3.5 mr-1" /> Link
                </Button>
                <Button size="sm" variant="outline" onClick={exportCSV} className="rounded-full border-[#E2E4E0] text-xs" data-testid="export-csv">
                  <FileDown className="w-3.5 h-3.5 mr-1" /> CSV
                </Button>
                <Button size="sm" variant="outline" onClick={exportPDF} className="rounded-full border-[#E2E4E0] text-xs" data-testid="export-pdf">
                  <FileText className="w-3.5 h-3.5 mr-1" /> PDF
                </Button>
              </div>
            </div>
            {isConfirmed && confirmedSlot && (
              <div className="mt-4 p-4 bg-[#6B8E23]/10 rounded-xl" data-testid="confirmed-info">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-[#6B8E23] font-medium mb-1">Bestätiger Termin:</p>
                    <p className="text-sm text-[#1C1F1D]">{new Date(confirmedSlot.date).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}, {confirmedSlot.start_time} - {confirmedSlot.end_time}</p>
                  </div>
                  <Button size="sm" onClick={downloadIcal}
                    className="rounded-full bg-[#6B8E23] hover:bg-[#5A7C1E] text-white text-xs px-4 sm:flex-shrink-0" data-testid="add-to-calendar">
                    <CalendarPlus className="w-3.5 h-3.5 mr-1" /> Zum Kalender
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Results Matrix */}
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6 overflow-x-auto" data-testid="results-matrix">
            <h3 className="text-sm font-medium text-[#1C1F1D] mb-4">Ergebnisse</h3>
            {poll.votes.length === 0 ? (
              <p className="text-sm text-[#9CA3AF] text-center py-8">{t('noVotes')}</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-left text-xs text-[#6B7280] font-medium pb-3 pr-4 min-w-[140px]">Teilnehmer</th>
                    {poll.time_slots.map(slot => {
                      const score = slotScore(slot.slot_id);
                      const isBest = slot.slot_id === bestSlotId && poll.votes.length > 0;
                      return (
                        <th key={slot.slot_id} className={`text-center pb-3 px-2 min-w-[100px] ${isBest ? 'bg-[#6B8E23]/5 rounded-t-lg' : ''}`}>
                          <div className="text-xs font-medium text-[#1C1F1D]">{new Date(slot.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })}</div>
                          <div className="text-[10px] text-[#9CA3AF]">{slot.start_time}-{slot.end_time}</div>
                          {isBest && <div className="text-[9px] text-[#6B8E23] font-bold mt-0.5">BESTE</div>}
                          <div className="text-[10px] text-[#6B7280] mt-1">{score.yes}x Ja {score.maybe > 0 ? `${score.maybe}x ` : ''}</div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {poll.votes.map(vote => (
                    <tr key={vote.vote_id} className="border-t border-[#E2E4E0]">
                      <td className="py-2.5 pr-4">
                        <span className="text-xs font-medium text-[#4B5563]">{vote.voter_name}</span>
                        {vote.voter_email && <span className="text-[10px] text-[#9CA3AF] block">{vote.voter_email}</span>}
                      </td>
                      {poll.time_slots.map(slot => (
                        <td key={slot.slot_id} className={`py-2.5 px-2 text-center ${slot.slot_id === bestSlotId && poll.votes.length > 0 ? 'bg-[#6B8E23]/5' : ''}`}>
                          {voteIcon(vote.votes[slot.slot_id])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Confirm Buttons */}
          {!isConfirmed && poll.votes.length > 0 && (
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6" data-testid="confirm-section">
              <h3 className="text-sm font-medium text-[#1C1F1D] mb-3">{t('confirmAppointment')}</h3>
              <p className="text-xs text-[#9CA3AF] mb-4">Wähle den besten Termin aus und bestätitge ihn. Ein MeetFlow-Meeting wird automatisch erstellt.</p>
              <div className="space-y-2">
                {poll.time_slots.map(slot => {
                  const score = slotScore(slot.slot_id);
                  const isBest = slot.slot_id === bestSlotId;
                  return (
                    <div key={slot.slot_id} className={`flex items-center justify-between p-3 rounded-lg border ${isBest ? 'border-[#6B8E23] bg-[#6B8E23]/5' : 'border-[#E2E4E0]'}`}>
                      <div>
                        <span className="text-sm font-medium text-[#1C1F1D]">{new Date(slot.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'long' })}</span>
                        <span className="text-sm text-[#9CA3AF] ml-2">{slot.start_time} - {slot.end_time}</span>
                        <span className={`text-xs ml-3 ${isBest ? 'text-[#6B8E23] font-bold' : 'text-[#9CA3AF]'}`}>{score.yes} Ja, {score.maybe} Vielleicht</span>
                      </div>
                      <Button size="sm" onClick={() => confirmSlot(slot.slot_id)} data-testid={`confirm-slot-${slot.slot_id}`}
                        className={`rounded-full px-4 text-xs ${isBest ? 'bg-[#6B8E23] hover:bg-[#5A7C1E] text-white' : 'bg-[#4A5D4E] hover:bg-[#3E4E42] text-white'}`}>
                        <Video className="w-3.5 h-3.5 mr-1" /> Bestätigen
                      </Button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* AI Suggestion */}
          {!isConfirmed && poll.votes.length > 0 && (
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6" data-testid="ai-suggestion-section">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-[#1C1F1D] flex items-center gap-1.5"><Sparkles className="w-4 h-4 text-[#D4A373]" />KI-Terminvorschlag</h3>
                <Button size="sm" onClick={getAiSuggestion} disabled={aiLoading} data-testid="get-ai-suggestion"
                  className="rounded-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs px-4">
                  {aiLoading ? <><Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />Analysiere...</> : <><Sparkles className="w-3.5 h-3.5 mr-1" />KI analysieren</>}
                </Button>
              </div>
              {aiSuggestion && (
                <div className="bg-[#F3F4F1] rounded-xl p-4 text-sm text-[#4B5563] leading-relaxed whitespace-pre-wrap" style={{ borderLeft: '3px solid #D4A373' }}
                  data-testid="ai-suggestion-content">
                  {aiSuggestion}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
