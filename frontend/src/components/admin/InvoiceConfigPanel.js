/**
 * Iter 293 — Invoice configuration admin panel.
 * Manages Templates, Number Ranges, Master Data (Konten/Kostenstellen/Kostenträger/Projekte).
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Switch } from '../ui/switch';
import { Badge } from '../ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Plus, Pencil, Trash2, FileText, Hash, Database, Upload, Image as ImageIcon, X } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const BACKEND = process.env.REACT_APP_BACKEND_URL;

// Iter 296 — Live-Preview helper. Mirrors the backend's `_render_rich_text`
// behaviour so the user sees roughly what the PDF will look like.
// `text` plain → newlines to <br/>, HTML-escaped
// `markdown`  → marked → DOMPurify
// `html`      → DOMPurify (allowlist similar to ReportLab's Paragraph)
const SAFE_TAGS = ['b', 'i', 'u', 'strong', 'em', 'br', 'a', 'font', 'p', 'span'];
const SAFE_ATTRS = ['href', 'color', 'size', 'style'];
function renderPreview(text, fmt) {
  if (!text) return '';
  if (fmt === 'text') {
    const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return escaped.replace(/\n/g, '<br/>');
  }
  let html = fmt === 'markdown' ? marked.parse(text, { breaks: true }) : text;
  return DOMPurify.sanitize(html, { ALLOWED_TAGS: SAFE_TAGS, ALLOWED_ATTR: SAFE_ATTRS });
}

const MASTER_TYPES = [
  { id: 'account', label: 'Konten' },
  { id: 'cost_center', label: 'Kostenstellen' },
  { id: 'cost_object', label: 'Kostenträger' },
  { id: 'project', label: 'Projekte' },
];

const OPTIONAL_FIELDS = [
  { key: 'service_period_from', label: 'Leistungszeitraum von' },
  { key: 'service_period_to', label: 'Leistungszeitraum bis' },
  { key: 'sender_org_unit', label: 'Absender / Org-Einheit' },
  { key: 'recipient_address', label: 'Anschrift Empfänger' },
  { key: 'payment_terms', label: 'Zahlungsbedingungen' },
  { key: 'notes', label: 'Hinweise' },
  { key: 'cost_center', label: 'Kostenstelle' },
  { key: 'account', label: 'Konto' },
  { key: 'cost_object', label: 'Kostenträger' },
  { key: 'project_code', label: 'Projekt' },
  { key: 'tax_rate', label: 'MwSt-Satz pro Position' },
];
const FIXED_REQUIRED = [
  { key: 'recipient_name', label: 'Empfänger (immer Pflicht)' },
  { key: 'issue_date', label: 'Rechnungsdatum (immer Pflicht)' },
  { key: 'lines', label: 'Positionen (immer Pflicht)' },
];

// ---------------- Master Data Panel ----------------

function MasterDataPanel() {
  const [type, setType] = useState('account');
  const [items, setItems] = useState([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ code: '', label: '', description: '', active: true, accounting_email: '' });

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/admin/invoice-master-data', { params: { type } });
      setItems(data || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Laden fehlgeschlagen');
    }
  }, [type]);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditing(null); setForm({ code: '', label: '', description: '', active: true, accounting_email: '' }); setEditorOpen(true); };
  const openEdit = (it) => { setEditing(it); setForm({ code: it.code, label: it.label, description: it.description || '', active: it.active, accounting_email: it.accounting_email || '' }); setEditorOpen(true); };

  const save = async () => {
    try {
      if (editing) {
        await api.put(`/admin/invoice-master-data/${editing.item_id}`, form);
      } else {
        await api.post('/admin/invoice-master-data', { type, ...form });
      }
      toast.success('Gespeichert');
      setEditorOpen(false);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen');
    }
  };
  const remove = async (it) => {
    if (!window.confirm(`Eintrag ${it.code} wirklich löschen?`)) return;
    try { await api.delete(`/admin/invoice-master-data/${it.item_id}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Löschen fehlgeschlagen'); }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="w-56" data-testid="master-data-type"><SelectValue /></SelectTrigger>
          <SelectContent>{MASTER_TYPES.map(t => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}</SelectContent>
        </Select>
        <Button size="sm" onClick={openCreate} data-testid="master-data-add" className="rounded-full">
          <Plus className="w-3.5 h-3.5 mr-1" />Eintrag
        </Button>
      </div>
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#F3F4F1] text-left text-xs text-[#6B7280]">
            <tr>
              <th className="py-2 px-3">Code</th>
              <th className="py-2 px-3">Bezeichnung</th>
              <th className="py-2 px-3">Beschreibung</th>
              {type === 'cost_center' && <th className="py-2 px-3">Buchhaltungs-E-Mail</th>}
              <th className="py-2 px-3">Aktiv</th>
              <th className="py-2 px-3"></th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={type === 'cost_center' ? 6 : 5} className="py-4 text-center text-[#9CA3AF]">Keine Einträge</td></tr>
            ) : items.map(it => (
              <tr key={it.item_id} className="border-t border-[#F3F4F1]" data-testid={`master-row-${it.item_id}`}>
                <td className="py-2 px-3 font-mono">{it.code}</td>
                <td className="py-2 px-3">{it.label}</td>
                <td className="py-2 px-3 text-[#6B7280]">{it.description}</td>
                {type === 'cost_center' && <td className="py-2 px-3 text-[#6B7280]">{it.accounting_email || '—'}</td>}
                <td className="py-2 px-3">{it.active ? <Badge variant="outline" className="text-[10px] border-emerald-400 text-emerald-700">aktiv</Badge> : <Badge variant="outline" className="text-[10px]">inaktiv</Badge>}</td>
                <td className="py-2 px-3 text-right">
                  <Button size="sm" variant="ghost" onClick={() => openEdit(it)}><Pencil className="w-3.5 h-3.5" /></Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(it)}><Trash2 className="w-3.5 h-3.5 text-rose-600" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent onInteractOutside={(e) => e.preventDefault()} data-testid="master-data-dialog">
          <DialogHeader><DialogTitle>{editing ? 'Bearbeiten' : 'Neuer Eintrag'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-xs">Code *</Label><Input value={form.code} disabled={!!editing} onChange={(e) => setForm(f => ({ ...f, code: e.target.value }))} data-testid="md-code" /></div>
            <div><Label className="text-xs">Bezeichnung *</Label><Input value={form.label} onChange={(e) => setForm(f => ({ ...f, label: e.target.value }))} data-testid="md-label" /></div>
            <div><Label className="text-xs">Beschreibung</Label><Textarea rows={2} value={form.description} onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))} data-testid="md-description" /></div>
            {type === 'cost_center' && (
              <div>
                <Label className="text-xs">Buchhaltungs-E-Mail</Label>
                <Input
                  type="email"
                  placeholder="buchhaltung@klinikum.de"
                  value={form.accounting_email}
                  onChange={(e) => setForm(f => ({ ...f, accounting_email: e.target.value }))}
                  data-testid="md-accounting-email"
                />
                <p className="text-[10px] text-[#9CA3AF] mt-0.5">Für Auto-Versand der Sammelrechnung an die Buchhaltung dieser Kostenstelle.</p>
              </div>
            )}
            <div className="flex items-center gap-2"><Switch checked={form.active} onCheckedChange={(v) => setForm(f => ({ ...f, active: v }))} data-testid="md-active" /><Label className="text-xs">Aktiv</Label></div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditorOpen(false)}>Abbrechen</Button>
            <Button onClick={save} data-testid="md-save">Speichern</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------- Number Ranges Panel ----------------

function NumberRangesPanel() {
  const [items, setItems] = useState([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', prefix: 'RE', pattern: '{PREFIX}-{YYYY}-{####}', start_number: 1, yearly_reset: true, active: true, is_default: false });

  const load = useCallback(async () => {
    try { const { data } = await api.get('/admin/invoice-number-ranges'); setItems(data || []); }
    catch (e) { toast.error(e.response?.data?.detail || 'Laden fehlgeschlagen'); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditing(null); setForm({ name: '', prefix: 'RE', pattern: '{PREFIX}-{YYYY}-{####}', start_number: 1, yearly_reset: true, active: true, is_default: false }); setEditorOpen(true); };
  const openEdit = (it) => { setEditing(it); setForm({ ...it }); setEditorOpen(true); };
  const save = async () => {
    try {
      if (editing) await api.put(`/admin/invoice-number-ranges/${editing.range_id}`, form);
      else await api.post('/admin/invoice-number-ranges', form);
      toast.success('Gespeichert'); setEditorOpen(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen'); }
  };
  const remove = async (it) => {
    if (!window.confirm(`Kreis ${it.name} wirklich löschen?`)) return;
    try { await api.delete(`/admin/invoice-number-ranges/${it.range_id}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Löschen fehlgeschlagen'); }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" onClick={openCreate} data-testid="range-add" className="rounded-full"><Plus className="w-3.5 h-3.5 mr-1" />Nummernkreis</Button>
      </div>
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#F3F4F1] text-left text-xs text-[#6B7280]">
            <tr><th className="py-2 px-3">Name</th><th className="py-2 px-3">Pattern</th><th className="py-2 px-3">Aktueller Zähler</th><th className="py-2 px-3">Standard</th><th className="py-2 px-3"></th></tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={5} className="py-4 text-center text-[#9CA3AF]">Keine Nummernkreise</td></tr>
            ) : items.map(it => (
              <tr key={it.range_id} className="border-t border-[#F3F4F1]" data-testid={`range-row-${it.range_id}`}>
                <td className="py-2 px-3 font-medium">{it.name}</td>
                <td className="py-2 px-3 font-mono text-xs">{it.pattern}</td>
                <td className="py-2 px-3">{it.current_number ?? '—'}{it.yearly_reset && it.current_year ? ` (${it.current_year})` : ''}</td>
                <td className="py-2 px-3">{it.is_default && <Badge className="bg-[#4A5D4E] text-white text-[10px]">Standard</Badge>}</td>
                <td className="py-2 px-3 text-right">
                  <Button size="sm" variant="ghost" onClick={() => openEdit(it)}><Pencil className="w-3.5 h-3.5" /></Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(it)}><Trash2 className="w-3.5 h-3.5 text-rose-600" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent onInteractOutside={(e) => e.preventDefault()} data-testid="range-dialog">
          <DialogHeader><DialogTitle>{editing ? 'Bearbeiten' : 'Neuer Kreis'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-xs">Name *</Label><Input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} data-testid="range-name" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs">Präfix</Label><Input value={form.prefix} onChange={(e) => setForm(f => ({ ...f, prefix: e.target.value }))} data-testid="range-prefix" /></div>
              <div><Label className="text-xs">Startnummer</Label><Input type="number" value={form.start_number} onChange={(e) => setForm(f => ({ ...f, start_number: Number(e.target.value) }))} data-testid="range-start" /></div>
            </div>
            <div>
              <Label className="text-xs">Pattern</Label>
              <Input value={form.pattern} onChange={(e) => setForm(f => ({ ...f, pattern: e.target.value }))} data-testid="range-pattern" />
              <p className="text-[10px] text-[#9CA3AF] mt-1">Platzhalter: {`{PREFIX} {YYYY} {YY} {MM} {####} {###} {##}`}</p>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2"><Switch checked={form.yearly_reset} onCheckedChange={(v) => setForm(f => ({ ...f, yearly_reset: v }))} data-testid="range-yearly-reset" /><Label className="text-xs">Jährlicher Reset</Label></div>
              <div className="flex items-center gap-2"><Switch checked={form.active} onCheckedChange={(v) => setForm(f => ({ ...f, active: v }))} data-testid="range-active" /><Label className="text-xs">Aktiv</Label></div>
              <div className="flex items-center gap-2"><Switch checked={form.is_default} onCheckedChange={(v) => setForm(f => ({ ...f, is_default: v }))} data-testid="range-default" /><Label className="text-xs">Standard</Label></div>
            </div>
          </div>
          <DialogFooter><Button variant="ghost" onClick={() => setEditorOpen(false)}>Abbrechen</Button><Button onClick={save} data-testid="range-save">Speichern</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------- Templates Panel ----------------

function TemplatesPanel() {
  const [items, setItems] = useState([]);
  const [ranges, setRanges] = useState([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [logoVersion, setLogoVersion] = useState(0); // cache-bust preview after upload
  const logoInputRef = useRef(null);
  // Iter 321 — Logo can now be selected BEFORE the template is saved.
  // We stash the file + a local object-URL preview, then upload to the
  // freshly-created template_id right after the POST succeeds in save().
  const [pendingLogo, setPendingLogo] = useState(null);
  const [pendingLogoUrl, setPendingLogoUrl] = useState(null);
  const [form, setForm] = useState({
    name: '', description: '', header_text: '', header_format: 'text',
    footer_text: '', footer_format: 'text',
    payment_terms_default: '', bank_details: '', sender_org_unit_default: '',
    default_tax_rate: 19, default_number_range_id: '',
    required_fields: ['recipient_name', 'issue_date', 'lines'],
    visible_fields: OPTIONAL_FIELDS.map(f => f.key),
    is_default: false, active: true,
  });

  const load = useCallback(async () => {
    try {
      const [t, r] = await Promise.all([
        api.get('/admin/invoice-templates').then(x => x.data),
        api.get('/admin/invoice-number-ranges').then(x => x.data),
      ]);
      setItems(t || []); setRanges(r || []);
    } catch (e) { toast.error(e.response?.data?.detail || 'Laden fehlgeschlagen'); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditing(null);
    setPendingLogo(null);
    if (pendingLogoUrl) URL.revokeObjectURL(pendingLogoUrl);
    setPendingLogoUrl(null);
    setForm({
      name: '', description: '', header_text: '', header_format: 'text',
      footer_text: '', footer_format: 'text',
      payment_terms_default: 'Zahlbar binnen 14 Tagen netto', bank_details: '', sender_org_unit_default: '',
      default_tax_rate: 19, default_number_range_id: '',
      required_fields: ['recipient_name', 'issue_date', 'lines'],
      visible_fields: OPTIONAL_FIELDS.map(f => f.key),
      is_default: false, active: true,
    });
    setEditorOpen(true);
  };
  const openEdit = (it) => {
    setEditing(it);
    setPendingLogo(null);
    if (pendingLogoUrl) URL.revokeObjectURL(pendingLogoUrl);
    setPendingLogoUrl(null);
    setForm({
      ...it,
      header_format: it.header_format || 'text',
      footer_format: it.footer_format || 'text',
      default_number_range_id: it.default_number_range_id || '',
    });
    setEditorOpen(true);
  };

  // Iter 321 — Validate + stash the file. Upload happens in `save()` after
  // we know the template_id (for new templates) or immediately (for edits).
  const stashLogo = (file) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast.error('Maximal 2 MB pro Logo'); return; }
    if (!['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/svg+xml'].includes(file.type)) {
      toast.error('Nur PNG, JPG, WebP oder SVG erlaubt');
      return;
    }
    setPendingLogo(file);
    if (pendingLogoUrl) URL.revokeObjectURL(pendingLogoUrl);
    setPendingLogoUrl(URL.createObjectURL(file));
  };

  const _uploadLogoToTemplate = async (templateId, file) => {
    const fd = new FormData();
    fd.append('file', file);
    await api.post(`/admin/invoice-templates/${templateId}/logo`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  const save = async () => {
    if (!form.name?.trim()) { toast.error('Name ist Pflicht'); return; }
    try {
      const payload = { ...form, default_number_range_id: form.default_number_range_id || null };
      let templateId;
      if (editing) {
        await api.put(`/admin/invoice-templates/${editing.template_id}`, payload);
        templateId = editing.template_id;
      } else {
        const { data } = await api.post('/admin/invoice-templates', payload);
        templateId = data?.template_id;
      }
      // Iter 321 — Upload stashed logo if user picked one during create/edit
      if (pendingLogo && templateId) {
        try {
          await _uploadLogoToTemplate(templateId, pendingLogo);
        } catch (e) {
          toast.error(e.response?.data?.detail || 'Logo-Upload fehlgeschlagen — Vorlage wurde aber gespeichert');
        }
        setPendingLogo(null);
        if (pendingLogoUrl) URL.revokeObjectURL(pendingLogoUrl);
        setPendingLogoUrl(null);
      }
      toast.success('Gespeichert'); setEditorOpen(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen'); }
  };
  const remove = async (it) => {
    if (!window.confirm(`Vorlage ${it.name} wirklich löschen?`)) return;
    try { await api.delete(`/admin/invoice-templates/${it.template_id}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Löschen fehlgeschlagen'); }
  };

  const uploadLogo = async (file) => {
    // Iter 321 — For NEW templates: stash locally + upload after save.
    // For EXISTING templates: stash for visual feedback, then push to backend.
    stashLogo(file);
    if (editing?.template_id && file) {
      try {
        await _uploadLogoToTemplate(editing.template_id, file);
        toast.success('Logo gespeichert');
        setLogoVersion(v => v + 1);
        load();
      } catch (e) {
        toast.error(e.response?.data?.detail || 'Logo-Upload fehlgeschlagen');
      }
    }
  };
  const removeLogo = async () => {
    // Clear local stash regardless
    if (pendingLogoUrl) URL.revokeObjectURL(pendingLogoUrl);
    setPendingLogo(null);
    setPendingLogoUrl(null);
    if (!editing?.template_id) return;  // Nothing to delete on backend yet
    if (!window.confirm('Logo entfernen?')) return;
    try {
      await api.delete(`/admin/invoice-templates/${editing.template_id}/logo`);
      setLogoVersion(v => v + 1);
      load();
      toast.success('Logo entfernt');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Löschen fehlgeschlagen');
    }
  };

  const toggleOptional = (key, list) => {
    if (form[list].includes(key)) setForm(f => ({ ...f, [list]: f[list].filter(x => x !== key) }));
    else setForm(f => ({ ...f, [list]: [...f[list], key] }));
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" onClick={openCreate} data-testid="template-add" className="rounded-full"><Plus className="w-3.5 h-3.5 mr-1" />Vorlage</Button>
      </div>
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-[#F3F4F1] text-left text-xs text-[#6B7280]">
            <tr><th className="py-2 px-3">Logo</th><th className="py-2 px-3">Name</th><th className="py-2 px-3">Pflichtfelder</th><th className="py-2 px-3">MwSt %</th><th className="py-2 px-3">Standard</th><th className="py-2 px-3"></th></tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={6} className="py-4 text-center text-[#9CA3AF]">Keine Vorlagen</td></tr>
            ) : items.map(it => (
              <tr key={it.template_id} className="border-t border-[#F3F4F1]" data-testid={`template-row-${it.template_id}`}>
                <td className="py-2 px-3">
                  {it.logo_storage_path ? (
                    <img src={`${BACKEND}/api/admin/invoice-templates/${it.template_id}/logo`} alt="" className="h-7 w-auto object-contain" data-testid={`template-logo-thumb-${it.template_id}`} />
                  ) : (
                    <ImageIcon className="w-4 h-4 text-[#D1D5DB]" />
                  )}
                </td>
                <td className="py-2 px-3 font-medium">{it.name}</td>
                <td className="py-2 px-3 text-xs">{(it.required_fields || []).join(', ')}</td>
                <td className="py-2 px-3">{it.default_tax_rate}%</td>
                <td className="py-2 px-3">{it.is_default && <Badge className="bg-[#4A5D4E] text-white text-[10px]">Standard</Badge>}</td>
                <td className="py-2 px-3 text-right">
                  <Button size="sm" variant="ghost" onClick={() => openEdit(it)}><Pencil className="w-3.5 h-3.5" /></Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(it)}><Trash2 className="w-3.5 h-3.5 text-rose-600" /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" onInteractOutside={(e) => e.preventDefault()} data-testid="template-dialog">
          <DialogHeader><DialogTitle>{editing ? 'Bearbeiten' : 'Neue Vorlage'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs">Name *</Label><Input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} data-testid="template-name" /></div>
              <div><Label className="text-xs">Std. MwSt %</Label><Input type="number" value={form.default_tax_rate} onChange={(e) => setForm(f => ({ ...f, default_tax_rate: Number(e.target.value) }))} data-testid="template-tax" /></div>
            </div>
            <div><Label className="text-xs">Beschreibung</Label><Input value={form.description || ''} onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))} /></div>

            {/* Logo (iter 295 + iter 321) — works for new AND existing templates */}
            <div>
              <Label className="text-xs font-semibold">Logo</Label>
              <div className="mt-1 flex items-center gap-3">
                <div className="w-32 h-16 border border-[#E2E4E0] rounded-md bg-[#F9FAF7] flex items-center justify-center overflow-hidden">
                  {pendingLogoUrl ? (
                    <img
                      src={pendingLogoUrl}
                      alt="Logo (Vorschau)"
                      className="max-w-full max-h-full object-contain"
                      data-testid="template-logo-pending-preview"
                    />
                  ) : editing?.logo_storage_path ? (
                    <img
                      src={`${BACKEND}/api/admin/invoice-templates/${editing.template_id}/logo?v=${logoVersion}`}
                      alt="Logo"
                      className="max-w-full max-h-full object-contain"
                      data-testid="template-logo-preview"
                    />
                  ) : (
                    <ImageIcon className="w-6 h-6 text-[#9CA3AF]" />
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/svg+xml"
                    ref={logoInputRef}
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadLogo(f);
                      e.target.value = '';
                    }}
                    data-testid="template-logo-input"
                  />
                  <Button
                    size="sm" variant="outline"
                    onClick={() => logoInputRef.current?.click()}
                    data-testid="template-logo-upload"
                    className="rounded-full"
                  >
                    <Upload className="w-3.5 h-3.5 mr-1" />
                    {(editing?.logo_storage_path || pendingLogoUrl) ? 'Ersetzen' : 'Hochladen'}
                  </Button>
                  {(editing?.logo_storage_path || pendingLogoUrl) && (
                    <Button size="sm" variant="ghost" onClick={removeLogo} data-testid="template-logo-remove" className="text-rose-600 text-xs">
                      <X className="w-3 h-3 mr-1" />Entfernen
                    </Button>
                  )}
                  <p className="text-[10px] text-[#9CA3AF]">
                    PNG/JPG/SVG, max 2 MB. Erscheint oben auf der Rechnung.
                    {!editing && pendingLogo && <span className="text-[#4A5D4E] block">Wird beim Speichern hochgeladen.</span>}
                  </p>
                </div>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">Kopfzeile</Label>
                <Select value={form.header_format} onValueChange={(v) => setForm(f => ({ ...f, header_format: v }))}>
                  <SelectTrigger className="h-7 w-32 text-xs" data-testid="template-header-format"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="text">Text</SelectItem>
                    <SelectItem value="markdown">Markdown</SelectItem>
                    <SelectItem value="html">HTML</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-1">
                <Textarea rows={4} value={form.header_text || ''}
                  placeholder={form.header_format === 'markdown' ? '**Fett**, *Kursiv*, [Link](https://…)' : form.header_format === 'html' ? '<b>Fett</b> <font color="#4A5D4E">Akzent</font>' : 'Plain text…'}
                  onChange={(e) => setForm(f => ({ ...f, header_text: e.target.value }))} data-testid="template-header" />
                <div
                  className="rounded-md border border-[#E2E4E0] bg-[#F9FAF7] px-3 py-2 text-xs text-[#6B7280] overflow-auto min-h-[90px] prose-preview"
                  data-testid="template-header-preview"
                  dangerouslySetInnerHTML={{ __html: renderPreview(form.header_text, form.header_format) || '<span style="color:#9CA3AF">Live-Vorschau…</span>' }}
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">Fußzeile</Label>
                <Select value={form.footer_format} onValueChange={(v) => setForm(f => ({ ...f, footer_format: v }))}>
                  <SelectTrigger className="h-7 w-32 text-xs" data-testid="template-footer-format"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="text">Text</SelectItem>
                    <SelectItem value="markdown">Markdown</SelectItem>
                    <SelectItem value="html">HTML</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-1">
                <Textarea rows={4} value={form.footer_text || ''}
                  placeholder={form.footer_format === 'markdown' ? 'Vielen Dank — bei Fragen [mailto](mailto:buchhaltung@…)' : 'Plain text…'}
                  onChange={(e) => setForm(f => ({ ...f, footer_text: e.target.value }))} data-testid="template-footer" />
                <div
                  className="rounded-md border border-[#E2E4E0] bg-[#F9FAF7] px-3 py-2 text-xs text-[#6B7280] overflow-auto min-h-[90px] prose-preview"
                  data-testid="template-footer-preview"
                  dangerouslySetInnerHTML={{ __html: renderPreview(form.footer_text, form.footer_format) || '<span style="color:#9CA3AF">Live-Vorschau…</span>' }}
                />
              </div>
            </div>
            <div><Label className="text-xs">Standard-Zahlungsbedingungen</Label><Textarea rows={2} value={form.payment_terms_default || ''} onChange={(e) => setForm(f => ({ ...f, payment_terms_default: e.target.value }))} data-testid="template-payment-terms" /></div>
            <div><Label className="text-xs">Bankverbindung</Label><Textarea rows={2} value={form.bank_details || ''} onChange={(e) => setForm(f => ({ ...f, bank_details: e.target.value }))} data-testid="template-bank" /></div>
            <div><Label className="text-xs">Std. Absender</Label><Input value={form.sender_org_unit_default || ''} onChange={(e) => setForm(f => ({ ...f, sender_org_unit_default: e.target.value }))} /></div>
            <div>
              <Label className="text-xs">Std. Nummernkreis</Label>
              <Select value={form.default_number_range_id || '_none'} onValueChange={(v) => setForm(f => ({ ...f, default_number_range_id: v === '_none' ? '' : v }))}>
                <SelectTrigger data-testid="template-range"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">— Standard (auto) —</SelectItem>
                  {ranges.map(r => <SelectItem key={r.range_id} value={r.range_id}>{r.name} ({r.pattern})</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-semibold">Pflicht- und sichtbare Felder</Label>
              <div className="text-[10px] text-[#9CA3AF] mb-2">Empfänger, Datum und Positionen sind immer Pflicht.</div>
              <div className="border border-[#E2E4E0] rounded-md divide-y divide-[#F3F4F1]">
                {FIXED_REQUIRED.map(f => (
                  <div key={f.key} className="px-3 py-1.5 text-xs flex items-center justify-between bg-[#F9FAF7]">
                    <span>{f.label}</span>
                    <span className="text-[#9CA3AF]">automatisch</span>
                  </div>
                ))}
                {OPTIONAL_FIELDS.map(f => (
                  <div key={f.key} className="px-3 py-1.5 text-xs grid grid-cols-[1fr_auto_auto] items-center gap-3">
                    <span>{f.label}</span>
                    <div className="flex items-center gap-1">
                      <Switch
                        checked={form.visible_fields.includes(f.key)}
                        onCheckedChange={() => toggleOptional(f.key, 'visible_fields')}
                        data-testid={`template-visible-${f.key}`}
                      />
                      <Label className="text-[10px]">Sichtbar</Label>
                    </div>
                    <div className="flex items-center gap-1">
                      <Switch
                        checked={form.required_fields.includes(f.key)}
                        onCheckedChange={() => toggleOptional(f.key, 'required_fields')}
                        disabled={!form.visible_fields.includes(f.key)}
                        data-testid={`template-required-${f.key}`}
                      />
                      <Label className="text-[10px]">Pflicht</Label>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2"><Switch checked={form.is_default} onCheckedChange={(v) => setForm(f => ({ ...f, is_default: v }))} data-testid="template-default" /><Label className="text-xs">Standard-Vorlage</Label></div>
              <div className="flex items-center gap-2"><Switch checked={form.active} onCheckedChange={(v) => setForm(f => ({ ...f, active: v }))} data-testid="template-active" /><Label className="text-xs">Aktiv</Label></div>
            </div>
          </div>
          <DialogFooter><Button variant="ghost" onClick={() => setEditorOpen(false)}>Abbrechen</Button><Button onClick={save} data-testid="template-save">Speichern</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------- Main Panel with sub-tabs ----------------

export default function InvoiceConfigPanel() {
  const [tab, setTab] = useState('templates');
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-4" data-testid="invoice-config-panel">
      <div className="flex items-center gap-2">
        <FileText className="w-5 h-5 text-[#4A5D4E]" />
        <h3 className="text-sm font-medium text-[#1C1F1D]">Rechnungs-Konfiguration</h3>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <div className="overflow-x-auto -mx-1 px-1">
          <TabsList className="bg-[#F3F4F1] w-max min-w-full">
            <TabsTrigger value="templates" data-testid="config-tab-templates"><FileText className="w-3.5 h-3.5 mr-1" />Vorlagen</TabsTrigger>
            <TabsTrigger value="ranges" data-testid="config-tab-ranges"><Hash className="w-3.5 h-3.5 mr-1" />Nummernkreise</TabsTrigger>
            <TabsTrigger value="master" data-testid="config-tab-master"><Database className="w-3.5 h-3.5 mr-1" />Stammdaten</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="templates"><TemplatesPanel /></TabsContent>
        <TabsContent value="ranges"><NumberRangesPanel /></TabsContent>
        <TabsContent value="master"><MasterDataPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
