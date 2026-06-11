/**
 * iter 212 — End-user „Meine Berechtigungen" page.
 *
 * Transparenzpage in jedem User-Profil: zeigt jeder Nutzer auf einen Blick
 *   - seine Rolle und alle Module die er sieht
 *   - die Gruppen denen er angehört + welche Caps daraus kommen
 *   - direkte Grants (mit Ablaufdatum) und Denies
 *   - jede effektive Capability mit der Quelle (Rolle/Gruppe/Grant)
 *
 * Read-only — Änderungen können nur Admins vornehmen. Die Page wird via
 * Profil-Menü oder Direkt-Link `/me/permissions` erreicht.
 */
import React, { useEffect, useState, useMemo } from 'react';
import api from '../lib/api';
import Sidebar from '../components/Sidebar';
import { Loader2, ShieldCheck, Layers, KeyRound, Clock, Lock } from 'lucide-react';
import { Badge } from '../components/ui/badge';

const ROLE_LABEL = { admin: 'Administrator', moderator: 'Moderator', member: 'Mitarbeiter', guest: 'Gast' };
const ROLE_COLOR = { admin: '#C87967', moderator: '#4A5D4E', member: '#8A9D8E', guest: '#9CA3AF' };

export default function MyPermissionsPage() {
  const [data, setData] = useState(null);
  const [caps, setCaps] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/me/permissions/breakdown'),
      api.get('/admin/capabilities').catch(() => ({ data: { capabilities: [] } })),
    ])
      .then(([b, c]) => {
        setData(b.data);
        setCaps(c.data?.capabilities || c.data || []);
      })
      .finally(() => setLoading(false));
  }, []);

  // Build cap → sources map for the effective list
  const enriched = useMemo(() => {
    if (!data) return [];
    const sourcesByCap = {};
    (data.role_defaults || []).forEach(c => {
      sourcesByCap[c] = sourcesByCap[c] || [];
      sourcesByCap[c].push({ type: 'role', label: data.role });
    });
    (data.groups || []).forEach(g => {
      (g.capabilities || []).forEach(c => {
        sourcesByCap[c] = sourcesByCap[c] || [];
        sourcesByCap[c].push({ type: 'group', label: g.name, color: g.color });
      });
    });
    (data.direct_grants || []).forEach(c => {
      sourcesByCap[c] = sourcesByCap[c] || [];
      sourcesByCap[c].push({ type: 'grant', expires_at: data.expires?.[c] });
    });
    return (data.effective || []).map(c => {
      const meta = caps.find(x => x.key === c) || {};
      return { cap: c, label: meta.label || c, category: meta.category || 'global', sources: sourcesByCap[c] || [] };
    });
  }, [data, caps]);

  const byCategory = useMemo(() => {
    const m = {};
    enriched.forEach(e => {
      if (!m[e.category]) m[e.category] = [];
      m[e.category].push(e);
    });
    return m;
  }, [enriched]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#FAFAF9]">
        <Loader2 className="w-6 h-6 animate-spin text-[#4A5D4E]" />
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="flex h-screen bg-[#FAFAF9]">
      <Sidebar />
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
          <div className="mb-6">
            <h1 className="text-2xl font-medium tracking-tight text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }} data-testid="my-perm-title">
              Meine Berechtigungen
            </h1>
            <p className="text-sm text-[#6B7280] mt-1">
              Transparenter Überblick: was darfst du, und woher kommt jedes Recht?
            </p>
          </div>

          {/* Summary card */}
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-5 mb-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#9CA3AF] font-semibold mb-1">Deine Rolle</div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4" style={{ color: ROLE_COLOR[data.role] }} />
                <span className="text-base font-semibold" style={{ color: ROLE_COLOR[data.role] }} data-testid="my-perm-role">
                  {ROLE_LABEL[data.role] || data.role}
                </span>
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#9CA3AF] font-semibold mb-1">Aktive Rechte</div>
              <div className="text-2xl font-light text-[#1A1D1B]" data-testid="my-perm-count">{data.effective_count}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#9CA3AF] font-semibold mb-1">Gruppen</div>
              <div className="flex flex-wrap gap-1">
                {data.groups.length === 0 ? (
                  <span className="text-xs text-[#9CA3AF]">Keine</span>
                ) : (
                  data.groups.map(g => (
                    <Badge key={g.group_id} variant="outline"
                      className="text-[10px] border-[#4A5D4E]/30"
                      style={{ borderColor: (g.color || '#4A5D4E') + '60', color: g.color || '#4A5D4E' }}
                      data-testid={`my-perm-group-${g.group_id}`}>
                      {g.name}
                    </Badge>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Effective caps grouped by category */}
          <div className="space-y-4">
            {Object.entries(byCategory).map(([cat, list]) => (
              <div key={cat} className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
                <div className="px-4 py-2 bg-[#FAFAF9] border-b border-[#E2E4E0]">
                  <span className="text-[11px] font-semibold text-[#6B7280] uppercase tracking-wider">
                    {CATEGORY_LABEL[cat] || cat} <span className="font-normal">({list.length})</span>
                  </span>
                </div>
                <div className="divide-y divide-[#F5F4F0]">
                  {list.map(({ cap, label, sources }) => (
                    <div key={cap} className="px-4 py-2.5 flex items-start gap-3" data-testid={`my-perm-cap-${cap}`}>
                      <ShieldCheck className="w-3.5 h-3.5 text-[#4A5D4E] mt-0.5 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-[#1A1D1B]">{label}</div>
                        <code className="text-[10px] text-[#9CA3AF]">{cap}</code>
                      </div>
                      <div className="flex flex-wrap gap-1 justify-end">
                        {sources.map((s, i) => {
                          if (s.type === 'role') return (
                            <span key={i} className="text-[9px] px-1.5 py-0.5 rounded bg-[#1A1D1B]/5 text-[#1A1D1B] font-medium flex items-center gap-1">
                              <Lock className="w-2.5 h-2.5" />Rolle
                            </span>
                          );
                          if (s.type === 'group') return (
                            <span key={i} className="text-[9px] px-1.5 py-0.5 rounded font-medium flex items-center gap-1"
                              style={{ background: (s.color || '#4A5D4E') + '15', color: s.color || '#4A5D4E' }}>
                              <Layers className="w-2.5 h-2.5" />{s.label}
                            </span>
                          );
                          return (
                            <span key={i} className="text-[9px] px-1.5 py-0.5 rounded bg-[#C87967]/10 text-[#C87967] font-medium flex items-center gap-1">
                              <Clock className="w-2.5 h-2.5" />
                              Persönlich{s.expires_at ? ` (bis ${new Date(s.expires_at).toLocaleDateString('de-DE')})` : ''}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {enriched.length === 0 && (
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 text-center text-sm text-[#9CA3AF]">
                Keine aktiven Berechtigungen — kontaktiere deinen Admin.
              </div>
            )}
          </div>

          <div className="mt-8 p-4 bg-[#F3F4F1] border border-[#E2E4E0] rounded-xl text-[11px] text-[#6B7280]">
            <KeyRound className="w-3.5 h-3.5 inline mr-1 align-text-bottom" />
            Berechtigungen werden aus drei Quellen kombiniert: <strong>Rolle</strong> (System-Defaults),
            <strong> Gruppen</strong> (Gruppen-Mitgliedschaft) und <strong>Persönlich</strong> (von Admin direkt zugewiesen).
            Direkte Verweigerungen überschreiben alles. Änderungen kann nur ein Administrator vornehmen.
          </div>
        </div>
      </div>
    </div>
  );
}

const CATEGORY_LABEL = {
  module: 'Module sichtbar',
  news: 'News & Kommunikation',
  meetings: 'Meetings',
  chat: 'Chat',
  documents: 'Dokumente & Whiteboard',
  scheduling: 'Terminplanung',
  surveys: 'Umfragen',
  tasks: 'Aufgaben',
  admin: 'Administration',
  global: 'Allgemein',
};
