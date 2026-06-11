/**
 * Iter 293 — Manual invoice creator dialog.
 *
 * Free-form invoice with arbitrary line items, validated against the active
 * template. Master-data dropdowns for Konto/Kostenstelle/Kostenträger/Projekt
 * with optional free-text override (Hybrid mode per user choice).
 */
import { useState, useEffect, useMemo } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Trash2, Plus, FileText, Loader2, Utensils, RotateCcw } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { openAuthedFile } from '../../lib/authedDownload';

const EMPTY_LINE = { label: '', description: '', quantity: 1, unit: '', unit_price: 0, tax_rate: null, discount_percent: null };

function MasterSelect({ value, onChange, items, testId, placeholder = 'Auswählen…' }) {
  // Hybrid: select OR free text. Empty `value` shows placeholder.
  const [mode, setMode] = useState(value && items.find(i => i.code === value) ? 'select' : (value ? 'text' : 'select'));
  useEffect(() => {
    if (value && !items.find(i => i.code === value)) setMode('text');
  }, [value, items]);

  return (
    <div className="flex items-center gap-1">
      {mode === 'select' ? (
        <Select value={value || '_none'} onValueChange={(v) => onChange(v === '_none' ? '' : v)}>
          <SelectTrigger data-testid={testId} className="flex-1"><SelectValue placeholder={placeholder} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="_none">— keine Auswahl —</SelectItem>
            {items.filter(i => i.active !== false).map(i => (
              <SelectItem key={i.item_id} value={i.code}>{i.code} — {i.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <Input value={value || ''} onChange={(e) => onChange(e.target.value)}
               placeholder="Freitext…" data-testid={`${testId}-text`} className="flex-1" />
      )}
      <Button size="sm" variant="outline" className="text-[10px] px-2"
              onClick={() => setMode(mode === 'select' ? 'text' : 'select')}>
        {mode === 'select' ? 'Frei' : 'Liste'}
      </Button>
    </div>
  );
}

export default function ManualInvoiceDialog({ open, onClose, onCreated, prefill = null, editInvoice = null }) {
  const [templates, setTemplates] = useState([]);
  const [ranges, setRanges] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [costObjects, setCostObjects] = useState([]);
  const [projects, setProjects] = useState([]);
  // Iter 324 — Option C: predefined catering items as quick line-item picker.
  const [cateringItems, setCateringItems] = useState([]);
  const [tpl, setTpl] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    template_id: '', number_range_id: '', title: '',
    recipient_name: '', recipient_address: '', sender_org_unit: '',
    issue_date: new Date().toISOString().slice(0, 10),
    service_period_from: '', service_period_to: '',
    payment_terms: '', notes: '',
    cost_center: '', account: '', cost_object: '', project_code: '',
    currency: 'EUR',
    lines: [{ ...EMPTY_LINE }],
  });
  const [createdId, setCreatedId] = useState(null);
  // Iter 324 — Catering picker is controlled separately so we can reset
  // to the placeholder after each pick (shadcn Select forbids "" as value).
  const [cateringPick, setCateringPick] = useState('__pick__');

  // Load master data when dialog opens
  useEffect(() => {
    if (!open) return;
    // Iter 328 — Form-Reset bei jedem neuen Öffnen ohne Prefill/Edit
    // (vorher blieb State zwischen Dialog-Zyklen erhalten → der nächste
    // "Manuelle Rechnung"-Klick zeigte noch alte Empfänger/Positionen).
    if (!editInvoice && !prefill) {
      setForm({
        template_id: '', number_range_id: '', title: '',
        recipient_name: '', recipient_address: '', sender_org_unit: '',
        issue_date: new Date().toISOString().slice(0, 10),
        service_period_from: '', service_period_to: '',
        payment_terms: '', notes: '',
        cost_center: '', account: '', cost_object: '', project_code: '',
        currency: 'EUR',
        lines: [{ ...EMPTY_LINE }],
      });
      setCateringPick('__pick__');
    }
    Promise.all([
      api.get('/admin/invoice-templates').then(r => r.data).catch(() => []),
      api.get('/admin/invoice-number-ranges').then(r => r.data).catch(() => []),
      api.get('/admin/invoice-master-data', { params: { type: 'account' } }).then(r => r.data).catch(() => []),
      api.get('/admin/invoice-master-data', { params: { type: 'cost_center' } }).then(r => r.data).catch(() => []),
      api.get('/admin/invoice-master-data', { params: { type: 'cost_object' } }).then(r => r.data).catch(() => []),
      api.get('/admin/invoice-master-data', { params: { type: 'project' } }).then(r => r.data).catch(() => []),
      // Iter 324 — pull active catering items so admin can drop them into the invoice.
      api.get('/catering-items').then(r => r.data).catch(() => []),
    ]).then(([t, r, a, cc, co, p, ci]) => {
      // Iter 324 — Drop test-data leftovers from the picker; same prefix
      // list as the SaveInvoiceWithTemplateDialog + startup migration.
      const TEST_NAME = /^(BugFixTest|E2E|TEST_|Test-(None|Templated|Plain))[\s_]/i;
      const cleanedTemplates = (t || []).filter(
        x => !TEST_NAME.test(x.name || ''),
      );
      setTemplates(cleanedTemplates);
      setRanges(r || []);
      setAccounts(a || []);
      setCostCenters(cc || []);
      setCostObjects(co || []);
      setProjects(p || []);
      setCateringItems(ci || []);
      const def = (cleanedTemplates || []).find(x => x.is_default && x.active);
      // Iter 326 — Edit-Modus: vorhandene Rechnung in das Formular laden.
      // Iter 332 — Lines werden jetzt für JEDEN Rechnungs-Typ vorgeladen,
      // damit die Buchhaltung auch Aggregat-Positionen anpassen kann.
      if (editInvoice) {
        const matchedTpl = (cleanedTemplates || []).find(
          x => x.template_id === editInvoice.template_id,
        ) || def || null;
        setTpl(matchedTpl);
        const snap = editInvoice.snapshot || {};
        const snapLines = Array.isArray(snap.lines) ? snap.lines : [];
        setForm({
          template_id: editInvoice.template_id || matchedTpl?.template_id || '',
          number_range_id: editInvoice.number_range_id || '',
          title: editInvoice.title || '',
          recipient_name: editInvoice.recipient_name || editInvoice.external_customer_name || '',
          recipient_address: editInvoice.recipient_address || '',
          sender_org_unit: editInvoice.sender_org_unit || '',
          issue_date: editInvoice.issue_date
            ? String(editInvoice.issue_date).slice(0, 10)
            : new Date().toISOString().slice(0, 10),
          service_period_from: editInvoice.service_period_from || '',
          service_period_to: editInvoice.service_period_to || '',
          payment_terms: editInvoice.payment_terms || '',
          notes: editInvoice.notes || '',
          cost_center: editInvoice.cost_center || '',
          account: editInvoice.account || '',
          cost_object: editInvoice.cost_object || '',
          project_code: editInvoice.project_code || '',
          currency: editInvoice.currency || 'EUR',
          lines: snapLines.length
            ? snapLines.map(l => ({
                label: l.label || l.description || '',
                description: l.description || '',
                quantity: l.quantity ?? 1,
                unit: l.unit || '',
                unit_price: l.unit_price ?? 0,
                tax_rate: l.tax_rate ?? l.tax_rate_effective ?? null,
                discount_percent: l.discount_percent ?? null,
              }))
            : [{ ...EMPTY_LINE }],
        });
      } else if (def) {
        setTpl(def);
        // Iter 294 — Prefill from booking (catering + km) when provided.
        // Lines coming from /api/resource-bookings/{id}/invoice already have
        // the right shape; we just need to fill the editable structure and
        // pull title/cost-center off the booking.
        const prefilledForm = {
          template_id: def.template_id,
          payment_terms: def.payment_terms_default || '',
          sender_org_unit: def.sender_org_unit_default || '',
        };
        if (prefill) {
          prefilledForm.title = prefill.title || '';
          prefilledForm.recipient_name = prefill.recipient_name || '';
          prefilledForm.cost_center = prefill.cost_center || '';
          prefilledForm.account = prefill.account || '';
          prefilledForm.notes = prefill.notes || '';
          if (Array.isArray(prefill.lines) && prefill.lines.length) {
            prefilledForm.lines = prefill.lines.map(l => ({
              label: l.label || '',
              description: l.description || '',
              quantity: l.quantity ?? 1,
              unit: l.unit || '',
              unit_price: l.unit_price ?? 0,
              tax_rate: l.tax_rate ?? null,
              discount_percent: l.discount_percent ?? null,
            }));
          }
        }
        setForm(f => ({ ...f, ...prefilledForm }));
      } else if (prefill) {
        // No default template — still apply prefill
        setForm(f => ({
          ...f,
          title: prefill.title || f.title,
          recipient_name: prefill.recipient_name || f.recipient_name,
          cost_center: prefill.cost_center || f.cost_center,
          account: prefill.account || f.account,
          notes: prefill.notes || f.notes,
          lines: (Array.isArray(prefill.lines) && prefill.lines.length)
            ? prefill.lines.map(l => ({
                label: l.label || '',
                description: l.description || '',
                quantity: l.quantity ?? 1,
                unit: l.unit || '',
                unit_price: l.unit_price ?? 0,
                tax_rate: l.tax_rate ?? null,
                discount_percent: l.discount_percent ?? null,
              }))
            : f.lines,
        }));
      }
    });
    setCreatedId(null);
  }, [open, prefill, editInvoice]);

  // When user changes template, apply its defaults
  const onTemplateChange = (template_id) => {
    const newTpl = templates.find(x => x.template_id === template_id) || null;
    setTpl(newTpl);
    setForm(f => ({
      ...f,
      template_id,
      payment_terms: newTpl?.payment_terms_default || f.payment_terms,
      sender_org_unit: newTpl?.sender_org_unit_default || f.sender_org_unit,
    }));
  };

  const required = tpl?.required_fields || ['recipient_name', 'issue_date', 'lines'];
  const visible = tpl?.visible_fields || [
    'service_period_from', 'service_period_to', 'sender_org_unit', 'recipient_address',
    'payment_terms', 'notes', 'cost_center', 'account', 'cost_object', 'project_code', 'tax_rate',
  ];
  const isVisible = (key) => visible.includes(key);
  const isRequired = (key) => required.includes(key);

  // Live totals (client-side preview)
  const totals = useMemo(() => {
    const defTax = tpl?.default_tax_rate || 0;
    let net = 0, tax = 0;
    form.lines.forEach(li => {
      const q = Number(li.quantity || 0);
      const up = Number(li.unit_price || 0);
      let g = q * up;
      if (li.discount_percent !== null && li.discount_percent !== '' && li.discount_percent !== undefined) {
        g = g * (1 - Number(li.discount_percent) / 100);
      }
      const rate = li.tax_rate !== null && li.tax_rate !== '' && li.tax_rate !== undefined ? Number(li.tax_rate) : defTax;
      net += g;
      tax += g * (rate / 100);
    });
    return { net, tax, gross: net + tax };
  }, [form.lines, tpl]);

  const setLine = (idx, patch) => {
    setForm(f => ({ ...f, lines: f.lines.map((l, i) => i === idx ? { ...l, ...patch } : l) }));
  };
  const addLine = () => setForm(f => ({ ...f, lines: [...f.lines, { ...EMPTY_LINE }] }));
  const removeLine = (idx) => setForm(f => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));

  // Iter 324 — add a predefined catering item as a new invoice line.
  // Replaces an "empty placeholder" first line if it's still untouched so
  // we don't leave a blank row at the top after the first pick.
  const addCateringLine = (itemId) => {
    const item = cateringItems.find(c => c.item_id === itemId);
    if (!item) return;
    const newLine = {
      label: item.name,
      description: item.description || '',
      quantity: item.min_quantity || 1,
      unit: item.unit || 'Stk',
      unit_price: item.price ?? 0,
      tax_rate: null,
      discount_percent: null,
    };
    setForm(f => {
      const onlyEmpty = f.lines.length === 1 && !f.lines[0].label && !Number(f.lines[0].unit_price);
      const next = onlyEmpty ? [newLine] : [...f.lines, newLine];
      return { ...f, lines: next };
    });
  };

  const submit = async () => {
    // Client-side required-field check (server still authoritative)
    const missing = required.filter(f => {
      if (f === 'lines') return !form.lines || form.lines.length === 0 || form.lines.every(l => !l.label);
      return !form[f];
    });
    if (missing.length) {
      toast.error(`Pflichtfelder fehlen: ${missing.join(', ')}`);
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        lines: form.lines.filter(l => l.label).map(l => ({
          ...l,
          quantity: Number(l.quantity || 0),
          unit_price: Number(l.unit_price || 0),
          tax_rate: l.tax_rate === '' || l.tax_rate === null || l.tax_rate === undefined ? null : Number(l.tax_rate),
          discount_percent: l.discount_percent === '' || l.discount_percent === null || l.discount_percent === undefined ? null : Number(l.discount_percent),
        })),
      };
      // Iter 326 — Edit-Modus: PUT statt POST, kein neues PDF-Öffnen
      if (editInvoice) {
        const { data } = await api.put(`/invoices/${editInvoice.invoice_id}`, payload);
        toast.success('Rechnung aktualisiert');
        onCreated?.(data);
        onClose();
        return;
      }
      const { data } = await api.post('/invoices/manual', payload);
      toast.success(`Rechnung ${data.invoice_number} erstellt`);
      setCreatedId(data.invoice_id);
      onCreated?.(data);
    } catch (e) {
      const msg = e.response?.data?.detail;
      const text = typeof msg === 'string' ? msg : msg?.message || 'Fehler';
      toast.error(text);
    } finally {
      setSaving(false);
    }
  };

  const openPdf = () => {
    // Iter 324 — use the JWT-aware blob helper so the PDF tab actually
    // renders (previously opened ?_t=token URL which leaked the JWT and
    // failed when the server stopped accepting the query-string token).
    openAuthedFile(`/invoices/${createdId}/pdf/manual`);
  };

  // Iter 330 — PDF-Vorschau ohne Speichern.
  const [previewing, setPreviewing] = useState(false);
  // Iter 333 — Positions-Reset auf Buchungs-Quelle.
  const [reloading, setReloading] = useState(false);

  const reloadLinesFromBookings = async () => {
    if (!editInvoice) return;
    if (!window.confirm('Positionen werden aus den verknüpften Buchungen neu erzeugt. Lokale Anpassungen gehen verloren. Fortfahren?')) return;
    setReloading(true);
    try {
      const { data } = await api.post(`/invoices/${editInvoice.invoice_id}/reload-lines-from-bookings`);
      const snapLines = data?.snapshot?.lines || [];
      setForm(f => ({
        ...f,
        lines: snapLines.length
          ? snapLines.map(l => ({
              label: l.label || l.description || '',
              description: l.description || '',
              quantity: l.quantity ?? 1,
              unit: l.unit || '',
              unit_price: l.unit_price ?? 0,
              tax_rate: l.tax_rate ?? l.tax_rate_effective ?? null,
              discount_percent: l.discount_percent ?? null,
            }))
          : [{ ...EMPTY_LINE }],
      }));
      toast.success(`Positionen aktualisiert (${snapLines.length} aus Buchungen geladen)`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Neuladen');
    } finally {
      setReloading(false);
    }
  };
  const openPreview = async () => {
    setPreviewing(true);
    try {
      const payload = {
        ...form,
        lines: form.lines.filter(l => l.label).map(l => ({
          ...l,
          quantity: Number(l.quantity || 0),
          unit_price: Number(l.unit_price || 0),
          tax_rate: l.tax_rate === '' || l.tax_rate === null || l.tax_rate === undefined ? null : Number(l.tax_rate),
          discount_percent: l.discount_percent === '' || l.discount_percent === null || l.discount_percent === undefined ? null : Number(l.discount_percent),
        })),
      };
      const apiBase = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem('mf_token');
      const res = await fetch(`${apiBase}/api/invoices/preview-pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail?.message || err.detail || 'Vorschau fehlgeschlagen');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      // Browser frees the object URL on close; small leak but acceptable
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      toast.error('Vorschau fehlgeschlagen');
    } finally {
      setPreviewing(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent
        className="max-w-3xl max-h-[90vh] overflow-y-auto"
        onInteractOutside={(e) => e.preventDefault()}
        data-testid="manual-invoice-dialog"
      >
        <DialogHeader>
          <DialogTitle>
            {editInvoice
              ? `Rechnung bearbeiten${editInvoice.invoice_number ? ` (${editInvoice.invoice_number})` : ''}`
              : 'Manuelle Rechnung erstellen'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Vorlage</Label>
              <Select value={form.template_id || '_none'} onValueChange={(v) => onTemplateChange(v === '_none' ? '' : v)}>
                <SelectTrigger data-testid="manual-invoice-template"><SelectValue placeholder="Standard" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">— keine —</SelectItem>
                  {templates.filter(t => t.active).map(t => (
                    <SelectItem key={t.template_id} value={t.template_id}>
                      {t.name}{t.is_default ? ' (Standard)' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Nummernkreis</Label>
              <Select value={form.number_range_id || '_default'} onValueChange={(v) => setForm(f => ({ ...f, number_range_id: v === '_default' ? '' : v }))}>
                <SelectTrigger data-testid="manual-invoice-range"><SelectValue placeholder="Standard" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_default">Standard (auto)</SelectItem>
                  {ranges.filter(r => r.active).map(r => (
                    <SelectItem key={r.range_id} value={r.range_id}>{r.name} — {r.pattern}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Rechnungstitel</Label>
              <Input value={form.title} onChange={(e) => setForm(f => ({ ...f, title: e.target.value }))}
                     placeholder="z. B. Beratung Q2" data-testid="manual-invoice-title" />
            </div>
            <div>
              <Label className="text-xs">Rechnungsdatum {isRequired('issue_date') && <span className="text-rose-600">*</span>}</Label>
              <Input type="date" value={form.issue_date} onChange={(e) => setForm(f => ({ ...f, issue_date: e.target.value }))}
                     data-testid="manual-invoice-issue-date" />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Empfänger {isRequired('recipient_name') && <span className="text-rose-600">*</span>}</Label>
              <Input value={form.recipient_name} onChange={(e) => setForm(f => ({ ...f, recipient_name: e.target.value }))}
                     data-testid="manual-invoice-recipient" />
            </div>
            {isVisible('sender_org_unit') && (
              <div>
                <Label className="text-xs">Absender / Org-Einheit {isRequired('sender_org_unit') && <span className="text-rose-600">*</span>}</Label>
                <Input value={form.sender_org_unit} onChange={(e) => setForm(f => ({ ...f, sender_org_unit: e.target.value }))}
                       data-testid="manual-invoice-sender" />
              </div>
            )}
          </div>

          {isVisible('recipient_address') && (
            <div>
              <Label className="text-xs">Anschrift Empfänger</Label>
              <Textarea rows={2} value={form.recipient_address} onChange={(e) => setForm(f => ({ ...f, recipient_address: e.target.value }))}
                        data-testid="manual-invoice-recipient-address" />
            </div>
          )}

          {(isVisible('service_period_from') || isVisible('service_period_to')) && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Leistung von</Label>
                <Input type="date" value={form.service_period_from} onChange={(e) => setForm(f => ({ ...f, service_period_from: e.target.value }))}
                       data-testid="manual-invoice-period-from" />
              </div>
              <div>
                <Label className="text-xs">Leistung bis</Label>
                <Input type="date" value={form.service_period_to} onChange={(e) => setForm(f => ({ ...f, service_period_to: e.target.value }))}
                       data-testid="manual-invoice-period-to" />
              </div>
            </div>
          )}

          {/* Accounting */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {isVisible('account') && (
              <div>
                <Label className="text-xs">Konto {isRequired('account') && <span className="text-rose-600">*</span>}</Label>
                <MasterSelect value={form.account} onChange={(v) => setForm(f => ({ ...f, account: v }))} items={accounts} testId="manual-invoice-account" />
              </div>
            )}
            {isVisible('cost_center') && (
              <div>
                <Label className="text-xs">Kostenstelle {isRequired('cost_center') && <span className="text-rose-600">*</span>}</Label>
                <MasterSelect value={form.cost_center} onChange={(v) => setForm(f => ({ ...f, cost_center: v }))} items={costCenters} testId="manual-invoice-cost-center" />
              </div>
            )}
            {isVisible('cost_object') && (
              <div>
                <Label className="text-xs">Kostenträger {isRequired('cost_object') && <span className="text-rose-600">*</span>}</Label>
                <MasterSelect value={form.cost_object} onChange={(v) => setForm(f => ({ ...f, cost_object: v }))} items={costObjects} testId="manual-invoice-cost-object" />
              </div>
            )}
            {isVisible('project_code') && (
              <div>
                <Label className="text-xs">Projekt {isRequired('project_code') && <span className="text-rose-600">*</span>}</Label>
                <MasterSelect value={form.project_code} onChange={(v) => setForm(f => ({ ...f, project_code: v }))} items={projects} testId="manual-invoice-project" />
              </div>
            )}
          </div>

          {/* Line items */}
          <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
            {/* Iter 332 — Positionen sind jetzt für JEDEN Rechnungs-Typ
                editierbar (Aggregat, Catering, Single, Manual). Vorher
                konnten Aggregat-Rechnungen nicht bearbeitet werden, was
                den Buchhaltungs-Workflow blockierte. Bei Aggregat zeigen
                wir nur einen Hinweis, dass die initialen Positionen aus
                den Buchungen erzeugt wurden. */}
            {editInvoice && editInvoice.kind !== 'manual' && (
              <div className="bg-[#FFFBEB] border-b border-[#FDE68A] p-2 text-[11px] text-[#92400E] flex items-center justify-between gap-2 flex-wrap"
                   data-testid="edit-invoice-aggregate-notice">
                <span>
                  <strong>Hinweis:</strong> Die Positionen wurden aus den
                  {' '}{editInvoice.kind === 'catering_aggregate' ? 'Catering-Anforderungen' : 'Buchungen'} erzeugt.
                  Du kannst sie hier nachträglich anpassen — der Bezug zu den
                  Buchungen bleibt im Audit-Verlauf erhalten.
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={reloadLinesFromBookings}
                  disabled={reloading}
                  data-testid="edit-invoice-reload-lines"
                  className="h-7 text-[11px] border-[#92400E]/30 text-[#92400E] hover:bg-[#FDE68A]/50"
                  title="Positionen aus den verknüpften Buchungen neu erzeugen"
                >
                  {reloading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RotateCcw className="w-3 h-3 mr-1" />}
                  Positionen neu laden
                </Button>
              </div>
            )}
            <>
            <div className="bg-[#F3F4F1] px-3 py-2 text-xs font-medium text-[#1C1F1D] flex items-center justify-between flex-wrap gap-2">
              <span>Positionen {isRequired('lines') && <span className="text-rose-600">*</span>}</span>
              <div className="flex items-center gap-1">
                {cateringItems.length > 0 && (
                  <Select
                    value={cateringPick}
                    onValueChange={(v) => {
                      if (v && v !== '__pick__') {
                        addCateringLine(v);
                        // Reset to placeholder so the same item can be picked again.
                        setCateringPick('__pick__');
                      }
                    }}
                  >
                    <SelectTrigger
                      data-testid="manual-invoice-catering-picker"
                      className="h-7 text-[11px] w-[210px]"
                    >
                      <SelectValue placeholder="Catering-Artikel hinzufügen…" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__pick__" disabled>
                        Catering-Artikel hinzufügen…
                      </SelectItem>
                      {cateringItems.map(ci => (
                        <SelectItem
                          key={ci.item_id}
                          value={ci.item_id}
                          data-testid={`manual-invoice-catering-option-${ci.item_id}`}
                        >
                          <span className="inline-flex items-center gap-1">
                            <Utensils className="w-3 h-3 text-[#4A5D4E]" />
                            {ci.name}
                            <span className="text-[10px] text-[#9CA3AF]">
                              {' '}· {Number(ci.price ?? 0).toFixed(2)} €/{ci.unit || 'Stk'}
                            </span>
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <Button size="sm" variant="ghost" onClick={addLine} data-testid="manual-invoice-add-line">
                  <Plus className="w-3.5 h-3.5 mr-1" />Position
                </Button>
              </div>
            </div>
            <div className="divide-y divide-[#F3F4F1]">
              {form.lines.map((li, idx) => (
                <div key={idx} className="p-3 space-y-2" data-testid={`manual-invoice-line-${idx}`}>
                  <div className="grid grid-cols-1 md:grid-cols-[1fr_70px_50px_90px_70px_70px_36px] gap-2 items-end">
                    <div>
                      <Label className="text-[10px]">Bezeichnung</Label>
                      <Input value={li.label} onChange={(e) => setLine(idx, { label: e.target.value })}
                             data-testid={`line-label-${idx}`} />
                    </div>
                    <div>
                      <Label className="text-[10px]">Menge</Label>
                      <Input type="number" step="0.01" value={li.quantity} onChange={(e) => setLine(idx, { quantity: e.target.value })}
                             data-testid={`line-quantity-${idx}`} />
                    </div>
                    <div>
                      <Label className="text-[10px]">Einheit</Label>
                      <Input value={li.unit} onChange={(e) => setLine(idx, { unit: e.target.value })}
                             placeholder="Stk" data-testid={`line-unit-${idx}`} />
                    </div>
                    <div>
                      <Label className="text-[10px]">€/Einheit</Label>
                      <Input type="number" step="0.01" value={li.unit_price} onChange={(e) => setLine(idx, { unit_price: e.target.value })}
                             data-testid={`line-unit-price-${idx}`} />
                    </div>
                    <div>
                      <Label className="text-[10px]">MwSt %</Label>
                      <Input type="number" step="0.1" value={li.tax_rate ?? ''} onChange={(e) => setLine(idx, { tax_rate: e.target.value })}
                             placeholder={`${tpl?.default_tax_rate ?? 0}`} data-testid={`line-tax-${idx}`} />
                    </div>
                    <div>
                      <Label className="text-[10px]">Rabatt %</Label>
                      <Input type="number" step="0.1" value={li.discount_percent ?? ''} onChange={(e) => setLine(idx, { discount_percent: e.target.value })}
                             placeholder="0" data-testid={`line-discount-${idx}`} />
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => removeLine(idx)} className="h-9"
                            data-testid={`line-remove-${idx}`}>
                      <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                    </Button>
                  </div>
                  <Input value={li.description ?? ''} onChange={(e) => setLine(idx, { description: e.target.value })}
                         placeholder="Beschreibung (optional)" className="text-xs"
                         data-testid={`line-description-${idx}`} />
                </div>
              ))}
            </div>
            </>
          </div>

          {/* Payment terms / notes */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {isVisible('payment_terms') && (
              <div>
                <Label className="text-xs">Zahlungsbedingungen</Label>
                <Textarea rows={2} value={form.payment_terms} onChange={(e) => setForm(f => ({ ...f, payment_terms: e.target.value }))}
                          data-testid="manual-invoice-payment-terms" />
              </div>
            )}
            {isVisible('notes') && (
              <div>
                <Label className="text-xs">Hinweise / Bemerkungen</Label>
                <Textarea rows={2} value={form.notes} onChange={(e) => setForm(f => ({ ...f, notes: e.target.value }))}
                          data-testid="manual-invoice-notes" />
              </div>
            )}
          </div>

          {/* Live totals */}
          <div className="bg-[#F9FAF7] border border-[#E2E4E0] rounded-lg p-3 grid grid-cols-3 gap-3 text-xs">
            <div>Netto: <span className="font-medium text-[#1C1F1D]">{totals.net.toFixed(2)} EUR</span></div>
            <div>MwSt: <span className="font-medium text-[#1C1F1D]">{totals.tax.toFixed(2)} EUR</span></div>
            <div>Brutto: <span className="font-semibold text-[#4A5D4E]">{totals.gross.toFixed(2)} EUR</span></div>
          </div>
        </div>

        <DialogFooter className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={onClose}>Schließen</Button>
          {/* Iter 330 — PDF-Vorschau ohne Speichern */}
          {!createdId && (
            <Button variant="outline" onClick={openPreview} disabled={previewing || saving}
                    data-testid="manual-invoice-preview"
                    className="border-[#4A5D4E] text-[#4A5D4E] hover:bg-[#F3F4F1]">
              {previewing ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <FileText className="w-3.5 h-3.5 mr-1" />}
              PDF-Vorschau
            </Button>
          )}
          {createdId ? (
            <Button onClick={openPdf} data-testid="manual-invoice-open-pdf" className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white">
              <FileText className="w-3.5 h-3.5 mr-1" />PDF öffnen
            </Button>
          ) : (
            <Button onClick={submit} disabled={saving} data-testid="manual-invoice-save"
                    className="bg-[#2C9A6E] hover:bg-[#218252] text-white">
              {saving ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : null}
              {editInvoice ? 'Änderungen speichern' : 'Rechnung erstellen'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
