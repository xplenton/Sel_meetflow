/**
 * Iter 322 — Auth-aware PDF/file download helpers.
 *
 * The naive pattern `window.open(${BACKEND}/api/...)` opens a new tab WITHOUT
 * the JWT Authorization header — every protected endpoint returns 401, so
 * the user sees a blank tab. These helpers fetch the file through the same
 * `api` axios instance (which injects the token), then open the blob in a
 * new tab via `URL.createObjectURL`.
 *
 * Usage:
 *   await openAuthedFile('/resource-bookings/invoices/aggregate.pdf', { from_date, to_date });
 *   await downloadAuthedFile('/resource-bookings/export/erp.csv', { format: 'datev' }, 'export.csv');
 */
import api from './api';
import { toast } from 'sonner';

/**
 * Fetch a binary file via authenticated API and open it in a new tab.
 * The blob URL is auto-revoked after 60 s.
 *
 * Iter 361 — Mobile-Strategie:
 *   • iOS Safari / Android Chrome blockieren `window.open()` nach einem
 *     `await`, weil die User-Gesture verloren geht. `<a download>` dagegen
 *     funktioniert auch nach async-Code, weil es das Save-Sheet bzw. den
 *     Download-Manager des OS aufruft (kein Popup).
 *   • Desktop-Browser zeigen PDFs lieber inline → wir öffnen weiterhin einen
 *     synchron erzeugten Tab und navigieren ihn nach dem Fetch zur Blob-URL.
 *   • Mobile-Erkennung via `pointer: coarse` (Touch-only Geräte). Das ist
 *     sauberer als UA-Sniffing und greift auch bei Tablets / iPadOS.
 */
function _isCoarsePointer() {
  try {
    return window.matchMedia?.('(pointer: coarse)')?.matches === true;
  } catch { return false; }
}

function _filenameFromHeaders(headers, path) {
  const cd = headers?.['content-disposition'] || '';
  const m = cd.match(/filename="?([^";]+)"?/i);
  if (m) return m[1];
  return path.split('/').pop() || 'download';
}

export async function openAuthedFile(path, params = {}) {
  const useDownload = _isCoarsePointer();
  // Desktop: Blank-Tab SYNCHRON öffnen, solange noch User-Gesture aktiv ist.
  // Mobile: kein Sync-Tab nötig — wir nutzen In-App-Viewer (PDF) bzw.
  // erzwungenen Download (CSV/XLSX/sonstiges).
  const win = useDownload ? null : window.open('', '_blank');
  try {
    const { data, headers } = await api.get(path, {
      params,
      responseType: 'blob',
    });
    const mime = headers['content-type'] || 'application/octet-stream';
    const blob = new Blob([data], { type: mime });
    const filename = _filenameFromHeaders(headers, path);
    const isPdf = mime.toLowerCase().includes('pdf');

    if (useDownload) {
      if (isPdf) {
        // Iter 362 — In-App-PDF-Viewer auf Mobile statt Share-Sheet/Download.
        // `PdfViewerHost` ist in App.js gemountet und lauscht auf dieses Event.
        try {
          window.dispatchEvent(new CustomEvent('mf:open-pdf', {
            detail: { blob, filename },
          }));
          // Blob bleibt im Viewer leben; kein revoke nötig.
          return true;
        } catch {
          // Fallback: regulärer Download, falls Event-API fehlt.
        }
      }
      // Mobile + Nicht-PDF (CSV/XLSX) → erzwungener Download via <a download>.
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } else if (win && !win.closed) {
      // Desktop-Happy-Path: Tab wurde geöffnet, jetzt zur Blob-URL navigieren.
      const url = URL.createObjectURL(blob);
      win.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } else {
      // Desktop, aber Popup-Blocker hat zugeschlagen → Download-Fallback.
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    }
    return true;
  } catch (e) {
    if (win && !win.closed) win.close();
    let detail = null;
    try {
      if (e.response?.data && e.response.data instanceof Blob) {
        const text = await e.response.data.text();
        try { detail = JSON.parse(text)?.detail; } catch { detail = text; }
      } else {
        detail = e.response?.data?.detail;
      }
    } catch { /* ignore */ }
    const msg = e.response?.status === 401
      ? 'Nicht authentifiziert. Bitte erneut anmelden.'
      : (detail || 'Datei konnte nicht geladen werden');
    toast.error(msg);
    return false;
  }
}

/**
 * Same as `openAuthedFile` but forces a `Save As` download with the given
 * filename, even if the browser would normally render the file inline.
 */
export async function downloadAuthedFile(path, params = {}, filename = 'download') {
  try {
    const { data, headers } = await api.get(path, {
      params,
      responseType: 'blob',
    });
    const mime = headers['content-type'] || 'application/octet-stream';
    const blob = new Blob([data], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return true;
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Datei konnte nicht geladen werden');
    return false;
  }
}
