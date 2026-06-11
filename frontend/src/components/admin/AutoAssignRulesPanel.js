import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useLanguage } from '../../contexts/LanguageContext';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Switch } from '../ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Zap, Plus, Edit, Trash2, Play, Info } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

const ROLES = [
  { value: '', label: 'Alle Rollen' },
  { value: 'admin', label: 'Administrator' },
  { value: 'moderator', label: 'Moderator' },
  { value: 'member', label: 'Mitarbeiter' },
  { value: 'guest', label: 'Gast' },
];

export default function AutoAssignRulesPanel() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({
    name: '', description: '', enabled: true,
    when: { department: '', location: '', profession: '', role: '' },
    apply: { preset_id: '', caps: [] },
  });
  const [running, setRunning] = useState(false);

  // Iter 121: React Query owns rules + presets. Save/delete/run mutations
  // auto-invalidate so the list is always in sync after any action.
  const rulesQ = useQuery({
    queryKey: ['admin', 'cap-rules'],
    queryFn: async () => (await api.get('/admin/cap-rules')).data.rules || [],
  });
  const presetsQ = useQuery({
    queryKey: ['admin', 'presets'],
    queryFn: async () => (await api.get('/admin/presets')).data.presets || [],
  });
  const rules = rulesQ.data || [];
  const presets = presetsQ.data || [];
  const loading = rulesQ.isLoading || presetsQ.isLoading;
  const invalidateRules = () => qc.invalidateQueries({ queryKey: ['admin', 'cap-rules'] });

  const saveMutation = useMutation({
    mutationFn: async ({ editing, data }) =>
      editing ? api.put(`/admin/cap-rules/${editing.rule_id}`, data) : api.post('/admin/cap-rules', data),
    onSuccess: (_r, { editing }) => {
      toast.success(editing ? 'Regel aktualisiert' : 'Regel erstellt');
      invalidateRules();
      setEditOpen(false);
    },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });
  const deleteMutation = useMutation({
    mutationFn: (rule_id) => api.delete(`/admin/cap-rules/${rule_id}`),
    onSuccess: () => { toast.success('Regel gelöscht'); invalidateRules(); },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });
  const runMutation = useMutation({
    mutationFn: (rule_id) => api.post('/admin/cap-rules/run', rule_id ? { rule_id } : {}),
    onMutate: () => setRunning(true),
    onSettled: () => setRunning(false),
    onSuccess: ({ data }) => {
      toast.success(`Regel(n) ausgefuehrt: ${data.users_affected} Nutzer aktualisiert`);
      invalidateRules();
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ name: '', description: '', enabled: true,
      when: { department: '', location: '', profession: '', role: '' },
      apply: { preset_id: '', caps: [] } });
    setEditOpen(true);
  };

  const openEdit = (r) => {
    setEditing(r);
    setForm({
      name: r.name, description: r.description || '', enabled: !!r.enabled,
      when: { ...r.when },
      apply: { preset_id: r.apply?.preset_id || '', caps: r.apply?.caps || [] },
    });
    setEditOpen(true);
  };

  const save = () => {
    if (!form.name.trim()) { toast.error('Name erforderlich'); return; }
    if (!form.apply.preset_id && (!form.apply.caps || form.apply.caps.length === 0)) {
      toast.error('Preset oder Rechte erforderlich'); return;
    }
    saveMutation.mutate({ editing, data: form });
  };

  const del = (r) => {
    if (!window.confirm(`"${r.name}" wirklich löschen?`)) return;
    deleteMutation.mutate(r.rule_id);
  };

  const runAll = (rule_id) => runMutation.mutate(rule_id);

  if (loading) return <div className="text-center py-12 text-[#9CA3AF] text-sm">{t('loading')}</div>;

  return (
    <div className="space-y-4" data-testid="auto-rules-panel">
      <div className="bg-[#D4A373]/5 border border-[#D4A373]/30 rounded-xl p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-[#D4A373] flex-shrink-0 mt-0.5" />
        <div className="flex-1 text-sm text-[#1C1F1D]">
          <p className="font-medium">Automatische Rechte-Zuweisung</p>
          <p className="text-xs text-[#6B7280]">Definiere Regeln nach Abteilung, Standort, Berufsgruppe oder Rolle. Passende Nutzer erhalten das Preset oder Rechte-Set automatisch (idempotent — merged).</p>
        </div>
        <Button onClick={() => runAll(null)} disabled={running} size="sm" variant="outline"
          className="rounded-full text-xs border-[#D4A373]/40 text-[#D4A373]"
          data-testid="run-all-rules-btn">
          <Play className={`w-3 h-3 mr-1 ${running ? 'animate-pulse' : ''}`} />
          {running ? 'Laeuft...' : 'Alle Regeln ausführen'}
        </Button>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-[#6B7280]">{rules.length} Regeln</p>
        <Button onClick={openCreate} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs"
          data-testid="create-rule-btn">
          <Plus className="w-3.5 h-3.5 mr-1" /> Neue Regel
        </Button>
      </div>

      {rules.length === 0 ? (
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 text-center">
          <Zap className="w-10 h-10 text-[#E2E4E0] mx-auto mb-3" />
          <p className="text-sm text-[#9CA3AF]">{t('noRulesDefinedYet')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {rules.map(r => {
            const preset = presets.find(p => p.preset_id === r.apply?.preset_id);
            const when = r.when || {};
            const conds = [];
            if (when.department) conds.push(`Abteilung: ${when.department}`);
            if (when.location) conds.push(`Standort: ${when.location}`);
            if (when.profession) conds.push(`Beruf: ${when.profession}`);
            if (when.role) conds.push(`Rolle: ${when.role}`);
            return (
              <div key={r.rule_id} className="bg-white border border-[#E2E4E0] rounded-xl p-4"
                data-testid={`rule-${r.rule_id}`}>
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex items-center gap-2">
                    <Zap className={`w-4 h-4 ${r.enabled ? 'text-[#6B8E23]' : 'text-[#9CA3AF]'}`} />
                    <span className="text-sm font-medium text-[#1C1F1D]">{r.name}</span>
                    {!r.enabled && <Badge className="text-[9px] bg-[#9CA3AF]/10 text-[#9CA3AF]">{t('deactivated')}</Badge>}
                  </div>
                  <div className="flex gap-1">
                    <button onClick={() => runAll(r.rule_id)} title="Nur diese Regel ausführen"
                      className="p-1.5 rounded-lg hover:bg-[#D4A373]/10 text-[#9CA3AF] hover:text-[#D4A373]"
                      data-testid={`run-rule-${r.rule_id}`}><Play className="w-3.5 h-3.5" /></button>
                    <button onClick={() => openEdit(r)}
                      className="p-1.5 rounded-lg hover:bg-[#E8EAE6] text-[#9CA3AF] hover:text-[#4A5D4E]"
                      data-testid={`edit-rule-${r.rule_id}`}><Edit className="w-3.5 h-3.5" /></button>
                    <button onClick={() => del(r)}
                      className="p-1.5 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]"
                      data-testid={`delete-rule-${r.rule_id}`}><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
                {r.description && <p className="text-xs text-[#9CA3AF] mb-2">{r.description}</p>}
                <div className="text-xs text-[#6B7280] space-y-0.5">
                  <div><span className="font-medium">Wenn:</span> {conds.length ? conds.join(' · ') : 'Alle Nutzer'}</div>
                  <div><span className="font-medium">Dann:</span> {preset ? `Preset „${preset.label}" (${preset.capabilities?.length || 0} Rechte)` :
                    r.apply?.caps?.length ? `${r.apply.caps.length} Rechte` : '-'}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-[480px] max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing ? 'Regel bearbeiten' : 'Neue Regel'}</DialogTitle></DialogHeader>
          <div className="space-y-3 pt-2">
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-[#6B7280] block mb-1">Name *</label>
              <Input value={form.name} onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="z.B. Kardiologie auto" className="border-[#E2E4E0] rounded-xl" data-testid="rule-name-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-[#6B7280] block mb-1">Beschreibung</label>
              <Input value={form.description} onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                className="border-[#E2E4E0] rounded-xl" />
            </div>
            <div className="flex items-center justify-between">
              <label className="text-sm text-[#1C1F1D]">{t('ruleEnabled')}</label>
              <Switch checked={form.enabled} onCheckedChange={v => setForm(prev => ({ ...prev, enabled: v }))} />
            </div>

            <div className="bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl p-3 space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[#6B7280]">Wenn Nutzer matcht (leer = egal)</p>
              <div className="grid grid-cols-2 gap-2">
                <Input value={form.when.department} onChange={e => setForm(prev => ({ ...prev, when: { ...prev.when, department: e.target.value } }))}
                  placeholder="Abteilung" className="border-[#E2E4E0] rounded-lg h-8 text-xs" data-testid="rule-when-dept" />
                <Input value={form.when.location} onChange={e => setForm(prev => ({ ...prev, when: { ...prev.when, location: e.target.value } }))}
                  placeholder="Standort" className="border-[#E2E4E0] rounded-lg h-8 text-xs" />
                <Input value={form.when.profession} onChange={e => setForm(prev => ({ ...prev, when: { ...prev.when, profession: e.target.value } }))}
                  placeholder={t('profession')} className="border-[#E2E4E0] rounded-lg h-8 text-xs" />
                <Select value={form.when.role || '__any__'} onValueChange={v => setForm(prev => ({ ...prev, when: { ...prev.when, role: v === '__any__' ? '' : v } }))}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-lg h-8 text-xs"><SelectValue placeholder="Rolle" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__any__">{t('allRoles')}</SelectItem>
                    {ROLES.filter(r => r.value).map(r => (<SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="bg-[#4A5D4E]/5 border border-[#4A5D4E]/20 rounded-xl p-3 space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[#4A5D4E]">{t('thenApply')}</p>
              <Select value={form.apply.preset_id || '__none__'} onValueChange={v => setForm(prev => ({ ...prev, apply: { ...prev.apply, preset_id: v === '__none__' ? '' : v } }))}>
                <SelectTrigger className="border-[#E2E4E0] rounded-lg h-9 text-sm" data-testid="rule-preset-select"><SelectValue placeholder="Preset wählen..." /></SelectTrigger>
                <SelectContent className="max-w-[420px]">
                  <SelectItem value="__none__">{t('noPreset')}</SelectItem>
                  {presets.map(p => (
                    <SelectItem key={p.preset_id} value={p.preset_id}>
                      <div className="flex flex-col gap-0.5">
                        <span className="text-xs font-medium">{p.label} <span className="text-[#9CA3AF]">(+{p.capabilities?.length || 0})</span></span>
                        {p.description && (
                          <span className="text-[10px] text-[#6B7280] whitespace-normal leading-tight">{p.description}</span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)} className="rounded-full border-[#E2E4E0]">{t('cancel')}</Button>
            <Button onClick={save} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full"
              data-testid="save-rule-btn">Speichern</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
