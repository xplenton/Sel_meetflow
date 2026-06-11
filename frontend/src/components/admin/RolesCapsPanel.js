import { Fragment, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useLanguage } from '../../contexts/LanguageContext';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Shield, Search, Check, X, Info, RefreshCw, Sparkles, Clock, Beaker } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import PresetTooltip from './PresetTooltip';

const ROLE_LABELS = {
  admin: { label: 'Administrator', color: '#4A5D4E', desc: 'Systemadministrator — volle Rechte' },
  moderator: { label: 'Moderator', color: '#D4A373', desc: 'Redaktion, Freigabe, Moderation' },
  member: { label: 'Mitarbeiter', color: '#6B8E23', desc: 'Standard-Nutzer' },
  guest: { label: 'Gast', color: '#9CA3AF', desc: 'Externer Zugang (sehr eingeschraenkt)' },
};

const CATEGORY_LABELS = {
  module: 'Modul-Sichtbarkeit',
  news: 'News & Kommunikation',
  meetings: 'Meetings',
  chat: 'Chat',
  documents: 'Dokumente & Whiteboard',
  scheduling: 'Terminplanung',
  surveys: 'Umfragen',
  admin: 'Admin',
  global: 'Global',
};

function fmtDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString('de-DE'); } catch { return iso; }
}

