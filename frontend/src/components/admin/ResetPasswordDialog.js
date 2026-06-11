import { useState, useRef, useEffect } from 'react';
import { KeyRound, Copy, Check, AlertTriangle } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import api from '../../lib/api';

/**
 * Iter 382 — Admin-Workflow „Passwort zurücksetzen".
 *
 * Loest die alte window.confirm + window.prompt-Kombination ab durch einen
 * zweistufigen Shadcn-Dialog:
 *
 *   Stufe 1 (confirm): Erklaert was passiert (Temp-PW, alle Sessions weg,
 *                       must_change_password). Buttons: Abbrechen / Zurücksetzen.
 *   Stufe 2 (result):  Zeigt das Temp-PW in einem read-only Code-Block mit
 *                       prominentem „Kopieren"-Button (Clipboard API +
 *                       Fallback execCommand). Erst nach „Schließen"-Klick
 *                       wird der Dialog wirklich geschlossen — Admin kann
 *                       so sicherstellen, dass das PW kopiert wurde.
 *
 * Ersetzt: window.confirm + window.prompt in AdminUserRow.js.
 */
export default function ResetPasswordDialog({ open, user, onOpenChange }) {
  const qc = useQueryClient();
  const [stage, setStage] = useState('confirm'); // 'confirm' | 'submitting' | 'result'
  const [tempPw, setTempPw] = useState('');
  const [copied, setCopied] = useState(false);
  const copyResetRef = useRef(null);

  // Reset wenn der Dialog frisch geoeffnet wird.
  useEffect(() => {
    if (open) {
      setStage('confirm');
      setTempPw('');
      setCopied(false);
    }
    return () => {
      if (copyResetRef.current) clearTimeout(copyResetRef.current);
    };
  }, [open]);

  if (!user) return null;

  const ident = user.no_email_account
    ? `Personalnummer ${user.personnel_number || '?'}`
    : user.email;
  const displayName = user.display_name
    || [user.first_name, user.last_name].filter(Boolean).join(' ')
    || user.name
    || ident;

  const handleConfirm = async () => {
    setStage('submitting');
    try {
      const { data } = await api.post(`/admin/users/${user.user_id}/reset-password`, {});
      setTempPw(data.new_password || '');
      setStage('result');
      qc.invalidateQueries({ queryKey: ['admin-users'] });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Zurücksetzen');
      setStage('confirm');
    }
  };

  const handleCopy = async () => {
    try {
      // Clipboard API ist nur in HTTPS-Kontexten verfügbar (Preview + Prod
      // erfüllen das); im seltenen non-secure-Kontext faellt die Funktion
      // auf den execCommand-Pfad zurück.
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(tempPw);
      } else {
        const ta = document.createElement('textarea');
        ta.value = tempPw;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      toast.success('Temp-Passwort in Zwischenablage kopiert');
      if (copyResetRef.current) clearTimeout(copyResetRef.current);
      copyResetRef.current = setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error('Kopieren fehlgeschlagen — bitte manuell markieren');
    }
  };

  const handleClose = () => {
    if (stage === 'result') {
      toast.success('User muss beim nächsten Login ein neues Passwort setzen');
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o && stage !== 'submitting') handleClose(); }}>
      <DialogContent className="sm:max-w-md" data-testid="reset-password-dialog">
        {stage !== 'result' ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-amber-600" />
                Passwort zurücksetzen
              </DialogTitle>
              <DialogDescription className="pt-2">
                <span className="block font-medium text-[#1C1F1D]">{displayName}</span>
                <span className="block text-xs text-[#6B7280] mt-0.5">{ident}</span>
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 text-sm text-[#374151]">
              <p>Es wird ein neues policy-konformes Temp-Passwort erzeugt.</p>
              <ul className="list-disc pl-5 space-y-1 text-xs text-[#6B7280]">
                <li>Alle aktiven Sessions dieses Users werden beendet.</li>
                <li>Der User wird beim nächsten Login zum Wechsel gezwungen.</li>
                <li>Du musst das Temp-Passwort persoenlich übermitteln.</li>
              </ul>
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 flex gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>Diese Aktion ist nicht widerrufbar. Sicher fortfahren?</span>
              </div>
            </div>
            <DialogFooter className="gap-2">
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={stage === 'submitting'}
                data-testid="reset-password-cancel"
              >
                Abbrechen
              </Button>
              <Button
                onClick={handleConfirm}
                disabled={stage === 'submitting'}
                className="bg-amber-600 hover:bg-amber-700 text-white"
                data-testid="reset-password-confirm"
              >
                {stage === 'submitting' ? 'Bitte warten...' : 'Passwort zurücksetzen'}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-emerald-600" />
                Neues Temp-Passwort
              </DialogTitle>
              <DialogDescription className="pt-2">
                Bitte übermittle das Passwort persoenlich an{' '}
                <span className="font-medium text-[#1C1F1D]">{displayName}</span>.
                Es ist nach diesem Schließen nicht mehr abrufbar.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div className="flex items-stretch gap-2">
                <code
                  className="flex-1 min-w-0 rounded-lg border border-[#E5E7EB] bg-[#F3F4F1] px-3 py-2.5 font-mono text-sm text-[#1C1F1D] select-all break-all"
                  data-testid="reset-password-value"
                >
                  {tempPw}
                </code>
                <Button
                  onClick={handleCopy}
                  variant="outline"
                  className="flex-shrink-0 px-3"
                  title="In Zwischenablage kopieren"
                  data-testid="reset-password-copy"
                >
                  {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
              <p className="text-xs text-[#6B7280]">
                Der User muss das Passwort beim nächsten Login zweimal eingeben und durch ein
                eigenes ersetzen (4-aus-4-Regel, min. 8 Zeichen).
              </p>
            </div>
            <DialogFooter>
              <Button
                onClick={handleClose}
                className="bg-[#4A5D4E] hover:bg-[#3a4a3e] text-white"
                data-testid="reset-password-close"
              >
                Schließen
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
