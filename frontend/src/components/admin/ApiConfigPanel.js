import { useState, useEffect, useCallback } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { CheckCircle, AlertCircle, Sparkles, Database } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../../contexts/LanguageContext';
export default function ApiConfigPanel() {
  const { t } = useLanguage();
  const [config, setConfig] = useState({ llm_key: '', llm_model: 'gpt-5.2', llm_enabled: false, llm_key_set: false });
  const [storageHealth, setStorageHealth] = useState({ available: null, source: null });
  const [storageTesting, setStorageTesting] = useState(false);
  const [storageTestResult, setStorageTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [keyEdited, setKeyEdited] = useState(false);

  const fetchConfig = useCallback(async () => {
    try { const { data } = await api.get('/admin/api-config'); setConfig(data); } catch { /* ignore */ }
    try { const { data } = await api.get('/admin/storage/health'); setStorageHealth(data); } catch { setStorageHealth({ available: false, source: null }); }
  }, []);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { llm_model: config.llm_model, llm_enabled: config.llm_enabled };
      if (keyEdited && config.llm_key) payload.llm_key = config.llm_key;
      await api.put('/admin/api-config', payload);
      setTimeout(() => toast.success('API-Konfiguration gespeichert'), 50);
      setKeyEdited(false);
      fetchConfig();
    } catch { setTimeout(() => toast.error('Fehler beim Speichern'), 50); }
    finally { setSaving(false); }
  };

  const handleTestLLM = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post('/admin/api-config/test-llm', {});
      setTestResult(data);
    } catch (err) {
      setTestResult({ status: 'error', message: err.response?.data?.detail || 'Fehler' });
    }
    finally { setTesting(false); }
  };

  const handleTestStorage = async () => {
    setStorageTesting(true);
    setStorageTestResult(null);
    try {
      const { data } = await api.post('/admin/storage/test', {});
      setStorageTestResult(data);
      if (data.ok) toast.success(`Storage-Test OK (${data.bytes} Bytes)`);
      else toast.error(`Storage-Test fehlgeschlagen: ${data.step || ''}`);
    } catch (err) {
      setStorageTestResult({ ok: false, error: err.response?.data?.detail || 'Fehler' });
      toast.error('Storage-Test fehlgeschlagen');
    } finally { setStorageTesting(false); }
  };

  return (
    <div className="space-y-6">
      {/* LLM / KI Config */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-5">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-5 h-5 text-[#D4A373]" />
          <h3 className="text-sm font-medium text-[#1C1F1D]">KI / LLM (Meeting-Zusammenfassungen)</h3>
        </div>
        <p className="text-xs text-[#9CA3AF] -mt-3">Konfiguriere den KI-Zugang für automatische Meeting-Zusammenfassungen und AI Insights.</p>

        <div className="flex items-center justify-between py-2 border-b border-[#E2E4E0]">
          <div>
            <span className="text-sm text-[#1C1F1D] font-medium">{t('aiEnabled')}</span>
            <p className="text-xs text-[#9CA3AF]">{t('aiEnabledHint')}</p>
          </div>
          <Switch data-testid="llm-enabled-toggle" checked={config.llm_enabled} onCheckedChange={v => setConfig(prev => ({ ...prev, llm_enabled: v }))} />
        </div>

        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('emergentLlmKey')}</Label>
          <Input data-testid="llm-key-input" type="password"
            value={keyEdited ? config.llm_key : config.llm_key}
            onChange={e => { setConfig(prev => ({ ...prev, llm_key: e.target.value })); setKeyEdited(true); }}
            placeholder="sk-emergent-..."
            className="border-[#E2E4E0] rounded-xl font-mono text-sm" />
          <p className="text-xs text-[#9CA3AF] mt-1">{t('universalKeyHint')}</p>
          {config.llm_key_set && !keyEdited && (
            <div className="flex items-center gap-1.5 mt-1">
              <CheckCircle className="w-3 h-3 text-[#6B8E23]" />
              <span className="text-xs text-[#6B8E23]">{t('keyConfigured')}</span>
            </div>
          )}
        </div>

        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">KI-Modell</Label>
          <Select value={config.llm_model || 'gpt-5.2'} onValueChange={v => setConfig(prev => ({ ...prev, llm_model: v }))}>
            <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="llm-model-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="gpt-5.2">OpenAI GPT-5.2</SelectItem>
              <SelectItem value="gpt-4o">OpenAI GPT-4o</SelectItem>
              <SelectItem value="gpt-4o-mini">OpenAI GPT-4o Mini</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave} disabled={saving} data-testid="save-api-config"
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-6">
            {saving ? '...' : 'Speichern'}
          </Button>
          {config.llm_enabled && (
            <Button variant="outline" onClick={handleTestLLM} disabled={testing} data-testid="test-llm-button"
              className="rounded-full border-[#E2E4E0] px-6">
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />{testing ? 'Teste...' : 'KI testen'}
            </Button>
          )}
        </div>

        {testResult && (
          <div className={`p-3 rounded-lg text-sm ${testResult.status === 'ok' ? 'bg-[#6B8E23]/10 text-[#6B8E23]' : 'bg-[#C87967]/10 text-[#C87967]'}`}
            data-testid="llm-test-result">
            {testResult.status === 'ok' ? (
              <div>
                <div className="flex items-center gap-1.5 mb-1"><CheckCircle className="w-4 h-4" /> KI funktioniert ({testResult.model})</div>
                <p className="text-xs opacity-80">{testResult.response}</p>
              </div>
            ) : (
              <div className="flex items-center gap-1.5"><AlertCircle className="w-4 h-4" /> {testResult.message}</div>
            )}
          </div>
        )}
      </div>

      {/* Storage Info */}
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6">
        <div className="flex items-center gap-2 mb-2">
          <Database className="w-5 h-5 text-[#4A5D4E]" />
          <h3 className="text-sm font-medium text-[#1C1F1D]">Object Storage</h3>
        </div>
        <p className="text-xs text-[#9CA3AF]">Für Dateiuploads, Aufnahmen, Avatare und Branding-Logos. Nutzt den selben Emergent-Key wie die KI.</p>
        <div className="mt-3 p-3 bg-[#F3F4F1] rounded-lg" data-testid="storage-health-panel">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-1.5">
              {storageHealth.available === true ? (
                <>
                  <CheckCircle className="w-3.5 h-3.5 text-[#6B8E23]" />
                  <span className="text-xs text-[#6B8E23]" data-testid="storage-status-ok">{t('storageConnected')}</span>
                  {storageHealth.source && (
                    <span className="text-[10px] text-[#9CA3AF] ml-1">
                      ({storageHealth.source === 'env' ? 'ENV-Variable' : 'GUI-Konfiguration'})
                    </span>
                  )}
                </>
              ) : storageHealth.available === false ? (
                <>
                  <AlertCircle className="w-3.5 h-3.5 text-[#C87967]" />
                  <span className="text-xs text-[#C87967]" data-testid="storage-status-error">{t('noStorageKey')}</span>
                </>
              ) : (
                <span className="text-xs text-[#9CA3AF]" data-testid="storage-status-loading">Prüfe…</span>
              )}
            </div>
            <Button
              size="sm" variant="outline"
              onClick={handleTestStorage}
              disabled={storageTesting}
              data-testid="storage-test-button"
              className="rounded-full border-[#E2E4E0] px-4 text-xs"
            >
              {storageTesting ? 'Teste…' : 'Storage testen'}
            </Button>
          </div>
          {storageTestResult && (
            <div
              className={`mt-2 p-2 rounded-md text-[11px] ${storageTestResult.ok ? 'bg-[#6B8E23]/10 text-[#6B8E23]' : 'bg-[#C87967]/10 text-[#C87967]'}`}
              data-testid="storage-test-result"
            >
              {storageTestResult.ok
                ? `Upload + Download + Verify OK (${storageTestResult.bytes} Bytes)`
                : `Fehler bei Schritt "${storageTestResult.step || '?'}": ${typeof storageTestResult.error === 'string' ? storageTestResult.error : JSON.stringify(storageTestResult.error)}`}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
