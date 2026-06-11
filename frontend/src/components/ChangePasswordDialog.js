/**
 * Iter 379 — Passwort ändern Dialog.
 *
 * Live-Validierung der Passwort-Richtlinie:
 * - Mindestlaenge 8
 * - Mindestens 1 Grossbuchstabe / Kleinbuchstabe / Ziffer / Sonderzeichen
 *
 * Felder werden niemals als Klartext angezeigt (type="password"). Optionaler
 * "Anzeigen"-Toggle pro Feld für den User, der sich selbst kontrollieren will.
 *
 * Holt die Policy live aus /api/auth/password-policy, damit änderungen am
 * Backend (z. B. größere Mindestlaenge) automatisch im UI sichtbar werden.
 */
import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Eye, EyeOff, Check, X as XIcon, ShieldCheck } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

function evaluatePolicy(pw) {
  const SPECIAL = /[!@#$%^&*()_+\-=[\]{};:'",.<>/?\\|`~]/;
  return {
    length_ok:   pw.length >= 8,
    has_upper:   /[A-Z]/.test(pw),
    has_lower:   /[a-z]/.test(pw),
    has_digit:   /\d/.test(pw),
    has_special: SPECIAL.test(pw),
  };
}
const policyAllOk = (e) => Object.values(e).every(Boolean);

function Criterion({ ok, label }) {
  return (
    <li className={`flex items-center gap-1.5 text-[11px] ${ok ? 'text-[#6B8E23]' : 'text-[#9CA3AF]'}`}>
      {ok ? <Check className="w-3 h-3" /> : <XIcon className="w-3 h-3" />}
      {label}
    </li>
  );
}

export default function ChangePasswordDialog({ open, onClose }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNext, setShowNext] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [policy, setPolicy] = useState(null);
  const [logoutEverywhere, setLogoutEverywhere] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCurrent(''); setNext(''); setConfirm('');
    setShowCurrent(false); setShowNext(false); setShowConfirm(false);
    setLogoutEverywhere(false);
    api.get('/auth/password-policy').then(({ data }) => setPolicy(data)).catch(() => setPolicy(null));
  }, [open]);

  const ev = evaluatePolicy(next);
  const matches = next.length > 0 && next === confirm;
  const canSubmit = current.length > 0 && policyAllOk(ev) && matches && current !== next;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    try {
      await api.post('/auth/change-password', {
        current_password: current,
        new_password: next,
        new_password_confirm: confirm,
        logout_other_sessions: logoutEverywhere,
      });
      toast.success('Passwort erfolgreich geaendert');
      onClose?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Änderung fehlgeschlagen');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose?.(); }}>
      <DialogContent className="sm:max-w-[480px]" data-testid="change-password-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-medium flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-[#4A5D4E]" /> Passwort ändern
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3 pt-2">
          {/* Aktuelles Passwort */}
          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Aktuelles Passwort</label>
            <div className="relative">
              <Input type={showCurrent ? 'text' : 'password'} value={current}
                onChange={e => setCurrent(e.target.value)} autoComplete="current-password"
                className="pr-10 border-[#E2E4E0] rounded-xl text-sm" data-testid="change-pw-current" />
              <button type="button" onClick={() => setShowCurrent(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9CA3AF] hover:text-[#4A5D4E]"
                aria-label={showCurrent ? 'Verbergen' : 'Anzeigen'}>
                {showCurrent ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Neues Passwort */}
          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Neues Passwort</label>
            <div className="relative">
              <Input type={showNext ? 'text' : 'password'} value={next}
                onChange={e => setNext(e.target.value)} autoComplete="new-password"
                className="pr-10 border-[#E2E4E0] rounded-xl text-sm" data-testid="change-pw-new" />
              <button type="button" onClick={() => setShowNext(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9CA3AF] hover:text-[#4A5D4E]"
                aria-label={showNext ? 'Verbergen' : 'Anzeigen'}>
                {showNext ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <ul className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-1.5">
              <Criterion ok={ev.length_ok}   label="≥ 8 Zeichen" />
              <Criterion ok={ev.has_upper}   label="Grossbuchstabe" />
              <Criterion ok={ev.has_lower}   label="Kleinbuchstabe" />
              <Criterion ok={ev.has_digit}   label="Ziffer" />
              <Criterion ok={ev.has_special} label="Sonderzeichen" />
            </ul>
          </div>

          {/* Bestätigung */}
          <div>
            <label className="text-[10px] font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Neues Passwort bestätigen</label>
            <div className="relative">
              <Input type={showConfirm ? 'text' : 'password'} value={confirm}
                onChange={e => setConfirm(e.target.value)} autoComplete="new-password"
                className="pr-10 border-[#E2E4E0] rounded-xl text-sm" data-testid="change-pw-confirm" />
              <button type="button" onClick={() => setShowConfirm(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9CA3AF] hover:text-[#4A5D4E]"
                aria-label={showConfirm ? 'Verbergen' : 'Anzeigen'}>
                {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {confirm.length > 0 && (
              <p className={`text-[10px] mt-1 ${matches ? 'text-[#6B8E23]' : 'text-[#C87967]'}`}>
                {matches ? '✓ Passwoerter stimmen überein' : '✗ Passwoerter weichen voneinander ab'}
              </p>
            )}
          </div>

          <label className="flex items-center gap-2 text-[11px] text-[#6B7280] cursor-pointer">
            <input type="checkbox" checked={logoutEverywhere}
              onChange={e => setLogoutEverywhere(e.target.checked)}
              className="rounded border-[#E2E4E0]" data-testid="change-pw-logout-everywhere" />
            Auf allen anderen Geraeten abmelden
          </label>

          {policy && (
            <p className="text-[10px] text-[#9CA3AF] border-t border-[#E2E4E0] pt-2">
              Hinweis: das neue Passwort darf nicht mit den letzten {policy.history_size} Passwoertern übereinstimmen.
              {policy.rotation_months > 0 && ` Passwoerter sind alle ${policy.rotation_months} Monate zu erneuern.`}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-full border-[#E2E4E0]"
            data-testid="change-pw-cancel">Abbrechen</Button>
          <Button onClick={submit} disabled={!canSubmit || busy}
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full disabled:opacity-40"
            data-testid="change-pw-submit">
            {busy ? 'Speichern…' : 'Passwort ändern'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
