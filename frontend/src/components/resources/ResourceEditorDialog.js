import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Plus, Trash2 } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

/**
 * Admin CRUD dialog for resources (rooms / desks / vehicles).
 * Props:
 *   - resource: existing record OR null (for create)
 *   - type: 'room' | 'desk' | 'vehicle' (only used when creating)
 *   - onClose(refresh:boolean)
 */
export default function ResourceEditorDialog({ resource, type: typeProp, onClose }) {
  const editing = !!resource;
  const t = resource?.type || typeProp || 'room';
  const [form, setForm] = useState({
    name: resource?.name || '',
    type: t,
    location: resource?.location || '',
    building: resource?.building || '',
    floor: resource?.floor || '',
    capacity: resource?.capacity || '',
    equipment: (resource?.equipment || []).join(', '),
    status: resource?.status || 'active',
    requires_approval: !!resource?.requires_approval,
    allow_catering: !!resource?.allow_catering,
    license_plate: resource?.license_plate || '',
    vehicle_type: resource?.vehicle_type || '',
    seats: resource?.seats || '',
    fuel_card: !!resource?.fuel_card,
    fuel_card_number: resource?.fuel_card_number || '',
    drive_type: resource?.drive_type || '',
    required_license_class: resource?.required_license_class || '',
    desk_number: resource?.desk_number || '',
    is_splitable: !!resource?.is_splitable,
    notes: resource?.notes || '',
    // Iter 299 — Fuhrpark-Stammblatt
    first_registration: resource?.first_registration || '',
    vin: resource?.vin || '',
    engine_ccm: resource?.engine_ccm || '',
    engine_kw: resource?.engine_kw || '',
    mileage: resource?.mileage || '',
    tuev_next: resource?.tuev_next || '',
    au_next: resource?.au_next || '',
    next_service_due: resource?.next_service_due || '',
    last_oil_change: resource?.last_oil_change || '',
    has_summer_tires: !!resource?.has_summer_tires,
    summer_tire_depth_mm: resource?.summer_tire_depth_mm || '',
    has_winter_tires: !!resource?.has_winter_tires,
    winter_tire_depth_mm: resource?.winter_tire_depth_mm || '',
    current_tires: resource?.current_tires || '',
    insurance_policy_no: resource?.insurance_policy_no || '',
    insurance_expires: resource?.insurance_expires || '',
    ownership: resource?.ownership || '',
    leasing_company: resource?.leasing_company || '',
    leasing_end: resource?.leasing_end || '',
    parking_location: resource?.parking_location || '',
    fleet_status: resource?.fleet_status || '',
  });
  const [subs, setSubs] = useState(resource?.sub_resources || (t === 'room' ? [] : []));

  const setField = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!form.name.trim()) { toast.error('Name fehlt'); return; }
    const body = {
      ...form,
      capacity: form.capacity ? Number(form.capacity) : null,
      seats: form.seats ? Number(form.seats) : null,
      drive_type: form.drive_type || null,
      required_license_class: form.required_license_class || null,
      fuel_card_number: form.fuel_card_number || null,
      equipment: form.equipment.split(',').map(s => s.trim()).filter(Boolean),
      sub_resources: form.is_splitable ? subs : [],
      // Iter 299 — fleet stammblatt: empty strings → null, numbers → Number
      first_registration: form.first_registration || null,
      vin: form.vin || null,
      engine_ccm: form.engine_ccm ? Number(form.engine_ccm) : null,
      engine_kw: form.engine_kw ? Number(form.engine_kw) : null,
      mileage: form.mileage ? Number(form.mileage) : null,
      tuev_next: form.tuev_next || null,
      au_next: form.au_next || null,
      next_service_due: form.next_service_due || null,
      last_oil_change: form.last_oil_change || null,
      summer_tire_depth_mm: form.summer_tire_depth_mm ? Number(form.summer_tire_depth_mm) : null,
      winter_tire_depth_mm: form.winter_tire_depth_mm ? Number(form.winter_tire_depth_mm) : null,
      current_tires: form.current_tires || null,
      insurance_policy_no: form.insurance_policy_no || null,
      insurance_expires: form.insurance_expires || null,
      ownership: form.ownership || null,
      leasing_company: form.leasing_company || null,
      leasing_end: form.leasing_end || null,
      parking_location: form.parking_location || null,
      fleet_status: form.fleet_status || null,
    };
    try {
      if (editing) {
        await api.put(`/resources/${resource.resource_id}`, body);
        toast.success('Aktualisiert');
      } else {
        await api.post('/resources', body);
        toast.success('Angelegt');
      }
      onClose(true);
    } catch (e) {
      // Iter 268 — Robustere Fehlermeldung. "Not Found" vom Server (404 oder
      // bare "Not Found"-String) deutet meist auf stale Production-Deploy oder
      // fehlende Berechtigung. Daher User-friendly Hinweis.
      const status = e?.response?.status;
      const raw = e?.response?.data?.detail;
      let msg;
      if (status === 404 || raw === 'Not Found') {
        msg = 'Server-Endpunkt nicht erreichbar. Bitte Seite neu laden oder erneut deployen.';
      } else if (status === 403) {
        msg = 'Keine Berechtigung zum Anlegen/Ändern von Ressourcen.';
      } else if (!e?.response) {
        msg = 'Server nicht erreichbar — Netzwerk prüfen.';
      } else {
        msg = (typeof raw === 'string' ? raw : raw?.detail) || 'Speichern fehlgeschlagen';
      }
      toast.error(msg);
    }
  };

  const onDelete = async () => {
    if (!editing) return;
    if (!window.confirm(`"${resource.name}" wirklich löschen?`)) return;
    try {
      await api.delete(`/resources/${resource.resource_id}`);
      toast.success('Gelöscht');
      onClose(true);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Löschen fehlgeschlagen');
    }
  };

  const addSub = () => {
    if (subs.length >= 3) { toast.error('Maximal 3 Teilbereiche'); return; }
    const next = String.fromCharCode(65 + subs.length); // A, B, C
    setSubs([...subs, { sub_id: next, name: `Bereich ${next}`, capacity: null, equipment: [] }]);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent className="max-w-xl w-[calc(100vw-1.5rem)] max-h-[90vh] overflow-y-auto" data-testid="resource-editor">
        <DialogHeader>
          <DialogTitle>{editing ? 'Ressource bearbeiten' : 'Neue Ressource'}</DialogTitle>
          <DialogDescription>Stammdaten für {t === 'room' ? 'Raum' : t === 'desk' ? 'Arbeitsplatz' : 'Fahrzeug'}</DialogDescription>
        </DialogHeader>

        <div>
          <Label>Name</Label>
          <Input data-testid="res-name-input" value={form.name} onChange={e => setField('name', e.target.value)} />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label>Standort</Label>
            <Input data-testid="res-location-input" value={form.location} onChange={e => setField('location', e.target.value)} />
          </div>
          <div>
            <Label>Gebaeude</Label>
            <Input value={form.building} onChange={e => setField('building', e.target.value)} />
          </div>
          <div>
            <Label>Etage</Label>
            <Input value={form.floor} onChange={e => setField('floor', e.target.value)} />
          </div>
          {t === 'room' && (
            <div>
              <Label>Kapazität</Label>
              <Input type="number" value={form.capacity} onChange={e => setField('capacity', e.target.value)} />
            </div>
          )}
          {t === 'desk' && (
            <div>
              <Label>Desk-Nummer</Label>
              <Input value={form.desk_number} onChange={e => setField('desk_number', e.target.value)} />
            </div>
          )}
          {t === 'vehicle' && (
            <>
              <div>
                <Label>Kennzeichen</Label>
                <Input value={form.license_plate} onChange={e => setField('license_plate', e.target.value)} data-testid="vehicle-license-input" />
              </div>
              <div>
                <Label>Fahrzeugtyp</Label>
                <Input value={form.vehicle_type} onChange={e => setField('vehicle_type', e.target.value)} data-testid="vehicle-type-input" />
              </div>
              <div>
                <Label>Sitzplätze</Label>
                <Input type="number" value={form.seats} onChange={e => setField('seats', e.target.value)} data-testid="vehicle-seats-input" />
              </div>
              <div>
                <Label>Antriebsart</Label>
                <Select value={form.drive_type || '_none'} onValueChange={v => setField('drive_type', v === '_none' ? '' : v)}>
                  <SelectTrigger data-testid="vehicle-drive-type"><SelectValue placeholder="Antriebsart" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">— keine Angabe —</SelectItem>
                    <SelectItem value="benzin">Benzin</SelectItem>
                    <SelectItem value="diesel">Diesel</SelectItem>
                    <SelectItem value="elektro">Elektro</SelectItem>
                    <SelectItem value="hybrid">Hybrid</SelectItem>
                    <SelectItem value="gas">Gas (LPG/CNG)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Geforderte Führerscheinklasse</Label>
                <Select value={form.required_license_class || '_none'} onValueChange={v => setField('required_license_class', v === '_none' ? '' : v)}>
                  <SelectTrigger data-testid="vehicle-required-class"><SelectValue placeholder="Keine Anforderung" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">— keine Anforderung —</SelectItem>
                    {['AM','A1','A2','A','B','BE','C1','C1E','C','CE','D1','D1E','D','DE','L','T'].map(c => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="col-span-2 grid grid-cols-[auto_1fr] gap-3 items-center">
                <div className="flex items-center gap-2">
                  <Switch checked={form.fuel_card} onCheckedChange={v => setField('fuel_card', v)} data-testid="vehicle-fuel-card-toggle" />
                  <Label className="text-xs">Tankkarte vorhanden</Label>
                </div>
                {form.fuel_card && (
                  <Input
                    placeholder="Tankkartennummer (z. B. DKV 12345678)"
                    value={form.fuel_card_number}
                    onChange={e => setField('fuel_card_number', e.target.value)}
                    data-testid="vehicle-fuel-card-number"
                  />
                )}
              </div>

              {/* Iter 299 — Fuhrpark-Stammblatt */}
              <div className="col-span-2 border-t border-[#E2E4E0] mt-2 pt-3">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280] mb-2">Fuhrpark-Stammblatt</p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="fleet-section-identity">
                  <div>
                    <Label className="text-xs">Erstzulassung</Label>
                    <Input type="date" value={form.first_registration} onChange={e => setField('first_registration', e.target.value)} data-testid="vehicle-first-registration" />
                    {!form.first_registration && (
                      <p className="text-[10px] text-[#9CA3AF] mt-0.5">Tippen zum Auswählen — TT.MM.JJJJ</p>
                    )}
                  </div>
                  <div>
                    <Label className="text-xs">Fahrgestellnummer (VIN)</Label>
                    <Input value={form.vin} onChange={e => setField('vin', e.target.value)} placeholder="WAU…" data-testid="vehicle-vin" />
                  </div>
                  <div>
                    <Label className="text-xs">Hubraum (ccm)</Label>
                    <Input type="number" value={form.engine_ccm} onChange={e => setField('engine_ccm', e.target.value)} data-testid="vehicle-engine-ccm" />
                  </div>
                  <div>
                    <Label className="text-xs">Leistung (kW)</Label>
                    <Input type="number" value={form.engine_kw} onChange={e => setField('engine_kw', e.target.value)} data-testid="vehicle-engine-kw" />
                  </div>
                  <div>
                    <Label className="text-xs">Kilometerstand</Label>
                    <Input type="number" value={form.mileage} onChange={e => setField('mileage', e.target.value)} data-testid="vehicle-mileage" />
                  </div>
                  <div>
                    <Label className="text-xs">Stellplatz / Standort</Label>
                    <Input value={form.parking_location} onChange={e => setField('parking_location', e.target.value)} placeholder="Tiefgarage A, Stellplatz 12" data-testid="vehicle-parking" />
                  </div>
                </div>

                <p className="text-[10px] font-semibold uppercase tracking-wider text-[#6B7280] mt-4 mb-1">Prüfungen & Wartung</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="fleet-section-checks">
                  <div>
                    <Label className="text-xs">TÜV (Hauptuntersuchung) nächste</Label>
                    <Input type="date" value={form.tuev_next} onChange={e => setField('tuev_next', e.target.value)} data-testid="vehicle-tuev" />
                  </div>
                  <div>
                    <Label className="text-xs">AU (Abgasuntersuchung) nächste</Label>
                    <Input type="date" value={form.au_next} onChange={e => setField('au_next', e.target.value)} data-testid="vehicle-au" />
                  </div>
                  <div>
                    <Label className="text-xs">Nächster Service</Label>
                    <Input type="date" value={form.next_service_due} onChange={e => setField('next_service_due', e.target.value)} data-testid="vehicle-service" />
                  </div>
                  <div>
                    <Label className="text-xs">Letzter Ölwechsel</Label>
                    <Input type="date" value={form.last_oil_change} onChange={e => setField('last_oil_change', e.target.value)} data-testid="vehicle-oil-change" />
                  </div>
                </div>

                <p className="text-[10px] font-semibold uppercase tracking-wider text-[#6B7280] mt-4 mb-1">Reifen</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="fleet-section-tires">
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <Switch checked={form.has_summer_tires} onCheckedChange={v => setField('has_summer_tires', v)} data-testid="vehicle-has-summer" />
                      <Label className="text-xs">Sommerreifen vorhanden</Label>
                    </div>
                    {form.has_summer_tires && (
                      <Input type="number" step="0.1" value={form.summer_tire_depth_mm} onChange={e => setField('summer_tire_depth_mm', e.target.value)} placeholder="Profil-Tiefe (mm)" data-testid="vehicle-summer-depth" />
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <Switch checked={form.has_winter_tires} onCheckedChange={v => setField('has_winter_tires', v)} data-testid="vehicle-has-winter" />
                      <Label className="text-xs">Winterreifen vorhanden</Label>
                    </div>
                    {form.has_winter_tires && (
                      <Input type="number" step="0.1" value={form.winter_tire_depth_mm} onChange={e => setField('winter_tire_depth_mm', e.target.value)} placeholder="Profil-Tiefe (mm)" data-testid="vehicle-winter-depth" />
                    )}
                  </div>
                  <div className="col-span-2">
                    <Label className="text-xs">Aktuell montiert</Label>
                    <Select value={form.current_tires || '_none'} onValueChange={v => setField('current_tires', v === '_none' ? '' : v)}>
                      <SelectTrigger data-testid="vehicle-current-tires"><SelectValue placeholder="Keine Angabe" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none">— keine Angabe —</SelectItem>
                        <SelectItem value="summer">Sommer</SelectItem>
                        <SelectItem value="winter">Winter</SelectItem>
                        <SelectItem value="allseason">Ganzjahres</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <p className="text-[10px] font-semibold uppercase tracking-wider text-[#6B7280] mt-4 mb-1">Versicherung & Verträge</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="fleet-section-insurance">
                  <div>
                    <Label className="text-xs">Versicherungs-Police</Label>
                    <Input value={form.insurance_policy_no} onChange={e => setField('insurance_policy_no', e.target.value)} placeholder="HUK-12345678" data-testid="vehicle-insurance-no" />
                  </div>
                  <div>
                    <Label className="text-xs">Versicherung läuft bis</Label>
                    <Input type="date" value={form.insurance_expires} onChange={e => setField('insurance_expires', e.target.value)} data-testid="vehicle-insurance-expires" />
                  </div>
                  <div>
                    <Label className="text-xs">Eigentum / Leasing</Label>
                    <Select value={form.ownership || '_none'} onValueChange={v => setField('ownership', v === '_none' ? '' : v)}>
                      <SelectTrigger data-testid="vehicle-ownership"><SelectValue placeholder="Keine Angabe" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none">— keine Angabe —</SelectItem>
                        <SelectItem value="owned">Eigentum</SelectItem>
                        <SelectItem value="leased">Leasing</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {form.ownership === 'leased' && (
                    <>
                      <div>
                        <Label className="text-xs">Leasinggesellschaft</Label>
                        <Input value={form.leasing_company} onChange={e => setField('leasing_company', e.target.value)} data-testid="vehicle-leasing-company" />
                      </div>
                      <div>
                        <Label className="text-xs">Leasingende</Label>
                        <Input type="date" value={form.leasing_end} onChange={e => setField('leasing_end', e.target.value)} data-testid="vehicle-leasing-end" />
                      </div>
                    </>
                  )}
                </div>

                <div className="mt-4">
                  <Label className="text-xs">Fuhrpark-Status</Label>
                  <Select value={form.fleet_status || '_none'} onValueChange={v => setField('fleet_status', v === '_none' ? '' : v)}>
                    <SelectTrigger data-testid="vehicle-fleet-status"><SelectValue placeholder="Keine Angabe" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_none">— keine Angabe —</SelectItem>
                      <SelectItem value="in_service">In Betrieb</SelectItem>
                      <SelectItem value="service_pending">Wartet auf Service</SelectItem>
                      <SelectItem value="out_of_service">Außer Betrieb</SelectItem>
                      <SelectItem value="sold">Verkauft</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </>
          )}
        </div>

        <div>
          <Label>Ausstattung (komma-getrennt)</Label>
          <Input value={form.equipment} onChange={e => setField('equipment', e.target.value)} placeholder="Beamer, Whiteboard, …" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label>Status</Label>
            <Select value={form.status} onValueChange={v => setField('status', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Aktiv</SelectItem>
                <SelectItem value="inactive">Inaktiv</SelectItem>
                <SelectItem value="blocked">Gesperrt</SelectItem>
                <SelectItem value="maintenance">Wartung</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between pt-6">
            <Label htmlFor="req-app">Buchung freigabepflichtig</Label>
            <Switch id="req-app" checked={form.requires_approval} onCheckedChange={v => setField('requires_approval', v)}
              data-testid="res-requires-approval" />
          </div>
          {t === 'room' && (
            <>
              <div className="flex items-center justify-between">
                <Label htmlFor="allow-cat">Catering erlauben</Label>
                <Switch id="allow-cat" checked={form.allow_catering} onCheckedChange={v => setField('allow_catering', v)} />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="splitable">Teilbarer Raum</Label>
                <Switch id="splitable" checked={form.is_splitable} onCheckedChange={v => setField('is_splitable', v)}
                  data-testid="res-is-splitable" />
              </div>
            </>
          )}
        </div>

        {t === 'room' && form.is_splitable && (
          <div className="border border-[#E2E4E0] rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <Label>Teilbereiche (max. 3)</Label>
              <Button size="sm" variant="outline" onClick={addSub} data-testid="res-add-sub">
                <Plus className="w-3 h-3 mr-1" /> Bereich
              </Button>
            </div>
            {subs.length === 0 && <div className="text-xs text-[#9CA3AF]">Noch kein Teilbereich.</div>}
            {subs.map((s, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 mb-2" data-testid={`res-sub-row-${i}`}>
                <Input className="col-span-2" value={s.sub_id} onChange={e => setSubs(p => p.map((x, ix) => ix === i ? { ...x, sub_id: e.target.value } : x))} />
                <Input className="col-span-5" value={s.name} placeholder="Name" onChange={e => setSubs(p => p.map((x, ix) => ix === i ? { ...x, name: e.target.value } : x))} />
                <Input className="col-span-3" type="number" placeholder="Kap." value={s.capacity || ''} onChange={e => setSubs(p => p.map((x, ix) => ix === i ? { ...x, capacity: e.target.value ? Number(e.target.value) : null } : x))} />
                <Button className="col-span-2" variant="ghost" size="icon" onClick={() => setSubs(p => p.filter((_, ix) => ix !== i))}>
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <div>
          <Label>Notizen</Label>
          <Textarea value={form.notes} onChange={e => setField('notes', e.target.value)} rows={2} />
        </div>

        <DialogFooter className="flex items-center justify-between">
          <div>
            {editing && (
              <Button variant="destructive" onClick={onDelete} data-testid="res-delete-btn">Löschen</Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => onClose(false)}>Abbrechen</Button>
            <Button onClick={submit} data-testid="res-save-btn">Speichern</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
