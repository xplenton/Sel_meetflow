// Web Push subscription utilities
import api from './api';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

export function isPushSupported() {
  return typeof window !== 'undefined'
    && 'serviceWorker' in navigator
    && 'PushManager' in window
    && 'Notification' in window;
}

export function getNotificationPermission() {
  if (!isPushSupported()) return 'unsupported';
  return Notification.permission; // 'default' | 'granted' | 'denied'
}

export async function registerPushServiceWorker() {
  if (!isPushSupported()) return null;
  try {
    const reg = await navigator.serviceWorker.register('/sw-push.js');
    // Force an update check so the new `/sw-push.js` (call notifications
    // with requireInteraction + action buttons — iter 144) replaces the
    // previously cached v1 handler on existing installs (iter 148).
    try { await reg.update(); } catch { /* ignore */ }
    return reg;
  } catch (e) {
    console.error('SW registration failed', e);
    return null;
  }
}

export async function subscribeToPush() {
  if (!isPushSupported()) {
    throw new Error('Push wird von diesem Browser nicht unterstuetzt');
  }
  console.log('[push] requesting notification permission…');
  const perm = await Notification.requestPermission();
  console.log('[push] permission=', perm);
  if (perm !== 'granted') {
    throw new Error(perm === 'denied' ? 'Benachrichtigungen wurden abgelehnt' : 'Keine Berechtigung erteilt');
  }
  console.log('[push] registering service worker…');
  const reg = await registerPushServiceWorker();
  if (!reg) throw new Error('Service Worker konnte nicht registriert werden');
  console.log('[push] SW scope=', reg.scope);

  // Fetch VAPID public key
  let publicKey = '';
  try {
    const { data } = await api.get('/news/push/vapid-public-key');
    publicKey = data.public_key || process.env.REACT_APP_VAPID_PUBLIC_KEY || '';
  } catch (e) {
    console.error('[push] VAPID key fetch failed', e);
    throw new Error('VAPID-Key konnte nicht geladen werden');
  }
  if (!publicKey) throw new Error('VAPID Public Key fehlt');
  console.log('[push] got VAPID key, length=', publicKey.length);

  // Check existing subscription
  let sub = await reg.pushManager.getSubscription();
  if (sub) {
    // Verify key match - re-subscribe if mismatch
    try {
      const existingKey = new Uint8Array(sub.options.applicationServerKey || new ArrayBuffer(0));
      const desiredKey = urlBase64ToUint8Array(publicKey);
      const match = existingKey.length === desiredKey.length
        && existingKey.every((v, i) => v === desiredKey[i]);
      if (!match) {
        console.log('[push] key mismatch → unsubscribing old one');
        await sub.unsubscribe();
        sub = null;
      }
    } catch { /* no-op */ }
  }
  if (!sub) {
    console.log('[push] creating new subscription…');
    try {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    } catch (e) {
      console.error('[push] pushManager.subscribe failed', e);
      const msg = e?.message || '';
      if (msg.includes('push service')) {
        throw new Error('Push-Dienst nicht verfügbar (Browser blockiert evtl. Push in privatem/Inkognito-Modus)');
      }
      throw new Error(`Push-Subscription fehlgeschlagen: ${msg || 'unbekannter Fehler'}`);
    }
  }
  console.log('[push] subscription ready, posting to backend…');
  try {
    await api.post('/news/push/subscribe', { subscription: sub.toJSON() });
  } catch (e) {
    console.error('[push] backend subscribe failed', e);
    const backendMsg = e?.response?.data?.detail || e?.message || 'Backend-Fehler';
    throw new Error(`Speichern auf Server fehlgeschlagen: ${backendMsg}`);
  }
  console.log('[push] ✓ subscribed');
  return sub;
}

export async function unsubscribeFromPush() {
  if (!isPushSupported()) return;
  const reg = await navigator.serviceWorker.getRegistration('/sw-push.js');
  if (!reg) return;
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    try { await api.delete('/news/push/subscribe', { data: { endpoint } }); } catch {}
  }
}

export async function getPushSubscriptionStatus() {
  if (!isPushSupported()) return { supported: false, permission: 'unsupported', subscribed: false };
  try {
    const reg = await navigator.serviceWorker.getRegistration('/sw-push.js');
    const sub = reg ? await reg.pushManager.getSubscription() : null;
    return {
      supported: true,
      permission: Notification.permission,
      subscribed: !!sub,
    };
  } catch {
    return { supported: true, permission: Notification.permission, subscribed: false };
  }
}

/**
 * iter 152 — Auto-Recovery for corrupt/missing server-side subscriptions.
 * Call on every app bootstrap: if the browser already granted permission
 * AND has a live PushSubscription, silently POST it to the server so any
 * prior corrupt DB row gets overwritten. This fixes the "Urgent call
 * doesn't arrive on locked phone" bug where older subs stored in the DB
 * had malformed p256dh keys and every webpush failed instantly.
 *
 * Safe to call repeatedly — the subscribe endpoint is an upsert.
 */
export async function ensureServerHasPushSubscription() {
  if (!isPushSupported()) return { ok: false, reason: 'unsupported' };
  try {
    if (Notification.permission !== 'granted') return { ok: false, reason: 'not_granted' };
    const reg = await registerPushServiceWorker();
    if (!reg) return { ok: false, reason: 'no_sw' };
    let sub = await reg.pushManager.getSubscription();

    // iter 153 — If the browser returned a subscription but its keys are
    // missing/empty (some iOS/Android configs do this), force a full
    // unsubscribe + resubscribe so we get fresh valid keys. Without this
    // Auto-Recovery kept re-uploading the same corrupt subscription and
    // the server rejected it (iter 152 validation).
    const needsFreshSub = sub && (() => {
      try {
        const json = sub.toJSON();
        const keys = json?.keys || {};
        const p256 = keys.p256dh || '';
        const auth = keys.auth || '';
        return p256.length < 80 || auth.length < 16;
      } catch { return true; }
    })();
    if (needsFreshSub) {
      try { await sub.unsubscribe(); } catch { /* ignore */ }
      sub = null;
    }

    if (!sub) {
      // No local subscription — request one using the current VAPID key.
      try {
        const { data } = await api.get('/news/push/vapid-public-key');
        const publicKey = data.public_key || process.env.REACT_APP_VAPID_PUBLIC_KEY || '';
        if (!publicKey) return { ok: false, reason: 'no_vapid' };
        sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        });
      } catch (e) {
        return { ok: false, reason: 'subscribe_failed' };
      }
    }
    // Re-send the (potentially already-existing) sub to the server so a
    // stale/corrupt DB row is overwritten by the fresh browser state.
    try { await api.post('/news/push/subscribe', { subscription: sub.toJSON() }); }
    catch { /* ignore server validation — user-facing flows still work */ }
    return { ok: true };
  } catch {
    return { ok: false, reason: 'unexpected' };
  }
}
