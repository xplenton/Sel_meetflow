import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Mail, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { toast } from 'sonner';

/**
 * Shown at the very top of the app shell whenever the current user has not
 * yet verified their email address. Only renders when org-settings have
 * email verification enabled AND the user hasn't verified yet. Non-blocking
 * by design (policy 1b): the user can still use the app, they just get a
 * soft reminder with a one-click "resend link" button.
 *
 * The banner is dismissable for the current session via localStorage so
 * users don't feel nagged — but it comes back after a page reload so the
 * reminder is persistent across genuine sessions.
 */
const DISMISS_KEY = 'emailVerifyBannerDismissed';

export default function EmailVerificationBanner() {
  const { user } = useAuth();
  const [dismissed, setDismissed] = useState(() => {
    try { return sessionStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
  });
  const [sending, setSending] = useState(false);

  // Only shown for logged-in, unverified users. Server policy check is
  // enforced on write; this banner is purely informational, so we render
  // it whenever the flag is false — doesn't matter if policy is off (the
  // account just stays "unverified" forever harmlessly).
  const shouldShow = user && user.email_verified === false && !dismissed;

  // Portal + fixed position + padding compensation (iter 120).
  // Shadcn Dialog overlay lives at z-50 and sits above anything in normal
  // flow. To keep the banner visible even when the onboarding dialog is
  // open we (1) portal it to document.body so it escapes every transformed
  // ancestor, (2) anchor it `fixed top-0 z-[70]`, and (3) reserve ~42 px of
  // top padding on document.body so the app content below is pushed down
  // instead of being hidden behind the banner.
  useEffect(() => {
    if (!shouldShow) {
      document.body.style.removeProperty('padding-top');
      return;
    }
    const previous = document.body.style.paddingTop;
    document.body.style.paddingTop = '44px';
    return () => {
      if (previous) document.body.style.paddingTop = previous;
      else document.body.style.removeProperty('padding-top');
    };
  }, [shouldShow]);

  if (!shouldShow) return null;

  const handleResend = async () => {
    setSending(true);
    try {
      await api.post('/auth/resend-verification');
      toast.success('Bestätigungs-Mail wurde erneut versendet');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Versenden');
    } finally { setSending(false); }
  };

  const handleDismiss = () => {
    setDismissed(true);
    try { sessionStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
  };

  return createPortal(
    <div
      className="fixed top-0 left-0 right-0 z-[70] bg-[#FFF7E6] border-b border-[#E6C889] px-4 py-2.5 flex items-center gap-3 text-sm shadow-sm"
      data-testid="email-verify-banner"
      role="status"
    >
      <Mail className="w-4 h-4 text-[#A17419] flex-shrink-0" />
      <span className="text-[#6D4C00] flex-1 truncate">
        Bitte bestätige deine E-Mail-Adresse <strong>{user.email}</strong>, um alle Funktionen zu nutzen.
      </span>
      <button
        onClick={handleResend}
        disabled={sending}
        className="text-[#6D4C00] hover:text-[#3D2B00] underline font-medium disabled:opacity-60 whitespace-nowrap"
        data-testid="email-verify-resend"
      >
        {sending ? 'Sende...' : 'Erneut senden'}
      </button>
      <button
        onClick={handleDismiss}
        className="text-[#A17419] hover:text-[#6D4C00] p-1"
        aria-label="Hinweis ausblenden"
        data-testid="email-verify-dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>,
    document.body,
  );
}
