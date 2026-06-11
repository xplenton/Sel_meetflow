/**
 * React Query configuration for MeetFlow.
 *
 * Migration status (iter 113): the infrastructure is wired in App.js and
 * one pilot component (`NotificationBell`) has been migrated to
 * demonstrate the pattern. Future components can adopt React Query
 * incrementally by swapping their `useEffect + useState + setInterval`
 * polling with `useQuery` — see `NotificationBell.js` for the canonical
 * example.
 *
 * Defaults chosen for a mildly-realtime SaaS:
 *   - `staleTime: 30s`  — data is considered fresh for 30 s, so switching
 *     pages doesn't trigger a refetch storm.
 *   - `gcTime: 5 min`   — cached entries live 5 min after last observer
 *     unmounts before being garbage-collected.
 *   - `refetchOnWindowFocus`: true — default, useful for catching
 *     changes after a user returns to the tab.
 *   - `refetchOnReconnect`: true — ties nicely into our `ws:reconnected`
 *     event: WS drop -> reconnect -> React Query also refetches stale
 *     queries automatically on the browser's `online` event.
 *   - `retry: 1`        — no infinite retry hell; the UI surfaces errors
 *     quickly instead of looking stuck.
 */
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
});

// Re-fetch every query tagged `['notifications', ...]` whenever a WS
// reconnect happens. Mirrors the vanilla `ws:reconnected` listener that
// non-React-Query components use today.
if (typeof window !== 'undefined') {
  window.addEventListener('ws:reconnected', () => {
    queryClient.invalidateQueries();
  });
}
