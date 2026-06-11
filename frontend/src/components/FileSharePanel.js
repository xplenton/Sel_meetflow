import { useState, useEffect, useCallback, useRef } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import { X, Upload, FileText, Download, Trash2, File as FileIcon, Image, Film } from 'lucide-react';
import api, { API_URL } from '../lib/api';
import { toast } from 'sonner';

export default function FileSharePanel({ meetingId, onClose }) {
  const { t } = useLanguage();
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  const fetchFiles = useCallback(async () => {
    try { const { data } = await api.get(`/meetings/${meetingId}/files`); setFiles(data); } catch {}
  }, [meetingId]);

  useEffect(() => { fetchFiles(); const i = setInterval(fetchFiles, 10000); return () => clearInterval(i); }, [fetchFiles]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) { toast.error('Max 50MB'); return; }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await api.post(`/meetings/${meetingId}/files`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('File uploaded');
      fetchFiles();
    } catch (err) {
      toast.error('Upload failed');
    } finally { setUploading(false); if (inputRef.current) inputRef.current.value = ''; }
  };

  const handleDownload = async (f) => {
    try {
      const response = await api.get(`/files/${f.file_id}/download`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url; a.download = f.original_filename; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Download failed'); }
  };

  const handleDelete = async (fileId) => {
    try { await api.delete(`/files/${fileId}`); fetchFiles(); } catch {}
  };

  const formatSize = (bytes) => {
    if (!bytes) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const fileIcon = (ct) => {
    if (ct?.startsWith('image/')) return Image;
    if (ct?.startsWith('video/')) return Film;
    return FileIcon;
  };

  return (
    <div className="w-full sm:w-80 fixed inset-0 sm:static sm:inset-auto bg-white border-l border-[#E2E4E0] flex flex-col h-full z-40 sm:z-auto" data-testid="file-share-panel">
      <div className="flex items-center justify-between p-4 border-b border-[#E2E4E0]">
        <h3 className="text-sm font-medium text-[#1C1F1D]">{t('fileSharing')}</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-[#F3F4F1] text-[#9CA3AF]" data-testid="close-files-panel"><X className="w-4 h-4" /></button>
      </div>

      <div className="p-3 border-b border-[#E2E4E0]">
        <input ref={inputRef} type="file" onChange={handleUpload} className="hidden" data-testid="file-input" />
        <Button onClick={() => inputRef.current?.click()} disabled={uploading} size="sm" data-testid="upload-file-button"
          className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg text-xs h-8">
          <Upload className="w-3.5 h-3.5 mr-1.5" /> {uploading ? 'Uploading...' : t('uploadFile')}
        </Button>
      </div>

      <ScrollArea className="flex-1 p-3">
        {files.length === 0 ? (
          <div className="text-center py-8">
            <FileText className="w-8 h-8 text-[#E2E4E0] mx-auto mb-2" />
            <p className="text-xs text-[#9CA3AF]">{t('noFiles')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {files.map(f => {
              const Icon = fileIcon(f.content_type);
              return (
                <div key={f.file_id} className="flex items-center gap-2.5 p-2.5 rounded-lg border border-[#E2E4E0] hover:border-[#4A5D4E]/30 transition-colors"
                  data-testid={`file-${f.file_id}`}>
                  <div className="w-8 h-8 rounded-lg bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-4 h-4 text-[#4A5D4E]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-[#1C1F1D] truncate">{f.original_filename}</p>
                    <p className="text-[10px] text-[#9CA3AF]">{formatSize(f.size)} - {f.uploaded_by_name}</p>
                  </div>
                  <div className="flex gap-0.5">
                    <button onClick={() => handleDownload(f)} className="p-1 rounded hover:bg-[#E8EAE6] text-[#4A5D4E]" data-testid={`download-${f.file_id}`}>
                      <Download className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => handleDelete(f.file_id)} className="p-1 rounded hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967]" data-testid={`delete-file-${f.file_id}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
