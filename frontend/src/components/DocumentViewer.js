import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import {
  ChevronLeft, ChevronRight, Maximize2, Minimize2, X, Download, PenTool, Plus, Crosshair
} from 'lucide-react';
import api, { API_URL } from '../lib/api';
import { toast } from 'sonner';
import PdfRenderer from './PdfRenderer';
import { useLanguage } from '../contexts/LanguageContext';

export default function DocumentViewer({ meetingId, doc, isPresenter, onClose, onPageChange, sigVersion }) {
  const { t } = useLanguage();
  const [fullscreen, setFullscreen] = useState(false);
  const [page, setPage] = useState(doc?.current_page || 1);
  const [signatures, setSignatures] = useState([]);
  const [sigFields, setSigFields] = useState([]);
  const [placeMode, setPlaceMode] = useState(false);
  const [pendingField, setPendingField] = useState(null);
  const [fieldLabel, setFieldLabel] = useState('Unterschrift');
  const [totalPages, setTotalPages] = useState(1);
  const docRef = useRef(null);
  const dragRef = useRef(null); // { type: 'move'|'resize', fieldId, startX, startY, origX, origY, origW, origH }

  const viewUrl = `${API_URL}/api/meetings/${meetingId}/documents/${doc.doc_id}/view`;
  const isImage = ['png', 'jpg', 'jpeg', 'webp'].includes(doc.file_ext);

  const fetchData = useCallback(async () => {
    try {
      const [docsRes, fieldsRes] = await Promise.all([
        api.get(`/meetings/${meetingId}/documents`),
        api.get(`/meetings/${meetingId}/documents/${doc.doc_id}/signature-fields`),
      ]);
      const thisDoc = docsRes.data.find(d => d.doc_id === doc.doc_id);
      if (thisDoc?.signatures) setSignatures(thisDoc.signatures);
      setSigFields(fieldsRes.data.fields || []);
    } catch {}
  }, [meetingId, doc.doc_id]);

  useEffect(() => { fetchData(); }, [fetchData, sigVersion]);

  const changePage = async (newPage) => {
    if (newPage < 1) return;
    setPage(newPage);
    if (isPresenter && onPageChange) onPageChange(doc.doc_id, newPage);
  };

  const handleDownload = async () => {
    try {
      const hasSigs = signatures.length > 0;
      const endpoint = hasSigs
        ? `/meetings/${meetingId}/documents/${doc.doc_id}/download-signed`
        : `/meetings/${meetingId}/documents/${doc.doc_id}/view`;
      const response = await api.get(endpoint, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = hasSigs ? `signed_${doc.filename}` : doc.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {}
  };

  const handleDocClick = (e) => {
    if (!placeMode || !docRef.current) return;
    const rect = docRef.current.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);
    setPendingField({ x, y, page });
    setFieldLabel('Unterschrift');
  };

  const confirmField = async () => {
    if (!pendingField) return;
    try {
      await api.post(`/meetings/${meetingId}/documents/${doc.doc_id}/signature-fields`, {
        x: pendingField.x, y: pendingField.y, page: pendingField.page,
        label: fieldLabel || 'Unterschrift',
      });
      toast.success(t('signatureFieldPlaced'));
      setPendingField(null);
      setPlaceMode(false);
      fetchData();
    } catch {
      toast.error(t('placementFailed'));
    }
  };

  const cancelField = () => {
    setPendingField(null);
  };

  const startFieldDrag = (e, field) => {
    e.preventDefault();
    e.stopPropagation();
    dragRef.current = {
      type: 'move', fieldId: field.field_id,
      startX: e.clientX, startY: e.clientY,
      origX: field.x, origY: field.y,
      origW: field.width || 200, origH: field.height || 60,
    };
    const onMove = (me) => {
      if (!dragRef.current) return;
      const dx = me.clientX - dragRef.current.startX;
      const dy = me.clientY - dragRef.current.startY;
      setSigFields(prev => prev.map(f =>
        f.field_id === dragRef.current.fieldId
          ? { ...f, x: Math.max(0, dragRef.current.origX + dx), y: Math.max(0, dragRef.current.origY + dy) }
          : f
      ));
    };
    const onUp = async () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (!dragRef.current) return;
      const updated = sigFields.find(f => f.field_id === dragRef.current.fieldId);
      if (updated) {
        try {
          await api.put(`/meetings/${meetingId}/documents/${doc.doc_id}/signature-fields/${dragRef.current.fieldId}`, {
            x: updated.x, y: updated.y,
          });
        } catch {}
      }
      dragRef.current = null;
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  const startFieldResize = (e, field) => {
    e.preventDefault();
    e.stopPropagation();
    dragRef.current = {
      type: 'resize', fieldId: field.field_id,
      startX: e.clientX, startY: e.clientY,
      origX: field.x, origY: field.y,
      origW: field.width || 200, origH: field.height || 60,
    };
    const onMove = (me) => {
      if (!dragRef.current) return;
      const dx = me.clientX - dragRef.current.startX;
      const dy = me.clientY - dragRef.current.startY;
      setSigFields(prev => prev.map(f =>
        f.field_id === dragRef.current.fieldId
          ? { ...f, width: Math.max(80, dragRef.current.origW + dx), height: Math.max(30, dragRef.current.origH + dy) }
          : f
      ));
    };
    const onUp = async () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (!dragRef.current) return;
      const updated = sigFields.find(f => f.field_id === dragRef.current.fieldId);
      if (updated) {
        try {
          await api.put(`/meetings/${meetingId}/documents/${doc.doc_id}/signature-fields/${dragRef.current.fieldId}`, {
            width: updated.width, height: updated.height,
          });
        } catch {}
      }
      dragRef.current = null;
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  const pageSigs = signatures.filter(s => (s.page || 1) === page && (s.pos_x || s.pos_y));
  const pageFields = sigFields.filter(f => (f.page || 1) === page);

  return (
    <div className={`bg-[#1A1D1B] flex flex-col ${fullscreen ? 'fixed inset-0 z-50' : 'flex-1 border-l border-white/10'}`}
      data-testid="document-viewer">
      {/* Toolbar */}
      <div className="h-10 flex items-center justify-between px-2 sm:px-3 border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-1 sm:gap-2 min-w-0">
          <span className="text-white/80 text-[10px] sm:text-xs font-medium truncate max-w-[100px] sm:max-w-[200px]">{doc.filename}</span>
          {signatures.length > 0 && (
            <Badge className="bg-[#4A5D4E]/30 text-[#4A5D4E] text-[9px] flex-shrink-0" data-testid="doc-sig-count">
              {signatures.length}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-0.5 sm:gap-1 flex-shrink-0">
          {!isImage && isPresenter && (
            <div className="flex items-center gap-0.5">
              <Button variant="ghost" size="sm" onClick={() => changePage(page - 1)} disabled={page <= 1}
                className="h-6 w-6 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="doc-prev-page">
                <ChevronLeft className="w-3.5 h-3.5" />
              </Button>
              <span className="text-white/60 text-[10px] min-w-[30px] sm:min-w-[50px] text-center" data-testid="doc-page-num">{page}/{totalPages}</span>
              <Button variant="ghost" size="sm" onClick={() => changePage(page + 1)} disabled={page >= totalPages}
                className="h-6 w-6 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="doc-next-page">
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          )}
          {isPresenter && (
            <Button variant="ghost" size="sm" onClick={() => { setPlaceMode(!placeMode); setPendingField(null); }}
              className={`h-6 px-1.5 sm:px-2 text-[10px] ${placeMode ? 'bg-[#D4A373]/20 text-[#D4A373]' : 'text-white/60 hover:text-white hover:bg-white/10'}`}
              data-testid="place-field-mode-btn">
              <Crosshair className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">Feld</span>
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={handleDownload}
            className="h-6 w-6 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="doc-viewer-download">
            <Download className="w-3.5 h-3.5" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setFullscreen(!fullscreen)}
            className="h-6 w-6 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="doc-viewer-fullscreen">
            {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </Button>
          {isPresenter && (
            <Button variant="ghost" size="sm" onClick={onClose}
              className="h-6 w-6 p-0 text-white/60 hover:text-white hover:bg-white/10" data-testid="doc-viewer-close">
              <X className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Place mode hint */}
      {placeMode && (
        <div className="h-7 bg-[#D4A373]/10 border-b border-[#D4A373]/20 flex items-center justify-center"
          data-testid="place-mode-hint">
          <Crosshair className="w-3 h-3 text-[#D4A373] mr-1.5" />
          <span className="text-[10px] text-[#D4A373]">{t('sigFieldPlaceHint')}</span>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-2 sm:p-4">
        <div className={`relative inline-block ${placeMode ? 'cursor-crosshair' : ''}`}
          ref={docRef} onClick={handleDocClick}>
          {isImage ? (
            <img src={viewUrl} alt={doc.filename}
              className="max-w-full max-h-full object-contain rounded-lg" data-testid="doc-viewer-image" />
          ) : doc.file_ext === 'pdf' ? (
            <PdfRenderer meetingId={meetingId} docId={doc.doc_id} page={page}
              onPageCount={setTotalPages} />
          ) : (
            <div className="text-center text-white/60">
              <p className="text-sm mb-3">{t('previewNotAvailable')} .{doc.file_ext}</p>
              <Button size="sm" onClick={handleDownload} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white text-xs">
                <Download className="w-3.5 h-3.5 mr-1.5" />{t('download')}
              </Button>
            </div>
          )}

          {/* Signature overlays */}
          {pageSigs.map((sig, i) => (
            <div key={sig.sig_id || i}
              className="absolute pointer-events-none"
              style={{ left: sig.pos_x, top: sig.pos_y }}
              data-testid={`sig-overlay-${sig.sig_id || i}`}>
              <div className="border border-[#4A5D4E]/40 rounded bg-white/90 px-2 py-1 shadow-sm">
                {sig.type === 'drawn' && sig.signature_data?.startsWith('data:image') ? (
                  <img src={sig.signature_data} alt={sig.signer_name} className="h-8 max-w-[140px] object-contain" />
                ) : (
                  <span className="text-sm italic font-serif text-[#1C1F1D]">{sig.signature_data}</span>
                )}
                <span className="block text-[7px] text-[#9CA3AF]">{sig.signer_name}</span>
              </div>
            </div>
          ))}

          {/* Signature field placeholders */}
          {pageFields.map((f, i) => {
            const isSigned = f.status === 'signed';
            const isEditable = placeMode && isPresenter && !isSigned;
            return (
              <div key={f.field_id || i}
                className={`absolute ${isEditable ? '' : 'pointer-events-none'}`}
                style={{ left: f.x, top: f.y, width: f.width || 200, height: f.height || 60 }}
                data-testid={`field-overlay-${f.field_id || i}`}
                onMouseDown={isEditable ? (e) => startFieldDrag(e, f) : undefined}>
                <div className={`w-full h-full rounded border-2 flex flex-col items-center justify-center relative ${
                  isEditable ? 'border-solid cursor-move border-[#D4A373] bg-[#D4A373]/10' :
                  isSigned ? 'border-dashed border-[#4A5D4E]/40 bg-[#4A5D4E]/5' : 'border-dashed border-[#D4A373]/50 bg-[#D4A373]/5'
                }`}>
                  {isSigned ? (
                    <span className="text-[9px] text-[#4A5D4E] font-medium">{f.signed_by}</span>
                  ) : (
                    <>
                      <PenTool className="w-3 h-3 text-[#D4A373]/60 mb-0.5" />
                      <span className="text-[8px] text-[#D4A373]/70">{f.label}</span>
                      {f.assigned_name && <span className="text-[7px] text-[#9CA3AF]">{f.assigned_name}</span>}
                    </>
                  )}
                  {/* Resize handle */}
                  {isEditable && (
                    <div className="absolute bottom-0 right-0 w-3.5 h-3.5 cursor-se-resize"
                      onMouseDown={(e) => { e.stopPropagation(); startFieldResize(e, f); }}
                      data-testid={`field-resize-${f.field_id}`}>
                      <svg viewBox="0 0 14 14" className="w-full h-full text-[#D4A373]">
                        <path d="M12 2L2 12M12 6L6 12M12 10L10 12" stroke="currentColor" strokeWidth="1.5" fill="none" />
                      </svg>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Pending field preview (click placement) */}
          {pendingField && (
            <div className="absolute z-20"
              style={{ left: pendingField.x, top: pendingField.y }}
              data-testid="pending-field-preview">
              <div className="border-2 border-[#4A5D4E] rounded-lg bg-white shadow-xl p-2.5 w-52"
                onClick={(e) => e.stopPropagation()}>
                <p className="text-[10px] font-medium text-[#1C1F1D] mb-1.5">{t('newSignatureField')}</p>
                <Input value={fieldLabel} onChange={(e) => setFieldLabel(e.target.value)}
                  className="text-xs h-7 mb-2" placeholder={t('labelPlaceholder')}
                  data-testid="pending-field-label" />
                <div className="flex gap-1.5">
                  <Button size="sm" onClick={confirmField}
                    className="flex-1 h-6 text-[9px] bg-[#4A5D4E] hover:bg-[#3E4E42] text-white"
                    data-testid="confirm-place-field">
                    <Plus className="w-2.5 h-2.5 mr-0.5" />{t('place')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={cancelField}
                    className="h-6 text-[9px] px-2" data-testid="cancel-place-field">
                    <X className="w-2.5 h-2.5" />
                  </Button>
                </div>
                <p className="text-[8px] text-[#9CA3AF] mt-1">Pos: {pendingField.x}, {pendingField.y} | {t('pageLabel')} {page}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
