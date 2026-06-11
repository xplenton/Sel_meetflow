import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card } from '../components/ui/card';
import { Building2, Sofa, Car, Inbox, RefreshCcw, Check, X, Settings, Utensils, CalendarRange, Receipt } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';
import BookingDialog from '../components/resources/BookingDialog';
import CateringInbox from '../components/resources/CateringInbox';
import OccupancyOverview from '../components/resources/OccupancyOverview';
import CateringCancelDialog from '../components/resources/CateringCancelDialog';
import QuickBookSlotPicker from '../components/resources/QuickBookSlotPicker';
import BillingPanel from '../components/resources/BillingPanel';
import ManualInvoiceDialog from '../components/resources/ManualInvoiceDialog';
import { describeResource, describeBookingUser } from '../lib/bookingLabels';
import usePullToRefresh from '../hooks/usePullToRefresh';
import PullToRefreshIndicator from '../components/PullToRefreshIndicator';

const TYPE_TABS = [
  { key: 'rooms', type: 'room', label: 'Räume', icon: Building2 },
  { key: 'desks', type: 'desk', label: 'Arbeitsplätze', icon: Sofa },
  { key: 'vehicles', type: 'vehicle', label: 'Fahrzeuge', icon: Car },
];

export default function ResourcesPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const activeTab = params.get('tab') || 'rooms';
  const [caps, setCaps] = useState([]);
  const [resources, setResources] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [pendingBookings, setPendingBookings] = useState([]);
  const [availSnapshot, setAvailSnapshot] = useState({});
  const [bookingFor, setBookingFor] = useState(null);  // resource to book
  const [loading, setLoading] = useState(false);
  const [manualInvoicePrefill, setManualInvoicePrefill] = useState(null);  // {title, recipient_name, cost_center, lines, notes}
  // Iter 324 — track which booking IDs currently have an approve/reject
  // request in flight. Rapidly clicking either button used to fire 2-3
  // POST /approve calls; the second one returned 400/409 because the
  // booking had already transitioned, surfacing a misleading error toast.
  const [decidingIds, setDecidingIds] = useState(() => new Set());

  const can = (c) => caps.includes(c);
  const canManage = can('resources.manage');
  const canApprove = can('resources.approve');
  const canProcessCatering = can('catering.process');

  // Iter 356 — Hybrid endpoint: snapshot + slot-picker bookings in ONE call.
  // - Without resource_ids: global snapshot (used on page mount + 60s tick)
  // - With resource_ids: scoped snapshot + bookings_by_resource so the slot
  //   picker can use the same data the badge derives from → no drift.
  const [availBookings, setAvailBookings] = useState({});
  // Track whether the SCOPED call has completed for the current resource set,
  // so slot pickers know to use prefetched data instead of firing their own.
  const [availLoaded, setAvailLoaded] = useState(false);
  const reloadAvailability = (ids = null) => {
    const q = ids && ids.length ? `?resource_ids=${ids.join(',')}` : '';
    api.get(`/resource-availability${q}`)
      .then(({ data }) => {
        setAvailSnapshot(data.snapshot || {});
        if (data.bookings_by_resource) {
          setAvailBookings(data.bookings_by_resource);
          if (ids && ids.length) setAvailLoaded(true);
        }
      })
      .catch(() => {});
  };
  useEffect(() => {
    api.get('/user/permissions').then(({ data }) => setCaps(data.capabilities || [])).catch(() => {});
    reloadAvailability();
    const t = setInterval(() => reloadAvailability(), 60000);
    const onFocus = () => reloadAvailability();
    window.addEventListener('focus', onFocus);
    return () => { clearInterval(t); window.removeEventListener('focus', onFocus); };
  }, []);

  // Whenever resources change (tab switch), refetch scoped availability
  // for those resources so the slot pickers don't each fire their own call.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (resources && resources.length) {
      setAvailLoaded(false);
      reloadAvailability(resources.map(r => r.resource_id));
    }
  }, [resources]);

  const fetchResources = async (type) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/resources?type=${type}`);
      // For splitable rooms, also fetch children for the booking dialog target list.
      const enriched = await Promise.all(data.map(async (r) => {
        if (r.is_splitable) {
          try {
            const detail = await api.get(`/resources/${r.resource_id}`);
            return { ...r, children: detail.data.children || [] };
          } catch { return r; }
        }
        return r;
      }));
      setResources(enriched);
      // Iter 264 — Bei leerer Liste keine Fehlermeldung mehr (nur die UI-Empty-State-Info)
    } catch (e) {
      // Iter 264/266/268 — 401/403/404 sind keine "echten" Fehler, nur leere Anzeige
      // 401 wird vom api.js Interceptor bereits über /auth/refresh probiert;
      // schlägt das fehl, redirected der Route-Guard. Hier nur silent fallback.
      // Netzwerk-Fehler oder 5xx zeigen klare Server-Meldung.
      const code = e?.response?.status;
      const raw = e?.response?.data?.detail;
      if (code === 401 || code === 403 || code === 404) {
        setResources([]);
      } else if (!e?.response) {
        toast.error('Server nicht erreichbar — Netzwerk prüfen oder erneut versuchen.');
      } else {
        toast.error((typeof raw === 'string' ? raw : raw?.detail) || 'Konnte Ressourcen nicht laden');
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchMyBookings = async () => {
    try {
      const { data } = await api.get('/resource-bookings?mine_only=true');
      setBookings(data || []);
    } catch { setBookings([]); }
  };

  const fetchPending = async () => {
    try {
      const { data } = await api.get('/resource-bookings?status=pending_approval');
      setPendingBookings(data || []);
    } catch { setPendingBookings([]); }
  };

  // Tab-driven loading
  useEffect(() => {
    if (TYPE_TABS.find(t => t.key === activeTab)) {
      fetchResources(TYPE_TABS.find(t => t.key === activeTab).type);
    } else if (activeTab === 'mine') {
      fetchMyBookings();
    } else if (activeTab === 'approvals') {
      fetchPending();
    }
  }, [activeTab]);

  const changeTab = (k) => setParams({ tab: k });

  const decideBooking = async (bk, decision) => {
    if (decidingIds.has(bk.booking_id)) return;  // Iter 324 — guard against double-click
    setDecidingIds(prev => {
      const n = new Set(prev);
      n.add(bk.booking_id);
      return n;
    });
    try {
      await api.post(`/resource-bookings/${bk.booking_id}/approve`, { decision });
      toast.success(decision === 'approve' ? 'Freigegeben' : 'Abgelehnt');
      fetchPending();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler');
    } finally {
      setDecidingIds(prev => {
        const n = new Set(prev);
        n.delete(bk.booking_id);
        return n;
      });
    }
  };

  const showInvoice = async (bk) => {
    try {
      // Polished A4 PDF — opens in new tab, fallback to JSON alert
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/resource-bookings/${bk.booking_id}/invoice.pdf`;
      window.open(url, '_blank');
    } catch (e) {
      toast.error('Konnte Rechnung nicht laden');
    }
  };

  // Iter 294 — open the configurable manual-invoice dialog with the booking's
  // catering + km positions prefilled. User can still edit, pick template,
  // set tax/discount and persist as a tracked invoice.
  const createInvoiceFromBooking = async (bk) => {
    try {
      const { data } = await api.get(`/resource-bookings/${bk.booking_id}/invoice`);
      const prefill = {
        title: `${data.title || 'Rechnung'} — ${data.resource_name || ''}`.trim(),
        recipient_name: bk.booked_for_name || bk.user_name || bk.user_email || '',
        cost_center: data.cost_center || '',
        account: data.account || '',
        notes: `Buchung ${bk.booking_id}`,
        lines: (data.lines || []).map(l => ({
          label: l.label,
          quantity: l.quantity,
          unit: l.unit || '',
          unit_price: l.unit_price,
        })),
      };
      if (!prefill.lines.length) {
        toast.error('Keine abrechenbaren Positionen (Catering oder km) für diese Buchung');
        return;
      }
      setManualInvoicePrefill(prefill);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Konnte Buchung nicht laden');
    }
  };

  const activeTypeTab = TYPE_TABS.find(t => t.key === activeTab);

  // Iter 358 — Pull-to-Refresh: gleicher Hook wie News/Tasks/Chat.
  // Lädt sowohl die aktuelle Ressourcen-Liste als auch das Hybrid-Snapshot
  // neu, damit Belegungs-Badges und Slot-Grids im selben Atemzug frisch sind.
  const ptr = usePullToRefresh({
    onRefresh: async () => {
      if (activeTypeTab) await fetchResources(activeTypeTab.type);
      else if (activeTab === 'mine') await fetchMyBookings();
      else if (activeTab === 'approvals') await fetchPending();
      reloadAvailability(resources.map(r => r.resource_id));
    },
  });

  return (
    <div className="min-h-screen flex bg-[#FAFBF9]">
      <Sidebar />
      <main {...ptr.bind} className="flex-1 px-4 sm:px-6 lg:px-10 pt-14 md:pt-20 pb-6 ml-0 md:ml-[260px] overflow-x-hidden touch-pan-y" data-testid="resources-page">
        <PullToRefreshIndicator pullPx={ptr.pullPx} refreshing={ptr.refreshing} threshold={ptr.threshold} />
        <header className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>Ressourcen buchen</h1>
            <p className="text-xs text-[#6B7280]">Räume, Arbeitsplätze, Fahrzeuge und Catering — alles an einem Ort.</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => {
            if (activeTypeTab) fetchResources(activeTypeTab.type);
            else if (activeTab === 'mine') fetchMyBookings();
            else if (activeTab === 'approvals') fetchPending();
          }} data-testid="resources-refresh">
            <RefreshCcw className="w-4 h-4 mr-1" /> Aktualisieren
          </Button>
        </header>

        <Tabs value={activeTab} onValueChange={changeTab}>
          {/* Iter 337 — Mobile: horizontal scroll statt vieler Zeilen. flex-nowrap +
              overflow-x-auto verhindert dass die 7+ Tabs den halben Bildschirm
              fressen. h-auto bleibt damit Badges Platz haben. */}
          <TabsList className="flex flex-nowrap gap-1 mb-4 h-auto overflow-x-auto sm:flex-wrap justify-start sm:justify-center w-full" data-testid="resources-tabs">
            {TYPE_TABS.map(t => (
              <TabsTrigger key={t.key} value={t.key} data-testid={`tab-${t.key}`}>
                <t.icon className="w-4 h-4 mr-1" /> {t.label}
              </TabsTrigger>
            ))}
            <TabsTrigger value="mine" data-testid="tab-mine">
              <Inbox className="w-4 h-4 mr-1" /> Meine Buchungen
            </TabsTrigger>
            <TabsTrigger value="occupancy" data-testid="tab-occupancy">
              <CalendarRange className="w-4 h-4 mr-1" /> Belegung
            </TabsTrigger>
            {canApprove && (
              <TabsTrigger value="approvals" data-testid="tab-approvals">
                <Check className="w-4 h-4 mr-1" /> Freigaben
                {pendingBookings.length > 0 && (
                  <Badge className="ml-1 bg-[#C87967] text-white">{pendingBookings.length}</Badge>
                )}
              </TabsTrigger>
            )}
            {canProcessCatering && (
              <TabsTrigger value="catering-inbox" data-testid="tab-catering-inbox">
                <Utensils className="w-4 h-4 mr-1" /> Catering-Inbox
              </TabsTrigger>
            )}
            {can('bookings.invoice') && (
              <TabsTrigger value="billing" data-testid="tab-billing">
                <Receipt className="w-4 h-4 mr-1" /> Rechnungen
              </TabsTrigger>
            )}
          </TabsList>

          {TYPE_TABS.map(tt => (
            <TabsContent key={tt.key} value={tt.key} className="mt-0">
              {/* Iter 264 — Lageplan wandert in den BookingDialog (Klick auf "Buchen"). 
                   Sub-View-Toggle entfernt, Liste ist die einzige Ansicht hier. */}
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid={`resources-list-${tt.type}`}>
                {loading && <div className="text-sm text-[#9CA3AF]">Lade …</div>}
                {!loading && resources.length === 0 && (
                  <div className="text-sm text-[#6B7280] col-span-full text-center py-12 border border-dashed border-[#E2E4E0] rounded-lg bg-[#FAFBF9]" data-testid={`resources-empty-${tt.type}`}>
                    <div className="flex justify-center mb-3">
                      <tt.icon className="w-8 h-8 text-[#9CA3AF]" />
                    </div>
                    <div className="font-medium text-[#1C1F1D]">Keine {tt.label.toLowerCase()} vorhanden</div>
                    <div className="text-xs text-[#9CA3AF] mt-1">
                      {canManage
                        ? `Lege ${tt.label.toLowerCase()} in der Verwaltung an, damit sie hier zur Buchung erscheinen.`
                        : `Bitte wende dich an deine/n Administrator/in, um ${tt.label.toLowerCase()} anzulegen.`}
                    </div>
                    {canManage && (
                      <div className="mt-3">
                        <Button size="sm" variant="outline" onClick={() => navigate('/admin?tab=resources-admin')} data-testid={`resources-empty-cta-${tt.type}`}>
                          Zur Verwaltung
                        </Button>
                      </div>
                    )}
                  </div>
                )}
                {resources.map(r => {
                  const av = availSnapshot[r.resource_id];
                  return (
                  <Card key={r.resource_id} className="p-4 hover:shadow-md transition-shadow" data-testid={`resource-card-${r.resource_id}`}>
                    <div className="flex items-start justify-between mb-1">
                      <div>
                        <div className="font-medium text-[#1C1F1D]">{r.name}</div>
                        <div className="text-xs text-[#6B7280]">{[r.location, r.building, r.floor].filter(Boolean).join(' · ')}</div>
                      </div>
                      <StatusBadge status={r.status} />
                    </div>
                    {/* Availability indicator */}
                    {av ? (
                      av.busy_now ? (
                        <div className="text-[10px] text-rose-700 mt-1" data-testid={`avail-busy-${r.resource_id}`}>
                          ● Belegt bis {new Date(av.next_free).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      ) : av.next_busy ? (
                        <div className="text-[10px] text-amber-700 mt-1" data-testid={`avail-soon-${r.resource_id}`}>
                          ● Frei bis {new Date(av.next_busy).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      ) : (
                        <div className="text-[10px] text-emerald-700 mt-1" data-testid={`avail-free-${r.resource_id}`}>● Jetzt frei</div>
                      )
                    ) : (
                      <div className="text-[10px] text-emerald-700 mt-1" data-testid={`avail-free-${r.resource_id}`}>● Jetzt frei</div>
                    )}
                    {r.capacity && <div className="text-xs text-[#6B7280]">Kapazität: {r.capacity}</div>}
                    {r.seats && <div className="text-xs text-[#6B7280]">{r.seats} Sitzplätze · {r.license_plate}</div>}
                    {r.desk_number && <div className="text-xs text-[#6B7280]">Desk-Nr: {r.desk_number}</div>}
                    {r.equipment?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {r.equipment.slice(0, 4).map((e, idx) => <Badge key={`${r.resource_id}-eq-${idx}`} variant="outline" className="text-[10px]">{e}</Badge>)}
                      </div>
                    )}
                    {r.is_splitable && (
                      <Badge variant="outline" className="mt-2 text-[10px] border-[#4A5D4E] text-[#4A5D4E]">Teilbar ({r.children?.length || 0} Bereiche)</Badge>
                    )}
                    {/* Iter 365 — Pro Teilbereich Status + Reservierungs-Zeitfenster.
                       Auf einen Blick sichtbar, welcher Bereich belegt ist und
                       welche frei zur Buchung sind. */}
                    {r.is_splitable && r.children?.length > 0 && (
                      <div className="mt-2 space-y-0.5 text-[11px]" data-testid={`split-status-${r.resource_id}`}>
                        {r.children.map(c => {
                          const childAv = availSnapshot[c.resource_id];
                          const childBookings = availBookings[c.resource_id] || [];
                          const nowMs = Date.now();
                          // Aktuelle oder nächste relevante Reservierung
                          const upcoming = childBookings
                            .map(b => ({ ...b, _s: new Date(b.start_at), _e: new Date(b.end_at) }))
                            .filter(b => b._e.getTime() > nowMs)
                            .sort((a, b) => a._s - b._s)[0];
                          // Anzeigename: „Saal — Bereich A" → „Bereich A"
                          const shortName = c.name?.includes('—')
                            ? c.name.split('—').pop().trim()
                            : (c.name || c.resource_id);
                          const fmtT = (d) => d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
                          if (childAv?.busy_now && upcoming) {
                            return (
                              <div key={c.resource_id}
                                   className="flex items-center gap-1.5 text-rose-700"
                                   data-testid={`split-child-busy-${c.resource_id}`}>
                                <span className="w-1.5 h-1.5 rounded-full bg-rose-500 inline-block flex-shrink-0" />
                                <span className="font-medium">{shortName}:</span>
                                <span className="truncate">belegt {fmtT(upcoming._s)}–{fmtT(upcoming._e)}</span>
                              </div>
                            );
                          }
                          if (upcoming) {
                            return (
                              <div key={c.resource_id}
                                   className="flex items-center gap-1.5 text-amber-700"
                                   data-testid={`split-child-reserved-${c.resource_id}`}>
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 inline-block flex-shrink-0" />
                                <span className="font-medium">{shortName}:</span>
                                <span className="truncate">reserviert {fmtT(upcoming._s)}–{fmtT(upcoming._e)}</span>
                              </div>
                            );
                          }
                          return (
                            <div key={c.resource_id}
                                 className="flex items-center gap-1.5 text-emerald-700"
                                 data-testid={`split-child-free-${c.resource_id}`}>
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block flex-shrink-0" />
                              <span className="font-medium">{shortName}:</span>
                              <span>frei</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {r.requires_approval && (
                      <Badge variant="outline" className="mt-2 ml-1 text-[10px] border-amber-500 text-amber-700">Freigabepflicht</Badge>
                    )}
                    <div className="flex gap-2 mt-3 flex-wrap">
                      {/* Iter 355 — Mobile-UX: Buchen-Button greift volle Breite auf
                         Handy für eine fette Touch-Zielfläche. Auf sm+ wieder
                         kompakt nebeneinander. */}
                      <Button
                        size="sm"
                        onClick={() => setBookingFor(r)}
                        disabled={r.status !== 'active'}
                        data-testid={`book-${r.resource_id}`}
                        className="w-full sm:w-auto h-10 sm:h-9 text-sm"
                      >
                        Buchen
                      </Button>
                    </div>
                    {/* Iter 250 — Quick-Book-Slot-Picker (heute, 8-20h) */}
                    {/* Iter 261 — bei Fahrzeugen wird km-Stand + Ziel inline erfasst */}
                    {/* Iter 356 — Hybrid-Daten: Slot-Picker bekommt die Bookings direkt
                       von der Page (selber Fetch wie das Badge) → kein eigener
                       Roundtrip mehr und garantiert konsistent. */}
                    {r.status === 'active' && !r.is_splitable && (
                      <QuickBookSlotPicker
                        resourceId={r.resource_id}
                        resourceName={r.name}
                        resourceType={r.type}
                        currentMileage={r.mileage}
                        prefetchedBookings={availLoaded ? (availBookings[r.resource_id] || []) : undefined}
                        onBooked={() => {
                          if (activeTypeTab) fetchResources(activeTypeTab.type);
                          reloadAvailability(resources.map(rr => rr.resource_id));
                        }}
                        onOpenFullDialog={() => setBookingFor(r)}
                      />
                    )}
                  </Card>
                  );
                })}
              </div>
            </TabsContent>
          ))}

          <TabsContent value="mine" className="mt-0">
            <BookingsTable bookings={bookings} onShowInvoice={showInvoice} onCreateInvoice={createInvoiceFromBooking} canBill={can('bookings.invoice')} canCreateInvoice={can('invoices.create_manual')} onRefresh={fetchMyBookings} />
          </TabsContent>

          <TabsContent value="occupancy" className="mt-0">
            <OccupancyOverview onBook={(r) => setBookingFor(r)} />
          </TabsContent>

          {canApprove && (
            <TabsContent value="approvals" className="mt-0">
              <div className="space-y-2" data-testid="approvals-list">
                {pendingBookings.length === 0 && <div className="text-sm text-[#9CA3AF] text-center py-12">Keine offenen Freigaben.</div>}
                {pendingBookings.map(bk => {
                  const resLabel = describeResource(bk);
                  const userLabel = describeBookingUser(bk);
                  return (
                  <Card key={bk.booking_id} className="p-3 flex items-center justify-between gap-3 flex-wrap" data-testid={`approval-row-${bk.booking_id}`}>
                    <div>
                      <div className="font-medium text-[#1C1F1D]">{bk.title}</div>
                      {/* Iter 328 — Klartext-Ressource für Genehmiger
                          (statt nackter resource_id). */}
                      {resLabel && (
                        <div className="text-xs text-[#4A5D4E]" data-testid={`approval-resource-${bk.booking_id}`}>
                          {resLabel}
                        </div>
                      )}
                      <div className="text-xs text-[#6B7280]">
                        {fmtDt(bk.start_at)} – {fmtDt(bk.end_at)}
                      </div>
                      {/* Iter 328 — User-Klartext */}
                      {userLabel && (
                        <div className="text-xs text-[#6B7280] mt-0.5" data-testid={`approval-user-${bk.booking_id}`}>
                          {userLabel}
                        </div>
                      )}
                      {bk.purpose && <div className="text-xs text-[#6B7280] mt-1">Zweck: {bk.purpose}</div>}
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm"
                              onClick={() => decideBooking(bk, 'approve')}
                              disabled={decidingIds.has(bk.booking_id)}
                              data-testid={`approve-${bk.booking_id}`}>
                        <Check className="w-4 h-4 mr-1" /> Freigeben
                      </Button>
                      <Button size="sm" variant="destructive"
                              onClick={() => decideBooking(bk, 'reject')}
                              disabled={decidingIds.has(bk.booking_id)}
                              data-testid={`reject-${bk.booking_id}`}>
                        <X className="w-4 h-4 mr-1" /> Ablehnen
                      </Button>
                    </div>
                  </Card>
                  );
                })}
              </div>
            </TabsContent>
          )}

          {canProcessCatering && (
            <TabsContent value="catering-inbox" className="mt-0">
              <CateringInbox />
            </TabsContent>
          )}
          {can('bookings.invoice') && (
            <TabsContent value="billing" className="mt-0">
              <BillingPanel />
            </TabsContent>
          )}
        </Tabs>

        {bookingFor && (
          <BookingDialog
            resource={bookingFor}
            onClose={(refresh) => {
              setBookingFor(null);
              if (refresh && activeTypeTab) fetchResources(activeTypeTab.type);
              if (refresh && activeTab === 'mine') fetchMyBookings();
            }}
          />
        )}

        <ManualInvoiceDialog
          open={!!manualInvoicePrefill}
          onClose={() => setManualInvoicePrefill(null)}
          onCreated={() => { fetchMyBookings(); }}
          prefill={manualInvoicePrefill}
        />
      </main>
    </div>
  );
}


function StatusBadge({ status }) {
  const map = {
    active: { label: 'Aktiv', cls: 'border-emerald-300 bg-emerald-50 text-emerald-700' },
    inactive: { label: 'Inaktiv', cls: 'border-zinc-300 bg-zinc-50 text-zinc-600' },
    blocked: { label: 'Gesperrt', cls: 'border-rose-300 bg-rose-50 text-rose-700' },
    maintenance: { label: 'Wartung', cls: 'border-amber-300 bg-amber-50 text-amber-700' },
  };
  const m = map[status] || map.active;
  return <Badge variant="outline" className={`${m.cls} text-[10px]`}>{m.label}</Badge>;
}


function BookingsTable({ bookings, onShowInvoice, onCreateInvoice, canBill, canCreateInvoice, onRefresh }) {
  const [cancelCateringFor, setCancelCateringFor] = useState(null);
  if (!bookings.length) {
    return <div className="text-sm text-[#9CA3AF] text-center py-12">Keine Buchungen.</div>;
  }
  const downloadICS = (bk) => {
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/resource-bookings/${bk.booking_id}/ical`, '_blank');
  };
  const checkIn = async (bk) => {
    try {
      await api.post(`/resource-bookings/${bk.booking_id}/check-in`);
      toast.success('Check-in erfolgreich');
      if (onRefresh) await onRefresh();
    }
    catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };
  const checkOut = async (bk) => {
    const mileage = bk.mileage_before != null ? window.prompt('End-Kilometerstand?') : null;
    try {
      await api.post(`/resource-bookings/${bk.booking_id}/check-out`,
        mileage ? { mileage_after: Number(mileage) } : {});
      toast.success('Check-out erfolgreich');
      if (onRefresh) await onRefresh();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };
  // Iter 286 — Catering-Status Helper (Anforderer-View)
  const _cateringPalette = (s) => ({
    requested: { label: 'Angefragt', cls: 'bg-slate-100 text-slate-700 border-slate-300' },
    confirmed: { label: 'Bestätigt', cls: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
    rejected: { label: 'Abgelehnt', cls: 'bg-rose-100 text-rose-700 border-rose-300' },
    in_progress: { label: 'In Bearbeitung', cls: 'bg-amber-100 text-amber-800 border-amber-300' },
    delivered: { label: 'Geliefert', cls: 'bg-blue-100 text-blue-800 border-blue-300' },
    completed: { label: 'Abgeschlossen', cls: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
    cancelled: { label: 'Storniert', cls: 'bg-slate-100 text-slate-500 border-slate-300 line-through' },
  })[s] || { label: s, cls: 'bg-slate-100 text-slate-600 border-slate-300' };
  return (
    <>
    {/* Iter 337 — Mobile: card layout (table is unusable below 600 px even
        with horizontal scroll). Desktop keeps the dense table view. */}
    <div className="sm:hidden space-y-2" data-testid="my-bookings-cards">
      {bookings.map(bk => {
        const resLabel = describeResource(bk);
        const userLabel = describeBookingUser(bk);
        const cat = bk.catering_status ? _cateringPalette(bk.catering_status) : null;
        return (
          <Card key={bk.booking_id} className="p-3 space-y-2" data-testid={`my-booking-card-${bk.booking_id}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="font-medium text-[#1C1F1D] text-sm truncate">{bk.title}</div>
                {resLabel && (
                  <div className="text-[11px] text-[#4A5D4E] mt-0.5 break-words" data-testid={`m-booking-resource-${bk.booking_id}`}>
                    {resLabel}
                  </div>
                )}
                {userLabel && (
                  <div className="text-[10px] text-[#6B7280] break-words" data-testid={`m-booking-user-${bk.booking_id}`}>
                    {userLabel}
                  </div>
                )}
              </div>
              <BookingStatus status={bk.status} />
            </div>
            <div className="text-xs text-[#6B7280]">{fmtDt(bk.start_at)} – {fmtDt(bk.end_at)}</div>
            {cat && (
              <div data-testid={`m-catering-status-${bk.booking_id}`}>
                <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${cat.cls}`}>
                  <Utensils className="w-2.5 h-2.5" /> Catering: {cat.label}
                </span>
                {bk.catering_status === 'rejected' && bk.catering_rejection_reason && (
                  <div className="text-[10px] text-rose-700 mt-0.5">Grund: {bk.catering_rejection_reason}</div>
                )}
              </div>
            )}
            <div className="flex gap-1.5 flex-wrap pt-1">
              <Button size="sm" variant="ghost" className="h-8 px-2 text-xs" onClick={() => downloadICS(bk)} data-testid={`m-ics-${bk.booking_id}`}>.ics</Button>
              {bk.status === 'confirmed' && !bk.checked_in_at && (
                <Button size="sm" variant="outline" className="h-8 px-2 text-xs" onClick={() => checkIn(bk)} data-testid={`m-checkin-${bk.booking_id}`}>Check-in</Button>
              )}
              {bk.checked_in_at && !bk.checked_out_at && (
                <Button size="sm" variant="outline" className="h-8 px-2 text-xs" onClick={() => checkOut(bk)} data-testid={`m-checkout-${bk.booking_id}`}>Check-out</Button>
              )}
              {canBill && (bk.catering_request_id || bk.mileage_after) && (
                <Button size="sm" variant="outline" className="h-8 px-2 text-xs" onClick={() => onShowInvoice(bk)} data-testid={`m-invoice-${bk.booking_id}`}>PDF</Button>
              )}
              {canCreateInvoice && (bk.catering_request_id || bk.mileage_after) && (
                <Button size="sm" className="h-8 px-2 text-xs bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" onClick={() => onCreateInvoice(bk)} data-testid={`m-create-invoice-${bk.booking_id}`}>
                  <Receipt className="w-3 h-3 mr-1" /> Rechnung
                </Button>
              )}
              {bk.catering_request_id && !['cancelled', 'completed'].includes(bk.status) && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 px-2 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                  onClick={() => setCancelCateringFor({ request_id: bk.catering_request_id })}
                  data-testid={`m-cancel-catering-${bk.booking_id}`}
                >
                  <X className="w-3 h-3 mr-1" /> Catering
                </Button>
              )}
            </div>
          </Card>
        );
      })}
    </div>

    <div className="hidden sm:block border border-[#E2E4E0] rounded-lg overflow-x-auto" data-testid="my-bookings-table">
      <table className="w-full text-sm min-w-[600px]">
        <thead className="bg-[#F3F4F1] text-left text-xs text-[#6B7280]">
          <tr><th className="px-3 py-2">Titel</th><th className="px-3 py-2">Zeitraum</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Aktionen</th></tr>
        </thead>
        <tbody>
          {bookings.map(bk => {
            const resLabel = describeResource(bk);
            const userLabel = describeBookingUser(bk);
            return (
            <tr key={bk.booking_id} className="border-t border-[#E2E4E0]" data-testid={`my-booking-row-${bk.booking_id}`}>
              <td className="px-3 py-2">
                <div className="font-medium text-[#1C1F1D]">{bk.title}</div>
                {/* Iter 325 — Klartext-Ressource (Auto: Name + Kennzeichen;
                    Raum/Desk: Name + Gebäude + Etage) */}
                {resLabel && (
                  <div className="text-[11px] text-[#4A5D4E] mt-0.5" data-testid={`booking-resource-${bk.booking_id}`}>
                    {resLabel}
                  </div>
                )}
                {/* Iter 325 — User-Klartext */}
                {userLabel && (
                  <div className="text-[10px] text-[#6B7280]" data-testid={`booking-user-${bk.booking_id}`}>
                    {userLabel}
                  </div>
                )}
                {/* Iter 286 — Catering-Status sichtbar für Anforderer */}
                {bk.catering_status && (
                  <div className="mt-1" data-testid={`catering-status-${bk.booking_id}`}>
                    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${_cateringPalette(bk.catering_status).cls}`}>
                      <Utensils className="w-2.5 h-2.5" /> Catering: {_cateringPalette(bk.catering_status).label}
                    </span>
                    {bk.catering_status === 'rejected' && bk.catering_rejection_reason && (
                      <div className="text-[10px] text-rose-700 mt-0.5">Grund: {bk.catering_rejection_reason}</div>
                    )}
                  </div>
                )}
              </td>
              {/* Iter 366 — „Zeitraum"-Spalte sauber formatieren:
                  - Gleicher Tag (Standardfall): Datum oben, „HH:MM–HH:MM" darunter
                  - Mehrtägig: zwei Zeilen „dd.MM HH:MM" mit Pfeil
                  Kein automatischer Umbruch am „–" mehr. */}
              <td className="px-3 py-2 whitespace-nowrap" data-testid={`booking-range-${bk.booking_id}`}>
                {renderBookingRange(bk.start_at, bk.end_at)}
              </td>
              <td className="px-3 py-2"><BookingStatus status={bk.status} /></td>
              <td className="px-3 py-2">
                <div className="flex gap-1 flex-wrap justify-end">
                  <Button size="sm" variant="ghost" onClick={() => downloadICS(bk)} title="ICS-Export" data-testid={`ics-${bk.booking_id}`}>.ics</Button>
                  {bk.status === 'confirmed' && !bk.checked_in_at && (
                    <Button size="sm" variant="outline" onClick={() => checkIn(bk)} data-testid={`checkin-${bk.booking_id}`}>Check-in</Button>
                  )}
                  {bk.checked_in_at && !bk.checked_out_at && (
                    <Button size="sm" variant="outline" onClick={() => checkOut(bk)} data-testid={`checkout-${bk.booking_id}`}>Check-out</Button>
                  )}
                  {canBill && (bk.catering_request_id || bk.mileage_after) && (
                    <Button size="sm" variant="outline" onClick={() => onShowInvoice(bk)} data-testid={`invoice-${bk.booking_id}`}>PDF</Button>
                  )}
                  {canCreateInvoice && (bk.catering_request_id || bk.mileage_after) && (
                    <Button size="sm" onClick={() => onCreateInvoice(bk)} data-testid={`create-invoice-${bk.booking_id}`}
                      className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white">
                      <Receipt className="w-3 h-3 mr-1" /> Rechnung
                    </Button>
                  )}
                  {bk.catering_request_id && !['cancelled', 'completed'].includes(bk.status) && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                      onClick={() => setCancelCateringFor({ request_id: bk.catering_request_id })}
                      data-testid={`cancel-catering-${bk.booking_id}`}
                      title="Catering stornieren"
                    >
                      <X className="w-3 h-3 mr-1" /> Catering
                    </Button>
                  )}
                </div>
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    {cancelCateringFor && (
      <CateringCancelDialog
        request={cancelCateringFor}
        onClose={(refresh) => {
          setCancelCateringFor(null);
          if (refresh && onRefresh) onRefresh();
        }}
      />
    )}
    </>
  );
}


function BookingStatus({ status }) {
  const map = {
    confirmed: { label: 'Bestätigt', cls: 'border-emerald-300 bg-emerald-50 text-emerald-700' },
    pending_approval: { label: 'Wartet auf Freigabe', cls: 'border-amber-300 bg-amber-50 text-amber-700' },
    cancelled: { label: 'Storniert', cls: 'border-zinc-300 bg-zinc-50 text-zinc-500' },
    completed: { label: 'Abgeschlossen', cls: 'border-blue-300 bg-blue-50 text-blue-700' },
    no_show: { label: 'No-Show', cls: 'border-rose-300 bg-rose-50 text-rose-700' },
  };
  const m = map[status] || map.confirmed;
  return <Badge variant="outline" className={`${m.cls} text-[10px]`}>{m.label}</Badge>;
}


function fmtDt(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

// Iter 366 — Zeitraum-Spalte in „Meine Buchungen" hat zuvor je nach Spalten-
// Breite hässlich auf das „–" umgebrochen. Wir rendern stattdessen einen
// kompakten zweizeiligen Block: Datum + Uhrzeit-Bereich, bei mehrtägigen
// Buchungen ein „Start → Ende"-Block.
function renderBookingRange(startIso, endIso) {
  if (!startIso || !endIso) return fmtDt(startIso || endIso);
  try {
    const s = new Date(startIso);
    const e = new Date(endIso);
    const sameDay = s.toDateString() === e.toDateString();
    const fmtDate = (d) => d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' });
    const fmtTime = (d) => d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    if (sameDay) {
      return (
        <div className="leading-tight">
          <div className="text-[#1C1F1D]">{fmtDate(s)}</div>
          <div className="text-[#6B7280] text-xs tabular-nums">{fmtTime(s)}–{fmtTime(e)}</div>
        </div>
      );
    }
    return (
      <div className="leading-tight text-xs tabular-nums">
        <div className="text-[#1C1F1D]">{fmtDate(s)} {fmtTime(s)}</div>
        <div className="text-[#6B7280]">→ {fmtDate(e)} {fmtTime(e)}</div>
      </div>
    );
  } catch { return `${fmtDt(startIso)} – ${fmtDt(endIso)}`; }
}
