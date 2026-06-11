import { useEffect, useState, useCallback } from 'react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../ui/dialog';
import { FileText, Mail, CreditCard, Check, XCircle, ExternalLink, Loader2, RefreshCcw, Receipt, Pencil, History } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { openAuthedFile } from '../../lib/authedDownload';
import ManualInvoiceDialog from './ManualInvoiceDialog';
import InvoiceHistoryDialog from './InvoiceHistoryDialog';

function _fmtMoney(n, currency = 'EUR') {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency }).format(n || 0);
}
function _fmtDt(s) {
  if (!s) return '';
  try { return new Date(s).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return s.slice(0, 16); }
}

const STATUS_LABELS = {
  draft: { label: 'Entwurf', color: 'bg-slate-100 text-slate-700 border-slate-300' },
  approved: { label: 'Freigegeben', color: 'bg-amber-100 text-amber-800 border-amber-300' },
  sent: { label: 'Versendet', color: 'bg-blue-100 text-blue-800 border-blue-300' },
  paid: { label: 'Bezahlt', color: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  void: { label: 'Storniert', color: 'bg-rose-100 text-rose-700 border-rose-300 line-through' },
};

/**
 * Iter 285 — Erstellte Rechnungen Tracking-UI
 *
 * Shows all persisted invoice snapshots with status, lets the user
 * approve, send via email or Stripe, void, or download the PDF.
 * `refreshKey` prop allows the parent BillingPanel to bump the list
 * after creating a new snapshot.
 */
export default function InvoicesTrackingPanel({ refreshKey = 0 }) {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  // Iter 326 — Bearbeiten von Draft-Rechnungen
  const [editInv, setEditInv] = useState(null);
  // Iter 327 — Audit-Verlauf
  const [historyInv, setHistoryInv] = useState(null);

  // Dialog state
  const [sendDialog, setSendDialog] = useState(null);  // { invoice, mode: 'email'|'stripe' }
  const [sending, setSending] = useState(false);
  const [emailOverride, setEmailOverride] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [extraMessage, setExtraMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      const { data } = await api.get('/invoices', { params });
      setList(data || []);
    } catch {
      setList([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const approve = async (inv) => {
    try {
      await api.post(`/invoices/${inv.invoice_id}/approve`);
      toast.success('Freigegeben');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    }
  };

  // Iter 328 — Storno mit Pflicht-Grund via Dialog (statt window.confirm).
  const [voidDialog, setVoidDialog] = useState(null);   // { invoice }
  const [voidReason, setVoidReason] = useState('');
  const [voidSaving, setVoidSaving] = useState(false);

  const openVoid = (inv) => {
    setVoidReason('');
    setVoidDialog({ invoice: inv });
  };
  const submitVoid = async () => {
    const reason = voidReason.trim();
    if (!reason) {
      toast.error('Bitte einen Stornogrund eingeben.');
      return;
    }
    setVoidSaving(true);
    try {
      await api.post(`/invoices/${voidDialog.invoice.invoice_id}/void`, { reason });
      toast.success('Storniert');
      setVoidDialog(null);
      setVoidReason('');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    } finally {
      setVoidSaving(false);
    }
  };

  const openSendDialog = (inv, mode) => {
    setSendDialog({ invoice: inv, mode });
    setEmailOverride(inv.external_customer_email || '');
    setCustomerName(inv.external_customer_name || '');
    setExtraMessage('');
  };

  const closeSendDialog = () => { setSendDialog(null); setSending(false); };

  const doSend = async () => {
    if (!sendDialog) return;
    const inv = sendDialog.invoice;
    setSending(true);
    try {
      if (sendDialog.mode === 'email') {
        const body = {};
        if (emailOverride.trim()) body.to_email = emailOverride.trim();
        if (extraMessage.trim()) body.message = extraMessage.trim();
        await api.post(`/invoices/${inv.invoice_id}/send-email`, body);
        toast.success('Rechnung per E-Mail versendet');
      } else {
        if (!emailOverride.trim()) {
          toast.error('Kunden-E-Mail erforderlich');
          setSending(false);
          return;
        }
        const { data } = await api.post(`/invoices/${inv.invoice_id}/send-stripe`, {
          external_customer_email: emailOverride.trim(),
          external_customer_name: customerName.trim() || undefined,
        });
        toast.success('An Stripe übergeben');
        if (data?.hosted_invoice_url) {
          window.open(data.hosted_invoice_url, '_blank');
        }
      }
      closeSendDialog();
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Versand fehlgeschlagen');
    } finally {
      setSending(false);
    }
  };

  const openPdf = (inv) => {
    // Iter 326 — JWT-fähiger Blob-Loader; ohne Auth gibt der neue Tab 401
    // zurück und zeigt eine leere Seite. Außerdem leitet das Backend nun
    // Manual-Rechnungen automatisch auf den Manual-PDF-Renderer um.
    openAuthedFile(`/invoices/${inv.invoice_id}/pdf`);
  };

  const openEdit = async (inv) => {
    try {
      const { data } = await api.get(`/invoices/${inv.invoice_id}`);
      setEditInv(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Rechnung nicht ladbar');
    }
  };

  return (
    <Card className="p-4" data-testid="invoices-tracking-panel">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Receipt className="w-4 h-4 text-[#4A5D4E]" />
        <div className="text-sm font-medium">Erstellte Rechnungen</div>
        <Badge variant="outline" className="text-[10px]">{list.length}</Badge>
        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9CA3AF]" />}
        <div className="ml-auto flex items-center gap-2">
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                  className="h-8 border border-[#E2E4E0] rounded px-2 text-xs"
                  data-testid="invoices-status-filter">
            <option value="">Alle Status</option>
            <option value="draft">Entwurf</option>
            <option value="approved">Freigegeben</option>
            <option value="sent">Versendet</option>
            <option value="paid">Bezahlt</option>
            <option value="void">Storniert</option>
          </select>
          <Button size="sm" variant="outline" onClick={load} data-testid="invoices-refresh">
            <RefreshCcw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {list.length === 0 ? (
        <div className="text-center text-xs text-[#9CA3AF] py-6">
          Noch keine Rechnungen erstellt. Klicke oben auf <b>"Als Rechnung speichern"</b>, um die erste anzulegen.
        </div>
      ) : (
        <>
        {/* Iter 360 — Mobile-First: <md Card-Stack, ≥md klassische Tabelle */}
        <div className="md:hidden space-y-2" data-testid="invoices-cards">
          {list.map(inv => {
            const sl = STATUS_LABELS[inv.status] || STATUS_LABELS.draft;
            return (
              <div key={inv.invoice_id}
                   className="border border-[#E2E4E0] rounded-lg p-3 bg-white"
                   data-testid={`invoice-card-${inv.invoice_id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] text-[#9CA3AF]">{_fmtDt(inv.created_at)}</div>
                    <div className="font-medium text-[#1C1F1D] text-sm truncate">{inv.title}</div>
                    <div className="text-[10px] font-mono text-[#4A5D4E]"
                         data-testid={`invoice-number-mobile-${inv.invoice_id}`}>
                      {inv.invoice_number || inv.invoice_id}
                    </div>
                  </div>
                  <div className="text-right whitespace-nowrap">
                    <div className="text-sm font-semibold">
                      {_fmtMoney(inv.snapshot?.total_gross ?? inv.snapshot?.total, inv.snapshot?.currency)}
                    </div>
                    <Badge className={`text-[10px] border mt-1 ${sl.color}`}>{sl.label}</Badge>
                  </div>
                </div>
                {inv.cost_center && (
                  <div className="mt-2">
                    <Badge variant="outline" className="text-[10px]">{inv.cost_center}</Badge>
                  </div>
                )}
                {inv.stripe_invoice_id && (
                  <div className="text-[10px] text-blue-600 mt-1 flex items-center gap-1">
                    <CreditCard className="w-3 h-3" /> {inv.stripe_invoice_id}
                    {inv.stripe_hosted_url && (
                      <a href={inv.stripe_hosted_url} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center hover:underline">
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                )}
                {inv.status === 'void' && (
                  <div className="text-[10px] text-rose-700 mt-2"
                       data-testid={`void-info-mobile-${inv.invoice_id}`}>
                    {inv.voided_by_name && <div className="font-medium">Storniert von: {inv.voided_by_name}</div>}
                    {inv.voided_at && <div>{_fmtDt(inv.voided_at)}</div>}
                    {inv.void_reason && <div className="italic break-words">„{inv.void_reason}"</div>}
                  </div>
                )}
                <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-[#F3F4F1]">
                  <Button size="sm" variant="outline" onClick={() => openPdf(inv)}
                          data-testid={`invoice-pdf-mobile-${inv.invoice_id}`} className="h-9">
                    <FileText className="w-3.5 h-3.5 mr-1" /> PDF
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setHistoryInv(inv)}
                          data-testid={`invoice-history-mobile-${inv.invoice_id}`} className="h-9">
                    <History className="w-3.5 h-3.5 mr-1" /> Verlauf
                  </Button>
                  {inv.status === 'draft' && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => openEdit(inv)}
                              data-testid={`invoice-edit-mobile-${inv.invoice_id}`} className="h-9">
                        <Pencil className="w-3.5 h-3.5 mr-1" /> Bearbeiten
                      </Button>
                      <Button size="sm" onClick={() => approve(inv)}
                              data-testid={`invoice-approve-mobile-${inv.invoice_id}`}
                              className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white">
                        <Check className="w-3.5 h-3.5 mr-1" /> Freigeben
                      </Button>
                    </>
                  )}
                  {(inv.status === 'approved' || inv.status === 'sent') && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => openSendDialog(inv, 'email')}
                              data-testid={`invoice-send-email-mobile-${inv.invoice_id}`} className="h-9">
                        <Mail className="w-3.5 h-3.5 mr-1" /> E-Mail
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => openSendDialog(inv, 'stripe')}
                              data-testid={`invoice-send-stripe-mobile-${inv.invoice_id}`}
                              className="h-9 text-blue-700 border-blue-300">
                        <CreditCard className="w-3.5 h-3.5 mr-1" /> Stripe
                      </Button>
                    </>
                  )}
                  {inv.status !== 'paid' && inv.status !== 'void' && (
                    <Button size="sm" variant="outline" onClick={() => openVoid(inv)}
                            data-testid={`invoice-void-mobile-${inv.invoice_id}`}
                            className="h-9 text-rose-700 border-rose-300 ml-auto">
                      <XCircle className="w-3.5 h-3.5 mr-1" /> Storno
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-sm" data-testid="invoices-table">
            <thead className="text-left text-xs text-[#6B7280] border-b border-[#E2E4E0]">
              <tr>
                <th className="py-2 px-2">Datum</th>
                <th className="py-2 px-2">Rechnung</th>
                <th className="py-2 px-2">Kostenstelle</th>
                <th className="py-2 px-2">Status</th>
                <th className="py-2 px-2 text-right">Betrag</th>
                <th className="py-2 px-2 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {list.map(inv => {
                const sl = STATUS_LABELS[inv.status] || STATUS_LABELS.draft;
                return (
                  <tr key={inv.invoice_id} className="border-b border-[#F3F4F1] align-top"
                      data-testid={`invoice-row-${inv.invoice_id}`}>
                    <td className="py-2 px-2 text-[#6B7280] whitespace-nowrap">{_fmtDt(inv.created_at)}</td>
                    <td className="py-2 px-2">
                      <div className="font-medium text-[#1C1F1D]">{inv.title}</div>
                      {/* Iter 339 — Zeige die konfigurierte Rechnungsnummer
                          (Prefix/Format aus Einstellungen) statt der internen
                          `invoice_id`. Falls noch keine vergeben wurde (sehr alte
                          Datensätze), fallen wir auf die ID zurück. */}
                      <div className="text-[11px] font-mono text-[#4A5D4E]" data-testid={`invoice-number-${inv.invoice_id}`}>
                        {inv.invoice_number || inv.invoice_id}
                      </div>
                      {inv.stripe_invoice_id && (
                        <div className="text-[10px] text-blue-600 mt-0.5 flex items-center gap-1">
                          <CreditCard className="w-3 h-3" /> {inv.stripe_invoice_id}
                          {inv.stripe_hosted_url && (
                            <a href={inv.stripe_hosted_url} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center hover:underline">
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-2">
                      {inv.cost_center && <Badge variant="outline" className="text-[10px]">{inv.cost_center}</Badge>}
                    </td>
                    <td className="py-2 px-2">
                      <Badge className={`text-[10px] border ${sl.color}`}>{sl.label}</Badge>
                      {/* Iter 328 — Storno-Info sichtbar (wer/wann/warum) */}
                      {inv.status === 'void' && (
                        <div className="text-[10px] text-rose-700 mt-1 max-w-[220px]"
                             data-testid={`void-info-${inv.invoice_id}`}>
                          {inv.voided_by_name && (
                            <div className="font-medium">Von: {inv.voided_by_name}</div>
                          )}
                          {inv.voided_at && (
                            <div>{_fmtDt(inv.voided_at)}</div>
                          )}
                          {inv.void_reason && (
                            <div className="italic break-words mt-0.5">„{inv.void_reason}"</div>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-2 text-right font-medium whitespace-nowrap">
                      {/* Iter 326 — Manual-Rechnungen speichern total_gross; Aggregate speichern total */}
                      {_fmtMoney(inv.snapshot?.total_gross ?? inv.snapshot?.total, inv.snapshot?.currency)}
                    </td>
                    <td className="py-2 px-2 text-right whitespace-nowrap">
                      <div className="inline-flex flex-wrap gap-1 justify-end">
                        <Button size="sm" variant="ghost" onClick={() => openPdf(inv)}
                                data-testid={`invoice-pdf-${inv.invoice_id}`}>
                          <FileText className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setHistoryInv(inv)}
                                data-testid={`invoice-history-${inv.invoice_id}`}
                                title="Änderungsverlauf">
                          <History className="w-3.5 h-3.5" />
                        </Button>
                        {inv.status === 'draft' && (
                          <>
                            <Button size="sm" variant="ghost" onClick={() => openEdit(inv)}
                                    data-testid={`invoice-edit-${inv.invoice_id}`}
                                    title="Bearbeiten">
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => approve(inv)}
                                    data-testid={`invoice-approve-${inv.invoice_id}`}
                                    className="text-emerald-700">
                              <Check className="w-3.5 h-3.5 mr-1" /> Freigeben
                            </Button>
                          </>
                        )}
                        {(inv.status === 'approved' || inv.status === 'sent') && (
                          <>
                            <Button size="sm" variant="ghost" onClick={() => openSendDialog(inv, 'email')}
                                    data-testid={`invoice-send-email-${inv.invoice_id}`}>
                              <Mail className="w-3.5 h-3.5 mr-1" /> E-Mail
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => openSendDialog(inv, 'stripe')}
                                    data-testid={`invoice-send-stripe-${inv.invoice_id}`}
                                    className="text-blue-700">
                              <CreditCard className="w-3.5 h-3.5 mr-1" /> Stripe
                            </Button>
                          </>
                        )}
                        {inv.status !== 'paid' && inv.status !== 'void' && (
                          <Button size="sm" variant="ghost" onClick={() => openVoid(inv)}
                                  data-testid={`invoice-void-${inv.invoice_id}`}
                                  className="text-rose-700">
                            <XCircle className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        </>
      )}

      {/* Send dialog */}
      <Dialog open={!!sendDialog} onOpenChange={(o) => !o && closeSendDialog()}>
        <DialogContent className="max-w-md" data-testid="invoice-send-dialog">
          <DialogHeader>
            <DialogTitle>
              {sendDialog?.mode === 'stripe' ? 'Rechnung via Stripe versenden' : 'Rechnung per E-Mail versenden'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-xs">
                {sendDialog?.mode === 'stripe' ? 'Kunden-E-Mail (Pflicht)' : 'Empfänger-E-Mail (optional, überschreibt Kostenstellen-E-Mail)'}
              </Label>
              <Input
                type="email"
                value={emailOverride}
                onChange={e => setEmailOverride(e.target.value)}
                placeholder={sendDialog?.mode === 'stripe' ? 'kunde@firma.de' : 'buchhaltung@firma.de'}
                data-testid="invoice-send-email-input"
              />
            </div>
            {sendDialog?.mode === 'stripe' && (
              <div>
                <Label className="text-xs">Kundenname (optional)</Label>
                <Input
                  value={customerName}
                  onChange={e => setCustomerName(e.target.value)}
                  placeholder="Firma Mustermann GmbH"
                  data-testid="invoice-send-customer-name"
                />
              </div>
            )}
            {sendDialog?.mode === 'email' && (
              <div>
                <Label className="text-xs">Zusatztext (optional)</Label>
                <textarea
                  value={extraMessage}
                  onChange={e => setExtraMessage(e.target.value)}
                  rows={3}
                  className="w-full border border-[#E2E4E0] rounded p-2 text-sm"
                  placeholder="z. B. Bitte bis 30. März begleichen."
                  data-testid="invoice-send-message"
                />
              </div>
            )}
            <div className="text-[11px] text-[#9CA3AF]">
              {sendDialog?.mode === 'stripe'
                ? 'Stripe erstellt die Rechnung, finalisiert sie und versendet sie per E-Mail an den Kunden. Status aktualisiert sich beim Bezahlen automatisch.'
                : 'PDF wird als Anhang versendet (sofern SMTP konfiguriert). Bei Resend/SendGrid ohne Anhang-Support enthält die E-Mail einen Download-Hinweis.'}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeSendDialog} data-testid="invoice-send-cancel">Abbrechen</Button>
            <Button onClick={doSend} disabled={sending} data-testid="invoice-send-confirm"
                    className={sendDialog?.mode === 'stripe' ? 'bg-blue-600 hover:bg-blue-700' : 'bg-[#4A5D4E] hover:bg-[#3E4E42]'}>
              {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
              {sendDialog?.mode === 'stripe' ? 'An Stripe übergeben' : 'Versenden'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Iter 326 — Bearbeiten-Dialog (Entwurf) */}
      {editInv && (
        <ManualInvoiceDialog
          open={!!editInv}
          editInvoice={editInv}
          onClose={() => setEditInv(null)}
          onCreated={() => { setEditInv(null); load(); }}
        />
      )}

      {/* Iter 328 — Audit-Verlauf */}
      {historyInv && (
        <InvoiceHistoryDialog
          invoice={historyInv}
          open={!!historyInv}
          onClose={() => setHistoryInv(null)}
        />
      )}

      {/* Iter 328 — Storno-Dialog mit Pflicht-Grund */}
      <Dialog open={!!voidDialog} onOpenChange={(o) => !o && setVoidDialog(null)}>
        <DialogContent className="max-w-md" data-testid="invoice-void-dialog">
          <DialogHeader>
            <DialogTitle className="text-base text-rose-700 flex items-center gap-2">
              <XCircle className="w-4 h-4" /> Rechnung stornieren
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="text-xs text-[#6B7280]">
              {voidDialog?.invoice?.title} ({voidDialog?.invoice?.invoice_number || voidDialog?.invoice?.invoice_id})
            </div>
            <div>
              <Label className="text-xs" htmlFor="void-reason">
                Stornogrund <span className="text-rose-600">*</span>
              </Label>
              <textarea
                id="void-reason"
                rows={3}
                value={voidReason}
                onChange={(e) => setVoidReason(e.target.value)}
                placeholder="z. B. Falsche Empfänger-Anschrift, Rechnung wird neu erstellt …"
                className="w-full mt-1 px-2 py-1.5 text-sm border border-[#E2E4E0] rounded resize-none focus:outline-none focus:ring-2 focus:ring-rose-200"
                data-testid="void-reason-input"
                autoFocus
              />
            </div>
            <div className="text-[11px] text-[#9CA3AF]">
              Der Grund wird mit Name und Zeitstempel im Audit-Verlauf gespeichert und ist auch in der Tabelle sichtbar.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setVoidDialog(null)}
                    data-testid="invoice-void-cancel">Abbrechen</Button>
            <Button onClick={submitVoid} disabled={voidSaving || !voidReason.trim()}
                    data-testid="invoice-void-confirm"
                    className="bg-rose-600 hover:bg-rose-700 text-white">
              {voidSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <XCircle className="w-3.5 h-3.5 mr-1" />}
              Stornieren
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
