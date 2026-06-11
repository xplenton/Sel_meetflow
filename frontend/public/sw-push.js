/* eslint-disable no-restricted-globals */
// MeetFlow Service Worker
// - Web Push notifications (VAPID) with Badge API
// - Click-to-focus existing tab, else open new
// - Offline fallback for top-level navigations
// - Iter 257: API-Cache (last-known-good GET) + Background-Sync for task ops

const CACHE_NAME = 'meetflow-shell-v6';
const API_CACHE = 'meetflow-api-v4';
const OFFLINE_URL = '/offline.html';

// Iter 257 — API GET paths whose latest response we cache so the user sees
// last-known-good data when offline (read-only, never used for writes).
//
// Iter 377 — CRITICAL: do NOT cache `/api/auth/me`. The auth state MUST
// reflect the live session, otherwise a logged-out user gets served the
// stale "still logged in" snapshot from before the logout call, and the
// React app cannot detect the session change until the cache eventually
// expires. This was the root cause of "Abmelden funktioniert nicht" on
// production (Service Worker only kicks in there because preview gets
// fresh SW state too often to accumulate the stale response).
//
// Iter 383 — CRITICAL: do NOT cache `/api/chat/conversations`. The same
// stale-while-revalidate trap as /auth/me hit chat: a startsWith match
// also catches `/api/chat/conversations/{id}/messages`, so after a user
// sends or receives a message the next REST refetch served the OLD
// message list from disk cache → "Eigene Nachricht erscheint nicht /
// empfangene aktualisieren sich nicht ohne Hard-Reload". Chat is realtime
// via WebSocket; it does not need offline caching.
const API_CACHE_PATHS = [
  '/api/tasks',
  '/api/news/posts',
  '/api/dashboard',
  '/api/notifications',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll([
      OFFLINE_URL,
      '/favicon.svg',
      '/manifest.json',
    ]).catch(() => undefined))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME && k !== API_CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch strategy:
//  - Navigation requests (HTML pages) → network, fallback offline.html
//  - GET /api/* on whitelist → stale-while-revalidate
//  - All else → pass-through
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match(OFFLINE_URL).then(r => r || new Response('Offline', { status: 503 }))
      )
    );
    return;
  }
  if (req.method === 'GET') {
    const url = new URL(req.url);
    if (API_CACHE_PATHS.some(p => url.pathname.startsWith(p))) {
      event.respondWith(staleWhileRevalidate(req));
    }
  }
});

async function staleWhileRevalidate(req) {
  const cache = await caches.open(API_CACHE);
  const cachedResp = await cache.match(req);
  const fetchPromise = fetch(req).then((resp) => {
    if (resp.ok) cache.put(req, resp.clone()).catch(() => undefined);
    return resp;
  }).catch(() => null);
  return cachedResp || (await fetchPromise) || new Response(
    JSON.stringify({ offline: true, error: 'no cached data available' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } },
  );
}

// ---------- Iter 257: Background-Sync for tasks ----------
// Frontend writes failed POST/PUT requests to IndexedDB ("mf-pending-ops"
// object store). When the SW receives a "sync" event with tag "tasks-queue"
// (registered by the app), we drain the queue and replay each request.
const QUEUE_DB = 'mf-pending-ops';
const QUEUE_STORE = 'queue';

function openQueueDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(QUEUE_DB, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(QUEUE_STORE)) {
        db.createObjectStore(QUEUE_STORE, { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function drainQueue() {
  const db = await openQueueDb();
  const tx = db.transaction(QUEUE_STORE, 'readwrite');
  const store = tx.objectStore(QUEUE_STORE);
  const all = await new Promise((res, rej) => {
    const r = store.getAll();
    r.onsuccess = () => res(r.result || []);
    r.onerror = () => rej(r.error);
  });

  const remaining = [];
  for (const op of all) {
    try {
      const res = await fetch(op.url, {
        method: op.method,
        headers: op.headers,
        body: op.body,
        credentials: 'include',
      });
      if (!res.ok && res.status >= 500) {
        remaining.push(op);  // retry on next sync
      }
    } catch (e) {
      remaining.push(op);  // offline again, keep
    }
  }

  // Replace queue with remaining items
  const tx2 = db.transaction(QUEUE_STORE, 'readwrite');
  const store2 = tx2.objectStore(QUEUE_STORE);
  store2.clear();
  for (const op of remaining) {
    delete op.id;
    store2.add(op);
  }
  await new Promise((res) => { tx2.oncomplete = res; });

  // Notify all open clients about the flush result
  const clients = await self.clients.matchAll({ type: 'window' });
  for (const client of clients) {
    client.postMessage({
      type: 'task-queue-flushed',
      total: all.length,
      success: all.length - remaining.length,
      remaining: remaining.length,
    });
  }
  return { total: all.length, remaining: remaining.length };
}

self.addEventListener('sync', (event) => {
  if (event.tag === 'tasks-queue') {
    event.waitUntil(drainQueue());
  }
});

// Manual trigger (used by the app's "Retry now" button)
self.addEventListener('message', async (event) => {
  if (event.data?.type === 'flush-task-queue') {
    const result = await drainQueue();
    event.source?.postMessage({ type: 'flush-result', ...result });
  }
  if (event.data?.type === 'clear-badge' && 'clearAppBadge' in self.navigator) {
    self.navigator.clearAppBadge().catch(() => undefined);
  }
  // Iter 377 — Hard-reset all API caches on logout. The app sends this
  // message right after POST /auth/logout so subsequent /auth/me requests
  // (and any other cached user-scoped data) cannot serve the previous
  // session's snapshot.
  if (event.data?.type === 'clear-api-cache') {
    try {
      await caches.delete(API_CACHE);
    } catch (e) { /* ignore */ }
    event.source?.postMessage({ type: 'api-cache-cleared' });
  }
});

// ---------- Push ----------
self.addEventListener('push', (event) => {
  let data = { title: 'MeetFlow', body: 'Neue Benachrichtigung', icon: '/favicon.svg' };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch (e) { /* noop */ }

  // Incoming calls (chat or meeting) deserve the full alert treatment:
  // requireInteraction so the system doesn't auto-dismiss, aggressive
  // vibration so the phone shakes through silent-mode grouping, and
  // renotify so repeat rings come through on the same tag.
  const isCall = data.kind === 'meeting_call' || data.kind === 'chat_call' || data.urgent === true;

  const notifPromise = self.registration.showNotification(data.title, {
    body: data.body,
    icon: data.icon || '/favicon.svg',
    badge: '/favicon.svg',
    tag: data.tag || 'meetflow-news',
    data: { url: data.url || '/', kind: data.kind, meeting_id: data.meeting_id },
    renotify: true,
    requireInteraction: isCall || data.priority === 'critical',
    silent: false,
    vibrate: isCall
      ? [400, 200, 400, 200, 400, 200, 400, 200, 400, 200, 400]
      : data.priority === 'critical' ? [200, 100, 200] : [100],
    actions: isCall ? [
      { action: 'accept', title: 'Annehmen' },
      { action: 'decline', title: 'Ablehnen' },
    ] : undefined,
  });

  // Badge API (Chrome, Edge, Android). Fail silently where unsupported.
  let badgePromise = Promise.resolve();
  if ('setAppBadge' in self.navigator) {
    badgePromise = self.navigator.setAppBadge(data.badge_count || 1).catch(() => undefined);
  }

  event.waitUntil(Promise.all([notifPromise, badgePromise]));
});

// ---------- Click handler: focus existing tab else open new ----------
self.addEventListener('notificationclick', (event) => {
  const action = event.action;
  event.notification.close();
  // "Ablehnen" button on a call — dismiss without opening.
  if (action === 'decline') return;
  const targetUrl = event.notification.data?.url || '/';
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of all) {
      try {
        const url = new URL(client.url);
        if (url.origin === self.location.origin) {
          await client.focus();
          if ('navigate' in client) {
            try { await client.navigate(targetUrl); } catch (e) { /* cross-origin */ }
          }
          return;
        }
      } catch (e) { /* ignore */ }
    }
    await self.clients.openWindow(targetUrl);
    if ('clearAppBadge' in self.navigator) {
      try { await self.navigator.clearAppBadge(); } catch (e) { /* noop */ }
    }
  })());
});

// (message handler above already includes clear-badge support)
