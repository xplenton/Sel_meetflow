import { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../../contexts/LanguageContext';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
  CheckCircle, AlertCircle, Mail, Send, Server,
  Shield, Loader2, RefreshCw, AlertTriangle, Copy,
} from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

const DEFAULT_SMTP = {
  host: '', port: 587, username: '', password: '',
  use_tls: false, use_starttls: true,
  from_name: 'MeetFlow', from_email: '',
};

export default function EmailConfigPanel() {
  const { t } = useLanguage();
  const [config, setConfig] = useState({
    provider: 'none', api_key: '', sender_email: 'noreply@meetflow.app',
    enabled: false, smtp: DEFAULT_SMTP, fallback_to_smtp: false,
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [keyEdited, setKeyEdited] = useState(false);
  const [smtpPwEdited, setSmtpPwEdited] = useState(false);
  const [smtpHealth, setSmtpHealth] = useState(null);
  const [checkingSmtp, setCheckingSmtp] = useState(false);
  const [dnsResult, setDnsResult] = useState(null);
  const [dnsLoading, setDnsLoading] = useState(false);
  const [dnsDomain, setDnsDomain] = useState('');
  // Iter 182 — track saved snapshot so we can warn about unsaved changes
  const [savedSnapshot, setSavedSnapshot] = useState('');

  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await api.get('/admin/email-config');
      const next = { ...data, smtp: { ...DEFAULT_SMTP, ...(data.smtp || {}) } };
      setConfig(next);
      setSavedSnapshot(JSON.stringify({
        provider: next.provider, sender_email: next.sender_email, enabled: next.enabled,
        fallback_to_smtp: next.fallback_to_smtp, smtp: next.smtp,
      }));
      if (!dnsDomain) setDnsDomain(data.sender_email || '');
    } catch { /* ignore */ }
  }, [dnsDomain]);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const updateSmtp = (patch) => setConfig(prev => ({ ...prev, smtp: { ...prev.smtp, ...patch } }));

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        provider: config.provider,
        sender_email: config.sender_email,
        enabled: config.enabled,
        fallback_to_smtp: !!config.fallback_to_smtp,
      };
      if (keyEdited && config.api_key && !String(config.api_key).startsWith('***')) {
        payload.api_key = config.api_key;
      }
      // Always include smtp block. Omit password if masked (server keeps stored value).
      const smtp = { ...config.smtp };
      if (!smtpPwEdited || String(smtp.password || '').startsWith('***')) delete smtp.password;
      payload.smtp = smtp;
      await api.put('/admin/email-config', payload);
      toast.success('E-Mail-Konfiguration gespeichert');
      setKeyEdited(false);
      setSmtpPwEdited(false);
      fetchConfig();
    } catch { toast.error('Fehler beim Speichern'); }
    finally { setSaving(false); }
  };

  const handleTest = async (targetProvider) => {
    setTesting(true);
    setTestResult(null);
    try {
      const body = {
        to_email: config.sender_email || '',
        sender_email: config.sender_email || '',
      };
      if (targetProvider) body.provider = targetProvider;
      // Iter 182 — if testing SMTP, always pass the current UI state so the
      // admin can verify unsaved changes (most common cause of "works in UI
      // but invites don't arrive" is that the save step was skipped).
      if (targetProvider === 'smtp') {
        const smtp = { ...config.smtp };
        if (!smtpPwEdited || String(smtp.password || '').startsWith('***')) delete smtp.password;
        body.smtp = smtp;
      }
      const { data } = await api.post('/admin/email-config/test', body);
      setTestResult(data);
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.error || 'Fehler';
      setTestResult({ provider: 'error', status: 'failed', detail: typeof detail === 'string' ? detail : JSON.stringify(detail) });
    } finally { setTesting(false); }
  };

  const handleSmtpHealth = async () => {
    setCheckingSmtp(true);
    setSmtpHealth(null);
    try {
      const smtp = { ...config.smtp };
      if (!smtpPwEdited || String(smtp.password || '').startsWith('***')) delete smtp.password;
      const { data } = await api.post('/admin/email-config/smtp-health', { smtp });
      setSmtpHealth(data);
    } catch (err) {
      setSmtpHealth({ ok: false, error: err.response?.data?.detail || 'Verbindungsfehler' });
    } finally { setCheckingSmtp(false); }
  };

  const handleDnsCheck = async () => {
    if (!dnsDomain.trim()) { toast.error('Bitte Domain oder E-Mail eintragen'); return; }
    setDnsLoading(true);
    setDnsResult(null);
    try {
      const { data } = await api.get('/admin/email-config/dns-check', {
        params: { domain: dnsDomain.trim(), provider: config.provider },
      });
      setDnsResult(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'DNS-Check fehlgeschlagen');
    } finally { setDnsLoading(false); }
  };

  const copyClip = (txt) => {
    try { navigator.clipboard.writeText(txt); toast.success('Kopiert'); } catch { /* noop */ }
  };

  const p = config.provider;
  const hasApiProvider = p === 'resend' || p === 'sendgrid';

  return (
    <div className="space-y-6">
      {/* ================ Main Provider ================ */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-5" data-testid="email-config-main">
        <div className="flex items-center gap-2 mb-2">
          <Mail className="w-5 h-5 text-[#4A5D4E]" />
          <h3 className="text-sm font-medium text-[#1C1F1D]">E-Mail-Provider</h3>
        </div>
        <p className="text-xs text-[#9CA3AF] -mt-3">{t('pickChannelForMailing')}</p>

        <div className="flex items-center justify-between py-2 border-b border-[#E2E4E0]">
          <div>
            <span className="text-sm text-[#1C1F1D] font-medium">{t('emailSendingEnabled')}</span>
            <p className="text-xs text-[#9CA3AF]">{t('whenOffMailsJustLogged')}</p>
          </div>
          <Switch data-testid="email-enabled-toggle" checked={config.enabled} onCheckedChange={v => setConfig(prev => ({ ...prev, enabled: v }))} />
        </div>

        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Provider</Label>
          <Select value={p} onValueChange={v => setConfig(prev => ({ ...prev, provider: v }))}>
            <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="email-provider-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">{t('noProvider')}</SelectItem>
              <SelectItem value="resend">Resend</SelectItem>
              <SelectItem value="sendgrid">SendGrid</SelectItem>
              <SelectItem value="smtp">SMTP (Klinik-Mailserver)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {hasApiProvider && (
          <>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">API-Key</Label>
              <Input data-testid="email-api-key-input" type="password"
                value={config.api_key || ''}
                onChange={e => { setConfig(prev => ({ ...prev, api_key: e.target.value })); setKeyEdited(true); }}
                placeholder={p === 'resend' ? 're_...' : 'SG...'}
                className="border-[#E2E4E0] rounded-xl font-mono text-sm" />
              <p className="text-xs text-[#9CA3AF] mt-1">
                {p === 'resend' ? 'Hol dir deinen Key: https://resend.com/api-keys' : 'Hol dir deinen Key: https://app.sendgrid.com/settings/api_keys'}
              </p>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Absender-E-Mail</Label>
              <Input data-testid="email-sender-input" value={config.sender_email}
                onChange={e => setConfig(prev => ({ ...prev, sender_email: e.target.value }))}
                placeholder="newsletter@klinik.de"
                className="border-[#E2E4E0] rounded-xl" />
            </div>
          </>
        )}
      </div>

      {/* ================ SMTP Section ================ */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-5" data-testid="smtp-config-block">
        <div className="flex items-center gap-2 mb-1">
          <Server className="w-5 h-5 text-[#4A5D4E]" />
          <h3 className="text-sm font-medium text-[#1C1F1D]">Klinik-SMTP</h3>
        </div>
        <p className="text-xs text-[#9CA3AF] -mt-3">
          {p === 'smtp' ? 'Dies ist der aktive Versandweg.' : 'Zusätzlich — kann als Fallback genutzt werden, wenn Resend/SendGrid fehlschlägt.'}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Host</Label>
            <Input data-testid="smtp-host-input" value={config.smtp?.host || ''}
              onChange={e => updateSmtp({ host: e.target.value })}
              placeholder="mail.klinik.de" className="border-[#E2E4E0] rounded-xl font-mono text-sm" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Port</Label>
            <Input data-testid="smtp-port-input" type="number" value={config.smtp?.port || 587}
              onChange={e => updateSmtp({ port: parseInt(e.target.value) || 587 })}
              className="border-[#E2E4E0] rounded-xl" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('encryption')}</Label>
            <Select
              value={config.smtp?.use_tls ? 'tls' : (config.smtp?.use_starttls ? 'starttls' : 'plain')}
              onValueChange={v => updateSmtp({
                use_tls: v === 'tls',
                use_starttls: v === 'starttls',
              })}
            >
              <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="smtp-encryption-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="starttls">STARTTLS (Port 587)</SelectItem>
                <SelectItem value="tls">Implicit TLS (Port 465)</SelectItem>
                <SelectItem value="plain">{t('noneLocalOnly')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Benutzername</Label>
            <Input data-testid="smtp-username-input" value={config.smtp?.username || ''}
              onChange={e => updateSmtp({ username: e.target.value })}
              placeholder="newsletter@klinik.de" className="border-[#E2E4E0] rounded-xl font-mono text-sm" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Passwort</Label>
            <Input data-testid="smtp-password-input" type="password" value={config.smtp?.password || ''}
              onChange={e => { updateSmtp({ password: e.target.value }); setSmtpPwEdited(true); }}
              placeholder="••••••••" className="border-[#E2E4E0] rounded-xl font-mono text-sm" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Absender-Name</Label>
            <Input data-testid="smtp-from-name-input" value={config.smtp?.from_name || ''}
              onChange={e => updateSmtp({ from_name: e.target.value })}
              placeholder="MeetFlow Klinik" className="border-[#E2E4E0] rounded-xl" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('fromEmailOptional')}</Label>
            <Input data-testid="smtp-from-email-input" value={config.smtp?.from_email || ''}
              onChange={e => updateSmtp({ from_email: e.target.value })}
              placeholder="newsletter@klinik.de" className="border-[#E2E4E0] rounded-xl" />
          </div>
        </div>

        {hasApiProvider && (
          <div className="flex items-center justify-between border-t border-[#E2E4E0] pt-4">
            <div>
              <span className="text-sm text-[#1C1F1D] font-medium">Als Fallback nutzen</span>
              <p className="text-xs text-[#9CA3AF]">Wenn {p === 'resend' ? 'Resend' : 'SendGrid'} fehlschlägt, automatisch über SMTP versenden.</p>
            </div>
            <Switch data-testid="smtp-fallback-toggle" checked={!!config.fallback_to_smtp}
              onCheckedChange={v => setConfig(prev => ({ ...prev, fallback_to_smtp: v }))} />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button onClick={handleSmtpHealth} disabled={checkingSmtp || !config.smtp?.host}
            variant="outline" data-testid="smtp-health-btn"
            className="rounded-full border-[#E2E4E0] px-4 text-sm">
            {checkingSmtp ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
            Verbindung prüfen
          </Button>
          <Button onClick={() => handleTest('smtp')} disabled={testing || !config.smtp?.host}
            variant="outline" data-testid="smtp-test-mail-btn"
            className="rounded-full border-[#E2E4E0] px-4 text-sm">
            <Send className="w-3.5 h-3.5 mr-1.5" />
            {t('testEmailViaSmtp')}
          </Button>
        </div>

        {smtpHealth && (
          <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${smtpHealth.ok ? 'bg-[#6B8E23]/10 text-[#6B8E23]' : 'bg-[#C87967]/10 text-[#C87967]'}`}
            data-testid="smtp-health-result">
            {smtpHealth.ok ? <CheckCircle className="w-4 h-4 mt-0.5" /> : <AlertCircle className="w-4 h-4 mt-0.5" />}
            <div>
              <p className="font-medium">{smtpHealth.ok ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen'}</p>
              {!smtpHealth.ok && smtpHealth.error && <p className="text-xs mt-0.5 opacity-80">{smtpHealth.error}</p>}
            </div>
          </div>
        )}
      </div>

      {/* ================ DNS-Check ================ */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-5" data-testid="dns-check-block">
        <div className="flex items-center gap-2 mb-1">
          <Shield className="w-5 h-5 text-[#4A5D4E]" />
          <h3 className="text-sm font-medium text-[#1C1F1D]">Domain-Verifikation (DNS)</h3>
        </div>
        <p className="text-xs text-[#9CA3AF] -mt-3">
          Prüft MX, SPF, DKIM und DMARC für die angegebene Domain. Fehlende Einträge führen bei vielen Providern zum Versand-Fehler oder landen im Spam.
        </p>

        <div className="flex items-end gap-3">
          <div className="flex-1">
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Domain oder E-Mail</Label>
            <Input data-testid="dns-domain-input" value={dnsDomain}
              onChange={e => setDnsDomain(e.target.value)}
              placeholder={t('emailDomainExamplePlaceholder')}
              className="border-[#E2E4E0] rounded-xl font-mono text-sm" />
          </div>
          <Button onClick={handleDnsCheck} disabled={dnsLoading}
            data-testid="dns-check-btn"
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-6">
            {dnsLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
            Prüfen
          </Button>
        </div>

        {dnsResult && (
          <div className="space-y-3 border-t border-[#E2E4E0] pt-4" data-testid="dns-result">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {['mx', 'spf', 'dkim', 'dmarc'].map(k => {
                const sum = dnsResult.summary?.[k];
                const color = sum === 'ok' ? 'text-[#6B8E23] bg-[#6B8E23]/10' : sum === 'warn' ? 'text-[#D4A373] bg-[#D4A373]/10' : 'text-[#C87967] bg-[#C87967]/10';
                const Icon = sum === 'ok' ? CheckCircle : sum === 'warn' ? AlertTriangle : AlertCircle;
                return (
                  <div key={k} className={`rounded-xl p-3 ${color}`} data-testid={`dns-${k}-status`}>
                    <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.1em]">
                      <Icon className="w-3.5 h-3.5" /> {k}
                    </div>
                    <p className="text-[11px] mt-1 opacity-80">
                      {sum === 'ok' ? 'Gefunden' : sum === 'warn' ? 'Empfohlen' : 'Fehlt'}
                    </p>
                  </div>
                );
              })}
            </div>

            {(dnsResult.hints || []).length > 0 && (
              <div className="bg-[#F3F4F1] border border-[#E2E4E0] rounded-xl p-3 space-y-1.5">
                {dnsResult.hints.map((h, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-[#4B5563]">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 text-[#D4A373] shrink-0" /> <span>{h}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Raw records (collapsible-ish, always shown for transparency) */}
            <div className="space-y-2 text-xs">
              {['mx', 'spf', 'dkim', 'dmarc'].map(k => {
                const block = dnsResult[k];
                if (!block) return null;
                const recs = block.records
                  || (block.selectors || []).flatMap(s => s.records.map(r => `${s.selector}: ${r}`));
                return (
                  <details key={k} className="border border-[#E2E4E0] rounded-lg">
                    <summary className="px-3 py-2 cursor-pointer font-mono uppercase text-[10px] tracking-[0.1em] text-[#6B7280]">
                      {k} ({recs?.length || 0})
                    </summary>
                    <div className="px-3 py-2 border-t border-[#E2E4E0] space-y-1">
                      {(recs || []).length === 0 ? (
                        <p className="text-[#9CA3AF] italic">{t('noEntriesFound')}</p>
                      ) : recs.map((r, i) => (
                        <div key={i} className="flex items-center justify-between gap-2 font-mono text-[11px] text-[#4B5563] break-all">
                          <span className="break-all">{r}</span>
                          <button onClick={() => copyClip(r)} className="shrink-0 text-[#9CA3AF] hover:text-[#4A5D4E]" title="Kopieren">
                            <Copy className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </details>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ================ Save + global test ================ */}
      {(() => {
        const currentSnap = JSON.stringify({
          provider: config.provider, sender_email: config.sender_email, enabled: config.enabled,
          fallback_to_smtp: config.fallback_to_smtp, smtp: config.smtp,
        });
        const isDirty = savedSnapshot && savedSnapshot !== currentSnap;
        return (
          <>
            {isDirty && (
              <div className="p-3 bg-[#D4A373]/10 border border-[#D4A373]/40 rounded-xl flex items-center gap-2 text-[11px] text-[#1C1F1D]"
                   data-testid="email-config-dirty">
                <AlertCircle className="w-4 h-4 text-[#D4A373] flex-shrink-0" />
                <span><strong>Ungespeicherte Änderungen.</strong> Klicke unten auf „Speichern", damit E-Mail-Versand und Einladungen deine Konfiguration nutzen.</span>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3 pt-2 pb-24 md:pb-2" data-testid="email-config-actions">
              <Button onClick={handleSave} disabled={saving} data-testid="save-email-config"
                className={`${isDirty ? 'bg-[#C87967] hover:bg-[#B86A5A] ring-2 ring-[#C87967]/30 animate-pulse' : 'bg-[#4A5D4E] hover:bg-[#3E4E42]'} text-white rounded-full px-6`}>
                {saving ? '...' : (isDirty ? 'Jetzt speichern' : 'Speichern')}
              </Button>
              {p !== 'none' && (
                <Button variant="outline" onClick={() => handleTest('')} disabled={testing} data-testid="test-email-button"
                  className="rounded-full border-[#E2E4E0] px-6">
                  <Send className="w-3.5 h-3.5 mr-1.5" />{testing ? 'Sende...' : 'Test-E-Mail über aktiven Provider'}
                </Button>
              )}
            </div>
          </>
        );
      })()}

      {testResult && (
        <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${testResult.status === 'sent' ? 'bg-[#6B8E23]/10 text-[#6B8E23]' : testResult.status === 'logged' ? 'bg-[#D4A373]/10 text-[#D4A373]' : 'bg-[#C87967]/10 text-[#C87967]'}`}
          data-testid="email-test-result">
          {testResult.status === 'sent' ? <CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />}
          <div className="flex-1 min-w-0">
            {testResult.status === 'sent'
              ? <span>E-Mail gesendet via {testResult.provider}{testResult.id ? ` (ID: ${testResult.id})` : ''}{testResult.fallback ? ' – über Fallback' : ''}</span>
              : testResult.status === 'logged'
                ? <span>E-Mail simuliert (kein aktiver Provider)</span>
                : (
                  <div className="space-y-1">
                    <div className="font-medium">Fehler: {testResult.error || testResult.detail || 'Senden fehlgeschlagen'}</div>
                    {(testResult.smtp_host || testResult.from_email) && (
                      <div className="text-xs opacity-80 font-mono break-all">
                        {testResult.smtp_host && `Host: ${testResult.smtp_host}:${testResult.smtp_port}`}
                        {testResult.from_email && ` · Absender: ${testResult.from_email}`}
                      </div>
                    )}
                  </div>
                )}
          </div>
        </div>
      )}
    </div>
  );
}
