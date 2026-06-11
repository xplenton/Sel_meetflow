import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import api from '../../lib/api';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { Card } from '../ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Building2, Sofa, Car, Plus, Pencil, QrCode, Download, Map, Lock, BarChart3, Utensils, Book, Sparkles, Printer, CheckSquare, Square } from 'lucide-react';
import { toast } from 'sonner';
import ResourceEditorDialog from '../resources/ResourceEditorDialog';
import CateringItemsPanel from '../resources/CateringItemsPanel';
import FloorPlanView from '../resources/FloorPlanView';
import BlackoutEditorDialog from '../resources/BlackoutEditorDialog';
// Iter 297 — CostCenter/Accounts werden jetzt in Rechnungen-Setup → Stammdaten gepflegt
import ResourceReportsPanel from './ResourceReportsPanel';
import VehicleLogbookDialog from '../VehicleLogbookDialog';

/**
 * Admin panel for managing all resources (rooms / desks / vehicles), plus
 * catering items, floorplan editor and the reports/ERP-Export dashboard.
 *
 * Stammdaten (Konten/Kostenstellen/Kostenträger/Projekte) wurden in iter 297
 * vollständig nach Admin → System → Rechnungen-Setup verschoben und in
 * iter 303 hier entfernt.
 *
 * Lives at /admin?tab=resources-admin (Verwaltung -> Ressourcen).
 *
 * Mobile-first: Select dropdown <sm, tabs >=sm. All inner cards/tables
 * scroll horizontally to prevent overflow.
 */
