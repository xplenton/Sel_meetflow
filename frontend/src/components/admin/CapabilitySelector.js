import { useState, useEffect, useMemo } from 'react';
import api from '../../lib/api';
import { Badge } from '../ui/badge';
import { Search, X, ChevronDown, ChevronRight, Info } from 'lucide-react';
import { Input } from '../ui/input';
import { useLanguage } from '../../contexts/LanguageContext';

const CATEGORY_LABELS = {
  module: 'Modul-Sichtbarkeit',
  news: 'News',
  meetings: 'Meetings',
  chat: 'Chat',
  documents: 'Dokumente & Whiteboard',
  scheduling: 'Terminplanung',
  surveys: 'Umfragen',
  tasks: 'Aufgaben',
  resources: 'Ressourcen & Catering',
  invoices: 'Rechnungen & Buchhaltung',
  fleet: 'Fuhrpark',
  admin: 'Admin',
  global: 'Global',
};

/**
 * CapabilitySelector — groups capabilities by category with search + category-toggle.
 *
 * iter 305: The "Modul-Sichtbarkeit" category is collapsed by default and
 * carries an explanatory hint, because module visibility is normally
 * controlled via the user's role. We also annotate every `view:*` cap with
 * a "source badge" listing the roles & sibling groups that ALREADY grant
 * this capability — so admins immediately see whether toggling here will
 * actually have any effect.
 *
 * Props:
 *   selected: string[] — selected capability keys
 *   onChange: (string[]) => void
 *   excludeGroupId?: string — when editing an existing group, skip itself in
 *                             the "Auch in Gruppe X"-badge so the badge
 *                             doesn't refer to the group being edited.
 */
