import { useEffect, useRef, useState } from 'react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Image as ImageIcon, Upload, Trash2, Loader2, Crop } from 'lucide-react';
import { toast } from 'sonner';
import BrandingCropDialog from './BrandingCropDialog';

/**
 * Klinik-Branding: Offizieller Virtual-Background (iter 191).
 * Admins laden hier ein Klinik-Hintergrundbild hoch; Mitarbeiter sehen es
 * als "Offizieller Klinik-Hintergrund" in der Virtual-Background-Auswahl
 * in jedem Live-Meeting.
 *
 * Iter 320 — Crop-Dialog: nach dem Datei-Auswählen lässt sich der
 * 16:9-Ausschnitt frei verschieben + zoomen, damit das Bild nicht
 * abgeschnitten wirkt.
 */
export default function BrandingPanel() {
  const [state, setState] = useState({ enabled: false, url: null, name: '' });
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [name, setName] = useState('');
  const [pendingFile, setPendingFile] = useState(null);
  const [cropOpen, setCropOpen] = useState(false);
  const fileRef = useRef(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/branding/official-background');
      setState(data);
      setName(data.name || '');
    } catch {
      // fallback
    } finally { setLoading(false); }
  };

  useEffect(() => { refresh(); }, []);

  const handleFile = async (f) => {
    if (!f) return;
    if (!['image/png', 'image/jpeg', 'image/jpg', 'image/webp'].includes(f.type)) {
      toast.error('Nur PNG, JPG oder WebP erlaubt');
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      toast.error('Bild darf maximal 10 MB gross sein');
      return;
    }
    // iter 320 — Erst Crop-Dialog öffnen, dann erst hochladen
    setPendingFile(f);
    setCropOpen(true);
    if (fileRef.current) fileRef.current.value = '';
  };

  const uploadCropped = async (cropped) => {
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', cropped);
      if (name) form.append('name', name);
      const { data } = await api.post('/admin/branding/background', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setState({ enabled: true, url: data.url, name: data.name });
      toast.success('Klinik-Hintergrund hochgeladen');
      setCropOpen(false);
      setPendingFile(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Upload fehlgeschlagen');
    } finally { setUploading(false); }
  };

  const recropExisting = async () => {
    if (!state.url) return;
    try {
      const res = await fetch(state.url);
      const blob = await res.blob();
      const f = new File([blob], 'klinik-hintergrund.jpg', { type: blob.type || 'image/jpeg' });
      setPendingFile(f);
      setCropOpen(true);
    } catch {
      toast.error('Bestehendes Bild konnte nicht geladen werden');
    }
  };

  const toggle = async (enabled) => {
    try {
      const { data } = await api.put('/admin/branding/background', { enabled });
      setState(s => ({ ...s, enabled: data.enabled }));
      toast.success(enabled ? 'Klinik-Hintergrund aktiviert' : 'Klinik-Hintergrund deaktiviert');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Änderung fehlgeschlagen');
    }
  };

  const saveName = async () => {
    try {
      const { data } = await api.put('/admin/branding/background', { name });
      setState(s => ({ ...s, name: data.name || name }));
      toast.success('Name aktualisiert');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen');
    }
  };

  const remove = async () => {
    if (!confirm('Klinik-Hintergrund wirklich löschen?')) return;
    try {
      await api.delete('/admin/branding/background');
      setState({ enabled: false, url: null, name: '' });
      setName('');
      toast.success('Klinik-Hintergrund gelöscht');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Löschen fehlgeschlagen');
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-5" data-testid="branding-panel">
      <div className="flex items-center gap-2 mb-4">
        <ImageIcon className="w-5 h-5 text-[#4A5D4E]" />
        <h2 className="text-base font-semibold text-[#1C1F1D]">Klinik-Branding</h2>
      </div>
      <p className="text-xs text-[#6B7280] mb-4 leading-relaxed">
        Offizielles Klinik-Hintergrundbild, das allen Mitarbeitern bei der
        Auswahl virtueller Hintergruende in Video-Meetings automatisch
        angezeigt wird. Ideal für einheitliches Erscheinungsbild bei
        Gespraechen mit Patienten oder externen Partnern.
      </p>

      {loading ? (
        <Loader2 className="w-5 h-5 animate-spin text-[#9CA3AF]" />
      ) : (
        <div className="space-y-4">
          {state.url ? (
            <div className="flex gap-3 items-start">
              <div className="w-32 h-20 rounded-lg overflow-hidden border border-[#E2E4E0] bg-[#1C1F1D] shrink-0">
                <img src={state.url} alt="Klinik-Hintergrund" className="w-full h-full object-contain" data-testid="branding-preview" />
              </div>
              <div className="flex-1 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-[#6B7280]">Aktivieren für alle User</span>
                  <Switch data-testid="branding-enabled-toggle" checked={state.enabled} onCheckedChange={toggle} />
                </div>
                <div className="flex gap-2">
                  <Button
                    data-testid="branding-recrop-button"
                    variant="outline" size="sm"
                    onClick={recropExisting}
                    className="h-8 text-xs border-[#4A5D4E]/40 text-[#4A5D4E] hover:bg-[#4A5D4E]/5"
                  >
                    <Crop className="w-3 h-3 mr-1" /> Zuschneiden
                  </Button>
                  <Button
                    data-testid="branding-remove-button"
                    variant="outline" size="sm"
                    onClick={remove}
                    className="h-8 text-xs border-[#C87967]/40 text-[#C87967] hover:bg-[#C87967]/5 hover:text-[#C87967]"
                  >
                    <Trash2 className="w-3 h-3 mr-1" /> Löschen
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="border-2 border-dashed border-[#E2E4E0] rounded-xl p-6 text-center">
              <ImageIcon className="w-8 h-8 text-[#9CA3AF] mx-auto mb-2" />
              <p className="text-xs text-[#6B7280]">Noch kein Klinik-Hintergrund hinterlegt</p>
            </div>
          )}

          <div className="pt-3 border-t border-[#E2E4E0] space-y-3">
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                Anzeigename
              </Label>
              <div className="flex gap-2">
                <Input
                  data-testid="branding-name-input"
                  value={name} onChange={e => setName(e.target.value)}
                  placeholder="z.B. Klinik XY"
                  className="border-[#E2E4E0] rounded-lg h-9 text-sm"
                />
                {state.url && state.name !== name && (
                  <Button size="sm" onClick={saveName} className="h-9 bg-[#4A5D4E] hover:bg-[#3E4E42] text-white">
                    Speichern
                  </Button>
                )}
              </div>
            </div>

            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                {state.url ? 'Bild austauschen' : 'Bild hochladen'}
              </Label>
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(e) => handleFile(e.target.files?.[0])}
                className="hidden"
                data-testid="branding-file-input"
              />
              <Button
                data-testid="branding-upload-button"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg h-10 text-sm"
              >
                {uploading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Upload className="w-4 h-4 mr-2" />}
                {uploading ? 'Laedt hoch...' : (state.url ? 'Neues Bild auswählen' : 'Bild auswählen')}
              </Button>
              <p className="text-[10px] text-[#9CA3AF] mt-1.5 text-center">
                PNG, JPG oder WebP &middot; Empfohlen: 1920&times;1080 px &middot; max. 10 MB
              </p>
            </div>
          </div>
        </div>
      )}
      <BrandingCropDialog
        open={cropOpen}
        file={pendingFile}
        onClose={() => { setCropOpen(false); setPendingFile(null); }}
        onConfirm={uploadCropped}
      />
    </div>
  );
}
