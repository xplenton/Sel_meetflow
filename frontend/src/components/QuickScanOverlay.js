import { Stethoscope, X, Heart, CheckCircle, AlertTriangle, ExternalLink, Copy } from 'lucide-react';
import { Badge } from './ui/badge';
import { toast } from 'sonner';

/**
 * QuickScanOverlay — floating card anchored bottom-right of the meeting room.
 *
 * Two distinct modes:
 *   - "request": shown to the *target* user when the host pushes a diag.
 *     Props: request={ token, share_url, from_name, message, expires_at }
 *   - "results": shown to the host once a target submits. Props: results=[{from_name, results}]
 *
 * Both can coexist (e.g. a host might also be asked for diag by a co-host).
 */
export function QuickScanRequestCard({ request, onDismiss }) {
  if (!request) return null;

  const openDiag = () => {
    window.open(request.share_url, '_blank', 'noopener,noreferrer');
  };
  const copyLink = async () => {
    try { await navigator.clipboard.writeText(request.share_url); toast.success('Link kopiert'); }
    catch { toast.error('Kopieren fehlgeschlagen'); }
  };

  return (
    <div
      className="fixed bottom-24 right-4 z-50 w-[320px] max-w-[92vw] bg-white rounded-xl border border-[#D4A373] shadow-2xl p-4 animate-in slide-in-from-bottom-4"
      data-testid="quick-scan-request-card"
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-[#D4A373]/15 flex items-center justify-center flex-shrink-0">
          <Stethoscope className="w-5 h-5 text-[#D4A373]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-[#1C1F1D]">Diagnose-Anfrage</h4>
            <button onClick={onDismiss} className="p-1 rounded hover:bg-[#F3F4F1]" data-testid="quick-scan-request-dismiss">
              <X className="w-4 h-4 text-[#9CA3AF]" />
            </button>
          </div>
          <p className="text-xs text-[#6B7280] mt-0.5">
            <span className="font-medium text-[#1C1F1D]">{request.from_name}</span> bittet um eine Schnell-Diagnose deines Geräts.
          </p>
          <p className="text-[11px] text-[#9CA3AF] mt-1">{request.message || 'Cam · Mic · Netzwerk · ca. 10 Sekunden'}</p>

          <div className="mt-3 flex gap-2">
            <button
              onClick={openDiag}
              className="flex-1 flex items-center justify-center gap-1.5 bg-[#4A5D4E] hover:bg-[#3A4C3E] text-white text-xs font-medium rounded-lg py-2 transition"
              data-testid="quick-scan-start-button"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Jetzt starten
            </button>
            <button
              onClick={copyLink}
              className="px-3 py-2 bg-[#F3F4F1] hover:bg-[#E8EAE6] text-[#4A5D4E] text-xs font-medium rounded-lg transition"
              data-testid="quick-scan-copy-link"
              title="Link kopieren"
            >
              <Copy className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function resultBadge(state) {
  if (state === 'ok') return <Badge className="text-[10px] bg-[#6B8E23]/15 text-[#6B8E23]"><CheckCircle className="w-3 h-3 mr-1" />ok</Badge>;
  if (state === 'fail') return <Badge className="text-[10px] bg-[#C87967]/15 text-[#C87967]"><AlertTriangle className="w-3 h-3 mr-1" />fail</Badge>;
  return <Badge className="text-[10px] bg-[#D4A373]/15 text-[#D4A373]">{state || '—'}</Badge>;
}

export function QuickScanResultCard({ result, onDismiss }) {
  if (!result) return null;
  const keys = ['cam', 'mic', 'screen', 'webrtc', 'push', 'secureCtx'];
  const r = result.results || {};

  return (
    <div
      className="fixed bottom-24 right-4 z-50 w-[340px] max-w-[92vw] bg-white rounded-xl border border-[#4A5D4E] shadow-2xl p-4 animate-in slide-in-from-bottom-4"
      data-testid="quick-scan-result-card"
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-[#4A5D4E]/15 flex items-center justify-center flex-shrink-0">
          <Heart className="w-5 h-5 text-[#4A5D4E]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-[#1C1F1D]">Diagnose eingegangen</h4>
            <button onClick={onDismiss} className="p-1 rounded hover:bg-[#F3F4F1]" data-testid="quick-scan-result-dismiss">
              <X className="w-4 h-4 text-[#9CA3AF]" />
            </button>
          </div>
          <p className="text-xs text-[#6B7280] mt-0.5">von <span className="font-medium text-[#1C1F1D]">{result.from_name || 'Anonym'}</span></p>

          <div className="mt-3 grid grid-cols-2 gap-1.5">
            {keys.map(k => {
              const v = r[k];
              if (!v) return null;
              return (
                <div key={k} className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-[#F8F9F7]">
                  <span className="text-[11px] text-[#6B7280] capitalize">{k}</span>
                  {resultBadge(v.state)}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
