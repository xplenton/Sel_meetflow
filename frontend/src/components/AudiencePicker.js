/**
 * AudiencePicker — reusable targeting UI for News & Surveys.
 *
 * Supports three mutually-exclusive top-level modes:
 *   1. "all"     → target_all=true
 *   2. "groups"  → target_all=false, target_groups=[...]
 *   3. "users"   → target_all=false, target_user_ids=[...]
 *
 * The picker handles its own user search (debounced, /chat/users/for-targeting).
 * Groups are fed in as prop (parent already fetches them).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Users, Globe, User as UserIcon, Search, X, Check } from 'lucide-react';
import api from '../lib/api';

export default function AudiencePicker({
  targetAll, onTargetAllChange,
  targetGroups, onTargetGroupsChange,
  targetUserIds, onTargetUserIdsChange,
  groups = [],
  isDE = true,
}) {
  // Local mode state — can't derive purely from props because an empty
  // `targetUserIds` array is ambiguous (could be unselected-users OR groups-mode).
  // Initialise from props so edit-flow hydrates correctly.
  const initialMode = targetAll
    ? 'all'
    : (targetUserIds && targetUserIds.length > 0 ? 'users' : 'groups');
  const [mode, setMode] = useState(initialMode);

  const [userSearch, setUserSearch] = useState('');
  const [userResults, setUserResults] = useState([]);
  const [selectedUsers, setSelectedUsers] = useState([]); // objects for chip rendering
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);

  // Hydrate selectedUsers from initial target_user_ids
  useEffect(() => {
    if (targetUserIds && targetUserIds.length > 0 && selectedUsers.length === 0) {
      api.get('/chat/users/for-targeting', { params: { limit: 200 } })
        .then(({ data }) => {
          const byId = new Map(data.map(u => [u.user_id, u]));
          setSelectedUsers(targetUserIds.map(id => byId.get(id) || { user_id: id, name: id }));
        })
        .catch(() => {
          setSelectedUsers(targetUserIds.map(id => ({ user_id: id, name: id })));
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced user search
  useEffect(() => {
    if (mode !== 'users') return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      api.get('/chat/users/for-targeting', { params: { search: userSearch, limit: 25 } })
        .then(({ data }) => setUserResults(data))
        .catch(() => setUserResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [userSearch, mode]);

  const switchMode = (next) => {
    setMode(next);
    if (next === 'all') {
      onTargetAllChange(true);
      onTargetGroupsChange([]);
      onTargetUserIdsChange([]);
      setSelectedUsers([]);
    } else if (next === 'groups') {
      onTargetAllChange(false);
      onTargetUserIdsChange([]);
      setSelectedUsers([]);
    } else {
      onTargetAllChange(false);
      onTargetGroupsChange([]);
    }
  };

  const toggleGroup = (groupId) => {
    const cur = targetGroups || [];
    onTargetGroupsChange(cur.includes(groupId) ? cur.filter(g => g !== groupId) : [...cur, groupId]);
  };

  const addUser = (u) => {
    if (!selectedUsers.find(s => s.user_id === u.user_id)) {
      const next = [...selectedUsers, u];
      setSelectedUsers(next);
      onTargetUserIdsChange(next.map(x => x.user_id));
    }
  };
  const removeUser = (uid) => {
    const next = selectedUsers.filter(s => s.user_id !== uid);
    setSelectedUsers(next);
    onTargetUserIdsChange(next.map(x => x.user_id));
  };

  const modeButtons = useMemo(() => [
    { key: 'all', label: isDE ? 'Alle' : 'Everyone', icon: Globe, desc: isDE ? 'Alle Nutzer' : 'All users' },
    { key: 'groups', label: isDE ? 'Gruppen' : 'Groups', icon: Users, desc: isDE ? 'Bestimmte Gruppen' : 'Specific groups' },
    { key: 'users', label: isDE ? 'Nutzer' : 'Users', icon: UserIcon, desc: isDE ? 'Einzelne Nutzer' : 'Individual users' },
  ], [isDE]);

  const summary = () => {
    if (mode === 'all') return isDE ? 'Sichtbar für alle Nutzer' : 'Visible to everyone';
    if (mode === 'groups') {
      const n = (targetGroups || []).length;
      return n === 0 ? (isDE ? 'Keine Gruppe ausgewählt' : 'No group selected') :
        (isDE ? `${n} Gruppe${n === 1 ? '' : 'n'} ausgewählt` : `${n} group${n === 1 ? '' : 's'} selected`);
    }
    const n = selectedUsers.length;
    return n === 0 ? (isDE ? 'Noch keine Nutzer ausgewählt' : 'No users selected') :
      (isDE ? `${n} Nutzer ausgewählt` : `${n} user${n === 1 ? '' : 's'} selected`);
  };

  return (
    <div className="space-y-3" data-testid="audience-picker">
      <div className="grid grid-cols-3 gap-1.5">
        {modeButtons.map(mb => {
          const Icon = mb.icon;
          const active = mode === mb.key;
          return (
            <button
              key={mb.key}
              type="button"
              onClick={() => switchMode(mb.key)}
              className={`flex flex-col items-center gap-1 px-2 py-2.5 rounded-xl border transition-colors ${active ? 'border-[#4A5D4E] bg-[#4A5D4E] text-white' : 'border-[#E2E4E0] bg-white text-[#4B5563] hover:border-[#4A5D4E]/40'}`}
              data-testid={`audience-mode-${mb.key}`}
            >
              <Icon className="w-4 h-4" />
              <span className="text-[11px] font-medium">{mb.label}</span>
              <span className={`text-[9px] ${active ? 'text-white/70' : 'text-[#9CA3AF]'} leading-tight text-center`}>{mb.desc}</span>
            </button>
          );
        })}
      </div>

      <p className="text-[11px] text-[#6B7280]" data-testid="audience-summary">{summary()}</p>

      {mode === 'groups' && (
        <div className="border border-[#E2E4E0] rounded-xl p-2.5" data-testid="audience-groups-panel">
          {groups.length === 0 ? (
            <p className="text-xs text-[#9CA3AF] text-center py-2">{isDE ? 'Keine Gruppen vorhanden' : 'No groups available'}</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {groups.map(g => {
                const active = (targetGroups || []).includes(g.group_id);
                return (
                  <button
                    key={g.group_id}
                    type="button"
                    onClick={() => toggleGroup(g.group_id)}
                    className={`flex items-center gap-1 text-[11px] rounded-full px-2.5 py-1 transition-colors ${active ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#E2E4E0]'}`}
                    data-testid={`audience-group-${g.group_id}`}
                  >
                    {active && <Check className="w-3 h-3" />}
                    {g.name}
                    {typeof g.member_count === 'number' && (
                      <span className={`text-[9px] ${active ? 'text-white/70' : 'text-[#9CA3AF]'}`}>
                        ({g.member_count})
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {mode === 'users' && (
        <div className="border border-[#E2E4E0] rounded-xl p-2.5 space-y-2" data-testid="audience-users-panel">
          {selectedUsers.length > 0 && (
            <div className="flex flex-wrap gap-1" data-testid="audience-selected-chips">
              {selectedUsers.map(u => (
                <span key={u.user_id} className="flex items-center gap-1 text-[11px] bg-[#4A5D4E] text-white rounded-full pl-2 pr-1 py-0.5" data-testid={`audience-chip-${u.user_id}`}>
                  {u.name}
                  <button type="button" onClick={() => removeUser(u.user_id)} className="hover:bg-white/20 rounded-full p-0.5">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF] pointer-events-none" />
            <input
              type="text"
              value={userSearch}
              onChange={e => setUserSearch(e.target.value)}
              placeholder={isDE ? 'Nutzer suchen (Name oder E-Mail)...' : 'Search users (name or email)...'}
              className="w-full pl-8 pr-2 py-1.5 text-xs border border-[#E2E4E0] rounded-lg focus:outline-none focus:border-[#4A5D4E]"
              data-testid="audience-user-search"
            />
          </div>
          <div className="max-h-48 overflow-y-auto space-y-0.5">
            {loading && <p className="text-[11px] text-[#9CA3AF] text-center py-2">{isDE ? 'Suche...' : 'Searching...'}</p>}
            {!loading && userResults.length === 0 && userSearch && (
              <p className="text-[11px] text-[#9CA3AF] text-center py-2">{isDE ? 'Keine Nutzer gefunden' : 'No users found'}</p>
            )}
            {!loading && userResults.map(u => {
              const already = selectedUsers.find(s => s.user_id === u.user_id);
              return (
                <button
                  key={u.user_id}
                  type="button"
                  onClick={() => addUser(u)}
                  disabled={!!already}
                  className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-left transition-colors ${already ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[#F3F4F1]'}`}
                  data-testid={`audience-user-option-${u.user_id}`}
                >
                  <div className="w-6 h-6 rounded-full bg-[#4A5D4E]/15 text-[#4A5D4E] flex items-center justify-center text-[10px] font-bold flex-shrink-0">
                    {(u.name || u.email || '?').slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-medium text-[#1C1F1D] truncate">{u.name}</p>
                    {u.email && <p className="text-[10px] text-[#9CA3AF] truncate">{u.email}</p>}
                  </div>
                  {already && <Check className="w-3 h-3 text-[#4A5D4E]" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
