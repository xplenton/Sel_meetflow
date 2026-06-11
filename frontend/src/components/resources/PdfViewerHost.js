/**
 * Iter 362 — PDF-Viewer-Host: einmaliger globaler Listener für
 * `mf:open-pdf`-CustomEvent (dispatcht von lib/authedDownload.js).
 *
 * Lazy-loaded, damit das ~1 MB pdf.js-Bundle nicht im Initial-Chunk landet.
 *
 * Erwartet Event-Detail: { blob: Blob, filename?: string }
 */
import { useEffect, useState, lazy, Suspense } from 'react';

const PdfViewerDialog = lazy(() => import('./PdfViewerDialog'));

export default function PdfViewerHost() {
  const [payload, setPayload] = useState(null);   // { blob, filename } | null

  useEffect(() => {
    const onOpen = (e) => {
      const { blob, filename } = e.detail || {};
      if (!(blob instanceof Blob)) return;
      setPayload({ blob, filename });
    };
    window.addEventListener('mf:open-pdf', onOpen);
    return () => window.removeEventListener('mf:open-pdf', onOpen);
  }, []);

  if (!payload) return null;

  return (
    <Suspense fallback={null}>
      <PdfViewerDialog
        blob={payload.blob}
        filename={payload.filename}
        onClose={() => setPayload(null)}
      />
    </Suspense>
  );
}
