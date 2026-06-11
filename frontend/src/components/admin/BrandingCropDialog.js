/**
 * Iter 320 — Klinik-Branding Crop-Dialog (Thema 3a).
 *
 * Before uploading the Virtual-Background image, let the admin choose
 * which part of the picture is visible (zoom + pan in a 16:9 frame).
 * Avoids the "image is cropped" UX surprise when the rendered virtual
 * background only shows a slice of the original.
 *
 * The dialog renders the chosen crop onto a canvas (max 1920×1080) and
 * returns a Blob to the parent so the existing upload flow keeps
 * working — no backend changes required.
 */
import { useCallback, useState } from 'react';
import Cropper from 'react-easy-crop';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Slider } from '../ui/slider';
import { Loader2, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

const DEFAULT_ASPECT = 16 / 9;
const DEFAULT_W = 1920;
const DEFAULT_H = 1080;

async function _renderCroppedImage(imageSrc, cropPx, targetW, targetH) {
  const img = await new Promise((resolve, reject) => {
    const im = new Image();
    im.crossOrigin = 'anonymous';
    im.onload = () => resolve(im);
    im.onerror = reject;
    im.src = imageSrc;
  });
  const canvas = document.createElement('canvas');
  canvas.width = targetW;
  canvas.height = targetH;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(
    img,
    cropPx.x, cropPx.y, cropPx.width, cropPx.height,
    0, 0, targetW, targetH,
  );
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.92);
  });
}

export default function BrandingCropDialog({
  open, onClose, file, onConfirm,
  aspect = DEFAULT_ASPECT,
  targetWidth = DEFAULT_W,
  targetHeight = DEFAULT_H,
  title = 'Bildausschnitt wählen',
  description = 'Ziehe das Bild zum Verschieben, nutze den Slider zum Zoomen. Der gewählte Ausschnitt wird als Klinik-Hintergrund gespeichert.',
}) {
  const [imageSrc, setImageSrc] = useState(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedPx, setCroppedPx] = useState(null);
  const [busy, setBusy] = useState(false);

  // Load file → data-URL when the dialog opens with a fresh file
  if (file && !imageSrc && open) {
    const reader = new FileReader();
    reader.onload = (e) => setImageSrc(e.target?.result || null);
    reader.readAsDataURL(file);
  }

  const onCropComplete = useCallback((_, areaPx) => setCroppedPx(areaPx), []);

  const handleConfirm = async () => {
    if (!imageSrc || !croppedPx) return;
    setBusy(true);
    try {
      const blob = await _renderCroppedImage(imageSrc, croppedPx, targetWidth, targetHeight);
      const cropped = new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), { type: 'image/jpeg' });
      await onConfirm(cropped);
      // Reset state before closing so the next dialog open starts fresh
      setImageSrc(null);
      setCrop({ x: 0, y: 0 });
      setZoom(1);
      setCroppedPx(null);
    } finally {
      setBusy(false);
    }
  };

  const handleClose = () => {
    setImageSrc(null);
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setCroppedPx(null);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent className="max-w-3xl" data-testid="branding-crop-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold text-[#1C1F1D]">
            {title}
          </DialogTitle>
          <p className="text-xs text-[#6B7280] mt-1">
            {description}
          </p>
        </DialogHeader>

        <div className="relative w-full bg-[#1C1F1D] rounded-xl overflow-hidden" style={{ aspectRatio: `${aspect}` }}>
          {imageSrc ? (
            <Cropper
              image={imageSrc}
              crop={crop}
              zoom={zoom}
              aspect={aspect}
              onCropChange={setCrop}
              onZoomChange={setZoom}
              onCropComplete={onCropComplete}
              objectFit="contain"
              restrictPosition={false}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-[#9CA3AF] text-sm">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Bild wird geladen…
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 pt-2">
          <ZoomOut className="w-4 h-4 text-[#6B7280] shrink-0" />
          <Slider
            value={[zoom]}
            min={1}
            max={5}
            step={0.05}
            onValueChange={(v) => setZoom(v[0])}
            className="flex-1"
            data-testid="branding-crop-zoom"
          />
          <ZoomIn className="w-4 h-4 text-[#6B7280] shrink-0" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setZoom(1); setCrop({ x: 0, y: 0 }); }}
            className="h-8 text-xs border-[#E2E4E0] text-[#6B7280] hover:bg-[#F3F4F1]"
            data-testid="branding-crop-reset"
          >
            <RotateCcw className="w-3 h-3 mr-1" /> Zurücksetzen
          </Button>
        </div>

        <DialogFooter className="gap-2 pt-2">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={busy}
            className="border-[#E2E4E0] text-[#6B7280]"
            data-testid="branding-crop-cancel"
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={busy || !croppedPx}
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white"
            data-testid="branding-crop-confirm"
          >
            {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            Ausschnitt übernehmen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
