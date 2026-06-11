import { useRef, useState } from 'react';
import { Paperclip, X, FileText, Image as ImageIcon, Download } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const MAX_SIZE = 10 * 1024 * 1024;

const ACCEPT = [
  'image/*', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
  '.txt', '.csv', '.md', 'audio/*', 'video/mp4', 'video/webm',
].join(',');

function fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentChip({ att, onRemove, compact = false }) {
  const isImage = (att.mime || '').startsWith('image/');
  const fullUrl = att.url?.startsWith('http') ? att.url : `${API_URL}${att.url}`;
  if (isImage && !compact) {
    return (
      <div className="relative inline-block" data-testid={`attachment-chip-${att.attachment_id}`}>
        <a href={fullUrl} target="_blank" rel="noopener noreferrer">
          <img src={fullUrl} alt={att.filename} className="h-20 w-20 object-cover rounded-lg border border-[#E2E4E0]" />
        </a>
        {onRemove && (
          <button type="button" onClick={() => onRemove(att.attachment_id)}
            className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-[#1C1F1D] text-white rounded-full flex items-center justify-center hover:bg-[#C87967]"
            data-testid={`remove-attachment-${att.attachment_id}`}>
            <X className="w-3 h-3" />
          </button>
        )}
      </div>
    );
  }
  const Icon = isImage ? ImageIcon : FileText;
  return (
    <div className="inline-flex items-center gap-2 max-w-[260px] bg-[#F3F4F1] border border-[#E2E4E0] rounded-lg px-2 py-1.5"
      data-testid={`attachment-chip-${att.attachment_id}`}>
      <Icon className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0" />
      <a href={fullUrl} target="_blank" rel="noopener noreferrer"
        className="text-xs text-[#1C1F1D] truncate hover:underline flex-1 min-w-0">
        {att.filename}
      </a>
      <span className="text-[10px] text-[#9CA3AF]">{fmtSize(att.size)}</span>
      <a href={`${fullUrl}?download=1`} className="text-[#9CA3AF] hover:text-[#4A5D4E]"
        data-testid={`download-attachment-${att.attachment_id}`}>
        <Download className="w-3 h-3" />
      </a>
      {onRemove && (
        <button type="button" onClick={() => onRemove(att.attachment_id)}
          className="text-[#9CA3AF] hover:text-[#C87967]"
          data-testid={`remove-attachment-${att.attachment_id}`}>
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

export default function AttachmentPicker({ attachments = [], onChange, max = 5, buttonLabel = null, testId = 'attachment-picker' }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  const upload = async (files) => {
    const list = Array.from(files || []).slice(0, max - attachments.length);
    if (list.length === 0) return;
    setUploading(true);
    const successes = [];
    for (const f of list) {
      if (f.size > MAX_SIZE) {
        toast.error(`"${f.name}" ist zu gross (max 10 MB)`);
        continue;
      }
      try {
        const form = new FormData();
        form.append('file', f);
        const { data } = await api.post('/attachments/upload', form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        successes.push(data);
      } catch (e) {
        toast.error(e.response?.data?.detail || `Upload fehlgeschlagen: ${f.name}`);
      }
    }
    if (successes.length) {
      onChange([...attachments, ...successes]);
    }
    setUploading(false);
    if (inputRef.current) inputRef.current.value = '';
  };

  const removeAt = (id) => {
    onChange(attachments.filter(a => a.attachment_id !== id));
  };

  return (
    <div data-testid={testId}>
      <input ref={inputRef} type="file" multiple accept={ACCEPT} className="hidden"
        onChange={e => upload(e.target.files)}
        data-testid={`${testId}-input`} />
      <button type="button" onClick={() => inputRef.current?.click()}
        disabled={uploading || attachments.length >= max}
        className="inline-flex items-center gap-1.5 text-xs text-[#4A5D4E] hover:text-[#3E4E42] disabled:opacity-50"
        title={attachments.length >= max ? `Max ${max} Anhänge` : 'Anhang hinzufügen'}
        data-testid={`${testId}-btn`}>
        <Paperclip className="w-3.5 h-3.5" />
        {uploading ? 'Laedt hoch...' : (buttonLabel || 'Anhang')}
      </button>
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2" data-testid={`${testId}-list`}>
          {attachments.map(att => (
            <AttachmentChip key={att.attachment_id} att={att} onRemove={removeAt} />
          ))}
        </div>
      )}
    </div>
  );
}
