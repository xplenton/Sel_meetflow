import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { Users } from 'lucide-react';

export function BookingForUserPicker({ bookableUsers, bookedForUserId, onChange }) {
  if (!bookableUsers.length) return null;
  return (
    <div data-testid="booking-for-user-section" className="rounded-lg border border-[#E2E4E0] bg-white p-3">
      <Label className="flex items-center gap-2">
        <Users className="w-4 h-4 text-[#4A5D4E]" />
        Buchen für
      </Label>
      <Select value={bookedForUserId || 'self'} onValueChange={(v) => onChange(v === 'self' ? '' : v)}>
        <SelectTrigger data-testid="booking-for-user-select" className="mt-1">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="self" data-testid="booking-for-self">Mich selbst</SelectItem>
          {bookableUsers.map(u => (
            <SelectItem key={u.user_id} value={u.user_id} data-testid={`booking-for-user-${u.user_id}`}>
              {u.name || u.email}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {bookedForUserId && (
        <p className="text-[11px] text-[#6B7280] mt-1">
          Diese Buchung wird im Namen des gewählten Kollegen angelegt.
        </p>
      )}
    </div>
  );
}

export function BookingTargetPicker({ resource, targets, target, onChange, availability }) {
  if (!(resource.is_splitable && targets.length > 1)) return null;
  // Iter 339 — Issue #3: für teilbare Räume zeige direkt in der Auswahl ob ein
  // Bereich frei oder belegt ist. `availability` ist { id: { state, conflicts }}.
  const fmtTime = (iso) => {
    try { return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }); }
    catch { return ''; }
  };
  const _renderLabel = (t) => {
    const a = availability?.[t.id];
    if (!a || a.state === 'unknown') return t.name;
    if (a.state === 'free') return `${t.name} · ✅ frei`;
    const slot = a.conflicts?.[0];
    if (slot) {
      const allPending = a.conflicts.every(c => c.status === 'pending_approval');
      const tag = allPending ? '⏳' : '⛔';
      return `${t.name} · ${tag} belegt ${fmtTime(slot.start_at)}–${fmtTime(slot.end_at)}`;
    }
    return `${t.name} · belegt`;
  };
  const current = availability?.[target];
  return (
    <div data-testid="booking-target-picker">
      <Label>Bereich</Label>
      <Select value={target} onValueChange={onChange}>
        <SelectTrigger data-testid="booking-target-select"><SelectValue>{_renderLabel(targets.find(t => t.id === target) || targets[0])}</SelectValue></SelectTrigger>
        <SelectContent>
          {targets.map(t => {
            const a = availability?.[t.id];
            const color = a?.state === 'free'
              ? 'text-emerald-700'
              : a?.state === 'busy'
                ? (a.conflicts?.every(c => c.status === 'pending_approval') ? 'text-amber-700' : 'text-rose-700')
                : 'text-[#1C1F1D]';
            return (
              <SelectItem key={t.id} value={t.id} data-testid={`booking-target-${t.id}`}>
                <span className={color}>{_renderLabel(t)}</span>
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
      {current?.state === 'busy' && (
        <p className="text-[10px] text-amber-700 mt-1">
          Tipp: oben einen freien Bereich wählen.
        </p>
      )}
    </div>
  );
}
