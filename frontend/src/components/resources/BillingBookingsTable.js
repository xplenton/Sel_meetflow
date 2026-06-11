/**
 * Iter 330 — Buchungen mit Positionen (klappbar) + Multi-Select-Sammelrechnung.
 *
 * Ersetzt die bisherigen zwei separaten Karten ("Summe abrechenbar" mit
 * aggregierten Lines + "Einzel-Buchungen mit Betrag") durch eine
 * einheitliche Tabelle:
 *
 *  - Jede Zeile = 1 Buchung (Datum, Titel, Ressource, KS, Σ)
 *  - Klick auf Pfeil → Klappt Positionen der Buchung auf
 *  - Pro Buchung: "Einzelrechnung" Button → erstellt Single-Invoice
 *  - Header-Checkbox + Pro-Zeilen-Checkboxen → "Sammelrechnung aus Auswahl"
 *    Button erstellt eine Aggregat-Rechnung über die gewählten Buchungen.
 *  - "Alle als Sammelrechnung" → wie bisher Sammelrechnung über die gesamte
 *    gefilterte Periode (Kostenstelle + Datumsbereich).
 */
import { useState, useMemo } from 'react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator } from '../ui/dropdown-menu';
import { ChevronRight, ChevronDown, FileText, Save, Receipt, ArrowUpDown, ArrowUp, ArrowDown, X, Search, MoreHorizontal, FileSpreadsheet, FileDown } from 'lucide-react';
import { openAuthedFile } from '../../lib/authedDownload';

