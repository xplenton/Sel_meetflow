import { useState } from 'react';
import { Button } from '../ui/button';
import { Send, X } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { useLanguage } from '../../contexts/LanguageContext';
import { sanitizeRichHTML } from '../../lib/sanitize';

/**
 * NewsletterActions — inline action button + preview dialog for sending
 * a news post as an e-mail newsletter to the audience. Extracted from
 * NewsPage during the iter 217 refactor.
 */
export default function NewsletterActions({ post }) {
  const { t } = useLanguage();
  const [preview, setPreview] = useState(null);
  const [sending, setSending] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  const loadPreview = async () => {
    try {
      const { data } = await api.get(`/news/posts/${post.post_id}/newsletter-preview`);
      setPreview(data);
      setPreviewOpen(true);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Vorschau nicht verfügbar');
    }
  };

  const sendNow = async () => {
    setSending(true);
    try {
      const { data } = await api.post(`/news/posts/${post.post_id}/send-newsletter`, { force: true });
      if (data.reason === 'no_recipients') {
        toast.error('Keine E-Mail-Empfänger gefunden');
      } else if (data.queued) {
        toast.success(`Newsletter wird an ${data.recipients} Empfänger versendet (laeuft im Hintergrund)`);
      } else {
        toast.success(`Gesendet: ${data.sent}/${data.total}`);
      }
      setPreviewOpen(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    }
    setSending(false);
  };

  return (
    <>
      <button
        onClick={loadPreview}
        className="inline-flex items-center gap-1 text-[#4A5D4E] hover:underline"
        title={t('newsletterPreviewAndSend')}
        data-testid={`newsletter-actions-${post.post_id}`}
      >
        <Send className="w-3 h-3" /> E-Mail-Newsletter
      </button>
      {previewOpen && preview && (
        <div className="fixed inset-0 z-[80] bg-black/40 flex items-center justify-center p-3 overflow-y-auto" onClick={() => setPreviewOpen(false)}>
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()} data-testid="newsletter-preview-dialog">
            <header className="flex items-center justify-between px-4 py-3 border-b border-[#E2E4E0]">
              <div className="text-sm font-semibold text-[#1C1F1D]">Newsletter-Vorschau</div>
              <button onClick={() => setPreviewOpen(false)} className="p-1 hover:bg-[#F3F4F1] rounded"><X className="w-4 h-4" /></button>
            </header>
            <div className="p-3 border-b border-[#E2E4E0] bg-[#F9F9F8] text-xs flex flex-wrap items-center gap-3">
              <span><strong>{preview.audience_count}</strong> Empfänger</span>
              <span>Kanaele: {preview.channels.join(', ')}</span>
              {preview.email_dispatched_at && (
                <span className="text-[#9CA3AF]">Zuletzt: {new Date(preview.email_dispatched_at).toLocaleString('de-DE')}
                  {preview.email_dispatch_stats && ` (${preview.email_dispatch_stats.sent}/${preview.email_dispatch_stats.total})`}
                </span>
              )}
            </div>
            <div className="flex-1 overflow-y-auto bg-[#F3F4F1] p-3" dangerouslySetInnerHTML={{ __html: sanitizeRichHTML(preview.preview_html) }} />
            <footer className="flex justify-end gap-2 px-4 py-3 border-t border-[#E2E4E0]">
              <Button variant="outline" onClick={() => setPreviewOpen(false)} className="rounded-full border-[#E2E4E0]">Schließen</Button>
              <Button onClick={sendNow} disabled={sending || preview.audience_count === 0}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="send-newsletter-now">
                {sending ? '...' : `Jetzt senden (${preview.audience_count})`}
              </Button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
