import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import api from './api';
import { useAuth } from '../contexts/AuthContext';

/**
 * Capability-based permissions.
 *
 * Usage:
 *   const { can, role, caps } = usePermissions();
 *   if (can('news.create')) ...
 *
 *   <Can cap="news.approve"><Button>Freigeben</Button></Can>
 *   <Can cap="admin.manage_users" fallback={<p>Keine Berechtigung</p>}>...</Can>
 *
 * Iter 378 — localStorage-Cache (user_id-keyed) hydratet die capabilities,
 * role und roleDowngradedBy SYNCHRON beim Mount. Damit erscheinen Sidebar,
 * RoleDowngradeBanner & andere Consumer ohne sichtbares Loading-Flackern,
 * der Refetch im Hintergrund hält den Cache frisch.
 */

const PERMS_CACHE_KEY = 'mf_perms_provider_cache';

function loadCachedState(userId) {
  try {
    const raw = localStorage.getItem(PERMS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed) return null;
    // Cold-Boot-Fall: wir haben noch keine User-ID (AuthContext lädt gerade).
    // In diesem Fall vertrauen wir dem Cache initial; sobald der User
    // feststeht, validiert der useEffect und schreibt notfalls neu.
    if (userId && parsed.user_id !== userId) return null;
    return {
      caps: new Set(parsed.capabilities || []),
      role: parsed.role || 'member',
      legacyRole: parsed.legacy_role,
      groups: parsed.groups || [],
      roleDowngradedBy: parsed.role_downgraded_by || null,
      loading: false, // hydrated — Consumer rendern direkt korrekt
    };
  } catch { /* ignore */ }
  return null;
}

function persistCache(userId, data) {
  try {
    localStorage.setItem(PERMS_CACHE_KEY, JSON.stringify({
      user_id: userId,
      capabilities: Array.from(data.capabilities || []),
      role: data.role,
      legacy_role: data.legacy_role,
      groups: data.groups || [],
      role_downgraded_by: data.role_downgraded_by || null,
      ts: Date.now(),
    }));
  } catch { /* localStorage voll/disabled — non-fatal */ }
}

const PermissionsContext = createContext({
  caps: new Set(),
  role: 'member',
  groups: [],
  // Iter 372 — null when no group downgrades the user; otherwise an object
  // { group_name, override_role, original_role } so the UI banner can
  // explain why the user has less rights than expected.
  roleDowngradedBy: null,
  loading: true,
  refresh: () => {},
  can: () => false,
});

export function PermissionsProvider({ children }) {
  const { user } = useAuth();
  const [state, setState] = useState(() => {
    const cached = loadCachedState(user?.user_id);
    if (cached) return cached;
    return {
      caps: new Set(),
      role: 'member',
      groups: [],
      roleDowngradedBy: null,
      loading: true,
    };
  });

  const refresh = useCallback(async () => {
    if (!user) {
      // Not logged in - reset to defaults
      setState({
        caps: new Set(),
        role: 'member',
        groups: [],
        roleDowngradedBy: null,
        loading: false,
      });
      return;
    }
    try {
      const { data } = await api.get('/user/permissions');
      const next = {
        caps: new Set(data.capabilities || []),
        role: data.role || 'member',
        legacyRole: data.legacy_role,
        groups: data.groups || [],
        roleDowngradedBy: data.role_downgraded_by || null,
        loading: false,
      };
      setState(next);
      persistCache(user.user_id, data);
    } catch (err) {
      setState(s => ({ ...s, loading: false }));
    }
  }, [user]);

  useEffect(() => {
    // Cache eines fremden Users sofort verwerfen, sobald sich der User ändert.
    if (user?.user_id) {
      const cached = loadCachedState(user.user_id);
      if (cached) setState(cached);
    }
    refresh();
  }, [refresh, user?.user_id]);

  const can = useCallback((cap) => {
    if (!cap) return false;
    if (Array.isArray(cap)) return cap.some(c => state.caps.has(c));
    return state.caps.has(cap);
  }, [state.caps]);

  return (
    <PermissionsContext.Provider value={{ ...state, refresh, can }}>
      {children}
    </PermissionsContext.Provider>
  );
}

export function usePermissions() {
  return useContext(PermissionsContext);
}

/**
 * <Can cap="news.create">...</Can>   single cap
 * <Can anyOf={['news.approve','news.publish']}>...</Can>   any of
 * <Can cap="x" fallback={<NoAccess />}>...</Can>
 */
export function Can({ cap, anyOf, fallback = null, children }) {
  const { can } = usePermissions();
  const ok = anyOf ? can(anyOf) : can(cap);
  return ok ? <>{children}</> : <>{fallback}</>;
}
