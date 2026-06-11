import { Button } from '../../ui/button';
import { AlertTriangle, Loader2, Sparkles, CheckCircle2, Info } from 'lucide-react';
import { fmt } from './bookingHelpers';

export default function BookingConflictsPanel({
  checking, conflicts, suggestions, start, end,
  onAcceptSuggestion,
  // Iter 338 — Issue 3+4 props (optional, ignored if not supplied)
  onSwitchTarget,            // (newTargetId) => void
  targets = [],              // [{id,name}, ...] from useBookingDialog
  currentTarget,             // current selected target id
  onForceSubmitPending,      // () => void — calls submit with allow_pending_overlap=true
}) {
  if (checking) {
    return (
      <div className="flex items-center gap-2 text-xs text-[#6B7280]" data-testid="booking-conflict-checking">
        <Loader2 className="w-3 h-3 animate-spin" /> Konflikt-Prüfung laeuft…
      </div>
    );
  }
  if (conflicts.length > 0) {
    // Iter 338 — Issue 3: if ALL conflicts are pending-approval bookings,
    // treat it as a soft warning with override option instead of a hard block.
    const allPending = conflicts.every(c => c.status === 'pending_approval');
    // Iter 338 — Issue 4: when the user picked the parent ("komplett") of a
    // teilbarer Raum, surface every sub-room that doesn't appear in the
    // conflict list as a one-click switch. We only suggest alternatives if
    // NO conflict points at the current target itself — otherwise the
    // alternative sub-rooms would inherit the parent block anyway.
    const conflictedResourceIds = new Set(conflicts.map(c => c.resource_id).filter(Boolean));
    const currentTargetIsBlocked = conflictedResourceIds.has(currentTarget);
    const freeAlternatives = currentTargetIsBlocked
      ? []   // current resource itself is booked → siblings inherit the block, no use suggesting
      : (targets || []).filter(t => t.id !== currentTarget && !conflictedResourceIds.has(t.id));

    return (
      <div className={`rounded-lg border p-3 text-xs space-y-2 ${
        allPending ? 'border-amber-300 bg-amber-50' : 'border-rose-300 bg-rose-50'
      }`} data-testid="booking-conflicts">
        <div className={`flex items-center gap-2 font-medium ${
          allPending ? 'text-amber-900' : 'text-rose-900'
        }`}>
          {allPending
            ? <><Info className="w-4 h-4" /> Bereich bereits beantragt — noch nicht freigegeben</>
            : <><AlertTriangle className="w-4 h-4" /> Zeitfenster nicht verfügbar</>}
        </div>
        <ul className={`ml-5 list-disc ${allPending ? 'text-amber-800' : 'text-rose-800'}`}>
          {conflicts.slice(0, 3).map((c, i) => (
            <li key={i}>
              {c.title || c.reason || 'Buchung'} · {fmt(c.start_at)} – {fmt(c.end_at)}
              {c.status === 'pending_approval' && ' · noch nicht freigegeben'}
            </li>
          ))}
        </ul>

        {allPending && onForceSubmitPending && (
          <div className="pt-2 border-t border-amber-200">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="bg-white border-amber-400 text-amber-900 hover:bg-amber-100"
              onClick={onForceSubmitPending}
              data-testid="booking-force-pending"
            >
              Trotzdem Buchung beantragen
            </Button>
            <div className="text-[10px] text-amber-700 mt-1">
              Die Buchung geht erneut in die Freigabe — die Genehmigung entscheidet, welche Anfrage angenommen wird.
            </div>
          </div>
        )}

        {freeAlternatives.length > 0 && onSwitchTarget && (
          <div className="pt-2 border-t border-amber-200">
            <div className={`flex items-center gap-1 font-medium mb-1 ${
              allPending ? 'text-amber-900' : 'text-rose-900'
            }`}>
              <Sparkles className="w-3 h-3" /> Freie Bereiche / Alternativen
            </div>
            <div className="flex flex-wrap gap-1">
              {freeAlternatives.slice(0, 4).map((t) => (
                <Button
                  key={t.id}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="bg-white text-xs"
                  onClick={() => onSwitchTarget(t.id)}
                  data-testid={`booking-switch-target-${t.id}`}
                >
                  {t.name}
                </Button>
              ))}
            </div>
          </div>
        )}

        {suggestions.length > 0 && (
          <div className="pt-2 border-t border-amber-200">
            <div className={`flex items-center gap-1 font-medium mb-1 ${
              allPending ? 'text-amber-900' : 'text-rose-900'
            }`}>
              <Sparkles className="w-3 h-3" /> Nächste freie Slots
            </div>
            <div className="flex flex-wrap gap-1">
              {suggestions.map((s, i) => (
                <Button key={i} type="button" size="sm" variant="outline"
                        onClick={() => onAcceptSuggestion(s)}
                        data-testid={`booking-suggestion-${i}`}
                        className="bg-white">
                  {fmt(s.start_at)} – {fmt(s.end_at).slice(-5)}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }
  if (start && end && new Date(end) > new Date(start)) {
    return (
      <div className="inline-flex items-center gap-1 text-xs text-emerald-700" data-testid="booking-slot-free">
        <CheckCircle2 className="w-4 h-4" /> Zeitfenster verfügbar
      </div>
    );
  }
  return null;
}
