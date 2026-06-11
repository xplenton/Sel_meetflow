import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { applyBrandingVars } from '../lib/branding';

const BrandingContext = createContext(null);

const DEFAULT_BRANDING = {
  company_name: 'MeetFlow',
  primary_color: '#4A5D4E',
  logo_url: '',
  email_footer: 'Sent via MeetFlow',
  favicon_url: '',
};

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING);

  const fetchBranding = useCallback(async () => {
    try {
      const { data } = await api.get('/organization/branding');
      const merged = { ...DEFAULT_BRANDING, ...data };
      setBranding(merged);
      applyBrandingVars(merged.primary_color);
      if (merged.favicon_url) {
        let link = document.querySelector("link[rel~='icon']");
        if (!link) {
          link = document.createElement('link');
          link.rel = 'icon';
          document.head.appendChild(link);
        }
        link.href = merged.favicon_url;
      }
      if (merged.company_name && typeof document !== 'undefined') {
        // Prefix document title with org name for recognizability
        const base = document.title.split(' — ')[0];
        document.title = `${base} — ${merged.company_name}`;
      }
    } catch { /* best-effort */ }
  }, []);

  // Live-preview: let the admin BrandingSettings call this without a
  // save round-trip to see colour changes immediately. Not persisted.
  const previewBranding = useCallback((patch) => {
    setBranding(prev => {
      const next = { ...prev, ...patch };
      if (patch.primary_color) applyBrandingVars(next.primary_color);
      return next;
    });
  }, []);

  useEffect(() => { fetchBranding(); }, [fetchBranding]);

  // Apply brand vars also on initial default, so `--brand-primary`
  // resolves even before the first fetch completes.
  useEffect(() => { applyBrandingVars(DEFAULT_BRANDING.primary_color); }, []);

  return (
    <BrandingContext.Provider value={{ branding, refreshBranding: fetchBranding, previewBranding }}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() { return useContext(BrandingContext); }
