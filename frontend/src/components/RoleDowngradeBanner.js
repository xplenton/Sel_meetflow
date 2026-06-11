/**
 * Iter 372 — Role-Downgrade-Banner.
 *
 * Hintergrund: Wenn ein User mit `role=member` Mitglied einer Gruppe ist,
 * die `role_override='guest'` setzt (z. B. die System-Gruppe „Gast"), wird
 * seine effektive Rolle auf „guest" reduziert. Der User sieht weniger
 * Menüs, kann nicht buchen, und hat keine Ahnung warum — der IAM-Audit
 * (iter 371) hat 434 solcher unbeabsichtigt entrechteter Konten gefunden.
 *
 * Dieser Banner zeigt einen freundlichen, gelben Hinweis oben in der App,
 * damit der User (und sein Admin) sofort verstehen, woher die Einschränkung
 * kommt — ohne dass wir das Verhalten ändern. Die Logik im Backend (iter 289)
 * bleibt unverändert; wir machen sie nur sichtbar.
 *
 * Mount: oberhalb des Routers in App.js, gleich neben LicenseBanner.
 */
import { AlertTriangle } from 'lucide-react';
import { usePermissions } from '../lib/permissions';

export default function RoleDowngradeBanner() {
  const { roleDowngradedBy: info, loading } = usePermissions();
  if (loading || !info) return null;

  return (
    <div
      className="w-full border-b-2 bg-amber-100 border-amber-400 text-amber-900 px-4 py-2 flex items-center gap-2 text-xs"
      data-testid="role-downgrade-banner"
    >
      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="font-semibold">
          Effektive Rolle: <span className="capitalize">{info.override_role}</span>
        </div>
        <div className="opacity-80">
          Deine ursprüngliche Rolle <strong className="capitalize">{info.original_role}</strong>{' '}
          wurde durch deine Mitgliedschaft in der Gruppe{' '}
          <strong>„{info.group_name}"</strong> auf{' '}
          <strong className="capitalize">{info.override_role}</strong> reduziert.
          Wenn das nicht beabsichtigt ist, kontaktiere bitte deinen Administrator.
        </div>
      </div>
    </div>
  );
}
