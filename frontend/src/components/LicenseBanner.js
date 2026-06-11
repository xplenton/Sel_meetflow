/**
 * Iter 369 — Lizenz-Status-Banner.
 *
 * Pollt alle 5 Minuten `/api/license/status`. Wenn die Lizenz inaktiv ist
 * (`invalid`), zeigt einen roten Top-Banner mit Hinweis an den Admin.
 * Bei `grace` (Lizenz-Server kurz offline) → gelber Banner. Bei `disabled`
 * oder `valid` → nichts.
 *
 * Wird einmal in `App.js` gemountet, oberhalb des Routers.
 *
 * Iter 378 — localStorage-Cache vermeidet Flicker beim Page-Reload: war die
 * Lizenz beim letzten Render `invalid`/`grace`, zeigt der Banner sofort beim
 * Mount den korrekten Zustand, statt erst nach 1-2s aus dem Backend-Request.
 */
import { useEffect, useState } from 'react';
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import api from '../lib/api';
import { CACHE_KEYS, getCache, setCache } from '../lib/cache';
import { useAuth } from '../contexts/AuthContext';

const POLL_INTERVAL_MS = 5 * 60 * 1000;
// Iter 378 — Cache nur kurz vertrauen (max. 1 Stunde), damit ein abgelaufener
// Cache nicht noch tagelang einen falschen Banner zeigt nachdem das Backend
// wieder gesund ist.
const STATUS_CACHE_TTL_MS = 60 * 60 * 1000;

export default function LicenseBanner() {
  const { user } = useAuth();
  // Sync-hydrate aus localStorage damit Folge-Page-Loads den Banner sofort
  // im korrekten Zustand zeigen (statt 1-2s leerer Header-Bereich → Banner).
  const [status, setStatus] = useState(() => getCache(CACHE_KEYS.LICENSE_STATUS, { ttlMs: STATUS_CACHE_TTL_MS }));

  useEffect(() => {
    // Iter 381 — Banner nur für eingeloggte User pollen. Vorher hat das
    // Polling auch auf der /login-Seite weitergelaufen und nach einem
    // Logout sofort wieder `mf_license_status_cache` gefüllt — was den
    // zentralen Logout-Cache-Cleanup (clearAllUserCaches) konterkariert.
    if (!user) return undefined;
    let cancelled = false;
    const fetchStatus = async () => {
      try {
        const { data } = await api.get('/license/status');
        if (!cancelled) {
          setStatus(data);
          setCache(CACHE_KEYS.LICENSE_STATUS, data);
        }
      } catch {
        // Iter 370 — Bei transienten Fehlern (Netzwerk, 5xx, Auth-Refresh)
        // NICHT eagerly "Anwendung ist gesperrt" anzeigen. Erst wenn der
        // Server explizit `status:"invalid"` liefert, zeigen wir den
        // roten Banner. So vermeiden wir False-Positives in Production
        // wenn der Server während eines Redeploys kurz nicht erreichbar
        // ist oder die Session abgelaufen ist.
        //
        // Iter 378 — Wir behalten den ggf. aus Cache hydrierten Status,
        // damit ein einzelner gescheiterter Refresh den Banner nicht
        // verschwinden lässt (würde sonst beim nächsten Backend-OK wieder
        // aufpoppen → Flicker).
      }
    };
    fetchStatus();
    const id = setInterval(fetchStatus, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [user]);

  if (!user || !status || status.status === 'valid' || status.status === 'disabled') {
    return null;
  }

  const isInvalid = status.status === 'invalid';
  const palette = isInvalid
    ? 'bg-rose-100 border-rose-400 text-rose-900'
    : 'bg-amber-100 border-amber-400 text-amber-900';
  const Icon = isInvalid ? ShieldAlert : AlertTriangle;
  const title = isInvalid
    ? 'Lizenz inaktiv'
    : 'Lizenz im Offline-Grace-Period';
  const subtitle = isInvalid
    ? 'Die Anwendung ist gesperrt. Bitte Administrator kontaktieren.'
    : 'Lizenz-Server vorübergehend nicht erreichbar — App läuft weiter, sobald Verbindung wieder steht.';

  return (
    <div
      className={`w-full border-b-2 ${palette} px-4 py-2 flex items-center gap-2 text-xs`}
      data-testid={`license-banner-${status.status}`}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="font-semibold">{title}</div>
        <div className="opacity-80">
          {subtitle}
          {status.message && <span className="ml-1 italic">· {status.message}</span>}
        </div>
      </div>
    </div>
  );
}
