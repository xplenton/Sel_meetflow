import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Loader2, Car, FileDown, MapPin } from 'lucide-react';
import api from '../lib/api';

/**
 * Fahrtenbuch-Dialog (P1 §15) — zeigt alle abgeschlossenen/bestätigten
 * Fahrten eines Dienstwagens mit Anwender, Ziel, Kilometerstand und Datum.
 *
 * Props: vehicle (mit resource_id + name + license_plate + drive_type)
 *        onClose: () => void
 */
export default function VehicleLogbookDialog({ vehicle, onClose }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!vehicle) return;
    setLoading(true);
    api.get(`/resources/${vehicle.resource_id}/driving-log`)
      .then(({ data }) => setRows(data || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [vehicle]);

  const apiBase = process.env.REACT_APP_BACKEND_URL || '';

  const exportCsv = () => {
    const head = ['Datum', 'Titel', 'Anwender', 'Ziel', 'Km Start', 'Km Ende', 'Differenz', 'Status'];
    const body = rows.map(r => {
      const km1 = r.mileage_before;
      const km2 = r.mileage_after;
      const diff = (km1 != null && km2 != null) ? km2 - km1 : '';
      return [
        new Date(r.start_at).toLocaleString('de-DE'),
        r.title || '',
        r.user_id || '',
        r.destination || '',
        km1 ?? '', km2 ?? '', diff, r.status || '',
      ].map(v => `"${String(v).replaceAll('"', '""')}"`).join(';');
    });
    const blob = new Blob(['\ufeff' + [head.join(';'), ...body].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `fahrtenbuch_${vehicle.license_plate || vehicle.resource_id}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const totalKm = rows.reduce((sum, r) => {
    if (r.mileage_before != null && r.mileage_after != null) {
      return sum + Math.max(0, r.mileage_after - r.mileage_before);
    }
    return sum;
  }, 0);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl w-[calc(100vw-1.5rem)] max-h-[90vh] overflow-y-auto" data-testid="vehicle-logbook-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Car className="w-4 h-4 text-[#4A5D4E]" />
            Fahrtenbuch — {vehicle?.name}
            {vehicle?.license_plate && (
              <Badge variant="outline" className="text-[10px]">{vehicle.license_plate}</Badge>
            )}
            {vehicle?.drive_type && (
              <Badge variant="outline" className="text-[10px] border-blue-400 text-blue-700">{vehicle.drive_type}</Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            Bestätigte und abgeschlossene Fahrten dieses Fahrzeugs. Gefahrene Gesamt-Kilometer:&nbsp;
            <strong className="text-[#1C1F1D]" data-testid="vehicle-logbook-total-km">{totalKm.toLocaleString('de-DE')} km</strong>
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="py-12 text-center text-[#9CA3AF]">
            <Loader2 className="w-5 h-5 animate-spin inline mr-2" /> Lade Fahrtenbuch …
          </div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-[#9CA3AF] text-sm">
            Keine Fahrten erfasst.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-xs text-[#6B7280] text-left">
                  <th className="py-1">Datum</th>
                  <th>Titel</th>
                  <th>Ziel</th>
                  <th className="text-right">Km Start</th>
                  <th className="text-right">Km Ende</th>
                  <th className="text-right">Diff</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => {
                  const diff = (r.mileage_before != null && r.mileage_after != null)
                    ? r.mileage_after - r.mileage_before : null;
                  return (
                    <tr key={r.booking_id} className="border-t border-[#E2E4E0]"
                        data-testid={`logbook-row-${r.booking_id}`}>
                      <td className="py-1 whitespace-nowrap">
                        {new Date(r.start_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td className="py-1">{r.title || '—'}</td>
                      <td className="py-1">
                        {r.destination ? (
                          <span className="inline-flex items-center gap-1">
                            <MapPin className="w-3 h-3 text-[#6B7280]" />{r.destination}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="py-1 text-right">{r.mileage_before ?? '—'}</td>
                      <td className="py-1 text-right">{r.mileage_after ?? '—'}</td>
                      <td className="py-1 text-right font-medium">{diff != null ? `${diff} km` : '—'}</td>
                      <td className="py-1">
                        <Badge variant="outline" className="text-[10px]">{r.status}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={exportCsv} disabled={rows.length === 0} data-testid="vehicle-logbook-export">
            <FileDown className="w-3 h-3 mr-1" /> CSV-Export
          </Button>
          <Button onClick={onClose} data-testid="vehicle-logbook-close">Schließen</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