export default function ResourcesAdminPanel() {
  const [tab, setTab] = useState('rooms');
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);
  const [creatingType, setCreatingType] = useState(null);
  const [qrData, setQrData] = useState(null);
  const [blackoutFor, setBlackoutFor] = useState(null);
  const [logbookFor, setLogbookFor] = useState(null);
  // Iter 371 — Multi-Select für QR-Bulk-Druck
  const [selectedIds, setSelectedIds] = useState(new Set());

  const type = { rooms: 'room', desks: 'desk', vehicles: 'vehicle' }[tab];

  const fetchList = async () => {
    if (!type) return;
    try {
      const { data } = await api.get(`/resources?type=${type}&include_children=true`);
      setItems(data || []);
      setSelectedIds(new Set()); // Reset auswahl bei Tab-Wechsel
    } catch (e) {
      toast.error('Konnte Ressourcen nicht laden');
    }
  };

  useEffect(() => { fetchList(); }, [tab]);

  const onClose = (refresh) => {
    setEditing(null);
    setCreatingType(null);
    if (refresh) fetchList();
  };

  const showQR = async (res) => {
    try {
      const { data } = await api.get(`/resources/${res.resource_id}/qr`);
      setQrData({ name: res.name, url: data.qr_code_url, deep: data.deep_link });
    } catch {
      toast.error('QR-Code-Erzeugung fehlgeschlagen');
    }
  };

  // Iter 371 — Multi-Select für QR-Bulk-Druck
  const toggleSelected = (id) => {
    setSelectedIds(prev => {
      const s = new Set(prev);
      if (s.has(id)) s.delete(id); else s.add(id);
      return s;
    });
  };
  const toggleSelectAll = () => {
    if (selectedIds.size === items.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(items.map(r => r.resource_id)));
  };
  const printQrBulk = async (ids) => {
    if (!ids || ids.length === 0) {
      toast.error('Bitte mindestens eine Ressource auswählen');
      return;
    }
    try {
      toast.info(`Erzeuge PDF für ${ids.length} QR-Code(s)…`);
      const res = await api.post('/resources-qr-bulk-pdf',
        { resource_ids: ids },
        { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `qr-codes-${new Date().toISOString().slice(0,10)}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success(`PDF mit ${ids.length} QR-Code(s) heruntergeladen`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'PDF-Erzeugung fehlgeschlagen');
    }
  };

  const exportCSV = async () => {
    try {
      const res = await api.get('/resource-bookings/export/csv', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = 'bookings.csv'; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('Export fehlgeschlagen');
    }
  };

  const exportXLSX = async () => {
    try {
      const res = await api.get('/resource-bookings/export/xlsx', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = 'bookings.xlsx'; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('XLSX-Export fehlgeschlagen');
    }
  };

  const seedDemo = async () => {
    if (!window.confirm(
      'Demo-Daten anlegen?\n\nDies erzeugt:\n• 12 Räume (inkl. teilbare + Catering)\n• 12 Arbeitsplätze\n• 10 Fahrzeuge (Benzin/Diesel/Elektro/Hybrid)\n• 15 Catering-Artikel\n• 10 Kostenstellen + 5 Konten\n• ~30 Beispiel-Buchungen über 14 Tage\n\nBestehende „Demo_"-Eintraege werden überschrieben.'
    )) return;
    try {
      toast.info('Lege Demo-Daten an…');
      const { data } = await api.post('/resources-seed-demo');
      toast.success(
        `Demo-Daten erstellt: ${data.created.rooms} Räume, ${data.created.desks} Desks, ${data.created.vehicles} Fahrzeuge, ${data.created.catering_items} Catering-Artikel, ${data.created.bookings} Buchungen`,
        { duration: 6000 }
      );
      fetchList();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Demo-Seed fehlgeschlagen');
    }
  };

  // Tab definitions for both mobile-Select and desktop-Tabs
  const TABS = [
    { value: 'rooms', label: 'Räume', icon: Building2 },
    { value: 'desks', label: 'Arbeitsplätze', icon: Sofa },
    { value: 'vehicles', label: 'Fahrzeuge', icon: Car },
    { value: 'catering', label: 'Catering-Artikel', icon: Utensils },
    { value: 'floorplan', label: 'Lageplan', icon: Map },
    { value: 'reports', label: 'Reports & Abrechnung', icon: BarChart3 },
  ];

  return (
    <div className="space-y-4" data-testid="resources-admin-panel">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold text-[#1C1F1D]">Ressourcen-Verwaltung</h2>
          <p className="text-[10px] text-[#6B7280]">Stammdaten · Catering · Lagepläne · Buchhaltung · Reports</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={seedDemo} data-testid="seed-demo-btn"
                  className="border-amber-400 text-amber-700 hover:bg-amber-50">
            <Sparkles className="w-4 h-4 mr-1" /> Demo-Daten
          </Button>
          <Button variant="outline" size="sm" onClick={exportCSV} data-testid="export-bookings-csv">
            <Download className="w-4 h-4 mr-1" /> Buchungen CSV
          </Button>
          <Button variant="outline" size="sm" onClick={exportXLSX} data-testid="export-bookings-xlsx">
            <Download className="w-4 h-4 mr-1" /> Buchungen XLSX
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        {/* Mobile: Select dropdown */}
        <div className="sm:hidden mb-2">
          <Select value={tab} onValueChange={setTab}>
            <SelectTrigger className="w-full" data-testid="admin-resources-mobile-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TABS.map(t => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {/* Desktop: Tabs */}
        <div className="hidden sm:block overflow-x-auto">
          <TabsList className="min-w-full justify-start w-max">
            {TABS.map(t => {
              const Icon = t.icon;
              return (
                <TabsTrigger key={t.value} value={t.value} data-testid={`admin-tab-${t.value}`}
                  className="whitespace-nowrap">
                  <Icon className="w-4 h-4 mr-1" /> {t.label}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </div>

        {['rooms', 'desks', 'vehicles'].map(t => (
          <TabsContent key={t} value={t}>
            <div className="flex justify-between items-center mb-3 gap-2 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap" data-testid="qr-bulk-toolbar">
                <Button size="sm" variant="ghost" onClick={toggleSelectAll}
                  data-testid="admin-select-all" className="text-xs">
                  {selectedIds.size === items.length && items.length > 0
                    ? <CheckSquare className="w-4 h-4 mr-1" />
                    : <Square className="w-4 h-4 mr-1" />}
                  {selectedIds.size === items.length && items.length > 0 ? 'Alle abwählen' : 'Alle wählen'}
                </Button>
                {selectedIds.size > 0 && (
                  <>
                    <span className="text-xs text-[#6B7280]">{selectedIds.size} ausgewählt</span>
                    <Button size="sm" variant="outline" onClick={() => printQrBulk(Array.from(selectedIds))}
                      data-testid="admin-print-qr-selected"
                      className="border-[#4A5D4E] text-[#4A5D4E] hover:bg-[#4A5D4E]/5">
                      <Printer className="w-4 h-4 mr-1" /> QR-Codes drucken ({selectedIds.size})
                    </Button>
                  </>
                )}
                {selectedIds.size === 0 && items.length > 0 && (
                  <Button size="sm" variant="outline" onClick={() => printQrBulk(items.map(r => r.resource_id))}
                    data-testid="admin-print-qr-all"
                    className="border-[#4A5D4E] text-[#4A5D4E] hover:bg-[#4A5D4E]/5">
                    <Printer className="w-4 h-4 mr-1" /> Alle QR-Codes drucken ({items.length})
                  </Button>
                )}
              </div>
              <Button size="sm" onClick={() => setCreatingType({ rooms: 'room', desks: 'desk', vehicles: 'vehicle' }[t])}
                data-testid={`admin-create-${t}`}>
                <Plus className="w-4 h-4 mr-1" /> Neu
              </Button>
            </div>
            <div className="space-y-2">
              {items.length === 0 && (
                <div className="text-sm text-[#9CA3AF] text-center py-8 border border-dashed border-[#E2E4E0] rounded-lg">
                  Keine Eintraege.
                </div>
              )}
              {items.map(r => (
                <Card key={r.resource_id} className="p-3 flex items-center justify-between flex-wrap gap-2" data-testid={`admin-row-${r.resource_id}`}>
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(r.resource_id)}
                      onChange={() => toggleSelected(r.resource_id)}
                      className="w-4 h-4 rounded border-[#E2E4E0] text-[#4A5D4E] focus:ring-[#4A5D4E] cursor-pointer flex-shrink-0"
                      data-testid={`admin-select-${r.resource_id}`}
                      title="Für QR-Bulk-Druck auswählen"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-[#1C1F1D] flex items-center flex-wrap gap-1">
                        <span>{r.name}</span>
                        {r.parent_resource_id && <Badge variant="outline" className="text-[10px]">Sub: {r.sub_id}</Badge>}
                        {r.is_splitable && <Badge variant="outline" className="text-[10px] border-[#4A5D4E] text-[#4A5D4E]">Teilbar</Badge>}
                        {r.requires_approval && <Badge variant="outline" className="text-[10px] border-amber-500 text-amber-700">Freigabepflicht</Badge>}
                        {r.drive_type && <Badge variant="outline" className="text-[10px] border-blue-400 text-blue-700">{r.drive_type}</Badge>}
                        {r.fuel_card && r.fuel_card_number && <Badge variant="outline" className="text-[10px]">Tankkarte: {r.fuel_card_number}</Badge>}
                      </div>
                      <div className="text-xs text-[#6B7280]">{[r.location, r.building, r.floor, r.license_plate, r.desk_number].filter(Boolean).join(' · ')}</div>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    {r.type === 'vehicle' && (
                      <Button size="sm" variant="ghost" onClick={() => setLogbookFor(r)}
                        data-testid={`admin-logbook-${r.resource_id}`} title="Fahrtenbuch">
                        <Book className="w-4 h-4" />
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => setBlackoutFor(r)}
                      data-testid={`admin-blackout-${r.resource_id}`} title="Sperrzeiten">
                      <Lock className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => showQR(r)} data-testid={`admin-qr-${r.resource_id}`} title="QR-Code">
                      <QrCode className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(r)} data-testid={`admin-edit-${r.resource_id}`} title="Bearbeiten">
                      <Pencil className="w-4 h-4" />
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          </TabsContent>
        ))}

        <TabsContent value="catering">
          <CateringItemsPanel canManage={true} />
        </TabsContent>

        <TabsContent value="floorplan">
          <div className="space-y-3">
            <div className="text-xs text-[#6B7280]">
              Lege eine <code>floor_plan_id</code> fest (z.B. „haus_b_2og") und ziehe Ressourcen aus der Liste auf den Plan.
              Hintergrundbild via Upload-Button oben.
            </div>
            <FloorplanEditTypeSwitcher />
          </div>
        </TabsContent>

        <TabsContent value="reports">
          <ResourceReportsPanel />
        </TabsContent>
      </Tabs>

      {(editing || creatingType) && (
        <ResourceEditorDialog resource={editing} type={creatingType} onClose={onClose} />
      )}

      {blackoutFor && (
        <BlackoutEditorDialog resource={blackoutFor} onClose={() => setBlackoutFor(null)} />
      )}

      {logbookFor && (
        <VehicleLogbookDialog vehicle={logbookFor} onClose={() => setLogbookFor(null)} />
      )}

      {qrData && typeof document !== 'undefined' && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" onClick={() => setQrData(null)}>
          <div className="bg-white rounded-xl p-6 max-w-sm w-full" onClick={e => e.stopPropagation()} data-testid="qr-modal">
            <div className="text-sm font-medium mb-2">{qrData.name}</div>
            <img src={qrData.url} alt="QR" className="w-full" />
            <div className="text-xs text-[#6B7280] mt-2 break-all">{qrData.deep}</div>
            <div className="flex gap-2 mt-3">
              <a href={qrData.url} download={`qr-${qrData.name}.png`} className="flex-1">
                <Button className="w-full" size="sm" variant="outline"><Download className="w-3 h-3 mr-1" /> PNG</Button>
              </a>
              <Button className="flex-1" size="sm" onClick={() => setQrData(null)}>Schließen</Button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}



/**
 * FloorplanEditTypeSwitcher (iter 241).
 * Erlaubt dem Admin, im Lageplan-Edit-Modus zwischen Räume/Arbeitsplätze/Fahrzeuge
 * zu wechseln, sodass jede Typ-Kategorie auf demselben Plan positioniert werden
 * kann.
 */
function FloorplanEditTypeSwitcher() {
  const [type, setType] = useState('desk');
  const labels = { desk: 'Arbeitsplätze', room: 'Räume', vehicle: 'Fahrzeuge' };
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2" data-testid="floorplan-edit-type-switcher">
        <span className="text-xs text-[#6B7280]">Typ:</span>
        {(['desk', 'room', 'vehicle']).map(t => (
          <Button key={t} size="sm" variant={type === t ? 'default' : 'outline'}
            onClick={() => setType(t)}
            data-testid={`floorplan-edit-type-${t}`}>
            {labels[t]}
          </Button>
        ))}
      </div>
      <FloorPlanView
        key={type}
        floorPlanId="default"
        editMode={true}
        resourceTypeFilter={type}
      />
    </div>
  );
}
