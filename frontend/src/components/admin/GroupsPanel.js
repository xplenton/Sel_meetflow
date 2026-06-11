import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Building2, Edit, Trash2, Plus, UserPlus, X, Sparkles } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import CapabilitySelector from './CapabilitySelector';

import { useLanguage } from '../../contexts/LanguageContext';
const ALL_MODULES = [
  { key: 'dashboard', label: 'Dashboard', icon: '🏠' },
  { key: 'news', label: 'News & Mitteilungen', icon: '📰' },
  { key: 'surveys', label: 'Umfragen', icon: '📋' },
  { key: 'tasks', label: 'Aufgaben', icon: '✅' },
  { key: 'resources', label: 'Ressourcen', icon: '🏢' },
  { key: 'meetings', label: 'Webkonferenz', icon: '🎥' },
  { key: 'scheduling', label: 'Terminplanung', icon: '📅' },
  { key: 'chat', label: 'Chat', icon: '💬' },
  { key: 'calendar', label: 'Kalender', icon: '📆' },
  { key: 'recordings', label: 'Aufnahmen', icon: '⏺' },
  { key: 'profile', label: 'Profil', icon: '👤' },
  { key: 'admin', label: 'Verwaltung', icon: '⚙' },
  { key: 'analytics', label: 'Auswertungen', icon: '📊' },
];

const COLORS = ['#4A5D4E', '#6B8E23', '#C87967', '#D4A373', '#4B5563', '#7C3AED'];

