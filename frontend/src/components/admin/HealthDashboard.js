import { useEffect, useState, useCallback } from 'react';
import { useLanguage } from '../../contexts/LanguageContext';
import {
  Heart, RefreshCw, Mail, Server, Wrench, AlertTriangle, CheckCircle2,
  TrendingUp, Users, Clock, AlertCircle, Loader2, Bell, Send, Settings,
} from 'lucide-react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Switch } from '../ui/switch';
import { Label } from '../ui/label';
import { toast } from 'sonner';
import WSHealthWidget from './WSHealthWidget';

const severityColor = (sev) => ({
  ok: 'bg-[#6B8E23]/10 text-[#6B8E23] border-[#6B8E23]/20',
  warn: 'bg-[#D4A373]/10 text-[#D4A373] border-[#D4A373]/30',
  error: 'bg-[#C87967]/10 text-[#C87967] border-[#C87967]/30',
}[sev] || 'bg-[#F3F4F1] text-[#6B7280] border-[#E2E4E0]');

const sevIcon = {
  ok: CheckCircle2, warn: AlertTriangle, error: AlertCircle,
};

function SevTile({ label, severity, primary, secondary, icon: Icon }) {
  const SevIcon = sevIcon[severity] || AlertCircle;
  return (
    <div className={`border rounded-xl p-4 ${severityColor(severity)}`} data-testid={`health-tile-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.15em] opacity-90">
          {Icon && <Icon className="w-3.5 h-3.5" />}
          {label}
        </div>
        <SevIcon className="w-4 h-4" />
      </div>
      <div className="text-2xl font-medium leading-none">{primary}</div>
      {secondary && <div className="text-[11px] opacity-80 mt-1.5">{secondary}</div>}
    </div>
  );
}

function Sparkline({ data, max }) {
  if (!data?.length) return null;
  const vmax = max || Math.max(...data, 1);
  const w = 160, h = 32;
  const step = w / Math.max(1, data.length - 1);
  const pts = data.map((v, i) => `${(i * step).toFixed(1)},${(h - (v / vmax) * h).toFixed(1)}`).join(' ');
  return (
    <svg width={w} height={h} className="block">
      <polyline fill="none" stroke="#4A5D4E" strokeWidth="1.5" points={pts} />
    </svg>
  );
}

const fmtTs = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts);
  const diff = (Date.now() - d.getTime()) / 60000; // minutes
  if (diff < 1) return 'gerade eben';
  if (diff < 60) return `vor ${Math.round(diff)} Min`;
  if (diff < 24 * 60) return `vor ${Math.round(diff / 60)} h`;
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

export default function HealthDashboard() {
  const { t } = useLanguage();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchHealth = useCallback(async () => {
    setRefreshing(true);
    try {
      const { data } = await api.get('/admin/health');
      setData(data);
    } catch { /* noop */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, 30000); // auto-refresh every 30s
    return () => clearInterval(id);
  }, [fetchHealth]);

  if (loading) {
    return <div className="flex items-center justify-center py-16 text-[#9CA3AF]" data-testid="health-loading"><Loader2 className="w-5 h-5 mr-2 animate-spin" />Lade Dashboard...</div>;
  }
  if (!data) return <div className="py-8 text-center text-[#9CA3AF]">{t('noDataAvailable')}</div>;

  // ===== Severities =====
  const emailRate = data.emails?.success_rate;
  const emailSev = data.emails?.total === 0 ? 'warn'
    : emailRate >= 95 ? 'ok' : emailRate >= 70 ? 'warn' : 'error';

  const dnsSev = data.dns?.severity || (data.dns?.error ? 'error' : 'warn');

  const anomalies = data.auth_refresh?.anomalies || [];
  const sessionSev = anomalies.length === 0 ? 'ok' : anomalies.length < 3 ? 'warn' : 'error';

  const tasks = data.maintenance?.tasks || [];
  const lastCleanup = tasks.find(t => t.task === 'cleanup_test_data');
  const lastArchive = tasks.find(t => t.task === 'auto_archive_surveys');
  const cleanupAge = lastCleanup ? (Date.now() - new Date(lastCleanup.last_ts).getTime()) / 60000 : Infinity;
  const cleanupSev = cleanupAge < 90 ? 'ok' : cleanupAge < 180 ? 'warn' : 'error';

  const sentSeries = (data.emails?.by_day || []).map(d => d.sent || 0);

  return (
    <div className="space-y-6" data-testid="health-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-medium text-[#1C1F1D] flex items-center gap-2">
            <Heart className="w-5 h-5 text-[#4A5D4E]" /> Health-Dashboard
          </h2>
          <p className="text-xs text-[#9CA3AF] mt-0.5">
            Generiert {fmtTs(data.generated_at)} · Auto-Refresh alle 30 s
          </p>
        </div>
        <Button variant="outline" onClick={fetchHealth} disabled={refreshing}
          className="rounded-full border-[#E2E4E0]" data-testid="health-refresh-btn">
          {refreshing ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
          Aktualisieren
        </Button>
      </div>

      {/* ===== WebSocket-Auth Live-Metrics (iter 107) ===== */}
      <WSHealthWidget />

      {/* ===== Top row: 4 big tiles ===== */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SevTile
          label="E-Mail 7d"
          icon={Mail}
          severity={emailSev}
          primary={emailRate !== null ? `${emailRate}%` : '—'}
          secondary={`${data.emails.sent} gesendet · ${data.emails.failed} Fehler`}
        />
        <SevTile
          label="DNS"
          icon={Server}
          severity={dnsSev}
          primary={data.dns?.domain || '—'}
          secondary={data.dns?.error ? data.dns.error : `MX ${data.dns?.summary?.mx || '?'} · SPF ${data.dns?.summary?.spf || '?'} · DKIM ${data.dns?.summary?.dkim || '?'}`}
        />
        <SevTile
          label="Sessions 24h"
          icon={Users}
          severity={sessionSev}
          primary={data.users?.active_sessions_24h?.toLocaleString('de-DE') || '0'}
          secondary={anomalies.length > 0 ? `${anomalies.length} Auffälligkeit(en)` : `${data.auth_refresh?.total_refreshes || 0} Refreshes`}
        />
        <SevTile
          label="Wartung"
          icon={Wrench}
          severity={cleanupSev}
          primary={lastCleanup ? fmtTs(lastCleanup.last_ts) : '—'}
          secondary={`${tasks.reduce((a, t) => a + (t.runs_24h || 0), 0)} Läufe / 24h`}
        />
      </div>

      {/* ===== E-Mail-Details ===== */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="health-email-detail">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-[#1C1F1D] flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-[#4A5D4E]" /> E-Mail-Versand (7 Tage)
          </h3>
          <Sparkline data={sentSeries} />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          {Object.entries(data.emails?.by_provider || {}).map(([p, v]) => (
            <div key={p} className="border border-[#E2E4E0] rounded-lg p-2.5">
              <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#6B7280]">{p}</p>
              <p className="text-sm text-[#1C1F1D] mt-1">
                <span className="text-[#6B8E23] font-medium">{v.sent || 0}</span> gesendet ·{' '}
                <span className="text-[#C87967]">{v.failed || 0}</span> Fehler
                {v.simulated ? <><span className="text-[#9CA3AF]"> · {v.simulated} simuliert</span></> : null}
              </p>
            </div>
          ))}
          {Object.keys(data.emails?.by_provider || {}).length === 0 && (
            <p className="text-[#9CA3AF] text-xs col-span-full">{t('noEmailSent7d')}</p>
          )}
        </div>
        {data.emails?.last_failure && (
          <div className="mt-3 border-t border-[#E2E4E0] pt-3 flex items-start gap-2 text-xs">
            <AlertCircle className="w-4 h-4 text-[#C87967] mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="font-medium text-[#1C1F1D]">Letzter Fehler · {fmtTs(data.emails.last_failure.ts)}</p>
              <p className="text-[#6B7280] break-words mt-0.5">
                → {data.emails.last_failure.to} via {data.emails.last_failure.provider}: {data.emails.last_failure.error}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ===== DNS + Session Anomalies ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="health-dns-detail">
          <h3 className="text-sm font-medium text-[#1C1F1D] mb-3 flex items-center gap-2">
            <Server className="w-4 h-4 text-[#4A5D4E]" /> DNS-Status
          </h3>
          {data.dns?.error ? (
            <p className="text-xs text-[#C87967]">{data.dns.error}</p>
          ) : data.dns ? (
            <div className="space-y-2">
              <p className="text-xs text-[#6B7280] font-mono">{data.dns.domain} ({data.dns.provider})</p>
              <div className="grid grid-cols-4 gap-2">
                {['mx', 'spf', 'dkim', 'dmarc'].map(k => {
                  const sum = data.dns.summary?.[k];
                  const color = sum === 'ok' ? 'text-[#6B8E23] bg-[#6B8E23]/10' : sum === 'warn' ? 'text-[#D4A373] bg-[#D4A373]/10' : 'text-[#C87967] bg-[#C87967]/10';
                  return <div key={k} className={`rounded-lg p-2 text-center ${color}`}>
                    <p className="text-[10px] font-bold uppercase">{k}</p>
                    <p className="text-[10px] mt-0.5">{sum === 'ok' ? '✓' : sum === 'warn' ? '!' : '×'}</p>
                  </div>;
                })}
              </div>
              {(data.dns.hints || []).length > 0 && (
                <p className="text-[11px] text-[#9CA3AF] mt-2 italic">{data.dns.hints[0]}</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-[#9CA3AF]">{t('noSenderConfigured')}</p>
          )}
        </div>

        <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="health-sessions-detail">
          <h3 className="text-sm font-medium text-[#1C1F1D] mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-[#4A5D4E]" /> {t('sessionActivity24h')}
          </h3>
          <p className="text-xs text-[#6B7280] mb-3">
            {data.auth_refresh?.total_refreshes || 0} Token-Refreshes von {data.users?.active_sessions_24h || 0} verschiedenen Nutzern
          </p>
          {anomalies.length === 0 ? (
            <div className="text-xs text-[#6B8E23] flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" /> {t('noAnomalies')}
            </div>
          ) : (
            <div className="space-y-1.5" data-testid="health-anomalies-list">
              {anomalies.slice(0, 5).map((a, i) => (
                <div key={i} className="flex items-center justify-between text-xs py-1.5 px-2 rounded bg-[#C87967]/5 border border-[#C87967]/20">
                  <div className="min-w-0">
                    <p className="text-[#1C1F1D] font-medium truncate">{a.email || a.user_id}</p>
                    {a.name && <p className="text-[10px] text-[#9CA3AF]">{a.name}</p>}
                  </div>
                  <div className="text-[#C87967] font-mono text-xs shrink-0">
                    {a.count}× · {fmtTs(a.last)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ===== Maintenance Table ===== */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="health-maintenance-detail">
        <h3 className="text-sm font-medium text-[#1C1F1D] mb-3 flex items-center gap-2">
          <Wrench className="w-4 h-4 text-[#4A5D4E]" /> Wartungs-Cron
        </h3>
        {tasks.length === 0 ? (
          <p className="text-xs text-[#9CA3AF]">{t('noCronRunsYet')}</p>
        ) : (
          <div className="space-y-2">
            {tasks.map(t => (
              <div key={t.task} className="flex items-center justify-between text-xs py-2 border-b border-[#E2E4E0] last:border-0">
                <div>
                  <p className="font-mono text-[#1C1F1D]">{t.task}</p>
                  <p className="text-[10px] text-[#9CA3AF] mt-0.5"><Clock className="w-2.5 h-2.5 inline mr-1" />{fmtTs(t.last_ts)} · {t.runs_24h} Läufe / 24h</p>
                </div>
                <div className="text-right">
                  <p className="text-[#4A5D4E] font-medium">{t.last_modified} Items</p>
                  <p className="text-[10px] text-[#9CA3AF]">{t.last_took_ms} ms</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ===== Alert-Einstellungen ===== */}
      <AlertSettings />
    </div>
  );
}


function AlertSettings() {
  const { t } = useLanguage();
  const [cfg, setCfg] = useState(null);
  const [history, setHistory] = useState([]);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, h] = await Promise.all([
        api.get('/admin/health/alerts/config'),
        api.get('/admin/health/alerts/history'),
      ]);
      setCfg(c.data);
      setHistory(h.data?.items || []);
    } catch { /* noop */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleChannel = (ch) => {
    setCfg(prev => {
      const set = new Set(prev.channels || []);
      set.has(ch) ? set.delete(ch) : set.add(ch);
      return { ...prev, channels: Array.from(set) };
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put('/admin/health/alerts/config', {
        enabled: cfg.enabled,
        email_rate_threshold: Number(cfg.email_rate_threshold),
        email_rate_min_sends: Number(cfg.email_rate_min_sends),
        session_anomaly_threshold: Number(cfg.session_anomaly_threshold),
        session_anomaly_count: Number(cfg.session_anomaly_count),
        alert_on_last_failure: !!cfg.alert_on_last_failure,
        cron_idle_minutes: Number(cfg.cron_idle_minutes || 0),
        cooldown_hours: Number(cfg.cooldown_hours),
        channels: cfg.channels || [],
        recipients: (cfg.recipients || []).filter(Boolean),
      });
      setCfg(data);
      toast.success('Alert-Einstellungen gespeichert');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Speichern fehlgeschlagen');
    } finally { setSaving(false); }
  };

  const runNow = async () => {
    setRunning(true);
    try {
      const { data } = await api.post('/admin/health/alerts/run');
      const fired = data?.fired?.length || 0;
      toast.success(fired ? `${fired} Alert(s) ausgeloest` : 'Alles unauffaellig — kein Alert noetig');
      load();
    } catch { toast.error('Prüfung fehlgeschlagen'); }
    finally { setRunning(false); }
  };

  const testAlert = async () => {
    setTesting(true);
    try {
      const { data } = await api.post('/admin/health/alerts/test');
      if (data?.dispatched > 0) {
        toast.success(`Test gesendet: ${data.emails} E-Mail(s), ${data.pushes} Push — an ${data.recipients} Empfänger`);
      } else {
        toast.error(data?.reason === 'no_recipients' ? 'Keine Empfänger konfiguriert' : 'Test fehlgeschlagen');
      }
    } catch { toast.error('Test fehlgeschlagen'); }
    finally { setTesting(false); }
  };

  if (!cfg) return null;

  const chan = new Set(cfg.channels || []);

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="health-alert-settings">
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h3 className="text-sm font-medium text-[#1C1F1D] flex items-center gap-2">
          <Bell className="w-4 h-4 text-[#4A5D4E]" /> {t('alertNotifications')}
        </h3>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={runNow} disabled={running} className="rounded-full text-xs border-[#E2E4E0]" data-testid="alerts-run-now-btn">
            {running ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Settings className="w-3.5 h-3.5 mr-1.5" />}
            Jetzt prüfen
          </Button>
          <Button variant="outline" size="sm" onClick={testAlert} disabled={testing} className="rounded-full text-xs border-[#E2E4E0]" data-testid="alerts-test-btn">
            {testing ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Send className="w-3.5 h-3.5 mr-1.5" />}
            Testnachricht
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between py-2 mb-3 border-b border-[#E2E4E0]">
        <div>
          <span className="text-sm text-[#1C1F1D] font-medium">Alerting aktiv</span>
          <p className="text-xs text-[#9CA3AF]">{t('hourlyCronCheck')}</p>
        </div>
        <Switch checked={!!cfg.enabled} onCheckedChange={v => setCfg(p => ({ ...p, enabled: v }))}
          data-testid="alerts-enabled-toggle" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1 block">
            {t('emailSuccessRateLt')}
          </Label>
          <Input type="number" min="0" max="100" value={cfg.email_rate_threshold}
            onChange={e => setCfg(p => ({ ...p, email_rate_threshold: e.target.value }))}
            className="border-[#E2E4E0] rounded-xl" data-testid="alerts-email-rate-input" />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1 block">
            Min. Versandvolumen 7d
          </Label>
          <Input type="number" min="0" value={cfg.email_rate_min_sends}
            onChange={e => setCfg(p => ({ ...p, email_rate_min_sends: e.target.value }))}
            className="border-[#E2E4E0] rounded-xl" data-testid="alerts-email-min-input" />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1 block">
            Session-Anomalie: Refreshes/User/24h &ge;
          </Label>
          <Input type="number" min="1" value={cfg.session_anomaly_threshold}
            onChange={e => setCfg(p => ({ ...p, session_anomaly_threshold: e.target.value }))}
            className="border-[#E2E4E0] rounded-xl" data-testid="alerts-session-threshold-input" />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1 block">
            Cooldown zwischen Alerts (h)
          </Label>
          <Input type="number" min="0" value={cfg.cooldown_hours}
            onChange={e => setCfg(p => ({ ...p, cooldown_hours: e.target.value }))}
            className="border-[#E2E4E0] rounded-xl" data-testid="alerts-cooldown-input" />
        </div>
        <div className="sm:col-span-2">
          <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1 block">
            {t('cronIdleAlertFrom')}
          </Label>
          <Input type="number" min="0" value={cfg.cron_idle_minutes || 0}
            onChange={e => setCfg(p => ({ ...p, cron_idle_minutes: e.target.value }))}
            className="border-[#E2E4E0] rounded-xl" data-testid="alerts-cron-idle-input" />
        </div>
      </div>

      <div className="flex items-center justify-between py-3 mt-3 border-t border-[#E2E4E0]">
        <div>
          <span className="text-sm text-[#1C1F1D] font-medium">{t('alertOnEveryEmailFailure')}</span>
          <p className="text-xs text-[#9CA3AF]">{t('otherwiseOnly7dRateBelow')}</p>
        </div>
        <Switch checked={!!cfg.alert_on_last_failure}
          onCheckedChange={v => setCfg(p => ({ ...p, alert_on_last_failure: v }))}
          data-testid="alerts-last-failure-toggle" />
      </div>

      <div className="mt-4">
        <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('channels')}</Label>
        <div className="flex gap-2 flex-wrap">
          {[{ id: 'email', label: 'E-Mail' }, { id: 'push', label: 'Web-Push' }].map(c => (
            <button key={c.id} type="button" onClick={() => toggleChannel(c.id)}
              className={`px-3 py-1.5 rounded-full text-xs transition-colors ${chan.has(c.id) ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280]'}`}
              data-testid={`alerts-channel-${c.id}`}>
              {chan.has(c.id) ? '✓ ' : ''}{c.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <Label className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
          {t('recipientsEmailsOrAllAdmins')}
        </Label>
        <Input value={(cfg.recipients || []).join(', ')}
          onChange={e => setCfg(p => ({ ...p, recipients: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
          placeholder="admin1@klinik.de, admin2@klinik.de"
          className="border-[#E2E4E0] rounded-xl font-mono text-sm"
          data-testid="alerts-recipients-input" />
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <Button onClick={save} disabled={saving}
          className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="alerts-save-btn">
          {saving ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : null}
          Speichern
        </Button>
        {history.length > 0 && (
          <span className="text-xs text-[#9CA3AF]">Letzte Alerts: {history.length}</span>
        )}
      </div>

      {history.length > 0 && (
        <div className="mt-4 border-t border-[#E2E4E0] pt-3 space-y-1.5" data-testid="alerts-history-list">
          <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#9CA3AF] mb-1">Letzte Alerts (bis 20)</p>
          {history.slice(0, 10).map((h, i) => (
            <div key={i} className="flex items-center justify-between text-xs py-1 px-2 rounded bg-[#F3F4F1]">
              <span className="font-mono text-[#4A5D4E] truncate">{h.rule_key}</span>
              <span className="text-[#9CA3AF] shrink-0 ml-2">{new Date(h.last_ts).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
