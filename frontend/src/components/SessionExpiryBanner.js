import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { LogIn, X } from 'lucide-react';
import { Button } from './ui/button';

/**
 * Iter 267 — Session-Expiry-Banner.
 *
 * Wird angezeigt, wenn der api.js-Interceptor einen 401 nicht via /auth/refresh
 * heilen konnte (Refresh-Token abgelaufen oder ungültig). Statt den User
 * einfach hart auf /login zu redirecten, zeigen wir oben einen freundlichen
 * Banner mit Login-CTA an. Nach erfolgreichem Login kehrt der User zur
 * ursprünglichen URL zurück.
 *
 * Trigger: window.dispatchEvent(new CustomEvent('mf:session-expired'))
 * — wird von api.js gefeuert.
 *
 * Iter 272 — Heuristik zur Vermeidung von False-Positives:
 *   - Skip wenn auf /login, /auth/* oder /unsubscribe (= public Routes)
 *   - Skip in den ersten 3 Sek nach Page-Load (Race-Condition: Bootstrap-API-
 *     Calls können 401 zurückgeben, bevor /auth/me settled ist)
 *   - Skip in den ersten 5 Sek nach erfolgreichem Login (auch hier kann eine
 *     im Flight gewesene Request mit altem Token noch ein 401 produzieren)
 */
const PUBLIC_ROUTE_PREFIXES = ['/login', '/auth/', '/unsubscribe', '/diag/', '/p/', '/public/'];
const PAGE_LOAD_GRACE_MS = 3000;
const POST_LOGIN_GRACE_MS = 5000;

export default function SessionExpiryBanner() {
  const [visible, setVisible] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const [pageLoadedAt] = useState(() => Date.now());

  useEffect(() => {
    const onExpired = () => {
      // 1. Skip auf Public/Login-Routes — User soll dort kein Banner sehen.
      if (PUBLIC_ROUTE_PREFIXES.some(p => location.pathname.startsWith(p))) return;

      // 2. Grace-Period direkt nach Page-Load: Bootstrap-Calls (AuthContext,
      //    ChatUnreadContext, NotificationBell) feuern parallel los und können
      //    mit veraltetem Cookie ein 401 abbekommen, bevor /auth/me settled.
      if (Date.now() - pageLoadedAt < PAGE_LOAD_GRACE_MS) return;

      // 3. Grace-Period direkt nach Login: ein in-flight Request mit altem
      //    Token kann nach erfolgreichem Login noch ein 401 produzieren.
      try {
        const tsRaw = sessionStorage.getItem('mf:last_login_ts');
        const ts = tsRaw ? Number(tsRaw) : 0;
        if (ts && Date.now() - ts < POST_LOGIN_GRACE_MS) return;
      } catch { /* ignore */ }

      setVisible(true);
    };
    window.addEventListener('mf:session-expired', onExpired);
    return () => window.removeEventListener('mf:session-expired', onExpired);
  }, [location.pathname, pageLoadedAt]);

  if (!visible) return null;

  const goLogin = () => {
    // Aktuelle URL als Return-Target speichern (lib/auth-friendly: AuthCallback handles)
    const returnTo = location.pathname + location.search + location.hash;
    if (returnTo && returnTo !== '/login') {
      try { sessionStorage.setItem('mf:return_to', returnTo); } catch { /* ignore */ }
    }
    setVisible(false);
    navigate('/login');
  };

  return (
    <div
      className="fixed top-0 inset-x-0 z-[100] bg-amber-50 border-b border-amber-200 shadow-sm animate-fade-in"
      data-testid="session-expiry-banner"
      role="alert"
    >
      <div className="max-w-6xl mx-auto px-4 py-2 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-amber-800 text-xs">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-200 text-amber-900 text-[10px] font-bold">!</span>
          <span>Deine Sitzung ist abgelaufen. Bitte erneut anmelden, um weiterzuarbeiten.</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="sm"
            onClick={goLogin}
            className="h-7 text-[11px] bg-amber-600 hover:bg-amber-700 text-white"
            data-testid="session-expiry-login-btn"
          >
            <LogIn className="w-3 h-3 mr-1" /> Erneut anmelden
          </Button>
          <button
            type="button"
            onClick={() => setVisible(false)}
            className="text-amber-700 hover:text-amber-900"
            data-testid="session-expiry-dismiss"
            aria-label="Banner schließen"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

