/**
 * Iter 292 — Drivers' license self-service (multi-license + photos).
 *
 * Replaces the legacy single-record UI. Each user keeps zero or more licenses
 * with class, number, issuing authority, validity range and front/back photo.
 * Admin or any user with cap `users.view_drivers_license` can read these via
 * the Admin → Auswertungen view (separate component).
 */
import { useEffect, useState, useRef } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Car, ShieldAlert, ShieldCheck, Plus, Pencil, Trash2, Camera, FolderOpen, Loader2, AlertTriangle, CheckCircle2 } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import { analyzeLicensePhoto } from '../lib/imageQuality';
import CameraCaptureDialog from './CameraCaptureDialog';

const STANDARD_CLASSES = [
  'AM', 'A1', 'A2', 'A',
  'B', 'BE',
  'C1', 'C1E', 'C', 'CE',
  'D1', 'D1E', 'D', 'DE',
  'L', 'T',
];

const BACKEND = process.env.REACT_APP_BACKEND_URL;

function LicenseRow({ lic, onEdit, onDelete, onPhotoChanged }) {
  const frontInputRef = useRef(null);
  const backInputRef = useRef(null);
  const [uploading, setUploading] = useState(null); // "front" | "back" | null
  // iter 309 — quality-review + camera-capture flow
  const [cameraOpen, setCameraOpen] = useState(null);  // "front" | "back" | null
  const [review, setReview] = useState(null);          // { side, file, report }
  const [analyzing, setAnalyzing] = useState(false);

  const sendUpload = async (side, file) => {
    setUploading(side);
    try {
      const fd = new FormData();
      fd.append('side', side);
      fd.append('file', file);
      await api.post(`/users/me/drivers-licenses/${lic.id}/photo`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success(`Foto (${side === 'front' ? 'Vorderseite' : 'Rückseite'}) gespeichert`);
      onPhotoChanged?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Upload fehlgeschlagen');
    } finally {
      setUploading(null);
    }
  };

  // Pipe both file-picker and camera through the same quality check.
  const handleCandidateFile = async (side, file) => {
    if (!file) return;
    setAnalyzing(true);
    try {
      const report = await analyzeLicensePhoto(file);
      // Auto-accept when there is nothing to flag — saves clicks for good shots.
      if (report.ok && report.issues.length === 0) {
        await sendUpload(side, file);
      } else {
        setReview({ side, file, report });
      }
    } catch (e) {
      // Analysis itself failed (e.g. corrupted file). Upload anyway — server validates.
      console.warn('[license] quality analysis failed, uploading raw', e);
      await sendUpload(side, file);
    } finally {
      setAnalyzing(false);
    }
  };

  const confirmReviewUpload = async () => {
    if (!review) return;
    const { side, file } = review;
    setReview(null);
    await sendUpload(side, file);
  };
  const retryReview = () => {
    if (!review) return;
    const side = review.side;
    setReview(null);
    // Re-open whichever path the user just came from. We open the camera again
    // when an issue was flagged so the next attempt is one click away.
    setCameraOpen(side);
  };

  const expired = lic.expires_at && new Date(lic.expires_at) < new Date();
  const photoUrl = (side) =>
    `${BACKEND}/api/users/me/drivers-licenses/${lic.id}/photo/${side}?v=${lic.updated_at}`;

  return (
    <div
      className="border border-[#E2E4E0] rounded-lg p-4 bg-white space-y-3"
      data-testid={`license-row-${lic.id}`}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Badge className="bg-[#4A5D4E] text-white text-[11px] font-semibold">
            {lic.is_custom ? (lic.custom_label || 'Sonderklasse') : lic.license_class}
          </Badge>
          {expired ? (
            <Badge variant="outline" className="border-rose-400 text-rose-700 text-[10px]">
              <ShieldAlert className="w-3 h-3 mr-1" />Abgelaufen
            </Badge>
          ) : lic.expires_at ? (
            <Badge variant="outline" className="border-emerald-400 text-emerald-700 text-[10px]">
              <ShieldCheck className="w-3 h-3 mr-1" />Gültig bis {lic.expires_at}
            </Badge>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" onClick={() => onEdit(lic)} data-testid={`edit-license-${lic.id}`}>
            <Pencil className="w-3.5 h-3.5" />
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onDelete(lic)} data-testid={`delete-license-${lic.id}`}>
            <Trash2 className="w-3.5 h-3.5 text-rose-600" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-3 gap-y-1 text-xs text-[#1C1F1D]">
        {lic.number && (
          <div><span className="text-[#9CA3AF]">Nummer:</span> {lic.number}</div>
        )}
        {lic.issuing_authority && (
          <div><span className="text-[#9CA3AF]">Behörde:</span> {lic.issuing_authority}</div>
        )}
        {lic.issued_at && (
          <div><span className="text-[#9CA3AF]">Ausgestellt:</span> {lic.issued_at}</div>
        )}
        {lic.notes && (
          <div className="sm:col-span-2 lg:col-span-4"><span className="text-[#9CA3AF]">Notiz:</span> {lic.notes}</div>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-[#F3F4F1]">
        {['front', 'back'].map(side => (
          <div key={side} className="space-y-1.5">
            <Label className="text-[10px] uppercase tracking-wide text-[#6B7280]">
              {side === 'front' ? 'Vorderseite' : 'Rückseite'}
            </Label>
            <div className="h-28 sm:h-24 border border-dashed border-[#E2E4E0] rounded-lg flex items-center justify-center overflow-hidden bg-[#F9FAF7]">
              {((side === 'front' && lic.has_front_photo) || (side === 'back' && lic.has_back_photo)) ? (
                <img
                  src={photoUrl(side)}
                  alt={`Führerschein ${side}`}
                  className="object-cover w-full h-full"
                  data-testid={`license-photo-${lic.id}-${side}`}
                />
              ) : (
                <Camera className="w-5 h-5 text-[#9CA3AF]" />
              )}
            </div>
            <input
              type="file"
              accept="image/*"
              ref={side === 'front' ? frontInputRef : backInputRef}
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleCandidateFile(side, f);
                e.target.value = '';
              }}
              data-testid={`license-photo-input-${lic.id}-${side}`}
            />
            <div className="grid grid-cols-2 gap-1.5">
              <Button
                size="sm" variant="outline"
                className="text-[11px] rounded-full px-2 min-w-0"
                onClick={() => (side === 'front' ? frontInputRef : backInputRef).current?.click()}
                disabled={uploading === side || analyzing}
                data-testid={`upload-photo-${lic.id}-${side}`}
                title="Bestehendes Foto vom Gerät auswählen"
              >
                {uploading === side ? (
                  <><Loader2 className="w-3 h-3 mr-1 animate-spin shrink-0" /><span className="truncate">Lade…</span></>
                ) : (
                  <><FolderOpen className="w-3 h-3 mr-1 shrink-0" /><span className="truncate">Datei</span></>
                )}
              </Button>
              <Button
                size="sm" variant="outline"
                className="text-[11px] rounded-full px-2 min-w-0"
                onClick={() => setCameraOpen(side)}
                disabled={uploading === side || analyzing}
                data-testid={`capture-photo-${lic.id}-${side}`}
                title="Foto mit Kamera aufnehmen"
              >
                <Camera className="w-3 h-3 mr-1 shrink-0" /><span className="truncate">Kamera</span>
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* iter 309 — Camera capture */}
      <CameraCaptureDialog
        open={!!cameraOpen}
        side={cameraOpen || 'front'}
        onClose={() => setCameraOpen(null)}
        onCapture={(file) => handleCandidateFile(cameraOpen, file)}
      />

      {/* iter 309 — Quality-review dialog */}
      <Dialog open={!!review} onOpenChange={(o) => !o && setReview(null)}>
        <DialogContent className="max-w-md" data-testid={`license-quality-review-${lic.id}`}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              Foto-Qualität prüfen
            </DialogTitle>
          </DialogHeader>
          {review && (
            <div className="space-y-3">
              <div className="text-xs text-[#6B7280]">
                Wir haben dein Foto kurz analysiert. Folgende Punkte fallen auf:
              </div>
              <ul className="space-y-1.5" data-testid={`license-quality-issues-${lic.id}`}>
                {review.report.issues.map((it) => (
                  <li key={it.key}
                    className={`flex items-start gap-2 text-xs p-2 rounded-md ${
                      it.severity === 'error' ? 'bg-rose-50 text-rose-800' : 'bg-amber-50 text-amber-800'
                    }`}>
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>{it.label}</span>
                  </li>
                ))}
                {review.report.issues.length === 0 && (
                  <li className="flex items-center gap-2 text-xs text-emerald-700">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Keine Auffälligkeiten.
                  </li>
                )}
              </ul>
              <div className="text-[10px] text-[#9CA3AF] grid grid-cols-1 sm:grid-cols-3 gap-x-3">
                <div>Auflösung: {review.report.stats.width}×{review.report.stats.height}</div>
                <div>Schärfe-Index: {review.report.stats.sharpness}</div>
                <div>Helligkeit: {review.report.stats.brightness}/255</div>
              </div>
              <DialogFooter className="gap-2">
                <Button variant="ghost" onClick={() => setReview(null)}
                  data-testid={`license-quality-cancel-${lic.id}`}>
                  Abbrechen
                </Button>
                <Button variant="outline" onClick={retryReview}
                  data-testid={`license-quality-retry-${lic.id}`}>
                  <Camera className="w-3 h-3 mr-1" />Neu aufnehmen
                </Button>
                <Button
                  onClick={confirmReviewUpload}
                  className={review.report.ok ? 'bg-[#4A5D4E] hover:bg-[#3E4E42] text-white' : 'bg-amber-600 hover:bg-amber-700 text-white'}
                  data-testid={`license-quality-accept-${lic.id}`}
                >
                  {review.report.ok ? 'Trotzdem hochladen' : 'Trotz Hinweis hochladen'}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function LicenseEditor({ open, onClose, initial, onSaved }) {
  const [form, setForm] = useState(initial || {
    license_class: 'B', is_custom: false, custom_label: '',
    number: '', issuing_authority: '', issued_at: '', expires_at: '', notes: '',
  });
  useEffect(() => { if (open) setForm(initial || {
    license_class: 'B', is_custom: false, custom_label: '',
    number: '', issuing_authority: '', issued_at: '', expires_at: '', notes: '',
  }); }, [open, initial]);

  const [saving, setSaving] = useState(false);
  const isEdit = !!initial?.id;

  const save = async () => {
    if (form.is_custom && !form.custom_label?.trim()) {
      toast.error('Bezeichnung der Sonderklasse fehlt');
      return;
    }
    setSaving(true);
    try {
      const payload = { ...form };
      if (isEdit) {
        await api.put(`/users/me/drivers-licenses/${initial.id}`, payload);
      } else {
        await api.post('/users/me/drivers-licenses', payload);
      }
      toast.success('Führerschein gespeichert');
      onSaved?.();
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent
        className="max-w-md"
        onInteractOutside={(e) => e.preventDefault()}
        data-testid="license-editor-dialog"
      >
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Führerschein bearbeiten' : 'Führerschein hinzufügen'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <Label className="text-xs">Klasse</Label>
              {form.is_custom ? (
                <Input
                  value={form.custom_label || ''}
                  placeholder="Eigene Bezeichnung"
                  onChange={(e) => setForm({ ...form, custom_label: e.target.value, license_class: e.target.value })}
                  data-testid="license-custom-label"
                />
              ) : (
                <Select value={form.license_class} onValueChange={(v) => setForm({ ...form, license_class: v })}>
                  <SelectTrigger data-testid="license-class-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STANDARD_CLASSES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            </div>
            <Button
              size="sm" variant="outline"
              onClick={() => setForm(f => ({ ...f, is_custom: !f.is_custom, custom_label: '', license_class: !f.is_custom ? '' : 'B' }))}
              data-testid="license-toggle-custom"
            >
              {form.is_custom ? 'Standard' : 'Sonderklasse'}
            </Button>
          </div>
          <div>
            <Label className="text-xs">Nummer</Label>
            <Input value={form.number || ''} onChange={(e) => setForm({ ...form, number: e.target.value })} data-testid="license-number" />
          </div>
          <div>
            <Label className="text-xs">Ausstellende Behörde</Label>
            <Input value={form.issuing_authority || ''} onChange={(e) => setForm({ ...form, issuing_authority: e.target.value })} data-testid="license-authority" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Ausgestellt am</Label>
              <Input type="date" value={form.issued_at || ''} onChange={(e) => setForm({ ...form, issued_at: e.target.value })} data-testid="license-issued-at" />
            </div>
            <div>
              <Label className="text-xs">Ablaufdatum</Label>
              <Input type="date" value={form.expires_at || ''} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} data-testid="license-expires-at" />
            </div>
          </div>
          <div>
            <Label className="text-xs">Notiz (optional)</Label>
            <Input value={form.notes || ''} onChange={(e) => setForm({ ...form, notes: e.target.value })} data-testid="license-notes" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Abbrechen</Button>
          <Button onClick={save} disabled={saving} data-testid="license-save">
            {saving ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null}
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function DriverLicenseSection() {
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const refresh = async () => {
    try {
      const { data } = await api.get('/users/me/drivers-licenses');
      setItems(data.licenses || []);
    } catch {
      /* user may not have any yet — keep empty list */
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => { refresh(); }, []);

  const onDelete = async (lic) => {
    if (!window.confirm(`Führerschein ${lic.license_class} wirklich löschen?`)) return;
    try {
      await api.delete(`/users/me/drivers-licenses/${lic.id}`);
      toast.success('Gelöscht');
      refresh();
    } catch {
      toast.error('Löschen fehlgeschlagen');
    }
  };

  if (!loaded) return null;

  return (
    <Card className="p-4" data-testid="driver-license-section">
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Car className="w-4 h-4 text-[#4A5D4E]" />
          <h3 className="text-sm font-semibold text-[#1C1F1D]">Führerscheine</h3>
        </div>
        <Button
          size="sm"
          onClick={() => { setEditing(null); setEditorOpen(true); }}
          data-testid="add-license-btn"
          className="rounded-full"
        >
          <Plus className="w-3.5 h-3.5 mr-1" />Hinzufügen
        </Button>
      </div>
      <p className="text-xs text-[#6B7280] mb-3">
        Trage deine Führerscheine ein. Beim Buchen eines Dienstfahrzeugs prüft das System die geforderte Klasse.
      </p>

      {items.length === 0 ? (
        <div className="text-xs text-[#9CA3AF] text-center py-6">Noch kein Führerschein hinterlegt.</div>
      ) : (
        <div className="space-y-3">
          {items.map(lic => (
            <LicenseRow
              key={lic.id}
              lic={lic}
              onEdit={(l) => { setEditing(l); setEditorOpen(true); }}
              onDelete={onDelete}
              onPhotoChanged={refresh}
            />
          ))}
        </div>
      )}

      <LicenseEditor
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        initial={editing}
        onSaved={refresh}
      />
    </Card>
  );
}
