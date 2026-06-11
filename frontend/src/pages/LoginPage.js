import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Workflow, Mail, Lock, ShieldCheck } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

function formatApiError(detail) {
  if (detail == null) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(e => e?.msg || JSON.stringify(e)).join(" ");
  if (detail?.msg) return detail.msg;
  return String(detail);
}

export default function LoginPage() {
  const { login, verifyTotp, setUser } = useAuth();
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [changePasswordOpen, setChangePasswordOpen] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  // iter 188 — 2FA challenge state
  const [totpChallenge, setTotpChallenge] = useState(null); // { token, email }
  const [totpCode, setTotpCode] = useState('');
  const [totpMode, setTotpMode] = useState('totp'); // 'totp' | 'recovery'
  const [totpVerifying, setTotpVerifying] = useState(false);
  // iter 273 — Azure SSO surface
  const [ssoAzure, setSsoAzure] = useState({ enabled: false, button_label: 'Mit Microsoft anmelden' });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get('/auth/sso/azure/status');
        if (!cancelled) setSsoAzure({
          enabled: !!data.enabled,
          button_label: data.button_label || 'Mit Microsoft anmelden',
        });
      } catch { /* ignore — feature simply stays hidden */ }
    })();
    // Surface error message returned by /auth/sso/azure/callback redirects
    const ssoErr = searchParams.get('sso_error');
    if (ssoErr) {
      const map = {
        disabled: 'SSO ist derzeit nicht aktiv.',
        missing_params: 'SSO-Antwort unvollständig.',
        state_mismatch: 'SSO-Sicherheitsprüfung fehlgeschlagen. Bitte erneut versuchen.',
        server_error: 'Server-Fehler bei der SSO-Anmeldung.',
      };
      setError(map[ssoErr] || ssoErr.replace(/\+/g, ' '));
      // remove the param from the URL so a refresh doesn't keep showing the banner
      const next = new URLSearchParams(searchParams);
      next.delete('sso_error');
      setSearchParams(next, { replace: true });
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await login(email, password);
      if (data?.totp_required) {
        setTotpChallenge({ token: data.challenge_token, email: data.user_email });
      } else if (data?.must_change_password) {
        setChangePasswordOpen(true);
      } else {
        // Iter 267 — wenn von Session-Expiry-Banner gekommen, zur Original-URL zurück
        let returnTo = '/schedule';
        try {
          const stored = sessionStorage.getItem('mf:return_to');
          if (stored && stored !== '/login' && !stored.startsWith('/auth/')) {
            returnTo = stored;
            sessionStorage.removeItem('mf:return_to');
          }
        } catch { /* ignore */ }
        navigate(returnTo, { replace: true });
      }
    } catch (err) {
      // iter 170 — Provide a useful error message instead of a dead "somethingWentWrong" i18n key.
      // Priority: backend `detail` → HTTP status code → network error → generic fallback.
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;
      const formatted = formatApiError(detail);
      let msg;
      if (formatted) {
        msg = formatted;
      } else if (status === 401 || status === 403) {
        msg = t('invalidCredentials') || 'E-Mail oder Passwort ist falsch';
      } else if (status === 429) {
        msg = 'Zu viele Versuche. Bitte warte einen Moment.';
      } else if (status >= 500) {
        msg = 'Server-Fehler (' + status + '). Bitte später erneut versuchen.';
      } else if (err?.code === 'ERR_NETWORK' || err?.message?.toLowerCase().includes('network')) {
        msg = 'Keine Verbindung. Prüfe deine Internetverbindung.';
      } else {
        msg = t('somethingWentWrong');
      }
      setError(msg);
      // Console trace for iPhone Safari debugging (visible in remote Web Inspector)
      if (typeof console !== 'undefined') {
        // eslint-disable-next-line no-console
        console.error('[LoginError]', { status, detail, code: err?.code, message: err?.message });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async () => {
    // Iter 379 — Erzwungener Passwort-Wechsel beim Login.
    // Strikte Policy-Validierung (8 Zeichen + 4-aus-4) wird vom Backend
    // durchgesetzt. Hier nur die UI-Pre-Checks für schnelles Feedback.
    if (!password) { toast.error('Bitte aktuelles (temporaeres) Passwort eingeben'); return; }
    const SPECIAL = /[!@#$%^&*()_+\-=[\]{};:'",.<>/?\\|`~]/;
    if (newPassword.length < 8 || !/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) ||
        !/\d/.test(newPassword) || !SPECIAL.test(newPassword)) {
      toast.error('Passwort muss min. 8 Zeichen + je 1 Gross-/Kleinbuchstabe, Ziffer und Sonderzeichen enthalten');
      return;
    }
    if (newPassword !== confirmPassword) { toast.error('Passwörter stimmen nicht überein'); return; }
    setChangingPassword(true);
    try {
      await api.post('/auth/change-password', {
        current_password: password,
        new_password: newPassword,
        new_password_confirm: confirmPassword,
      });
      toast.success('Passwort geändert!');
      setChangePasswordOpen(false);
      // Now log in with new password to set user in context
      const data = await login(email, newPassword);
      setUser(data);
      navigate('/schedule', { replace: true });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler');
    } finally { setChangingPassword(false); }
  };

  const handleGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/schedule';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleAzureSso = () => {
    // Hard navigate — backend issues a 302 to Microsoft and sets HttpOnly
    // state+verifier cookies. Using window.location ensures cookies stick
    // across the cross-origin OAuth round-trip.
    const backend = process.env.REACT_APP_BACKEND_URL;
    window.location.href = `${backend}/api/auth/sso/azure/login`;
  };

  return (
    <div className="min-h-screen flex" style={{ background: '#F9F9F8' }}>
      <div className="hidden lg:flex lg:w-1/2 items-center justify-center p-12" style={{ background: 'linear-gradient(135deg, #4A5D4E 0%, #3E4E42 100%)' }}>
        <div className="text-white max-w-md animate-fade-in">
          <div className="flex items-center gap-3 mb-8">
            <Workflow className="w-10 h-10" />
            <span className="text-3xl font-light tracking-tight" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
          </div>
          <h1 className="text-4xl font-light tracking-tight leading-tight mb-4" style={{ fontFamily: 'Manrope' }}>
            {t('heroTitle')}
          </h1>
          <p className="text-white/70 text-base leading-relaxed whitespace-pre-line">
            {t('heroDesc')}
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm animate-fade-in">
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <Workflow className="w-7 h-7 text-[#4A5D4E]" />
            <span className="text-xl font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
          </div>

          <h2 className="text-2xl font-medium tracking-tight mb-1" style={{ fontFamily: 'Manrope' }}>{t('signIn')}</h2>
          <p className="text-[#9CA3AF] text-sm mb-8">{t('welcomeBack')}</p>

          {error && <div className="bg-[#C87967]/10 text-[#C87967] text-sm p-3 rounded-lg mb-4" data-testid="login-error">{error}</div>}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5">
                {t('email')} <span className="text-[10px] font-normal normal-case opacity-70">oder Personalnummer</span>
              </Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input
                  data-testid="login-email-input"
                  /* Iter 379 — Type von "email" auf "text" umstellen, damit
                     User ohne dienstliche E-Mail ihre Personalnummer eingeben
                     können. Browser-Native Email-Validierung wuerde sonst die
                     Personalnummer als ungültig kennzeichnen. */
                  type="text"
                  inputMode="email"
                  autoComplete="username"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="name@firma.de oder P-12345"
                  className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] focus:ring-[#4A5D4E] rounded-xl h-11"
                  required
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">{t('password')}</Label>
                <Link to="/forgot-password" className="text-xs text-[#4A5D4E] hover:underline" data-testid="forgot-password-link">{t('forgotPassword')}</Link>
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input
                  data-testid="login-password-input"
                  type="password" value={password} onChange={e => setPassword(e.target.value)}
                  className="pl-10 border-[#E2E4E0] focus:border-[#4A5D4E] focus:ring-[#4A5D4E] rounded-xl h-11"
                  required
                />
              </div>
            </div>
            <Button
              data-testid="login-submit-button"
              type="submit" disabled={loading}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11 font-medium transition-all active:scale-95"
            >
              {loading ? '...' : t('signIn')}
            </Button>
          </form>

          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-[#E2E4E0]" />
            <span className="text-xs text-[#9CA3AF]">{t('or')}</span>
            <div className="flex-1 h-px bg-[#E2E4E0]" />
          </div>

          <Button
            data-testid="google-login-button"
            onClick={handleGoogle} variant="outline"
            className="w-full rounded-full h-11 border-[#E2E4E0] hover:bg-[#F3F4F1] font-medium transition-all"
          >
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
            {t('loginWithGoogle')}
          </Button>

          {ssoAzure.enabled && (
            <Button
              data-testid="azure-sso-login-button"
              onClick={handleAzureSso} variant="outline"
              className="w-full rounded-full h-11 border-[#E2E4E0] hover:bg-[#F3F4F1] font-medium transition-all mt-3"
            >
              <svg className="w-5 h-5 mr-2" viewBox="0 0 21 21" aria-hidden="true">
                <rect x="1" y="1" width="9" height="9" fill="#f25022"/>
                <rect x="11" y="1" width="9" height="9" fill="#7fba00"/>
                <rect x="1" y="11" width="9" height="9" fill="#00a4ef"/>
                <rect x="11" y="11" width="9" height="9" fill="#ffb900"/>
              </svg>
              {ssoAzure.button_label}
            </Button>
          )}

          <p className="text-center text-sm text-[#9CA3AF] mt-6">
            {t('noAccount')}{' '}
            <Link to="/register" className="text-[#4A5D4E] font-medium hover:underline" data-testid="register-link">{t('signUp')}</Link>
          </p>
        </div>
      </div>

      {/* Change Password Dialog */}
      <Dialog open={changePasswordOpen} onOpenChange={() => {}}>
        <DialogContent className="sm:max-w-[400px]" onPointerDownOutside={e => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-[#4A5D4E]" /> Passwort ändern
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-sm text-[#6B7280]">Bitte setzen Sie ein neues Passwort für Ihr Konto. Das temporaere Passwort kann danach nicht mehr verwendet werden.</p>
            <p className="text-[11px] text-[#9CA3AF] -mt-2">
              Mindestens 8 Zeichen, je 1 Gross-/Kleinbuchstabe, Ziffer und Sonderzeichen.
            </p>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('newPassword')}</Label>
              <Input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
                placeholder="Mindestens 8 Zeichen" className="border-[#E2E4E0] rounded-xl" data-testid="new-password-input" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('confirmPassword')}</Label>
              <Input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                placeholder="Passwort wiederholen" className="border-[#E2E4E0] rounded-xl" data-testid="confirm-password-input" />
            </div>
            <Button onClick={handleChangePassword} disabled={changingPassword}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11" data-testid="change-password-btn">
              {changingPassword ? '...' : 'Passwort ändern'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* iter 188 — 2FA Challenge Dialog */}
      <Dialog open={!!totpChallenge} onOpenChange={(o) => { if (!o) { setTotpChallenge(null); setTotpCode(''); } }}>
        <DialogContent className="sm:max-w-[400px]" onPointerDownOutside={e => e.preventDefault()} data-testid="totp-challenge-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-[#4A5D4E]" /> Zwei-Faktor-Authentifizierung
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <p className="text-sm text-[#6B7280]">
              {totpMode === 'totp'
                ? `Bitte den 6-stelligen Code aus Ihrer Authenticator-App für ${totpChallenge?.email || ''} eingeben.`
                : 'Bitte einen Wiederherstellungscode (Format AAAA-AAAA-AAAA) eingeben.'}
            </p>
            <Input
              data-testid="totp-code-input"
              value={totpCode}
              onChange={e => setTotpCode(e.target.value)}
              placeholder={totpMode === 'totp' ? '123456' : 'AAAA-AAAA-AAAA'}
              maxLength={totpMode === 'totp' ? 6 : 14}
              className="border-[#E2E4E0] rounded-xl text-center font-mono text-lg tracking-widest"
              autoFocus
              onKeyDown={async (e) => {
                if (e.key === 'Enter' && totpCode && !totpVerifying) {
                  e.preventDefault();
                  setTotpVerifying(true);
                  try {
                    await verifyTotp(totpChallenge.token, totpCode, totpMode);
                    setTotpChallenge(null);
                    setTotpCode('');
                    navigate('/schedule', { replace: true });
                  } catch (err) {
                    setError(formatApiError(err?.response?.data?.detail) || 'Code ungültig');
                  } finally { setTotpVerifying(false); }
                }
              }}
            />
            <Button
              data-testid="totp-verify-button"
              disabled={!totpCode || totpVerifying}
              onClick={async () => {
                setTotpVerifying(true);
                try {
                  await verifyTotp(totpChallenge.token, totpCode, totpMode);
                  setTotpChallenge(null);
                  setTotpCode('');
                  navigate('/schedule', { replace: true });
                } catch (err) {
                  setError(formatApiError(err?.response?.data?.detail) || 'Code ungültig');
                } finally { setTotpVerifying(false); }
              }}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11"
            >
              {totpVerifying ? 'Prüfe ...' : 'Bestätigen'}
            </Button>
            <button
              data-testid="totp-mode-toggle"
              type="button"
              className="w-full text-xs text-[#4A5D4E] hover:underline"
              onClick={() => { setTotpMode(m => m === 'totp' ? 'recovery' : 'totp'); setTotpCode(''); }}
            >
              {totpMode === 'totp' ? 'Stattdessen Wiederherstellungscode verwenden' : 'Zurück zum 6-stelligen Code'}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
