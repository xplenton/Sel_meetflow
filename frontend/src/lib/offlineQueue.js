/**
 * Offline action queue.
 *
 * Persists write-requests (POST/PUT/DELETE on whitelisted endpoints) while the
 * user is offline, then replays them in FIFO order as soon as the browser
 * reports the connection back. Backed by localStorage so a tab-refresh (or
 * even a full restart) does not lose the user's intent.
 *
 * Only specific endpoints are queued (reactions, comments, read-receipts etc.)
 * because blindly replaying every failed POST would be dangerous — a user
 * could, for example, double-create a meeting if they tap "create" twice.
 */
import axios from 'axios';

const STORAGE_KEY = 'mf_offline_queue_v1';
const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

/** Endpoint path-prefixes that are SAFE to replay automatically.
 *  Each entry is matched against the request URL path-only (no querystring). */
const QUEUEABLE = [
  { method: 'POST',   prefix: '/news/',      suffix: '/reactions' },       // reactions
  { method: 'DELETE', prefix: '/news/',      suffix: '/reactions' },       // reaction undo
  { method: 'POST',   prefix: '/news/',      suffix: '/comments' },        // new comment
  { method: 'POST',   prefix: '/news/',      suffix: '/read' },            // read receipt
  { method: 'POST',   prefix: '/news/',      suffix: '/read-receipt' },    // read receipt alt
  { method: 'POST',   prefix: '/news/',      suffix: '/questions' },       // Q&A ask
  { method: 'POST',   prefix: '/news/',      suffix: '/upvote' },          // Q&A upvote
  { method: 'POST',   prefix: '/news/polls/', suffix: '/vote' },           // poll vote
  // Iter 257 — task ops queueable for offline use.
  { method: 'POST',   prefix: '/tasks',      suffix: '' },                 // create new task
  { method: 'PUT',    prefix: '/tasks/',     suffix: '' },                 // update task fields
  { method: 'POST',   prefix: '/tasks/',     suffix: '/comments' },        // task comment
  { method: 'POST',   prefix: '/tasks/',     suffix: '/sub-tasks' },       // add sub-task
  { method: 'PUT',    prefix: '/tasks/',     suffix: '/status' },          // status change
];

function matchesQueueable(method, url) {
  const path = (url || '').replace(API_BASE, '').split('?')[0];
  const upperMethod = (method || '').toUpperCase();
  return QUEUEABLE.some(q =>
    q.method === upperMethod
    && path.startsWith(q.prefix)
    && (q.suffix === '' ? true : path.endsWith(q.suffix))
  );
}

function readQueue() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
  catch { return []; }
}

function writeQueue(arr) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(arr)); } catch {}
  listeners.forEach(fn => { try { fn(arr.length); } catch {} });
}

const listeners = new Set();
export function onQueueChange(fn) {
  listeners.add(fn);
  // Emit current count right away
  try { fn(readQueue().length); } catch {}
  return () => listeners.delete(fn);
}

export function getQueueCount() {
  return readQueue().length;
}

export function enqueue({ method, url, data, headers }) {
  const item = {
    id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    method, url, data, headers: headers || {},
    queued_at: new Date().toISOString(),
  };
  const arr = readQueue();
  arr.push(item);
  writeQueue(arr);
  return item;
}

export function isQueueable(method, url) {
  return matchesQueueable(method, url);
}

/** Replay all queued requests in FIFO order.  Best-effort: on individual
 *  failure that is NOT a network error (e.g. 400/404) we drop the item so a
 *  single bad request cannot block the rest. */
let flushing = false;
export async function flushQueue() {
  if (flushing) return { flushed: 0, remaining: readQueue().length };
  flushing = true;
  let flushed = 0;
  try {
    while (true) {
      const arr = readQueue();
      if (!arr.length) break;
      const item = arr[0];
      try {
        await axios({
          method: item.method,
          url: item.url,
          data: item.data,
          headers: item.headers,
          withCredentials: true,
        });
        flushed += 1;
        writeQueue(arr.slice(1));
      } catch (err) {
        const status = err?.response?.status;
        if (!status) {
          // Still offline — stop and try later
          break;
        }
        if (status >= 400 && status < 500 && status !== 401 && status !== 408 && status !== 429) {
          // Request itself is bad (e.g. post was deleted meanwhile) — drop and move on
          writeQueue(arr.slice(1));
          continue;
        }
        // Server 5xx — stop for now, retry later
        break;
      }
    }
  } finally {
    flushing = false;
  }
  return { flushed, remaining: readQueue().length };
}

/** Initialise auto-flush: try once on boot if already online, and every time
 *  the browser reports coming back online. */
export function initOfflineQueue() {
  if (navigator.onLine) {
    setTimeout(() => { flushQueue().catch(() => {}); }, 500);
  }
  window.addEventListener('online', () => { flushQueue().catch(() => {}); });
}
