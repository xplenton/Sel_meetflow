/**
 * Iter 379 — Banner: zwingt zum Passwort-Wechsel, wenn Backend `must_change_password=true`
 * für den User gemeldet hat (entweder durch ablaufende Rotation oder durch
 * Admin-Initialpasswort).
 *
 * Wird global (App.js) gemountet — der User kann den Dialog NICHT schließen
 * ohne sein Passwort zu ändern. Logout bleibt jederzeit möglich.
 */
import { useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Button } from './ui/button';
import ChangePasswordDialog from './ChangePasswordDialog';

export default function MustChangePasswordBanner() {
  const { user, refresh } = useAuth();
  const [open, setOpen] = useState(false);

  if (!user || !user.must_change_password) return null;

  const handleClose = async () => {
    setOpen(false);
    // Nach dem Schließen `/auth/me` neu laden — wenn der Wechsel
    // erfolgreich war, ist `must_change_password` weg und das Banner verschwindet.
    if (typeof refresh === 'function') {
      try { await refresh(); } catch { /* ignore */ }
    } else {
      // Fallback: hard reload
      window.location.reload();
    }
  };

  return (
    <>
      <div
        className="fixed top-0 left-0 right-0 z-[120] bg-[#C87967] text-white shadow-lg"
        data-testid="must-change-password-banner"
        role="alert"
      >
        <div className="max-w-7xl mx-auto px-4 py-2.5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <ShieldAlert className="w-4 h-4 flex-shrink-0" />
            <span>Bitte ändere dein Passwort — es ist abgelaufen oder muss erstmalig gesetzt werden.</span>
          </div>
          <Button
            size="sm"
            onClick={() => setOpen(true)}
            className="bg-white text-[#C87967] hover:bg-white/90 rounded-full font-medium shrink-0"
            data-testid="must-change-password-cta"
          >
            Jetzt ändern
          </Button>
        </div>
      </div>
      <ChangePasswordDialog open={open} onClose={handleClose} />
    </>
  );
}
