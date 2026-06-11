/**
 * Sentry error tracking for production (iter 121).
 *
 * Initialised lazily so the app has zero cost when `REACT_APP_SENTRY_DSN`
 * is unset (local dev / preview). When a DSN is present:
 *   - Unhandled errors + promise rejections auto-capture
 *   - React component stack traces auto-attach (`reactRouterV6Instrumentation` not used because our router lives inside a provider, keep it simple for now)
 *   - A `data-testid="sentry-ready"` meta tag lands on <html> so tests can
 *     verify the integration is wired up without having to trigger an error.
 *
 * To enable: set `REACT_APP_SENTRY_DSN=https://...@sentry.io/...` in
 * `/app/frontend/.env` and redeploy. Also set `REACT_APP_SENTRY_ENV`
 * (e.g. `production`, `staging`) for correct per-environment filtering in
 * the Sentry dashboard.
 */
import * as Sentry from '@sentry/react';

export function initSentry() {
  const dsn = process.env.REACT_APP_SENTRY_DSN;
  if (!dsn) return;
  try {
    Sentry.init({
      dsn,
      environment: process.env.REACT_APP_SENTRY_ENV || 'production',
      release: process.env.REACT_APP_RELEASE || 'meetflow@iter-121',
      // Sample 20% of transactions in production to stay inside the free tier.
      tracesSampleRate: 0.2,
      // Only 10% of sessions are replayed; errors always.
      replaysSessionSampleRate: 0.1,
      replaysOnErrorSampleRate: 1.0,
      integrations: [
        Sentry.browserTracingIntegration(),
        Sentry.replayIntegration({ maskAllText: true, blockAllMedia: true }),
      ],
      // Don't spam Sentry when the user is offline — those errors are expected.
      beforeSend(event, hint) {
        const msg = hint?.originalException?.message || '';
        if (/Network Error|Failed to fetch|NetworkError/i.test(msg)) return null;
        return event;
      },
    });
    document.documentElement.setAttribute('data-sentry-ready', 'true');
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[sentry] init failed:', err);
  }
}

export const SentryErrorBoundary = Sentry.ErrorBoundary;