function _fmtMoney(n, currency = 'EUR') {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: currency || 'EUR' }).format(Number(n || 0));
}
function _fmtDt(s) {
  if (!s) return '';
  try { return new Date(s).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  catch { return s.slice(0, 10); }
}

export default function BillingBookingsTable({
  aggregate,
  onSaveSingle,        // (bookingId) => void
  onSaveSelection,     // (bookingIds[]) => void
  onSaveAllAggregate,  // () => void   (uses current filter as before)
  onSaveCateringAggregate,
  onOpenSammelrechnungPdf,
  onOpenCateringAggregatePdf,
  onOpenDatevCsv,
  onOpenGenericCsv,
}) {
  const bookings = aggregate?.bookings || [];
  const currency = aggregate?.currency || 'EUR';

  const [expanded, setExpanded] = useState(() => new Set());
  const [selected, setSelected] = useState(() => new Set());

  // Iter 331 — Power-User-Filter + Sort
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('__all__');
  const [costCenterFilter, setCostCenterFilter] = useState('__all__');
  const [sortKey, setSortKey] = useState('start_at');   // start_at | subtotal | title
  const [sortDir, setSortDir] = useState('desc');       // asc | desc

  // Unique cost-center / resource-type options derived from the data
  const costCenterOptions = useMemo(() => {
    const s = new Set();
    bookings.forEach(b => { if (b.cost_center) s.add(b.cost_center); });
    return Array.from(s).sort();
  }, [bookings]);
  const typeOptions = useMemo(() => {
    const s = new Set();
    bookings.forEach(b => { if (b.resource_type) s.add(b.resource_type); });
    return Array.from(s).sort();
  }, [bookings]);

  const filteredBookings = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = bookings.filter(b => {
      if (typeFilter !== '__all__' && b.resource_type !== typeFilter) return false;
      if (costCenterFilter !== '__all__' && (b.cost_center || '') !== costCenterFilter) return false;
      if (q) {
        const hay = `${b.title || ''} ${b.resource_name || ''} ${b.cost_center || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    return filtered.sort((a, b) => {
      let av; let bv;
      if (sortKey === 'subtotal') { av = Number(a.subtotal || 0); bv = Number(b.subtotal || 0); }
      else if (sortKey === 'title') { av = (a.title || '').toLowerCase(); bv = (b.title || '').toLowerCase(); }
      else { av = a.start_at || ''; bv = b.start_at || ''; }
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }, [bookings, search, typeFilter, costCenterFilter, sortKey, sortDir]);

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('asc'); }
  };
  const SortIcon = ({ k }) => sortKey !== k
    ? <ArrowUpDown className="w-3 h-3 inline ml-1 opacity-40" />
    : sortDir === 'asc'
      ? <ArrowUp className="w-3 h-3 inline ml-1" />
      : <ArrowDown className="w-3 h-3 inline ml-1" />;

  const resetFilters = () => { setSearch(''); setTypeFilter('__all__'); setCostCenterFilter('__all__'); };
  const hasActiveFilters = search || typeFilter !== '__all__' || costCenterFilter !== '__all__';

  const toggleExpand = (id) => {
    setExpanded(prev => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };
  const toggleSelect = (id) => {
    setSelected(prev => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };
  const toggleSelectAll = () => {
    if (selected.size === filteredBookings.length) setSelected(new Set());
    else setSelected(new Set(filteredBookings.map(b => b.booking_id)));
  };

  const selTotal = useMemo(() => {
    return bookings
      .filter(b => selected.has(b.booking_id))
      .reduce((s, b) => s + Number(b.subtotal || 0), 0);
  }, [bookings, selected]);

  const openBookingPdf = (id) => openAuthedFile(`/resource-bookings/${id}/invoice.pdf`);

  if (bookings.length === 0) {
    return (
      <Card className="p-6" data-testid="billing-bookings-empty">
        <div className="flex items-end justify-end gap-2 mb-4 flex-wrap">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="outline" data-testid="billing-more-menu">
                <MoreHorizontal className="w-3.5 h-3.5 mr-1" /> Weitere Aktionen
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel>PDF Export (ohne speichern)</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => onOpenSammelrechnungPdf?.()}><FileText className="w-3.5 h-3.5 mr-2" /> Sammelrechnung PDF</DropdownMenuItem>
              <DropdownMenuItem onClick={() => onOpenCateringAggregatePdf?.()}><FileText className="w-3.5 h-3.5 mr-2" /> Nur Catering PDF</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>CSV Export</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => onOpenDatevCsv?.()}><FileSpreadsheet className="w-3.5 h-3.5 mr-2" /> DATEV-CSV</DropdownMenuItem>
              <DropdownMenuItem onClick={() => onOpenGenericCsv?.()}><FileDown className="w-3.5 h-3.5 mr-2" /> Generisch CSV</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="text-center text-sm text-[#9CA3AF]">
          Keine abrechenbaren Buchungen im gewählten Zeitraum.
          <div className="text-xs text-[#9CA3AF] mt-1">
            (Bereits in Entwurf/Freigabe enthaltene Buchungen werden ausgeblendet.)
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-4" data-testid="billing-bookings-table">
      <div className="flex items-end justify-between gap-3 flex-wrap mb-3">
        <div className="flex items-center gap-2">
          <Receipt className="w-4 h-4 text-[#4A5D4E]" />
          <div className="text-sm font-medium">Buchungen mit Positionen</div>
          <Badge variant="outline" className="text-[10px]">
            {filteredBookings.length === bookings.length
              ? `${bookings.length} Buchungen · ${_fmtMoney(aggregate.total || 0, currency)}`
              : `${filteredBookings.length} / ${bookings.length} Buchungen gefiltert`}
          </Badge>
        </div>

        <div className="flex flex-wrap gap-2">
          {/* Iter 332 — Selektion-Button: bei 1 Buchung = "Rechnung erstellen",
              bei >1 = "Sammelrechnung erstellen", damit der User klar sieht
              was passiert. Iter 338 — Klartext "erstellen" statt "aus Auswahl". */}
          <Button
            size="sm"
            disabled={selected.size === 0}
            onClick={() => onSaveSelection?.(Array.from(selected))}
            data-testid="billing-save-selection"
            className="bg-[#2C9A6E] hover:bg-[#218252] text-white disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5 mr-1" />
            {selected.size <= 1 ? 'Rechnung erstellen' : 'Sammelrechnung erstellen'}
            {selected.size > 0 && <> ({selected.size}) · {_fmtMoney(selTotal, currency)}</>}
          </Button>
          {/* Iter 366 — User-Request: separater „Sammelrechnung erstellen"-
              Outline-Button entfernt. Der grüne Button oben unterstützt
              Multi-Select bereits (Auswahl + Klick = Sammelrechnung). */}
          {/* Iter 332 — Export-Buttons sind jetzt unter "Weitere" zusammen-
              gefasst (statt eigenem Banner darüber). */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="outline" data-testid="billing-more-menu" title="Weitere Aktionen">
                <MoreHorizontal className="w-3.5 h-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel>Speichern</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => onSaveCateringAggregate?.()} data-testid="billing-menu-save-catering">
                <Save className="w-3.5 h-3.5 mr-2" /> Nur Catering als Rechnung
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>PDF Export (ohne speichern)</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => onOpenSammelrechnungPdf?.()} data-testid="billing-menu-pdf-aggregate">
                <FileText className="w-3.5 h-3.5 mr-2" /> Sammelrechnung PDF
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onOpenCateringAggregatePdf?.()} data-testid="billing-menu-pdf-catering">
                <FileText className="w-3.5 h-3.5 mr-2" /> Nur Catering PDF
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>CSV Export</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => onOpenDatevCsv?.()} data-testid="billing-menu-csv-datev">
                <FileSpreadsheet className="w-3.5 h-3.5 mr-2" /> DATEV-CSV
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onOpenGenericCsv?.()} data-testid="billing-menu-csv-generic">
                <FileDown className="w-3.5 h-3.5 mr-2" /> Generisch CSV
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Iter 331 — Filter-Leiste (Suche / Typ / Kostenstelle) */}
      <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 border-b border-[#F3F4F1]">
        <div className="relative flex-1 min-w-[200px] max-w-[320px]">
          <Search className="w-3.5 h-3.5 text-[#9CA3AF] absolute left-2 top-1/2 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Titel, Ressource oder KS suchen…"
            className="pl-7 h-8 text-xs"
            data-testid="billing-search"
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="h-8 w-[150px] text-xs" data-testid="billing-type-filter">
            <SelectValue placeholder="Ressourcen-Typ" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Alle Typen</SelectItem>
            {typeOptions.map(t => (
              <SelectItem key={t} value={t}>
                {t === 'room' ? 'Räume' : t === 'desk' ? 'Arbeitsplätze' : t === 'vehicle' ? 'Fahrzeuge' : t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={costCenterFilter} onValueChange={setCostCenterFilter}>
          <SelectTrigger className="h-8 w-[170px] text-xs" data-testid="billing-cc-filter">
            <SelectValue placeholder="Kostenstelle" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Alle Kostenstellen</SelectItem>
            {costCenterOptions.map(cc => (
              <SelectItem key={cc} value={cc}>{cc}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hasActiveFilters && (
          <Button size="sm" variant="ghost" onClick={resetFilters}
                  data-testid="billing-reset-filters" className="h-8 text-xs">
            <X className="w-3 h-3 mr-1" /> Filter zurücksetzen
          </Button>
        )}
      </div>

      {/* Iter 360 — Mobile-First: <md Card-Stack-Layout, ≥md klassische Tabelle.
         Damit verschwinden Horizontal-Scrolling und unleserliche Mini-Spalten
         auf dem Handy. Beide Layouts teilen sich denselben State (selected,
         expanded), daher kein Duplikat-Code für Selection-Logik. */}
      <div className="md:hidden space-y-2" data-testid="billing-bookings-cards">
        {filteredBookings.length === 0 ? (
          <div className="text-center text-xs text-[#9CA3AF] py-6">
            Keine Buchungen entsprechen den Filtern.
          </div>
        ) : filteredBookings.map(b => {
          const isOpen = expanded.has(b.booking_id);
          const isSelected = selected.has(b.booking_id);
          return (
            <div
              key={b.booking_id}
              className={`border rounded-lg p-3 ${isSelected ? 'bg-emerald-50/50 border-emerald-300' : 'border-[#E2E4E0] bg-white'}`}
              data-testid={`billing-booking-card-${b.booking_id}`}
            >
              <div className="flex items-start gap-2">
                <Checkbox
                  checked={isSelected}
                  onCheckedChange={() => toggleSelect(b.booking_id)}
                  data-testid={`billing-select-mobile-${b.booking_id}`}
                  className="mt-1"
                />
                <button
                  className="flex-1 text-left min-w-0"
                  onClick={() => toggleExpand(b.booking_id)}
                  data-testid={`billing-booking-card-toggle-${b.booking_id}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] text-[#6B7280]">{_fmtDt(b.start_at)}</div>
                    <div className="text-sm font-semibold text-[#1C1F1D] whitespace-nowrap">
                      {_fmtMoney(b.subtotal, currency)}
                    </div>
                  </div>
                  <div className="font-medium text-[#1C1F1D] text-sm mt-0.5 line-clamp-2">{b.title}</div>
                  <div className="text-xs text-[#6B7280] mt-0.5">{b.resource_name}</div>
                  {b.cost_center && (
                    <Badge variant="outline" className="text-[10px] mt-1">{b.cost_center}</Badge>
                  )}
                </button>
                <div className="text-[#9CA3AF] pt-1">
                  {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </div>
              </div>

              {isOpen && (
                <div className="mt-3 pt-3 border-t border-[#F3F4F1]"
                     data-testid={`billing-booking-card-lines-${b.booking_id}`}>
                  {(!b.lines || b.lines.length === 0) ? (
                    <div className="text-xs text-[#9CA3AF] italic">Keine Einzel-Positionen erfasst.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {b.lines.map((ln, i) => (
                        <div key={i} className="flex items-start justify-between gap-2 text-xs"
                             data-testid={`billing-booking-card-line-${b.booking_id}-${i}`}>
                          <div className="min-w-0 flex-1">
                            <Badge variant="outline" className="text-[9px] mr-1">
                              {ln.kind === 'km' ? 'Fahrt' : 'Catering'}
                            </Badge>
                            <span className="text-[#1C1F1D]">{ln.label}</span>
                            <div className="text-[10px] text-[#9CA3AF]">
                              {ln.quantity} {ln.unit || ''} × {_fmtMoney(ln.unit_price, currency)}
                            </div>
                          </div>
                          <div className="font-medium whitespace-nowrap">{_fmtMoney(ln.subtotal, currency)}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-2 mt-3 pt-2 border-t border-[#F3F4F1]">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => openBookingPdf(b.booking_id)}
                  data-testid={`billing-pdf-mobile-${b.booking_id}`}
                  className="flex-1 h-9"
                >
                  <FileText className="w-3.5 h-3.5 mr-1" /> PDF
                </Button>
                <Button
                  size="sm"
                  onClick={() => onSaveSingle?.(b.booking_id)}
                  data-testid={`billing-save-single-mobile-${b.booking_id}`}
                  className="flex-1 h-9 bg-[#2C9A6E] hover:bg-[#218252] text-white"
                >
                  <Save className="w-3.5 h-3.5 mr-1" /> Rechnung
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-[#6B7280] border-b border-[#E2E4E0]">
            <tr>
              <th className="py-2 px-2 w-[36px]">
                <Checkbox
                  data-testid="billing-select-all"
                  checked={selected.size > 0 && selected.size === filteredBookings.length}
                  onCheckedChange={toggleSelectAll}
                />
              </th>
              <th className="py-2 px-2 w-[28px]"></th>
              <th className="py-2 px-2 cursor-pointer select-none hover:text-[#1C1F1D]"
                  onClick={() => toggleSort('start_at')}
                  data-testid="billing-sort-date">
                Datum <SortIcon k="start_at" />
              </th>
              <th className="py-2 px-2 cursor-pointer select-none hover:text-[#1C1F1D]"
                  onClick={() => toggleSort('title')}
                  data-testid="billing-sort-title">
                Titel <SortIcon k="title" />
              </th>
              <th className="py-2 px-2">Ressource</th>
              <th className="py-2 px-2">Kostenstelle</th>
              <th className="py-2 px-2 text-right cursor-pointer select-none hover:text-[#1C1F1D]"
                  onClick={() => toggleSort('subtotal')}
                  data-testid="billing-sort-amount">
                Betrag <SortIcon k="subtotal" />
              </th>
              <th className="py-2 px-2 text-right w-[210px]">Aktion</th>
            </tr>
          </thead>
          <tbody data-testid="billing-bookings-rows">
            {filteredBookings.map(b => {
              const isOpen = expanded.has(b.booking_id);
              const isSelected = selected.has(b.booking_id);
              return (
                <>
                  <tr
                    key={b.booking_id}
                    className={`border-b border-[#F3F4F1] hover:bg-[#F8F8F6] cursor-pointer ${isSelected ? 'bg-emerald-50/50' : ''}`}
                    data-testid={`billing-booking-row-${b.booking_id}`}
                    onClick={() => toggleExpand(b.booking_id)}
                  >
                    <td className="py-2 px-2" onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={() => toggleSelect(b.booking_id)}
                        data-testid={`billing-select-${b.booking_id}`}
                      />
                    </td>
                    <td className="py-2 px-2 text-[#9CA3AF]">
                      {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    </td>
                    <td className="py-2 px-2 text-[#6B7280] whitespace-nowrap">{_fmtDt(b.start_at)}</td>
                    <td className="py-2 px-2 font-medium text-[#1C1F1D]">{b.title}</td>
                    <td className="py-2 px-2 text-[#6B7280]">{b.resource_name}</td>
                    <td className="py-2 px-2">
                      {b.cost_center && <Badge variant="outline" className="text-[10px]">{b.cost_center}</Badge>}
                    </td>
                    <td className="py-2 px-2 text-right font-medium whitespace-nowrap">
                      {_fmtMoney(b.subtotal, currency)}
                    </td>
                    <td className="py-2 px-2 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => openBookingPdf(b.booking_id)}
                          data-testid={`billing-pdf-${b.booking_id}`}
                          title="Einzel-Rechnungs-PDF (Vorschau)"
                        >
                          <FileText className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => onSaveSingle?.(b.booking_id)}
                          data-testid={`billing-save-single-${b.booking_id}`}
                          className="text-emerald-700"
                          title="Rechnung für diese Buchung erstellen"
                        >
                          <Save className="w-3.5 h-3.5 mr-1" /> Rechnung
                        </Button>
                      </div>
                    </td>
                  </tr>

                  {isOpen && (
                    <tr className="border-b border-[#F3F4F1] bg-[#FBFBFA]"
                        data-testid={`billing-booking-lines-${b.booking_id}`}>
                      <td colSpan={8} className="px-6 py-3">
                        {(!b.lines || b.lines.length === 0) ? (
                          <div className="text-xs text-[#9CA3AF] italic">Keine Einzel-Positionen erfasst.</div>
                        ) : (
                          <table className="w-full text-xs">
                            <thead className="text-left text-[#9CA3AF]">
                              <tr>
                                <th className="py-1 pr-3">Position</th>
                                <th className="py-1 pr-3 text-right">Menge</th>
                                <th className="py-1 pr-3">Einheit</th>
                                <th className="py-1 pr-3 text-right">Einzelpreis</th>
                                <th className="py-1 pr-3 text-right">Summe</th>
                              </tr>
                            </thead>
                            <tbody>
                              {b.lines.map((ln, i) => (
                                <tr key={i} data-testid={`billing-booking-line-${b.booking_id}-${i}`}>
                                  <td className="py-1 pr-3">
                                    <Badge variant="outline" className="text-[9px] mr-2">
                                      {ln.kind === 'km' ? 'Fahrt' : 'Catering'}
                                    </Badge>
                                    {ln.label}
                                  </td>
                                  <td className="py-1 pr-3 text-right">{ln.quantity}</td>
                                  <td className="py-1 pr-3">{ln.unit || ''}</td>
                                  <td className="py-1 pr-3 text-right">{_fmtMoney(ln.unit_price, currency)}</td>
                                  <td className="py-1 pr-3 text-right font-medium">{_fmtMoney(ln.subtotal, currency)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
