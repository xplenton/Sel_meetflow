import { useState, useEffect, useCallback, useRef } from 'react';
import { useLanguage } from '../contexts/LanguageContext';
import { useBranding } from '../contexts/BrandingContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Video, Upload, Save, RotateCcw, Eye, Crop } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import BrandingCropDialog from './admin/BrandingCropDialog';

export default function BrandingSettings() {
  const { t } = useLanguage();
  const { refreshBranding, previewBranding } = useBranding();
  const [branding, setBranding] = useState({
    company_name: 'MeetFlow', primary_color: '#4A5D4E',
    logo_url: '', email_footer: 'Sent via MeetFlow', favicon_url: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [pendingLogo, setPendingLogo] = useState(null);
  const [cropOpen, setCropOpen] = useState(false);
  const logoInputRef = useRef(null);

  const fetchBranding = useCallback(async () => {
    try {
      const { data } = await api.get('/organization/branding');
      setBranding(prev => ({ ...prev, ...data }));
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchBranding(); }, [fetchBranding]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put('/organization/branding', branding);
      await refreshBranding?.();
      toast.success(t('brandingSaved'));
    } catch { toast.error('Failed to save'); }
    finally { setSaving(false); }
  };

  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error('Max 5MB'); return; }
    // Iter 320 — Crop-Dialog vor Upload, damit das Logo nicht abgeschnitten
    // wirkt. Die UI rendert das Logo in einem 28×28-Slot mit object-contain,
    // ein vorab-zugeschnittener Square macht es deutlich klarer lesbar.
    setPendingLogo(file);
    setCropOpen(true);
    if (logoInputRef.current) logoInputRef.current.value = '';
  };

  const uploadCroppedLogo = async (cropped) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', cropped);
      const { data } = await api.post('/organization/branding/logo', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      const newUrl = data?.logo_url || '';
      if (newUrl) {
        setBranding(prev => ({ ...prev, logo_url: newUrl }));
        try {
          await api.put('/organization/branding', { logo_url: newUrl });
        } catch { /* save is best-effort — the upload itself already set it */ }
      }
      toast.success('Logo hochgeladen — sichtbar in der Seitenleiste, im Login und in Emails');
      await refreshBranding?.();
      fetchBranding();
      setCropOpen(false);
      setPendingLogo(null);
    } catch { toast.error('Upload failed'); }
    finally { setUploading(false); }
  };

  const recropExistingLogo = async () => {
    if (!branding.logo_url) return;
    try {
      const fullUrl = branding.logo_url.startsWith('/api/')
        ? `${process.env.REACT_APP_BACKEND_URL}${branding.logo_url}`
        : branding.logo_url;
      const res = await fetch(fullUrl);
      const blob = await res.blob();
      const f = new File([blob], 'logo.jpg', { type: blob.type || 'image/jpeg' });
      setPendingLogo(f);
      setCropOpen(true);
    } catch {
      toast.error('Bestehendes Logo konnte nicht geladen werden');
    }
  };

  const handleReset = () => {
    const defaults = { company_name: 'MeetFlow', primary_color: '#4A5D4E', logo_url: '', email_footer: 'Sent via MeetFlow', favicon_url: '' };
    setBranding(defaults);
    previewBranding?.(defaults);
  };

  const update = (key, val) => {
    setBranding(prev => ({ ...prev, [key]: val }));
    // Live-preview colours + logo immediately without saving
    if (key === 'primary_color' || key === 'logo_url' || key === 'company_name') {
      previewBranding?.({ [key]: val });
    }
  };

  if (loading) return <div className="text-center py-8 text-[#9CA3AF]">Loading...</div>;

  return (
    <div className="space-y-6" data-testid="branding-settings">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Settings */}
        <div className="space-y-5">
          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('companyName')}</Label>
            <Input data-testid="branding-company-name" value={branding.company_name} onChange={e => update('company_name', e.target.value)}
              className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('primaryColor')}</Label>
            <div className="flex gap-3 items-center">
              <input type="color" value={branding.primary_color} onChange={e => update('primary_color', e.target.value)}
                className="w-10 h-10 rounded-lg border border-[#E2E4E0] cursor-pointer" data-testid="branding-color-picker" />
              <Input value={branding.primary_color} onChange={e => update('primary_color', e.target.value)}
                className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl flex-1 font-mono text-sm" data-testid="branding-color-input" />
              <div className="w-10 h-10 rounded-lg" style={{ backgroundColor: branding.primary_color }} />
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('logoUpload')}</Label>
            <div className="flex gap-2">
              <Input data-testid="branding-logo-url" value={branding.logo_url} onChange={e => update('logo_url', e.target.value)}
                placeholder="https://example.com/logo.png" className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl flex-1 text-sm" />
              <input ref={logoInputRef} type="file" accept="image/*" onChange={handleLogoUpload} className="hidden" />
              <Button onClick={() => logoInputRef.current?.click()} variant="outline" size="sm" disabled={uploading}
                className="border-[#E2E4E0] rounded-xl" data-testid="branding-upload-logo">
                <Upload className="w-4 h-4" />
              </Button>
              {branding.logo_url && (
                <Button onClick={recropExistingLogo} variant="outline" size="sm" disabled={uploading}
                  className="border-[#4A5D4E]/40 text-[#4A5D4E] hover:bg-[#4A5D4E]/5 rounded-xl"
                  data-testid="branding-recrop-logo" title="Bild verschieben/anpassen">
                  <Crop className="w-4 h-4" />
                </Button>
              )}
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('emailFooter')}</Label>
            <Textarea data-testid="branding-email-footer" value={branding.email_footer} onChange={e => update('email_footer', e.target.value)}
              className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl min-h-[60px] text-sm" />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('faviconUrl')}</Label>
            <Input data-testid="branding-favicon-url" value={branding.favicon_url} onChange={e => update('favicon_url', e.target.value)}
              placeholder="https://example.com/favicon.ico" className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl text-sm" />
          </div>

          <div className="flex gap-3">
            <Button onClick={handleSave} disabled={saving} data-testid="save-branding-button"
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-6 flex-1">
              <Save className="w-4 h-4 mr-2" /> {saving ? '...' : t('saveBranding')}
            </Button>
            <Button onClick={handleReset} variant="outline" data-testid="reset-branding-button"
              className="rounded-full px-4 border-[#E2E4E0]">
              <RotateCcw className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Live Preview */}
        <div>
          <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-3 block flex items-center gap-1.5">
            <Eye className="w-3.5 h-3.5" /> {t('brandingPreview')}
          </Label>

          {/* Sidebar Preview */}
          <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid="branding-preview">
            <div className="p-4 border-b border-[#E2E4E0]">
              <div className="flex items-center gap-2.5">
                {branding.logo_url ? (
                  <img
                    src={branding.logo_url.startsWith('/api/')
                      ? `${process.env.REACT_APP_BACKEND_URL}${branding.logo_url}`
                      : branding.logo_url}
                    alt="" className="w-7 h-7 rounded object-contain"
                  />
                ) : (
                  <Video className="w-7 h-7" style={{ color: branding.primary_color }} />
                )}
                <span className="text-lg font-semibold tracking-tight" style={{ fontFamily: 'Manrope', color: '#1C1F1D' }}>
                  {branding.company_name}
                </span>
              </div>
            </div>
            <div className="p-3 space-y-1">
              {['Dashboard', 'Calendar', 'Meetings'].map(item => (
                <div key={item} className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-[#4B5563]">
                  <div className="w-4 h-4 rounded bg-[#E8EAE6]" />
                  <span>{item}</span>
                </div>
              ))}
              <div className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-white"
                style={{ backgroundColor: branding.primary_color }}>
                <div className="w-4 h-4 rounded bg-white/20" />
                <span>Active Page</span>
              </div>
            </div>

            {/* Button Preview */}
            <div className="p-4 border-t border-[#E2E4E0] space-y-2">
              <button className="w-full text-white rounded-full py-2 text-sm font-medium transition-all"
                style={{ backgroundColor: branding.primary_color }}>
                Join Meeting
              </button>
              <button className="w-full border rounded-full py-2 text-sm font-medium"
                style={{ borderColor: branding.primary_color, color: branding.primary_color }}>
                Schedule Meeting
              </button>
            </div>

            {/* Email Footer Preview */}
            <div className="p-3 bg-[#F3F4F1] border-t border-[#E2E4E0]">
              <p className="text-[10px] text-[#9CA3AF] text-center">{branding.email_footer}</p>
            </div>
          </div>
        </div>
      </div>
      <BrandingCropDialog
        open={cropOpen}
        file={pendingLogo}
        aspect={1}
        targetWidth={256}
        targetHeight={256}
        title="Logo anpassen"
        description="Ziehe das Logo zum Verschieben, nutze den Slider zum Zoomen. Der quadratische Ausschnitt wird in der Seitenleiste, im Login und in E-Mails verwendet."
        onClose={() => { setCropOpen(false); setPendingLogo(null); }}
        onConfirm={uploadCroppedLogo}
      />
    </div>
  );
}
