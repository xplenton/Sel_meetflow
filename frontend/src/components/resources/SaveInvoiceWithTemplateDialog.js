/**
 * Iter 322 — Template picker shown before saving an aggregate invoice.
 *
 * The "Als Rechnung speichern" / "Nur Catering speichern" buttons now route
 * through this dialog so the admin can pick which configured template (with
 * logo, header, footer, payment terms) will be applied to the saved invoice
 * PDF. The default template is pre-selected so power-users can hit Enter to
 * keep the previous one-click flow.
 */
import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { FileText, Loader2 } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

export default function SaveInvoiceWithTemplateDialog({
  open, onClose, kind = 'aggregate',
  costCenter = '', fromDate = '', toDate = '',
  defaultTitle = '',
  // Iter 324 — header title is now contextual to the trigger button so
  // "Als Rechnung speichern" no longer shows "Sammelrechnung speichern".
  dialogTitle = '',
  // Iter 330 — Single-Buchung-Rechnung (kind="single") oder
  // Sammelrechnung aus expliziter Auswahl (bookingIds[]).
  bookingId = null,
  bookingIds = null,
  onSaved,
}) {
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [title, setTitle] = useState(defaultTitle);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle(defaultTitle);
    api.get('/admin/invoice-templates')
      .then(r => {
        // Iter 324 — Drop any leftover test fixtures so they can't poll up
        // in the picker even if a future automated test forgets to clean
        // up. Same prefix list as the one-shot startup migration.
        const TEST_NAME = /^(BugFixTest|E2E|TEST_|Test-(None|Templated|Plain))[\s_]/i;
        const all = (r.data || []).filter(
          t => t.active !== false && !TEST_NAME.test(t.name || ''),
        );
        // Sort: default template first, then alphabetical
        all.sort((a, b) => {
          if (a.is_default && !b.is_default) return -1;
          if (!a.is_default && b.is_default) return 1;
          return (a.name || '').localeCompare(b.name || '', 'de');
        });
        setTemplates(all);
        // Preselect default template if any, else the first one
        const def = all.find(t => t.is_default) || all[0];
        setTemplateId(def?.template_id || '');
      })
      .catch(() => setTemplates([]));
  }, [open, defaultTitle]);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.post('/invoices', {
        kind,
        cost_center: costCenter || null,
        from_date: fromDate,
        to_date: toDate,
        title: title || null,
        template_id: templateId || null,
        // Iter 330 — Single-Booking-/Selektion-Rechnungen
        booking_id: bookingId || undefined,
        booking_ids: bookingIds && bookingIds.length ? bookingIds : undefined,
      });
      const invId = data?.invoice_id;
      const invLabel = data?.invoice_number || invId || '';

      // Iter 364 — User-Wunsch: Undo nach „Versehentlich erstellt". Toast
      // bietet 10 s lang einen „Rückgängig"-Button. Klick storniert den
      // Entwurf direkt (kein Storno-Dialog nötig) und löst ein erneutes
      // `onSaved` aus, damit die Buchung sofort wieder in der Tabelle
      // erscheint. Funktioniert nur für nicht-freigegebene Entwürfe (was
      // im Moment direkt nach `save` immer der Fall ist).
      toast.success(
        invLabel
          ? `Rechnung ${invLabel} als Entwurf gespeichert`
          : 'Rechnung als Entwurf gespeichert',
        {
          duration: 10_000,
          action: invId
            ? {
                label: 'Rückgängig',
                onClick: async () => {
                  try {
                    await api.post(`/invoices/${invId}/void`, {
                      reason: 'Versehentlich erstellt — vom User rückgängig gemacht',
                    });
                    toast.success('Rechnung rückgängig gemacht');
                    onSaved?.();
                  } catch (err) {
                    toast.error(err.response?.data?.detail || 'Rückgängig fehlgeschlagen');
                  }
                },
              }
            : undefined,
        }
      );
      onSaved?.();
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  const kindLabel = dialogTitle
    || (kind === 'catering_aggregate' ? 'Nur Catering speichern' : 'Als Rechnung speichern');

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md" data-testid="save-invoice-template-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold text-[#1C1F1D] flex items-center gap-2">
            <FileText className="w-4 h-4 text-[#4A5D4E]" /> {kindLabel}
          </DialogTitle>
          <p className="text-xs text-[#6B7280] mt-1">
            Wählen Sie eine Rechnungsvorlage. Logo, Kopf-/Fußzeile und Zahlungsbedingungen
            werden in den PDF-Druck der gespeicherten Rechnung übernommen.
          </p>
        </DialogHeader>

        <div className="space-y-3 pt-2">
          <div>
            <Label className="text-xs">Titel (optional)</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={defaultTitle || 'Leer lassen → automatisch „Rechnung_<Nummer>"'}
              className="border-[#E2E4E0]"
              data-testid="save-invoice-title"
            />
          </div>

          <div>
            <Label className="text-xs">Rechnungsvorlage</Label>
            {templates.length === 0 ? (
              <div className="text-xs text-[#9CA3AF] mt-1 p-2 rounded bg-[#F3F4F1] border border-[#E2E4E0]">
                Keine Vorlagen konfiguriert — Rechnung wird im Standard-Layout (ohne Logo) gespeichert.
              </div>
            ) : (
              <Select value={templateId} onValueChange={setTemplateId}>
                <SelectTrigger data-testid="save-invoice-template-select" className="border-[#E2E4E0]">
                  <SelectValue placeholder="— ohne Vorlage —" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— ohne Vorlage (Standard-Layout) —</SelectItem>
                  {templates.map(t => (
                    <SelectItem key={t.template_id} value={t.template_id}>
                      {t.name}{t.is_default ? ' (Standard)' : ''}
                      {t.logo_storage_path ? ' · mit Logo' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="text-xs text-[#6B7280] space-y-0.5 pt-1">
            {bookingId ? (
              <div><span className="text-[#9CA3AF]">Buchung:</span> {bookingId}</div>
            ) : bookingIds?.length ? (
              <div><span className="text-[#9CA3AF]">Buchungen:</span> {bookingIds.length} ausgewählt</div>
            ) : (
              <>
                <div><span className="text-[#9CA3AF]">Kostenstelle:</span> {costCenter || '— alle —'}</div>
                <div><span className="text-[#9CA3AF]">Zeitraum:</span> {fromDate || '...'} – {toDate || '...'}</div>
              </>
            )}
          </div>
        </div>

        <DialogFooter className="gap-2 pt-2">
          <Button variant="outline" onClick={onClose} disabled={saving}
                  className="border-[#E2E4E0] text-[#6B7280]"
                  data-testid="save-invoice-cancel">
            Abbrechen
          </Button>
          <Button onClick={() => save()} disabled={saving}
                  className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white"
                  data-testid="save-invoice-confirm">
            {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
