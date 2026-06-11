import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from './AuthContext';
import api from '../lib/api';
import { createChatWebSocket } from '../lib/chatWebSocket';

const StatusContext = createContext(null);

export const STATUS_CFG = {
  online:  { label: 'Online',       color: '#6B8E23', ring: 'ring-[#6B8E23]' },
  away:    { label: 'Abwesend',     color: '#D4A373', ring: 'ring-[#D4A373]' },
  dnd:     { label: 'Nicht stoeren', color: '#C87967', ring: 'ring-[#C87967]' },
  offline: { label: 'Offline',      color: '#9CA3AF', ring: 'ring-[#9CA3AF]' },
};

const IDLE_MINUTES = 30;
// LocalStorage key for persisting the user's manually-chosen status across
// reloads. Auto-logic (idle, calendar-DND) never overrides a manual pick.
const MANUAL_OVERRIDE_KEY = 'meetflow_manual_status';

export function StatusProvider({ children }) {
  const { user } = useAuth();
  const [myStatus, setMyStatus] = useState('offline');
  const [manualOverride, setManualOverride] = useState(() => {
    try { return localStorage.getItem(MANUAL_OVERRIDE_KEY) || null; } catch { return null; }
  });
  const [userStatuses, setUserStatuses] = useState({}); // user_id -> status_mode
  const lastActivityRef = useRef(Date.now());
  const wsRef = useRef(null);

  // ============ My status polling ============
  const fetchMyStatus = useCallback(async () => {
    if (!user?.user_id) return;
    try {
      const { data } = await api.get('/chat/my-status');
      setMyStatus(data.status_mode || 'online');
    } catch {}
  }, [user]);

  useEffect(() => {
    fetchMyStatus();
    // Iter 280 — Tighter poll (25s vs 60s) keeps the UI consistent if the WS
    // is in a degraded state (e.g., ingress packet loss); the backend call
    // is also a heartbeat that auto-promotes an out-of-sync "offline" back
    // to "online", so each poll actively self-repairs.
    const t = setInterval(fetchMyStatus, 25_000);
    // Also refresh whenever the tab becomes visible again — a backgrounded
    // mobile tab often misses 1-2 WS pongs and shows stale state.
    const onVis = () => { if (document.visibilityState === 'visible') fetchMyStatus(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      clearInterval(t);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [fetchMyStatus]);

  // ============ Manual status setter ============
  const setStatus = useCallback(async (status) => {
    if (!user?.user_id) return;
    try {
      await api.put('/chat/my-status', { status_mode: status });
      setMyStatus(status);
      setManualOverride(status);
      try {
        // Persist so a browser reload doesn't silently revert the user's
        // explicit choice back to auto-managed (iter 148).
        localStorage.setItem(MANUAL_OVERRIDE_KEY, status);
      } catch { /* ignore quota */ }
    } catch {}
  }, [user]);

  // Allow user to "clear" manual override and return to auto-managed
  const clearManualOverride = useCallback(() => {
    setManualOverride(null);
    try { localStorage.removeItem(MANUAL_OVERRIDE_KEY); } catch { /* ignore */ }
  }, []);

  const refreshMyStatus = useCallback(() => {
    fetchMyStatus();
  }, [fetchMyStatus]);

  useEffect(() => {
    const h = () => refreshMyStatus();
    window.addEventListener('status:refresh', h);
    // After a WS reconnect (idle-drop + reconnect), refetch status so we don't
    // show stale data while the user thinks they're back online.
    window.addEventListener('ws:reconnected', h);
    return () => {
      window.removeEventListener('status:refresh', h);
      window.removeEventListener('ws:reconnected', h);
    };
  }, [refreshMyStatus]);

  // ============ Idle detection (auto -> away) ============
  useEffect(() => {
    if (!user?.user_id) return;
    const markActive = () => { lastActivityRef.current = Date.now(); };
    const events = ['mousemove', 'keydown', 'click', 'touchstart', 'scroll'];
    events.forEach(e => window.addEventListener(e, markActive, { passive: true }));
    const interval = setInterval(async () => {
      // Manual override wins — never auto-switch when the user has picked
      // a status explicitly (including "online" — they may want to
      // appear online while away from keyboard). Auto-away only works
      // when there's no manual pick at all (iter 148).
      if (manualOverride) return;
      const idleMin = (Date.now() - lastActivityRef.current) / 60000;
      if (idleMin >= IDLE_MINUTES && myStatus === 'online') {
        try { await api.put('/chat/my-status', { status_mode: 'away' }); setMyStatus('away'); } catch {}
      } else if (idleMin < IDLE_MINUTES && myStatus === 'away') {
        try { await api.put('/chat/my-status', { status_mode: 'online' }); setMyStatus('online'); } catch {}
      }
    }, 60000);
    return () => {
      events.forEach(e => window.removeEventListener(e, markActive));
      clearInterval(interval);
    };
  }, [user, myStatus, manualOverride]);

  // ============ Visibility/browser focus -> update ============
  useEffect(() => {
    if (!user?.user_id) return;
    const onVis = () => { if (!document.hidden) lastActivityRef.current = Date.now(); };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [user]);

  // ============ Global WS for status-change events ============
  // Uses the resilient `createChatWebSocket` helper so status updates keep
  // flowing even after idle-proxy drops or tab backgrounding.
  useEffect(() => {
    if (!user?.user_id) return;
    const backendUrl = process.env.REACT_APP_BACKEND_URL;
    if (!backendUrl) return;
    const wsUrl = backendUrl.replace(/^http/, 'ws') + `/api/ws/chat/${user.user_id}`;
    const handle = createChatWebSocket(wsUrl, (data) => {
      if (data.type === 'status-change') {
        setUserStatuses(prev => ({ ...prev, [data.user_id]: data.status_mode }));
      }
      // Iter 336 — re-dispatch task-* events on a window event so feature
      // pages (TasksPage, DashboardPage) can listen without each opening
      // their own WebSocket. Keeps the global socket as single source of
      // truth and avoids N parallel sockets per user.
      if (data && typeof data.type === 'string' && data.type.startsWith('task-')) {
        try {
          window.dispatchEvent(new CustomEvent('meetflow:task-event', { detail: data }));
        } catch { /* ignore */ }
      }
      // Iter 375 — re-dispatch incoming-call / call-cancelled / call-ended
      // as window events so the global IncomingCallModal has a redundant
      // delivery path. Users reported the fullscreen ringing UI sometimes
      // failed to appear (only the in-chat "Jetzt beitreten" button
      // showed) — a 2nd parallel delivery channel guarantees the modal
      // fires even if its own WS is mid-reconnect when the event arrives.
      if (data && (data.type === 'incoming-call' || data.type === 'call-cancelled' || data.type === 'call-ended')) {
        try {
          window.dispatchEvent(new CustomEvent('meetflow:call-event', { detail: data }));
        } catch { /* ignore */ }
      }
    });
    wsRef.current = handle;
    return () => { try { handle.close(); } catch { /* ignore */ } wsRef.current = null; };
  }, [user]);

  // ============ Bulk fetch statuses for given user ids ============
  const fetchStatuses = useCallback(async (userIds) => {
    const missing = (userIds || []).filter(id => id && userStatuses[id] === undefined);
    if (missing.length === 0) return userStatuses;
    try {
      const { data } = await api.post('/chat/statuses', { user_ids: missing });
      setUserStatuses(prev => {
        const next = { ...prev };
        Object.entries(data.statuses || {}).forEach(([uid, s]) => { next[uid] = s.status_mode; });
        return next;
      });
    } catch {}
  }, [userStatuses]);

  const getStatus = useCallback((userId) => {
    if (userId === user?.user_id) return myStatus;
    return userStatuses[userId] || 'offline';
  }, [user, myStatus, userStatuses]);

  return (
    <StatusContext.Provider value={{
      myStatus, setStatus, manualOverride, clearManualOverride,
      getStatus, fetchStatuses, userStatuses,
    }}>
      {children}
    </StatusContext.Provider>
  );
}

export function useStatus() {
  const ctx = useContext(StatusContext);
  if (!ctx) return {
    myStatus: 'offline', setStatus: () => {},
    getStatus: () => 'offline', fetchStatuses: () => {}, userStatuses: {},
  };
  return ctx;
}
