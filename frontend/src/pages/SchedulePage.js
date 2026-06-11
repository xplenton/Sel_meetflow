import { copyToClipboard } from '../lib/clipboard';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Plus, Search, CalendarClock, Users, CheckCircle, Clock, Trash2, Copy, ExternalLink, ChevronLeft, ChevronRight, ListChecks, BarChart3, Share2, CalendarCheck, Globe, Link2, Download } from 'lucide-react';
import ShareMenu from '../components/ShareMenu';
import api from '../lib/api';
import { toast } from 'sonner';
import { flushSync } from 'react-dom';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';

const LIMIT = 10;

export default function SchedulePage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [polls, setPolls] = useState([]);
  const [generalPolls, setGeneralPolls] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [activeTab, setActiveTab] = useState('schedule');
  const [resultPoll, setResultPoll] = useState(null);
  const [resultOpen, setResultOpen] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState(null);

  useEffect(() => { const t = setTimeout(() => setDebouncedSearch(search), 350); return () => clearTimeout(t); }, [search]);
  useEffect(() => { setPage(1); }, [debouncedSearch, activeTab]);

  const fetchPolls = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(LIMIT) });
      if (debouncedSearch) params.set('search', debouncedSearch);
      if (activeTab === 'schedule') {
        const { data } = await api.get(`/schedule-polls?${params}`);
        setPolls(data.polls || []);
        setTotalPages(data.pages || 1);
        setTotal(data.total || 0);
      } else if (activeTab === 'surveys') {
        const { data } = await api.get(`/general-polls?${params}`);
        setGeneralPolls(data.polls || []);
        setTotalPages(data.pages || 1);
        setTotal(data.total || 0);
      } else if (activeTab === 'bookings') {
        const { data } = await api.get('/booking/my-bookings');
        const bks = data.bookings || data || [];
        setBookings(bks);
        setTotalPages(1);
        setTotal(bks.length);
      }
    } catch (e) { console.warn("silent error:", e); } finally { setLoading(false); }
  }, [page, debouncedSearch, activeTab]);

  useEffect(() => { fetchPolls(); }, [fetchPolls]);

  const deletePoll = async (pollId) => {
    if (!window.confirm('Wirklich löschen?')) return;
    try {
      if (activeTab === 'bookings') {
        await api.delete(`/bookings/${pollId}`);
      } else {
        await api.delete(activeTab === 'schedule' ? `/schedule-polls/${pollId}` : `/general-polls/${pollId}`);
      }
      fetchPolls();
      setTimeout(() => toast.success('Gelöscht'), 50);
    } catch (e) { console.warn("silent error:", e); }
  };

  const copyLink = (token) => {
    const url = `${window.location.origin}/poll/${token}`;
    copyToClipboard(url);
    setTimeout(() => toast.success('Link kopiert'), 50);
  };

  const openPollResults = async (poll) => {
    try {
      const { data } = await api.get(`/general-polls/${poll.poll_id}`);
      setResultPoll(data);
      setResultOpen(true);
    } catch {
      toast.error('Ergebnisse konnten nicht geladen werden');
    }
  };

  const statusBadge = (poll) => {
    if (poll.status === 'confirmed') return <Badge className="bg-[#6B8E23]/10 text-[#6B8E23] text-[10px]"><CheckCircle className="w-3 h-3 mr-1" />Bestätigt</Badge>;
    if (poll.deadline && new Date(poll.deadline) < new Date()) return <Badge className="bg-[#C87967]/10 text-[#C87967] text-[10px]"><Clock className="w-3 h-3 mr-1" />Abgelaufen</Badge>;
    return <Badge className="bg-[#4A5D4E]/10 text-[#4A5D4E] text-[10px]"><Clock className="w-3 h-3 mr-1" />Offen</Badge>;
  };

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-3 pt-14 sm:p-4 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="schedule-page">
        <div className="max-w-4xl mx-auto">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
            <h1 className="text-xl sm:text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{t('scheduling')}</h1>
            <div className="grid grid-cols-3 gap-1.5 sm:flex sm:items-center sm:gap-2">
              <Button onClick={() => navigate('/schedule/create')} data-testid="create-poll-button"
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-2 sm:px-4 h-9 text-[10px] sm:text-xs">
                <Plus className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">Terminabstimmung</span><span className="sm:hidden ml-1">Abstimmung</span>
              </Button>
              <Button onClick={() => navigate('/booking/settings')} data-testid="booking-settings-button"
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-2 sm:px-4 h-9 text-[10px] sm:text-xs">
                <Plus className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">Terminbuchung</span><span className="sm:hidden ml-1">Buchung</span>
              </Button>
              <Button onClick={() => navigate('/schedule/survey/create')} data-testid="create-survey-button"
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-2 sm:px-4 h-9 text-[10px] sm:text-xs">
                <ListChecks className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">Umfragen</span><span className="sm:hidden ml-1">Umfrage</span>
              </Button>
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="mb-4">
            <TabsList className="bg-[#F3F4F1] rounded-lg w-full sm:w-auto overflow-x-auto">
              <TabsTrigger value="schedule" className="rounded-lg text-xs sm:text-sm flex-1 sm:flex-none" data-testid="tab-schedule"><CalendarClock className="w-3.5 h-3.5 mr-1 hidden sm:inline" />Terminabstimmung</TabsTrigger>
              <TabsTrigger value="bookings" className="rounded-lg text-xs sm:text-sm flex-1 sm:flex-none" data-testid="tab-bookings"><CalendarCheck className="w-3.5 h-3.5 mr-1 hidden sm:inline" />Terminbuchung</TabsTrigger>
              <TabsTrigger value="surveys" className="rounded-lg text-xs sm:text-sm flex-1 sm:flex-none" data-testid="tab-surveys"><ListChecks className="w-3.5 h-3.5 mr-1 hidden sm:inline" />Umfragen</TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="relative mb-5">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
            <Input data-testid="schedule-search" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Suchen..." className="pl-10 border-[#E2E4E0] rounded-xl h-10" />
          </div>

          {loading ? (
            <div className="text-center py-16 text-[#9CA3AF]">Loading...</div>
          ) : activeTab === 'schedule' ? (
            polls.length === 0 ? (
              <div className="text-center py-20 bg-white border border-[#E2E4E0] rounded-xl">
                <CalendarClock className="w-14 h-14 text-[#E2E4E0] mx-auto mb-4" />
                <p className="text-[#9CA3AF] text-sm mb-4">{t('noSchedulesYet')}</p>
                <Button onClick={() => navigate('/schedule/create')} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-5">
                  <Plus className="w-4 h-4 mr-1.5" /> Erste Terminabstimmung erstellen
                </Button>
              </div>
            ) : (
              <>
                <div className="space-y-3">
                  {polls.map(poll => (
                    <div key={poll.poll_id} className="bg-white border border-[#E2E4E0] rounded-xl p-3 sm:p-5 hover:border-[#4A5D4E]/30 transition-colors"
                      data-testid={`poll-${poll.poll_id}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => navigate(`/schedule/${poll.poll_id}`)}>
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            <h3 className="text-sm font-medium text-[#1C1F1D] truncate">{poll.title}</h3>
                            {statusBadge(poll)}
                          </div>
                          {poll.description && <p className="text-xs text-[#9CA3AF] truncate mb-2">{poll.description}</p>}
                          <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-[10px] sm:text-xs text-[#9CA3AF]">
                            <span className="flex items-center gap-1"><CalendarClock className="w-3 h-3" />{poll.time_slots?.length || 0} Zeitfenster</span>
                            <span className="flex items-center gap-1"><Users className="w-3 h-3" />{poll.votes?.length || 0} Antworten</span>
                            <span className="hidden sm:inline">{new Date(poll.created_at).toLocaleDateString('de-DE')}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-0.5 flex-shrink-0">
                          <Button variant="outline" size="sm" onClick={() => navigate(`/schedule/${poll.poll_id}`)}
                            className="rounded-full border-[#E2E4E0] text-[10px] sm:text-xs h-7 sm:h-8 px-2 sm:px-3 text-[#4A5D4E]"
                            data-testid={`open-poll-${poll.poll_id}`}>
                            <ExternalLink className="w-3 h-3 sm:mr-1" /><span className="hidden sm:inline">Oeffnen</span>
                          </Button>
                          <ShareMenu url={`${window.location.origin}/poll/${poll.share_token}`} title={poll.title} description={poll.description} type="terminplanung" />
                          <button onClick={() => deletePoll(poll.poll_id)} className="p-1.5 sm:p-2 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]" title="Löschen"><Trash2 className="w-3.5 h-3.5 sm:w-4 sm:h-4" /></button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                {totalPages > 1 && (
                  <div className="flex items-center justify-between mt-6 pt-4 border-t border-[#E2E4E0]">
                    <span className="text-xs text-[#9CA3AF]">{total} - Seite {page}/{totalPages}</span>
                    <div className="flex gap-1.5">
                      <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronLeft className="w-4 h-4" /></Button>
                      <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronRight className="w-4 h-4" /></Button>
                    </div>
                  </div>
                )}
              </>
            )
          ) : activeTab === 'bookings' ? (
            bookings.length === 0 ? (
              <div className="text-center py-20 bg-white border border-[#E2E4E0] rounded-xl">
                <CalendarCheck className="w-14 h-14 text-[#E2E4E0] mx-auto mb-4" />
                <p className="text-[#9CA3AF] text-sm mb-4">{t('noBookingsYet')}</p>
                <Button onClick={() => navigate('/booking/settings')} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-5">
                  Buchungsseite einrichten
                </Button>
              </div>
            ) : (
              <>
                <div className="space-y-3">
                  {bookings.map(b => (
                    <div key={b.booking_id} className="bg-white border border-[#E2E4E0] rounded-xl p-3 sm:p-5 hover:border-[#4A5D4E]/30 transition-colors cursor-pointer"
                      data-testid={`booking-${b.booking_id}`} onClick={() => setSelectedBooking(b)}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            <h3 className="text-sm font-medium text-[#1C1F1D]">{b.guest_name || b.booker_name || 'Buchung'}</h3>
                            <Badge className={`text-[10px] ${b.status === 'confirmed' ? 'bg-[#4A5D4E]/10 text-[#4A5D4E]' : b.status === 'cancelled' ? 'bg-[#C87967]/10 text-[#C87967]' : 'bg-[#D4A373]/10 text-[#D4A373]'}`}>
                              {b.status === 'confirmed' ? 'Bestätigt' : b.status === 'cancelled' ? 'Abgesagt' : 'Ausstehend'}
                            </Badge>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-[10px] sm:text-xs text-[#9CA3AF]">
                            <span className="flex items-center gap-1"><CalendarClock className="w-3 h-3" />
                              {b.date ? new Date(b.date + 'T12:00').toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'}
                            </span>
                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />
                              {b.start_time && b.end_time ? `${b.start_time} - ${b.end_time}` : '—'}
                            </span>
                            {b.duration && <span>{b.duration} min</span>}
                          </div>
                        </div>
                        <div className="flex items-center gap-0.5 flex-shrink-0" onClick={e => e.stopPropagation()}>
                          <Button variant="outline" size="sm" onClick={() => setSelectedBooking(b)}
                            className="rounded-full border-[#E2E4E0] text-[10px] sm:text-xs h-7 sm:h-8 px-2 sm:px-3 text-[#4A5D4E]"
                            data-testid={`open-booking-${b.booking_id}`}>
                            <ExternalLink className="w-3 h-3 sm:mr-1" /><span className="hidden sm:inline">Oeffnen</span>
                          </Button>
                          <button onClick={() => deletePoll(b.booking_id)}
                            className="p-1.5 sm:p-2 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]" data-testid={`delete-booking-${b.booking_id}`}>
                            <Trash2 className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                {totalPages > 1 && (
                  <div className="flex items-center justify-between mt-6 pt-4 border-t border-[#E2E4E0]">
                    <span className="text-xs text-[#9CA3AF]">{total} - Seite {page}/{totalPages}</span>
                    <div className="flex gap-1.5">
                      <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronLeft className="w-4 h-4" /></Button>
                      <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronRight className="w-4 h-4" /></Button>
                    </div>
                  </div>
                )}
              </>
            )
          ) : activeTab === 'surveys' ? (
            generalPolls.length === 0 ? (
              <div className="text-center py-20 bg-white border border-[#E2E4E0] rounded-xl">
                <ListChecks className="w-14 h-14 text-[#E2E4E0] mx-auto mb-4" />
                <p className="text-[#9CA3AF] text-sm mb-4">{t('noSurveysYet')}</p>
                <Button onClick={() => navigate('/schedule/survey/create')} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-5">
                  <Plus className="w-4 h-4 mr-1.5" /> Erste Umfrage erstellen
                </Button>
              </div>
            ) : (
              <>
                <div className="space-y-3">
                  {generalPolls.map(poll => (
                    <div key={poll.poll_id} className="bg-white border border-[#E2E4E0] rounded-xl p-3 sm:p-5 hover:border-[#4A5D4E]/30 transition-colors"
                      data-testid={`gpoll-${poll.poll_id}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => openPollResults(poll)}>
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            <h3 className="text-sm font-medium text-[#1C1F1D] truncate">{poll.title}</h3>
                            <Badge className={`text-[10px] ${poll.status === 'closed' ? 'bg-[#C87967]/10 text-[#C87967]' : 'bg-[#4A5D4E]/10 text-[#4A5D4E]'}`}>
                              {poll.status === 'closed' ? 'Geschlossen' : 'Offen'}
                            </Badge>
                            <Badge className="bg-[#F3F4F1] text-[#6B7280] text-[10px]">
                              {poll.poll_type === 'single' ? 'Einzelauswahl' : poll.poll_type === 'multiple' ? 'Mehrfach' : 'Prioritaet'}
                            </Badge>
                          </div>
                          {poll.description && <p className="text-xs text-[#9CA3AF] truncate mb-2">{poll.description}</p>}
                          <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-[10px] sm:text-xs text-[#9CA3AF]">
                            <span className="flex items-center gap-1"><ListChecks className="w-3 h-3" />{poll.options?.length || 0} Optionen</span>
                            <span className="flex items-center gap-1"><Users className="w-3 h-3" />{poll.votes?.length || 0} Antworten</span>
                            <span className="hidden sm:inline">{new Date(poll.created_at).toLocaleDateString('de-DE')}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-0.5 flex-shrink-0">
                          <Button variant="outline" size="sm" onClick={() => openPollResults(poll)}
                            className="rounded-full border-[#E2E4E0] text-[10px] sm:text-xs h-7 sm:h-8 px-2 sm:px-3 text-[#4A5D4E]"
                            data-testid={`open-gpoll-${poll.poll_id}`}>
                            <ExternalLink className="w-3 h-3 sm:mr-1" /><span className="hidden sm:inline">Oeffnen</span>
                          </Button>
                          <ShareMenu url={`${window.location.origin}/survey/${poll.share_token}`} title={poll.title} description={poll.description} type="umfrage" />
                          <button onClick={() => deletePoll(poll.poll_id)}
                            className="p-1.5 sm:p-2 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]" title="Löschen"><Trash2 className="w-3.5 h-3.5 sm:w-4 sm:h-4" /></button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                {totalPages > 1 && (
                  <div className="flex items-center justify-between mt-6 pt-4 border-t border-[#E2E4E0]">
                    <span className="text-xs text-[#9CA3AF]">{total} - Seite {page}/{totalPages}</span>
                    <div className="flex gap-1.5">
                      <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronLeft className="w-4 h-4" /></Button>
                      <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronRight className="w-4 h-4" /></Button>
                    </div>
                  </div>
                )}
              </>
            )
          ) : null}
        </div>
      </main>

      {/* Poll Results Dialog */}
      <Dialog open={resultOpen} onOpenChange={setResultOpen}>
        <DialogContent className="sm:max-w-[520px] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{resultPoll?.title || 'Umfrage-Ergebnisse'}</DialogTitle>
          </DialogHeader>
          {resultPoll && (
            <div className="space-y-4 pt-2">
              {resultPoll.description && <p className="text-sm text-[#6B7280]">{resultPoll.description}</p>}
              <div className="flex items-center gap-3 text-xs text-[#9CA3AF]">
                <span>{resultPoll.votes?.length || 0} Stimmen</span>
                <span>{resultPoll.poll_type === 'single' ? 'Einzelauswahl' : 'Mehrfachwahl'}</span>
                <Badge className={resultPoll.status === 'closed' ? 'bg-[#C87967]/10 text-[#C87967] text-[10px]' : 'bg-[#4A5D4E]/10 text-[#4A5D4E] text-[10px]'}>
                  {resultPoll.status === 'closed' ? 'Geschlossen' : 'Offen'}
                </Badge>
              </div>

              {/* Options with vote bars */}
              <div className="space-y-3">
                {(resultPoll.options || []).map((opt, i) => {
                  const optText = typeof opt === 'string' ? opt : opt.text || opt;
                  const totalVotes = resultPoll.votes?.length || 0;
                  const matchesVote = (v) => {
                    const sel = v.selected_options || v.selected || [];
                    return sel.includes(i) || sel.includes(optText);
                  };
                  const optVotes = resultPoll.votes?.filter(matchesVote).length || 0;
                  const pct = totalVotes > 0 ? Math.round((optVotes / totalVotes) * 100) : 0;
                  const voters = resultPoll.votes?.filter(matchesVote).map(v => v.voter_name) || [];
                  return (
                    <div key={(typeof opt === 'string' ? opt : opt.option_id || opt.text) || `opt-${i}`} className="bg-[#F3F4F1] rounded-lg p-3">
                      <div className="flex justify-between items-center mb-1.5">
                        <span className="text-sm font-medium text-[#1C1F1D]">{typeof opt === 'string' ? opt : opt.text || opt}</span>
                        <span className="text-sm font-bold text-[#4A5D4E]">{pct}%</span>
                      </div>
                      <div className="w-full bg-[#E2E4E0] rounded-full h-2 mb-2">
                        <div className="bg-[#4A5D4E] h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
                      </div>
                      {voters.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {voters.map((name, vi) => (
                            <span key={`${name || 'anon'}-${vi}`} className="text-[10px] bg-white px-1.5 py-0.5 rounded text-[#6B7280]">{name}</span>
                          ))}
                        </div>
                      )}
                      {voters.length === 0 && <p className="text-[10px] text-[#9CA3AF]">{t('noVotes')}</p>}
                    </div>
                  );
                })}
              </div>

              {/* Comments */}
              {resultPoll.comments?.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-[#6B7280] mb-2">Kommentare ({resultPoll.comments.length})</h4>
                  <div className="space-y-2">
                    {resultPoll.comments.map((c, i) => (
                      <div key={c.comment_id || c.created_at || `c-${i}`} className="bg-[#F9F9F8] rounded-lg p-2.5">
                        <span className="text-xs font-medium text-[#1C1F1D]">{c.author_name}</span>
                        <p className="text-xs text-[#6B7280] mt-0.5">{c.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Share link */}
              <div className="flex items-center gap-2 bg-[#F3F4F1] rounded-lg p-2.5">
                <input readOnly value={`${window.location.origin}/survey/${resultPoll.share_token}`}
                  className="flex-1 bg-transparent text-xs text-[#4B5563] outline-none truncate" />
                <Button size="sm" onClick={() => { copyToClipboard(`${window.location.origin}/survey/${resultPoll.share_token}`); toast.success('Link kopiert'); }}
                  className="bg-[#4A5D4E] text-white rounded-full px-2.5 h-6 text-[10px]">
                  <Copy className="w-3 h-3 mr-1" />Kopieren
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
      {/* Booking Detail Dialog */}
      <Dialog open={!!selectedBooking} onOpenChange={(open) => { if (!open) setSelectedBooking(null); }}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle>Buchungsdetails</DialogTitle>
          </DialogHeader>
          {selectedBooking && (
            <div className="space-y-4 pt-2">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">Status</span>
                  <Badge className={`text-xs ${selectedBooking.status === 'confirmed' ? 'bg-[#6B8E23]/10 text-[#6B8E23]' : 'bg-[#C87967]/10 text-[#C87967]'}`}>
                    {selectedBooking.status === 'confirmed' ? 'Bestätigt' : 'Abgesagt'}
                  </Badge>
                </div>
                <div className="bg-[#F3F4F1] rounded-lg p-4 space-y-2.5">
                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-[#4A5D4E]" />
                    <span className="text-sm font-medium text-[#1C1F1D]">{selectedBooking.guest_name}</span>
                  </div>
                  {selectedBooking.guest_email && (
                    <div className="flex items-center gap-2 text-sm text-[#6B7280]">
                      <span className="w-4 h-4 flex items-center justify-center text-[#4A5D4E]">@</span>
                      {selectedBooking.guest_email}
                    </div>
                  )}
                </div>
                <div className="bg-[#F3F4F1] rounded-lg p-4 space-y-2.5">
                  <div className="flex items-center gap-2">
                    <CalendarClock className="w-4 h-4 text-[#4A5D4E]" />
                    <span className="text-sm text-[#1C1F1D]">
                      {selectedBooking.date ? new Date(selectedBooking.date + 'T12:00').toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }) : '—'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-[#4A5D4E]" />
                    <span className="text-sm text-[#1C1F1D]">
                      {selectedBooking.start_time} - {selectedBooking.end_time} ({selectedBooking.duration} Min.)
                    </span>
                  </div>
                </div>
                {selectedBooking.topic && (
                  <div className="bg-[#F3F4F1] rounded-lg p-4">
                    <span className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] block mb-1">Thema</span>
                    <p className="text-sm text-[#1C1F1D]">{selectedBooking.topic}</p>
                  </div>
                )}
                {selectedBooking.page_slug && (
                  <div className="text-xs text-[#9CA3AF]">Buchungsseite: <span className="font-medium">{selectedBooking.page_slug}</span></div>
                )}
                <div className="text-xs text-[#9CA3AF]">
                  Erstellt am: {new Date(selectedBooking.created_at).toLocaleString('de-DE')}
                </div>
                {/* Meeting Link */}
                {selectedBooking.meeting_id && (
                  <div>
                    <span className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] block mb-1.5">Meeting-Link</span>
                    <div className="flex items-center gap-2 bg-[#F3F4F1] rounded-lg p-2.5">
                      <Link2 className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0" />
                      <input readOnly value={`${window.location.origin}/meetings/${selectedBooking.meeting_id}/join`}
                        className="flex-1 bg-transparent text-xs text-[#4B5563] outline-none truncate" data-testid="booking-meeting-link" />
                      <Button size="sm" onClick={() => { copyToClipboard(`${window.location.origin}/meetings/${selectedBooking.meeting_id}/join`); toast.success('Link kopiert'); }}
                        className="bg-[#4A5D4E] text-white rounded-full px-2.5 h-6 text-[10px]" data-testid="copy-meeting-link">
                        <Copy className="w-3 h-3 mr-1" />Kopieren
                      </Button>
                    </div>
                  </div>
                )}
              </div>
              <div className="flex gap-2 pt-2 flex-wrap">
                {selectedBooking.meeting_id && selectedBooking.status === 'confirmed' && (
                  <Button onClick={() => { setSelectedBooking(null); navigate(`/meetings/${selectedBooking.meeting_id}/join`); }}
                    className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full flex-1 text-xs"
                    data-testid="booking-detail-join">
                    Zur Besprechung <ExternalLink className="w-3.5 h-3.5 ml-1" />
                  </Button>
                )}
                <Button variant="outline" onClick={() => { window.open(`${process.env.REACT_APP_BACKEND_URL}/api/bookings/${selectedBooking.booking_id}/ical`, '_blank'); }}
                  className="rounded-full border-[#E2E4E0] text-[#4A5D4E] text-xs" data-testid="booking-detail-ical">
                  <Download className="w-3.5 h-3.5 mr-1" /> .ics Export
                </Button>
                {selectedBooking.status === 'confirmed' && (
                  <Button variant="outline" onClick={() => { deletePoll(selectedBooking.booking_id); setSelectedBooking(null); }}
                    className="rounded-full border-[#C87967] text-[#C87967] hover:bg-[#C87967]/10 text-xs"
                    data-testid="booking-detail-cancel">
                    Stornieren
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
