import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import Sidebar from '../components/Sidebar';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import {
  Video, Plus, Calendar, Search, Sparkles, Zap, ChevronLeft, ChevronRight,
} from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import MeetingRow from '../components/meetings/MeetingRow';

export default function MeetingsPage() {
  const { user } = useAuth();
  const { t, language } = useLanguage();
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState([]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('upcoming');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const LIMIT = 10;

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchMeetings = useCallback(async () => {
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(LIMIT) });
      if (tab === 'upcoming') params.set('meeting_type', 'upcoming');
      else if (tab === 'past') params.set('meeting_type', 'past');
      if (debouncedSearch) params.set('search', debouncedSearch);
      const { data } = await api.get(`/meetings?${params}`);
      setMeetings(data.meetings || []);
      setTotalPages(data.pages || 1);
      setTotalCount(data.total || 0);
    } catch (err) {
      console.error('Failed to fetch meetings:', err);
    } finally { setLoading(false); }
  }, [page, tab, debouncedSearch]);

  useEffect(() => { setLoading(true); fetchMeetings(); }, [fetchMeetings]);
  useEffect(() => { setPage(1); }, [tab, debouncedSearch]);

  const startInstant = async () => {
    try {
      const { data } = await api.post('/meetings', {
        title: `${user?.name || 'User'}'s Meeting`,
        meeting_type: 'instant',
      });
      navigate(`/meetings/${data.meeting_id}/join`);
    } catch { toast.error('Meeting konnte nicht erstellt werden'); }
  };

  const handleQuickJoin = () => {
    if (joinCode.trim()) navigate(`/meetings/${joinCode.trim()}/join`);
  };

  const formatDate = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const statusColor = { active: 'bg-[#6B8E23]/10 text-[#6B8E23]', scheduled: 'bg-[#D4A373]/10 text-[#D4A373]', ended: 'bg-[#9CA3AF]/10 text-[#9CA3AF]' };

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="meetings-page">
        <div className="max-w-5xl mx-auto">

          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{t('dashboard')}</h1>
          </div>

          {/* Quick Actions Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-8">
            <button onClick={startInstant} data-testid="start-instant-meeting-button"
              className="relative overflow-hidden bg-[#4A5D4E] rounded-xl p-5 text-left transition-all active:scale-[0.98] group hover:shadow-lg hover:shadow-[#4A5D4E]/10">
              <div className="absolute top-0 right-0 w-24 h-24 bg-white/5 rounded-full -translate-y-8 translate-x-8" />
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-lg bg-white/15 flex items-center justify-center">
                  <Zap className="w-4.5 h-4.5 text-white" />
                </div>
                <span className="font-medium text-sm text-white">{t('startInstantMeeting')}</span>
              </div>
              <p className="text-white/60 text-xs">{t('instantMeetingDesc')}</p>
            </button>

            <button onClick={() => navigate('/meetings/create')} data-testid="schedule-meeting-button"
              className="bg-white border border-[#E2E4E0] rounded-xl p-5 text-left hover:border-[#4A5D4E]/40 transition-all active:scale-[0.98] group">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-lg bg-[#4A5D4E]/8 flex items-center justify-center">
                  <Calendar className="w-4.5 h-4.5 text-[#4A5D4E]" />
                </div>
                <span className="font-medium text-sm text-[#1C1F1D]">{t('scheduleMeeting')}</span>
              </div>
              <p className="text-[#9CA3AF] text-xs">{t('scheduleMeetingDesc')}</p>
            </button>

            <div className="bg-white border border-[#E2E4E0] rounded-xl p-5">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-9 h-9 rounded-lg bg-[#4A5D4E]/8 flex items-center justify-center">
                  <Plus className="w-4.5 h-4.5 text-[#4A5D4E]" />
                </div>
                <span className="font-medium text-sm text-[#1C1F1D]">{t('quickJoin')}</span>
              </div>
              <div className="flex gap-2">
                <Input data-testid="join-code-input" value={joinCode} onChange={e => setJoinCode(e.target.value)}
                  placeholder={t('enterMeetingCode')} className="border-[#E2E4E0] rounded-lg h-9 text-sm flex-1"
                  onKeyDown={e => e.key === 'Enter' && handleQuickJoin()} />
                <Button data-testid="quick-join-button" onClick={handleQuickJoin} size="sm"
                  className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg h-9 px-4">{t('join')}</Button>
              </div>
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
            <Input data-testid="search-meetings-input" value={search} onChange={e => setSearch(e.target.value)}
              placeholder={t('searchMeetings')} className="pl-10 border-[#E2E4E0] rounded-xl h-10" />
          </div>

          {/* Tabs */}
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="bg-[#F3F4F1] mb-4 rounded-lg">
              <TabsTrigger value="upcoming" data-testid="tab-upcoming" className="rounded-lg text-sm">{t('upcomingMeetings')}</TabsTrigger>
              <TabsTrigger value="past" data-testid="tab-past" className="rounded-lg text-sm">{t('pastMeetings')}</TabsTrigger>
            </TabsList>

            <TabsContent value={tab} forceMount>
              {loading ? (
                <div className="text-center py-12 text-[#9CA3AF]">Loading...</div>
              ) : meetings.length === 0 ? (
                <div className="text-center py-16 bg-white border border-[#E2E4E0] rounded-xl">
                  <Calendar className="w-12 h-12 text-[#E2E4E0] mx-auto mb-3" />
                  <p className="text-[#9CA3AF] text-sm">{t('noMeetings')}</p>
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    {meetings.map(m => (
                      <MeetingRow key={m.meeting_id} meeting={m} t={t} formatDate={formatDate} statusColor={statusColor} navigate={navigate} onRefresh={fetchMeetings} />
                    ))}
                  </div>
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between mt-6 pt-4 border-t border-[#E2E4E0]" data-testid="pagination-controls">
                      <span className="text-xs text-[#9CA3AF]">{totalCount} Meetings - Seite {page} von {totalPages}</span>
                      <div className="flex items-center gap-1.5">
                        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)}
                          data-testid="pagination-prev" className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]">
                          <ChevronLeft className="w-4 h-4" />
                        </Button>
                        {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                          let p;
                          if (totalPages <= 5) p = i + 1;
                          else if (page <= 3) p = i + 1;
                          else if (page >= totalPages - 2) p = totalPages - 4 + i;
                          else p = page - 2 + i;
                          return (
                            <Button key={p} size="sm" variant={p === page ? 'default' : 'outline'} onClick={() => setPage(p)}
                              data-testid={`pagination-page-${p}`}
                              className={`rounded-lg h-8 w-8 p-0 text-xs ${p === page ? 'bg-[#4A5D4E] text-white hover:bg-[#3E4E42]' : 'border-[#E2E4E0]'}`}>
                              {p}
                            </Button>
                          );
                        })}
                        <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                          data-testid="pagination-next" className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]">
                          <ChevronRight className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}

