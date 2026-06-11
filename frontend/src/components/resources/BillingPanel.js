import { useEffect, useState, useCallback } from 'react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Receipt, FileDown, Loader2, RefreshCcw, FileText, FileSpreadsheet, Save, Plus } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { openAuthedFile } from '../../lib/authedDownload';
import InvoicesTrackingPanel from './InvoicesTrackingPanel';
import ManualInvoiceDialog from './ManualInvoiceDialog';
import SaveInvoiceWithTemplateDialog from './SaveInvoiceWithTemplateDialog';
import BillingBookingsTable from './BillingBookingsTable';

/**
 * Iter 284 — Rechnungen-Panel im Ressourcen-Bereich.
 *
 * User-facing Billing-UI. Bislang waren alle Endpoints vorhanden, aber
 * nur tief im Admin-Panel versteckt. Dieses Panel zeigt:
 *  - Filter (Zeitraum + Kostenstelle)
 *  - Live-Aggregat: Catering + Fahrtkilometer pro Kostenstelle
 *  - Buchungen-Liste mit abrechenbarem Betrag + Direkt-PDF
 *  - Export-Buttons: Sammelrechnung PDF, DATEV-CSV, ERP-CSV
 *
 * Sichtbar für User mit Capability `bookings.invoice`.
 */
