import { useState, useEffect, useRef, useCallback } from 'react';
import { FileText, Image as ImageIcon } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const THUMB_WIDTH = 120;
const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'webp'];

// Simple in-memory cache for thumbnail data URLs
const thumbCache = new Map();

function getCacheKey(meetingId, docId) {
  return `${meetingId}_${docId}`;
}

export default function DocThumbnail({ meetingId, docId, fileExt, filename }) {
  const [imgSrc, setImgSrc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const mountedRef = useRef(true);

  const isImage = IMAGE_EXTS.includes(fileExt);
  const isPdf = fileExt === 'pdf';
  const cacheKey = getCacheKey(meetingId, docId);

  const generateThumbnail = useCallback(async () => {
    if (thumbCache.has(cacheKey)) {
      setImgSrc(thumbCache.get(cacheKey));
      setLoading(false);
      return;
    }

    try {
      // Use native fetch to avoid axios interceptor issues with arraybuffer
      const resp = await fetch(
        `${API_URL}/api/meetings/${meetingId}/documents/${docId}/view`,
        { credentials: 'include' }
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      if (!mountedRef.current) return;

      const buffer = await resp.arrayBuffer();
      if (!mountedRef.current) return;

      if (isImage) {
        const blob = new Blob([buffer]);
        const url = URL.createObjectURL(blob);
        thumbCache.set(cacheKey, url);
        setImgSrc(url);
        setLoading(false);
      } else if (isPdf) {
        const pdfjsLib = await import('pdfjs-dist');
        pdfjsLib.GlobalWorkerOptions.workerSrc =
          'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

        const pdf = await pdfjsLib.getDocument({ data: buffer.slice(0) }).promise;
        const page = await pdf.getPage(1);

        const viewport = page.getViewport({ scale: 1 });
        const scale = THUMB_WIDTH / viewport.width;
        const scaledVP = page.getViewport({ scale });

        const offCanvas = document.createElement('canvas');
        offCanvas.width = scaledVP.width;
        offCanvas.height = scaledVP.height;
        const ctx = offCanvas.getContext('2d');

        await page.render({ canvasContext: ctx, viewport: scaledVP }).promise;

        if (!mountedRef.current) return;

        const dataUrl = offCanvas.toDataURL('image/jpeg', 0.7);
        thumbCache.set(cacheKey, dataUrl);
        setImgSrc(dataUrl);
        setLoading(false);
      } else {
        setLoading(false);
        setError(true);
      }
    } catch {
      if (mountedRef.current) {
        setLoading(false);
        setError(true);
      }
    }
  }, [meetingId, docId, isImage, isPdf, cacheKey]);

  useEffect(() => {
    mountedRef.current = true;
    generateThumbnail();
    return () => { mountedRef.current = false; };
  }, [generateThumbnail]);

  // Fallback icon for unsupported types or errors
  if (error || (!isPdf && !isImage)) {
    const Icon = isImage ? ImageIcon : FileText;
    return (
      <div
        className="w-full h-full flex items-center justify-center bg-[#F3F4F1] rounded"
        data-testid={`doc-thumbnail-fallback-${docId}`}
      >
        <Icon className="w-6 h-6 text-[#9CA3AF]" />
      </div>
    );
  }

  if (loading) {
    return (
      <div
        className="w-full h-full flex items-center justify-center bg-[#F3F4F1] rounded animate-pulse"
        data-testid={`doc-thumbnail-loading-${docId}`}
      >
        <div className="w-6 h-6 rounded bg-[#E2E4E0]" />
      </div>
    );
  }

  return (
    <div
      className="w-full h-full rounded overflow-hidden bg-[#F3F4F1]"
      data-testid={`doc-thumbnail-${docId}`}
    >
      <img
        src={imgSrc}
        alt={`Vorschau: ${filename}`}
        className="w-full h-full object-cover"
        loading="lazy"
      />
    </div>
  );
}
