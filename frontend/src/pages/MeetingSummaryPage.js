import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { ArrowLeft, Sparkles, Send, Users, Calendar, Clock, CheckCircle, Loader2, FileText } from 'lucide-react';
import api from '../lib/api';
import { sanitizeRichHTML } from '../lib/sanitize';
import { toast } from 'sonner';

export default function MeetingSummaryPage() {
  const { meetingId } = useParams();

  const formatMarkdown = (text) => {
    // Iter 270 — escape HTML entities first to prevent XSS, then apply markdown.
    // Uses sanitizeRichHTML so the literal style="…" attrs survive.
    const safe = String(text || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return sanitizeRichHTML(safe
      .replace(/## (.*)/g, '<h3 style="font-size:15px;font-weight:600;color:#1C1F1D;margin:16px 0 8px 0;">$1</h3>')
      .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#1C1F1D;">$1</strong>')
      .replace(/^- (.*)/gm, '<li style="margin:4px 0;padding-left:4px;">$1</li>')
      .replace(/(<li.*<\/li>\n?)+/g, (m) => `<ul style="list-style:disc;padding-left:20px;margin:8px 0;">${m}</ul>`)
      .replace(/\n{2,}/g, '<br/><br/>')
      .replace(/\n/g, '<br/>'));
  };
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);

  const fetchSummary = useCallback(async () => {
    try {
      const { data: res } = await api.get(`/meetings/${meetingId}/summary`);
      setData(res);
    } catch {
      toast.error('Fehler beim Laden der Zusammenfassung');
    } finally { setLoading(false); }
  }, [meetingId]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const { data: res } = await api.post(`/meetings/${meetingId}/ai/summarize`);
      toast.success('KI-Zusammenfassung generiert');
      fetchSummary();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Zusammenfassung konnte nicht generiert werden');
    } finally { setGenerating(false); }
  };

  const handleSendEmail = async () => {
    setSending(true);
    try {
      const { data: res } = await api.post(`/meetings/${meetingId}/send-summary-email`);
      toast.success(`Zusammenfassung an ${res.sent_to} Teilnehmer gesendet`);
      fetchSummary();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'E-Mail-Versand fehlgeschlagen');
    } finally { setSending(false); }
  };

  const meeting = data?.meeting;
  const summary = data?.summary;
  const participants = data?.participants || [];
  const emailSent = data?.email_sent;

  const formatDate = (iso) => {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleString('de-DE', { dateStyle: 'long', timeStyle: 'short' });
    } catch { return iso; }
  };

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="summary-page">
        <div className="max-w-3xl mx-auto">
          <button onClick={() => navigate('/dashboard')} className="flex items-center gap-1.5 text-sm text-[#4B5563] hover:text-[#1C1F1D] mb-6" data-testid="back-to-dashboard">
            <ArrowLeft className="w-4 h-4" /> Dashboard
          </button>

          {loading ? (
            <div className="text-center py-16 text-[#9CA3AF]">Loading...</div>
          ) : !meeting ? (
            <div className="text-center py-16 text-[#9CA3AF]">{t('meetingNotFound')}</div>
          ) : (
            <div className="space-y-6">
              {/* Meeting Header */}
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <h1 className="text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }} data-testid="summary-meeting-title">
                      {meeting.title}
                    </h1>
                    <div className="flex items-center gap-4 mt-2 text-sm text-[#6B7280]">
                      {(meeting.scheduled_at || meeting.created_at) && (
                        <span className="flex items-center gap-1.5"><Calendar className="w-4 h-4" />{formatDate(meeting.scheduled_at || meeting.created_at)}</span>
                      )}
                      <span className="flex items-center gap-1.5"><Clock className="w-4 h-4" />{meeting.duration || 60} Min.</span>
                      <span className="flex items-center gap-1.5"><Users className="w-4 h-4" />{participants.length} Teilnehmer</span>
                    </div>
                  </div>
                  {emailSent && (
                    <div className="flex items-center gap-1.5 text-xs text-[#6B8E23] bg-[#6B8E23]/10 px-3 py-1.5 rounded-full" data-testid="email-sent-badge">
                      <CheckCircle className="w-3.5 h-3.5" /> E-Mail gesendet
                    </div>
                  )}
                </div>

                {/* Participants */}
                {participants.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-[#E2E4E0]">
                    <p className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-2">Teilnehmer</p>
                    <div className="flex flex-wrap gap-2">
                      {participants.map(p => (
                        <span key={p.user_id} className="text-xs bg-[#F3F4F1] text-[#4B5563] px-2.5 py-1 rounded-full" data-testid={`participant-${p.user_id}`}>
                          {p.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Summary Content */}
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-base font-medium text-[#1C1F1D] flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-[#4A5D4E]" /> KI-Zusammenfassung
                  </h2>
                  <div className="flex gap-2">
                    {!summary && (
                      <Button size="sm" onClick={handleGenerate} disabled={generating} data-testid="generate-summary-button"
                        className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs px-4">
                        {generating ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />{t('generating')}</> : <><Sparkles className="w-3.5 h-3.5 mr-1.5" />{t('generateAiSummary')}</>}
                      </Button>
                    )}
                    {summary && (
                      <>
                        <Button size="sm" variant="outline" onClick={handleGenerate} disabled={generating} data-testid="regenerate-summary-button"
                          className="rounded-full text-xs px-4 border-[#E2E4E0]">
                          {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Neu generieren'}
                        </Button>
                        <Button size="sm" onClick={handleSendEmail} disabled={sending} data-testid="send-summary-email-button"
                          className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs px-4">
                          {sending ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />Sende...</> : <><Send className="w-3.5 h-3.5 mr-1.5" />Per E-Mail senden</>}
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {summary ? (
                  <div className="prose prose-sm max-w-none" data-testid="summary-content">
                    <div className="bg-[#F3F4F1] rounded-xl p-5 text-sm text-[#4B5563] leading-relaxed" style={{ borderLeft: '3px solid #4A5D4E' }}
                      dangerouslySetInnerHTML={{ __html: formatMarkdown(summary) }} />
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <FileText className="w-12 h-12 text-[#E2E4E0] mx-auto mb-3" />
                    <p className="text-sm text-[#9CA3AF]">{t('noSummaryYet')}</p>
                    <p className="text-xs text-[#9CA3AF] mt-1">Klicke auf "Zusammenfassung generieren" um eine KI-Zusammenfassung zu erstellen</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