export default function GroupsPanel({ users }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editGroup, setEditGroup] = useState(null);
  const [form, setForm] = useState({ name: '', description: '', color: '#4A5D4E', members: [], permissions: [], capabilities: [], role_override: '' });
  const [addMemberOpen, setAddMemberOpen] = useState(null);

  // React Query owns groups + presets lists (iter 118). Mutations invalidate
  // the shared `['admin','groups']` key so AdminPage's sidebar count + any
  // other consumer re-renders in sync.
  const groupsQ = useQuery({
    queryKey: ['admin', 'groups'],
    queryFn: async () => (await api.get('/admin/groups')).data,
  });
  const presetsQ = useQuery({
    queryKey: ['admin', 'presets'],
    queryFn: async () => (await api.get('/admin/presets')).data.presets || [],
    staleTime: 5 * 60_000,
  });
  // iter 305 — needed for the "fully redundant module caps" save-warning.
  const capsMetaQ = useQuery({
    queryKey: ['admin', 'capabilities-meta'],
    queryFn: async () => (await api.get('/admin/capabilities')).data,
    staleTime: 10 * 60_000,
  });
  const groups = groupsQ.data || [];
  const presets = presetsQ.data || [];
  const allCapsMeta = capsMetaQ.data?.capabilities || [];
  const roleDefaultsMap = capsMetaQ.data?.role_defaults || {};
  const loading = groupsQ.isLoading;

  const invalidateGroups = () => qc.invalidateQueries({ queryKey: ['admin', 'groups'] });

  const saveMutation = useMutation({
    mutationFn: async ({ editing, data }) =>
      editing
        ? api.put(`/admin/groups/${editing.group_id}`, {
            name: data.name, description: data.description, color: data.color,
            permissions: data.permissions, capabilities: data.capabilities,
          })
        : api.post('/admin/groups', data),
    onSuccess: (_r, { editing }) => { toast.success(editing ? 'Gruppe aktualisiert' : 'Gruppe erstellt'); invalidateGroups(); setDialogOpen(false); },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });
  const deleteMutation = useMutation({
    mutationFn: (group_id) => api.delete(`/admin/groups/${group_id}`),
    onSuccess: () => { toast.success('Gruppe gelöscht'); invalidateGroups(); },
    onError: () => toast.error('Fehler'),
  });
  const addMemberMutation = useMutation({
    mutationFn: ({ group_id, user_id }) => api.post(`/admin/groups/${group_id}/members`, { user_id }),
    onSuccess: () => { toast.success('Mitglied hinzugefuegt'); invalidateGroups(); },
    onError: () => toast.error('Fehler'),
  });
  const removeMemberMutation = useMutation({
    mutationFn: ({ group_id, user_id }) => api.delete(`/admin/groups/${group_id}/members/${user_id}`),
    onSuccess: () => { toast.success('Mitglied entfernt'); invalidateGroups(); },
    onError: () => toast.error('Fehler'),
  });
  const applyPresetMutation = useMutation({
    mutationFn: ({ preset_id, group_id }) => api.post(`/admin/presets/${preset_id}/apply-to-group/${group_id}`),
    onSuccess: ({ data }) => { toast.success(`Preset angewendet: ${data.applied.length} Rechte hinzugefuegt`); invalidateGroups(); },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler'),
  });

  const openCreate = () => {
    setEditGroup(null);
    setForm({ name: '', description: '', color: '#4A5D4E', members: [],
      permissions: ['dashboard', 'news', 'scheduling', 'chat', 'calendar', 'recordings', 'profile'],
      capabilities: [], role_override: '' });
    setDialogOpen(true);
  };

  const openEdit = (g) => {
    setEditGroup(g);
    setForm({
      name: g.name, description: g.description || '', color: g.color || '#4A5D4E', members: g.members || [],
      permissions: g.permissions || ['dashboard', 'news', 'scheduling', 'chat', 'calendar', 'recordings', 'profile'],
      capabilities: g.capabilities || [],
      role_override: g.role_override || '',
    });
    setDialogOpen(true);
  };

  const handleSave = () => {
    if (!form.name.trim()) { toast.error('Name erforderlich'); return; }

    // iter 305 — Warn admins when "view:*" caps in this group are already
    // covered by ALL roles' defaults. Such grants change nothing → most
    // likely an accidental click. Soft confirm rather than blocking.
    const moduleCaps = (form.capabilities || []).filter(c => c.startsWith('view:'));
    if (moduleCaps.length > 0 && allCapsMeta.length > 0) {
      const roleDefaultsAll = roleDefaultsMap; // computed below in useMemo
      const allRoles = Object.keys(roleDefaultsAll);
      const fullyRedundant = moduleCaps.filter(cap =>
        allRoles.length > 0 && allRoles.every(r => (roleDefaultsAll[r] || []).includes(cap))
      );
      if (fullyRedundant.length > 0) {
        const ok = window.confirm(
          `Hinweis: ${fullyRedundant.length} von ${moduleCaps.length} Modul-Rechten sind bereits durch alle Rollen abgedeckt — diese Gruppen-Einstellung ändert effektiv nichts.\n\n` +
          `Betroffen: ${fullyRedundant.join(', ')}\n\n` +
          `Trotzdem speichern?`
        );
        if (!ok) return;
      }
    }

    saveMutation.mutate({ editing: editGroup, data: form });
  };

  const applyPresetToGroup = (presetId, groupId) => applyPresetMutation.mutate({ preset_id: presetId, group_id: groupId });

  const handleDelete = (g) => {
    if (!window.confirm(`"${g.name}" wirklich löschen?`)) return;
    deleteMutation.mutate(g.group_id);
  };

  const addMember = (groupId, userId) => addMemberMutation.mutate({ group_id: groupId, user_id: userId });
  const removeMember = (groupId, userId) => removeMemberMutation.mutate({ group_id: groupId, user_id: userId });

  const getUserName = (uid) => {
    const u = users.find(u => u.user_id === uid);
    return u ? u.name : uid;
  };

  if (loading) return <div className="text-center py-8 text-[#9CA3AF]">Laden...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[#6B7280]">{groups.length} Gruppen</p>
        <Button onClick={openCreate} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs" data-testid="create-group-btn">
          <Plus className="w-3.5 h-3.5 mr-1" /> Neue Gruppe
        </Button>
      </div>

      {groups.length === 0 ? (
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 text-center">
          <Building2 className="w-10 h-10 text-[#E2E4E0] mx-auto mb-3" />
          <p className="text-sm text-[#9CA3AF] mb-3">{t('noGroupsYet')}</p>
          <Button onClick={openCreate} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs">
            <Plus className="w-3.5 h-3.5 mr-1" /> Erste Gruppe erstellen
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map(g => (
            <div key={g.group_id} className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid={`group-${g.group_id}`}>
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{ backgroundColor: g.color || '#4A5D4E' }}>
                    {g.name?.[0]?.toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <h3 className="text-sm font-medium text-[#1C1F1D]">{g.name}</h3>
                      {g.module_group && (
                        <span className="text-[8px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#7C3AED]/10 text-[#7C3AED] font-medium"
                          title="System-Modul-Gruppe — Mitgliedschaft wird automatisch über die Rolle gepflegt. Modul-Rechte sind editierbar und bleiben dauerhaft erhalten (auch nach Backend-Restart, ab Iter 384)."
                          data-testid={`group-system-badge-${g.group_id}`}>
                          SYSTEM
                        </span>
                      )}
                    </div>
                    {g.description && <p className="text-xs text-[#9CA3AF]">{g.description}</p>}
                    <span className="text-[10px] text-[#6B7280]">{(g.members || []).length} Mitglieder</span>
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {(g.permissions || []).map(p => {
                        const mod = ALL_MODULES.find(m => m.key === p);
                        return mod ? <span key={p} className="text-[9px] px-1.5 py-0.5 bg-[#F3F4F1] rounded text-[#6B7280]">{mod.label}</span> : null;
                      })}
                      {(g.capabilities || []).length > 0 && (
                        <span className="text-[9px] px-1.5 py-0.5 bg-[#4A5D4E]/10 text-[#4A5D4E] rounded font-medium"
                          data-testid={`group-caps-count-${g.group_id}`}>
                          +{(g.capabilities || []).length} Rechte
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex gap-1">
                  <button onClick={() => openEdit(g)} className="p-1.5 rounded-lg hover:bg-[#E8EAE6] text-[#9CA3AF] hover:text-[#4A5D4E]" data-testid={`edit-group-${g.group_id}`}>
                    <Edit className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(g)}
                    disabled={!!(g.module_group || g.is_system)}
                    title={g.module_group || g.is_system ? 'System-Gruppe — nicht löschbar' : 'Gruppe löschen'}
                    className={`p-1.5 rounded-lg ${g.module_group || g.is_system ? 'text-[#E2E4E0] cursor-not-allowed' : 'hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]'}`}
                    data-testid={`delete-group-${g.group_id}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {/* Members */}
              <div className="flex flex-wrap gap-1.5 mb-2">
                {(g.members || []).map(mid => (
                  <span key={mid} className="inline-flex items-center gap-1 px-2 py-1 bg-[#F3F4F1] rounded-full text-[11px] text-[#4B5563]">
                    {getUserName(mid)}
                    <button onClick={() => removeMember(g.group_id, mid)} className="text-[#9CA3AF] hover:text-[#C87967]"><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
              {/* Add member */}
              {addMemberOpen === g.group_id ? (
                <div className="flex items-center gap-2">
                  <Select onValueChange={(uid) => { addMember(g.group_id, uid); setAddMemberOpen(null); }}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg text-xs h-8 flex-1"><SelectValue placeholder={t('chooseMember')} /></SelectTrigger>
                    <SelectContent>
                      {users.filter(u => !(g.members || []).includes(u.user_id)).map(u => (
                        <SelectItem key={u.user_id} value={u.user_id} className="text-xs">{u.name} ({u.email})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <button onClick={() => setAddMemberOpen(null)} className="text-[#9CA3AF] hover:text-[#C87967]"><X className="w-4 h-4" /></button>
                </div>
              ) : (
                <button onClick={() => setAddMemberOpen(g.group_id)}
                  className="text-[10px] text-[#4A5D4E] hover:text-[#3E4E42] font-medium flex items-center gap-1" data-testid={`add-member-${g.group_id}`}>
                  <UserPlus className="w-3 h-3" /> Mitglied hinzufügen
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[520px] max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editGroup ? 'Gruppe bearbeiten' : 'Neue Gruppe'}</DialogTitle></DialogHeader>
          <div className="space-y-4 pt-2">
            {/* Iter 384 — Hinweis-Banner für System-Modul-Gruppen, damit Admins
                wissen, dass Module-Rechte (z.B. view:news) angepasst werden
                können und der Edit dauerhaft persistiert. Frühere Anwender
                wunderten sich, warum Änderungen scheinbar zurückgesetzt wurden
                — das war der Re-Seed beim Backend-Boot, jetzt gefixt. */}
            {editGroup?.module_group && (
              <div className="rounded-lg border border-[#7C3AED]/30 bg-[#7C3AED]/5 px-3 py-2.5 text-xs text-[#4B3F77] flex gap-2"
                data-testid="system-module-group-info-banner">
                <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#7C3AED]/15 text-[#7C3AED] font-bold flex-shrink-0 self-start">
                  SYSTEM
                </span>
                <div className="space-y-1">
                  <p className="font-medium text-[#1C1F1D]">
                    Diese Gruppe ist systemverwaltet
                  </p>
                  <p className="text-[#4B3F77]/90 leading-snug">
                    Mitgliedschaft wird automatisch über die Benutzer-Rolle gepflegt
                    (Mitarbeiter → „Modul: Standard“, Admin → zusätzlich „Modul: Verwaltung“ usw.).
                    Modul-Rechte (z.B. <span className="font-mono text-[11px]">view:news</span>) kannst
                    du anpassen — Änderungen bleiben dauerhaft erhalten, auch nach Backend-Restart.
                  </p>
                </div>
              </div>
            )}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Name</Label>
              <Input value={form.name} onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="z.B. Entwicklung, Marketing" className="border-[#E2E4E0] rounded-xl" data-testid="group-name-input" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Beschreibung</Label>
              <Input value={form.description} onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder={t('optionalDescription')} className="border-[#E2E4E0] rounded-xl" />
            </div>
            {/* Iter 289 — Role-Override für diese Gruppe */}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                System-Rolle erzwingen (optional)
              </Label>
              <select
                value={form.role_override || ''}
                onChange={e => setForm(prev => ({ ...prev, role_override: e.target.value }))}
                className="w-full h-10 border border-[#E2E4E0] rounded-xl px-3 text-sm bg-white"
                data-testid="group-role-override-select"
              >
                <option value="">(keine — Mitglied behält eigene Rolle)</option>
                <option value="guest">Gast (überschreibt höhere Rollen)</option>
                <option value="member">Mitarbeiter</option>
                <option value="moderator">Moderator</option>
              </select>
              <p className="text-[10px] text-[#9CA3AF] mt-1">
                Wenn gesetzt, wird die System-Rolle eines Mitglieds auf diese Rolle reduziert.
                Bsp.: Gruppe „Gast“ mit Override „Gast“ sorgt dafür, dass alle Mitglieder nur Gast-Rechte sehen,
                auch wenn ihre Benutzer-Rolle „Mitarbeiter“ ist.
              </p>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Farbe</Label>
              <div className="flex gap-2">
                {COLORS.map(c => (
                  <button key={c} onClick={() => setForm(prev => ({ ...prev, color: c }))}
                    className={`w-8 h-8 rounded-lg transition-all ${form.color === c ? 'ring-2 ring-offset-2 ring-[#4A5D4E]' : ''}`}
                    style={{ backgroundColor: c }} />
                ))}
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-2 block">{t('visibleModules')}</Label>
              <div className="space-y-1.5">
                {ALL_MODULES.map(mod => (
                  <label key={mod.key} className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-[#F3F4F1] cursor-pointer">
                    <input type="checkbox" checked={(form.permissions || []).includes(mod.key)}
                      onChange={e => {
                        setForm(prev => ({
                          ...prev,
                          permissions: e.target.checked
                            ? [...(prev.permissions || []), mod.key]
                            : (prev.permissions || []).filter(p => p !== mod.key),
                        }));
                      }}
                      className="w-4 h-4 rounded border-[#E2E4E0] text-[#4A5D4E] focus:ring-[#4A5D4E]" />
                    <span className="text-sm text-[#1C1F1D]">{mod.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] block">Zusaetzliche Rechte (Capabilities)</Label>
                {presets.length > 0 && (
                  <Select onValueChange={(pid) => {
                    const p = presets.find(x => x.preset_id === pid);
                    if (!p) return;
                    const merged = Array.from(new Set([...(form.capabilities || []), ...p.capabilities]));
                    setForm(prev => ({ ...prev, capabilities: merged }));
                    toast.success(`${p.label} angewendet (+${p.capabilities.length} Rechte)`);
                  }}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-lg h-8 text-xs w-[180px]" data-testid="apply-preset-select">
                      <div className="flex items-center gap-1.5 text-[#4A5D4E]">
                        <Sparkles className="w-3 h-3" /> Preset anwenden
                      </div>
                    </SelectTrigger>
                    <SelectContent className="max-w-[420px]">
                      {presets.map(p => (
                        <SelectItem key={p.preset_id} value={p.preset_id} className="text-xs">
                          <div className="flex flex-col gap-0.5">
                            <div className="font-medium">{p.label} <span className="text-[#9CA3AF]">(+{p.capabilities.length})</span></div>
                            {p.description && (
                              <div className="text-[10px] text-[#6B7280] whitespace-normal leading-tight">{p.description}</div>
                            )}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <CapabilitySelector
                selected={form.capabilities || []}
                onChange={caps => setForm(prev => ({ ...prev, capabilities: caps }))}
                testId="group-cap-selector"
                excludeGroupId={editGroup?.group_id}
              />
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)} className="rounded-lg">Abbrechen</Button>
              <Button onClick={handleSave} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg" data-testid="save-group-btn">
                {editGroup ? 'Speichern' : 'Erstellen'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
