import { useEffect, useRef, useCallback, useState } from 'react';
import { SelfieSegmentation } from '@mediapipe/selfie_segmentation';

const BG_IMAGES = {
  office: 'https://images.unsplash.com/photo-1497366216548-37526070297c?w=1920&q=90',
  nature: 'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1920&q=90',
  abstract: 'https://images.unsplash.com/photo-1557682250-33bd709cbe85?w=1920&q=90',
  library: 'https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=1920&q=90',
};

export default function VirtualBgCanvas({ stream, bgType, bgUrl, className, style, mirrored = true, onCanvasReady, onPainting }) {
  const canvasRef = useRef(null);
  const maskCanvasRef = useRef(null);
  const videoRef = useRef(null);
  const segRef = useRef(null);
  const bgImageRef = useRef(null);
  const bgTypeRef = useRef(bgType);
  const animRef = useRef(null);
  const paintedRef = useRef(false);
  const onPaintingRef = useRef(onPainting);
  const [ready, setReady] = useState(false);

  bgTypeRef.current = bgType;
  onPaintingRef.current = onPainting;

  // iter 190 — expose the canvas element to the parent as soon as it exists,
  // so the parent can call `canvas.captureStream(30)` and publish that via
  // LiveKit. Without this the virtual background was only painted locally,
  // remote participants kept seeing the raw camera feed.
  useEffect(() => {
    if (canvasRef.current && onCanvasReady) {
      onCanvasReady(canvasRef.current);
    }
    return () => {
      if (onCanvasReady) onCanvasReady(null);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Preload background image at high quality
  useEffect(() => {
    // iter 191 — `bgUrl` takes precedence over the BG_IMAGES lookup so the
    // clinic's custom "official" background (uploaded via /admin/branding)
    // is honored across every Live-Meeting.
    const url = bgUrl || BG_IMAGES[bgType];
    if (url) {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => { bgImageRef.current = img; };
      img.onerror = () => { bgImageRef.current = null; };
      img.src = url;
    } else {
      bgImageRef.current = null;
    }
  }, [bgType, bgUrl]);

  // Create offscreen mask canvas for edge smoothing
  useEffect(() => {
    maskCanvasRef.current = document.createElement('canvas');
  }, []);

  const onResults = useCallback((results) => {
    const canvas = canvasRef.current;
    const maskCanvas = maskCanvasRef.current;
    if (!canvas || !maskCanvas) return;

    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    // Configure high-quality rendering
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // --- Step 1: Smooth the segmentation mask on offscreen canvas ---
    maskCanvas.width = w;
    maskCanvas.height = h;
    const maskCtx = maskCanvas.getContext('2d');
    maskCtx.imageSmoothingEnabled = true;
    maskCtx.imageSmoothingQuality = 'high';

    // Draw mask, then apply a light blur for soft edges
    maskCtx.clearRect(0, 0, w, h);
    maskCtx.filter = 'blur(4px)';
    maskCtx.drawImage(results.segmentationMask, 0, 0, w, h);
    maskCtx.filter = 'none';

    // Slightly boost contrast of the blurred mask to tighten the edge
    maskCtx.globalCompositeOperation = 'source-atop';
    maskCtx.filter = 'contrast(1.6) brightness(1.1)';
    maskCtx.drawImage(maskCanvas, 0, 0);
    maskCtx.filter = 'none';
    maskCtx.globalCompositeOperation = 'source-over';

    // --- Step 2: Composite final output ---
    ctx.save();
    ctx.clearRect(0, 0, w, h);

    if (mirrored) {
      ctx.translate(w, 0);
      ctx.scale(-1, 1);
    }

    // Draw the smoothed mask
    ctx.drawImage(maskCanvas, 0, 0, w, h);

    // Draw person (source-in: keep only where mask is opaque)
    ctx.globalCompositeOperation = 'source-in';
    ctx.drawImage(results.image, 0, 0, w, h);

    // Draw background behind person (destination-over: fill transparent areas)
    ctx.globalCompositeOperation = 'destination-over';

    const currentBg = bgTypeRef.current;
    if (currentBg === 'blur') {
      // Blur the original camera frame as background
      ctx.filter = 'blur(14px) saturate(1.1)';
      ctx.drawImage(results.image, 0, 0, w, h);
      ctx.filter = 'none';
    } else if (bgImageRef.current) {
      // Draw high-res background image with cover fit
      const img = bgImageRef.current;
      const imgRatio = img.naturalWidth / img.naturalHeight;
      const canvasRatio = w / h;
      let sx = 0, sy = 0, sw = img.naturalWidth, sh = img.naturalHeight;
      if (imgRatio > canvasRatio) {
        sw = img.naturalHeight * canvasRatio;
        sx = (img.naturalWidth - sw) / 2;
      } else {
        sh = img.naturalWidth / canvasRatio;
        sy = (img.naturalHeight - sh) / 2;
      }
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, w, h);
    } else {
      // Fallback solid color
      ctx.fillStyle = '#1A1D1B';
      ctx.fillRect(0, 0, w, h);
    }

    ctx.restore();

    // iter 206 — fire `onPainting` exactly once, after the first composited
    // frame is drawn. The Live-Meeting page waits for this event before
    // capturing the canvas stream so the published track contains real
    // segmented frames from frame 1, not a blank 300×150 placeholder.
    if (!paintedRef.current) {
      paintedRef.current = true;
      try { onPaintingRef.current && onPaintingRef.current(); } catch {}
    }
  }, [mirrored]);

  // Initialize MediaPipe segmentation
  useEffect(() => {
    if (!stream) return;

    paintedRef.current = false;  // iter 206 — re-arm `onPainting` for new stream
    const video = document.createElement('video');
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    video.setAttribute('playsinline', '');
    videoRef.current = video;

    const selfieSegmentation = new SelfieSegmentation({
      locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/selfie_segmentation/${file}`,
    });
    // modelSelection: 0 = general (faster), 1 = landscape (higher quality)
    selfieSegmentation.setOptions({ modelSelection: 1, selfieMode: true });
    selfieSegmentation.onResults(onResults);
    segRef.current = selfieSegmentation;

    video.onloadeddata = () => {
      const canvas = canvasRef.current;
      if (canvas) {
        // Use native video resolution for best quality (min 720p)
        const vw = video.videoWidth || 1280;
        const vh = video.videoHeight || 720;
        canvas.width = Math.max(vw, 1280);
        canvas.height = Math.max(vh, 720);
      }
      setReady(true);
    };
    video.play().catch(() => {});

    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
      try { selfieSegmentation.close(); } catch {}
      video.pause();
      video.srcObject = null;
    };
  }, [stream, onResults]);

  // Frame processing loop
  useEffect(() => {
    if (!ready || !segRef.current || !videoRef.current) return;

    let running = true;
    const processFrame = async () => {
      if (!running) return;
      const video = videoRef.current;
      if (video && video.readyState >= 2 && segRef.current) {
        try {
          await segRef.current.send({ image: video });
        } catch {
          // Model loading or frame skip
        }
      }
      animRef.current = requestAnimationFrame(processFrame);
    };
    processFrame();

    return () => {
      running = false;
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [ready]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ ...style, imageRendering: 'auto' }}
      data-testid="virtual-bg-canvas"
    />
  );
}
