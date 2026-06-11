/**
 * Branding helpers — hex → HSL conversion + dynamic CSS variable injection.
 *
 * Used by BrandingContext to apply the org's `primary_color` across the
 * whole app via CSS variables. Hard-coded hex classes (`bg-[#4A5D4E]`
 * etc.) are remapped via a dedicated `index.css` layer that references
 * these variables (see `html[data-branded="true"]`).
 */
export function hexToHsl(hex) {
  if (!hex || typeof hex !== 'string') return null;
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  if (h.length !== 6) return null;
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let hue = 0, sat = 0;
  const light = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    sat = light > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: hue = (g - b) / d + (g < b ? 6 : 0); break;
      case g: hue = (b - r) / d + 2; break;
      default: hue = (r - g) / d + 4;
    }
    hue /= 6;
  }
  return {
    h: Math.round(hue * 360),
    s: Math.round(sat * 100),
    l: Math.round(light * 100),
  };
}

/** Lighten/darken by delta percentage points on lightness. */
function adjustL(hsl, delta) {
  if (!hsl) return null;
  const l = Math.max(0, Math.min(100, hsl.l + delta));
  return { ...hsl, l };
}

/** Pick white or near-black as foreground based on background lightness. */
function foregroundFor(hsl) {
  if (!hsl) return '#FFFFFF';
  return hsl.l > 55 ? '#1C1F1D' : '#FFFFFF';
}

export function applyBrandingVars(primaryHex) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const hsl = hexToHsl(primaryHex);
  if (!hsl) {
    root.removeAttribute('data-branded');
    return;
  }
  root.style.setProperty('--brand-primary', primaryHex);
  root.style.setProperty('--brand-primary-hover', hslString(adjustL(hsl, -6)));
  root.style.setProperty('--brand-primary-soft', hslString(adjustL(hsl, +45), 0.12));
  root.style.setProperty('--brand-primary-fg', foregroundFor(hsl));
  // Override Shadcn primary HSL tokens so <Button variant="default"> etc.
  // pick up the brand color automatically.
  root.style.setProperty('--primary', `${hsl.h} ${hsl.s}% ${hsl.l}%`);
  root.style.setProperty('--primary-foreground', hsl.l > 55 ? '150 6% 12%' : '0 0% 100%');
  root.style.setProperty('--ring', `${hsl.h} ${hsl.s}% ${hsl.l}%`);
  root.setAttribute('data-branded', 'true');
}

function hslString(hsl, alpha) {
  if (!hsl) return '';
  if (alpha != null) return `hsla(${hsl.h}, ${hsl.s}%, ${hsl.l}%, ${alpha})`;
  return `hsl(${hsl.h}, ${hsl.s}%, ${hsl.l}%)`;
}