export default function RolesCapsPanel() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [userSearch, setUserSearch] = useState('');
  const [editUser, setEditUser] = useState(null);
  const [userCaps, setUserCaps] = useState({ grants: [], denies: [], expires: {} });
  const [migrating, setMigrating] = useState(false);
  const [simulateUser, setSimulateUser] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [selectedUsers, setSelectedUsers] = useState(new Set());
  const [bulkPreset, setBulkPreset] = useState('');

  // Iter 121: React Query owns the three admin-capability lists. Mutations
  // elsewhere (grant / revoke / preset-apply / migration) call
  // `qc.invalidateQueries(['admin','capabilities'])` etc. to force a refetch.
  const capsQ = useQuery({ queryKey: ['admin', 'capabilities'], queryFn: async () => (await api.get('/admin/capabilities')).data });
  const usersQ = useQuery({ queryKey: ['admin', 'users-all'], queryFn: async () => (await api.get('/admin/users')).data });
  const presetsQ = useQuery({
    queryKey: ['admin', 'presets'],
    queryFn: async () => (await api.get('/admin/presets').catch(() => ({ data: { presets: [] } }))).data.presets || [],
  });
  const capsData = capsQ.data;
  const users = usersQ.data || [];
  const presets = presetsQ.data || [];
  const loading = capsQ.isLoading || usersQ.isLoading;

  const load = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'capabilities'] });
    qc.invalidateQueries({ queryKey: ['admin', 'users-all'] });
    qc.invalidateQueries({ queryKey: ['admin', 'presets'] });
  };

  const runMigration = async () => {
    setMigrating(true);
    try {
      const { data } = await api.post('/admin/migrate-roles');
      toast.success(`Migration erfolgreich: ${data.migrated} Nutzer aktualisiert, ${data.unchanged} unveraendert`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
    finally { setMigrating(false); }
  };

  const openUser = (u) => {
    setEditUser(u);
    setUserCaps({
      grants: u.cap_grants || [],
      denies: u.cap_denies || [],
      expires: u.cap_expires || {},
    });
  };

  const toggleCap = (list, cap) => {
    setUserCaps(prev => ({
      ...prev,
      [list]: prev[list].includes(cap) ? prev[list].filter(c => c !== cap) : [...prev[list], cap],
    }));
  };

  const setExpires = (cap, isoDate) => {
    setUserCaps(prev => {
      const exp = { ...prev.expires };
      if (isoDate) exp[cap] = new Date(isoDate).toISOString();
      else delete exp[cap];
      return { ...prev, expires: exp };
    });
  };

  const applyPresetToUser = (p) => {
    const merged = Array.from(new Set([...(userCaps.grants || []), ...p.capabilities]));
    setUserCaps(prev => ({ ...prev, grants: merged }));
    toast.success(`${p.label} angewendet (+${p.capabilities.length})`);
  };

  const saveUserCaps = async () => {
    if (!editUser) return;
    try {
      await api.put(`/admin/users/${editUser.user_id}/capabilities`, userCaps);
      toast.success('Rechte gespeichert');
      setEditUser(null);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  const runSimulation = async (u) => {
    setSimulateUser(u);
    setSimulation(null);
    try {
      const { data } = await api.get(`/admin/users/${u.user_id}/simulate`);
      setSimulation(data);
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  const toggleUserSelection = (uid) => {
    setSelectedUsers(prev => {
      const s = new Set(prev);
      if (s.has(uid)) s.delete(uid); else s.add(uid);
      return s;
    });
  };

  const bulkApply = async () => {
    if (!bulkPreset || selectedUsers.size === 0) {
      toast.error('Preset wählen und mindestens einen Nutzer markieren');
      return;
    }
    try {
      const { data } = await api.post(`/admin/presets/${bulkPreset}/apply-to-users`, {
        user_ids: Array.from(selectedUsers),
      });
      toast.success(`Preset auf ${data.updated} Nutzer angewendet`);
      setSelectedUsers(new Set());
      setBulkPreset('');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  if (loading) return <div className="text-center py-12 text-[#9CA3AF] text-sm">{t('loading')}</div>;
  if (!capsData) return null;

  const capsByCategory = capsData.capabilities.reduce((acc, c) => {
    (acc[c.category] = acc[c.category] || []).push(c);
    return acc;
  }, {});

  // Iter 375 — Lookup-Map cap_key → {label, category} für die Preset-Tooltips.
  const capsMeta = capsData.capabilities.reduce((acc, c) => {
    acc[c.key] = { label: c.label, category: c.category };
    return acc;
  }, {});

  const filteredUsers = users.filter(u =>
    !userSearch || u.name?.toLowerCase().includes(userSearch.toLowerCase())
    || u.email?.toLowerCase().includes(userSearch.toLowerCase())
  );

  return (
    <div className="space-y-6" data-testid="roles-caps-panel">
      {/* Intro + Migration */}
      <div className="bg-[#4A5D4E]/5 border border-[#4A5D4E]/20 rounded-xl p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-[#4A5D4E] flex-shrink-0 mt-0.5" />
        <div className="flex-1 text-sm text-[#1C1F1D]">
          <p className="font-medium mb-1">Capability-basiertes Rechtesystem</p>
          <p className="text-xs text-[#6B7280]">
            4 System-Rollen (<strong>{t('adminModeratorEmployeeGuest')}</strong>) mit vordefinierten Rechte-Sets.
            Pro Nutzer können zusaetzliche Rechte gewaehrt oder entzogen werden (Overrides).
            Gruppen können zusaetzliche Rechte beisteuern.
          </p>
        </div>
        <Button onClick={runMigration} disabled={migrating} size="sm" variant="outline"
          className="rounded-full text-xs border-[#4A5D4E]/20 text-[#4A5D4E]"
          data-testid="run-migration-btn">
          <RefreshCw className={`w-3 h-3 mr-1 ${migrating ? 'animate-spin' : ''}`} />
          {migrating ? 'Migriere...' : 'Legacy-Rollen migrieren'}
        </Button>
      </div>

      {/* Rollen-Matrix */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
        <div className="p-4 border-b border-[#E2E4E0]">
          <h3 className="text-sm font-semibold text-[#1C1F1D]">{t('rolePermissionsMatrix')}</h3>
          <p className="text-xs text-[#9CA3AF] mt-0.5">Welche Rolle hat welche Rechte? (nur Anzeige — Rollen-Defaults sind im Code definiert)</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-[#F3F4F1]">
              <tr>
                <th className="text-left p-3 font-bold text-[#6B7280] uppercase tracking-wider text-[10px]">Berechtigung</th>
                {Object.entries(ROLE_LABELS).map(([k, r]) => (
                  <th key={k} className="text-center p-3 min-w-[110px]">
                    <div className="flex flex-col items-center gap-1">
                      <Shield className="w-4 h-4" style={{ color: r.color }} />
                      <span className="font-semibold text-[#1C1F1D]">{r.label}</span>
                      <span className="text-[9px] text-[#9CA3AF]">{r.desc}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(capsByCategory).map(([cat, caps]) => (
                <Fragment key={cat}>
                  <tr className="bg-[#F9F9F8]">
                    <td colSpan={5} className="px-3 py-2 font-bold text-[10px] uppercase tracking-wider text-[#4A5D4E]">
                      {CATEGORY_LABELS[cat] || cat}
                    </td>
                  </tr>
                  {caps.map(c => (
                    <tr key={c.key} className="border-t border-[#E2E4E0]" data-testid={`cap-row-${c.key}`}>
                      <td className="p-3">
                        <div className="text-sm text-[#1C1F1D]">{c.label}</div>
                        <div className="text-[10px] text-[#9CA3AF]">{c.description}</div>
                        <code className="text-[9px] text-[#6B7280]">{c.key}</code>
                      </td>
                      {Object.keys(ROLE_LABELS).map(r => {
                        const has = (capsData.role_defaults[r] || []).includes(c.key);
                        return (
                          <td key={r} className="text-center p-3">
                            {has
                              ? <Check className="w-4 h-4 text-[#6B8E23] mx-auto" data-testid={`cap-${c.key}-${r}-has`} />
                              : <X className="w-4 h-4 text-[#E2E4E0] mx-auto" />
                            }
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Per-User Overrides */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
        <div className="p-4 border-b border-[#E2E4E0] flex items-center gap-3 flex-wrap">
          <div>
            <h3 className="text-sm font-semibold text-[#1C1F1D]">Individuelle Rechte-Overrides</h3>
            <p className="text-xs text-[#9CA3AF] mt-0.5">{t('grantRevokeOrBulkApply')}</p>
          </div>
          <div className="flex-1" />
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
            <Input value={userSearch} onChange={e => setUserSearch(e.target.value)}
              placeholder="Nutzer suchen..." className="pl-9 h-9 text-sm border-[#E2E4E0] rounded-lg"
              data-testid="user-caps-search" />
          </div>
        </div>

        {/* Bulk-apply bar */}
        {selectedUsers.size > 0 && (
          <div className="p-3 bg-[#4A5D4E]/5 border-b border-[#4A5D4E]/20 flex items-center gap-2 flex-wrap"
            data-testid="bulk-bar">
            <Badge className="bg-[#4A5D4E] text-white text-[10px]" data-testid="bulk-selected-count">
              {selectedUsers.size} Nutzer ausgewählt
            </Badge>
            <button onClick={() => setSelectedUsers(new Set())}
              className="text-[10px] text-[#6B7280] hover:text-[#C87967]">{t('clearSelection')}</button>
            <div className="flex-1" />
            <Select value={bulkPreset} onValueChange={setBulkPreset}>
              <SelectTrigger className="w-[260px] h-8 text-xs border-[#E2E4E0] rounded-lg"
                data-testid="bulk-preset-select"><SelectValue placeholder="Preset wählen..." /></SelectTrigger>
              <SelectContent className="max-w-[420px]">
                {presets.map(p => (
                  <SelectItem key={p.preset_id} value={p.preset_id}>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-xs font-medium">{p.label} <span className="text-[#9CA3AF]">(+{p.capabilities?.length || 0})</span></span>
                      {p.description && (
                        <span className="text-[10px] text-[#6B7280] leading-tight whitespace-normal">{p.description}</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={bulkApply} disabled={!bulkPreset} size="sm"
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs"
              data-testid="bulk-apply-btn">
              Anwenden
            </Button>
          </div>
        )}

        <div className="divide-y divide-[#E2E4E0] max-h-[400px] overflow-y-auto">
          {filteredUsers.slice(0, 50).map(u => {
            const role = u.role || 'member';
            const roleCfg = ROLE_LABELS[role] || ROLE_LABELS.member;
            const grantCount = (u.cap_grants || []).length;
            const denyCount = (u.cap_denies || []).length;
            const isSelected = selectedUsers.has(u.user_id);
            return (
              <div key={u.user_id} className={`flex items-center gap-3 p-3 hover:bg-[#F3F4F1] ${isSelected ? 'bg-[#4A5D4E]/5' : ''}`}
                data-testid={`user-caps-row-${u.user_id}`}>
                <input type="checkbox" checked={isSelected} onChange={() => toggleUserSelection(u.user_id)}
                  className="w-4 h-4 rounded border-[#E2E4E0] text-[#4A5D4E] focus:ring-[#4A5D4E] flex-shrink-0"
                  data-testid={`select-user-${u.user_id}`} />
                <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs text-[#4A5D4E] font-medium flex-shrink-0">
                  {u.name?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[#1C1F1D] truncate">{u.name}</p>
                  <p className="text-[10px] text-[#9CA3AF]">{u.email}</p>
                </div>
                <Badge className="text-[10px] flex-shrink-0" style={{ backgroundColor: `${roleCfg.color}15`, color: roleCfg.color }}>
                  {roleCfg.label}
                </Badge>
                {grantCount > 0 && <Badge className="text-[10px] bg-[#6B8E23]/10 text-[#6B8E23]">+{grantCount}</Badge>}
                {denyCount > 0 && <Badge className="text-[10px] bg-[#C87967]/10 text-[#C87967]">-{denyCount}</Badge>}
                <Button onClick={() => runSimulation(u)} size="sm" variant="outline"
                  className="rounded-full text-xs h-8 border-[#E2E4E0] text-[#4A5D4E]"
                  title="Rechte simulieren"
                  data-testid={`simulate-user-${u.user_id}`}>
                  <Beaker className="w-3 h-3" />
                </Button>
                <Button onClick={() => openUser(u)} size="sm" variant="outline"
                  className="rounded-full text-xs h-8 border-[#E2E4E0]"
                  data-testid={`edit-user-caps-${u.user_id}`}>
                  {t('editPermissions')}
                </Button>
              </div>
            );
          })}
          {filteredUsers.length > 50 && (
            <div className="p-3 text-center text-xs text-[#9CA3AF]">
              {filteredUsers.length - 50} weitere Nutzer — bitte Suche verwenden
            </div>
          )}
        </div>
      </div>

      {/* Edit user caps dialog */}
      <Dialog open={!!editUser} onOpenChange={() => setEditUser(null)}>
        <DialogContent className="sm:max-w-[640px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-base">
              Individuelle Rechte: {editUser?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-xs text-[#6B7280]">
              {t('role')} <strong>{ROLE_LABELS[editUser?.role || 'member']?.label}</strong>.
              Hier kannst du zusaetzlich zu den Rollen-Defaults Rechte <span className="text-[#6B8E23] font-medium">gewaehren (+)</span>
              {' '}oder <span className="text-[#C87967] font-medium">entziehen (−)</span>.
              Mit dem <Clock className="inline w-3 h-3" />-Icon kannst du ein Ablaufdatum setzen (z.B. für Urlaubsvertretungen).
            </p>

            {presets.length > 0 && (
              <div className="bg-[#4A5D4E]/5 border border-[#4A5D4E]/20 rounded-xl p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4 text-[#4A5D4E]" />
                  <p className="text-xs font-semibold text-[#4A5D4E]">Schnell-Presets anwenden</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {presets.map(p => (
                    <PresetTooltip key={p.preset_id} preset={p} capsMeta={capsMeta}>
                      <button onClick={() => applyPresetToUser(p)}
                        className="text-[10px] px-2 py-1 bg-white border border-[#4A5D4E]/30 text-[#4A5D4E] hover:bg-[#4A5D4E] hover:text-white rounded-full transition-colors"
                        data-testid={`apply-preset-${p.preset_id}`}>
                        {p.label} (+{p.capabilities.length})
                      </button>
                    </PresetTooltip>
                  ))}
                </div>
              </div>
            )}

            {Object.entries(capsByCategory).map(([cat, caps]) => (
              <div key={cat}>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#4A5D4E] mb-2">
                  {CATEGORY_LABELS[cat] || cat}
                </h4>
                <div className="space-y-1.5">
                  {caps.map(c => {
                    const roleHas = (capsData.role_defaults[editUser?.role || 'member'] || []).includes(c.key);
                    const granted = userCaps.grants.includes(c.key);
                    const denied = userCaps.denies.includes(c.key);
                    const exp = userCaps.expires?.[c.key];
                    const hasOverride = granted || denied;
                    return (
                      <div key={c.key} className="rounded-lg hover:bg-[#F3F4F1]"
                        data-testid={`user-cap-row-${c.key}`}>
                        <div className="flex items-center gap-3 p-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-[#1C1F1D]">{c.label}</span>
                              {roleHas && <Badge className="text-[9px] bg-[#9CA3AF]/10 text-[#6B7280]">Rolle</Badge>}
                              {exp && <Badge className="text-[9px] bg-[#D4A373]/10 text-[#D4A373]">bis {fmtDate(exp)}</Badge>}
                            </div>
                            <p className="text-[10px] text-[#9CA3AF]">{c.description}</p>
                          </div>
                          <div className="flex gap-1 flex-shrink-0">
                            <button onClick={() => toggleCap('grants', c.key)}
                              className={`px-2 py-1 rounded text-[11px] border transition-colors ${granted ? 'bg-[#6B8E23] text-white border-[#6B8E23]' : 'border-[#E2E4E0] text-[#9CA3AF] hover:border-[#6B8E23] hover:text-[#6B8E23]'}`}
                              data-testid={`grant-btn-${c.key}`}>
                              + Gewaehren
                            </button>
                            <button onClick={() => toggleCap('denies', c.key)}
                              className={`px-2 py-1 rounded text-[11px] border transition-colors ${denied ? 'bg-[#C87967] text-white border-[#C87967]' : 'border-[#E2E4E0] text-[#9CA3AF] hover:border-[#C87967] hover:text-[#C87967]'}`}
                              data-testid={`deny-btn-${c.key}`}>
                              − Entziehen
                            </button>
                          </div>
                        </div>
                        {hasOverride && (
                          <div className="flex items-center gap-2 pl-2 pb-2 pr-2">
                            <Clock className="w-3 h-3 text-[#9CA3AF]" />
                            <label className="text-[10px] text-[#6B7280]">Gültig bis:</label>
                            <input type="date"
                              value={exp ? exp.slice(0, 10) : ''}
                              onChange={e => setExpires(c.key, e.target.value)}
                              className="text-[11px] border border-[#E2E4E0] rounded px-1.5 py-0.5 focus:outline-none focus:border-[#4A5D4E]"
                              data-testid={`expires-${c.key}`} />
                            {exp && (
                              <button onClick={() => setExpires(c.key, null)}
                                className="text-[#9CA3AF] hover:text-[#C87967]" title={t('removeExpiry')}>
                                <X className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditUser(null)} className="rounded-full border-[#E2E4E0]">
              {t('cancel')}
            </Button>
            <Button onClick={saveUserCaps} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full"
              data-testid="save-user-caps-btn">
              Speichern
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Simulator Dialog */}
      <Dialog open={!!simulateUser} onOpenChange={() => { setSimulateUser(null); setSimulation(null); }}>
        <DialogContent className="sm:max-w-[640px] max-h-[85vh] overflow-y-auto" data-testid="simulator-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Beaker className="w-4 h-4 text-[#4A5D4E]" />
              Rechte-Simulator: {simulateUser?.name}
            </DialogTitle>
          </DialogHeader>
          {!simulation ? (
            <div className="py-8 text-center text-sm text-[#9CA3AF]">Berechnung laeuft...</div>
          ) : (
            <div className="space-y-4 pt-2 text-sm">
              <div className="bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl p-3">
                <p className="text-xs text-[#6B7280]">{t('role')} <strong>{ROLE_LABELS[simulation.user.role]?.label}</strong>
                  {simulation.user.legacy_role && simulation.user.legacy_role !== simulation.user.role &&
                    <span className="text-[10px] text-[#9CA3AF] ml-2">(vorher: {simulation.user.legacy_role})</span>}
                </p>
                <p className="text-xs text-[#6B7280]">{simulation.user.email}</p>
                <p className="text-lg font-semibold text-[#4A5D4E] mt-1" data-testid="sim-effective-count">
                  {simulation.effective_count} effektive Rechte
                </p>
              </div>

              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#4A5D4E] mb-1.5">
                  Aus Rolle ({simulation.role_defaults.length})
                </h4>
                <div className="flex flex-wrap gap-1">
                  {simulation.role_defaults.map(c => (
                    <code key={c} className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E] px-1.5 py-0.5 rounded">{c}</code>
                  ))}
                </div>
              </div>

              {simulation.groups.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#D4A373] mb-1.5">
                    Aus Gruppen ({simulation.groups.length})
                  </h4>
                  {simulation.groups.map(g => (
                    <div key={g.group_id} className="mb-1.5">
                      <span className="text-xs text-[#1C1F1D] font-medium">{g.name}</span>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {g.capabilities.map(c => (
                          <code key={c} className="text-[10px] bg-[#D4A373]/10 text-[#D4A373] px-1.5 py-0.5 rounded">{c}</code>
                        ))}
                        {g.capabilities.length === 0 && <span className="text-[10px] text-[#9CA3AF] italic">{t('noCapabilities')}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {simulation.direct_grants_active.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#6B8E23] mb-1.5">
                    Aktive Direkt-Grants (+{simulation.direct_grants_active.length})
                  </h4>
                  <div className="space-y-1">
                    {simulation.direct_grants_active.map((g, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <code className="bg-[#6B8E23]/10 text-[#6B8E23] px-1.5 py-0.5 rounded">{g.cap}</code>
                        {g.expires_at && <span className="text-[10px] text-[#D4A373] flex items-center gap-1"><Clock className="w-3 h-3" />bis {fmtDate(g.expires_at)}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {simulation.direct_denies_active.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#C87967] mb-1.5">
                    Aktive Direkt-Denies (−{simulation.direct_denies_active.length})
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {simulation.direct_denies_active.map((d, i) => (
                      <code key={i} className="text-[10px] bg-[#C87967]/10 text-[#C87967] px-1.5 py-0.5 rounded">{d.cap}</code>
                    ))}
                  </div>
                </div>
              )}

              {(simulation.direct_grants_expired.length + simulation.direct_denies_expired.length) > 0 && (
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#9CA3AF] mb-1.5">
                    Abgelaufen ({simulation.direct_grants_expired.length + simulation.direct_denies_expired.length})
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {[...simulation.direct_grants_expired, ...simulation.direct_denies_expired].map((e, i) => (
                      <code key={i} className="text-[10px] bg-[#E2E4E0]/50 text-[#9CA3AF] px-1.5 py-0.5 rounded line-through" title={`Abgelaufen am ${fmtDate(e.expires_at)}`}>
                        {e.cap}
                      </code>
                    ))}
                  </div>
                </div>
              )}

              <div className="pt-2 border-t border-[#E2E4E0]">
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-[#1C1F1D] mb-1.5">
                  Effektive Rechte ({simulation.effective.length})
                </h4>
                <div className="flex flex-wrap gap-1 max-h-[120px] overflow-y-auto">
                  {simulation.effective.map(c => (
                    <code key={c} className="text-[10px] bg-[#F3F4F1] text-[#1C1F1D] px-1.5 py-0.5 rounded">{c}</code>
                  ))}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
