/**
 * iter 212 — Unified Permissions Hub.
 *
 * Single panel that consolidates Roles+Caps + Presets + Auto-Rules into
 * one cohesive workspace. Three tabs:
 *   1. Effektiv — pick a user, see every cap with its source (role/group/grant).
 *   2. Wer darf X? — pick a capability, see every user who has it + source.
 *   3. Audit — find redundant grants, expired entries, orphan groups.
 *
 * Plus an inline link to the existing RolesCapsPanel & PresetEditorPanel via
 * mini-tabs at the top of the parent admin page.
 */
import React, { useState, useEffect, useMemo } from 'react';
import api from '../../lib/api';
import { roleLabel } from '../../lib/roleLabel';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { Loader2, Search, AlertTriangle, Trash2, User as UserIcon, Layers, ShieldCheck, Sparkles, KeyRound, Wrench, Users as UsersIcon, Database } from 'lucide-react';
import { toast } from 'sonner';

const ROLE_COLORS = {
  admin: '#C87967', moderator: '#4A5D4E', member: '#8A9D8E', guest: '#9CA3AF',
};

function SourceBadge({ source }) {
  if (source.type === 'role') {
    return (
      <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#1A1D1B]/5 text-[#1A1D1B] font-medium">
        Rolle: {source.label}
      </span>
    );
  }
  if (source.type === 'group') {
    return (
      <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#4A5D4E]/10 text-[#4A5D4E] font-medium">
        Gruppe: {source.label}
      </span>
    );
  }
  return (
    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#C87967]/10 text-[#C87967] font-medium">
      Direkt-Grant{source.expires_at ? ` (bis ${new Date(source.expires_at).toLocaleDateString('de-DE')})` : ''}
    </span>
  );
}

