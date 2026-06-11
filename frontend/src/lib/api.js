import axios from 'axios';
import { enqueue, isQueueable } from './offlineQueue';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: `${API_URL}/api`,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

// Single-flight refresh: if multiple requests 401 in parallel, only one hits
// /auth/refresh; the others wait for the same promise to resolve before retry.
let refreshInFlight = null;

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const orig = error.config;
    if (error.response?.status === 401 && !orig._retry && !orig.url?.includes('/auth/')) {
      orig._retry = true;
      try {
        if (!refreshInFlight) {
          refreshInFlight = axios.post(
            `${API_URL}/api/auth/refresh`, {}, { withCredentials: true }
          ).finally(() => { refreshInFlight = null; });
        }
        await refreshInFlight;
        return api(orig);
      } catch {
        // Iter 267 — Refresh failed; let the app show a friendly banner.
        // SessionExpiryBanner mounts in App.js and listens to this event.
        // Iter 276 — suppress the banner if the user just initiated a
        // logout-everywhere themselves; otherwise they see a confusing
        // "Sitzung abgelaufen" toast instead of the expected success state.
        if (!window.__mf_logging_out) {
          try { window.dispatchEvent(new CustomEvent('mf:session-expired')); } catch { /* SSR-safe */ }
        }
        return Promise.reject(error);
      }
    }
    // iter 180 — Auto-retry for transient GET failures (5xx, network).
    // During pod restarts the first few requests often race with the backend
    // startup; silently retrying once after 1.2s converts these transient
    // failures into successful responses without the admin ever seeing
    // "Konfiguration konnte nicht geladen werden" toasts.
    const isGet = (orig?.method || 'get').toLowerCase() === 'get';
    const isServerError = error.response && error.response.status >= 500;
    const isTransientNetwork = !error.response && (error.code === 'ERR_NETWORK' || error.code === 'ECONNABORTED');
    if (isGet && (isServerError || isTransientNetwork) && !orig._retriedTransient) {
      orig._retriedTransient = true;
      await new Promise((r) => setTimeout(r, 1200));
      try {
        return await api(orig);
      } catch {
        // fall through to the original error handling below
      }
    }
    // Offline queueing: when a write-request fails with no response (network
    // error) AND targets a whitelisted endpoint, stash it in localStorage and
    // resolve with a synthetic "queued" response so the caller can render an
    // optimistic UI. The queue is flushed automatically on `online` events.
    const isNetworkError = !error.response && (error.code === 'ERR_NETWORK' || error.message?.includes('Network') || !navigator.onLine);
    if (isNetworkError && orig && !orig._queued && isQueueable(orig.method, (orig.baseURL || '') + (orig.url || ''))) {
      orig._queued = true;
      const fullUrl = `${orig.baseURL || ''}${orig.url || ''}`;
      enqueue({
        method: orig.method,
        url: fullUrl,
        data: orig.data ? (typeof orig.data === 'string' ? JSON.parse(orig.data) : orig.data) : undefined,
        headers: { 'Content-Type': 'application/json' },
      });
      return Promise.resolve({
        status: 202,
        statusText: 'Queued (offline)',
        data: { queued: true },
        headers: {},
        config: orig,
        _offlineQueued: true,
      });
    }
    return Promise.reject(error);
  }
);

export default api;
export { API_URL };
