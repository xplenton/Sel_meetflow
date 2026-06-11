import { useState } from 'react';
import { Download, X } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const extColors = {
  pdf: '#C87967', doc: '#4A5D4E', docx: '#4A5D4E', xls: '#6B8E23', xlsx: '#6B8E23',
  ppt: '#D4A373', pptx: '#D4A373', zip: '#9CA3AF', rar: '#9CA3AF', txt: '#6B7280',
};

// Chat file preview card with download + lightbox for images/PDFs.
export default function FilePreview({ msg, isOwn }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const fileUrl = `${API_URL}${msg.file_url}`;
  const downloadUrl = `${fileUrl}?download=1`;
  const type = msg.file_type || '';
  const name = msg.file_name || 'Datei';
  const size = msg.file_size ? (msg.file_size < 1024 * 1024 ? `${(msg.file_size / 1024).toFixed(0)} KB` : `${(msg.file_size / 1024 / 1024).toFixed(1)} MB`) : '';
  const ext = name.split('.').pop()?.toLowerCase() || '';

  const handleDownload = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      const res = await fetch(downloadUrl);
      if (!res.ok) throw new Error('Fetch failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 200);
    } catch {
      try {
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = downloadUrl;
        document.body.appendChild(iframe);
        setTimeout(() => document.body.removeChild(iframe), 5000);
      } catch {
        window.location.href = downloadUrl;
      }
    }
  };

  const isImg = type.startsWith('image/');
  const isPdf = type === 'application/pdf' || ext === 'pdf';
  const isVideo = type.startsWith('video/');
  const isAudio = type.startsWith('audio/');
  const extColor = extColors[ext] || '#4A5D4E';

  if (isImg) {
    return (
      <div>
        <img src={fileUrl} alt={name} className="max-w-[260px] rounded-lg mb-1 cursor-pointer" loading="lazy"
          onClick={() => setLightboxOpen(true)} />
        <div className="flex items-center gap-2 mt-1">
          <span className={`text-[10px] truncate max-w-[160px] ${isOwn ? 'text-white/50' : 'text-[#9CA3AF]'}`}>{name}</span>
          {size && <span className={`text-[10px] ${isOwn ? 'text-white/40' : 'text-[#9CA3AF]'}`}>{size}</span>}
          <button onClick={handleDownload} className={`flex-shrink-0 ${isOwn ? 'text-white/60 hover:text-white' : 'text-[#4A5D4E] hover:text-[#3E4E42]'}`} title="Herunterladen">
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
        {lightboxOpen && (
          <div className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center" onClick={() => setLightboxOpen(false)} data-testid="image-lightbox">
            <button onClick={() => setLightboxOpen(false)} className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 flex items-center justify-center text-white transition-colors z-10" data-testid="lightbox-close">
              <X className="w-5 h-5" />
            </button>
            <button onClick={handleDownload} className="absolute top-4 right-16 w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 flex items-center justify-center text-white transition-colors z-10" title="Herunterladen">
              <Download className="w-5 h-5" />
            </button>
            <img src={fileUrl} alt={name} className="max-w-[90vw] max-h-[85vh] rounded-lg object-contain" onClick={e => e.stopPropagation()} />
          </div>
        )}
      </div>
    );
  }

  if (isPdf) {
    return (
      <div className={`rounded-lg overflow-hidden ${isOwn ? 'bg-white/10' : 'bg-[#F3F4F1]'}`} style={{ maxWidth: 280 }}>
        <div className="h-40 relative">
          <iframe src={`${fileUrl}#toolbar=0&navpanes=0`} className="w-full h-full border-0" title={name} />
          <button onClick={() => setLightboxOpen(true)}
            className="absolute inset-0 bg-transparent hover:bg-black/5 transition-colors" />
        </div>
        <div className="px-3 py-2 flex items-center gap-2">
          <div className="w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${extColor}18` }}>
            <span className="text-[9px] font-bold uppercase" style={{ color: extColor }}>PDF</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-xs font-medium truncate ${isOwn ? 'text-white' : 'text-[#1C1F1D]'}`}>{name}</p>
            {size && <p className={`text-[10px] ${isOwn ? 'text-white/50' : 'text-[#9CA3AF]'}`}>{size}</p>}
          </div>
          <button onClick={handleDownload} className={`p-1 rounded hover:bg-black/10 flex-shrink-0 ${isOwn ? 'text-white/60' : 'text-[#4A5D4E]'}`} title="Herunterladen">
            <Download className="w-4 h-4" />
          </button>
        </div>
        {lightboxOpen && (
          <div className="fixed inset-0 z-[100] bg-black/80 flex flex-col" onClick={() => setLightboxOpen(false)} data-testid="pdf-lightbox">
            <div className="flex items-center justify-between px-4 py-3 flex-shrink-0" onClick={e => e.stopPropagation()}>
              <span className="text-white text-sm font-medium truncate">{name}</span>
              <div className="flex items-center gap-2">
                <button onClick={handleDownload} className="w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 flex items-center justify-center text-white transition-colors" title="Herunterladen">
                  <Download className="w-5 h-5" />
                </button>
                <button onClick={() => setLightboxOpen(false)} className="w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 flex items-center justify-center text-white transition-colors" data-testid="pdf-lightbox-close">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            <div className="flex-1 p-2" onClick={e => e.stopPropagation()}>
              <iframe src={fileUrl} className="w-full h-full border-0 rounded-lg bg-white" title={name} />
            </div>
          </div>
        )}
      </div>
    );
  }

  if (isVideo) {
    return (
      <div>
        <video src={fileUrl} controls className="max-w-[280px] rounded-lg" preload="metadata" />
        <div className="flex items-center gap-2 mt-1">
          <span className={`text-[10px] truncate max-w-[160px] ${isOwn ? 'text-white/50' : 'text-[#9CA3AF]'}`}>{name}</span>
          {size && <span className={`text-[10px] ${isOwn ? 'text-white/40' : 'text-[#9CA3AF]'}`}>{size}</span>}
          <button onClick={handleDownload} className={`flex-shrink-0 ${isOwn ? 'text-white/60 hover:text-white' : 'text-[#4A5D4E]'}`}>
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  if (isAudio) {
    return (
      <div>
        <audio src={fileUrl} controls className="max-w-[260px]" preload="metadata" />
        <div className="flex items-center gap-2 mt-1">
          <span className={`text-[10px] truncate max-w-[160px] ${isOwn ? 'text-white/50' : 'text-[#9CA3AF]'}`}>{name}</span>
          {size && <span className={`text-[10px] ${isOwn ? 'text-white/40' : 'text-[#9CA3AF]'}`}>{size}</span>}
          <button onClick={handleDownload} className={`flex-shrink-0 ${isOwn ? 'text-white/60 hover:text-white' : 'text-[#4A5D4E]'}`}>
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg ${isOwn ? 'bg-white/10' : 'bg-[#F3F4F1]'} cursor-pointer hover:opacity-90 transition-opacity`} style={{ minWidth: 220 }}
      onClick={handleDownload} data-testid={`file-card-${msg.message_id}`}>
      <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${extColor}18` }}>
        <span className="text-[10px] font-bold uppercase" style={{ color: extColor }}>{ext || '?'}</span>
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-medium truncate ${isOwn ? 'text-white' : 'text-[#1C1F1D]'}`}>{name}</p>
        <p className={`text-[10px] ${isOwn ? 'text-white/50' : 'text-[#9CA3AF]'}`}>
          {size}{size ? ' · ' : ''}Herunterladen
        </p>
      </div>
      <div className={`p-2 rounded-lg flex-shrink-0 ${isOwn ? 'bg-white/10 text-white/70 hover:text-white' : 'bg-[#4A5D4E]/10 text-[#4A5D4E] hover:bg-[#4A5D4E]/20'} transition-colors`} data-testid={`download-${msg.message_id}`}>
        <Download className="w-4.5 h-4.5" />
      </div>
    </div>
  );
}
