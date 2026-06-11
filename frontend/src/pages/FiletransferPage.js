import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import api from '../lib/api';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  Upload, Send, Trash2, Download, Link as LinkIcon, Plus, Search, Filter,
  Eye, Copy, ShieldCheck, Clock, Lock, X, Users, FileText, Settings,
} from 'lucide-react';
import FiletransferStorageSettings from '../components/filetransfer/StorageSettings';

const STATUS_LABEL = {
  draft: 'Entwurf', active: 'Aktiv', expired: 'Abgelaufen',
  revoked: 'Widerrufen', downloaded: 'Heruntergeladen',
};
const STATUS_COLOR = {
  draft: 'bg-[#D4A373]/15 text-[#D4A373]',
  active: 'bg-[#6B8E23]/15 text-[#6B8E23]',
  expired: 'bg-[#9CA3AF]/15 text-[#6B7280]',
  revoked: 'bg-[#C87967]/15 text-[#C87967]',
  downloaded: 'bg-[#4A5D4E]/15 text-[#4A5D4E]',
};

function fmtBytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB']; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
function fmtDate(iso) { return iso ? new Date(iso).toLocaleString('de-DE') : ''; }

export default function FiletransferPage() {
  const navigate = useNavigate();
  const params = useParams();

  const [transfers, setTransfers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedId, setSelectedId] = useState(params.transferId || null);

  const fetchList = useCallback(async () => {
    try {
      const status = filterStatus === 'all' ? undefined : filterStatus;
      const { data } = await api.get('/filetransfer/transfers', { params: { status, q: search || undefined } });
      setTransfers(data);
    } catch (err) {
      if (err?.response?.status === 403) toast.error('Keine Filetransfer-Berechtigung');
    } finally { setLoading(false); }
  }, [filterStatus, search]);

  useEffect(() => { fetchList(); }, [fetchList]);

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]" data-testid="filetransfer-page">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-3 md:p-6 max-w-[1400px]">
        <header className="flex items-center justify-between mb-4 md:mb-6 flex-wrap gap-2 pr-24 md:pr-0">
          <div className="min-w-0">
            <h1 className="text-xl md:text-2xl font-semibold text-[#1C1F1D] truncate" style={{ fontFamily: 'Manrope' }}>Filetransfer</h1>
            <p className="text-[11px] md:text-xs text-[#6B7280] mt-0.5 hidden sm:block">Dateien sicher an Kollegen und externe Empfänger senden</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button onClick={() => setCreateOpen(true)} size="sm" className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" data-testid="ft-new-transfer">
              <Plus className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Neuer Transfer</span>
            </Button>
          </div>
        </header>

        {/* Iter 387 — Admin-Übersicht in /analytics?tab=filetransfer-usage,
            Speicher-Einstellungen in /admin?tab=filetransfer-storage. */}

        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
            <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Suche nach Dateiname oder Nachricht..." className="pl-9 h-9" data-testid="ft-search" />
          </div>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-[180px] h-9" data-testid="ft-filter-status">
              <Filter className="w-3.5 h-3.5 mr-1" /><SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle</SelectItem>
              <SelectItem value="draft">Entwurf</SelectItem>
              <SelectItem value="active">Aktiv</SelectItem>
              <SelectItem value="expired">Abgelaufen</SelectItem>
              <SelectItem value="revoked">Widerrufen</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {loading ? <Loading /> :
          transfers.length === 0 ? <EmptyState onCreate={() => setCreateOpen(true)} /> :
            <TransferList rows={transfers} onSelect={(t) => { setSelectedId(t.transfer_id); navigate(`/filetransfer/${t.transfer_id}`); }} />
        }
      </main>

      {createOpen && <CreateTransferDialog onClose={() => setCreateOpen(false)} onCreated={(t) => { setCreateOpen(false); fetchList(); setSelectedId(t.transfer_id); navigate(`/filetransfer/${t.transfer_id}`); }} />}
      {selectedId && <TransferDetailDialog transferId={selectedId} onClose={() => { setSelectedId(null); navigate('/filetransfer'); }} onChanged={fetchList} />}
    </div>
  );
}

function Loading() { return <div className="text-center py-12 text-[#9CA3AF] text-sm">Lade...</div>; }

