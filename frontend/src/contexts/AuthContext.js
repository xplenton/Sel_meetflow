import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { clearAllUserCaches } from '../lib/cache';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // AuthCallback will exchange the session_id and establish the session first.
    if (window.location.hash?.includes('session_id=')) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get('/auth/me');
      setUser(data);
    } catch {
      // iter 167 — Do NOT log the user out on a /auth/me error if we already
      // have a populated user object. This prevents a Safari/iOS race where
      // the just-set auth cookie hasn't been persisted yet and the immediate
      // follow-up /auth/me returns 401, nuking the freshly-logged-in state.
      // Only treat "no session" as explicit logout (user === null, i.e. the
      // initial page load check).
      setUser(prev => (prev ? prev : false));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  // iter 152 — after a successful auth, silently refresh the push
  // subscription on the server. This repairs users whose old DB row
  // was stored with corrupt p256dh keys so pushes now actually deliver.
  useEffect(() => {
    if (!user?.user_id) return;
    (async () => {
      try {
        const { ensureServerHasPushSubscription } = await import('../lib/push');
        await ensureServerHasPushSubscription();
      } catch { /* silent — NewsPage can re-prompt if needed */ }
    })();
  }, [user?.user_id]);

  const loginFn = async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password });
    // iter 188 — 2FA challenge: surface to caller without setting user.
    if (data.totp_required) {
      return data;
    }
    if (data.must_change_password) {
      return data; // Don't set user yet - force password change first
    }
    setUser(data);
    // Iter 272 — Mark successful login timestamp so SessionExpiryBanner can
    // suppress false-positive 401 events from in-flight stale requests.
    try { sessionStorage.setItem('mf:last_login_ts', String(Date.now())); } catch { /* ignore */ }
    // iter 155 — /auth/login returns the raw user doc without the
    // server-computed `is_guest` flag. Fire `checkAuth()` right after
    // so the AuthContext state is fully populated and the
    // GuestWelcomeDialog can decide whether to show.
    checkAuth();
    return data;
  };

  const verifyTotpFn = async (challengeToken, code, mode = 'totp') => {
    const { data } = await api.post('/auth/2fa/verify-login', {
      challenge_token: challengeToken, code, mode,
    });
    setUser(data);
    checkAuth();
    return data;
  };

  const registerFn = async (email, password, name) => {
    const { data } = await api.post('/auth/register', { email, password, name });
    setUser(data);
    checkAuth();
    return data;
  };

  const logoutFn = async () => {
    // Iter 276 — flag so the axios 401 interceptor does not raise the
    // "Sitzung abgelaufen" banner during an intentional logout.
    window.__mf_logging_out = true;
    try { await api.post('/auth/logout'); } catch { /* server may be down — local logout still ok */ }
    // Iter 377 — Tell the Service Worker to drop its API response cache so
    // a stale `/api/auth/me` snapshot from the previous session cannot be
    // replayed on next page load. ROOT CAUSE of the production-only
    // "Abmelden funktioniert nicht" bug — sw-push.js was caching
    // /api/auth/me with stale-while-revalidate and replayed the logged-in
    // user object even after the cookies were cleared.
    try {
      if ('serviceWorker' in navigator) {
        const reg = await navigator.serviceWorker.getRegistration('/sw-push.js');
        if (reg && reg.active) {
          reg.active.postMessage({ type: 'clear-api-cache' });
        }
      }
      // Defense-in-depth: clear ALL Cache Storage entries reachable from JS.
      if ('caches' in window) {
        const keys = await caches.keys();
        await Promise.all(keys.map(k => caches.delete(k)));
      }
    } catch { /* ignore — fallback hard-reload still gives clean state */ }
    // Iter 374 — Full page reload on logout. Without this, all the other
    // React contexts (PermissionsContext, fetched user lists, cached data
    // in queries, open WebSocket connections, push subscriptions) keep
    // showing the previous user's data until the browser is manually
    // refreshed. User reported on Production: "Daten in Browser bleiben
    // vom altem user solange ich manuell nicht aktualisiere".
    //
    // We also clear all the user-scoped local/session storage. The auth
    // cookies (httpOnly) are cleared by the /auth/logout response above,
    // but Safari/Chromium can leave the cookie if the SameSite=None
    // attribute mismatches even slightly. As an extra safety net, we
    // also clear any non-httpOnly cookie we can see from JS so that any
    // post-redirect /auth/me will get a clean 401.
    try {
      // Iter 380 — zentraler Cache-Cleanup via lib/cache.js. Räumt
      // sessionStorage + alle `mf_*` localStorage-Keys (außer device-scoped
      // Lang/Install/Theme — definiert in cache.KEEP_ON_LOGOUT).
      clearAllUserCaches();
      // Extra: nuke any client-visible cookie just in case.
      document.cookie.split(';').forEach(c => {
        const name = c.split('=')[0].trim();
        if (name) {
          document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
        }
      });
    } catch { /* ignore */ }
    // Hard navigation: this drops every React provider, in-memory cache,
    // event subscriber, push/WebSocket handler and forces a clean app load
    // on the login screen. `replace()` ensures the previous SPA state is
    // not reachable via Back.
    window.location.replace('/login');
  };

  const googleLogin = async (sessionId) => {
    const { data } = await api.post('/auth/google-session', { session_id: sessionId });
    setUser(data);
    checkAuth();
    return data;
  };

  return (
    <AuthContext.Provider value={{ user, loading, login: loginFn, verifyTotp: verifyTotpFn, register: registerFn, logout: logoutFn, googleLogin, setUser, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() { return useContext(AuthContext); }
