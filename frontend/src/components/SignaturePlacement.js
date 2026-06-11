import { useState, useRef, useCallback, useEffect } from 'react';
import { Button } from '../components/ui/button';
import { Check, X, Move, ZoomIn, ZoomOut, ChevronLeft, ChevronRight } from 'lucide-react';
import api from '../lib/api';
import PdfRenderer from './PdfRenderer';
import { useLanguage } from '../contexts/LanguageContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function SignaturePlacement({ meetingId, doc, signatureData, onConfirm, onCancel }) {
  const { t } = useLanguage();
  const containerRef = useRef(null);
  const docAreaRef = useRef(null);
  const [pos, setPos] = useState({ x: 200, y: 400 });
  const [zoom, setZoom] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [existingSigs, setExistingSigs] = useState([]);
  const isDragging = useRef(false);
  const dragOffset = useRef({ x: 0, y: 0 });

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/meetings/${meetingId}/documents`);
        const thisDoc = data.find(d => d.doc_id === doc.doc_id);
        if (thisDoc?.signatures) setExistingSigs(thisDoc.signatures.filter(s => s.pos_x || s.pos_y));
      } catch {}
    })();
  }, [meetingId, doc.doc_id]);

  const viewUrl = `${API_URL}/api/meetings/${meetingId}/documents/${doc.doc_id}/view`;
  const isImage = ['png', 'jpg', 'jpeg', 'webp'].includes(doc.file_ext);

  const sigPreview = signatureData.type === 'drawn'
    ? signatureData.signature_data
    : null;

  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    isDragging.current = true;
    if (!docAreaRef.current) return;
    const docRect = docAreaRef.current.getBoundingClientRect();
    dragOffset.current = {
      x: (e.clientX - docRect.left) / zoom - pos.x,
      y: (e.clientY - docRect.top) / zoom - pos.y,
    };
  }, [zoom, pos]);

  const handleMouseMove = useCallback((e) => {
    if (!isDragging.current || !docAreaRef.current) return;
    const docRect = docAreaRef.current.getBoundingClientRect();
    const x = (e.clientX - docRect.left) / zoom - dragOffset.current.x;
    const y = (e.clientY - docRect.top) / zoom - dragOffset.current.y;
    setPos({ x: Math.max(0, x), y: Math.max(0, y) });
  }, [zoom]);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  const handleTouchStart = useCallback((e) => {
    const touch = e.touches[0];
    isDragging.current = true;
    if (!docAreaRef.current) return;
    const docRect = docAreaRef.current.getBoundingClientRect();
    dragOffset.current = {
      x: (touch.clientX - docRect.left) / zoom - pos.x,
      y: (touch.clientY - docRect.top) / zoom - pos.y,
    };
  }, [zoom, pos]);

  const handleTouchMove = useCallback((e) => {
    if (!isDragging.current || !docAreaRef.current) return;
    const touch = e.touches[0];
    const docRect = docAreaRef.current.getBoundingClientRect();
    const x = (touch.clientX - docRect.left) / zoom - dragOffset.current.x;
    const y = (touch.clientY - docRect.top) / zoom - dragOffset.current.y;
    setPos({ x: Math.max(0, x), y: Math.max(0, y) });
  }, [zoom]);

  const handleConfirm = () => {
    onConfirm({
      ...signatureData,
      pos_x: Math.round(pos.x),
      pos_y: Math.round(pos.y),
      page: currentPage,
    });
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/80 flex flex-col" data-testid="signature-placement-overlay">
      {/* Toolbar */}
      <div className="h-12 bg-[#1A1D1B] border-b border-white/10 flex items-center justify-between px-2 sm:px-4 flex-shrink-0">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <Move className="w-4 h-4 text-white/60 flex-shrink-0" />
          <span className="text-white/80 text-xs sm:text-sm truncate">{t('placeSignature')}</span>
        </div>
        <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0">
          <Button variant="ghost" size="sm" onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}
            className="h-7 w-7 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="placement-zoom-out">
            <ZoomOut className="w-3.5 h-3.5" />
          </Button>
          <span className="text-white/50 text-[10px] w-8 text-center hidden sm:inline">{Math.round(zoom * 100)}%</span>
          <Button variant="ghost" size="sm" onClick={() => setZoom(z => Math.min(2, z + 0.25))}
            className="h-7 w-7 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="placement-zoom-in">
            <ZoomIn className="w-3.5 h-3.5" />
          </Button>
          {doc.file_ext === 'pdf' && (
            <>
              <div className="w-px h-5 bg-white/10 mx-0.5 hidden sm:block" />
              <Button variant="ghost" size="sm" onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                className="h-7 w-7 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="placement-prev-page">
                <ChevronLeft className="w-3.5 h-3.5" />
              </Button>
              <span className="text-white/50 text-[10px] min-w-[30px] text-center" data-testid="placement-page-num">
                {currentPage}/{totalPages}
              </span>
              <Button variant="ghost" size="sm" onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                className="h-7 w-7 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="placement-next-page">
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </>
          )}
          <div className="w-px h-5 bg-white/10 mx-0.5" />
          <Button size="sm" onClick={onCancel}
            className="h-7 px-2 sm:px-3 text-[10px] sm:text-xs bg-transparent border border-white/20 text-white/70 hover:bg-white/10"
            data-testid="placement-cancel">
            <X className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">{t('cancel')}</span>
          </Button>
          <Button size="sm" onClick={handleConfirm}
            className="h-7 px-2 sm:px-3 text-[10px] sm:text-xs bg-[#4A5D4E] hover:bg-[#3E4E42] text-white"
            data-testid="placement-confirm">
            <Check className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">{t('save')}</span>
          </Button>
        </div>
      </div>

      {/* Document with draggable signature */}
      <div className="flex-1 flex overflow-hidden">
        {/* Page thumbnails sidebar for PDFs - hidden on mobile */}
        {doc.file_ext === 'pdf' && (
          <div className="w-16 sm:w-20 bg-[#111] border-r border-white/10 overflow-y-auto flex-shrink-0 p-1.5 sm:p-2 space-y-1.5 sm:space-y-2 hidden sm:block"
            data-testid="page-thumbnails">
            {Array.from({ length: Math.max(totalPages, 5) }, (_, i) => i + 1).map(p => (
              <button key={p} onClick={() => setCurrentPage(p)}
                className={`w-full aspect-[3/4] rounded border-2 transition-colors flex items-center justify-center text-[10px] ${
                  p === currentPage ? 'border-[#4A5D4E] bg-white/10 text-white' : 'border-white/10 bg-white/5 text-white/40 hover:border-white/30'
                }`}
                data-testid={`page-thumb-${p}`}>
                {p}
              </button>
            ))}
          </div>
        )}

        {/* Document area - scrollable */}
        <div className="flex-1 overflow-auto p-4 sm:p-6"
          ref={containerRef}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleMouseUp}>
          <div className="relative inline-block" ref={docAreaRef} style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
            {/* Document Preview */}
            {isImage ? (
              <img src={viewUrl} alt={doc.filename}
                className="max-w-[800px] rounded-lg shadow-2xl select-none pointer-events-none"
                draggable={false} data-testid="placement-doc-image" />
            ) : doc.file_ext === 'pdf' ? (
              <div className="pointer-events-none">
                <PdfRenderer meetingId={meetingId} docId={doc.doc_id} page={currentPage}
                  className="shadow-2xl" onPageCount={setTotalPages} />
              </div>
            ) : (
              <div className="w-[800px] h-[600px] bg-white rounded-lg shadow-2xl flex items-center justify-center">
                <span className="text-[#9CA3AF]">{t('documentPreview')}: {doc.filename}</span>
              </div>
            )}

            {/* Existing signatures */}
            {existingSigs.filter(s => (s.page || 1) === currentPage).map((sig, i) => (
              <div key={sig.sig_id || i} className="absolute pointer-events-none"
                style={{ left: sig.pos_x, top: sig.pos_y }} data-testid={`existing-sig-${i}`}>
                <div className="border border-[#4A5D4E]/30 rounded bg-white/80 px-2 py-1 shadow-sm opacity-70">
                  {sig.type === 'drawn' && sig.signature_data?.startsWith('data:image') ? (
                    <img src={sig.signature_data} alt={sig.signer_name} className="h-8 max-w-[140px] object-contain" />
                  ) : (
                    <span className="text-sm italic font-serif text-[#1C1F1D]">{sig.signature_data}</span>
                  )}
                  <span className="block text-[7px] text-[#9CA3AF]">{sig.signer_name}</span>
                </div>
              </div>
            ))}

            {/* Draggable Signature */}
            <div
              className="absolute cursor-grab active:cursor-grabbing select-none touch-none"
              style={{ left: pos.x, top: pos.y }}
              onMouseDown={handleMouseDown}
              onTouchStart={handleTouchStart}
              data-testid="draggable-signature"
            >
              <div className="border-2 border-dashed border-[#4A5D4E] rounded-lg p-2 bg-white/90 shadow-lg min-w-[100px] sm:min-w-[120px]">
                {sigPreview ? (
                  <img src={sigPreview} alt={t('signatureLabel')} className="h-10 sm:h-12 max-w-[160px] sm:max-w-[200px] object-contain pointer-events-none" draggable={false} />
                ) : (
                  <span className="text-base sm:text-lg italic font-serif text-[#1C1F1D] block px-1 sm:px-2">
                    {signatureData.signature_data}
                  </span>
                )}
                <div className="flex items-center gap-1 mt-1 pt-1 border-t border-[#E2E4E0]">
                  <Move className="w-2.5 h-2.5 text-[#9CA3AF]" />
                  <span className="text-[8px] text-[#9CA3AF]">{t('drag')}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Position indicator */}
      <div className="h-7 bg-[#1A1D1B] border-t border-white/10 flex items-center justify-center flex-shrink-0">
        <span className="text-white/40 text-[10px]" data-testid="placement-position-info">
          X={Math.round(pos.x)}, Y={Math.round(pos.y)} | {t('pageLabel')} {currentPage}
        </span>
      </div>
    </div>
  );
}
