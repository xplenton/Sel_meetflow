import { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Disc, FileText, Search, Video, Clock, Calendar, ChevronLeft, ChevronRight, Play, X, Sparkles } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import { format } from 'date-fns';

const LIMIT = 10;

export default function RecordingsPage() {
  const { t } = useLanguage();
  const [tab, setTab] = useState('recordings');
  const [recordings, setRecordings] = useState([]);
  const [transcripts, setTranscripts] = useState([]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [recPage, setRecPage] = useState(1);
  const [playingRec, setPlayingRec] = useState(null);
  const [recTotal, setRecTotal] = useState(0);
  const [recPages, setRecPages] = useState(1);
  const [trPage, setTrPage] = useState(1);
  const [trTotal, setTrTotal] = useState(0);
  const [trPages, setTrPages] = useState(1);
  const [summarizing, setSummarizing] = useState('');
  const [summaryDialog, setSummaryDialog] = useState(null);

  const requestSummary = async (rec) => {
    setSummarizing(rec.recording_id);
    try {
      const { data } = await api.post(`/recordings/${rec.recording_id}/summarize`);
      setRecordings(prev => prev.map(r => r.recording_id === rec.recording_id ? { ...r, ai_summary: data.summary, ai_summary_at: new Date().toISOString() } : r));
      setSummaryDialog({ ...rec, ai_summary: data.summary });
      toast.success('Zusammenfassung erstellt');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler bei KI-Zusammenfassung');
    } finally {
      setSummarizing('');
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => { setRecPage(1); setTrPage(1); }, [debouncedSearch]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const recParams = new URLSearchParams({ page: String(recPage), limit: String(LIMIT) });
      const trParams = new URLSearchParams({ page: String(trPage), limit: String(LIMIT) });
      if (debouncedSearch) { recParams.set('search', debouncedSearch); trParams.set('search', debouncedSearch); }
      const [recRes, trRes] = await Promise.all([
        api.get(`/recordings?${recParams}`),
        api.get(`/transcripts?${trParams}`),
      ]);
      setRecordings(recRes.data.recordings || []);
      setRecTotal(recRes.data.total || 0);
      setRecPages(recRes.data.pages || 1);
      setTranscripts(trRes.data.transcripts || []);
      setTrTotal(trRes.data.total || 0);
      setTrPages(trRes.data.pages || 1);
    } catch (e) { console.warn("silent error:", e); } finally { setLoading(false); }
  }, [recPage, trPage, debouncedSearch]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const formatDate = (iso) => {
    if (!iso) return '';
    return format(new Date(iso), 'MMM dd, yyyy HH:mm');
  };

  const PaginationBar = ({ page, setPage, totalPages, total, label }) => {
    if (totalPages <= 1) return null;
    return (
      <div className="flex items-center justify-between mt-6 pt-4 border-t border-[#E2E4E0]" data-testid={`${label}-pagination`}>
        <span className="text-xs text-[#9CA3AF]">{total} {label} - Seite {page} von {totalPages}</span>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)}
            className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronLeft className="w-4 h-4" /></Button>
          {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
            let p;
            if (totalPages <= 5) p = i + 1;
            else if (page <= 3) p = i + 1;
            else if (page >= totalPages - 2) p = totalPages - 4 + i;
            else p = page - 2 + i;
            return (
              <Button key={p} size="sm" variant={p === page ? 'default' : 'outline'} onClick={() => setPage(p)}
                className={`rounded-lg h-8 w-8 p-0 text-xs ${p === page ? 'bg-[#4A5D4E] text-white hover:bg-[#3E4E42]' : 'border-[#E2E4E0]'}`}>{p}</Button>
            );
          })}
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
            className="rounded-lg h-8 w-8 p-0 border-[#E2E4E0]"><ChevronRight className="w-4 h-4" /></Button>
        </div>
      </div>
    );
  };

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="recordings-page">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-2xl font-medium tracking-tight mb-6 text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{t('recordings')}</h1>

          <div className="relative mb-6">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
            <Input data-testid="recordings-search" value={search} onChange={e => setSearch(e.target.value)}
              placeholder={t('search')} className="pl-10 border-[#E2E4E0] rounded-xl h-10" />
          </div>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="bg-[#F3F4F1] mb-4 rounded-lg">
              <TabsTrigger value="recordings" data-testid="tab-recordings" className="rounded-lg text-sm">
                <Disc className="w-3.5 h-3.5 mr-1.5" />{t('recordings')} ({recTotal})
              </TabsTrigger>
              <TabsTrigger value="transcripts" data-testid="tab-transcripts" className="rounded-lg text-sm">
                <FileText className="w-3.5 h-3.5 mr-1.5" />{t('transcripts')} ({trTotal})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="recordings">
              {loading ? (
                <div className="text-center py-12 text-[#9CA3AF]">Loading...</div>
              ) : recordings.length === 0 ? (
                <EmptyState icon={Disc} text={t('noRecordings')} />
              ) : (
                <>
                  <div className="space-y-3">
                    {recordings.map(rec => (
                      <div key={rec.recording_id} className="bg-white border border-[#E2E4E0] rounded-xl p-5 hover:border-[#4A5D4E]/30 transition-colors"
                        data-testid={`recording-${rec.recording_id}`}>
                        <div className="flex items-center gap-4">
                          <div className="w-12 h-12 rounded-lg bg-[#C87967]/10 flex items-center justify-center flex-shrink-0">
                            <Disc className="w-6 h-6 text-[#C87967]" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-medium text-[#1C1F1D] truncate">{rec.title}</h3>
                            <div className="flex items-center gap-3 text-xs text-[#9CA3AF] mt-1 flex-wrap">
                              <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{formatDate(rec.created_at)}</span>
                              {rec.duration > 0 && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{rec.duration} min</span>}
                              <span className="flex items-center gap-1"><Video className="w-3 h-3" />{rec.meeting_id}</span>
                              {rec.ai_summary && <span className="flex items-center gap-1 text-[#6B8E23]"><Sparkles className="w-3 h-3" />KI-Zusammenfassung</span>}
                            </div>
                          </div>
                          <Button size="sm" variant="outline" disabled={summarizing === rec.recording_id}
                            onClick={() => rec.ai_summary ? setSummaryDialog(rec) : requestSummary(rec)}
                            className="rounded-full text-xs h-8 border-[#4A5D4E]/30 text-[#4A5D4E] hover:bg-[#4A5D4E]/5"
                            data-testid={`summarize-${rec.recording_id}`}>
                            <Sparkles className="w-3 h-3 mr-1" />
                            {summarizing === rec.recording_id ? 'KI arbeitet...' : rec.ai_summary ? 'Zusammenfassung' : 'KI-Zusammenfassung'}
                          </Button>
                          {rec.url ? (
                            <Button size="sm" onClick={() => setPlayingRec(rec)} data-testid={`play-${rec.recording_id}`}
                              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs h-8 px-4">
                              <Play className="w-3.5 h-3.5 mr-1" /> Abspielen
                            </Button>
                          ) : (
                            <span className="text-xs text-[#9CA3AF]">{t('noFile')}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <PaginationBar page={recPage} setPage={setRecPage} totalPages={recPages} total={recTotal} label="Recordings" />
                </>
              )}
            </TabsContent>

            <TabsContent value="transcripts">
              {loading ? (
                <div className="text-center py-12 text-[#9CA3AF]">Loading...</div>
              ) : transcripts.length === 0 ? (
                <EmptyState icon={FileText} text={t('noTranscripts')} />
              ) : (
                <>
                  <div className="space-y-3">
                    {transcripts.map(tr => (
                      <div key={tr.transcript_id} className="bg-white border border-[#E2E4E0] rounded-xl p-5 hover:border-[#4A5D4E]/30 transition-colors"
                        data-testid={`transcript-${tr.transcript_id}`}>
                        <div className="flex items-center gap-4 mb-3">
                          <div className="w-10 h-10 rounded-lg bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                            <FileText className="w-5 h-5 text-[#4A5D4E]" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-medium text-[#1C1F1D] truncate">{tr.meeting_title || tr.meeting_id}</h3>
                            <span className="text-xs text-[#9CA3AF]">{formatDate(tr.created_at)}</span>
                          </div>
                        </div>
                        <p className="text-sm text-[#4B5563] bg-[#F3F4F1] rounded-lg p-3 line-clamp-3 leading-relaxed">{tr.content}</p>
                      </div>
                    ))}
                  </div>
                  <PaginationBar page={trPage} setPage={setTrPage} totalPages={trPages} total={trTotal} label="Transcripts" />
                </>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </main>

      {/* Video Player Dialog */}
      <Dialog open={!!playingRec} onOpenChange={() => setPlayingRec(null)}>
        <DialogContent className="sm:max-w-[720px] p-0 overflow-hidden">
          {playingRec && (
            <>
              <DialogHeader className="p-4 pb-0">
                <DialogTitle className="text-base font-medium">{playingRec.title}</DialogTitle>
              </DialogHeader>
              <div className="p-4">
                {playingRec.url && (
                  <video controls autoPlay className="w-full rounded-lg bg-black" data-testid="recording-player"
                    src={playingRec.url.startsWith('/api/') ? `${process.env.REACT_APP_BACKEND_URL}${playingRec.url}` : playingRec.url}>
                    Dein Browser unterstuetzt kein Video.
                  </video>
                )}
                <div className="flex items-center gap-3 text-xs text-[#9CA3AF] mt-3">
                  <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{formatDate(playingRec.created_at)}</span>
                  {playingRec.duration > 0 && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{playingRec.duration} min</span>}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!summaryDialog} onOpenChange={(o) => { if (!o) setSummaryDialog(null); }}>
        <DialogContent className="sm:max-w-[680px] max-h-[85vh] overflow-y-auto" data-testid="ai-summary-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-medium flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#D4A373]" />
              KI-Zusammenfassung: {summaryDialog?.title}
            </DialogTitle>
          </DialogHeader>
          <div className="pt-2 text-sm text-[#1C1F1D] whitespace-pre-wrap leading-relaxed" data-testid="ai-summary-content">
            {summaryDialog?.ai_summary || <span className="italic text-[#9CA3AF]">{t('noSummaryYet')}</span>}
          </div>
          <div className="pt-3 border-t border-[#E2E4E0] flex items-center justify-between text-[10px] text-[#9CA3AF]">
            <span>Generiert von GPT-5.2</span>
            <Button variant="outline" size="sm" onClick={() => summaryDialog && requestSummary(summaryDialog)}
              disabled={summarizing === summaryDialog?.recording_id}
              className="rounded-full text-xs h-7 border-[#E2E4E0]">
              <Sparkles className="w-3 h-3 mr-1" />Neu generieren
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EmptyState({ icon: Icon, text }) {
  return (
    <div className="text-center py-16 bg-white border border-[#E2E4E0] rounded-xl">
      <Icon className="w-12 h-12 text-[#E2E4E0] mx-auto mb-3" />
      <p className="text-[#9CA3AF] text-sm">{text}</p>
    </div>
  );
}
