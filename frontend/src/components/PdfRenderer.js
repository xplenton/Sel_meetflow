import { useState, useEffect, useRef, useCallback, memo } from 'react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Cache PDF data to avoid re-fetching
const pdfCache = new Map();

const PdfRenderer = memo(function PdfRenderer({ meetingId, docId, page, className, onPageCount }) {
  const canvasRef = useRef(null);
  const [error, setError] = useState(false);
  const renderTask = useRef(null);
  const onPageCountRef = useRef(onPageCount);
  onPageCountRef.current = onPageCount;

  const cacheKey = `${meetingId}_${docId}`;

  const renderPage = useCallback(async () => {
    try {
      let buffer;
      if (pdfCache.has(cacheKey)) {
        buffer = pdfCache.get(cacheKey);
      } else {
        const resp = await fetch(
          `${API_URL}/api/meetings/${meetingId}/documents/${docId}/view`,
          { credentials: 'include' }
        );
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        buffer = await resp.arrayBuffer();
        pdfCache.set(cacheKey, buffer);
      }

      const pdfjsLib = await import('pdfjs-dist');
      pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js`;

      const pdf = await pdfjsLib.getDocument({ data: buffer.slice(0) }).promise;
      if (onPageCountRef.current) onPageCountRef.current(pdf.numPages);

      const pageNum = Math.min(page || 1, pdf.numPages);
      const pdfPage = await pdf.getPage(pageNum);

      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');

      const viewport = pdfPage.getViewport({ scale: 1 });
      const targetWidth = 800;
      const scale = targetWidth / viewport.width;
      const scaledViewport = pdfPage.getViewport({ scale });

      canvas.width = scaledViewport.width;
      canvas.height = scaledViewport.height;
      canvas.style.width = scaledViewport.width + 'px';
      canvas.style.height = scaledViewport.height + 'px';

      if (renderTask.current) {
        try { renderTask.current.cancel(); } catch {}
      }

      renderTask.current = pdfPage.render({
        canvasContext: ctx,
        viewport: scaledViewport,
      });
      await renderTask.current.promise;
      setError(false);
    } catch (err) {
      if (err?.name !== 'RenderingCancelledException') {
        console.error('PDF render error:', err);
        setError(true);
      }
    }
  }, [meetingId, docId, page, cacheKey]);

  useEffect(() => {
    renderPage();
    return () => {
      if (renderTask.current) {
        try { renderTask.current.cancel(); } catch {}
      }
    };
  }, [renderPage]);

  if (error) {
    return (
      <div className={`flex items-center justify-center bg-white rounded-lg ${className || ''}`}
        style={{ width: 800, height: 600 }}>
        <p className="text-sm text-[#9CA3AF]">PDF konnte nicht gerendert werden</p>
      </div>
    );
  }

  return (
    <canvas ref={canvasRef} className={`rounded-lg bg-white ${className || ''}`}
      data-testid="pdf-canvas" />
  );
});

export default PdfRenderer;
