import { useEffect, useState } from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Video, Save, RefreshCw, Eye, EyeOff, CheckCircle2, AlertCircle } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

/**
 * Admin panel (iter 136) to manage LiveKit Cloud credentials at runtime.
 * The backend keeps .env values as a fallback; whatever the admin saves here
 * lives in the `system_config` collection and takes precedence. The secret
 * is never returned in plain — we show a masked form (API•••xyz) and only
 * submit a new secret when the field is non-empty, so admins can rotate URL
 * or key without re-entering the full secret.
 */
export default function LiveKitConfigPanel() {
  const [url, setUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [showSecret, setShowSecret] = useState(false);
  const [secretMasked, setSecretMasked] = useState('');
  const [secretSet, setSecretSet] = useState(false);
  const [threshold, setThreshold] = useState(4);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState('');

  const load = async (attempt = 0) => {
    setLoading(true);
    setLoadError('');
    try {
      const [{ data: cfg }, { data: status }] = await Promise.all([
        api.get('/livekit/admin/config'),
        api.get('/livekit/config-status'),
      ]);
      setUrl(cfg.url || '');
      setApiKey(cfg.api_key || '');
      setSecretMasked(cfg.api_secret_masked || '');
      setSecretSet(!!cfg.api_secret_set);
      setThreshold(cfg.upgrade_threshold || 4);
      setConfigured(!!status.configured);
    } catch (e) {
      // iter 180 — transient failure right after a pod restart: retry once
      // after 1.5 s before surfacing the error to the admin.
      if (attempt === 0) {
        await new Promise(r => setTimeout(r, 1500));
        return load(1);
      }
      const backend = e?.response?.data?.detail || e?.message || 'Unbekannter Fehler';
      const status = e?.response?.status;
      setLoadError(status === 403
        ? 'Keine Admin-Berechtigung für LiveKit-Konfiguration'
        : `Konfiguration konnte nicht geladen werden: ${backend}`
      );
      toast.error(status === 403 ? 'Keine Admin-Berechtigung' : `LiveKit: ${backend}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!url.trim() || !apiKey.trim()) {
      toast.error('URL und API Key sind erforderlich');
      return;
    }
    if (!secretSet && !apiSecret.trim()) {
      toast.error('API Secret ist beim ersten Speichern erforderlich');
      return;
    }
    setSaving(true);
    try {
      await api.post('/livekit/admin/config', {
        url: url.trim(),
        api_key: apiKey.trim(),
        api_secret: apiSecret.trim(), // empty = keep existing
        upgrade_threshold: Math.max(2, Math.min(20, parseInt(threshold, 10) || 4)),
      });
      toast.success('LiveKit-Konfiguration gespeichert');
      setApiSecret(''); // clear the plaintext field
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="bg-white rounded-2xl border border-[#E2E4E0] p-6" data-testid="livekit-config-panel">
      <div className="flex items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-[#6B8E23]/10 flex items-center justify-center">
            <Video className="w-4 h-4 text-[#6B8E23]" />
          </div>
          <div>
            <h2 className="text-sm font-medium text-[#1C1F1D]">LiveKit SFU Konfiguration</h2>
            <p className="text-[11px] text-[#6B7280]">Video-Transport für alle Meetings (iter 140)</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {configured ? (
            <span className="flex items-center gap-1 text-[10px] text-[#6B8E23] bg-[#6B8E23]/10 px-2 py-1 rounded-full">
              <CheckCircle2 className="w-3 h-3" /> Aktiv
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-[#C87967] bg-[#C87967]/10 px-2 py-1 rounded-full">
              <AlertCircle className="w-3 h-3" /> Nicht konfiguriert
            </span>
          )}
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}
                  className="rounded-full text-[#6B7280]" data-testid="livekit-reload-btn">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {loadError && (
        <div className="mb-4 p-3 bg-[#C87967]/5 border border-[#C87967]/20 rounded-xl flex items-start gap-2" data-testid="livekit-load-error">
          <AlertCircle className="w-4 h-4 text-[#C87967] flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-[11px] text-[#4B5563]">
            <strong className="text-[#1C1F1D]">{loadError}</strong>
            <p className="text-[10px] text-[#9CA3AF] mt-0.5">
              Häufige Ursachen: Server kurz nach Neustart noch nicht bereit, fehlende Admin-Berechtigung,
              oder Netzwerkproblem. Erneut versuchen löst das meist.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => load(0)}
                  className="rounded-full text-xs h-8 border-[#E2E4E0] flex-shrink-0"
                  data-testid="livekit-retry-btn">
            <RefreshCw className="w-3.5 h-3.5 mr-1" /> Erneut versuchen
          </Button>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
            LiveKit URL
          </Label>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="wss://your-project.livekit.cloud"
            className="border-[#E2E4E0] rounded-lg font-mono text-xs"
            data-testid="livekit-url-input"
            disabled={loading}
          />
          <p className="text-[10px] text-[#9CA3AF] mt-1">Aus cloud.livekit.io → Settings → Keys</p>
        </div>

        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
            API Key
          </Label>
          <Input
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="API…"
            className="border-[#E2E4E0] rounded-lg font-mono text-xs"
            data-testid="livekit-key-input"
            disabled={loading}
          />
        </div>

        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
            API Secret {secretSet && <span className="text-[10px] normal-case tracking-normal font-normal text-[#6B8E23]">— gesetzt: {secretMasked}</span>}
          </Label>
          <div className="relative">
            <Input
              type={showSecret ? 'text' : 'password'}
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              placeholder={secretSet ? 'Leer lassen, um bestehendes Secret zu behalten' : 'Neues Secret eingeben'}
              className="border-[#E2E4E0] rounded-lg font-mono text-xs pr-9"
              data-testid="livekit-secret-input"
              disabled={loading}
            />
            <button
              type="button"
              onClick={() => setShowSecret(v => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[#9CA3AF] hover:text-[#1C1F1D]"
              aria-label={showSecret ? 'Verbergen' : 'Anzeigen'}
              data-testid="livekit-secret-toggle"
            >
              {showSecret ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
            Auto-Upgrade Schwellenwert (Legacy)
          </Label>
          <Input
            type="number"
            min={2}
            max={20}
            value={threshold}
            onChange={(e) => setThreshold(parseInt(e.target.value, 10) || 2)}
            className="border-[#E2E4E0] rounded-lg text-xs w-24"
            data-testid="livekit-threshold-input"
            disabled={loading}
          />
          <p className="text-[10px] text-[#9CA3AF] mt-1">
            Seit iter 140 nutzen <strong>alle</strong> Meetings LiveKit — die Mesh-WebRTC-Route wurde entfernt.
            Dieser Wert ist nur noch für Abwärtskompatibilität mit älteren Clients relevant.
          </p>
        </div>

        <div className="pt-2 flex items-center gap-3">
          <Button
            onClick={save}
            disabled={saving || loading}
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-5"
            data-testid="livekit-save-btn"
          >
            {saving ? '...' : <><Save className="w-3.5 h-3.5 mr-1.5" /> Speichern</>}
          </Button>
          <span className="text-[11px] text-[#9CA3AF]">
            Änderungen gelten sofort für neue Meetings — laufende Sitzungen bleiben unverändert.
          </span>
        </div>
      </div>
    </section>
  );
}
