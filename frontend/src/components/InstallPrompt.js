import { useEffect, useState } from 'react';
import { Download, X, Smartphone, Share, Plus } from 'lucide-react';

const VISITS_KEY = 'meetflow_visit_count';
const DISMISSED_KEY = 'meetflow_install_dismissed';
const LAST_VISIT_DAY_KEY = 'meetflow_last_visit_day';
const MIN_VISITS = 2;

/**
 * PWA install prompt.
 * - Captures `beforeinstallprompt` (Chrome/Edge/Android)
 * - For iOS Safari (no native prompt) shows manual instructions after MIN_VISITS
 * - Persists dismissal in localStorage
 * - Registers the service worker early so offline fallback + push work
 */
export default function InstallPrompt() {
  const [deferredEvt, setDeferredEvt] = useState(null);
  const [visible, setVisible] = useState(false);
  const [iosInstructions, setIosInstructions] = useState(false);

  useEffect(() => {
    // Register SW (used for offline + push)
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw-push.js').catch(() => undefined);
    }

    // Clear app badge when user opens the app (they've seen notifications)
    const clearBadge = () => {
      if ('clearAppBadge' in navigator) navigator.clearAppBadge().catch(() => undefined);
    };
    clearBadge();
    window.addEventListener('focus', clearBadge);

    // Already installed?
    const standalone = window.matchMedia('(display-mode: standalone)').matches
      || window.navigator.standalone === true;
    if (standalone) {
      return () => window.removeEventListener('focus', clearBadge);
    }

    const dismissed = localStorage.getItem(DISMISSED_KEY);
    if (dismissed) {
      // Re-show after 14 days
      const when = parseInt(dismissed, 10);
      if (!Number.isNaN(when) && Date.now() - when < 14 * 24 * 60 * 60 * 1000) return;
    }

    const visits = (() => {
      // iter 315 — count one visit PER calendar day instead of per page load,
      // so the prompt waits until the user has actually returned to the app
      // on a second day (matches the "2x / Tag" intent in the spec).
      const today = new Date().toISOString().slice(0, 10);
      const lastDay = localStorage.getItem(LAST_VISIT_DAY_KEY);
      const current = parseInt(localStorage.getItem(VISITS_KEY) || '0', 10) || 0;
      if (lastDay === today) return current;
      const next = current + 1;
      localStorage.setItem(VISITS_KEY, String(next));
      localStorage.setItem(LAST_VISIT_DAY_KEY, today);
      return next;
    })();

    const onBip = (e) => {
      e.preventDefault();
      setDeferredEvt(e);
      if (visits >= MIN_VISITS) setVisible(true);
    };
    const onInstalled = () => {
      // OS-level install completed — hide the banner and record it so we
      // don't pester the user again.
      setVisible(false);
      setDeferredEvt(null);
      localStorage.setItem(DISMISSED_KEY, String(Date.now()));
    };
    window.addEventListener('beforeinstallprompt', onBip);
    window.addEventListener('appinstalled', onInstalled);

    // iOS fallback
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    if (isIOS && visits >= MIN_VISITS) {
      setIosInstructions(true);
      setVisible(true);
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', onBip);
      window.removeEventListener('appinstalled', onInstalled);
      window.removeEventListener('focus', clearBadge);
    };
  }, []);

  const dismiss = () => {
    localStorage.setItem(DISMISSED_KEY, String(Date.now()));
    setVisible(false);
  };

  const install = async () => {
    if (!deferredEvt) return;
    try {
      deferredEvt.prompt();
      const { outcome } = await deferredEvt.userChoice;
      if (outcome === 'accepted') {
        setVisible(false);
      }
    } catch (e) { /* ignore */ }
    setDeferredEvt(null);
  };

  if (!visible) return null;

  return (
    <div
      className="fixed bottom-20 md:bottom-4 left-4 right-4 sm:left-auto sm:w-[380px] z-[70] bg-white border border-[#E2E4E0] rounded-2xl shadow-xl p-4 animate-fade-in"
      style={{ marginBottom: 'env(safe-area-inset-bottom)' }}
      data-testid="install-prompt"
    >
      <button onClick={dismiss}
        className="absolute top-2 right-2 text-[#9CA3AF] hover:text-[#1C1F1D] p-1"
        aria-label="Schließen"
        data-testid="install-prompt-dismiss">
        <X className="w-4 h-4" />
      </button>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
          <Smartphone className="w-5 h-5 text-[#4A5D4E]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[#1C1F1D]">MeetFlow installieren</p>
          {iosInstructions ? (
            <p className="text-xs text-[#6B7280] mt-1 leading-relaxed">
              In Safari unten auf{' '}
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#F3F4F1] align-middle">
                <Share className="w-3 h-3" /> Teilen
              </span>
              {' '}tippen und{' '}
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#F3F4F1] align-middle">
                <Plus className="w-3 h-3" /> Zum Home-Bildschirm
              </span>
              {' '}wählen — direkter App-Zugriff &amp; Push.
            </p>
          ) : (
            <p className="text-xs text-[#6B7280] mt-1">
              Schneller Zugriff, Push-Benachrichtigungen und Offline-Hinweis.
            </p>
          )}
          <div className="flex items-center gap-2 mt-3">
            {!iosInstructions && deferredEvt && (
              <button onClick={install}
                className="inline-flex items-center gap-1.5 text-xs text-white bg-[#4A5D4E] hover:bg-[#3E4E42] rounded-full px-3 py-1.5"
                data-testid="install-prompt-install">
                <Download className="w-3.5 h-3.5" /> Installieren
              </button>
            )}
            <button onClick={dismiss}
              className="text-xs text-[#6B7280] hover:text-[#1C1F1D] px-2 py-1.5"
              data-testid="install-prompt-later">
              Spaeter
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
