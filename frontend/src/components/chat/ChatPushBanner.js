import { useEffect, useState } from 'react';
import { Bell, BellOff, X, Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { toast } from 'sonner';
import api from '../../lib/api';
import {
  isPushSupported,
  getPushSubscriptionStatus,
  subscribeToPush,
  ensureServerHasPushSubscription,
} from '../../lib/push';

const DISMISS_KEY = 'mf:chat-push-banner-dismissed';

/**
 * Iter 262 — Chat-Push-Banner
 *
 * Erscheint im ChatPage-Header für Nutzer, die noch keine Push-Subscription
 * haben oder noch nicht den Permission-Prompt gesehen haben.
 *
 * Verhalten:
 *  - Permission `default` (noch nie gefragt) → CTA "Push aktivieren"
 *  - Permission `granted` + Subscription fehlt auf Server → silent recovery
 *  - Permission `denied` → kleine Warnung mit Reset-Hinweis (kein erneuter Prompt möglich)
 *  - Bereits subscribed → nicht angezeigt
 *  - User klickt X → 30 Tage stumm (localStorage)
 */
export default function ChatPushBanner({ language = 'de' }) {
  const [status, setStatus] = useState(null); // { supported, permission, subscribed }
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Check dismiss state
    try {
      const t = Number(localStorage.getItem(DISMISS_KEY) || '0');
      const THIRTY_DAYS = 30 * 24 * 3600 * 1000;
      if (t && Date.now() - t < THIRTY_DAYS) {
        setDismissed(true);
        return;
      }
    } catch { /* ignore */ }

    if (!isPushSupported()) {
      setStatus({ supported: false });
      return;
    }
    (async () => {
      const s = await getPushSubscriptionStatus();
      setStatus(s);
      // Auto-recovery: granted but no sub on server → silently re-register
      if (s.permission === 'granted' && !s.subscribed) {
        const res = await ensureServerHasPushSubscription();
        if (res.ok) {
          setStatus({ ...s, subscribed: true });
        }
      }
    })();
  }, []);

  if (!status || dismissed) return null;
  if (status.subscribed) return null; // happy path — keine Anzeige
  if (!status.supported) return null;

  const enable = async () => {
    setBusy(true);
    try {
      await subscribeToPush();
      const fresh = await getPushSubscriptionStatus();
      setStatus(fresh);
      if (fresh.subscribed) {
        toast.success(language === 'de' ? 'Push aktiviert — du bekommst jetzt Chat-Benachrichtigungen.' : 'Push enabled');
      }
    } catch (e) {
      toast.error(e.message || (language === 'de' ? 'Aktivierung fehlgeschlagen' : 'Activation failed'));
      const fresh = await getPushSubscriptionStatus();
      setStatus(fresh);
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const { data } = await api.post('/chat/push/test', {});
      if (data?.result?.sent > 0) {
        toast.success(language === 'de' ? 'Test-Push gesendet — schau auf dein Gerät.' : 'Test push sent.');
      } else {
        toast.warning(language === 'de' ? 'Push abgesendet, aber keine Bestätigung vom Browser.' : 'Push sent, no ack.');
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || (language === 'de' ? 'Test fehlgeschlagen' : 'Test failed'));
    } finally {
      setTesting(false);
    }
  };

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* ignore */ }
    setDismissed(true);
  };

  // Denied-Fall: User hat in Browser-Settings abgelehnt
  if (status.permission === 'denied') {
    return (
      <div
        className="mx-3 mt-2 mb-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 flex items-center justify-between gap-2"
        data-testid="chat-push-banner-denied"
      >
        <div className="flex items-center gap-2 text-amber-800 text-xs">
          <BellOff className="w-4 h-4 shrink-0" />
          <span>
            {language === 'de'
              ? 'Push-Benachrichtigungen sind im Browser geblockt. Aktiviere sie in den Site-Einstellungen, um Chat-Nachrichten zu erhalten.'
              : 'Push notifications are blocked. Enable them in site settings to receive chat messages.'}
          </span>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="text-amber-700 hover:text-amber-900 shrink-0"
          data-testid="chat-push-banner-dismiss-denied"
          aria-label="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  // Default-Fall: noch nie gefragt
  return (
    <div
      className="mx-3 mt-2 mb-1 rounded-md border border-[#E2E4E0] bg-[#F3F4F1] px-3 py-2 flex items-center justify-between gap-2"
      data-testid="chat-push-banner"
    >
      <div className="flex items-center gap-2 text-[#1C1F1D] text-xs">
        <Bell className="w-4 h-4 shrink-0 text-[#4A5D4E]" />
        <span>
          {language === 'de'
            ? 'Aktiviere Push-Benachrichtigungen, damit dich neue Chat-Nachrichten auch erreichen, wenn die Seite geschlossen ist.'
            : 'Enable push notifications to receive chat messages while the page is closed.'}
        </span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {status.permission === 'granted' ? (
          <Button
            size="sm"
            variant="outline"
            onClick={sendTest}
            disabled={testing}
            className="h-7 text-[10px] px-2"
            data-testid="chat-push-banner-test"
          >
            {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : (language === 'de' ? 'Test senden' : 'Send test')}
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={enable}
            disabled={busy}
            className="h-7 text-[10px] px-2 bg-[#4A5D4E] hover:bg-[#3E4F40]"
            data-testid="chat-push-banner-enable"
          >
            {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : (language === 'de' ? 'Push aktivieren' : 'Enable push')}
          </Button>
        )}
        <button
          type="button"
          onClick={dismiss}
          className="text-[#6B7280] hover:text-[#1C1F1D]"
          data-testid="chat-push-banner-dismiss"
          aria-label="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