function EmptyState({ onCreate }) {
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-2xl p-12 text-center" data-testid="ft-empty">
      <Send className="w-10 h-10 mx-auto text-[#9CA3AF] mb-3" />
      <p className="text-sm text-[#1C1F1D] font-medium mb-1">Noch keine Transfers</p>
      <p className="text-xs text-[#9CA3AF] mb-4">Sende Dateien sicher an Kollegen oder externe Empfänger.</p>
      <Button onClick={onCreate} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" data-testid="ft-empty-create">
        <Plus className="w-4 h-4 mr-1" /> Ersten Transfer erstellen
      </Button>
    </div>
  );
}

function TransferList({ rows, onSelect }) {
  return (
    <div className="space-y-2" data-testid="ft-list">
      {rows.map(t => (
        <button key={t.transfer_id} onClick={() => onSelect(t)}
          data-testid={`ft-row-${t.transfer_id}`}
          className="w-full text-left bg-white border border-[#E2E4E0] rounded-xl p-3 md:p-4 hover:border-[#4A5D4E]/40 hover:shadow-sm transition">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLOR[t.status] || STATUS_COLOR.draft}`}>
                  {STATUS_LABEL[t.status] || t.status}
                </span>
                <span className="text-xs text-[#6B7280]">{fmtDate(t.created_at)}</span>
                <span className="text-[10px] text-[#9CA3AF]">• {(t.file_names || []).length} Datei(en) • {fmtBytes(t.total_size_bytes)}</span>
              </div>
              <p className="text-sm text-[#1C1F1D] truncate font-medium">{t.message || '(ohne Nachricht)'}</p>
              <p className="text-[11px] text-[#9CA3AF] truncate">
                an {(t.recipient_user_ids || []).length} Empfänger • läuft ab am {fmtDate(t.expires_at)}
              </p>
            </div>
            <div className="text-right text-xs text-[#6B7280]">
              <div className="flex items-center gap-1 justify-end"><Download className="w-3.5 h-3.5" /> {t.download_count || 0}</div>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

// ----------------- Create Dialog -----------------
function CreateTransferDialog({ onClose, onCreated }) {
  const [message, setMessage] = useState('');
  const [expiry, setExpiry] = useState(14);
  const [recipientSearch, setRecipientSearch] = useState('');
  const [recipientResults, setRecipientResults] = useState([]);
  const [recipients, setRecipients] = useState([]); // {user_id, name}
  const [files, setFiles] = useState([]);
  const [progress, setProgress] = useState({});  // file_name -> %
  const [creating, setCreating] = useState(false);
  const dropRef = useRef(null);

  useEffect(() => {
    if (recipientSearch.length < 2) { setRecipientResults([]); return; }
    let alive = true;
    api.get('/chat/users', { params: { q: recipientSearch } }).then(({ data }) => {
      if (alive) setRecipientResults(data);
    });
    return () => { alive = false; };
  }, [recipientSearch]);

  useEffect(() => {
    const div = dropRef.current;
    if (!div) return;
    const onDrag = (e) => { e.preventDefault(); e.stopPropagation(); };
    const onDrop = (e) => {
      onDrag(e);
      const dropped = Array.from(e.dataTransfer?.files || []);
      if (dropped.length) setFiles(prev => [...prev, ...dropped]);
    };
    div.addEventListener('dragover', onDrag);
    div.addEventListener('dragenter', onDrag);
    div.addEventListener('drop', onDrop);
    return () => {
      div.removeEventListener('dragover', onDrag);
      div.removeEventListener('dragenter', onDrag);
      div.removeEventListener('drop', onDrop);
    };
  }, []);

  const handleFileInput = (e) => {
    setFiles(prev => [...prev, ...Array.from(e.target.files || [])]);
    e.target.value = '';
  };

  const submit = async () => {
    if (files.length === 0) { toast.error('Keine Dateien ausgewählt'); return; }
    setCreating(true);
    try {
      const { data: t } = await api.post('/filetransfer/transfers', {
        message: message.trim(),
        recipient_user_ids: recipients.map(r => r.user_id),
        expiry_days: parseInt(expiry, 10) || 14,
      });
      for (const f of files) {
        // iter 386b — files > 50 MB use chunked upload to bypass single-shot
        // POST limits and provide finer-grained progress.
        const CHUNKED_THRESHOLD = 50 * 1024 * 1024;
        const CHUNK_SIZE = 4 * 1024 * 1024;
        if (f.size > CHUNKED_THRESHOLD) {
          const totalChunks = Math.ceil(f.size / CHUNK_SIZE);
          const { data: init } = await api.post(`/filetransfer/transfers/${t.transfer_id}/uploads/init`, {
            file_name: f.name, total_size: f.size, mime: f.type, total_chunks: totalChunks,
          });
          let sent = 0;
          for (let i = 0; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const blob = f.slice(start, Math.min(start + CHUNK_SIZE, f.size));
            const fd = new FormData();
            fd.append('chunk_index', String(i));
            fd.append('chunk', blob);
            await api.post(`/filetransfer/transfers/${t.transfer_id}/uploads/${init.upload_id}/chunk`, fd, {
              headers: { 'Content-Type': 'multipart/form-data' },
            });
            sent++;
            setProgress(p => ({ ...p, [f.name]: Math.round((sent / totalChunks) * 100) }));
          }
          await api.post(`/filetransfer/transfers/${t.transfer_id}/uploads/${init.upload_id}/commit`);
        } else {
          const fd = new FormData();
          fd.append('file', f);
          await api.post(`/filetransfer/transfers/${t.transfer_id}/files`, fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: (e) => {
              const pct = e.total ? Math.round((e.loaded / e.total) * 100) : 0;
              setProgress(p => ({ ...p, [f.name]: pct }));
            },
          });
        }
      }
      toast.success(`Transfer mit ${files.length} Datei(en) erstellt`);
      onCreated(t);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Fehler beim Erstellen');
    } finally { setCreating(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-[640px] max-h-[95vh] sm:max-h-[90vh] overflow-y-auto w-[calc(100vw-1rem)] sm:w-auto">
        <DialogHeader><DialogTitle>Neuer Transfer</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-[#6B7280]">Nachricht (optional)</label>
            <textarea value={message} onChange={e => setMessage(e.target.value)} rows={3}
              className="mt-1 w-full text-sm border border-[#E2E4E0] rounded-lg p-2"
              placeholder="Was möchtest du dem Empfänger mitteilen?" data-testid="ft-create-message" />
          </div>

          <div>
            <label className="text-xs font-medium text-[#6B7280]">Empfänger (intern)</label>
            <div className="flex flex-wrap gap-1 mb-1 mt-1">
              {recipients.map(r => (
                <span key={r.user_id} className="inline-flex items-center gap-1 bg-[#4A5D4E]/10 text-[#4A5D4E] text-xs px-2 py-0.5 rounded-full">
                  {r.name}
                  <button onClick={() => setRecipients(p => p.filter(x => x.user_id !== r.user_id))}><X className="w-3 h-3" /></button>
                </span>
              ))}
            </div>
            <Input value={recipientSearch} onChange={e => setRecipientSearch(e.target.value)}
              placeholder="Nutzer suchen (Name / E-Mail)..." data-testid="ft-create-recipient-search" />
            {recipientResults.length > 0 && (
              <div className="border border-[#E2E4E0] rounded-lg mt-1 max-h-40 overflow-y-auto bg-white">
                {recipientResults.slice(0, 8).map(u => (
                  <button key={u.user_id}
                    disabled={!!recipients.find(r => r.user_id === u.user_id)}
                    onClick={() => { setRecipients(p => [...p, { user_id: u.user_id, name: u.name }]); setRecipientSearch(''); setRecipientResults([]); }}
                    className="w-full flex items-center gap-2 px-2 py-1.5 text-sm hover:bg-[#F3F4F1] disabled:opacity-50 text-left"
                    data-testid={`ft-recipient-${u.user_id}`}>
                    <Users className="w-3.5 h-3.5 text-[#6B7280]" /> {u.name} <span className="text-xs text-[#9CA3AF]">{u.email}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="text-xs font-medium text-[#6B7280]">Ablauf (Tage)</label>
            <Input type="number" value={expiry} onChange={e => setExpiry(e.target.value)} min={1} max={365}
              className="mt-1" data-testid="ft-create-expiry" />
          </div>

          <div ref={dropRef}
            className="border-2 border-dashed border-[#E2E4E0] hover:border-[#4A5D4E]/40 rounded-xl p-6 text-center transition"
            data-testid="ft-dropzone">
            <Upload className="w-8 h-8 text-[#9CA3AF] mx-auto mb-2" />
            <p className="text-sm text-[#6B7280] mb-2">Dateien hierher ziehen oder</p>
            <label className="inline-block cursor-pointer">
              <span className="bg-[#4A5D4E]/10 text-[#4A5D4E] text-xs font-medium px-3 py-1.5 rounded-lg hover:bg-[#4A5D4E]/15">Dateien auswählen</span>
              <input type="file" multiple onChange={handleFileInput} className="hidden" data-testid="ft-file-input" />
            </label>
            {files.length > 0 && (
              <div className="mt-3 text-left space-y-1 max-h-40 overflow-y-auto">
                {files.map((f, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-[#1C1F1D] bg-[#F9F9F8] rounded p-2">
                    <FileText className="w-3.5 h-3.5 text-[#6B7280]" />
                    <span className="truncate flex-1">{f.name}</span>
                    <span className="text-[10px] text-[#9CA3AF]">{fmtBytes(f.size)}</span>
                    {progress[f.name] != null && <span className="text-[10px] text-[#4A5D4E]">{progress[f.name]}%</span>}
                    <button onClick={() => setFiles(p => p.filter((_, j) => j !== i))} className="text-[#9CA3AF] hover:text-[#C87967]" disabled={creating}><X className="w-3 h-3" /></button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={creating}>Abbrechen</Button>
            <Button onClick={submit} disabled={creating || files.length === 0}
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" data-testid="ft-create-submit">
              {creating ? 'Wird erstellt...' : 'Senden'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ----------------- Detail Dialog -----------------
function TransferDetailDialog({ transferId, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [pwInput, setPwInput] = useState('');
  const [oneTime, setOneTime] = useState(false);
  const reload = useCallback(async () => {
    try {
      const { data } = await api.get(`/filetransfer/transfers/${transferId}`);
      setData(data);
    } catch { onClose(); }
  }, [transferId, onClose]);
  useEffect(() => { reload(); }, [reload]);
  if (!data) return null;
  const isOwner = data.owner_user_id;

  const revoke = async () => {
    if (!window.confirm('Transfer wirklich widerrufen?')) return;
    await api.patch(`/filetransfer/transfers/${transferId}`, { status: 'revoked' });
    toast.success('Widerrufen');
    onChanged(); reload();
  };
  const remove = async () => {
    if (!window.confirm('Transfer endgültig löschen?')) return;
    await api.delete(`/filetransfer/transfers/${transferId}`);
    toast.success('Gelöscht'); onChanged(); onClose();
  };
  const createShare = async () => {
    setShareLoading(true);
    try {
      const { data: s } = await api.post(`/filetransfer/transfers/${transferId}/shares`, {
        password: pwInput || null, one_time: oneTime,
      });
      const url = `${window.location.origin}/filetransfer/public/${s.token}`;
      try { await navigator.clipboard.writeText(url); } catch { /* ignore */ }
      toast.success('Link erstellt und in die Zwischenablage kopiert');
      setPwInput(''); setOneTime(false); reload();
    } catch (err) { toast.error(err?.response?.data?.detail || 'Fehler'); }
    finally { setShareLoading(false); }
  };
  const revokeShare = async (sid) => {
    await api.delete(`/filetransfer/shares/${sid}`);
    toast.success('Link widerrufen'); reload();
  };
  const download = async (fid, name) => {
    try {
      const resp = await api.get(`/filetransfer/transfers/${transferId}/files/${fid}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement('a'); a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(err?.response?.data?.detail || 'Download fehlgeschlagen'); }
  };
  const downloadZip = async () => {
    try {
      const resp = await api.get(`/filetransfer/transfers/${transferId}/zip`, { responseType: 'blob' });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement('a'); a.href = url; a.download = `transfer_${transferId}.zip`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(err?.response?.data?.detail || 'Download fehlgeschlagen'); }
  };
  void isOwner;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-[700px] max-h-[95vh] sm:max-h-[90vh] overflow-y-auto w-[calc(100vw-1rem)] sm:w-auto" data-testid={`ft-detail-${transferId}`}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="w-4 h-4" /> Transfer-Details
            <span className={`text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLOR[data.status] || STATUS_COLOR.draft}`}>{STATUS_LABEL[data.status]}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <section className="bg-[#F9F9F8] rounded-lg p-3 text-xs space-y-1">
            <div><span className="text-[#6B7280]">Von</span> <strong>{data.owner_name}</strong></div>
            <div><span className="text-[#6B7280]">Erstellt</span> {fmtDate(data.created_at)}</div>
            <div><span className="text-[#6B7280]">Ablauf</span> {fmtDate(data.expires_at)}</div>
            <div><span className="text-[#6B7280]">Empfänger</span> {(data.recipient_user_ids || []).length}</div>
            <div><span className="text-[#6B7280]">Downloads</span> {data.download_count || 0}</div>
            {data.message && <div className="pt-1"><span className="text-[#6B7280]">Nachricht:</span> <em>{data.message}</em></div>}
          </section>

          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-[#6B7280] uppercase">Dateien ({data.files?.length || 0})</h3>
              {data.files?.length > 1 && <Button size="sm" variant="outline" onClick={downloadZip} data-testid="ft-download-zip"><Download className="w-3.5 h-3.5 mr-1" />ZIP</Button>}
            </div>
            <div className="space-y-1">
              {(data.files || []).map(f => (
                <div key={f.file_id} className="flex items-center gap-2 bg-white border border-[#E2E4E0] rounded-lg p-2 text-sm" data-testid={`ft-file-${f.file_id}`}>
                  <FileText className="w-4 h-4 text-[#6B7280]" />
                  <span className="flex-1 truncate">{f.file_name}</span>
                  <span className="text-[10px] text-[#9CA3AF]">{fmtBytes(f.size_bytes)}</span>
                  {f.encrypted && <ShieldCheck className="w-3.5 h-3.5 text-[#6B8E23]" title={`AES-256-GCM (Key v${f.key_version})`} />}
                  <button onClick={() => download(f.file_id, f.file_name)} className="text-[#4A5D4E] hover:text-[#3E4E42]" data-testid={`ft-download-${f.file_id}`}>
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-[#6B7280] uppercase mb-2">Externe Links</h3>
            {(data.shares || []).map(s => (
              <div key={s.share_id} className="flex items-center gap-2 bg-white border border-[#E2E4E0] rounded-lg p-2 text-xs mb-1" data-testid={`ft-share-${s.share_id}`}>
                <LinkIcon className="w-3.5 h-3.5 text-[#4A5D4E]" />
                <input readOnly value={`${window.location.origin}/filetransfer/public/${s.token}`} className="flex-1 bg-transparent outline-none truncate" />
                <button onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/filetransfer/public/${s.token}`); toast.success('Kopiert'); }}><Copy className="w-3.5 h-3.5 text-[#6B7280]" /></button>
                {s.one_time && <span className="bg-[#D4A373]/15 text-[#D4A373] px-1.5 py-0.5 rounded-full text-[9px]">1×</span>}
                {!s.revoked && !s.password_hash && <Lock className="w-3 h-3 text-[#9CA3AF]" />}
                <span className="text-[9px] text-[#9CA3AF]">{s.downloaded_count || 0} DL</span>
                {!s.revoked ? (
                  <button onClick={() => revokeShare(s.share_id)} className="text-[#C87967] hover:underline">Widerrufen</button>
                ) : (
                  <span className="text-[#C87967]">widerrufen</span>
                )}
              </div>
            ))}
            <div className="bg-[#F9F9F8] rounded-lg p-3 mt-2 space-y-2">
              <p className="text-xs font-medium text-[#6B7280]">Neuen externen Link erstellen</p>
              <div className="flex items-center gap-2 flex-wrap">
                <Input type="password" placeholder="Passwort (optional)" value={pwInput} onChange={e => setPwInput(e.target.value)} className="h-8 text-xs flex-1 min-w-[120px]" data-testid="ft-share-pw" />
                <label className="flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={oneTime} onChange={e => setOneTime(e.target.checked)} data-testid="ft-share-onetime" />
                  Einmal-Download
                </label>
                <Button size="sm" onClick={createShare} disabled={shareLoading || data.status === 'revoked'} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" data-testid="ft-create-share">
                  <LinkIcon className="w-3.5 h-3.5 mr-1" />Link erstellen
                </Button>
              </div>
            </div>
          </section>

          {(data.downloads || []).length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-[#6B7280] uppercase mb-2 flex items-center gap-1"><Eye className="w-3 h-3" /> Downloads ({data.downloads.length})</h3>
              <div className="max-h-32 overflow-y-auto space-y-1">
                {data.downloads.map(d => (
                  <div key={d.download_id} className="text-[10px] text-[#6B7280] bg-white border border-[#E2E4E0] rounded p-1.5">
                    <strong>{d.by_name || 'extern'}</strong> via {d.channel} • {fmtDate(d.created_at)}
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="flex justify-between pt-2 border-t">
            <Button variant="outline" onClick={remove} className="text-[#C87967]" data-testid="ft-delete-transfer">
              <Trash2 className="w-3.5 h-3.5 mr-1" /> Löschen
            </Button>
            <div className="flex gap-2">
              {data.status !== 'revoked' && <Button variant="outline" onClick={revoke} data-testid="ft-revoke-transfer"><X className="w-3.5 h-3.5 mr-1" />Widerrufen</Button>}
              <Button onClick={onClose}>Schließen</Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
