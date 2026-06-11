import { Badge } from '../ui/badge';
import StatusDot from '../chat/StatusDot';
import { timeAgo } from '../../lib/timeAgo';
import { roleLabel } from '../../lib/roleLabel';
import { Edit, Trash2, UserCheck, UserX, LogOut, Mail, AlertCircle, Hourglass, ShieldCheck, KeyRound } from 'lucide-react';
import { useLanguage } from '../../contexts/LanguageContext';
import api from '../../lib/api';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import ResetPasswordDialog from './ResetPasswordDialog';

/**
 * AdminUserRow — single row in the admin users list. Renders avatar +
 * online status, name + email, groups, last-seen, role badge, verification
 * status, and the action buttons (toggle/edit/force-logout/delete/resend).
 */
export default function AdminUserRow({
  user, groups, isCurrentUser,
  roleColors,
  onToggleStatus, onEdit, onForceLogout, onDelete,
  autoLockHours = 24,  // Iter 291 — passed from parent so the grace badge shows the correct remaining time
}) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const isInactive = user.status === 'inactive';
  // Iter 291 — derive verification state
  const isLockedUnverified = user.status === 'locked_unverified';
  const isPendingVerify = user.self_registered === true
    && user.email_verified !== true
    && !isLockedUnverified
    && !isInactive;
  const showResend = isPendingVerify || isLockedUnverified;

  // Remaining-hours calc (for pending-verify badge)
  let remainingHours = null;
  if (isPendingVerify && user.created_at && autoLockHours > 0) {
    const createdMs = new Date(user.created_at).getTime();
    const expiresMs = createdMs + autoLockHours * 3600 * 1000;
    const remMs = expiresMs - Date.now();
    remainingHours = Math.max(0, Math.round(remMs / 3600000));
  }

  const resend = async () => {
    try {
      await api.post(`/admin/users/${user.user_id}/resend-verification`);
      toast.success('Verifizierungs-E-Mail erneut versendet');
      qc.invalidateQueries({ queryKey: ['admin-users'] });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Versand');
    }
  };

  // Iter 300 — Admin marks user as verified directly without email click
  const verifyNow = async () => {
    if (!window.confirm(`Nutzer ${user.email} ohne E-Mail-Bestätigung verifizieren?`)) return;
    try {
      await api.post(`/admin/users/${user.user_id}/verify-now`);
      toast.success('Nutzer manuell verifiziert');
      qc.invalidateQueries({ queryKey: ['admin-users'] });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler bei der Verifizierung');
    }
  };

  // Iter 380/382 — Admin setzt Passwort des Users zurück. Backend erzeugt ein
  // 4-aus-4-konformes Temp-Passwort, bumped token_version (= alle Sessions
  // dieses Users werden invalidiert), und setzt must_change_password=true.
  // UI: Shadcn-Dialog mit Confirm-Stufe + Result-Stufe (Clipboard-Copy),
  // ersetzt die alte window.confirm + window.prompt-Kombination.
  const [resetDialogOpen, setResetDialogOpen] = useState(false);

  return (
    <div className={`flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-3 sm:p-4 hover:bg-[#F3F4F1] transition-colors ${isInactive ? 'opacity-50' : ''}`}
      data-testid={`admin-user-${user.user_id}`}>
      {/* Row 1 on mobile: avatar + identity + actions */}
      <div className="flex items-start gap-3 flex-1 min-w-0 w-full sm:w-auto">
        <div className="relative w-9 h-9 flex-shrink-0">
          <div className="w-9 h-9 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center text-xs font-medium text-[#4A5D4E]">
            {user.avatar ? <img src={user.avatar} alt="" className="w-9 h-9 rounded-full object-cover" /> : ((user.display_name || user.name)?.[0]?.toUpperCase() || '?')}
          </div>
          <StatusDot status={user.online ? (user.status_mode || 'online') : 'offline'} />
        </div>
        <div className="flex-1 min-w-0">
          {/* Iter 340 — Anzeigename hat Vorrang, dann ggf. Vor+Nach, dann Legacy `name`. */}
          <span className="text-sm font-medium text-[#1C1F1D] block truncate">
            {user.display_name
              || ([user.first_name, user.last_name].filter(Boolean).join(' '))
              || user.name}
          </span>
          <span className="text-xs text-[#9CA3AF] block truncate">{user.email}</span>
          {user.phone && (
            <span className="text-[10px] text-[#6B7280] block truncate" data-testid={`admin-user-phone-${user.user_id}`}>{user.phone}</span>
          )}
          {/* Iter 379 — System-managed Module-Gruppen (`Modul: Standard`,
              `Modul: Verwaltung`, ...) sind interne Capability-Plumbing.
              Sie werden bei jeder Rollenänderung automatisch synchronisiert
              (siehe `sync_user_module_groups`) und können vom Admin nicht
              dauerhaft entfernt werden. Damit der Admin keinen redundanten
              und „nicht entfernbaren" Badge sieht, blenden wir Module-
              Gruppen hier komplett aus — die Modul-Sichtbarkeit ergibt sich
              ohnehin aus der Rolle (Mitarbeiter/Moderator/Admin/Gast). */}
          {(() => {
            const visibleGroups = groups.filter(g => !g.module_group);
            return visibleGroups.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {visibleGroups.map(g => (
                  <span key={g.group_id} className="text-[9px] px-1.5 py-0.5 rounded-full text-white whitespace-nowrap"
                    style={{ backgroundColor: g.color || '#4A5D4E' }}>{g.name}</span>
                ))}
              </div>
            );
          })()}
        </div>
        <div className="hidden md:block text-right flex-shrink-0" data-testid={`last-seen-${user.user_id}`}>
          {user.online ? (
            <span className="text-[10px] text-[#6B8E23] font-medium">Online</span>
          ) : user.last_seen ? (
            <>
              <p className="text-[10px] text-[#9CA3AF]">{t('lastSeen')}</p>
              <p className="text-xs text-[#1C1F1D]" title={new Date(user.last_seen).toLocaleString('de-DE')}>{timeAgo(user.last_seen, 'de')}</p>
            </>
          ) : (
            <span className="text-[10px] text-[#9CA3AF] italic">{t('neverLoggedIn')}</span>
          )}
          {/* Iter 379 — Letzter Passwort-Wechsel (Compliance). Wird angezeigt
              wenn der User schon einmal ein Passwort gesetzt hat. Roter Indikator
              wenn aelter als 6 Monate. */}
          {user.password_changed_at && (() => {
            const days = Math.floor((Date.now() - new Date(user.password_changed_at).getTime()) / (1000 * 60 * 60 * 24));
            const overdue = days >= 180;
            return (
              <p className={`text-[10px] mt-0.5 ${overdue ? 'text-rose-700 font-medium' : 'text-[#9CA3AF]'}`}
                title={`Letzter Passwort-Wechsel: ${new Date(user.password_changed_at).toLocaleDateString('de-DE')}`}
                data-testid={`pw-changed-${user.user_id}`}>
                PW: {timeAgo(user.password_changed_at, 'de')}
                {overdue && ' ⚠'}
              </p>
            );
          })()}
        </div>
      </div>
      {/* Row 2 on mobile: status badges (wrap) */}
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-1 pl-12 sm:pl-0">
        {/* Iter 379 — Rollen-Badge auf Deutsch lokalisieren via Shared-Helper. */}
        <Badge className={`text-[10px] capitalize ${roleColors[user.role] || 'bg-[#E8EAE6]'}`}>
          {roleLabel(user.role)}
        </Badge>
        {isInactive && <Badge className="text-[10px] bg-[#C87967]/10 text-[#C87967]">{t('deactivated')}</Badge>}
        {isLockedUnverified && (
          <Badge className="text-[10px] bg-rose-100 text-rose-700 border border-rose-300 inline-flex items-center gap-1"
                 data-testid={`verify-locked-${user.user_id}`}
                 title="Konto gesperrt: E-Mail nicht innerhalb der Frist bestätigt">
            <AlertCircle className="w-3 h-3" /> Gesperrt
          </Badge>
        )}
        {isPendingVerify && (
          <Badge className="text-[10px] bg-amber-100 text-amber-800 border border-amber-300 inline-flex items-center gap-1"
                 data-testid={`verify-pending-${user.user_id}`}
                 title={`Verifizierung läuft — auto-Sperre in ${remainingHours} h`}>
            <Hourglass className="w-3 h-3" /> Verifizierung läuft
            {remainingHours != null && <span className="opacity-70">({remainingHours}h)</span>}
          </Badge>
        )}
      </div>
      {/* Row 3 on mobile: action icons */}
      <div className="flex gap-1 flex-wrap pl-12 sm:pl-0 sm:flex-shrink-0">
        {showResend && (
          <>
            <button onClick={verifyNow} title="Nutzer jetzt manuell verifizieren"
              className="p-1.5 rounded-lg hover:bg-emerald-50 text-[#9CA3AF] hover:text-emerald-700 transition-colors"
              data-testid={`verify-now-${user.user_id}`}>
              <ShieldCheck className="w-4 h-4" />
            </button>
            <button onClick={resend} title="Verifizierungs-E-Mail erneut senden"
              className="p-1.5 rounded-lg hover:bg-[#4A5D4E]/10 text-[#9CA3AF] hover:text-[#4A5D4E] transition-colors"
              data-testid={`resend-verification-${user.user_id}`}>
              <Mail className="w-4 h-4" />
            </button>
          </>
        )}
        <button onClick={() => onToggleStatus(user.user_id)}
          title={isInactive ? 'Aktivieren' : 'Deaktivieren'}
          className={`p-1.5 rounded-lg transition-colors ${isInactive ? 'hover:bg-[#6B8E23]/10 text-[#9CA3AF] hover:text-[#6B8E23]' : 'hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]'}`}
          data-testid={`toggle-status-${user.user_id}`}>
          {isInactive ? <UserCheck className="w-4 h-4" /> : <UserX className="w-4 h-4" />}
        </button>
        <button onClick={() => onEdit(user)}
          className="p-1.5 rounded-lg hover:bg-[#E8EAE6] text-[#9CA3AF] hover:text-[#4A5D4E] transition-colors"
          data-testid={`edit-user-${user.user_id}`}><Edit className="w-4 h-4" /></button>
        {/* Iter 380 — Admin-Aktion „Passwort zurücksetzen". Wird besonders für
            User ohne E-Mail-Konto gebraucht (kein Self-Service-Reset möglich). */}
        {!isCurrentUser && (
          <button onClick={() => setResetDialogOpen(true)}
            title="Passwort zurücksetzen — User muss bei nächstem Login neues setzen"
            className="p-1.5 rounded-lg hover:bg-amber-50 text-[#9CA3AF] hover:text-amber-700 transition-colors"
            data-testid={`reset-password-${user.user_id}`}>
            <KeyRound className="w-4 h-4" />
          </button>
        )}
        {!isCurrentUser && (
          <button onClick={() => onForceLogout(user)} title="Sessions beenden (ausloggen erzwingen)"
            className="p-1.5 rounded-lg hover:bg-[#D4A373]/10 text-[#9CA3AF] hover:text-[#D4A373] transition-colors"
            data-testid={`force-logout-${user.user_id}`}><LogOut className="w-4 h-4" /></button>
        )}
        {!isCurrentUser && (
          <button onClick={() => onDelete(user)}
            className="p-1.5 rounded-lg hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967] transition-colors"
            data-testid={`delete-user-${user.user_id}`}><Trash2 className="w-4 h-4" /></button>
        )}
      </div>
      <ResetPasswordDialog
        open={resetDialogOpen}
        user={user}
        onOpenChange={setResetDialogOpen}
      />
    </div>
  );
}