function _fmtMoney(n, currency = 'EUR') {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency }).format(n);
}
function _fmtDt(s) {
  if (!s) return '';
  try { return new Date(s).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  catch { return s.slice(0, 10); }
}

export default function BillingPanel() {
  const [costCenters, setCostCenters] = useState([]);
  const [costCenter, setCostCenter] = useState('');
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
  const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().slice(0, 10);
  const [fromDate, setFromDate] = useState(monthStart);
  const [toDate, setToDate] = useState(monthEnd);
  const [aggregate, setAggregate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  // Iter 322 — save dialog (template picker) state
  const [saveDialog, setSaveDialog] = useState({ open: false, kind: 'aggregate' });

  useEffect(() => {
    api.get('/cost-centers').then(r => setCostCenters(r.data || [])).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (costCenter) params.cost_center = costCenter;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const { data } = await api.get('/resource-bookings/invoices/aggregate', { params });
      setAggregate(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Aggregat konnte nicht geladen werden');
    } finally {
      setLoading(false);
    }
  }, [costCenter, fromDate, toDate]);

  useEffect(() => { load(); }, [load]);

  const buildQueryParams = () => {
    const p = {};
    if (costCenter) p.cost_center = costCenter;
    if (fromDate) p.from_date = fromDate;
    if (toDate) p.to_date = toDate;
    return p;
  };

  // Iter 322 — All PDF/CSV opens now go through the authenticated blob
  // helper. Previously `window.open(url)` made the request without the JWT
  // and got a 401, so the new tab stayed blank.
  const openSammelrechnungPdf = () =>
    openAuthedFile('/resource-bookings/invoices/aggregate.pdf', buildQueryParams());
  const openCateringAggregatePdf = () =>
    openAuthedFile('/catering-requests/invoices/aggregate.pdf', buildQueryParams());
  const openDatevCsv = () => {
    const days = Math.max(1, Math.round((new Date(toDate) - new Date(fromDate)) / 86400000) + 1);
    return openAuthedFile('/resource-bookings/export/erp.csv', { format: 'datev', days });
  };
  const openGenericCsv = () => {
    const days = Math.max(1, Math.round((new Date(toDate) - new Date(fromDate)) / 86400000) + 1);
    return openAuthedFile('/resource-bookings/export/erp.csv', { format: 'generic', days });
  };
  const openBookingInvoice = (bookingId) =>
    openAuthedFile(`/resource-bookings/${bookingId}/invoice.pdf`);

  // Iter 322 — Save flows now open a dialog for template selection
  // (previously they POSTed directly without giving the user a chance to
  // pick a template / set a custom title).
  const openSaveSnapshot = () => setSaveDialog({ open: true, kind: 'aggregate' });
  const openSaveCateringSnapshot = () => setSaveDialog({ open: true, kind: 'catering_aggregate' });
  // Iter 330 — Save flows from the unified bookings-table.
  const openSaveSingle = (bookingId) => {
    setSaveDialog({ open: true, kind: 'single', bookingId });
  };
  const openSaveSelection = (bookingIds) => {
    if (!bookingIds || bookingIds.length === 0) {
      toast.error('Bitte mindestens eine Buchung auswählen');
      return;
    }
    setSaveDialog({ open: true, kind: 'aggregate', bookingIds });
  };
  // Iter 285 — bump to refresh InvoicesTrackingPanel after save
  const [savedTick, setSavedTick] = useState(0);
  const [saving, setSaving] = useState(false);  // still used for Stripe / per-booking saves elsewhere

  return (
    <div className="space-y-4" data-testid="billing-panel">
      {/* Filter */}
      <Card className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <Receipt className="w-4 h-4 text-[#4A5D4E]" />
          <div className="text-sm font-medium">Filter</div>
          {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9CA3AF]" />}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto_auto] gap-3 items-end">
          <div>
            <Label className="text-xs">Von</Label>
            <Input type="date" value={fromDate} onChange={e => {
              const v = e.target.value;
              setFromDate(v);
              // Iter 286 — auto-adjust to-date if before from-date
              if (v && toDate && toDate < v) setToDate(v);
            }} data-testid="billing-from-date" className="h-10 sm:h-9" />
          </div>
          <div>
            <Label className="text-xs">Bis</Label>
            <Input type="date" value={toDate} min={fromDate || undefined} onChange={e => {
              const v = e.target.value;
              if (fromDate && v && v < fromDate) {
                toast.error('Bis-Datum darf nicht vor Von-Datum liegen');
                return;
              }
              setToDate(v);
            }} data-testid="billing-to-date" className="h-10 sm:h-9" />
          </div>
          <div className="sm:col-span-2 lg:col-span-1">
            <Label className="text-xs">Kostenstelle</Label>
            <select
              value={costCenter}
              onChange={e => setCostCenter(e.target.value)}
              className="w-full h-10 border border-[#E2E4E0] rounded-lg px-3 text-sm"
              data-testid="billing-cost-center-select"
            >
              <option value="">Alle Kostenstellen</option>
              {costCenters.map(cc => (
                <option key={cc.code || cc.id} value={cc.code}>{cc.code}{cc.name ? ` — ${cc.name}` : ''}</option>
              ))}
            </select>
          </div>
          {/* Iter 359 — Mobile: Action-Buttons in eigene Zeile, voll-breit und
             gleichmäßig aufgeteilt mit `flex-1`. Desktop: kompakt nebeneinander. */}
          <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="billing-refresh"
                  className="h-10 sm:h-9 w-full sm:w-auto">
            <RefreshCcw className="w-3.5 h-3.5 mr-1" /> Neu laden
          </Button>
          <Button size="sm" onClick={() => setManualOpen(true)}
                  className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-10 sm:h-9 w-full sm:w-auto"
                  data-testid="billing-manual-invoice">
            <Plus className="w-3.5 h-3.5 mr-1" /> Manuelle Rechnung
          </Button>
        </div>
      </Card>

      <ManualInvoiceDialog open={manualOpen} onClose={() => setManualOpen(false)} onCreated={() => {
        // Iter 338 — Issue #6: refresh aggregate-bookings list immediately so the
        // just-invoiced bookings disappear from the "Buchungen mit Positionen"
        // table. Previously the user had to hit "Neu laden" manually.
        load();
        setSavedTick(t => t + 1);
      }} />

      <SaveInvoiceWithTemplateDialog
        open={saveDialog.open}
        kind={saveDialog.kind}
        costCenter={costCenter}
        fromDate={fromDate}
        toDate={toDate}
        defaultTitle=""
        dialogTitle={saveDialog.kind === 'catering_aggregate' ? 'Nur Catering speichern' : 'Als Rechnung speichern'}
        // Iter 363 — BUGFIX: bookingId/bookingIds wurden bisher NICHT an den
        // Dialog weitergereicht. Folge: POST /invoices kam ohne `booking_ids`
        // raus, das Backend hat „Sammelrechnung über gesamten Zeitraum"
        // erstellt → ALLE Buchungen verschwanden statt nur der ausgewählten.
        bookingId={saveDialog.bookingId}
        bookingIds={saveDialog.bookingIds}
        onClose={() => setSaveDialog(s => ({ ...s, open: false }))}
        onSaved={() => {
          // Iter 338 — Issue #6: also refresh the aggregate so invoiced
          // bookings vanish from "Buchungen mit Positionen" immediately.
          load();
          setSavedTick(t => t + 1);
        }}
      />

      {/* Iter 332 — Total + Export Buttons jetzt im BillingBookingsTable
          Header integriert. Der frühere große "Summe abrechenbar" Banner
          wurde vom User entfernt. */}

      {/* Iter 330 — Unified Bookings-with-Positions table (replaces the
          old separate Aggregat-Zeilen + Einzel-Buchungen cards). */}
      {aggregate && (
        <BillingBookingsTable
          aggregate={aggregate}
          onSaveSingle={openSaveSingle}
          onSaveSelection={openSaveSelection}
          onSaveAllAggregate={openSaveSnapshot}
          onSaveCateringAggregate={openSaveCateringSnapshot}
          onOpenSammelrechnungPdf={openSammelrechnungPdf}
          onOpenCateringAggregatePdf={openCateringAggregatePdf}
          onOpenDatevCsv={openDatevCsv}
          onOpenGenericCsv={openGenericCsv}
        />
      )}

      {/* Iter 285 — Erstellte Rechnungen (Tracking) */}
      <InvoicesTrackingPanel refreshKey={savedTick} />
    </div>
  );
}
