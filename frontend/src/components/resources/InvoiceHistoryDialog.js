/**
 * Iter 327 — Audit-Verlauf einer Rechnung.
 *
 * Zeigt die Chronik aller Mutationen (Anlegen, Bearbeiten, Freigeben,
 * E-Mail-Versand, Stripe, Stornieren) inkl. Feld-Diffs.
 *
 * Backend: `GET /api/invoices/{id}/history` (Iter 327)
 */
import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Badge } from '../ui/badge';
import { History, Pencil, Plus, Check, Mail, CreditCard, XCircle, Loader2 } from 'lucide-react';
import api from '../../lib/api';

const ACTION_META = {
  created:     { label: 'Angelegt',     icon: Plus,       color: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  edited:      { label: 'Bearbeitet',   icon: Pencil,     color: 'bg-amber-50 text-amber-800 border-amber-200' },
  approved:    { label: 'Freigegeben',  icon: Check,      color: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  sent_email:  { label: 'E-Mail',       icon: Mail,       color: 'bg-blue-50 text-blue-800 border-blue-200' },
  sent_stripe: { label: 'Stripe',       icon: CreditCard, color: 'bg-blue-50 text-blue-800 border-blue-200' },
  voided:      { label: 'Storniert',    icon: XCircle,    color: 'bg-rose-50 text-rose-800 border-rose-200' },
};

function _fmtDt(s) {
  if (!s) return '';
  try { return new Date(s).toLocaleString('de-DE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }); } catch { return s.slice(0, 16); }
}

function _renderValue(v) {
  if (v === null || v === undefined || v === '') {
    return <span className="text-[#9CA3AF] italic">(leer)</span>;
  }
  return <span className="break-words">{String(v)}</span>;
}

export default function InvoiceHistoryDialog({ invoice, open, onClose }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!open || !invoice) return;
    setLoading(true);
    api.get(`/invoices/${invoice.invoice_id}/history`)
      .then(r => setEntries(r.data || []))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [open, invoice]);

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto" data-testid="invoice-history-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold text-[#1C1F1D] flex items-center gap-2">
            <History className="w-4 h-4 text-[#4A5D4E]" />
            Änderungsverlauf
            {invoice?.invoice_number && (
              <span className="text-[#6B7280] font-normal">· {invoice.invoice_number}</span>
            )}
          </DialogTitle>
          <p className="text-xs text-[#6B7280] mt-1">
            Chronologische Protokollierung aller Änderungen an dieser Rechnung — buchhaltungs-konform.
          </p>
        </DialogHeader>

        {loading ? (
          <div className="py-8 text-center text-xs text-[#9CA3AF]">
            <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> Lade Verlauf…
          </div>
        ) : entries.length === 0 ? (
          <div className="py-6 text-center text-xs text-[#9CA3AF]">
            Noch keine Änderungen erfasst.
          </div>
        ) : (
          <ol className="space-y-3 mt-2">
            {entries.map((e, idx) => {
              const meta = ACTION_META[e.action] || { label: e.action, icon: History, color: 'bg-slate-50 text-slate-800 border-slate-200' };
              const Icon = meta.icon;
              return (
                <li key={e.entry_id || idx}
                    className="border border-[#E2E4E0] rounded-lg p-3 bg-white"
                    data-testid={`history-entry-${e.entry_id || idx}`}>
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <Badge className={`text-[10px] border ${meta.color}`}>
                        <Icon className="w-3 h-3 mr-1" /> {meta.label}
                      </Badge>
                      <span className="text-xs text-[#1C1F1D] font-medium">
                        {e.user_name || e.user_email || 'System'}
                      </span>
                    </div>
                    <span className="text-[11px] text-[#9CA3AF]">{_fmtDt(e.ts)}</span>
                  </div>

                  {(e.diff && e.diff.length > 0) && (
                    <div className="mt-2 space-y-1.5">
                      {e.diff.map((d, i) => (
                        <div key={i} className="text-[11px] leading-relaxed"
                             data-testid={`history-diff-${e.entry_id}-${d.field}`}>
                          <span className="font-medium text-[#4A5D4E]">{d.label || d.field}:</span>{' '}
                          <span className="text-rose-700 line-through">{_renderValue(d.before)}</span>
                          {' '}<span className="text-[#9CA3AF]">→</span>{' '}
                          <span className="text-emerald-700 font-medium">{_renderValue(d.after)}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {(!e.diff || e.diff.length === 0) && e.extra && Object.keys(e.extra).length > 0 && (
                    <div className="mt-2 text-[11px] text-[#6B7280] space-x-2">
                      {Object.entries(e.extra).filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, v]) => (
                        <span key={k}><strong>{k}:</strong> {String(v)}</span>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </DialogContent>
    </Dialog>
  );
}
