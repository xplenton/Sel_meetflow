/**
 * Client-side image quality checks for driver's licence uploads (iter 309).
 *
 * Runs in the browser against a File/Blob and returns a structured report
 * the UI can show before triggering the upload. Cheap (<100 ms on a 4 MP
 * picture) — uses a downsampled canvas to keep things responsive on mobile.
 *
 * Four checks performed:
 *   1. Resolution     — at least 1024×768
 *   2. Sharpness      — Laplacian variance on grayscale; below 60 is blurry
 *   3. Brightness     — mean luminance; outside 50..210 is too dark / too bright
 *   4. Orientation    — driver's licences are landscape (width > height)
 *
 * Returns `{ ok, issues: [{ key, label, severity }], stats: {...} }`.
 *   - `ok` is true when there are no `severity:'error'` issues.
 *   - `severity:'warn'` issues are shown but the user can still continue.
 */

const MIN_W = 1024;
const MIN_H = 768;
const MIN_SHARPNESS = 60;       // Laplacian variance
const BRIGHTNESS_MIN = 50;
const BRIGHTNESS_MAX = 210;

function readImageBitmap(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = (e) => { URL.revokeObjectURL(url); reject(e); };
    img.src = url;
  });
}

function downsampleToGrayscale(img, targetWidth = 320) {
  // Downsample to keep the Laplacian/brightness pass cheap on mobile.
  const scale = Math.min(1, targetWidth / img.width);
  const w = Math.max(32, Math.round(img.width * scale));
  const h = Math.max(32, Math.round(img.height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);
  // ITU-R BT.601 luma
  const gray = new Uint8ClampedArray(w * h);
  for (let i = 0, j = 0; i < data.length; i += 4, j++) {
    gray[j] = (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114) | 0;
  }
  return { gray, w, h };
}

function meanBrightness(gray) {
  let sum = 0;
  for (let i = 0; i < gray.length; i++) sum += gray[i];
  return sum / gray.length;
}

function laplacianVariance(gray, w, h) {
  // 3x3 Laplacian kernel: [[0,1,0],[1,-4,1],[0,1,0]]
  // Skip the 1-pixel border to keep things simple.
  let n = 0, sum = 0, sumSq = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const c = gray[y * w + x];
      const l = (
        gray[(y - 1) * w + x] +
        gray[(y + 1) * w + x] +
        gray[y * w + (x - 1)] +
        gray[y * w + (x + 1)] -
        4 * c
      );
      sum += l;
      sumSq += l * l;
      n++;
    }
  }
  const mean = sum / n;
  return sumSq / n - mean * mean;
}

export async function analyzeLicensePhoto(file) {
  const img = await readImageBitmap(file);
  const { gray, w, h } = downsampleToGrayscale(img);
  const brightness = meanBrightness(gray);
  const sharpness = laplacianVariance(gray, w, h);
  const issues = [];

  if (img.width < MIN_W || img.height < MIN_H) {
    issues.push({
      key: 'resolution',
      severity: 'error',
      label: `Auflösung zu niedrig: ${img.width}×${img.height} (mindestens ${MIN_W}×${MIN_H} empfohlen)`,
    });
  }
  if (sharpness < MIN_SHARPNESS) {
    issues.push({
      key: 'sharpness',
      severity: 'warn',
      label: `Bild wirkt verschwommen — bitte Kamera ruhig halten und auf den Führerschein fokussieren`,
    });
  }
  if (brightness < BRIGHTNESS_MIN) {
    issues.push({
      key: 'brightness-low',
      severity: 'warn',
      label: `Bild zu dunkel — bitte für gleichmäßiges Licht sorgen`,
    });
  } else if (brightness > BRIGHTNESS_MAX) {
    issues.push({
      key: 'brightness-high',
      severity: 'warn',
      label: `Bild überbelichtet — bitte direktes Blitzlicht / Reflektionen vermeiden`,
    });
  }
  if (img.width <= img.height) {
    issues.push({
      key: 'orientation',
      severity: 'warn',
      label: `Querformat empfohlen — der Führerschein ist breiter als hoch`,
    });
  }

  return {
    ok: !issues.some(i => i.severity === 'error'),
    issues,
    stats: {
      width: img.width,
      height: img.height,
      brightness: Math.round(brightness),
      sharpness: Math.round(sharpness),
    },
  };
}
