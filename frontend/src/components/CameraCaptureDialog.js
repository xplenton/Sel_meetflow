import { useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Camera, RotateCcw, Check, AlertTriangle, Loader2, X } from 'lucide-react';

/**
 * Camera capture dialog (iter 309).
 *
 * Opens the user-facing camera via getUserMedia (rear-camera preferred via
 * `facingMode: { ideal: 'environment' }`), shows a live preview with an
 * aspect-ratio frame matching a driver's licence (1.586:1), captures the
 * still as a JPEG Blob and hands it back to the caller through `onCapture`.
 *
 * No quality check happens here — that runs in the parent component on
 * EITHER the camera output OR a file-picker output so both paths share the
 * same downstream pipeline.
 *
 * Falls back to a hidden `<input type="file" capture="environment">` if
 * getUserMedia is unavailable (e.g. http://localhost on some browsers).
 */
export default function CameraCaptureDialog({ open, onClose, onCapture, side = 'front' }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fallbackInputRef = useRef(null);
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setError(null);
    setStarting(true);

    const start = async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error('Kamera-API in diesem Browser nicht verfügbar');
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width:  { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach(t => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
      } catch (e) {
        if (!cancelled) {
          setError(e.message || 'Kamera konnte nicht geöffnet werden');
        }
      } finally {
        if (!cancelled) setStarting(false);
      }
    };
    start();

    return () => {
      cancelled = true;
      const stream = streamRef.current;
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
      }
      streamRef.current = null;
    };
  }, [open]);

  const capture = () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const file = new File([blob], `license-${side}-${Date.now()}.jpg`, { type: 'image/jpeg' });
      onCapture?.(file);
      onClose?.();
    }, 'image/jpeg', 0.92);
  };

  const onFallbackFile = (e) => {
    const f = e.target.files?.[0];
    if (f) { onCapture?.(f); onClose?.(); }
    e.target.value = '';
  };

  const sideLabel = side === 'front' ? 'Vorderseite' : 'Rückseite';

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose?.()}>
      <DialogContent className="max-w-xl w-[calc(100vw-1.5rem)]" data-testid="camera-capture-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Camera className="w-4 h-4" /> Führerschein – {sideLabel} fotografieren
          </DialogTitle>
        </DialogHeader>

        {error ? (
          <div className="space-y-3">
            <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-medium mb-1">Kamera nicht verfügbar</div>
                <div>{error}</div>
                <div className="mt-1 text-amber-800">
                  Du kannst alternativ ein Foto über die System-Kamera deines Geräts machen — wir öffnen sie für dich.
                </div>
              </div>
            </div>
            <input
              ref={fallbackInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={onFallbackFile}
              data-testid="camera-capture-fallback-input"
            />
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={() => onClose?.()} data-testid="camera-capture-cancel">Abbrechen</Button>
              <Button
                onClick={() => fallbackInputRef.current?.click()}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white"
                data-testid="camera-capture-fallback"
              >
                <Camera className="w-4 h-4 mr-1" /> System-Kamera öffnen
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="relative bg-black rounded-lg overflow-hidden" style={{ aspectRatio: '1.586/1' }}>
              <video
                ref={videoRef}
                playsInline
                muted
                className="w-full h-full object-cover"
                data-testid="camera-capture-video"
              />
              {/* Licence-shaped guide frame */}
              <div className="absolute inset-2 sm:inset-4 border-2 border-white/70 rounded-md pointer-events-none" />
              {starting && (
                <div className="absolute inset-0 flex items-center justify-center text-white/80 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin mr-1" /> Kamera startet…
                </div>
              )}
            </div>
            <p className="text-[11px] text-[#6B7280]">
              Tipp: Führerschein flach auf eine helle Unterlage legen, Kamera ruhig halten, Reflektionen vermeiden.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={() => onClose?.()} data-testid="camera-capture-cancel">
                <X className="w-4 h-4 mr-1" /> Abbrechen
              </Button>
              <Button
                onClick={capture}
                disabled={starting}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white"
                data-testid="camera-capture-shoot"
              >
                <Check className="w-4 h-4 mr-1" /> Foto aufnehmen
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Tiny preview component for a captured image with a "retake" affordance.
 * Lives here so the caller doesn't have to know about File preview URLs.
 */
export function CapturedPreview({ file, onRetake }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    if (!file) return undefined;
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  if (!url) return null;
  return (
    <div className="relative">
      <img src={url} alt="" className="w-full rounded-md max-h-48 object-cover" />
      <Button size="sm" variant="outline" onClick={onRetake}
        className="absolute top-2 right-2 bg-white/90"
        data-testid="captured-preview-retake">
        <RotateCcw className="w-3 h-3 mr-1" /> Neu
      </Button>
    </div>
  );
}
