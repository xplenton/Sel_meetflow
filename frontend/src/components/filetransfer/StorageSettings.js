import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { ShieldCheck, HardDrive, Network, Plug, Save, AlertTriangle } from 'lucide-react';

function fmtBytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB']; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

export default function FiletransferStorageSettings() {
  const [s, setS] = useState(null);
  const [usage, setUsage] = useState({});
  const [health, setHealth] = useState({});
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get('/filetransfer/settings');
      setS(data.settings); setUsage(data.usage || {}); setHealth(data.health || {});
    } catch (err) { toast.error(err?.response?.data?.detail || 'Laden fehlgeschlagen'); }
  };
  useEffect(() => { load(); }, []);

  if (!s) return <div className="text-sm text-[#9CA3AF]">Lade Speicher-Einstellungen…</div>;

  const update = (patch) => setS({ ...s, ...patch });

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        target: s.target,
        local_root: s.local_root,
        network_share_path: s.network_share_path,
        fallback_to_local: !!s.fallback_to_local,
        max_file_size_mb: parseInt(s.max_file_size_mb, 10) || 200,
        max_total_quota_mb: parseInt(s.max_total_quota_mb, 10) || 50000,
        warn_threshold_pct: parseInt(s.warn_threshold_pct, 10) || 80,
        default_expiry_days: parseInt(s.default_expiry_days, 10) || 14,
        allowed_extensions: (s.allowed_extensions || []).map(e => String(e).toLowerCase().trim()).filter(Boolean),
        encryption_required_local: !!s.encryption_required_local,
        chunked_upload_backend: s.chunked_upload_backend || 'mongo',
        chunked_upload_tmp_dir: s.chunked_upload_tmp_dir || '/tmp/meetflow_ft_uploads',
        enable_virus_scan: !!s.enable_virus_scan,
        virus_scan_required: !!s.virus_scan_required,
        clamav_host: s.clamav_host || '127.0.0.1',
        clamav_port: parseInt(s.clamav_port, 10) || 3310,
      };
      await api.patch('/filetransfer/settings', payload);
      toast.success('Speicher-Einstellungen gespeichert');
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Speichern fehlgeschlagen');
    } finally { setSaving(false); }
  };

  const test = async () => {
    setTesting(true); setTestResult(null);
    try {
      const path = s.target === 'network_share' ? s.network_share_path : s.local_root;
      const { data } = await api.post('/filetransfer/settings/test', { target: s.target, path });
      setTestResult(data);
      if (data.ok) toast.success('Verbindungs-/Schreibtest erfolgreich');
      else toast.error('Test fehlgeschlagen: ' + (data.error || 'unbekannt'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Test fehlgeschlagen');
    } finally { setTesting(false); }
  };

  return (
    <div className="space-y-4" data-testid="ft-storage-settings">
      <header className="flex items-start justify-between gap-2 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-[#1C1F1D]">Speicherverwaltung</h2>
          <p className="text-xs text-[#6B7280]">Wo Filetransfer-Dateien gespeichert und ob sie verschlüsselt werden.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={test} disabled={testing} data-testid="ft-storage-test">
            <Plug className="w-4 h-4 mr-1" /> {testing ? 'Teste…' : 'Verbindung testen'}
          </Button>
          <Button onClick={save} disabled={saving} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" data-testid="ft-storage-save">
            <Save className="w-4 h-4 mr-1" /> {saving ? 'Speichere…' : 'Speichern'}
          </Button>
        </div>
      </header>

      {s._degraded && (
        <div className="bg-[#D4A373]/10 border border-[#D4A373]/30 rounded-lg p-3 flex items-start gap-2" data-testid="ft-storage-degraded">
          <AlertTriangle className="w-4 h-4 text-[#D4A373] mt-0.5" />
          <div className="text-xs">
            <strong className="text-[#D4A373]">Fallback aktiv:</strong> {s._degraded_reason}. Filetransfer schreibt aktuell ins lokale Backup-Verzeichnis.
          </div>
        </div>
      )}

      <section className="bg-white border border-[#E2E4E0] rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-[#6B7280] uppercase">Ziel</h3>
        <Select value={s.target} onValueChange={v => update({ target: v })}>
          <SelectTrigger className="w-[280px]" data-testid="ft-storage-target"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="local"><HardDrive className="w-3.5 h-3.5 inline mr-1" /> Lokales Dateisystem</SelectItem>
            <SelectItem value="network_share"><Network className="w-3.5 h-3.5 inline mr-1" /> Netzwerkfreigabe (SMB/NFS/UNC)</SelectItem>
          </SelectContent>
        </Select>
        {s.target === 'local' && (
          <div>
            <label className="text-xs text-[#6B7280]">Lokaler Pfad</label>
            <Input value={s.local_root || ''} onChange={e => update({ local_root: e.target.value })}
              placeholder="/app/backend/data/filetransfer" data-testid="ft-storage-local-path" />
          </div>
        )}
        {s.target === 'network_share' && (
          <div className="space-y-2">
            <div>
              <label className="text-xs text-[#6B7280]">UNC-Pfad / Mountpoint</label>
              <Input value={s.network_share_path || ''} onChange={e => update({ network_share_path: e.target.value })}
                placeholder="/mnt/fileserver/transfer  oder  \\fileserver\transfer" data-testid="ft-storage-nas-path" />
              <p className="text-[10px] text-[#9CA3AF] mt-1">
                Hinweis: Die Freigabe muss vom Server-Betriebssystem (cifs-utils / autofs) gemountet sein.
                Wir verwenden ausschließlich den Mountpoint. Zugangsdaten gehören in die OS-Mount-Konfiguration,
                damit sie nicht in der Anwendungs-DB landen.
              </p>
            </div>
            <div className="bg-[#6B8E23]/10 border border-[#6B8E23]/30 rounded-lg p-2 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-[#6B8E23]" />
              <span className="text-xs"><strong>AES-256-GCM Verschlüsselung ist Pflicht</strong> für Netzwerkfreigaben – Klartextdateien werden niemals geschrieben.</span>
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={!!s.fallback_to_local} onChange={e => update({ fallback_to_local: e.target.checked })} data-testid="ft-storage-fallback" />
              Bei Verbindungsfehler auf lokales Verzeichnis ausweichen
            </label>
          </div>
        )}
      </section>

      <section className="bg-white border border-[#E2E4E0] rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-[#6B7280] uppercase">Sicherheit</h3>
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={!!s.encryption_required_local} onChange={e => update({ encryption_required_local: e.target.checked })} data-testid="ft-storage-encrypt-local" />
          Auch bei lokalem Speicher verschlüsseln (AES-256-GCM)
        </label>
        <p className="text-[10px] text-[#9CA3AF]">Schlüsselverwaltung: <code>FT_ENCRYPTION_KEY</code> Umgebungsvariable (HKDF-SHA256 → AES-256). Schlüssel-Version wird pro Datei gespeichert. Schlüssel niemals in der DB.</p>
      </section>

      <section className="bg-white border border-[#E2E4E0] rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-[#6B7280] uppercase">Virus-Scan (ClamAV, optional)</h3>
        <label className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={!!s.enable_virus_scan}
            onChange={e => update({ enable_virus_scan: e.target.checked })} data-testid="ft-storage-virus-enable" />
          ClamAV-INSTREAM-Scan vor dem Speichern aktivieren
        </label>
        {s.enable_virus_scan && (
          <>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={!!s.virus_scan_required}
                onChange={e => update({ virus_scan_required: e.target.checked })} data-testid="ft-storage-virus-required" />
              Upload ablehnen, wenn Scanner nicht erreichbar (fail-closed)
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-[#6B7280]">clamd Host</label>
                <Input value={s.clamav_host || ''} onChange={e => update({ clamav_host: e.target.value })}
                  placeholder="127.0.0.1" data-testid="ft-storage-clamav-host" />
              </div>
              <div>
                <label className="text-xs text-[#6B7280]">clamd Port</label>
                <Input type="number" value={s.clamav_port || 3310}
                  onChange={e => update({ clamav_port: e.target.value })} data-testid="ft-storage-clamav-port" />
              </div>
            </div>
            <p className="text-[10px] text-[#9CA3AF]">
              Scanner wird über INSTREAM TCP-Socket angesprochen. Bei Treffer →
              HTTP 400 mit Virusname + Audit-Log-Eintrag <code>file.virus</code>.
              Falls clamd nicht installiert ist, bleibt das Modul ohne Scan
              funktionsfähig (es sei denn "fail-closed" ist aktiv).
            </p>
          </>
        )}
      </section>

      <section className="bg-white border border-[#E2E4E0] rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-[#6B7280] uppercase">Chunked-Upload (für sehr große Dateien)</h3>
        <Select value={s.chunked_upload_backend || 'mongo'} onValueChange={v => update({ chunked_upload_backend: v })}>
          <SelectTrigger className="w-[300px]" data-testid="ft-storage-chunk-backend"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="mongo">MongoDB-Buffer (klein–mittel, &lt; 1 GB)</SelectItem>
            <SelectItem value="disk">Disk-Streaming (groß, &gt; 1 GB)</SelectItem>
          </SelectContent>
        </Select>
        {(s.chunked_upload_backend || 'mongo') === 'disk' && (
          <div>
            <label className="text-xs text-[#6B7280]">Temp-Verzeichnis</label>
            <Input value={s.chunked_upload_tmp_dir || '/tmp/meetflow_ft_uploads'}
              onChange={e => update({ chunked_upload_tmp_dir: e.target.value })}
              data-testid="ft-storage-chunk-tmpdir" />
            <p className="text-[10px] text-[#9CA3AF] mt-1">
              Chunks werden während des Uploads dorthin geschrieben (1 Datei pro Chunk).
              Nach dem Commit wird das Verzeichnis automatisch geleert. Muss vom
              Backend-Prozess schreibbar sein und genug freien Platz haben (≥ größte
              erwartete Datei).
            </p>
          </div>
        )}
      </section>

      <section className="bg-white border border-[#E2E4E0] rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-[#6B7280] uppercase">Limits</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-[#6B7280]">Max. Dateigröße (MB)</label>
            <Input type="number" value={s.max_file_size_mb || 200} onChange={e => update({ max_file_size_mb: e.target.value })} data-testid="ft-storage-max-size" />
          </div>
          <div>
            <label className="text-xs text-[#6B7280]">Speicher-Kontingent (MB)</label>
            <Input type="number" value={s.max_total_quota_mb || 50000} onChange={e => update({ max_total_quota_mb: e.target.value })} data-testid="ft-storage-quota" />
          </div>
          <div>
            <label className="text-xs text-[#6B7280]">Warn-Schwelle (%)</label>
            <Input type="number" value={s.warn_threshold_pct || 80} onChange={e => update({ warn_threshold_pct: e.target.value })} data-testid="ft-storage-warn" />
          </div>
          <div>
            <label className="text-xs text-[#6B7280]">Standard-Ablauf (Tage)</label>
            <Input type="number" value={s.default_expiry_days || 14} onChange={e => update({ default_expiry_days: e.target.value })} data-testid="ft-storage-default-expiry" />
          </div>
        </div>
        <div>
          <label className="text-xs text-[#6B7280]">Erlaubte Dateitypen (kommagetrennt, leer = alle)</label>
          <Input value={(s.allowed_extensions || []).join(',')} onChange={e => update({ allowed_extensions: e.target.value.split(',').map(x => x.trim()).filter(Boolean) })}
            placeholder="pdf,docx,xlsx,png,jpg" data-testid="ft-storage-allowed" />
        </div>
      </section>

      <section className="bg-white border border-[#E2E4E0] rounded-xl p-4">
        <h3 className="text-xs font-semibold text-[#6B7280] uppercase mb-2">Aktueller Status</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div>
            <p className="text-[#9CA3AF]">Verbindung</p>
            <p>{health.ok ? <span className="text-[#6B8E23]">✓ OK</span> : <span className="text-[#C87967]">✗ {health.error || 'Fehler'}</span>}</p>
          </div>
          <div>
            <p className="text-[#9CA3AF]">Freier Speicher</p>
            <p>{fmtBytes(health.free_bytes)} / {fmtBytes(health.total_bytes)}</p>
          </div>
          <div>
            <p className="text-[#9CA3AF]">Filetransfer-Nutzung</p>
            <p>{fmtBytes(usage.used_by_filetransfer_bytes)}</p>
          </div>
        </div>
      </section>

      {testResult && (
        <section className="bg-[#F9F9F8] border border-[#E2E4E0] rounded-xl p-4 text-xs" data-testid="ft-storage-test-result">
          <h3 className="font-semibold text-[#6B7280] uppercase mb-2">Test-Ergebnis</h3>
          <p>Schreiben: {testResult.write_ok ? '✓' : '✗'}</p>
          <p>Lesen: {testResult.read_ok ? '✓' : '✗'}</p>
          <p>Pfad: <code>{testResult.health?.root}</code></p>
          {testResult.error && <p className="text-[#C87967] mt-1">Fehler: {testResult.error}</p>}
        </section>
      )}
    </div>
  );
}
