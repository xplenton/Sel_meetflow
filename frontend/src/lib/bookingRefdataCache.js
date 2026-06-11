/**
 * Iter 338 — In-memory + sessionStorage cache for booking-dialog reference
 * data. cost-centers, accounts, catering-items and bookable-users change
 * rarely (admins edit them sporadically) but every open of the booking
 * dialog used to refetch all 4 in parallel — adding 200-500 ms before the
 * user sees any selectable values.
 *
 * Strategy:
 *   - 10-minute TTL in sessionStorage
 *   - First subscriber to a key triggers the fetch; concurrent dialog
 *     opens reuse the same in-flight promise.
 */
import api from './api';

const TTL_MS = 10 * 60 * 1000;
const PENDING = new Map(); // key -> Promise

function _read(key) {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (!obj || typeof obj.t !== 'number') return null;
    if (Date.now() - obj.t > TTL_MS) return null;
    return obj.v;
  } catch { return null; }
}

function _write(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify({ t: Date.now(), v: value })); }
  catch { /* quota — ignore */ }
}

async function cachedGet(key, path) {
  const hit = _read(key);
  if (hit) return hit;
  if (PENDING.has(key)) return PENDING.get(key);
  const p = api.get(path)
    .then(({ data }) => {
      const v = data || [];
      _write(key, v);
      return v;
    })
    .catch(() => [])
    .finally(() => { PENDING.delete(key); });
  PENDING.set(key, p);
  return p;
}

export const fetchCateringItems = () => cachedGet('mf:booking:catering-items', '/catering-items');
export const fetchCostCenters   = () => cachedGet('mf:booking:cost-centers', '/cost-centers');
export const fetchAccounts      = () => cachedGet('mf:booking:accounts', '/accounts');
export const fetchBookableUsers = () => cachedGet('mf:booking:bookable-users', '/users/bookable-for');

/** Manual purge — call after admin edits these collections to force refetch. */
export function purgeBookingRefdataCache() {
  ['mf:booking:catering-items', 'mf:booking:cost-centers',
   'mf:booking:accounts', 'mf:booking:bookable-users'].forEach(k => {
     try { sessionStorage.removeItem(k); } catch { /* ignore */ }
  });
  PENDING.clear();
}
