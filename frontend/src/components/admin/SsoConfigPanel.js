import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Textarea } from '../ui/textarea';
import {
  ShieldCheck, Cloud, Copy, Loader2, CheckCircle, AlertCircle, ExternalLink,
} from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

const DEFAULT_CFG = {
  enabled: false,
  tenant_id: '',
  client_id: '',
  client_secret: '',
  has_secret: false,
  button_label: 'Mit Microsoft anmelden',
  allowed_domains: [],
  redirect_uri: '',
  updated_at: null,
  updated_by: null,
};

export default function SsoConfigPanel() {
  const [cfg, setCfg] = useState(DEFAULT_CFG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [secretEdited, setSecretEdited] = useState(false);
  const [domainsText, setDomainsText] = useState('');

  const fetchCfg = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/admin/sso/azure');
      setCfg({ ...DEFAULT_CFG, ...data });
      setDomainsText((data.allowed_domains || []).join(', '));
      setSecretEdited(false);
    } catch {
      toast.error('SSO-Konfiguration konnte nicht geladen werden');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchCfg(); }, [fetchCfg]);

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      const payload = {
        enabled: !!cfg.enabled,
        tenant_id: (cfg.tenant_id || '').trim(),
        client_id: (cfg.client_id || '').trim(),
        button_label: (cfg.button_label || '').trim() || 'Mit Microsoft anmelden',
        allowed_domains: domainsText
          .split(',').map(s => s.trim().toLowerCase()).filter(Boolean),
      };
      if (secretEdited && cfg.client_secret && !cfg.client_secret.startsWith('***')) {
        payload.client_secret = cfg.client_secret;
      }
      const { data } = await api.put('/admin/sso/azure', payload);
      setCfg({ ...DEFAULT_CFG, ...data });
      setDomainsText((data.allowed_domains || []).join(', '));
      setSecretEdited(false);
      toast.success('SSO-Konfiguration gespeichert');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post('/admin/sso/azure/test');
      setTestResult({ ok: true, ...data });
      toast.success('Tenant gefunden – Microsoft erreichbar');
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Test fehlgeschlagen';
      setTestResult({ ok: false, error: msg });
      toast.error(msg);
    } finally {
      setTesting(false);
    }
  };

  const copy = (val, what) => {
    try {
      navigator.clipboard.writeText(val);
      toast.success(`${what} kopiert`);
    } catch { /* ignore */ }
  };

  if (loading) {
    return (
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 flex items-center gap-2 text-[#6B7280]">
        <Loader2 className="w-4 h-4 animate-spin" /> SSO-Konfiguration wird geladen…
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="sso-azure-panel">
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
        <div className="flex items-start justify-between mb-5 gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#4A5D4E]/10 flex items-center justify-center">
              <Cloud className="w-5 h-5 text-[#4A5D4E]" />
            </div>
            <div>
              <h3 className="text-base font-medium text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
                Microsoft Entra ID (Azure AD) SSO
              </h3>
              <p className="text-xs text-[#9CA3AF] mt-0.5">
                Single Sign-On per OIDC. Neue Nutzer werden automatisch mit Rolle „user" angelegt.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Switch
              data-testid="sso-azure-enabled-toggle"
              checked={!!cfg.enabled}
              onCheckedChange={(v) => setCfg(prev => ({ ...prev, enabled: v }))}
            />
            <span className="text-xs font-medium text-[#1C1F1D]">{cfg.enabled ? 'aktiv' : 'aus'}</span>
          </div>
        </div>

        {/* Redirect URI — read-only, copyable */}
        <div className="mb-5 p-3 rounded-lg bg-[#F3F4F1] border border-[#E2E4E0]">
          <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
            Redirect URI (in Azure App Registration eintragen)
          </Label>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs text-[#1C1F1D] break-all bg-white px-2 py-1.5 rounded border border-[#E2E4E0]">
              {cfg.redirect_uri}
            </code>
            <Button
              type="button" size="sm" variant="ghost"
              onClick={() => copy(cfg.redirect_uri, 'Redirect URI')}
              data-testid="sso-azure-copy-redirect"
            >
              <Copy className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
              Tenant ID (Directory)
            </Label>
            <Input
              data-testid="sso-azure-tenant-id"
              value={cfg.tenant_id}
              onChange={e => setCfg(p => ({ ...p, tenant_id: e.target.value }))}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="font-mono text-xs"
            />
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
              Client ID (Application)
            </Label>
            <Input
              data-testid="sso-azure-client-id"
              value={cfg.client_id}
              onChange={e => setCfg(p => ({ ...p, client_id: e.target.value }))}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="font-mono text-xs"
            />
          </div>
        </div>

        <div className="mb-4">
          <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
            Client Secret {cfg.has_secret && !secretEdited && <span className="text-[#4A5D4E] font-normal normal-case tracking-normal ml-1">· hinterlegt</span>}
          </Label>
          <Input
            data-testid="sso-azure-client-secret"
            type="password"
            value={cfg.client_secret}
            onFocus={() => { if (cfg.client_secret === '***') { setCfg(p => ({ ...p, client_secret: '' })); setSecretEdited(true); } }}
            onChange={e => { setCfg(p => ({ ...p, client_secret: e.target.value })); setSecretEdited(true); }}
            placeholder={cfg.has_secret ? 'Leer lassen = bestehendes Secret behalten' : 'Wert (NICHT die Secret-ID)'}
            className="font-mono text-xs"
            autoComplete="new-password"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
              Button-Beschriftung
            </Label>
            <Input
              data-testid="sso-azure-button-label"
              value={cfg.button_label}
              onChange={e => setCfg(p => ({ ...p, button_label: e.target.value }))}
              placeholder="Mit Microsoft anmelden"
            />
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
              Domain-Whitelist (optional, kommagetrennt)
            </Label>
            <Input
              data-testid="sso-azure-allowed-domains"
              value={domainsText}
              onChange={e => setDomainsText(e.target.value)}
              placeholder="z. B. meinefirma.de, partner.com"
            />
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <Button
            data-testid="sso-azure-save"
            onClick={handleSave} disabled={saving}
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4 mr-2" />}
            Speichern
          </Button>
          <Button
            data-testid="sso-azure-test"
            type="button" variant="outline"
            onClick={handleTest} disabled={testing || !cfg.has_secret}
            className="rounded-full"
            title={!cfg.has_secret ? 'Erst speichern, dann testen' : ''}
          >
            {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4 mr-2" />}
            Verbindung testen
          </Button>
          {cfg.updated_at && (
            <span className="text-[11px] text-[#9CA3AF]">
              zuletzt gespeichert {new Date(cfg.updated_at).toLocaleString('de-DE')}
              {cfg.updated_by ? ` von ${cfg.updated_by}` : ''}
            </span>
          )}
        </div>

        {testResult && (
          <div
            data-testid="sso-azure-test-result"
            className={`mt-4 p-3 rounded-lg border text-xs ${
              testResult.ok ? 'bg-[#4A5D4E]/5 border-[#4A5D4E]/20 text-[#1C1F1D]' : 'bg-[#C87967]/10 border-[#C87967]/30 text-[#C87967]'
            }`}
          >
            {testResult.ok ? (
              <div className="flex items-start gap-2">
                <CheckCircle className="w-4 h-4 text-[#4A5D4E] shrink-0 mt-0.5" />
                <div>
                  <div className="font-medium mb-1">Verbindung erfolgreich</div>
                  <div className="text-[11px] text-[#6B7280] break-all">Issuer: {testResult.issuer}</div>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <div>{testResult.error}</div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Setup-Anleitung */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
        <h4 className="text-sm font-medium text-[#1C1F1D] mb-3" style={{ fontFamily: 'Manrope' }}>
          Anleitung: Azure App Registration anlegen
        </h4>
        <ol className="text-xs text-[#4B5563] space-y-2 list-decimal pl-5 leading-relaxed">
          <li>
            <a href="https://portal.azure.com" target="_blank" rel="noopener noreferrer" className="text-[#4A5D4E] hover:underline">
              Azure Portal
            </a>{' '}
            öffnen → <strong>Microsoft Entra ID</strong> → <strong>App registrations</strong> → <strong>+ New registration</strong>
          </li>
          <li>Name vergeben (z. B. <em>MeetFlow SSO</em>), <em>Single tenant</em> wählen, <strong>Redirect URI</strong> (oben kopierbar) als <em>Web</em>-Typ eintragen.</li>
          <li>Auf „<strong>Overview</strong>" gehen → <strong>Application (client) ID</strong> und <strong>Directory (tenant) ID</strong> kopieren und oben einfügen.</li>
          <li>„<strong>Certificates &amp; secrets</strong>" → <em>+ New client secret</em> → den angezeigten <strong>Value</strong> (NICHT die Secret-ID!) sofort kopieren und oben einfügen.</li>
          <li>„<strong>API permissions</strong>" → <em>Microsoft Graph</em> → <em>Delegated</em> → <strong>openid, profile, email, User.Read</strong> hinzufügen → <em>Grant admin consent</em>.</li>
          <li>Oben Schalter <strong>auf „aktiv"</strong> stellen → <strong>Speichern</strong> → <strong>Verbindung testen</strong>.</li>
        </ol>
      </div>
    </div>
  );
}
