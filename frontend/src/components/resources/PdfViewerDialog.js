/**
 * Iter 362 — In-App PDF-Viewer Dialog (Mobile-First).
 *
 * Wird per CustomEvent `mf:open-pdf` von `lib/authedDownload.js` getriggert
 * — der User sieht die Rechnung direkt im Tab statt über das OS-Share-Sheet
 * oder den Download-Manager-Umweg. Auf Desktop wird der Viewer ebenfalls
 * benutzt, falls ein Aufrufer explizit `forceInAppViewer: true` mitsendet.
 *
 * Features:
 *   • Sheet-Layout voll-bildschirm auf Mobile, Modal auf ≥ md
 *   • Page-Navigation (← / →) + „Seite X / Y"
 *   • Zoom −/+ (50–200 %)
 *   • Download-Button (Share-Sheet/Speichern via <a download>)
 *   • Schließen via Top-Bar oder Tap außerhalb
 *
 * Worker-Setup: pdfjs-Worker liegt unter `/pdf.worker.min.js` (lokal
 * gehostet, da CSP `script-src` externe CDNs blockiert).
 */
import { useEffect, useState, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { Button } from '../ui/button';
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download as DownloadIcon, Loader2 } from 'lucide-react';

pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';

export default function PdfViewerDialog({ blob, filename, onClose }) {
  const [numPages, setNumPages] = useState(null);
  const [pageNum, setPageNum] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [pageWidth, setPageWidth] = useState(null);
  const containerRef = useRef(null);

  // Iter 362 — Initial-Breite an Container anpassen, damit die Seite die
  // verfügbare Breite nutzt. Zoom-Buttons multiplizieren danach scale.
  useEffect(() => {
    if (containerRef.current) {
      // 32 px Padding-Abzug
      setPageWidth(Math.min(containerRef.current.clientWidth - 24, 900));
    }
    const onResize = () => {
      if (containerRef.current) {
        setPageWidth(Math.min(containerRef.current.clientWidth - 24, 900));
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // ESC zum Schließen
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight' && numPages && pageNum < numPages) setPageNum(p => p + 1);
      else if (e.key === 'ArrowLeft' && pageNum > 1) setPageNum(p => p - 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pageNum, numPages, onClose]);

  // Body-Scroll sperren, solange Viewer offen
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  const onDownload = () => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'rechnung.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  };

  return (
    <div
      className="fixed inset-0 z-[200] bg-black/70 flex items-stretch md:items-center md:justify-center md:p-6"
      onClick={onClose}
      data-testid="pdf-viewer-backdrop"
    >
      <div
        className="bg-[#F8F8F6] w-full md:max-w-4xl md:h-[90vh] md:rounded-lg overflow-hidden flex flex-col shadow-xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="pdf-viewer-dialog"
      >
        {/* Top-Bar */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-[#E2E4E0] bg-white">
          <Button size="sm" variant="ghost" onClick={onClose}
                  data-testid="pdf-viewer-close" className="h-9 w-9 p-0">
            <X className="w-4 h-4" />
          </Button>
          <div className="text-xs font-medium text-[#1C1F1D] truncate flex-1 min-w-0">
            {filename || 'Rechnung.pdf'}
          </div>
          <Button size="sm" variant="ghost" onClick={onDownload}
                  data-testid="pdf-viewer-download" className="h-9 px-2">
            <DownloadIcon className="w-4 h-4 sm:mr-1" />
            <span className="hidden sm:inline text-xs">Speichern</span>
          </Button>
        </div>

        {/* PDF-Bereich */}
        <div
          ref={containerRef}
          className="flex-1 overflow-auto bg-[#2C2E2A] flex justify-center px-3 py-4"
          data-testid="pdf-viewer-canvas-wrapper"
        >
          <Document
            file={blob}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            loading={
              <div className="flex flex-col items-center justify-center text-white py-12 gap-2">
                <Loader2 className="w-6 h-6 animate-spin" />
                <div className="text-xs">PDF wird geladen…</div>
              </div>
            }
            error={
              <div className="text-rose-400 text-sm py-12" data-testid="pdf-viewer-error">
                PDF konnte nicht angezeigt werden.
              </div>
            }
            data-testid="pdf-viewer-document"
          >
            {pageWidth && (
              <Page
                pageNumber={pageNum}
                width={pageWidth * scale}
                renderTextLayer={false}
                renderAnnotationLayer={false}
                className="shadow-lg"
                data-testid={`pdf-viewer-page-${pageNum}`}
              />
            )}
          </Document>
        </div>

        {/* Footer-Controls */}
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-t border-[#E2E4E0] bg-white">
          <div className="flex items-center gap-1">
            <Button
              size="sm" variant="outline"
              onClick={() => setPageNum(p => Math.max(1, p - 1))}
              disabled={pageNum <= 1}
              data-testid="pdf-viewer-prev"
              className="h-9 w-9 p-0"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <div className="text-xs tabular-nums px-2 min-w-[60px] text-center"
                 data-testid="pdf-viewer-page-indicator">
              {numPages ? `${pageNum} / ${numPages}` : '— / —'}
            </div>
            <Button
              size="sm" variant="outline"
              onClick={() => setPageNum(p => Math.min(numPages || p, p + 1))}
              disabled={!numPages || pageNum >= numPages}
              data-testid="pdf-viewer-next"
              className="h-9 w-9 p-0"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>

          <div className="flex items-center gap-1">
            <Button
              size="sm" variant="outline"
              onClick={() => setScale(s => Math.max(0.5, Math.round((s - 0.25) * 100) / 100))}
              disabled={scale <= 0.5}
              data-testid="pdf-viewer-zoom-out"
              className="h-9 w-9 p-0"
            >
              <ZoomOut className="w-4 h-4" />
            </Button>
            <div className="text-xs tabular-nums px-1 min-w-[44px] text-center"
                 data-testid="pdf-viewer-zoom-indicator">
              {Math.round(scale * 100)}%
            </div>
            <Button
              size="sm" variant="outline"
              onClick={() => setScale(s => Math.min(2.0, Math.round((s + 0.25) * 100) / 100))}
              disabled={scale >= 2.0}
              data-testid="pdf-viewer-zoom-in"
              className="h-9 w-9 p-0"
            >
              <ZoomIn className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
