import { useEffect, useState } from 'react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Check, X, ChevronRight, Paperclip } from 'lucide-react';
import api from '../../lib/api';
import { describeResource } from '../../lib/bookingLabels';
import { toast } from 'sonner';
import AttachmentPicker from '../AttachmentPicker';
import CateringCancelDialog from './CateringCancelDialog';

/**
 * Operational catering inbox for catering staff (cap: catering.process).
 * Lists incoming catering requests + drives the §11 status workflow
 * (requested -> confirmed/rejected -> in_progress -> delivered -> completed).
 */
export default function CateringInbox() {
  const [items, setItems] = useState([]);
  const [reasons, setReasons] = useState([]);
  const [statusFilter, setStatusFilter] = useState('requested');
  const [rejectFor, setRejectFor] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectNote, setRejectNote] = useState('');
  const [attachFor, setAttachFor] = useState(null);   // request whose attachments dialog is open
  const [newAttachments, setNewAttachments] = useState([]);
  const [cancelFor, setCancelFor] = useState(null);   // catering request to cancel with fee preview
  // Iter 324 — guard against rapid clicks on confirm/reject/transition buttons.
  // Prevents double-fires that cause stale-state 409s on the second click.
  const [transitioningIds, setTransitioningIds] = useState(() => new Set());

  const load = async () => {
    try {
      const params = statusFilter && statusFilter !== 'all' ? `?status=${statusFilter}` : '';
      const { data } = await api.get(`/catering-requests${params}`);
      setItems(data || []);
    } catch { setItems([]); }
  };
  useEffect(() => { load(); }, [statusFilter]);

  useEffect(() => {
    api.get('/catering-requests/rejection-reasons')
      .then(r => setReasons(r.data?.reasons || []))
      .catch(() => {});
  }, []);

  const transition = async (cr, newStatus, extra = {}) => {
    if (transitioningIds.has(cr.request_id)) return;
    setTransitioningIds(prev => {
      const n = new Set(prev); n.add(cr.request_id); return n;
    });
    try {
      await api.post(`/catering-requests/${cr.request_id}/transition`, {
        status: newStatus, ...extra,
      });
      toast.success('Status aktualisiert');
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    } finally {
      setTransitioningIds(prev => {
        const n = new Set(prev); n.delete(cr.request_id); return n;
      });
    }
  };

  const submitReject = async () => {
    if (!rejectReason) { toast.error('Grund wählen'); return; }
    await transition(rejectFor, 'rejected', {
      reason: rejectReason + (rejectNote ? ` — ${rejectNote}` : ''),
    });
    setRejectFor(null);
    setRejectReason('');
    setRejectNote('');
  };

  const STATUS_LABELS = {
    requested: { label: 'Angefragt', cls: 'border-amber-300 bg-amber-50 text-amber-700' },
    confirmed: { label: 'Bestätigt', cls: 'border-emerald-300 bg-emerald-50 text-emerald-700' },
    rejected: { label: 'Abgelehnt', cls: 'border-rose-300 bg-rose-50 text-rose-700' },
    in_progress: { label: 'In Vorbereitung', cls: 'border-blue-300 bg-blue-50 text-blue-700' },
    delivered: { label: 'Geliefert', cls: 'border-violet-300 bg-violet-50 text-violet-700' },
    completed: { label: 'Abgeschlossen', cls: 'border-zinc-300 bg-zinc-50 text-zinc-700' },
  };

  const NEXT_ACTIONS = {
    requested: [{ label: 'Bestätigen', target: 'confirmed', icon: Check },
                { label: 'Ablehnen', target: 'rejected', icon: X, variant: 'destructive' }],
    confirmed: [{ label: 'In Vorbereitung', target: 'in_progress', icon: ChevronRight }],
    in_progress: [{ label: 'Geliefert', target: 'delivered', icon: ChevronRight }],
    delivered: [{ label: 'Abgeschlossen', target: 'completed', icon: Check }],
  };

  return (
    <div className="space-y-3" data-testid="catering-inbox">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-sm font-medium text-[#1C1F1D]">Catering-Anfragen</div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[200px]" data-testid="catering-status-filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Status</SelectItem>
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        {items.length === 0 && (
          <div className="text-sm text-[#9CA3AF] text-center py-12 border border-dashed border-[#E2E4E0] rounded-lg">
            Keine Anfragen.
          </div>
        )}
        {items.map(cr => {
          const sl = STATUS_LABELS[cr.status] || STATUS_LABELS.requested;
          const actions = NEXT_ACTIONS[cr.status] || [];
          return (
            <Card key={cr.request_id} className="p-3" data-testid={`catering-row-${cr.request_id}`}>
              {/* Iter 395 — Mobile-Fix: vorher waren Content + Action-Buttons in
                  einer einzigen flex-row, was auf Mobile dazu führte dass die
                  Content-Spalte (`min-w-0 flex-1`) auf ca. 50% Viewport schrumpfte
                  und „Raum: Seminarräume · Gebäude …" buchstabenweise umbrach.
                  Lösung: flex-col auf Mobile, ab `sm:` (640px) flex-row. */}
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                <div className="min-w-0 flex-1">
                  {/* Iter 395 — Titel + Status-Pill jetzt in einem flex-wrap-
                      Container, damit der Titel nicht hinter dem Status-Badge
                      verschwindet (vorher: inline `<Badge ml-2>` innerhalb von
                      `<div className="font-medium">` kollidierte mit dem Titel
                      auf schmalen Viewports). */}
                  <div className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-[#1C1F1D]">
                    <span className="break-words" data-testid={`catering-row-title-${cr.request_id}`}>
                      {cr.booking?.title || `Anfrage ${cr.request_id.slice(-6)}`}
                    </span>
                    <Badge variant="outline" className={`${sl.cls} text-[10px]`}>{sl.label}</Badge>
                    {cr.lead_time_breach && (
                      <Badge
                        variant="outline"
                        className="text-[10px] border-[#F0C75A] bg-[#FFF7E6] text-[#7A4D00] font-semibold"
                        data-testid={`catering-shortnotice-${cr.request_id}`}
                        title={`Vorlaufzeit unterschritten: ${cr.lead_time_worst_item ? cr.lead_time_worst_item + ' benötigt ' : ''}${cr.lead_time_required_min} Min., verfügbar ${cr.lead_time_available_min} Min.`}
                      >
                        ⚠ Kurzfristig
                      </Badge>
                    )}
                  </div>
                  {/* Iter 286 — Besprechung + Raum + Zeitraum.
                      Iter 343 — Wenn Sub-Raum, dann describeResource() für
                      Klartext "Großer Saal — Bereich A · Gebäude X · 2. Etage". */}
                  {cr.booking && (
                    <div className="text-xs text-[#4A5D4E] mt-1" data-testid={`catering-inbox-resource-${cr.request_id}`}>
                      {(() => {
                        // Use the central describeResource helper so the
                        // catering inbox stays in sync with everywhere else.
                        const label = describeResource(cr.booking);
                        return label ? <><strong>Raum:</strong> {label} · </> : null;
                      })()}
                      {cr.booking.start_at && cr.booking.end_at && (
                        <>{new Date(cr.booking.start_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })} – {new Date(cr.booking.end_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</>
                      )}
                    </div>
                  )}
                  {/* Iter 286 — Anforderer */}
                  {cr.requester && (
                    <div className="text-xs text-[#6B7280] mt-0.5">
                      <strong>Anforderer:</strong> {cr.requester.name || cr.requester.email}
                    </div>
                  )}
                  <div className="text-xs text-[#6B7280] mt-1">
                    {cr.delivery_at && <>Lieferung: {new Date(cr.delivery_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })} · </>}
                    {cr.delivery_target && <>Ziel: {cr.delivery_target} · </>}
                    {cr.contact && <>Kontakt: {cr.contact}</>}
                  </div>
                  <div className="text-xs text-[#6B7280]">
                    {cr.cost_center && <>KS: {cr.cost_center} · </>}
                    {cr.account && <>Konto: {cr.account}</>}
                  </div>
                  {/* Iter 286 — Items mit Namen */}
                  {cr.items?.length > 0 && (
                    <div className="text-xs text-[#1C1F1D] mt-1">
                      <strong>{cr.items.length} Position(en):</strong> {cr.items.slice(0, 5).map((i, ix) => (
                        <span key={ix}>
                          {ix > 0 && ', '}
                          {i.quantity}× {i.item_name || i.item_id}
                          {i.item_unit && i.item_unit !== 'Stk' && ` (${i.item_unit})`}
                        </span>
                      ))}
                      {cr.items.length > 5 && <> &hellip; +{cr.items.length - 5}</>}
                    </div>
                  )}
                  {cr.notes && <div className="text-xs italic text-[#6B7280] mt-1">„{cr.notes}“</div>}
                  {cr.rejection_reason && <div className="text-xs text-rose-700 mt-1">Grund: {cr.rejection_reason}</div>}
                  {/* Iter 286 — Anhänge klickbar */}
                  {cr.attachments?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5" data-testid={`catering-attachments-${cr.request_id}`}>
                      <span className="text-[10px] text-[#6B7280] inline-flex items-center gap-1">
                        <Paperclip className="w-3 h-3" /> Anhänge:
                      </span>
                      {cr.attachments.map(a => (
                        <a
                          key={a.attachment_id || a.id}
                          href={`${process.env.REACT_APP_BACKEND_URL}/api/attachments/${a.attachment_id || a.id}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[10px] inline-flex items-center gap-1 px-1.5 py-0.5 bg-[#F3F4F1] hover:bg-[#E2E4E0] rounded border border-[#E2E4E0] text-[#4A5D4E]"
                          data-testid={`catering-attachment-link-${a.attachment_id || a.id}`}
                        >
                          <Paperclip className="w-2.5 h-2.5" />
                          {a.filename || a.name || a.attachment_id}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex gap-1 flex-wrap sm:justify-end shrink-0">
                  {/* Iter 366 — Banner: Wenn Buchung freigabepflichtig ist und
                      noch nicht confirmed, kommt eine optische Sperre. */}
                  {cr.booking?.resource_requires_approval
                    && cr.booking?.status && cr.booking.status !== 'confirmed'
                    && ['requested'].includes(cr.status) && (
                      <div
                        className="w-full mb-1 text-[10px] text-amber-800 bg-amber-50 border border-amber-300 rounded px-2 py-1"
                        data-testid={`catering-blocked-${cr.request_id}`}
                      >
                        Buchung freigabepflichtig — Catering kann erst nach Buchungs-Freigabe bestätigt werden.
                      </div>
                    )}
                  {/* Iter 367 — Positiv-Banner: Buchung wurde freigegeben →
                      Catering kann jetzt bestätigt werden. Zeigen wir nur,
                      wenn die Anfrage noch in „requested" ist. */}
                  {cr.booking?.resource_requires_approval
                    && cr.booking?.status === 'confirmed'
                    && cr.booking_approved_at
                    && cr.status === 'requested' && (
                      <div
                        className="w-full mb-1 text-[10px] text-emerald-800 bg-emerald-50 border border-emerald-300 rounded px-2 py-1 flex items-center gap-1"
                        data-testid={`catering-ready-${cr.request_id}`}
                      >
                        <Check className="w-3 h-3 flex-shrink-0" />
                        Buchung freigegeben — Catering kann jetzt bestätigt werden.
                      </div>
                    )}
                  {/* Iter 366 — Gating: Wenn die Buchung freigabepflichtig ist
                      und der „Bestätigen"-Button geklickt würde, bevor die
                      Buchung selbst freigegeben ist, deaktivieren wir den
                      Button und zeigen einen Tooltip-Hinweis. */}
                  {(() => {
                    const bkPending = cr.booking?.resource_requires_approval
                      && cr.booking?.status && cr.booking.status !== 'confirmed';
                    return actions.map(a => {
                      const isConfirmAction = a.target === 'confirmed';
                      const blocked = isConfirmAction && bkPending;
                      return (
                        <Button
                          key={a.target}
                          size="sm"
                          variant={a.variant || 'outline'}
                          disabled={transitioningIds.has(cr.request_id) || blocked}
                          onClick={() => {
                            if (a.target === 'rejected') setRejectFor(cr);
                            else transition(cr, a.target);
                          }}
                          data-testid={`catering-${a.target}-${cr.request_id}`}
                          title={blocked
                            ? 'Buchung muss erst freigegeben werden, bevor das Catering bestätigt werden kann.'
                            : undefined}
                        >
                          {a.icon && <a.icon className="w-3 h-3 mr-1" />} {a.label}
                        </Button>
                      );
                    });
                  })()}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => { setAttachFor(cr); setNewAttachments([]); }}
                    data-testid={`catering-attach-${cr.request_id}`}
                    title="Anhang hinzufügen"
                  >
                    <Paperclip className="w-3 h-3" />
                  </Button>
                  {!['completed', 'cancelled', 'rejected'].includes(cr.status) && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                      onClick={() => setCancelFor(cr)}
                      data-testid={`catering-cancel-${cr.request_id}`}
                      title="Stornieren"
                    >
                      <X className="w-3 h-3 mr-1" /> Stornieren
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {rejectFor && (
        <Dialog open onOpenChange={(o) => !o && setRejectFor(null)}>
          <DialogContent className="max-w-md w-[calc(100vw-1.5rem)]" data-testid="catering-reject-dialog">
            <DialogHeader>
              <DialogTitle>Catering-Anfrage ablehnen</DialogTitle>
              <DialogDescription>Bitte einen Grund auswählen — wird dem Anfragenden angezeigt.</DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div>
                <Label>Grund</Label>
                <Select value={rejectReason} onValueChange={setRejectReason}>
                  <SelectTrigger data-testid="reject-reason-select"><SelectValue placeholder="— bitte wählen —" /></SelectTrigger>
                  <SelectContent>
                    {reasons.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Notiz (optional)</Label>
                <Textarea value={rejectNote} onChange={e => setRejectNote(e.target.value)}
                          placeholder="z. B. Alternativvorschlag" data-testid="reject-note-input" />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectFor(null)}>Abbrechen</Button>
              <Button variant="destructive" onClick={submitReject} data-testid="reject-submit-btn">
                Ablehnen
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {attachFor && (
        <Dialog open onOpenChange={(o) => !o && setAttachFor(null)}>
          <DialogContent className="max-w-md w-[calc(100vw-1.5rem)]" data-testid="catering-attach-dialog">
            <DialogHeader>
              <DialogTitle>Anhang hinzufügen</DialogTitle>
              <DialogDescription>
                Anfrage {attachFor.request_id.slice(-6)} —
                aktuell {attachFor.attachments?.length || 0} Anhang/Anhänge.
                Es gelten die zentralen Upload-Limits (Verwaltung &rarr; Reports).
              </DialogDescription>
            </DialogHeader>
            <AttachmentPicker
              attachments={newAttachments}
              onChange={setNewAttachments}
              max={5}
              testId="catering-attach-picker"
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setAttachFor(null)}>Abbrechen</Button>
              <Button
                onClick={async () => {
                  if (!newAttachments.length) {
                    toast.error('Bitte zuerst eine Datei hochladen');
                    return;
                  }
                  let okCount = 0;
                  for (const a of newAttachments) {
                    try {
                      await api.post(`/catering-requests/${attachFor.request_id}/attachments/${a.attachment_id}`);
                      okCount += 1;
                    } catch (e) {
                      const d = e.response?.data?.detail;
                      toast.error(`Anhang abgelehnt: ${typeof d === 'string' ? d : e.message}`);
                    }
                  }
                  if (okCount) toast.success(`${okCount} Anhang/Anhänge ergänzt`);
                  setAttachFor(null);
                  setNewAttachments([]);
                  load();
                }}
                data-testid="catering-attach-submit"
              >
                Hinzufügen
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {cancelFor && (
        <CateringCancelDialog
          request={cancelFor}
          onClose={(refresh) => {
            setCancelFor(null);
            if (refresh) load();
          }}
        />
      )}
    </div>
  );
}
