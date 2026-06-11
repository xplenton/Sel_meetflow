import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Sparkles, Plus, Edit, Trash2, Lock } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import CapabilitySelector from './CapabilitySelector';
import PresetTooltip from './PresetTooltip';

import { useLanguage } from '../../contexts/LanguageContext';
export default function PresetEditorPanel() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ label: '', description: '', capabilities: [] });

  // Iter 121: React Query for presets list. Mutations invalidate the
  // shared `['admin','presets']` key so GroupsPanel's "apply preset" list +
  // RolesCapsPanel's bulk-preset dropdown refresh together.
  const presetsQ = useQuery({
    queryKey: ['admin', 'presets'],
    queryFn: async () => (await api.get('/admin/presets')).data.presets || [],
  });
  // Iter 375 — capability meta map for the preset tooltip (cap_key → {label, category}).
  const capsQ = useQuery({
    queryKey: ['admin', 'capabilities'],
    queryFn: async () => (await api.get('/admin/capabilities')).data,
  });
  const capsMeta = (capsQ.data?.capabilities || []).reduce((acc, c) => {
    acc[c.key] = { label: c.label, category: c.category };
    return acc;
  }, {});
  const presets = presetsQ.data || [];
  const loading = presetsQ.isLoading;

  const saveMutation = useMutation({
    mutationFn: async ({ editing, data }) =>
      editing ? api.put(`/admin/presets/${editing.preset_id}`, data) : api.post('/admin/presets', data),
    onSuccess: (_r, { editing }) => {
      toast.success(editing ? 'Preset aktualisiert' : 'Preset erstellt');
      qc.invalidateQueries({ queryKey: ['admin', 'presets'] });
      setEditOpen(false);
    },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });
  const deleteMutation = useMutation({
    mutationFn: (preset_id) => api.delete(`/admin/presets/${preset_id}`),
    onSuccess: () => { toast.success('Preset gelöscht'); qc.invalidateQueries({ queryKey: ['admin', 'presets'] }); },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });

  const openCreate = () => {
    setEditing(null);
    setForm({ label: '', description: '', capabilities: [] });
    setEditOpen(true);
  };

  const openEdit = (p) => {
    setEditing(p);
    setForm({ label: p.label, description: p.description || '', capabilities: p.capabilities || [] });
    setEditOpen(true);
  };

  const save = () => {
    if (!form.label.trim()) { toast.error('Label erforderlich'); return; }
    saveMutation.mutate({ editing, data: form });
  };

  const del = (p) => {
    if (!window.confirm(`"${p.label}" wirklich löschen?`)) return;
    deleteMutation.mutate(p.preset_id);
  };

  if (loading) return <div className="text-center py-12 text-[#9CA3AF] text-sm">Laden...</div>;

  const builtin = presets.filter(p => p.builtin);
  const custom = presets.filter(p => !p.builtin);

  return (
    <div className="space-y-6" data-testid="preset-editor-panel">
      <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
        <div className="p-4 border-b border-[#E2E4E0] flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-[#1C1F1D]">Capability-Presets</h3>
            <p className="text-xs text-[#9CA3AF]">{t('predefinedRightsSetsHint')}</p>
          </div>
          <Button onClick={openCreate} size="sm" className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs"
            data-testid="create-preset-btn">
            <Plus className="w-3.5 h-3.5 mr-1" /> Neues Preset
          </Button>
        </div>

        {custom.length > 0 && (
          <div className="p-4 border-b border-[#E2E4E0]">
            <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#4A5D4E] mb-3">{t('customPresets')}</h4>
            <div className="space-y-2">
              {custom.map(p => (
                <PresetTooltip key={p.preset_id} preset={p} capsMeta={capsMeta} side="bottom">
                  <div className="flex items-center gap-3 p-3 bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl"
                    data-testid={`preset-row-${p.preset_id}`}>
                    <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center">
                      <Sparkles className="w-4 h-4 text-[#4A5D4E]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-[#1C1F1D]">{p.label}</div>
                      {p.description && <div className="text-xs text-[#9CA3AF]">{p.description}</div>}
                      <div className="text-[10px] text-[#6B7280] mt-0.5">{p.capabilities?.length || 0} Rechte — Mauszeiger drüber für Details</div>
                    </div>
                    <button onClick={(e) => { e.stopPropagation(); openEdit(p); }} className="p-1.5 rounded-lg hover:bg-[#E8EAE6] text-[#9CA3AF] hover:text-[#4A5D4E]"
                      data-testid={`edit-preset-${p.preset_id}`}><Edit className="w-4 h-4" /></button>
                    <button onClick={(e) => { e.stopPropagation(); del(p); }} className="p-1.5 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]"
                      data-testid={`delete-preset-${p.preset_id}`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                </PresetTooltip>
              ))}
            </div>
          </div>
        )}

        <div className="p-4">
          <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#9CA3AF] mb-3">Built-in Presets</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {builtin.map(p => (
              <PresetTooltip key={p.preset_id} preset={p} capsMeta={capsMeta} side="bottom">
                <div className="flex items-center gap-3 p-3 bg-[#F3F4F1] rounded-xl cursor-help hover:bg-[#EEF0EB] transition-colors"
                  data-testid={`builtin-preset-${p.preset_id}`}>
                  <Lock className="w-3.5 h-3.5 text-[#9CA3AF] flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-[#1C1F1D]">{p.label}</div>
                    <div className="text-[10px] text-[#9CA3AF]">{p.capabilities?.length || 0} Rechte — Mauszeiger drüber für Details</div>
                  </div>
                  <Badge className="text-[9px] bg-[#9CA3AF]/10 text-[#6B7280]">System</Badge>
                </div>
              </PresetTooltip>
            ))}
          </div>
        </div>
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-[520px] max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing ? `Preset: ${editing.label}` : 'Neues Preset'}</DialogTitle></DialogHeader>
          <div className="space-y-4 pt-2">
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-[#6B7280] block mb-1">Label *</label>
              <Input value={form.label} onChange={e => setForm(prev => ({ ...prev, label: e.target.value }))}
                placeholder="z.B. Stations-Leitung" className="border-[#E2E4E0] rounded-xl"
                data-testid="preset-label-input" />
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-[#6B7280] block mb-1">Beschreibung</label>
              <Input value={form.description} onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Kurze Beschreibung" className="border-[#E2E4E0] rounded-xl" />
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-[#6B7280] block mb-1.5">Rechte</label>
              <CapabilitySelector
                selected={form.capabilities}
                onChange={caps => setForm(prev => ({ ...prev, capabilities: caps }))}
                testId="preset-cap-selector"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)} className="rounded-full border-[#E2E4E0]">Abbrechen</Button>
            <Button onClick={save} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full"
              data-testid="save-preset-btn">Speichern</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