// ============ TAB 1: User → Caps with sources ============
function EffectivePanel({ users, capabilities }) {
  const [pickedUserId, setPickedUserId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users.slice(0, 30);
    return users.filter(u =>
      (u.name || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q)
    ).slice(0, 30);
  }, [users, search]);

  useEffect(() => {
    if (!pickedUserId) { setData(null); return; }
    setLoading(true);
    api.get(`/admin/users/${pickedUserId}/simulate`)
      .then(r => setData(r.data))
      .catch(() => toast.error('Fehler beim Laden'))
      .finally(() => setLoading(false));
  }, [pickedUserId]);

  const grouped = useMemo(() => {
    if (!data) return null;
    // Build a map: cap_key -> [sources]
    const sourcesByCap = {};
    (data.role_defaults || []).forEach(c => {
      sourcesByCap[c] = sourcesByCap[c] || [];
      sourcesByCap[c].push({ type: 'role', label: data.user.role });
    });
    (data.groups || []).forEach(g => {
      (g.capabilities || []).forEach(c => {
        sourcesByCap[c] = sourcesByCap[c] || [];
        sourcesByCap[c].push({ type: 'group', label: g.name, id: g.group_id });
      });
    });
    (data.direct_grants_active || []).forEach(g => {
      sourcesByCap[g.cap] = sourcesByCap[g.cap] || [];
      sourcesByCap[g.cap].push({ type: 'grant', expires_at: g.expires_at });
    });
    return data.effective.map(c => ({ cap: c, sources: sourcesByCap[c] || [] }));
  }, [data]);

  return (
    <div className="grid grid-cols-12 gap-4 h-[600px]">
      {/* Left: User picker */}
      <div className="col-span-4 border border-[#E2E4E0] rounded-lg overflow-hidden flex flex-col">
        <div className="p-2 border-b border-[#E2E4E0] bg-[#FAFAF9]">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Nutzer suchen…" className="h-8 pl-8 text-xs"
              data-testid="perm-effective-search" />
          </div>
        </div>
        <ScrollArea className="flex-1">
          {filteredUsers.map(u => (
            <button key={u.user_id}
              onClick={() => setPickedUserId(u.user_id)}
              className={`w-full text-left px-3 py-2 border-b border-[#E2E4E0] hover:bg-[#F5F4F0] transition ${pickedUserId === u.user_id ? 'bg-[#4A5D4E]/5' : ''}`}
              data-testid={`perm-effective-user-${u.user_id}`}>
              <div className="text-xs font-medium text-[#1A1D1B] truncate">{u.name || u.email}</div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-[9px] px-1 py-0.5 rounded font-medium" style={{
                  background: ROLE_COLORS[u.role] + '20', color: ROLE_COLORS[u.role] || '#6B7280',
                }}>{roleLabel(u.role)}</span>
                <span className="text-[9px] text-[#9CA3AF] truncate">{u.email}</span>
              </div>
            </button>
          ))}
          {filteredUsers.length === 0 && <div className="p-4 text-xs text-[#9CA3AF] text-center">Keine Treffer</div>}
        </ScrollArea>
      </div>

      {/* Right: Effective view */}
      <div className="col-span-8 border border-[#E2E4E0] rounded-lg overflow-hidden flex flex-col">
        {!pickedUserId && (
          <div className="flex-1 flex items-center justify-center text-xs text-[#9CA3AF]">
            Wähle links einen Nutzer aus, um seine effektiven Rechte zu sehen.
          </div>
        )}
        {pickedUserId && loading && <div className="flex-1 flex items-center justify-center"><Loader2 className="w-5 h-5 animate-spin text-[#4A5D4E]" /></div>}
        {pickedUserId && !loading && data && (
          <>
            <div className="px-4 py-3 border-b border-[#E2E4E0] bg-[#FAFAF9]">
              <div className="text-sm font-semibold text-[#1A1D1B]">{data.user.name}</div>
              <div className="text-[11px] text-[#6B7280]">{data.user.email} · Rolle: <strong>{data.user.role}</strong> · {data.effective_count} aktive Rechte</div>
              {data.groups.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {data.groups.map(g => (
                    <Badge key={g.group_id} variant="outline" className="text-[9px] border-[#4A5D4E]/30 text-[#4A5D4E]">{g.name}</Badge>
                  ))}
                </div>
              )}
            </div>
            <ScrollArea className="flex-1">
              <div className="p-3 space-y-1">
                {grouped.map(({ cap, sources }) => {
                  const meta = capabilities.find(c => c.key === cap);
                  return (
                    <div key={cap} className="flex items-start gap-2 py-1.5 border-b border-[#F5F4F0] last:border-0" data-testid={`effective-cap-${cap}`}>
                      <ShieldCheck className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-[#1A1D1B]">{meta?.label || cap}</div>
                        <code className="text-[9px] text-[#9CA3AF]">{cap}</code>
                      </div>
                      <div className="flex flex-wrap gap-1 justify-end max-w-[55%]">
                        {sources.map((s, i) => <SourceBadge key={i} source={s} />)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          </>
        )}
      </div>
    </div>
  );
}

// ============ TAB 2: Capability → Users ============
function WhoHasCapPanel({ capabilities }) {
  const [pickedCap, setPickedCap] = useState('');
  const [search, setSearch] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const filteredCaps = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return capabilities;
    return capabilities.filter(c =>
      c.key.toLowerCase().includes(q) ||
      (c.label || '').toLowerCase().includes(q)
    );
  }, [capabilities, search]);

  // Group caps by category
  const byCategory = useMemo(() => {
    const map = {};
    filteredCaps.forEach(c => {
      const cat = c.category || 'global';
      if (!map[cat]) map[cat] = [];
      map[cat].push(c);
    });
    return map;
  }, [filteredCaps]);

  useEffect(() => {
    if (!pickedCap) { setData(null); return; }
    setLoading(true);
    api.get(`/admin/permissions/who-has-cap/${encodeURIComponent(pickedCap)}`)
      .then(r => setData(r.data))
      .catch(() => toast.error('Fehler beim Laden'))
      .finally(() => setLoading(false));
  }, [pickedCap]);

  return (
    <div className="grid grid-cols-12 gap-4 h-[600px]">
      <div className="col-span-5 border border-[#E2E4E0] rounded-lg overflow-hidden flex flex-col">
        <div className="p-2 border-b border-[#E2E4E0] bg-[#FAFAF9]">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Capability suchen…" className="h-8 pl-8 text-xs"
              data-testid="perm-who-search" />
          </div>
        </div>
        <ScrollArea className="flex-1">
          {Object.entries(byCategory).map(([cat, caps]) => (
            <div key={cat}>
              <div className="px-3 py-1 text-[9px] font-semibold text-[#9CA3AF] uppercase bg-[#F5F4F0] sticky top-0">{cat}</div>
              {caps.map(c => (
                <button key={c.key} onClick={() => setPickedCap(c.key)}
                  className={`w-full text-left px-3 py-1.5 border-b border-[#E2E4E0] hover:bg-[#F5F4F0] transition ${pickedCap === c.key ? 'bg-[#4A5D4E]/5' : ''}`}
                  data-testid={`perm-who-cap-${c.key}`}>
                  <div className="text-xs font-medium text-[#1A1D1B]">{c.label}</div>
                  <code className="text-[9px] text-[#9CA3AF]">{c.key}</code>
                </button>
              ))}
            </div>
          ))}
        </ScrollArea>
      </div>

      <div className="col-span-7 border border-[#E2E4E0] rounded-lg overflow-hidden flex flex-col">
        {!pickedCap && <div className="flex-1 flex items-center justify-center text-xs text-[#9CA3AF]">Wähle links eine Capability.</div>}
        {pickedCap && loading && <div className="flex-1 flex items-center justify-center"><Loader2 className="w-5 h-5 animate-spin text-[#4A5D4E]" /></div>}
        {pickedCap && !loading && data && (
          <>
            <div className="px-4 py-3 border-b border-[#E2E4E0] bg-[#FAFAF9]">
              <div className="text-sm font-semibold text-[#1A1D1B]"><code>{data.capability}</code></div>
              <div className="text-[11px] text-[#6B7280]"><strong>{data.count}</strong> Nutzer haben diese Berechtigung</div>
            </div>
            <ScrollArea className="flex-1">
              <div className="divide-y divide-[#F5F4F0]">
                {data.users.map(u => (
                  <div key={u.user_id} className="px-4 py-2 flex items-start justify-between gap-2 hover:bg-[#FAFAF9]" data-testid={`who-user-${u.user_id}`}>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-[#1A1D1B]">{u.name}</div>
                      <div className="text-[10px] text-[#9CA3AF]">{u.email}</div>
                    </div>
                    <div className="flex flex-wrap gap-1 justify-end max-w-[55%]">
                      {u.sources.map((s, i) => <SourceBadge key={i} source={s} />)}
                    </div>
                  </div>
                ))}
                {data.users.length === 0 && <div className="p-4 text-xs text-[#9CA3AF] text-center">Niemand hat dieses Recht aktiv.</div>}
              </div>
            </ScrollArea>
          </>
        )}
      </div>
    </div>
  );
}

// ============ TAB 3: Audit ============
function AuditPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const reload = () => {
    setLoading(true);
    api.get('/admin/permissions/audit')
      .then(r => setData(r.data))
      .catch(() => toast.error('Fehler beim Laden'))
      .finally(() => setLoading(false));
  };
  useEffect(() => { reload(); }, []);

  const removeRedundant = async (item) => {
    if (!window.confirm(`Direkt-Grant "${item.cap}" für ${item.name} entfernen? (Wird durch ${item.covered_by} bereits abgedeckt)`)) return;
    try {
      const { data: u } = await api.get(`/admin/users/${item.user_id}/simulate`);
      const newGrants = (u.direct_grants_active || []).map(g => g.cap).filter(c => c !== item.cap);
      const newDenies = (u.direct_denies_active || []).map(d => d.cap);
      await api.put(`/admin/users/${item.user_id}/capabilities`, {
        grants: newGrants, denies: newDenies,
      });
      toast.success('Entfernt');
      reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    }
  };

  if (loading || !data) return <div className="flex items-center justify-center h-64"><Loader2 className="w-5 h-5 animate-spin text-[#4A5D4E]" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-[#1A1D1B]">Konsistenz-Audit</div>
          <div className="text-[11px] text-[#6B7280]">{data.total_issues} potenzielle Aufräum-Aufgaben gefunden</div>
        </div>
        <Button onClick={reload} size="sm" variant="outline" className="h-8 text-xs">Neu prüfen</Button>
      </div>

      {/* Redundant grants */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-[#4A5D4E]" />
          <span className="text-xs font-semibold">Redundante Direkt-Grants ({data.redundant_grants.length})</span>
        </div>
        {data.redundant_grants.length === 0 ? (
          <div className="p-4 text-xs text-[#9CA3AF] text-center">Keine Redundanzen — sauber!</div>
        ) : (
          <div className="divide-y divide-[#F5F4F0] max-h-72 overflow-y-auto">
            {data.redundant_grants.map((r, i) => (
              <div key={i} className="px-3 py-2 flex items-center justify-between gap-2 text-xs">
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{r.name}</div>
                  <div className="text-[10px] text-[#6B7280]">
                    <code>{r.cap}</code> — bereits durch <strong>{r.covered_by === 'role' ? 'Rolle' : 'Gruppe'}</strong> abgedeckt
                  </div>
                </div>
                <Button onClick={() => removeRedundant(r)} size="sm" variant="ghost"
                  className="h-7 text-[10px] text-[#C87967] hover:bg-[#C87967]/10"
                  data-testid={`audit-remove-${r.user_id}-${r.cap}`}>
                  <Trash2 className="w-3 h-3 mr-1" />Entfernen
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Expired entries */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-[#C87967]" />
          <span className="text-xs font-semibold">Abgelaufene Grants/Denies ({data.expired_entries.length})</span>
        </div>
        {data.expired_entries.length === 0 ? (
          <div className="p-4 text-xs text-[#9CA3AF] text-center">Keine abgelaufenen Einträge.</div>
        ) : (
          <div className="divide-y divide-[#F5F4F0] max-h-72 overflow-y-auto">
            {data.expired_entries.map((r, i) => (
              <div key={i} className="px-3 py-2 text-xs">
                <div className="font-medium">{r.name}</div>
                <div className="text-[10px] text-[#6B7280]">
                  <code>{r.cap}</code> — abgelaufen am {new Date(r.expired_at).toLocaleString('de-DE')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* iter 373 R3 — Users with direct grants (Migration to groups suggested) */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <KeyRound className="w-3.5 h-3.5 text-[#C87967]" />
          <span className="text-xs font-semibold">User mit direkten Capabilities ({(data.direct_grants_summary || []).length})</span>
          <span className="text-[10px] text-[#9CA3AF]">— Empfehlung: lieber über Gruppen verwalten (besser auditierbar)</span>
        </div>
        {(data.direct_grants_summary || []).length === 0 ? (
          <div className="p-4 text-xs text-[#9CA3AF] text-center">Keine User mit direkten Grants/Denies.</div>
        ) : (
          <div className="divide-y divide-[#F5F4F0] max-h-72 overflow-y-auto" data-testid="direct-grants-summary">
            {(data.direct_grants_summary || []).map((u) => (
              <div key={u.user_id} className="px-3 py-2 text-xs" data-testid={`direct-grant-${u.user_id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-[#1A1D1B]">{u.name}</div>
                    <div className="text-[10px] text-[#9CA3AF]">{u.email} · Rolle: {roleLabel(u.role)}</div>
                  </div>
                </div>
                {u.grants?.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    <span className="text-[9px] text-[#6B7280] mr-1">Grants:</span>
                    {u.grants.map((c) => (
                      <code key={c} className="text-[9px] px-1.5 py-0.5 rounded bg-[#4A5D4E]/10 text-[#4A5D4E]">{c}</code>
                    ))}
                  </div>
                )}
                {u.denies?.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    <span className="text-[9px] text-[#6B7280] mr-1">Denies:</span>
                    {u.denies.map((c) => (
                      <code key={c} className="text-[9px] px-1.5 py-0.5 rounded bg-[#C87967]/10 text-[#C87967]">{c}</code>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Orphan groups */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <UserIcon className="w-3.5 h-3.5 text-[#9CA3AF]" />
          <span className="text-xs font-semibold">Leere Gruppen mit Capabilities ({data.orphan_groups.length})</span>
        </div>
        {data.orphan_groups.length === 0 ? (
          <div className="p-4 text-xs text-[#9CA3AF] text-center">Alle Gruppen mit Rechten haben Mitglieder.</div>
        ) : (
          <div className="divide-y divide-[#F5F4F0] max-h-48 overflow-y-auto">
            {data.orphan_groups.map(g => (
              <div key={g.group_id} className="px-3 py-2 text-xs flex items-center justify-between">
                <div className="font-medium">{g.name}</div>
                <span className="text-[10px] text-[#6B7280]">{g.capability_count} Rechte, 0 Mitglieder</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============ TAB 4: Wartung (iter 373 R4 + L2) ============
function MaintenancePanel() {
  const [staleResult, setStaleResult] = useState(null);
  const [staleLoading, setStaleLoading] = useState(false);
  const [unverifiedPreview, setUnverifiedPreview] = useState(null);
  const [unverifiedLoading, setUnverifiedLoading] = useState(false);
  const [unverifiedConfirming, setUnverifiedConfirming] = useState(false);
  // Iter 377 — Preset-Groups seed + Demo-Wipe
  const [presetSeedResult, setPresetSeedResult] = useState(null);
  const [presetSeedLoading, setPresetSeedLoading] = useState(false);
  const [demoPreview, setDemoPreview] = useState(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoConfirming, setDemoConfirming] = useState(false);

  const runStaleCleanup = async () => {
    if (!window.confirm('Verwaiste Gruppen-Member-Einträge wirklich entfernen?')) return;
    setStaleLoading(true);
    try {
      const { data } = await api.post('/admin/groups/cleanup-stale-members');
      setStaleResult(data);
      toast.success(`${data.total_removed} verwaiste Einträge entfernt`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Cleanup');
    } finally {
      setStaleLoading(false);
    }
  };

  const previewUnverified = async () => {
    setUnverifiedLoading(true);
    try {
      const { data } = await api.post('/admin/users/cleanup-unverified-test-users', { dry_run: true });
      setUnverifiedPreview(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Vorschauen');
    } finally {
      setUnverifiedLoading(false);
    }
  };

  const runUnverifiedCleanup = async () => {
    if (!unverifiedPreview || unverifiedPreview.would_delete === 0) return;
    if (!window.confirm(`${unverifiedPreview.would_delete} unverifizierte Test-Konten endgültig löschen?\n\nDie Aktion ist NICHT umkehrbar. QA-Accounts (qa_*) sind ausgenommen.`)) return;
    setUnverifiedConfirming(true);
    try {
      const { data } = await api.post('/admin/users/cleanup-unverified-test-users', { dry_run: false });
      toast.success(`${data.deleted} Test-Konten gelöscht`);
      setUnverifiedPreview(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Löschen');
    } finally {
      setUnverifiedConfirming(false);
    }
  };

  // Iter 377 — Standardgruppen "Mitarbeiter Standard" + "Mitarbeiter Küche"
  // erstellen oder aktualisieren. Idempotent.
  const seedPresetGroups = async () => {
    setPresetSeedLoading(true);
    try {
      const { data } = await api.post('/admin/seed-preset-groups');
      setPresetSeedResult(data);
      const total = (data.created || []).length + (data.updated || []).length;
      toast.success(
        `${(data.created || []).length} angelegt, ${(data.updated || []).length} aktualisiert (${total} Gruppen aktiv)`
      );
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Anlegen der Standardgruppen');
    } finally {
      setPresetSeedLoading(false);
    }
  };

  const previewDemo = async () => {
    setDemoLoading(true);
    try {
      const { data } = await api.post('/admin/demo-data/preview');
      setDemoPreview(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler bei Demo-Vorschau');
    } finally {
      setDemoLoading(false);
    }
  };

  const wipeDemo = async () => {
    if (!demoPreview || demoPreview.total === 0) return;
    const userCount = demoPreview.demo_users || 0;
    const userWarning = userCount > 0
      ? `\n\nDavon ${userCount} Demo-Benutzer (Domain @demo.meetflow.local) inkl. ihrer Buchungen, Tasks, Chat-Nachrichten und Notifications.`
      : '';
    if (!window.confirm(
      `Achtung: ${demoPreview.total} Demo-Datenobjekte werden ENDGÜLTIG gelöscht ` +
      `(Demo-Ressourcen, deren Buchungen, Catering, Kostenstellen, Demo-Benutzer).` +
      userWarning +
      `\n\nEchte Nutzerdaten bleiben unangetastet — gelöscht wird nur, was mit ` +
      `"Demo_" / "DEMO-" beginnt oder die Domain @demo.meetflow.local trägt.\n\nWirklich fortfahren?`
    )) return;
    setDemoConfirming(true);
    try {
      const { data } = await api.post('/admin/demo-data/wipe', { confirm: true });
      toast.success(`${data.total} Demo-Objekte gelöscht`);
      setDemoPreview(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Demo-Wipe');
    } finally {
      setDemoConfirming(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="text-sm font-semibold text-[#1A1D1B]">Wartung & Aufräum-Aktionen</div>
        <div className="text-[11px] text-[#6B7280]">
          Diese Aktionen helfen, die Datenqualität der Benutzer- und Gruppenverwaltung sauber zu halten.
        </div>
      </div>

      {/* R4 — Stale group-member cleanup */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden" data-testid="maintenance-stale-members">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-[#4A5D4E]" />
          <span className="text-xs font-semibold">Verwaiste Gruppen-Mitgliedschaften aufräumen</span>
        </div>
        <div className="p-3 space-y-2">
          <div className="text-[11px] text-[#6B7280]">
            Entfernt Einträge in <code>group.members</code>, deren zugehöriger Benutzer nicht mehr existiert.
            Diese können entstehen, wenn Benutzer vor Iter 372 gelöscht wurden, ohne die Gruppen-Memberships zu aktualisieren.
          </div>
          <Button onClick={runStaleCleanup} disabled={staleLoading} size="sm"
            className="bg-[#4A5D4E] hover:bg-[#3D4E40] text-white h-8 text-xs"
            data-testid="maintenance-stale-run">
            {staleLoading ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Räume auf…</> : <><Wrench className="w-3 h-3 mr-1" />Jetzt aufräumen</>}
          </Button>
          {staleResult && (
            <div className="mt-2 text-[11px] bg-[#F5F4F0] rounded p-2" data-testid="maintenance-stale-result">
              <div className="font-medium text-[#1A1D1B]">Ergebnis: {staleResult.total_removed} Einträge entfernt</div>
              {staleResult.groups_cleaned?.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {staleResult.groups_cleaned.map((g) => (
                    <li key={g.group_id} className="text-[#6B7280]">
                      • <strong>{g.name}</strong>: {g.removed} entfernt → {g.remaining} verbleiben
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>

      {/* L2 — Unverified test users cleanup */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden" data-testid="maintenance-unverified-users">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-[#C87967]" />
          <span className="text-xs font-semibold">Unverifizierte Test-Konten entfernen</span>
        </div>
        <div className="p-3 space-y-2">
          <div className="text-[11px] text-[#6B7280] space-y-1">
            <div>
              Löscht unverifizierte Konten aus bekannten Test-Domains{' '}
              (<code>klinik.de, meetflow.local, test.com, example.com</code> …) und Test-Präfixen{' '}
              (<code>testuser_, loadtest, freshtest_</code> …).
            </div>
            <div className="text-[10px]">
              Sicherheits-Stop: Konten mit eigenen Tasks oder Buchungen werden NICHT gelöscht.
              QA-Konten (<code>qa_*</code>) sind generell ausgenommen.
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={previewUnverified} disabled={unverifiedLoading} size="sm"
              variant="outline" className="h-8 text-xs"
              data-testid="maintenance-unverified-preview">
              {unverifiedLoading ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Suche…</> : <><Search className="w-3 h-3 mr-1" />Vorschau anzeigen</>}
            </Button>
            {unverifiedPreview && unverifiedPreview.would_delete > 0 && (
              <Button onClick={runUnverifiedCleanup} disabled={unverifiedConfirming} size="sm"
                className="bg-[#C87967] hover:bg-[#B86A57] text-white h-8 text-xs"
                data-testid="maintenance-unverified-delete">
                {unverifiedConfirming ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Lösche…</> : <><Trash2 className="w-3 h-3 mr-1" />{unverifiedPreview.would_delete} jetzt löschen</>}
              </Button>
            )}
          </div>
          {unverifiedPreview && (
            <div className="mt-2 text-[11px] bg-[#F5F4F0] rounded p-2" data-testid="maintenance-unverified-result">
              <div className="font-medium text-[#1A1D1B]">
                {unverifiedPreview.would_delete} Konten zur Löschung gefunden
              </div>
              {unverifiedPreview.sample?.length > 0 && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-[#6B7280] text-[10px]">
                    Beispiele (max. 25) anzeigen
                  </summary>
                  <ul className="mt-1 space-y-0.5 max-h-48 overflow-y-auto">
                    {unverifiedPreview.sample.map((u) => (
                      <li key={u.user_id} className="text-[#6B7280] text-[10px]">
                        • {u.email} <span className="text-[#9CA3AF]">({u.status || 'no-status'})</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Iter 377 — Standardgruppen anlegen / aktualisieren */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden" data-testid="maintenance-preset-groups">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <UsersIcon className="w-3.5 h-3.5 text-[#4A5D4E]" />
          <span className="text-xs font-semibold">Standard-Mitarbeitergruppen anlegen</span>
        </div>
        <div className="p-3 space-y-2">
          <div className="text-[11px] text-[#6B7280]">
            Legt zwei vordefinierte Gruppen mit den passenden Rechten an (Dashboard, Aufgaben mit
            Abteilungs-Sichtbarkeit, Ressourcen, Terminplanung, Chat, Kalender):
            <ul className="mt-1 ml-3 list-disc">
              <li><strong>Mitarbeiter Standard</strong> — buchen für sich + andere; KEIN Ressourcen-Stammdaten-Zugriff</li>
              <li><strong>Mitarbeiter Küche</strong> — alle Ressourcen-Rechte inkl. Stammdaten, Genehmigung, Catering und Rechnungen</li>
            </ul>
            Bestehende Capabilities werden bei erneutem Anklicken zurückgesetzt — Mitgliedschaften bleiben erhalten.
          </div>
          <Button onClick={seedPresetGroups} disabled={presetSeedLoading} size="sm"
            className="bg-[#4A5D4E] hover:bg-[#3D4E40] text-white h-8 text-xs"
            data-testid="maintenance-preset-seed">
            {presetSeedLoading
              ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Lege an…</>
              : <><Wrench className="w-3 h-3 mr-1" />Gruppen anlegen / aktualisieren</>}
          </Button>
          {presetSeedResult && (
            <div className="mt-2 text-[11px] bg-[#F5F4F0] rounded p-2" data-testid="maintenance-preset-result">
              <div className="font-medium text-[#1A1D1B]">
                ✓ {(presetSeedResult.created || []).length} angelegt, {(presetSeedResult.updated || []).length} aktualisiert
              </div>
              <ul className="mt-1 space-y-0.5">
                {(presetSeedResult.groups || []).map(g => (
                  <li key={g.group_id} className="text-[#6B7280]">
                    • <strong>{g.name}</strong> ({g.capabilities.length} Rechte)
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Iter 377 — Demo-Daten entfernen */}
      <div className="border border-[#E2E4E0] rounded-lg overflow-hidden" data-testid="maintenance-demo-data">
        <div className="px-3 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0] flex items-center gap-2">
          <Database className="w-3.5 h-3.5 text-[#C87967]" />
          <span className="text-xs font-semibold">Demo-Daten entfernen</span>
        </div>
        <div className="p-3 space-y-2">
          <div className="text-[11px] text-[#6B7280] space-y-1">
            <div>
              Löscht alle vom System generierten Demo-Datensätze (Ressourcen mit Präfix <code>Demo_</code>,
              ihre Buchungen + Catering, Kostenstellen / Konten mit Präfix <code>DEMO-</code>,
              sowie Demo-Benutzer mit Email-Domain <code>@demo.meetflow.local</code> inkl. ihrer
              Buchungen, Tasks, Chat-Nachrichten und Notifications).
            </div>
            <div className="text-[10px]">
              Echte Nutzerdaten und manuell angelegte Objekte sind nicht betroffen
              (QA-Tester wie <code>qa_admin@meetflow.com</code> bleiben unangetastet).
              Dry-Run-Vorschau zuerst.
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={previewDemo} disabled={demoLoading} size="sm"
              variant="outline" className="h-8 text-xs"
              data-testid="maintenance-demo-preview">
              {demoLoading
                ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Suche…</>
                : <><Search className="w-3 h-3 mr-1" />Vorschau anzeigen</>}
            </Button>
            {demoPreview && demoPreview.total > 0 && (
              <Button onClick={wipeDemo} disabled={demoConfirming} size="sm"
                className="bg-[#C87967] hover:bg-[#B86A57] text-white h-8 text-xs"
                data-testid="maintenance-demo-wipe">
                {demoConfirming
                  ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Lösche…</>
                  : <><Trash2 className="w-3 h-3 mr-1" />{demoPreview.total} jetzt löschen</>}
              </Button>
            )}
          </div>
          {demoPreview && (
            <div className="mt-2 text-[11px] bg-[#F5F4F0] rounded p-2" data-testid="maintenance-demo-result">
              <div className="font-medium text-[#1A1D1B]">
                {demoPreview.total} Demo-Datenobjekte gefunden
              </div>
              <ul className="mt-1 space-y-0.5 text-[10px] text-[#6B7280]">
                <li>• {demoPreview.demo_resources} Ressourcen (Räume, Desks, Fahrzeuge)</li>
                <li>• {demoPreview.demo_bookings} Buchungen</li>
                <li>• {demoPreview.demo_catering_requests} Catering-Anfragen</li>
                <li>• {demoPreview.demo_catering_items} Catering-Artikel</li>
                <li>• {demoPreview.demo_master_data_entries} Stammdaten-Einträge (Kostenstellen/Konten)</li>
                {demoPreview.demo_legacy_cost_centers > 0 && <li>• {demoPreview.demo_legacy_cost_centers} Legacy-Kostenstellen</li>}
                {demoPreview.demo_legacy_accounts > 0 && <li>• {demoPreview.demo_legacy_accounts} Legacy-Konten</li>}
                {demoPreview.demo_users > 0 && (
                  <li className="font-medium text-[#C87967]">
                    • {demoPreview.demo_users} Demo-Benutzer
                    {demoPreview.demo_user_bookings > 0 && `, ${demoPreview.demo_user_bookings} Buchungen`}
                    {demoPreview.demo_user_tasks > 0 && `, ${demoPreview.demo_user_tasks} Tasks`}
                    {demoPreview.demo_user_messages > 0 && `, ${demoPreview.demo_user_messages} Nachrichten`}
                    {demoPreview.demo_user_notifications > 0 && `, ${demoPreview.demo_user_notifications} Notifications`}
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============ MAIN COMPONENT ============
const TABS = [
  { id: 'effective', label: 'Effektive Rechte', icon: ShieldCheck },
  { id: 'who', label: 'Wer darf X?', icon: KeyRound },
  { id: 'audit', label: 'Konsistenz-Audit', icon: Sparkles },
  { id: 'maintenance', label: 'Wartung', icon: Wrench },
];

export default function PermissionsHub() {
  const [tab, setTab] = useState('effective');
  const [users, setUsers] = useState([]);
  const [capabilities, setCapabilities] = useState([]);

  useEffect(() => {
    api.get('/admin/users').then(r => setUsers(r.data || [])).catch(() => {});
    api.get('/admin/capabilities').then(r => {
      // Backend returns { capabilities: [...] }
      setCapabilities(r.data?.capabilities || r.data || []);
    }).catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1 border-b border-[#E2E4E0] -mx-1 px-1">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-3 py-2 text-xs font-medium rounded-t-md flex items-center gap-1.5 transition ${active ? 'bg-[#4A5D4E] text-white' : 'text-[#6B7280] hover:bg-[#F5F4F0]'}`}
              data-testid={`perm-hub-tab-${t.id}`}>
              <Icon className="w-3.5 h-3.5" />{t.label}
            </button>
          );
        })}
      </div>
      {tab === 'effective' && <EffectivePanel users={users} capabilities={capabilities} />}
      {tab === 'who' && <WhoHasCapPanel capabilities={capabilities} />}
      {tab === 'audit' && <AuditPanel />}
      {tab === 'maintenance' && <MaintenancePanel />}
    </div>
  );
}
