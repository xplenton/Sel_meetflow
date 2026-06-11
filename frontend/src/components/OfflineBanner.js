import { useEffect, useState } from 'react';
import { WifiOff, Wifi, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { getQueueCount, onQueueChange, flushQueue } from '../lib/offlineQueue';

/**
 * Thin floating banner that appears when the browser reports the device is
 * offline. It also keeps the user informed that their actions are not lost:
 * pending writes are stashed locally and shown as a small counter. When the
 * connection returns, the queue is drained and a success toast is fired.
 */
export default function OfflineBanner() {
  const [online, setOnline] = useState(navigator.onLine);
  const [queued, setQueued] = useState(getQueueCount());

  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      // Give the browser a moment to settle its connection, then flush
      setTimeout(async () => {
        const before = getQueueCount();
        if (before > 0) {
          const { flushed } = await flushQueue();
          if (flushed > 0) {
            toast.success(
              flushed === 1
                ? 'Ausstehende Aktion gesendet'
                : `${flushed} ausstehende Aktionen gesendet`
            );
          }
        }
      }, 400);
    };
    const goOffline = () => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    const unsub = onQueueChange(setQueued);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
      unsub();
    };
  }, []);

  // Don't render when everything is fine and nothing is queued
  if (online && queued === 0) return null;

  if (!online) {
    return (
      <div
        className="fixed top-0 left-0 right-0 z-[80] bg-[#C87967] text-white shadow-lg"
        role="status"
        data-testid="offline-banner"
      >
        <div className="max-w-5xl mx-auto px-4 py-2 flex items-center gap-3 text-xs sm:text-sm">
          <WifiOff className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1 min-w-0">
            <span className="font-semibold">Offline-Modus</span>
            <span className="hidden sm:inline"> · Deine Aktionen werden automatisch gesendet, sobald du wieder online bist.</span>
          </span>
          {queued > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/20 text-[11px] font-semibold flex-shrink-0" data-testid="offline-queued-count">
              <Clock className="w-3 h-3" /> {queued}
            </span>
          )}
        </div>
      </div>
    );
  }

  // Online but queue still draining (rare — quick flicker after reconnect)
  return (
    <div
      className="fixed top-0 left-0 right-0 z-[80] bg-[#6B8E23] text-white shadow-lg animate-fade-out"
      role="status"
      data-testid="offline-banner-reconnecting"
    >
      <div className="max-w-5xl mx-auto px-4 py-2 flex items-center gap-3 text-xs sm:text-sm">
        <Wifi className="w-4 h-4 flex-shrink-0" />
        <span className="flex-1 min-w-0">
          Wieder online — sende {queued} ausstehende Aktion{queued === 1 ? '' : 'en'}…
        </span>
      </div>
    </div>
  );
}
