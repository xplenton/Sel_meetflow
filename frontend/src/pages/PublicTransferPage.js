import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { toast } from 'sonner';
import { Send, ShieldCheck, FileText, Download, Lock, Clock, AlertTriangle, Workflow } from 'lucide-react';

function fmtBytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB']; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

/** Anonymous public-link download page (iter 386). */
export default function PublicTransferPage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [pw, setPw] = useState('');
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(null);

  const reload = useCallback(async () => {
    try {
      const { data } = await api.get(`/filetransfer/public/${token}`);
      setInfo(data); setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Link ungültig');
      setInfo(null);
    }
  }, [token]);
  useEffect(() => { reload(); }, [reload]);

  const download = async (fileId, fileName) => {
    setDownloading(fileId);
    try {
      const resp = await api.post(
        `/filetransfer/public/${token}/files/${fileId}/download`,
        { password: pw || null },
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement('a'); a.href = url; a.download = fileName; a.click();
      URL.revokeObjectURL(url);
      toast.success(`${fileName} heruntergeladen`);
      // Re-fetch share info to update download count + one-time consumption
      setTimeout(reload, 1200);
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Download fehlgeschlagen';
      if (err?.response?.status === 401) toast.error('Passwort falsch');
      else toast.error(detail);
    } finally { setDownloading(null); }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#F9F9F8] via-white to-[#F3F4F1] flex items-center justify-center p-4">
      <div className="w-full max-w-xl bg-white border border-[#E2E4E0] rounded-2xl shadow-sm p-6" data-testid="public-transfer-page">
        <div className="flex items-center gap-2 mb-4">
          <Workflow className="w-6 h-6 text-[#4A5D4E]" />
          <h1 className="text-xl font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow Filetransfer</h1>
        </div>

        {error && (
          <div className="bg-[#C87967]/10 border border-[#C87967]/30 rounded-lg p-4 flex items-start gap-2" data-testid="public-error">
            <AlertTriangle className="w-5 h-5 text-[#C87967] mt-0.5" />
            <div>
              <p className="font-medium text-[#C87967]">Zugriff nicht möglich</p>
              <p className="text-xs text-[#6B7280] mt-1">{error}</p>
            </div>
          </div>
        )}

        {info && (
          <>
            <div className="bg-[#F9F9F8] rounded-lg p-3 mb-4 text-sm">
              <p className="text-xs text-[#9CA3AF] mb-1">Absender</p>
              <p className="font-medium">{info.owner_name}</p>
              {info.message && (<>
                <p className="text-xs text-[#9CA3AF] mt-2 mb-1">Nachricht</p>
                <p className="italic text-[#1C1F1D]">{info.message}</p>
              </>)}
              <div className="flex items-center gap-3 mt-2 text-xs text-[#6B7280]">
                <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3" /> gültig bis {new Date(info.expires_at).toLocaleString('de-DE')}</span>
                {info.one_time && <span className="bg-[#D4A373]/15 text-[#D4A373] px-2 rounded-full">Einmal-Download</span>}
                <span className="inline-flex items-center gap-1 text-[#6B8E23]"><ShieldCheck className="w-3 h-3" /> AES-256-GCM</span>
              </div>
            </div>

            {info.password_required && (
              <div className="mb-4">
                <label className="text-xs text-[#6B7280] flex items-center gap-1"><Lock className="w-3 h-3" /> Passwort erforderlich</label>
                <Input type="password" value={pw} onChange={e => setPw(e.target.value)} className="mt-1" data-testid="public-pw" placeholder="Passwort eingeben" />
              </div>
            )}

            <div>
              <h2 className="text-xs font-semibold text-[#6B7280] uppercase mb-2">{info.files.length} Datei(en)</h2>
              <div className="space-y-2">
                {info.files.map(f => (
                  <div key={f.file_id} className="flex items-center gap-2 border border-[#E2E4E0] rounded-lg p-2.5" data-testid={`public-file-${f.file_id}`}>
                    <FileText className="w-4 h-4 text-[#6B7280]" />
                    <span className="flex-1 truncate text-sm">{f.file_name}</span>
                    <span className="text-[10px] text-[#9CA3AF]">{fmtBytes(f.size_bytes)}</span>
                    <Button size="sm" onClick={() => download(f.file_id, f.file_name)} disabled={downloading === f.file_id}
                      className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" data-testid={`public-download-${f.file_id}`}>
                      <Download className="w-3.5 h-3.5 mr-1" />
                      {downloading === f.file_id ? 'Lade…' : 'Download'}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        <p className="text-[10px] text-[#9CA3AF] mt-6 text-center">
          Inhalte werden auf dem Server entschlüsselt und nur an authorisierte Empfänger ausgeliefert.
        </p>
      </div>
    </div>
  );
}
