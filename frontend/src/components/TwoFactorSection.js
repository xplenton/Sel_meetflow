import { useEffect, useState } from 'react';
import api from '../lib/api';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { ShieldCheck, ShieldOff, Loader2, KeyRound, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

/**
 * Two-Factor (TOTP) settings block for the user's profile (iter 188).
 * Self-contained — drop into any page; uses /auth/2fa/* endpoints.
 */
export default function TwoFactorSection() {
  const [status, setStatus] = useState({ totp_enabled: false, recovery_codes_remaining: 0, totp_enabled_at: null });
  const [loading, setLoading] = useState(true);

  // Setup flow state
  const [setupOpen, setSetupOpen] = useState(false);
  const [setupData, setSetupData] = useState(null); // { secret, uri, qr_png, recovery_codes }
  const [setupCode, setSetupCode] = useState('');
  const [setupBusy, setSetupBusy] = useState(false);

  // Disable / regenerate state
  const [confirmOpen, setConfirmOpen] = useState(null); // 'disable' | 'regenerate' | null
  const [confirmCode, setConfirmCode] = useState('');
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [newRecoveryCodes, setNewRecoveryCodes] = useState(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/auth/2fa/status');
      setStatus(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const beginSetup = async () => {
    try {
      const { data } = await api.post('/auth/2fa/setup');
      setSetupData(data);
      setSetupCode('');
      setSetupOpen(true);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Setup fehlgeschlagen');
    }
  };

  const finishSetup = async () => {
    if (!setupCode || setupCode.length < 6) { toast.error('6-stelliger Code erforderlich'); return; }
    setSetupBusy(true);
    try {
      await api.post('/auth/2fa/verify-setup', { code: setupCode });
      toast.success('Zwei-Faktor aktiviert');
      setSetupOpen(false);
      setSetupData(null);
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Code ungültig');
    } finally { setSetupBusy(false); }
  };

  const submitConfirm = async () => {
    if (!confirmCode) { toast.error('Code erforderlich'); return; }
    setConfirmBusy(true);
    try {
      if (confirmOpen === 'disable') {
        await api.post('/auth/2fa/disable', { code: confirmCode });
        toast.success('Zwei-Faktor deaktiviert');
        setConfirmOpen(null);
        setConfirmCode('');
        await refresh();
      } else if (confirmOpen === 'regenerate') {
        const { data } = await api.post('/auth/2fa/regenerate-recovery', { code: confirmCode });
        setNewRecoveryCodes(data.recovery_codes);
        setConfirmOpen(null);
        setConfirmCode('');
        await refresh();
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Code ungültig');
    } finally { setConfirmBusy(false); }
  };

  const downloadRecovery = (codes, label) => {
    const blob = new Blob(
      [`MeetFlow Wiederherstellungscodes\nGeneriert: ${new Date().toISOString()}\n\nJEDER CODE IST NUR EINMAL VERWENDBAR.\nVerwahre diese Codes an einem sicheren Ort (z.B. Passwort-Manager).\n\n${codes.join('\n')}\n`],
      { type: 'text/plain' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `meetflow-recovery-codes-${label}.txt`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="pt-5 mt-2 border-t border-[#E2E4E0]" data-testid="two-factor-section">
      <div className="flex items-center gap-2 mb-1">
        {status.totp_enabled
          ? <ShieldCheck className="w-4 h-4 text-emerald-600" />
          : <ShieldOff className="w-4 h-4 text-[#9CA3AF]" />}
        <h3 className="text-sm font-semibold text-[#1C1F1D]">Zwei-Faktor-Authentifizierung</h3>
      </div>
      <p className="text-[11px] text-[#6B7280] mb-3 leading-relaxed">
        Schuetzt dein Konto durch einen zusaetzlichen 6-stelligen Code beim Login.
        Empfohlen vor allem für Admin- und Moderator-Konten.
      </p>

      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin text-[#9CA3AF]" />
      ) : status.totp_enabled ? (
        <div className="space-y-2">
          <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2" data-testid="totp-status-on">
            Aktiviert seit {status.totp_enabled_at ? new Date(status.totp_enabled_at).toLocaleString('de-DE') : ''}
            <br />
            <span className="text-[11px] opacity-80">{status.recovery_codes_remaining} Wiederherstellungscodes verbleibend</span>
          </div>
          <Button
            variant="outline"
            data-testid="totp-regenerate-button"
            onClick={() => { setConfirmOpen('regenerate'); setConfirmCode(''); }}
            className="w-full border-[#E2E4E0] rounded-full h-10 text-sm hover:bg-[#F3F4F1]"
          ><RefreshCw className="w-4 h-4 mr-2" /> Wiederherstellungscodes neu erstellen</Button>
          <Button
            variant="outline"
            data-testid="totp-disable-button"
            onClick={() => { setConfirmOpen('disable'); setConfirmCode(''); }}
            className="w-full border-[#C87967]/40 text-[#C87967] rounded-full h-10 text-sm hover:bg-[#C87967]/5 hover:text-[#C87967]"
          ><ShieldOff className="w-4 h-4 mr-2" /> Zwei-Faktor deaktivieren</Button>
        </div>
      ) : (
        <Button
          data-testid="totp-enable-button"
          onClick={beginSetup}
          className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-10 text-sm"
        ><ShieldCheck className="w-4 h-4 mr-2" /> Zwei-Faktor einrichten</Button>
      )}

      {/* Setup dialog ------------------------------------------------- */}
      <Dialog open={setupOpen} onOpenChange={(o) => { if (!o) { setSetupOpen(false); setSetupData(null); } }}>
        <DialogContent className="sm:max-w-[480px]" data-testid="totp-setup-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-[#4A5D4E]" /> Authenticator einrichten
            </DialogTitle>
          </DialogHeader>
          {setupData && (
            <div className="space-y-3 pt-2 text-sm">
              <p className="text-[#6B7280]">
                Scanne den QR-Code mit einer Authenticator-App (Google Authenticator, 1Password, Authy, ...).
              </p>
              <div className="flex justify-center bg-white border border-[#E2E4E0] rounded-lg p-3">
                <img src={setupData.qr_png} alt="TOTP QR" className="w-48 h-48" data-testid="totp-qr" />
              </div>
              <details className="text-xs text-[#6B7280]">
                <summary className="cursor-pointer">Manuell einrichten (Secret kopieren)</summary>
                <code className="block mt-1 p-2 bg-[#F3F4F1] rounded font-mono break-all" data-testid="totp-secret-text">{setupData.secret}</code>
              </details>

              <div className="border-t border-[#E2E4E0] pt-3">
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Wiederherstellungscodes</Label>
                <div className="grid grid-cols-2 gap-1 text-xs font-mono bg-[#F9F9F8] border border-[#E2E4E0] rounded-lg p-3" data-testid="totp-recovery-list">
                  {setupData.recovery_codes.map(c => <div key={c}>{c}</div>)}
                </div>
                <Button variant="outline" size="sm" className="mt-2 text-xs h-8"
                  data-testid="totp-recovery-download"
                  onClick={() => downloadRecovery(setupData.recovery_codes, 'setup')}
                >Codes als Datei speichern</Button>
                <p className="text-[11px] text-[#C87967] mt-2">
                  Bewahre die Codes sicher auf. Jeder Code ist nur einmal verwendbar und wird benötigt,
                  wenn du dein Gerät verlierst.
                </p>
              </div>

              <div className="border-t border-[#E2E4E0] pt-3">
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Code aus deiner App</Label>
                <Input
                  data-testid="totp-setup-code-input"
                  value={setupCode}
                  onChange={e => setSetupCode(e.target.value)}
                  placeholder="123456"
                  maxLength={6}
                  className="text-center font-mono text-lg tracking-widest border-[#E2E4E0] rounded-xl"
                />
              </div>

              <Button
                data-testid="totp-setup-submit"
                onClick={finishSetup}
                disabled={setupBusy || setupCode.length < 6}
                className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11"
              >{setupBusy ? '...' : 'Aktivieren'}</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Confirm dialog (disable / regenerate) ------------------------ */}
      <Dialog open={!!confirmOpen} onOpenChange={(o) => { if (!o) { setConfirmOpen(null); setConfirmCode(''); } }}>
        <DialogContent className="sm:max-w-[400px]" data-testid="totp-confirm-dialog">
          <DialogHeader>
            <DialogTitle>
              {confirmOpen === 'disable' ? 'Zwei-Faktor deaktivieren' : 'Wiederherstellungscodes erneuern'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 pt-2 text-sm">
            <p className="text-[#6B7280]">Bitte aktuellen 6-stelligen Code aus deiner Authenticator-App eingeben.</p>
            <Input
              data-testid="totp-confirm-code-input"
              value={confirmCode}
              onChange={e => setConfirmCode(e.target.value)}
              placeholder="123456"
              maxLength={6}
              className="text-center font-mono text-lg tracking-widest border-[#E2E4E0] rounded-xl"
              autoFocus
            />
            <Button
              data-testid="totp-confirm-submit"
              onClick={submitConfirm}
              disabled={confirmBusy || confirmCode.length < 6}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11"
            >{confirmBusy ? '...' : 'Bestätigen'}</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Fresh recovery codes display --------------------------------- */}
      <Dialog open={!!newRecoveryCodes} onOpenChange={(o) => { if (!o) setNewRecoveryCodes(null); }}>
        <DialogContent className="sm:max-w-[440px]" data-testid="totp-new-recovery-dialog">
          <DialogHeader>
            <DialogTitle>Neue Wiederherstellungscodes</DialogTitle>
          </DialogHeader>
          {newRecoveryCodes && (
            <div className="space-y-3 pt-2 text-sm">
              <p className="text-[#C87967]">
                Wichtig: Die alten Codes sind ab sofort Ungültig. Speichere die neuen Codes sicher ab,
                bevor du diesen Dialog schließt.
              </p>
              <div className="grid grid-cols-2 gap-1 text-xs font-mono bg-[#F9F9F8] border border-[#E2E4E0] rounded-lg p-3">
                {newRecoveryCodes.map(c => <div key={c}>{c}</div>)}
              </div>
              <Button variant="outline" size="sm" className="text-xs h-8"
                data-testid="totp-new-recovery-download"
                onClick={() => downloadRecovery(newRecoveryCodes, 'fresh')}>
                Codes als Datei speichern
              </Button>
              <Button onClick={() => setNewRecoveryCodes(null)} className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-10">
                Schließen
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