export default function CapabilitySelector({ selected = [], onChange, testId = 'cap-selector', excludeGroupId }) {
  const { t } = useLanguage();
  const [all, setAll] = useState([]);
  const [roleDefaults, setRoleDefaults] = useState({}); // { roleName: [cap, ...] }
  const [groups, setGroups] = useState([]);             // [{ group_id, name, capabilities: [] }]
  const [filter, setFilter] = useState('');
  // Module category collapsed by default — that's the whole point of iter 305.
  const [collapsedCats, setCollapsedCats] = useState(() => new Set(['module']));

  useEffect(() => {
    api.get('/admin/capabilities').then(r => {
      setAll(r.data.capabilities || []);
      setRoleDefaults(r.data.role_defaults || {});
    }).catch(() => {});
    api.get('/admin/groups').then(r => setGroups(r.data || [])).catch(() => {});
  }, []);

  const selectedSet = new Set(selected);

  // Build a quick "where does cap X come from elsewhere?" index — only for
  // module caps. Keeps the per-checkbox render cheap.
  const sourceIndex = useMemo(() => {
    const idx = {}; // capKey -> { roles: [], groups: [{group_id,name}] }
    Object.entries(roleDefaults).forEach(([roleName, caps]) => {
      (caps || []).forEach(cap => {
        if (!cap.startsWith('view:')) return;
        (idx[cap] = idx[cap] || { roles: [], groups: [] }).roles.push(roleName);
      });
    });
    groups.forEach(g => {
      if (g.group_id === excludeGroupId) return;
      (g.capabilities || []).forEach(cap => {
        if (!cap.startsWith('view:')) return;
        (idx[cap] = idx[cap] || { roles: [], groups: [] }).groups.push({ group_id: g.group_id, name: g.name });
      });
    });
    return idx;
  }, [roleDefaults, groups, excludeGroupId]);

  const toggle = (k) => {
    const s = new Set(selectedSet);
    if (s.has(k)) s.delete(k);
    else s.add(k);
    onChange(Array.from(s));
  };

  const filtered = filter
    ? all.filter(c =>
        c.key.toLowerCase().includes(filter.toLowerCase())
        || c.label.toLowerCase().includes(filter.toLowerCase())
        || c.description.toLowerCase().includes(filter.toLowerCase()))
    : all;

  const byCategory = filtered.reduce((acc, c) => {
    (acc[c.category] = acc[c.category] || []).push(c);
    return acc;
  }, {});

  const toggleCategory = (caps) => {
    const keys = caps.map(c => c.key);
    const allSelected = keys.every(k => selectedSet.has(k));
    const s = new Set(selectedSet);
    if (allSelected) keys.forEach(k => s.delete(k));
    else keys.forEach(k => s.add(k));
    onChange(Array.from(s));
  };

  const toggleCollapse = (cat) => {
    const s = new Set(collapsedCats);
    if (s.has(cat)) s.delete(cat);
    else s.add(cat);
    setCollapsedCats(s);
  };

  return (
    <div className="border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid={testId}>
      <div className="p-2.5 border-b border-[#E2E4E0] bg-[#F9F9F8] flex items-center gap-2">
        <Search className="w-3.5 h-3.5 text-[#9CA3AF]" />
        <Input value={filter} onChange={e => setFilter(e.target.value)}
          placeholder="Suche Rechte..."
          className="border-0 bg-transparent h-7 text-xs p-0 focus-visible:ring-0"
          data-testid={`${testId}-search`} />
        {selected.length > 0 && (
          <Badge className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E]">{selected.length}</Badge>
        )}
        {selected.length > 0 && (
          <button onClick={() => onChange([])} className="text-[#9CA3AF] hover:text-[#C87967]" title="Alle abwählen"
            data-testid={`${testId}-clear`}>
            <X className="w-3 h-3" />
          </button>
        )}
      </div>
      <div className="max-h-[320px] overflow-y-auto p-2 space-y-3">
        {Object.entries(byCategory).map(([cat, caps]) => {
          const allInCat = caps.every(c => selectedSet.has(c.key));
          // While searching we expand everything so users can see hits.
          const isCollapsed = !filter && collapsedCats.has(cat);
          const isModuleCat = cat === 'module';

          return (
            <div key={cat} data-testid={`${testId}-section-${cat}`}>
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <button onClick={() => toggleCollapse(cat)}
                  className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-[#4A5D4E] hover:text-[#3E4E42]"
                  data-testid={`${testId}-collapse-${cat}`}>
                  {isCollapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  {CATEGORY_LABELS[cat] || cat} ({caps.length})
                </button>
                <button onClick={() => toggleCategory(caps)}
                  className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-[#6B7280] hover:text-[#4A5D4E]"
                  data-testid={`${testId}-cat-${cat}`}
                  title={allInCat ? 'Alle abwaehlen' : 'Alle auswählen'}>
                  <input type="checkbox" readOnly checked={allInCat}
                    className="w-3 h-3 rounded border-[#E2E4E0] text-[#4A5D4E] pointer-events-none" />
                  {allInCat ? 'alle' : 'alle wählen'}
                </button>
              </div>

              {isModuleCat && !isCollapsed && (
                <div className="mb-2 mx-1 p-2 rounded-lg bg-[#FFF8E7] border border-[#F4E4B8] flex gap-2 items-start"
                  data-testid={`${testId}-module-hint`}>
                  <Info className="w-3.5 h-3.5 text-[#A07A1F] mt-0.5 shrink-0" />
                  <p className="text-[10px] leading-relaxed text-[#6B5316]">
                    Modul-Sichtbarkeit wird normalerweise über die <strong>Rolle</strong> des Users gesteuert.
                    Hier nur überschreiben, wenn diese Gruppe gezielt ein zusätzliches Modul freischalten oder ausblenden soll.
                  </p>
                </div>
              )}

              {!isCollapsed && (
                <div className="space-y-0.5 pl-4">
                  {caps.map(c => {
                    const src = isModuleCat ? sourceIndex[c.key] : null;
                    const hasSource = src && (src.roles.length > 0 || src.groups.length > 0);
                    return (
                      <label key={c.key} className="flex items-start gap-2 py-1 cursor-pointer hover:bg-[#F3F4F1] rounded px-1"
                        data-testid={`${testId}-cap-${c.key}`}>
                        <input type="checkbox" checked={selectedSet.has(c.key)} onChange={() => toggle(c.key)}
                          className="w-3.5 h-3.5 rounded border-[#E2E4E0] text-[#4A5D4E] focus:ring-[#4A5D4E] mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs text-[#1C1F1D]">{c.label}</div>
                          <div className="text-[9px] text-[#9CA3AF] truncate">{c.description}</div>
                          {hasSource && (
                            <div className="flex flex-wrap gap-1 mt-0.5" data-testid={`${testId}-source-${c.key}`}>
                              {src.roles.map(r => (
                                <span key={`r-${r}`}
                                  className="text-[8px] uppercase tracking-wider px-1 py-0.5 rounded bg-[#4A5D4E]/10 text-[#4A5D4E]"
                                  title={`Bereits durch Rolle "${r}" gesetzt`}>
                                  Rolle: {r}
                                </span>
                              ))}
                              {src.groups.slice(0, 3).map(g => (
                                <span key={`g-${g.group_id}`}
                                  className="text-[8px] uppercase tracking-wider px-1 py-0.5 rounded bg-[#D4A373]/15 text-[#8B5E2B]"
                                  title={`Bereits in Gruppe "${g.name}" gesetzt`}>
                                  Gruppe: {g.name}
                                </span>
                              ))}
                              {src.groups.length > 3 && (
                                <span className="text-[8px] text-[#9CA3AF]">+{src.groups.length - 3} Gruppen</span>
                              )}
                            </div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
        {filter && filtered.length === 0 && (
          <div className="text-xs text-[#9CA3AF] text-center py-4">{t('noMatches')}</div>
        )}
      </div>
    </div>
  );
}
