import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Save, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

/**
 * Iter 246 — Admin-Panel für Catering-Storno-Frist + Gebuehren.
 *
 * 4 Felder:
 *   - cancellation_deadline_hours (kostenfrei ab dieser Frist)
 *   - late_fee_percent (innerhalb der Frist, aber vor very_late)
 *   - very_late_threshold_hours (sehr-spaet Grenze)
 *   - very_late_fee_percent (kurz vor / nach Lieferung)
 *
 * Wird im Tab "Catering-Artikel" oben eingebunden.
 */
export default function CateringCancelConfigPanel() {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/catering-config')
      .then(r => setCfg(r.data))
      .catch(() => toast.error('Konnte Storno-Config nicht laden'));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put('/catering-config', {
        cancellation_deadline_hours: Number(cfg.cancellation_deadline_hours),
        late_fee_percent: Number(cfg.late_fee_percent),
        very_late_threshold_hours: Number(cfg.very_late_threshold_hours),
        very_late_fee_percent: Number(cfg.very_late_fee_percent),
        // Iter 322c — Global default lead time for catering
        default_lead_time_min: Number(cfg.default_lead_time_min ?? 60),
      });
      setCfg(data);
      toast.success('Konfiguration gespeichert');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Speichern');
    } finally {
      setSaving(false);
    }
  };

  if (!cfg) {
    return (
      <div className="border border-[#E2E4E0] rounded-lg p-3 text-sm text-[#6B7280] flex items-center"
           data-testid="catering-cancel-cfg-loading">
        <Loader2 className="w-4 h-4 animate-spin mr-2" /> Lade Storno-Config ...
      </div>
    );
  }

  const set = (k, v) => setCfg(prev => ({ ...prev, [k]: v }));

  return (
    <div className="border border-[#E2E4E0] rounded-lg p-3 bg-[#FAFBF9]" data-testid="catering-cancel-cfg-panel">
      <div className="text-sm font-medium text-[#1C1F1D] mb-1">Storno-Frist, Gebuehren &amp; Vorlaufzeit</div>
      <p className="text-[11px] text-[#6B7280] mb-3">
        Storniert der Anforderer eine Catering-Anfrage innerhalb der Frist, wird je nach Zeitpunkt
        eine Gebuehr berechnet. Werte werden direkt auf der Anfrage gespeichert (Audit/Rechnung).
        Die <strong>Vorlaufzeit</strong> ist der globale Default, falls ein Artikel selbst keinen Wert hat —
        wird beim Buchen geprüft und loest bei Unterschreitung Warnung + E-Mail an die Cafeteria aus.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <div className="min-w-0">
          <Label htmlFor="cfg-deadline" className="text-xs block leading-tight min-h-[2.2em]">Frist (Stunden, kostenfrei ab ...)</Label>
          <Input
            id="cfg-deadline"
            type="number"
            min={0}
            value={cfg.cancellation_deadline_hours}
            onChange={e => set('cancellation_deadline_hours', e.target.value)}
            data-testid="cfg-deadline-input"
          />
        </div>
        <div className="min-w-0">
          <Label htmlFor="cfg-late" className="text-xs block leading-tight min-h-[2.2em]">Spaet-Gebuehr (% der Summe)</Label>
          <Input
            id="cfg-late"
            type="number"
            min={0}
            max={100}
            step="0.1"
            value={cfg.late_fee_percent}
            onChange={e => set('late_fee_percent', e.target.value)}
            data-testid="cfg-late-fee-input"
          />
        </div>
        <div className="min-w-0">
          <Label htmlFor="cfg-vl-h" className="text-xs block leading-tight min-h-[2.2em]">Sehr-spaet-Grenze (Stunden)</Label>
          <Input
            id="cfg-vl-h"
            type="number"
            min={0}
            value={cfg.very_late_threshold_hours}
            onChange={e => set('very_late_threshold_hours', e.target.value)}
            data-testid="cfg-vl-threshold-input"
          />
        </div>
        <div className="min-w-0">
          <Label htmlFor="cfg-vl-fee" className="text-xs block leading-tight min-h-[2.2em]">Sehr-spaet-Gebuehr (% der Summe)</Label>
          <Input
            id="cfg-vl-fee"
            type="number"
            min={0}
            max={100}
            step="0.1"
            value={cfg.very_late_fee_percent}
            onChange={e => set('very_late_fee_percent', e.target.value)}
            data-testid="cfg-vl-fee-input"
          />
        </div>
        <div className="min-w-0">
          <Label htmlFor="cfg-lead" className="text-xs block leading-tight min-h-[2.2em]">Standard-Vorlaufzeit (Min.)</Label>
          <Input
            id="cfg-lead"
            type="number"
            min={0}
            max={20160}
            value={cfg.default_lead_time_min ?? 60}
            onChange={e => set('default_lead_time_min', e.target.value)}
            data-testid="cfg-lead-time-input"
            placeholder="60"
          />
        </div>
      </div>
      <div className="flex justify-end mt-3">
        <Button size="sm" onClick={save} disabled={saving} data-testid="cfg-save-btn">
          {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
          Speichern
        </Button>
      </div>
    </div>
  );
}
