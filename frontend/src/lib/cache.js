/**
 * Zentrale localStorage-Cache-Utility (Iter 380 — Refactoring).
 *
 * Vor diesem Modul hat jeder Konsument (Sidebar, NotificationBell,
 * ChatUnreadContext, LicenseBanner …) seinen eigenen kleinen
 * `loadCachedX()` / `persistX()`-Helfer dupliziert — alle nach demselben
 * Schema, aber leicht abweichend (mal `value`, mal `data`, mal `summary`,
 * mit/ohne `user_id`, leicht unterschiedliche TTL-Werte). Beim Hinzufügen
 * neuer Caches musste man das Pattern jedes Mal erneut tippen und beim
 * Logout-Cleanup in `AuthContext` die KEEP-Liste manuell pflegen.
 *
 * Diese Utility ist die Single-Source-of-Truth:
 *
 *   • `CACHE_KEYS`      — Registry aller bekannten `mf_*_cache` Schlüssel.
 *   • `KEEP_ON_LOGOUT`  — Prefixe, die beim Logout NICHT geleert werden
 *                         (Geräte-scoped: Sprache, Theme, Install-Hint).
 *   • `getCache(key,o)` — synchrones Lesen mit TTL-Check + optional
 *                         `userId`-Scope.
 *   • `setCache(key,v)` — Schreiben mit `{ value, ts, user_id? }`-Schema.
 *   • `removeCache`     — gezieltes Entfernen einzelner Keys.
 *   • `clearAllUserCaches()` — Logout-Cleanup. Räumt sessionStorage und
 *                         ALLE `mf_*`-Localstorage-Einträge AUSSER den
 *                         in `KEEP_ON_LOGOUT` definierten Prefixen.
 *   • `invalidateUserScoped(reason?)` — feuert ein DOM-Custom-Event
 *                         `meetflow:cache-invalidate`, an dem Consumer
 *                         lauschen können um proaktiv neu zu laden
 *                         (z.B. nach Admin-Rollen-Update). Aktuell nur
 *                         optional — Polling-Loops decken den Refresh
 *                         ohnehin innerhalb von 15-60 s ab.
 *
 * Format der gespeicherten Werte:
 *   { value: <T>, ts: <epochMs>, user_id?: <string> }
 *
 * Hinweis zu `permissions.js`:
 *   Das `mf_perms_provider_cache` benutzt ein komplexeres Schema mit
 *   mehreren Top-Level-Feldern (capabilities, role, groups, …). Es ist
 *   absichtlich NICHT auf diese Helper umgestellt — der Key ist aber in
 *   `CACHE_KEYS` registriert, damit der Logout-Cleanup ihn mitfegt.
 */

// Alle bekannten user-scoped Cache-Keys. Single source of truth.
export const CACHE_KEYS = Object.freeze({
  // Berechtigungen + Sidebar
  USER_PERMS: 'mf_user_perms_cache',            // Sidebar.js
  PERMS_PROVIDER: 'mf_perms_provider_cache',    // lib/permissions.js (eigenes Schema)
  TASKS_PENDING: 'mf_tasks_pending_cache',      // Sidebar.js
  NEWS_REPORTS_PENDING: 'mf_news_reports_pending_cache', // Sidebar.js
  // Notifications
  NOTIF_UNREAD: 'mf_notif_unread_cache',
  NOTIF_CATEGORIES: 'mf_notif_categories_cache',
  // Chat
  CHAT_UNREAD_SUMMARY: 'mf_chat_unread_cache',
  // Lizenz-Banner
  LICENSE_STATUS: 'mf_license_status_cache',
});

// Prefixe, die beim Logout erhalten bleiben (Geräte-scoped, nicht User-scoped).
//   • mf_lang     — UI-Sprache
//   • mf_install_ — PWA-Install-Banner-Cooldowns
//   • mf_theme    — Dark/Light/System-Präferenz
export const KEEP_ON_LOGOUT = Object.freeze(['mf_lang', 'mf_install_', 'mf_theme']);

const DEFAULT_TTL_MS = 10 * 60 * 1000; // 10 min — sicherer Default

/**
 * Liest einen gecachten Wert. Gibt `null` zurück bei Fehler, fehlendem Key,
 * TTL-Ablauf oder UserId-Mismatch.
 *
 * @param {string} key  - der storage key (typischerweise aus CACHE_KEYS)
 * @param {object} [opts]
 * @param {number} [opts.ttlMs=DEFAULT_TTL_MS] - Max-Alter
 * @param {string} [opts.userId] - wenn gesetzt, muss `parsed.user_id` matchen
 */
export function getCache(key, opts = {}) {
  const { ttlMs = DEFAULT_TTL_MS, userId } = opts;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    if (Date.now() - (parsed.ts || 0) > ttlMs) return null;
    if (userId && parsed.user_id && parsed.user_id !== userId) return null;
    return parsed.value;
  } catch {
    return null;
  }
}

/**
 * Schreibt einen Wert in den Cache. Schluckt Fehler (z.B. localStorage voll
 * oder im Inkognito disabled) — Caches sind immer best-effort.
 *
 * @param {string} key
 * @param {*} value
 * @param {object} [opts]
 * @param {string} [opts.userId] - bindet den Cache an einen User
 */
export function setCache(key, value, opts = {}) {
  try {
    const payload = { value, ts: Date.now() };
    if (opts.userId) payload.user_id = opts.userId;
    localStorage.setItem(key, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

/** Entfernt einen einzelnen Cache-Eintrag. */
export function removeCache(key) {
  try { localStorage.removeItem(key); } catch { /* ignore */ }
}

/**
 * Räumt sessionStorage komplett und alle `mf_*` localStorage-Einträge,
 * außer den in `KEEP_ON_LOGOUT` aufgeführten Prefixen. Wird vom
 * AuthContext.logoutFn aufgerufen.
 */
export function clearAllUserCaches() {
  try { sessionStorage.clear(); } catch { /* ignore */ }
  try {
    Object.keys(localStorage).forEach((k) => {
      if (!k.startsWith('mf_')) return;
      if (KEEP_ON_LOGOUT.some((p) => k.startsWith(p))) return;
      localStorage.removeItem(k);
    });
  } catch { /* ignore */ }
}

/**
 * Sendet ein App-weites Custom-Event `meetflow:cache-invalidate`. Consumer
 * können darauf lauschen und Refetches triggern. Wird (Stand 380) noch
 * nirgends produktiv konsumiert — exportiert als Hook für künftige
 * "Admin hat dich gerade umgruppiert"-Realtime-Pfade.
 *
 * @param {string} [reason]
 */
export function invalidateUserScoped(reason = 'manual') {
  try {
    window.dispatchEvent(new CustomEvent('meetflow:cache-invalidate', { detail: { reason } }));
  } catch { /* ignore */ }
}
