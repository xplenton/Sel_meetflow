import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Plus, Trash2, Utensils, AlertTriangle, Minus } from 'lucide-react';
import AttachmentPicker from '../AttachmentPicker';

/**
 * Catering-Section aus BookingDialog (iter 260 refactor).
 * Keine eigene State-Verwaltung — alles Controlled-Props vom Parent.
 *
 * Iter 322 (Thema 2) — `leadTimeWarning` zeigt eine Warnung, wenn die
 * Buchung innerhalb der Vorlaufzeit eines ausgewählten Catering-Artikels
 * liegt (Standard 60 Min., pro Artikel im Catering-Admin überschreibbar).
 * Die Warnung blockiert die Buchung nicht — sie informiert nur.
 */
export default function BookingCateringSection({
  enabled,
  onToggle,
  items,
  availableItems,
  onAddLine,
  onUpdateLine,
  onRemoveLine,
  total,
  totalQty,
  attachments,
  onAttachmentsChange,
  leadTimeWarning,
}) {
  return (
    <div className="border border-[#E2E4E0] rounded-lg p-3">
      <button
        type="button"
        onClick={onToggle}
        data-testid="booking-toggle-catering"
        className="flex items-center gap-2 text-sm font-medium text-[#1C1F1D]"
      >
        <Utensils className="w-4 h-4" />
        Catering {enabled ? 'aktiv' : 'hinzufügen'}
      </button>
      {enabled && (
        <div className="mt-3 space-y-2">
          {items.map((line, idx) => {
            const it = availableItems.find(i => i.item_id === line.item_id);
            const sub = it ? (it.price || 0) * (line.quantity || 0) : 0;
            return (
              <div
                key={idx}
                className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-2"
                data-testid={`booking-catering-line-${idx}`}
              >
                <Select value={line.item_id} onValueChange={v => onUpdateLine(idx, { item_id: v })}>
                  <SelectTrigger className="w-full sm:flex-1 sm:min-w-[180px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {availableItems.map(av => (
                      <SelectItem key={av.item_id} value={av.item_id}>
                        {av.name} · {av.price.toFixed(2)} EUR / {av.unit}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {/* Iter 353 — Mobile-Layout: zweite Zeile zeigt Menge | Subtotal + Löschen
                   nebeneinander mit justify-between, damit das Eingabefeld nicht
                   neben der Trash-Schaltfläche eingequetscht wird. Desktop bleibt
                   unverändert (eine Zeile). */}
                <div className="flex items-center justify-between gap-2 sm:justify-end sm:flex-shrink-0">
                  {/* Iter 354 — Touch-friendly Stepper: −/+ links/rechts des Mengen-Inputs.
                     Tippen erspart Tastatur, beschleunigt Catering auf Mobile spürbar.
                     Tastatur-Eingabe bleibt voll funktionsfähig. */}
                  <div className="inline-flex items-center rounded-md border border-[#E2E4E0] overflow-hidden">
                    <button
                      type="button"
                      onClick={() => {
                        const cur = Number(line.quantity);
                        const next = Number.isFinite(cur) && cur > 1 ? cur - 1 : 1;
                        onUpdateLine(idx, { quantity: next });
                      }}
                      className="px-2 h-9 text-[#4A5D4E] hover:bg-[#F2F4EF] active:bg-[#E2E4E0] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      disabled={Number(line.quantity) <= 1}
                      aria-label="Menge verringern"
                      data-testid={`booking-catering-qty-dec-${idx}`}
                    >
                      <Minus className="w-3.5 h-3.5" />
                    </button>
                    <Input
                      type="number"
                      min="1"
                      value={line.quantity}
                      className="w-12 sm:w-14 text-center border-0 rounded-none focus-visible:ring-0 focus-visible:ring-offset-0 h-9 px-0
                                 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      /* Iter 339 — Issue #5: vorher klemmten wir Math.max(1, Number(v))
                         direkt im onChange. Bei leerem Feld lieferte Number("") = 0
                         und der Klemm setzte das Feld sofort wieder auf 1, sodass
                         der User die alte erste Ziffer nicht überschreiben konnte.
                         Jetzt geben wir leere/ungeparste Werte unverändert weiter
                         (für die Anzeige) und klemmen erst beim onBlur. */
                      onChange={e => {
                        const raw = e.target.value;
                        if (raw === '') {
                          onUpdateLine(idx, { quantity: '' });
                        } else {
                          const n = Number(raw);
                          onUpdateLine(idx, { quantity: Number.isFinite(n) ? n : raw });
                        }
                      }}
                      onBlur={e => {
                        const n = Number(e.target.value);
                        onUpdateLine(idx, { quantity: Number.isFinite(n) && n >= 1 ? Math.floor(n) : 1 });
                      }}
                      data-testid={`booking-catering-qty-${idx}`}
                      aria-label="Menge"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const cur = Number(line.quantity);
                        const next = Number.isFinite(cur) && cur >= 1 ? cur + 1 : 1;
                        onUpdateLine(idx, { quantity: next });
                      }}
                      className="px-2 h-9 text-[#4A5D4E] hover:bg-[#F2F4EF] active:bg-[#E2E4E0] transition-colors"
                      aria-label="Menge erhöhen"
                      data-testid={`booking-catering-qty-inc-${idx}`}
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <span className="text-xs text-[#6B7280] min-w-[64px] text-right">{sub.toFixed(2)} EUR</span>
                  <Button variant="ghost" size="icon" onClick={() => onRemoveLine(idx)} data-testid={`booking-catering-remove-${idx}`}>
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            );
          })}
          <Button
            variant="outline"
            size="sm"
            onClick={onAddLine}
            data-testid="booking-catering-add"
            disabled={!availableItems.length}
          >
            <Plus className="w-3 h-3 mr-1" /> Artikel hinzufügen
          </Button>
          {items.length > 0 && (
            <div
              className="flex items-center justify-between bg-[#F3F4F1] rounded px-3 py-2 text-sm font-medium"
              data-testid="catering-total"
            >
              <span>{totalQty} Position(en) gesamt</span>
              <span>{total.toFixed(2)} EUR</span>
            </div>
          )}
          {leadTimeWarning && (
            <div
              className="flex gap-2 items-start bg-[#FFF7E6] border border-[#F0C75A]/50 rounded-lg px-3 py-2.5 text-xs leading-relaxed"
              data-testid="catering-leadtime-warning"
              role="alert"
            >
              <AlertTriangle className="w-4 h-4 text-[#B26B00] shrink-0 mt-0.5" />
              <div className="flex-1 text-[#7A4D00]">
                <span className="font-semibold">Vorlaufzeit unterschritten:</span>{' '}
                "{leadTimeWarning.worst_item}" benötigt mindestens
                {' '}<span className="font-semibold">{leadTimeWarning.max_lead_human}</span> Vorlauf,
                die Besprechung startet in {' '}
                <span className="font-semibold">
                  {leadTimeWarning.mins_until_start < 0
                    ? 'der Vergangenheit'
                    : leadTimeWarning.mins_until_start < 60
                      ? `${leadTimeWarning.mins_until_start} Min.`
                      : `${Math.floor(leadTimeWarning.mins_until_start / 60)} Std.`}
                </span>. Bitte mit der Cafeteria Rücksprache halten, ob die Bestellung
                kurzfristig möglich ist.
              </div>
            </div>
          )}
          <div className="pt-2 border-t border-[#E2E4E0]">
            <div className="text-[10px] uppercase tracking-wider text-[#6B7280] mb-1">Anhänge (z.B. Teilnehmerliste)</div>
            <AttachmentPicker
              attachments={attachments}
              onChange={onAttachmentsChange}
              max={5}
              testId="booking-catering-attachments"
            />
          </div>
        </div>
      )}
    </div>
  );
}
