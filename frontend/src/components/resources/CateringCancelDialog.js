import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { AlertTriangle, Loader2 } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

/**
 * Iter 246 — Catering-Storno-Dialog mit Gebuehren-Preview.
 *
 * Props:
 *   request: Catering-Request-Objekt (request_id + optional total_amount)
 *   onClose(refresh: boolean)
 *
 * Holt /catering-requests/{id}/cancel-preview, zeigt Gebuehren-Tier
 * (free/late/very_late) als Ampel und sendet beim Bestätigen
 * POST /catering-requests/{id}/transition status=cancelled.
 */
export default function CateringCancelDialog({ request, onClose }) {
  const [preview, setPreview] = useState(null);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!request) return;
    setLoading(true);
    api.get(`/catering-requests/${request.request_id}/cancel-preview`)
      .then(r => setPreview(r.data))
      .catch(e => {
        toast.error(e.response?.data?.detail || 'Konnte Storno-Vorschau nicht laden');
        onClose(false);
      })
      .finally(() => setLoading(false));
  }, [request, onClose]);

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.post(`/catering-requests/${request.request_id}/transition`, {
        status: 'cancelled',
        reason: reason.trim(),
      });
      const fee = preview?.fee_amount || 0;
      toast.success(fee > 0
        ? `Catering storniert — Gebuehr ${fee.toFixed(2)} EUR wird in Rechnung gestellt`
        : 'Catering kostenfrei storniert');
      onClose(true);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Stornieren');
    } finally {
      setSubmitting(false);
    }
  };

  const tierMeta = {
    free:      { label: 'Kostenfrei',      cls: 'border-emerald-300 bg-emerald-50 text-emerald-700' },
    late:      { label: 'Spaet',           cls: 'border-amber-300 bg-amber-50 text-amber-700' },
    very_late: { label: 'Sehr spaet',      cls: 'border-rose-300 bg-rose-50 text-rose-700' },
  };

  return (
    <Dialog open onOpenChange={(o) => !o && !submitting && onClose(false)}>
      <DialogContent className="max-w-md w-[calc(100vw-1.5rem)]" data-testid="catering-cancel-dialog">
        <DialogHeader>
          <DialogTitle>Catering-Anfrage stornieren</DialogTitle>
          <DialogDescription>
            Bitte prüfe die voraussichtliche Storno-Gebuehr und bestätige die Stornierung.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center py-8 text-[#6B7280] text-sm">
            <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Lade Storno-Vorschau ...
          </div>
        )}

        {!loading && preview?.already_finalized && (
          <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3"
               data-testid="cancel-already-finalized">
            Diese Anfrage ist bereits {preview.status === 'cancelled' ? 'storniert' : 'abgeschlossen'} und kann nicht mehr storniert werden.
          </div>
        )}

        {!loading && preview && !preview.already_finalized && (
          <div className="space-y-3">
            <div className={`p-3 rounded-lg border ${preview.fee_amount > 0 ? 'border-amber-300 bg-amber-50' : 'border-emerald-300 bg-emerald-50'}`}>
              <div className="flex items-start gap-2">
                {preview.fee_amount > 0 && (
                  <AlertTriangle className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-[#1C1F1D]">
                      {preview.fee_amount > 0
                        ? `Storno-Gebuehr: ${preview.fee_amount.toFixed(2)} EUR`
                        : 'Stornierung ist kostenfrei'}
                    </span>
                    <Badge variant="outline" className={`text-[10px] ${tierMeta[preview.tier]?.cls || ''}`}
                           data-testid="cancel-tier-badge">
                      {tierMeta[preview.tier]?.label || preview.tier}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-[#6B7280] mt-1">
                    {preview.hours_until_event >= 0
                      ? `Noch ${preview.hours_until_event.toFixed(1)}h bis zur Lieferung`
                      : `${Math.abs(preview.hours_until_event).toFixed(1)}h nach Liefertermin`}
                    {' · '}
                    Frist: {preview.cancel_cfg?.cancellation_deadline_hours}h
                    {preview.fee_percent > 0 && ` · ${preview.fee_percent}% von ${preview.total.toFixed(2)} EUR`}
                  </div>
                </div>
              </div>
            </div>
            <div>
              <Label htmlFor="cancel-reason">Grund (optional)</Label>
              <Textarea
                id="cancel-reason"
                value={reason}
                onChange={e => setReason(e.target.value)}
                placeholder="z. B. Meeting verschoben, Gaeste abgesagt ..."
                data-testid="cancel-reason-input"
                rows={2}
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} disabled={submitting}
                  data-testid="cancel-dialog-close-btn">
            Abbrechen
          </Button>
          {!loading && preview && !preview.already_finalized && (
            <Button
              variant="destructive"
              onClick={submit}
              disabled={submitting}
              data-testid="cancel-dialog-confirm-btn"
            >
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {preview.fee_amount > 0 ? `Trotzdem stornieren (${preview.fee_amount.toFixed(2)} EUR)` : 'Stornieren'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
